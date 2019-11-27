#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re

import config
import log_and_mail
import general_function

mount_point = ''


class MountError(Exception):
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return self.message


def get_storage_data(job_name, storage_data):
    ''' The function on the input gets the name of the job, as well as the dictionary with this particular storage.
    Then it checks all the necessary data for mounting this type of storage to the server. Returns:
        filtered dictionary - if successful
        Exception MyError with error text in case of problems.

    '''

    data_dict = {}

    storage = storage_data['storage']
    data_dict['storage'] = storage

    backup_dir = storage_data['backup_dir']
    data_dict['backup_dir'] = backup_dir

    err_message = ''

    if not storage in ('local', 's3'):
        host = storage_data.get('host')

        if not host:
            err_message = f"Field 'host' in job '{job_name}' for storage '{job_name}' can't be empty!"
        else:
            data_dict['host'] = host

    if not storage in ('local', 'nfs', 's3'):
        user = storage_data.get('user', '')
        password = storage_data.get('password', '')
        port = storage_data.get('port', '')

        if port:
            data_dict['port'] = port

        if not user:
            err_message = f"Field 'user' in job '{job_name}' for storage '{storage}' can't be empty!"
        else:
            data_dict['user'] = user

        if storage == 'scp':
            path_to_key = storage_data.get('path_to_key', '')
            if not (password or path_to_key):
                err_message = "At least one of the fields 'path_to_key' or 'password' must be filled in" + \
                              f" job '{job_name}' for storage '{storage}'!"
            else:
                if password:
                    data_dict['password'] = password

                if path_to_key:
                    data_dict['path_to_key'] = path_to_key
        else:
            if not password:
                err_message = f"Field 'password' in job '{job_name}' for storage '{storage}' can't be empty!"
            else:
                data_dict['password'] = password

    if storage == 'nfs':
        data_dict['extra_keys'] = storage_data.get('extra_keys', '')

    if storage == 'smb':
        share = storage_data.get('share', '')
        if not share:
            err_message = f"Field 'share' in job '{job_name}' for storage '{storage}' can't be empty!"
        else:
            data_dict['share'] = share

    if storage == 's3':
        bucketname = storage_data.get('bucket_name', '')

        if not bucketname:
            err_message = f"Field 'bucketname' in job '{job_name}' for storage '{storage}' can't be empty!"
        else:
            data_dict['bucket_name'] = bucketname
        data_dict['s3fs_opts'] = storage_data.get('s3fs_opts', '')
        data_dict['access_key_id'] = storage_data.get('access_key_id', '')
        data_dict['secret_access_key'] = storage_data.get('secret_access_key', '')

    if err_message:
        raise general_function.MyError(err_message)
    else:
        return data_dict


def get_mount_data(current_storage_data):
    ''' The function takes a dictionary with data from a specific storage. AT
    Returns an array of two dictionaries:
        dict_mount_data - data to mount:
        - list of packages required to mount storage
        - command to check if the system has the necessary packages to mount
        - command to mount storage
        pre_mount - contains information about the need for additional manipulations
            in the system before the packages are installed (required to install packages that are
            requires interactive mode). For example, it is necessary to answer the question concerning
            the ability to mount WebDAV resources to unprivileged users.
            Contains pairs of the form 'function name': 'function arguments'.

    '''

    global mount_point
    dist = general_function.get_dist()
    pre_mount = {}

    dict_mount_data = {}

    if re.match('(debian|ubuntu)', dist, re.I):
        family_os = 'deb'
        general_check_packet_cmd = 'dpkg -s'
    elif re.match('centos', dist, re.I):
        family_os = 'rpm'
        general_check_packet_cmd = 'rpm -q'
    else:
        raise MountError(f"This distribution of Linux:'{dist}' is not supported.")

    storage = current_storage_data.get('storage', '')
    backup_dir = current_storage_data.get('backup_dir', '')
    user = current_storage_data.get('user', '')
    host = current_storage_data.get('host', '')
    port = current_storage_data.get('port', '')
    password = current_storage_data.get('password', '')
    extra_keys = current_storage_data.get('extra_keys', '')
    share = current_storage_data.get('share', '')
    path_to_key = current_storage_data.get('path_to_key', '')
    bucket_name = current_storage_data.get('bucket_name', '')
    s3fs_opts = current_storage_data.get('s3fs_opts', '')
    s3fs_access_key_id = current_storage_data.get('access_key_id', '')
    s3fs_secret_access_key = current_storage_data.get('secret_access_key', '')

    if storage == 'scp':
        packets = ['openssh-client', 'sshfs', 'sshpass']
        mount_point = '/mnt/sshfs'

        if not port:
            port = '22'

        if not path_to_key:
            mount_cmd = f'echo "{password}" | sshfs -o StrictHostKeyChecking=no,password_stdin -p {port} {user}@{host}:{backup_dir} {mount_point} '
        else:
            mount_cmd = f'sshfs -o StrictHostKeyChecking=no,IdentityFile={path_to_key} -p {port} {user}@{host}:{backup_dir} {mount_point}'

    elif storage == 'ftp':
        packets = ['curlftpfs']
        mount_point = '/mnt/curlftpfs'
        mount_cmd = f'curlftpfs -o nonempty ftp://{user}:{password}@{host} {mount_point}'
    elif storage == 'smb':
        packets = ['cifs-utils']
        mount_point = '/mnt/smbfs'

        if not port:
            port = '445'

        mount_cmd = f'mount -t cifs -o port={port},noperm,username={user},password={password} //{host}/{share} {mount_point}'
    elif storage == 'nfs':
        if family_os == 'deb':
            packets = ['nfs-common']
        else:
            packets = ['nfs-utils']
        mount_point = '/mnt/nfs'
        mount_cmd = f'mount -t nfs {host}:{backup_dir} {mount_point} {extra_keys}'
    elif storage == 'webdav':
        packets = ['davfs2']
        mount_point = '/mnt/davfs'
        if not port:
            port = '443'

        str_auth = f"{host}:{port} {user} {password}\n"

        pre_mount['check_secrets'] = f'{str_auth}'

        mount_cmd = f"mount -t davfs {host}:{port} {mount_point}"
    elif storage == 's3':
        packets = ['']
        mount_point = '/mnt/s3'
        mount_cmd = f's3fs {bucket_name} {mount_point} {s3fs_opts}'

        if s3fs_access_key_id and s3fs_secret_access_key:
            pre_mount['check_s3fs_secrets'] = f'{bucket_name}:{s3fs_access_key_i}:{s3fs_secret_access_key}\n'
    else:
        mount_point = ''
        return [dict_mount_data, pre_mount]

    packets.append('fuse')
    dict_mount_data['type_storage'] = storage
    dict_mount_data['packets'] = packets
    dict_mount_data['check_cmd'] = general_check_packet_cmd
    dict_mount_data['mount_cmd'] = mount_cmd

    return [dict_mount_data, pre_mount]


