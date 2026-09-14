"""Exports Excel et PDF du récapitulatif de dépannages."""

from functools import partial
from pathlib import Path
from xml.sax.saxutils import escape

from django.http import HttpResponse
from django.utils import timezone

from core.validators import neutralise_formule

from .models import Statut
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table as ExcelTable, TableStyleInfo
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
ILLUSTRATION_COUVERTURE = RACINE_PROJET / "static" / "img" / "pylones.png"

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

ENTETES = [
    "Nº BTA",
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


def _kpi_theme(libelle):
    texte = str(libelle).lower()
    if "hors" in texte or "retard" in texte:
        return ROUGE, FOND_ROUGE
    if "provisoire" in texte or "cloturer" in texte or "clôturer" in texte or "shunt" in texte:
        return ORANGE, FOND_ORANGE
    return VERT, FOND_VERT


def _logo_pdf(largeur=23 * mm, hauteur=13 * mm):
    if not LOGO_CIE.exists():
        return ""
    return RLImage(str(LOGO_CIE), width=largeur, height=hauteur)


def _rect_alpha(canevas, couleur, x, y, largeur, hauteur, alpha=1, rayon=0, stroke=0):
    canevas.saveState()
    if hasattr(canevas, "setFillAlpha"):
        canevas.setFillAlpha(alpha)
    canevas.setFillColor(_couleur(couleur))
    if rayon:
        canevas.roundRect(x, y, largeur, hauteur, rayon, stroke=stroke, fill=1)
    else:
        canevas.rect(x, y, largeur, hauteur, stroke=stroke, fill=1)
    canevas.restoreState()


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
        self.width = self.largeur
        self.height = 48 * mm if len(self.kpis) > 1 else 34 * mm
        return self.width, self.height

    def draw(self):
        if not self.kpis:
            return
        canevas = self.canv
        principal = self.kpis[0]
        secondaires = self.kpis[1:]
        largeur_principale = 78 * mm
        espace = 6 * mm
        largeur_secondaire = self.width - largeur_principale - espace

        canevas.saveState()
        canevas.setFillColor(_couleur(VERT_FONCE))
        canevas.setStrokeColor(_couleur(VERT_FONCE))
        canevas.roundRect(0, 0, largeur_principale, self.height, 6, stroke=0, fill=1)
        canevas.setFillColor(_couleur(ORANGE))
        canevas.rect(0, 0, 4 * mm, self.height, stroke=0, fill=1)
        canevas.setFont("Helvetica-Bold", 8)
        canevas.setFillColor(_couleur(VERT_DOUX))
        canevas.drawString(9 * mm, self.height - 12 * mm, "VOLUME À PILOTER")
        canevas.setFont("Helvetica-Bold", 30)
        canevas.setFillColor(colors.white)
        canevas.drawString(9 * mm, self.height - 30 * mm, str(principal[1]))
        canevas.setFont("Helvetica-Bold", 10)
        canevas.drawString(9 * mm, self.height - 39 * mm, str(principal[0])[:30])
        canevas.setFont("Helvetica", 7)
        canevas.setFillColor(_couleur(VERT_DOUX))
        canevas.drawString(9 * mm, 9 * mm, "Synthèse opérationnelle CIE")
        canevas.restoreState()

        if not secondaires:
            return

        colonnes = 3 if len(secondaires) > 3 else len(secondaires)
        lignes = (len(secondaires) + colonnes - 1) // colonnes
        largeur_carte = (largeur_secondaire - (colonnes - 1) * 4 * mm) / colonnes
        hauteur_carte = (self.height - (lignes - 1) * 4 * mm) / lignes
        for index, (libelle, valeur) in enumerate(secondaires):
            colonne = index % colonnes
            ligne = index // colonnes
            x = largeur_principale + espace + colonne * (largeur_carte + 4 * mm)
            y = self.height - (ligne + 1) * hauteur_carte - ligne * 4 * mm
            accent, fond = _kpi_theme(libelle)
            canevas.saveState()
            canevas.setFillColor(colors.white)
            canevas.setStrokeColor(_couleur(BORDURE))
            canevas.setLineWidth(0.55)
            canevas.roundRect(x, y, largeur_carte, hauteur_carte, 5, stroke=1, fill=1)
            canevas.setFillColor(_couleur(fond))
            canevas.rect(x, y, largeur_carte, 4 * mm, stroke=0, fill=1)
            canevas.setFillColor(_couleur(accent))
            canevas.setFont("Helvetica-Bold", 7)
            canevas.drawString(x + 5 * mm, y + hauteur_carte - 8 * mm, _kpi_code(libelle))
            canevas.setFont("Helvetica-Bold", 18)
            canevas.setFillColor(_couleur(VERT_FONCE))
            canevas.drawRightString(x + largeur_carte - 5 * mm, y + hauteur_carte - 9 * mm, str(valeur))
            canevas.setFont("Helvetica-Bold", 7.5)
            canevas.setFillColor(_couleur(SLATE))
            canevas.drawString(x + 5 * mm, y + 8 * mm, str(libelle)[:28])
            canevas.restoreState()


class _BarresHorizontalesPdf(Flowable):
    def __init__(self, titre, donnees, styles, largeur=126 * mm, limite=8):
        super().__init__()
        self.titre = titre
        self.donnees = [(str(libelle), valeur or 0) for libelle, valeur in donnees[:limite]]
        self.styles = styles
        self.largeur = largeur
        self.hauteur_titre = 12 * mm
        self.hauteur_ligne = 9 * mm
        self.marge_interne = 6 * mm

    def wrap(self, largeur_disponible, hauteur_disponible):
        self.width = min(self.largeur, largeur_disponible)
        self.height = self.hauteur_titre + max(len(self.donnees), 1) * self.hauteur_ligne + 8 * mm
        return self.width, self.height

    def draw(self):
        canevas = self.canv
        canevas.saveState()
        canevas.setFillColor(colors.white)
        canevas.setStrokeColor(_couleur(BORDURE))
        canevas.setLineWidth(0.5)
        canevas.roundRect(0, 0, self.width, self.height, 5, stroke=1, fill=1)
        _rect_alpha(canevas, VERT_DOUX, 0, self.height - self.hauteur_titre, self.width, self.hauteur_titre, 0.92)
        canevas.setFillColor(_couleur(ORANGE))
        canevas.rect(0, self.height - self.hauteur_titre, 1.8 * mm, self.hauteur_titre, stroke=0, fill=1)
        canevas.setFillColor(_couleur(VERT_FONCE))
        canevas.setFont("Helvetica-Bold", 8.2)
        canevas.drawString(5 * mm, self.height - 8 * mm, self.titre[:46])

        if not self.donnees:
            canevas.setFont("Helvetica", 8)
            canevas.setFillColor(_couleur(SLATE))
            canevas.drawString(5 * mm, self.height - self.hauteur_titre - 8 * mm, "Aucune donnée")
            canevas.restoreState()
            return

        maximum = max([valeur for _, valeur in self.donnees] + [1])
        label_width = self.width * 0.42
        value_width = 13 * mm
        bar_x = label_width + self.marge_interne
        bar_width = self.width - bar_x - value_width - self.marge_interne
        y = self.height - self.hauteur_titre - 8 * mm

        for index, (libelle, valeur) in enumerate(self.donnees):
            ligne_y = y - index * self.hauteur_ligne
            canevas.setFont("Helvetica", 6.8)
            canevas.setFillColor(_couleur(SLATE_DARK))
            canevas.drawString(5 * mm, ligne_y, libelle[:32])
            canevas.setFillColor(_couleur(FOND_CLAIR))
            canevas.roundRect(bar_x, ligne_y - 1.2 * mm, bar_width, 2.8 * mm, 1.4 * mm, stroke=0, fill=1)
            canevas.setFillColor(_couleur(VERT_FONCE))
            largeur_valeur = bar_width * (valeur / maximum)
            canevas.roundRect(
                bar_x,
                ligne_y - 1.2 * mm,
                max(largeur_valeur, 0.8 * mm),
                2.8 * mm,
                1.4 * mm,
                stroke=0,
                fill=1,
            )
            canevas.setFont("Helvetica-Bold", 6.8)
            canevas.setFillColor(_couleur(VERT_FONCE))
            canevas.drawRightString(self.width - 5 * mm, ligne_y, str(valeur))
        canevas.restoreState()


def _bloc_graphique_pdf(titre, donnees, styles, largeur=126 * mm, limite=8):
    return _BarresHorizontalesPdf(titre, donnees, styles, largeur=largeur, limite=limite)


def _periode_courte_pdf(debut, fin):
    mois = [
        "",
        "JANVIER",
        "FEVRIER",
        "MARS",
        "AVRIL",
        "MAI",
        "JUIN",
        "JUILLET",
        "AOUT",
        "SEPTEMBRE",
        "OCTOBRE",
        "NOVEMBRE",
        "DECEMBRE",
    ]
    return f"{debut:%d} -> {fin:%d} {mois[fin.month]} {fin:%Y}"


def _tableau_top_pdf(titre, colonnes, donnees, largeurs):
    corps = [[Paragraph(titre, ParagraphStyle(
        "TopTitre",
        parent=getSampleStyleSheet()["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=9,
        textColor=_couleur(VERT_FONCE),
    ))]]
    tableau_titre = Table(corps, colWidths=[sum(largeurs)])
    tableau_titre.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _couleur(VERT_DOUX)),
        ("BOX", (0, 0), (-1, -1), 0.4, _couleur(BORDURE)),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    lignes = [colonnes] + donnees
    tableau = Table(lignes, colWidths=largeurs, repeatRows=1)
    tableau.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _couleur(FOND_CLAIR)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, 0), _couleur(SLATE_DARK)),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("GRID", (0, 0), (-1, -1), 0.25, _couleur(BORDURE)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _couleur(FOND_CLAIR)]),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [tableau_titre, tableau]


