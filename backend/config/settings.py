"""Orbit settings. Values come from environment variables or backend/.env (via python-decouple)."""

from pathlib import Path

from decouple import Csv, config
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
FRONTEND_DIR = BASE_DIR.parent / "frontend"

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.github",
    "apps.core",
    "apps.accounts",
    "apps.projects",
    "apps.notes",
    "apps.insights",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.core.ratelimit.PostRateLimitMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [FRONTEND_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.csp",
                "apps.core.context_processors.orbit",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if config("DB_ENGINE", default="") == "mysql":
    db_host = config("DB_HOST", default="127.0.0.1")
    options = {"charset": "utf8mb4"}

    # TiDB Cloud / remote databases require SSL (Connections using insecure transport are prohibited)
    use_ssl = config("DB_SSL", default=False, cast=bool) or (db_host not in ("127.0.0.1", "localhost", ""))
    if use_ssl:
        import certifi

        ca_path = config("DB_SSL_CA", default="")
        if not ca_path and (BASE_DIR / "ca.pem").exists():
            ca_path = str(BASE_DIR / "ca.pem")
        if not ca_path:
            ca_path = certifi.where()

        options["ssl"] = {"ca": ca_path}
        options["ssl_mode"] = "VERIFY_IDENTITY"

    DATABASES = {
        "default": {
            "ENGINE": "config.tidb",
            "NAME": config("DB_NAME", default="orbit"),
            "USER": config("DB_USER", default="root"),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": db_host,
            "PORT": config("DB_PORT", default="3306"),
            "OPTIONS": options,
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = config("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [FRONTEND_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# --- Auth (django-allauth): sign in with Google or GitHub only, no passwords ---
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/accounts/login/"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*"]
ACCOUNT_EMAIL_VERIFICATION = "none"  # both providers hand us verified emails
ACCOUNT_ADAPTER = "apps.accounts.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "apps.accounts.adapters.SocialAccountAdapter"
SOCIALACCOUNT_STORE_TOKENS = True  # needed to call the GitHub API as the user
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_QUERY_EMAIL = True
# Same verified email on Google and GitHub -> one Orbit account.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

SOCIALACCOUNT_PROVIDERS = {}
if config("GOOGLE_CLIENT_ID", default=""):
    SOCIALACCOUNT_PROVIDERS["google"] = {
        "APPS": [{"client_id": config("GOOGLE_CLIENT_ID", default=""), "secret": config("GOOGLE_CLIENT_SECRET", default="")}],
        "SCOPE": ["profile", "email"],
    }
if config("GITHUB_CLIENT_ID", default=""):
    SOCIALACCOUNT_PROVIDERS["github"] = {
        "APPS": [{"client_id": config("GITHUB_CLIENT_ID", default=""), "secret": config("GITHUB_CLIENT_SECRET", default="")}],
        # public_repo: read public repos + create issues. Private repos -> personal key in Settings > Keys.
        "SCOPE": ["read:user", "user:email", "public_repo"],
    }

# --- Security ---
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # 2 weeks

# Content Security Policy: only our own scripts (plus nonce'd inline ones), no third-party JS.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],  # inline style="" is used for user-picked project colours
    "img-src": [CSP.SELF, "data:", "https:"],  # avatars + images in markdown
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    # OAuth sign-in posts to us, then redirects to the provider; browsers check that redirect too.
    "form-action": [CSP.SELF, "https://github.com", "https://accounts.google.com"],
}

# Rate limits (requests per minute) — see apps/core/ratelimit.py.
RATELIMIT_POST_PER_MINUTE = config("RATELIMIT_POST_PER_MINUTE", default=120, cast=int)

# shortcut: in-process cache, so rate limits count per worker process; switch to Redis cache when running several workers.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
