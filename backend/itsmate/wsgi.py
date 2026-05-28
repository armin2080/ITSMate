"""WSGI config for ITSMate."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "itsmate.settings")

application = get_wsgi_application()
