"""Lecture d'un jeu de donnees, et regroupement par unite de sauvegarde.

Deux exigences se rejoignent ici, et elles expliquent tout le module.

**Le fichier de KO doit etre reinjectable tel quel.** On conserve donc, en
plus des valeurs, le *dialecte* du fichier lu : encodage, BOM, delimiteur,
guillemet, fin de ligne, et surtout l'ORDRE des colonnes. Reexporter en
devinant ces choix produirait un fichier que l'utilisateur devrait retoucher
avant de le relancer — ce qui annulerait le benefice de l'automatisation sur
les cas difficiles, qui sont precisement ceux qui coutent.

**L'item est l'unite de sauvegarde SAP, pas l'unite de constat.** Trois cents
caracteristiques fautives reparties sur quarante classes font quarante items,
pas trois cents : une transaction traite toutes les caracteristiques d'une
classe dans un meme ecran et une seule validation. Regrouper avant d'executer
divise le volume et fait coincider la granularite de reprise avec la frontiere
transactionnelle reelle — une sauvegarde passe ou echoue en entier.

Ce regroupement est un parametre de lecture, pas une gymnastique dans la
boucle : on declare les colonnes de clef, et la lecture rend des items.
"""

from __future__ import annotations

import codecs
import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

#: Les colonnes de diagnostic ajoutees au fichier de KO portent ce prefixe, et
#: la lecture les retire. C'est ce qui permet au fichier d'etre a la fois
#: enrichi pour l'humain ET reinjectable sans retouche.
PREFIXE_DIAGNOSTIC = "falcon_"

SEPARATEUR_CLEF = "\x1f"        # separateur d'unites ASCII : jamais dans une valeur


class JeuInvalide(Exception):
    """Le jeu de donnees ne peut pas etre lu, ou ne porte pas les clefs."""


@dataclass(frozen=True)
class Dialecte:
    """De quoi reecrire un fichier exactement comme on l'a lu."""

    encodage: str = "utf-8"
    bom: bool = False
    delimiteur: str = ","
    guillemet: str = '"'
    fin_de_ligne: str = "\n"
    colonnes: tuple[str, ...] = ()
    format: str = "csv"          # csv | jsonl


@dataclass(frozen=True)
class Item:
    """Une unite de sauvegarde : une ou plusieurs lignes source."""

    item_id: str
    cle: dict[str, str] = field(default_factory=dict)
    brut: tuple[dict[str, Any], ...] = ()
    index: int = 0


def identifiant(cle: Sequence[str]) -> str:
    """Empreinte des valeurs de clef.

    L'identifiant ne peut pas etre le rang de la ligne : un fichier de KO
    reinjecte n'a plus les memes rangs, et la reprise doit rester juste
    malgre ca.
    """
    condense = hashlib.sha256(SEPARATEUR_CLEF.join(cle).encode("utf-8"))
    return condense.hexdigest()[:16]


# =====================================================================
# Lecture
# =====================================================================

