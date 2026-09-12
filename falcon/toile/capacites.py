"""Ce que ce terminal-ci SAIT faire, mesure ou declare dans CE processus.

Aucune valeur de ce module n'est une supposition, et aucune ne se donne pour
plus qu'elle n'est. Deux provenances, deux mots, jamais confondus :

  - MESUREE — un appel systeme a rendu ce qu'il fallait, ici, maintenant. Le
    bit VT pose PUIS RELU sur un handle de console en est une ; `isatty()` en
    est une ; `os.get_terminal_size` en est une.
  - DECLAREE — l'hote l'affirme et rien ne le verifie. `TERM` en est une,
    `COLUMNS`/`LINES` en sont une. On les croit faute de mieux, et on ECRIT
    qu'on les a crues.

Tout le reste vaut faux, `None` ou vide, et `motifs` nomme l'appel qui a
echoue. C'est ce qui permet de repondre « tu as tape quoi, et elle a repondu
quoi » quand l'utilisateur appellera depuis sa machine — ce qu'aucune ligne de
ce depot ne sait faire aujourd'hui.

**Le pire cas de ce module n'est pas qu'il refuse, c'est qu'il accepte a
tort** : `<-[31m` en toutes lettres sur une console qui n'interprete rien. Une
declaration maquillee en mesure est donc le defaut directeur ici, et le releve
porte la provenance a cote de CHAQUE verdict pour que personne n'ait a la
deviner.

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

**ANSI ne se mesure pas de la meme facon des deux cotes, et c'est ecrit dans
le releve.** Sur Windows, le bit VT se pose, se RELIT et se restaure : trois
appels, donc une mesure. Sur POSIX, aucun appel ne repond « je comprends les
sequences » ; il n'y a que `isatty()`, qui dit seulement qu'il y a un terminal,
et `TERM`, qui est la parole de l'hote. Un POSIX dont le `TERM` est herite
d'un `ssh`, d'un `env -i` ou d'un editeur obtient donc la couleur sur une
declaration, et la page de `falcon sonde` le dit mot pour mot : `declare par
TERM, non mesure`. Pretendre l'inverse serait, dans la commande meme qu'on
lance PARCE QU'ON DOUTE de son terminal, le mensonge le plus couteux du depot.

Meme partage pour la taille — la mesure d'abord, la declaration
`COLUMNS`/`LINES` seulement si la mesure a echoue, et jamais sans le dire.
C'est exactement l'ordre inverse de `shutil`, qui prefere la declaration puis
se tait.

**Aucun texte compose ici n'echappe a `ENCODAGE_MINIMAL`.** Les motifs
interpolent deux chaines venues du monde — la valeur de `TERM` et le message
d'une `OSError`, que Windows LOCALISE selon la langue du systeme. Sur un
Windows japonais, russe ou grec, un motif recopie tel quel ferait mourir
`falcon sonde` sur un `UnicodeEncodeError` au moment precis ou on l'appelle au
telephone. Le texte etranger est donc ramene a cp1252 des son entree dans un
motif : perdre trois glyphes d'un `strerror` ne coute rien, l'errno et le nom
de l'appel portent l'information.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, TextIO

from .fragment import couper

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

#: Nom de flux -> handle standard. FERMEE, et c'est tout son interet.
#:
#: Le premier jet ecrivait `STD_ERREUR if nom == "stderr" else STD_SORTIE` :
#: tout autre nom — « STDERR », « erreur standard », « log » — etait alors
#: mesure sur le handle de la SORTIE et le releve estampille du nom qu'on lui
#: avait donne. VT etant un mode par HANDLE, c'est mot pour mot le defaut que
#: la docstring du module jure d'empecher : de l'ANSI deverse dans le journal
#: de celui qui tape `falcon explorer ... 2> journal.log`. Une clef inconnue
#: LEVE — un refus vaut mieux qu'une valeur devinee.
HANDLES = {"stdout": STD_SORTIE, "stderr": STD_ERREUR}

#: `ENABLE_VIRTUAL_TERMINAL_PROCESSING`. Le seul bit que ce depot pose.
VT_SORTIE = 0x0004

#: Encodage que la sortie de la sonde doit supporter.
#:
#: Repete ici plutot qu'importe de `falcon.console` : ce paquet ne connait pas
#: un mot de FALCON, et le rendre dependant d'une couche applicative pour une
#: constante de cinq lettres serait payer cher un doublon. `supervision` fait
#: deja le meme choix pour la meme raison.
ENCODAGE_MINIMAL = "cp1252"


def _lisible(texte: str) -> str:
    """Le texte ramene a ce que `ENCODAGE_MINIMAL` sait ecrire.

    Appele sur tout ce qui entre dans un motif depuis le monde exterieur : la
    valeur de `TERM`, et le `strerror` d'une `OSError`, que Windows traduit
    dans la langue du systeme. Sans ce passage, la page de `falcon sonde`
    leverait `UnicodeEncodeError` sur un poste japonais — donc precisement sur
    le genre de machine ou l'on appelle cette commande a l'aide.

    On REMPLACE au lieu de refuser : un motif est un recit, pas une donnee.
    Trois points d'interrogation a la place de trois ideogrammes laissent
    l'errno, le nom de l'appel et la phrase lisibles, ce qui est tout ce qu'on
    lit au telephone.
    """
    return texte.encode(ENCODAGE_MINIMAL, "replace").decode(ENCODAGE_MINIMAL)


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

    `nom_du_flux` est VALIDE, et pas seulement documente par un commentaire.
    Il sert a deux choses qui ne pardonnent pas l'a-peu-pres : choisir le
    handle Windows a interroger, et estampiller le releve. Un nom libre
    laissait mesurer la sortie standard puis signer « stderr ».
    """

    plateforme: str
    variables: Mapping[str, str]
    nom_du_flux: str                                # "stdout" | "stderr"
    fileno: int | None                              # None = pas de fileno
    isatty: bool
    encodage: str
    console: ConsoleWindows | None = None
    taille: Callable[[int], tuple[int, int]] | None = None

    def __post_init__(self) -> None:
        if self.nom_du_flux not in HANDLES:
            raise ValueError(
                f"nom de flux inconnu : {self.nom_du_flux!r} ; connus : "
                f"{sorted(HANDLES)}. VT est un mode par HANDLE : mesurer un "
                f"flux et signer du nom d'un autre ferait deverser de l'ANSI "
                f"dans un journal redirige.")


