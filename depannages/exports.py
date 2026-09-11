"""Exports Excel et PDF du récapitulatif de dépannages."""

from pathlib import Path
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Image as RLImage,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.doctemplate import BaseDocTemplate
from reportlab.platypus.frames import Frame

RACINE_PROJET = Path(__file__).resolve().parent.parent
LOGO_CIE = RACINE_PROJET / "static" / "img" / "Logo_CIE.jpg"

NAVY = "0F6F3F"
VERT_FONCE = "064128"
VERT_DOUX = "E6F4EC"
BLEU = "2F6FED"
ORANGE = "EE7D0F"
ORANGE_FONCE = "D66C08"
JAUNE = "F6B300"
VERT = "0F6F3F"
ROUGE = "DC2626"
VIOLET = "7C5CF0"
SLATE = "666F5E"
SLATE_DARK = "1C2536"
TEXTE_LEGER = "98A189"
BORDURE = "E8ECE5"
FOND_PAGE = "F6F7F2"
FOND_CLAIR = "F8F9F5"
FOND_BLEU = "EAF1FF"
FOND_ORANGE = "FDF0DE"
FOND_VERT = "E6F4EC"
FOND_ROUGE = "FDECEC"
FOND_VIOLET = "F1EDFD"
FOND_JAUNE = "FFF7DA"

COULEURS_KPI = [BLEU, VERT, ORANGE, ORANGE, VIOLET, BLEU, ROUGE, JAUNE]
FONDS_KPI = [FOND_BLEU, FOND_VERT, FOND_ORANGE, FOND_ORANGE, FOND_VIOLET, FOND_BLEU, FOND_ROUGE, FOND_JAUNE]

ENTETES = [
    "N BT / BTA",
    "Date de saisie",
    "Nature du dossier",
    "Statut",
    "Secteur",
    "Commune",
    "Quartier",
    "Équipements",
    "Durée",
    "Hors délai",
    "Ouvert par",
    "Clôture par",
]


def _couleur(couleur_hex):
    return colors.HexColor("#" + couleur_hex)


def _paragraphe(valeur):
    return escape(str(valeur))


def _kpi_code(libelle):
    texte = str(libelle).lower()
    if "hors" in texte or "retard" in texte:
        return "!"
    if "délai" in texte or "delai" in texte:
        return "H"
    if "shunt" in texte:
        return "CS"
    if "définit" in texte or "definit" in texte:
        return "DF"
    if "provisoire" in texte or "à clôturer" in texte or "a cloturer" in texte:
        return "AC"
    if "clôtur" in texte or "clotur" in texte or "trait" in texte:
        return "OK"
    return "BT"


def _logo_pdf(largeur=23 * mm, hauteur=13 * mm):
    if not LOGO_CIE.exists():
        return ""
    return RLImage(str(LOGO_CIE), width=largeur, height=hauteur)


def _ajouter_logo_excel(feuille, cellule="B1"):
    if not LOGO_CIE.exists():
        return
    logo = XLImage(str(LOGO_CIE))
    logo.width = 82
    logo.height = 34
    feuille.add_image(logo, cellule)


class _GrilleKpiPdf(Flowable):
    def __init__(self, resume, styles, colonnes=4, largeur=265 * mm):
        super().__init__()
        self.kpis = _aplatir_resume(resume)
        self.styles = styles
        self.colonnes = colonnes
        self.largeur = largeur
        self.hauteur_carte = 30 * mm
        self.gouttiere = 5 * mm

    def wrap(self, largeur_disponible, hauteur_disponible):
        self.largeur = min(self.largeur, largeur_disponible)
        lignes = (len(self.kpis) + self.colonnes - 1) // self.colonnes
        self.width = self.largeur
        self.height = lignes * self.hauteur_carte + max(lignes - 1, 0) * self.gouttiere
        return self.width, self.height

    def draw(self):
        if not self.kpis:
            return
        canevas = self.canv
        largeur_carte = (
            self.width - (self.colonnes - 1) * self.gouttiere
        ) / self.colonnes
        valeur_style = ParagraphStyle(
            "KpiFlowValue",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=20,
            textColor=_couleur(VERT_FONCE),
        )
        libelle_style = ParagraphStyle(
            "KpiFlowLabel",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.8,
            leading=9,
            textColor=_couleur(SLATE),
        )

        for index, (libelle, valeur) in enumerate(self.kpis):
            colonne = index % self.colonnes
            ligne = index // self.colonnes
            x = colonne * (largeur_carte + self.gouttiere)
            y = self.height - (ligne + 1) * self.hauteur_carte - ligne * self.gouttiere
            accent = COULEURS_KPI[index % len(COULEURS_KPI)]
            fond = FONDS_KPI[index % len(FONDS_KPI)]

            canevas.saveState()
            canevas.setFillColor(colors.white)
            canevas.setStrokeColor(_couleur(BORDURE))
            canevas.setLineWidth(0.6)
            canevas.roundRect(x, y, largeur_carte, self.hauteur_carte, 7, stroke=1, fill=1)
            canevas.setFillColor(_couleur(accent))
            canevas.roundRect(x, y, 3.4 * mm, self.hauteur_carte, 7, stroke=0, fill=1)
            canevas.setFillColor(_couleur(fond))
            canevas.circle(x + 12 * mm, y + self.hauteur_carte - 10.5 * mm, 6.2 * mm, stroke=0, fill=1)
            canevas.setFillColor(_couleur(accent))
            canevas.setFont("Helvetica-Bold", 6.8)
            canevas.drawCentredString(
                x + 12 * mm,
                y + self.hauteur_carte - 12 * mm,
                _kpi_code(libelle),
            )
            canevas.restoreState()

            largeur_texte = largeur_carte - 24 * mm
            valeur_para = Paragraph(_paragraphe(valeur), valeur_style)
            libelle_para = Paragraph(_paragraphe(libelle), libelle_style)
            valeur_para.wrapOn(canevas, largeur_texte, 10 * mm)
            libelle_para.wrapOn(canevas, largeur_texte, 11 * mm)
            valeur_para.drawOn(canevas, x + 23 * mm, y + 13 * mm)
            libelle_para.drawOn(canevas, x + 23 * mm, y + 5 * mm)


