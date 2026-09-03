#!/usr/bin/env python3
"""Lance les deux suites du depot et rend un verdict unique.

FALCON et l'archive ont des racines differentes : l'archive est un paquet
autonome, deplace en bloc, dont les tests se resolvent depuis historique/.
Une seule commande evite d'en oublier une, et evite surtout de croire le
depot vert alors qu'une seule moitie a tourne.

    python outils/verifier.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

SUITES = [
    ("FALCON", ["-m", "unittest", "discover", "-s", "tests", "-t", "."]),
    ("archive", ["-m", "unittest", "discover", "-s", "historique/tests",
                 "-t", "historique"]),
]


def main() -> int:
    echecs = []
    for nom, arguments in SUITES:
        print(f"\n=== {nom} ===", flush=True)
        code = subprocess.run([sys.executable, *arguments], cwd=RACINE).returncode
        if code != 0:
            echecs.append(nom)

    print()
    if echecs:
        print(f"ECHEC : {', '.join(echecs)}")
        return 1
    print("Tout passe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
