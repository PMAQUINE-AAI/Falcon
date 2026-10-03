"""Recette : étapes d'une trace + liaisons de colonnes CSV, sérialisable en YAML."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from falcon.trace import Etape, lire_trace

LIABLES = {"set", "select"}


@dataclass(frozen=True)
class Recette:
    nom: str
    etapes: list[Etape]
    liaisons: dict[int, str] = field(default_factory=dict)  # indice d'étape -> colonne


def depuis_trace(chemin_vbs: str | Path, nom: str) -> Recette:
    return Recette(nom, lire_trace(chemin_vbs), {})


def lier(recette: Recette, indice: int, colonne: str) -> Recette:
    if not 0 <= indice < len(recette.etapes):
        raise ValueError(f"indice {indice} hors bornes (0..{len(recette.etapes) - 1})")
    action = recette.etapes[indice].action
    if action not in LIABLES:
        raise ValueError(f"étape {indice} ({action}) non liable : seules set/select le sont")
    return replace(recette, liaisons={**recette.liaisons, indice: colonne})


def ecrire(recette: Recette, chemin: str | Path) -> None:
    etapes = []
    for i, e in enumerate(recette.etapes):
        item = {"id": e.id, "verbe": e.verbe, "action": e.action, "valeur": e.valeur, "ligne": e.ligne}
        if i in recette.liaisons:
            item["colonne"] = recette.liaisons[i]
        etapes.append(item)
    texte = yaml.safe_dump(
        {"nom": recette.nom, "etapes": etapes},
        allow_unicode=True, sort_keys=False, default_flow_style=False,
    )
    Path(chemin).write_text(texte, encoding="utf-8")


def lire(chemin: str | Path) -> Recette:
    donnees = yaml.safe_load(Path(chemin).read_text(encoding="utf-8"))
    etapes, colonnes = [], {}
    for i, e in enumerate(donnees["etapes"]):
        valeur = e["valeur"]
        etapes.append(Etape(e["id"], e["verbe"], e["action"], None if valeur is None else str(valeur), e["ligne"]))
        if e.get("colonne"):
            colonnes[i] = e["colonne"]
    recette = Recette(donnees["nom"], etapes, {})
    for i, colonne in colonnes.items():
        recette = lier(recette, i, colonne)
    return recette


def appliquer(recette: Recette, ligne: dict[str, str]) -> list[Etape]:
    etapes = list(recette.etapes)
    for i, colonne in recette.liaisons.items():
        if colonne not in ligne:
            raise KeyError(colonne)
        etapes[i] = replace(etapes[i], valeur=ligne[colonne])
    return etapes
