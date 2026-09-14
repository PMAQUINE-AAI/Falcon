"""Les deux rayons du catalogue, lus une fois, et ce qu'on peut en dire.

Le depot sait enregistrer, promouvoir et relire une variante. Il ne sait ni
chercher, ni compter, ni comparer, ni survivre a un fichier casse :
`Depot.triplets()` leve sur le premier et perd tout le reste. Ce module le fait
au-dessus, en DONNEES — aucune ligne de texte n'y est produite, c'est le
partage que `commandes/dictionnaire.py` trace deja pour lui-meme.

**Un fichier illisible est compte a part, nomme, avec son motif, et EXCLU des
totaux.** « 21 variantes » au lieu de « 22 dont une illisible » est un compte
plausible et faux ; l'avaler serait pire que de tomber.

**L'empreinte est une CLEF STOCKEE, jamais recalculee.** `Depot._variante` la
lit telle quelle dans le YAML. On ne peut donc affirmer aucune propriete
arithmetique sur elle : deux variantes d'un meme triplet ont normalement au
moins un identifiant non partage, mais un fichier fusionne a la main casse
l'invariant sans collision et sans exception. Ce module ne raisonne que sur ce
qu'il a relu.

**`comparer` REFUSE une esquisse.** Une esquisse porte les identifiants
TOUCHES, un releve les identifiants PRESENTS ; les rapprocher compare deux
choses qui ne comptent pas la meme. Mesure faite sur la quarantaine que produit
la trace de reference : `_______.yaml` porte cinq esquisses sous le triplet
vide, dont deux citent `wnd[0]` et trois `wnd[1]`, sans aucun identifiant
commun. Six paires y declencheraient, sans cette garde, le paragraphe
« signature du couple modale / porteur » — qui decrit un phenomene de RELEVES,
et n'a rien a voir. Une heuristique fausse au premier usage, sur la fixture du
depot.

**`au_cure` n'affirme aucun acte humain.** Le catalogue ne garde aucune trace
d'une promotion : la meme empreinte presente au cure est un FAIT de fichier, et
c'est ainsi qu'on l'ecrit. Et ce n'est pas un filtre par defaut : cacher des
lignes sur une inference est le reglage le plus dangereux possible pour une
file de decisions.

**Un identifiant SAP NOMME sa fenetre ; on la lit, on ne la devine pas.** Une
variante dont aucun identifiant ne porte de segment `wnd[...]` rend un tuple
VIDE, et l'affichage ecrit « ? ». `wnd[0]` par defaut serait une affirmation,
et c'est exactement celle que la modale rend dangereuse.

**Ce module ne produit pas une ligne de texte, et c'est la regle qui le tient
honnete.** Tout ce qui se lit — « 22 variante(s) », « 2 id. », « ? » — est
compose par `falcon/console/navigateur.py`, qui seul connait la largeur. Un
modele qui rendrait des chaines toutes faites deciderait de la mise en page
depuis un module qui n'a jamais mesure l'ecran.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import yaml

from falcon.noyau import Champ

from .depot import Depot
from .modele import CatalogueInvalide, ClefVariante, Variante

#: Les deux rayons, et le mot qui les designe tous les deux.
CURE = "cure"
QUARANTAINE = "quarantaine"
TOUS = "tous"

RAYONS = (QUARANTAINE, CURE)

#: Portees de recherche. `ECRAN` cherche dans l'identite d'une variante,
#: `CHAMP` dans chacun de ses champs — ce ne sont pas deux filtres sur la meme
#: matiere, et le resultat n'a pas la meme unite.
ECRAN = "ecran"
CHAMP = "champ"
PORTEES = (ECRAN, CHAMP)

#: Les attributs qu'on rapproche quand deux variantes partagent un identifiant.
#: `id` n'y est pas : c'est la clef du rapprochement, pas un de ses resultats.
ATTRIBUTS_COMPARES = ("type", "soustype", "nom", "texte", "modifiable",
                      "infobulle")

#: Ce que `filtrer` cherche, selon la portee. **Les deux appariements LISENT
#: ces tuples** — `_apparie_ecran` et `_apparie_champ` n'enumerent aucun
#: attribut a la main — et les deux ecrans qui annoncent ou ils ont cherche les
#: lisent aussi. C'est ce qui rend la divergence impossible au lieu de la
#: deconseiller : ajouter un attribut ici le cherche vraiment, et la ligne
#: « cherche dans » le dit le meme jour.
#:
#: Les attributs se lisent d'abord sur `ClefVariante`, puis sur la `Variante` :
#: `titre` vit sur la seconde, le triplet et l'empreinte sur la premiere.
CHERCHE_DANS_ECRAN = ("transaction", "programme", "dynpro", "empreinte",
                      "titre")
CHERCHE_DANS_CHAMP = ("id", "nom", "texte", "infobulle", "type", "soustype")

#: Un type d'objet d'ecran dont `Changeable` n'existe pas, et pour lequel
#: `couture/sapgui.py` inscrit son defaut — `FACULTATIFS["Changeable"] = True`.
#: Un « oui » porte par un objet de ce type n'a donc ete mesure par personne.
TYPE_SANS_CHANGEABLE = "GuiShell"

#: Un segment de fenetre dans un identifiant SAP, cherche en SOUS-CHAINE.
#:
#: `sapgui.py:198` fait `str(objet.Id)`, et SAP GUI rend usuellement un chemin
#: ABSOLU — `/app/con[0]/ses[0]/wnd[0]/usr/...` — la ou les fixtures du depot
#: ecrivent `wnd[0]/usr/...`. Un motif ancre au debut n'apparierait que les
#: secondes : il rendrait « aucune fenetre » sur un catalogue reel, et l'ecran
#: ecrirait « ? » partout sans que rien ne leve.
_FENETRE = re.compile(r"wnd\[\d+\]")


def fenetres_citees(champs: Iterable[Champ]) -> tuple[str, ...]:
    """Les fenetres que les identifiants NOMMENT, triees, sans doublon.

    Vide quand aucun identifiant ne porte de segment `wnd[...]`, et c'est le
    resultat : `wnd[0]` par defaut serait une affirmation, et c'est exactement
    celle que la modale rend dangereuse. Une variante relevee sur une modale
    porte le programme et le dynpro de l'ecran de DESSOUS — ses identifiants
    sont alors le seul endroit ou la fenetre se lise.

    Le tri est celui des chaines et non celui des numeros : `wnd[10]` se
    rangerait avant `wnd[2]`. Aucune session SAP n'ouvre dix fenetres
    empilees, et un tri numerique demanderait d'analyser le contenu des
    crochets — donc de decider quoi faire d'un `wnd[x]` que la regex ne peut
    pas produire. Le dire vaut mieux que de le laisser croire.
    """
    trouvees = set()
    for champ in champs:
        trouvees.update(_FENETRE.findall(champ.id))
    return tuple(sorted(trouvees))


def sans_mesure(champ: Champ) -> bool:
    """Ce « oui »-la a-t-il ete INSCRIT plutot que mesure ?

    Vrai pour un `GuiShell` **dont `modifiable` vaut exactement `True`** :
    l'objet n'expose pas `Changeable`, et `couture/sapgui.py` y inscrit alors
    son defaut, qui est `True` — `test_inventaire` epingle
    `FACULTATIFS["Changeable"]`. Ce « oui » entre donc dans les ecrivables sans
    que personne ne l'ait lu sur SAP.

    **Le TYPE ne suffit pas, et le croire etait un defaut.** Rien n'empeche un
    `GuiShell` de porter `modifiable: false` — `Depot._variante` pose `None`
    des que le fichier ne renseigne rien, et un YAML relu, converti ou retouche
    a la main peut porter n'importe laquelle des trois valeurs. Sur un tel
    champ, annoter « ce oui-la n'a ete mesure par personne » nomme un « oui »
    qui n'est pas la : le fichier dit VERROUILLE, l'ecran dit « sans preuve »,
    et qui redige un `set` y lit l'inverse de la donnee. On ne signale donc que
    la valeur qu'on accuse.

    Ce n'est PAS le troisieme etat de `compte_modifiable` : celui-la compte
    les champs dont le fichier ne renseigne rien du tout (`None`). Ici la
    valeur est renseignee — elle est simplement sans preuve. Les confondre
    rendrait un compte plausible et faux dans les deux sens.
    """
    return champ.type == TYPE_SANS_CHANGEABLE and champ.modifiable is True


@dataclass(frozen=True)
class Fiche:
    """Une variante relue, son rayon, et le fichier d'ou elle vient.

    Le FICHIER est porte parce qu'il est la seule chose qu'on puisse montrer a
    quelqu'un qui veut verifier : le triplet se recompose, le chemin non.
    """

    variante: Variante
    rayon: str
    fichier: Path
    #: La meme empreinte existe aussi dans le catalogue cure. FAIT DE FICHIER.
    #: Le catalogue ne garde aucune trace d'une promotion : ce booleen ne dit
    #: pas qu'un humain a decide, il dit que les deux rayons portent la meme
    #: clef. Les deux se ressemblent et ne valent pas la meme chose.
    au_cure: bool = False

    @property
    def clef(self) -> ClefVariante:
        return self.variante.clef

    @property
    def relevee(self) -> bool:
        """Relevee sur un systeme, par opposition a conjecturee d'une trace."""
        return self.variante.observee

    @property
    def fenetres(self) -> tuple[str, ...]:
        return fenetres_citees(self.variante.champs)

    @property
    def compte_modifiable(self) -> tuple[int, int, int]:
        """(ecrivables, verrouilles, NON RENSEIGNES AU FICHIER).

        Le troisieme n'est pas « non observes » : contre un vrai SAP,
        `sapgui.py` renseigne toujours `Changeable`, donc il vaudra zero. Le
        cas qui trompe est ailleurs et n'est PAS compte ici — un `GuiShell`
        n'expose pas `Changeable`, la couture y inscrit le defaut `True`, et
        ce « oui » entre dans les ECRIVABLES sans que personne ne l'ait mesure.
        La fiche annote donc chaque `GuiShell` ligne a ligne, et l'en-tete ne
        pretend pas trancher.
        """
        ecrivables = sum(1 for c in self.variante.champs if c.modifiable is True)
        verrouilles = sum(1 for c in self.variante.champs
                          if c.modifiable is False)
        inconnus = sum(1 for c in self.variante.champs if c.modifiable is None)
        return (ecrivables, verrouilles, inconnus)

    @property
    def sans_preuve(self) -> tuple[Champ, ...]:
        """Les champs dont le « modifiable » vient d'un defaut de la couture."""
        return tuple(c for c in self.variante.champs if sans_mesure(c))


