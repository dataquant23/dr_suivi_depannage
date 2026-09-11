# Proposition wireframe - Digitalisation du rapport de depannage

## 1. Orientation corrigee

L'application ne remplace pas la fiche papier. Elle vient en complement pour faciliter le suivi, les alertes, la consolidation et les statistiques, sans donner au depanneur l'impression qu'on lui ajoute du travail.

Principe produit :

- La fiche papier reste le support terrain principal.
- L'application sert a capter rapidement les informations essentielles.
- La saisie doit prendre moins de 2 minutes pour un cas simple.
- Pas de signature dans l'application.
- Les champs longs sont limites. Tout ce qui est manuscrit sur la fiche papier est saisi dans un seul champ `commentaire`.
- Les equipements peuvent etre coches en multi-selection.
- Les equipements doivent rester classes par structure responsable, sans figer le systeme sur `DRAN` et `DCRD`.
- Aujourd'hui les structures actives sont `DRAN` et `DCRD`, mais demain l'application doit accepter d'autres DR, DC ou structures techniques.ET EN FOCNTION DU USER QUI SE CONNECTE ON SAURA LES INFORMATIOSN DE QUELLES STRUCTURES ON DOIT AVOIR MAIS IL FAUT SURROTUT PAS DES AOPTIONS AUTRES DR OU AUTRE DC 

## 2. Objectifs metier

- Centraliser les rapports de depannage.
- Suivre les indisponibilites et les interventions provisoires.
-(CETTE PARTIE NE CONCERNE PAS LAPPLICATION ) Notifier les acteurs lorsqu'une indisponibilite ou un provisoire est declare.
- Declencher une alerte si une date de remplacement est renseignee dans un cas de compteur shunte.
- Distinguer clairement les travaux relevant de chaque structure responsable.
- Faciliter les relances et le suivi sans ressaisie lourde.
- Produire des statistiques fiables a partir des saisies rapides.

## 3. Roles principaux

- DEPANNAGE : cree rapidement une fiche de suivi a partir de la fiche papier.
- STAFF / supervision : controle, suit les priorites, relance les equipes ou les structures.
- SECTEUR / agence : traite les actions qui lui sont transmises.
- Structure technique : traite les equipements relevant de son perimetre, par exemple DRAN, DCRD.
LES GENS DE LA DCRD NE SONT PAS UTILISATEURS DE LA PLATEFORME SEULE LES DR MAIS ELLES DDOIVENET DISTINGUERLES TRAVAUX QUI LES CONCERNENT OU CELLES AQUELLE DOIT TRANSMETTRE A LA DC QUI LEUR EST ASSINGEE 
- Responsable : consulte les tableaux de bord, retards et performances.

## 4. Navigation proposee

```text
Tableau de bord
Saisie rapide
Indisponibilites
Provisoires
Suivi structures
Carte
Equipements
Equipes
Statistiques
Archives
Parametres
```

## 5. Wireframe - Tableau de bord responsable

```text
+------------------------------------------------------------------------------+
| GESTION DES DEPANNAGES                         Recherche...  Alertes  Profil |
+----------------+-------------------------------------------------------------+
| Tableau bord   | Aujourd'hui                                                 |
| Saisie rapide  |                                                             |
| Indisponib.    | [Nouveaux: 18] [Provisoires: 7] [En retard: 3] [Clotures:24]|
| Provisoires    |                                                             |
| Suivi struct.  | Alertes critiques                                           |
| Carte          | - #DA 24699 | Compteur shunte | remplacement renseigne      |
| Equipements    | - #DA 24700 | Provisoire depasse | DCRD a relancer          |
| Equipes        |                                                             |
| Stats          | Dossiers a suivre                                            |
| Archives       | N DA    Client       Entite   Statut       Action           |
| Parametres     | 24699   Miada M.     DRAN     Provisoire   Ouvrir           |
|                | 24700   Ayeh D.      DCRD     En attente   Relancer         |
+----------------+-------------------------------------------------------------+
```

Idee UX : l'accueil doit montrer ce qui demande une action maintenant : provisoires, retards, dossiers transmis, alertes compteur shunte.


Points importants :

- L'utilisateur peut cocher plusieurs equipements.
- Chaque equipement coche conserve sa structure responsable : `DRAN`, `DCRD`
- Si au moins un equipement d'une structure est coche, le dossier apparait dans la file de cette structure.
- Si plusieurs structures sont concernees, le dossier devient multi-structure.


Cette version mobile doit eviter les longs formulaires en plusieurs etapes. Le depanneur voit tout l'essentiel sur un seul ecran, avec des cases a cocher et peu de texte a saisir.
TOUS LES EQUIPEMENTS DOIVENT ETRE CITE  AVEC LA BASE D EDONNES ON SAURA CA REVIENT A QUELLE STRUCTUTRE
## 8. Regles metier multi-structures

