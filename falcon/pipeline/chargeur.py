"""YAML vers `Pipeline`, strictement.

Le critere de ce lot tient en une phrase : **un YAML invalide echoue avec un
message situe, jamais en silence.** Chaque refus nomme le fichier, et le rang
et le nom de l'etape fautive — parce qu'un message d'erreur qu'il faut aller
chercher dans un fichier de trois cents lignes coute autant qu'une absence de
message.

Le chargeur est strict par principe, pas par gout : une cle inconnue est le
plus souvent une faute de frappe sur une cle connue, et l'ignorer transforme
une etape qui devait declarer `sauvegarde: true` en etape qui ne sauvegarde
pas, sans un mot.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from falcon.noyau.yaml_strict import (
    YamlAmbigu, booleen, liste_de_texte, texte,
)
from falcon.noyau.yaml_strict import lire as lire_yaml

from falcon.noyau import COMPARAISONS, DEROGEABLES, MOTIF_MINIMAL, PORTEE_TOTALE

from . import extension
from .composition import (
    CompositionInvalide, lire_transformation, verifier_gabarit,
)
from .modele import (
    ACTIONS, AVEC_CIBLE, AVEC_SOURCE, CLASSES, GENRES_SOURCE, SOURCE_CONSTANTE,
    DerogationDeclaree, Etape, Pipeline, Source,
)

#: Marqueur laisse par le generateur de brouillon. Une pipeline qui en porte
#: encore n'est pas finie, et ne doit pas atteindre une session SAP par
#: inadvertance.
MARQUEUR_BROUILLON = "TODO"

CLES_PIPELINE = frozenset({
    "version", "nom", "classe", "cles", "plafond_items",
    "plafond_sauvegardes", "validation_reelle", "etapes",
})

CLES_ETAPE = frozenset({
    "nom", "action", "cible", "source", "fonction", "ecran",
    "navigation_libre", "fenetres", "statut_attendu", "sauvegarde",
    "comparaison", "derogations", "format", "defaut",
})

VERSION = 1


class PipelineInvalide(Exception):
    """Le YAML ne decrit pas une pipeline exploitable."""


def _refus(source: str, message: str, etape: int | None = None,
           nom: str = "") -> PipelineInvalide:
    """Construit un refus situe."""
    ou = f"{source}"
    if etape is not None:
        ou += f", etape {etape}" + (f" « {nom} »" if nom else "")
    return PipelineInvalide(f"{ou} : {message}")


def charger(chemin: str | Path, *, brouillon: bool = False) -> Pipeline:
    """Lit un YAML de pipeline et le valide entierement avant de rendre.

    `brouillon` autorise les marqueurs laisses par le generateur d'ebauche.
    Sans lui, une pipeline inachevee est refusee : le brouillon est une aide a
    la redaction, pas un livrable.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise PipelineInvalide(f"pipeline introuvable : {chemin}")

    brut = chemin.read_text(encoding="utf-8")
    source = str(chemin)

    if not brouillon and MARQUEUR_BROUILLON in brut:
        raise _refus(source,
                     f"porte encore des marqueurs {MARQUEUR_BROUILLON!r}. "
                     f"C'est un brouillon : le completer, ou le charger "
                     f"explicitement comme brouillon")

    try:
        contenu = lire_yaml(brut, source)
    except YamlAmbigu as erreur:
        raise PipelineInvalide(str(erreur)) from None
    except yaml.YAMLError as erreur:
        raise _refus(source, f"YAML illisible ({erreur})") from erreur

    if not isinstance(contenu, dict):
        raise _refus(source, "un dictionnaire est attendu a la racine")

    inconnues = sorted(set(contenu) - CLES_PIPELINE)
    if inconnues:
        raise _refus(source, f"cle(s) inconnue(s) {inconnues}. "
                             f"Connues : {sorted(CLES_PIPELINE)}")

    if contenu.get("version") != VERSION:
        raise _refus(source, f"version {contenu.get('version')!r}, "
                             f"attendu {VERSION}")

    nom = contenu.get("nom")
    if not nom:
        raise _refus(source, "pipeline sans nom")

    classe = contenu.get("classe")
    if classe not in CLASSES:
        raise _refus(source, f"classe {classe!r}, attendu {sorted(CLASSES)}")

    # `tuple("site")` rend ('s','i','t','e') : quatre colonnes de clef nommees
    # s, i, t et e. L'erreur ressortait bien plus loin, au moment de lire le
    # jeu — et accusait le fichier de donnees plutot que la pipeline.
    try:
        cles = liste_de_texte(contenu.get("cles"), "cles", source=source,
                              defaut=())
    except YamlAmbigu as erreur:
        raise PipelineInvalide(str(erreur)) from None
    if classe == "iterative" and not cles:
        raise _refus(source,
                     "une pipeline iterative doit declarer `cles`. Sans "
                     "colonnes de clef, l'identifiant d'item retomberait sur "
                     "le rang de la ligne — et un fichier de KO reinjecte n'a "
                     "plus les memes rangs")

    plafonds = {}
    for cle in ("plafond_items", "plafond_sauvegardes"):
        valeur = contenu.get(cle)
        if not isinstance(valeur, int) or isinstance(valeur, bool) or valeur < 1:
            raise _refus(source, f"`{cle}` doit etre un entier positif "
                                 f"(recu {valeur!r}). Le rayon d'action est "
                                 f"obligatoire, pas optionnel")
        plafonds[cle] = valeur

    brutes = contenu.get("etapes")
    if not isinstance(brutes, list) or not brutes:
        raise _refus(source, "`etapes` doit etre une liste non vide")

    etapes: list[Etape] = []
    vus: set[str] = set()
    lues: set[str] = set()          # noms des etapes `lire` deja rencontrees
    for rang, brute in enumerate(brutes, start=1):
        etape = _etape(brute, source, rang, brouillon=brouillon)
        if etape.nom in vus:
            raise _refus(source, f"nom d'etape en double : {etape.nom!r}. "
                                 f"Les derogations se designent par ce nom",
                         rang, etape.nom)
        # Une source « lue » designe une etape `lire` ANTERIEURE. La verifier
        # ici, dans l'ordre, refuse du meme coup la reference pendante et la
        # reference a une etape qui n'a pas encore lu. Sans ce controle, la
        # valeur serait vide a l'execution et la saisie passerait sans un mot.
        if etape.source is not None and etape.source.genre == "lue":
            if etape.source.valeur not in lues:
                raise _refus(
                    source,
                    f"source « lue: {etape.source.valeur} » : aucune etape "
                    f"`lire` de ce nom ne precede. Connues a ce rang : "
                    f"{sorted(lues) or 'aucune'}", rang, etape.nom)
        if etape.action == "lire":
            lues.add(etape.nom)
        vus.add(etape.nom)
        etapes.append(etape)

    return Pipeline(
        nom=nom, classe=classe, etapes=tuple(etapes), cles=cles,
        plafond_items=plafonds["plafond_items"],
        plafond_sauvegardes=plafonds["plafond_sauvegardes"],
        validation_reelle=contenu.get("validation_reelle"),
        empreinte=hashlib.sha256(brut.encode("utf-8")).hexdigest()[:16],
        source=source,
    )


