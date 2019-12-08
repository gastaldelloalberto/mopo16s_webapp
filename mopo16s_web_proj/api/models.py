from functools import wraps
from accounts.models import ApiToken
from mopo16s_web.models import Job, RepresentativeSequenceSet, InitialPrimerPairs
from mopo16s_web.utils import validate_fasta_str
from django.forms import ValidationError


class BotApiException(BaseException):
    def __init__(self, description, error_code=400):
        super().__init__(description)
        self.error_code = error_code


class BadParameterException(BotApiException):
    def __init__(self, description):
        super().__init__('Bad request: ' + description, 400)


class ObjectNotFoundException(BotApiException):
    def __init__(self):
        super().__init__('Not Found: object does not exist or is unaccesible', 404)


class ObjectForbiddenException(BotApiException):
    def __init__(self, description=None):
        super().__init__('Forbidden' + (': ' + description if description is not None else ''), 403)


class MethodNotFoundException(BotApiException):
    def __init__(self, method):
        super().__init__('Not Found' + (": '{}' method not found".format(method) if method else ''), 404)


class MethodNotAllowedException(BotApiException):
    def __init__(self, http_method, method):
        super().__init__("Not Allowed: '{}' method not allowed for '{}' request".format(method, http_method), 405)


def check_parameters(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        kwargs_keys = list(kwargs.keys())
        method_info = self.METHODS[func.__name__]
        # required parameters
        for param_info in method_info.get('url_params', ()) + method_info.get('required_params', ()):
            if param_info['name'] in kwargs:
                kwargs_keys.remove(param_info['name'])
            else:
                raise BadParameterException("parameter '{}' is required for this request".format(param_info['name']))
        # optional parameters
        for param_info in method_info.get('optional_params', ()):
            param_name = param_info['name']
            param_type = param_info['type']
            if param_name in kwargs:
                # clean parameter
                try:
                    if 'decoder' in param_info:
                        kwargs[param_name] = param_info['decoder'](param_type(kwargs[param_name]))
                    else:
                        kwargs[param_name] = param_type(kwargs[param_name])
                except ValueError:
                    raise BadParameterException(
                            "parameter '{}' must be of type '{}'".format(param_name, param_type.__name__))
                kwargs_keys.remove(param_name)
        for param in kwargs_keys:
            raise BadParameterException("parameter '{}' is not allowed for this request".format(param))
        return func(self, *args, **kwargs)
    
    return wrapper


class Bot(ApiToken):
    # for every method there's a tuple of tuples ('parameter_name','path_converter')
    PAGINATE_BY = 20
    METHODS = dict(
            get_me=dict(http_method='GET', url_path=''),
            list_jobs=dict(http_method='GET', url_path='jobs',
                           optional_params=(
                               dict(name='offset', type=int),
                               ),
                           ),
            list_sequences=dict(http_method='GET', url_path='sequences',
                                optional_params=(
                                    dict(name='offset', type=int),
                                    ),
                                ),
            list_primers=dict(http_method='GET', url_path='primers',
                              optional_params=(
                                  dict(name='offset', type=int),
                                  ),
                              ),
            view_job=dict(http_method='GET', url_path='jobs',
                          url_params=(
                              dict(name='job_id', url_path='<int:job_id>'),
                              ),
                          ),
            view_sequence_set=dict(http_method='GET', url_path='sequences',
                                   url_params=(
                                       dict(name='sequence_set_id', url_path='<int:sequence_set_id>'),
                                       ),
                                   ),
            view_primer_set=dict(http_method='GET', url_path='primers',
                                 url_params=(
                                     dict(name='primer_set_id', url_path='<int:primer_set_id>'),
                                     ),
                                 ),
            new_primer_set=dict(http_method='POST', url_path='primers/new',
                                required_params=(
                                    dict(name='name', type=str),
                                    dict(name='description', type=str),
                                    dict(name='content', type=str),
                                    dict(name='version', type=str),
                                    ),
                                optional_params=(
                                    dict(name='is_public', type=bool, decoder=bool),
                                    dict(name='previous_version', type=int),
                                    ),
                                ),
            )
    
    @classmethod
    def get(cls, id_, token):
        if id_ is None or token is None:
            raise cls.DoesNotExist
        return cls.objects.get(id=id_, token=token)
    
    def is_active(self):
        return self.owner.is_active
    
    def execute_method(self, http_method, method, params=None):
        if (not method) or (method not in self.METHODS):
            raise MethodNotFoundException(method)
        if http_method != self.METHODS[method]['http_method']:
            raise MethodNotAllowedException(http_method, method)
        if params is None:
            params = dict()
        return getattr(self, method)(**params)
    
    def _to_dict(self):
        return dict(id=self.id, name=self.name, description=self.description,
                    owner=self.owner.to_api_dict(include_private=True))
    
    def to_api_dict(self):
        return dict(id=self.id, name=self.name, description=self.description,
                    owner=self.owner.to_api_dict())
    
    @check_parameters
    def get_me(self):
        return self._to_dict()
    
    @check_parameters
    def list_jobs(self, offset=0):
        return (job.to_api_dict() for job in
                self.get_jobs_queryset().order_by('-id')[offset:offset + self.PAGINATE_BY])
    
    @check_parameters
    def list_sequences(self, offset=0):
        return (sequence_set.to_api_dict() for sequence_set in
                self.get_sequences_queryset().order_by('-id')[offset:offset + self.PAGINATE_BY])
    
    @check_parameters
    def list_primers(self, offset=0):
        return (primer_set.to_api_dict() for primer_set in
                self.get_primers_queryset().order_by('-id')[offset:offset + self.PAGINATE_BY])
    
    @check_parameters
    def view_job(self, job_id):
        try:
            return self.get_jobs_queryset().get(id=job_id).to_api_dict()
        except Job.DoesNotExist:
            raise ObjectNotFoundException
    
    @check_parameters
    def view_sequence_set(self, sequence_set_id):
        try:
            return self.get_sequences_queryset().get(id=sequence_set_id).to_api_dict()
        except RepresentativeSequenceSet.DoesNotExist:
            raise ObjectNotFoundException
    
    @check_parameters
    def view_primer_set(self, primer_set_id):
        try:
            return self.get_primers_queryset().get(id=primer_set_id).to_api_dict()
        except InitialPrimerPairs.DoesNotExist:
            raise ObjectNotFoundException
    
    @check_parameters
    def new_primer_set(self, name, description, content, version, is_public=False, previous_version=None):
        try:
            sequences_count = validate_fasta_str(content)
            primer_set = InitialPrimerPairs.objects.create(name=name, description=description, content=content,
                                                           version=version, is_public=is_public,
                                                           uploaded_by_id=self.owner_id, sequences_count=sequences_count,
                                                           previous_version=previous_version)
            return primer_set.to_api_dict()
        except ValidationError:
            raise BotApiException('invalid FASTA format')
        except Exception as e:
            # TODO: handle exception
            raise e
    
    def get_jobs_queryset(self):
        return Job.objects.filter(request_user=self.owner)
    
    def get_sequences_queryset(self):
        return RepresentativeSequenceSet.objects.filter(request_user=self.owner)
    
    def get_primers_queryset(self):
        return InitialPrimerPairs.objects.filter(request_user=self.owner)
    
    class Meta:
        proxy = True
