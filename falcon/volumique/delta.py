"""Ce qui a bouge depuis le dernier export.

Le cas 2 est un audit RECURRENT : on ne cherche pas l'etat complet, on cherche
les ecrasements introduits au fil de l'eau. Le §3.6 demande donc, en plus de
l'etat, un delta contre l'export precedent.

**Trois categories, et la troisieme est celle qui compte.** Les ajouts et les
retraits se voient a l'oeil sur deux fichiers ; les MODIFICATIONS non. Ce sont
elles que le cas 2 traque : une ligne toujours la, dont une colonne a change.

**L'identite d'une ligne est declaree, jamais devinee.** Deux exports d'une
meme table n'ont aucune raison de sortir dans le meme ordre : rapprocher par
rang produirait des modifications imaginaires en masse. L'appelant declare les
colonnes de clef, comme une pipeline iterative declare les siennes, et la
meme fonction d'empreinte sert dans les deux cas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from falcon.donnees import identifiant

from .export import Export


class DeltaImpossible(Exception):
    """Les deux exports ne sont pas comparables."""


@dataclass(frozen=True)
class Modification:
    """Une ligne presente des deux cotes, dont au moins une colonne a change."""

    clef: dict[str, str]
    avant: dict[str, Any]
    apres: dict[str, Any]
    colonnes: tuple[str, ...] = ()

    def __str__(self) -> str:
        valeurs = ", ".join(f"{c}: {self.avant.get(c)!r} -> {self.apres.get(c)!r}"
                            for c in self.colonnes)
        return f"{self.clef} : {valeurs}"


@dataclass(frozen=True)
class Delta:
    """Ce qui a change entre deux exports."""

    ajoutes: tuple[dict[str, Any], ...] = ()
    retires: tuple[dict[str, Any], ...] = ()
    modifies: tuple[Modification, ...] = ()
    cles: tuple[str, ...] = ()
    inchanges: int = 0

    @property
    def vide(self) -> bool:
        return not (self.ajoutes or self.retires or self.modifies)

    def __len__(self) -> int:
        return len(self.ajoutes) + len(self.retires) + len(self.modifies)


def _indexer(lignes: Sequence[Mapping[str, Any]], cles: Sequence[str],
             quoi: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for rang, ligne in enumerate(lignes, start=1):
        manquantes = [c for c in cles if c not in ligne]
        if manquantes:
            raise DeltaImpossible(
                f"{quoi}, ligne {rang} : colonne(s) de clef absente(s) "
                f"{manquantes}. Une clef qui ne resout pas rapprocherait des "
                f"lignes au hasard")
        marque = identifiant([str(ligne[c]) for c in cles])
        if marque in index:
            raise DeltaImpossible(
                f"{quoi}, ligne {rang} : deux lignes portent la meme clef "
                f"{ {c: ligne[c] for c in cles} }. Le rapprochement en "
                f"perdrait une, sans le dire")
        index[marque] = dict(ligne)
    return index


def delta(precedent: Export, courant: Export,
          cles: Sequence[str]) -> Delta:
    """Ce qui separe deux exports d'une meme table.

    Refuse de comparer deux tables differentes : le §3.6 fait de la provenance
    le contrat, et comparer `MARA` a `MARC` produirait un delta ou tout est
    ajoute et tout est retire — un resultat qui a l'air d'un resultat.
    """
    if not cles:
        raise DeltaImpossible(
            "aucune colonne de clef. Rapprocher par rang produirait des "
            "modifications imaginaires des que l'ordre change")
    if precedent.provenance.table != courant.provenance.table:
        raise DeltaImpossible(
            f"tables differentes : {precedent.provenance.table!r} et "
            f"{courant.provenance.table!r}")

    avant = _indexer(precedent.lignes, cles, "export precedent")
    apres = _indexer(courant.lignes, cles, "export courant")

    ajoutes = [apres[m] for m in apres if m not in avant]
    retires = [avant[m] for m in avant if m not in apres]

    modifies: list[Modification] = []
    inchanges = 0
    for marque in avant.keys() & apres.keys():
        gauche, droite = avant[marque], apres[marque]
        colonnes = tuple(sorted(
            c for c in set(gauche) | set(droite)
            if gauche.get(c) != droite.get(c)))
        if not colonnes:
            inchanges += 1
            continue
        modifies.append(Modification(
            clef={c: str(droite[c]) for c in cles},
            avant=gauche, apres=droite, colonnes=colonnes))

    return Delta(ajoutes=tuple(ajoutes), retires=tuple(retires),
                 modifies=tuple(sorted(modifies, key=lambda m: sorted(m.clef.items()))),
                 cles=tuple(cles), inchanges=inchanges)


def rendre(ecart: Delta) -> str:
    """Le delta en texte, sans couleur ni ANSI."""
    lignes = [
        "  delta",
        f"    ajoutes    {len(ecart.ajoutes)}",
        f"    retires    {len(ecart.retires)}",
        f"    modifies   {len(ecart.modifies)}",
        f"    inchanges  {ecart.inchanges}",
    ]
    if ecart.modifies:
        lignes.append("")
        lignes.append("  Ce sont les modifications qui comptent : une ligne "
                      "toujours la,")
        lignes.append("  dont une colonne a change. Elles ne se voient pas a "
                      "l'oeil.")
        for modification in ecart.modifies:
            lignes.append(f"    {modification}")
    elif ecart.vide:
        lignes.append("")
        lignes.append("  Rien n'a bouge depuis l'export precedent.")
    return "\n".join(lignes)
