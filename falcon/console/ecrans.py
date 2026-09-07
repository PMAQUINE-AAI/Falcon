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


def _rapporteur() -> Any:
    """L'observateur de progression du lot 11. Muet hors terminal."""
    from falcon.supervision import Rapporteur
    return Rapporteur()


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
    #: Fabrique l'observateur de progression branche sur le moteur. La barre
    #: et l'ETA glissant existent depuis le lot 11 et n'avaient jamais rien
    #: affiche : personne ne les appelait.
    rapporteur: Callable[[], Any] = _rapporteur


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

    return Menu(
        titre="FALCON — traces du recorder",
        preambule="Lecture seule d'enregistrements .vbs. Seul le brouillon "
                  "ecrit,\net seulement un fichier que vous nommez.",
        entrees=(
            Entree("1", "Couverture du parseur", inventaire,
                   "ce qu'il sait lire, et ce qu'il n'en sait pas"),
            Entree("2", "Ecrans conjectures", ecrans,
                   "decoupage en visites, et champs touches"),
            Entree("3", "Gestes significatifs", gestes,
                   "la trace, sans les gestes de confort"),
            Entree("4", "Brouillon de pipeline", ebauche,
                   "ebauche YAML, inachevee a dessein"),
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


def confirmer(console: Console, attendu: str) -> bool:
    """Confirmation en TOUTES LETTRES. Rend True seulement sur le mot exact.

    Pas un `o/n`. Un `o/n` se tape sans lire — c'est un reflexe, et un reflexe
    n'est pas un consentement. Le mot attendu est le nom de la pipeline : on
    ne peut pas le taper sans avoir lu le recapitulatif qui le nomme, donc
    sans avoir vu au passage les plafonds, le nombre d'items et les
    derogations.

    Toute autre saisie renonce — y compris une saisie vide, une fin de flux ou
    un Ctrl-C. Le defaut est de NE PAS ecrire dans un ERP.
    """
    console.ecrire()
    console.ecrire("  Ceci va ECRIRE dans SAP. Pour confirmer, tape le nom de "
                   "la pipeline")
    console.ecrire("  en toutes lettres. Toute autre reponse annule.")
    try:
        saisie = console.lire(f"\n  nom attendu « {attendu} » : ").strip()
    except (EOFError, KeyboardInterrupt):
        saisie = ""
    if saisie == attendu:
        return True
    console.ecrire("\n  Annule. Rien n'a ete ecrit.")
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

    def _preparer(console: Console, mode: str):
        """(pipeline, jeu, items, empreinte, journal) ou None.

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
        return pipeline, jeu, items, empreinte, journal

    def _executer(console: Console, mode: str, titre: str) -> str:
        from falcon.moteur import executer
        from falcon.noyau import ErreurFalcon

        prepare = _preparer(console, mode)
        if prepare is None:
            return CONTINUER
        pipeline, jeu, items, empreinte, journal = prepare

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

        observateur = env.rapporteur()
        try:
            resultat = executer(
                pipeline, jeu, driver, journal=journal, mode=mode,
                sortie_ko=str(Path(journal).with_suffix(".ko.csv")),
                observateur=observateur)
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
        from falcon.moteur import Maillon, enchainer
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
            prepare = _preparer(console, "run")
            if prepare is None:
                break
            pipeline, jeu, items, empreinte, journal = prepare
            maillons.append(Maillon(
                pipeline=pipeline, jeu=jeu, journal=journal,
                sortie_ko=str(Path(journal).with_suffix(".ko.csv"))))
            recaps.append((pipeline, items, jeu, empreinte))
            console.ecrire(f"\n  + {pipeline.nom}  ({len(items)} item(s))")

        if not maillons:
            console.ecrire("\n  Chaine vide. Rien a lancer.")
            console.pause()
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
            resultats = enchainer(maillons, driver, observateur=observateur)
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

    return Menu(
        titre="FALCON — pipelines et donnees",
        preambule=(
            "1 a 3 : relecture, aucun geste.\n"
            "4 : repetition a blanc, s'arrete avant toute validation.\n"
            "5 a 7 : ECRIVENT DANS SAP, apres confirmation en toutes lettres."),
        entrees=(
            Entree("1", "Charger et valider une pipeline", valider,
                   "ce que les gardes verront, etape par etape"),
            Entree("2", "Relire un brouillon", brouillon,
                   "meme chose, marqueurs toleres"),
            Entree("3", "Inspecter un jeu de donnees", jeu,
                   "dialecte, colonnes, et regroupement en items"),
            Entree("4", "Repetition a blanc", a_blanc,
                   "tout sauf la validation — aucune ecriture dans SAP"),
            Entree("5", "Executer", lancer,
                   "ECRIT DANS SAP. Confirmation en toutes lettres"),
            Entree("6", "Reprendre une execution", reprendre,
                   "ECRIT DANS SAP. Les douteux ne sont jamais rejoues"),
            Entree("7", "Enchainer des pipelines", enchainer_les,
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
            "Automatisation SAP Front End.\n"
            "\n"
            "Tout se lit sans rien changer, SAUF trois ecrans — « 3 > Executer »,\n"
            "« 3 > Reprendre » et « 3 > Enchainer » — qui ECRIVENT DANS SAP,\n"
            "apres confirmation en toutes lettres."),
        entrees=(
            Entree("1", "Verification et livraison", ecran_verification(env),
                   "les suites, la preuve que les gardes protegent, le bundle"),
            Entree("2", "Traces du recorder", ecran_traces(env),
                   "couverture du parseur, ecrans conjectures, gestes"),
            Entree("3", "Pipelines et donnees", ecran_pipelines(env),
                   "charger, inspecter, et EXECUTER"),
            Entree("4", "Journaux", ecran_journaux(env),
                   "rapport, etats des items, douteux, reexport des KO"),
            Entree("5", "Catalogue d'ecrans", ecran_catalogue(env),
                   "variantes curees et quarantaine"),
            Entree("6", "Exports de table", ecran_volumique(env),
                   "conservation, delta contre le precedent, carte SE16N"),
            Entree("7", "Session SAP", ecran_sap(env),
                   "diagnostic de l'ecran courant, en lecture seule"),
        ))