def _etape(brute: Any, source: str, rang: int, *, brouillon: bool = False
           ) -> Etape:
    if not isinstance(brute, dict):
        raise _refus(source, "une etape doit etre un dictionnaire", rang)

    nom = brute.get("nom") or ""
    inconnues = sorted(set(brute) - CLES_ETAPE)
    if inconnues:
        raise _refus(source, f"cle(s) inconnue(s) {inconnues}", rang, nom)
    if not nom:
        raise _refus(source, "etape sans nom", rang)

    action = brute.get("action")
    if action not in ACTIONS:
        raise _refus(source, f"action {action!r}, attendu {sorted(ACTIONS)}",
                     rang, nom)

    cible = brute.get("cible") or ""
    if action in AVEC_CIBLE and not cible:
        raise _refus(source, f"l'action {action!r} exige une `cible`", rang, nom)

    fonction = brute.get("fonction") or ""
    if action == "python":
        if not fonction:
            raise _refus(source, "l'action « python » exige une `fonction`",
                         rang, nom)
        # Un brouillon est inacheve par definition : le generateur y pose
        # `fonction: TODO` la ou la trace contient un geste qu'aucune action
        # ne sait exprimer. Un fichier livre, lui, n'a pas ce droit — et
        # `charger()` sans `brouillon` refuse le fichier entier bien avant
        # d'arriver ici, sur le seul marqueur.
        toleree = brouillon and fonction == MARQUEUR_BROUILLON
        if not toleree and fonction not in extension.connues():
            raise _refus(source,
                         f"fonction {fonction!r} non enregistree. Connues : "
                         f"{sorted(extension.connues()) or 'aucune'}", rang, nom)

    source_valeur = _source(brute.get("source"), source, rang, nom)
    if action in AVEC_SOURCE and source_valeur is None:
        raise _refus(source, f"l'action {action!r} exige une `source`", rang, nom)

    if action in SOURCE_CONSTANTE and source_valeur is not None:
        if source_valeur.genre != "constante":
            raise _refus(source,
                         f"l'action {action!r} exige une source « constante » "
                         f"(recu {source_valeur.genre!r}). Une touche de "
                         f"fonction est une propriete de la pipeline, pas de "
                         f"l'item : la faire varier d'une ligne a l'autre "
                         f"rendrait le geste imprevisible", rang, nom)

    if action == "vkey" and source_valeur is not None:
        # Refuse ici, pas au moment ou le moteur enverrait une touche fantome.
        try:
            int(source_valeur.valeur)
        except ValueError:
            raise _refus(source,
                         f"touche de fonction {source_valeur.valeur!r} : un "
                         f"entier est attendu", rang, nom) from None

    ecran = _ecran(brute.get("ecran"), source, rang, nom)
    libre = bool(brute.get("navigation_libre", False))
    if ecran is None and not libre:
        raise _refus(source,
                     "declarer `ecran`, ou `navigation_libre: true` si "
                     "l'etape ne sait pas encore ou elle atterrit. Une etape "
                     "muette neutraliserait la garde d'identite sans que "
                     "personne ne le voie", rang, nom)
    if ecran is not None and libre:
        raise _refus(source, "`ecran` et `navigation_libre` ensemble n'ont pas "
                             "de sens", rang, nom)

    comparaison = brute.get("comparaison") or "casse"
    if comparaison not in COMPARAISONS:
        raise _refus(source, f"comparaison {comparaison!r}, attendu "
                             f"{sorted(COMPARAISONS)}", rang, nom)

    try:
        # Meme piege que `cles` : « wnd[0] » en scalaire donnait six fenetres
        # attendues nommees w, n, d, [, 0 et ]. La fenetre principale n'etait
        # alors plus attendue, et la garde 3 la traitait en intruse.
        fenetres = liste_de_texte(brute.get("fenetres"), "fenetres",
                                  source=source, defaut=("wnd[0]",))
        # Declarer la cle et ne rien mettre derriere donnait None, c'est-a-dire
        # exactement le meme resultat que ne pas la declarer : la garde 2
        # n'etait pas posee. C'est le relachement par omission que le §5
        # refuse partout ailleurs.
        statut = brute.get("statut_attendu")
        if "statut_attendu" in brute:
            statut = texte(statut, "statut_attendu", source=source)
        sauvegarde = booleen(brute.get("sauvegarde"), "sauvegarde",
                             source=source, defaut=False)
        repli = brute.get("defaut")
        if "defaut" in brute:
            repli = texte(repli, "defaut", source=source)
        libre_verifie = booleen(brute.get("navigation_libre"),
                                "navigation_libre", source=source, defaut=False)
    except YamlAmbigu as erreur:
        raise _refus(source, str(erreur).split(" : ", 1)[-1], rang, nom) from None

    brutes_format = brute.get("format") or []
    if not isinstance(brutes_format, list):
        raise _refus(source, "`format` doit etre une LISTE de transformations, "
                             "appliquees dans l'ordre declare", rang, nom)
    try:
        formats = tuple(lire_transformation(b) for b in brutes_format)
    except CompositionInvalide as erreur:
        raise _refus(source, str(erreur), rang, nom) from None
    if formats and source_valeur is None:
        raise _refus(source, "`format` sans `source` : il n'y a rien a "
                             "transformer", rang, nom)
    if repli is not None and source_valeur is None:
        raise _refus(source, "`defaut` sans `source` : il n'y a rien a "
                             "remplacer", rang, nom)

    return Etape(
        nom=nom, action=action, cible=cible, source=source_valeur,
        format=formats, defaut=repli,
        fonction=fonction, ecran=ecran, navigation_libre=libre_verifie,
        fenetres=fenetres,
        statut_attendu=statut,
        sauvegarde=sauvegarde,
        comparaison=comparaison,
        derogations=_derogations(brute.get("derogations"), source, rang, nom),
    )


