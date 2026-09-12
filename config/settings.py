"""Configuration Django — Gestion des dépannages.

Projet autonome : le socle `core` (agents, accès, authentification) est
embarqué dans ce dépôt, aucune dépendance à django_dran sur la machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    ALLOWED_HOSTS=(list, ["innovation.dxteriz.com", "localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(
        list,
        ["https://innovation.dxteriz.com", "http://localhost", "http://127.0.0.1"],
    ),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-secret-a-remplacer-en-production")
DEBUG = env("DEBUG")
TESTING = "test" in sys.argv or "pytest" in Path(sys.argv[0]).name
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

USE_X_FORWARDED_HOST = True

BASE_PATH = env("BASE_PATH", default="/dr_depannage")


def _norm_base(chemin: str) -> str:
    if not chemin or chemin == "/":
        return ""
    return chemin.strip("/")


_BASE = _norm_base(BASE_PATH)
URL_PREFIX = _BASE

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    "core.apps.CoreConfig",
    "comptes",
    "referentiel",
    "depannages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Après AuthenticationMiddleware (besoin de request.user).
    "comptes.middleware.ChangementMotDePasseObligatoireMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "depannages.context_processors.badges_navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de donnees ------------------------------------------------------
# Base autonome, initialisée par copie de django_dran/data/dran.sqlite3.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("DJANGO_DB_NAME", default=str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {"timeout": 20},
    }
}

# Propriétaire du socle : applique les migrations core/auth/sessions/admin.
DR_SOCLE_PROPRIETAIRE = env.bool("DR_SOCLE_PROPRIETAIRE", default=True)
DATABASE_ROUTERS = ["core.routers.RouteurBasePartagee"]

AUTH_USER_MODEL = "core.Agent"
AUTHENTICATION_BACKENDS = ["core.backends.MatriculeBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},  # 10 au lieu de 8
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Argon2 en tete : bien plus couteux a casser sur GPU que PBKDF2. Les
# condensats deja stockes restent lisibles (hacheurs suivants) et sont
# re-encodes en Argon2 a la connexion suivante de chaque agent.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
    "core.hashers.WerkzeugScryptPasswordHasher",
]

LOGIN_URL = "comptes:connexion"
LOGIN_REDIRECT_URL = "depannages:travaux_en_cours"
LOGOUT_REDIRECT_URL = "comptes:connexion"

# SSO inter-applications (voir core.sso).
DR_HOTES_SSO = [h.strip() for h in env("DR_HOTES_SSO", default="").split(",") if h.strip()]
DR_URL_CONNEXION = env("DR_URL_CONNEXION", default="")

# Anti brute-force (core.security).
DR_LOGIN_MAX_ATTEMPTS = env.int("DR_LOGIN_MAX_ATTEMPTS", default=5)
DR_LOGIN_LOCKOUT_SECONDS = env.int("DR_LOGIN_LOCKOUT_SECONDS", default=5 * 60)

# Plafond des demandes d'activation de compte par adresse (core.services.
# authentification.traite_nouvel_utilisateur).
DR_ACTIVATION_MAX_TENTATIVES = env.int("DR_ACTIVATION_MAX_TENTATIVES", default=5)
DR_ACTIVATION_FENETRE_SECONDES = env.int("DR_ACTIVATION_FENETRE_SECONDES", default=60 * 60)

# Direction régionale par défaut, exigée par le socle pour amorcer
# core.DirectionRegionale sur une base fraîche.
DR_CODE_DEFAUT = env("DR_CODE_DEFAUT", default="DRAN")
DR_NOM_DEFAUT = env("DR_NOM_DEFAUT", default="Direction Régionale Abidjan Nord")
DR_CODE_SECTEUR_DEFAUT = env("DR_CODE_SECTEUR_DEFAUT", default="040")

# --- Localisation -----------------------------------------------------------
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Abidjan"
USE_I18N = True
USE_TZ = True

# --- Fichiers statiques et medias -------------------------------------------
STATIC_URL = f"/{_BASE}/static/" if _BASE else "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

MEDIA_URL = f"/{_BASE}/media/" if _BASE else "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Taille maximale d'une photo envoyee depuis le terrain (10 Mo).
TAILLE_MAX_PHOTO_MO = 10
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- WebAuthn (connexion par empreinte) -------------------------------------
# Exige HTTPS hors localhost.
WEBAUTHN_RP_ID = env("WEBAUTHN_RP_ID", default="localhost")
WEBAUTHN_RP_NAME = env("WEBAUTHN_RP_NAME", default="Gestion des depannages")
WEBAUTHN_ORIGIN = env("WEBAUTHN_ORIGIN", default="http://localhost:8000")

# --- Fond de carte (MapTiler, compte gratuit) -------------------------------
# Cle a restreindre par domaine dans le tableau de bord MapTiler.
MAPTILER_KEY = env("MAPTILER_KEY", default="")

# --- Cache ------------------------------------------------------------------
# Compteur anti brute-force. Renseigner CACHE_URL (Redis...) dès qu'il y a
# plus d'un worker, sinon le plafond est compté par processus.
CACHES = {"default": env.cache("CACHE_URL", default="locmemcache://")}

# --- Courriel --------------------------------------------------------------
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="dataquant.pwdreset@gmail.com")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=20)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL",
    default=f"Gestion des depannages <{EMAIL_HOST_USER}>",
)

# Sans mot de passe SMTP, les courriels s'affichent dans la console.
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.smtp.EmailBackend"
        if EMAIL_HOST_PASSWORD
        else "django.core.mail.backends.console.EmailBackend"
    ),
)

# URL de base pour les liens des courriels hors requête HTTP.
SITE_URL = env("SITE_URL", default="http://localhost:8000")

# Duree de vie du mot de passe provisoire envoye par courriel. Passe ce
# delai, il ne permet plus de se connecter : l'agent repasse par « mot de
# passe oublie ». Mettre 0 desactive l'expiration.
MOT_DE_PASSE_PROVISOIRE_JOURS = env.int("MOT_DE_PASSE_PROVISOIRE_JOURS", default=2)
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=2 * 60 * 60)

# --- Securite (activee automatiquement hors DEBUG) --------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_HTTPONLY = True
    X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True

# Déconnexion automatique après 2 h d'inactivité.
SESSION_COOKIE_AGE = 2 * 60 * 60
SESSION_SAVE_EVERY_REQUEST = True
