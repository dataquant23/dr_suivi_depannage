# Gestion des depannages

Application Django de digitalisation des rapports de depannage : saisie terrain
depuis le telephone, suivi des dossiers a cloturer, cartographie, itineraire,
alertes de depassement de delai et gestion des acces.

## Demarrage rapide

```bash
venv/Scripts/python.exe manage.py migrate
venv/Scripts/python.exe manage.py initialiser --demo
venv/Scripts/python.exe manage.py runserver
```

Puis ouvrir http://127.0.0.1:8000/

### Comptes de demonstration

Mot de passe commun : `depannage2026`

| Identifiant | Role | Peut |
|---|---|---|
| `depanneur` | Depanneur | Saisir, consulter travaux en cours, carte, itineraire |
| `agentdcrd` | Agent activites DCRD | Idem, pour les activites transmises a la DC |
| `responsable` | Responsable | Tout consulter, alertes, **modifier les delais** |
| `admin` | Administrateur | En plus : **gerer les acces et les roles** |

## Architecture

```
config/        settings, urls
comptes/       Utilisateur (roles, perimetre), WebAuthnCredential, authentification
referentiel/   Structure, Secteur, Equipement, ParametreDelai, administration
depannages/    Depannage, PhotoDepannage, HistoriqueStatut, carte, recapitulatif
templates/     gabarits (sidebar navy, contenu clair, accent bleu)
static/css/    app.css - systeme visuel unique
media/         photos des ouvrages et fiches d avis
```

Une seule base de donnees. Le perimetre par structure est filtre au niveau
applicatif (`DepannageQuerySet.pour_utilisateur`), pas par base separee : les
responsables gardent ainsi des statistiques globales.

## Fonctionnalites

**Saisie terrain** (`/saisie/`) - un seul ecran : N BT, secteur, position GPS
captee automatiquement, definitif / a cloturer, nature du dossier, equipements
coches par structure responsable, photo de l ouvrage et photo de la fiche d avis
(prise dans l application ou fichier joint), commentaire.

**Travaux en cours** (`/travaux-en-cours/`) - dossiers encore ouverts,
compteurs shuntes remontes en tete avec marqueur rouge, anciennete et etat du
delai par ligne, filtres secteur / type / delai, recherche par N BT.

**Carte** (`/carte/`) - marqueurs differencies par categorie,
quartiers colories, resume de zone, recherche par N BT et rayon parametrable
autour d un point de reference.

**Recapitulatif** (`/recapitulatif/`) - semaine, mois ou periode personnalisee ;
repartition par secteur, commune, quartier, equipement et agent ; delai moyen de
cloture ; export Excel (synthese + detail filtrable) et export PDF.

**Alertes** (`/alertes/`, responsable) - delais depasses, echeances proches,
dossiers sans photo de fiche, BT avec interventions repetees.

**Administration** (`/referentiel/`) - delais modifiables avec journal des
changements ; comptes, roles et perimetres (administrateur uniquement).

## Delais de traitement

Valeurs par defaut, modifiables par le responsable :

| Cas | Delai |
|---|---|
| Compteur shunte | 48 h |
| Client sans electricite | 24 h |
| Autres equipements | 48 h |

Le compteur demarre a l enregistrement du dossier et s arrete a la
cloture. Trois etats : `OK` (sous le seuil), `BIENTOT` (seuil a 100 %),
`DEPASSE`. Le delai est fige a la creation du dossier : modifier le parametrage
n affecte les dossiers deja ouverts que si le responsable le demande
explicitement. Chaque modification est tracee (champ, avant, apres, qui, quand).

## Authentification par empreinte

L application etant servie par Django dans le navigateur, la biometrie passe par
**WebAuthn** : le navigateur pilote le capteur d empreinte / Face ID du telephone.

1. Premiere connexion : identifiant + mot de passe.
2. Depuis `/comptes/profil/`, activation du deverrouillage par empreinte : une
   paire de cles est generee, la cle privee reste dans le Secure Enclave /
   Keystone du telephone, seule la cle publique est enregistree en base.
3. Connexions suivantes : empreinte posee, le navigateur signe un challenge,
   Django verifie la signature.
4. Repli mot de passe toujours disponible.

**Aucune donnee biometrique n est transmise ni stockee par Django.**

### Prerequis de production

- **HTTPS obligatoire** : WebAuthn ne fonctionne pas en HTTP hors localhost.
- Renseigner dans `.env` :

```
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=depannage.exemple.ci
WEBAUTHN_RP_ID=depannage.exemple.ci
WEBAUTHN_ORIGIN=https://depannage.exemple.ci
DATABASE_URL=postgres://utilisateur:motdepasse@serveur:5432/depannages
```

Le `WEBAUTHN_RP_ID` doit correspondre au domaine servi, sinon les empreintes
enrolees cessent de fonctionner.

## Decoupage territorial (quartiers)

Les contours de communes et de quartiers sont importes une fois depuis un
extrait OpenStreetMap au format `.osm.pbf` (par exemple celui de Geofabrik pour
la Cote d Ivoire) :

```bash
python manage.py importer_quartiers ivory-coast-260826.osm.pbf
python manage.py rattacher_depannages --tous
```

- Par defaut la bbox couvre **tout le pays** (pas seulement le Grand Abidjan) :
  le decoupage geographique des DR/DC hors Abidjan (Nord, Ouest...) est deja en
  base, meme si aucun secteur ni dossier n y existe encore. Pour se limiter au
  Grand Abidjan : `--bbox 5.10,-4.40,5.65,-3.70`.
- `importer_quartiers` retient `boundary=administrative` (admin_level 7-8 pour
  les communes, 9-11 pour les quartiers) et `place=suburb|neighbourhood|quarter`.
- Les contours sont stockes en GeoJSON dans la table `Quartier` : **pas de
  PostGIS ni de GeoDjango**, le test point-dans-polygone se fait en Python avec
  un prefiltre par boite englobante.
- Les contours sont simplifies (Douglas-Peucker, tolerance ~15 m) : 236 zones
  (pays entier) pesent environ 520 Ko en base.
- `--bbox lat_min,lon_min,lat_max,lon_max` limite l import a une zone ; le defaut
  couvre le Grand Abidjan.

Chaque depannage est rattache automatiquement a son quartier et a sa commune
lors de l enregistrement, et le rattachement est recalcule si la position change.

**Couverture** : OpenStreetMap decrit finement certaines communes (Cocody,
Attecoube, Abobo...) et pas d autres. Quand aucun quartier ne correspond,
l analyse retombe sur la commune, puis sur le secteur saisi.

## Dependances externes

La carte utilise Leaflet et les tuiles OpenStreetMap chargees depuis un CDN.
Pour un deploiement sans acces internet sortant, telecharger Leaflet dans
`static/` et heberger un serveur de tuiles interne.

`osmium` n est necessaire que pour l import des quartiers, pas a l execution.

## Reste a faire

- **Mode hors ligne** (service worker + file d attente locale) : prevu dans le
  wireframe, pas encore implemente.
- Relance automatique des structures sur depassement de delai.
- Enrichir le decoupage des quartiers la ou OpenStreetMap est lacunaire
  (import d un fichier GeoJSON metier via la meme table `Quartier`).