def systeme_reel(flux: TextIO, nom: str) -> Systeme:
    """LA SEULE fonction du paquet qui touche le monde.

    Appelee par `falcon/commandes/principal.py` et par le defaut du champ
    `Environnement.sonde` de `falcon/console/ecrans.py` — et par personne
    d'autre. L'enumeration est ici parce que c'est elle qui rend l'invariant du
    module verifiable a l'oeil : si un troisieme appelant apparait sans y
    entrer, la phrase devient fausse, et une docstring fausse est un defaut a
    part entiere. Un test du paquet qui la citerait lirait le terminal de qui
    lance la suite ; dans `tests/test_toile.py`, le test nomme « la suite ne
    touche jamais le vrai terminal » l'interdit sur l'arbre syntaxique.

    Chaque interrogation du monde est enveloppee, sans exception. Un flux ferme
    leve `ValueError` sur `fileno()` comme sur `isatty()` ; `ctypes` peut
    echouer a ouvrir kernel32 sur un Windows bride ou dans un processus sans
    console. La sonde doit rendre « je ne sais pas » et pas une trace de pile,
    sinon `falcon sonde` meurt precisement sur le terminal bizarre qu'on
    l'appelle pour decrire — et l'ecran de console qui l'appelle emporte la
    session entiere avec lui.
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
    console: ConsoleWindows | None = None
    if plateforme == "win32":
        try:
            console = _ConsoleKernel32()
        except Exception:
            # `ctypes` n'a pas pu ouvrir kernel32. Le motif sortira par
            # `_ansi_windows`, qui sait deja dire « aucune console Windows a
            # interroger » : un refus motive, jamais une trace de pile.
            console = None

    return Systeme(
        plateforme=plateforme,
        variables=dict(os.environ),
        nom_du_flux=nom,
        fileno=descripteur,
        isatty=interactif,
        encodage=getattr(flux, "encoding", "") or "",
        console=console,
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

    Ce que la CI PEUT voir, et qu'un test regarde : la FORME. Les noms et
    l'ordre des parametres sont apparies a ceux de `ConsoleWindows`. Sans ce
    controle, inverser `poser_mode(self, handle, mode)` en `(self, mode,
    handle)` laisserait les suites entierement vertes et poserait, sur
    Windows, un mode sur le mauvais handle — sans exception, avec une
    relecture qui rendrait le mode d'un autre flux et une sonde qui
    repondrait « ANSI oui » sur une mesure qu'elle n'a pas faite.

    `ctypes.WinDLL` et pas `ctypes.windll.kernel32` : le second est un objet de
    CACHE partage par tout le processus, et y poser des `argtypes` changerait
    le comportement de n'importe quel autre code qui l'utilise. Les `argtypes`
    et `restype` ne sont pas un ornement : sans `restype`, `GetStdHandle` rend
    un `HANDLE` relu comme un `c_int`, donc tronque a 32 bits signes sur
    Win64. La direction de l'echec serait sure — `GetConsoleMode` refuserait,
    donc NU — mais ce module est bati sur le refus de croire une lecture de
    documentation, et une ligne coute moins cher qu'un doute.
    """

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._noyau = ctypes.WinDLL("kernel32", use_last_error=True)

        self._noyau.GetStdHandle.argtypes = [wintypes.DWORD]
        self._noyau.GetStdHandle.restype = wintypes.HANDLE
        self._noyau.GetConsoleMode.argtypes = [wintypes.HANDLE,
                                               ctypes.POINTER(wintypes.DWORD)]
        self._noyau.GetConsoleMode.restype = wintypes.BOOL
        self._noyau.SetConsoleMode.argtypes = [wintypes.HANDLE,
                                               wintypes.DWORD]
        self._noyau.SetConsoleMode.restype = wintypes.BOOL
        self._wintypes = wintypes

    def _brut(self, handle: int):
        # `GetStdHandle` prend un DWORD ; -11 et -12 s'y ecrivent modulo 2^32.
        return self._noyau.GetStdHandle(handle & 0xFFFFFFFF)

    def lire_mode(self, handle: int) -> int | None:
        mode = self._wintypes.DWORD()
        if not self._noyau.GetConsoleMode(self._brut(handle),
                                          self._ctypes.byref(mode)):
            return None
        return int(mode.value)

    def poser_mode(self, handle: int, mode: int) -> bool:
        return bool(self._noyau.SetConsoleMode(self._brut(handle), mode))


