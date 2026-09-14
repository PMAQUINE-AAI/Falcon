"""Export de table : un fichier, sa provenance, et le refus d'en produire un muet.

**La provenance est obligatoire, et refusee a l'ecriture si elle est
incomplete.** Le §3.6 en fait le contrat minimal vis-a-vis du programme
d'analyse tiers : sans systeme, mandant, table, criteres, horodatage et
utilisateur, le rapprochement inter-systeme du cas 3 devient invérifiable — on
ne sait plus ce qu'on compare a quoi. Un export dont on ignore l'origine est
pire qu'un export absent : il a l'air exploitable.

**Un seul fichier, et la provenance dedans.** Une provenance en fichier
separe finit separee : copiee sans son voisin, versionnee a part, perdue. La
premiere ligne du JSONL porte donc la provenance, les suivantes les donnees.

Toutes les clefs de cette premiere ligne portent le prefixe `falcon_`, celui
que `falcon.donnees` retire a la lecture. Un export passe par megarde au
lecteur de jeux de donnees y rend donc une ligne VIDE, que le regroupement
refuse aussitot faute de colonne de clef — plutot qu'une ligne de donnees
fantome qui se serait glissee dans un lot.

**Conservation.** Un dossier par systeme, un fichier horodate par execution.
C'est ce que la comparaison au dernier export (§3.6) suppose, et le §8 ne
l'avait pas fixe : c'est fixe ici.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

#: Prefixe des clefs de la ligne de provenance. Le meme que celui des colonnes
#: de diagnostic, et pour la meme raison : `falcon.donnees` le retire.
PREFIXE = "falcon_"

#: Champs de provenance qui doivent etre renseignes (§3.6).
#:
#: `criteres` n'y est pas : un export sans critere est un export de table
#: complete, ce qui est une information et non une omission. Sa PRESENCE est
#: obligatoire, sa valeur peut etre vide.
OBLIGATOIRES = ("systeme", "mandant", "table", "horodatage", "utilisateur")

VERSION = 1

_INTERDITS = re.compile(r"[^A-Za-z0-9_.-]")


class ExportInvalide(Exception):
    """L'export ne peut pas etre ecrit, ou ne peut pas etre relu."""


@dataclass(frozen=True)
class Provenance:
    """De quoi savoir, six mois plus tard, ce qu'on est en train de comparer."""

    systeme: str
    mandant: str
    table: str
    horodatage: str
    utilisateur: str
    criteres: dict[str, str] = field(default_factory=dict)
    version: int = VERSION
    falcon: str = ""                     # version de FALCON, si connue

    def verifier(self) -> None:
        manquants = [c for c in OBLIGATOIRES if not str(getattr(self, c)).strip()]
        if manquants:
            raise ExportInvalide(
                f"provenance incomplete, manque {manquants}. Sans elle, le "
                f"rapprochement inter-systeme devient invérifiable : on ne "
                f"sait plus ce qu'on compare a quoi (§3.6)")

    def vers_ligne(self) -> dict[str, Any]:
        return {f"{PREFIXE}{cle}": valeur for cle, valeur in asdict(self).items()}

    @classmethod
    def depuis_ligne(cls, brute: dict[str, Any]) -> "Provenance":
        connus = {c.replace(PREFIXE, "", 1): v for c, v in brute.items()
                  if c.startswith(PREFIXE)}
        inconnus = sorted(set(connus) - set(cls.__dataclass_fields__))
        if inconnus:
            raise ExportInvalide(f"provenance : champ(s) inconnu(s) {inconnus}")
        return cls(**connus)               # type: ignore[arg-type]


@dataclass(frozen=True)
class Export:
    """Un export relu : sa provenance, ses lignes, son chemin."""

    provenance: Provenance
    lignes: tuple[dict[str, Any], ...] = ()
    chemin: str = ""

    def __len__(self) -> int:
        return len(self.lignes)


# ---------------------------------------------------------------------------
# Ecriture et lecture
# ---------------------------------------------------------------------------

