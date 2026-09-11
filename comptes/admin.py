from django.contrib import admin

from .models import WebAuthnCredential

# L'identité (core.Agent) s'administre dans django_dran.


@admin.register(WebAuthnCredential)
class WebAuthnCredentialAdmin(admin.ModelAdmin):
    list_display = ("utilisateur", "libelle_appareil", "cree_le", "derniere_utilisation")
    search_fields = ("utilisateur__matricule", "libelle_appareil")
    readonly_fields = ("credential_id", "public_key", "sign_count")
