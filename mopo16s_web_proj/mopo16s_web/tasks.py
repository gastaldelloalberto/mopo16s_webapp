from mopo16s_web_proj.settings import MEDIA_ROOT, DEFAULT_FROM_EMAIL, EMAIL_SUBJECT_PREFIX, \
    MOPO16S_PATH, MOPO16S_MAX_THREADS, MOPO16S_MAX_THREADS_PER_INSTANCE, MOPO16S_PARAMETERS
from mopo16s_web_proj.caches import cache
from mopo16s_web.models import Job, JOB_MAX_RUN_RETRIES
from os import path, remove
import subprocess
from django.core.mail import send_mail
from mopo16s_web_proj.celery import app as celery_app, get_running_tasks_ids, task_is_running
from celery.utils.log import get_task_logger
from django.db.models import Q
from celery.result import AsyncResult


logger = get_task_logger(__name__)


def deallocate_threads(job_id):
    cache.delete('threads_allocated@job_{}'.format(job_id))


def allocate_threads(job, current_run):
    runs = job.mopo16s_parameters['runs']
    restarts = job.mopo16s_parameters['restarts']
    threads = MOPO16S_MAX_THREADS
    deallocate_threads(job.id)
    for key in cache.keys('threads_allocated@job_*'):
        threads -= int(cache.get(key))
    
    # if previous job was killed with SIGKILL (-9), assign one less thread
    last_run = job.runs.exclude(id=current_run.id).last()
    if (last_run is not None) and (last_run.log_data.get('exit_code') == -9) \
            and ('threads' in last_run.log_data) and (threads >= last_run.log_data['threads']):
        threads = last_run.log_data['threads'] - 1
    # allocate maximum a thread per run
    if threads > runs:
        threads = runs
    # if restarts is greater than default parameter, allocate one less thread
    if restarts > MOPO16S_PARAMETERS['restarts']['default']:
        threads -= 1
    if threads > MOPO16S_MAX_THREADS_PER_INSTANCE:
        threads = MOPO16S_MAX_THREADS_PER_INSTANCE
    # assign one thread at least, obviously
    if threads < 1:
        threads = 1
    # assume a maximum runtime of 36 hours, the allocated threads will be reset
    # this is to prevent long runnning (or failed) tasks to mess up thread count
    # only in the case 'clean_allocated_threads' didn't fix it
    cache.set('threads_allocated@job_{}'.format(job.id), threads, 36 * 60 * 60)
    return threads


@celery_app.task(bind=True, expire=1200)
def clean_allocated_threads(self):
    # get ids of running tasks
    active_tasks = get_running_tasks_ids('*mopo_run*')
    
    # get allocated threads
    keys = cache.keys('threads_allocated@job_*')
    if not keys:
        return 'OK, zero threads allocated'
    threads_allocated = (int(cache.get(key)) for key in keys)
    
    result = ''
    for key, threads in zip(keys, threads_allocated):
        job_id = key.rsplit('_', 1)[-1]
        try:
            job_task_id = Job.objects.only('task_id').get(id=job_id).task_id
        except Job.DoesNotExist:
            cache.delete(key)
            result += '\n job {} notfound-{:2d} threads - job does not exist!'.format(job_id, threads)
            continue
        
        # if the task is not running, delete threads allocation
        # the worker could have crashed
        if job_task_id not in active_tasks:
            cache.delete(key)
            result += '\n job {} cleaned -{:2d} threads - {} not running'.format(job_id, threads, job_task_id)
        else:
            result += '\n job {}   OK    -{:2d} threads - {} running'.format(job_id, threads, job_task_id)
    return 'CLEANING COMPLETED' + result


@celery_app.task(bind=True, expire=1200)
def check_failed_jobs(self):
    # load not completed jobs (no 'result')
    # that were sent ('task' exists and 'task.status' is 'STARTED') but killed ('run' without 'date_finished')
    jobs = Job.objects.filter(result=None, task__status='STARTED') \
        .filter(Q(run__date_finished=None) | Q(run=None)).distinct().only('task_id')
    running_tasks = get_running_tasks_ids()
    result = ''
    jobs_resetted = 0
    for job in jobs:
        # check if not running
        if job.task_id not in running_tasks:
            # create a new task, the other is lost
            job.task_id = run_mopo16s_job.delay(job.id).id
            job.save()
            jobs_resetted += 1
            result += '\n job {} resetted - new task_id: {}'.format(job.id, job.task_id)
    return '{} jobs resetted'.format(jobs_resetted) + result


