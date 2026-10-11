from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assistant", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SpectrumDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("webhook_id", models.CharField(max_length=255)),
                ("message_id", models.CharField(max_length=255)),
            ],
        ),
        migrations.AddConstraint(
            model_name="spectrumdelivery",
            constraint=models.UniqueConstraint(fields=("webhook_id", "message_id"), name="assistant_spectrum_delivery_unique"),
        ),
    ]