@dataclass(frozen=True)
class Inventaire:
    """Les deux rayons relus, et ce qu'on n'a PAS pu relire.

    `fichiers_lus` ne compte que les fichiers dont la lecture a abouti, et
    `illisibles` porte les autres avec leur motif. Un total qui les melerait
    serait le compte plausible et faux que ce module existe pour eviter.
    """

    fiches: tuple[Fiche, ...] = ()
    illisibles: tuple[tuple[Path, str], ...] = ()
    fichiers_lus: int = 0
    duree_ms: int = 0

    def rayon(self, rayon: str) -> tuple[Fiche, ...]:
        if rayon == TOUS:
            return self.fiches
        return tuple(f for f in self.fiches if f.rayon == rayon)

    def voisines(self, fiche: Fiche) -> tuple[Fiche, ...]:
        """Les AUTRES variantes du meme triplet, dans le meme rayon.

        C'est ce qui declenche l'avertissement de la fiche : deux variantes
        d'un meme triplet sont le cas que le catalogue existe pour distinguer,
        et promouvoir la premiere venue sans avoir vu la seconde est
        exactement le geste que la comparaison sert a eviter.

        Le rayon entre dans le critere : une variante du cure n'est pas une
        « autre variante a decider », elle est deja decidee.
        """
        return tuple(f for f in self.fiches
                     if f.rayon == fiche.rayon
                     and f.clef.triplet == fiche.clef.triplet
                     and f.clef.empreinte != fiche.clef.empreinte)


