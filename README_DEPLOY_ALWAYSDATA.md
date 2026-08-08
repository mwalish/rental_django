# 🚀 Smart Rental System — Complete Deployment Guide (alwaysdata.net)

> **Read this WHOLE guide before you start.** Deployment is just a sequence of
> repeatable steps. Follow them in order and you will NOT get lost. This is the
> complete, beginner-proof walkthrough — verify each step as you go.

---

## 0. What we are deploying (understand the stack first)

| Piece | What it is |
|---|---|
| **App** | Django 4.2+ REST API (two apps: `core`, `landlord`) |
| **Server** | Gunicorn (Python WSGI), launched by alwaysdata |
| **Database** | MySQL (hosted on alwaysdata) |
| **Static files** (CSS/JS for admin & Swagger) | Served by **WhiteNoise** |
| **Media files** (photos) | Stored in `media/`, served via alwaysdata static path |
| **Key integrations** | M-Pesa (STK Push), Africa's Talking SMS, email OTP |

### Your deployment target
- **Site URL:** `https://lexnul.alwaysdata.net`
- **WSGI entry:** root-level `wsgi.py` (already in your project)
- **Application type:** **Python WSGI** (NOT PHP — you must set this)
- **Account name:** `lexnul`

### Folder layout (what you upload)
Alwaysdata starts every session in `/home/lexnul/`. Your project will live in
a folder under `www/`. This guide uses `www/rental_django/` — **replace this
with your actual folder name** if different.

```
/home/lexnul/www/rental_django/
├── wsgi.py            <- WSGI entry (root-level, already in your project)
├── manage.py
├── requirements.txt
├── .env               <- SECRETS (never commit this)
├── rental/            <- Django project package (settings, urls, wsgi, asgi)
├── core/              <- core app
├── landlord/          <- landlord app
├── media/             <- uploaded photos (persists on alwaysdata)
├── staticfiles/       <- created by collectstatic (served by WhiteNoise)
└── venv/              <- Python virtualenv (created on the server)
```

> ⚠️ **Important:** The **root-level** `wsgi.py` (next to `manage.py`) is what
> alwaysdata's site points to. It sets `DJANGO_SETTINGS_MODULE=rental.settings`.
> Do NOT point alwaysdata at `rental/wsgi.py` — point it at the root one.

---

## 1. Prerequisites (have these ready before you start)

1. **alwaysdata account** — you already have one (`lexnul`).
2. **SSH/SFTP access** — enabled in alwaysdata Admin → *Account → SSH*. You'll
   need the SSH password or an SSH key.
3. **Your project code** — the `rental/` folder from your Mac.
4. **A way to generate a secret key** — one command (below).
5. **Your real credentials** for (as needed):
   - M-Pesa: consumer key, consumer secret, shortcode, passkey
   - Africa's Talking: username, API key
   - Email (SMTP): Gmail app password or similar

---

## 2. Create the MySQL database (alwaysdata Admin)

1. Log in to **alwaysdata Admin** → **Databases → MySQL**.
2. Click **Add a MySQL database**.
3. Fill in:
   - **Name:** `lexnul_renta` (or any name you like)
   - **User:** `lexnul` (or a new user)
   - **Password:** set a strong one and **save it somewhere safe**
4. Note the **hostname** given to you — typically:
   ```
   mysql-lexnul.alwaysdata.net
   ```
5. Note the **port** (usually `3306`).

> 📝 These exact values go into your `.env` in Step 5. The example values in
> this guide are:
> - DB name: `lexnul_renta`
> - DB user: `lexnul`
> - DB host: `mysql-lexnul.alwaysdata.net`

---

## 3. Upload the code (SFTP or SSH)

### Option A — SFTP (easiest, visual)
Use a tool like **FileZilla**, **Cyberduck**, or VS Code's SFTP extension:
- Host: `ssh-lexnul.alwaysdata.net`
- Username: `lexnul`
- Password: your alwaysdata SSH password
- Upload the **contents** of your local `rental/` folder into
  `/home/lexnul/www/rental_django/`

> ⚠️ Upload the **contents**, not the folder itself. You want `manage.py` at
> the top of `www/rental_django/`, not `www/rental_django/rental/manage.py`.

### Option B — SSH (command line)
```bash
# From your Mac, `cd` into the folder that CONTAINS the rental/ folder
cd ~/Desktop/main_smart_rental_system/  # adjust to your path

# Create the target folder on the server
ssh lexnul@ssh-lexnul.alwaysdata.net "mkdir -p ~/www/rental_django"

# Copy the contents of rental/ up to the server
scp -r rental/. lexnul@ssh-lexnul.alwaysdata.net:~/www/rental_django/
```