def _carte_indicateurs_pdf(resume, largeur=58 * mm):
    lignes = [
        ["Autres indicateurs", ""],
        ["Interventions", _texte_kpi(resume, "depannage") or _texte_kpi(resume, "dossier") or "-"],
        ["Délai moyen", _texte_kpi(resume, "delai") or "-"],
        ["Clôtures hors délai", _texte_kpi(resume, "hors") or "-"],
    ]
    tableau = Table(lignes, colWidths=[35 * mm, largeur - 35 * mm])
    tableau.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), _couleur(VERT_DOUX)),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, 0), _couleur(VERT_FONCE)),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.4, _couleur(BORDURE)),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, _couleur(BORDURE)),
        ("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 1), (1, -2), _couleur(VERT)),
        ("TEXTCOLOR", (1, -1), (1, -1), _couleur(ROUGE)),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTSIZE", (1, 1), (1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return tableau


class _EnteteOperationnellePdf(Flowable):
    def __init__(self, titre, sous_titre, debut, fin, genere_le, largeur=182 * mm):
        super().__init__()
        self.titre = titre
        self.sous_titre = sous_titre
        self.debut = debut
        self.fin = fin
        self.genere_le = genere_le
        self.largeur = largeur
        self.height = 28 * mm

    def wrap(self, largeur_disponible, hauteur_disponible):
        self.width = min(self.largeur, largeur_disponible)
        return self.width, self.height

    def draw(self):
        canevas = self.canv
        canevas.saveState()
        canevas.setFillColor(_couleur(VERT_FONCE))
        canevas.setFont("Helvetica-Bold", 19)
        canevas.drawString(0, 15 * mm, self.titre)
        canevas.setFillColor(_couleur(ORANGE))
        canevas.rect(0, 9.3 * mm, 13 * mm, 0.8 * mm, stroke=0, fill=1)
        canevas.setFillColor(_couleur(SLATE_DARK))
        canevas.setFont("Helvetica", 10)
        canevas.drawString(0, 4.8 * mm, self.sous_titre)
        canevas.restoreState()


class _CartesImpactPdf(Flowable):
    def __init__(self, resume, largeur=182 * mm):
        super().__init__()
        self.kpis = _aplatir_resume(resume)
        self.largeur = largeur
        self.height = 53 * mm

    def wrap(self, largeur_disponible, hauteur_disponible):
        self.width = min(self.largeur, largeur_disponible)
        return self.width, self.height

    def draw(self):
        if not self.kpis:
            return
        canevas = self.canv
        colonnes = 4
        gouttiere = 4 * mm
        largeur_carte = (self.width - (colonnes - 1) * gouttiere) / colonnes
        hauteur_carte = 22 * mm
        for index, (libelle, valeur) in enumerate(self.kpis[:8]):
            colonne = index % colonnes
            ligne = index // colonnes
            x = colonne * (largeur_carte + gouttiere)
            y = self.height - (ligne + 1) * hauteur_carte - ligne * 5 * mm
            accent, fond = _kpi_theme(libelle)
            canevas.saveState()
            canevas.setFillColor(colors.white)
            canevas.setStrokeColor(_couleur(BORDURE))
            canevas.setLineWidth(0.45)
            canevas.roundRect(x, y, largeur_carte, hauteur_carte, 5, stroke=1, fill=1)
            canevas.setFillColor(_couleur(accent))
            canevas.roundRect(x, y, 2.1 * mm, hauteur_carte, 2, stroke=0, fill=1)
            _rect_alpha(canevas, fond, x + 2.1 * mm, y, largeur_carte - 2.1 * mm, hauteur_carte, 0.72, rayon=5)
            canevas.setFillColor(colors.white)
            canevas.circle(x + largeur_carte - 10 * mm, y + hauteur_carte - 9 * mm, 6 * mm, stroke=0, fill=1)
            canevas.setFillColor(_couleur(accent))
            canevas.setFont("Helvetica-Bold", 8)
            canevas.drawCentredString(x + largeur_carte - 10 * mm, y + hauteur_carte - 11 * mm, _kpi_code(libelle))
            canevas.setFont("Helvetica-Bold", 22)
            canevas.drawString(x + 6 * mm, y + 9.5 * mm, str(valeur))
            canevas.setFont("Helvetica-Bold", 7.1)
            canevas.drawString(x + 6 * mm, y + 5 * mm, str(libelle).upper()[:23])
            canevas.setFillColor(_couleur(accent))
            canevas.rect(x + 6 * mm, y + 2.5 * mm, 10 * mm, 0.55 * mm, stroke=0, fill=1)
            canevas.restoreState()


class _DonutTraitementPdf(Flowable):
    def __init__(self, resume, largeur=58 * mm):
        super().__init__()
        self.resume = resume
        self.largeur = largeur
        self.height = 78 * mm

    def wrap(self, largeur_disponible, hauteur_disponible):
        self.width = min(self.largeur, largeur_disponible)
        return self.width, self.height

    def draw(self):
        a_cloturer = _entier_kpi(self.resume, "cloturer")
        clotures = _entier_kpi(self.resume, "clotures") or _entier_kpi(self.resume, "traites")
        hors_delai = _entier_kpi(self.resume, "hors")
        total = max(a_cloturer + clotures + hors_delai, 1)
        valeurs = [
            ("À clôturer", a_cloturer, ORANGE),
            ("Clôtures", clotures, VERT),
            ("Hors délai", hors_delai, ROUGE),
        ]
        canevas = self.canv
        canevas.saveState()
        canevas.setFillColor(colors.white)
        canevas.setStrokeColor(_couleur(BORDURE))
        canevas.setLineWidth(0.5)
        canevas.roundRect(0, 0, self.width, self.height, 5, stroke=1, fill=1)
        _rect_alpha(canevas, VERT_DOUX, 0, self.height - 11 * mm, self.width, 11 * mm, 0.92)
        canevas.setFillColor(_couleur(ORANGE))
        canevas.rect(0, self.height - 11 * mm, 1.8 * mm, 11 * mm, stroke=0, fill=1)
        canevas.setFillColor(_couleur(VERT_FONCE))
        canevas.setFont("Helvetica-Bold", 8)
        canevas.drawString(5 * mm, self.height - 7 * mm, "État du traitement")

        taille = 38 * mm if self.width >= 80 * mm else 30 * mm
        x1 = (self.width - taille) / 2
        y1 = 27 * mm
        angle = 90
        for _, valeur, couleur in valeurs:
            if not valeur:
                continue
            etendue = 360 * valeur / total
            canevas.setFillColor(_couleur(couleur))
            # Trait blanc fin entre les segments : lisibilite d'un anneau
            # plutot que l'effet camembert plein d'un simple wedge.
            canevas.setStrokeColor(colors.white)
            canevas.setLineWidth(1.2)
            canevas.wedge(x1, y1, x1 + taille, y1 + taille, angle, -etendue, stroke=1, fill=1)
            angle -= etendue
        canevas.setFillColor(colors.white)
        canevas.circle(x1 + taille / 2, y1 + taille / 2, taille * 0.39, stroke=0, fill=1)
        canevas.setFillColor(_couleur(VERT_FONCE))
        canevas.setFont("Helvetica-Bold", 15 if self.width >= 80 * mm else 12)
        canevas.drawCentredString(x1 + taille / 2, y1 + taille / 2 + 1.5 * mm, str(total))
        canevas.setFont("Helvetica", 6.8)
        canevas.setFillColor(_couleur(SLATE))
        canevas.drawCentredString(x1 + taille / 2, y1 + taille / 2 - 4 * mm, "dossiers")

        y = 18 * mm
        x_legende = max(8 * mm, (self.width - 58 * mm) / 2)
        for libelle, valeur, couleur in valeurs:
            canevas.setFillColor(_couleur(couleur))
            canevas.rect(x_legende, y - 1.8 * mm, 3 * mm, 3 * mm, stroke=0, fill=1)
            canevas.setFillColor(_couleur(SLATE_DARK))
            canevas.setFont("Helvetica", 7)
            canevas.drawString(x_legende + 6.5 * mm, y - 1.8 * mm, libelle)
            canevas.setFont("Helvetica-Bold", 7)
            canevas.drawRightString(min(self.width - 8 * mm, x_legende + 58 * mm), y - 1.8 * mm, str(valeur))
            y -= 7 * mm
        canevas.restoreState()


def _texte_kpi(resume, *mots):
    mots = [mot.lower() for mot in mots]
    for libelle, valeur in _aplatir_resume(resume):
        texte = str(libelle).lower()
        texte = texte.replace("é", "e").replace("è", "e").replace("ê", "e").replace("ô", "o").replace("û", "u").replace("à", "a")
        if all(mot in texte for mot in mots):
            return str(valeur)
    return None


def _entier_kpi(resume, *mots):
    valeur = _texte_kpi(resume, *mots)
    if valeur is None:
        return 0
    chiffres = "".join(car for car in str(valeur) if car.isdigit())
    return int(chiffres) if chiffres else 0


def _trouver_repartition(repartitions, mot_cle):
    mot_cle = mot_cle.lower()
    for nom_bloc, donnees in repartitions:
        if mot_cle in str(nom_bloc).lower():
            return donnees
    return []


def _entete_rapport_pdf(titre, sous_titre, genere_le, styles, largeur_disponible=265 * mm):
    titre_style = ParagraphStyle(
        "RapportTitreApp",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=24,
        textColor=colors.white,
        spaceAfter=2,
    )
    sous_titre_style = ParagraphStyle(
        "RapportSousTitreApp",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        textColor=_couleur(VERT_DOUX),
    )
    meta_style = ParagraphStyle(
        "RapportMetaApp",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.2,
        leading=8.5,
        textColor=colors.white,
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
            ("BACKGROUND", (0, 0), (-1, -1), _couleur(VERT_FONCE)),
            ("BACKGROUND", (0, 0), (0, -1), colors.white),
            ("BACKGROUND", (2, 0), (2, -1), _couleur(ORANGE)),
            ("LINEBELOW", (0, 0), (-1, -1), 2.2, _couleur(ORANGE)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
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


def _ecrire_kpis_excel(feuille, resume, ligne=10, cartes_par_ligne=4, dernier_col=8, titre="Indicateurs clés"):
    kpis = _aplatir_resume(resume)
    if not kpis:
        return ligne

    if titre:
        _ecrire_section_excel(feuille, ligne - 1, titre, dernier_col, ORANGE)
    for index, (libelle, valeur) in enumerate(kpis):
        bloc_ligne = ligne + (index // cartes_par_ligne) * 4
        colonne = 1 + (index % cartes_par_ligne) * 2
        accent, fond = _kpi_theme(libelle)

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

    # Couleur (accent, fond) par libellé de statut affiché
    # (Agent.get_statut_display) : match exact, remplace l'ancien
    # sous-marquage par sous-chaine qui laissait "En cours" sans couleur.
    badges_statut = {
        "Saisi": (SLATE, FOND_CLAIR),
        "En cours": (ORANGE_FONCE, FOND_ORANGE),
        "Clôturé": (VERT_FONCE, FOND_VERT),
        "Clôturé (définitif)": (VERT_FONCE, FOND_VERT),
        "Archivé": (TEXTE_LEGER, FOND_CLAIR),
    }
    colonne_statut = ENTETES.index("Statut") + 1 if "Statut" in ENTETES else None
    colonne_hors_delai = ENTETES.index("Hors délai") + 1 if "Hors délai" in ENTETES else None
    centre = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for r in range(ligne_entete + 1, feuille.max_row + 1):
        fond_ligne = PatternFill("solid", fgColor=FOND_CLAIR if r % 2 == 0 else "FFFFFF")
        for cellule in feuille[r]:
            cellule.fill = fond_ligne
            cellule.border = bordure
            cellule.alignment = Alignment(vertical="top", wrap_text=True)

        if colonne_statut:
            cellule_statut = feuille.cell(row=r, column=colonne_statut)
            accent, fond = badges_statut.get(str(cellule_statut.value), (SLATE, FOND_CLAIR))
            cellule_statut.font = Font(bold=True, size=9, color=accent)
            cellule_statut.fill = PatternFill("solid", fgColor=fond)
            cellule_statut.alignment = centre

        if colonne_hors_delai:
            cellule_retard = feuille.cell(row=r, column=colonne_hors_delai)
            if cellule_retard.value == "Hors délai":
                cellule_retard.font = Font(bold=True, size=9, color=ROUGE)
                cellule_retard.fill = PatternFill("solid", fgColor=FOND_ROUGE)
            else:
                cellule_retard.font = Font(color=TEXTE_LEGER)
            cellule_retard.alignment = centre

    for indice, largeur in enumerate(largeurs, start=1):
        feuille.column_dimensions[get_column_letter(indice)].width = largeur
    feuille.row_dimensions[ligne_entete].height = 28
    feuille.freeze_panes = f"B{ligne_entete + 1}"
    reference = f"A{ligne_entete}:{get_column_letter(len(largeurs))}{max(feuille.max_row, ligne_entete)}"
    feuille.auto_filter.ref = reference
    _ajouter_table_excel(feuille, reference, "TableDossiers")
    feuille.page_setup.orientation = "landscape"
    feuille.page_setup.fitToWidth = 1
    feuille.page_setup.fitToHeight = 0
    feuille.print_title_rows = f"{ligne_entete}:{ligne_entete}"


def _ajouter_table_excel(feuille, reference, nom):
    if feuille.max_row <= 1:
        return
    nom_table = nom
    compteur = 1
    while nom_table in feuille.tables:
        compteur += 1
        nom_table = f"{nom}{compteur}"
    table = ExcelTable(displayName=nom_table, ref=reference)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium4",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    feuille.add_table(table)


def _cellule_sure(valeur):
    if isinstance(valeur, str) and len(valeur) > 1:
        return neutralise_formule(valeur)
    return valeur


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
            _cellule_sure(valeur)
            for valeur in (
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
                "Hors délai" if hors_delai else "—",
                str(depannage.cree_par),
                clotureurs or "-",
            )
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


def _entete_liste_dossiers_excel(feuille, sous_titre, debut, fin, dernier_col):
    """En-tête sobre : logo sur fond blanc (pas de bandeau colore), titre de
    l'application, sous-titre du document, et la periode dans un encart a
    droite. Pas de bandeau d'indicateurs sous ce titre pour cet export."""
    feuille.sheet_view.showGridLines = False
    _ajouter_logo_excel(feuille, "A1")
    feuille.column_dimensions["A"].width = 16
    feuille.row_dimensions[1].height = 24
    feuille.row_dimensions[2].height = 18
    feuille.row_dimensions[3].height = 8

    colonne_titre_fin = max(dernier_col - 3, 2)
    feuille.merge_cells(start_row=1, start_column=2, end_row=1, end_column=colonne_titre_fin)
    feuille.merge_cells(start_row=2, start_column=2, end_row=2, end_column=colonne_titre_fin)
    feuille.cell(row=1, column=2, value="GESTION DES DÉPANNAGES")
    feuille.cell(row=1, column=2).font = Font(bold=True, size=15, color=VERT_FONCE)
    feuille.cell(row=2, column=2, value=sous_titre)
    feuille.cell(row=2, column=2).font = Font(size=11, color=SLATE)
    for r in (1, 2):
        feuille.cell(row=r, column=2).alignment = Alignment(horizontal="left", vertical="center")

    colonne_periode_debut = colonne_titre_fin + 1
    feuille.merge_cells(
        start_row=1, start_column=colonne_periode_debut, end_row=2, end_column=dernier_col
    )
    cellule_periode = feuille.cell(
        row=1,
        column=colonne_periode_debut,
        value=f"Période : {debut:%d/%m/%Y} → {fin:%d/%m/%Y}",
    )
    cellule_periode.font = Font(bold=True, size=10, color=SLATE_DARK)
    cellule_periode.alignment = Alignment(horizontal="center", vertical="center")
    for cellule in _cellules(feuille, 1, 2, colonne_periode_debut, dernier_col):
        cellule.fill = PatternFill("solid", fgColor=FOND_CLAIR)
        cellule.border = _bordure_excel()

    for cellule in _cellules(feuille, 3, 3, 1, dernier_col):
        cellule.border = Border(bottom=Side(style="thin", color=BORDURE))

    return 4


def exporter_detail_dossiers_excel(depannages, debut, fin):
    """Classeur à une seule feuille : le détail des dossiers, sans la
    colonne Type (le bilan PDF ne détaille plus les dossiers un par un ;
    ce fichier est le téléchargement dédié pour ce niveau de détail).

    Badges colorés Statut/Hors délai : même définition de « clôturé » que le
    tableau de bord et le bilan (`statut`, pas `cloture_en_attente`) pour
    rester cohérent entre les trois écrans.
    """
    classeur = Workbook()
    feuille = classeur.active
    feuille.title = "Dossiers"
    feuille.sheet_properties.tabColor = BLEU
    dernier_col = len(ENTETES)

    ligne_entete = _entete_liste_dossiers_excel(
        feuille, "Liste des dépannages", debut, fin, dernier_col
    )

    depannages = list(depannages)

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
    """Bilan PDF operationnel : page de garde puis trois pages (synthese,
    analyse, matrice)."""
    reponse = HttpResponse(content_type="application/pdf")
    reponse["Content-Disposition"] = (
        f'attachment; filename="bilan_depannages_{_suffixe_nom_fichier(debut, fin)}.pdf"'
    )

    largeur_page, hauteur_page = A4
    marge = 12 * mm
    marge_bas = 20 * mm
    largeur_contenu = largeur_page - 2 * marge

    document = BaseDocTemplate(
        reponse,
        pagesize=A4,
        leftMargin=marge, rightMargin=marge, topMargin=marge, bottomMargin=marge_bas,
        title="Bilan des dépannages",
    )
    cadre = Frame(
        marge, marge_bas, largeur_page - 2 * marge, hauteur_page - marge - marge_bas,
        id="cadre",
    )
    # Cadre pleine page pour la couverture : le contenu y est entierement
    # dessine par `onPage`, ce cadre ne sert qu'a satisfaire BaseDocTemplate
    # (une page a besoin d'au moins un frame).
    cadre_couverture = Frame(0, 0, largeur_page, hauteur_page, id="cadre_couverture")

    genere_le = timezone.localtime()

    document.addPageTemplates([
        PageTemplate(
            id="couverture",
            frames=[cadre_couverture],
            onPage=partial(
                _dessiner_couverture_rapport,
                debut=debut,
                fin=fin,
                genere_le=genere_le,
                resume=resume,
            ),
        ),
        PageTemplate(id="rapport", frames=[cadre], onPage=_dessiner_pied_page_rapport),
    ])

    secteur_data = _trouver_repartition(repartitions, "secteur")
    equipement_data = _trouver_repartition(repartitions, "quipement")
    elements = [
        NextPageTemplate("rapport"),
        PageBreak(),
        _EnteteOperationnellePdf(
            "Analyse des dépannages",
            "Répartitions et principaux indicateurs",
            debut,
            fin,
            genere_le,
            largeur=largeur_contenu,
        ),
        Spacer(1, 5 * mm),
        Table(
            [[
                _bloc_graphique_pdf("1. Répartition par secteur", secteur_data, getSampleStyleSheet(), largeur=88 * mm, limite=8),
                _bloc_graphique_pdf("2. Équipements les plus concernés", equipement_data, getSampleStyleSheet(), largeur=88 * mm, limite=8),
            ]],
            colWidths=[91 * mm, 91 * mm],
            hAlign="LEFT",
            style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]),
        ),
        Spacer(1, 9 * mm),
        Table(
            [[_DonutTraitementPdf(resume, largeur=92 * mm)]],
            colWidths=[largeur_contenu],
            hAlign="LEFT",
            style=TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]),
        ),
    ]
    elements.extend([
        PageBreak(),
        _EnteteOperationnellePdf(
            "Matrice équipements × secteurs",
            "Nombre de dossiers · Taux de traitement · Délai moyen",
            debut,
            fin,
            genere_le,
            largeur=largeur_contenu,
        ),
        Spacer(1, 5 * mm),
    ])

    if secteurs_matrice and lignes_equipement:
        elements.append(
            _tableau_croise_secteur_equipement(
                secteurs_matrice,
                lignes_equipement,
                largeur_disponible=largeur_contenu,
            )
        )
    else:
        styles = getSampleStyleSheet()
        vide = Paragraph(
            "Aucune donnée de matrice disponible pour la période sélectionnée.",
            ParagraphStyle(
                "MatriceVide",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=9,
                leading=12,
                textColor=_couleur(SLATE_DARK),
            ),
        )
        tableau_vide = Table([[vide]], colWidths=[largeur_contenu], rowHeights=[28 * mm])
        tableau_vide.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.45, _couleur(BORDURE)),
            ("LINEBEFORE", (0, 0), (0, -1), 2, _couleur(ORANGE)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ]))
        elements.append(tableau_vide)

    document.build(elements)
    return reponse


