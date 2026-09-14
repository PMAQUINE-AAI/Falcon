"""Pipelines volumiques : une navigation, un export (§3.5, §3.6).

Ne pas confondre avec l'iteratif. Une volumique ne porte ni journal par item,
ni reprise fine, ni ETA : la machinerie lourde ne sert qu'aux remediations.
Une volumique qui en heriterait serait du gaspillage — et surtout une
confusion de modele.

La provenance d'un export est obligatoire et refusee incomplete : c'est le
contrat minimal vis-a-vis du programme d'analyse tiers.
"""

from .carte import (
    CHAMPS, CHEMIN_CARTE_DEFAUT, ECRANS, TODO, Carte, CarteIncomplete,
    CarteInvalide, charger_carte,
)
from .delta import Delta, DeltaImpossible, Modification, delta, rendre
from .se16n import PLAFOND_SAUVEGARDES, TRANSACTION, exporter_table
from .export import (
    OBLIGATOIRES, PREFIXE, VERSION, Export, ExportInvalide, Provenance,
    chemin_d_export, dernier_export, ecrire_export, enregistrer, exports,
    lire_export, nom_de_fichier,
)

__all__ = [
    "Provenance", "Export", "ExportInvalide",
    "ecrire_export", "lire_export", "enregistrer",
    "chemin_d_export", "exports", "dernier_export", "nom_de_fichier",
    "OBLIGATOIRES", "PREFIXE", "VERSION",
    "delta", "Delta", "Modification", "DeltaImpossible", "rendre",
    "Carte", "charger_carte", "CarteIncomplete", "CarteInvalide",
    "CHEMIN_CARTE_DEFAUT", "CHAMPS", "ECRANS", "TODO",
    "exporter_table", "TRANSACTION", "PLAFOND_SAUVEGARDES",
]