def _entete_rapport_pdf(titre, sous_titre, genere_le, styles, largeur_disponible=265 * mm):
    titre_style = ParagraphStyle(
        "RapportTitreApp",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=23,
        textColor=_couleur(VERT_FONCE),
        spaceAfter=2,
    )
    sous_titre_style = ParagraphStyle(
        "RapportSousTitreApp",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=11,
        textColor=_couleur(SLATE),
    )
    meta_style = ParagraphStyle(
        "RapportMetaApp",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9,
        textColor=_couleur(TEXTE_LEGER),
        alignment=2,
    )
    bloc_titre = [
        Paragraph(_paragraphe(titre), titre_style),
        Paragraph(_paragraphe(sous_titre), sous_titre_style),
    ]
    donnees = [[
        _logo_pdf(),
        bloc_titre,
        Paragraph(f"Rapport<br/>généré le {genere_le:%d/%m/%Y à %H:%M}", meta_style),
    ]]
    tableau = Table(donnees, colWidths=[31 * mm, largeur_disponible - 74 * mm, 43 * mm])
    tableau.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.6, _couleur(BORDURE)),
            ("LINEBEFORE", (0, 0), (0, -1), 4, _couleur(NAVY)),
            ("LINEAFTER", (0, 0), (0, -1), 1.5, _couleur(ORANGE)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ])
    )
    return tableau


def _bordure_excel(couleur=BORDURE, style="thin"):
    cote = Side(style=style, color=couleur)
    return Border(left=cote, right=cote, top=cote, bottom=cote)


def _bordure_bas_excel(couleur=ORANGE, style="medium"):
    return Border(bottom=Side(style=style, color=couleur))


def _cellules(feuille, ligne_debut, ligne_fin, colonne_debut, colonne_fin):
    for ligne in feuille.iter_rows(
        min_row=ligne_debut,
        max_row=ligne_fin,
        min_col=colonne_debut,
        max_col=colonne_fin,
    ):
        for cellule in ligne:
            yield cellule


def _aplatir_resume(resume):
    return [(libelle, valeur) for _, valeurs in resume for libelle, valeur in valeurs]


def _periode_libelle(debut, fin):
    return f"Du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}"


def _suffixe_nom_fichier(debut, fin):
    """Suffixe compact pour les noms de fichiers téléchargés : période en
    AAMMJJ (plus court que AAAAMMJJ) et heure de génération (HHMM), pour que
    deux exports de la même période ne s'écrasent pas dans le dossier de
    téléchargements."""
    heure = timezone.localtime().strftime("%Hh%M")
    return f"{debut:%y%m%d}-{fin:%y%m%d}_{heure}"


def _styliser_bandeau_excel(feuille, titre, sous_titre, dernier_col=8):
    feuille.sheet_view.showGridLines = False
    dernier_col = max(dernier_col, 3)
    for ligne in range(1, 5):
        for cellule in _cellules(feuille, ligne, ligne, 1, dernier_col):
            cellule.fill = PatternFill("solid", fgColor="FFFFFF")
            cellule.border = _bordure_excel(BORDURE)

    feuille.merge_cells(start_row=1, start_column=1, end_row=3, end_column=1)
    feuille["A1"].fill = PatternFill("solid", fgColor=NAVY)
    feuille["A1"].border = Border(
        bottom=Side(style="medium", color=ORANGE),
        left=Side(style="thin", color=NAVY),
        right=Side(style="thin", color=NAVY),
        top=Side(style="thin", color=NAVY),
    )

    _ajouter_logo_excel(feuille, "B1")
    feuille.column_dimensions["A"].width = 2.5
    feuille.column_dimensions["B"].width = 14

    feuille.merge_cells(start_row=1, start_column=3, end_row=1, end_column=dernier_col)
    feuille.merge_cells(start_row=2, start_column=3, end_row=2, end_column=dernier_col)
    feuille.merge_cells(start_row=3, start_column=3, end_row=3, end_column=dernier_col)
    feuille.cell(row=1, column=3, value=titre)
    feuille.cell(row=2, column=3, value=sous_titre)
    feuille.cell(row=3, column=3, value=f"Généré le {timezone.localtime():%d/%m/%Y à %H:%M}")
    feuille.cell(row=1, column=3).font = Font(bold=True, size=18, color=VERT_FONCE)
    feuille.cell(row=2, column=3).font = Font(size=10.5, color=SLATE)
    feuille.cell(row=3, column=3).font = Font(size=9, color=TEXTE_LEGER)
    for ligne in (1, 2, 3):
        feuille.cell(row=ligne, column=3).alignment = Alignment(
            horizontal="left", vertical="center"
        )

    for cellule in _cellules(feuille, 4, 4, 1, dernier_col):
        cellule.fill = PatternFill("solid", fgColor=FOND_CLAIR)
        cellule.border = _bordure_bas_excel(ORANGE, "medium")

    feuille.row_dimensions[1].height = 24
    feuille.row_dimensions[2].height = 20
    feuille.row_dimensions[3].height = 18
    feuille.row_dimensions[4].height = 6


