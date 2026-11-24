# EstateHub Naija

EstateHub Naija is a Django real-estate listings website. It includes property search and details, agent accounts and listing management, saved properties and searches, and email-based account verification and notifications.

## Requirements

- Python 3.12 or newer
- Git
- Internet access to install Python packages

The project uses SQLite for local development, so you do not need to install a separate database server. No Node.js build step is required.

## Get the source code

Clone this repository, then change into the project directory containing `manage.py` and `requirements.txt`:

```bash
git clone https://github.com/okorocy089-crypto/Estatehub-Naija.git
cd ehub
```

Replace `<repository-url>` with this repository's Git URL. If you already have the source code, open a terminal in the directory containing `manage.py`.

## Create a virtual environment

Use the instructions for your operating system. Activate the environment before installing dependencies or running Django commands.

### Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell cannot find `py`, install Python 3.12 or newer from [python.org](https://www.python.org/downloads/windows/) and select the option to add Python to `PATH`. If script activation is blocked, activate the environment from Command Prompt instead:

```bat
.venv\Scripts\activate.bat
```

### macOS

Install Python 3.12 or newer if needed, for example with [Homebrew](https://brew.sh/):

```bash
brew install python
python3 -m venv .venv
source .venv/bin/activate
```

### Linux

Install Python 3.12 or newer and the venv package for your distribution. On Debian or Ubuntu, for example:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
```

If your distribution's default Python is older than 3.12, install a newer Python release and use its versioned executable (for example, `python3.12`) to create the environment.

## Install and initialize

Run these commands from the project directory, with the virtual environment activated:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
```

The migrations create the local SQLite database. Do not run `makemigrations` for a normal setup; the project's migrations are already included.

To create an administrator account for `/admin/`, run:

```bash
python manage.py createsuperuser
```

This step is optional.

## Start the development server

```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) in your browser. The Django admin is at [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/).

Stop the server with `Ctrl+C`. To exit the virtual environment, run `deactivate`.

## Optional configuration

### Email delivery

Without SMTP credentials, the project uses Django's console email backend. Verification and password-reset messages are printed in the terminal running the development server.

To send email through SMTP, copy `.env.example` to `.env` and enter your mail provider's settings:

**PowerShell**

```powershell
Copy-Item .env.example .env
```

**macOS and Linux**

```bash
cp .env.example .env
```

Edit `.env` and set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, and `DEFAULT_FROM_EMAIL` as appropriate for your provider. For Gmail, use a Google App Password rather than your regular account password. Keep `.env` private; it is excluded from Git.

### Google sign-in

Google sign-in is optional. Set `GOOGLE_CLIENT_ID` in `.env` to the OAuth 2.0 client ID for a Google web application, and add your local site origin (such as `http://127.0.0.1:8000`) to that client's authorized JavaScript origins. Email and password authentication works without Google credentials.

## Tests

Run the Django test suite with:

```bash
python manage.py test
```

## Troubleshooting

- **Django is not installed:** confirm the virtual environment is activated, then run `python -m pip install -r requirements.txt` again.
- **The virtual environment cannot be created on Linux:** install the Python `venv` package for your distribution (for Debian/Ubuntu, `python3-venv`).
- **Database tables are missing:** run `python manage.py migrate` from the directory containing `manage.py`.
- **Email did not arrive:** without complete SMTP configuration, check the development server terminal for the email contents.
- **Uploaded images or documents are not visible:** use the Django development server while `DEBUG` is enabled; it serves local media files for development.

## Production deployment

The included Django settings are intended for local development, not direct production deployment. Before deploying, configure a production secret key, disable `DEBUG`, restrict allowed hosts and CSRF trusted origins, configure persistent database and media storage, and serve static files through an appropriate web server or hosting platform. Review the security and privacy pages for your jurisdiction before using them in production.
