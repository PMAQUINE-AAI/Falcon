"""Lire une grille ALV, et y retrouver une ligne par son CONTENU.

Deux fonctions, et elles ne decident rien. Elles lisent, elles refusent ce
qu'elles ne peuvent pas lire, et elles rendent des donnees. La politique — que
faire de zero ligne, que faire de trois — appartient a l'appelant : au moteur,
ou vivent deja `ItemAbandonne` et `ArretBloquant`. Un module du controleur qui
leverait `ItemAbandonne` importerait une notion de moteur.

**Pourquoi ici, et pas dans un paquet a part.** Le seul argument de ces
fonctions est un `Poste`, qui vit a cote, dans `poste.py`. Un paquet dedie ne
contiendrait qu'une fonction important le controleur. Et un `falcon/tableau/` a
une lettre de `falcon/tableur/` — le classeur — serait exactement le genre de
nom qu'on lit de travers un vendredi soir.

**Pourquoi une seule boucle dans tout le depot.** `volumique/se16n.py` lisait
deja une grille, et c'etait le seul endroit. Recopier ce corps ailleurs, c'est
se donner rendez-vous avec le jour ou l'une des deux copies apprend quelque
chose que l'autre ignore. Un test AST refuse desormais tout appel a
`grid_read` hors de ce module.

**Ce que ce module ne fait pas, et pourquoi c'est le point.**

Il ne selectionne jamais par index litteral. `couture/interface.py` le dit
d'elle-meme : « Selectionner par index est un piege, pas une commodite.
L'index depend du contenu de la base au moment ou on regarde. […] La regle :
lire la grille avec `grid_read` pour retrouver la ligne voulue par son CONTENU,
et n'appeler ceci qu'avec l'index ainsi obtenu. » Cette regle etait ecrite et
personne ne l'appliquait, faute d'un endroit ou l'ecrire. C'est cet endroit.

**Le refus qui compte, et il n'est pas theorique.** `chercher` exige que la
colonne demandee figure dans `grid_columns`. Sans lui, une colonne mal
orthographiee ne leve rien : `couture/double.py` rend `""` pour une colonne
inconnue, et l'appariement retiendrait alors TOUTES les lignes dont la cellule
est vide — puis en rendrait une. Ce que fait `GetCellValue` en production sur
une colonne inconnue, personne ici ne le sait ; ce refus existe pour ne pas
avoir a le savoir.
"""

from __future__ import annotations

from typing import Any

from .gardes import _comparer
from .poste import Poste


class GrilleIllisible(Exception):
    """La grille ne peut pas etre lue telle qu'on la demande.

    Distincte de `ObjetIntrouvable`, qui dit que l'identifiant ne resout pas :
    celle-ci dit que la grille resout mais que ce qu'on lui demande n'y est
    pas. Les deux se corrigent differemment — l'un en relevant l'ecran, l'autre
    en relisant les noms de colonnes.
    """


def colonnes_de(poste: Poste, id: str) -> tuple[str, ...]:
    """Les colonnes que la grille EXPOSE, dans l'ordre d'affichage.

    **Ce n'est pas la liste des colonnes de la table.** `grid_columns` derive
    de `ColumnOrder`, c'est-a-dire de la mise en page ALV active dans la
    session de cet utilisateur-la. Deux personnes peuvent en obtenir deux
    listes differentes sur le meme ecran. Rien ici ne peut le corriger ; tout
    ce qu'on peut faire est de ne jamais supposer une colonne sans l'avoir
    trouvee dans cette liste.
    """
    return tuple(poste.grid_columns(id))


def relever(poste: Poste, id: str, *,
            colonnes: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """Toutes les lignes de la grille, par index ABSOLU et sans defilement.

    `colonnes` vide = celles que la grille expose. Declarees, elles deviennent
    un refus : une colonne absente arrete la lecture au lieu de rendre une
    colonne vide qui aurait l'air d'une colonne.

    L'index est absolu et aucun defilement n'est requis — c'est la propriete
    qui separe l'ALV du table control, et `couture/interface.py` la porte en
    en-tete. Un code qui prendrait l'un pour l'autre lirait des lignes
    lointaines en croyant repartir du debut.
    """
    exposees = colonnes_de(poste, id)
    retenues = _retenir(exposees, colonnes, id)
    return [
        {colonne: poste.grid_read(id, ligne, colonne)
         for colonne in retenues}
        for ligne in range(poste.grid_rows(id))
    ]


def chercher(poste: Poste, id: str, colonne: str, valeur: str, *,
             comparaison: str = "casse") -> tuple[int, ...]:
    """Les rangs dont `colonne` apparie `valeur`. TOUS, jamais un seul.

    Rendre le premier serait choisir au hasard la ligne qu'on va modifier.
    Rendre le compte laisserait l'appelant croire qu'il peut s'en servir. Le
    seul rendu honnete est l'ensemble : c'est l'appelant qui decide, et il n'a
    aucun moyen d'ignorer qu'ils etaient trois.

    `comparaison` est celle des gardes — `exact`, `casse`, `prefixe` — et pas
    un second dialecte. `_comparer` rend « conforme » ou « normalise » quand
    ca apparie, « tronque » ou « divergent » sinon ; on n'accepte ici que les
    deux premiers, parce qu'une troncature n'est pas une egalite : « 1000 » et
    « 1 » ne designent pas la meme variante.
    """
    lignes = relever(poste, id, colonnes=(colonne,))
    return tuple(
        rang for rang, ligne in enumerate(lignes)
        if _comparer(valeur, ligne[colonne], comparaison)
        in ("conforme", "normalise")
    )


def _retenir(exposees: tuple[str, ...], demandees: tuple[str, ...],
             id: str) -> tuple[str, ...]:
    """Les colonnes a lire, ou `GrilleIllisible`."""
    if not demandees:
        return exposees
    manquantes = [c for c in demandees if c not in exposees]
    if manquantes:
        raise GrilleIllisible(
            f"grille {id!r} : colonne(s) {manquantes} absente(s). Elle expose "
            f"{list(exposees)}. Lire une colonne qu'elle n'expose pas rendrait "
            f"une valeur vide qui aurait l'air d'une valeur — et sur une "
            f"recherche, apparierait toutes les lignes a la fois")
    return tuple(demandees)
