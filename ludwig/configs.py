from pathlib import Path
import socket


class WorkerDirs:
    root = Path(__file__).parent.parent
    ludwig_data = Path('/') / 'media' / 'ludwig_data'
    stdout = ludwig_data / 'stdout'
    watched = Path('/') / 'var' / 'sftp' / 'ludwig_jobs'


class Remote:
    watched_pattern = 'run*.py'  # this is required for watcher to know which file to run
    path_to_ssh_config = Path.home() / '.ssh' / 'ludwig_config'
    online_worker_names = ['norman', 'hebb', 'hinton', 'pitts', 'hawkins', 'lecun']
    # TODO bengio is down - march 24 2020
    # todo hoff - no NVIDIA driver found by torch.
    all_worker_names = ['hoff', 'norman', 'hebb', 'hinton', 'pitts', 'hawkins', 'bengio', 'lecun']
    group2workers = {'half1': ['hoff', 'norman', 'hebb', 'hinton'],
                     'half2': ['pitts', 'hawkins', 'bengio', 'lecun']}
    disk_max_percent = 90


class Time:
    delete_delta = 24  # hours
    format = '%Y-%m-%d-%H:%M:%S'


class Constants:
    param2val = 'param2val'
    saves = 'saves'
    runs = 'runs'
    added_param_names = ['job_name', 'param_name', 'project_path', 'save_path']


hostname = socket.gethostname()