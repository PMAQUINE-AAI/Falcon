"""Vue en LECTURE SEULE d'un driver.

Le premier contact avec un systeme reel se fait par un diagnostic, et un
diagnostic ne doit pas pouvoir ecrire. Le faire respecter par une consigne —
« n'appelle pas `write` ici » — serait tenir jusqu'a la premiere fois ou ce
serait commode.

`DriverLecture` n'est donc PAS un `Driver`. C'est une facade qui expose les
quatre methodes d'observation, et aucune autre : `write`, `press`, `vkey`, le
double-clic ALV n'existent tout simplement pas sur l'objet. Une commande qui
n'a que ca en main ne peut pas ecrire — pas « ne doit pas » : ne peut pas, et
l'erreur serait un `AttributeError` a la lecture du code, pas un incident en
production.

C'est la meme idee que `Poste`, prise dans l'autre sens : `Poste` borne ce
qu'une etape Python peut faire en gardant toute la surface ; `DriverLecture`
borne en la retirant.
"""

from __future__ import annotations

from falcon.noyau import Ecran, Fenetre, Identite, Statut

from .interface import Driver

#: Les quatre methodes d'observation de la couture. Aucune ne mute l'ecran.
OBSERVATION = ("screen", "fields", "windows", "status")


class DriverLecture:
    """Facade d'observation. Le driver sous-jacent est sous nom mangle."""

    def __init__(self, driver: Driver):
        self.__driver = driver

    def screen(self) -> Identite:
        return self.__driver.screen()

    def fields(self, fenetre: str = "wnd[0]") -> Ecran:
        return self.__driver.fields(fenetre)

    def windows(self) -> tuple[Fenetre, ...]:
        return self.__driver.windows()

    def status(self) -> Statut:
        return self.__driver.status()
