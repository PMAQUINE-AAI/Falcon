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


def _lire_jsonl(chemin: Path) -> tuple[list[dict[str, Any]], Dialecte]:
    texte, encodage, bom = _decoder(chemin.read_bytes())
    fin_de_ligne = "\r\n" if "\r\n" in texte else "\n"

    lignes = [json.loads(ligne) for ligne in texte.splitlines() if ligne.strip()]
    vues: dict[str, None] = {}
    for ligne in lignes:
        for cle in ligne:
            if not cle.startswith(PREFIXE_DIAGNOSTIC):
                vues.setdefault(cle, None)
    colonnes = tuple(vues)
    lignes = [{c: v for c, v in ligne.items()
               if not c.startswith(PREFIXE_DIAGNOSTIC)} for ligne in lignes]

    return lignes, Dialecte(encodage=encodage, bom=bom,
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
    """Empreinte du fichier, pour la garde de reprise."""
    return hashlib.sha256(Path(chemin).read_bytes()).hexdigest()[:16]