def charger(depot: Depot, *, horloge: Callable[[], float] = time.monotonic
            ) -> Inventaire:
    """Relit les deux rayons, un fichier a la fois. Un fichier casse n'en
    emporte aucun autre.

    `depot` est le catalogue CURE ; la quarantaine est son sous-dossier, et
    c'est `Depot` qui le sait. Les deux rayons sont relus d'un seul geste
    parce que la question qu'on pose au navigateur — « qu'est-ce qui reste a
    decider » — est une question sur les DEUX : `au_cure` ne se calcule pas
    autrement.

    **Un fichier casse n'interrompt rien.** Il entre dans `illisibles` avec le
    message de `CatalogueInvalide`, et ses variantes n'entrent nulle part. La
    boucle continue : `Depot.triplets()` leve sur le premier et perd les neuf
    suivants sans jamais dire lequel a fache.

    **Trois familles sont attrapees, et il a fallu les MESURER.**
    `CatalogueInvalide` couvre ce que `Depot` sait refuser. `OSError` couvre le
    fichier verrouille par l'antivirus, le lien casse, le partage coupe en
    pleine lecture. Et `yaml.YAMLError` couvre le cas le plus banal des trois,
    celui qu'on croyait converti : `Depot._lire_fichier` appelle
    `yaml.safe_load` directement, donc un fichier tronque par une copie
    interrompue leve une `ParserError` NUE. Mesure faite en ecrivant
    « version: 1\nvariantes: { » dans la quarantaine : sans cette troisieme
    famille, l'inventaire entier tombe pour un fichier sur dix.

    **Ces trois-la ne suffisaient pas, et ce n'est pas ici que c'est corrige.**
    Quatre formes de fichier casse traversaient encore les trois familles et
    emportaient l'inventaire entier : un YAML resauvegarde en cp1252 par le
    Bloc-notes (`UnicodeDecodeError`, qui est un `ValueError`), un `variantes:`
    rendu comme une LISTE, un corps de variante scalaire, un `champs: 3` — les
    trois derniers en `AttributeError` et `TypeError`. Elles sont desormais
    traduites en `CatalogueInvalide` par `Depot._lire_fichier` et
    `Depot._variante`, c'est-a-dire au seul endroit qui sait quel fichier est
    en cause : elargir l'`except` ici aurait laisse `falcon inventaire` et tous
    les autres appelants de `Depot` tomber sur les memes fichiers. La liste des
    familles attrapees ici n'a donc pas bouge, et la forme des fichiers est
    verifiee en amont.

    `horloge` est injectee et vaut `time.monotonic` : l'ecran d'accueil affiche
    le temps de relecture, et une suite qui l'assertirait sur la vraie horloge
    serait instable. `time.monotonic` et non `p.horloge` du parcours : celle-la
    date des captures, et la faire servir a chronometrer decalerait la fausse
    horloge sequentielle des tests d'exploration.
    """
    debut = horloge()
    fiches: list[Fiche] = []
    illisibles: list[tuple[Path, str]] = []
    lus = 0

    rayons = ((QUARANTAINE, Depot(depot.quarantaine)), (CURE, depot))
    par_rayon: dict[str, list[Fiche]] = {QUARANTAINE: [], CURE: []}
    for nom, rayon in rayons:
        for chemin in rayon.fichiers():
            try:
                _, variantes = rayon.contenu(chemin)
            except (CatalogueInvalide, OSError,
                    yaml.YAMLError) as erreur:
                illisibles.append((chemin, str(erreur)))
                continue
            lus += 1
            for variante in variantes:
                par_rayon[nom].append(
                    Fiche(variante=variante, rayon=nom, fichier=chemin))

    # La clef ENTIERE, jamais l'empreinte seule. `empreinte` vaut
    # `empreinte(c.id for c in ecran.champs)` : elle ne depend QUE des
    # identifiants, jamais du triplet. Deux ecrans sans rapport qui portent les
    # memes identifiants — une modale de confirmation vue sous deux
    # transactions, une esquisse de triplet ('?','?','?') tiree d'une trace —
    # ont donc la meme empreinte et des clefs differentes. Comparer les
    # empreintes seules ferait afficher « Q+ » a une variante qui n'est PAS au
    # cure, et surtout `Critere(a_decider=True)` la retirerait de la file : une
    # ligne qui s'evapore d'une file de decisions sur une collision, sans un
    # mot. `Depot.promouvoir` prend une `ClefVariante` entiere ; on compare ce
    # qu'elle compare.
    clefs_du_cure = {f.clef for f in par_rayon[CURE]}
    for fiche in par_rayon[QUARANTAINE]:
        fiches.append(Fiche(variante=fiche.variante, rayon=QUARANTAINE,
                            fichier=fiche.fichier,
                            au_cure=fiche.clef in clefs_du_cure))
    fiches += par_rayon[CURE]
    fiches.sort(key=lambda f: (f.rayon, f.clef.triplet, f.clef.empreinte))

    return Inventaire(fiches=tuple(fiches), illisibles=tuple(illisibles),
                      fichiers_lus=lus,
                      duree_ms=int((horloge() - debut) * 1000))