> Because `.env`, `media/`, and `venv/` are often git-ignored, if you upload
> via `git clone` from a repo, you may need to upload `media/` and `.env`
> separately. **The simplest reliable method is SFTP/SCP of the folder.**

---

## 4. Create the Python virtualenv & install dependencies (SSH)

SSH into the server and run the setup. alwaysdata defaults to Python 3.13 —
make sure the venv uses the same version you select in the site config (Step 7).

```bash
# 1. Connect
ssh lexnul@ssh-lexnul.alwaysdata.net

# 2. Go to your project
cd ~/www/rental_django

# 3. Create the virtual environment
python3 -m venv venv

# 4. Activate it
source venv/bin/activate

# 5. Upgrade pip
pip install --upgrade pip setuptools wheel

# 6. Install requirements
pip install -r requirements.txt

# 7. Verify Django installed
python -m django --version
```

> ✅ **Checkpoint:** `python -m django --version` prints a version (e.g. `4.2.x`).
> If it errors, the venv isn't active or the install failed.

---

## 5. Configure environment variables (the `.env` file)

The Django settings read everything from environment variables or a `.env`
file in the **project root**. Create it on the server:

```bash
cd ~/www/rental_django
nano .env        # or use your SFTP tool to upload a .env file
```

Paste the **full template** below and fill in your real values:

```bash
# ===== Django core =====
DEBUG=False
SECRET_KEY=CHANGE_ME_rX6z9...longrandomstring...
ALLOWED_HOSTS=lexnul.alwaysdata.net,localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=https://lexnul.alwaysdata.net
CSRF_TRUSTED_ORIGINS=https://lexnul.alwaysdata.net
SECURE_SSL_REDIRECT=True

# ===== MySQL database =====
DB_ENGINE=django.db.backends.mysql
DB_NAME=lexnul_renta
DB_HOST=mysql-lexnul.alwaysdata.net
DB_PORT=3306
DB_USER=lexnul
DB_PASSWORD=YOUR_DB_PASSWORD

# ===== M-Pesa =====
MPESA_CONSUMER_KEY=your_consumer_key
MPESA_CONSUMER_SECRET=your_consumer_secret
MPESA_SHORTCODE=174379
MPESA_PASSKEY=your_passkey
MPESA_CALLBACK_URL=https://lexnul.alwaysdata.net/api/core/payments/mpesa/callback/

# ===== Africa's Talking SMS =====
AFRICAS_TALKING_USERNAME=sandbox
AFRICAS_TALKING_API_KEY=your_api_key
AFRICAS_TALKING_SENDER_ID=RENTAL

# ===== Email (SMTP) — for sending OTP / password reset emails =====
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=youremail@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
DEFAULT_FROM_EMAIL=Smart Rental System <youremail@gmail.com>
```

**Generate a secret key** (run on your Mac or the server):
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```
Paste the output into `SECRET_KEY=`.

> 🔐 **Never** commit `.env` to git — your `.gitignore` already excludes it.

---

## 6. Run migrations, collect static, create superuser (SSH)

With the venv still active and inside your project:

```bash
cd ~/www/rental_django
source venv/bin/activate

# 1. Apply database migrations
python manage.py migrate

# 2. Collect static files (builds staticfiles/ for WhiteNoise)
python manage.py collectstatic --noinput

