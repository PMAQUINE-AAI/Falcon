"""Les ecrans de la console FALCON.

Trois domaines, et un seul principe qui les traverse : **rien ici n'ecrit dans
SAP.** La branche SAP ne manipule qu'un `DriverLecture`, la facade qui n'a ni
`write`, ni `press`, ni `vkey`. Ce n'est pas une consigne de relecture — les
methodes n'existent pas sur l'objet, et un ajout distrait leverait un
`AttributeError` avant toute session reelle.

**Tout ce qui vient de l'exterieur est injecte** par `Environnement` : le
lanceur de sous-processus et l'ouverture de session SAP. C'est ce qui permet
a la suite de jouer une session complete de console — y compris la branche
SAP, contre le double — sans lancer les 380 tests dans un test, et sans
Windows.

Les choix de fichier se font dans une liste **decouverte sur le disque**,
jamais par un nom construit a la volee : la console ne doit pas offrir de
chemin par lequel une saisie deviendrait un module importe ou une commande
executee. Les sous-processus sont lances par liste d'arguments, jamais par le
shell.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .menu import CONTINUER, Console, Entree, Menu

RACINE = Path(__file__).resolve().parent.parent.parent

#: Repertoire des traces livrees avec le depot.
FIXTURES = RACINE / "tests" / "fixtures" / "traces"


def _lancer(arguments: list[str]) -> tuple[int, str]:
    """Execute un outil du depot et rend (code, sortie fusionnee).

    Liste d'arguments, jamais `shell=True` : rien de ce que l'utilisateur
    tape ne doit pouvoir atteindre un interpreteur de commandes.
    """
    fini = subprocess.run([sys.executable, *arguments], cwd=RACINE,
                          capture_output=True, text=True)
    return fini.returncode, (fini.stdout or "") + (fini.stderr or "")


def _connecter() -> Any:
    """Ouvre une session SAP. Importe pywin32 seulement ici."""
    from falcon.couture.sapgui import connecter
    return connecter()


@dataclass(frozen=True)
class Environnement:
    """Ce que la console emprunte au monde exterieur.

    Injecte pour etre remplacable en test. Le defaut est le vrai.
    """

    racine: Path = RACINE
    lancer: Callable[[list[str]], tuple[int, str]] = _lancer
    connecter: Callable[[], Any] = _connecter
    fixtures: Path = field(default=FIXTURES)


# ---------------------------------------------------------------------------
# Choix
# ---------------------------------------------------------------------------

def choisir(console: Console, titre: str,
            options: list[tuple[str, str]],
            *, invite_libre: str = "") -> str | None:
    """Presente des options numerotees. Rend la valeur choisie, ou None.

    Les options sont fournies par l'appelant, qui les a decouvertes sur le
    disque. La console ne fabrique aucun chemin a partir d'une saisie libre
    sans que l'appelant l'ait explicitement demande.
    """
    console.section(titre)
    for rang, (_, libelle) in enumerate(options, start=1):
        console.ecrire(f"    {rang:>2}  {libelle}")
    if invite_libre:
        console.ecrire(f"     s  {invite_libre}")
    console.ecrire("     0  annuler")

    try:
        saisie = console.lire().strip()
    except (EOFError, KeyboardInterrupt):
        return None

    if saisie in ("", "0"):
        return None
    if invite_libre and saisie.lower() == "s":
        try:
            return console.lire("     chemin : ").strip() or None
        except (EOFError, KeyboardInterrupt):
            return None
    if saisie.isdigit() and 1 <= int(saisie) <= len(options):
        return options[int(saisie) - 1][0]
    console.ecrire(f"\n  « {saisie} » n'est pas dans la liste.")
    return None


def _traces(env: Environnement) -> list[tuple[str, str]]:
    return [(str(c), f"{c.name}  ({c.stat().st_size} o)")
            for c in sorted(env.fixtures.glob("*.vbs"))]


def _suites(env: Environnement) -> list[tuple[str, str]]:
    dossier = env.racine / "tests"
    return [(f"tests.{c.stem}", c.name)
            for c in sorted(dossier.glob("test_*.py"))]


def _trace_choisie(console: Console, env: Environnement):
    """Demande une trace et la lit STRICTEMENT. Rend la trace, ou None."""
    from falcon.trace import TraceInvalide, lire

    chemin = choisir(console, "Quelle trace ?", _traces(env),
                     invite_libre="saisir un autre chemin")
    if chemin is None:
        return None
    try:
        return lire(chemin)
    except TraceInvalide as erreur:
        console.ecrire(f"\n  Lecture refusee.\n\n  {erreur}\n")
        console.ecrire("  L'inventaire, lui, lit ce qu'il peut et nomme le "
                       "reste.")
        return None


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _rendre_sortie(console: Console, code: int, sortie: str) -> None:
    console.ecrire()
    for ligne in sortie.rstrip().splitlines():
        console.ecrire(f"  | {ligne}")
    console.ecrire()
    console.ecrire(f"  code de retour : {code}"
                   f"{'   — vert' if code == 0 else '   — ECHEC'}")


def ecran_verification(env: Environnement) -> Menu:

    def tout(console: Console) -> str:
        console.titre("Verification — les deux suites")
        _rendre_sortie(console, *env.lancer(["outils/verifier.py"]))
        console.pause()
        return CONTINUER

    def gardes(console: Console) -> str:
        console.titre("Chaque garde retiree doit faire tomber la suite")
        console.ecrire()
        console.ecrire("  Une garde couverte par des tests qui passent n'est "
                       "pas une garde")
        console.ecrire("  verifiee : le test passerait aussi si la garde ne "
                       "faisait rien.")
        _rendre_sortie(console, *env.lancer(["outils/neutraliser.py"]))
        console.pause()
        return CONTINUER

    def une_suite(console: Console) -> str:
        module = choisir(console, "Quelle suite ?", _suites(env))
        if module is None:
            return CONTINUER
        console.titre(module)
        _rendre_sortie(console, *env.lancer(["-m", "unittest", module, "-v"]))
        console.pause()
        return CONTINUER

    return Menu(
        titre="FALCON — verification",
        preambule="Les deux commandes du protocole de travail, plus le detail "
                  "suite par suite.",
        entrees=(
            Entree("1", "Tout verifier", tout,
                   "les deux suites, FALCON et l'archive ; dit aussi ce qui "
                   "n'a PAS ete verifie"),
            Entree("2", "Les gardes sont-elles protegees ?", gardes,
                   "retire chaque garde et exige que la suite tombe"),
            Entree("3", "Une suite au choix", une_suite,
                   "detail test par test"),
        ))


# ---------------------------------------------------------------------------
# Traces
# ---------------------------------------------------------------------------

def ecran_traces(env: Environnement) -> Menu:

    def inventaire(console: Console) -> str:
        from falcon.trace import inventorier
        from falcon.trace.inventaire import rapport

        chemin = choisir(console, "Quelle trace ?", _traces(env),
                         invite_libre="saisir un autre chemin")
        if chemin is None:
            return CONTINUER
        console.titre("Couverture du parseur")
        console.ecrire()
        console.ecrire(rapport(inventorier(chemin)))
        console.pause()
        return CONTINUER

    def ecrans(console: Console) -> str:
        from falcon.trace.esquisse import esquisses, visites

        trace = _trace_choisie(console, env)
        if trace is None:
            return CONTINUER
        console.titre("Ecrans conjectures")
        console.ecrire()
        console.ecrire("  Une trace ne dit ni l'identite des ecrans ni les "
                       "champs presents.")
        console.ecrire("  Ce qui suit est une liste de ce qu'il reste a aller "
                       "observer.")
        console.ecrire()
        for visite in visites(trace):
            lignes = f"l.{visite.gestes[0].ligne}-{visite.gestes[-1].ligne}"
            console.ecrire(f"  {visite.ordre:>3}  {visite.fenetre}  "
                           f"{(visite.transaction or '-'):<8} {lignes:<12}"
                           f"{len(visite.cibles)} champ(s) touche(s)")
            for cible in visite.cibles:
                console.ecrire(f"         {cible}")
        console.ecrire()
        console.ecrire(f"  {len(esquisses(trace))} esquisse(s) apres "
                       f"dedoublonnage sur la clef.")
        console.pause()
        return CONTINUER

    def gestes(console: Console) -> str:
        trace = _trace_choisie(console, env)
        if trace is None:
            return CONTINUER
        console.titre("Gestes significatifs")
        console.ecrire()
        for geste in trace.significatifs:
            valeur = "" if geste.valeur is None else f" = {geste.valeur!r}"
            console.ecrire(f"  l.{geste.ligne:>4}  {geste.fenetre}  "
                           f"{geste.verbe:<24}{valeur}")
            console.ecrire(f"          {geste.cible}")
        console.ecrire()
        console.ecrire(f"  {len(trace.significatifs)} significatif(s) sur "
                       f"{len(trace.gestes)} geste(s).")
        console.ecrire("  Les gestes de confort — focus, curseur, "
                       "agrandissement — sont conserves")
        console.ecrire("  mais ecartes d'ici : ils ne changent rien dans SAP.")
        console.pause()
        return CONTINUER

    return Menu(
        titre="FALCON — traces du recorder",
        preambule="Lecture seule d'enregistrements .vbs. Rien n'est ecrit.",
        entrees=(
            Entree("1", "Couverture du parseur", inventaire,
                   "ce qu'il sait lire, et ce qu'il n'en sait pas"),
            Entree("2", "Ecrans conjectures", ecrans,
                   "decoupage en visites, et champs touches"),
            Entree("3", "Gestes significatifs", gestes,
                   "la trace, sans les gestes de confort"),
        ))


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

def ecran_catalogue(env: Environnement) -> Menu:

    def _depot(console: Console):
        from falcon.catalogue import Depot

        try:
            saisie = console.lire("\n  dossier du catalogue : ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not saisie:
            return None
        chemin = Path(saisie)
        if not chemin.is_dir():
            console.ecrire(f"\n  {chemin} n'est pas un dossier.")
            return None
        return Depot(chemin)

    def _lister(console: Console, depot, quoi: str) -> None:
        triplets = list(depot.triplets())
        console.ecrire()
        if not triplets:
            console.ecrire(f"  {quoi} : vide.")
            return
        for triplet in triplets:
            variantes = depot.variantes(triplet)
            console.ecrire(f"  {'/'.join(triplet)}   "
                           f"{len(variantes)} variante(s)")
            for variante in variantes:
                marque = ("observee" if variante.observee
                          else "ESQUISSE — ne peut pas garder un ecran")
                console.ecrire(f"      {variante.clef.empreinte}  "
                               f"{len(variante.champs):>3} champ(s)  {marque}")

    def cure(console: Console) -> str:
        depot = _depot(console)
        if depot is None:
            return CONTINUER
        console.titre("Catalogue cure")
        _lister(console, depot, "Catalogue")
        console.pause()
        return CONTINUER

    def quarantaine(console: Console) -> str:
        from falcon.catalogue import Depot

        depot = _depot(console)
        if depot is None:
            return CONTINUER
        console.titre("Quarantaine")
        console.ecrire()
        console.ecrire("  Ce qui n'a ete relu par personne. La promotion est "
                       "un geste explicite :")
        console.ecrire("  celui par lequel un humain dit avoir regarde "
                       "l'ecran.")
        _lister(console, Depot(depot.quarantaine), "Quarantaine")
        console.pause()
        return CONTINUER

    return Menu(
        titre="FALCON — catalogue d'ecrans",
        preambule="Lecture seule. La promotion d'une capture reste un geste "
                  "delibere,\net ne se fait pas depuis ici.",
        entrees=(
            Entree("1", "Catalogue cure", cure, "ce qu'un humain a valide"),
            Entree("2", "Quarantaine", quarantaine,
                   "les captures pas encore relues"),
        ))


# ---------------------------------------------------------------------------
# SAP
# ---------------------------------------------------------------------------

def ecran_sap(env: Environnement) -> Menu:

    def _diagnostiquer(console: Console, catalogue: str | None) -> str:
        from falcon.commandes.diagnostic import diagnostiquer
        from falcon.couture import DriverLecture
        from falcon.noyau import ErreurFalcon

        try:
            driver = env.connecter()
        except ErreurFalcon as erreur:
            console.ecrire(f"\n  {type(erreur).__name__} : {erreur}")
            console.pause()
            return CONTINUER

        # Le driver brut ne franchit pas cette ligne : la console ne manipule
        # qu'une facade sans `write`, sans `press` et sans `vkey`.
        lecteur = DriverLecture(driver)
        console.titre("Diagnostic — lecture seule")
        console.ecrire()
        console.ecrire(diagnostiquer(lecteur, catalogue=catalogue))
        console.pause()
        return CONTINUER

    def regarder(console: Console) -> str:
        return _diagnostiquer(console, None)

    def relever(console: Console) -> str:
        try:
            dossier = console.lire("\n  dossier du catalogue : ").strip()
        except (EOFError, KeyboardInterrupt):
            return CONTINUER
        if not dossier:
            return CONTINUER
        return _diagnostiquer(console, dossier)

    return Menu(
        titre="FALCON — session SAP (LECTURE SEULE)",
        preambule=(
            "Se greffe sur une session que vous avez ouverte et sur laquelle\n"
            "vous vous etes authentifie vous-meme. Aucun mot de passe ne\n"
            "transite par FALCON, et rien d'ici ne peut ecrire dans SAP.\n"
            "\n"
            "Exige Windows, pywin32, et le scripting autorise des deux cotes."),
        entrees=(
            Entree("1", "Diagnostiquer l'ecran courant", regarder,
                   "identite, fenetres, statut, releve des champs"),
            Entree("2", "Diagnostiquer et verser en quarantaine", relever,
                   "le releve devient une capture a relire"),
        ))


# ---------------------------------------------------------------------------

def racine(env: Environnement | None = None) -> Menu:
    env = env or Environnement()
    return Menu(
        titre="FALCON — console",
        preambule=(
            "Automatisation SAP Front End. Aucune commande de cette console\n"
            "n'ecrit dans SAP."),
        entrees=(
            Entree("1", "Verification", ecran_verification(env),
                   "les suites, et la preuve que les gardes protegent"),
            Entree("2", "Traces du recorder", ecran_traces(env),
                   "couverture du parseur, ecrans conjectures, gestes"),
            Entree("3", "Catalogue d'ecrans", ecran_catalogue(env),
                   "variantes curees et quarantaine"),
            Entree("4", "Session SAP", ecran_sap(env),
                   "diagnostic de l'ecran courant, en lecture seule"),
        ))
