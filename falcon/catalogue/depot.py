"""Depot de catalogue : YAML versionne, un fichier par triplet d'ecran.

Format arrete par la decision n°1 — YAML versionne, diffable et relisible.
Un fichier par triplet plutot qu'un gros fichier unique : c'est ce qui rend un
diff lisible quand une variante apparait, et c'est la seule raison du
decoupage.

**Deux acces distincts, et c'est le point du module.** `pour_garde` sert la
garde d'identite et REFUSE une esquisse ; `pour_edition` sert l'humain qui
cartographie et les sert toutes. Sans cette separation, une esquisse
conjecturee depuis une trace finirait par satisfaire une garde d'identite —
c'est-a-dire par certifier un ecran que personne n'a jamais observe.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

import yaml

from falcon.noyau import Champ

from .modele import (
    ESQUISSE, OBSERVEE, CatalogueInvalide, ClefVariante, Variante,
)

VERSION = 1

#: Attributs releves pour chaque objet d'ecran (§3.1).
ATTRIBUTS = ("id", "type", "soustype", "nom", "texte", "modifiable", "infobulle")

_INTERDITS = re.compile(r"[^A-Za-z0-9_.-]")


def _nom_de_fichier(triplet: tuple[str, str, str]) -> str:
    """Nom de fichier lisible et sur, derive du triplet."""
    morceaux = [_INTERDITS.sub("_", partie) or "_" for partie in triplet]
    return "__".join(morceaux) + ".yaml"


class Depot:
    """Acces au catalogue sur disque.

    Les ecrans qu'on n'a pas encore relus vont en quarantaine plutot que dans
    le catalogue cure : un dump d'incident inconnu est une capture utile, mais
    la verser directement polluerait le catalogue d'ecrans d'erreur que
    personne n'a valides.
    """

    def __init__(self, racine: str | Path):
        self.racine = Path(racine)
        self.quarantaine = self.racine / "quarantaine"

    # -- ecriture ---------------------------------------------------------

    def enregistrer(self, variante: Variante) -> Path:
        """Ajoute ou remplace une variante. Rend le fichier ecrit."""
        chemin = self.racine / _nom_de_fichier(variante.clef.triplet)
        chemin.parent.mkdir(parents=True, exist_ok=True)

        contenu = self._lire_fichier(chemin) if chemin.exists() else {
            "version": VERSION,
            "transaction": variante.clef.transaction,
            "programme": variante.clef.programme,
            "dynpro": variante.clef.dynpro,
            "variantes": {},
        }
        contenu["variantes"][variante.clef.empreinte] = {
            "titre": variante.titre,
            "capture_le": variante.capture_le,
            "source": variante.source,
            "champs": [
                {attribut: getattr(champ, attribut) for attribut in ATTRIBUTS}
                for champ in variante.champs
            ],
        }
        chemin.write_text(
            yaml.safe_dump(contenu, allow_unicode=True, sort_keys=True),
            encoding="utf-8")
        return chemin

    def mettre_en_quarantaine(self, variante: Variante) -> Path:
        """Range une capture non relue a l'ecart du catalogue cure."""
        ecarte = Depot(self.quarantaine)
        return ecarte.enregistrer(variante)

    def promouvoir(self, clef: ClefVariante) -> Path:
        """Verse une capture de quarantaine dans le catalogue.

        Geste explicite, et c'est voulu : c'est le moment ou un humain dit
        avoir relu l'ecran.
        """
        ecarte = Depot(self.quarantaine)
        variante = ecarte.pour_edition(clef)
        if variante is None:
            raise CatalogueInvalide(f"{clef} : rien de tel en quarantaine")
        return self.enregistrer(variante)

    # -- lecture ----------------------------------------------------------

    def pour_garde(self, clef: ClefVariante) -> Variante:
        """La variante a opposer a la garde d'identite.

        Refuse une esquisse : une variante conjecturee ne peut pas certifier
        un ecran que personne n'a observe. Refuse aussi l'absence — une garde
        d'identite sans reference n'est pas une garde.
        """
        variante = self.pour_edition(clef)
        if variante is None:
            raise CatalogueInvalide(
                f"{clef} : absente du catalogue. Cartographier l'ecran avant "
                f"de l'opposer a une garde")
        if not variante.observee:
            raise CatalogueInvalide(
                f"{clef} : c'est une esquisse, pas un releve. Une esquisse ne "
                f"peut pas satisfaire une garde d'identite — elle certifierait "
                f"un ecran que personne n'a jamais observe")
        return variante

    def pour_edition(self, clef: ClefVariante) -> Variante | None:
        """Toute variante connue, esquisse comprise. Pour l'humain."""
        for variante in self.variantes(clef.triplet):
            if variante.clef.empreinte == clef.empreinte:
                return variante
        return None

    def variantes(self, triplet: tuple[str, str, str]) -> tuple[Variante, ...]:
        chemin = self.racine / _nom_de_fichier(triplet)
        if not chemin.exists():
            return ()
        contenu = self._lire_fichier(chemin)
        return tuple(
            self._variante(triplet, marque, brute)
            for marque, brute in sorted(contenu.get("variantes", {}).items())
        )

    def triplets(self) -> Iterator[tuple[str, str, str]]:
        if not self.racine.is_dir():
            return
        for chemin in sorted(self.racine.glob("*.yaml")):
            contenu = self._lire_fichier(chemin)
            yield (contenu.get("transaction", ""), contenu.get("programme", ""),
                   str(contenu.get("dynpro", "")))

    # -- interne -----------------------------------------------------------

    @staticmethod
    def _lire_fichier(chemin: Path) -> dict:
        contenu = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
        if not isinstance(contenu, dict):
            raise CatalogueInvalide(f"{chemin} : un dictionnaire est attendu")
        if contenu.get("version") != VERSION:
            raise CatalogueInvalide(
                f"{chemin} : version {contenu.get('version')!r}, "
                f"attendu {VERSION}")
        contenu.setdefault("variantes", {})
        return contenu

    @staticmethod
    def _variante(triplet: tuple[str, str, str], marque: str,
                  brute: dict) -> Variante:
        champs = tuple(
            # `modifiable` absent du fichier veut dire « pas observe », donc
            # `None` — et non `True`, qui aurait reintroduit l'affirmation que
            # le tri-etat de `Champ` retire.
            Champ(**{attribut: brut.get(attribut, "" if attribut != "modifiable"
                                        else None)
                     for attribut in ATTRIBUTS})
            for brut in brute.get("champs", []))
        return Variante(
            clef=ClefVariante(*triplet, empreinte=marque),
            champs=champs,
            titre=brute.get("titre", ""),
            capture_le=brute.get("capture_le", ""),
            source=brute.get("source", OBSERVEE),
        )
