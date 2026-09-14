"""Noyau : types et erreurs partages. N'importe rien d'autre de FALCON."""

from .erreurs import (
    ErreurFalcon, Echec, ErreurCouture, ObjetIntrouvable, SessionPerdue,
    DelaiDepasse, JournalCorrompu, IncidentBloquant, ItemAbandonne, Refus,
    SapIndisponible,
    RefusDryRun, ArretBloquant,
    EcartIdentite, FenetreImprevue, PlafondAtteint, RepriseIncoherente,
)
from .horloge import Horloge, horloge_figee, maintenant
from .types import (
    FENETRE_PRINCIPALE, Champ, Ecran, Fenetre, Identite, Statut, empreinte,
    fenetre_de,
)
from .vocabulaire import (
    CHAMP_DE_COMMANDE, COMPARAISONS, DEROGEABLES, FENETRE, GARDES, IDENTITE,
    MOTIF_MINIMAL, PORTEE_TOTALE, RAYON, RELECTURE, RETOUR_ACCUEIL,
    SAUVEGARDE_IMMINENTE, STATUT, SUFFIXE_CHAMP_DE_COMMANDE, VERDICTS,
)

__all__ = [
    "ErreurFalcon", "Echec", "ErreurCouture", "ObjetIntrouvable",
    "SessionPerdue", "SapIndisponible", "DelaiDepasse", "JournalCorrompu",
    "Refus",
    "RefusDryRun", "ArretBloquant", "EcartIdentite", "FenetreImprevue",
    "IncidentBloquant", "ItemAbandonne",
    "PlafondAtteint", "RepriseIncoherente",
    "Champ", "Ecran", "Fenetre", "Identite", "Statut", "empreinte",
    "fenetre_de", "FENETRE_PRINCIPALE",
    "Horloge", "horloge_figee", "maintenant",
    "GARDES", "IDENTITE", "STATUT", "FENETRE", "RELECTURE", "RAYON",
    "DEROGEABLES", "MOTIF_MINIMAL", "PORTEE_TOTALE", "COMPARAISONS",
    "CHAMP_DE_COMMANDE", "SUFFIXE_CHAMP_DE_COMMANDE", "RETOUR_ACCUEIL",
    "VERDICTS", "SAUVEGARDE_IMMINENTE",
]