@dataclass(frozen=True)
class Critere:
    """Ce qu'on garde d'un inventaire. Aucun champ ne CACHE par defaut.

    `a_decider` est le seul reglage qui retire des lignes sur autre chose que
    le motif tape, et il vaut faux : cacher des lignes sur une inference —
    « celle-ci est deja au cure, donc quelqu'un l'a vue » — est le reglage le
    plus dangereux possible pour une file de decisions. Le catalogue ne garde
    aucune trace d'une promotion ; `au_cure` est un fait de fichier.
    """

    motif: str = ""
    portee: str = ECRAN
    rayon: str = QUARANTAINE
    a_decider: bool = False

    #: **Il n'y a PAS de champ `source`**, et l'absence est une decision. Un
    #: reglage « relevees seulement / esquisses seulement » a existe ici : rien
    #: dans `falcon/` ne le renseignait, aucune touche ne l'atteignait, aucun
    #: test ne le traversait — et il n'etait pas valide, donc
    #: `Critere(source="observe")` (au lieu de `"observee"`) aurait rendu une
    #: liste VIDE en silence : un refus deguise en resultat, qu'il aurait fallu
    #: deviner. La liste distingue deja les deux a l'oeil, colonne `s`. Le jour
    #: ou la touche existe, le champ revient avec sa validation et son test.

    def __post_init__(self) -> None:
        if self.portee not in PORTEES:
            raise ValueError(f"portee inconnue : {self.portee!r}, "
                             f"attendu {list(PORTEES)}")
        if self.rayon not in (*RAYONS, TOUS):
            raise ValueError(f"rayon inconnu : {self.rayon!r}, "
                             f"attendu {[*RAYONS, TOUS]}")


