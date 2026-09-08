"""Schema du journal : un type d'enregistrement par evenement.

Le journal est en JSONL append-only. Trois raisons, dans l'ordre
d'importance :

1. **La reprise en depend.** Un fichier ou l'on n'ajoute jamais qu'a la fin
   survit a une coupure : la seule ligne perdue est celle qu'on etait en
   train d'ecrire. Un format qui reecrit en place peut perdre le passe.
2. **Il est relisible sans outil.** `grep`, `tail`, un editeur — quand une
   execution de trois heures s'est mal passee, l'ouvrir ne doit pas demander
   de charger un programme.
3. **Le dernier fait foi.** Aucune mise a jour n'est necessaire : on ajoute
   un nouvel etat, et le repli retient le dernier.

Chaque ligne porte `v`, `type`, `horodatage`, `run_id`. Le champ `type`
discrimine ; il n'y a pas d'enregistrement generique.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, ClassVar

from falcon.noyau import JournalCorrompu

VERSION = 1

# --- etats d'un item -------------------------------------------------
EN_COURS = "en_cours"
OK = "ok"
KO = "ko"
IGNORE = "ignore"
DOUTEUX = "douteux"

#: Etats sur lesquels la reprise ne revient pas.
#:
#: `douteux` y figure alors qu'il signale un doute, et c'est delibere : un
#: item interrompu APRES sa sauvegarde ne doit surtout pas etre rejoue — ce
#: serait la double ecriture. Il sort a l'arbitrage humain, pas dans le flux.
TERMINAUX = frozenset({OK, KO, IGNORE, DOUTEUX})

TYPES: dict[str, type["Enregistrement"]] = {}


def _enregistre(classe: type["Enregistrement"]) -> type["Enregistrement"]:
    TYPES[classe.TYPE] = classe
    return classe


@dataclass(frozen=True, kw_only=True)
class Enregistrement:
    """Champs communs a toute ligne du journal."""

    TYPE: ClassVar[str] = ""

    run_id: str
    horodatage: str = ""        # pose par l'ecrivain s'il est vide
    v: int = VERSION

    def vers_dict(self) -> dict[str, Any]:
        tout = asdict(self)
        entete = {
            "v": tout.pop("v"),
            "type": self.TYPE,
            "horodatage": tout.pop("horodatage"),
            "run_id": tout.pop("run_id"),
        }
        return {**entete, **tout}

    def date(self, horodatage: str) -> "Enregistrement":
        return replace(self, horodatage=horodatage)


def depuis_dict(donnees: dict[str, Any]) -> Enregistrement:
    """Reconstruit un enregistrement, en refusant tout ce qui n'est pas prevu.

    Strict a dessein : une cle inconnue ou une version inattendue signale un
    journal ecrit par une autre version de FALCON. Reprendre dessus en
    ignorant ce qu'on ne comprend pas, c'est reprendre sur un modele faux.
    """
    copie = dict(donnees)
    version = copie.pop("v", None)
    if version != VERSION:
        raise JournalCorrompu(
            f"version de schema {version!r}, attendu {VERSION}")

    nom = copie.pop("type", None)
    classe = TYPES.get(nom)
    if classe is None:
        raise JournalCorrompu(f"type d'enregistrement inconnu : {nom!r}")

    try:
        return classe(**copie)
    except TypeError as erreur:
        raise JournalCorrompu(f"{nom} : {erreur}") from erreur


# =====================================================================
# Execution
# =====================================================================

@_enregistre
@dataclass(frozen=True, kw_only=True)
class ExecutionDebut(Enregistrement):
    """Ouverture. Porte la provenance, et les empreintes que la reprise compare."""

    TYPE: ClassVar[str] = "execution_debut"

    mode: str                       # run | dry-run | resume
    classe: str                     # iterative | volumique
    pipeline: str
    pipeline_empreinte: str
    jeu: str = ""
    jeu_empreinte: str = ""
    systeme: str = ""
    mandant: str = ""
    utilisateur: str = ""
    plafond_items: int | None = None
    derogations: list[dict[str, Any]] = field(default_factory=list)
    falcon_version: str = ""

    #: Motif du contournement de la garde de repetition a blanc, s'il y en a eu.
    #:
    #: Un contournement qui ne laisse pas de trace n'est pas un contournement,
    #: c'est un trou. Il vit dans l'ouverture, a cote des derogations, parce
    #: que c'est la que le journal dit sous quelles conditions le lot est
    #: parti — et que ces conditions sont ce qu'on relit quand une correction
    #: de masse est contestee.
    repetition_forcee: str = ""

    #: Motif du contournement de la garde de REPRISE (`garde_du_monde`).
    #:
    #: `preparer` promettait « un motif, qui sera trace » — et ne l'ecrivait
    #: nulle part. Il etait exige puis jete, et `executer` n'exposait meme pas
    #: le parametre : la porte de sortie decrite par deux docstrings
    #: n'existait dans aucune commande. Une reprise refusee etait une impasse.
    reprise_forcee: str = ""


@_enregistre
@dataclass(frozen=True, kw_only=True)
class ExecutionFin(Enregistrement):
    TYPE: ClassVar[str] = "execution_fin"

    etat: str                       # termine | interrompu | plafond
    raison: str = ""
    compteurs: dict[str, int] = field(default_factory=dict)
    duree_ms: int = 0


# =====================================================================
# Item — pipelines iteratives uniquement
# =====================================================================

@_enregistre
@dataclass(frozen=True, kw_only=True)
class ItemDebut(Enregistrement):
    """Ouverture d'un item.

    `brut` porte la ou les lignes d'entree telles quelles. C'est ce qui rend
    le reexport des KO au format d'entree fidele : on ne reconstruit rien,
    on reprojette ce qu'on a lu.
    """

    TYPE: ClassVar[str] = "item_debut"

    item_id: str
    index: int = 0
    cle: dict[str, Any] = field(default_factory=dict)
    brut: list[dict[str, Any]] = field(default_factory=list)


@_enregistre
@dataclass(frozen=True, kw_only=True)
class ItemFin(Enregistrement):
    TYPE: ClassVar[str] = "item_fin"

    item_id: str
    etat: str                       # ok | ko | ignore
    duree_ms: int = 0
    sauvegardes: int = 0
    incident: str | None = None


# =====================================================================
# Deroulement
# =====================================================================

@_enregistre
@dataclass(frozen=True, kw_only=True)
class Etape(Enregistrement):
    """Une action effectuee.

    `sauvegarde` n'est pas decoratif : c'est lui qui permet, apres une
    interruption, de distinguer un item qu'on peut rejouer d'un item que SAP
    a peut-etre deja enregistre.
    """

    TYPE: ClassVar[str] = "etape"

    etape: str
    rang: int = 0
    action: str = ""                # read | write | press | vkey | select...
    cible: str = ""
    valeur: str | None = None
    duree_ms: int = 0
    sauvegarde: bool = False
    item_id: str | None = None
    ecran: dict[str, Any] = field(default_factory=dict)
    statut: dict[str, Any] | None = None
    relecture: dict[str, Any] | None = None


@_enregistre
@dataclass(frozen=True, kw_only=True)
class Garde(Enregistrement):
    """Emis uniquement sur violation ou derogation appliquee.

    Journaliser chaque garde satisfaite noierait le fichier : elles se
    declenchent a chaque action. On ne trace que ce qui sort de l'ordinaire.
    """

    TYPE: ClassVar[str] = "garde"

    garde: str                      # identite | statut | fenetre | relecture | rayon
    verdict: str                    # violation | derogee
    item_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    derogation: dict[str, Any] | None = None


@_enregistre
@dataclass(frozen=True, kw_only=True)
class Incident(Enregistrement):
    """Un evenement classe par la taxonomie — ou justement pas classe.

    `entree` vaut None quand la categorie est `inconnue` : rien ne
    correspondait au registre, et c'est bloquant par defaut.
    """

    TYPE: ClassVar[str] = "incident"

    categorie: str                  # connue_benigne | connue_fautive | inconnue
    signature: dict[str, Any] = field(default_factory=dict)
    bloquant: bool = True
    item_id: str | None = None
    entree: str | None = None
    dump: str | None = None