def _ecrire_section_excel(feuille, ligne, titre, dernier_col=8, couleur=ORANGE):
    feuille.merge_cells(start_row=ligne, start_column=1, end_row=ligne, end_column=dernier_col)
    cellule = feuille.cell(row=ligne, column=1, value=titre)
    cellule.font = Font(bold=True, size=12, color=VERT_FONCE)
    cellule.fill = PatternFill("solid", fgColor="FFFFFF")
    cellule.alignment = Alignment(horizontal="left", vertical="center")
    for c in _cellules(feuille, ligne, ligne, 1, dernier_col):
        c.border = Border(bottom=Side(style="thin", color=BORDURE))
    feuille.cell(row=ligne, column=1).border = Border(
        left=Side(style="medium", color=couleur),
        bottom=Side(style="thin", color=BORDURE),
    )
    feuille.row_dimensions[ligne].height = 24


def _ecrire_infos_generales_excel(feuille, debut, fin, document, ligne=5, dernier_col=8):
    _ecrire_section_excel(feuille, ligne, "Informations générales", dernier_col, NAVY)
    infos = [
        ("Période", _periode_libelle(debut, fin), "Application", "Gestion des dépannages"),
        ("Document", document, "Généré le", f"{timezone.localtime():%d/%m/%Y à %H:%M}"),
    ]
    etiquette = Font(bold=True, size=9, color=SLATE)
    valeur = Font(bold=True, size=10, color=SLATE_DARK)
    for offset, ligne_infos in enumerate(infos, start=1):
        r = ligne + offset
        feuille.cell(row=r, column=1, value=ligne_infos[0])
        feuille.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        feuille.cell(row=r, column=2, value=ligne_infos[1])
        feuille.cell(row=r, column=5, value=ligne_infos[2])
        feuille.merge_cells(start_row=r, start_column=6, end_row=r, end_column=dernier_col)
        feuille.cell(row=r, column=6, value=ligne_infos[3])
        for cellule in _cellules(feuille, r, r, 1, dernier_col):
            cellule.fill = PatternFill("solid", fgColor=FOND_CLAIR)
            cellule.border = _bordure_excel()
            cellule.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        for colonne in (1, 5):
            feuille.cell(row=r, column=colonne).fill = PatternFill("solid", fgColor=VERT_DOUX)
        feuille.cell(row=r, column=1).font = etiquette
        feuille.cell(row=r, column=5).font = etiquette
        feuille.cell(row=r, column=2).font = valeur
        feuille.cell(row=r, column=6).font = valeur
        feuille.row_dimensions[r].height = 24


