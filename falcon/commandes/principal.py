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
                                  "dans son sous-dossier `quarantaine`, et le "
                                  "compte rendu dans son sous-dossier "
                                  "`rapports`")
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
    # Le direct, et les deux facons de le refuser. Elles ne se recouvrent pas :
    # `--muet` ne montre plus rien, `--sans-couleur` montre la meme chose sans
    # decor. Aucune des deux ne change ce que le parcours FAIT.
    exploration.add_argument("--muet", action="store_true",
                             help="coupe le direct : rien ne s'affiche "
                                  "pendant le rejeu, seul le compte rendu "
                                  "sort a la fin")
    exploration.add_argument("--sans-couleur", action="store_true",
                             help="le meme direct, sans couleur, sans avoir "
                                  "a argumenter pourquoi (le decor de texte "
                                  "reste : il est en ASCII)")

    sous.add_parser(
        "sonde", help="ce que CE terminal sait faire (DIAGNOSTIC)",
        description="Interroge, dans CE processus et sur CE terminal, la "
                    "taille de la fenetre et la capacite a interpreter les "
                    "sequences ANSI. Chaque ligne porte sa provenance : "
                    "« mesure » veut dire qu'un appel systeme a repondu, "
                    "« declare » qu'une variable de l'hote l'affirme sans que "
                    "rien ne le verifie — sur POSIX, ANSI ne se mesure pas, "
                    "il se lit dans TERM. C'est la commande a lancer EN "
                    "PREMIER sur une machine neuve, et celle qu'on demande "
                    "par telephone quand un affichage est illisible. Ne se "
                    "connecte a rien et n'ecrit aucun fichier ; sur Windows "
                    "elle pose le bit VT de la console puis le restaure, ce "
                    "qui est la seule facon de le MESURER.")

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
    """La console, et le SEUL endroit ou sa geometrie se mesure vraiment.

    `Environnement.capacites` a pour defaut `_capacites_nues` — tout faux —
    et ce defaut reste : il fait dependre le rendu de la suite de rien du
    tout, donc la CI exerce le meme chemin qu'un poste de developpement. Mais
    « la mesure est un geste que le programme pose », et c'est ICI qu'il se
    pose. Sans ce cablage, `gabarit_pour` rendait TOUJOURS
    `Gabarit(72, 24, INCONNUE)` : mesure faite en pilotant `falcon.pyz console`
    dans un pty regle a 80x24, l'accueil du navigateur imprimait « largeur 72
    (inconnue), hauteur 24 ». Sur un Windows Terminal maximise a 200x50, le
    navigateur employait 72 colonnes sur 200 et paginait pour 24 lignes sur
    50, en tronquant a `~` des identifiants qui tenaient — et deux docstrings
    affirmaient la remesure a chaque tour d'un gabarit qui etait une
    constante.

    `stdout` et non `stderr` : c'est le flux ou `Console.ecrire` ecrit, et sur
    Windows la capacite a interpreter une sequence est un mode par HANDLE.
    Mesurer l'un pour peindre sur l'autre serait une capacite affirmee sans
    avoir ete mesuree.
    """
    from falcon.console import Console, Environnement, parcourir, racine

    if not sys.stdin.isatty():
        # Une console interactive sur un flux non interactif ne peut rien
        # faire d'utile, et boucler sur un `input` qui leve immediatement
        # produirait un mur d'ecrans. Mieux vaut le dire.
        print("`console` demande un terminal interactif. Hors terminal, "
              "utiliser `inventaire` ou `diagnostiquer`.", file=sys.stderr)
        return 2
    # Une FONCTION, et pas une valeur : le navigateur la rappelle a chaque
    # tour. Windows n'a pas de `SIGWINCH`, et une reconnexion RDP a une autre
    # resolution redimensionne la console de l'hote en pleine session.
    env = Environnement(capacites=lambda: _capacites_a_peindre(sys.stdout,
                                                               "stdout"))
    return parcourir(racine(env), Console())