def _dessiner_kpi_couverture(canevas, x, y, largeur, hauteur, valeur, libelle, accent, code):
    canevas.saveState()
    canevas.setFillColor(colors.white)
    canevas.setStrokeColor(_couleur(BORDURE))
    canevas.setLineWidth(0.45)
    canevas.roundRect(x, y, largeur, hauteur, 5, stroke=1, fill=1)
    _rect_alpha(canevas, FOND_CLAIR, x, y, largeur, hauteur, 0.65, rayon=5)
    canevas.setFillColor(_couleur(accent))
    canevas.roundRect(x, y, 1.7 * mm, hauteur, 1.5, stroke=0, fill=1)
    _rect_alpha(canevas, accent, x + largeur - 16 * mm, y + hauteur - 16 * mm, 11 * mm, 11 * mm, 0.09, rayon=6)
    canevas.setFillColor(_couleur(accent))
    canevas.setFont("Helvetica-Bold", 26)
    canevas.drawString(x + 6 * mm, y + 11 * mm, str(valeur))
    canevas.setFont("Helvetica-Bold", 8)
    canevas.drawString(x + 6 * mm, y + 5 * mm, str(libelle).upper())
    canevas.setFont("Helvetica-Bold", 8.5)
    canevas.drawCentredString(x + largeur - 10.5 * mm, y + hauteur - 11.5 * mm, code)
    canevas.setFillColor(_couleur(accent))
    canevas.rect(x + 6 * mm, y + 2.2 * mm, 10 * mm, 0.55 * mm, stroke=0, fill=1)
    canevas.restoreState()


