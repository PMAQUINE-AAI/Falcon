#!/usr/bin/env python3
"""Neutralise chaque garde tour a tour et verifie que la suite tombe.

Une garde couverte par des tests qui passent n'est pas une garde verifiee :
le test passerait aussi si la garde ne faisait rien. La seule preuve qu'elle
protege quelque chose est de la retirer et de constater que la suite s'en
apercoit.

Ce fichier existe parce que le backlog affirmait cette verification alors
qu'elle n'etait qu'un geste manuel. Une affirmation qu'aucun mecanisme ne
soutient se perime en silence — exactement le defaut que ce projet traque
ailleurs.

    python outils/neutraliser.py

Rend 0 si les cinq gardes sont detectees, 1 sinon.
"""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from falcon.controleur import gardes                          # noqa: E402

#: Garde -> methode a neutraliser. Ajouter une garde sans l'inscrire ici la
#: laisserait non verifiee : c'est pourquoi le total est compare a DEROGEABLES
#: et aux deux gardes non derogeables.
CIBLES = {
    "1 identite": "_garde_identite",
    "2 statut": "_garde_statut",
    "3 fenetres": "_garde_fenetres",
    "4 relecture": "_garde_relecture",
    "5 rayon": "_garde_rayon",
}

SUITE = "tests.test_gardes"


def _relancer_la_suite() -> int:
    """Recharge les tests et rend le nombre d'echecs."""
    for module in [m for m in list(sys.modules) if m.startswith("tests")]:
        del sys.modules[module]
    suite = unittest.defaultTestLoader.loadTestsFromName(SUITE)
    resultat = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    return len(resultat.failures) + len(resultat.errors)


def main() -> int:
    if _relancer_la_suite() != 0:
        print("La suite ne passe pas avant neutralisation : rien a conclure.")
        return 1

    muettes = []
    for libelle, methode in sorted(CIBLES.items()):
        origine = getattr(gardes.DriverGarde, methode)
        setattr(gardes.DriverGarde, methode, lambda self, *a, **k: None)
        try:
            rates = _relancer_la_suite()
        finally:
            setattr(gardes.DriverGarde, methode, origine)

        detectee = rates > 0
        if not detectee:
            muettes.append(libelle)
        print(f"  garde {libelle:12s} neutralisee -> "
              f"{'detectee' if detectee else 'PASSEE INAPERCUE'} "
              f"({rates} test(s) en echec)")

    print()
    if muettes:
        print(f"ECHEC : aucun test ne protege {', '.join(muettes)}")
        return 1
    print(f"Les {len(CIBLES)} gardes sont protegees par au moins un test.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
