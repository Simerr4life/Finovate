from django.contrib import admin

from .models import ConnectedAccountPlaceholder, NotificationEvent, Profile

admin.site.register(Profile)
admin.site.register(NotificationEvent)
admin.site.register(ConnectedAccountPlaceholder)