def _ecrire_kpis_excel(feuille, resume, ligne=10, cartes_par_ligne=4):
    kpis = _aplatir_resume(resume)
    if not kpis:
        return ligne

    _ecrire_section_excel(feuille, ligne - 1, "Indicateurs clés", 8, ORANGE)
    for index, (libelle, valeur) in enumerate(kpis):
        bloc_ligne = ligne + (index // cartes_par_ligne) * 4
        colonne = 1 + (index % cartes_par_ligne) * 2
        accent = COULEURS_KPI[index % len(COULEURS_KPI)]
        fond = FONDS_KPI[index % len(FONDS_KPI)]

        for cellule in _cellules(feuille, bloc_ligne, bloc_ligne + 2, colonne, colonne + 1):
            cellule.fill = PatternFill("solid", fgColor="FFFFFF")
            cellule.border = _bordure_excel()
            cellule.alignment = Alignment(vertical="center", wrap_text=True)

        for r in range(bloc_ligne, bloc_ligne + 3):
            feuille.cell(row=r, column=colonne).fill = PatternFill("solid", fgColor=fond)
            feuille.cell(row=r, column=colonne).alignment = Alignment(
                horizontal="center", vertical="center"
            )
        feuille.cell(row=bloc_ligne + 1, column=colonne, value=_kpi_code(libelle))
        feuille.cell(row=bloc_ligne + 1, column=colonne).font = Font(
            bold=True, size=11, color=accent
        )

        feuille.cell(row=bloc_ligne, column=colonne + 1, value=str(libelle))
        feuille.cell(row=bloc_ligne + 1, column=colonne + 1, value=str(valeur))
        feuille.cell(row=bloc_ligne, column=colonne + 1).font = Font(
            bold=True, size=9, color=SLATE
        )
        feuille.cell(row=bloc_ligne + 1, column=colonne + 1).font = Font(
            bold=True, size=20, color=VERT_FONCE
        )
        feuille.cell(row=bloc_ligne + 2, column=colonne + 1).fill = PatternFill(
            "solid", fgColor=FOND_CLAIR
        )
        feuille.cell(row=bloc_ligne + 2, column=colonne + 1).border = Border(
            top=Side(style="medium", color=accent),
            left=Side(style="thin", color=BORDURE),
            right=Side(style="thin", color=BORDURE),
            bottom=Side(style="thin", color=BORDURE),
        )

        feuille.row_dimensions[bloc_ligne].height = 24
        feuille.row_dimensions[bloc_ligne + 1].height = 28
        feuille.row_dimensions[bloc_ligne + 2].height = 7

    derniere_ligne = ligne + ((len(kpis) - 1) // cartes_par_ligne) * 4 + 2
    return derniere_ligne + 2


def _styliser_feuille_dossiers(feuille, largeurs, ligne_entete=1):
    feuille.sheet_view.showGridLines = False
    gras_blanc = Font(bold=True, color="FFFFFF")
    bordure = _bordure_excel()
    fond_entete = PatternFill("solid", fgColor=NAVY)
    centre = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for cellule in feuille[ligne_entete]:
        cellule.font = gras_blanc
        cellule.fill = fond_entete
        cellule.alignment = centre
        cellule.border = bordure

    for r in range(ligne_entete + 1, feuille.max_row + 1):
        fond_ligne = PatternFill("solid", fgColor=FOND_CLAIR if r % 2 == 0 else "FFFFFF")
        for cellule in feuille[r]:
            cellule.fill = fond_ligne
            cellule.border = bordure
            cellule.alignment = Alignment(vertical="top", wrap_text=True)
        feuille.cell(row=r, column=2).alignment = Alignment(horizontal="center", vertical="top")
        feuille.cell(row=r, column=4).alignment = Alignment(horizontal="center", vertical="top")
        feuille.cell(row=r, column=9).alignment = Alignment(horizontal="center", vertical="top")
        feuille.cell(row=r, column=10).alignment = Alignment(horizontal="center", vertical="top")
        if feuille.cell(row=r, column=10).value == "Oui":
            cellule_retard = feuille.cell(row=r, column=10)
            cellule_retard.fill = PatternFill("solid", fgColor=FOND_ROUGE)
            cellule_retard.font = Font(bold=True, color=ROUGE)

    for indice, largeur in enumerate(largeurs, start=1):
        feuille.column_dimensions[get_column_letter(indice)].width = largeur
    feuille.row_dimensions[ligne_entete].height = 28
    feuille.freeze_panes = f"A{ligne_entete + 1}"
    feuille.auto_filter.ref = (
        f"A{ligne_entete}:{get_column_letter(len(largeurs))}{max(feuille.max_row, ligne_entete)}"
    )
    feuille.page_setup.orientation = "landscape"
    feuille.page_setup.fitToWidth = 1
    feuille.page_setup.fitToHeight = 0


def _lignes(depannages):
    for depannage in depannages:
        duree = depannage.heures_ecoulees
        hors_delai = (
            depannage.delai_applique_heures
            and duree is not None
            and duree > depannage.delai_applique_heures
        )
        clotureurs = ", ".join(
            str(c.cloture_par) for c in depannage.clotures.all()
        )
        yield [
            depannage.numero_bt,
            depannage.date_saisie.strftime("%d/%m/%Y %H:%M"),
            depannage.get_categorie_provisoire_display() or "-",
            depannage.get_statut_display(),
            depannage.secteur.libelle if depannage.secteur_id else "-",
            depannage.commune.nom if depannage.commune_id else "-",
            depannage.quartier.nom if depannage.quartier_id else "-",
            ", ".join(
                f"{e.structure.code}/{e.libelle}" for e in depannage.equipements.all()
            ),
            _valeur_delai_jh(duree),
            "Oui" if hors_delai else "Non",
            str(depannage.cree_par),
            clotureurs or "-",
        ]


def exporter_excel(depannages, resume, debut, fin):
    """Classeur à deux feuilles : synthèse et détail des dossiers."""
    classeur = Workbook()

    # --- Feuille de synthèse ---
    synthese = classeur.active
    synthese.title = "Synthèse"
    synthese.sheet_properties.tabColor = ORANGE
    _styliser_bandeau_excel(
        synthese,
        "Bilan des dépannages",
        _periode_libelle(debut, fin),
        dernier_col=8,
    )
    _ecrire_infos_generales_excel(
        synthese, debut, fin, "Classeur Excel complet", ligne=5, dernier_col=8
    )
    _ecrire_kpis_excel(synthese, resume, ligne=10)
    for indice, largeur in enumerate([6.5, 24, 6.5, 24, 6.5, 24, 6.5, 24], start=1):
        synthese.column_dimensions[get_column_letter(indice)].width = largeur

    # --- Feuille de détail ---
    detail = classeur.create_sheet("Dossiers")
    detail.sheet_properties.tabColor = BLEU
    detail.append(ENTETES)

    for valeurs in _lignes(depannages):
        detail.append(valeurs)

    largeurs = [14, 18, 22, 16, 16, 16, 16, 36, 9, 10, 18, 18]
    _styliser_feuille_dossiers(detail, largeurs)

    reponse = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    reponse["Content-Disposition"] = (
        f'attachment; filename="depannages_{_suffixe_nom_fichier(debut, fin)}.xlsx"'
    )
    classeur.save(reponse)
    return reponse


def exporter_detail_dossiers_excel(depannages, debut, fin):
    """Classeur à une seule feuille : le détail des dossiers, sans la
    colonne Type (le bilan PDF ne détaille plus les dossiers un par un ;
    ce fichier est le téléchargement dédié pour ce niveau de détail)."""
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Dossiers"
    feuille.sheet_properties.tabColor = BLEU
    dernier_col = len(ENTETES)

    _styliser_bandeau_excel(
        feuille,
        "Détail des dossiers",
        _periode_libelle(debut, fin),
        dernier_col=dernier_col,
    )

    ligne_entete = 5
    for colonne, valeur in enumerate(ENTETES, start=1):
        feuille.cell(row=ligne_entete, column=colonne, value=valeur)

    ligne = ligne_entete + 1
    for valeurs in _lignes(depannages):
        for colonne, valeur in enumerate(valeurs, start=1):
            feuille.cell(row=ligne, column=colonne, value=valeur)
        ligne += 1

    largeurs = [14, 18, 22, 16, 16, 16, 16, 36, 9, 10, 18, 18]
    _styliser_feuille_dossiers(feuille, largeurs, ligne_entete=ligne_entete)

    reponse = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    reponse["Content-Disposition"] = (
        f'attachment; filename="liste_depannages_{_suffixe_nom_fichier(debut, fin)}.xlsx"'
    )
    classeur.save(reponse)
    return reponse


def _tableau_infos_generales_pdf(
    debut, fin, genere_le, styles, document="Bilan PDF", largeur_disponible=265 * mm
):
    libelle = ParagraphStyle(
        "InfoLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.2,
        leading=9,
        textColor=_couleur(SLATE),
    )
    valeur = ParagraphStyle(
        "InfoValue",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11,
        textColor=_couleur(SLATE_DARK),
    )
    donnees = [
        [
            Paragraph("Période", libelle),
            Paragraph(_paragraphe(_periode_libelle(debut, fin)), valeur),
            Paragraph("Document", libelle),
            Paragraph(_paragraphe(document), valeur),
        ],
        [
            Paragraph("Application", libelle),
            Paragraph("Gestion des dépannages", valeur),
            Paragraph("Généré le", libelle),
            Paragraph(_paragraphe(f"{genere_le:%d/%m/%Y à %H:%M}"), valeur),
        ],
    ]
    largeur_etiquette = 28 * mm
    largeur_valeur = (largeur_disponible - 2 * largeur_etiquette) / 2
    tableau = Table(
        donnees,
        colWidths=[largeur_etiquette, largeur_valeur, largeur_etiquette, largeur_valeur],
        hAlign="LEFT",
    )
    tableau.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BACKGROUND", (0, 0), (0, -1), _couleur(VERT_DOUX)),
            ("BACKGROUND", (2, 0), (2, -1), _couleur(VERT_DOUX)),
            ("BOX", (0, 0), (-1, -1), 0.6, _couleur(BORDURE)),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, _couleur(BORDURE)),
            ("LINEBEFORE", (0, 0), (0, -1), 2, _couleur(ORANGE)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ])
    )
    return tableau


