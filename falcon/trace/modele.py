"""Ce qu'une trace du recorder SAP contient, et sous quelle forme.

Une trace `.vbs` est un enregistrement d'ACTIONS. Elle ne dit ni l'identite
des ecrans traverses, ni les champs presents sur chacun. C'est la limite
structurante de tout ce lot : une trace ne peut pas peupler le catalogue, elle
ne peut produire qu'une *esquisse* — que `catalogue.Depot.pour_garde` refuse
deja de servir.

**Les trois formes syntaxiques sont relevees sur une trace reelle**, pas
supposees. Le recorder ecrit un appel sans argument sans parentheses
(`.press`), une affectation avec `=` (`.text = "*BCP*"`), et un appel a
argument separe par une espace (`.sendVKey 0`). L'archive documentait
`.press()` ; c'etait faux, et c'est pour cela que le lot est reste bloque
jusqu'a l'arrivee d'un enregistrement.

**Aucun verbe n'apparait sous deux formes.** C'est une propriete observee, et
le parseur en fait une regle : `text` employe comme appel nu ne serait pas la
meme chose, et laisser passer la confusion ferait rejouer autre chose que ce
qui a ete enregistre.

**Le typage des litteraux n'est pas cosmetique.** Sur le meme objet ALV, la
trace ecrit `selectedRows = "0"` — une chaine — et `currentCellRow = 4` — un
entier. Ce n'est pas une incoherence de l'enregistrement, c'est le typage de
l'API. Un parseur qui normaliserait les deux en entier produirait un rejeu que
SAP refuse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Appel sans argument : `.press`, `.doubleClickCurrentCell`.
APPEL = "appel"

#: Affectation de propriete : `.text = "*BCP*"`, `.currentCellRow = 4`.
AFFECTATION = "affectation"

#: Appel a argument separe par une espace : `.sendVKey 0`, `.expandNode "26"`.
APPEL_ARGUMENT = "appel_argument"

FORMES = (APPEL, AFFECTATION, APPEL_ARGUMENT)

#: Verbes releves sur la trace reelle, avec la forme sous laquelle ils y
#: apparaissent — et la seule sous laquelle ils sont acceptes.
#:
#: Cette table n'est pas une liste blanche du parseur : un verbe inconnu se lit
#: quand meme, il est simplement signale comme inconnu (voir `Geste.connu`).
#: C'est ce qui permet a la commande `inventaire` de nommer ce qu'on ne sait
#: pas encore traiter, au lieu de refuser la trace entiere.
VERBES: dict[str, str] = {
    # gestes de navigation et de commande
    "press": APPEL,
    "sendVKey": APPEL_ARGUMENT,
    "close": APPEL,
    "text": AFFECTATION,
    "selected": AFFECTATION,
    # grille ALV
    "selectedRows": AFFECTATION,
    "currentCellRow": AFFECTATION,
    "doubleClickCurrentCell": APPEL,
    # arbre (SAP Easy Access, favoris)
    "expandNode": APPEL_ARGUMENT,
    "selectedNode": AFFECTATION,
    "doubleClickNode": APPEL_ARGUMENT,
    "topNode": AFFECTATION,
    # confort
    "setFocus": APPEL,
    "caretPosition": AFFECTATION,
    "maximize": APPEL,
}

#: Gestes de confort : ils deplacent le curseur ou la fenetre, ils ne changent
#: rien dans SAP.
#:
#: Ils sont CONSERVES — les jeter perdrait la capacite de rejouer la trace a
#: l'identique, ce qui est le seul controle serieux du parseur — mais marques
#: non significatifs, pour qu'un brouillon de pipeline ne les recopie pas.
#:
#: `currentCellRow` n'en fait PAS partie, et c'est le piege de cette table.
#: `doubleClickCurrentCell` agit sur la cellule COURANTE, pas sur
#: `selectedRows` : la trace positionne `currentCellRow` avant `selectedRows`
#: des que l'index vise n'est pas 0, jamais pour l'index 0. Un rejeu qui
#: l'omettrait double-cliquerait sur la premiere ligne — et ne leverait pas.
CONFORT = frozenset({"setFocus", "caretPosition", "maximize"})

#: Toute cible est enracinee dans une fenetre. La garde des fenetres
#: imprevues compare la-dessus.
FENETRE_RACINE = re.compile(r"^(wnd\[\d+\])")


class TraceInvalide(Exception):
    """La trace ne se lit pas — et on refuse de deviner ce qu'elle disait."""


def rendre_litteral(valeur: object) -> str:
    """Rend un litteral VBScript tel que le recorder l'ecrirait.

    `bool` avant `int` : en Python `True` EST un entier, et l'ordre inverse
    ecrirait `1` la ou la trace ecrit `true`.
    """
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    if isinstance(valeur, int):
        return str(valeur)
    if isinstance(valeur, str):
        return '"' + valeur.replace('"', '""') + '"'
    raise TraceInvalide(f"litteral non rendable : {valeur!r}")


