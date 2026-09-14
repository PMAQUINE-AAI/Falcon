"""Les refus du PRE-VOL — ce qui tombe avant le premier contact avec SAP.

Un module a part, et pour une raison de dependances qui n'est pas cosmetique :
`boucle.py` importe `extraction.py`, donc `extraction.py` ne peut pas importer
`boucle.py`. Sans ce module, l'extraction aurait sa propre famille
d'exceptions, et un refus de pre-vol se serait rendu de deux facons selon
l'endroit ou il naissait — l'un lisible par la CLI, l'autre en trace de pile.

**Ce que ces refus ont en commun, et qui les distingue de tout le reste :**
ils disent qu'un defaut de la PIPELINE ou du JEU rend le lot injouable. Ce
n'est pas un comportement de SAP. Les faire passer par la taxonomie les
deguiserait en incidents metier, et l'auteur de la pipeline chercherait au
mauvais endroit.
"""

from __future__ import annotations


class PreparationImpossible(Exception):
    """Le jeu et la pipeline ne vont pas ensemble. Rien n'a ete tente."""


class ExtractionImpossible(PreparationImpossible):
    """Un fichier d'extraction ne peut pas etre ecrit.

    Levee AVANT d'ecrire quoi que ce soit — un fichier a moitie ecrit serait
    pire qu'aucun fichier. Sous-classe de `PreparationImpossible` parce que
    c'est le meme genre de defaut, decouvert au meme moment : le dossier de
    sortie, les noms de fichiers et les collisions sont tous calculables des
    la lecture du jeu, donc sans agir.
    """
