"""La ligne de commande de FALCON.

Minimale, et delibere. **Aucune de ces commandes n'ECRIT dans SAP**, mais deux
d'entre elles y AGISSENT, et la nuance compte assez pour etre ecrite ici :

  - `console` peut lancer une pipeline, donc ecrire, apres confirmation ;
  - `explorer` rejoue une trace en observation. Elle ne SAUVEGARDE rien —
    toute sauvegarde reconnue est refusee — mais elle saisit des valeurs dans
    les champs, navigue, presse des boutons et lance des selections.
    « Lecture seule » serait faux, et « n'ecrit rien » aussi : un `write` en
    dry-run tape dans SAP, il n'est simplement jamais valide.

Les autres regardent un ecran, une trace, un catalogue, et rien de plus.

`argparse` plutot qu'une bibliotheque : la livraison est un fichier unique, et
chaque dependance de plus est une piece a embarquer.

**Les erreurs de lecture se rendent lisibles, pas en trace de pile.** Elles
disent deja ce qui ne va pas — un YAML mal forme, une ligne de trace inconnue,
un registre ambigu — et une trace de pile ferait croire a un defaut du
programme la ou c'est le fichier qui est en cause. Elles n'heritent pas toutes
d'`ErreurFalcon` : `ErreurFalcon` est la hierarchie de l'EXECUTION, ces
erreurs-la sont celles du CHARGEMENT. D'ou la liste explicite ci-dessous.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from falcon.catalogue import CatalogueInvalide
from falcon.donnees import JeuInvalide
from falcon.noyau import ErreurFalcon
from falcon.pipeline import PipelineInvalide
from falcon.taxonomie import RegistreInvalide
from falcon.trace import TraceInvalide

#: Ce qui se rend lisible plutot qu'en trace de pile.
ERREURS_LISIBLES = (ErreurFalcon, TraceInvalide, PipelineInvalide,
                    CatalogueInvalide, JeuInvalide, RegistreInvalide)

DESCRIPTION = """FALCON — automatisation SAP Front End.

Une seule commande peut ECRIRE dans SAP — `console` — et seulement sur trois
de ses ecrans, apres confirmation du nom de la pipeline en toutes lettres.

`explorer` ne SAUVEGARDE rien mais AGIT : elle rejoue une trace, donc elle
saisit des valeurs, navigue et presse des boutons. Elle demande, elle aussi,
le nom du fichier de trace en toutes lettres. Les autres commandes sont en
lecture seule.

  console         menus interactifs : tests, traces, catalogue, EXECUTION
  explorer        rejoue une trace en OBSERVATION et peuple la quarantaine
  diagnostiquer   identite de l'ecran courant et releve des champs
  inventaire      rapport de couverture d'une trace du SAP GUI Recorder
  brouillon       ebauche de pipeline depuis une trace — inachevee a dessein
  dictionnaire    le catalogue a plat, en CSV lisible par un tableur
  composer        les CSV du classeur -> une pipeline YAML
  promouvoir      verse une capture de quarantaine au catalogue
  recolter        les entrees de registre a ecrire, d'apres les dumps
  sonde           ce que CE terminal sait faire — mesure, jamais supposition