def mount(current_storage_data):
    ''' A function that is responsible for directly mounting a particular storage.
    The input receives a dictionary containing the necessary data for connecting storage.

    '''

    try:
        (data_mount, pre_mount) = get_mount_data(current_storage_data)
    except MountError as e:
        raise general_function.MyError(f"{e}")

    if not data_mount:
        # if local storage
        return 0
    else:
        type_storage = data_mount.get('type_storage')
        packets = data_mount.get('packets')
        check_cmd = data_mount.get('check_cmd')
        mount_cmd = data_mount.get('mount_cmd')

        for i in packets:
            if i:
                check_packet = general_function.exec_cmd(f"{check_cmd} {i}")
                stdout_check = check_packet['stdout']

                if not stdout_check:
                    raise general_function.MyError(f"Required package '{i}' not installed!")
            else:
                continue

        if pre_mount:
            for key in pre_mount:
                try:
                    f = globals()[key]
                    args = pre_mount[key]
                    f(args)
                except Exception as err:
                    raise general_function.MyError(f"Impossible perform pre-mount operations for storage '{type_storage}': {err}")

        check_mount_cmd = f"mount | grep {mount_point}"
        check_mount = general_function.exec_cmd(check_mount_cmd)
        stdout_mount = check_mount['stdout']

        if stdout_mount:
            raise general_function.MyError(f"Mount point {mount_point} is busy!")
        else:
            general_function.create_dirs(job_name='', dirs_pairs={mount_point: ''})
            data_mounting = general_function.exec_cmd(f"{mount_cmd}")
            stderr_mounting = data_mounting['stderr']
            code = data_mounting['code']

            if stderr_mounting:
                raise general_function.MyError(stderr_mounting)

            if code != 0:
                raise general_function.MyError(f"Bad result code external process '{mount_cmd}':'{code}'")

            if type_storage == 's3':
                try:
                    os.chdir('/mnt/s3')
                except ConnectionAbortedError:
                    raise general_function.MyError("incorrect authentification data!")

    return 1


def unmount():
    if mount_point:
        umount_cmd = f"fusermount -uz {mount_point}"
        umount = general_function.exec_cmd(umount_cmd)
        stderr_umount = umount['stderr']
        code = umount['code']

        if stderr_umount:
            raise general_function.MyError(stderr_umount)
        elif code != 0:
            raise general_function.MyError(f"Bad result code external process '{umount_cmd}':'{code}'")
        else:
            general_function.del_file_objects('', mount_point)
    return 1


def check_secrets(str_auth):
    conf_path = '/etc/davfs2/secrets'

    if not os.path.isfile(conf_path):
        raise MountError("Can't record the authentication information for 'webdav' resource: /etc/davfs2/secrets is not found")

    try:
        with open(conf_path, 'r+') as f:
            conf = f.read()
            if conf.find(str_auth) == -1:
                f.write(str_auth)

    except (FileNotFoundError, IOError) as e:
        raise MountError(f"Can't write authentication information for 'webdav' resource: {e}")

    return 1


def check_s3fs_secrets(str_auth):
    conf_path = '/etc/passwd-s3fs'

    if not os.path.isfile(conf_path):
        with open(conf_path, 'w') as f:
            pass
    try:
        with open(conf_path, 'r+') as f:
            conf = f.read()
            if conf.find(str_auth) == -1:
                f.write(str_auth)
    except (FileNotFoundError, IOError) as e:
        raise MountError(f"Can't write authentication information for 's3fs' resource: {e}")
    try:
        os.chmod(conf_path, 0o600)
    except OSError:
        pass
    return 1
