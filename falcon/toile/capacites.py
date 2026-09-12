"""Ce que ce terminal-ci SAIT faire, mesure dans CE processus.

Aucune valeur de ce module n'est une supposition. Chaque `True` correspond a un
appel systeme qui a rendu ce qu'il fallait, ici, maintenant ; tout le reste vaut
faux ou `None`, et `motifs` nomme l'appel qui a echoue. C'est ce qui permet de
repondre « tu as tape quoi, et elle a repondu quoi » quand l'utilisateur
appellera depuis sa machine — ce qu'aucune ligne de ce depot ne sait faire
aujourd'hui.

**`shutil.get_terminal_size` est bannie, et cette docstring est l'endroit ou
c'est ecrit.** Mesure faite dans un tube : `os.get_terminal_size(1)` leve
`OSError [Errno 25]`, et `shutil` rend `(80, 24)`. Elle lit `COLUMNS`, puis
tente la mesure, puis avale l'exception. Elle ne leve jamais, ne dit jamais
qu'elle ne sait pas, et rend une valeur plausible et FAUSSE : c'est
litteralement la classe de defaut que ce depot traque, livree par la stdlib.

**Deux exceptions a attraper, et la raison n'est pas celle qu'on croit.** Sur
Windows, `os.get_terminal_size` n'accepte que les descripteurs 0, 1 et 2,
qu'elle traduit en handles standards (`Modules/posixmodule.c`, branche
`TERMSIZE_USE_CONIO`) ; tout autre descripteur donne
`ValueError("bad file descriptor")`. Mais une REDIRECTION de shell ne change
pas le numero du descripteur : `> journal.txt` laisse `fileno()` a 1, et l'on
obtient un `OSError` comme sous POSIX. Le `ValueError` n'arrive que pour un
flux tiers ouvert a la main. Les deux sont attrapees ; ecrire le mauvais
mecanisme dans la docstring qui justifie le `except` serait un defaut a part
entiere.

**Un pty sans TIOCSWINSZ rend `terminal_size(columns=0, lines=0)` SANS lever.**
Mesure. D'ou la validation `> 0` : dessiner une fenetre de largeur nulle, ou
diviser par elle, serait le resultat plausible et faux du jour.

**La sonde nomme le flux qu'elle a mesure.** Sur Windows, VT est un mode par
HANDLE : le poser sur la sortie standard ne l'active pas sur l'erreur standard.
Le navigateur ecrit sur `stdout` et le direct sur `stderr` ; deux flux, deux
sondes, et `Capacites.flux` dit lequel. Une capacite mesuree sur un flux et
affirmee sur un autre ferait deverser de l'ANSI dans le journal de celui qui
tape `falcon explorer ... 2> journal.log`.

**Tout passe par `Systeme`, et `sonder` l'exige.** Le chemin Windows —
handles de console, kernel32 — ne s'execute pas sur la CI Linux. S'il n'etait
pas injecte il ne serait jamais teste et vivrait sur la foi d'une lecture de
documentation : la meme faute que d'inventer un comportement SAP. `Systeme`
est obligatoire precisement pour que `tests/test_toile.py` ne PUISSE PAS lire
le vrai terminal — c'est la suite que `outils/neutraliser.py` relance en
pre-controle, et une suite qui depend du terminal de qui la lance ferait
rougir la verification des huit gardes SAP pour un motif sans rapport.

**Ce qui est MESURE et ce qui est DECLARE ne portent pas le meme mot, et c'est
la raison d'etre de `MESUREE` / `DECLAREE` / `INCONNUE`.** Sur Windows, le bit
VT se pose et se RELIT : c'est une mesure. Sur POSIX, aucun appel ne repond « je
comprends les sequences » ; il n'y a que `isatty()`, qui est un appel systeme,
et `TERM`, qui est une declaration de l'hote qu'on ne peut que croire. La sonde
ne fait pas semblant que ce soit la meme chose : le motif dit toujours d'ou
vient le verdict. Meme partage pour la taille — la mesure d'abord, la
declaration `COLUMNS`/`LINES` seulement si la mesure a echoue, et jamais sans
le dire. C'est exactement l'ordre inverse de `shutil`, qui prefere la
declaration puis se tait.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, TextIO

#: Les deux seuls niveaux de rendu.
#:
#: `NU` est le cas de BASE, pas un repli. Un echelon intermediaire — « largeur
#: mesuree mais pas de couleur » — a ete mesure sur les valeurs d'un cmd.exe
#: reel : la composition rend 0 ou tout. Deux sur trois ne donnent pas une
#: demi-interface, ca donne une interface cassee.
NU = 0
COULEUR = 1

#: D'ou vient la taille qu'on affiche. Trois mots, parce que deux mentiraient.
MESUREE, DECLAREE, INCONNUE = "mesuree", "declaree", "inconnue"

#: La largeur qu'on retient quand PERSONNE n'a su dire la vraie.
#:
#: Ce n'est pas une supposition sur la fenetre : c'est le cadre que
#: `console/menu.py:41` garantit deja partout, et que toute la console tient
#: depuis le premier jour. 80x24 devine serait, lui, mesurablement un mensonge.
LARGEUR_SANS_MESURE = 72

#: En dessous : refus, pas degradation. Une vue qui se replie n'est pas une vue.
LARGEUR_PLANCHER = 40

#: Au-dessus : on ne suit plus. Une ligne de 130 colonnes ne se lit pas, et
#: l'oeil perd la colonne de depart entre deux rangees.
LARGEUR_PLAFOND = 110

HAUTEUR_SANS_MESURE = 24

#: La largeur de la page de `falcon sonde`.
#:
#: Fixe, et pas mesuree : c'est la seule page du depot qu'on lance PARCE QU'ON
#: DOUTE de ce que le terminal sait faire. La mesurer la ferait dependre de ce
#: qu'elle est chargee de rapporter.
LARGEUR_DE_PAGE = 79

#: Handles standards de Windows, tels que `GetStdHandle` les numerote.
STD_SORTIE, STD_ERREUR = -11, -12

#: `ENABLE_VIRTUAL_TERMINAL_PROCESSING`. Le seul bit que ce depot pose.
VT_SORTIE = 0x0004

#: Encodage que la sortie de la sonde doit supporter.
#:
#: Repete ici plutot qu'importe de `falcon.console` : ce paquet ne connait pas
#: un mot de FALCON, et le rendre dependant d'une couche applicative pour une
#: constante de cinq lettres serait payer cher un doublon. `supervision` fait
#: deja le meme choix pour la meme raison.
ENCODAGE_MINIMAL = "cp1252"


class ConsoleWindows(Protocol):
    """Les deux appels kernel32 dont la sonde a besoin, et rien de plus.

    Etroit a dessein : c'est la seule surface par laquelle le chemin Windows
    touche le monde, donc la seule qu'un double ait a imiter. `None` en retour
    de `lire_mode` veut dire « `GetConsoleMode` a echoue », c'est-a-dire « ce
    handle n'est pas une console » — un fichier, un tube, un service.
    """

    def lire_mode(self, handle: int) -> int | None: ...

    def poser_mode(self, handle: int, mode: int) -> bool: ...


@dataclass(frozen=True)
class Systeme:
    """La frontiere entre la sonde et le monde. OBLIGATOIRE, jamais implicite.

    Un defaut ici — `systeme: Systeme | None = None`, puis « si None, je
    mesure » — suffirait a rendre toute la suite sensible au terminal de qui la
    lance : il suffirait d'un appel ou l'argument a ete oublie. Ce qu'on ne
    peut pas oublier de passer, on ne peut pas oublier de simuler.
    """

    plateforme: str
    variables: Mapping[str, str]
    nom_du_flux: str                                # "stdout" | "stderr"
    fileno: int | None                              # None = pas de fileno
    isatty: bool
    encodage: str
    console: ConsoleWindows | None = None
    taille: Callable[[int], tuple[int, int]] | None = None


def systeme_reel(flux: TextIO, nom: str) -> Systeme:
    """LA SEULE fonction du paquet qui touche le monde.

    Appelee par `falcon/commandes/principal.py` et par personne d'autre. Un
    test du paquet qui la citerait lirait le terminal de qui lance la suite ;
    `test_toile.test_la_suite_ne_touche_jamais_le_vrai_terminal` l'interdit sur
    l'arbre syntaxique.

    Chaque interrogation du flux est enveloppee. Un flux ferme leve
    `ValueError` sur `fileno()` comme sur `isatty()`, et un double de test peut
    n'avoir ni l'un ni l'autre : la sonde doit rendre « je ne sais pas » et pas
    une trace de pile, sinon `falcon sonde` meurt precisement sur le terminal
    bizarre qu'on l'appelle pour decrire.
    """
    import os
    import sys

    try:
        descripteur: int | None = flux.fileno()
    except (OSError, ValueError, AttributeError):
        descripteur = None

    try:
        interactif = bool(flux.isatty())
    except (OSError, ValueError, AttributeError):
        interactif = False

    plateforme = sys.platform
    return Systeme(
        plateforme=plateforme,
        variables=dict(os.environ),
        nom_du_flux=nom,
        fileno=descripteur,
        isatty=interactif,
        encodage=getattr(flux, "encoding", "") or "",
        console=_ConsoleKernel32() if plateforme == "win32" else None,
        taille=os.get_terminal_size,
    )


class _ConsoleKernel32:
    """`GetConsoleMode` / `SetConsoleMode` par `ctypes`, sur Windows seulement.

    **Aucune ligne de cette classe n'est exercee par la suite**, et c'est
    assume au meme titre que `couture/sapgui.py` : la CI est Linux, et un
    double y prouverait seulement que le double se comporte comme le double.
    Ce qui est teste, c'est le PROTOCOLE — poser, relire, restaurer, refuser si
    la relecture dement — contre `ConsoleWindows`. La conformite de ces
    quatre lignes a kernel32 se verifie a la main, sur la machine cible, par
    `falcon sonde`. C'est la reserve n°1 de la section 6 du plan.
    """

    def __init__(self) -> None:
        import ctypes

        self._noyau = ctypes.windll.kernel32           # type: ignore[attr-defined]
        self._ctypes = ctypes

    def _handle(self, handle: int):
        return self._noyau.GetStdHandle(self._ctypes.c_int(handle))

    def lire_mode(self, handle: int) -> int | None:
        mode = self._ctypes.c_uint()
        if not self._noyau.GetConsoleMode(self._handle(handle),
                                          self._ctypes.byref(mode)):
            return None
        return int(mode.value)

    def poser_mode(self, handle: int, mode: int) -> bool:
        return bool(self._noyau.SetConsoleMode(self._handle(handle),
                                               self._ctypes.c_uint(mode)))


@dataclass(frozen=True)
class Capacites:
    """Le releve d'un flux, et le journal de ce qui l'a produit.

    `colonnes` vaut `None` et JAMAIS 80 quand la mesure a echoue : `None` se
    propage jusqu'a une decision — poser le cadre de 72 et dire qu'il n'est pas
    mesure — alors que 80 se propage jusqu'a une ligne repliee que personne ne
    sait expliquer.
    """

    flux: str = ""
    interactif: bool = False
    colonnes: int | None = None          # None, JAMAIS 80
    lignes: int | None = None
    source_taille: str = INCONNUE        # mesuree | declaree | inconnue
    ansi: bool = False
    couleur: bool = False
    encodage: str = ENCODAGE_MINIMAL
    motifs: tuple[str, ...] = ()

    @property
    def niveau(self) -> int:
        """`COULEUR` seulement si TOUT a ete prouve sur CE flux."""
        return COULEUR if (self.interactif and self.ansi
                           and self.couleur) else NU


def _taille(systeme: Systeme,
            motifs: list[str]) -> tuple[int | None, int | None, str]:
    """La taille du terminal, ou `None` — jamais une valeur de confort.

    L'ordre est la mesure D'ABORD, la declaration ensuite. `shutil` fait
    l'inverse : elle lit `COLUMNS` avant de mesurer, si bien qu'un `COLUMNS`
    oublie dans un profil l'emporte sur la fenetre reelle. Ici la declaration
    n'est qu'un dernier recours, et elle sort sous le mot `declaree`.
    """
    if systeme.taille is None or systeme.fileno is None:
        motifs.append("aucun descripteur de fichier : la taille ne se "
                      "demande pas")
        return None, None, INCONNUE

    try:
        colonnes, lignes = systeme.taille(systeme.fileno)
    except OSError as erreur:
        # La redirection de shell : `> journal.txt` laisse fileno() a 1, et
        # l'ioctl echoue comme sous POSIX.
        motifs.append(f"os.get_terminal_size : OSError {erreur}")
        return _declaree(systeme, motifs)
    except ValueError as erreur:
        # Windows seulement : un descripteur autre que 0, 1 ou 2 n'a pas de
        # handle standard a qui parler.
        motifs.append(f"os.get_terminal_size : ValueError {erreur}")
        return _declaree(systeme, motifs)

    if colonnes > 0 and lignes > 0:
        return int(colonnes), int(lignes), MESUREE

    # Un pty sans TIOCSWINSZ rend (0, 0) SANS lever. Le prendre pour une
    # mesure donnerait une division par zero, ou pire, une fenetre de largeur
    # nulle dessinee sans un mot.
    motifs.append(f"os.get_terminal_size rend colonnes={colonnes} : "
                  f"ce pty ne sait pas sa taille")
    return _declaree(systeme, motifs)


def _declaree(systeme: Systeme,
              motifs: list[str]) -> tuple[int | None, int | None, str]:
    """`COLUMNS` / `LINES`, s'ils existent et s'ils sont lisibles.

    C'est une DECLARATION, pas une mesure, et le mot rendu le dit. On l'accepte
    parce que c'est le seul moyen qu'a un utilisateur de dire sa largeur a un
    programme qui n'a pas su la mesurer ; on refuse de la maquiller en mesure
    parce que c'est exactement ce qui rend `shutil` inutilisable ici.
    """
    brut_colonnes = systeme.variables.get("COLUMNS", "")
    brut_lignes = systeme.variables.get("LINES", "")
    try:
        colonnes, lignes = int(brut_colonnes), int(brut_lignes)
    except ValueError:
        return None, None, INCONNUE
    if colonnes <= 0 or lignes <= 0:
        return None, None, INCONNUE
    motifs.append(f"COLUMNS={colonnes} et LINES={lignes} declares par "
                  f"l'environnement, jamais verifies")
    return colonnes, lignes, DECLAREE


def _ansi_windows(systeme: Systeme, motifs: list[str]) -> bool:
    """Pose le bit VT, le RELIT, puis restaure le mode d'origine.

    Les trois temps comptent, et le troisieme est celui qu'on oublie.
    `SetConsoleMode` peut rendre vrai sans que le bit ait pris — le mode est un
    masque, et un hote qui filtre les bits inconnus n'a aucune obligation de le
    dire. Sans la relecture, la sonde affirmerait « ANSI oui » sur une console
    qui affichera `<-[31m` en toutes lettres. C'est la seule facon de
    transformer une lecture de documentation en mesure.

    **On restaure ce qu'on a trouve.** Une sonde est une mesure, pas un
    reglage : elle repond « ce terminal SAIT », elle ne decide pas qu'il le
    fera. Reposer le bit au moment de peindre est le geste du peintre, et il
    appartient au lot qui peint. Une sonde qui laisserait le mode modifie
    derriere elle changerait le comportement d'un programme qui ne lui a rien
    demande d'autre qu'un diagnostic.
    """
    console = systeme.console
    if console is None:
        motifs.append("aucune console Windows a interroger : le systeme "
                      "injecte n'en porte pas")
        return False

    handle = STD_ERREUR if systeme.nom_du_flux == "stderr" else STD_SORTIE
    mode = console.lire_mode(handle)
    if mode is None:
        motifs.append("GetConsoleMode a echoue : ce handle n'est pas une "
                      "console")
        return False

    if mode & VT_SORTIE:
        motifs.append("bit VT deja pose par l'hote")
        return True

    if not console.poser_mode(handle, mode | VT_SORTIE):
        motifs.append("SetConsoleMode refuse : console trop ancienne pour VT")
        return False

    verification = console.lire_mode(handle)
    console.poser_mode(handle, mode)
    if verification is None or not (verification & VT_SORTIE):
        motifs.append("SetConsoleMode a rendu vrai, le bit VT n'est pas la "
                      "a la relecture : console menteuse")
        return False

    motifs.append("bit VT pose, relu, mode restaure")
    return True


def _ansi_posix(systeme: Systeme, motifs: list[str]) -> bool:
    """Ce que POSIX permet de savoir, c'est-a-dire moins que sur Windows.

    Il n'existe aucun appel qui reponde « j'interprete les sequences ». Les
    deux faits disponibles sont `isatty()` — deja lu par l'appelant — et
    `TERM`, qui est une declaration de l'hote. Le motif dit donc toujours
    laquelle des deux a tranche : personne ne doit pouvoir lire « ANSI oui »
    sans voir d'ou ca sort.
    """
    terme = systeme.variables.get("TERM", "")
    if not terme:
        motifs.append("TERM n'est pas defini : rien ne declare ce terminal")
        return False
    if terme == "dumb":
        motifs.append("TERM=dumb : le terminal se declare sans capacite")
        return False
    motifs.append(f"TERM={terme} declare par l'hote (POSIX ne mesure pas)")
    return True


def sonder(systeme: Systeme) -> Capacites:
    """Le releve d'UN flux. Rien n'y est devine, tout y est date de maintenant.

    `systeme` est obligatoire : voir la docstring du module. L'ordre des
    questions n'est pas indifferent — la taille se demande MEME quand le flux
    n'est pas un terminal, parce que le motif de l'echec est precisement ce
    qu'on veut pouvoir lire quand l'utilisateur appelle.
    """
    motifs: list[str] = []
    colonnes, lignes, source = _taille(systeme, motifs)

    if not systeme.isatty:
        motifs.append("isatty() est faux : pas de terminal a qui envoyer des "
                      "sequences")
        ansi = False
    elif systeme.plateforme.startswith("win"):
        ansi = _ansi_windows(systeme, motifs)
    else:
        ansi = _ansi_posix(systeme, motifs)

    couleur = ansi
    if ansi and systeme.variables.get("NO_COLOR", ""):
        # Une convention, et elle se respecte sans discuter : celui qui la pose
        # a deja dit ce qu'il voulait. On garde `ansi` vrai — il est mesure —
        # et on refuse la couleur, qui est un choix.
        motifs.append("NO_COLOR est pose : la couleur est refusee par "
                      "l'environnement")
        couleur = False

    return Capacites(
        flux=systeme.nom_du_flux,
        interactif=systeme.isatty,
        colonnes=colonnes,
        lignes=lignes,
        source_taille=source,
        ansi=ansi,
        couleur=couleur,
        encodage=systeme.encodage or ENCODAGE_MINIMAL,
        motifs=tuple(motifs),
    )


#: Ce que `falcon sonde` dit une fois pour toutes les deux sondes.
#:
#: Ecrit ici et pas dans les deux appelants — la CLI et l'ecran de console — :
#: un texte normatif recopie a deux endroits derive au premier amendement, et
#: c'est alors la moitie des lecteurs qui lit la version perimee.
NOTE_DE_LECTURE = (
    "  Chaque « oui » ci-dessus est un appel systeme qui a REUSSI dans ce",
    "  processus-ci. Aucun n'est deduit d'un nom de variable, d'un numero de",
    "  version, ni d'un « en general ca marche ». Un « non » nomme l'appel",
    "  qui a repondu ce qu'il a repondu.",
)

_MOTS = {True: "oui", False: "non"}
_NIVEAUX = {NU: "NU", COULEUR: "COULEUR"}


def _ligne(etiquette: str, valeur: str, note: str = "") -> str:
    corps = f"    {etiquette:<20} {valeur:<15}"
    return (corps + note).rstrip() if note else corps.rstrip()


def rendre_capacites(capacites: Capacites) -> tuple[str, ...]:
    """Ce qu'imprime `falcon sonde`. Fonction PURE, cp1252, sans sequence.

    Le bloc des motifs n'est pas un ornement : c'est la moitie utile du relevé
    quand quelque chose ne marche pas. Une sonde qui ecrirait « ANSI non » sans
    dire lequel des quatre chemins a refuse obligerait a deviner a distance,
    ce qui est exactement le service qu'elle existe pour rendre inutile.
    """
    if capacites.colonnes is None or capacites.lignes is None:
        taille, source = "inconnue", ""
    else:
        taille = f"{capacites.colonnes} x {capacites.lignes}"
        source = capacites.source_taille

    lignes = [
        _ligne("flux mesure", capacites.flux or "(sans nom)"),
        _ligne("interactif", _MOTS[capacites.interactif]),
        _ligne("taille", taille, source),
        _ligne("ANSI", _MOTS[capacites.ansi]),
        _ligne("couleur", _MOTS[capacites.couleur],
               "16 couleurs" if capacites.couleur else ""),
        _ligne("encodage de sortie", capacites.encodage),
        _ligne("niveau retenu", _NIVEAUX[capacites.niveau]),
    ]
    if capacites.motifs:
        lignes.append("    ce qui a ete appele, et ce qu'il a repondu :")
        for motif in capacites.motifs:
            # Un motif porte un message d'OSError ou une valeur de TERM :
            # sa longueur n'est pas la notre. On le REPLIE, on ne le coupe
            # pas — c'est la seule ligne de cette page dont on ne peut rien
            # jeter sans perdre precisement ce qu'on est venu lire.
            lignes += textwrap.wrap(motif, width=LARGEUR_DE_PAGE - 6,
                                    initial_indent="      ",
                                    subsequent_indent="        ") or ["      "]
    return tuple(lignes)


def rendre_sonde(releves: tuple[Capacites, ...]) -> tuple[str, ...]:
    """La page entiere de `falcon sonde` : un bloc par flux, et la note.

    Les deux appelants — la ligne de commande et l'ecran de console — n'ont
    alors plus une ligne de texte a eux. Un ecran qui composerait sa propre
    version du meme releve finirait par en dire autre chose, et il n'y a aucune
    facon de s'en apercevoir depuis un test qui ne regarde qu'un des deux.
    """
    barre = "  " + "-" * (LARGEUR_DE_PAGE - 6)
    lignes = ["  FALCON — ce que CE terminal sait faire", barre]
    for capacites in releves:
        lignes += list(rendre_capacites(capacites))
        lignes.append(barre)
    lignes += list(NOTE_DE_LECTURE)
    return tuple(lignes)


@dataclass(frozen=True)
class Gabarit:
    """La geometrie retenue. C'est CE qu'on peint, pas ce qu'on a mesure.

    `colonnes` vaut la mesure MOINS UNE colonne. conhost n'a pas le repli
    differe de Windows Terminal : ecrire un glyphe dans la derniere colonne y
    fait passer le curseur a la ligne suivante immediatement, et le saut de
    ligne que `print` ajoute en pose alors un second — une rangee blanche par
    ligne pleine, et un defilement double. Cette colonne coute zero et je ne
    peux pas la tester d'ici.

    Sans mesure, `colonnes` vaut 72 : ce n'est pas une supposition sur la
    fenetre, c'est le cadre que `console/menu.py:41` garantit deja partout. Et
    `mesuree` est FAUX, et chaque ecran le dit. Le contraire — 80x24 devine —
    est mesurablement un mensonge.

    **Aucun plancher ne surpasse jamais une mesure plus petite.** Une mesure a
    60 donne 59, pas 72 : reprocher a `shutil` son repli suppose puis faire le
    meme geste dans l'autre sens serait la meme faute.
    """

    colonnes: int = LARGEUR_SANS_MESURE
    lignes: int = HAUTEUR_SANS_MESURE
    mesuree: bool = False
    niveau: int = NU

    @property
    def trop_etroit(self) -> bool:
        return self.colonnes < LARGEUR_PLANCHER


def gabarit_pour(capacites: Capacites, *, forcer_nu: bool = False) -> Gabarit:
    """Des capacites vers la geometrie qu'on peindra vraiment.

    `forcer_nu` est le `--sans-couleur` de la ligne de commande : un refus que
    l'utilisateur pose sans avoir a l'argumenter. Il ne touche pas a la
    largeur — refuser la couleur n'est pas refuser de savoir ou finit l'ecran.
    """
    niveau = NU if forcer_nu else capacites.niveau
    if capacites.colonnes is None or capacites.lignes is None:
        return Gabarit(niveau=niveau)
    return Gabarit(colonnes=min(capacites.colonnes, LARGEUR_PLAFOND) - 1,
                   lignes=capacites.lignes,
                   mesuree=capacites.source_taille == MESUREE,
                   niveau=niveau)
