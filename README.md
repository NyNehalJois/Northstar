# Northstar — Training Management

Northstar is a responsive training operations app for managing courses, learners, and course enrollments. It combines a Flask and SQLite backend with a custom, framework-free HTML, CSS, and JavaScript interface.

## Project highlights

- Course lifecycle management with date, capacity, and status validation
- Learner directory with contact details, search, and duplicate-email protection
- Course rosters with enrollment limits, duplicate prevention, and unenrollment
- Archive and restore workflows that preserve enrollment history
- Admin-only access with CSRF-protected state changes
- Responsive desktop and mobile layouts with persistent light, dark, and system themes
- SQLite persistence and a Render Blueprint for single-instance deployment

## Technology

Python 3 · Flask · SQLite · Jinja · HTML · CSS · Vanilla JavaScript · Render

## LinkedIn project description

> Built Northstar, a responsive training management platform for organizing courses, learners, and enrollments. The app includes course capacity and date validation, searchable learner management, roster and archive workflows, administrator authentication, and persistent light/dark themes. Built with Python, Flask, SQLite, and a custom framework-free frontend.

## Run locally

1. Create and activate a virtual environment:

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the dependency:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Set administrator credentials and a stable session secret in PowerShell:

   ```powershell
   $env:ADMIN_USERNAME = "choose-an-admin-name"
   $env:ADMIN_PASSWORD = "choose-a-long-unique-password"
   $env:FLASK_SECRET_KEY = "set-a-long-random-secret"
   ```

   Do not commit real credentials or session secrets. The app has local-development fallback credentials (`admin123` / `123`); always replace them with strong, unique environment values before deploying or exposing the app to a network.

4. Start the app:

   ```powershell
   python app.py
   ```

5. Open the local address printed by Flask (usually `http://127.0.0.1:5000`) and sign in.

The SQLite database is created automatically at `instance/training.db`. Management pages require administrator sign-in and state-changing forms are protected with CSRF tokens. Keep the app bound to localhost unless you configure HTTPS and production deployment settings.

To run the focused tests:

```powershell
python -m unittest discover -s tests -v
```

Set `FLASK_SECRET_KEY` to a stable secret before using the app across restarts. Set `FLASK_DEBUG=1` only for local development when you need Flask's debugger.
All state-changing forms use CSRF tokens. For an HTTPS deployment, set `FLASK_COOKIE_SECURE=1`.

## Deploy to Render

The repository includes `render.yaml` for a single-instance Render web service with a 1 GB persistent disk mounted at `/var/data`. The SQLite database is stored on that disk, not on Render's ephemeral application filesystem. Render requires a paid web-service plan for persistent disks; review its current pricing before creating the service.

1. Push this project to a GitHub repository you control. Do not commit `.venv`, `instance`, or real credentials.
2. In Render, create a Blueprint from that repository and select `render.yaml`.
3. Provide a unique `ADMIN_USERNAME` and a long, unique `ADMIN_PASSWORD` when prompted. Render generates `FLASK_SECRET_KEY`. Never use the local fallback credentials on a public deployment.
4. Wait for the deploy and health check to succeed. Render will show the public `onrender.com` URL in the service overview.

The disk-backed SQLite setup is intentionally a single service instance; it is suitable for a small internal platform, not horizontal scaling. Set up regular backups before relying on the hosted database for important records.

## Included flows

- Dashboard counts and a course overview
- Course creation, capacity, dates, instructor, and status
- Course editing with safeguards against reducing capacity below current enrollment
- Learner creation and case-insensitive duplicate email protection
- Learner contact detail editing with duplicate email protection
- Course rosters, enrollment, duplicate prevention, capacity enforcement, and unenrollment
- Course and learner archiving/restoring without deleting roster or enrollment history
- Settings page with persistent light, dark, and system appearance preferences
- Responsive layouts and searchable learner list
