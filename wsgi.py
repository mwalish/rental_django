"""
Root-level WSGI entry point for the Smart Rental System.

This file is the deployment entry point used by ALWAYSDATA.
It sits at the root of the uploaded project (next to manage.py) and simply
wires up the real Django WSGI application from the `rental` package, exposing
a module-level variable named `application`.

On alwaysdata, set the site's "Application path" to the directory containing
this file (relative to /home/lexnul/), e.g.  www/rental/
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

