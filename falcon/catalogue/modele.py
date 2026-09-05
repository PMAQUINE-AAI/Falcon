"""Ecrans catalogues, et leurs variantes.

**Les variantes sont le point de ce module.** Un meme dynpro ne rend pas
toujours les memes champs : onglets, layouts ALV, table controls, parametres
utilisateur. La specification dit que ne pas traiter cette variabilite est la
premiere cause d'echec d'un framework de ce type — parce qu'un catalogue qui
ne connait qu'un rendu par dynpro fait echouer la garde d'identite sur le
second rendu, ou pire, la fait passer alors que l'ecran n'est pas celui qu'on
croit.

La clef d'une variante est donc le triplet PLUS l'empreinte de l'ensemble des
identifiants presents. Deux rendus du meme dynpro avec des champs differents
sont deux variantes, et le catalogue les distingue.

Les types viennent du noyau : `Ecran`, `Champ`, `Identite` et `empreinte` y
sont deja definis, et en recreer des variantes locales ferait diverger le
catalogue de ce que la couture releve.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from falcon.noyau import Champ, Ecran, Identite, empreinte

#: Une variante relevee sur un systeme reel, par la passe de cartographie.
OBSERVEE = "observee"

#: Une variante conjecturee — typiquement depuis une trace du recorder, qui
#: donne les identifiants TOUCHES mais ni l'identite d'ecran ni les
#: identifiants PRESENTS. Une esquisse ne peut jamais satisfaire une garde.
ESQUISSE = "esquisse"

SOURCES = frozenset({OBSERVEE, ESQUISSE})


class CatalogueInvalide(Exception):
    """Le catalogue ne peut pas etre lu, ou on lui demande l'impossible."""


@dataclass(frozen=True)
class ClefVariante:
    """Triplet d'ecran plus empreinte des identifiants presents."""

    transaction: str
    programme: str
    dynpro: str                      # chaine : « 0100 » n'est pas « 100 »
    empreinte: str

    @property
    def triplet(self) -> tuple[str, str, str]:
        return (self.transaction, self.programme, self.dynpro)

    def __str__(self) -> str:
        return f"{self.transaction}/{self.programme}/{self.dynpro}#{self.empreinte}"


@dataclass(frozen=True)
class Variante:
    """Un rendu observe d'un ecran."""

    clef: ClefVariante
    champs: tuple[Champ, ...] = ()
    titre: str = ""
    capture_le: str = ""
    source: str = OBSERVEE

    def __post_init__(self) -> None:
        if self.source not in SOURCES:
            raise CatalogueInvalide(
                f"source {self.source!r}, attendu {sorted(SOURCES)}")

    @property
    def observee(self) -> bool:
        return self.source == OBSERVEE

    def par_suffixe(self, suffixe: str) -> tuple[Champ, ...]:
        """Champs dont l'identifiant se termine par `suffixe`.

        Le numero de sous-ecran figure dans l'identifiant et change avec le
        type d'objet affiche : un chemin fige cesse de resoudre, la lecture
        leve, et la boucle sort en croyant avoir fini.
        """
        return tuple(c for c in self.champs if c.id.endswith(suffixe))


def clef_de(ecran: Ecran) -> ClefVariante:
    """Clef de variante d'un ecran releve."""
    return ClefVariante(
        transaction=ecran.identite.transaction,
        programme=ecran.identite.programme,
        dynpro=ecran.identite.dynpro,
        empreinte=empreinte(c.id for c in ecran.champs),
    )


def variante_de(ecran: Ecran, *, source: str = OBSERVEE) -> Variante:
    return Variante(clef=clef_de(ecran), champs=ecran.champs,
                    titre=ecran.titre, capture_le=ecran.capture_le,
                    source=source)
