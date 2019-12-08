from .models import Bot, BotApiException
from rest_framework.views import APIView
from rest_framework.response import Response
from functools import wraps


def api_login_required(func):
    """
    Decorator for api token authorization.
    After successful authentication, fills 'request.bot' and calls the wrapped function,
    returns 401 in case of invalid credentials,
    and 403 in case of disabled api token.
    """
    
    @wraps(func)
    def wrapper(self, http_method, request, id_=None, token=None, **kwargs):
        try:
            self.request.bot = Bot.get(id_=id_, token=token)
        except Bot.DoesNotExist:
            return Response(dict(ok=False, error_code=401, description='Unauthorized'), status=401)
        if not self.request.bot.is_active():
            return Response(dict(ok=False, error_code=403, description='Forbidden: disabled api token'), status=403)
        return func(self, http_method, request, **kwargs)
    
    return wrapper


class BotAPIView(APIView):
    name = 'mopo16S Web API'
    http_method_names = ['get', 'post']
    
    @api_login_required
    def _serve_request(self, http_method, request, method, **params):
        if 'format' in params:
            del params['format']
        # include also request parameters passed via get or post
        for key, value in self.request.data.items():
            # do not overwrite url parameters
            if key not in params:
                params[key] = value
        for key, value in self.request.query_params.items():
            # do not overwrite url parameters and data parameters
            if key not in params:
                params[key] = value
        
        try:
            return Response(dict(ok=True, result=request.bot.execute_method(http_method, method, params=params)))
        except BotApiException as e:
            return Response(dict(ok=False, error_code=e.error_code, description=str(e)), status=e.error_code)
    
    def get(self, *args, **kwargs):
        return self._serve_request('GET', *args, **kwargs)
    
    def post(self, *args, **kwargs):
        return self._serve_request('POST', *args, **kwargs)
