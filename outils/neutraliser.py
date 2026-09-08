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

Rend 0 si les sept gardes sont detectees, 1 sinon.

Cinq gardent une SESSION SAP ouverte (§5). Deux gardent la REPRISE, un moment
ou aucun driver n'existe et ou une garde qui cede fait rejouer un item que SAP
a peut-etre deja enregistre.
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
from falcon.journal import lecteur                            # noqa: E402
from falcon.pipeline import modele                            # noqa: E402

#: Garde -> (porteur, attribut, suite qui doit s'en apercevoir).
#:
#: Ajouter une garde sans l'inscrire ici la laisserait non verifiee. C'est
#: arrive : la garde de reprise n'y figurait pas, et son contournement par
#: empreinte vide a vecu jusqu'a ce qu'on le cherche a la main.
#:
#: Les cinq premieres sont les gardes de session du §5, portees par
#: `DriverGarde`. Les deux suivantes protegent la REPRISE — un moment ou
#: aucun driver n'est ouvert, et ou une garde qui cede fait rejouer un item
#: que SAP a peut-etre deja enregistre.
#:
#: Une garde ecrite EN LIGNE au milieu d'une fonction n'a pas de nom, donc ne
#: se neutralise pas, donc n'est pas verifiable ici. C'est pourquoi la garde
#: de reprise a ete extraite dans `lecteur.garde_du_monde` : lui donner un nom
#: etait la condition pour pouvoir la retirer.
CIBLES = {
    "1 identite": (gardes.DriverGarde, "_garde_identite", "tests.test_gardes"),
    "2 statut": (gardes.DriverGarde, "_garde_statut", "tests.test_gardes"),
    "3 fenetres": (gardes.DriverGarde, "_garde_fenetres", "tests.test_gardes"),
    "4 relecture": (gardes.DriverGarde, "_garde_relecture", "tests.test_gardes"),
    "5 rayon": (gardes.DriverGarde, "_garde_rayon", "tests.test_gardes"),
    "6 reprise": (lecteur, "garde_du_monde", "tests.test_journal"),
    "7 empreinte": (modele.Pipeline, "__post_init__", "tests.test_pipeline"),
}


def _relancer_la_suite(nom: str) -> int:
    """Recharge les tests et rend le nombre d'echecs."""
    for module in [m for m in list(sys.modules) if m.startswith("tests")]:
        del sys.modules[module]
    suite = unittest.defaultTestLoader.loadTestsFromName(nom)
    resultat = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    return len(resultat.failures) + len(resultat.errors)


def main() -> int:
    for suite in sorted({s for _, _, s in CIBLES.values()}):
        if _relancer_la_suite(suite) != 0:
            print(f"{suite} ne passe pas avant neutralisation : "
                  f"rien a conclure.")
            return 1

    muettes = []
    for libelle, (porteur, attribut, suite) in sorted(CIBLES.items()):
        origine = getattr(porteur, attribut)
        setattr(porteur, attribut, lambda *a, **k: None)
        try:
            rates = _relancer_la_suite(suite)
        finally:
            setattr(porteur, attribut, origine)

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