@dataclass(frozen=True)
class Trouvaille:
    """Une fiche, et le champ qui a apparie quand la portee etait `CHAMP`.

    `champ` vaut `None` en portee `ECRAN` : la trouvaille est alors l'ecran
    lui-meme. Rendre le premier champ venu pour « avoir toujours un champ »
    designerait une cible que rien n'a appariee.
    """

    fiche: Fiche
    champ: Champ | None = None


def parcourues(inventaire: Inventaire, critere: Critere
               ) -> tuple[Fiche, ...]:
    """Les fiches que `filtrer` REGARDE, motif mis a part.

    C'est le denominateur honnete de « n trouvee(s) sur N variante(s) relues ».
    `len(inventaire.rayon(critere.rayon))` ne l'est pas : il ignore
    `a_decider`, que `filtrer` applique pourtant. Sur six variantes dont quatre
    deja au cure, l'ecran ecrivait « 2 trouvee(s) sur 6 variante(s) relues »
    alors que deux seulement avaient ete regardees — « le motif est rare » au
    lieu de « il est partout », sur deux comptes qui ne comptent pas la meme
    chose.

    Ecrite ICI et appelee par `filtrer` : deux implementations de la meme
    selection auraient diverge, et c'est precisement la divergence qu'on vient
    de payer.
    """
    return tuple(
        fiche for fiche in inventaire.rayon(critere.rayon)
        if not (critere.a_decider
                and (fiche.rayon != QUARANTAINE or fiche.au_cure)))


