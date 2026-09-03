"""Dump d'un incident inconnu.

Quand rien n'apparie, on arrete et on capture. Le dump est ce qui permettra,
plus tard, d'ecrire l'entree de registre correspondante : sans lui, la
taxonomie ne pourrait pas se recolter, et chaque inconnu se reproduirait a
l'identique.

Ce module n'ecrit que ce qu'on lui donne. La collecte de l'etat SAP (identite,
fenetres, champs, statut) appartient au controleur, seul a detenir la couture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from falcon.noyau import Horloge, maintenant


def _horodatage_pour_nom(horodatage: str) -> str:
    """Rend un horodatage utilisable comme nom de fichier."""
    return (horodatage.replace(":", "-").replace(".", "-")
            .replace("+", "-").replace("Z", "Z"))


def ecrire_dump(dossier: str | Path,
                contexte: dict[str, Any],
                *,
                nom: str = "inconnu",
                horloge: Horloge = maintenant) -> Path:
    """Ecrit un dump JSON et rend son chemin.

    Le contenu est serialise en tolerant les objets non JSON (ils passent par
    `str`) : un dump partiel vaut infiniment mieux qu'une exception de
    serialisation pendant qu'on essaie justement de rendre compte d'un
    incident.
    """
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)

    instant = horloge()
    chemin = dossier / f"{_horodatage_pour_nom(instant)}_{nom}.json"

    charge = {"horodatage": instant, "nom": nom, **contexte}
    chemin.write_text(
        json.dumps(charge, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    return chemin
