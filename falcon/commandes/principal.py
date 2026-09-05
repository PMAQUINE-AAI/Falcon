"""La ligne de commande de FALCON.

Minimale, et delibere : deux commandes, `diagnostiquer` et `inventaire`. Ce
sont les deux seules qui aient du sens tant qu'aucune pipeline n'a tourne sur
un systeme reel — l'une regarde un ecran, l'autre regarde une trace, et
aucune n'ecrit nulle part dans SAP.

`argparse` plutot qu'une bibliotheque : la livraison est un fichier unique, et
chaque dependance de plus est une piece a embarquer.
"""

from __future__ import annotations

import argparse
import sys

from falcon.noyau import ErreurFalcon

DESCRIPTION = """FALCON — automatisation SAP Front End.

Trois commandes, et aucune n'ecrit dans SAP :

  console         menus interactifs : tests, traces, catalogue, diagnostic
  diagnostiquer   identite de l'ecran courant et releve des champs
  inventaire      rapport de couverture d'une trace du SAP GUI Recorder

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
        description="Tout FALCON depuis un seul endroit. Aucun ecran n'ecrit "
                    "dans SAP.")

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

    return principal


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


COMMANDES = {"console": _console, "diagnostiquer": _diagnostiquer,
             "inventaire": _inventaire}


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
    except ErreurFalcon as erreur:
        # Une erreur de FALCON se rend lisible, pas sous forme de trace de
        # pile : elle dit deja ce qui ne va pas, et une trace de pile ferait
        # croire a un defaut du programme.
        print(f"\n{type(erreur).__name__} : {erreur}", file=sys.stderr)
        return 1