# 3. Create an admin user (optional but recommended)
python manage.py createsuperuser
```

> ✅ **Checkpoint:** `migrate` ends without errors and prints `Applying ... OK`
> for each migration. `collectstatic` copies files into `staticfiles/`.

> ⚠️ If `migrate` fails with a DB connection error, double-check the `.env`
> DB values (host, name, user, password) and that the database exists in the
> alwaysdata Admin panel.

---

## 7. Configure the alwaysdata site (the CRITICAL form fields)

> ### ⚠️ CRITICAL — use **RELATIVE** paths (this caused your `chdir()` error)
>
> alwaysdata already starts from `/home/lexnul/`. The **Application path** and
> **Working directory** must be **relative** to `/home/lexnul/`.
> If you enter the full `/home/lexnul/www/rental_django/`, alwaysdata doubles
> it to `/home/lexnul/home/lexnul/www/rental_django/` and uWSGI fails with:
> `chdir(): No such file or directory`.
>
> ❌ WRONG: `Application path = /home/lexnul/www/rental_django/`
> ✅ CORRECT: `Application path = www/rental_django/`

**Steps:**
1. Go to **Web → Sites → your site** (`lexnul.alwaysdata.net`).
2. Set **Type** to **Python WSGI**.
3. Set **Application path** to `www/rental_django/` (⚠️ relative).
4. Set **Working directory** to `www/rental_django/` (⚠️ relative).
5. Set **Python version** to the same version your venv was built with.
6. Set **virtualenv directory** to `www/rental_django/venv` (⚠️ relative).
7. Add **Static paths** (⚠️ relative):
   ```
   /static=www/rental_django/staticfiles
   /media=www/rental_django/media
   ```
8. Set **Address(es)** to `lexnul.alwaysdata.net`.
9. **Save** the site.

### Reference table (fill exactly like this)

| Field | Value (RELATIVE — no leading `/home/lexnul/`) |
|---|---|
| **Type** | Python WSGI |
| **Application path** | `www/rental_django/` |
| **Working directory** | `www/rental_django/` |
| **Python version** | e.g. `3.12` (match your venv) |
| **Virtualenv directory** | `www/rental_django/venv` |
| **Static paths** | `/static=www/rental_django/staticfiles /media=www/rental_django/media` |
| **Addresses** | `lexnul.alwaysdata.net` |

> Replace `www/rental_django/` with your actual folder name under `www/`.

---

## 8. Environment variables in the alwaysdata panel (optional alternative)

Instead of (or in addition to) the `.env` file, you can paste the same variables
in **Web → Sites → your site → Environment variables**. The `.env` file method
is simpler and keeps everything in one file. Choose **one** method to avoid
confusion — `.env` is recommended.

---

## 9. Restart the site & verify

After saving the site config, **restart** it (alwaysdata reinitializes on save,
but restart if anything changed). Then open these URLs:

| Check | URL | What you should see |
|---|---|---|
| API docs (Swagger) | `https://lexnul.alwaysdata.net/api/docs/` | Interactive Swagger UI |
| API schema | `https://lexnul.alwaysdata.net/api/schema/` | JSON schema |
| Django admin | `https://lexnul.alwaysdata.net/admin/` | Admin login page |
| Login endpoint (POST) | `https://lexnul.alwaysdata.net/api/core/login/` | JSON response (no 500) |
| Public properties | `https://lexnul.alwaysdata.net/api/core/properties/available/` | JSON list |

**Quick command-line test from your Mac:**
```bash
curl -I https://lexnul.alwaysdata.net/api/docs/
# Expect: HTTP/2 200
```

> ✅ **Checkpoint:** Swagger loads and shows your endpoints. `curl -I` returns
> `200`. If you get a `500`, `404`, or `chdir()` page, jump to **Troubleshooting**.

---

## 10. Serve media files (uploaded photos) in production

Django only auto-serves `/media/` when `DEBUG=True`. In production you must
serve `media/` through alwaysdata. This is **already handled** by the
**Static paths** entry you added in Step 7:

```
/media=www/rental_django/media
```

So uploaded profile/property photos will be reachable at:
```
https://lexnul.alwaysdata.net/media/...
```

> ✅ **Checkpoint:** Visit a known uploaded photo URL, e.g.
> `https://lexnul.alwaysdata.net/media/landlords/Porsche_911.jpeg` — it should
> display the image.

---

## 11. Security checklist (do all of these)

- [ ] `DEBUG=False` in `.env`
- [ ] `SECRET_KEY` is a long random string, not committed to git
- [ ] `ALLOWED_HOSTS` only `lexnul.alwaysdata.net,localhost,127.0.0.1`
- [ ] `CORS_ALLOWED_ORIGINS` = your frontend origin(s)
- [ ] `CSRF_TRUSTED_ORIGINS` = `https://lexnul.alwaysdata.net`
- [ ] HTTPS is on (alwaysdata provides it automatically)
- [ ] `.env` is git-ignored (it already is)
- [ ] You created a superuser with a strong password
- [ ] DB password is strong and stored safely

The settings already auto-enable secure cookies, HSTS, `X-Frame-Options`,
`SECURE_CONTENT_TYPE_NOSNIFF`, and SSL redirect when `DEBUG=False`.

---

## 12. Troubleshooting (read this before panicking)

### A. `chdir(): No such file or directory` (uWSGI fails to start)
**Cause:** You entered **absolute** paths (`/home/lexnul/...`) in the site form.
**Fix:** Use **relative** paths (`www/rental_django/`). See Step 7.

### A2. `502 Bad Gateway` / `upstream prematurely closed connection` / `connection upstream`
These all mean the alwaysdata web server could not reach **or** get a response
from your Python app (Gunicorn/uWSGI). The app either **crashed**, **didn't
start**, or **timed out**.

**Fix (in order):**
1. **Check the app log first** — **Web → Sites → your site → Logs**. It shows the
   real underlying error (missing `.env`, DB failure, bad import, etc.).
