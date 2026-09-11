"""Génère une SECRET_KEY et l'écrit dans .env sans jamais l'afficher.

    python manage.py generer_secret_key [--force] [--fichier .env.production]

Seule une empreinte partielle est affichée, pour confirmer l'écriture sans
révéler la clé.
"""

import hashlib
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.management.utils import get_random_secret_key


class Command(BaseCommand):
    help = "Génère une SECRET_KEY robuste et l'écrit dans .env (jamais affichée)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fichier",
            default=".env",
            help="Fichier à modifier, relatif à la racine du projet (défaut : .env).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Remplacer une SECRET_KEY déjà présente dans le fichier.",
        )

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        chemin = base_dir / options["fichier"]

        contenu = chemin.read_text(encoding="utf-8") if chemin.exists() else ""
        deja_presente = re.search(r"^SECRET_KEY=.+$", contenu, flags=re.MULTILINE)

        if deja_presente and not options["force"]:
            raise CommandError(
                f"{chemin.name} contient déjà une SECRET_KEY. Relancez avec "
                "--force pour la remplacer (toutes les sessions et tous les "
                "liens de réinitialisation en cours seront invalidés)."
            )

        nouvelle_cle = get_random_secret_key()
        # Guillemets simples : get_random_secret_key() peut tirer un '#', que
        # django-environ traite comme un commentaire hors quotes simples.
        assert "'" not in nouvelle_cle
        valeur_protegee = f"'{nouvelle_cle}'"

        if deja_presente:
            contenu = re.sub(
                r"^SECRET_KEY=.*$",
                f"SECRET_KEY={valeur_protegee}",
                contenu,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            ligne = f"SECRET_KEY={valeur_protegee}\n"
            contenu = ligne if not contenu else ligne + contenu

        # Écriture atomique (jamais de .env à moitié écrit).
        fichier_temp = chemin.with_suffix(chemin.suffix + ".tmp")
        fichier_temp.write_text(contenu, encoding="utf-8")
        fichier_temp.replace(chemin)

        try:
            chemin.chmod(0o600)
        except (NotImplementedError, OSError):
            pass  # sans effet sous Windows

        empreinte = hashlib.sha256(nouvelle_cle.encode()).hexdigest()[:8]
        self.stdout.write(
            self.style.SUCCESS(
                f"SECRET_KEY générée et écrite dans {chemin.name} "
                f"({len(nouvelle_cle)} caractères, empreinte {empreinte}…)."
            )
        )
        self.stdout.write(
            "La valeur n'a pas été affichée. Ne la copiez ni ne la transmettez : "
            "elle ne doit exister que dans ce fichier."
        )