def _capacites_a_peindre(flux, nom: str):
    """Ce que le flux sait faire, ET le bit VT repose dessus avant de peindre.

    **Le trou que cette fonction bouche.** `sonder` RESTAURE le mode qu'elle a
    trouve — elle mesure, elle ne regle pas — et `reposer_le_bit` existe pour
    le reposer avant de peindre. Sa propre docstring disait : « L'appelant —
    aujourd'hui `commandes/principal.py:_explorer` — en fait un `forcer_nu`.
    Il n'y a pas d'autre usage. » C'etait faux depuis que la console peint :
    elle sondait `stdout`, en tirait un `PeintreColore`, et n'avait jamais
    repose le bit. Sur un conhost de Windows 10 ou de PowerShell 5.1 — la
    machine cible, ou VT est ETEINT par defaut — chaque ligne du navigateur
    serait sortie en `<-[1m` en toutes lettres.

    Et la garde n°9 n'aurait pas mordu : elle ne regarde que les CAPACITES,
    qui etaient vraies. C'est l'etat du HANDLE qui avait change apres la
    mesure. Des capacites exactes, un terminal illisible, aucune exception —
    le defaut directeur du depot, par le seul chemin ou la garde est aveugle.

    **Le refus est le repli, et il ne degrade rien.** Un bit qu'on n'a pas pu
    reposer rend des capacites ou `ansi` et `couleur` valent faux : le peintre
    nu est le cas de BASE, pas un mode degrade. Le motif dit pourquoi, et
    `falcon sonde` reste la commande qui l'explique.

    **Appelee a CHAQUE tour du navigateur, et c'est voulu.** Windows n'a pas
    de `SIGWINCH` : la geometrie se remesure a chaque tour. Le mode VT, lui,
    peut avoir ete remis a zero entre deux tours — une reconnexion RDP ouvre
    un autre handle de console. Mesurer la largeur a chaque tour et le mode
    une seule fois laisserait la seconde moitie d'une session peindre sur un
    handle qui n'interprete plus rien.
    """
    from dataclasses import replace

    from falcon.toile import reposer_le_bit, sonder, systeme_reel

    systeme = systeme_reel(flux, nom)
    capacites = sonder(systeme)
    if not capacites.ansi:
        return capacites
    if reposer_le_bit(systeme):
        return capacites
    return replace(
        capacites, ansi=False, couleur=False,
        motifs=capacites.motifs + (
            "le bit VT n'a pas pu etre repose avant de peindre : ce terminal "
            "SAIT interpreter les sequences, mais son handle ne les "
            "interprete pas maintenant",))


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
    from falcon.toile.capacites import reposer_le_bit, sonder, systeme_reel
    from falcon.toile.direct import Diffuseur
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

    # Le direct sort sur l'ERREUR standard, et le compte rendu sur la sortie
    # standard. Les deux flux sont separes a dessein : `falcon explorer ... >
    # rapport.txt` doit rendre un rapport propre, et le direct reste a
    # l'ecran. C'est aussi pour cela que la sonde mesure `stderr` et pas
    # `stdout` — sur Windows le bit VT est un mode par HANDLE, et une capacite
    # mesuree sur un flux puis affirmee sur l'autre deverserait de l'ANSI dans
    # le journal de qui tape `2> journal.log`.
    diffuseur = None
    if not options.muet:
        systeme = systeme_reel(sys.stderr, "stderr")
        # La sonde RESTAURE le mode qu'elle a trouve : elle mesure, elle ne
        # regle pas. Reposer le bit VT avant de peindre est le geste du
        # peintre, et `capacites.py` le dit. Sans lui, sur un conhost de
        # Windows 10 — la cible — VT est eteint par defaut et chaque ligne du
        # direct sortirait en `<-[1m` : des capacites vraies, un handle dont
        # l'etat a change apres la mesure, et une garde n°9 qui ne mord pas
        # parce qu'elle ne regarde que les capacites. Un bit qu'on n'a pas pu
        # reposer se paie en texte nu, qui est le cas de BASE.
        diffuseur = Diffuseur(
            sys.stderr, sonder(systeme),
            forcer_nu=options.sans_couleur or not reposer_le_bit(systeme))
    try:
        _, exploration, compte_rendu = cartographier(
            chemin, options.catalogue,
            plafond_gestes=options.plafond_gestes,
            plafond_ecrans=options.plafond_ecrans,
            esquisses=options.esquisses,
            registre=Registre.avec_surcouches(*options.registre),
            driver=driver, observateur=diffuseur)
    finally:
        # Dans un `finally` : une exploration qui leve a DEJA agi dans SAP, et
        # elle doit rendre le terminal propre — le bandeau collant est une
        # ligne sans saut de ligne, et la laisser en place collerait la trace
        # de pile a sa suite.
        if diffuseur is not None:
            try:
                diffuseur.clore()
            except OSError:
                # Le flux du direct est parti — `| more` puis `q`, la croix de
                # la fenetre, une liaison RDP qui lache. `_Parcours.emettre`
                # l'a deja compte et `rapport.rendre` le dit. Ce `finally`
                # s'execute AVANT l'impression du compte rendu : laisser la
                # levee passer emporterait le seul endroit ou vivent la
                # partition, les branches, les reprises et les visites non
                # atteintes — sur une exploration qui a DEJA agi dans SAP — et
                # `main` convertirait la `BrokenPipeError` en code 0. Un
                # succes annonce sur un travail dont personne n'a le compte
                # rendu. Perdre le compte rendu pour un bandeau qu'on n'arrive
                # plus a effacer serait le pire echange possible.
                pass

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
