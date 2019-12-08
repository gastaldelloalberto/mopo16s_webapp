from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from mopo16s_web.models import Job, RepresentativeSequenceSet, InitialPrimerPairs, Result
from django.views.generic import ListView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin
from web_interface.forms import NewJobForm, NewRepresentativeSequenceSet, NewInitialPrimerPairs
from mopo16s_web.tasks import run_mopo16s_job
from os import remove
from mopo16s_web_proj.settings import MEDIA_ROOT
from django.http import HttpResponse
from zipfile import ZipFile


def home(request):
    return render(request, 'home.html')


class JobListView(LoginRequiredMixin, ListView):
    model = Job
    context_object_name = 'jobs'
    template_name = 'jobs/list.html'
    paginate_by = 20
    
    def get_queryset(self):
        # filter results based on the authenticated user
        # ordering by 'id' equals ordering by 'created_at', and it's more efficient
        return Job.objects.filter(request_user=self.request.user) \
            .select_related('created_by', 'result', 'task') \
            .order_by('-id')


class JobDetailView(LoginRequiredMixin, DetailView):
    model = Job
    context_object_name = 'job'
    template_name = 'jobs/details.html'
    
    def get_object(self, **kwargs):
        # filter results based on the authenticated user
        return get_object_or_404(Job.objects.filter(request_user=self.request.user), id=self.kwargs['id'])


@login_required
def jobs_new(request):
    """
    Get a form for new job creation, or validate the form and save the new job.
    """
    if request.method == 'POST':
        form = NewJobForm(request.POST, request_user=request.user)
        if form.is_valid():
            job = form.save(commit=False)
            job.created_by = request.user
            job.set_mopo16s_parameters(form.mopo16s_parameters)
            job.save()
            # task = run_mopo16s_job.delay(job.id)
            # job.task_id = task.id
            job.task_id = run_mopo16s_job.delay(job.id).id
            job.save()
            return redirect('jobs.details', id=job.id)
    else:
        form = NewJobForm(request_user=request.user)
    return render(request, 'jobs/new.html', dict(form=form))


class RepresentativeSequenceSetListView(LoginRequiredMixin, ListView):
    model = RepresentativeSequenceSet
    context_object_name = 'sequences'
    template_name = 'sequences/list.html'
    paginate_by = 20
    
    def get_queryset(self):
        # filter results based on the authenticated user
        # ordering by 'id' equals ordering by 'created_at', and it's more efficient
        return RepresentativeSequenceSet.objects.filter(request_user=self.request.user).order_by('is_curated', '-id')


class RepresentativeSequenceSetDetailView(LoginRequiredMixin, DetailView):
    model = RepresentativeSequenceSet
    context_object_name = 'sequence'
    template_name = 'sequences/details.html'
    
    def get_object(self, **kwargs):
        # filter results based on the authenticated user
        return get_object_or_404(RepresentativeSequenceSet.objects.filter(request_user=self.request.user),
                                 id=self.kwargs['id'])


@login_required
def sequences_new(request):
    if request.method == 'POST':
        form = NewRepresentativeSequenceSet(request.POST, request.FILES)
        if form.is_valid():
            sequence_set = form.save(commit=False)
            sequence_set.uploaded_by = request.user
            sequence_set.is_database = False
            sequence_set.file = form.cleaned_data['validated_file']
            sequence_set.sequences_count = form.cleaned_data['validated_seq_count']
            sequence_set.file_size = sequence_set.file.size
            sequence_set.save()
            remove(form.cleaned_data['validated_file'].name)
            return redirect('sequences.details', id=sequence_set.id)
    else:
        form = NewRepresentativeSequenceSet()
    return render(request, 'sequences/new.html', dict(form=form))


class InitialPrimerPairsListView(LoginRequiredMixin, ListView):
    model = InitialPrimerPairs
    context_object_name = 'primers'
    template_name = 'primers/list.html'
    paginate_by = 20
    
    def get_queryset(self):
        # filter results based on the authenticated user
        # ordering by 'id' equals ordering by 'created_at', and it's more efficient
        return InitialPrimerPairs.objects.filter(request_user=self.request.user).order_by('-id')


class InitialPrimerPairsDetailView(LoginRequiredMixin, DetailView):
    model = InitialPrimerPairs
    context_object_name = 'primer'
    template_name = 'primers/details.html'
    
    def get_object(self, **kwargs):
        # filter results based on the authenticated user
        return get_object_or_404(InitialPrimerPairs.objects.filter(request_user=self.request.user),
                                 id=self.kwargs['id'])


@login_required
def primers_new(request):
    if request.method == 'POST':
        form = NewInitialPrimerPairs(request.POST, request.FILES)
        if form.is_valid():
            primer_pairs = form.save(commit=False)
            primer_pairs.uploaded_by = request.user
            primer_pairs.sequences_count = form.cleaned_data['validated_seq_count']
            primer_pairs.content = form.cleaned_data['validated_file'].read()
            primer_pairs.save()
            remove(form.cleaned_data['validated_file'].name)
            return redirect('primers.details', id=primer_pairs.id)
    else:
        form = NewInitialPrimerPairs()
    return render(request, 'primers/new.html', dict(form=form))


class ResultView(LoginRequiredMixin, DetailView):
    context_object_name = 'result'
    template_name = 'results/view.html'
    
    def get_object(self, **kwargs):
        job_id = self.kwargs['job_id']
        # filter results based on the authenticated user
        result = get_object_or_404(Result.objects.filter(request_user=self.request.user).only('job_id', 'data'),
                                   job_id=job_id)
        html_init, html_out = result.get_html_tables()
        return html_init, html_out, result.data, job_id


@login_required
def download_file(request, job_id):
    result = Result.objects.filter(request_user=request.user).get(job_id=job_id)
    tmp_zip_name = MEDIA_ROOT + '/tmp/results_{}.zip'.format(job_id)
    with ZipFile(tmp_zip_name, 'w') as zip_file:
        for name in ('init_primers', 'init_scores', 'out_primers', 'out_scores'):
            name_ = name.replace('_', '.')
            tmp_file_name = MEDIA_ROOT + '/tmp/{}_{}'.format(job_id, name_)
            with open(tmp_file_name, 'w') as tmp_file:
                tmp_file.write(getattr(result, name))
            zip_file.write(tmp_file_name, name_)
            remove(tmp_file_name)
    response = HttpResponse(open(tmp_zip_name, 'rb'), content_type="application/zip")
    response['Content-Disposition'] = 'inline; filename=mopo16S_webapp_job_{}_results.zip'.format(job_id)
    remove(tmp_zip_name)
    return response