Pour tout faire depuis un seul endroit :  python -m falcon console
"""


def analyseur() -> argparse.ArgumentParser:
    principal = argparse.ArgumentParser(
        prog="falcon", description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    principal.add_argument("--aide", action="help",
                           help="affiche cette aide et sort")
    sous = principal.add_subparsers(dest="commande")

    sous.add_parser(
        "console", help="menus interactifs (tests, traces, catalogue, SAP)",
        description="Tout FALCON depuis un seul endroit. Trois ecrans "
                    "ECRIVENT dans SAP — execution, reprise, enchainement — "
                    "et demandent le nom de la pipeline en toutes lettres "
                    "avant d'agir. La repetition a blanc, elle, n'ecrit rien.")

    diagnostic = sous.add_parser(
        "diagnostiquer",
        help="ecran courant de la session SAP ouverte (LECTURE SEULE)",
        description="Se greffe sur une session SAP deja ouverte et deja "
                    "authentifiee. N'ecrit rien dans SAP.")
    diagnostic.add_argument("--fenetre", default="wnd[0]",
                            help="fenetre a relever (defaut : wnd[0])")
    diagnostic.add_argument("--catalogue", metavar="DOSSIER", default=None,
                            help="verse le releve en QUARANTAINE du catalogue "
                                 "indique ; la promotion reste un geste "
                                 "explicite")
    diagnostic.add_argument("--connexion", type=int, default=0)
    diagnostic.add_argument("--session", type=int, default=0)

    trace = sous.add_parser(
        "inventaire", help="rapport de couverture d'une trace .vbs",
        description="Ce que le parseur sait lire d'un enregistrement, et ce "
                    "qu'il n'en sait pas.")
    trace.add_argument("traces", nargs="+", metavar="TRACE.vbs")

    ebauche = sous.add_parser(
        "brouillon", help="ebauche de pipeline depuis une trace .vbs",
        description="Produit un YAML de pipeline INACHEVE : tout ce que la "
                    "trace ne dit pas porte un marqueur, et `charger()` "
                    "refuse le fichier tant qu'il en reste un.")
    ebauche.add_argument("trace", metavar="TRACE.vbs")
    ebauche.add_argument("-o", "--sortie", metavar="PIPELINE.yaml",
                         default=None,
                         help="fichier a ecrire (defaut : sortie standard)")
    ebauche.add_argument("--nom", default="",
                         help="nom de la pipeline (defaut : un marqueur)")

    dico = sous.add_parser(
        "dictionnaire", help="le catalogue a plat, en CSV pour un tableur",
        description="Une ligne par champ, pour qu'un tableur puisse proposer "
                    "les ecrans et les champs disponibles. Ecrit en UTF-8 "
                    "AVEC BOM et delimite par « ; » : c'est ce qu'un Excel "
                    "francais lit sans rien demander.")
    dico.add_argument("catalogue", metavar="DOSSIER",
                      help="dossier du catalogue a recenser")
    dico.add_argument("-o", "--sortie", metavar="DICTIONNAIRE.csv",
                      default="dictionnaire.csv",
                      help="fichier a ecrire (defaut : dictionnaire.csv)")
    dico.add_argument("--quarantaine", action="store_true",
                      help="recenser la quarantaine plutot que le catalogue "
                           "cure — utile pour un ecran tout juste releve")

    recolte = sous.add_parser(
        "recolter", help="propose les entrees de registre d'apres les dumps",
        description="Un incident inconnu est bloquant, et laisse un dump. "
                    "Cette commande relit ces dumps et propose la surcouche "
                    "de registre a completer : c'est le geste que l'en-tete "
                    "du registre appelle « la taxonomie se recolte ». Rien "
                    "n'est decide a ta place — categorie et politique portent "
                    "un marqueur, et le fichier refuse de charger tant qu'il "
                    "en reste un.")
    recolte.add_argument("dumps", metavar="DOSSIER",
                         help="dossier de dumps (a cote du journal, par "
                              "defaut : <journal>/../dumps)")
    recolte.add_argument("-o", "--sortie", metavar="SURCOUCHE.yaml",
                         default=None,
                         help="fichier a ecrire (defaut : sortie standard)")

    composer = sous.add_parser(
        "composer", help="convertit les CSV du classeur en pipeline YAML",
        description="Trois CSV — pipeline.csv, etapes.csv, derogations.csv — "
                    "produits par le classeur, convertis en une pipeline "
                    "YAML. Le fichier n'est ecrit QUE si FALCON le recharge "
                    "sans rien refuser : un YAML casse a cote d'un YAML "
                    "valide plus ancien, c'est le mauvais fichier lance un "
                    "jour de fatigue.")
    composer.add_argument("dossier", metavar="DOSSIER",
                          help="dossier portant les trois CSV")
    composer.add_argument("-o", "--sortie", metavar="PIPELINE.yaml",
                          default=None,
                          help="fichier a ecrire (defaut : sortie standard, "
                               "sans rien ecrire)")

    promotion = sous.add_parser(
        "promouvoir", help="verse une capture de quarantaine au catalogue",
        description="`diagnostiquer --catalogue` verse en QUARANTAINE, et dit "
                    "que la promotion reste un geste explicite. C'est ce "
                    "geste. Sans argument, il LISTE ce qui attend ; avec une "
                    "empreinte, il promeut cette capture-la. La console "
                    "(« 5 > Promouvoir ») montre en plus ce qu'on promeut "
                    "avant de le promouvoir.")
    promotion.add_argument("catalogue", metavar="DOSSIER")
    promotion.add_argument("--empreinte", default=None,
                           help="empreinte de la capture a promouvoir ; sans "
                                "elle, la commande se contente de lister")

    exploration = sous.add_parser(
        "explorer", help="rejoue une trace en OBSERVATION et peuple la "
                         "quarantaine",
        description="Etape 2 du cycle de vie : FALCON rejoue la trace, releve "
                    "chaque ecran traverse et le verse en QUARANTAINE. "
                    "Ne SAUVEGARDE rien — toute sauvegarde reconnue est "
                    "refusee — mais AGIT : elle saisit des valeurs dans les "
                    "champs, navigue, presse des boutons et lance des "
                    "selections qui peuvent tourner longtemps. Exige une "
                    "session SAP ouverte, et le nom du fichier de trace en "
                    "toutes lettres. A lancer sur un mandant de qualite avant "
                    "la production.")
    exploration.add_argument("trace", metavar="TRACE.vbs")
    exploration.add_argument("--catalogue", metavar="DOSSIER", required=True,
                             help="dossier du catalogue ; les releves vont "
                                  "dans son sous-dossier `quarantaine`")
    # Les deux plafonds sont REQUIS et sans defaut. Le §5.5 dit « rayon
    # d'action obligatoire », et le chargeur de pipeline applique deja
    # litteralement cette phrase. Un defaut serait un rayon d'action que
    # personne n'a choisi, sur la seule commande qui agit dans SAP sans
    # pipeline pour declarer ses bornes.
    exploration.add_argument("--plafond-gestes", type=int, required=True,
                             metavar="N",
                             help="nombre maximal d'actions envoyees a SAP, "
                                  "gestes de reprise compris (obligatoire)")
    exploration.add_argument("--plafond-ecrans", type=int, required=True,
                             metavar="N",
                             help="nombre maximal d'ecrans verses en "
                                  "quarantaine (obligatoire)")
    exploration.add_argument("--esquisses", action="store_true",
                             help="verse aussi, en quarantaine, les esquisses "
                                  "des visites NON atteintes — une liste de "
                                  "courses, pas des releves")
    exploration.add_argument("--registre", metavar="SURCOUCHE.yaml",
                             action="append", default=[],
                             help="surcouche de taxonomie ; repetable")
    exploration.add_argument("--oui-je-sais", metavar="TRACE.vbs", default="",
                             help="nom du fichier de trace, en toutes "
                                  "lettres ; sans lui la commande demande la "
                                  "confirmation au terminal")
    exploration.add_argument("--connexion", type=int, default=0)
    exploration.add_argument("--session", type=int, default=0)

    sous.add_parser(
        "sonde", help="ce que CE terminal sait faire (LECTURE SEULE)",
        description="Mesure, dans CE processus et sur CE terminal, la taille "
                    "de la fenetre et la capacite a interpreter les sequences "
                    "ANSI. Chaque « oui » est un appel systeme qui a reussi ; "
                    "chaque « non » nomme l'appel qui a refuse. C'est la "
                    "commande a lancer EN PREMIER sur une machine neuve, et "
                    "celle qu'on demande par telephone quand un affichage est "
                    "illisible. N'ecrit rien, ne se connecte a rien.")

    return principal


def _promouvoir(options: argparse.Namespace) -> int:
    from falcon.catalogue import CatalogueInvalide, Depot

    racine = Path(options.catalogue)
    if not racine.is_dir():
        print(f"{racine} n'est pas un dossier", file=sys.stderr)
        return 1

    depot = Depot(racine)
    ecarte = Depot(depot.quarantaine)
    clefs = [v.clef for t in ecarte.triplets() for v in ecarte.variantes(t)]
    if not clefs:
        print(f"{racine} : la quarantaine est vide. Une capture y entre par "
              f"`diagnostiquer --catalogue`.", file=sys.stderr)
        return 1

    if not options.empreinte:
        # Sans empreinte on LISTE, on ne promeut pas « la premiere ». Choisir
        # a la place de l'utilisateur ce qu'il certifie avoir relu serait le
        # contraire de ce que ce geste signifie.
        print(f"{len(clefs)} capture(s) en quarantaine :\n")
        for clef in clefs:
            variante = ecarte.pour_edition(clef)
            marque = "observee" if variante.observee else "ESQUISSE"
            print(f"  {clef.empreinte}  {clef.transaction}/{clef.programme}"
                  f"/{clef.dynpro}  {len(variante.champs):>3} champ(s)  "
                  f"{marque}")
        print("\n  --empreinte <EMPREINTE> pour en promouvoir une.")
        return 0

    choisies = [c for c in clefs if c.empreinte == options.empreinte]
    if not choisies:
        print(f"empreinte {options.empreinte!r} : rien de tel en quarantaine",
              file=sys.stderr)
        return 1

    try:
        chemin = depot.promouvoir(choisies[0])
    except CatalogueInvalide as erreur:
        print(str(erreur), file=sys.stderr)
        return 1
    print(f"{chemin}")
    return 0


def _composer(options: argparse.Namespace) -> int:
    from falcon.tableur import TableurInvalide, convertir, convertir_fichiers

    dossier = Path(options.dossier)
    if not dossier.is_dir():
        print(f"{dossier} n'est pas un dossier", file=sys.stderr)
        return 1

    try:
        if not options.sortie:
            # Sans `-o`, on MONTRE sans ecrire. La relecture par `charger()`
            # n'a pas lieu : elle exige un fichier, et ecrire pour verifier
            # irait contre l'objet meme du mode sans sortie.
            print(convertir(dossier), end="")
            return 0
        chemin = convertir_fichiers(dossier, options.sortie)
    except TableurInvalide as erreur:
        print(str(erreur), file=sys.stderr)
        return 1

    print(f"{chemin}")
    return 0


def _recolter(options: argparse.Namespace) -> int:
    from falcon.taxonomie.recolte import (
        dumps_de, lire_dump, surcouche_proposee,
    )

    dossier = Path(options.dumps)
    if not dossier.is_dir():
        print(f"{dossier} n'est pas un dossier. Les dumps sont ecrits a cote "
              f"du journal, dans « dumps ».", file=sys.stderr)
        return 1

    chemins = dumps_de(dossier)
    if not chemins:
        # Aucun dump n'est une BONNE nouvelle : rien n'a bloque. Le dire
        # comme tel, plutot que de rendre un fichier vide qu'on prendrait
        # pour une surcouche legitime.
        print(f"{dossier} ne porte aucun dump : aucun incident inconnu n'a "
              f"bloque de lot.", file=sys.stderr)
        return 1

    texte = surcouche_proposee([lire_dump(c) for c in chemins])
    if options.sortie:
        Path(options.sortie).write_text(texte, encoding="utf-8")
        print(f"{options.sortie}  —  {len(chemins)} entree(s) a completer")
    else:
        print(texte)
    return 0


def _dictionnaire(options: argparse.Namespace) -> int:
    from falcon.catalogue import Depot
    from falcon.commandes.dictionnaire import exporter, recenser

    racine = Path(options.catalogue)
    if not racine.is_dir():
        print(f"{racine} n'est pas un dossier", file=sys.stderr)
        return 1

    depot = Depot(racine)
    if options.quarantaine:
        depot = Depot(depot.quarantaine)

    lignes = recenser(depot)
    if not lignes:
        # Un fichier vide serait pris pour un catalogue vide plutot que pour
        # un dossier qui n'est pas celui qu'on croit. Le dire, et ne rien
        # ecrire.
        print(f"{racine} ne porte aucun champ a recenser. Un ecran entre au "
              f"catalogue par `diagnostiquer --catalogue`.", file=sys.stderr)
        return 1

    chemin = exporter(depot, options.sortie)
    ecrans = len({(l["transaction"], l["programme"], l["dynpro"],
                   l["empreinte"]) for l in lignes})
    print(f"{chemin}  —  {len(lignes)} champ(s) sur {ecrans} variante(s)")
    return 0


def _diagnostiquer(options: argparse.Namespace) -> int:
    # Imports locaux : `falcon.couture.sapgui` charge pywin32 quand on lui
    # demande de se connecter, et rien avant. `python -m falcon inventaire`
    # doit marcher sur une machine qui n'aura jamais de SAP GUI.
    from falcon.commandes.diagnostic import diagnostiquer
    from falcon.couture import DriverLecture
    from falcon.couture.sapgui import connecter

    driver = connecter(connexion=options.connexion, session=options.session)
    print(diagnostiquer(DriverLecture(driver), fenetre=options.fenetre,
                        catalogue=options.catalogue))
    return 0


def _sonde(options: argparse.Namespace) -> int:
    """Le releve des deux flux, imprime sur la sortie standard.

    Les DEUX, et pas seulement celui-ci : sur Windows, le bit VT est un mode
    par HANDLE, donc une capacite mesuree sur `stdout` ne dit rien de `stderr`.
    Le navigateur ecrira sur l'un et le direct sur l'autre ; quelqu'un qui
    tape `falcon explorer ... 2> journal.log` doit pouvoir lire ici pourquoi
    son journal reste propre alors que son ecran est en couleur.

    Tout sort sur la SORTIE standard, y compris le releve de l'erreur standard.
    Ecrire sur `stderr` pour parler de `stderr` melangerait la mesure et son
    objet : `falcon sonde > sonde.txt` doit donner un fichier complet, c'est
    tout l'interet d'une commande qu'on demande a distance.
    """
    from falcon.toile import rendre_sonde, sonder, systeme_reel

    releves = tuple(sonder(systeme_reel(flux, nom))
                    for flux, nom in ((sys.stdout, "stdout"),
                                      (sys.stderr, "stderr")))
    for ligne in rendre_sonde(releves):
        print(ligne)
    return 0


def _console(options: argparse.Namespace) -> int:
    from falcon.console import Console, parcourir, racine

    if not sys.stdin.isatty():
        # Une console interactive sur un flux non interactif ne peut rien
        # faire d'utile, et boucler sur un `input` qui leve immediatement
        # produirait un mur d'ecrans. Mieux vaut le dire.
        print("`console` demande un terminal interactif. Hors terminal, "
              "utiliser `inventaire` ou `diagnostiquer`.", file=sys.stderr)
        return 2
    return parcourir(racine(), Console())


def _inventaire(options: argparse.Namespace) -> int:
    from falcon.trace.inventaire import main as inventorier
    return inventorier(list(options.traces))


def _brouillon(options: argparse.Namespace) -> int:
    from falcon.trace import brouillon_de, lire
    from falcon.trace.brouillon import apercu

    # Lecture STRICTE : un brouillon bati sur des lignes non appariees serait
    # faux sans le dire. Une trace que `lire` refuse doit passer par
    # `inventaire`, qui nomme ce qui manque.
    ebauche = brouillon_de(lire(Path(options.trace)), nom=options.nom)
    if options.sortie:
        Path(options.sortie).write_text(ebauche.yaml, encoding="utf-8")
        print(f"{options.sortie} ecrit.\n")
    else:
        print(ebauche.yaml)
    print(apercu(ebauche), file=sys.stderr)
    return 0


def _explorer(options: argparse.Namespace) -> int:
    """Rejoue une trace en observation. La seule commande, avec `console`, qui
    exige une session SAP ouverte — et qui AGIT dessus.

    La confirmation porte sur le NOM DU FICHIER DE TRACE, en toutes lettres.
    Un `o/n` se tape sans lire ; le nom du fichier ne peut se taper qu'apres
    avoir vu le recapitulatif qui l'annonce, donc au passage le nombre de
    gestes de sauvegarde que la trace contient.
    """
    from falcon.commandes.cartographie import (
        INCOMPLET, TERMINE, annoncer_la_session, cartographier,
    )
    from falcon.couture.sapgui import connecter
    from falcon.exploration import TERMINEE
    from falcon.exploration.rapport import previsualisation
    from falcon.taxonomie import Registre
    from falcon.trace import lire

    chemin = Path(options.trace)
    attendu = chemin.name

    print(f"exploration de {chemin}")
    print(previsualisation(lire(chemin)), file=sys.stderr)
    print(f"\n  plafonds : {options.plafond_gestes} action(s), "
          f"{options.plafond_ecrans} ecran(s)", file=sys.stderr)

    # La connexion precede la confirmation, pour que le mandant se lise a
    # l'endroit meme ou l'on decide de lancer. Elle n'agit pas : elle se
    # greffe sur une session ouverte et en LIT l'identite.
    driver = connecter(connexion=options.connexion, session=options.session)
    print("\n  session SAP :", file=sys.stderr)
    print(annoncer_la_session(driver), file=sys.stderr)

    if options.oui_je_sais != attendu:
        if not sys.stdin.isatty():
            print(f"\nConfirmation requise. Hors terminal, passer "
                  f"`--oui-je-sais {attendu}`.", file=sys.stderr)
            return 2
        print("\n  Ceci va AGIR dans SAP : naviguer, presser des boutons, "
              "lancer des", file=sys.stderr)
        print("  selections. Aucune donnee ne sera ecrite. Pour confirmer, "
              "tape le nom", file=sys.stderr)
        print("  du fichier de trace en toutes lettres.", file=sys.stderr)
        try:
            saisie = input(f"\n  nom attendu « {attendu} » : ").strip()
        except (EOFError, KeyboardInterrupt):
            saisie = ""
        if saisie != attendu:
            print("\n  Annule. Rien n'a ete fait.", file=sys.stderr)
            return 2

    _, exploration, compte_rendu = cartographier(
        chemin, options.catalogue,
        plafond_gestes=options.plafond_gestes,
        plafond_ecrans=options.plafond_ecrans,
        esquisses=options.esquisses,
        registre=Registre.avec_surcouches(*options.registre),
        driver=driver)

    print()
    print(compte_rendu)
    # 0 seulement si la trace a ete parcourue de bout en bout. Une
    # cartographie coupee a la visite 17 sur 40 qui rendrait 0 serait un
    # succes annonce sur un travail a moitie fait.
    return TERMINE if exploration.etat == TERMINEE else INCOMPLET


COMMANDES = {"console": _console, "diagnostiquer": _diagnostiquer,
             "inventaire": _inventaire, "brouillon": _brouillon,
             "dictionnaire": _dictionnaire, "recolter": _recolter,
             "composer": _composer, "promouvoir": _promouvoir,
             "explorer": _explorer, "sonde": _sonde}


def main(arguments: list[str] | None = None) -> int:
    principal = analyseur()
    options = principal.parse_args(sys.argv[1:] if arguments is None
                                   else arguments)
    if options.commande is None:
        principal.print_help()
        return 2
    try:
        return COMMANDES[options.commande](options)
    except BrokenPipeError:
        # `falcon inventaire trace.vbs | head` : le lecteur est parti, ce
        # n'est pas une erreur du programme. Une trace de pile ici ferait
        # croire a un defaut.
        return 0
    except ERREURS_LISIBLES as erreur:
        # Une erreur de FALCON se rend lisible, pas sous forme de trace de
        # pile : elle dit deja ce qui ne va pas, et une trace de pile ferait
        # croire a un defaut du programme.
        print(f"\n{type(erreur).__name__} : {erreur}", file=sys.stderr)
        return 1
