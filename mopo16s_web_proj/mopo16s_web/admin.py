from django.contrib import admin
from .models import Job, RepresentativeSequenceSet, InitialPrimerPairs, Run, Result


admin.site.register(Job)
admin.site.register(RepresentativeSequenceSet)
admin.site.register(InitialPrimerPairs)
admin.site.register(Run)
admin.site.register(Result)
