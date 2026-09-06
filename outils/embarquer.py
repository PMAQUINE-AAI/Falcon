#!/usr/bin/env python3
"""Construit `falcon.pyz` — la livraison en un seul fichier executable.

Le §6 l'exige : « le depot est modulaire, la livraison est un fichier unique
executable ». La contrainte d'autonomie au deploiement qui avait conduit
EagleLoader a un fichier de 4500 lignes reste valable, mais elle se traite **a
la construction**, pas dans l'organisation du code source.

    python outils/embarquer.py            # produit falcon.pyz
    python falcon.pyz inventaire trace.vbs

`zipapp` est dans la bibliotheque standard : construire le bundle n'ajoute
aucune dependance, y compris de construction.

**PyYAML est embarque, pywin32 ne l'est pas.** PyYAML est du Python pur et
voyage ; pywin32 est une extension binaire Windows, liee a une version
d'interpreteur, et un `.pyd` fige dans une archive serait faux la moitie du
temps. Il s'installe sur le poste. La seule commande qui l'exige —
`diagnostiquer` — le dit deja par `SapIndisponible`, avec la ligne de commande
a taper.

**L'accelerateur C de PyYAML est ECARTE volontairement.** `_yaml` est compile
pour la plateforme de construction : embarquer un `.so` Linux dans un bundle
destine a Windows produirait une archive qui a l'air complete et qui echoue a
l'import. PyYAML retombe seul sur son analyseur en Python pur — plus lent, et
sans importance ici : FALCON lit des fichiers de configuration, pas des
gigaoctets.
"""

from __future__ import annotations

import argparse
import compileall  # noqa: F401  (documente : voir `_copier`, on n'en veut pas)
import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

#: Point d'entree du bundle.
ENTREE = "falcon.commandes.principal:main"

#: Le `__main__.py` de l'archive, ecrit a la main.
#:
#: `zipapp` sait en generer un, mais son gabarit appelle `main()` en jetant ce
#: qu'elle rend : le bundle sortait toujours a 0. Ces trois lignes-la sont la
#: difference entre un code de retour qui veut dire quelque chose et un code
#: de retour qui ment.
POINT_D_ENTREE = """import sys

from falcon.commandes.principal import main

sys.exit(main())
"""

#: Ce qui n'entre pas dans l'archive.
#:
#: Les `__pycache__` sont lies a une version d'interpreteur : embarques, ils
#: seraient ignores au mieux, trompeurs au pire. Les extensions binaires sont
#: liees a une plateforme, et le bundle traverse les plateformes.
EXCLUS = ("__pycache__", "*.pyc", "*.pyo", "*.so", "*.pyd", "*.dll")


def _copier(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination,
                    ignore=shutil.ignore_patterns(*EXCLUS))


def _paquet_yaml() -> Path:
    """Le paquet PyYAML installe, en Python pur."""
    try:
        import yaml
    except ImportError as erreur:      # pragma: no cover - dependance declaree
        raise SystemExit(
            f"PyYAML est introuvable ({erreur}). C'est la seule dependance "
            f"d'execution de FALCON, et le bundle doit l'embarquer : "
            f"`pip install PyYAML`") from erreur
    chemin = Path(yaml.__file__).parent
    if not (chemin / "__init__.py").exists():   # pragma: no cover
        raise SystemExit(f"{chemin} ne ressemble pas au paquet PyYAML")
    return chemin


def construire(cible: str | Path = RACINE / "falcon.pyz") -> Path:
    """Assemble le bundle et rend son chemin."""
    destination = Path(cible)
    with tempfile.TemporaryDirectory() as brouillon:
        etage = Path(brouillon)
        _copier(RACINE / "falcon", etage / "falcon")
        _copier(_paquet_yaml(), etage / "yaml")

        # Le `__main__.py` est ECRIT ICI, et pas laisse a `zipapp`.
        #
        # Le gabarit de `zipapp` appelle `main()` sans transmettre ce qu'elle
        # rend : le bundle sortait toujours a 0, quoi qu'il arrive. Une trace
        # illisible, une session SAP absente, une commande refusee — tout
        # ressortait « reussi », et un script qui s'appuie sur le code de
        # retour aurait cru le lot passe. C'est exactement le genre de defaut
        # que ce projet traque : il ne leve pas.
        (etage / "__main__.py").write_text(POINT_D_ENTREE, encoding="utf-8")

        destination.parent.mkdir(parents=True, exist_ok=True)
        zipapp.create_archive(etage, destination, compressed=True)
    return destination


def main(arguments: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="embarquer", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    analyseur.add_argument("-o", "--sortie", default=str(RACINE / "falcon.pyz"))
    options = analyseur.parse_args(sys.argv[1:] if arguments is None
                                   else arguments)

    chemin = construire(options.sortie)
    taille = chemin.stat().st_size
    print(f"{chemin}  ({taille // 1024} Kio)")
    print()
    print("  python falcon.pyz console")
    print("  python falcon.pyz inventaire trace.vbs")
    print()
    print("  `diagnostiquer` exige en plus `pip install pywin32` sur le poste :")
    print("  une extension binaire Windows ne s'embarque pas.")
    return 0


if __name__ == "__main__":              # pragma: no cover
    raise SystemExit(main())
