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


#: Un test ignore, tel que `unittest -v` l'ecrit. DEUX formes, et la seconde
#: cassait la premiere version de ce motif :
#:
#:     test_x (mod.Classe.test_x) ... skipped 'motif'
#:
#:     test_x (mod.Classe.test_x)
#:     Premiere ligne de la docstring ... skipped 'motif'
#:
#: Quand le test a une docstring, `... skipped` se trouve sur la LIGNE DE LA
#: DOCSTRING. Un `^(\S+)` y capturait donc son premier mot — la liste
#: annoncait « La », « Une », « Meme » au lieu des noms de tests. Une liste de
#: ce qui n'a pas ete verifie et qui ne sait pas le nommer ne vaut pas mieux
#: que le decompte qu'elle remplace.
IGNORE = re.compile(
    r"^(?P<test>\w+) \((?P<chemin>[\w.]+)\)"       # toujours sur sa ligne
    r"(?:\n[^\n]*?)?"                              # la docstring, s'il y en a
    # Le guillemet fermant doit etre CELUI qui a ouvert : `unittest` passe le
    # motif par `repr`, donc un motif contenant une apostrophe — « pas
    # dependance d'execution » — sort entre guillemets doubles. Une classe
    # `['\"]` des deux cotes tronquait le motif a la premiere apostrophe.
    r" \.\.\. skipped (?P<q>['\"])(?P<motif>.*?)(?P=q)$",
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
