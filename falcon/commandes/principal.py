"""La ligne de commande de FALCON.

Minimale, et delibere. Aucune de ces commandes n'ecrit dans SAP : elles
regardent un ecran, une trace, un catalogue. C'est tout ce qui a du sens tant
qu'aucune pipeline n'a tourne sur un systeme reel.

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

Six commandes. Une seule peut ecrire dans SAP — `console` — et elle ne le
fait que sur trois de ses ecrans, apres confirmation du nom de la pipeline
en toutes lettres. Les cinq autres sont en lecture seule.

  console         menus interactifs : tests, traces, catalogue, EXECUTION
  diagnostiquer   identite de l'ecran courant et releve des champs
  inventaire      rapport de couverture d'une trace du SAP GUI Recorder
  brouillon       ebauche de pipeline depuis une trace — inachevee a dessein
  dictionnaire    le catalogue a plat, en CSV lisible par un tableur
  recolter        les entrees de registre a ecrire, d'apres les dumps

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

    return principal


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


COMMANDES = {"console": _console, "diagnostiquer": _diagnostiquer,
             "inventaire": _inventaire, "brouillon": _brouillon,
             "dictionnaire": _dictionnaire, "recolter": _recolter}


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
