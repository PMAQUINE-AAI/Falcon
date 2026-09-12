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


def depuis_le_depot() -> bool:
    """Tourne-t-on sur l'arborescence source, ou depuis `falcon.pyz` ?

    Deux branches de la console — « Verification » et « Traces » — lisent des
    choses qui n'existent QUE dans le depot : les suites de tests, les outils,
    et les traces d'exemple. Depuis le bundle, `Path(__file__)` designe un
    chemin A L'INTERIEUR de l'archive : `RACINE` vaut le fichier `.pyz`
    lui-meme, et `FIXTURES` ne designe rien.

    Mesure avant ce controle, sur la livraison que le README recommande : le
    lancement d'un outil recevait `cwd=<un fichier>`, et la liste des traces
    etait vide sans un mot. Deux branches cassees, dont l'une s'appelle
    « Verification » — c'est-a-dire celle a laquelle on demande si tout va
    bien.

    Le bon comportement n'est pas de les faire marcher — le depot n'est pas
    la, et l'embarquer serait absurde — c'est de le DIRE.
    """
    return RACINE.is_dir() and (RACINE / "outils").is_dir()


#: Ce qu'on affiche quand une branche exige le depot et qu'on est dans le
#: bundle. Un message qui nomme la cause et la sortie, pas une liste vide.
SANS_DEPOT = (
    "Cette branche lit des fichiers du DEPOT — les suites de tests, les\n"
    "outils, les traces d'exemple — et tu tournes depuis `falcon.pyz`,\n"
    "qui ne les embarque pas (et n'a aucune raison de le faire).\n"
    "\n"
    "Pour t'en servir, lance FALCON depuis le depot :\n"
    "    python -m falcon console")


def _lancer(arguments: list[str]) -> tuple[int, str]:
    """Execute un outil du depot et rend (code, sortie fusionnee).

    Liste d'arguments, jamais `shell=True` : rien de ce que l'utilisateur
    tape ne doit pouvoir atteindre un interpreteur de commandes.
    """
    if not depuis_le_depot():
        # `cwd=RACINE` recevrait le chemin du `.pyz`, qui n'est pas un
        # dossier : `subprocess` leve alors une `NotADirectoryError` que rien
        # n'attrape, sur un ecran qui s'appelle « Verification ».
        return 1, SANS_DEPOT
    fini = subprocess.run([sys.executable, *arguments], cwd=RACINE,
                          capture_output=True, text=True)
    return fini.returncode, (fini.stdout or "") + (fini.stderr or "")


def _rapporteur() -> Any:
    """L'observateur de progression du lot 11. Muet hors terminal."""
    from falcon.supervision import Rapporteur
    return Rapporteur()


def _connecter() -> Any:
    """Ouvre une session SAP. Importe pywin32 seulement ici."""
    from falcon.couture.sapgui import connecter
    return connecter()


def _sonder_les_flux() -> tuple[Any, ...]:
    """Mesure les DEUX flux de sortie, ici et maintenant.

    Les deux, parce que sur Windows la capacite a interpreter une sequence est
    un mode par HANDLE : ce qui est vrai de la sortie standard ne dit rien de
    l'erreur standard. Le prix d'une seconde mesure est deux appels systeme.

    C'est le seul endroit de la console qui touche le terminal, et il est
    injecte comme le lanceur de sous-processus et l'ouverture de session : ce
    que l'ecran AFFICHE doit etre la vraie mesure, et ce qu'une suite lui joue
    doit pouvoir etre un terminal qui n'existe pas.
    """
    from falcon.toile import sonder, systeme_reel
    return tuple(sonder(systeme_reel(flux, nom))
                 for flux, nom in ((sys.stdout, "stdout"),
                                   (sys.stderr, "stderr")))


@dataclass(frozen=True)
class Environnement:
    """Ce que la console emprunte au monde exterieur.

    Injecte pour etre remplacable en test. Le defaut est le vrai.
    """

    racine: Path = RACINE
    lancer: Callable[[list[str]], tuple[int, str]] = _lancer
    connecter: Callable[[], Any] = _connecter
    fixtures: Path = field(default=FIXTURES)
    #: Fabrique l'observateur de progression branche sur le moteur. La barre
    #: et l'ETA glissant existent depuis le lot 11 et n'avaient jamais rien
    #: affiche : personne ne les appelait.
    rapporteur: Callable[[], Any] = _rapporteur
    #: Le releve des deux flux de sortie. Ce que « Sonder ce terminal »
    #: montre, et rien d'autre : aucun ecran ne s'en sert pour DECIDER quoi
    #: que ce soit. La sonde RAPPORTE, elle ne choisit rien, et c'est ce qui
    #: permet d'en garder la vraie pour defaut — « le defaut est le vrai ».
    #:
    #: **C'est en revanche la SEULE surface de la console dont le rendu
    #: depende de la machine qui l'execute**, et il faut le savoir avant
    #: d'ecrire un test : aucun test ne doit asserter le CONTENU de cet ecran
    #: sans injecter sa propre sonde, sinon il sera vert dans un tube et rouge
    #: dans un terminal, pour un motif sans rapport avec ce qu'il teste. Le
    #: test de fumee qui parcourt tout l'arbre en injecte une inerte pour
    #: cette raison.
    #:
    #: AVERTISSEMENT POUR LE LOT QUI PEINDRA : `capacites` sera un AUTRE
    #: champ, et son defaut devra rester `Capacites()` — tout faux. Les deux
    #: ne se fusionnent pas : celui-ci RAPPORTE une mesure a l'ecran, l'autre
    #: DECIDERAIT ce que la console a le droit d'emettre, et le rendu de toute
    #: la console dependrait alors du terminal de qui lance la suite.
    sonde: Callable[[], tuple[Any, ...]] = _sonder_les_flux


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