def _source(brute: Any, source: str, rang: int, nom: str) -> Source | None:
    if brute is None:
        return None
    if not isinstance(brute, dict) or len(brute) != 1:
        raise _refus(source, f"`source` doit porter exactement un genre parmi "
                             f"{sorted(GENRES_SOURCE)}", rang, nom)
    genre, valeur = next(iter(brute.items()))
    if genre not in GENRES_SOURCE:
        raise _refus(source, f"genre de source {genre!r}, attendu "
                             f"{sorted(GENRES_SOURCE)}", rang, nom)

    # Une source doit etre ECRITE comme une chaine. Meme raison que pour
    # `ecran.dynpro` (decision n°20), mais la consequence est pire : ce n'est
    # pas une comparaison qui devient fausse, c'est une valeur qui est TAPEE
    # DANS SAP.
    #
    # YAML n'est pas du texte. `0100` est de l'octal et vaut 64. `007` vaut 7,
    # et les codes SAP sont remplis de zeros. `12:30` est du sexagesimal et
    # vaut 750. `1.50` est un flottant et se reecrit « 1.5 ». `on` est un
    # booleen et se reecrit « True ». `2026-09-07` est une date, et son
    # str() depend de la bibliotheque.
    #
    # Cinq de ces six formes s'ecrivaient dans un champ SAP sans que rien ne
    # leve. Refuser ici coute deux guillemets ; deviner coute une correction
    # de masse fausse.
    if not isinstance(valeur, str):
        raise _refus(source,
                     f"`source.{genre}` doit etre une CHAINE, entre "
                     f"guillemets (recu {valeur!r}). Sans eux, YAML lit "
                     f"« 0100 » comme de l'octal et en fait 64, « 007 » "
                     f"comme 7, « 12:30 » comme 750, « on » comme True — et "
                     f"c'est cela qui serait tape dans SAP", rang, nom)
    colonnes: tuple[str, ...] = ()
    if genre == "gabarit":
        # Valide MAINTENANT : une accolade non appariee finirait tapee telle
        # quelle dans le champ SAP, et les colonnes citees doivent entrer dans
        # le controle de pre-vol du moteur.
        try:
            colonnes = verifier_gabarit(valeur)
        except CompositionInvalide as erreur:
            raise _refus(source, str(erreur), rang, nom) from None
    return Source(genre=genre, valeur=valeur, colonnes=colonnes)