def filtrer(inventaire: Inventaire, critere: Critere, *,
            limite: int = 500) -> tuple[tuple[Trouvaille, ...], int]:
    """Rend (les trouvailles retenues, le TOTAL avant troncature).

    **Le total est rendu a part, et il n'est pas `len()` du premier membre.**
    Une liste tronquee a 500 dont on afficherait la longueur dirait « 500
    trouvees » sur 1200 : un compte plausible et faux, et celui-la se recopie
    dans une decision (« il n'y en a que 500, je peux tout relire »).

    La recherche est insensible a la casse et cherche en SOUS-CHAINE : un
    identifiant SAP se retient par un morceau — « werks », « btn[8] » — et
    exiger le chemin entier rendrait la recherche inutile precisement la ou
    elle sert.
    """
    motif = critere.motif.strip().lower()
    retenues: list[Trouvaille] = []
    total = 0

    for fiche in parcourues(inventaire, critere):
        if critere.portee == ECRAN:
            if motif and not _apparie_ecran(fiche, motif):
                continue
            total += 1
            if len(retenues) < limite:
                retenues.append(Trouvaille(fiche=fiche))
            continue

        for champ in fiche.variante.champs:
            if motif and not _apparie_champ(champ, motif):
                continue
            total += 1
            if len(retenues) < limite:
                retenues.append(Trouvaille(fiche=fiche, champ=champ))

    return tuple(retenues), total


def _apparie_ecran(fiche: Fiche, motif: str) -> bool:
    """Apparie sur les attributs que `CHERCHE_DANS_ECRAN` NOMME.

    La liste n'est pas recopiee ici : une copie a la main et la constante
    auraient diverge, et la ligne « cherche dans » de la liste aurait alors
    nomme des attributs que personne ne cherche. `test_inventaire` apparie les
    deux bouts.
    """
    manquant = object()
    for attribut in CHERCHE_DANS_ECRAN:
        valeur = getattr(fiche.clef, attribut, manquant)
        if valeur is manquant:
            valeur = getattr(fiche.variante, attribut, manquant)
        if valeur is manquant:
            raise AttributeError(
                f"CHERCHE_DANS_ECRAN nomme {attribut!r}, que ni la clef ni la "
                f"variante ne portent : la ligne qui annonce ou l'on a "
                f"cherche nommerait un attribut sur lequel rien n'apparie")
        if motif in (valeur or "").lower():
            return True
    return False


def _apparie_champ(champ: Champ, motif: str) -> bool:
    return any(motif in (getattr(champ, attribut) or "").lower()
               for attribut in CHERCHE_DANS_CHAMP)