@dataclass(frozen=True)
class Capacites:
    """Le releve d'un flux, et le journal de ce qui l'a produit.

    `colonnes` vaut `None` et JAMAIS 80 quand la mesure a echoue : `None` se
    propage jusqu'a une decision — poser le cadre de 72 et dire qu'il n'est pas
    mesure — alors que 80 se propage jusqu'a une ligne repliee que personne ne
    sait expliquer.

    `encodage` vaut la chaine VIDE quand le flux n'en declare aucun, et surtout
    pas `ENCODAGE_MINIMAL` : `ENCODAGE_MINIMAL` est le plancher de celui qui
    doit CHOISIR quoi ecrire, jamais une valeur qu'on rapporte. Ecrire
    « encodage de sortie cp1252 » sur une machine Linux en UTF-8, sous une
    etiquette qui dit « ce qui a ete mesure », serait exactement la classe de
    defaut que ce module existe pour ne pas avoir.

    `source_taille` et `source_ansi` disent d'ou vient chaque verdict. Ils sont
    DEUX et pas un : la taille se mesure par `os.get_terminal_size` et ANSI par
    le bit VT ou par `TERM` ; les deux echouent independamment, et un drapeau
    unique obligerait a choisir laquelle des deux provenances on ment.
    """

    flux: str = ""
    interactif: bool = False
    colonnes: int | None = None          # None, JAMAIS 80
    lignes: int | None = None
    source_taille: str = INCONNUE        # mesuree | declaree | inconnue
    ansi: bool = False
    source_ansi: str = INCONNUE          # mesuree | declaree | inconnue
    couleur: bool = False
    encodage: str = ""                   # vide = le flux n'a rien declare
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
        # `pythonw` sur Windows, un service, un flux sans descripteur. La
        # declaration passe par le MEME dernier recours que les autres echecs :
        # un chemin d'echec qui n'aurait pas le meme repli que ses voisins est
        # une incoherence dont personne ne se souviendra dans six mois.
        motifs.append("aucun descripteur de fichier : la taille ne se "
                      "demande pas")
        return _declaree(systeme, motifs)

    try:
        colonnes, lignes = systeme.taille(systeme.fileno)
    except OSError as erreur:
        # La redirection de shell : `> journal.txt` laisse fileno() a 1, et
        # l'ioctl echoue comme sous POSIX. Le `strerror` est LOCALISE par
        # Windows : il passe par `_lisible` comme tout texte venu du monde.
        motifs.append(_lisible(f"os.get_terminal_size : OSError {erreur}"))
        return _declaree(systeme, motifs)
    except ValueError as erreur:
        # Windows seulement : un descripteur autre que 0, 1 ou 2 n'a pas de
        # handle standard a qui parler.
        motifs.append(_lisible(f"os.get_terminal_size : ValueError {erreur}"))
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

    **Les DEUX sont exigees, et ce refus se dit.** `bash` exporte souvent
    `COLUMNS` sans `LINES` ; accepter la largeur seule obligerait a inventer
    une hauteur, ce qui est precisement le geste interdit. Mais se taire
    laisserait celui qui a pose `COLUMNS` pour se faire entendre sans aucun
    moyen de savoir pourquoi il ne l'a pas ete — d'ou le motif.
    """
    brut_colonnes = systeme.variables.get("COLUMNS", "")
    brut_lignes = systeme.variables.get("LINES", "")
    if not brut_colonnes and not brut_lignes:
        return None, None, INCONNUE

    try:
        colonnes, lignes = int(brut_colonnes), int(brut_lignes)
    except ValueError:
        motifs.append(_lisible(
            f"COLUMNS={brut_colonnes!r} et LINES={brut_lignes!r} : il faut "
            f"les DEUX, entieres, pour poser une taille declaree ; la "
            f"hauteur ne s'invente pas"))
        return None, None, INCONNUE
    if colonnes <= 0 or lignes <= 0:
        motifs.append(f"COLUMNS={colonnes} et LINES={lignes} : une taille "
                      f"nulle ou negative ne se dessine pas")
        return None, None, INCONNUE

    motifs.append(f"COLUMNS={colonnes} et LINES={lignes} declares par "
                  f"l'environnement, jamais verifies")
    return colonnes, lignes, DECLAREE


def _appeler(quoi: str, appel, motifs: list[str], *arguments):
    """Un appel kernel32, et la promesse qu'il ne remonte jamais une trace.

    Le chemin Windows ne s'execute sur aucune CI : une exception venue de
    `ctypes` y serait invisible jusqu'au jour ou elle tuerait `falcon sonde`
    sur la machine de l'utilisateur, et l'ecran de console avec — la session
    entiere, pas seulement la page. La docstring de `systeme_reel` promet « je
    ne sais pas, et pas une trace de pile » ; sans cette enveloppe elle ne le
    promettrait que pour `fileno()` et `isatty()`.

    Rend `None` en cas d'accident, ce que les deux appelants traitent deja
    comme un echec — `lire_mode` rend deja `None`, et `poser_mode` ne rend
    vrai que sur un succes.
    """
    try:
        return appel(*arguments)
    except Exception as erreur:            # noqa: BLE001 — motive, pas avale
        motifs.append(_lisible(f"{quoi} a leve {type(erreur).__name__} : "
                               f"{erreur}"))
        return None


def _ansi_windows(systeme: Systeme,
                  motifs: list[str]) -> tuple[bool, str]:
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
        return False, INCONNUE

    # Table FERMEE, et c'est la SECONDE mesure : `Systeme` a deja refuse tout
    # autre nom a la construction. Si cette validation sautait, on leve ici
    # plutot que de mesurer la sortie standard en signant du nom de l'erreur
    # standard — un refus vaut mieux qu'une valeur devinee.
    handle = HANDLES.get(systeme.nom_du_flux)
    if handle is None:
        raise ValueError(
            f"aucun handle standard pour le flux {systeme.nom_du_flux!r} : "
            f"connus {sorted(HANDLES)}. Deviner reviendrait a mesurer un flux "
            f"et a signer du nom d'un autre.")

    mode = _appeler("GetConsoleMode", console.lire_mode, motifs, handle)
    if mode is None:
        motifs.append("GetConsoleMode a echoue : ce handle n'est pas une "
                      "console")
        return False, MESUREE

    if mode & VT_SORTIE:
        motifs.append("bit VT deja pose par l'hote")
        return True, MESUREE

    if not _appeler("SetConsoleMode", console.poser_mode, motifs,
                    handle, mode | VT_SORTIE):
        motifs.append("SetConsoleMode refuse : console trop ancienne pour VT")
        return False, MESUREE

    verification = _appeler("GetConsoleMode (relecture)", console.lire_mode,
                            motifs, handle)
    restaure = _appeler("SetConsoleMode (restauration)", console.poser_mode,
                        motifs, handle, mode)
    if verification is None or not (verification & VT_SORTIE):
        motifs.append("SetConsoleMode a rendu vrai, le bit VT n'est pas la "
                      "a la relecture : console menteuse")
        return False, MESUREE

    if restaure:
        motifs.append("bit VT pose, relu, mode d'origine restaure")
    else:
        # Le verdict ne change pas — la capacite EST prouvee — mais le RECIT
        # si, et c'est lui qu'on lit au telephone. Ecrire « mode restaure »
        # quand `SetConsoleMode` a refuse serait une affirmation non mesuree
        # dans le seul module dont le contrat est de n'en produire aucune. Et
        # le lot qui peindra a besoin de savoir si le bit est encore la.
        motifs.append("bit VT pose et relu, mais SetConsoleMode a refuse de "
                      "reposer le mode d'origine : le bit reste pose")
    return True, MESUREE


def reposer_le_bit(systeme: Systeme) -> bool:
    """Repose le bit VT sur le flux qu'on va peindre, et le LAISSE pose.

    **C'est le geste que `_ansi_windows` annonce et ne fait pas.** La sonde
    restaure le mode qu'elle a trouve, parce qu'une sonde mesure et ne regle
    pas : sur un conhost de Windows 10 ou de PowerShell 5.1 — la machine
    cible — VT est ETEINT par defaut, et apres `sonder` il l'est de nouveau.
    Peindre la-dessus sur la foi d'un `ansi=True` mesure une seconde plus tot
    deverserait `<-[1m` en toutes lettres a chaque ligne : les capacites
    seraient vraies, l'etat du handle aurait change apres la mesure, et la
    garde n°9 ne mordrait pas puisqu'elle ne regarde que les capacites.
    C'est le pire cas du plan — non pas qu'elle refuse, mais qu'elle accepte
    a tort — et il ne se voit sur aucune machine de la CI.

    **On ne restaure PAS.** Ce n'est pas un oubli symetrique : le peintre
    veut que le bit reste pose pendant qu'il peint, et il n'y a pas de
    « pendant » au sens d'un bloc — le direct ecrit sur toute la duree du
    rejeu, et un `finally` qui le reposerait ne s'executerait pas sur un
    CTRL_CLOSE_EVENT. Reposer un mode que l'hote avait deja pose n'aurait de
    toute facon rien restaure.

    Rend VRAI seulement si le bit EST pose au moment ou cette fonction rend
    la main :

      - hors Windows, il n'y a pas de bit : vrai, il n'y a rien a reposer et
        `_ansi_posix` a deja dit ce qu'on savait ;
      - sur Windows sans console a interroger — `ctypes` n'a pas pu ouvrir
        kernel32 — c'est FAUX : on ne sait pas, et un refus vaut mieux qu'une
        valeur devinee. L'appelant peint alors en texte nu, ce qui est le cas
        de BASE et non un repli degrade ;
      - sur Windows 8.1, `SetConsoleMode` refuse le bit inconnu : faux, et
        c'est exactement ce que la sonde avait deja mesure.

    L'appelant — aujourd'hui `commandes/principal.py:_explorer` — en fait un
    `forcer_nu`. Il n'y a pas d'autre usage, et il ne doit pas y en avoir un
    qui se contente de la valeur de retour sans peindre derriere : reposer le
    bit est un effet sur le terminal de quelqu'un.
    """
    if not systeme.plateforme.startswith("win"):
        return True
    console = systeme.console
    if console is None:
        return False
    handle = HANDLES[systeme.nom_du_flux]
    try:
        mode = console.lire_mode(handle)
        if mode is None:
            return False
        if mode & VT_SORTIE:
            return True
        if not console.poser_mode(handle, mode | VT_SORTIE):
            return False
        verification = console.lire_mode(handle)
    except Exception:                      # noqa: BLE001 — voir ci-dessous
        # Meme regle que `_appeler` : ce module ne laisse pas kernel32 tuer
        # le programme. Une exploration qui a une session SAP ouverte ne doit
        # pas mourir sur un appel de confort d'affichage.
        return False
    return bool(verification is not None and verification & VT_SORTIE)


def _ansi_posix(systeme: Systeme, motifs: list[str]) -> tuple[bool, str]:
    """Ce que POSIX permet de savoir, c'est-a-dire moins que sur Windows.

    Il n'existe aucun appel qui reponde « j'interprete les sequences ». Les
    deux faits disponibles sont `isatty()` — deja lu par l'appelant — et
    `TERM`, qui est une declaration de l'hote. Le motif dit donc toujours
    laquelle des deux a tranche : personne ne doit pouvoir lire « ANSI oui »
    sans voir d'ou ca sort.

    **Et la provenance rendue est DECLAREE, pas MESUREE.** C'est ce mot qui
    empeche la page de `falcon sonde` de jurer qu'un appel systeme a prouve ce
    que seule une variable affirme. Un `TERM` herite d'une session ssh, d'un
    `env -i TERM=xterm` ou d'un editeur donne alors « oui », et la page ecrit a
    cote « declare par TERM, non mesure ». Le refus est le meme, la phrase est
    vraie.

    `TERM` vient de l'environnement : il peut porter n'importe quel octet, et
    il finit dans une page qui promet cp1252. Il passe donc par `_lisible`.
    """
    terme = systeme.variables.get("TERM", "")
    if not terme:
        motifs.append("TERM n'est pas defini : rien ne declare ce terminal")
        return False, DECLAREE
    if terme == "dumb":
        motifs.append("TERM=dumb : le terminal se declare sans capacite")
        return False, DECLAREE
    motifs.append(_lisible(f"TERM={terme} declare par l'hote "
                           f"(POSIX ne mesure pas)"))
    return True, DECLAREE


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
        # `isatty()` EST un appel systeme : le « non » est mesure, meme si
        # rien n'a interroge de console.
        ansi, source_ansi = False, MESUREE
    elif systeme.plateforme.startswith("win"):
        ansi, source_ansi = _ansi_windows(systeme, motifs)
    else:
        ansi, source_ansi = _ansi_posix(systeme, motifs)

    couleur = ansi
    if ansi and systeme.variables.get("NO_COLOR", ""):
        # Une convention, et elle se respecte sans discuter : celui qui la pose
        # a deja dit ce qu'il voulait. On garde `ansi` vrai — il est mesure —
        # et on refuse la couleur, qui est un choix.
        motifs.append("NO_COLOR est pose : la couleur est refusee par "
                      "l'environnement")
        couleur = False

    encodage = _lisible(systeme.encodage)
    if not encodage:
        # On garde la chaine vide. Poser `ENCODAGE_MINIMAL` ici ferait imprimer
        # « encodage de sortie cp1252 » sur une machine Linux en UTF-8, sous
        # une etiquette qui dit « ce qui a ete mesure » — un defaut de confort
        # qui se fait passer pour un releve.
        motifs.append("le flux ne declare aucun encodage : rien n'a ete lu "
                      "sur ce point")

    return Capacites(
        flux=systeme.nom_du_flux,
        interactif=systeme.isatty,
        colonnes=colonnes,
        lignes=lignes,
        source_taille=source,
        ansi=ansi,
        source_ansi=source_ansi,
        couleur=couleur,
        encodage=encodage,
        motifs=tuple(motifs),
    )


#: Ce que `falcon sonde` dit une fois pour toutes les deux sondes.
#:
#: Ecrit ici et pas dans les deux appelants — la CLI et l'ecran de console — :
#: un texte normatif recopie a deux endroits derive au premier amendement, et
#: c'est alors la moitie des lecteurs qui lit la version perimee.
NOTE_DE_LECTURE = (
    "  Ce qui est marque « mesure » sort d'un appel systeme fait dans ce",
    "  processus-ci, et la colonne de droite nomme lequel. Ce qui est marque",
    "  « declare » est la parole de l'hote — TERM, COLUMNS, LINES — qu'aucun",
    "  appel ne verifie et qu'on ne peut que croire.",
    "",
    "  Sur POSIX, ANSI ne se mesure pas : il n'existe aucun appel qui reponde",
    "  « j'interprete les sequences ». Un TERM herite d'un ssh ou d'un",
    "  editeur suffit donc a obtenir la couleur. Si les lignes qui suivent",
    "  sont illisibles, c'est  --sans-couleur.",
)

_MOTS = {True: "oui", False: "non"}
_NIVEAUX = {NU: "NU", COULEUR: "COULEUR"}

#: Ce que la colonne de droite ecrit a cote d'un verdict ANSI.
#:
#: La phrase est longue a dessein : c'est la seule ligne de la page qui dise
#: la difference entre « une console l'a prouve » et « une variable le dit »,
#: et c'est cette difference-la qu'on appelle pour trancher.
#: Le mot de MESUREE reste generique a dessein : le meme verdict sort de
#: `isatty()` sur POSIX et du bit VT sur Windows, et ecrire « bit VT » dans le
#: premier cas serait un releve faux — le defaut exact que cette colonne
#: existe pour empecher. Le motif, lui, nomme l'appel exact.
_PROVENANCE_ANSI = {
    MESUREE: "appel systeme, voir les motifs",
    DECLAREE: "declare par TERM, non mesure",
    INCONNUE: "rien n'a pu etre interroge",
}


def _ligne(etiquette: str, valeur: str, note: str = "") -> str:
    """Une ligne du releve : etiquette, valeur, et d'ou elle sort.

    La valeur est TRONQUEE a sa colonne. Un nom d'encodage exotique rendu par
    `flux.encoding` deborderait sinon la page sans qu'aucun test ne le voie —
    les cas du banc portent tous des noms courts.
    """
    corps = f"    {etiquette:<20} {_lisible(couper(valeur, 15)):<15}"
    return (corps + _lisible(note)).rstrip() if note else corps.rstrip()


def rendre_capacites(capacites: Capacites) -> tuple[str, ...]:
    """Ce qu'imprime `falcon sonde`. Fonction PURE, cp1252, sans sequence.

    Le bloc des motifs n'est pas un ornement : c'est la moitie utile du releve
    quand quelque chose ne marche pas. Une sonde qui ecrirait « ANSI non » sans
    dire lequel des quatre chemins a refuse obligerait a deviner a distance,
    ce qui est exactement le service qu'elle existe pour rendre inutile.

    **Le « cp1252 » de la premiere ligne est une propriete, pas un espoir.**
    Cette page interpole deux textes venus du monde — la valeur de `TERM` et le
    `strerror` d'une `OSError`, que Windows localise — et un `Capacites`
    construit a la main peut en porter n'importe lequel. Tout ce qui sort d'ici
    repasse donc par `_lisible`. C'est un doublon assume avec l'assainissement
    fait a l'entree des motifs : l'autre protege `Capacites.motifs`, qui part
    aussi dans le message de `RenduRefuse` ; celui-ci protege la promesse
    ecrite juste au-dessus, et c'est cette fonction-ci qui la fait.

    **Chaque verdict porte sa provenance.** « ANSI oui » seul serait, sur
    POSIX, une certitude la ou il n'y a qu'une declaration : `falcon sonde`
    est la commande qu'on lance PARCE QU'ON DOUTE, elle ne peut pas etre celle
    qui affirme le plus.
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
        _ligne("ANSI", _MOTS[capacites.ansi],
               _PROVENANCE_ANSI.get(capacites.source_ansi, "")),
        # « 16 couleurs » etait un releve d'apparence : rien n'a jamais compte
        # de couleurs, ni sur Windows — le bit VT prouve l'interpretation de
        # SGR, pas la palette — ni sur POSIX, ou c'est TERM. C'est une
        # INTENTION, et elle s'ecrit comme telle.
        _ligne("couleur", _MOTS[capacites.couleur],
               "seize couleurs seront emises" if capacites.couleur else ""),
        _ligne("encodage de sortie", capacites.encodage or "inconnu"),
        _ligne("niveau retenu", _NIVEAUX[capacites.niveau]),
    ]
    if capacites.motifs:
        lignes.append("    ce qui a ete appele, et ce qu'il a repondu :")
        for motif in capacites.motifs:
            # Un motif porte un message d'OSError ou une valeur de TERM :
            # sa longueur n'est pas la notre. On le REPLIE, on ne le coupe
            # pas — c'est la seule ligne de cette page dont on ne peut rien
            # jeter sans perdre precisement ce qu'on est venu lire.
            lignes += textwrap.wrap(_lisible(motif),
                                    width=LARGEUR_DE_PAGE - 6,
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

    **TROIS cas, et pas deux — d'ou `source` et pas un booleen.** Un booleen
    obligerait a ranger la declaration avec l'ignorance ou avec la mesure, et
    les deux choix mentent :

      - `MESUREE` — `os.get_terminal_size` a repondu. `colonnes` vaut cette
        mesure, moins une, bornee par `LARGEUR_PLAFOND`.
      - `DECLAREE` — la mesure a echoue et `COLUMNS`/`LINES` etaient poses.
        `colonnes` vaut cette declaration, moins une, bornee de meme. Une vue
        qui met en page 109 colonnes dans une fenetre de 80 replie chaque
        ligne, et le repli est precisement ce que la marge d'une colonne
        existe pour eviter : la vue doit pouvoir lire que personne n'a verifie.
      - `INCONNUE` — rien n'a su dire. `colonnes` vaut 72, ce qui n'est pas
        une supposition sur la fenetre mais le cadre que `console/menu.py:41`
        garantit deja partout. Le contraire — 80x24 devine — est mesurablement
        un mensonge.

    `mesuree` reste lisible, comme PROPRIETE : c'est la question que pose une
    vue qui veut annoncer « largeur non mesuree », et elle ne doit jamais
    pouvoir se poser a la construction.

    **`lignes` se justifie a part, et moins bien que `colonnes`.** Faute de
    mesure elle vaut 24, alors que le cmd.exe par defaut en fait 25 : c'est
    delibere, une page d'une ligne trop courte se lit entierement, une page
    d'une ligne trop longue fait defiler l'en-tete qui dit ou l'on est. Le
    choix est conservateur dans le sens ou la perte est visible. Largeur et
    hauteur partagent une seule `source` parce qu'elles partagent un seul
    appel : `os.get_terminal_size` les rend ensemble ou pas du tout.

    **Aucun plancher ne surpasse jamais une mesure plus petite.** Une mesure a
    60 donne 59, pas 72 : reprocher a `shutil` son repli suppose puis faire le
    meme geste dans l'autre sens serait la meme faute.
    """

    colonnes: int = LARGEUR_SANS_MESURE
    lignes: int = HAUTEUR_SANS_MESURE
    source: str = INCONNUE
    niveau: int = NU

    @property
    def mesuree(self) -> bool:
        """Vrai pour la SEULE provenance qui soit un appel systeme."""
        return self.source == MESUREE

    @property
    def trop_etroit(self) -> bool:
        return self.colonnes < LARGEUR_PLANCHER


def gabarit_pour(capacites: Capacites, *, forcer_nu: bool = False) -> Gabarit:
    """Des capacites vers la geometrie qu'on peindra vraiment.

    `forcer_nu` est le `--sans-couleur` de la ligne de commande : un refus que
    l'utilisateur pose sans avoir a l'argumenter. Il ne touche pas a la
    largeur — refuser la couleur n'est pas refuser de savoir ou finit l'ecran.

    **La provenance passe la frontiere avec la valeur.** Sans elle, une
    declaration `COLUMNS=300` oubliee dans un profil deviendrait ici une
    largeur de 109 indiscernable d'une mesure, et plus aucune vue ne pourrait
    faire la difference entre « 72, je ne sais rien » et « 109, quelqu'un a
    dit 300 ».

    **Jamais moins d'une colonne.** Une mesure a 1 donnerait zero, et
    `PeintreNu.peindre` leverait « largeur de coupe absurde : 0 » en plein
    rendu. Ce plancher-la ne surpasse aucune mesure — il refuse de rendre une
    largeur qui n'en est pas une — et `trop_etroit` reste le vrai garde-fou :
    a une colonne il est vrai, et la vue doit refuser d'elle-meme.
    """
    niveau = NU if forcer_nu else capacites.niveau
    if capacites.colonnes is None or capacites.lignes is None:
        return Gabarit(niveau=niveau, source=capacites.source_taille)
    return Gabarit(colonnes=max(min(capacites.colonnes,
                                    LARGEUR_PLAFOND) - 1, 1),
                   lignes=max(capacites.lignes, 1),
                   source=capacites.source_taille,
                   niveau=niveau)
