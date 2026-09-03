"""Journal d'execution : trace, reprise, metriques.

JSONL append-only. N'importe que `falcon.noyau` : le journal ne sait rien de
SAP, rien des pipelines, rien du moteur. Il enregistre ce qu'on lui donne et
sait replier ce qu'il a enregistre.
"""

from .ecrivain import Ecrivain
from .enregistrement import (
    DOUTEUX, EN_COURS, IGNORE, KO, OK, TERMINAUX, VERSION, Enregistrement,
    Etape, ExecutionDebut, ExecutionFin, Garde, Incident, ItemDebut, ItemFin,
    depuis_dict,
)
from .lecteur import EtatItem, Reprise, etats, lire, preparer

__all__ = [
    "Ecrivain",
    "Enregistrement", "ExecutionDebut", "ExecutionFin", "ItemDebut",
    "ItemFin", "Etape", "Garde", "Incident", "depuis_dict",
    "VERSION", "EN_COURS", "OK", "KO", "IGNORE", "DOUTEUX", "TERMINAUX",
    "lire", "etats", "preparer", "EtatItem", "Reprise",
]