def _tableau_kpis_pdf(resume, styles, largeur_disponible=265 * mm, cartes_par_ligne=4):
    return _GrilleKpiPdf(
        resume,
        styles,
        colonnes=cartes_par_ligne,
        largeur=largeur_disponible,
    )


def exporter_pdf(
    resume, debut, fin, repartitions,
    secteurs_matrice=None, lignes_equipement=None,
):
    """Bilan PDF paysage : page de garde, chiffres clés, tableau croisé
    secteurs x équipements et répartitions (secteur/commune/quartier/
    équipement) ; pagination (numéro de page) sur toutes les pages sauf la
    couverture. Le détail dossier par dossier n'est plus dans ce bilan : il
    se télécharge séparément en Excel (voir exporter_detail_dossiers_excel)."""
    reponse = HttpResponse(content_type="application/pdf")
    reponse["Content-Disposition"] = (
        f'attachment; filename="bilan_depannages_{_suffixe_nom_fichier(debut, fin)}.pdf"'
    )

    largeur_page, hauteur_page = landscape(A4)
    marge = 14 * mm

    document = BaseDocTemplate(
        reponse,
        pagesize=landscape(A4),
        leftMargin=marge, rightMargin=marge, topMargin=marge, bottomMargin=marge,
        title="Bilan des dépannages",
    )
    cadre = Frame(
        marge, marge, largeur_page - 2 * marge, hauteur_page - 2 * marge,
        id="cadre",
    )
    document.addPageTemplates([
        PageTemplate(id="couverture", frames=[cadre], onPage=_dessiner_couverture),
        PageTemplate(id="contenu", frames=[cadre], onPage=_dessiner_pied_page),
    ])

    styles = getSampleStyleSheet()
    genere_le = timezone.localtime()
    section_couverture = ParagraphStyle(
        "SectionCouverture",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=_couleur(VERT_FONCE),
        spaceBefore=8,
        spaceAfter=6,
    )
    section = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        spaceBefore=12,
        spaceAfter=6,
        textColor=_couleur(VERT_FONCE),
    )

    # --- Page de garde : infos générales + KPI visibles dès la première page.
    elements = [
        NextPageTemplate("contenu"),
        _entete_rapport_pdf(
            "Bilan des dépannages",
            "Récapitulatif des dossiers, délais et répartitions",
            genere_le,
            styles,
        ),
        Spacer(1, 7 * mm),
        Paragraph("Informations générales", section_couverture),
        _tableau_infos_generales_pdf(debut, fin, genere_le, styles),
        Spacer(1, 7 * mm),
        Paragraph("Indicateurs clés", section_couverture),
        _tableau_kpis_pdf(resume, styles),
    ]

    contenu = []

    # --- Tableau croisé secteurs x équipements (Créés / Taux / Délai) -------
    if secteurs_matrice and lignes_equipement:
        contenu.append(Paragraph("Récapitulatif par secteur et équipement", section))
        contenu.append(_tableau_croise_secteur_equipement(secteurs_matrice, lignes_equipement))

    # --- Répartitions (secteur, commune, quartier, équipement) --------------
    for nom_bloc, donnees in repartitions:
        if not donnees:
            continue
        contenu.append(Paragraph(nom_bloc, section))
        corps = [["Libellé", "Dossiers"]] + [[str(a), str(b)] for a, b in donnees]
        tableau = Table(corps, colWidths=[120 * mm, 30 * mm], repeatRows=1)
        tableau.setStyle(_style_tableau())
        contenu.append(tableau)

    if contenu:
        elements.append(PageBreak())
        elements.extend(contenu)

    document.build(elements)
    return reponse


