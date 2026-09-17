"""Le geste d'apres : regarder ce qu'on vient de capturer.

`Depot.promouvoir` dit ce que ce module existe pour rendre possible : « Geste
explicite, et c'est voulu : c'est le moment ou un humain dit avoir relu
l'ecran. » Voila ce que la console lui montrait avant qu'il le dise : le
triplet, l'empreinte, le nombre de champs, le titre. **Il certifiait avoir relu
un ecran qu'il n'avait jamais vu.** Mesure : le SEUL endroit de tout `falcon/`
qui affiche des `Champ` est `commandes/diagnostic.py`, et il affiche l'ecran
SAP VIVANT. Les 22 variantes que la trace de reference verse en quarantaine
sont invisibles depuis toute la console.

Et le compte rendu d'exploration donnait un ordre qu'aucun outil ne permettait
d'executer : « avant de promouvoir, verifier lesquelles ». Verifier avec quoi ?
Deux YAML ouverts cote a cote dans un editeur. Ce module EST cette
verification.

**Il vit dans `falcon/console/` a dessein.** `_arbres()` fait un glob NON
recursif sur ce dossier : un fichier depose ici tombe gratuitement sous les
gardes qui interdisent un litteral non-cp1252, la plage U+2500-257F, un `\\x1b`
litteral, un `shell=` et tout appel a une methode de `MUTATIONS`. Un
`falcon/tui/` n'en recevrait AUCUNE et exigerait la duplication de tout
l'appareil. « Une regle d'architecture qu'aucun test ne verifie est une
intention, pas une regle. »

**Les vues sont PURES, et c'est ce qui les rend verifiables.** Une vue recoit
des donnees et un `Gabarit`, et rend une liste de `Bloc`. Elle ne lit aucun
disque, n'ecrit sur aucun flux, ne connait aucun peintre. Le decor colore
n'est pas dans ce fichier : il arrive tout fait du peintre, et au niveau NU —
le seul que ce lot cable — il n'y a aucun decor du tout.

**Aucune vue ne concatene a la main.** Toute rangee passe par `rangee()`, qui
repartit la largeur par `colonnes()` et coupe chaque cellule par `couper()` ou
`couper_chemin()`. Ce n'est pas une preference de style : `PeintreNu` coupe la
ligne entiere en dernier recours, donc une rangee composee a la main ne
deborde pas — elle perd sa DERNIERE colonne, en silence, et la ligne garde
l'aspect d'une ligne complete. Le test de propriete du lot verifie qu'aucun
bloc ne depasse la largeur AVANT le peintre, c'est-a-dire que le filet du
peintre ne sert jamais.

**La hauteur est une contrainte au meme titre que la largeur.** Chaque vue
declare son CHROME et son cout par item, et la pagination vaut
`(lignes - chrome) // cout`. Une constante y serait fausse : sur le cmd.exe par
defaut, 25 lignes moins 18 de chrome laissent SIX champs, pas vingt. Dans un
rendu qui reaffiche tout et ne repositionne jamais rien, une vue qui ne tient
pas dans un ecran n'est pas une vue — l'en-tete qui dit sur quel rayon on est a
deja defile quand l'invite apparait. Et quand meme UN item ne tient pas, la vue
REFUSE de se peindre et dit combien de lignes il lui faut : une demi-page n'est
pas une page, et la moitie manquante ne se signale nulle part.

**La geometrie est remesuree a chaque tour**, comme `parcourir` reaffiche le
menu a chaque tour. Une reconnexion RDP a une autre resolution redimensionne la
console de l'hote en pleine session : un gabarit fige continuerait d'ecrire 118
colonnes dans une fenetre redevenue 80, et chaque ligne se replierait. D'ou un
`gabarit` qui est une FONCTION, appelee au debut de chaque tour.

**La promotion en lot n'existe pas, et c'est le point.** Un mot tape ne peut
pas certifier N ecrans que personne n'a lus. `p` n'existe que dans la fiche
OUVERTE ; `garde_de_la_promotion` le rend structurel plutot que conventionnel.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Sequence

from falcon.catalogue import (
    CHAMP, CHERCHE_DANS_CHAMP, CHERCHE_DANS_ECRAN, CURE, ECRAN, QUARANTAINE,
    TOUS, TYPE_SANS_CHANGEABLE, Comparaison, ComparaisonRefusee, Critere,
    Depot, Fiche, Inventaire, Trouvaille, charger, comparer, filtrer,
    parcourues, rapports, sans_mesure,
)
from falcon.commandes.dictionnaire import SEPARATEUR_ECRAN
from falcon.noyau import Champ
from falcon.toile import (
    ALERTE, ATTENUE, ENTETE, LARGEUR_PLANCHER, LIGNE, NEUTRE, SEPARATEUR, VIDE,
    Bloc, Fragment, Gabarit, Peintre, colonnes, couper, couper_chemin,
)

from .menu import CONTINUER, Console

# ---------------------------------------------------------------------------
# Geometrie
# ---------------------------------------------------------------------------

#: Combien de LIGNES chaque forme de bloc produit, une fois peinte.
#:
#: C'est une connaissance que `toile/peintre.py` porte deja, et la dupliquer
#: ici est une dette assumee : une vue doit savoir combien de place elle prend
#: AVANT d'avoir un peintre, sans quoi la pagination ne peut pas se calculer.
#: `test_navigateur` apparie cette table au vrai `PeintreNu`, forme par forme —
#: sans cet appariement ce serait une declaration prise pour une mesure, et le
#: jour ou l'entete passerait a quatre lignes chaque vue deborderait d'une
#: ligne sans que rien ne leve.
LIGNES_PAR_FORME = {LIGNE: 1, VIDE: 1, SEPARATEUR: 1, ENTETE: 3}

#: Colonnes blanches entre deux cellules d'une rangee.
ESPACE = 1

#: Retrait du texte d'un entete, sous son cadre. C'est `PeintreNu` qui le pose
#: (`marge + 2`) ; il entre ici dans le calcul de largeur, jamais dans le texte.
RETRAIT_ENTETE = 2

#: Ce qu'on ecrit quand aucun identifiant ne nomme de fenetre. Pas `wnd[0]` :
#: ce serait l'affirmation que la modale rend dangereuse.
INCONNU = "?"

#: Ce qui remplace un saut de ligne dans une valeur du catalogue. Un espace
#: ferait passer deux lignes pour une phrase ; ce point se VOIT, et il est du
#: decor deja autorise.
RECOLLE = " · "


@dataclass(frozen=True)
class Cellule:
    """Une colonne d'une rangee, et la facon dont elle se coupe.

    `largeur` non nulle fait une colonne FIXE — un numero de rang, un drapeau,
    une empreinte. Les autres se partagent ce qui reste, au prorata de `poids`.

    `chemin` choisit la coupe au MILIEU. Elle vaut pour tout identifiant SAP :
    `wnd[0]/usr/ctxtWERKS-LOW` et `wnd[0]/usr/ctxtWERKS-HIGH` coupes a droite
    donnent la meme chaine, d'aspect complet, et la confusion se recopie dans
    une pipeline.

    **Elle ne garantit pas la distinction, elle la rend possible.** La coupe au
    milieu garde la tete ET la queue ; deux identifiants qui ne different qu'au
    MILIEU restent identiques une fois coupes —
    `wnd[0]/usr/cntlALV/shellcont/shell` et `wnd[0]/usr/cntlB/shellcont/shell`
    rendent tous deux `wnd[0]/usr/cntl~shellcont/shell` a 79 colonnes, et les
    conteneurs ALV sont justement la famille ou le discriminant est au milieu.
    La marque `~` est la, donc la perte SE VOIT : c'est tout ce qu'on peut
    promettre a largeur constante. `vue_champ` ne tronque rien, et c'est la
    qu'on va lire l'identifiant entier.
    """

    texte: str
    poids: int = 1
    largeur: int = 0
    chemin: bool = False
    droite: bool = False
    ton: str = NEUTRE


def _une_seule_ligne(valeur: str) -> str:
    """Aplatit une valeur avant toute mesure de largeur. LE point d'etranglement.

    Un `\n`, un `\r` ou un `\t` traverse le depot intact : `charger` les rend
    tels quels et `illisibles` reste vide — verifie en ecrivant
    `texte: "col1\tcol2"` dans un YAML de quarantaine. Or `couper` et
    `couper_chemin` comptent un caractere de controle pour UNE colonne, et
    `LIGNES_PAR_FORME` compte un bloc LIGNE pour UNE ligne. Les deux contrats
    du module tombent alors en silence, sans une exception : la rangee sort sur
    deux lignes physiques dont la seconde commence en colonne zero, `hauteur()`
    sous-compte, `paginer` calcule une page qui ne tient pas, et l'en-tete qui
    dit sur quel rayon on est defile hors de l'ecran — exactement ce que la
    pagination calculee existe pour empecher. Un `\t` occupe en outre jusqu'a
    huit colonnes a l'affichage, donc une ligne comptee a 79 se replie.

    C'est ici et nulle part ailleurs, parce que `rangee` est le seul assemblage
    du module : une vue ne peut pas composer une ligne sans y passer.
    """
    aplatie = valeur.replace("\r\n", "\n").replace("\r", "\n")
    aplatie = aplatie.replace("\t", " ").replace("\n", RECOLLE)
    # Ce qui reste sous 0x20 — un `\x0b`, un `\x0c` sortis d'une infobulle
    # recopiee — n'a pas de largeur connue non plus. On le remplace par un
    # espace plutot que de le jeter : une chaine qui raccourcit sans marque
    # serait une troncature invisible de plus.
    return "".join(c if ord(c) >= 32 else " " for c in aplatie)


def rangee(gabarit: Gabarit, cellules: Sequence[Cellule], *, marge: int = 2,
           forme: str = LIGNE) -> Bloc:
    """Une rangee de colonnes, chacune coupee a la largeur qu'elle a recue.

    **C'est le SEUL assemblage de ce module**, et c'est ce qui rend la regle
    verifiable au lieu d'etre une consigne : la repartition passe par
    `colonnes()`, chaque cellule par `couper()` ou `couper_chemin()`, et le
    total plus les fixes fait exactement `gabarit.colonnes`. Une vue qui
    composerait une ligne avec une f-string se ferait couper par `PeintreNu`,
    donc perdrait sa derniere colonne sans que la ligne en ait l'air.

    La DERNIERE cellule n'est pas completee a droite : des blancs de fin ne se
    voient pas, mais ils comptent dans la largeur et donnent des lignes pleines
    — exactement ce que la marge d'une colonne du gabarit existe pour eviter.
    """
    if not cellules:
        raise ValueError("une rangee sans cellule n'a rien a montrer")
    souples = [c.poids for c in cellules if not c.largeur]
    if not souples:
        raise ValueError(
            "aucune cellule souple : la rangee ne saurait pas quoi faire de la "
            "largeur restante, et la figer serait une supposition sur l'ecran")

    retrait = marge + (RETRAIT_ENTETE if forme == ENTETE else 0)
    fixes = [retrait, ESPACE * (len(cellules) - 1)]
    fixes += [c.largeur for c in cellules if c.largeur]
    parts = list(colonnes(gabarit, souples, fixes))

    fragments: list[Fragment] = []
    for rang, cellule in enumerate(cellules):
        largeur = cellule.largeur or parts.pop(0)
        coupe = couper_chemin if cellule.chemin else couper
        texte = coupe(_une_seule_ligne(cellule.texte), largeur)
        if rang < len(cellules) - 1:
            texte = texte.rjust(largeur) if cellule.droite else texte.ljust(largeur)
            texte += " " * ESPACE
        elif cellule.droite:
            texte = texte.rjust(largeur)
        fragments.append(Fragment(texte, cellule.ton))
    return Bloc(fragments=tuple(fragments), forme=forme, marge=marge)


def texte(gabarit: Gabarit, contenu: str, *, ton: str = NEUTRE,
          marge: int = 2) -> Bloc:
    """Une ligne de prose, coupee a la largeur. Une seule colonne."""
    return rangee(gabarit, (Cellule(contenu, ton=ton),), marge=marge)


def vide() -> Bloc:
    return Bloc(forme=VIDE)


def separateur(marge: int = 2) -> Bloc:
    return Bloc(forme=SEPARATEUR, marge=marge)


def entete(gabarit: Gabarit, gauche: str, droite: str = "") -> Bloc:
    """Le cadre et son titre. `droite` se pose au bout de la meme ligne."""
    cellules = [Cellule(gauche, poids=3)]
    if droite:
        cellules.append(Cellule(droite, largeur=min(len(droite),
                                                    max(gabarit.colonnes // 3,
                                                        1))))
    return rangee(gabarit, cellules, forme=ENTETE)


def hauteur(blocs: Sequence[Bloc]) -> int:
    """Combien de lignes ces blocs feront une fois peints."""
    return sum(LIGNES_PAR_FORME[bloc.forme] for bloc in blocs)


@dataclass(frozen=True)
class Pagination:
    """Ou l'on en est dans une liste trop longue pour l'ecran."""

    par_page: int
    page: int
    pages: int
    debut: int
    fin: int


def paginer(gabarit: Gabarit, *, chrome: int, cout: int, total: int,
            page: int) -> Pagination | None:
    """Combien d'items tiennent, et lesquels. `None` si aucun ne tient.

    `chrome` est le nombre de lignes que la vue depense en en-tete, legende et
    pied ; `cout` le nombre de lignes que coute UN item. La formule est la
    seule chose qui rende la pagination vraie sur l'ecran qu'on a : une
    constante — vingt lignes, comme le suggerent les maquettes dessinees sur
    une grande fenetre — donne SIX champs de trop sur le cmd.exe par defaut, et
    la vue deborde sans que rien ne leve. La hauteur employee est celle du
    gabarit, qui peut venir d'une mesure, d'une declaration ou de rien du
    tout — `Gabarit.source` le dit, et l'accueil l'ecrit.

    `None` plutot qu'une page d'un item impossible : une vue dont le chrome
    seul ne tient pas dans la fenetre n'est pas une vue degradee, c'est une vue
    illisible. L'appelant ecrit alors combien de lignes il lui faut.
    """
    par_page = (gabarit.lignes - chrome) // cout
    if par_page < 1:
        return None
    pages = max((total + par_page - 1) // par_page, 1)
    page = min(max(page, 0), pages - 1)
    debut = page * par_page
    return Pagination(par_page=par_page, page=page, pages=pages, debut=debut,
                      fin=min(debut + par_page, total))


def trop_etroit(gabarit: Gabarit) -> list[Bloc]:
    """Le refus de peindre, faute de LARGEUR. Il se compose sans `rangee`.

    La hauteur avait un refus explicite — `paginer` rend `None`, `trop_court`
    ecrit les lignes disponibles et necessaires. La largeur n'en avait AUCUN :
    `gabarit_pour` ne pose pas de plancher, et ce sont les largeurs fixes des
    rangees qui finissaient par ne plus tenir. Mesure, par balayage : a 30
    colonnes la liste, la fiche, le detail et la comparaison levent
    `ValueError: il reste -2 colonne(s) pour 2 colonne(s) souples` ; a 15 les
    rapports et l'aide ; a 5 l'accueil. `menu.parcourir` n'attrape rien et
    `ERREURS_LISIBLES` ne contient pas `ValueError` : l'utilisateur qui a
    retreci sa fenetre recevait une trace de pile et perdait sa session.

    **Il ne passe pas par `rangee`.** Un refus compose comme ce qu'il refuse
    leverait pour la meme raison — c'est le piege que `PeintreNu` a deja
    resolu en bornant ses deux retraits. D'ou des `Bloc` a marge nulle, coupes
    a `max(colonnes, 1)`.

    `LARGEUR_PLANCHER` et `Gabarit.trop_etroit` existent depuis le lot 1, et le
    lot qui peint est leur premier consommateur : « la vue doit refuser
    d'elle-meme » etait ecrit et n'etait fait nulle part.
    """
    largeur = max(gabarit.colonnes, 1)
    lignes = (
        "Fenetre trop etroite.",
        f"colonnes mesurees   {gabarit.colonnes}",
        f"colonnes minimales  {LARGEUR_PLANCHER}",
        "Elargis la fenetre, puis retape la commande.",
    )
    return [Bloc(fragments=(Fragment(couper(ligne, largeur)),), marge=0)
            for ligne in lignes]


def trop_court(gabarit: Gabarit, demandees: int) -> list[Bloc]:
    """Le refus de peindre. Court par construction : il doit tenir, lui."""
    return [
        vide(),
        texte(gabarit, "Cette vue ne tient pas dans cette fenetre."),
        texte(gabarit, f"lignes disponibles   {gabarit.lignes}"),
        texte(gabarit, f"lignes necessaires   {demandees}"),
        texte(gabarit, "Agrandis la fenetre, puis retape la commande."),
        *commandes(gabarit, ("0",)),
    ]


def tenir(blocs: list[Bloc], gabarit: Gabarit) -> list[Bloc]:
    """Rend les blocs s'ils tiennent, le refus sinon.

    Pour les vues SANS pagination — l'accueil, le detail d'un champ, l'aide —
    ou il n'y a pas d'item a retrancher : on montre tout, ou on dit qu'on ne
    peut pas. Montrer les quinze premieres lignes d'un ecran qui en fait vingt
    laisserait l'utilisateur conclure qu'il a tout lu.
    """
    besoin = hauteur(blocs)
    if besoin <= gabarit.lignes:
        return blocs
    return trop_court(gabarit, besoin)


# ---------------------------------------------------------------------------
# Ce que les vues montrent d'une fiche
# ---------------------------------------------------------------------------

#: Le drapeau de rayon de la liste. `Q+` est un FAIT DE FICHIER — la meme
#: empreinte existe aussi au cure — et non la trace d'une decision humaine :
#: le catalogue n'en garde aucune.
RAYON_COURT = {QUARANTAINE: "Q", CURE: "C"}


def _rayon_court(fiche: Fiche) -> str:
    court = RAYON_COURT[fiche.rayon]
    return court + "+" if fiche.au_cure else court


def _fenetres(fiche: Fiche) -> str:
    return ",".join(fiche.fenetres) or INCONNU


def _compte_champs(fiche: Fiche) -> str:
    """« 12 ch » ou « 2 id. » — deux unites, deux mots.

    Une esquisse porte les identifiants TOUCHES par la trace sur un ecran de
    taille inconnue ; un releve porte les champs PRESENTS. Les afficher dans la
    meme colonne avec le meme mot serait un compte plausible et faux : « 2 »
    sur une esquisse ne dit pas que l'ecran a deux champs.
    """
    combien = len(fiche.variante.champs)
    return f"{combien} ch" if fiche.relevee else f"{combien} id."


def _ecran_du(fiche: Fiche) -> str:
    """Le triplet dans la forme que le classeur attend (`IH06::SAPLIH06::1000`)."""
    return SEPARATEUR_ECRAN.join(fiche.clef.triplet)


def _titre_de(fiche: Fiche) -> str:
    if fiche.variante.titre:
        return fiche.variante.titre
    if fiche.relevee:
        return ""
    return "(esquisse : ni titre ni identite d'ecran)"


def _modifiable(champ: Champ) -> str:
    """« oui », « non », « ? » — ou « (1) » quand ce OUI-LA est sans preuve.

    Le tri-etat vient du fichier : `None` veut dire « le fichier ne le
    renseigne pas », et ce n'est pas « non ». Le quatrieme cas est ailleurs :
    un `GuiShell` n'expose pas `Changeable`, la couture y inscrit son defaut —
    `True` — et la valeur est alors renseignee sans avoir ete mesuree.
    L'ecrire « oui » la ferait passer pour une lecture.

    **Le TYPE seul ne suffit pas a poser « (1) », et le croire etait un
    defaut.** Un `GuiShell` qui porte `modifiable: false` ou rien du tout
    n'affiche PAS « (1) » : la note de pied parle d'un « oui », et il n'y en a
    pas. Un champ que le fichier declare VERROUILLE presente comme un oui sans
    preuve est l'inverse de la donnee, et qui redige un `set` y lit l'inverse
    de ce qu'il y a. La garde est dans `sans_mesure`, qui regarde la valeur.
    """
    if sans_mesure(champ):
        return "(1)"
    if champ.modifiable is None:
        return INCONNU
    return "oui" if champ.modifiable else "non"


NOTE_SHELL = (
    "(1) un GuiShell n'expose pas `Changeable` : la couture y inscrit son",
    "    defaut. Ce « oui »-la n'a ete mesure par personne.",
)

#: Ce qu'une esquisse promue certifie, et ce qu'elle ne certifie pas.
#:
#: Ecrit ICI, dans le module PUR, et relu par `ecrans.promouvoir` : les deux
#: ecrans qui promeuvent doivent dire la meme chose, et deux copies auraient
#: diverge a la premiere retouche. Le texte est celui du lot precedent, au
#: caractere pres — `test_console` epingle deja « personne n'a vu cet ».
TEXTE_ESQUISSE = (
    "C'est une ESQUISSE, tiree d'une trace : personne n'a vu cet",
    "ecran. La promouvoir la rend disponible pour REDIGER une",
    "pipeline, rien de plus — une garde d'identite la refusera",
    "toujours. Tu certifies avoir lu le FICHIER, pas l'ecran.",
)


# ---------------------------------------------------------------------------
# L'etat du navigateur
# ---------------------------------------------------------------------------

ACCUEIL = "accueil"
LISTE = "liste"
FICHE = "fiche"
DETAIL = "detail"
COMPARAISON = "comparaison"
RECHERCHE = "recherche"
RAPPORTS = "rapports"
AIDE = "aide"

ECRANS = frozenset({ACCUEIL, LISTE, FICHE, DETAIL, COMPARAISON, RECHERCHE,
                    RAPPORTS, AIDE})


@dataclass(frozen=True)
class Vue:
    """Ou l'on est, et ce qu'on a marque. Immuable : chaque tour en rend une.

    `ouverte` porte la fiche AFFICHEE, pas son numero : c'est sur elle que
    `garde_de_la_promotion` mord. Un numero designerait une ligne d'une liste
    qui a pu changer entre-temps — un relecture (`L`), un filtre — et la garde
    laisserait promouvoir une autre variante que celle qu'on a lue.
    """

    ecran: str = ACCUEIL
    critere: Critere = field(default_factory=Critere)
    page: int = 0
    ouverte: Fiche | None = None
    champ: int = -1
    marques: tuple[Fiche, ...] = ()

    def __post_init__(self) -> None:
        if self.ecran not in ECRANS:
            raise ValueError(f"ecran inconnu : {self.ecran!r}")


class PromotionHorsFiche(Exception):
    """On promeut depuis un ecran qui n'a pas montre ce qu'on promeut."""


def garde_de_la_promotion(vue: Vue, fiche: Fiche) -> None:
    """Interdit de promouvoir ce qu'on n'a pas affiche.

    `confirmer(empreinte)` protege contre le reflexe : on ne peut pas taper
    seize caracteres hexadecimaux sans avoir lu le recapitulatif qui les porte.
    Le navigateur AFFAIBLIRAIT cette protection, parce que dans la liste
    l'empreinte serait recopiable sans avoir rien regarde. La ceremonie
    resterait, son sens partirait. `p` n'existe donc que dans la fiche OUVERTE.

    Elle n'entre PAS dans `outils/neutraliser.py`, et c'est delibere : elle ne
    cede sur rien qui atteigne SAP ni le disque, seulement sur une
    certification moins fondee. L'inscrire ferait dire « les dix gardes » a un
    chiffre dont les elements n'auraient plus la meme portee, et ce depot a
    deja paye le prix d'un chiffre qui voulait dire deux choses.
    """
    if vue.ecran != FICHE or vue.ouverte is None:
        raise PromotionHorsFiche(
            f"{fiche.clef.empreinte} n'est pas la fiche ouverte. Ouvre-la "
            f"(son numero), lis ses champs, puis promeus-la.")
    if vue.ouverte.clef != fiche.clef or vue.ouverte.rayon != fiche.rayon:
        raise PromotionHorsFiche(
            f"{fiche.clef.empreinte} n'est pas la fiche ouverte "
            f"({vue.ouverte.clef.empreinte}). Ouvre-la, lis ses champs, puis "
            f"promeus-la.")


# ---------------------------------------------------------------------------
# Les vues — fonctions PURES
# ---------------------------------------------------------------------------

#: Combien de fichiers illisibles l'accueil nomme avant de se resumer. Trois,
#: parce qu'au-dela la liste chasse de l'ecran tout ce qui va bien — et que le
#: COMPTE, lui, est toujours exact : c'est la liste qui se tronque, jamais le
#: nombre.
ILLISIBLES_MONTRES = 3


def vue_accueil(inventaire: Inventaire, gabarit: Gabarit, *, racine: Path,
                comptes_rendus: int) -> list[Bloc]:
    """Ce qu'on a relu, ce qu'on n'a pas pu relire, et ou l'on est.

    Les illisibles sont nommes AVANT les totaux dans l'ordre de lecture de
    l'ecran parce qu'ils changent le sens des totaux : « 22 variante(s) » se
    lit autrement quand on sait qu'un fichier sur onze n'a pas ete ouvert.
    """
    if gabarit.trop_etroit:
        return trop_etroit(gabarit)
    quarantaine = inventaire.rayon(QUARANTAINE)
    cure = inventaire.rayon(CURE)
    blocs = [
        entete(gabarit, "FALCON — navigateur de catalogue"),
        texte(gabarit, str(racine)),
        texte(gabarit,
              f"{inventaire.fichiers_lus} fichier(s) lus en "
              f"{inventaire.duree_ms / 1000:.1f} s  ->  "
              f"{len(quarantaine)} variante(s) en quarantaine, "
              f"{len(cure)} au cure"),
    ]

    if inventaire.illisibles:
        blocs.append(vide())
        blocs.append(texte(
            gabarit,
            f"{len(inventaire.illisibles)} fichier(s) n'ont pas pu etre lus, "
            f"et n'entrent dans aucun compte :", ton=ALERTE))
        for chemin, motif in inventaire.illisibles[:ILLISIBLES_MONTRES]:
            # Relatif a la racine, deja affichee deux lignes plus haut, et coupe
            # au MILIEU : coupe a droite, un chemin absolu un peu long perdait
            # justement le nom du fichier — la seule chose a lire ici.
            try:
                nom = str(chemin.relative_to(racine))
            except ValueError:
                nom = str(chemin)
            blocs.append(rangee(gabarit, (Cellule(nom, chemin=True),),
                                marge=4))
            blocs.append(texte(gabarit, motif, marge=6, ton=ATTENUE))
        reste = len(inventaire.illisibles) - ILLISIBLES_MONTRES
        if reste > 0:
            blocs.append(texte(gabarit, f"et {reste} autre(s), non nomme(s) "
                                        f"ici faute de place.", marge=4))

    blocs.append(vide())
    blocs.append(texte(gabarit, f"{comptes_rendus} compte(s) rendu(s) "
                                f"d'exploration conserves"))
    blocs.append(vide())
    blocs.append(texte(gabarit, f"largeur {gabarit.colonnes} "
                                f"({gabarit.source}), hauteur {gabarit.lignes}",
                       ton=ATTENUE))
    blocs.append(vide())
    blocs.append(texte(gabarit, "Tape ? pour la liste des commandes, ou "
                                "Entree pour voir la quarantaine."))
    return tenir(blocs, gabarit)


#: Les colonnes de la liste, et leurs largeurs fixes.
_LARGEUR_RANG = 3
_LARGEUR_MARQUE = 1
_LARGEUR_RAYON = 2
_LARGEUR_SOURCE = 1
_LARGEUR_FENETRE = 7
_LARGEUR_CHAMPS = 7


def _rangee_liste(gabarit: Gabarit, cellules: Sequence[Cellule]) -> Bloc:
    return rangee(gabarit, cellules, marge=4)


def vue_liste(vue: Vue, fiches: Sequence[Fiche], total: int,
              gabarit: Gabarit) -> list[Bloc]:
    """Une ligne par variante, et rien qui cache une ligne sans le dire.

    Le filtre est ECRIT en toutes lettres au-dessus du tableau, y compris
    quand il n'y en a pas. Une liste filtree qui ne dit pas qu'elle l'est est
    un compte plausible et faux : « 3 variantes » sur un catalogue qui en porte
    vingt-deux se lit comme « il n'y en a que trois ».

    **`total` est recu a part de `len(fiches)`**, comme dans la recherche. La
    liste affichait `len(fiches)` aux deux places pendant que `filtrer`
    tronquait a cinq cents : sur un inventaire de six cents variantes l'ecran
    ecrivait « 500 variante(s) » puis « 24 affichee(s) sur 500 », et les cent
    dernieres n'etaient ni comptees, ni nommees, ni joignables par `<n>`,
    `m <n>` ou `p`. C'est mot pour mot le defaut que la docstring de `filtrer`
    dit exister pour eviter. Aujourd'hui `_fiches_de` demande une limite egale
    a la taille de l'inventaire, donc la pagination est la seule troncature —
    mais l'ecart est ECRIT si jamais il reparait, plutot que suppose absent.
    """
    if gabarit.trop_etroit:
        return trop_etroit(gabarit)
    relevees = sum(1 for f in fiches if f.relevee)
    rayon = {QUARANTAINE: "QUARANTAINE", CURE: "CURE",
             TOUS: "QUARANTAINE + CURE"}[vue.critere.rayon]

    tete = [
        entete(gabarit, "FALCON — navigateur de catalogue", rayon),
        texte(gabarit, f"{total} variante(s)   ·   {relevees} relevee(s), "
                       f"{len(fiches) - relevees} esquisse(s)"
                       + _mention_au_cure(vue, fiches)),
        texte(gabarit, "filtre : " + (f"« {vue.critere.motif} »"
                                      if vue.critere.motif else "(aucun)")
                       + ("   ·   a decider seulement"
                          if vue.critere.a_decider else "")),
    ]
    if vue.critere.motif:
        # Ou l'on a cherche, comme l'ecran de recherche le dit. La liste
        # l'ecrivait nulle part : « filtre : werks » ne dit pas si `werks` a
        # ete cherche dans l'identite de l'ecran ou dans ses champs, et les
        # deux ne rendent pas du tout la meme chose.
        tete.append(texte(gabarit, "cherche dans : "
                                   + ", ".join(CHERCHE_DANS_ECRAN),
                          ton=ATTENUE))
    if len(fiches) < total:
        tete.append(texte(
            gabarit, f"{total - len(fiches)} variante(s) ne sont PAS dans "
                     f"cette liste : la recherche s'est arretee a "
                     f"{len(fiches)}.", ton=ALERTE))
    tete += [
        separateur(),
        _rangee_liste(gabarit, (
            Cellule("n", largeur=_LARGEUR_RANG, droite=True),
            Cellule("m", largeur=_LARGEUR_MARQUE),
            Cellule("ry", largeur=_LARGEUR_RAYON),
            Cellule("s", largeur=_LARGEUR_SOURCE),
            Cellule("ecran", poids=3),
            Cellule("fen", largeur=_LARGEUR_FENETRE),
            Cellule("champs", largeur=_LARGEUR_CHAMPS, droite=True),
            Cellule("titre", poids=4))),
        separateur(),
    ]
    pied_forme = _pied_liste(gabarit, vue, Pagination(1, 0, 1, 0, 0),
                             len(fiches))
    page = paginer(gabarit, chrome=hauteur(tete) + hauteur(pied_forme),
                   cout=1, total=len(fiches), page=vue.page)
    if page is None:
        return trop_court(gabarit,
                          hauteur(tete) + hauteur(pied_forme) + 1)

    corps = []
    for rang in range(page.debut, page.fin):
        fiche = fiches[rang]
        corps.append(_rangee_liste(gabarit, (
            Cellule(str(rang + 1), largeur=_LARGEUR_RANG, droite=True),
            Cellule("*" if fiche in vue.marques else "",
                    largeur=_LARGEUR_MARQUE),
            Cellule(_rayon_court(fiche), largeur=_LARGEUR_RAYON),
            Cellule("o" if fiche.relevee else "e", largeur=_LARGEUR_SOURCE),
            Cellule(_ecran_du(fiche), poids=3),
            Cellule(_fenetres(fiche), largeur=_LARGEUR_FENETRE),
            Cellule(_compte_champs(fiche), largeur=_LARGEUR_CHAMPS,
                    droite=True),
            Cellule(_titre_de(fiche), poids=4))))
    if not fiches:
        # Une page vide se lit « le catalogue est vide », ce qui est faux des
        # qu'un filtre est pose. Le filtre est deja ecrit au-dessus ; cette
        # ligne dit qu'il n'a rien laisse passer, et les deux ensemble
        # suffisent a distinguer les deux cas.
        corps.append(texte(gabarit, "Aucune variante ici. « f » change de "
                                    "rayon, « / » sans motif ote le filtre.",
                           marge=4))

    return tete + corps + _pied_liste(gabarit, vue, page, len(fiches))


def _mention_au_cure(vue: Vue, fiches: Sequence[Fiche]) -> str:
    """« N deja au cure », et SEULEMENT la ou ce compte veut dire quelque chose.

    `charger` ne pose `au_cure` que sur les fiches de QUARANTAINE : c'est la
    question « celle-ci a-t-elle son double au cure », et une fiche du cure ne
    se la pose pas. Sur le rayon CURE, le compteur ecrivait donc « 0 deja au
    cure » pour trois variantes qui y sont toutes — le sens du compteur
    changeait avec l'ecran sans que l'etiquette change.
    """
    if vue.critere.rayon == CURE:
        return ""
    combien = sum(1 for f in fiches if f.au_cure)
    return f"   ·   {combien} aussi au cure"


def _pied_liste(gabarit: Gabarit, vue: Vue, page: Pagination,
                total: int) -> list[Bloc]:
    montrees = page.fin - page.debut
    return [
        separateur(),
        texte(gabarit, f"page {page.page + 1}/{page.pages}  —  {montrees} "
                       f"affichee(s) sur {total}"),
        texte(gabarit, "ry : Q quarantaine, Q+ aussi au cure, C cure  ·  "
                       "s : o relevee, e esquisse", ton=ATTENUE),
        texte(gabarit, "fen : lue dans les identifiants, « ? » si aucun ne la "
                       "nomme", ton=ATTENUE),
        separateur(),
        *commandes(gabarit, ("<n>", "/motif", "//motif", "m", "d", "f", "a",
                             "r", "L", "+", "-", "?", "0")),
    ]


def vue_fiche(vue: Vue, fiche: Fiche, voisines: Sequence[Fiche],
              gabarit: Gabarit) -> list[Bloc]:
    """Ce qu'il faut avoir lu avant de promouvoir — les CHAMPS, un par un.

    Les voisines sont nommees quand il y en a : deux variantes d'un meme
    triplet sont le cas que le catalogue existe pour distinguer, et promouvoir
    la premiere sans avoir vu la seconde est exactement le geste que la
    comparaison sert a eviter.
    """
    if gabarit.trop_etroit:
        return trop_etroit(gabarit)
    ecrivables, verrouilles, non_renseignes = fiche.compte_modifiable
    tete = [
        entete(gabarit, " / ".join(fiche.clef.triplet), fiche.rayon),
        rangee(gabarit, (Cellule("empreinte", largeur=11),
                         Cellule(fiche.clef.empreinte))),
        rangee(gabarit, (Cellule("titre", largeur=11),
                         Cellule(_titre_de(fiche) or "(aucun)"))),
        rangee(gabarit, (Cellule("capture", largeur=11),
                         Cellule(fiche.variante.capture_le or "(aucune)"),
                         Cellule("source : " + fiche.variante.source,
                                 poids=1))),
        rangee(gabarit, (Cellule("fichier", largeur=11),
                         Cellule(str(fiche.fichier), chemin=True))),
        rangee(gabarit, (Cellule("fenetres", largeur=11),
                         Cellule("citees par les identifiants : "
                                 + _fenetres(fiche)))),
        texte(gabarit,
              f"{len(fiche.variante.champs)} champ(s) — {ecrivables} "
              f"ecrivable(s), {verrouilles} verrouille(s), {non_renseignes} "
              f"non renseigne(s) au fichier"),
    ]
    if voisines:
        autres = ", ".join(f"{v.clef.empreinte[:8]} {_fenetres(v)}"
                           for v in voisines)
        tete.append(vide())
        tete.append(texte(gabarit,
                          f"{len(voisines)} autre(s) variante(s) du meme "
                          f"triplet dans ce rayon : {autres}", ton=ALERTE))
        tete.append(texte(gabarit, "Avant de promouvoir, compare-les : m ici, "
                                   "0, puis m sur l'autre, puis d"))
    tete += [
        separateur(),
        _rangee_liste(gabarit, (
            Cellule("n", largeur=_LARGEUR_RANG, droite=True),
            Cellule("identifiant", poids=5),
            Cellule("type", largeur=14),
            Cellule("mod.", largeur=4),
            Cellule("libelle", poids=3))),
        separateur(),
    ]

    shells = bool(fiche.sans_preuve)
    pied_forme = _pied_fiche(gabarit, Pagination(1, 0, 1, 0, 0),
                             len(fiche.variante.champs), shells)
    chrome = hauteur(tete) + hauteur(pied_forme)
    page = paginer(gabarit, chrome=chrome, cout=1,
                   total=len(fiche.variante.champs), page=vue.page)
    if page is None:
        return trop_court(gabarit, chrome + 1)

    corps = []
    for rang in range(page.debut, page.fin):
        champ = fiche.variante.champs[rang]
        corps.append(_rangee_liste(gabarit, (
            Cellule(str(rang + 1), largeur=_LARGEUR_RANG, droite=True),
            Cellule(champ.id, poids=5, chemin=True),
            Cellule(champ.type, largeur=14),
            Cellule(_modifiable(champ), largeur=4),
            Cellule(champ.texte, poids=3))))

    return tete + corps + _pied_fiche(gabarit, page,
                                      len(fiche.variante.champs), shells)


def _pied_fiche(gabarit: Gabarit, page: Pagination, total: int,
                shells: bool) -> list[Bloc]:
    blocs = [
        separateur(),
        texte(gabarit, f"champs {page.debut + 1}-{page.fin} sur {total}  —  "
                       f"page {page.page + 1}/{page.pages}"),
    ]
    if shells:
        blocs += [texte(gabarit, ligne, ton=ATTENUE) for ligne in NOTE_SHELL]
    blocs += [
        separateur(),
        *commandes(gabarit, ("<n>", "+", "-", "m", "p", "0")),
    ]
    return blocs


def vue_champ(fiche: Fiche, champ: Champ, gabarit: Gabarit) -> list[Bloc]:
    """Un champ, un attribut par ligne, et ce qu'on ne peut pas en conclure.

    Chaque valeur recoit la largeur entiere moins son etiquette, la ou le
    tableau de la fiche lui donne une colonne etroite. Elle reste coupee a la
    largeur du gabarit — c'est la regle de tout ce module, et la marque `~` dit
    ou — parce que replier une valeur sur plusieurs lignes ferait dependre la
    HAUTEUR de cet ecran de la longueur d'une infobulle : la vue tiendrait ou
    non selon la donnee, et la page refuserait de s'afficher un jour sur deux.
    """
    if gabarit.trop_etroit:
        return trop_etroit(gabarit)
    blocs = [
        entete(gabarit, champ.id),
        rangee(gabarit, (Cellule("ecran", largeur=11),
                         Cellule(_ecran_du(fiche)),
                         Cellule("·  " + fiche.clef.empreinte, poids=1))),
        rangee(gabarit, (Cellule("type", largeur=11), Cellule(champ.type))),
        rangee(gabarit, (Cellule("soustype", largeur=11),
                         Cellule(champ.soustype or "(vide)"))),
        rangee(gabarit, (Cellule("nom", largeur=11),
                         Cellule(champ.nom or "(vide)"))),
        rangee(gabarit, (Cellule("texte", largeur=11),
                         Cellule(champ.texte or "(vide)"))),
        rangee(gabarit, (Cellule("infobulle", largeur=11),
                         Cellule(champ.infobulle or "(vide)"))),
        rangee(gabarit, (Cellule("modifiable", largeur=11),
                         Cellule(INCONNU if champ.modifiable is None
                                 else ("oui" if champ.modifiable else "non")))),
    ]
    # DEUX conditions, et pas une : le paragraphe sur `texte` est vrai de tout
    # GuiShell, quelle que soit la valeur de `modifiable` ; celui sur
    # `modifiable` ne parle que du defaut que la couture inscrit, c'est-a-dire
    # de `True`. Les avoir conditionnes ensemble sur le seul TYPE faisait
    # ecrire « `modifiable` est renseigne ici » quatre lignes sous une ligne
    # qui affichait « modifiable  ? » — un texte qui affirme davantage, et
    # autre chose, que la valeur qu'il commente, sur le meme ecran.
    if champ.type == TYPE_SANS_CHANGEABLE:
        blocs += [
            vide(),
            texte(gabarit, "A LIRE AVANT DE S'EN SERVIR", ton=ALERTE),
            texte(gabarit, "`texte` vaut ici le nom de classe ActiveX du "
                           "controle, pas un", marge=4),
            texte(gabarit, "libelle : un shell repond ca a la propriete "
                           "`Text`. Ni le catalogue", marge=4),
            texte(gabarit, "ni les gardes ne s'en servent. C'est `soustype` "
                           "qui distingue un", marge=4),
            texte(gabarit, "vrai editeur d'une barre d'outils.", marge=4),
        ]
    if sans_mesure(champ):
        blocs += [
            vide(),
            texte(gabarit, "`modifiable` vaut « oui » et personne ne l'a "
                           "peut-etre mesure : un", marge=4),
            texte(gabarit, "shell n'expose pas `Changeable`, et la couture "
                           "inscrit alors son", marge=4),
            texte(gabarit, "defaut. Sur un GuiShell, ce « oui » ne vaut pas "
                           "preuve.", marge=4),
        ]
    blocs += [
        vide(),
        rangee(gabarit, (Cellule("Pour le classeur :", largeur=20),
                         Cellule("ecran", largeur=6),
                         Cellule(_ecran_du(fiche)))),
        rangee(gabarit, (Cellule("", largeur=20), Cellule("cible", largeur=6),
                         Cellule(champ.id, chemin=True))),
        *commandes(gabarit, ("0",)),
    ]
    return tenir(blocs, gabarit)


def vue_comparaison(comparaison: Comparaison, vue: Vue,
                    gabarit: Gabarit) -> list[Bloc]:
    """La MESURE de deux variantes. Jamais la conclusion « c'est la modale ».

    Le bloc « CE QUE FALCON NE SAIT PAS » ne s'affiche que quand les deux
    conditions sont reunies — aucun identifiant commun ET des fenetres citees
    disjointes — et il DECRIT le phenomene sans l'affirmer. `comparer` a deja
    refuse toute esquisse : sans cette garde, six paires de la quarantaine de
    reference le declencheraient des le premier jour.
    """
    if gabarit.trop_etroit:
        return trop_etroit(gabarit)
    gauche, droite = comparaison.gauche, comparaison.droite
    # Le titre ne porte qu'UN triplet, et c'est desormais exact : `comparer`
    # refuse deux triplets differents. Avant cette garde, l'ecran titrait du
    # seul triplet de gauche une comparaison dont le cote droit n'etait
    # identifie nulle part.
    ecarts_par_id = len({ecart.id for ecart in comparaison.ecarts})
    tete = [
        entete(gabarit, "Comparaison — " + " / ".join(gauche.clef.triplet)),
        _rangee_cote(gabarit, "gauche", gauche),
        _rangee_cote(gabarit, "droite", droite),
        vide(),
        # Deux lignes et pas une : a 79 colonnes la ligne unique se coupait sur
        # le nombre d'ecarts, et aucune vue plus large n'est atteignable depuis
        # le navigateur. Et les deux nombres ne comptent pas la meme chose —
        # `ecarts` porte des couples (identifiant, attribut), le tableau
        # dessous compte des identifiants : « ecarts 4 » sous « lignes 1-1 sur
        # 1 » sont deux comptes justes qu'on lit comme contradictoires.
        rangee(gabarit, (
            Cellule(f"communs {len(comparaison.communs)}", poids=1),
            Cellule(f"a gauche seulement {len(comparaison.seuls_a_gauche)}",
                    poids=2),
            Cellule(f"a droite seulement {len(comparaison.seuls_a_droite)}",
                    poids=2))),
        rangee(gabarit, (
            Cellule(f"ecarts : {ecarts_par_id} identifiant(s) commun(s), "
                    f"{len(comparaison.ecarts)} attribut(s)", poids=1),)),
        separateur(),
        texte(gabarit, "CE QUI EST MESURE"),
        texte(gabarit, ("Ces deux variantes n'ont AUCUN identifiant commun."
                        if comparaison.aucun_identifiant_commun
                        else f"Elles partagent {len(comparaison.communs)} "
                             f"identifiant(s)."), marge=4),
        texte(gabarit, _phrase_fenetres(comparaison), marge=4),
    ]
    if comparaison.aucun_identifiant_commun and comparaison.fenetres_disjointes:
        tete += [
            vide(),
            texte(gabarit, "CE QUE FALCON NE SAIT PAS", ton=ALERTE),
            texte(gabarit, "La variante ne porte pas la fenetre dont elle "
                           "vient : `fields(f)` prend", marge=4),
            texte(gabarit, "son identite de `screen()`, qui decrit wnd[0]. Le "
                           "releve d'une MODALE", marge=4),
            texte(gabarit, "porte donc le programme et le dynpro de l'ecran "
                           "de DESSOUS. Ce que", marge=4),
            texte(gabarit, "tu vois est la signature du couple modale / "
                           "porteur decrit par le", marge=4),
            texte(gabarit, "compte rendu — PAS sa preuve. Les deux se "
                           "promeuvent separement, et", marge=4),
            texte(gabarit, "rien n'oblige a promouvoir les deux.", marge=4),
        ]
    tete += [
        separateur(),
        _rangee_liste(gabarit, (Cellule("cote", largeur=10),
                                Cellule("identifiant", poids=5),
                                Cellule("type", largeur=14),
                                Cellule("ecart", poids=3))),
        separateur(),
    ]

    items = _items_comparaison(comparaison)
    pied_forme = _pied_comparaison(gabarit, Pagination(1, 0, 1, 0, 0),
                                   len(items))
    chrome = hauteur(tete) + hauteur(pied_forme)
    page = paginer(gabarit, chrome=chrome, cout=1, total=len(items),
                   page=vue.page)
    if page is None:
        return trop_court(gabarit, chrome + 1)

    corps = [_rangee_liste(gabarit, (Cellule(cote, largeur=10),
                                     Cellule(identifiant, poids=5,
                                             chemin=True),
                                     Cellule(type_, largeur=14),
                                     Cellule(ecart, poids=3)))
             for cote, identifiant, type_, ecart in items[page.debut:page.fin]]
    return tete + corps + _pied_comparaison(gabarit, page, len(items))


def _rangee_cote(gabarit: Gabarit, nom: str, fiche: Fiche) -> Bloc:
    """Un cote, et son ECRAN. Le triplet y figure des deux cotes.

    `comparer` garantit qu'ils sont egaux, donc la repetition ne dit rien de
    neuf — elle dit qu'on l'a verifie. Une rangee qui ne portait que
    l'empreinte laissait le cote droit sans identite nulle part sur l'ecran,
    et c'est ce qui rendait invisible une comparaison de deux ecrans sans
    rapport.
    """
    return rangee(gabarit, (
        Cellule(nom, largeur=7),
        Cellule(fiche.clef.empreinte, poids=3),
        Cellule(_ecran_du(fiche), poids=4),
        Cellule(fiche.rayon, poids=2),
        Cellule(_compte_champs(fiche), poids=1, droite=True),
        Cellule(_fenetres(fiche), poids=2)))


def _phrase_fenetres(comparaison: Comparaison) -> str:
    """Ce que les identifiants disent des fenetres. Un fait, pas une deduction."""
    gauche = _fenetres(comparaison.gauche)
    droite = _fenetres(comparaison.droite)
    if comparaison.fenetres_disjointes:
        return (f"Leurs identifiants ne citent pas les memes fenetres : "
                f"{gauche} contre {droite}.")
    return (f"Fenetres citees : {gauche} a gauche, {droite} a droite.")


def _items_comparaison(comparaison: Comparaison
                       ) -> tuple[tuple[str, str, str, str], ...]:
    """Les lignes du tableau : (cote, identifiant, type, ecart).

    Le COTE est repete sur chaque ligne, la ou la maquette ne le posait qu'en
    tete de groupe. Dans une vue paginee, un groupe coupe entre deux pages
    laisserait une page entiere d'identifiants sans dire de quel cote ils
    sont : la lecture reste plausible, et elle est fausse une page sur deux.
    """
    par_id: dict[str, list[str]] = {}
    for ecart in comparaison.ecarts:
        par_id.setdefault(ecart.id, []).append(ecart.attribut)

    types_gauche = {c.id: c.type for c in comparaison.gauche.variante.champs}
    types_droite = {c.id: c.type for c in comparaison.droite.variante.champs}

    items = [("commun", identifiant, types_gauche.get(identifiant, ""),
              ", ".join(par_id[identifiant]))
             for identifiant in comparaison.communs if identifiant in par_id]
    items += [("gauche", identifiant, types_gauche.get(identifiant, ""), "")
              for identifiant in comparaison.seuls_a_gauche]
    items += [("droite", identifiant, types_droite.get(identifiant, ""), "")
              for identifiant in comparaison.seuls_a_droite]
    return tuple(items)


def _pied_comparaison(gabarit: Gabarit, page: Pagination,
                      total: int) -> list[Bloc]:
    return [
        separateur(),
        texte(gabarit, f"lignes {page.debut + 1}-{page.fin} sur {total}  —  "
                       f"page {page.page + 1}/{page.pages}   "
                       f"(« commun » : meme identifiant, attribut different)"),
        *commandes(gabarit, ("+", "-", "g", "h", "0")),
    ]


#: Combien de lignes coute une trouvaille de champ. Trois, comme la maquette :
#: l'identifiant, ce qu'il affiche, et d'ou il vient.
COUT_TROUVAILLE = 3


def vue_recherche(trouvailles: Sequence[Trouvaille], total: int,
                  critere: Critere, variantes_relues: int, vue: Vue,
                  gabarit: Gabarit) -> list[Bloc]:
    """Les champs qui apparient, et les deux colonnes que le classeur attend.

    `total` est rendu a part de `len(trouvailles)` : une liste tronquee dont on
    afficherait la longueur dirait « 500 trouvees » sur 1200, et ce compte-la
    se recopie dans une decision.

    `variantes_relues` est le nombre de variantes REELLEMENT parcourues, que
    l'appelant tire de `parcourues()`. Ce n'est pas la taille du rayon : celle
    -la ignore `a_decider`, que `filtrer` applique pourtant, et « 2 trouvee(s)
    sur 6 variante(s) relues » se lisait « le motif est rare » la ou la mesure
    vraie etait « 2 sur 2, il est partout ». Deux comptes qui ne comptent pas
    la meme chose dans la meme phrase.
    """
    if gabarit.trop_etroit:
        return trop_etroit(gabarit)
    if critere.portee != CHAMP:
        # Aucun chemin de la boucle n'y mene aujourd'hui — seul `//` pose
        # l'ecran RECHERCHE, et il force la portee. Mais `premiere.champ`
        # vaudrait `None` en portee ECRAN et le pied leverait un
        # `AttributeError` en plein rendu : une touche posee un jour depuis la
        # recherche l'ouvrirait. Un refus nomme coute deux lignes.
        return [
            entete(gabarit, "RECHERCHE"),
            texte(gabarit, "Cet ecran montre des CHAMPS ; le critere recu "
                           "porte sur l'identite des"),
            texte(gabarit, "ecrans. Les deux ne comptent pas la meme chose. "
                           "Tape //motif."),
            *commandes(gabarit, ("0",)),
        ]
    tete = [
        entete(gabarit, f"RECHERCHE « {critere.motif} » dans les champs",
               _mot_du_rayon(critere.rayon)),
        texte(gabarit, "cherche dans : " + ", ".join(CHERCHE_DANS_CHAMP),
              ton=ATTENUE),
    ]
    if critere.a_decider:
        # `a_decider` retire des lignes. La liste l'ecrit ; la recherche ne
        # l'ecrivait nulle part, et un filtre qui retire des lignes sans le
        # dire est ce que la docstring de `Critere` appelle le reglage le plus
        # dangereux possible.
        tete.append(texte(gabarit, "filtre : a decider seulement — ce qui est "
                                   "deja au cure n'est pas parcouru"))
    tete.append(separateur())
    pied_forme = _pied_recherche(gabarit, len(trouvailles), total,
                                 variantes_relues,
                                 trouvailles[0] if trouvailles else None,
                                 Pagination(1, 0, 1, 0, 0))

    chrome = hauteur(tete) + hauteur(pied_forme)
    page = paginer(gabarit, chrome=chrome, cout=COUT_TROUVAILLE,
                   total=len(trouvailles), page=vue.page)
    if page is None:
        return trop_court(gabarit, chrome + COUT_TROUVAILLE)

    corps: list[Bloc] = []
    for rang in range(page.debut, page.fin):
        trouvaille = trouvailles[rang]
        champ = trouvaille.champ
        corps.append(rangee(gabarit, (
            Cellule(str(rang + 1), largeur=_LARGEUR_RANG, droite=True),
            Cellule(champ.id, poids=5, chemin=True),
            Cellule(champ.type, largeur=14),
            Cellule(_modifiable(champ), largeur=4))))
        corps.append(rangee(gabarit, (
            Cellule("", largeur=_LARGEUR_RANG),
            Cellule(f"texte « {champ.texte} »", poids=1),
            Cellule(f"infobulle « {champ.infobulle} »", poids=1))))
        corps.append(rangee(gabarit, (
            Cellule("", largeur=_LARGEUR_RANG),
            Cellule("ecran", largeur=6),
            Cellule(_ecran_du(trouvaille.fiche), poids=4),
            Cellule(trouvaille.fiche.rayon, poids=2),
            Cellule(trouvaille.fiche.clef.empreinte, poids=3))))

    # La paire « ecran / cible » du pied cite la PREMIERE ligne de la page
    # affichee, pas la premiere de la recherche : sur la page 3, recopier une
    # cible qui n'est plus a l'ecran donnerait un couple juste et invisible.
    return tete + corps + _pied_recherche(
        gabarit, len(trouvailles), total, variantes_relues,
        trouvailles[page.debut] if trouvailles else None, page)


def _mot_du_rayon(rayon: str) -> str:
    return {QUARANTAINE: "quarantaine", CURE: "cure",
            TOUS: "quarantaine + cure"}[rayon]


def _pied_recherche(gabarit: Gabarit, retenues: int, total: int,
                    variantes_relues: int, premiere: Trouvaille | None,
                    page: Pagination) -> list[Bloc]:
    blocs = [separateur()]
    if retenues < total:
        blocs.append(texte(gabarit, f"{total} trouvee(s) sur "
                                    f"{variantes_relues} variante(s) relues ; "
                                    f"{retenues} montrees.", ton=ALERTE))
    else:
        blocs.append(texte(gabarit, f"{total} trouvee(s) sur "
                                    f"{variantes_relues} variante(s) relues."))
    blocs.append(texte(gabarit, f"page {page.page + 1}/{page.pages}"))
    if premiere is not None:
        blocs.append(texte(gabarit,
                           "Les deux colonnes que le classeur attend :"))
        blocs.append(rangee(gabarit, (
            Cellule("", largeur=6), Cellule("ecran", largeur=6),
            Cellule(_ecran_du(premiere.fiche)))))
        blocs.append(rangee(gabarit, (
            Cellule("", largeur=6), Cellule("cible", largeur=6),
            Cellule(premiere.champ.id, chemin=True))))
    blocs += commandes(gabarit, ("<n>", "+", "-", "0"))
    return blocs


def vue_rapports(chemins: Sequence[Path], tailles: Sequence[int | None],
                 vue: Vue, gabarit: Gabarit) -> list[Bloc]:
    """Les comptes rendus conserves. Nom et taille, jamais un etat re-devine.

    La maquette annoncait un etat par ligne — « interrompue », « terminee ».
    Il faudrait le relire dans la prose du compte rendu : un etat faux sur
    cette liste enverrait quelqu'un ouvrir le mauvais fichier en croyant
    savoir ce qu'il contient. Le nom porte l'horodatage et la trace, ce qui
    suffit a choisir ; l'etat se lit dans le compte rendu, qui fait foi.
    """
    if gabarit.trop_etroit:
        return trop_etroit(gabarit)
    tete = [entete(gabarit, "Comptes rendus d'exploration conserves")]
    pied_forme = _pied_rapports(gabarit, Pagination(1, 0, 1, 0, 0))
    chrome = hauteur(tete) + hauteur(pied_forme)
    page = paginer(gabarit, chrome=chrome, cout=1, total=len(chemins),
                   page=vue.page)
    if page is None:
        return trop_court(gabarit, chrome + 1)

    corps = [rangee(gabarit, (
        Cellule(str(rang + 1), largeur=_LARGEUR_RANG, droite=True),
        Cellule(chemins[rang].name, poids=5),
        Cellule(f"{tailles[rang]} o" if tailles[rang] is not None
                else f"{INCONNU} o", largeur=10, droite=True)), marge=4)
        for rang in range(page.debut, page.fin)]
    if not chemins:
        corps = [texte(gabarit, "Aucun. Une cartographie en conserve un a "
                                "chaque passage.", marge=4)]
    return tete + corps + _pied_rapports(gabarit, page)


def _pied_rapports(gabarit: Gabarit, page: Pagination) -> list[Bloc]:
    return [
        separateur(),
        texte(gabarit, "Le compte rendu est le SEUL endroit ou vivent la "
                       "partition des gestes,"),
        texte(gabarit, "les branches, les reprises et les visites non "
                       "atteintes."),
        vide(),
        texte(gabarit, f"page {page.page + 1}/{page.pages}"),
        *commandes(gabarit, ("<n>", "+", "-", "0")),
    ]


#: Les commandes, ecrites UNE fois : (clef, libelle court, ce que ca fait).
#:
#: **Les pieds d'ecran sont COMPOSES a partir de cette table**, par
#: `commandes()`, et jamais ecrits a la main. C'est ce qui rend impossible le
#: defaut que la maquette de ce lot portait : un pied qui annonce « x exporter »
#: pendant que la boucle ignore `x`. Un texte qui affirme plus que ce que le
#: code fait est un defaut a part entiere, et celui-la se decouvre en tapant la
#: touche.
COMMANDES = (
    ("<n>", "ouvrir",
     "ouvrir la variante n depuis une liste, le champ n depuis une fiche"),
    ("/motif", "filtrer les ecrans",
     "filtrer sur transaction, programme, dynpro, empreinte, titre"),
    ("//motif", "chercher un champ",
     "chercher dans id, nom, texte, infobulle, type, soustype"),
    ("f", "rayon", "quarantaine, cure, puis les deux"),
    ("a", "reste a decider",
     "n'afficher que ce qui n'est pas deja au cure. Jamais actif par defaut"),
    ("m", "marquer", "marquer pour comparer. « m 3 » depuis une liste"),
    ("d", "comparer", "comparer les deux marquees. REFUSE une esquisse"),
    ("p", "PROMOUVOIR", "depuis la fiche OUVERTE seulement"),
    ("g", "ouvrir la gauche", "depuis une comparaison"),
    ("h", "ouvrir la droite", "depuis une comparaison"),
    ("r", "rapports", "les comptes rendus d'exploration conserves"),
    ("L", "relire", "relire le catalogue sur le disque"),
    ("+", "page suivante", "la page suivante de la vue courante"),
    ("-", "page precedente", "la page precedente"),
    ("?", "aide", "cette aide"),
    ("0", "retour",
     "revenir d'un cran ; depuis l'accueil, sortir du navigateur"),
)

#: Ce qui separe deux commandes sur une ligne de pied.
SEPARATION = "   "


def commandes(gabarit: Gabarit, clefs: Sequence[str], *,
              marge: int = 2) -> list[Bloc]:
    """Le pied d'un ecran, compose depuis `COMMANDES`.

    Une clef inconnue leve : c'est une garantie sur le RENDU — aucun pied ne
    peut afficher une touche absente de la table. Elle ne dit rien de la
    boucle : c'est `test_chaque_commande_annoncee_a_un_EFFET` qui joue chaque
    touche a travers `naviguer` et exige qu'elle fasse quelque chose.

    Le repliage tient compte de la largeur du GABARIT — a quarante colonnes le
    meme pied prend trois lignes au lieu de deux, et c'est le chrome qui
    change, donc la pagination avec lui.
    """
    courts = {clef: court for clef, court, _ in COMMANDES}
    morceaux = [f"{clef} {courts[clef]}" for clef in clefs]
    largeur = max(gabarit.colonnes - marge, 1)

    lignes: list[str] = []
    courante = ""
    for morceau in morceaux:
        candidat = f"{courante}{SEPARATION}{morceau}" if courante else morceau
        if courante and len(candidat) > largeur:
            lignes.append(courante)
            courante = morceau
        else:
            courante = candidat
    if courante:
        lignes.append(courante)
    return [texte(gabarit, ligne, marge=marge) for ligne in lignes]


def vue_aide(gabarit: Gabarit) -> list[Bloc]:
    """L'aide. Elle aussi refuse plutot que de lever.

    Elle tenait plus longtemps que les autres — jusqu'a quinze colonnes — et
    tombait au meme endroit, sur un `ValueError` de `colonnes()`.
    """
    if gabarit.trop_etroit:
        return trop_etroit(gabarit)
    blocs = [entete(gabarit, "Navigateur de catalogue — les commandes")]
    blocs += [rangee(gabarit, (Cellule(clef, largeur=9),
                               Cellule(quoi)), marge=4)
              for clef, _, quoi in COMMANDES]
    blocs += [
        vide(),
        texte(gabarit, "La promotion n'existe que dans une fiche OUVERTE. Un "
                       "mot tape ne peut"),
        texte(gabarit, "pas certifier des ecrans que personne n'a lus."),
        *commandes(gabarit, ("0",)),
    ]
    return tenir(blocs, gabarit)


# ---------------------------------------------------------------------------
# La boucle
# ---------------------------------------------------------------------------

def naviguer(console: Console, depot: Depot, *,
             gabarit: Callable[[], Gabarit], peintre: Peintre) -> str:
    """La boucle. Rend un verdict de `VERDICTS` ; une fin de flux rend CONTINUER.

    Meme forme que `menu.parcourir` : on reaffiche tout a chaque tour et on lit
    une ligne. Aucun repositionnement, aucun effacement, aucune fleche. C'est ce
    qui marche dans `cmd`, dans PowerShell, a travers RDP et dans une sortie
    redirigee — et c'est ce qui laisse un test lui jouer une session complete
    sans terminal.

    `gabarit` est une FONCTION, rappelee a chaque tour : Windows n'a pas de
    `SIGWINCH`, et une reconnexion RDP a une autre resolution redimensionne la
    console de l'hote en pleine session. Un gabarit fige continuerait d'ecrire
    118 colonnes dans une fenetre redevenue 80.
    """
    inventaire = charger(depot)
    vue = Vue()
    comparaison: Comparaison | None = None

    while True:
        forme = gabarit()
        fiches, total = _fiches_de(inventaire, vue)
        for bloc in _peindre(vue, inventaire, fiches, total, comparaison,
                             depot, forme):
            for ligne in peintre.peindre(bloc, forme):
                console.ecrire(ligne)

        try:
            saisie = console.lire().strip()
        except (EOFError, KeyboardInterrupt):
            console.ecrire("\n  Fin de session.")
            return CONTINUER

        if saisie.lower() in ("0", "q") and vue.ecran == ACCUEIL:
            return CONTINUER

        vue, comparaison, inventaire = _repondre(
            console, depot, vue, inventaire, fiches, comparaison, forme,
            peintre, saisie)


def _fiches_de(inventaire: Inventaire,
               vue: Vue) -> tuple[tuple[Fiche, ...], int]:
    """(les fiches que la liste numerote, le TOTAL qui leur correspond).

    **La limite vaut la taille de l'inventaire**, donc la PAGINATION est la
    seule troncature. Avec le defaut de `filtrer` — cinq cents — un inventaire
    de six cents variantes rendait une liste de cinq cents dont l'ecran
    affichait la longueur aux deux places : « 500 variante(s) » puis
    « 24 affichee(s) sur 500 ». Les cent dernieres n'etaient ni comptees, ni
    nommees, ni joignables par `<n>`, `m <n>` ou `p`, et rien ne le disait.

    Le total est tout de meme rendu et affiche : si la limite redevient
    inferieure au total un jour, l'ecart s'ECRIT au lieu d'etre suppose absent.
    """
    trouvailles, total = filtrer(inventaire,
                                 replace(vue.critere, portee=ECRAN),
                                 limite=max(len(inventaire.fiches), 1))
    return tuple(t.fiche for t in trouvailles), total


def _peindre(vue: Vue, inventaire: Inventaire, fiches: Sequence[Fiche],
             total: int, comparaison: Comparaison | None, depot: Depot,
             forme: Gabarit) -> list[Bloc]:
    """Aiguille vers la vue courante. Aucun effet, et DEUX lectures de disque.

    Les deux sont le meme glob : `rapports(depot)` liste un dossier, pour
    l'ecran des comptes rendus et pour la ligne de l'accueil qui les compte.
    C'est la seule matiere qui ne soit pas dans l'inventaire. La docstring
    n'en nommait qu'une, et le second appel — celui de l'accueil — est
    pourtant execute a chaque affichage de l'accueil.
    """
    if vue.ecran == AIDE:
        return vue_aide(forme)
    if vue.ecran == RAPPORTS:
        chemins = rapports(depot)
        return vue_rapports(chemins, [_taille(c) for c in chemins], vue, forme)
    if vue.ecran == COMPARAISON and comparaison is not None:
        return vue_comparaison(comparaison, vue, forme)
    if vue.ecran == RECHERCHE:
        trouvailles, trouvees = filtrer(inventaire, vue.critere)
        return vue_recherche(trouvailles, trouvees, vue.critere,
                             len(parcourues(inventaire, vue.critere)), vue,
                             forme)
    if vue.ecran == DETAIL and vue.ouverte is not None:
        return vue_champ(vue.ouverte, vue.ouverte.variante.champs[vue.champ],
                         forme)
    if vue.ecran == FICHE and vue.ouverte is not None:
        return vue_fiche(vue, vue.ouverte, inventaire.voisines(vue.ouverte),
                         forme)
    if vue.ecran == LISTE:
        return vue_liste(vue, fiches, total, forme)
    return vue_accueil(inventaire, forme, racine=depot.racine,
                       comptes_rendus=len(rapports(depot)))


def _taille(chemin: Path) -> int | None:
    """La taille du fichier, ou `None` s'il a disparu entre le glob et ici.

    `None` et pas zero. Un compte rendu de quatre kilo-octets affiche « 0 o »
    se lit « il est vide » : personne ne l'ouvre, et c'est un resultat
    plausible et faux produit par un repli. L'ecran ecrit « ? », qui ne dit
    que ce qu'on sait.
    """
    try:
        return chemin.stat().st_size
    except OSError:
        return None


#: Les commandes d'une seule lettre. Reconnues EXACTEMENT, et pas par prefixe :
#: un `saisie.startswith("p")` ferait promouvoir sur « page », et un
#: `startswith("m")` marquerait sur « motif ». Le seul argument accepte est un
#: numero, derriere `m` et `p`.
LETTRES = frozenset("0q?lrfad+-mpgh")


def _decouper(saisie: str) -> tuple[str, str]:
    """(commande, argument). Rend ("", saisie) quand rien ne reconnait.

    Les deux formes de recherche sont traitees avant, par l'appelant : `/` et
    `//` collent leur motif a la commande, et les separer ici couperait un
    motif qui commence par un espace.
    """
    bas = saisie.strip().lower()
    if not bas:
        return "", ""
    if bas in LETTRES:
        # « 0 » est un chiffre ET la sortie de tous les ecrans. Le tester en
        # premier : sans cela il ouvrirait « la variante numero zero », et
        # l'ecran repondrait qu'elle n'existe pas a quelqu'un qui voulait
        # remonter d'un cran.
        return bas, ""
    if _est_un_nombre(bas):
        return "<n>", bas
    lettre, reste = bas[0], bas[1:].strip()
    if lettre not in LETTRES:
        return "", saisie
    if lettre in ("m", "p") and _est_un_nombre(reste):
        return lettre, reste
    return "", saisie


def _est_un_nombre(mot: str) -> bool:
    """Des chiffres ASCII, et rien d'autre. `int()` doit pouvoir l'avaler.

    `str.isdigit()` est VRAI pour des caracteres que `int()` refuse — `²`,
    `³`, `¹`, les chiffres cercles. Or `²` est une touche DEDIEE du clavier
    AZERTY francais, en haut a gauche, contre la touche `&`/1 : c'est le
    clavier de la machine cible. Mesure : `²`, `m²` et `p²` faisaient lever
    `ValueError: invalid literal for int() with base 10: '²'` a travers
    `naviguer`, `parcourir` et `_console` — une trace de pile Python a la
    place du catalogue, pour une faute de frappe a cote de la touche 1, sur le
    poste ou l'on vient de piloter SAP.

    Tout ce que cette fonction refuse retombe sur « n'est pas une commande
    d'ici », qui est deja ecrite et deja testee.
    """
    return bool(mot) and mot.isascii() and mot.isdigit()


def _repondre(console: Console, depot: Depot, vue: Vue,
              inventaire: Inventaire, fiches: Sequence[Fiche],
              comparaison: Comparaison | None, forme: Gabarit,
              peintre: Peintre, saisie: str,
              ) -> tuple[Vue, Comparaison | None, Inventaire]:
    """Un tour de dialogue. Rend (vue, comparaison, inventaire).

    Les refus s'ecrivent ici et pas dans une vue : ils repondent a ce qui vient
    d'etre tape, ils se lisent au-dessus du prochain affichage, et une vue qui
    les porterait devrait garder un etat de message — donc pouvoir l'oublier.
    """
    if saisie.startswith("//"):
        return (replace(vue, ecran=RECHERCHE, page=0,
                        critere=replace(vue.critere, portee=CHAMP,
                                        motif=saisie[2:].strip())),
                comparaison, inventaire)
    if saisie.startswith("/"):
        return (replace(vue, ecran=LISTE, page=0,
                        critere=replace(vue.critere, portee=ECRAN,
                                        motif=saisie[1:].strip())),
                comparaison, inventaire)

    commande, argument = _decouper(saisie)

    if commande == "" and not saisie.strip():
        if vue.ecran == ACCUEIL:
            return replace(vue, ecran=LISTE, page=0), comparaison, inventaire
        return vue, comparaison, inventaire
    if commande == "":
        console.ecrire(f"\n  « {saisie} » n'est pas une commande d'ici. Tape ? "
                       f"pour la liste.")
        return vue, comparaison, inventaire

    if commande in ("0", "q"):
        return _remonter(vue), comparaison, inventaire
    if commande == "?":
        return replace(vue, ecran=AIDE, page=0), comparaison, inventaire
    if commande == "l":
        console.ecrire("\n  Catalogue relu sur le disque.")
        return _relire(console, vue, comparaison, depot)
    if commande == "r":
        return replace(vue, ecran=RAPPORTS, page=0), comparaison, inventaire
    if commande == "+":
        return replace(vue, page=vue.page + 1), comparaison, inventaire
    if commande == "-":
        return replace(vue, page=max(vue.page - 1, 0)), comparaison, inventaire
    if commande == "f":
        return _changer_de_rayon(vue), comparaison, inventaire
    if commande == "a":
        return (replace(vue, ecran=LISTE, page=0,
                        critere=replace(vue.critere,
                                        a_decider=not vue.critere.a_decider)),
                comparaison, inventaire)
    if commande == "m":
        return (_marquer(console, vue, inventaire, fiches, argument),
                comparaison, inventaire)
    if commande == "d":
        return _comparer(console, vue, comparaison, inventaire)
    if commande == "p":
        vue, promue = _promouvoir(console, depot, vue, inventaire, fiches,
                                  argument)
        if not promue:
            return vue, comparaison, inventaire
        return _relire(console, vue, comparaison, depot)
    if commande in ("g", "h"):
        if vue.ecran != COMPARAISON or comparaison is None:
            console.ecrire("\n  « g » et « h » n'ouvrent un cote que depuis "
                           "une comparaison.")
            return vue, comparaison, inventaire
        cote = comparaison.gauche if commande == "g" else comparaison.droite
        return (replace(vue, ecran=FICHE, ouverte=cote, page=0), comparaison,
                inventaire)

    # commande == "<n>"
    numero = int(argument)
    if vue.ecran == RAPPORTS:
        _afficher_rapport(console, peintre, forme, rapports(depot), numero)
        return vue, comparaison, inventaire
    return (_ouvrir(console, vue, fiches, inventaire, numero), comparaison,
            inventaire)


def _afficher_rapport(console: Console, peintre: Peintre, forme: Gabarit,
                      chemins: Sequence[Path], numero: int) -> None:
    """Le compte rendu, VERBATIM, et l'avertissement qui va avec.

    Le texte n'est pas recoupe a la largeur mesuree : c'est celui de
    `rapport.rendre`, mesure a 375 caracteres sur sa plus longue ligne, et le
    couper ferait perdre a chaque ligne trop longue exactement ce qu'on vient
    y chercher — un identifiant, un motif de branche. Une ligne qui se replie
    reste lisible ; une ligne coupee, non, et rien ne dit ce qui manque. Le
    prix est ECRIT a l'ecran juste avant.
    """
    if not 1 <= numero <= len(chemins):
        console.ecrire(f"\n  « {numero} » n'est pas dans cette liste.")
        return
    chemin = chemins[numero - 1]
    for bloc in (vide(),
                 texte(forme, str(chemin)),
                 texte(forme, "Texte conserve, verbatim. Les lignes plus "
                              "longues que la fenetre s'y", ton=ATTENUE),
                 texte(forme, "replieront : les couper ferait perdre "
                              "justement ce qu'on y cherche.", ton=ATTENUE),
                 separateur()):
        for ligne in peintre.peindre(bloc, forme):
            console.ecrire(ligne)
    try:
        contenu = chemin.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as erreur:
        # `UnicodeDecodeError` est un `ValueError`, pas un `OSError` : c'est la
        # meme erreur d'inventaire de familles que celle corrigee dans
        # `Depot._lire_fichier`. `rapports()` globe `*.txt` dans un dossier
        # ouvert a tous — un compte rendu recopie ou retouche au Bloc-notes en
        # ANSI n'est pas de l'UTF-8 — et sans cette famille la levee sortait de
        # `naviguer`, de `parcourir`, jusqu'a la trace de pile. On REFUSE en
        # nommant plutot que de lire avec `errors="replace"` : l'ecran promet
        # « verbatim », et un texte altere tiendrait moins la promesse qu'un
        # refus.
        console.ecrire(f"\n  Illisible : {type(erreur).__name__} : {erreur}")
        return
    try:
        for ligne in contenu.splitlines():
            console.ecrire(ligne)
    except UnicodeEncodeError:
        # Symetrique, cote ECRITURE : un compte rendu qui porte un caractere
        # hors cp1252 — un motif de branche venu d'un SAP non francais, un nom
        # de trace pris sur un partage — tue la console sur une sortie
        # redirigee en cp1252, qui est le cas Windows FR. L'ecran de relecture
        # est le dernier endroit ou l'on veut perdre la session : le chemin est
        # deja affiche deux lignes plus haut, on y renvoie.
        console.ecrire("\n  Ce compte rendu porte un caractere que ce "
                       "terminal ne sait pas ecrire.")
        console.ecrire(f"  Ouvre-le dans un editeur : {chemin}")


def _relire(console: Console, vue: Vue, comparaison: Comparaison | None,
            depot: Depot) -> tuple[Vue, Comparaison | None, Inventaire]:
    """Relit le disque, PUIS re-resout ce que la vue portait.

    `L` ecrivait « Catalogue relu sur le disque » et remplacait l'inventaire,
    mais `vue.ouverte` et `vue.marques` continuaient de porter les `Fiche`
    capturees AVANT la relecture, et `_peindre` rend la fiche depuis
    `vue.ouverte`. Mesure : on modifie le YAML a cote, on tape `L` sur la fiche
    ouverte ; la console annonce la relecture, l'inventaire recharge porte bien
    la nouvelle valeur, et l'ecran continue d'afficher l'ancien titre et les
    anciens champs. Le message affirmait plus que ce que le code faisait.

    Et la ceremonie s'en trouvait videe : `p` promeut par
    `depot.promouvoir(cible.clef)`, qui relit le DISQUE. On certifiait « TU as
    relu cet ecran » sur un affichage qui n'etait plus ce qui allait etre
    promu. Meme chose pour les marques, qui alimentent `comparer` avec des
    objets perimes — memes clefs, champs anciens.

    Ce qui a DISPARU du disque est retire, et l'ecran le dit : une fiche qu'on
    garderait a l'affichage serait un ecran de catalogue sans fichier derriere.
    """
    inventaire = charger(depot)
    par_clef = {(f.clef, f.rayon): f for f in inventaire.fiches}

    perdues: list[Fiche] = []

    def reprendre(fiche: Fiche | None) -> Fiche | None:
        if fiche is None:
            return None
        fraiche = par_clef.get((fiche.clef, fiche.rayon))
        if fraiche is None:
            perdues.append(fiche)
        return fraiche

    ouverte = reprendre(vue.ouverte)
    marques = tuple(f for f in (reprendre(m) for m in vue.marques)
                    if f is not None)

    for fiche in perdues:
        console.ecrire(f"  {fiche.clef.empreinte} n'est plus dans le "
                       f"catalogue relu : elle est retiree de l'ecran.")

    vue = replace(vue, ouverte=ouverte, marques=marques)
    if ouverte is None and vue.ecran in (FICHE, DETAIL):
        vue = replace(vue, ecran=LISTE, champ=-1, page=0)
    # La comparaison affichee porte les DEUX fiches d'avant. La garder apres
    # une relecture ferait lire un ecart mesure sur des donnees que le disque
    # ne porte plus ; on la jette, et on quitte son ecran plutot que de laisser
    # `_peindre` retomber sur l'accueil sans rien dire.
    if comparaison is not None and vue.ecran == COMPARAISON:
        console.ecrire("  La comparaison portait sur les donnees d'avant : "
                       "remarque les deux fiches et retape « d ».")
        vue = replace(vue, ecran=LISTE, page=0)
    return vue, None, inventaire


def _remonter(vue: Vue) -> Vue:
    """`0` remonte d'un cran, comme dans `menu.parcourir`.

    **Quitter la RECHERCHE vide le motif**, et c'est une correction. Le motif
    de la recherche porte sur les CHAMPS ; la liste le reinterprete en portee
    ECRAN. Chercher « werks » dans les champs puis remonter donnait donc une
    liste filtree sur l'IDENTITE d'ecran par « werks » — vide le plus souvent.
    L'en-tete le disait (« filtre : werks »), donc ce n'etait pas silencieux ;
    c'etait surprenant, et la surprise porte sur les numeros que `<n>`,
    `m <n>` et `p` designent.
    """
    if vue.ecran == DETAIL:
        return replace(vue, ecran=FICHE, champ=-1, page=0)
    if vue.ecran == RECHERCHE:
        return replace(vue, ecran=LISTE, ouverte=None, champ=-1, page=0,
                       critere=replace(vue.critere, motif="", portee=ECRAN))
    if vue.ecran in (FICHE, COMPARAISON, RAPPORTS, AIDE):
        return replace(vue, ecran=LISTE, ouverte=None, champ=-1, page=0)
    return replace(vue, ecran=ACCUEIL, page=0)


#: L'ordre dans lequel `f` fait tourner les rayons.
CYCLE_RAYONS = (QUARANTAINE, CURE, TOUS)


def _changer_de_rayon(vue: Vue) -> Vue:
    suivant = CYCLE_RAYONS[(CYCLE_RAYONS.index(vue.critere.rayon) + 1)
                           % len(CYCLE_RAYONS)]
    return replace(vue, ecran=LISTE, page=0,
                   critere=replace(vue.critere, rayon=suivant))


def _numerotees(vue: Vue, inventaire: Inventaire,
                fiches: Sequence[Fiche]) -> tuple[Fiche, ...] | None:
    """Les fiches que l'ECRAN COURANT a numerotees, ou `None` s'il n'en a pas.

    `m <n>` indexait toujours la liste, que `_fiches_de` recalcule en forcant
    `portee=ECRAN`. Sur l'ecran RECHERCHE, le motif est un motif de CHAMP : la
    liste indexee n'etait pas celle que l'ecran avait numerotee. Mesure :
    `//ih06` affiche une seule trouvaille, `wnd[0]/usr/ctxtIH06X` de
    IW39::SAPLIW39::1000 ; taper `m 1` en la regardant marquait IH06, une
    variante ABSENTE de l'ecran, sans un mot. La marque alimente ensuite `d`,
    puis `g`/`h` ouvrent une fiche que personne n'a choisie.

    Sur FICHE et DETAIL, les numeros affiches sont des CHAMPS : il n'y a pas
    de fiche a designer par un numero, et `None` le dit.

    C'est la meme resolution que `_ouvrir` fait deja pour `<n>` ; elle est
    ecrite une fois et les deux la lisent.
    """
    if vue.ecran in (FICHE, DETAIL):
        return None
    if vue.ecran == RECHERCHE:
        trouvailles, _ = filtrer(inventaire, vue.critere)
        return tuple(t.fiche for t in trouvailles)
    return tuple(fiches)


def _marquer(console: Console, vue: Vue, inventaire: Inventaire,
             fiches: Sequence[Fiche], argument: str) -> Vue:
    """`m` marque la fiche ouverte, `m <n>` celle que L'ECRAN a numerotee.

    Marquer n'est pas decider : la marque ne sert qu'a la comparaison, elle ne
    touche aucun fichier et elle disparait a la sortie du navigateur. Mais
    elle alimente `d`, puis `g`/`h` : marquer la mauvaise ligne ouvre une
    fiche que personne n'a choisie, et l'ecran n'en dit rien.
    """
    if argument:
        numerotees = _numerotees(vue, inventaire, fiches)
        if numerotees is None:
            console.ecrire("\n  Ici les numeros sont des champs, pas des "
                           "variantes. « m » seul marque la fiche ouverte.")
            return vue
        if not 1 <= int(argument) <= len(numerotees):
            console.ecrire(f"\n  « {argument} » n'est pas un numero de cette "
                           f"liste ({len(numerotees)} ligne(s)).")
            return vue
        cible = numerotees[int(argument) - 1]
    elif vue.ouverte is not None:
        cible = vue.ouverte
    else:
        console.ecrire("\n  Rien a marquer ici : donne un numero, « m 3 ».")
        return vue

    if cible in vue.marques:
        marques = tuple(f for f in vue.marques if f != cible)
    else:
        marques = (*vue.marques, cible)[-2:]
    return replace(vue, marques=marques)


def _comparer(console: Console, vue: Vue, comparaison: Comparaison | None,
              inventaire: Inventaire,
              ) -> tuple[Vue, Comparaison | None, Inventaire]:
    """`d` — et le refus qui protege la mesure de l'heuristique.

    Deux marquees exactement : comparer trois variantes n'a pas de sens, et en
    comparer une a elle-meme ne mesure rien. Le refus d'une esquisse vient du
    modele, pas d'ici — `comparer` le leve, et ce module ne fait que l'ecrire.
    """
    if len(vue.marques) != 2:
        console.ecrire(f"\n  Il en faut DEUX marquees ; il y en a "
                       f"{len(vue.marques)}. « m <n> » depuis la liste.")
        return vue, comparaison, inventaire
    try:
        faite = comparer(*vue.marques)
    except ComparaisonRefusee as refus:
        console.ecrire("")
        console.ecrire(f"  Refuse. {refus}")
        return vue, comparaison, inventaire
    return replace(vue, ecran=COMPARAISON, page=0), faite, inventaire


def _ouvrir(console: Console, vue: Vue, fiches: Sequence[Fiche],
            inventaire: Inventaire, numero: int) -> Vue:
    """`<n>` ouvre une variante depuis la liste, un champ depuis la fiche."""
    if vue.ecran in (FICHE, DETAIL) and vue.ouverte is not None:
        champs = vue.ouverte.variante.champs
        if not 1 <= numero <= len(champs):
            console.ecrire(f"\n  Cette fiche porte {len(champs)} champ(s) ; "
                           f"« {numero} » n'en est pas un.")
            return vue
        return replace(vue, ecran=DETAIL, champ=numero - 1, page=0)

    if vue.ecran == RECHERCHE:
        trouvailles, _ = filtrer(inventaire, vue.critere)
        if not 1 <= numero <= len(trouvailles):
            console.ecrire(f"\n  « {numero} » n'est pas dans cette liste.")
            return vue
        return replace(vue, ecran=FICHE, ouverte=trouvailles[numero - 1].fiche,
                       page=0)

    if not 1 <= numero <= len(fiches):
        console.ecrire(f"\n  « {numero} » n'est pas dans cette liste "
                       f"({len(fiches)} ligne(s)).")
        return vue
    return replace(vue, ecran=FICHE, ouverte=fiches[numero - 1], page=0)


def _promouvoir(console: Console, depot: Depot, vue: Vue,
                inventaire: Inventaire, fiches: Sequence[Fiche],
                argument: str) -> tuple[Vue, bool]:
    """`p` — la ceremonie, et la garde qui l'empeche de devenir un lot.

    **L'import de `confirmer` est LOCAL, et il doit le rester.**
    `Environnement.capacites` vit dans `ecrans.py`, qui construit le menu d'ou
    l'on arrive ici : un `from .ecrans import confirmer` en tete de ce module
    donnerait `ImportError: partially initialized module` des que `ecrans`
    importerait le navigateur, et emporterait toute la console. Le garde-fou
    AST de `test_console` ne regarde que l'appel — `confirmer(...)` — pas
    l'endroit de l'import.
    """
    from .ecrans import confirmer
    from falcon.catalogue import CatalogueInvalide

    cible = vue.ouverte
    if argument:
        # Un numero hors bornes retombait SILENCIEUSEMENT sur la fiche
        # ouverte : `p 99` depuis une fiche engageait la ceremonie sur la
        # variante COURANTE, dont l'empreinte est justement a l'ecran. Qui
        # s'est trompe de numero la tape et promeut un ecran qu'il n'avait pas
        # designe — le contraire de « un refus vaut mieux qu'une valeur
        # devinee », dans la fonction meme dont c'est le sujet. `_marquer` et
        # `_ouvrir` refusent proprement ; celle-ci le fait maintenant aussi.
        numerotees = _numerotees(vue, inventaire, fiches)
        if numerotees is None:
            console.ecrire("\n  Ici les numeros sont des champs, pas des "
                           "variantes. « p » seul promeut la fiche ouverte.")
            return vue, False
        if not 1 <= int(argument) <= len(numerotees):
            console.ecrire(f"\n  « {argument} » n'est pas un numero de cette "
                           f"liste ({len(numerotees)} ligne(s)).")
            return vue, False
        cible = numerotees[int(argument) - 1]
    if cible is None:
        console.ecrire("\n  Rien a promouvoir ici : ouvre une fiche d'abord.")
        return vue, False

    try:
        garde_de_la_promotion(vue, cible)
    except PromotionHorsFiche as refus:
        console.ecrire("")
        console.ecrire(f"  Refuse. {refus}")
        console.ecrire("  L'empreinte est a l'ecran : la taper sans avoir "
                       "rien regarde ne certifie rien.")
        return vue, False

    if cible.rayon != QUARANTAINE:
        console.ecrire("\n  Elle est deja au catalogue cure : il n'y a rien "
                       "a promouvoir.")
        return vue, False

    console.ecrire("")
    if cible.relevee:
        annonce = "Promouvoir, c'est dire que TU as relu cet ecran."
    else:
        for ligne in TEXTE_ESQUISSE:
            console.ecrire(f"  {ligne}")
        annonce = ("Promouvoir une esquisse, c'est certifier avoir lu le "
                   "FICHIER.")
    if not confirmer(console, cible.clef.empreinte, annonce=annonce,
                     quoi="son empreinte"):
        return vue, False

    try:
        chemin = depot.promouvoir(cible.clef)
    except CatalogueInvalide as erreur:
        console.ecrire(f"\n  Refuse.\n\n  {erreur}")
        return vue, False
    console.ecrire(f"\n  Promue : {chemin}")
    console.ecrire("  La capture RESTE en quarantaine — promouvoir COPIE, ne "
                   "deplace pas.")
    console.ecrire("  Elle porte desormais « Q+ ».")
    return replace(vue, ecran=LISTE, ouverte=None, page=0), True
