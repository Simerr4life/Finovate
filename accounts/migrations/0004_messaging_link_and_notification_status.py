from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_profile_auth0_sub"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="messaging_linked_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When this user proved control of photon_chat_id by sending a one-time link code.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="notify_simulated_orders",
            field=models.BooleanField(
                default=False,
                help_text="Opt in to local records when a simulated investment proposal is created. This does not send iMessage.",
            ),
        ),
        migrations.AddField(
            model_name="notificationevent",
            name="delivery_status",
            field=models.CharField(
                default="recorded",
                help_text="recorded means Finovate stored the event. This server does not mark events sent over iMessage.",
                max_length=20,
            ),
        ),
    ]
