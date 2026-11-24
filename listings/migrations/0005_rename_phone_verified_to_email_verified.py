from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0004_agentregistrationdraft_resend_count'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentregistrationdraft',
            name='email_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.RemoveField(
            model_name='agentregistrationdraft',
            name='phone_verified',
        ),
    ]