@dataclass(frozen=True)
class Geste:
    """Une ligne d'action de la trace, lue.

    `texte_source` et `ligne` sont conserves pour que tout diagnostic puisse
    renvoyer a l'enregistrement d'origine, et pour que `rendu()` puisse etre
    compare a la ligne exacte dont il sort.
    """

    ordre: int                  # rang parmi les gestes, a partir de 1
    ligne: int                  # rang dans le fichier, a partir de 1
    texte_source: str           # la ligne, sans sa fin de ligne
    retrait: str                # blancs de tete, pour un rendu fidele
    cible: str                  # l'identifiant passe a findById
    verbe: str
    forme: str                  # appel | affectation | appel_argument
    valeur: str | int | bool | None = None

    @property
    def fenetre(self) -> str:
        """`wnd[0]`, `wnd[1]`... — extrait de la cible.

        La fenetre compte : la garde des fenetres imprevues raisonne dessus,
        et le flux de variantes fait la moitie de son travail dans `wnd[1]`.
        """
        trouve = FENETRE_RACINE.match(self.cible)
        return trouve.group(1) if trouve else ""

    @property
    def connu(self) -> bool:
        """Le verbe figure-t-il parmi ceux releves sur une trace reelle."""
        return self.verbe in VERBES

    @property
    def significatif(self) -> bool:
        """Le geste change-t-il quelque chose dans SAP.

        Un verbe inconnu est significatif par defaut : le presumer anodin
        serait exactement la supposition que ce projet refuse.
        """
        return self.verbe not in CONFORT

    def rendu(self) -> str:
        """Reconstruit la ligne VBScript depuis les valeurs LUES.

        Rendu depuis le modele, pas depuis le texte conserve : c'est ce qui
        fait de l'aller-retour une preuve. Une valeur mal typee, un
        echappement perdu, une forme confondue — tout cela casse l'egalite
        avec `texte_source`.
        """
        corps = (f"session.findById({rendre_litteral(self.cible)})"
                 f".{self.verbe}")
        if self.forme == AFFECTATION:
            corps += f" = {rendre_litteral(self.valeur)}"
        elif self.forme == APPEL_ARGUMENT:
            corps += f" {rendre_litteral(self.valeur)}"
        return self.retrait + corps


@dataclass(frozen=True)
class Trace:
    """Une trace entierement lue — toutes ses lignes appariees.

    L'existence d'un objet `Trace` vaut donc certificat : aucune ligne n'a ete
    ignoree. Ce que l'analyse tolerante produit est un `Inventaire`, un type
    different, sans aucun `Geste` — de sorte qu'une lecture partielle ne peut
    pas etre rejouee par megarde.
    """

    source: str
    encodage: str
    bom: bool
    fin_de_ligne: str           # "\r\n" | "\n" | "mixte" | ""
    lignes: int
    gestes: tuple[Geste, ...] = ()
    prologue: tuple[int, ...] = ()
    commentaires: tuple[int, ...] = ()
    vides: tuple[int, ...] = ()

    @property
    def significatifs(self) -> tuple[Geste, ...]:
        return tuple(g for g in self.gestes if g.significatif)

    @property
    def verbes_inconnus(self) -> tuple[str, ...]:
        return tuple(sorted({g.verbe for g in self.gestes if not g.connu}))

    def par_verbe(self) -> tuple[tuple[str, int], ...]:
        decompte: dict[str, int] = {}
        for geste in self.gestes:
            decompte[geste.verbe] = decompte.get(geste.verbe, 0) + 1
        return tuple(sorted(decompte.items()))

    def fenetres(self) -> tuple[str, ...]:
        return tuple(sorted({g.fenetre for g in self.gestes if g.fenetre}))


@dataclass(frozen=True)
class Inventaire:
    """Rapport de couverture d'une trace — y compris d'une trace illisible.

    **Ne contient aucun `Geste`, et c'est le point.** L'inventaire sert a
    decouvrir ce qu'on ne sait pas encore lire ; s'il rendait des gestes, une
    trace a moitie comprise finirait rejouee. La seule facon d'obtenir des
    gestes est `vbs.lire`, qui echoue plutot que de rendre un resultat partiel.
    """

    source: str
    encodage: str
    bom: bool
    fin_de_ligne: str
    lignes: int
    gestes: int = 0
    prologue: int = 0
    commentaires: int = 0
    vides: int = 0
    par_verbe: tuple[tuple[str, int], ...] = ()
    verbes_inconnus: tuple[str, ...] = ()
    inconnues: tuple[tuple[int, str], ...] = ()     # (ligne, texte verbatim)

    @property
    def complet(self) -> bool:
        return not self.inconnues
