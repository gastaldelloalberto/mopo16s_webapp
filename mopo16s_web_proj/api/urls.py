from django.urls import path
from .views import BotAPIView
from .models import Bot


auth_token_path = '<int:id_>:<slug:token>'
BotAPI_view = BotAPIView.as_view()


def prefix_slash_if_not_empty(s):
    if s:
        return '/' + s
    return ''


urlpatterns = [
    path(auth_token_path + prefix_slash_if_not_empty(method_info['url_path']) +
         prefix_slash_if_not_empty('/'.join(
                 param_info['url_path'] for param_info in method_info.get('url_params', ()))) +
         '/',
         BotAPI_view, kwargs=dict(method=method_name), name=method_name)
    for method_name, method_info in Bot.METHODS.items()
    ]
