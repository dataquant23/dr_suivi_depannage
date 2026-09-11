"""Modèles côté comptes.

L'identité est portée par `core.Agent` (socle partagé). Seule la clé
WebAuthn est propre à ce projet.
"""

from django.conf import settings
from django.db import models


class WebAuthnCredential(models.Model):
    """Clé publique WebAuthn enrôlée pour un appareil (la clé privée reste
    dans le téléphone)."""

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cles_webauthn"
    )
    credential_id = models.CharField("identifiant de clé", max_length=500, unique=True)
    public_key = models.TextField("clé publique")
    sign_count = models.PositiveIntegerField("compteur de signature", default=0)
    libelle_appareil = models.CharField("appareil", max_length=150, blank=True)
    transports = models.CharField("transports", max_length=120, blank=True)
    cree_le = models.DateTimeField("enrôlé le", auto_now_add=True)
    derniere_utilisation = models.DateTimeField(
        "dernière utilisation", null=True, blank=True
    )

    class Meta:
        verbose_name = "clé WebAuthn"
        verbose_name_plural = "clés WebAuthn"
        ordering = ["-cree_le"]

    def __str__(self):
        return f"{self.utilisateur} - {self.libelle_appareil or 'appareil'}"
