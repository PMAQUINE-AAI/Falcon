"""La carte d'ecran de `SE16N` — relevee, jamais devinee.

**Les identifiants d'ecran de `SE16N` ne sont ni dans ce depot, ni dans la
trace fournie.** Les ecrire de memoire produirait un module qui a l'air
complet et qui echoue au premier appel reel, avec un `ObjetIntrouvable` que
personne ne saurait rattacher a une conjecture faite six mois plus tot.

La mecanique d'export est donc **parametree par une carte**, livree vide avec
ses marqueurs. Tant qu'elle n'est pas remplie, l'export refuse de tourner et
dit lequel des champs manque. Un `python -m falcon diagnostiquer` sur l'ecran
`SE16N` d'un poste reel donne tout ce qu'il faut pour la remplir.

C'est la meme forme que le lot 6 : la mecanique d'abord, la verite terrain
quand elle arrive, et un refus explicite entre les deux. La regle transverse
du projet — « aucun comportement SAP n'est invente » — ne souffre pas
d'exception parce qu'un lot serait plus commode a finir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

#: Marqueur laisse dans la carte livree. Le meme que celui du brouillon de
#: pipeline, et pour la meme raison : il rend le fichier inutilisable tel quel.
TODO = "TODO"

VERSION = 1

#: Carte livree avec le paquet, vide et marquee.
CHEMIN_CARTE_DEFAUT = Path(__file__).parent / "carte_se16n.yaml"

#: Champs simples que la carte doit nommer.
CHAMPS = ("champ_table", "bouton_executer", "grille")

#: Ecrans que la carte doit nommer, par leur triplet.
ECRANS = ("ecran_selection", "ecran_resultat")


class CarteIncomplete(Exception):
    """La carte porte encore des marqueurs : rien ne peut etre execute."""


class CarteInvalide(Exception):
    """La carte ne se lit pas."""


@dataclass(frozen=True)
class Carte:
    """Ce qu'il faut savoir de `SE16N` pour l'automatiser.

    Volontairement plate et courte : plus elle grossit, plus elle conjecture.
    """

    champ_table: str = TODO
    bouton_executer: str = TODO
    grille: str = TODO
    ecran_selection: tuple[str, str, str] = (TODO, TODO, TODO)
    ecran_resultat: tuple[str, str, str] = (TODO, TODO, TODO)
    #: Nom de critere -> identifiant de champ. Vide tant que rien n'est releve.
    criteres: dict[str, str] = field(default_factory=dict)
    source: str = ""

    @property
    def manquants(self) -> tuple[str, ...]:
        absents = [c for c in CHAMPS
                   if TODO in str(getattr(self, c)) or not getattr(self, c)]
        for nom in ECRANS:
            triplet = getattr(self, nom)
            if any(TODO in str(p) or not p for p in triplet):
                absents.append(nom)
        return tuple(absents)

    @property
    def complete(self) -> bool:
        return not self.manquants

    def verifier(self) -> None:
        """Refuse une carte incomplete, en nommant ce qui manque."""
        if self.manquants:
            raise CarteIncomplete(
                f"carte SE16N incomplete : {list(self.manquants)} "
                f"{'(' + self.source + ')' if self.source else ''}. Ces "
                f"identifiants ne sont pas devinables — les relever avec "
                f"`python -m falcon diagnostiquer` sur l'ecran SE16N d'un "
                f"poste reel, puis les inscrire dans la carte")

    def champ_de_critere(self, nom: str) -> str:
        """L'identifiant du champ portant ce critere, ou un refus nomme."""
        if nom not in self.criteres:
            raise CarteIncomplete(
                f"critere {nom!r} : aucun champ ne lui correspond dans la "
                f"carte. Les criteres de SE16N vivent dans un table control "
                f"dont la disposition n'a pas ete relevee ; conjecturer une "
                f"position, c'est filtrer sur autre chose que ce qu'on croit")
        return self.criteres[nom]


def charger_carte(chemin: str | Path | None = None) -> Carte:
    """Lit une carte. La carte livree est vide, et c'est voulu."""
    cible = Path(chemin) if chemin is not None else CHEMIN_CARTE_DEFAUT
    if chemin is None:
        # La carte livree avec le paquet. `Path(__file__).parent` ne la trouve
        # pas depuis `falcon.pyz` : dans un zipapp, `__file__` n'est pas un
        # chemin de systeme de fichiers, et le fichier « n'existe pas ».
        # `importlib.resources` lit les deux.
        brut = files(__package__).joinpath("carte_se16n.yaml").read_text(
            encoding="utf-8")
    else:
        if not cible.exists():
            raise CarteInvalide(f"carte introuvable : {cible}")
        brut = cible.read_text(encoding="utf-8")

    contenu = yaml.safe_load(brut) or {}
    if not isinstance(contenu, dict):
        raise CarteInvalide(f"{cible} : un dictionnaire est attendu")
    if contenu.get("version") != VERSION:
        raise CarteInvalide(
            f"{cible} : version {contenu.get('version')!r}, attendu {VERSION}")

    inconnues = sorted(set(contenu) - {"version", "criteres", *CHAMPS, *ECRANS})
    if inconnues:
        raise CarteInvalide(f"{cible} : cle(s) inconnue(s) {inconnues}")

    return Carte(
        source=str(cible),
        criteres={str(c): str(v)
                  for c, v in (contenu.get("criteres") or {}).items()},
        **{c: str(contenu.get(c, TODO)) for c in CHAMPS},
        **{e: _triplet(contenu.get(e), e, cible) for e in ECRANS},
    )


def _triplet(brut: Any, nom: str, cible: Path) -> tuple[str, str, str]:
    if brut is None:
        return (TODO, TODO, TODO)
    if not isinstance(brut, dict):
        raise CarteInvalide(
            f"{cible} : `{nom}` doit porter transaction, programme et dynpro")
    inconnues = sorted(set(brut) - {"transaction", "programme", "dynpro"})
    if inconnues:
        raise CarteInvalide(f"{cible} : `{nom}` cle(s) inconnue(s) {inconnues}")

    dynpro = brut.get("dynpro", TODO)
    if not isinstance(dynpro, str):
        # YAML lit `0100` comme de l'OCTAL : la valeur devient 64, et le
        # dynpro est corrompu sans que rien ne leve. La garde d'identite
        # comparerait alors contre un numero d'ecran qui n'existe pas.
        raise CarteInvalide(
            f"{cible} : `{nom}.dynpro` doit etre une CHAINE, entre "
            f"guillemets. Sans eux, YAML lit « 0100 » comme de l'octal et en "
            f"fait 64 — le dynpro est corrompu sans un mot")
    return (str(brut.get("transaction", TODO)), str(brut.get("programme", TODO)),
            dynpro)
