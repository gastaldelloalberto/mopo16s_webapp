from os import remove
from django import forms
from django.forms import ValidationError
from django.forms import ModelForm, IntegerField, DecimalField, TextInput
from mopo16s_web.models import Job, RepresentativeSequenceSet, InitialPrimerPairs
from mopo16s_web_proj.settings import MOPO16S_PARAMETERS, MEDIA_ROOT
from django.core.files.base import File
from time import time
from mopo16s_web.utils import validate_fasta_str, validate_fasta_file


# prepare mopo16s parameter fields dynamically, according to settings
JOB_FORM_PARAMETERS = {}
for param_name, param_details in MOPO16S_PARAMETERS.items():
    if param_name in ('threads', 'verbose'):
        # threads param can't be set by user
        # celery worker select the best value at running time
        continue
    # select the field type
    if param_details['type'] == int:
        field_class = IntegerField
    elif param_details['type'] == float:
        field_class = DecimalField
    else:
        raise TypeError
    # prepare kwargs for the field
    field_kwargs = dict(label=param_name)
    # rename according to field's parameters name
    for name, field_kwarg in (
            ('default', 'initial'), ('min', 'min_value'), ('max', 'max_value'), ('description', 'help_text')):
        if name in param_details:
            field_kwargs[field_kwarg] = param_details[name]
    JOB_FORM_PARAMETERS[param_name] = field_class(**field_kwargs)


class _NewJobForm(ModelForm):
    """
    Base class for NewJobForm
    defines the non-dynamic part
    """
    
    def __init__(self, *args, request_user, **kwargs):
        super().__init__(*args, **kwargs)
        # rep_set order, filtered by user: list databases first, then the other sequence sets
        self.fields['rep_set'].queryset = RepresentativeSequenceSet.objects.filter(
                request_user=request_user).order_by('-is_curated', 'id')
        # good_pairs order, filtered by user
        self.fields['good_pairs'].queryset = InitialPrimerPairs.objects.filter(
                request_user=request_user).order_by('id')
    
    class Meta:
        model = Job
        fields = ['name', 'description', 'is_public', 'good_pairs', 'rep_set']
        labels = {
            'is_public': 'Make the job public?'
            }
        help_texts = {
            'name':        'Name or brief description of the job (required).',
            'description': 'Detailed description of the job (required).',
            'is_public':   'Every user will be able to see it along with its results.',
            }
        widgets = {
            'description': TextInput,
            }
    
    @property
    def mopo16s_parameters(self):
        """
        :return: iterable containing all declared fields
                 (mopo16S_parameters dynamically defined from JOB_FORM_PARAMETERS)
        """
        return ((field_name, self.data[field_name]) for field_name in JOB_FORM_PARAMETERS.keys())
    
    def clean(self):
        cleaned_data = super().clean()
        cleaned_data['mopo16s_parameters'] = self.mopo16s_parameters
        return cleaned_data


# create the new type dynamically, in order to set parameter fields as defined in the form
NewJobForm = type('NewJobForm', (_NewJobForm,), JOB_FORM_PARAMETERS.copy())


def clean_sequences_upload(modelform, cleaned_data):
    # validate uploaded file here because adding a validator and scanning the stream
    # will close it after the loop, making it not reusable
    
    file = cleaned_data.get('file')
    # count how much content-fields were filled by the user
    n_filled_content = bool(file) + bool(modelform.data['content'])
    
    if n_filled_content != 1:
        msg = 'Fill in exactly one of the content fields.'
        if modelform.data['content']:
            modelform.add_error('content', msg)
        if modelform.files.get('file'):
            modelform.add_error('file', msg)
        if n_filled_content == 0:
            raise ValidationError('One of the content fields must be filled.', code='missing')
        else:
            raise ValidationError('Exactly one of the content fields must be filled.', code='invalid')
    
    tmp_file_name = MEDIA_ROOT + '/tmp/upload_' + str(time())
    # save the sequence set in a temporary file, in order to collect it later
    with open(tmp_file_name, 'w') as temp_file:
        try:
            if file:
                seq_count = validate_fasta_file(file, temp_file.writelines)
            else:
                seq_count = validate_fasta_str(modelform.data['content'], temp_file.writelines)
        except ValidationError:
            modelform.add_error('file' if file else 'content', 'Invalid FASTA format.')
    if seq_count == 0:
        remove(tmp_file_name)
    else:
        cleaned_data.update(validated_file=File(open(tmp_file_name, 'rt')), validated_seq_count=seq_count)
    return cleaned_data


class NewRepresentativeSequenceSet(ModelForm):
    # content can be inserted manually from text
    content = forms.CharField(required=False, widget=forms.Textarea(),
                              error_messages=dict(invalid='Invalid FASTA format.'),
                              label='Content from text', help_text='Fill with FASTA-formatted content.')
    
    # content can be inserted uploading a text file
    file = forms.FileField(required=False, error_messages=dict(invalid='Invalid FASTA file format.'),
                           label='Content from file', help_text='Upload a FASTA-formatted text file.')
    
    def clean(self):
        cleaned_data = super().clean()
        return clean_sequences_upload(self, cleaned_data)
    
    class Meta:
        model = RepresentativeSequenceSet
        fields = ['name', 'description', 'is_public', 'version', 'previous_version', 'file']
        help_texts = {
            'name':        'Name or brief description of the representative sequence set (required).',
            'description': 'Detailed description of the representative sequence set (required).',
            'is_public':   'Every user will be able to see it along with its results.',
            }
        labels = {
            'is_public': 'Make the representative sequence set public?'
            }


class NewInitialPrimerPairs(ModelForm):
    # content can be inserted manually from text
    content = forms.CharField(required=False, widget=forms.Textarea(),
                              error_messages=dict(invalid='Invalid FASTA format.'),
                              label='Content from text', help_text='Fill with FASTA-formatted content.')
    # content can be inserted uploading a text file
    file = forms.FileField(required=False, error_messages=dict(invalid='Invalid FASTA file format.'),
                           label='Content from file', help_text='Upload a FASTA-formatted text file.')
    
    def clean(self):
        cleaned_data = super().clean()
        return clean_sequences_upload(self, cleaned_data)
    
    class Meta:
        model = InitialPrimerPairs
        fields = ['name', 'description', 'is_public', 'version', 'previous_version', 'content']
        help_texts = {
            'name':        'Name or brief description of the initial primer pairs set (required).',
            'description': 'Detailed description of the initial primer pairs set (required).',
            'is_public':   'Every user will be able to see it along with its results.',
            }
        labels = {
            'is_public': 'Make the initial primer pairs set public?'
            }
