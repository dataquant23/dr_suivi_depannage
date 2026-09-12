"""Initialisation des comptes : mot de passe provisoire et courriels.

Le mot de passe provisoire est généré, envoyé une fois par courriel, puis
seul son hachage est conservé. `must_change_password` impose son
remplacement à la première connexion.
"""

import secrets

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

# Alphabet sans caractères ambigus (0/O, 1/l/I) : le mot de passe est recopié
# à la main depuis un courriel, souvent sur un clavier de téléphone.
_MINUSCULES = "abcdefghijkmnopqrstuvwxyz"
_MAJUSCULES = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_CHIFFRES = "23456789"
_SYMBOLES = "!@#$%*-+="

LONGUEUR_MOT_DE_PASSE_PROVISOIRE = 14


def generer_mot_de_passe_provisoire(longueur=LONGUEUR_MOT_DE_PASSE_PROVISOIRE):
    """Mot de passe provisoire aléatoire (`secrets`), retiré tant qu'il ne
    passe pas AUTH_PASSWORD_VALIDATORS."""
    if longueur < 12:
        raise ValueError("Un mot de passe provisoire fait au moins 12 caractères.")

    alphabet = _MINUSCULES + _MAJUSCULES + _CHIFFRES + _SYMBOLES
    for _ in range(20):
        # Au moins un caractère de chaque famille, puis complément et mélange.
        caracteres = [
            secrets.choice(_MINUSCULES),
            secrets.choice(_MAJUSCULES),
            secrets.choice(_CHIFFRES),
            secrets.choice(_SYMBOLES),
        ]
        caracteres += [secrets.choice(alphabet) for _ in range(longueur - 4)]
        secrets.SystemRandom().shuffle(caracteres)
        mot_de_passe = "".join(caracteres)
        try:
            validate_password(mot_de_passe)
        except ValidationError:
            continue
        return mot_de_passe
    raise RuntimeError("Impossible de générer un mot de passe provisoire valide.")


def _url_absolue(request, chemin):
    """URL complète pour un courriel (SITE_URL hors requête HTTP)."""
    if request is not None:
        return request.build_absolute_uri(chemin)
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    return f"{base}{chemin}"


def _envoyer(sujet, gabarit, contexte, destinataire):
    """Envoie un courriel texte + HTML. Retourne True si l'envoi a abouti."""
    corps_texte = render_to_string(f"comptes/courriels/{gabarit}.txt", contexte)
    message = EmailMultiAlternatives(
        subject=sujet,
        body=corps_texte,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[destinataire],
    )
    try:
        corps_html = render_to_string(f"comptes/courriels/{gabarit}.html", contexte)
    except Exception:  # pragma: no cover - gabarit HTML optionnel
        corps_html = None
    if corps_html:
        message.attach_alternative(corps_html, "text/html")
    return message.send(fail_silently=False) == 1


def initialiser_mot_de_passe(agent):
    """Attribue un mot de passe provisoire et le retourne en clair (pour
    envoi immédiat par courriel — ne pas journaliser ni stocker)."""
    from django.utils import timezone

    mot_de_passe = generer_mot_de_passe_provisoire()
    agent.set_password(mot_de_passe)
    agent.must_change_password = True
    # Depart du compte a rebours : passe ce delai, le provisoire ne permet
    # plus de se connecter (cf. `Agent.mot_de_passe_provisoire_expire`).
    agent.mot_de_passe_defini_le = timezone.now()
    agent.save(
        update_fields=["password", "must_change_password", "mot_de_passe_defini_le"]
    )
    return mot_de_passe


def envoyer_invitation(agent, mot_de_passe, request=None):
    """Courriel d'ouverture de compte : lien de connexion + mot de passe."""
    contexte = {
        "utilisateur": agent,
        "mot_de_passe": mot_de_passe,
        "lien_connexion": _url_absolue(request, reverse("comptes:connexion")),
        "application": settings.WEBAUTHN_RP_NAME,
    }
    return _envoyer(
        sujet="Vos accès à l'application Gestion des dépannages",
        gabarit="invitation",
        contexte=contexte,
        destinataire=agent.email,
    )


def creer_et_inviter(agent, request=None):
    """Génère le mot de passe provisoire puis envoie l'invitation (l'erreur
    d'envoi remonte à l'appelant)."""
    mot_de_passe = initialiser_mot_de_passe(agent)
    envoyer_invitation(agent, mot_de_passe, request=request)
    return mot_de_passe
