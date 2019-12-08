from django.db import models
from django.contrib.postgres.fields import JSONField
from mopo16s_web_proj.settings import MOPO16S_VERSION, AUTH_USER_MODEL, MOPO16S_PARAMETERS
from django.db.models import Q, F, Func, Value
from django.db.models.functions import Concat
from time import strftime, time
from django.utils.timezone import now as tznow
from django.core.files.base import File
from celery.result import AsyncResult
from mopo16s_web_proj.celery import task_is_running
from django_celery_results.models import TaskResult
from mopo16s_web_proj.caches import cache_celery
from json import loads as json_loads
from Bio import motifs
from Bio.Seq import Seq
import pandas as pd


def _get_query_filter_getter(user_field: str, permission: str):
    def query_filter_getter(_manager, user):
        """
        User without view permission can see only his sequences and public ones
        :param _manager: Self (manager)
        :param user: settings.AUTH_USER_MODEL
        :return: query filter
        """
        if user.has_perm('mopo16s_web.' + permission):
            return Q()
        return Q(**{user_field: user}) | Q(is_public=True)
    
    return query_filter_getter


class RepresentativeSequenceSetManager(models.Manager):
    view_sequence_query_filter = _get_query_filter_getter('uploaded_by', 'view_representativesequenceset')
    
    def filter(self, *args, request_user=None, **kwargs):
        """
        Allows to filter by authenticated user,
        furthermore it defers 'content' loading
        :param request_user: settings.AUTH_USER_MODEL
        """
        queryset = super().filter(*args, **kwargs)
        if request_user is not None:
            queryset = queryset.filter(self.view_sequence_query_filter(request_user))
        return queryset


def rep_sets_upload_path(instance, filename):
    # get full file path for fasta formatted files
    # file will be uploaded to: MEDIA_ROOT/<directory>/YYYY-MM-DD_user<AUTH_USER_MODEL_id>_<timestamp>.fasta
    return 'sequence_sets/{}_user{}_{}.fasta'.format(strftime('%Y-%m-%d'), instance.uploaded_by.id, time())


class RepresentativeSequenceSet(models.Model):
    objects = RepresentativeSequenceSetManager()
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=128, null=False, blank=False)
    description = models.TextField(null=False, blank=False)
    file = models.FileField(upload_to=rep_sets_upload_path, db_column='file_path', max_length=128)
    file_size = models.IntegerField(verbose_name='File size')
    sequences_count = models.IntegerField(verbose_name='Number of sequences')
    is_public = models.BooleanField()
    is_curated = models.BooleanField()
    version = models.CharField(max_length=16)
    uploaded_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.DO_NOTHING,
                                    related_name='uploaded_rep_set', related_query_name='uploaded_rep_set')
    date_uploaded = models.DateTimeField(auto_now_add=True)
    previous_version = models.ForeignKey('RepresentativeSequenceSet', on_delete=models.DO_NOTHING,
                                         related_name='next_versions', related_query_name='next_versions')
    
    # jobs_served = reverse relation with Job
    # next_versions = reverse recursive-relation
    
    def to_api_dict(self):
        return dict(id=self.id, name=self.name, description=self.description, is_public=self.is_public,
                    is_curated=self.is_curated, version=self.version, uploaded_by=self.uploaded_by.to_api_dict(),
                    file_size=self.file_size, sequences_count=self.sequences_count)
    
    def __str__(self):
        return self.get_name()
    
    def get_name(self, max_length=60):
        s = self.name
        if self.is_curated:
            s = '(DB) ' + s
        count = '  (# of seq: {})'.format(self.sequences_count)
        if max_length:
            if len(s) + len(count) > max_length:
                s = s[:max_length - 5 - len(count)] + '[...]'
        return s + count
    
    def delete(self, **kwargs):
        # when deleting the object, delete the file too
        self.file.delete()
        return super().delete(**kwargs)
    
    class Meta:
        managed = False
        db_table = 'mopo16s_representative_sequence_set'