def demander_chemin(console: Console, invite: str, *,
                    existant: bool = True) -> Path | None:
    """Demande un chemin de fichier ou de dossier. Rend None si on renonce.

    Le chemin est LU, jamais construit : la console ne fabrique pas de nom a
    partir d'un morceau saisi. Ce qu'on en fait ensuite est toujours une
    lecture — c'est la branche appelante qui en repond.

    `existant=False` pour un journal : il est append-only et partage entre
    executions, donc il peut aussi bien exister deja que naitre ici. Exiger
    l'un ou l'autre serait faux dans la moitie des cas.
    """
    try:
        saisie = console.lire(f"\n  {invite} : ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not saisie:
        return None
    chemin = Path(saisie)
    if existant and not chemin.exists():
        console.ecrire(f"\n  {chemin} n'existe pas.")
        return None
    return chemin


def demander_chemin_facultatif(console: Console, invite: str) -> Path | None:
    """Un chemin dont l'absence est une reponse valide, pas un renoncement.

    `demander_chemin` rend `None` aussi bien pour « rien saisi » que pour
    « annule », et ses appelants lisent les deux comme un abandon. Pour une
    surcouche de registre, ne rien saisir est le cas NORMAL — on n'en a une
    que quand on en a recolte une.
    """
    try:
        saisie = console.lire(f"\n  {invite} : ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not saisie:
        return None
    chemin = Path(saisie)
    if not chemin.exists():
        console.ecrire(f"\n  {chemin} n'existe pas — poursuite sans surcouche.")
        return None
    return chemin


def demander_chemin_neuf(console: Console, invite: str) -> Path | None:
    """Demande un chemin a ECRIRE. Refuse un fichier qui existe deja.

    Le seul endroit de la console qui produise un fichier. Ecraser en silence
    un export precedent ferait perdre un travail qu'on ne peut pas refaire :
    le journal dont il vient est peut-etre le seul temoin de ce qui s'est
    passe. Refuser coute une saisie ; ecraser coute la trace.
    """
    try:
        saisie = console.lire(f"\n  {invite} : ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not saisie:
        return None
    chemin = Path(saisie)
    if chemin.exists():
        console.ecrire(f"\n  {chemin} existe deja. Choisis un autre nom : "
                       "rien ici n'ecrase.")
        return None
    return chemin


def _traces(env: Environnement) -> list[tuple[str, str]]:
    """Les traces livrees avec le DEPOT. Vide depuis le bundle, et c'est normal.

    `Path.glob` sur un dossier inexistant rend une suite vide sans lever : la
    liste etait donc vide depuis `falcon.pyz`, sans un mot, et l'utilisateur
    en concluait qu'il n'y avait aucune trace. C'est l'ecran appelant qui doit
    le dire — voir `SANS_DEPOT`.
    """
    if not env.fixtures.is_dir():
        return []
    return [(str(c), f"{c.name}  ({c.stat().st_size} o)")
            for c in sorted(env.fixtures.glob("*.vbs"))]


def _suites(env: Environnement) -> list[tuple[str, str]]:
    dossier = env.racine / "tests"
    if not dossier.is_dir():
        return []
    return [(f"tests.{c.stem}", c.name)
            for c in sorted(dossier.glob("test_*.py"))]


def _trace_choisie(console: Console, env: Environnement):
    """Demande une trace et la lit STRICTEMENT. Rend la trace, ou None.

    Une trace se saisit toujours au chemin, meme sans depot : c'est la
    branche entiere qui n'aurait aucune trace A PROPOSER, pas la lecture qui
    serait impossible. On le dit, et on laisse saisir.
    """
    from falcon.trace import TraceInvalide, lire

    livrees = _traces(env)
    if not livrees:
        console.ecrire()
        for ligne in SANS_DEPOT.splitlines():
            console.ecrire(f"  {ligne}")
        console.ecrire()
        console.ecrire("  Tu peux tout de meme saisir le chemin d'une trace.")

    chemin = choisir(console, "Quelle trace ?", livrees,
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

    def sonde(console: Console) -> str:
        """Ce que CE terminal sait faire, mesure a l'instant ou on le demande.

        L'ecran est dans « Verification et livraison » et pas ailleurs : c'est
        une verification, au meme titre que les suites et le neutraliseur. La
        difference est qu'elle porte sur la machine et non sur le code, et
        c'est la seule de la console dans ce cas.

        **La mesure est enveloppee, comme `env.connecter()` l'est deja.** Le
        chemin Windows passe par `ctypes` et par des handles de console ; un
        accident doit couter CET ecran, jamais la session, avec tout ce qu'on
        avait sous les yeux. Et c'est la page qu'on ouvre quand quelque chose
        ne va deja pas.
        """
        from falcon.toile import rendre_sonde

        console.titre("Sonder ce terminal")
        console.ecrire()
        try:
            releves = env.sonde()
        except Exception as erreur:                    # noqa: BLE001
            console.ecrire(f"  La sonde elle-meme a echoue : "
                           f"{type(erreur).__name__} : {erreur}")
            console.ecrire("  C'est un renseignement, pas une panne de "
                           "FALCON : note-le et signale-le.")
            console.pause()
            return CONTINUER
        for ligne in rendre_sonde(releves):
            console.ecrire(ligne)
        console.ecrire()
        console.ecrire("  La meme mesure en ligne de commande, celle qu'on "
                       "demande par")
        console.ecrire("  telephone quand un affichage est illisible :")
        console.ecrire("      python -m falcon sonde")
        console.pause()
        return CONTINUER

    def bundle(console: Console) -> str:
        """Construit `falcon.pyz` — la livraison en un seul fichier (§6).

        Le depot est modulaire, la livraison est un fichier unique. La
        contrainte d'autonomie au deploiement se traite A LA CONSTRUCTION, pas
        dans l'organisation du code source.

        Le sous-processus passe par le meme lanceur injecte que les suites :
        liste d'arguments, jamais le shell.
        """
        console.titre("Construire le bundle")
        console.ecrire()
        console.ecrire("  PyYAML voyage dans l'archive — c'est du Python pur. "
                       "pywin32 NON :")
        console.ecrire("  une extension binaire liee a une version "
                       "d'interpreteur et a une")
        console.ecrire("  plateforme, figee dans un zip, serait fausse la "
                       "moitie du temps.")
        _rendre_sortie(console, *env.lancer(["outils/embarquer.py"]))
        console.ecrire()
        console.ecrire("  `diagnostiquer` est la seule commande qui exige "
                       "pywin32, et elle le dit")
        console.ecrire("  avec la ligne a taper :  pip install pywin32")
        console.pause()
        return CONTINUER

    return Menu(
        titre="FALCON — verification et livraison",
        preambule="Les deux commandes du protocole de travail, le detail suite "
                  "par suite,\net la construction du livrable.",
        entrees=(
            Entree("1", "Tout verifier", tout,
                   "les deux suites, et ce qui n'a PAS ete verifie"),
            Entree("2", "Les gardes sont-elles protegees ?", gardes,
                   "retire chaque garde et exige que la suite tombe"),
            Entree("3", "Une suite au choix", une_suite,
                   "detail test par test"),
            Entree("4", "Construire le bundle", bundle,
                   "falcon.pyz — un fichier unique executable (§6)"),
            Entree("5", "Sonder ce terminal", sonde,
                   "taille, ANSI, couleur : ce qui est mesure, ce qui est "
                   "seulement declare"),
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

    def ebauche(console: Console) -> str:
        from falcon.trace.brouillon import apercu, brouillon_de

        trace = _trace_choisie(console, env)
        if trace is None:
            return CONTINUER
        brouillon = brouillon_de(trace)
        console.titre("Brouillon de pipeline")
        console.ecrire()
        console.ecrire(apercu(brouillon))
        console.ecrire()
        try:
            sortie = console.lire("\n  ecrire dans (vide = ne rien ecrire) : ")
        except (EOFError, KeyboardInterrupt):
            return CONTINUER
        if sortie.strip():
            Path(sortie.strip()).write_text(brouillon.yaml, encoding="utf-8")
            console.ecrire(f"\n  {sortie.strip()} ecrit.")
        console.pause()
        return CONTINUER

    def explorer(console: Console) -> str:
        return _cartographier(console, env)

    return Menu(
        titre="FALCON — traces du recorder",
        preambule=(
            "Les quatre premieres entrees ne font que lire le fichier .vbs ;\n"
            "le brouillon ecrit un fichier que vous nommez, et rien d'autre.\n"
            "\n"
            "La cinquieme AGIT DANS SAP : elle rejoue la trace sur une\n"
            "session ouverte pour aller observer les ecrans. Elle ne\n"
            "SAUVEGARDE rien. C'est la meme que « 8 > Explorer la trace »."),
        entrees=(
            # « Inventaire » et pas seulement « Couverture du parseur » :
            # c'est le nom de `falcon inventaire`, et deux textes de cette
            # console renvoyaient vers « 2 > Inventaire », qui n'existait pas.
            Entree("1", "Inventaire : couverture du parseur", inventaire,
                   "ce qu'il sait lire, et ce qu'il n'en sait pas"),
            Entree("2", "Ecrans conjectures", ecrans,
                   "decoupage en visites, et champs touches"),
            Entree("3", "Gestes significatifs", gestes,
                   "la trace, sans les gestes de confort"),
            Entree("4", "Brouillon de pipeline", ebauche,
                   "ebauche YAML, inachevee a dessein"),
            # La MEME action que « 8 > 3 », au meme nom, delibere. Elle etait
            # atteignable uniquement sous « Session SAP » : presente, testee,
            # et introuvable pour qui tient un .vbs et cherche quoi en faire.
            # Une fonctionnalite qu'on ne trouve pas ne se distingue pas
            # d'une fonctionnalite absente.
            Entree("5", "Explorer la trace dans SAP", explorer,
                   "AGIT DANS SAP — cartographie les ecrans, sans y ecrire"),
        ))


# ---------------------------------------------------------------------------
# Pipelines et donnees
# ---------------------------------------------------------------------------

def _rendre_pipeline(console: Console, pipeline) -> None:
    """Une pipeline chargee, etape par etape.

    Montre ce que les gardes verront : l'ecran attendu de chaque etape, les
    fenetres qu'elle tolere, le statut qu'elle exige, et les derogations avec
    leur motif. C'est la relecture qu'un humain doit pouvoir faire AVANT de
    lancer quoi que ce soit — pas apres, dans un journal.
    """
    console.ecrire()
    console.ecrire(f"  {pipeline.nom}")
    console.ecrire(f"    classe                {pipeline.classe}")
    console.ecrire(f"    cles                  "
                   f"{', '.join(pipeline.cles) or '(aucune)'}")
    console.ecrire(f"    plafond items         {pipeline.plafond_items}")
    console.ecrire(f"    plafond sauvegardes   {pipeline.plafond_sauvegardes}")
    console.ecrire(f"    empreinte             {pipeline.empreinte}")
    console.ecrire(f"    etapes                {len(pipeline.etapes)}")

    console.ecrire()
    for rang, etape in enumerate(pipeline.etapes, start=1):
        console.ecrire(f"  {rang:>3}  {etape.nom:<24} {etape.action:<8}"
                       f"{etape.cible}")
        details = []
        if etape.ecran:
            details.append("ecran " + "/".join(etape.ecran))
        if etape.navigation_libre:
            details.append("NAVIGATION LIBRE (garde d'identite non posee)")
        if etape.source is not None:
            details.append(f"source {etape.source.genre}: "
                           f"{etape.source.valeur!r}")
            if etape.source.colonnes:
                details.append(f"  colonnes lues : "
                               f"{', '.join(etape.source.colonnes)}")
        if etape.defaut is not None:
            details.append(f"defaut si vide {etape.defaut!r}")
        if etape.format:
            # La valeur tapee n'est plus celle de la colonne : la relecture
            # d'une pipeline doit montrer la transformation, sinon elle montre
            # autre chose que ce qui partira dans SAP.
            details.append("format " + " -> ".join(
                str(transformation) for transformation in etape.format))
        if etape.fonction:
            details.append(f"fonction {etape.fonction}")
        if etape.statut_attendu:
            details.append(f"statut attendu {etape.statut_attendu}")
        if etape.sauvegarde:
            details.append("SAUVEGARDE")
        if tuple(etape.fenetres) != ("wnd[0]",):
            details.append(f"fenetres {list(etape.fenetres)}")
        if etape.comparaison != "casse":
            details.append(f"comparaison {etape.comparaison}")
        for detail in details:
            console.ecrire(f"          {detail}")
        for derogation in etape.derogations:
            console.ecrire(f"          DEROGATION a « {derogation.garde} » "
                           f"({derogation.portee})")
            console.ecrire(f"            {derogation.motif}")

    sauvent = sum(1 for e in pipeline.etapes if e.sauvegarde)
    libres = sum(1 for e in pipeline.etapes if e.navigation_libre)
    derogent = sum(len(e.derogations) for e in pipeline.etapes)
    console.ecrire()
    console.ecrire(f"  {sauvent} etape(s) declarent sauvegarder  |  "
                   f"{libres} en navigation libre  |  "
                   f"{derogent} derogation(s)")
    if libres:
        console.ecrire("  Une navigation libre ne pose PAS la garde "
                       "d'identite. C'est declare, donc")
        console.ecrire("  trace — mais c'est a relire.")


def _rendre_jeu(console: Console, dialecte, lignes: list) -> None:
    console.ecrire()
    console.ecrire("  dialecte lu")
    console.ecrire(f"    format          {dialecte.format}")
    console.ecrire(f"    encodage        {dialecte.encodage}"
                   f"{' + BOM' if dialecte.bom else ''}")
    if dialecte.format == "csv":
        console.ecrire(f"    delimiteur      {dialecte.delimiteur!r}")
        console.ecrire(f"    fins de ligne   {dialecte.fin_de_ligne!r}")
    console.ecrire(f"    colonnes        {len(dialecte.colonnes)}")
    for colonne in dialecte.colonnes:
        console.ecrire(f"      {colonne}")
    console.ecrire(f"    lignes          {len(lignes)}")
    console.ecrire()
    console.ecrire("  Le dialecte lu est celui qui sera reecrit : un fichier "
                   "de KO reinjecte")
    console.ecrire("  garde l'encodage, le delimiteur et l'ordre des colonnes "
                   "d'origine.")


def _provenance(driver) -> dict[str, str]:
    """`systeme` et `mandant`, LUS sur la session ouverte.

    Ils viennent de `screen()`, qui les porte deja : rien de neuf n'est
    demande a la couture, dont la surface est epinglee. Une session qui ne
    les rend pas laisse les champs vides — « on ne sait pas » est une reponse,
    inventer n'en est pas une.
    """
    try:
        identite = driver.screen()
    except Exception:                                # noqa: BLE001
        # La provenance est un CONFORT du journal ; la perdre ne doit pas
        # empecher un lot de tourner. Le journal dira « inconnu ».
        return {}
    return {"systeme": getattr(identite, "systeme", "") or "",
            "mandant": getattr(identite, "mandant", "") or ""}


def _recapituler(console: Console, pipeline, items, jeu: Path,
                 jeu_empreinte: str, mode: str) -> None:
    """Ce qui va se passer, AVANT que ca se passe.

    Tout ce qui borne les degats est ici : les deux plafonds, le nombre
    d'items, et chaque derogation avec son motif. Un recapitulatif qui
    omettrait l'un des deux plafonds laisserait croire que l'autre n'existe
    pas — or c'est celui des sauvegardes qui borne ce qui part dans SAP.
    """
    console.section("Ce qui va se passer")
    console.ecrire(f"    mode                  {mode}")
    console.ecrire(f"    pipeline              {pipeline.nom}")
    console.ecrire(f"    empreinte pipeline    {pipeline.empreinte}")
    console.ecrire(f"    jeu                   {jeu}")
    console.ecrire(f"    empreinte jeu         {jeu_empreinte}")
    console.ecrire(f"    cles                  "
                   f"{', '.join(pipeline.cles) or '(aucune)'}")
    console.ecrire(f"    items a traiter       {len(items)}")
    console.ecrire(f"    PLAFOND items         {pipeline.plafond_items}")
    console.ecrire(f"    PLAFOND sauvegardes   {pipeline.plafond_sauvegardes}")

    sauvent = [e.nom for e in pipeline.etapes if e.sauvegarde]
    libres = [e.nom for e in pipeline.etapes if e.navigation_libre]
    console.ecrire(f"    etapes qui sauvent    "
                   f"{', '.join(sauvent) or '(aucune)'}")

    # Une pipeline qui ne sauvegarde NULLE PART n'ecrit rien dans SAP.
    #
    # `Pipeline.sauvegarde_quelque_part` existait sans aucun appelant, ni en
    # production ni en test. Elle a pourtant un usage evident : c'est presque
    # toujours une erreur de redaction, et le seul moment ou la signaler
    # utilement est celui ou l'on s'apprete a taper le nom pour confirmer. La
    # dire ici coute une ligne ; l'apprendre a la fin d'un lot qui « a
    # marche » coute la confiance dans le lot suivant.
    if mode != "dry-run" and not pipeline.sauvegarde_quelque_part:
        console.ecrire()
        console.ecrire("    ATTENTION : aucune etape ne SAUVEGARDE.")
        console.ecrire("    Ce lot va parcourir SAP sans rien y valider. Si")
        console.ecrire("    tu attendais une ecriture, c'est une etape qui")
        console.ecrire("    manque — pas un lot qui a reussi.")

    composees = [e for e in pipeline.etapes
                 if e.format or e.defaut is not None
                 or (e.source is not None and e.source.genre == "gabarit")]
    if composees:
        console.ecrire(f"    valeurs COMPOSEES     {len(composees)}")
        for etape in composees:
            morceaux = []
            if etape.source is not None and etape.source.genre == "gabarit":
                morceaux.append(f"gabarit {etape.source.valeur!r}")
            if etape.defaut is not None:
                morceaux.append(f"defaut {etape.defaut!r}")
            if etape.format:
                morceaux.append(" -> ".join(str(t) for t in etape.format))
            console.ecrire(f"      {etape.nom} : {' | '.join(morceaux)}")
        console.ecrire("      Ce n'est pas la colonne qui part dans SAP, "
                       "c'est le resultat.")
    if libres:
        console.ecrire(f"    navigation libre      {', '.join(libres)}")
        console.ecrire("      ces etapes ne posent PAS la garde d'identite.")

    derogations = [(e.nom, d) for e in pipeline.etapes
                   for d in e.derogations]
    if derogations:
        console.ecrire(f"    DEROGATIONS           {len(derogations)}")
        for nom, derogation in derogations:
            console.ecrire(f"      {nom} : garde « {derogation.garde} » "
                           f"({derogation.portee})")
            console.ecrire(f"        {derogation.motif}")
    else:
        console.ecrire("    derogations           aucune")


def confirmer(console: Console, attendu: str, *,
              annonce: str = "Ceci va ECRIRE dans SAP.",
              quoi: str = "le nom de la pipeline") -> bool:
    """Confirmation en TOUTES LETTRES. Rend True seulement sur le mot exact.

    Pas un `o/n`. Un `o/n` se tape sans lire — c'est un reflexe, et un reflexe
    n'est pas un consentement. Le mot attendu est le nom de la pipeline : on
    ne peut pas le taper sans avoir lu le recapitulatif qui le nomme, donc
    sans avoir vu au passage les plafonds, le nombre d'items et les
    derogations.

    `annonce` et `quoi` sont des PARAMETRES parce que la cartographie confirme
    autre chose — elle n'ecrit rien mais elle AGIT, et le mot attendu y est le
    nom du fichier de trace. Recopier cette fonction pour en changer la
    premiere phrase donnerait deux confirmations qui divergeraient, et c'est
    la confirmation qui protege ici.

    Toute autre saisie renonce — y compris une saisie vide, une fin de flux ou
    un Ctrl-C. Le defaut est de NE RIEN faire dans un ERP.
    """
    console.ecrire()
    console.ecrire(f"  {annonce}")
    console.ecrire(f"  Pour confirmer, tape {quoi} en toutes lettres.")
    console.ecrire("  Toute autre reponse annule.")
    try:
        saisie = console.lire(f"\n  nom attendu « {attendu} » : ").strip()
    except (EOFError, KeyboardInterrupt):
        saisie = ""
    if saisie == attendu:
        return True
    console.ecrire("\n  Annule. Rien n'a ete fait.")
    return False


def _rendre_resultat(console: Console, resultat) -> None:
    console.ecrire()
    console.ecrire(f"  etat        {resultat.etat}")
    console.ecrire(f"  duree       {resultat.duree_ms / 1000:.1f} s")
    console.ecrire("  compteurs   " + ", ".join(
        f"{nom} {valeur}" for nom, valeur in sorted(resultat.compteurs.items())))
    console.ecrire(f"  journal     {resultat.journal}")
    if resultat.ko:
        console.ecrire(f"  KO          {resultat.ko}")
    for chemin in resultat.extraits:
        console.ecrire(f"  extrait     {chemin}")
    if resultat.extraits:
        console.ecrire()
        console.ecrire("  RELIS CES FICHIERS avant de lancer la passe "
                       "suivante. Ils s'ouvrent")
        console.ecrire("  dans Excel, et ce que SAP a trouve n'est pas "
                       "forcement ce que tu")
        console.ecrire("  voulais : supprime les lignes de trop, puis donne "
                       "le fichier comme")
        console.ecrire("  jeu a la pipeline de remediation. Il se redonne tel "
                       "quel.")
    if resultat.raison:
        console.ecrire(f"  raison      {resultat.raison}")
    if resultat.interrompu:
        console.ecrire()
        console.ecrire("  INTERROMPU. Un item ouvert APRES une sauvegarde est "
                       "douteux : la reprise")
        console.ecrire("  ne le rejouera pas. Va le voir dans « Journaux > "
                       "Les douteux a arbitrer »")
        console.ecrire("  avant de relancer quoi que ce soit.")


def ecran_pipelines(env: Environnement) -> Menu:

    def valider(console: Console) -> str:
        from falcon.pipeline import PipelineInvalide, charger

        chemin = demander_chemin(console, "pipeline YAML")
        if chemin is None:
            return CONTINUER
        console.titre("Pipeline")
        try:
            _rendre_pipeline(console, charger(chemin))
        except PipelineInvalide as erreur:
            # Le refus du chargeur est deja SITUE : fichier, rang, nom
            # d'etape. On le rend tel quel plutot que de le reformuler.
            console.ecrire(f"\n  Refuse.\n\n  {erreur}")
        console.pause()
        return CONTINUER

    def brouillon(console: Console) -> str:
        from falcon.pipeline import PipelineInvalide, charger

        chemin = demander_chemin(console, "brouillon YAML")
        if chemin is None:
            return CONTINUER
        console.titre("Brouillon de pipeline")
        console.ecrire()
        console.ecrire("  Charge en BROUILLON : les marqueurs sont toleres. "
                       "Un fichier qui")
        console.ecrire("  en porte encore n'est pas livrable — il reste a "
                       "completer.")
        try:
            _rendre_pipeline(console, charger(chemin, brouillon=True))
        except PipelineInvalide as erreur:
            console.ecrire(f"\n  Refuse meme en brouillon.\n\n  {erreur}")
        console.pause()
        return CONTINUER

    def jeu(console: Console) -> str:
        from falcon.donnees import JeuInvalide, grouper, lire

        chemin = demander_chemin(console, "jeu de donnees (csv ou jsonl)")
        if chemin is None:
            return CONTINUER
        console.titre("Jeu de donnees")
        try:
            lignes, dialecte = lire(chemin)
        except JeuInvalide as erreur:
            console.ecrire(f"\n  Refuse.\n\n  {erreur}")
            console.pause()
            return CONTINUER

        _rendre_jeu(console, dialecte, lignes)

        try:
            saisie = console.lire(
                "\n  colonnes de clef, separees par une virgule "
                "(vide = pas de regroupement) : ").strip()
        except (EOFError, KeyboardInterrupt):
            return CONTINUER
        if not saisie:
            return CONTINUER

        cles = [c.strip() for c in saisie.split(",") if c.strip()]
        try:
            items = grouper(lignes, cles)
        except JeuInvalide as erreur:
            console.ecrire(f"\n  Regroupement refuse.\n\n  {erreur}")
            console.pause()
            return CONTINUER

        console.section("Regroupement par unite de sauvegarde")
        console.ecrire(f"    {len(lignes)} ligne(s) -> {len(items)} item(s)")
        console.ecrire()
        for item in items[:20]:
            cle = ", ".join(f"{c}={v}" for c, v in item.cle.items())
            console.ecrire(f"    {item.item_id}  {len(item.brut):>3} ligne(s)"
                           f"  {cle}")
        if len(items) > 20:
            console.ecrire(f"    ... et {len(items) - 20} autre(s)")
        console.ecrire()
        console.ecrire("  L'unite d'iteration est l'unite de SAUVEGARDE SAP, "
                       "pas l'unite de")
        console.ecrire("  constat. C'est ce regroupement qui fait coincider la "
                       "granularite de")
        console.ecrire("  reprise avec la frontiere transactionnelle reelle.")
        console.pause()
        return CONTINUER

    # -- execution ---------------------------------------------------------
    #
    # A partir d'ici, ca ecrit dans un ERP. L'ordre des entrees n'est pas
    # cosmetique : la repetition a blanc est proposee AVANT l'execution, et
    # l'execution avant la reprise.

    def _demander_surcouche(console: Console):
        """(registre, ok) — le registre livre ENRICHI, ou None si aucune.

        Facultative, et c'est le point : sans elle, tout incident non apparie
        est `inconnue`, donc BLOQUANT, et la garde de statut y route tout
        message E/A. Sur un systeme reel, le premier message d'erreur metier
        arrete donc le lot — c'est le comportement voulu — et la surcouche est
        ce qui permet de repartir en ayant CLASSE ce message plutot qu'en le
        redecouvrant. `falcon recolter` la propose depuis les dumps.

        `avec_surcouches`, pas `charger` : un chemin passe a `charger`
        REMPLACE les entrees livrees au lieu de s'y ajouter.
        """
        chemin = demander_chemin_facultatif(
            console, "surcouche de registre (facultatif, Entree pour aucune)")
        if chemin is None:
            return None, True
        from falcon.taxonomie import Registre, RegistreInvalide
        try:
            return Registre.avec_surcouches(chemin), True
        except RegistreInvalide as erreur:
            console.ecrire(f"\n  Surcouche refusee.\n\n  {erreur}")
            console.pause()
            return None, False

    def _preparer(console: Console, mode: str, *, surcouche: bool = True):
        """(pipeline, jeu, items, empreinte, journal, registre) ou None.

        Tout ce qui peut etre refuse l'est ICI, avant la moindre connexion :
        pipeline illisible, jeu illisible, regroupement impossible. Tomber a
        la preparation coute une saisie ; tomber a l'item quarante coute
        trente-neuf ecritures a demeler.
        """
        from falcon.donnees import JeuInvalide, empreinte_jeu, lire_items
        from falcon.pipeline import PipelineInvalide, charger

        chemin = demander_chemin(console, "pipeline YAML")
        if chemin is None:
            return None
        try:
            pipeline = charger(chemin)
        except PipelineInvalide as erreur:
            console.ecrire(f"\n  Refuse.\n\n  {erreur}")
            console.pause()
            return None

        if not pipeline.iterative:
            console.ecrire(f"\n  {pipeline.nom!r} est une pipeline "
                           f"{pipeline.classe!r}. La machinerie par item —")
            console.ecrire("  journal, reprise, ETA — ne sert qu'aux "
                           "iteratives (§3.5).")
            console.pause()
            return None

        jeu = demander_chemin(console, "jeu de donnees")
        if jeu is None:
            return None
        try:
            items, _ = lire_items(jeu, pipeline.cles)
            empreinte = empreinte_jeu(jeu)
        except JeuInvalide as erreur:
            console.ecrire(f"\n  Refuse.\n\n  {erreur}")
            console.pause()
            return None

        journal = demander_chemin(console, "journal JSONL (existant ou neuf)",
                                  existant=False)
        if journal is None:
            return None

        # La chaine ne demande PAS la surcouche ici : `enchainer` n'accepte
        # qu'un registre pour toute la chaine, donc la poser par maillon
        # ferait saisir n fois une reponse dont n-1 seraient jetees.
        registre = None
        if surcouche:
            registre, ok = _demander_surcouche(console)
            if not ok:
                return None
        return pipeline, jeu, items, empreinte, journal, registre

    def _forcage(console: Console, erreur) -> dict:
        """Propose le contournement TRACE de la garde de repetition a blanc.

        La garde refuse d'abord, et explique. C'est seulement ensuite qu'on
        offre de passer outre — et le motif n'est pas une formalite : il part
        dans l'ouverture du journal, a cote des derogations. Un contournement
        qui ne laisse pas de trace n'est pas un contournement, c'est un trou.
        """
        console.ecrire(f"\n  Refuse.\n")
        for ligne in str(erreur).splitlines():
            console.ecrire(f"  {ligne}")
        console.ecrire()
        console.ecrire("  Tu peux passer outre, mais il faudra dire pourquoi :")
        console.ecrire("  le motif sera ecrit dans le journal, a cote des")
        console.ecrire("  derogations, et c'est ce qu'on relira le jour ou ce")
        console.ecrire("  lot sera conteste.")
        try:
            motif = console.lire("\n  motif (vide : renoncer) : ").strip()
        except (EOFError, KeyboardInterrupt):
            return {}
        if not motif:
            return {}
        return {"forcer_sans_repetition": True, "motif_forcage": motif}

    def _forcage_reprise(console: Console, erreur) -> dict:
        """Le pendant de `_forcage`, pour la garde de REPRISE.

        `preparer` promettait « un motif, qui sera trace » — et `executer`
        n'exposait meme pas le parametre : une reprise refusee etait une
        impasse. Elle l'etait d'autant plus que le refus se declenchait sur
        une donnee INCHANGEE dont on avait seulement change les fins de ligne.
        """
        console.ecrire(f"\n  Refuse.\n")
        for ligne in str(erreur).splitlines():
            console.ecrire(f"  {ligne}")
        console.ecrire()
        console.ecrire("  Reprendre malgre cet ecart demande de dire pourquoi :")
        console.ecrire("  le motif sera ecrit dans le journal. Reprendre sur un")
        console.ecrire("  monde qui a change, c'est rejouer des items avec un")
        console.ecrire("  modele du monde faux — assure-toi que l'ecart est")
        console.ecrire("  celui que tu crois.")
        try:
            motif = console.lire("\n  motif (vide : renoncer) : ").strip()
        except (EOFError, KeyboardInterrupt):
            return {}
        if not motif:
            return {}
        return {"forcer_reprise": True, "motif_reprise": motif}

    def _executer(console: Console, mode: str, titre: str) -> str:
        from falcon.moteur import RepetitionManquante, executer
        from falcon.noyau import ErreurFalcon, RepriseIncoherente

        prepare = _preparer(console, mode)
        if prepare is None:
            return CONTINUER
        pipeline, jeu, items, empreinte, journal, registre = prepare

        console.titre(titre)
        _recapituler(console, pipeline, items, jeu, empreinte, mode)

        # La repetition a blanc s'arrete avant toute validation : elle ne
        # demande pas de confirmation, parce qu'il n'y a rien a confirmer.
        if mode != "dry-run" and not confirmer(console, pipeline.nom):
            console.pause()
            return CONTINUER

        try:
            driver = env.connecter()
        except ErreurFalcon as erreur:
            console.ecrire(f"\n  {type(erreur).__name__} : {erreur}")
            console.pause()
            return CONTINUER

        # La PROVENANCE, prise sur la session reellement ouverte.
        #
        # `executer` accepte `systeme`, `mandant` et `utilisateur`, et la
        # console n'en passait aucun : le journal ne disait donc ni sur quel
        # systeme ni sur quel mandant le lot avait tourne. Pour un fichier
        # cense faire foi, c'est le premier renseignement qu'on lui demande le
        # jour ou une correction de masse est contestee.
        #
        # `utilisateur` reste vide, et ce n'est pas un oubli : la couture est
        # epinglee a dix-huit methodes (§3.4) et aucune ne rend l'identifiant
        # de connexion. Le deviner serait inventer du comportement SAP. Un
        # champ vide dit « on ne sait pas » ; un champ rempli au hasard dirait
        # quelque chose de faux.
        provenance = _provenance(driver)

        observateur = env.rapporteur()
        forcage: dict = {}
        try:
            resultat = executer(
                pipeline, jeu, driver, journal=journal, mode=mode,
                registre=registre, **provenance,
                sortie_ko=str(Path(journal).with_suffix(".ko.csv")),
                sortie_extraction=str(Path(journal).parent
                                      / "extractions"),
                observateur=observateur)
        except RepetitionManquante as erreur:
            # La garde a refuse AVANT toute action : rien n'a ete ecrit, et on
            # peut donc proposer le contournement sans risque de double
            # execution. On ne le propose qu'ici, jamais d'avance : offrir de
            # desarmer une garde avant qu'elle ait parle, c'est l'inviter.
            forcage = _forcage(console, erreur)
            if not forcage:
                console.ecrire("\n  Annule. Rien n'a ete ecrit.")
                console.pause()
                return CONTINUER
            try:
                resultat = executer(
                    pipeline, jeu, driver, journal=journal, mode=mode,
                    registre=registre, **provenance, **forcage,
                    sortie_ko=str(Path(journal).with_suffix(".ko.csv")),
                sortie_extraction=str(Path(journal).parent
                                      / "extractions"),
                    observateur=observateur)
            except ErreurFalcon as seconde:
                console.ecrire(f"\n  {type(seconde).__name__} : {seconde}")
                console.ecrire(f"\n  Le journal fait foi : {journal}")
                console.pause()
                return CONTINUER
        except RepriseIncoherente as erreur:
            # Meme posture que pour la repetition : la garde refuse d'abord et
            # explique, et c'est seulement ensuite qu'on offre de passer outre.
            forcage = _forcage_reprise(console, erreur)
            if not forcage:
                console.ecrire("\n  Annule. Rien n'a ete ecrit.")
                console.pause()
                return CONTINUER
            try:
                resultat = executer(
                    pipeline, jeu, driver, journal=journal, mode=mode,
                    registre=registre, **provenance, **forcage,
                    sortie_ko=str(Path(journal).with_suffix(".ko.csv")),
                sortie_extraction=str(Path(journal).parent
                                      / "extractions"),
                    observateur=observateur)
            except ErreurFalcon as seconde:
                console.ecrire(f"\n  {type(seconde).__name__} : {seconde}")
                console.ecrire(f"\n  Le journal fait foi : {journal}")
                console.pause()
                return CONTINUER
        except ErreurFalcon as erreur:
            # Le moteur a refuse AVANT d'agir, ou s'est arrete sur un
            # inconnu. Dans les deux cas le journal dit ce qui a ete fait ;
            # la console n'a pas a le resumer de memoire.
            console.ecrire(f"\n  {type(erreur).__name__} : {erreur}")
            console.ecrire(f"\n  Le journal fait foi : {journal}")
            console.pause()
            return CONTINUER
        finally:
            clore = getattr(observateur, "clore", None)
            if callable(clore):
                clore()

        _rendre_resultat(console, resultat)
        console.pause()
        return CONTINUER

    def a_blanc(console: Console) -> str:
        return _executer(console, "dry-run", "Repetition a blanc")

    def lancer(console: Console) -> str:
        return _executer(console, "run", "Execution")

    def reprendre(console: Console) -> str:
        return _executer(console, "resume", "Reprise")

    def enchainer_les(console: Console) -> str:
        """Une chaine de pipelines : declenchements successifs, rien de plus.

        Aucune donnee ne passe d'un maillon au suivant, et c'est la limite qui
        empeche la chaine de devenir un orchestrateur (§3.3). Un maillon
        interrompu arrete la chaine : un arret bloquant dit que le modele du
        monde est faux, et passer au suivant serait ecrire n'importe ou avec
        entrain.
        """
        from falcon.moteur import Maillon, RepetitionManquante, enchainer
        from falcon.noyau import ErreurFalcon

        console.titre("Chaine de pipelines")
        console.ecrire()
        console.ecrire("  Declenchements successifs. AUCUNE donnee ne passe "
                       "d'un maillon au")
        console.ecrire("  suivant, et un maillon interrompu arrete la chaine.")

        maillons: list = []
        recaps: list = []
        while True:
            console.ecrire()
            console.ecrire(f"  Maillon {len(maillons) + 1} — laisser vide "
                           "pour lancer la chaine.")
            prepare = _preparer(console, "run", surcouche=False)
            if prepare is None:
                break
            pipeline, jeu, items, empreinte, journal, _ = prepare
            maillons.append(Maillon(
                pipeline=pipeline, jeu=jeu, journal=journal,
                sortie_ko=str(Path(journal).with_suffix(".ko.csv")),
                sortie_extraction=str(Path(journal).parent
                                      / "extractions")))
            recaps.append((pipeline, items, jeu, empreinte))
            console.ecrire(f"\n  + {pipeline.nom}  ({len(items)} item(s))")

        if not maillons:
            console.ecrire("\n  Chaine vide. Rien a lancer.")
            console.pause()
            return CONTINUER

        registre, ok = _demander_surcouche(console)
        if not ok:
            return CONTINUER

        console.titre(f"Chaine — {len(maillons)} maillon(s)")
        for pipeline, items, jeu, empreinte in recaps:
            _recapituler(console, pipeline, items, jeu, empreinte, "run")

        # Le nom attendu est celui du PREMIER maillon : c'est lui qui part en
        # premier, et c'est le seul dont on soit sur qu'il s'executera.
        if not confirmer(console, maillons[0].pipeline.nom):
            console.pause()
            return CONTINUER

        try:
            driver = env.connecter()
        except ErreurFalcon as erreur:
            console.ecrire(f"\n  {type(erreur).__name__} : {erreur}")
            console.pause()
            return CONTINUER

        observateur = env.rapporteur()
        try:
            resultats = enchainer(maillons, driver, registre=registre,
                                  observateur=observateur)
        except RepetitionManquante as erreur:
            # La garde a refuse sur le PREMIER maillon, donc avant toute
            # action : rien n'a ete ecrit. Le motif vaut pour la chaine
            # entiere, ce qui est coherent avec `enchainer`, qui ne prend
            # qu'un jeu d'options pour tous les maillons.
            forcage = _forcage(console, erreur)
            if not forcage:
                console.ecrire("\n  Annule. Rien n'a ete ecrit.")
                console.pause()
                return CONTINUER
            try:
                resultats = enchainer(maillons, driver, registre=registre,
                                      observateur=observateur, **forcage)
            except ErreurFalcon as seconde:
                console.ecrire(f"\n  {type(seconde).__name__} : {seconde}")
                console.pause()
                return CONTINUER
        except ErreurFalcon as erreur:
            console.ecrire(f"\n  {type(erreur).__name__} : {erreur}")
            console.pause()
            return CONTINUER
        finally:
            clore = getattr(observateur, "clore", None)
            if callable(clore):
                clore()

        for maillon, resultat in zip(maillons, resultats):
            console.section(maillon.pipeline.nom)
            _rendre_resultat(console, resultat)
        if len(resultats) < len(maillons):
            console.ecrire()
            console.ecrire(f"  Chaine ARRETEE apres {len(resultats)} "
                           f"maillon(s) sur {len(maillons)}.")
        console.pause()
        return CONTINUER

    def composer_le_classeur(console: Console) -> str:
        """`falcon composer` : les CSV exportes du classeur, vers un YAML.

        C'est le maillon entre le classeur Excel et une pipeline chargeable,
        et il n'existait que dans la CLI. La console — c'est-a-dire ce que
        l'utilisateur ouvre — ne savait pas le faire : le classeur produisait
        deux CSV dont rien, ici, ne savait quoi faire.

        On MONTRE avant d'ecrire, et l'ecriture passe par
        `convertir_fichiers`, qui RELIT par `charger()` avant de poser le
        fichier. Un YAML produit et refuse n'atteint donc jamais le disque.
        """
        from falcon.tableur import (
            TableurInvalide, convertir, convertir_fichiers,
        )

        dossier = demander_chemin(console, "dossier des CSV du classeur")
        if dossier is None:
            return CONTINUER
        if not dossier.is_dir():
            console.ecrire(f"\n  {dossier} n'est pas un dossier. Le classeur "
                           "exporte deux CSV ;")
            console.ecrire("  c'est le dossier qui les contient qu'on attend "
                           "ici.")
            console.pause()
            return CONTINUER

        try:
            texte = convertir(dossier)
        except TableurInvalide as erreur:
            console.ecrire(f"\n  TableurInvalide : {erreur}")
            console.pause()
            return CONTINUER

        console.titre("Pipeline composee")
        console.ecrire()
        console.ecrire(texte)

        sortie = demander_chemin_neuf(console, "ecrire dans (vide = ne rien "
                                               "ecrire)")
        if sortie is None:
            console.pause()
            return CONTINUER
        try:
            chemin = convertir_fichiers(dossier, sortie)
        except TableurInvalide as erreur:
            console.ecrire(f"\n  TableurInvalide : {erreur}")
            console.ecrire("  RIEN n'a ete ecrit.")
            console.pause()
            return CONTINUER
        console.ecrire(f"\n  {chemin} ecrit.")
        console.pause()
        return CONTINUER

    return Menu(
        titre="FALCON — pipelines et donnees",
        preambule=(
            "1 a 4 : relecture et composition, aucun geste dans SAP.\n"
            "5 : repetition a blanc, s'arrete avant toute validation.\n"
            "6 a 8 : ECRIVENT DANS SAP, apres confirmation en toutes lettres."),
        entrees=(
            Entree("1", "Composer depuis le classeur", composer_le_classeur,
                   "les deux CSV exportes d'Excel deviennent un YAML"),
            Entree("2", "Charger et valider une pipeline", valider,
                   "ce que les gardes verront, etape par etape"),
            Entree("3", "Relire un brouillon", brouillon,
                   "meme chose, marqueurs toleres"),
            Entree("4", "Inspecter un jeu de donnees", jeu,
                   "dialecte, colonnes, et regroupement en items"),
            Entree("5", "Repetition a blanc", a_blanc,
                   "tout sauf la validation — aucune ecriture dans SAP"),
            Entree("6", "Executer", lancer,
                   "ECRIT DANS SAP. Confirmation en toutes lettres"),
            Entree("7", "Reprendre une execution", reprendre,
                   "ECRIT DANS SAP. Les douteux ne sont jamais rejoues"),
            Entree("8", "Enchainer des pipelines", enchainer_les,
                   "ECRIT DANS SAP. Un maillon interrompu arrete la chaine"),
        ))


# ---------------------------------------------------------------------------
# Journaux
# ---------------------------------------------------------------------------

def ecran_journaux(env: Environnement) -> Menu:
    """Relire un journal d'execution. **Jamais y ecrire.**

    Le journal est append-only et fait foi : c'est de lui que la reprise tire
    ce qu'elle a le droit de rejouer. Une console qui pourrait le retoucher —
    « clore » un item resté ouvert, « passer » un douteux — deferait la seule
    chose qui empeche une double ecriture dans SAP. Arbitrer un douteux est un
    geste qui se fait dans SAP, pas dans un menu.
    """

    def _cles(enregistrements) -> dict[str, str]:
        """item_id -> clef lisible.

        `item_id` est une empreinte des valeurs de clef, pas le rang de la
        ligne : un fichier de KO reinjecte n'a plus les memes rangs, et la
        reprise doit rester juste malgre ca. Le prix, c'est qu'un item
        s'appelle `a3f2b1...` — illisible pour qui doit aller verifier dans
        SAP. `ItemDebut` porte la clef ; on la remet en face.
        """
        from falcon.journal import ItemDebut

        return {e.item_id: ", ".join(f"{c}={v}" for c, v in e.cle.items())
                for e in enregistrements
                if isinstance(e, ItemDebut) and e.cle}

    def _nommer(cles: dict[str, str], item_id: str) -> str:
        lisible = cles.get(item_id)
        return f"{item_id}  {lisible}" if lisible else item_id

    def _replier(console: Console):
        """(enregistrements, etats) d'un journal choisi, ou None."""
        from falcon.journal import etats, lire
        from falcon.noyau import JournalCorrompu

        chemin = demander_chemin(console, "journal JSONL")
        if chemin is None:
            return None
        try:
            enregistrements = lire(chemin)
        except (JournalCorrompu, OSError) as erreur:
            console.ecrire(f"\n  Journal illisible.\n\n  {erreur}")
            return None
        return chemin, enregistrements, etats(enregistrements)

    def rapport(console: Console) -> str:
        from falcon.journal import depuis_journal, rendre

        replie = _replier(console)
        if replie is None:
            return CONTINUER
        chemin, enregistrements, _ = replie
        console.titre("Rapport de fin")
        console.ecrire()
        console.ecrire(f"  {chemin}")
        console.ecrire()
        for ligne in rendre(depuis_journal(enregistrements)).splitlines():
            console.ecrire(f"  {ligne}")
        console.pause()
        return CONTINUER

    def etats_des_items(console: Console) -> str:
        from falcon.journal import TERMINAUX

        replie = _replier(console)
        if replie is None:
            return CONTINUER
        _, enregistrements, etats = replie
        cles = _cles(enregistrements)
        console.titre("Etats des items")

        par_etat: dict[str, list] = {}
        for etat_item in etats.values():
            par_etat.setdefault(etat_item.etat, []).append(etat_item)

        console.ecrire()
        if not etats:
            console.ecrire("  Aucun item dans ce journal.")
            console.pause()
            return CONTINUER

        for etat in sorted(par_etat):
            items = sorted(par_etat[etat], key=lambda e: e.item_id)
            console.ecrire(f"  {etat:<10} {len(items):>4}")
            for etat_item in items[:20]:
                sauve = (f"  {etat_item.sauvegardes} sauvegarde(s)"
                         if etat_item.sauvegardes else "")
                console.ecrire(
                    f"      {_nommer(cles, etat_item.item_id)}{sauve}")
            if len(items) > 20:
                console.ecrire(f"      ... et {len(items) - 20} autre(s)")

        ouverts = [e for e in etats.values() if e.etat not in TERMINAUX]
        if ouverts:
            console.ecrire()
            console.ecrire(f"  {len(ouverts)} item(s) sans etat terminal : "
                           "l'execution s'est interrompue.")
        console.pause()
        return CONTINUER

    def douteux(console: Console) -> str:
        from falcon.journal import DOUTEUX

        replie = _replier(console)
        if replie is None:
            return CONTINUER
        _, enregistrements, etats = replie
        cles = _cles(enregistrements)
        console.titre("Douteux — a arbitrer a la main")
        console.ecrire()
        console.ecrire("  Interrompus APRES une sauvegarde reussie. SAP a "
                       "peut-etre enregistre ;")
        console.ecrire("  les rejouer serait une double ecriture. La reprise "
                       "ne les reprendra")
        console.ecrire("  jamais, et c'est voulu.")

        a_arbitrer = sorted((e for e in etats.values() if e.etat == DOUTEUX),
                            key=lambda e: e.item_id)
        console.ecrire()
        if not a_arbitrer:
            console.ecrire("  Aucun. Rien a arbitrer sur ce journal.")
            console.pause()
            return CONTINUER

        for etat_item in a_arbitrer:
            console.ecrire(f"    {_nommer(cles, etat_item.item_id)}   "
                           f"{etat_item.sauvegardes} sauvegarde(s) passee(s)")
        console.ecrire()
        console.ecrire(f"  {len(a_arbitrer)} item(s). Va voir dans SAP ce qui "
                       "y est reellement, puis")
        console.ecrire("  reprends la main dessus a l'unite. Rien ici ne peut "
                       "le faire pour toi.")
        console.pause()
        return CONTINUER

    def reexporter(console: Console) -> str:
        """Le fichier de KO, REPROJETE depuis le journal.

        `ItemDebut.brut` porte les lignes d'entree telles qu'elles ont ete
        lues. On ne reconstruit donc rien : ni le regroupement — qu'il
        faudrait redeviner en redemandant les clefs de la pipeline, avec le
        risque de n'en pas retrouver les memes items — ni les valeurs. Le
        journal fait foi jusque-la.

        Le jeu d'origine reste demande, mais pour une seule chose : son
        DIALECTE. Encodage, BOM, delimiteur, fins de ligne et ordre des
        colonnes ne sont pas dans le journal, et ce sont eux qui rendent le
        fichier reinjectable sans retouche.

        **Les douteux en sont exclus, nommement.** Un fichier de KO est fait
        pour etre reinjecte tel quel ; y laisser un item qui a peut-etre deja
        ecrit dans SAP en ferait un chemin vers la double ecriture, par le
        canal meme qui est cense etre sur.

        `falcon_sauvegardes` est rempli depuis le repli du journal. Sans lui,
        l'humain qui relit le fichier n'a aucun moyen de savoir qu'un item a
        deja ecrit — c'est le pendant, cote fichier, de l'etat « douteux ».
        """
        from falcon.donnees import Item, JeuInvalide, ecrire_items, lire
        from falcon.journal import DOUTEUX, KO, Incident, ItemDebut, ItemFin

        replie = _replier(console)
        if replie is None:
            return CONTINUER
        _, enregistrements, etats = replie
        cles = _cles(enregistrements)

        console.titre("Reexport des KO")

        recales = {i for i, e in etats.items() if e.etat == KO}
        ecartes = sorted(i for i, e in etats.items() if e.etat == DOUTEUX)

        console.ecrire()
        if ecartes:
            console.ecrire(f"  {len(ecartes)} douteux ECARTE(S) du fichier : "
                           "ils ont peut-etre deja")
            console.ecrire("  ecrit dans SAP. Les reinjecter ecrirait deux "
                           "fois.")
            for item_id in ecartes:
                console.ecrire(f"      {_nommer(cles, item_id)}")
            console.ecrire()

        # La DERNIERE ouverture de chaque item : un item rejoue a plusieurs
        # ouvertures, et c'est la derniere qui porte les lignes du run qu'on
        # reexporte.
        ouvertures: dict[str, ItemDebut] = {}
        for enregistrement in enregistrements:
            if isinstance(enregistrement, ItemDebut):
                ouvertures[enregistrement.item_id] = enregistrement

        a_ecrire = [
            Item(item_id=ouverture.item_id, cle=dict(ouverture.cle),
                 brut=tuple(ouverture.brut), index=ouverture.index)
            for item_id, ouverture in sorted(ouvertures.items())
            if item_id in recales and ouverture.brut
        ]

        muets = sorted(i for i in recales
                       if i in ouvertures and not ouvertures[i].brut)
        if muets:
            console.ecrire(f"  {len(muets)} item(s) KO sans lignes d'entree "
                           "dans le journal : rien a")
            console.ecrire("  reprojeter pour eux. Ils sont nommes ici, pas "
                           "reconstruits :")
            for item_id in muets:
                console.ecrire(f"      {_nommer(cles, item_id)}")
            console.ecrire()

        if not a_ecrire:
            console.ecrire("  Aucun KO a reexporter.")
            console.pause()
            return CONTINUER

        chemin_jeu = demander_chemin(
            console, "jeu d'origine (pour son dialecte : encodage, "
                     "delimiteur, colonnes)")
        if chemin_jeu is None:
            return CONTINUER
        try:
            _, dialecte = lire(chemin_jeu)
        except JeuInvalide as erreur:
            console.ecrire(f"\n  Dialecte illisible.\n\n  {erreur}")
            console.pause()
            return CONTINUER

        # Les CINQ colonnes de diagnostic, toutes remplies.
        #
        # `falcon_categorie` et `falcon_entree` viennent de l'`Incident` — le
        # seul enregistrement ou la taxonomie ait dit ce qu'elle a reconnu, et
        # la seule facon de distinguer un `connue_fautive` nomme d'un
        # `inconnue` qui n'a rien trouve. `ItemFin.incident` est un message
        # libre : il va dans `falcon_message`, pas dans une colonne de
        # classement. Une colonne vide dans un fichier de KO, c'est un tri que
        # l'humain devra faire a la main.
        classements = {e.item_id: e for e in enregistrements
                       if isinstance(e, Incident) and e.item_id}
        messages = {e.item_id: e.incident or ""
                    for e in enregistrements if isinstance(e, ItemFin)}
        diagnostics = {}
        for item in a_ecrire:
            classement = classements.get(item.item_id)
            diagnostics[item.item_id] = {
                "falcon_categorie": classement.categorie if classement else "ko",
                "falcon_entree": (classement.entree or "") if classement else "",
                "falcon_message": messages.get(item.item_id, ""),
                "falcon_sauvegardes": str(etats[item.item_id].sauvegardes),
            }

        cible = demander_chemin_neuf(
            console, f"fichier a ecrire ({len(a_ecrire)} item(s))")
        if cible is None:
            return CONTINUER

        ecrit = ecrire_items(cible, a_ecrire, dialecte, diagnostics)
        console.ecrire()
        console.ecrire(f"  {ecrit}  —  {len(a_ecrire)} item(s), "
                       f"{sum(len(i.brut) for i in a_ecrire)} ligne(s)")
        console.ecrire()
        console.ecrire("  Format et dialecte d'origine : reinjectable tel "
                       "quel. Les colonnes")
        console.ecrire("  `falcon_` sont retirees a la lecture.")
        console.pause()
        return CONTINUER

    return Menu(
        titre="FALCON — journaux",
        preambule=("Lecture seule sur le journal : il est append-only et fait "
                   "foi. Rien\nici ne le retouche, ne le clot, ni n'arbitre "
                   "un douteux."),
        entrees=(
            Entree("1", "Rapport de fin", rapport,
                   "provenance, compteurs, incidents, derogations"),
            Entree("2", "Etats des items", etats_des_items,
                   "ok, ko, ignore, douteux, en cours — et lesquels"),
            Entree("3", "Les douteux a arbitrer", douteux,
                   "interrompus apres sauvegarde ; jamais rejoues"),
            Entree("4", "Reexporter les KO", reexporter,
                   "au format d'entree, reinjectable, douteux exclus"),
        ))


# ---------------------------------------------------------------------------
# Exports de table
# ---------------------------------------------------------------------------

def ecran_volumique(env: Environnement) -> Menu:
    """Les exports conserves, et ce qui a bouge entre deux.

    Une volumique ne porte ni journal par item, ni reprise fine : sa valeur
    est ailleurs, dans le RAPPROCHEMENT. Un export seul dit l'etat d'une table
    a un instant ; deux exports disent ce qui a change — et ce sont les
    modifications, pas les ajouts, qui ne se voient pas a l'oeil.
    """

    def _conservation(console: Console):
        """(racine, systeme, table) d'une arborescence de conservation."""
        racine_exports = demander_chemin(console, "dossier de conservation")
        if racine_exports is None:
            return None
        if not racine_exports.is_dir():
            console.ecrire(f"\n  {racine_exports} n'est pas un dossier.")
            return None
        try:
            systeme = console.lire("\n  systeme (K75, P01...) : ").strip()
            table = console.lire("  table (MARA, EQUI...) : ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not systeme or not table:
            console.ecrire("\n  Un export se range par systeme ET par table. "
                           "Sans les deux, il n'y a")
            console.ecrire("  rien a lister.")
            return None
        return racine_exports, systeme, table

    def _provenance(console: Console, export) -> None:
        provenance = export.provenance
        console.ecrire(f"    systeme       {provenance.systeme}/"
                       f"{provenance.mandant}")
        console.ecrire(f"    table         {provenance.table}")
        console.ecrire(f"    horodatage    {provenance.horodatage}")
        console.ecrire(f"    utilisateur   {provenance.utilisateur}")
        if provenance.criteres:
            console.ecrire("    criteres")
            for nom, valeur in sorted(provenance.criteres.items()):
                console.ecrire(f"      {nom} = {valeur}")
        else:
            console.ecrire("    criteres      (aucun — table entiere)")
        console.ecrire(f"    lignes        {len(export)}")

    def lister(console: Console) -> str:
        from falcon.volumique import ExportInvalide, exports, lire_export

        choix = _conservation(console)
        if choix is None:
            return CONTINUER
        racine_exports, systeme, table = choix
        console.titre(f"Exports {systeme}/{table}")

        connus = exports(racine_exports, systeme, table)
        console.ecrire()
        if not connus:
            console.ecrire(f"  Aucun export conserve pour {systeme}/{table}.")
            console.ecrire()
            console.ecrire("  Le dossier est range par systeme : melanger les "
                           "systemes rendrait le")
            console.ecrire("  rapprochement inter-systeme dependant d'un nom "
                           "de fichier bien lu.")
            console.pause()
            return CONTINUER

        console.ecrire(f"  {len(connus)} export(s), du plus ancien au plus "
                       "recent.")
        console.ecrire("  Tri sur le NOM : une copie ou une restauration "
                       "change la date du")
        console.ecrire("  fichier, pas l'horodatage qu'il porte.")
        for chemin in connus:
            console.ecrire()
            console.ecrire(f"  {chemin.name}")
            try:
                _provenance(console, lire_export(chemin))
            except ExportInvalide as erreur:
                console.ecrire(f"    ILLISIBLE — {erreur}")
        console.pause()
        return CONTINUER

    def comparer(console: Console) -> str:
        from falcon.volumique import (
            DeltaImpossible, ExportInvalide, delta, exports, lire_export,
            rendre,
        )

        choix = _conservation(console)
        if choix is None:
            return CONTINUER
        racine_exports, systeme, table = choix
        connus = exports(racine_exports, systeme, table)
        console.titre(f"Delta {systeme}/{table}")
        console.ecrire()
        if len(connus) < 2:
            console.ecrire(f"  {len(connus)} export(s) conserve(s). Il en faut "
                           "deux pour comparer.")
            console.pause()
            return CONTINUER

        precedent, courant = connus[-2], connus[-1]
        console.ecrire(f"  precedent   {precedent.name}")
        console.ecrire(f"  courant     {courant.name}")

        try:
            saisie = console.lire(
                "\n  colonnes de clef, separees par une virgule : ").strip()
        except (EOFError, KeyboardInterrupt):
            return CONTINUER
        cles = [c.strip() for c in saisie.split(",") if c.strip()]

        try:
            ecart = delta(lire_export(precedent), lire_export(courant), cles)
        except (DeltaImpossible, ExportInvalide) as erreur:
            # Un rapprochement par rang produirait des modifications
            # imaginaires des que l'ordre change. Le refus est le bon
            # resultat, et il se lit.
            console.ecrire(f"\n  Comparaison refusee.\n\n  {erreur}")
            console.pause()
            return CONTINUER

        console.ecrire()
        for ligne in rendre(ecart).splitlines():
            console.ecrire(ligne)
        console.pause()
        return CONTINUER

    def carte(console: Console) -> str:
        from falcon.volumique import (
            CHEMIN_CARTE_DEFAUT, CarteInvalide, charger_carte,
        )

        console.titre("Carte SE16N")
        try:
            relevee = charger_carte()
        except CarteInvalide as erreur:
            console.ecrire(f"\n  {erreur}")
            console.pause()
            return CONTINUER

        console.ecrire()
        console.ecrire(f"  {CHEMIN_CARTE_DEFAUT}")
        console.ecrire()
        console.ecrire(f"    champ_table       {relevee.champ_table}")
        console.ecrire(f"    bouton_executer   {relevee.bouton_executer}")
        console.ecrire(f"    grille            {relevee.grille}")
        console.ecrire("    ecran_selection   "
                       + "/".join(relevee.ecran_selection))
        console.ecrire("    ecran_resultat    "
                       + "/".join(relevee.ecran_resultat))
        console.ecrire(f"    criteres          {len(relevee.criteres)}")
        for nom, champ in sorted(relevee.criteres.items()):
            console.ecrire(f"      {nom} -> {champ}")

        console.ecrire()
        if relevee.complete:
            console.ecrire("  Carte complete. L'export peut naviguer.")
            console.pause()
            return CONTINUER

        console.ecrire(f"  INCOMPLETE — il manque {list(relevee.manquants)}")
        console.ecrire()
        console.ecrire("  La carte est livree VIDE, et c'est voulu. Ces "
                       "identifiants ne sont pas")
        console.ecrire("  devinables : les conjecturer, c'est piloter un "
                       "ecran qu'on n'a jamais vu.")
        console.ecrire("  L'export refuse avant toute navigation tant qu'ils "
                       "manquent.")
        console.ecrire()
        console.ecrire("  Pour la remplir, sur un poste ou SAP GUI est "
                       "ouvert sur SE16N :")
        console.ecrire()
        console.ecrire("      python -m falcon diagnostiquer")
        console.pause()
        return CONTINUER

    return Menu(
        titre="FALCON — exports de table",
        preambule=("Lecture seule. Rien ici ne lance d'export ni n'ecrase un "
                   "fichier conserve."),
        entrees=(
            Entree("1", "Lister les exports", lister,
                   "ce qui est conserve, du plus ancien au plus recent"),
            Entree("2", "Comparer au precedent", comparer,
                   "ajouts, retraits, et surtout modifications"),
            Entree("3", "La carte SE16N", carte,
                   "ce qu'elle contient, et ce qui lui manque"),
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

    def promouvoir(console: Console) -> str:
        """Le geste que `diagnostiquer` annonce et qui n'existait nulle part.

        `Depot.promouvoir` n'etait appele que par des tests. Or
        `diagnostiquer --catalogue` verse en QUARANTAINE et dit a
        l'utilisateur que « le promouvoir au catalogue reste un geste
        explicite » — un geste qui n'existait ni en CLI ni ici. Le catalogue
        cure restait donc vide, et `dictionnaire` devait etre lance avec
        `--quarantaine` pour voir quoi que ce soit.

        Cet ecran est le bon endroit : c'est le seul d'ou l'utilisateur VOIT
        ce qu'il promeut avant de le promouvoir.
        """
        from falcon.catalogue import CatalogueInvalide, ClefVariante, Depot

        depot = _depot(console)
        if depot is None:
            return CONTINUER

        console.titre("Promouvoir une capture")
        ecarte = Depot(depot.quarantaine)
        clefs = [v.clef for t in ecarte.triplets() for v in ecarte.variantes(t)]
        if not clefs:
            console.ecrire("\n  La quarantaine est vide : rien a promouvoir.")
            console.ecrire("  Une capture y entre par "
                           "`diagnostiquer --catalogue`.")
            console.pause()
            return CONTINUER

        console.ecrire()
        for rang, clef in enumerate(clefs, start=1):
            variante = ecarte.pour_edition(clef)
            marque = ("observee" if variante.observee
                      else "ESQUISSE — ne peut pas garder un ecran")
            console.ecrire(f"  {rang:>2}  {clef.transaction}/{clef.programme}"
                           f"/{clef.dynpro}  {clef.empreinte}")
            console.ecrire(f"      {len(variante.champs):>3} champ(s)  "
                           f"{marque}  « {variante.titre} »")

        try:
            saisie = console.lire("\n  numero a promouvoir (vide : "
                                  "aucune) : ").strip()
        except (EOFError, KeyboardInterrupt):
            return CONTINUER
        if not saisie:
            return CONTINUER
        try:
            choisie = clefs[int(saisie) - 1]
            if int(saisie) < 1:
                raise IndexError
        except (ValueError, IndexError):
            console.ecrire(f"\n  « {saisie} » n'est pas dans la liste.")
            console.pause()
            return CONTINUER

        # Confirmation par l'EMPREINTE, en toutes lettres. Deux variantes d'un
        # meme ecran ne different que par elle : un « oui » ne dirait pas
        # laquelle on a relue, et c'est precisement ce qu'on certifie ici.
        variante = ecarte.pour_edition(choisie)
        if variante.observee:
            console.ecrire("\n  Promouvoir, c'est dire que TU as relu cet "
                           "ecran.")
        else:
            # Une esquisse vient d'une TRACE : elle porte les champs touches,
            # pas les champs presents, et personne n'a vu l'ecran. La promouvoir
            # dit « j'ai vu le fichier », pas « j'ai vu l'ecran » — et
            # `pour_garde` continuera de la refuser. Le dire ici evite de faire
            # certifier a l'utilisateur quelque chose qu'il n'a pas fait.
            console.ecrire("\n  C'est une ESQUISSE, tiree d'une trace : "
                           "personne n'a vu cet")
            console.ecrire("  ecran. La promouvoir la rend disponible pour "
                           "REDIGER une")
            console.ecrire("  pipeline, rien de plus — une garde d'identite "
                           "la refusera")
            console.ecrire("  toujours. Tu certifies avoir lu le FICHIER, pas "
                           "l'ecran.")
        console.ecrire("  Pour confirmer, tape son empreinte en toutes "
                       "lettres.")
        if not confirmer(console, choisie.empreinte):
            console.pause()
            return CONTINUER

        try:
            chemin = depot.promouvoir(choisie)
        except CatalogueInvalide as erreur:
            console.ecrire(f"\n  Refuse.\n\n  {erreur}")
            console.pause()
            return CONTINUER
        console.ecrire(f"\n  Promue : {chemin}")
        console.pause()
        return CONTINUER

    def dictionnaire(console: Console) -> str:
        """Le catalogue a plat, pour le classeur. Existait en CLI seulement.

        Le lot 15 s'appelle « la console pilote tout FALCON » ; `dictionnaire`
        y faisait exception.
        """
        from falcon.catalogue import Depot
        from falcon.commandes.dictionnaire import exporter, recenser

        depot = _depot(console)
        if depot is None:
            return CONTINUER

        console.titre("Dictionnaire des ecrans")
        console.ecrire()
        console.ecrire("  Une ligne par champ, pour que le classeur propose "
                       "les ecrans")
        console.ecrire("  et les cibles dans des listes deroulantes.")

        try:
            reponse = console.lire("\n  recenser la quarantaine plutot que le "
                                   "catalogue cure ? (oui/non) : ").strip()
        except (EOFError, KeyboardInterrupt):
            return CONTINUER
        if reponse.lower() in ("oui", "o"):
            depot = Depot(depot.quarantaine)

        lignes = recenser(depot)
        if not lignes:
            console.ecrire("\n  Aucun champ a recenser. Un ecran entre au "
                           "catalogue par")
            console.ecrire("  `diagnostiquer --catalogue`, puis par la "
                           "promotion.")
            console.pause()
            return CONTINUER

        chemin = demander_chemin_neuf(console, "fichier CSV a ecrire")
        if chemin is None:
            return CONTINUER
        exporter(depot, chemin)
        ecrans = len({(l["transaction"], l["programme"], l["dynpro"],
                       l["empreinte"]) for l in lignes})
        console.ecrire(f"\n  {chemin}  —  {len(lignes)} champ(s) sur "
                       f"{ecrans} variante(s)")
        console.pause()
        return CONTINUER

    return Menu(
        titre="FALCON — catalogue d'ecrans",
        preambule=(
            "Les deux premieres entrees lisent. La troisieme PROMEUT une\n"
            "capture : c'est le geste par lequel tu dis avoir relu l'ecran,\n"
            "et il se confirme par l'empreinte en toutes lettres.\n"
            "\n"
            "Rien ici n'ecrit dans SAP."),
        entrees=(
            Entree("1", "Catalogue cure", cure, "ce qu'un humain a valide"),
            Entree("2", "Quarantaine", quarantaine,
                   "les captures pas encore relues"),
            Entree("3", "Promouvoir une capture", promouvoir,
                   "de la quarantaine au catalogue — apres relecture"),
            Entree("4", "Exporter le dictionnaire", dictionnaire,
                   "le catalogue a plat, en CSV pour le classeur"),
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

    def cartographier(console: Console) -> str:
        return _cartographier(console, env)


    return Menu(
        titre="FALCON — session SAP",
        preambule=(
            "Se greffe sur une session que vous avez ouverte et sur laquelle\n"
            "vous vous etes authentifie vous-meme. Aucun mot de passe ne\n"
            "transite par FALCON.\n"
            "\n"
            "AUCUNE entree d'ici ne SAUVEGARDE dans SAP. Les deux premieres\n"
            "ne font que REGARDER. La troisieme AGIT DANS SAP : elle rejoue\n"
            "une trace, donc elle SAISIT des valeurs dans les champs — sans\n"
            "jamais les valider — navigue, presse des boutons et lance des\n"
            "selections qui peuvent tourner longtemps. Elle demande le nom du\n"
            "fichier de trace en toutes lettres avant de partir.\n"
            "\n"
            "Le dry-run refuse les deux gestes de sauvegarde qu'il sait\n"
            "reconnaitre. Une sauvegarde par un chemin de MENU passerait au\n"
            "travers : c'est une limite connue, ecrite dans le controleur.\n"
            "\n"
            "Exige Windows, pywin32, et le scripting autorise des deux cotes."),
        entrees=(
            Entree("1", "Diagnostiquer l'ecran courant", regarder,
                   "identite, fenetres, statut, releve des champs"),
            Entree("2", "Diagnostiquer et verser en quarantaine", relever,
                   "le releve devient une capture a relire"),
            # Le marqueur est dans le DETAIL, pas dans le libelle : c'est la
            # regle que la console s'est donnee, et le libelle se lit trop
            # vite. « AGIT » et non « ECRIT » : la distinction est reelle et
            # un test verifie qu'aucun preambule ne la gomme.
            Entree("3", "Explorer la trace dans SAP", cartographier,
                   "AGIT DANS SAP — cartographie les ecrans, sans y ecrire"),
        ))


def _cartographier(console: Console, env: Environnement) -> str:
    """L'etape 2 du cycle de vie, depuis la console.

    La seule entree de la console, avec l'execution, qui AGISSE dans SAP. Elle
    n'ecrit aucune donnee — le dry-run refuse toute sauvegarde — mais elle
    navigue. D'ou la confirmation en toutes lettres, et d'ou l'apercu AVANT :
    on ne peut pas taper le nom du fichier sans avoir lu combien de gestes de
    sauvegarde la trace contient.
    """
    from falcon.commandes.cartographie import (
        annoncer_la_session, cartographier,
    )
    from falcon.exploration.rapport import previsualisation
    from falcon.noyau import ErreurFalcon
    from falcon.trace import TraceInvalide, lire

    chemin = demander_chemin(console, "trace du recorder (.vbs)")
    if chemin is None:
        return CONTINUER
    catalogue = demander_chemin(console, "dossier du catalogue")
    if catalogue is None:
        return CONTINUER

    try:
        trace = lire(chemin)
    except TraceInvalide as erreur:
        console.ecrire(f"\n  TraceInvalide : {erreur}")
        console.ecrire("  Une trace a moitie comprise ne se rejoue pas. Passe "
                       "par « 2 > Inventaire ».")
        console.pause()
        return CONTINUER

    console.titre("Explorer la trace dans SAP")
    console.ecrire()
    console.ecrire(previsualisation(trace))

    plafond_gestes = _demander_plafond(console, "plafond d'actions envoyees "
                                                "a SAP")
    if plafond_gestes is None:
        return CONTINUER
    plafond_ecrans = _demander_plafond(console, "plafond d'ecrans verses en "
                                                "quarantaine")
    if plafond_ecrans is None:
        return CONTINUER

    # La connexion precede la confirmation : le mandant doit se lire a
    # l'endroit meme ou l'on decide de lancer. Elle ne fait que LIRE.
    try:
        driver = env.connecter()
        console.ecrire()
        console.ecrire("  session SAP :")
        console.ecrire(annoncer_la_session(driver))
    except ErreurFalcon as erreur:
        console.ecrire(f"\n  {type(erreur).__name__} : {erreur}")
        console.pause()
        return CONTINUER

    if not confirmer(console, chemin.name,
                     annonce="Ceci va AGIR dans SAP, sur la session ci-dessus.",
                     quoi="le nom du fichier de trace"):
        return CONTINUER

    try:
        _, _, compte_rendu = cartographier(
            chemin, catalogue, plafond_gestes=plafond_gestes,
            plafond_ecrans=plafond_ecrans, esquisses=True, driver=driver)
    except ErreurFalcon as erreur:
        console.ecrire(f"\n  {type(erreur).__name__} : {erreur}")
        console.pause()
        return CONTINUER

    console.ecrire()
    console.ecrire(compte_rendu)
    console.pause()
    return CONTINUER


def _demander_plafond(console: Console, invite: str) -> int | None:
    """Un plafond, sans defaut et strictement positif.

    Sans defaut a dessein : le §5.5 fait du rayon d'action une obligation. Un
    defaut serait un rayon que personne n'a choisi, sur l'entree de console
    qui agit dans SAP sans pipeline pour declarer ses bornes.
    """
    try:
        saisie = console.lire(f"\n  {invite} : ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not saisie.isdigit() or int(saisie) <= 0:
        console.ecrire("\n  Un nombre entier strictement positif est attendu. "
                       "Un plafond nul")
        console.ecrire("  donnerait une exploration qui semble passer et n'a "
                       "rien vu.")
        console.pause()
        return None
    return int(saisie)


# ---------------------------------------------------------------------------

def ecran_taxonomie(env: Environnement) -> Menu:
    """Recolter la taxonomie : d'un inconnu bloquant a l'entree qui le classe.

    Le maillon qui manquait. Tout incident non apparie est `inconnue`, donc
    BLOQUANT, et le registre livre ne porte aucun message SAP — il ne peut pas
    en porter, personne n'en a observe. Sur un systeme reel, le premier
    message d'erreur metier arrete donc le lot entier ; c'est le comportement
    voulu, mais il ne laissait aucune sortie.
    """

    def _dossier(console: Console):
        """Le dossier de dumps, ou None. Par defaut a cote d'un journal."""
        chemin = demander_chemin(console, "dossier de dumps, ou journal JSONL")
        if chemin is None:
            return None
        # On accepte le JOURNAL, parce que c'est le chemin que l'utilisateur a
        # sous les yeux : les dumps sont ecrits a cote, dans « dumps ».
        if chemin.is_file():
            chemin = chemin.parent / "dumps"
        if not chemin.is_dir():
            console.ecrire(f"\n  {chemin} n'est pas un dossier de dumps.")
            console.ecrire("  Aucun incident inconnu n'a donc bloque de lot.")
            console.pause()
            return None
        return chemin

    def inspecter(console: Console) -> str:
        from falcon.taxonomie.recolte import dumps_de, lire_dump

        console.titre("Incidents inconnus")
        dossier = _dossier(console)
        if dossier is None:
            return CONTINUER

        chemins = dumps_de(dossier)
        if not chemins:
            console.ecrire(f"\n  {dossier} ne porte aucun dump.")
            console.ecrire("  Aucun incident inconnu n'a bloque de lot — "
                           "c'est une bonne nouvelle.")
            console.pause()
            return CONTINUER

        console.ecrire(f"\n  {len(chemins)} dump(s), du plus recent au plus "
                       f"ancien.\n")
        for chemin in chemins:
            inconnu = lire_dump(chemin)
            console.ecrire(f"  {chemin.name}")
            console.ecrire(f"    item {inconnu.item_id or '?'}   "
                           f"garde {inconnu.garde or '?'}   "
                           f"canal {inconnu.canal}")
            for cle, valeur in sorted(inconnu.detail.items()):
                console.ecrire(f"      {cle:<12} {valeur!r}")
            console.ecrire()
        console.pause()
        return CONTINUER

    def proposer(console: Console) -> str:
        from falcon.taxonomie.recolte import (
            dumps_de, lire_dump, surcouche_proposee,
        )

        console.titre("Surcouche de registre proposee")
        dossier = _dossier(console)
        if dossier is None:
            return CONTINUER

        chemins = dumps_de(dossier)
        if not chemins:
            console.ecrire(f"\n  {dossier} ne porte aucun dump : rien a "
                           f"proposer.")
            console.pause()
            return CONTINUER

        texte = surcouche_proposee([lire_dump(c) for c in chemins])
        console.ecrire()
        for ligne in texte.splitlines():
            console.ecrire(f"  {ligne}")

        console.ecrire()
        console.ecrire("  Ce qui a ete OBSERVE est rempli ; ce qui se DECIDE")
        console.ecrire("  porte un marqueur, et le registre refuse de charger")
        console.ecrire("  tant qu'il en reste un. Decider a ta place qu'un")
        console.ecrire("  message est benin serait ecrire une regle de")
        console.ecrire("  securite sur une seule observation.")

        chemin = demander_chemin_neuf(console,
                                      "enregistrer sous (vide : ne pas ecrire)")
        if chemin is not None:
            chemin.write_text(texte, encoding="utf-8")
            console.ecrire(f"\n  {chemin}")
        console.pause()
        return CONTINUER

    def registre_courant(console: Console) -> str:
        from falcon.taxonomie import Registre, RegistreInvalide

        console.titre("Registre en vigueur")
        chemin = demander_chemin_facultatif(
            console, "surcouche a joindre (facultatif, Entree pour aucune)")
        try:
            registre = (Registre.avec_surcouches(chemin) if chemin
                        else Registre.charger())
        except RegistreInvalide as erreur:
            console.ecrire(f"\n  Refuse.\n\n  {erreur}")
            console.pause()
            return CONTINUER

        entrees = registre.entrees
        console.ecrire(f"\n  {len(entrees)} entree(s).\n")
        for entree in entrees:
            console.ecrire(f"  {entree.nom}")
            console.ecrire(f"    {entree.categorie}   canal {entree.canal}   "
                           f"origine {entree.origine}")
            console.ecrire(f"    poursuivre {entree.politique.poursuivre}   "
                           f"item {entree.politique.item}")
        console.ecrire()
        console.ecrire("  Aucune entree livree ne porte de message SAP : elles")
        console.ecrire("  ne peuvent pas en porter, personne n'en a observe.")
        console.pause()
        return CONTINUER

    return Menu(
        titre="FALCON — taxonomie des incidents",
        preambule=(
            "Un incident que rien n'apparie est INCONNU, donc BLOQUANT, et il\n"
            "laisse un dump a cote du journal. C'est de ce dump que sort\n"
            "l'entree de registre qui le classera la prochaine fois.\n"
            "\n"
            "Rien ici n'ecrit dans SAP."),
        entrees=(
            Entree("1", "Recolter les incidents inconnus", inspecter,
                   "ce qui a bloque, et sur quelle signature"),
            Entree("2", "Proposer la surcouche a completer", proposer,
                   "le YAML a relire, completer, puis joindre a l'execution"),
            Entree("3", "Voir le registre en vigueur", registre_courant,
                   "ce qui est deja classe, livre et surcouche"),
        ))


# ---------------------------------------------------------------------------

def racine(env: Environnement | None = None) -> Menu:
    env = env or Environnement()
    return Menu(
        titre="FALCON — console",
        preambule=(
            "Automatisation SAP Front End.\n"
            "\n"
            "Tout se lit sans rien changer, SAUF ces ecrans, tous derriere\n"
            "une confirmation en toutes lettres :\n"
            "\n"
            "  « 3 > Executer », « 3 > Reprendre », « 3 > Enchainer »\n"
            "        ECRIVENT DANS SAP.\n"
            "  « 2 > Explorer la trace » — la MEME que « 8 > Explorer »\n"
            "        AGIT DANS SAP sans y ecrire : elle rejoue une trace, donc\n"
            "        elle navigue et presse des boutons."),
        entrees=(
            Entree("1", "Verification et livraison", ecran_verification(env),
                   "les suites, la preuve que les gardes protegent, le bundle"),
            Entree("2", "Traces du recorder", ecran_traces(env),
                   "couverture, ecrans conjectures, et EXPLORER la trace"),
            Entree("3", "Pipelines et donnees", ecran_pipelines(env),
                   "charger, inspecter, et EXECUTER"),
            Entree("4", "Journaux", ecran_journaux(env),
                   "rapport, etats des items, douteux, reexport des KO"),
            Entree("5", "Catalogue d'ecrans", ecran_catalogue(env),
                   "variantes curees et quarantaine"),
            Entree("6", "Exports de table", ecran_volumique(env),
                   "conservation, delta contre le precedent, carte SE16N"),
            Entree("7", "Taxonomie des incidents", ecran_taxonomie(env),
                   "inconnus bloquants, et les entrees de registre a ecrire"),
            Entree("8", "Session SAP", ecran_sap(env),
                   "diagnostic de l'ecran courant, et CARTOGRAPHIE d'une trace"),
        ))
