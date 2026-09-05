"""Noyau : types et erreurs partages. N'importe rien d'autre de FALCON."""

from .erreurs import (
    ErreurFalcon, Echec, ErreurCouture, ObjetIntrouvable, SessionPerdue,
    DelaiDepasse, JournalCorrompu, IncidentBloquant, ItemAbandonne, Refus,
    SapIndisponible,
    RefusDryRun, ArretBloquant,
    EcartIdentite, FenetreImprevue, PlafondAtteint, RepriseIncoherente,
)
from .horloge import Horloge, horloge_figee, maintenant
from .types import Champ, Ecran, Fenetre, Identite, Statut, empreinte
from .vocabulaire import (
    COMPARAISONS, DEROGEABLES, FENETRE, GARDES, IDENTITE, MOTIF_MINIMAL,
    PORTEE_TOTALE, RAYON, RELECTURE, STATUT,
)

__all__ = [
    "ErreurFalcon", "Echec", "ErreurCouture", "ObjetIntrouvable",
    "SessionPerdue", "SapIndisponible", "DelaiDepasse", "JournalCorrompu",
    "Refus",
    "RefusDryRun", "ArretBloquant", "EcartIdentite", "FenetreImprevue",
    "IncidentBloquant", "ItemAbandonne",
    "PlafondAtteint", "RepriseIncoherente",
    "Champ", "Ecran", "Fenetre", "Identite", "Statut", "empreinte",
    "Horloge", "horloge_figee", "maintenant",
    "GARDES", "IDENTITE", "STATUT", "FENETRE", "RELECTURE", "RAYON",
    "DEROGEABLES", "MOTIF_MINIMAL", "PORTEE_TOTALE", "COMPARAISONS",
]