def lire(chemin: str | Path) -> tuple[list[dict[str, Any]], Dialecte]:
    """Rend les lignes et le dialecte du fichier.

    Les colonnes de diagnostic sont retirees : un fichier de KO se relit donc
    comme le fichier d'origine, sans retouche.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise JeuInvalide(f"jeu introuvable : {chemin}")

    if chemin.suffix.lower() in {".jsonl", ".ndjson"}:
        return _lire_jsonl(chemin)
    return _lire_csv(chemin)


def _decoder(brut: bytes) -> tuple[str, str, bool]:
    bom = brut.startswith(codecs.BOM_UTF8)
    encodage = "utf-8-sig" if bom else "utf-8"
    try:
        return brut.decode(encodage), encodage, bom
    except UnicodeDecodeError:
        pass

    # Un export SAP passe par un poste Windows : cp1252 est le repli naturel.
    # Il PEUT echouer — les octets 0x81, 0x8D, 0x8F, 0x90 et 0x9D n'y sont pas
    # definis — d'ou le dernier repli sur latin-1, qui accepte tout octet.
    for encodage in ("cp1252", "latin-1"):
        try:
            return brut.decode(encodage), encodage, False
        except UnicodeDecodeError:
            continue
    raise JeuInvalide("encodage non reconnu")


#: Cle sous laquelle csv.DictReader range les cellules surnumeraires.
_SURPLUS = "\x00surplus"


def _verifier_entete(chemin: Path, colonnes: tuple[str, ...]) -> None:
    """Refuse un en-tete qui ferait perdre des donnees en silence.

    Une colonne dupliquee est le cas le plus vicieux : `DictReader` garde la
    DERNIERE valeur, donc la premiere colonne homonyme est definitivement
    perdue et remplacee par la seconde — dans les deux positions au reexport.
    Sur un export SE16N avec deux colonnes de meme nom, c'est une reinjection
    de valeurs fausses, sans une exception.
    """
    if not colonnes:
        raise JeuInvalide(f"{chemin} : aucun en-tete")

    vides = [rang for rang, nom in enumerate(colonnes, start=1) if not nom.strip()]
    if vides:
        raise JeuInvalide(f"{chemin} : colonne(s) sans nom en position {vides}")

    doublons = sorted({nom for nom in colonnes if colonnes.count(nom) > 1})
    if doublons:
        raise JeuInvalide(
            f"{chemin} : colonne(s) en double {doublons}. La valeur de la "
            f"premiere serait perdue au profit de la seconde, sans erreur")


def _verifier_ligne(chemin: Path, rang: int, ligne: dict[str, Any],
                    colonnes: tuple[str, ...]) -> None:
    if _SURPLUS in ligne:
        raise JeuInvalide(
            f"{chemin}, ligne {rang} : {len(colonnes) + len(ligne[_SURPLUS])} "
            f"cellules pour {len(colonnes)} colonnes. Le surplus serait jete")

    manquantes = [nom for nom, valeur in ligne.items() if valeur is None]
    if manquantes:
        raise JeuInvalide(
            f"{chemin}, ligne {rang} : colonne(s) absente(s) {manquantes}")


def _lire_csv(chemin: Path) -> tuple[list[dict[str, Any]], Dialecte]:
    texte, encodage, bom = _decoder(chemin.read_bytes())
    fin_de_ligne = "\r\n" if "\r\n" in texte else "\n"

    try:
        renifle = csv.Sniffer().sniff(texte[:4096], delimiters=",;\t|")
        delimiteur, guillemet = renifle.delimiter, renifle.quotechar
    except csv.Error:
        delimiteur, guillemet = ",", '"'

    lecteur = csv.DictReader(io.StringIO(texte), delimiter=delimiteur,
                             quotechar=guillemet, restkey=_SURPLUS)
    colonnes = tuple(lecteur.fieldnames or ())
    _verifier_entete(chemin, colonnes)

    lignes = []
    for rang, ligne in enumerate(lecteur, start=2):     # 1 = l'en-tete
        _verifier_ligne(chemin, rang, ligne, colonnes)
        lignes.append(dict(ligne))

    retenues = tuple(c for c in colonnes if not c.startswith(PREFIXE_DIAGNOSTIC))
    lignes = [{c: (ligne.get(c) or "") for c in retenues} for ligne in lignes]

    return lignes, Dialecte(encodage=encodage, bom=bom, delimiteur=delimiteur,
                            guillemet=guillemet, fin_de_ligne=fin_de_ligne,
                            colonnes=retenues, format="csv")


def _paires_sans_doublon(chemin: Path, rang: int):
    """`object_pairs_hook` : refuse une clef ecrite deux fois dans un objet.

    `json.loads` garde la DERNIERE, exactement comme PyYAML et comme
    `csv.DictReader` sur deux colonnes homonymes — les deux cas que ce module
    et `yaml_strict` refusent deja. Le troisieme membre de la famille passait.
    """
    def hook(paires):
        vues: set[str] = set()
        for cle, _ in paires:
            if cle in vues:
                raise JeuInvalide(
                    f"{chemin}, ligne {rang} : clef {cle!r} ecrite deux fois. "
                    f"JSON garde la DERNIERE, et la premiere valeur serait "
                    f"perdue sans une erreur")
            vues.add(cle)
        return dict(paires)
    return hook


def _texte_de_json(chemin: Path, rang: int, cle: str, valeur: Any) -> str:
    """La valeur doit etre une CHAINE JSON. On ne convertit rien.

    C'est la meme regle que `yaml_strict` applique au fichier de pipeline, et
    elle vaut a plus forte raison ici : le jeu de donnees vient de l'ERP, et
    c'est lui qu'on retape dans l'ERP.

    Le chemin CSV rend toujours du texte — un CSV n'a pas de types. Le chemin
    JSONL, lui, ne convertissait ni ne verifiait rien, et les valeurs
    gardaient leur type JSON jusqu'au `str()` du moteur. Mesure de bout en
    bout, jeu JSONL -> `lire_items` -> saisie :

        "site": null   -> le texte « None » tape dans le champ SAP
        "site": 1.50   -> « 1.5 », le zero de cadrage perdu
        "site": true   -> « True »

    C'est mot pour mot ce que le chargeur de pipeline declare bloquer, et la
    barriere etait posee du cote qu'on ecrit a la main plutot que du cote qui
    vient du systeme.

    Convertir serait pire que refuser : `str(None)` rend une valeur d'aspect
    parfaitement normal. Un refus nomme la ligne et la colonne.
    """
    if isinstance(valeur, str):
        return valeur
    raise JeuInvalide(
        f"{chemin}, ligne {rang}, colonne {cle!r} : la valeur doit etre une "
        f"CHAINE JSON, entre guillemets (recu {valeur!r}). Un nombre perd son "
        f"cadrage — 1.50 se relit « 1.5 » — et `null` deviendrait le texte "
        f"« None », tape tel quel dans SAP")


def _lire_jsonl(chemin: Path) -> tuple[list[dict[str, Any]], Dialecte]:
    texte, encodage, bom = _decoder(chemin.read_bytes())
    fin_de_ligne = "\r\n" if "\r\n" in texte else "\n"

    lignes = []
    for rang, brute in enumerate(texte.splitlines(), start=1):
        if not brute.strip():
            continue
        try:
            lue = json.loads(brute,
                             object_pairs_hook=_paires_sans_doublon(chemin, rang))
        except json.JSONDecodeError as erreur:
            raise JeuInvalide(f"{chemin}, ligne {rang} : {erreur}") from None
        if not isinstance(lue, dict):
            raise JeuInvalide(
                f"{chemin}, ligne {rang} : chaque ligne doit etre un OBJET "
                f"JSON — « {{\"site\": \"K75\"}} » — pas {type(lue).__name__}")
        lignes.append((rang, lue))

    vues: dict[str, None] = {}
    for _, ligne in lignes:
        for cle in ligne:
            if not cle.startswith(PREFIXE_DIAGNOSTIC):
                vues.setdefault(cle, None)
    colonnes = tuple(vues)

    # Une clef ABSENTE n'est PAS comblee par une chaine vide, et ce n'est pas
    # un oubli : en JSONL l'absence porte du sens. « ne touche pas a ce
    # champ » et « vide ce champ » ne sont pas les memes instructions pour une
    # injection SAP, et le fichier de KO doit pouvoir refaire l'aller-retour
    # sans que la seconde soit fabriquee a partir de la premiere.
    #
    # Le CSV n'a pas ce choix — une cellule manquante y est une ligne courte,
    # donc un fichier malforme — d'ou le refus de `_verifier_ligne`. Ce n'est
    # pas un precedent applicable ici.
    #
    # Le trou que l'absence ouvrait vraiment est ailleurs : le pre-vol du
    # moteur compare aux colonnes du DIALECTE, c'est-a-dire a l'union des
    # clefs de toutes les lignes, si bien qu'une ligne incomplete produisait
    # une chaine vide au milieu du lot. Il est bouche la, dans
    # `moteur/boucle.py`, ou l'on sait quelles colonnes la pipeline lit
    # vraiment — ici, on ne le sait pas.
    retenues = [{c: _texte_de_json(chemin, rang, c, ligne[c])
                 for c in colonnes if c in ligne}
                for rang, ligne in lignes]

    return retenues, Dialecte(encodage=encodage, bom=bom,
                              fin_de_ligne=fin_de_ligne, colonnes=colonnes,
                              format="jsonl")


# =====================================================================
# Regroupement
# =====================================================================

def grouper(lignes: Sequence[dict[str, Any]],
            cles: Sequence[str]) -> list[Item]:
    """Regroupe les lignes par unite de sauvegarde.

    Les lignes d'un meme item restent dans leur ordre d'apparition, et l'ordre
    des items suit celui de leur premiere ligne : rejouer un fichier doit
    donner la meme sequence.
    """
    if not cles:
        raise JeuInvalide(
            "aucune colonne de clef declaree. Une pipeline iterative doit "
            "declarer `cles`, sinon la reprise devient sensible a l'ordre du "
            "fichier et le fichier de KO reinjecte ne se raccroche a rien")

    groupes: dict[str, list[dict[str, Any]]] = {}
    valeurs: dict[str, dict[str, str]] = {}
    ordre: list[str] = []

    for ligne in lignes:
        manquantes = [c for c in cles if c not in ligne]
        if manquantes:
            raise JeuInvalide(
                f"colonne(s) de clef absente(s) du jeu : {manquantes}")
        cle = {c: str(ligne[c]) for c in cles}
        item_id = identifiant([cle[c] for c in cles])
        if item_id not in groupes:
            groupes[item_id] = []
            valeurs[item_id] = cle
            ordre.append(item_id)
        groupes[item_id].append(ligne)

    return [Item(item_id=item_id, cle=valeurs[item_id],
                 brut=tuple(groupes[item_id]), index=rang)
            for rang, item_id in enumerate(ordre)]


def lire_items(chemin: str | Path,
               cles: Sequence[str]) -> tuple[list[Item], Dialecte]:
    """Lecture et regroupement en une passe."""
    lignes, dialecte = lire(chemin)
    return grouper(lignes, cles), dialecte


def empreinte_jeu(chemin: str | Path) -> str:
    """Empreinte du jeu, pour la garde de reprise.

    Elle porte sur le TEXTE DECODE, fins de ligne normalisees — pas sur les
    octets. Les deux empreintes que la reprise compare doivent poser la meme
    question : « FALCON lirait-il la meme chose ? »

    Elles n'y repondaient pas de la meme facon. Celle de la pipeline passe par
    `read_text`, donc par les fins de ligne universelles ; celle-ci hachait
    les octets bruts. Mesure sur un contenu IDENTIQUE :

        pipeline LF / CRLF  ->  92f0df95545a5d28  92f0df95545a5d28   identiques
        jeu      LF / CRLF  ->  38c51400c26fa990  aff7a5dc7040adef   differents

    Conséquence : ouvrir le jeu dans un editeur Windows et l'enregistrer — le
    geste le plus banal du poste vise — suffisait a interdire la reprise d'un
    lot interrompu, sur une donnee inchangee. Et le contournement decrit par
    la docstring de `preparer` n'etait atteignable depuis aucune commande.

    Le decodage est CELUI DE LA LECTURE : deux fichiers qui donnent les memes
    valeurs a `lire` donnent la meme empreinte, et c'est exactement ce que la
    garde veut savoir. Toute difference de contenu reelle la change toujours.
    """
    texte, _, _ = _decoder(Path(chemin).read_bytes())
    normalise = texte.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalise.encode("utf-8")).hexdigest()[:16]