2. **Restart the site** and reload the page.
3. Confirm the **Application path** and **Working directory** are **relative**
   (`www/rental_django/`), not absolute (this is the #1 cause).
4. Confirm the **virtualenv dir** is correct and the **Python version matches**
   the venv.
5. Confirm `.env` exists in the project root with correct values, and run
   `python manage.py check` on the server.
6. If a **single request** is slow (e.g. M-Pesa), it may be timing out — break
   it into a background task or increase the timeout.
7. If the server is **out of memory**, reduce the number of workers / check
   alwaysdata's RAM limits.

### B. Site loads but every page is a `500`
**Most common cause:** a missing/incorrect `.env`, or migrations not run.
1. Check the app log: **Web → Sites → your site → Logs**.
2. Confirm `.env` exists in the project root with correct values.
3. Run `python manage.py migrate` and `collectstatic` again.

### C. `DisallowedHost` / `Invalid HTTP_HOST header`
**Cause:** your domain isn't in `ALLOWED_HOSTS`.
**Fix:** add `lexnul.alwaysdata.net` to `ALLOWED_HOSTS` in `.env`, restart.

### D. Static files (admin/Swagger) look broken
**Fix:** run `python manage.py collectstatic --noinput` and confirm the
`/static` **Static path** points to `staticfiles/`. Restart the site.

### E. Media photos don't load
**Fix:** confirm the `/media` **Static path** points to `www/rental_django/media`. Verify the file exists on the server.

### F. M-Pesa callback not reaching your app
- The callback URL must be **public HTTPS**: `https://lexnul.alwaysdata.net/...`
- Confirm `MPESA_CALLBACK_URL` is set.
- Check the **app log** for callback errors.
- In the M-Pesa sandbox, the callback must be reachable from the internet.

### G. CORS errors in the frontend
**Fix:** set `CORS_ALLOWED_ORIGINS` in `.env` to your exact frontend origin
(e.g. `https://yourfrontend.com`). Restart. Do **not** use wildcards in
production.

### H. Emails (OTP / password reset) not delivering
- The default is `console` backend (prints to terminal — fine for dev).
- For real emails set `EMAIL_BACKEND=smtp` + the SMTP vars in `.env`.
- Use a **Gmail App Password**, not your normal password.

### I. `ImportError` / module not found on server
**Fix:** reinstall deps: `source venv/bin/activate && pip install -r requirements.txt`.
Confirm the venv Python version matches the site's Python version.

### J. Database connection refused
**Fix:** verify DB host/name/user/password in `.env`, and that the database
exists. Check alwaysdata's DB hostname (e.g. `mysql-lexnul.alwaysdata.net`).

---

## 13. Deploying updates (the repeatable workflow)

After every code change, redeploy like this:

```bash
# 1. Upload changed files (or git pull if you deployed via git)
scp -r rental/. lexnul@ssh-lexnul.alwaysdata.net:~/www/rental_django/

# 2. SSH in
ssh lexnul@ssh-lexnul.alwaysdata.net

# 3. Activate venv & apply changes
cd ~/www/rental_django
source venv/bin/activate
pip install -r requirements.txt    # only if deps changed
python manage.py migrate           # only if models changed
python manage.py collectstatic --noinput
```

Then **restart the site** in alwaysdata Admin (or wait for auto-restart).

> 💡 **Pro tip:** Test changes locally first, keep `.env` secrets out of git,
> and keep a backup of your database (see next section).

---

## 14. Backups & maintenance

### Database backup (do this regularly)
You can export your MySQL database from the alwaysdata Admin:
**Databases → MySQL → your database → Backup / Export.**

Or from SSH:
```bash
mysqldump -h mysql-lexnul.alwaysdata.net -u lexnul -p lexnul_renta > backup_$(date +%F).sql
```

### Media files
Uploaded photos live in `~/www/rental_django/media/`. Back them up by copying
the folder to your Mac periodically.

### Logs
Check **Web → Sites → your site → Logs** for errors. Keep an eye on the app
log after each deploy.

---

## 15. Final checklist — launch day

- [ ] All of Step 11 (security) is done
- [ ] `https://lexnul.alwaysdata.net/api/docs/` loads
- [ ] `https://lexnul.alwaysdata.net/admin/` loads & you can log in
- [ ] A test login API call works (returns JWT tokens)
- [ ] A test M-Pesa STK push works (or at least the callback is reachable)
- [ ] Media photos load at `/media/...`
- [ ] Database backup procedure is known & tested
- [ ] You know how to redeploy (Step 13)

---

## Appendix — handy reference commands

```bash
# Generate a Django secret key
python -c "import secrets; print(secrets.token_urlsafe(50))"

# SSH into the server
ssh lexnul@ssh-lexnul.alwaysdata.net

# Activate venv
cd ~/www/rental_django && source venv/bin/activate

# Run Django management commands
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
python manage.py check   # verify config is OK

# Test an endpoint from your Mac
curl -I https://lexnul.alwaysdata.net/api/docs/
```

---

*Good luck — you've got this. Follow the steps in order, use the checkpoints,
and refer to Troubleshooting before panicking. 🚀*