class InitialPrimerPairsManager(models.Manager):
    view_sequence_query_filter = _get_query_filter_getter('uploaded_by', 'view_initialprimerpairs')
    
    def filter(self, *args, request_user=None, **kwargs):
        """
        Allows to filter by authenticated user,
        furthermore it defers 'content' loading
        :param request_user: settings.AUTH_USER_MODEL
        """
        queryset = super().filter(*args, **kwargs).defer('content')
        if request_user is not None:
            queryset = queryset.filter(self.view_sequence_query_filter(request_user))
        return queryset
    
    def get_content_size_queryset(self):
        return self.annotate(content_size=Func(F('content'), function='octet_length'))


class InitialPrimerPairs(models.Model):
    objects = InitialPrimerPairsManager()
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=128, null=False, blank=False)
    description = models.TextField(null=False, blank=False)
    content = models.TextField(null=False, blank=False)
    sequences_count = models.IntegerField(verbose_name='Number of sequences')
    is_public = models.BooleanField()
    is_curated = models.BooleanField()
    version = models.CharField(max_length=16)
    uploaded_by = models.ForeignKey(AUTH_USER_MODEL, models.DO_NOTHING,
                                    related_name='uploaded_good_pairs',  # TODO: change in 'uploaded_primer_pairs'?
                                    related_query_name='uploaded_good_pairs')
    date_uploaded = models.DateTimeField(auto_now_add=True)
    previous_version = models.ForeignKey('InitialPrimerPairs', on_delete=models.DO_NOTHING,
                                         related_name='next_versions', related_query_name='next_versions')
    
    # jobs_served = reverse relation with Job
    
    def to_api_dict(self):
        return dict(id=self.id, name=self.name, description=self.description, is_public=self.is_public,
                    version=self.version, uploaded_by=self.uploaded_by.to_api_dict(),
                    sequences_count=self.sequences_count)
    
    def __str__(self):
        return self.get_name()
    
    def get_name(self, max_length=60):
        s = self.name
        count = '  (# of seq: {})'.format(self.sequences_count)
        if max_length:
            if len(s) + len(count) > max_length:
                s = s[:max_length - 5 - len(count)] + '[...]'
        return s + count
    
    def append_content(self, content):
        self.content = Concat(F('content'), Value(content))
    
    class Meta:
        managed = False
        db_table = 'mopo16s_initial_primer_pairs'


def view_job_query_filter(user):
    """
    User without view permission can see only his jobs and public ones
    :param user: settings.AUTH_USER_MODEL
    :return: query filter
    """
    if user.has_perm('mopo16s_web.view_job'):
        return Q()
    return Q(created_by=user) | Q(is_public=True)


def view_result_query_filter(user):
    """
    User without view permission can see only results for his jobs and public ones
    :param user: settings.AUTH_USER_MODEL
    :return: query filter
    """
    if user.has_perm('mopo16s_web.view_job'):
        return Q()
    return Q(job__created_by=user) | Q(job__is_public=True)


class JobManager(models.Manager):
    def filter(self, *args, request_user=None, **kwargs):
        """
        Allows to filter by authenticated user
        :param request_user: settings.AUTH_USER_MODEL
        """
        queryset = super().filter(*args, **kwargs)
        if request_user is not None:
            queryset = queryset.filter(view_job_query_filter(request_user))
        return queryset


JOB_MAX_RUN_RETRIES = 5