def _ecran(brute: Any, source: str, rang: int, nom: str
           ) -> tuple[str, str, str] | None:
    if brute is None:
        return None
    if not isinstance(brute, dict):
        raise _refus(source, "`ecran` doit porter transaction, programme et "
                             "dynpro", rang, nom)
    manquantes = [c for c in ("transaction", "programme", "dynpro")
                  if not brute.get(c)]
    if manquantes:
        raise _refus(source, f"`ecran` incomplet, manque {manquantes}", rang, nom)
    inconnues = sorted(set(brute) - {"transaction", "programme", "dynpro"})
    if inconnues:
        raise _refus(source, f"`ecran` : cle(s) inconnue(s) {inconnues}",
                     rang, nom)
    # Le dynpro reste une chaine : « 0100 » n'est pas « 100 », et le catalogue
    # doit rester diffable. Il doit surtout etre ECRIT comme une chaine :
    # YAML lit `0100` comme de l'octal et en fait 64, ce qui corrompt le
    # dynpro sans que rien ne leve — la garde d'identite comparerait ensuite
    # contre un numero d'ecran qui n'existe pas.
    if not isinstance(brute["dynpro"], str):
        raise _refus(source,
                     f"`ecran.dynpro` doit etre une CHAINE, entre guillemets "
                     f"(recu {brute['dynpro']!r}). Sans eux, YAML lit "
                     f"« 0100 » comme de l'octal et en fait 64", rang, nom)
    return (str(brute["transaction"]), str(brute["programme"]),
            brute["dynpro"])


def _derogations(brute: Any, source: str, rang: int, nom: str
                 ) -> tuple[DerogationDeclaree, ...]:
    if brute is None:
        return ()
    if not isinstance(brute, list):
        raise _refus(source, "`derogations` doit etre une liste", rang, nom)

    demandees: list[DerogationDeclaree] = []
    for brute_derogation in brute:
        if not isinstance(brute_derogation, dict):
            raise _refus(source, "une derogation doit etre un dictionnaire",
                         rang, nom)
        inconnues = sorted(set(brute_derogation) - {"garde", "portee", "motif"})
        if inconnues:
            raise _refus(source, f"derogation : cle(s) inconnue(s) {inconnues}",
                         rang, nom)

        garde = brute_derogation.get("garde")
        if garde not in DEROGEABLES:
            raise _refus(source,
                         f"aucune derogation possible a la garde {garde!r}. "
                         f"Derogeables : {sorted(DEROGEABLES)} — une identite "
                         f"violee signale que le modele du monde est faux, et "
                         f"le plafond est la derniere barriere", rang, nom)

        motif = str(brute_derogation.get("motif") or "")
        if len(motif.strip()) < MOTIF_MINIMAL:
            raise _refus(source,
                         f"derogation a {garde!r} : motif de "
                         f"{len(motif.strip())} caracteres, {MOTIF_MINIMAL} "
                         f"minimum. Une derogation non expliquee est une garde "
                         f"desactivee en douce", rang, nom)

        portee = str(brute_derogation.get("portee") or f"etape:{nom}")
        if portee != PORTEE_TOTALE and not portee.startswith("etape:"):
            raise _refus(source,
                         f"portee {portee!r} : attendu {PORTEE_TOTALE!r} ou "
                         f"« etape:<nom> »", rang, nom)

        demandees.append(DerogationDeclaree(garde=garde, portee=portee,
                                           motif=motif))
    return tuple(demandees)
