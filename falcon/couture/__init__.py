"""Couture de driver : le seul endroit de FALCON qui connait SAP.

Rien d'autre n'importe win32com — la regle est verifiee par
tests/test_frontieres.py, parce qu'une frontiere que rien ne verifie tient
jusqu'au premier import presse.

Trois benefices, dont un seul concerne les tests : les gardes s'implementent
ici une fois pour toutes au lieu d'etre recopiees et oubliees ; les erreurs
COM se traitent au meme endroit ; et le harness de rejeu devient une seconde
implementation de cette meme interface, sans rien changer au reste.
"""

from .interface import Driver
from .lecture import OBSERVATION, DriverLecture

__all__ = ["Driver", "DriverLecture", "OBSERVATION"]
