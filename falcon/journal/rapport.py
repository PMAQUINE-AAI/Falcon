"""Rapport de fin d'execution, replie depuis le journal.

Le rapport ne recalcule rien et n'observe rien : il replie le journal. C'est
ce qui garantit qu'il dit la meme chose que la reprise — deux sources de
verite sur un meme lot finiraient par diverger, et on ne saurait plus
laquelle croire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .enregistrement import (
    DOUTEUX, Enregistrement, ExecutionDebut, ExecutionFin, Garde, ItemFin,
)
from .lecteur import etats


@dataclass(frozen=True)
class Rapport:
    pipeline: str = ""
    systeme: str = ""
    mandant: str = ""
    mode: str = ""
    compteurs: dict[str, int] = field(default_factory=dict)
    duree_ms: int = 0
    items_par_etat: dict[str, list[str]] = field(default_factory=dict)
    incidents: dict[str, int] = field(default_factory=dict)
    derogations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def douteux(self) -> list[str]:
        return self.items_par_etat.get(DOUTEUX, [])


def depuis_journal(enregistrements: Iterable[Enregistrement]) -> Rapport:
    enregistrements = list(enregistrements)

    ouverture = next((e for e in enregistrements
                      if isinstance(e, ExecutionDebut)), None)
    cloture = next((e for e in reversed(enregistrements)
                    if isinstance(e, ExecutionFin)), None)

    par_etat: dict[str, list[str]] = {}
    for item_id, etat in sorted((i, e.etat) for i, e in etats(enregistrements).items()):
        par_etat.setdefault(etat, []).append(item_id)

    incidents: dict[str, int] = {}
    for fin in (e for e in enregistrements if isinstance(e, ItemFin)):
        if fin.incident:
            incidents[fin.incident] = incidents.get(fin.incident, 0) + 1

    # Les derogations sont repetees a chaque execution, deliberement : une
    # garde assouplie doit rester visible, pas s'oublier dans un fichier de
    # configuration lu une fois.
    derogations = [
        {"garde": e.garde, **(e.derogation or {})}
        for e in enregistrements
        if isinstance(e, Garde) and e.verdict == "derogee"
    ]

    return Rapport(
        pipeline=ouverture.pipeline if ouverture else "",
        systeme=ouverture.systeme if ouverture else "",
        mandant=ouverture.mandant if ouverture else "",
        mode=ouverture.mode if ouverture else "",
        compteurs={etat: len(items) for etat, items in sorted(par_etat.items())},
        duree_ms=cloture.duree_ms if cloture else 0,
        items_par_etat=par_etat,
        incidents=incidents,
        derogations=derogations,
    )


def rendre(rapport: Rapport) -> str:
    """Rapport lisible en terminal ou dans un fichier."""
    lignes = [
        f"Pipeline   : {rapport.pipeline}",
        f"Cible      : {rapport.systeme}/{rapport.mandant}  (mode {rapport.mode})",
        f"Duree      : {rapport.duree_ms / 1000:.1f} s",
        "",
        "Items      : " + (", ".join(f"{etat} {nombre}"
                                     for etat, nombre in rapport.compteurs.items())
                           or "aucun"),
    ]

    if rapport.douteux:
        lignes += [
            "",
            f"DOUTEUX ({len(rapport.douteux)}) — interrompus apres sauvegarde,",
            "a arbitrer a la main : les rejouer serait une double ecriture.",
        ]

    if rapport.incidents:
        lignes += ["", "Incidents :"]
        lignes += [f"  {nombre:4d}  {nom}"
                   for nom, nombre in sorted(rapport.incidents.items(),
                                             key=lambda p: -p[1])]

    if rapport.derogations:
        lignes += ["", "Derogations appliquees :"]
        lignes += [f"  garde {d.get('garde')} — {d.get('motif', '')}"
                   for d in rapport.derogations]

    return "\n".join(lignes)
