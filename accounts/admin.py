from django.contrib import admin

from .models import Auth0UserBackup, ConnectedAccountPlaceholder, NotificationEvent, Profile

admin.site.register(Profile)
admin.site.register(NotificationEvent)
admin.site.register(ConnectedAccountPlaceholder)


@admin.register(Auth0UserBackup)
class Auth0UserBackupAdmin(admin.ModelAdmin):
    list_display = (
        "auth0_user_id",
        "email",
        "email_verified",
        "sync_status",
        "last_synced_at",
        "signup_created_at",
    )
    list_filter = ("sync_status", "email_verified")
    search_fields = ("auth0_user_id", "email")
    readonly_fields = ("created_at", "updated_at", "last_synced_at")