def ecrire_export(chemin: str | Path, provenance: Provenance,
                  lignes: Iterable[dict[str, Any]]) -> Path:
    """Ecrit un export. Refuse une provenance incomplete AVANT d'ecrire."""
    provenance.verifier()
    cible = Path(chemin)
    cible.parent.mkdir(parents=True, exist_ok=True)

    with cible.open("w", encoding="utf-8", newline="\n") as fichier:
        fichier.write(json.dumps(provenance.vers_ligne(), ensure_ascii=False,
                                 sort_keys=True) + "\n")
        for ligne in lignes:
            if any(str(c).startswith(PREFIXE) for c in ligne):
                raise ExportInvalide(
                    f"une ligne de donnees porte une colonne prefixee "
                    f"{PREFIXE!r}, reservee a la provenance : elle serait "
                    f"retiree a la relecture, en silence")
            fichier.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    return cible


def lire_export(chemin: str | Path) -> Export:
    """Relit un export. Refuse un fichier sans provenance en tete."""
    cible = Path(chemin)
    if not cible.exists():
        raise ExportInvalide(f"export introuvable : {cible}")

    lignes = cible.read_text(encoding="utf-8").splitlines()
    if not lignes:
        raise ExportInvalide(f"{cible} : fichier vide, pas meme une provenance")

    try:
        entete = json.loads(lignes[0])
    except json.JSONDecodeError as erreur:
        raise ExportInvalide(f"{cible} : premiere ligne illisible "
                             f"({erreur})") from erreur
    if not isinstance(entete, dict) or not any(
            c.startswith(PREFIXE) for c in entete):
        raise ExportInvalide(
            f"{cible} : la premiere ligne n'est pas une provenance. Un export "
            f"dont on ignore l'origine est pire qu'un export absent — il a "
            f"l'air exploitable")

    provenance = Provenance.depuis_ligne(entete)
    provenance.verifier()

    donnees: list[dict[str, Any]] = []
    for rang, brute in enumerate(lignes[1:], start=2):
        if not brute.strip():
            continue
        try:
            donnees.append(json.loads(brute))
        except json.JSONDecodeError as erreur:
            raise ExportInvalide(f"{cible}, ligne {rang} : {erreur}") from erreur
    return Export(provenance=provenance, lignes=tuple(donnees),
                  chemin=str(cible))


# ---------------------------------------------------------------------------
# Conservation
# ---------------------------------------------------------------------------

def nom_de_fichier(table: str, horodatage: str) -> str:
    """`MARA_2026-09-06T101500.000Z.jsonl` — triable comme du texte.

    Les deux-points sautent : ils sont interdits dans un nom de fichier
    Windows, et la cible de ce projet est Windows. Les tirets restent, parce
    qu'un horodatage ISO a champs de largeur fixe se trie correctement comme
    une chaine — c'est ce sur quoi `exports` s'appuie.

    Une seule normalisation, ici. Il y en avait deux, dont une jamais
    appelee : elles auraient fini par diverger, et le tri par nom avec elles.
    """
    return (f"{_INTERDITS.sub('_', table)}_"
            f"{_INTERDITS.sub('', horodatage)}.jsonl")


def chemin_d_export(racine: str | Path, systeme: str, table: str,
                    horodatage: str) -> Path:
    """Un dossier par systeme, un fichier horodate par execution.

    Le decoupage par systeme n'est pas cosmetique : la comparaison
    inter-systeme du cas 3 rapproche des exports de systemes differents, et les
    melanger dans un dossier unique rendrait le rapprochement dependant d'un
    nom de fichier bien lu.
    """
    return Path(racine) / _INTERDITS.sub("_", systeme) / nom_de_fichier(
        table, horodatage)


def exports(racine: str | Path, systeme: str, table: str) -> list[Path]:
    """Les exports connus pour ce couple, du plus ancien au plus recent.

    Tri sur le NOM, pas sur la date du fichier : une copie ou une restauration
    change la seconde, pas la premiere, et l'horodatage est dans le nom
    justement pour ca.
    """
    dossier = Path(racine) / _INTERDITS.sub("_", systeme)
    if not dossier.is_dir():
        return []
    prefixe = f"{_INTERDITS.sub('_', table)}_"
    return sorted(c for c in dossier.glob("*.jsonl") if c.name.startswith(prefixe))


def dernier_export(racine: str | Path, systeme: str, table: str) -> Path | None:
    connus = exports(racine, systeme, table)
    return connus[-1] if connus else None


def enregistrer(racine: str | Path, provenance: Provenance,
                lignes: Sequence[dict[str, Any]]) -> Path:
    """Ecrit un export a sa place dans l'arborescence de conservation."""
    provenance.verifier()
    return ecrire_export(
        chemin_d_export(racine, provenance.systeme, provenance.table,
                        provenance.horodatage),
        provenance, lignes)
