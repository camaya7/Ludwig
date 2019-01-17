"""
The client is used to submit jobs to one or more nodes in LudwigCluster.
It uses an sftp client library to upload all files in a user's project to LudwigCluster.
"""
from pathlib import Path
import pysftp
import platform
import psutil
import datetime
import yaml
import numpy as np
from distutils.dir_util import copy_tree
import sys

from ludwigcluster import config
from ludwigcluster.logger import Logger

DISK_USAGE_MAX = 90


# TODO rename all configs_dict occurrences to params

class Client:
    def __init__(self, project_name):
        self.project_name = project_name
        self.hostname2ip = self.make_hostname2ip()
        self.logger = Logger(project_name)
        self.num_workers = len(config.SFTP.worker_names)
        self.private_key_pass = config.SFTP.private_key_pass_path.read_text().strip('\n')
        self.private_key = '{}/.ssh/id_rsa'.format(Path.home())
        self.ludwig = 'ludwig'

    @staticmethod
    def make_hostname2ip():
        """load hostname aliases from .ssh/config"""
        res = {}
        h = None
        p = Path.home() / '.ssh' / 'config'
        if not p.exists():
            raise FileNotFoundError('Please specify hostname-to-IP mappings in .ssh/config.')
        with p.open('r') as f:
            for line in f.readlines():
                words = line.split()
                if 'Host' in words:
                    h = line.split()[1]
                    res[h] = None
                elif 'HostName' in words:
                    ip = line.split()[1]
                    res[h] = ip
        return res

    @staticmethod
    def check_lab_disk_space():
        if platform.system() == 'Linux':
            usage_stats = psutil.disk_usage(str(config.Dirs.lab))
            percent_used = usage_stats[3]
            print('Percent Disk Space used at {}: {}'.format(config.Dirs.lab, percent_used))
            if percent_used > DISK_USAGE_MAX:
                raise RuntimeError('Disk space usage > {}.'.format(DISK_USAGE_MAX))
        else:
            print('WARNING: Cannot determine disk space on non-Linux platform.')

    def make_job_base_name(self, worker_name):
        time_of_init = datetime.datetime.now().strftime(config.Time.format)
        res = '{}_{}'.format(worker_name, time_of_init)
        path = config.Dirs.lab / self.project_name / res
        if path.is_dir():
            raise IsADirectoryError('Directory "{}" already exists.'.format(res))
        return res

    def add_reps(self, param2val_list, reps):
        res = []
        for n, param2val in enumerate(param2val_list):
            num_times_logged = self.logger.count_num_times_in_backup(param2val)
            num_times_train = reps - num_times_logged
            num_times_train = max(0, num_times_train)
            print('Params {} logged {} times. Will train {} times'.format(
                n, num_times_logged, num_times_train))
            res += [param2val] * num_times_train
        if not res:
            raise RuntimeError('{} replications of each model already exist.'.format(reps))
        return res

    def submit(self, src_ps, param2val_list, data_ps=None, reps=1, test=True, worker=None):
        self.check_lab_disk_space()
        self.logger.delete_incomplete_models()
        # upload data
        for data_p in data_ps:
            src = str(data_p)
            dst = str(config.Dirs.lab / self.project_name / data_p.name)
            print('Copying data in {} to {}'.format(src, dst))
            copy_tree(src, dst)
        # add reps
        param2val_list = self.add_reps(param2val_list, reps)
        # split into 8 chunks (one per node)
        worker_names = iter(np.random.permutation(config.SFTP.worker_names)) if worker is None else iter([worker])
        for param2val_chunk in np.array_split(param2val_list, self.num_workers):
            try:
                worker_name = next(worker_names)  # distribute jobs across workers randomly
            except StopIteration:
                raise SystemExit('Using only worker "{}" because "worker" arg is not None.'.format(worker))
            #
            if len(param2val_chunk) == 0:
                print('Not submitting to {}'.format(worker_name))
                continue
            # make job dirs
            base_name = self.make_job_base_name(worker_name)

            # console
            print('Connecting to {}'.format(worker_name))
            for param2val in param2val_chunk:
                print(param2val)
            # connect via sftp
            sftp = pysftp.Connection(username='ludwig',
                                     host=self.hostname2ip[worker_name],
                                     private_key=self.private_key,
                                     private_key_pass=self.private_key_pass)
            # upload src code to worker
            for p in src_ps:
                localpath = str(p)
                remotepath = '{}/{}'.format(self.ludwig, p.name)
                print('Uploading {} to {}'.format(localpath, remotepath))
                sftp.makedirs(remotepath)
                sftp.put_r(localpath=localpath, remotepath=remotepath)
            sys.stdout.flush()
            if test:
                print('Test successful. Not uploading run.py.')
                continue
            # save + upload param2val files
            remotepath = '{}/{}'.format(self.ludwig, 'param2vals')
            sftp.makedirs(remotepath)
            for n, param2val in enumerate(param2val_chunk):
                job_name = '{}_{}'.format(base_name, n)
                (config.Dirs.lab / self.project_name / 'runs' / job_name).mkdir(parents=True)
                p = config.Dirs.lab / self.project_name / 'runs' / job_name / '{}.yaml'.format(job_name)
                with p.open('w', encoding='utf8') as f:
                    yaml.dump(param2val, f, default_flow_style=False, allow_unicode=True)
                sftp.put(localpath=str(p),
                         remotepath='{}/{}/{}'.format(self.ludwig, 'param2vals', p.name))  # TODO test
            # upload run.py
            sftp.put(localpath='run.py',
                     remotepath='{}/{}'.format(self.ludwig, 'run.py'))
            print('--------------')
            print()