class Job(models.Model):
    objects = JobManager()
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=128, null=False, blank=False)
    description = models.TextField(null=False, blank=False)
    is_public = models.BooleanField()
    mopo16s_version = models.CharField(max_length=16, default=MOPO16S_VERSION, null=False, blank=False)
    mopo16s_parameters = JSONField(default=dict, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    task = models.ForeignKey(TaskResult, on_delete=models.PROTECT, to_field='task_id', db_constraint=False,
                             null=True, default=None)
    created_by = models.ForeignKey(AUTH_USER_MODEL, on_delete=models.DO_NOTHING,
                                   related_name='submitted_jobs', related_query_name='submitted_job')
    rep_set = models.ForeignKey(RepresentativeSequenceSet, on_delete=models.DO_NOTHING,
                                related_name='jobs_served', related_query_name='is_used')
    good_pairs = models.ForeignKey(InitialPrimerPairs, on_delete=models.DO_NOTHING,
                                   related_name='jobs_served', related_query_name='is_used')
    
    # result = reverse relation with Result
    # runs = reverse relation with Run
    
    def __str__(self):
        return 'Job {:2d}'.format(self.id)
    
    def get_info_str(self):
        return 'Job info:\n- name: {0.name}\n- description: {0.description}'.format(self)
    
    def to_api_dict(self):
        d = dict(
                created_by=self.created_by.to_api_dict(),
                created_at=self.date_created.timestamp(),
                rep_set=self.rep_set.to_api_dict(),
                good_pairs=self.good_pairs.to_api_dict(),
                )
        d.update((name, getattr(self, name))
                 for name in (
                     'id', 'name', 'description', 'is_public',
                     'mopo16s_version', 'mopo16s_parameters')
                 )
        return d
    
    @property
    def mopo16s_command_options(self):
        return ('--{}={}'.format(option, value) for option, value in self.mopo16s_parameters.items())
    
    def set_mopo16s_parameters(self, pairs):
        self.mopo16s_parameters = dict((name, MOPO16S_PARAMETERS[name]['type'](value)) for name, value in pairs)
    
    @property
    def mopo16s_parameters_sorted_list(self):
        return sorted(self.mopo16s_parameters.items(), key=lambda tup: tup[0])
    
    @property
    def status(self):
        if self.is_completed:
            return 'completed'
        try:
            if self.task is None:
                raise TaskResult.DoesNotExist
            status = self.task.status
        except TaskResult.DoesNotExist:
            for value in cache_celery.lrange('queue_mopo16s', 0, -1):
                mapping = json_loads(value)
                if 'headers' in mapping and mapping['headers']['id'] == self.task_id:
                    return 'pending'
            return 'failed'
        
        if status == 'STARTED':
            if task_is_running(self.task_id, pattern='*mopo_run*'):
                return 'running'
            return 'pending retry'
        if status == 'RETRY':
            return 'pending retry'
        if status == 'FAILURE':
            return 'failed'
        return status
    
    @property
    def is_completed(self):
        # job is completed only when a result exists
        try:
            return bool(self.result)
        except Result.DoesNotExist:
            pass
        return False
    
    @property
    def is_running(self):
        # job is running if a run without date_finished exists
        return AsyncResult(self.task_id).status == 'STARTED'
    
    class AlreadyCompletedException(Exception):
        description = 'Job is already completed'
        
        def __init__(self):
            super().__init__(self.description)
    
    class StillRunningException(Exception):
        description = 'Job is still running'
        
        def __init__(self):
            super().__init__(self.description)
    
    class MaxRunReachedException(Exception):
        description = 'Job run {} times already'.format(JOB_MAX_RUN_RETRIES)
        
        def __init__(self):
            super().__init__(self.description)
    
    def create_run(self):
        return self.runs.create()
    
    def set_result(self, init_file_path, out_file_path):
        Result.objects.create(job=self,
                              init_primers=File(open(init_file_path + '.primers', 'rt')).read(),
                              init_scores=File(open(init_file_path + '.scores', 'rt')).read(),
                              out_primers=File(open(out_file_path + '.primers', 'rt')).read(),
                              out_scores=File(open(out_file_path + '.scores', 'rt')).read())
    
    class Meta:
        managed = False
        db_table = 'mopo16s_job'


class Run(models.Model):
    id = models.AutoField(primary_key=True)
    job = models.ForeignKey(Job, on_delete=models.DO_NOTHING, related_name='runs', related_query_name='run')
    log_data = JSONField(blank=True, null=True, default=dict)
    date_started = models.DateTimeField(auto_now_add=True)
    date_finished = models.DateTimeField(null=True, default=None)
    
    def set_completed(self, stdout, init_file_path, out_file_path, **kwargs):
        self.job.set_result(init_file_path, out_file_path)
        self.log_data.update(kwargs)
        self.log_data['stdout'] = stdout
        self.log_data['completed'] = True
        self.date_finished = tznow()
        self.save()
    
    def set_failed(self, error, **kwargs):
        self.log_data.update(kwargs)
        self.log_data['error'] = error
        self.log_data['failed'] = True
        self.date_finished = tznow()
        self.save()
    
    def set_threads(self, threads):
        self.log_data['threads'] = threads
        self.save()
    
    class Meta:
        managed = False
        db_table = 'mopo16s_run'


class ResultManager(models.Manager):
    def filter(self, *args, request_user=None, **kwargs):
        """
        Allows to filter by authenticated user
        :param request_user: settings.AUTH_USER_MODEL
        """
        queryset = super().filter(*args, **kwargs)
        if request_user is not None:
            queryset = queryset.filter(view_result_query_filter(request_user))
        return queryset
    
    def create(self, **kwargs):
        instance = super().create(**kwargs)
        instance.structure_data()
        instance.save()
        return instance


def degenerate_sequence(sequences):
    return str(motifs.create([Seq(seq) for seq in sequences]).degenerate_consensus)


def cluster_seq_by_length(sequences):
    cluster = {}
    for seq in sequences:
        length = len(seq)
        if length in cluster:
            cluster[length].append(seq)
        else:
            cluster[length] = [seq]
    return cluster.values()


class Result(models.Model):
    COLUMN_MAMES = ['Forward primers', 'Reverse primers', 'Efficiency', 'Coverage', 'Matching-bias']
    PREFIXES = ('init', 'out')
    
    objects = ResultManager()
    job = models.OneToOneField(Job, on_delete=models.DO_NOTHING, primary_key=True,
                               related_name='result', related_query_name='result')
    init_primers = models.TextField(null=False, blank=False)
    init_scores = models.TextField(null=False, blank=False)
    out_primers = models.TextField(null=False, blank=False)
    out_scores = models.TextField(null=False, blank=False)
    data = JSONField(default=dict, null=False, blank=False)
    date_completed = models.DateTimeField(auto_now_add=True)
    
    def structure_data(self):
        self.data = {}
        for prefix in self.PREFIXES:
            matrix = []
            # skip the first line, that contains the 3 score names
            iter_scores_lines = iter(getattr(self, prefix + '_scores').splitlines())
            next(iter_scores_lines).split('\t')
            for primer_set_pair, scores_line in zip(getattr(self, prefix + '_primers').splitlines(), iter_scores_lines):
                forward_set, reverse_set = primer_set_pair.split('\tx\t')
                scores = (float(s) for s in scores_line.split('\t'))
                matrix.append([
                    *([degenerate_sequence(cluster)
                       for cluster in cluster_seq_by_length(primer_set.split('\t'))]
                      for primer_set in primer_set_pair.split('\tx\t')),
                    # primer_set is forward_set on the 1st iteration, then reverse_set
                    *scores,
                    ])
            self.data[prefix] = matrix
        # self.save()
    
    def get_html_tables(self):
        # resulting tables will have id: T_table_init and T_table_out
        
        def red_min_values(s):
            cond = (s == s.min())
            return ['color: red' if v else '' for v in cond]
        
        def green_max_values(s):
            cond = (s == s.max())
            return ['color: green' if v else '' for v in cond]
        
        def red_max_values(s):
            cond = (s == s.max())
            return ['color: red' if v else '' for v in cond]
        
        def green_min_values(s):
            cond = (s == s.min())
            return ['color: green' if v else '' for v in cond]
        
        tables = []
        for df, name in zip(self.get_dataframes(), self.PREFIXES):
            tables.append(df.style
                          .set_table_attributes('class="table table-striped'
                                                ' table-bordered table-hover order-column pre"')
                          .format('&#13;&#10;'.join, subset=self.COLUMN_MAMES[:2])
                          .apply(red_min_values, subset=self.COLUMN_MAMES[2:-1])
                          .apply(green_max_values, subset=self.COLUMN_MAMES[2:-1])
                          # matching-bias has to be minimized
                          .apply(red_max_values, subset=self.COLUMN_MAMES[-1])
                          .apply(green_min_values, subset=self.COLUMN_MAMES[-1])
                          .set_table_styles([dict(selector='td',
                                                  props=[('font-family',
                                                          'SFMono-Regular, Menlo, Monaco, Consolas,'
                                                          ' "Liberation Mono", "Courier New", monospace;')])])
                          .set_uuid('table_' + name)
                          .hide_index()
                          .render()
                          )
        return tables
    
    def get_dataframes(self):
        return (pd.DataFrame(self.data[prefix], columns=self.COLUMN_MAMES) for prefix in self.PREFIXES)
    
    class Meta:
        managed = False
        db_table = 'mopo16s_result'
