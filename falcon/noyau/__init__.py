"""Noyau : types et erreurs partages. N'importe rien d'autre de FALCON."""

from .erreurs import (
    ErreurFalcon, Echec, ErreurCouture, ObjetIntrouvable, SessionPerdue,
    DelaiDepasse, Refus, RefusDryRun, ArretBloquant, EcartIdentite,
    FenetreImprevue, PlafondAtteint,
)
from .types import Champ, Ecran, Fenetre, Identite, Statut, empreinte

__all__ = [
    "ErreurFalcon", "Echec", "ErreurCouture", "ObjetIntrouvable",
    "SessionPerdue", "DelaiDepasse", "Refus", "RefusDryRun", "ArretBloquant",
    "EcartIdentite", "FenetreImprevue", "PlafondAtteint",
    "Champ", "Ecran", "Fenetre", "Identite", "Statut", "empreinte",
]
