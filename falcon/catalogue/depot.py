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
        return self.contenu(chemin)[1]

    def triplets(self) -> Iterator[tuple[str, str, str]]:
        if not self.racine.is_dir():
            return
        for chemin in self.fichiers():
            contenu = self._lire_fichier(chemin)
            yield (contenu.get("transaction", ""), contenu.get("programme", ""),
                   str(contenu.get("dynpro", "")))

    def fichiers(self) -> tuple[Path, ...]:
        """Les fichiers de ce rayon, tries, sans en lire aucun.

        **Non recursif, comme `triplets()`, et c'est le meme glob.** Un
        sous-dossier — `quarantaine/` sous le catalogue cure, `rapports/` a
        cote — n'en fait donc pas partie, et c'est ce qui permet d'ecrire des
        comptes rendus dans le dossier de catalogue sans que le depot les
        prenne pour des ecrans.

        Rendre les CHEMINS plutot que les triplets est ce qui permet a
        `catalogue/inventaire.py` de nommer un fichier illisible : `triplets()`
        leve sur le premier casse et perd tout ce qui suit, sans jamais dire
        lequel.
        """
        if not self.racine.is_dir():
            return ()
        return tuple(sorted(self.racine.glob("*.yaml")))

    def contenu(self, chemin: str | Path) -> tuple[tuple[str, str, str],
                                                   tuple[Variante, ...]]:
        """Le triplet et TOUTES les variantes d'un fichier, lu UNE seule fois.

        `triplets()` puis `variantes(triplet)` lisent le meme fichier deux
        fois : la premiere passe pour en tirer le triplet, la seconde pour
        recomposer son nom a partir de ce triplet et le relire. Sur les dix
        fichiers de la quarantaine de reference, cela fait vingt lectures et
        vingt analyses YAML pour dix fichiers — et le loader embarque dans
        `falcon.pyz` est le pur-Python, jamais l'accelerateur C.

        **Le chemin est celui qu'on a LU, pas celui qu'on recompose.** Un
        fichier dont l'en-tete ne redonne pas son propre nom — renomme a la
        main, recopie d'un autre catalogue — reste lisible ici, alors que
        `variantes(triplet)` chercherait un nom qui n'existe pas et rendrait un
        tuple vide : un catalogue d'aspect normal, ampute sans un mot.
        """
        chemin = Path(chemin)
        contenu = self._lire_fichier(chemin)
        triplet = (contenu.get("transaction", ""),
                   contenu.get("programme", ""),
                   str(contenu.get("dynpro", "")))
        variantes = contenu.get("variantes", {})
        # La FORME est verifiee avant d'etre parcourue, et le refus NOMME le
        # fichier. Sans cela `variantes:` rendu comme une liste YAML sortait en
        # « 'list' object has no attribute 'items' » — une AttributeError nue,
        # qui ne dit pas quel fichier, qu'aucun appelant n'attrape, et qui fait
        # tomber l'inventaire ENTIER pour un fichier sur dix. Ce module existe
        # pour relire des fichiers ecrits ailleurs ; la forme est une donnee,
        # pas un invariant.
        if not isinstance(variantes, dict):
            raise CatalogueInvalide(
                f"{chemin} : « variantes » est un "
                f"{type(variantes).__name__}, un dictionnaire est attendu")
        for marque, brute in variantes.items():
            if not isinstance(brute, dict):
                raise CatalogueInvalide(
                    f"{chemin} : la variante {marque!r} est un "
                    f"{type(brute).__name__}, un dictionnaire est attendu")
            bruts = brute.get("champs", [])
            # `champs: 3` sortait en « 'int' object is not iterable » — une
            # TypeError nue, sans nom de fichier, qui emportait tout le reste.
            if not isinstance(bruts, (list, tuple)):
                raise CatalogueInvalide(
                    f"{chemin} : « champs » de la variante {marque!r} est un "
                    f"{type(bruts).__name__}, une liste est attendue")
            for brut in bruts:
                if not isinstance(brut, dict):
                    raise CatalogueInvalide(
                        f"{chemin} : un champ de la variante {marque!r} est "
                        f"un {type(brut).__name__}, un dictionnaire est "
                        f"attendu")
        return triplet, tuple(
            self._variante(triplet, marque, brute)
            for marque, brute in sorted(variantes.items()))

    # -- interne -----------------------------------------------------------

    @staticmethod
    def _lire_fichier(chemin: Path) -> dict:
        try:
            brut = chemin.read_text(encoding="utf-8")
        except UnicodeDecodeError as erreur:
            # Le cas le plus probable sur la cible, et il n'a rien d'exotique :
            # un YAML rouvert et resauvegarde par le Bloc-notes d'un poste
            # Windows francais sort en cp1252. `UnicodeDecodeError` est un
            # `ValueError`, donc ni `OSError` ni `yaml.YAMLError` ne
            # l'attrapaient, et la console repondait par une trace de pile a la
            # place du catalogue.
            raise CatalogueInvalide(
                f"{chemin} : ce fichier n'est pas de l'UTF-8 "
                f"({erreur.reason}, octet {erreur.object[erreur.start]:#04x} "
                f"en position {erreur.start}). Reenregistre-le en UTF-8") \
                from erreur
        contenu = yaml.safe_load(brut) or {}
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