def _dessiner_couverture_rapport(canevas, document, debut, fin, genere_le, resume):
    """Couverture executive : visuel pleine largeur, titre fort et KPIs."""
    largeur_page, hauteur_page = A4
    marge = 10 * mm
    canevas.saveState()
    canevas.setFillColor(_couleur(FOND_CLAIR))
    canevas.rect(0, 0, largeur_page, hauteur_page, stroke=0, fill=1)

    if ILLUSTRATION_COUVERTURE.exists():
        largeur_image = largeur_page
        hauteur_image = largeur_image * 1086 / 1448
        canevas.drawImage(
            str(ILLUSTRATION_COUVERTURE),
            0,
            87 * mm,
            width=largeur_image,
            height=hauteur_image,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )
        _rect_alpha(canevas, "FFFFFF", 0, 226 * mm, largeur_page, 72 * mm, 0.86)

    if LOGO_CIE.exists():
        logo = RLImage(str(LOGO_CIE), width=31 * mm, height=17 * mm)
        logo.wrapOn(canevas, 31 * mm, 17 * mm)
        logo.drawOn(canevas, marge, hauteur_page - 29 * mm)
    canevas.setFillColor(_couleur(VERT_FONCE))
    canevas.setFont("Helvetica-Bold", 11)
    canevas.drawString(46 * mm, hauteur_page - 16 * mm, "COMPAGNIE IVOIRIENNE")
    canevas.drawString(46 * mm, hauteur_page - 21 * mm, "D'ÉLECTRICITÉ")
    x_meta = 130 * mm
    canevas.setStrokeColor(_couleur(SLATE))
    canevas.setLineWidth(0.7)
    canevas.line(x_meta - 8 * mm, hauteur_page - 31 * mm, x_meta - 8 * mm, hauteur_page - 7 * mm)
    canevas.setFont("Helvetica", 8.5)
    canevas.setFillColor(_couleur(SLATE_DARK))
    canevas.drawString(x_meta, hauteur_page - 13 * mm, f"Rapport généré le {genere_le:%d/%m/%Y à %H:%M}")
    canevas.drawString(x_meta, hauteur_page - 20 * mm, f"Période : du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}")

    canevas.setFillColor(_couleur(VERT_FONCE))
    canevas.setFont("Helvetica-Bold", 39)
    canevas.drawString(marge, 212 * mm, "Bilan des")
    canevas.setFillColor(_couleur(ORANGE))
    canevas.setFont("Helvetica-Bold", 41)
    canevas.drawString(marge, 192 * mm, "dépannages")
    canevas.setFillColor(_couleur(VERT_FONCE))
    canevas.setFont("Helvetica", 22)
    canevas.drawString(marge, 178 * mm, "Synthèse opérationnelle")
    canevas.setFillColor(_couleur(ORANGE))
    canevas.rect(marge, 168 * mm, 14 * mm, 0.8 * mm, stroke=0, fill=1)

    total = _texte_kpi(resume, "depannage") or _texte_kpi(resume, "dossier") or "-"
    a_cloturer = _texte_kpi(resume, "cloturer") or "-"
    clotures = _texte_kpi(resume, "clotures") or _texte_kpi(resume, "traites") or "-"
    hors_delai = _texte_kpi(resume, "hors") or "-"
    definitifs = _texte_kpi(resume, "definit") or "-"
    shuntes = _texte_kpi(resume, "shunt") or "-"
    delai = _texte_kpi(resume, "delai") or "-"

    y_kpi = 51 * mm
    largeur_carte = 43 * mm
    gouttiere = 5 * mm
    _dessiner_kpi_couverture(canevas, marge, y_kpi, largeur_carte, 25 * mm, total, "Dépannages", VERT_FONCE, "BT")
    _dessiner_kpi_couverture(canevas, marge + (largeur_carte + gouttiere), y_kpi, largeur_carte, 25 * mm, a_cloturer, "À clôturer", ORANGE, "AC")
    _dessiner_kpi_couverture(canevas, marge + 2 * (largeur_carte + gouttiere), y_kpi, largeur_carte, 25 * mm, clotures, "Clôturés", VERT, "OK")
    _dessiner_kpi_couverture(canevas, marge + 3 * (largeur_carte + gouttiere), y_kpi, largeur_carte, 25 * mm, hors_delai, "Hors délai", ORANGE, "H")

    canevas.setStrokeColor(_couleur(BORDURE))
    canevas.line(marge, 31 * mm, largeur_page - marge, 31 * mm)
    mini_y = 20 * mm
    donnees_bas = [("Définitifs", definitifs), ("Compteurs shuntés", shuntes), ("Délai moyen", delai)]
    for index, (libelle, valeur) in enumerate(donnees_bas):
        x = marge + index * 62 * mm
        canevas.setFillColor(_couleur(FOND_VERT))
        canevas.circle(x + 4 * mm, mini_y + 4 * mm, 4.5 * mm, stroke=0, fill=1)
        canevas.setFillColor(_couleur(VERT_FONCE))
        canevas.setFont("Helvetica-Bold", 6)
        canevas.drawCentredString(x + 4 * mm, mini_y + 2.2 * mm, _kpi_code(libelle))
        canevas.setFont("Helvetica", 7.2)
        canevas.drawString(x + 12 * mm, mini_y + 5.3 * mm, libelle)
        canevas.setFont("Helvetica-Bold", 15)
        canevas.drawString(x + 12 * mm, mini_y - 0.4 * mm, str(valeur))
        if index < 2:
            canevas.setStrokeColor(_couleur(BORDURE))
            canevas.line(x + 55 * mm, mini_y - 1 * mm, x + 55 * mm, mini_y + 10 * mm)

    canevas.setFont("Helvetica", 7)
    canevas.setFillColor(_couleur(SLATE_DARK))
    canevas.drawString(marge, 4.6 * mm, "Gestion des dépannages  •  CIE")
    canevas.drawRightString(largeur_page - marge, 4.6 * mm, "Page 1 / 3")
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