def _dessiner_couverture(canevas, document):
    """Fond de page de garde, sans pagination."""
    largeur_page, hauteur_page = landscape(A4)
    canevas.saveState()
    canevas.setFillColor(_couleur(FOND_PAGE))
    canevas.rect(0, 0, largeur_page, hauteur_page, stroke=0, fill=1)

    canevas.setStrokeColor(_couleur("E2E9DF"))
    canevas.setLineWidth(0.45)
    canevas.setDash(2, 5)
    for decalage in range(-40, 330, 34):
        canevas.line(decalage * mm, 8 * mm, (decalage + 64) * mm, hauteur_page - 8 * mm)
    canevas.setDash()

    canevas.setFillColor(_couleur(VERT))
    canevas.roundRect(9 * mm, hauteur_page - 34 * mm, 3.2 * mm, 22 * mm, 1.6 * mm, stroke=0, fill=1)
    canevas.setFillColor(_couleur(ORANGE))
    canevas.roundRect(9 * mm, hauteur_page - 43 * mm, 3.2 * mm, 8 * mm, 1.6 * mm, stroke=0, fill=1)

    canevas.setFillColor(_couleur(VERT_DOUX))
    for x, y in [(242, 35), (262, 63), (224, 95), (271, 128)]:
        canevas.circle(x * mm, y * mm, 2.2 * mm, stroke=0, fill=1)
    canevas.setStrokeColor(_couleur(ORANGE))
    canevas.setLineWidth(0.6)
    canevas.line(242 * mm, 35 * mm, 262 * mm, 63 * mm)
    canevas.line(262 * mm, 63 * mm, 224 * mm, 95 * mm)
    canevas.line(224 * mm, 95 * mm, 271 * mm, 128 * mm)
    canevas.restoreState()


def _dessiner_pied_page(canevas, document):
    """Pied de page commun aux pages de contenu (pas la couverture) :
    numéro de page (hors couverture), nom de l application, date de
    génération."""
    largeur_page, hauteur_page = landscape(A4)
    numero_page = canevas.getPageNumber() - 1  # la couverture ne compte pas
    canevas.saveState()
    canevas.setFillColor(_couleur(FOND_PAGE))
    canevas.rect(0, 0, largeur_page, hauteur_page, stroke=0, fill=1)
    canevas.setFillColor(_couleur(NAVY))
    canevas.rect(0, 0, largeur_page, 5 * mm, stroke=0, fill=1)
    canevas.setFillColor(_couleur(ORANGE))
    canevas.rect(0, 4.7 * mm, largeur_page, 0.8 * mm, stroke=0, fill=1)
    canevas.setFont("Helvetica", 8)
    canevas.setFillColor(colors.white)
    canevas.drawCentredString(largeur_page / 2, 1.5 * mm, f"Page {numero_page}")
    canevas.drawString(14 * mm, 1.5 * mm, "Gestion des dépannages - CIE")
    canevas.drawRightString(
        largeur_page - 14 * mm, 1.5 * mm, f"{timezone.localtime():%d/%m/%Y}"
    )
    canevas.restoreState()


def _dessiner_page_resume(canevas, document):
    """Fond + pied de page du résumé portrait."""
    largeur_page, hauteur_page = A4
    canevas.saveState()
    canevas.setFillColor(_couleur(FOND_PAGE))
    canevas.rect(0, 0, largeur_page, hauteur_page, stroke=0, fill=1)
    canevas.setFillColor(_couleur(NAVY))
    canevas.rect(0, 0, largeur_page, 5 * mm, stroke=0, fill=1)
    canevas.setFillColor(_couleur(ORANGE))
    canevas.rect(0, 4.7 * mm, largeur_page, 0.8 * mm, stroke=0, fill=1)
    canevas.setFont("Helvetica", 8)
    canevas.setFillColor(colors.white)
    canevas.drawString(14 * mm, 1.5 * mm, "Gestion des dépannages - CIE")
    canevas.drawRightString(largeur_page - 14 * mm, 1.5 * mm, f"Page {canevas.getPageNumber()}")
    canevas.restoreState()


def _tableau_croise_secteur_equipement(secteurs, lignes_equipement):
    """Tableau croisé équipement x secteur, 3 sous-lignes par équipement
    (Créés / Taux Traitement / Délai), tel que demandé par la
    direction : mêmes colonnes/lignes que le tableau de bord habituel."""
    entete = ["Équipement", ""] + [s.libelle for s in secteurs]
    corps = [entete]
    fusions = []
    ligne = 1
    for item in lignes_equipement:
        libelle_equip = item["libelle"].split(" · ", 1)[-1]
        corps.append([
            libelle_equip, "Créés",
            *[str(c["crees"]) for c in item["par_secteur"]],
        ])
        corps.append([
            "", "Taux Traitement",
            *[_valeur_pct(c["taux"]) for c in item["par_secteur"]],
        ])
        corps.append([
            "", "Délai",
            *[_valeur_delai_jh(c["delai_h"]) for c in item["par_secteur"]],
        ])
        fusions.append(("SPAN", (0, ligne), (0, ligne + 2)))
        fusions.append(("LINEABOVE", (0, ligne), (-1, ligne), 0.6, _couleur("CBD5E1")))
        ligne += 3

    largeur_libelle = 32 * mm
    largeur_indicateur = 26 * mm
    largeur_dispo = 265 * mm - largeur_libelle - largeur_indicateur
    largeur_secteur = largeur_dispo / max(len(secteurs), 1)
    colonnes = [largeur_libelle, largeur_indicateur] + [largeur_secteur] * len(secteurs)

    tableau = Table(corps, colWidths=colonnes, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _couleur(NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, _couleur(ORANGE)),
        ("FONTSIZE", (0, 0), (-1, -1), 7.3),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, _couleur(BORDURE)),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 1), (0, -1), "MIDDLE"),
    ]
    style.extend(fusions)
    # Une bande grise tres claire sur la sous-ligne "Créés" de chaque groupe
    # d equipement, pour scander visuellement les groupes de 3 lignes.
    for i in range(1, len(corps), 3):
        style.append(("BACKGROUND", (1, i), (-1, i), _couleur(FOND_CLAIR)))
    tableau.setStyle(TableStyle(style))
    return tableau


