from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_messaging_link_and_notification_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="account_created_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the Finovate profile was first created for this Auth0 subject.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="email_verified",
            field=models.BooleanField(
                default=False,
                help_text="True only when Auth0's email_verified claim is true.",
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="identity_status",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "Latest Auth0 account state. Empty for local fixture users that "
                    "were never created through Auth0. Never set to verified just "
                    "because a form was submitted."
                ),
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="messaging_consent",
            field=models.BooleanField(
                default=False,
                help_text="The user agreed to receive Finovate messages. Consent alone does not verify the phone.",
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="phone_number",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Contact number collected for messaging. Ownership is not verified by saving this value.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="phone_verified",
            field=models.BooleanField(
                default=False,
                help_text="True only when Auth0 reports phone_number_verified. A typed number never sets this.",
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="welcome_recorded_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the one-time welcome record was written. Stops retries from sending it again.",
                null=True,
            ),
        ),
    ]
