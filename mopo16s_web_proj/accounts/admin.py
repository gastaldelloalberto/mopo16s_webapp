from django.contrib.auth.admin import UserAdmin
from django.contrib import admin
from .models import User, ApiToken


admin.site.register(User, UserAdmin)
admin.site.register(ApiToken)