Structure de donnees conseillee pour les equipements coches :

```text
equipements_selectionnes:
  - structure_id: DRAN
    type_structure: DR
    libelle: Compteur
  - structure_id: DRAN
    type_structure: DR
    libelle: Scelle
  - structure_id: DCRD
    type_structure: DC
    libelle: Grille
```

Regles :

- Un dossier peut contenir plusieurs equipements.
- Un dossier peut concerner une seule structure ou plusieurs structures.
- Le tableau de suivi doit permettre de filtrer par structure, par type de structure et par zone.
- Une notification est envoyee a chaque structure concernee.
- La cloture peut etre globale, mais chaque structure doit pouvoir marquer sa partie comme traitee.
- Les structures et leurs listes d'equipements doivent etre parametrees dans l'application, pas codees en dur.

Exemple de referentiel parametre :

```text
structures:
  - id: DRAN
    libelle: Direction Regionale Abidjan Nord
    type: DR
    equipements: [Compteur, CCA/coffret, Tableau, Branchement, Scelle, Tube, Disjoncteur]
  - id: DCRD
    libelle: Direction Centrale Reseau Distribution
    type: DC
    equipements: [TFO, TUR, Liaison TFO TUR, Cahors, Sortie poste, Grille, Borne de lotissement, Potelet, IACM, Raccord brule, Fusion fusibles]
  - id: DRAUTRE
    libelle: Autre Direction Regionale
    type: DR
    equipements: [...]
  - id: DCAUTRE
    libelle: Autre Direction Centrale
    type: DC
    equipements: [...]
```

## 9. Cycle de vie simplifie

```text
Saisi
  -> A traiter
  -> Transmis aux structures concernees
  -> En cours
  -> Provisoire a regulariser si besoin
  -> Traite
  -> Cloture STAFF
  -> Archive
```

Historique automatique :

- date et heure,
- utilisateur,
- action realisee,
- statut avant / apres,
- commentaire si ajoute.

## 10. Alertes utiles

- Compteur shunte + date de remplacement renseignee.
- Situation provisoire non regularisee apres le delai fixe.
- Indisponibilite declaree.
- Dossier multi-structure sans retour d'une des structures concernees.
- Dossier cree sans photo de la fiche papier, si la photo devient obligatoire.
- Plusieurs depannages sur le meme compteur dans une periode courte.

## 11. Fonctionnalites additionnelles proposees

1. Saisie express par modele
   Boutons predefinis : compteur shunte, scelle depose, fusible fondu, raccord brule, grille defectueuse. Le commentaire reste libre.

2. Photo de la fiche papier
   Une photo permet de garder la preuve complete sans recopier tous les details.

3. OCR assiste optionnel
   L'application peut proposer de lire le numero DA, compteur, date ou BTA depuis la photo. L'utilisateur valide seulement ce qui est reconnu.

4. Mode hors ligne
   La fiche rapide peut etre enregistree sans connexion, puis synchronisee plus tard.

5. Files de travail par structure
   Une file par structure active : DRAN, DCRD, autre DR, autre DC, avec une vue multi-structure pour les dossiers partages.

6. Relance automatique
   Si un dossier reste provisoire ou en attente trop longtemps, l'application relance la structure responsable.

7. Statistiques par equipement
   Voir les equipements les plus touches : compteur, grille, TFO, scelle, tube, disjoncteur, etc.

8. Historique compteur
   Lorsqu'un numero compteur revient plusieurs fois, l'application signale les interventions precedentes.

9. Carte des incidents
   Localiser les zones avec beaucoup d'indisponibilites ou de provisoires.

10. Export simple
    Export Excel/PDF pour reunions, suivi hebdomadaire et archivage.

## 12. Champs prioritaires

Obligatoires pour une saisie rapide :

- numero DA,
- date,
- heure,
- agence,
- type de situation : definitif, provisoire ou indisponibilite,
- au moins un equipement coche,
- commentaire manuscrit.

Recommandes mais non bloquants :

- numero compteur,
- numero BTA,
- client / appelant,
- contact,
- zone,
- photo de la fiche papier,
- localisation GPS,
- photo equipement.

Supprimes de la proposition :

- signature client,
- signature chef d'equipe,
- remplacement complet de la fiche papier.

## 13. Priorite MVP

Pour livrer vite et utile :

1. Authentification + roles.
2. Saisie rapide en un seul ecran.
3. Multi-selection des equipements.
4. Distinction claire par structure responsable.
5. Champ `commentaire manuscrit` obligatoire.
6. Photo optionnelle de la fiche papier.
7. Gestion definitif / provisoire / indisponibilite.
8. Notifications aux structures concernees.
9. Alerte compteur shunte + date remplacement.
10. Tableau de suivi par structure et dossiers multi-structures.
11. Archives et export Excel/PDF.
