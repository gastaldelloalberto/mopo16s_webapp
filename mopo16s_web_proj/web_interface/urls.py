from django.urls import path
from . import views


urlpatterns = [
    path('', views.home, name='home'),
    
    path('jobs/', views.JobListView.as_view(), name='jobs.list'),
    path('jobs/<int:id>/', views.JobDetailView.as_view(), name='jobs.details'),
    path('jobs/new/', views.jobs_new, name='jobs.new'),
    
    path('sequences/', views.RepresentativeSequenceSetListView.as_view(), name='sequences.list'),
    path('sequences/<int:id>/', views.RepresentativeSequenceSetDetailView.as_view(), name='sequences.details'),
    path('sequences/new/', views.sequences_new, name='sequences.new'),
    
    path('primers/', views.InitialPrimerPairsListView.as_view(), name='primers.list'),
    path('primers/<int:id>/', views.InitialPrimerPairsDetailView.as_view(), name='primers.details'),
    path('primers/new/', views.primers_new, name='primers.new'),
    
    path('results/<int:job_id>/', views.ResultView.as_view(), name='results.view'),
    path('results/<int:job_id>/download', views.download_file, name='results.download'),
    ]
