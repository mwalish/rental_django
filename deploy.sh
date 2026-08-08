#!/usr/bin/env bash
# ============================================================================
# Smart Rental System — alwaysdata deployment helper
#
# Run this SCRIPT ON THE ALWAYSDATA SERVER (via SSH) inside your project folder.
# It sets up the venv, installs deps, runs migrations, collects static files,
# and reports a checklist. It does NOT create the database or configure the
# site — do those in the alwaysdata Admin panel (see README_DEPLOY_ALWAYSDATA.md).
#
# Usage (on the server):
#   cd ~/www/rental_django
#   bash deploy.sh
# ============================================================================
set -e  # stop on any error

echo "=============================================="
echo " Smart Rental System — Deployment Helper"
echo "=============================================="

# Detect Python (prefer python3)
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "❌ $PYTHON not found. Install Python 3 first."
  exit 1
fi
echo "✅ Using Python: $("$PYTHON" --version 2>&1)"

# --- 1. Virtual environment ------------------------------------------------
if [ ! -d "venv" ]; then
  echo ""
  echo "▶ Creating virtual environment (venv)..."
  "$PYTHON" -m venv venv
else
  echo ""
  echo "▶ venv already exists — reusing it."
fi

# shellcheck disable=SC1091
source venv/bin/activate
echo "✅ Virtual environment active."

# --- 2. Upgrade pip & install deps ------------------------------------------
echo ""
echo "▶ Upgrading pip/setuptools/wheel..."
pip install --upgrade pip setuptools wheel

echo ""
echo "▶ Installing requirements.txt..."
if [ ! -f "requirements.txt" ]; then
  echo "❌ requirements.txt not found in $(pwd)."
  exit 1
fi
pip install -r requirements.txt
echo "✅ Dependencies installed."

# --- 3. Django checks & migrations ------------------------------------------
echo ""
echo "▶ Running Django system check..."
python manage.py check

echo ""
echo "▶ Applying database migrations..."
python manage.py migrate
echo "✅ Migrations applied."

# --- 4. Static files --------------------------------------------------------
echo ""
echo "▶ Collecting static files..."
python manage.py collectstatic --noinput
echo "✅ Static files collected into staticfiles/."

# --- 5. Superuser (optional) ------------------------------------------------
if ! python manage.py shell -c "from django.contrib.auth import get_user_model; print('x')" >/dev/null 2>&1; then
  :
fi
echo ""
read -r -p "Create a superuser now? (y/N) " yn
if [[ "$yn" =~ ^[Yy]$ ]]; then
  python manage.py createsuperuser
fi

# --- 6. Summary / checklist -------------------------------------------------
echo ""
echo "=============================================="
echo " Deployment helper finished."
echo "=============================================="
echo ""
echo "NEXT STEPS (do these in the alwaysdata Admin / Web > Sites):"
echo "  1. Set site Type = Python WSGI"
echo "  2. Application path  = www/rental_django/wsgi.py   (the FILE, RELATIVE - points uWSGI at your wsgi entry)"
echo "  3. Working directory = www/rental_django/          (RELATIVE)"
echo "  4. virtualenv dir    = www/rental_django/venv      (RELATIVE)"
echo "  5. Static paths:"
echo "       /static=www/rental_django/staticfiles"
echo "       /media=www/rental_django/media"
echo "  6. Addresses = lexnul.alwaysdata.net"
echo ""
echo "  IMPORTANT: Application path MUST end in wsgi.py (not the folder)."
echo "  If it points at the folder, uWSGI fails with '__init__.py not found'"
echo "  and you get 'Connection to upstream failed: connection failure'."
echo ""
echo "Then restart the site and verify:"
echo "  https://lexnul.alwaysdata.net/api/docs/"
echo "  https://lexnul.alwaysdata.net/admin/"
echo ""
echo "Full guide: README_DEPLOY_ALWAYSDATA.md"
