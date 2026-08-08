# Deploying the Smart Rental Backend to alwaysdata.net

This guide walks you through deploying the Django backend to **alwaysdata.net**
with a **MySQL** database.

## Deployment target (your configuration)

- Site URL: `https://lexnul.alwaysdata.net`
- WSGI entry (as set in alwaysdata): `/home/lexnul/www/maziwasync/syncbck/wsgi.py`
  → This maps to the `wsgi.py` file at the **root of the uploaded project**.
- Application type in alwaysdata: **Python WSGI** (NOT PHP — you must change
  this in the site configuration, otherwise Python won't run).

---

## 1. Upload the code

Upload the contents of the `rental/` folder to:

```
/home/lexnul/www/maziwasync/syncbck/
```

The folder should contain `manage.py`, `wsgi.py`, `requirements.txt`, and the
`rental/` + `core/` + `landlord/` packages, e.g.:

```
syncbck/
├── wsgi.py            <- this is your WSGI entry (root-level)
├── manage.py
├── requirements.txt
├── .env.example
├── rental/            <- Django project package (settings, urls, wsgi, asgi)
├── core/              <- core app
├── landlord/          <- landlord app
└── media/             <- uploaded user content (persists on alwaysdata)
```

> **Important:** The root-level `wsgi.py` (created for alwaysdata) is what the
> alwaysdata site points to. It wires up `DJANGO_SETTINGS_MODULE=rental.settings`.

---

## 2. Create a Python virtual environment inside the project

In alwaysdata's **Web → Sites → your site → Python** (or via SSH), create a
virtualenv and install requirements:

```bash
cd /home/lexnul/www/maziwasync/syncbck
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Configure the MySQL database

**In alwaysdata Admin → Databases → MySQL**, create a database. On alwaysdata:

- The **host** is typically `mysql-lexnul.alwaysdata.net`
- The **database name** and **user** are prefixed with your account, e.g.
  `lexnul_rental_managment` and `lexnul_rental`
- Set a strong password

Then set these **environment variables** either in the alwaysdata
**Environment variables** panel or in a `.env` file in the project root:

```bash
DB_ENGINE=django.db.backends.mysql
DB_NAME=lexnul_rental_managment
DB_HOST=mysql-lexnul.alwaysdata.net
DB_PORT=3306
DB_USER=lexnul_rental
DB_PASSWORD=your_alwaysdata_db_password
```

> PyMySQL is already enabled via `install_as_MySQLdb()` in
> `rental/rental/__init__.py`, so no extra driver is needed.

---

## 4. Set the rest of the environment variables

Set these in alwaysdata's **Environment variables** panel (or `.env`):

```bash
DEBUG=False
SECRET_KEY=<a-long-random-secret>
ALLOWED_HOSTS=lexnul.alwaysdata.net,localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=https://lexnul.alwaysdata.net
CSRF_TRUSTED_ORIGINS=https://lexnul.alwaysdata.net
SECURE_SSL_REDIRECT=True

# M-Pesa (public HTTPS callback)
MPESA_CALLBACK_URL=https://lexnul.alwaysdata.net/api/core/payments/mpesa/callback/

# Africa's Talking SMS
AFRICAS_TALKING_USERNAME=...
AFRICAS_TALKING_API_KEY=...
```

Generate a secret key with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## 5. Run migrations & collect static files

From the project root (with the venv activated):

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser   # optional, for the Django admin
```

---

## 6. Configure the alwaysdata site

1. **Web → Sites → your site**.
2. Set **Type** to **Python WSGI** (currently it says PHP — this must change).
3. Set the **Root directory** to:
   ```
   /home/lexnul/www/maziwasync/syncbck
   ```
4. Set the **WSGI application** to the `wsgi.py` file at that root
   (e.g. `/home/lexnul/www/maziwasync/syncbck/wsgi.py`).
5. Set the **Python version** to match your venv (e.g. 3.11 or 3.12).
6. Point the **Address(es)** to `lexnul.alwaysdata.net`.

---

## 7. Verify

After deployment, check:

- `https://lexnul.alwaysdata.net/api/docs/` — Swagger API docs
- `https://lexnul.alwaysdata.net/admin/` — Django admin
- `https://lexnul.alwaysdata.net/api/core/login/` — test login endpoint

---

## 8. Serve media files (uploaded photos)

Django only serves `/media/` automatically when `DEBUG=True`. In production
(`DEBUG=False`) you must serve the `media/` folder through alwaysdata so the
uploaded profile/property photos are reachable at `https://lexnul.alwaysdata.net/media/...`.

**Option A — alwaysdata alias (recommended):**

1. In **Web → Sites → your site**, add an **Alias**.
2. Set the web path to `/media/` and the directory to the project's media
   folder: `/home/lexnul/www/maziwasync/syncbck/media/`.

**Option B — serve via Django (simpler, slightly slower):**

If you prefer to let Django serve media, uncomment/add the media URL pattern
unconditionally in `rental/rental/urls.py`:

```python
from django.conf.urls.static import static
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

(Remove the `if settings.DEBUG:` guard so it always applies.)

---

## Notes

- **Static files** are served via WhiteNoise (`whitenoise`), so no separate CDN
  is required.
- **Media files** (uploaded profile/property photos) are stored in `media/`
  inside the project root, which persists on alwaysdata.
- If emails are not delivered, set the real SMTP values in the environment
  variables (Gmail app passwords are recommended).
