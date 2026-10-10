from django.contrib import admin

from .models import Contribution, Goal

admin.site.register(Goal)
admin.site.register(Contribution)
