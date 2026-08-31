"""Chargement des cartes de controles SAP GUI.

Les identifiants de controles changent avec le systeme, le mandant et la
release. Ils sont donc des DONNEES, pas du code : ce module les lit depuis
`cartes/sap_map.yaml` et les rend disponibles aux adaptateurs d'ecran.

    carte = charger_carte()
    carte["operations_synthese"]["boutons"]["marquer_tout"]
"""

from __future__ import annotations

from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_CARTE_DEFAUT = RACINE / "cartes" / "sap_map.yaml"


def charger_carte(chemin: str | Path | None = None) -> dict:
    """Lit une carte YAML et retourne son contenu tel quel.

    Aucune valeur par defaut n'est injectee : une cle absente doit echouer
    bruyamment chez l'appelant plutot que d'etre devinee ici.
    """
    chemin = Path(chemin) if chemin is not None else CHEMIN_CARTE_DEFAUT
    with open(chemin, encoding="utf-8") as f:
        contenu = yaml.safe_load(f)
    if not isinstance(contenu, dict):
        raise ValueError(f"{chemin} ne contient pas une carte (dict attendu)")
    return contenu
