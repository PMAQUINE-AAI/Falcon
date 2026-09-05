"""Ce qu'une pipeline declare.

Ce module ne connait ni SAP, ni le controleur, ni les gardes. Il ne peut
importer ni `falcon.couture` ni `falcon.controleur` — regle verifiee par
`tests/test_frontieres.py`.

Ce n'est pas de l'hygiene : c'est la traduction mecanique de la separation du
modele de securite. Une pipeline qui ne peut nommer aucun driver ne peut pas
non plus, par construction, en manipuler un ni desactiver une garde. Elle
declare une intention ; c'est le controleur qui applique les regles.

La conversion d'une `Etape` en contrat de garde appartient donc au controleur,
et le sens de l'import le dit : `falcon/controleur/` importe `falcon/pipeline/`,
jamais l'inverse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Actions declarables dans une etape.
#:
#: La specification en nomme quatre — set, press, select, read. Les trois
#: autres suivent la meme logique que l'elargissement de la couture : sans
#: `cocher`, on ne peut pas positionner explicitement les trois cases de
#: selection que le terrain impose ; sans `vkey`, aucune touche de fonction ;
#: et `python` est l'echappatoire que la specification rend obligatoire.
ACTIONS = frozenset({"set", "cocher", "press", "select", "vkey", "lire",
                     "python"})

#: Actions qui exigent une cible.
AVEC_CIBLE = frozenset({"set", "cocher", "press", "select", "lire"})

#: Actions qui exigent une source de valeur.
AVEC_SOURCE = frozenset({"set", "cocher"})

CLASSES = frozenset({"iterative", "volumique"})

#: Genres de source, dans l'ordre de la specification : colonne du fichier
#: d'entree, constante, ou valeur lue par une etape `lire` precedente.
GENRES_SOURCE = frozenset({"colonne", "constante", "lue"})


@dataclass(frozen=True)
class Source:
    """D'ou vient la valeur d'une saisie."""

    genre: str                      # colonne | constante | lue
    valeur: str


@dataclass(frozen=True)
class DerogationDeclaree:
    """Une derogation telle que le YAML la demande.

    Distincte de `controleur.Derogation`, qui est celle que le controleur
    ACCORDE apres validation. La pipeline demande, le controleur dispose —
    et le typage le dit.
    """

    garde: str
    portee: str
    motif: str


@dataclass(frozen=True)
class Etape:
    nom: str
    action: str
    cible: str = ""
    source: Source | None = None
    fonction: str = ""                       # action « python »

    # Ce que l'etape declare aux gardes.
    ecran: tuple[str, str, str] | None = None
    navigation_libre: bool = False
    fenetres: tuple[str, ...] = ("wnd[0]",)
    statut_attendu: str | None = None
    sauvegarde: bool = False
    comparaison: str = "casse"
    derogations: tuple[DerogationDeclaree, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Pipeline:
    nom: str
    classe: str                              # iterative | volumique
    etapes: tuple[Etape, ...]
    plafond_items: int
    plafond_sauvegardes: int
    cles: tuple[str, ...] = ()               # obligatoire si iterative
    validation_reelle: dict[str, Any] | None = None
    empreinte: str = ""
    source: str = ""                         # chemin du fichier charge

    @property
    def iterative(self) -> bool:
        return self.classe == "iterative"

    @property
    def sauvegarde_quelque_part(self) -> bool:
        return any(e.sauvegarde for e in self.etapes)
