"""
WSGI config for finovate project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'finovate.settings')

application = get_wsgi_application()

if os.environ.get("VERCEL"):
    from django.contrib.auth.models import User
    from django.core.management import call_command

    call_command("migrate", interactive=False, verbosity=0)
    demo_password = os.environ.get("DEMO_ACCOUNT_PASSWORD")
    if demo_password and not User.objects.filter(username="demo").exists():
        call_command("seed_demo", password=demo_password, verbosity=0)
