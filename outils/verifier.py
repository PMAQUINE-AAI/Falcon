#!/usr/bin/env python3
"""Lance les deux suites du depot et rend un verdict unique.

FALCON et l'archive ont des racines differentes : l'archive est un paquet
autonome, deplace en bloc, dont les tests se resolvent depuis historique/.
Une seule commande evite d'en oublier une, et evite surtout de croire le
depot vert alors qu'une seule moitie a tourne.

    python outils/verifier.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

SUITES = [
    ("FALCON", ["-m", "unittest", "discover", "-s", "tests", "-t", "."]),
    ("archive", ["-m", "unittest", "discover", "-s", "historique/tests",
                 "-t", "historique"]),
]


#: `test_x (...) ... skipped 'motif'`, tel que unittest l'ecrit en verbeux.
IGNORE = re.compile(r"^(?P<test>\S+) .*\.\.\. skipped ['\"](?P<motif>.*)['\"]$",
                    re.MULTILINE)


def ignores(arguments: list[str]) -> list[tuple[str, str]]:
    """Les tests ignores et leur motif, par une seconde passe verbeuse.

    Un test qui ne s'execute pas doit le DIRE. `unittest` n'annonce qu'un
    decompte — « OK (skipped=4) » — et un decompte ne dit pas ce qui n'a pas
    ete verifie. Sur un projet dont le module le plus critique n'est testable
    sur aucune machine du depot, laisser cette information au niveau du
    decompte reviendrait a la perdre.
    """
    passe = subprocess.run([sys.executable, *arguments, "-v"], cwd=RACINE,
                           capture_output=True, text=True)
    return [(t.group("test"), t.group("motif"))
            for t in IGNORE.finditer(passe.stderr)]


def main() -> int:
    echecs = []
    ecartes: list[tuple[str, str, str]] = []
    for nom, arguments in SUITES:
        print(f"\n=== {nom} ===", flush=True)
        code = subprocess.run([sys.executable, *arguments], cwd=RACINE).returncode
        if code != 0:
            echecs.append(nom)
        else:
            ecartes += [(nom, test, motif) for test, motif in ignores(arguments)]

    if ecartes:
        print(f"\n=== ce qui n'a PAS ete verifie ({len(ecartes)}) ===")
        motifs: dict[str, list[str]] = {}
        for _, test, motif in ecartes:
            motifs.setdefault(motif, []).append(test)
        for motif, tests in sorted(motifs.items()):
            print(f"\n  {len(tests)} test(s) : {motif}")
            for test in tests:
                print(f"    {test}")

    print()
    if echecs:
        print(f"ECHEC : {', '.join(echecs)}")
        return 1
    print("Tout passe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