def exporter_resume_structures(cartes_secteur, lignes_equipement, debut, fin):
    """Résumé PDF compact (1-2 pages) pour la direction, séparé par structure
    (DRAN puis DCRD) : dossiers créés, traités, taux et délai moyen par
    équipement. Réutilise les données déjà calculées par
    _matrice_secteur_equipement (lignes_equipement, dont le libellé est
    préfixé par le code de structure, ex. "DRAN · Compteur")."""
    reponse = HttpResponse(content_type="application/pdf")
    reponse["Content-Disposition"] = (
        f'attachment; filename="resume_dr_dc_{_suffixe_nom_fichier(debut, fin)}.pdf"'
    )

    document = SimpleDocTemplate(
        reponse,
        pagesize=A4,
        leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title="Résumé DR / DC",
    )

    styles = getSampleStyleSheet()
    genere_le = timezone.localtime()
    section = ParagraphStyle(
        "SectionResume", parent=styles["Heading2"], fontSize=12.5,
        textColor=_couleur(VERT_FONCE), spaceBefore=12, spaceAfter=6,
    )
    synthese_globale = next(
        (
            bloc["provisoires"]
            for bloc in cartes_secteur
            if getattr(bloc["secteur"], "pk", None) is None
        ),
        cartes_secteur[0]["provisoires"] if cartes_secteur else None,
    )
    resume_global = []
    if synthese_globale:
        resume_global = [
            ("Indicateurs clés", [
                ("Dossiers créés", synthese_globale["crees"]),
                ("Dossiers traités", synthese_globale["traites"]),
                ("Taux de traitement", _valeur_pct(synthese_globale["taux"])),
                ("Délai moyen", _valeur_delai_jh(synthese_globale["delai_h"])),
            ]),
        ]

    elements = [
        _entete_rapport_pdf(
            "Résumé par structure - DR et DC",
            "Synthèse des dossiers créés, traités, taux et délais moyens",
            genere_le,
            styles,
            largeur_disponible=182 * mm,
        ),
        Spacer(1, 5 * mm),
        Paragraph("Informations générales", section),
        _tableau_infos_generales_pdf(
            debut,
            fin,
            genere_le,
            styles,
            document="Résumé DR/DC",
            largeur_disponible=182 * mm,
        ),
        Paragraph("Indicateurs clés", section),
        _tableau_kpis_pdf(
            resume_global,
            styles,
            largeur_disponible=182 * mm,
            cartes_par_ligne=2,
        ),
        Spacer(1, 4 * mm),
    ]

    # Chiffres globaux par secteur (dossiers provisoires, tous équipements).
    entetes_secteur = [["Secteur", "Créés", "Traités", "Taux", "Délai moyen"]]
    corps_secteur = [
        [
            bloc["secteur"].libelle,
            bloc["provisoires"]["crees"],
            bloc["provisoires"]["traites"],
            _valeur_pct(bloc["provisoires"]["taux"]),
            _valeur_delai_jh(bloc["provisoires"]["delai_h"]),
        ]
        for bloc in cartes_secteur
    ]
    if corps_secteur:
        elements.append(Paragraph("Synthèse par secteur (DRAN)", section))
        tableau = Table(
            entetes_secteur + corps_secteur,
            colWidths=[60 * mm, 25 * mm, 25 * mm, 25 * mm, 40 * mm],
            repeatRows=1,
        )
        tableau.setStyle(_style_tableau())
        elements.append(tableau)

    # Détail par équipement, regroupé par structure (le libellé est déjà
    # préfixé "CODE · Équipement" par _matrice_secteur_equipement).
    groupes = {}
    for ligne in lignes_equipement:
        code_structure, _, libelle_equip = ligne["libelle"].partition(" · ")
        crees = sum(cellule["crees"] for cellule in ligne["par_secteur"])
        traites = sum(cellule["traites"] for cellule in ligne["par_secteur"])
        taux = round(traites / crees * 100, 1) if crees else None
        groupes.setdefault(code_structure, []).append((libelle_equip, crees, traites, taux))

    for code_structure in sorted(groupes, key=lambda c: c != "DRAN"):
        elements.append(Paragraph(f"Détail équipements — {code_structure}", section))
        corps = [["Équipement", "Créés", "Traités", "Taux"]] + [
            [libelle, crees, traites, _valeur_pct(taux)]
            for libelle, crees, traites, taux in groupes[code_structure]
        ]
        tableau = Table(corps, colWidths=[80 * mm, 25 * mm, 25 * mm, 25 * mm], repeatRows=1)
        tableau.setStyle(_style_tableau())
        elements.append(tableau)

    document.build(elements, onFirstPage=_dessiner_page_resume, onLaterPages=_dessiner_page_resume)
    return reponse


def _style_tableau():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _couleur(NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, _couleur(ORANGE)),
        ("GRID", (0, 0), (-1, -1), 0.35, _couleur(BORDURE)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _couleur(FOND_CLAIR)]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ])


def _valeur_pct(valeur):
    return f"{valeur:.1f}%".replace(".", ",") if valeur is not None else "-"


def _valeur_nombre(valeur):
    return str(valeur) if valeur is not None else "-"


