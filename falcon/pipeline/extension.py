"""L'echappatoire Python.

La specification la rend obligatoire, et pour une raison precise : toutes les
manipulations SAP ne sont pas exprimables en sequence declarative. Le cas
fondateur est la langue de lecture d'un texte long, qui impose « supprimer,
sauver, rouvrir, ecrire, sauver » — une sequence qu'une pipeline declarative ne
peut pas decouvrir, et que l'utilisateur doit pouvoir coder.

Cette echappatoire ne doit pas devenir une porte de sortie du modele de
securite. Deux choses l'en empechent :

1. la fonction recoit un `Poste`, la facade etroite du controleur, et rien
   d'autre — elle code n'importe quelle mecanique retorse sans jamais sortir
   des gardes ;
2. elle est enregistree par un nom, et le chargeur REFUSE un nom inconnu. Une
   pipeline ne peut donc pas designer du code arbitraire par son chemin.
"""

from __future__ import annotations

from typing import Callable

#: Signature attendue : (poste, item, contexte) -> None.
#:
#: `poste` est la facade gardee, `item` la ou les lignes d'entree de l'unite
#: de sauvegarde en cours, `contexte` le dictionnaire des valeurs lues par les
#: etapes precedentes.
Fonction = Callable[..., None]

_REGISTRE: dict[str, Fonction] = {}


class ExtensionInconnue(Exception):
    """Une pipeline reference une fonction qui n'est pas enregistree."""


def etape_python(nom: str) -> Callable[[Fonction], Fonction]:
    """Enregistre une fonction utilisable comme etape.

        @etape_python("basculer_langue_texte_long")
        def basculer(poste, item, contexte): ...
    """
    def poser(fonction: Fonction) -> Fonction:
        if nom in _REGISTRE and _REGISTRE[nom] is not fonction:
            raise ValueError(
                f"deux fonctions enregistrees sous le nom {nom!r} : la "
                f"pipeline ne saurait pas laquelle appeler")
        _REGISTRE[nom] = fonction
        return fonction
    return poser


def resoudre(nom: str) -> Fonction:
    if nom not in _REGISTRE:
        raise ExtensionInconnue(
            f"aucune extension enregistree sous le nom {nom!r}. "
            f"Connues : {sorted(_REGISTRE) or 'aucune'}")
    return _REGISTRE[nom]


def connues() -> frozenset[str]:
    return frozenset(_REGISTRE)


def oublier_tout() -> None:
    """Vide le registre. Reserve aux tests."""
    _REGISTRE.clear()