class ComparaisonRefusee(Exception):
    """On demande de rapprocher deux choses qui ne se comptent pas pareil."""


@dataclass(frozen=True)
class Ecart:
    """Un identifiant present des deux cotes, et ce qui y differe."""

    id: str
    attribut: str
    gauche: object
    droite: object


@dataclass(frozen=True)
class Comparaison:
    """La MESURE de deux variantes relevees. Jamais une conclusion.

    Rien ici ne dit « c'est la modale ». `aucun_identifiant_commun` et
    `fenetres_disjointes` sont deux faits ; l'ecran les affiche comme tels et
    nomme separement ce que FALCON ne sait pas. Une propriete `est_une_modale`
    serait la meme heuristique, deplacee dans le modele et rendue invisible.
    """

    gauche: Fiche
    droite: Fiche
    communs: tuple[str, ...] = ()
    seuls_a_gauche: tuple[str, ...] = ()
    seuls_a_droite: tuple[str, ...] = ()
    ecarts: tuple[Ecart, ...] = ()

    @property
    def aucun_identifiant_commun(self) -> bool:
        return not self.communs

    @property
    def fenetres_disjointes(self) -> bool:
        """Vrai seulement si les DEUX cotes citent une fenetre, et pas la meme.

        Un cote qui n'en cite aucune rend faux : « disjoint » supposerait
        alors qu'on sache de quelle fenetre vient l'autre, et on ne le sait
        pas. Deux ensembles dont l'un est vide sont disjoints au sens des
        ensembles ; ce n'est pas le sens utile ici, et prendre l'un pour
        l'autre ferait affirmer un ecart de fenetres sur une variante qui ne
        nomme aucune fenetre.
        """
        gauche, droite = set(self.gauche.fenetres), set(self.droite.fenetres)
        return bool(gauche) and bool(droite) and not (gauche & droite)


def comparer(gauche: Fiche, droite: Fiche) -> Comparaison:
    """Rapproche deux variantes RELEVEES d'un MEME triplet. Deux refus.

    Une esquisse porte les identifiants TOUCHES par la trace ; un releve porte
    les identifiants PRESENTS a l'ecran. Les comparer compterait deux choses
    differentes, et le resultat aurait l'air d'un ecart : « 12 a gauche
    seulement » sur une esquisse qui en cite deux ne mesure que la difference
    entre observer et deviner.

    Mesure faite sur la quarantaine de la trace de reference : `_______.yaml`
    porte cinq esquisses sous le triplet vide, deux citant `wnd[0]` et trois
    `wnd[1]`, sans aucun identifiant commun. Six paires y satisferaient, sans
    cette garde, la condition exacte du paragraphe « signature du couple
    modale / porteur ». Une heuristique fausse des le premier jour, sur la
    fixture du depot.

    **Et elle refuse deux ecrans DIFFERENTS.** Le triplet n'etait garde par
    rien : `m` sur IH06/SAPLIH06/1000, `m` sur IW39/SAPLIW39/1000, puis `d`
    rendait une comparaison que l'ecran titrait du seul triplet de GAUCHE —
    celui de droite n'apparaissant nulle part — et dont les deux faits
    mesures, aucun identifiant commun et fenetres disjointes, sont ce que deux
    ecrans sans rapport donnent PRESQUE TOUJOURS. Le paragraphe « signature du
    couple modale / porteur » s'affichait donc en entier : il decrit une modale
    posee sur SON porteur, donc UN triplet, et sur deux ecrans sans rapport il
    est faux. C'est la conclusion meme que cet ecran existe pour ne pas tirer.
    L'ecart mesure entre deux ecrans differents n'est que la difference entre
    deux ecrans : un resultat plausible, et qui ne mesure rien.
    """
    for cote, fiche in (("gauche", gauche), ("droite", droite)):
        if not fiche.relevee:
            raise ComparaisonRefusee(
                f"{fiche.clef} ({cote}) est une ESQUISSE. Une esquisse porte "
                f"les identifiants TOUCHES par la trace ; un releve porte les "
                f"identifiants PRESENTS a l'ecran. Les comparer compterait "
                f"deux choses differentes, et le resultat aurait l'air d'un "
                f"ecart.")

    if gauche.clef.triplet != droite.clef.triplet:
        raise ComparaisonRefusee(
            f"{'/'.join(gauche.clef.triplet)} et "
            f"{'/'.join(droite.clef.triplet)} ne sont pas deux variantes d'un "
            f"MEME ecran. L'ecart mesure ne serait que la difference entre "
            f"deux ecrans, et l'avertissement sur la modale — qui decrit une "
            f"modale posee sur SON porteur — s'y poserait presque toujours, a "
            f"tort.")

    a = {c.id: c for c in gauche.variante.champs}
    b = {c.id: c for c in droite.variante.champs}
    communs = tuple(sorted(set(a) & set(b)))
    ecarts = tuple(
        Ecart(id=identifiant, attribut=attribut,
              gauche=getattr(a[identifiant], attribut),
              droite=getattr(b[identifiant], attribut))
        for identifiant in communs
        for attribut in ATTRIBUTS_COMPARES
        if getattr(a[identifiant], attribut) != getattr(b[identifiant],
                                                        attribut))
    return Comparaison(
        gauche=gauche, droite=droite, communs=communs,
        seuls_a_gauche=tuple(sorted(set(a) - set(b))),
        seuls_a_droite=tuple(sorted(set(b) - set(a))),
        ecarts=ecarts)


