"""Importe les communes et quartiers depuis un extrait OpenStreetMap (.osm.pbf).

    python manage.py importer_quartiers ivory-coast-260826.osm.pbf
    python manage.py importer_quartiers fichier.pbf --bbox 5.10,-4.40,5.65,-3.70

Par defaut la bbox couvre tout le pays : les DR/DC hors Grand Abidjan (Nord,
Ouest...) trouvent deja leur decoupage geographique le jour ou elles sont
ajoutees, sans reimport. Les contours sont stockes en GeoJSON dans la table
Quartier : aucune dependance a PostGIS, le rattachement d un depannage se
fait en Python.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from referentiel.models import NiveauZone, Quartier

# Cote d Ivoire entiere par defaut : lat_min, lon_min, lat_max, lon_max.
# Passer --bbox 5.10,-4.40,5.65,-3.70 pour se limiter au Grand Abidjan.
BBOX_DEFAUT = (4.2, -8.7, 10.8, -2.4)

# Ce qui fait une commune : arrondissement / commune urbaine.
NIVEAUX_COMMUNE = {"7", "8"}
PLACES_COMMUNE = {"suburb", "municipality", "city", "town"}

# Subdivisions d'une commune. Le niveau réel (QUARTIER/SOUS_QUARTIER) n'est
# pas déduit d'admin_level (non comparable d'une commune à l'autre dans OSM)
# mais de l'emboîtement géométrique : voir _rattacher_hierarchie.
NIVEAUX_SUBDIVISION = {"9", "10", "11"}
PLACES_SUBDIVISION = {"neighbourhood", "quarter", "locality", "village", "hamlet"}


class Command(BaseCommand):
    help = "Importe les polygones de communes et quartiers depuis un fichier .osm.pbf"

    def add_arguments(self, parseur):
        parseur.add_argument("fichier", help="Chemin du fichier .osm.pbf")
        parseur.add_argument(
            "--bbox",
            help="Zone a importer : lat_min,lon_min,lat_max,lon_max",
            default=",".join(str(v) for v in BBOX_DEFAUT),
        )
        parseur.add_argument(
            "--tolerance",
            type=float,
            default=0.00015,
            help="Simplification des contours en degres (0 pour desactiver).",
        )
        parseur.add_argument(
            "--remplacer",
            action="store_true",
            help="Vide le referentiel de zones avant import.",
        )

    def handle(self, *args, **options):
        try:
            import osmium
        except ImportError as erreur:
            raise CommandError(
                "La bibliotheque osmium est requise : pip install osmium"
            ) from erreur

        chemin = Path(options["fichier"])
        if not chemin.exists():
            raise CommandError(f"Fichier introuvable : {chemin}")

        try:
            lat_min, lon_min, lat_max, lon_max = (
                float(v) for v in options["bbox"].split(",")
            )
        except ValueError as erreur:
            raise CommandError("Format de bbox attendu : lat_min,lon_min,lat_max,lon_max") from erreur

        tolerance = options["tolerance"]
        self.stdout.write(f"Lecture de {chemin.name} ({chemin.stat().st_size / 1e6:.0f} Mo)...")
        self.stdout.write(
            f"Zone : lat {lat_min} a {lat_max}, lon {lon_min} a {lon_max}"
        )

        zones = self._extraire(osmium, chemin, (lat_min, lon_min, lat_max, lon_max), tolerance)
        self.stdout.write(f"{len(zones)} zone(s) retenue(s) dans la bbox.")

        with transaction.atomic():
            if options["remplacer"]:
                supprimees = Quartier.objects.all().delete()[0]
                self.stdout.write(self.style.WARNING(f"{supprimees} zone(s) supprimee(s)."))
            crees, majs = self._enregistrer(zones)
            rattaches_commune, reclasses_sous_quartier = self._rattacher_hierarchie()

        self.stdout.write(self.style.SUCCESS("\nImport termine."))
        self.stdout.write(f"  Creees                       : {crees}")
        self.stdout.write(f"  Mises a jour                 : {majs}")
        self.stdout.write(f"  Communes                     : {Quartier.objects.filter(niveau=NiveauZone.COMMUNE).count()}")
        self.stdout.write(f"  Quartiers                    : {Quartier.objects.filter(niveau=NiveauZone.QUARTIER).count()}")
        self.stdout.write(f"  Sous-quartiers               : {Quartier.objects.filter(niveau=NiveauZone.SOUS_QUARTIER).count()}")
        self.stdout.write(f"  Subdivisions rattachees      : {rattaches_commune}")
        self.stdout.write(f"  Dont reclassees sous-quartier: {reclasses_sous_quartier}")
        self.stdout.write(
            "\nRattacher les dossiers existants : "
            "python manage.py rattacher_depannages"
        )

    # --- Lecture du fichier OSM ------------------------------------------

    def _extraire(self, osmium, chemin, bbox, tolerance):
        lat_min, lon_min, lat_max, lon_max = bbox
        zones = []

        processeur = (
            osmium.FileProcessor(str(chemin))
            .with_areas()
            .with_filter(osmium.filter.KeyFilter("boundary", "place"))
        )

        for objet in processeur:
            if not isinstance(objet, osmium.osm.Area):
                continue
            tags = dict(objet.tags)
            nom = tags.get("name")
            if not nom:
                continue

            niveau = self._classer(tags)
            if niveau is None:
                continue

            try:
                geometrie = self._geometrie(objet, tolerance)
            except (RuntimeError, osmium.InvalidLocationError):
                continue
            if geometrie is None:
                continue

            boite = geometrie.pop("_bbox")
            if not (
                lat_min <= boite["centre_lat"] <= lat_max
                and lon_min <= boite["centre_lon"] <= lon_max
            ):
                continue

            zones.append(
                {
                    "nom": nom,
                    "niveau": niveau,
                    "osm_id": objet.orig_id(),
                    "source": self._source(tags),
                    "contour": geometrie,
                    **boite,
                }
            )
        return zones

    @staticmethod
    def _classer(tags):
        """COMMUNE, QUARTIER (subdivision, niveau precis a determiner apres
        coup par _rattacher_hierarchie) ou None selon les tags OSM."""
        if tags.get("boundary") == "administrative":
            niveau_admin = tags.get("admin_level")
            if niveau_admin in NIVEAUX_COMMUNE:
                return NiveauZone.COMMUNE
            if niveau_admin in NIVEAUX_SUBDIVISION:
                return NiveauZone.QUARTIER
        lieu = tags.get("place")
        if lieu in PLACES_COMMUNE:
            return NiveauZone.COMMUNE
        if lieu in PLACES_SUBDIVISION:
            return NiveauZone.QUARTIER
        return None

    @staticmethod
    def _source(tags):
        if tags.get("boundary") == "administrative":
            return f"OSM admin_level={tags.get('admin_level')}"
        return f"OSM place={tags.get('place')}"

    def _geometrie(self, aire, tolerance):
        """Construit un GeoJSON Polygon/MultiPolygon et sa boite englobante."""
        polygones = []
        lats, lons = [], []

        for anneau_ext in aire.outer_rings():
            exterieur = self._anneau(anneau_ext, tolerance, lats, lons)
            if len(exterieur) < 4:
                continue
            polygone = [exterieur]
            for anneau_int in aire.inner_rings(anneau_ext):
                trou = self._anneau(anneau_int, tolerance, [], [])
                if len(trou) >= 4:
                    polygone.append(trou)
            polygones.append(polygone)

        if not polygones or not lats:
            return None

        if len(polygones) == 1:
            geometrie = {"type": "Polygon", "coordinates": polygones[0]}
        else:
            geometrie = {"type": "MultiPolygon", "coordinates": polygones}

        geometrie["_bbox"] = {
            "lat_min": min(lats),
            "lat_max": max(lats),
            "lon_min": min(lons),
            "lon_max": max(lons),
            "centre_lat": (min(lats) + max(lats)) / 2,
            "centre_lon": (min(lons) + max(lons)) / 2,
        }
        return geometrie

    def _anneau(self, anneau, tolerance, lats, lons):
        points = []
        for noeud in anneau:
            points.append([round(noeud.lon, 6), round(noeud.lat, 6)])
            lats.append(noeud.lat)
            lons.append(noeud.lon)
        if tolerance > 0 and len(points) > 8:
            points = _simplifier(points, tolerance)
        # Un anneau GeoJSON doit etre ferme.
        if points and points[0] != points[-1]:
            points.append(points[0])
        return points

    # --- Enregistrement ---------------------------------------------------

    def _enregistrer(self, zones):
        crees = majs = 0
        for zone in zones:
            _, cree = Quartier.objects.update_or_create(
                osm_id=zone["osm_id"],
                defaults={
                    "nom": zone["nom"],
                    "niveau": zone["niveau"],
                    "source": zone["source"],
                    "contour": zone["contour"],
                    "lat_min": zone["lat_min"],
                    "lat_max": zone["lat_max"],
                    "lon_min": zone["lon_min"],
                    "lon_max": zone["lon_max"],
                    "centre_lat": zone["centre_lat"],
                    "centre_lon": zone["centre_lon"],
                    "actif": True,
                },
            )
            crees += cree
            majs += not cree
        return crees, majs

    def _rattacher_hierarchie(self):
        """Determine le niveau reel des subdivisions et les rattache a leurs parents.

        Toutes les subdivisions sont importees au niveau QUARTIER (voir
        _classer) : le numero admin_level d OSM n est pas comparable d une
        commune a l autre (Cocody est detaillee en admin_level=9 ; Attecoube
        et Yopougon directement en admin_level=10, sans niveau intermediaire).

        Le niveau reel est donc deduit de l emboitement geometrique : une
        subdivision contenue dans une autre subdivision plus grande de la
        meme commune devient SOUS_QUARTIER de celle-ci ; sinon elle reste
        QUARTIER, rattachee directement a la commune.
        """
        communes = list(Quartier.objects.filter(niveau=NiveauZone.COMMUNE, actif=True))
        subdivisions = list(
            Quartier.objects.filter(niveau=NiveauZone.QUARTIER, actif=True)
        )

        # Passe 1 : chaque subdivision rattachee a sa commune.
        rattaches_commune = 0
        par_commune = {}
        for zone in subdivisions:
            commune = self._plus_petit_contenant(communes, zone)
            if commune is None:
                continue
            if zone.commune_id != commune.pk:
                zone.commune = commune
            par_commune.setdefault(commune.pk, []).append(zone)
            rattaches_commune += 1

        # Passe 2 : au sein d une meme commune, une subdivision contenue dans
        # une autre plus grande devient son sous-quartier.
        rattaches_sous_quartier = 0
        for zones_commune in par_commune.values():
            for zone in zones_commune:
                conteneurs = [
                    autre
                    for autre in zones_commune
                    if autre.pk != zone.pk
                    and autre.surface_approx_km2 > zone.surface_approx_km2
                    and autre.contient(zone.centre_lat, zone.centre_lon)
                ]
                if conteneurs:
                    parent = min(conteneurs, key=lambda z: z.surface_approx_km2)
                    zone.niveau = NiveauZone.SOUS_QUARTIER
                    zone.quartier = parent
                    rattaches_sous_quartier += 1
                else:
                    zone.niveau = NiveauZone.QUARTIER
                    zone.quartier = None

        for zone in subdivisions:
            zone.save(update_fields=["niveau", "commune", "quartier"])

        return rattaches_commune, rattaches_sous_quartier

    @staticmethod
    def _plus_petit_contenant(candidats, zone):
        """Parmi les candidats contenant le centre de `zone`, le plus petit."""
        trouves = [c for c in candidats if c.contient(zone.centre_lat, zone.centre_lon)]
        if not trouves:
            return None
        return min(trouves, key=lambda c: c.surface_approx_km2)


def _simplifier(points, tolerance):
    """Simplification Douglas-Peucker : allege les contours pour la carte."""
    if len(points) < 3:
        return points

    def distance(point, debut, fin):
        (x, y), (x1, y1), (x2, y2) = point, debut, fin
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
        t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        px, py = x1 + t * dx, y1 + t * dy
        return ((x - px) ** 2 + (y - py) ** 2) ** 0.5

    pile = [(0, len(points) - 1)]
    garder = {0, len(points) - 1}
    while pile:
        debut, fin = pile.pop()
        if fin <= debut + 1:
            continue
        distance_max, indice_max = 0.0, debut
        for i in range(debut + 1, fin):
            d = distance(points[i], points[debut], points[fin])
            if d > distance_max:
                distance_max, indice_max = d, i
        if distance_max > tolerance:
            garder.add(indice_max)
            pile.append((debut, indice_max))
            pile.append((indice_max, fin))
    return [points[i] for i in sorted(garder)]
