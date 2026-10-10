from django.contrib import admin

from .models import ConversationMessage, PendingConfirmation

admin.site.register(PendingConfirmation)
admin.site.register(ConversationMessage)