@celery_app.task(bind=True, queue='queue_mopo16s', max_retries=JOB_MAX_RUN_RETRIES, default_retry_delay=30)
def run_mopo16s_job(self, job_id):
    # this method is idempotent
    
    logger.info('Running job {} - (re)try #{}'.format(job_id, self.request.retries))
    job = Job.objects.get(id=job_id)
    run = job.create_run()
    
    if job.is_completed:
        logger.error('Skipping job {} - {}'.format(job_id, Job.AlreadyCompletedException.description))
        run.set_failed(Job.AlreadyCompletedException.description)
        raise Job.AlreadyCompletedException
    if job.runs.count() > JOB_MAX_RUN_RETRIES or self.request.retries > JOB_MAX_RUN_RETRIES:
        logger.error('Stopping job {} - {}'.format(job_id, Job.MaxRunReachedException.description))
        run.set_failed(Job.MaxRunReachedException.description)
        raise Job.MaxRunReachedException
    if job.task_id != self.request.id:
        if task_is_running(job.task_id):
            run.set_failed(Job.MaxRunReachedException.description)
            return 'task_id CHANGED, skipping'
        else:
            AsyncResult(job.task_id).revoke()
            job.task_id = self.request.id
            job.save()
    
    tmp_path = MEDIA_ROOT + '/tmp/job_{}_'.format(job.id)
    tmp_primers_file_path = tmp_path + 'good_pairs_{}.fasta'.format(job.good_pairs_id)
    tmp_init_file_path = tmp_path + 'init'
    tmp_out_file_path = tmp_path + 'out'
    
    def delete_tmp_files():
        # remove InitialPrimerPairs temp file
        if path.exists(tmp_primers_file_path):
            remove(tmp_primers_file_path)
        # remove the 4 output files
        for path_ in (tmp_init_file_path, tmp_out_file_path):
            for extension in ('.primers', '.scores'):
                if path.exists(path_ + extension):
                    remove(path_ + extension)
    
    try:
        # write (or overwrite) temp initial_primer_pairs file
        with open(tmp_primers_file_path, 'w') as temp_file:
            temp_file.write(job.good_pairs.content)
        
        threads = allocate_threads(job, run)
        run.set_threads(threads)
        cmd_args = [MOPO16S_PATH,
                    job.rep_set.file.path,
                    tmp_primers_file_path,
                    '--threads=' + str(threads),
                    *job.mopo16s_command_options,
                    '--outInitFileName=' + tmp_init_file_path,
                    '--outFileName=' + tmp_out_file_path]
        p = subprocess.run(cmd_args, check=True, capture_output=True)
        deallocate_threads(job_id)
        
        run.set_completed(stdout=p.stdout.decode("utf-8"),
                          init_file_path=tmp_init_file_path,
                          out_file_path=tmp_out_file_path,
                          error=p.stderr.decode("utf-8"),
                          exit_code=p.returncode,
                          cmd=' '.join(cmd_args))
        send_job_completed_email.delay(job.id)
    except subprocess.CalledProcessError as exc:
        logger.error('Error job {} - CalledProcessError\n{!r}'.format(job_id, exc))
        deallocate_threads(job_id)
        run.set_failed(error='{!r}'.format(exc),
                       sterr=exc.stderr.decode("utf-8"),
                       stoout=exc.stdout.decode("utf-8"),
                       exit_code=exc.returncode,
                       cmd=' '.join(exc.cmd),
                       output=exc.output.decode("utf-8"))
        delete_tmp_files()
        raise run_mopo16s_job.retry(exc=exc)
    except Exception as exc:
        logger.error('Error job {} - Exception\n{!r}'.format(job_id, exc))
        deallocate_threads(job_id)
        run.set_failed(error=str(exc))
        delete_tmp_files()
        raise run_mopo16s_job.retry(exc=exc)
    return 'OK'


@celery_app.task(bind=True)
def send_email(self, subject, message, recipient, is_auto=True):
    if is_auto:
        message += '\n\n\nThis is an automatic notification from mopo16S Webapp.'
    return send_mail(EMAIL_SUBJECT_PREFIX + subject, message, DEFAULT_FROM_EMAIL, [recipient])


@celery_app.task(bind=True)
def send_job_completed_email(self, job_id):
    job = Job.objects.get(id=job_id)
    return send_mail('Job completed', 'Your job has been completed.\n\n' + job.get_info_str(),
                     DEFAULT_FROM_EMAIL, [job.created_by.email])