def _dessiner_pied_page_rapport(canevas, document):
    largeur_page, hauteur_page = A4
    numero_page = canevas.getPageNumber()
    canevas.saveState()
    canevas.setFillColor(_couleur(FOND_PAGE))
    canevas.rect(0, 0, largeur_page, hauteur_page, stroke=0, fill=1)
    canevas.setStrokeColor(_couleur(BORDURE))
    canevas.setLineWidth(0.8)
    canevas.line(12 * mm, 14 * mm, largeur_page - 12 * mm, 14 * mm)
    canevas.setFont("Helvetica", 6.5)
    canevas.setFillColor(_couleur(SLATE_DARK))
    canevas.drawString(12 * mm, 8 * mm, "Gestion des dépannages - CIE")
    canevas.drawCentredString(largeur_page / 2, 8 * mm, f"Page {numero_page} / 3")
    canevas.drawRightString(largeur_page - 12 * mm, 8 * mm, f"{timezone.localtime():%d/%m/%Y}")
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


def _tableau_croise_secteur_equipement(secteurs, lignes_equipement, largeur_disponible=265 * mm):
    """Matrice compacte : une ligne par equipement, une cellule par secteur."""
    petit = ParagraphStyle(
        "CelluleMatrice",
        parent=getSampleStyleSheet()["Normal"],
        fontSize=6.1,
        leading=7.2,
        alignment=1,
        textColor=_couleur(SLATE_DARK),
    )
    equipement_style = ParagraphStyle(
        "EquipementMatrice",
        parent=getSampleStyleSheet()["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.7,
        leading=7.8,
        textColor=_couleur(VERT_FONCE),
    )
    entete = ["Equipement"] + [s.libelle for s in secteurs]
    corps = [entete]
    styles_cellules = []
    for ligne_index, item in enumerate(lignes_equipement, start=1):
        libelle_equip = item["libelle"].split(" · ", 1)[-1]
        ligne = [Paragraph(_paragraphe(libelle_equip), equipement_style)]
        for colonne_index, cellule in enumerate(item["par_secteur"], start=1):
            crees = cellule["crees"]
            if not crees:
                ligne.append(Paragraph("-", petit))
                styles_cellules.append(
                    ("BACKGROUND", (colonne_index, ligne_index), (colonne_index, ligne_index), _couleur(FOND_CLAIR))
                )
                continue
            taux = cellule["taux"]
            delai = _valeur_delai_jh(cellule["delai_h"])
            texte = f"<b>{crees}</b> - {_valeur_pct(taux)}<br/><font size='5.5' color='#{SLATE}'>{delai}</font>"
            ligne.append(Paragraph(texte, petit))
            fond = FOND_VERT if taux == 100 else FOND_ORANGE if taux and taux < 70 else FOND_CLAIR
            styles_cellules.append(
                ("BACKGROUND", (colonne_index, ligne_index), (colonne_index, ligne_index), _couleur(fond))
            )
        corps.append(ligne)

    largeur_libelle = 34 * mm
    largeur_dispo = largeur_disponible - largeur_libelle
    largeur_secteur = largeur_dispo / max(len(secteurs), 1)
    colonnes = [largeur_libelle] + [largeur_secteur] * len(secteurs)

    tableau = Table(corps, colWidths=colonnes, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _couleur(NAVY)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 6.6),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, _couleur(ORANGE)),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, _couleur(BORDURE)),
        ("LINEAFTER", (0, 0), (-1, -1), 0.2, _couleur(BORDURE)),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (0, -1), [colors.white, _couleur(FOND_CLAIR)]),
    ]
    style.extend(styles_cellules)
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