def _valeur_delai_jh(heures):
    """Formate une duree en heures en 'j h' (ex. '2 j 3 h'), comme le
    filtre de gabarit jours_heures : les fichiers telecharges doivent
    afficher les delais dans la meme unite que le reste de l appli plutot
    qu en jours decimaux (ex. "2,2") ou en heures brutes seules."""
    if heures is None:
        return "-"
    total = round(heures)
    jours, reste = divmod(total, 24)
    if jours <= 0:
        return f"{reste} h"
    return f"{jours} j {reste} h"


def exporter_matrice_secteur_equipement(secteurs, lignes_equipement, ligne_provisoires, debut, fin):
    """Tableau croisé secteurs x équipements : créés, taux de traitement,
    délai moyen (en jours). Une feuille, en largeur, un groupe de lignes par
    équipement puis la synthèse "Provisoires" tous équipements confondus.
    """
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Secteurs x Équipements"
    feuille.sheet_properties.tabColor = ORANGE

    gras_blanc = Font(bold=True, color="FFFFFF")
    gras = Font(bold=True, color=SLATE_DARK)
    fond_entete = PatternFill("solid", fgColor=NAVY)
    fond_groupe = PatternFill("solid", fgColor=FOND_BLEU)
    fond_total = PatternFill("solid", fgColor=FOND_ORANGE)
    bordure = _bordure_excel()
    centre = Alignment(horizontal="center", vertical="center", wrap_text=True)
    dernier_col = max(3, 2 + len(secteurs))

    _styliser_bandeau_excel(
        feuille,
        "Traitement par secteur et équipement",
        _periode_libelle(debut, fin),
        dernier_col=dernier_col,
    )

    ligne_entete = 4
    feuille.cell(row=ligne_entete, column=1, value="Équipement").font = gras_blanc
    feuille.cell(row=ligne_entete, column=2, value="Indicateur").font = gras_blanc
    for colonne, secteur in enumerate(secteurs, start=3):
        cellule = feuille.cell(row=ligne_entete, column=colonne, value=secteur.libelle)
        cellule.font = gras_blanc
        cellule.alignment = centre
    for cellule in feuille[ligne_entete]:
        cellule.fill = fond_entete
        cellule.border = bordure
        cellule.alignment = centre
    feuille.row_dimensions[ligne_entete].height = 28

    ligne = ligne_entete + 1

    def _bloc(nom, lignes_valeurs, indicateurs):
        nonlocal ligne
        premiere = ligne
        fond_bloc = fond_total if nom == "Provisoires" else fond_groupe
        for indicateur, extracteur, formateur in indicateurs:
            cellule_indicateur = feuille.cell(row=ligne, column=2, value=indicateur)
            cellule_indicateur.font = Font(bold=True, color=SLATE_DARK)
            cellule_indicateur.alignment = Alignment(vertical="center", wrap_text=True)
            for colonne, valeurs in enumerate(lignes_valeurs, start=3):
                cellule = feuille.cell(row=ligne, column=colonne, value=formateur(extracteur(valeurs)))
                cellule.alignment = centre
                cellule.border = bordure
            ligne += 1
        feuille.cell(row=premiere, column=1, value=nom).font = gras
        feuille.merge_cells(start_row=premiere, start_column=1, end_row=ligne - 1, end_column=1)
        feuille.cell(row=premiere, column=1).alignment = Alignment(vertical="center", wrap_text=True)
        for r in range(premiere, ligne):
            fond_ligne = PatternFill("solid", fgColor=FOND_CLAIR if r % 2 == 0 else "FFFFFF")
            feuille.row_dimensions[r].height = 22
            for c in range(1, dernier_col + 1):
                cellule = feuille.cell(row=r, column=c)
                cellule.border = bordure
                cellule.alignment = Alignment(vertical="center", wrap_text=True)
                cellule.fill = fond_bloc if c in (1, 2) else fond_ligne

    indicateurs_equipement = [
        ("Créés", lambda v: v["crees"], _valeur_nombre),
        ("Taux de traitement", lambda v: v["taux"], _valeur_pct),
        ("Délai", lambda v: v["delai_h"], _valeur_delai_jh),
    ]
    for ligne_equip in lignes_equipement:
        _bloc(ligne_equip["libelle"], ligne_equip["par_secteur"], indicateurs_equipement)

    indicateurs_provisoires = [
        ("Créés", lambda v: v["crees"], _valeur_nombre),
        ("Traités", lambda v: v["traites"], _valeur_nombre),
        ("Taux de traitement", lambda v: v["taux"], _valeur_pct),
        ("Délai", lambda v: v["delai_h"], _valeur_delai_jh),
    ]
    _bloc("Provisoires", ligne_provisoires, indicateurs_provisoires)

    feuille.column_dimensions["A"].width = 16
    feuille.column_dimensions["B"].width = 20
    for indice in range(3, dernier_col + 1):
        feuille.column_dimensions[get_column_letter(indice)].width = 14
    feuille.freeze_panes = feuille.cell(row=ligne_entete + 1, column=3).coordinate
    feuille.auto_filter.ref = f"A{ligne_entete}:{get_column_letter(dernier_col)}{max(ligne - 1, ligne_entete)}"
    feuille.sheet_view.showGridLines = False
    feuille.page_setup.orientation = "landscape"
    feuille.page_setup.fitToWidth = 1
    feuille.page_setup.fitToHeight = 0

    reponse = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    reponse["Content-Disposition"] = (
        f'attachment; filename="secteurs_equipements_{_suffixe_nom_fichier(debut, fin)}.xlsx"'
    )
    classeur.save(reponse)
    return reponse