#: Le sous-dossier des comptes rendus conserves, et leur extension.
#:
#: Recopie de `commandes/cartographie.DOSSIER_RAPPORTS` plutot qu'importe :
#: `falcon/catalogue/` ne connait pas `falcon/commandes/`, et l'y faire
#: dependre inverserait la seule direction que le depot tienne. Les deux
#: valeurs sont appariees par `test_inventaire`.
DOSSIER_RAPPORTS = "rapports"
EXTENSION_RAPPORT = ".txt"


def rapports(depot: Depot) -> tuple[Path, ...]:
    """Les comptes rendus d'exploration conserves, du plus recent au plus vieux.

    Ils vivent dans `<catalogue>/rapports/`, un sous-dossier : `Depot` globe
    `racine/*.yaml` sans recursion, donc il ne les voit pas. Ils sont en `.txt`
    et pas en YAML — c'est le texte de `rapport.rendre`, verbatim, sans format
    nouveau donc sans classe de defaut nouvelle.

    **Le tri est celui des NOMS, a l'envers, et pas celui des dates de
    fichier.** Le nom commence par l'horodatage de la cartographie, qui est ce
    qu'on cherche ; la date du fichier est celle de la derniere ecriture, et
    une copie de sauvegarde qui les rafraichit toutes remettrait le plus vieux
    compte rendu en tete sans que rien ne leve. Le suffixe `_2` que pose
    `cartographie._conserver` sur une collision se range apres le fichier sans
    suffixe, donc le plus recent des deux sort bien en premier.

    **Le glob est sensible a la casse sous Linux et INSENSIBLE sous Windows.**
    Un `RAPPORT.TXT` depose a la main apparaitra donc dans cette liste chez
    l'utilisateur et jamais en CI. C'est ecrit plutot que corrige : forcer la
    casse ici ferait diverger cette liste de `Depot.fichiers()`, qui globe
    `*.yaml` avec exactement la meme dissymetrie depuis le premier jour.
    """
    dossier = Path(depot.racine) / DOSSIER_RAPPORTS
    if not dossier.is_dir():
        return ()
    return tuple(sorted(dossier.glob(f"*{EXTENSION_RAPPORT}"),
                        key=lambda c: c.name, reverse=True))
