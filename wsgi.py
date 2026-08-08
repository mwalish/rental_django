"""
Root-level WSGI entry point for the Smart Rental System.

This file is the deployment entry point used by ALWAYSDATA.
It corresponds to the WSGI file configured at:

    /home/lexnul/www/maziwasync/syncbck/wsgi.py

It simply wires up the real Django WSGI application from the `rental`
package and must expose a module-level variable named `application`.
"""
import os
import sys

# Make the directory containing this file (the project root) importable,
# so the `rental` package and its `rental.settings` module can be found.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rental.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()

