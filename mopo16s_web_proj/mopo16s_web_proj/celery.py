import os
from celery import Celery
from time import sleep
from .caches import cached_string, bool_encoder


# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mopo16s_web_proj.settings')

app = Celery('mopo16s_web_proj')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# first redis database is better to be reserved for the broker
app.conf.broker_url = 'redis://localhost:6379/0'
# task results and task schedules are stored in default django database
app.conf.result_backend = 'django-db'
app.conf.beat_scheduler = 'django_celery_beat.schedulers:DatabaseScheduler'
app.conf.worker_prefetch_multiplier = 1
app.conf.task_track_started = True

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    sleep(1)
    return 'Request: {!r}'.format(self.request)


app.conf.beat_schedule = {
    'check_failed_jobs':       {
        'task':     'mopo16s_web.tasks.check_failed_jobs',
        'schedule': 60 * 15
        },
    'clean_allocated_threads': {
        'task':     'mopo16s_web.tasks.clean_allocated_threads',
        'schedule': 60 * 15
        },
    'debug_task':              {
        'task':     'mopo16s_web_proj.celery.debug_task',
        'schedule': 60 * 60
        },
    }


def get_running_tasks_ids(pattern='*'):
    # get info of workers with name matching the pattern
    active_workers = app.control.inspect(pattern=pattern).active()
    return tuple(task['id'] for worker_name, task_list in active_workers.items() for task in task_list)


@cached_string('celery.task.running', 8, encoder=bool_encoder, decoder=bool)
def task_is_running(task_id, pattern='*'):
    return task_id in get_running_tasks_ids(pattern)
