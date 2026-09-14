"""Temps injectable.

Le journal horodate chaque enregistrement et mesure des durees. Si le temps
vient directement de `datetime.now()`, les tests du journal deviennent soit
non deterministes, soit truffes de comparaisons approximatives. Une horloge
qu'on passe en argument rend les enregistrements exactement reproductibles.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Iterator

Horloge = Callable[[], str]


def maintenant() -> str:
    """Horodatage ISO 8601 en UTC, a la milliseconde."""
    return (datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"))


def horloge_figee(*instants: str) -> Horloge:
    """Horloge de test : rend les instants donnes, puis repete le dernier.

    Repeter le dernier plutot que lever permet d'ecrire un test qui ne se
    soucie que des premiers horodatages, sans avoir a compter les appels.
    """
    if not instants:
        raise ValueError("au moins un instant est requis")
    restants: Iterator[str] = iter(instants)
    dernier = instants[-1]

    def lire() -> str:
        nonlocal dernier
        try:
            dernier = next(restants)
        except StopIteration:
            pass
        return dernier

    return lire
