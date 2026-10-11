from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_auth0_user_backup"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="name_customized_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "When the user last changed their display name in Finovate. Once "
                    "set, signing in again never overwrites the name with the "
                    "identity provider's copy."
                ),
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="notificationevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("budget_warning", "Budget warning threshold reached"),
                    ("goal_milestone", "Savings goal milestone reached"),
                    ("roundup_paused", "Round-ups paused"),
                    ("account_created", "Auth0 account created"),
                    ("welcome", "Welcome"),
                    ("system", "System message"),
                    ("savings_plan", "Savings plan updated"),
                ],
                max_length=30,
            ),
        ),
    ]
