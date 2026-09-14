"""Le poste : ce qu'une etape Python recoit, et rien de plus.

La specification impose une echappatoire — toutes les manipulations SAP ne
sont pas exprimables en sequence declarative, et l'utilisateur doit pouvoir
coder les cas retors. Cette echappatoire ne doit pas devenir une porte de
sortie du modele de securite.

`Poste` porte donc exactement la surface de `Driver`, et rien d'autre. Pas de
`sous_contrat`, pas d'acces au driver brut, pas de compteur a remettre a zero.
Une etape Python peut coder n'importe quelle mecanique bizarre — sans jamais
sortir des gardes.

Les dix-huit methodes sont ecrites une par une plutot que generees. Sur une
facade dont le role est de borner ce qui est accessible, on doit pouvoir lire
la liste, pas la deduire.

Elle doit rester EXACTEMENT aussi large que la couture, et un test l'epingle.
Plus large, elle rendrait le mecanisme des gardes accessible ; plus etroite,
elle rendrait une manipulation legitime inexprimable — et quelqu'un irait
appeler COM ailleurs, ce que toute l'architecture existe pour empecher. C'est
ce test qui a rattrape l'oubli des trois methodes ALV en ecriture.
"""

from __future__ import annotations

from falcon.noyau import Ecran, Fenetre, Identite, Statut

from .gardes import DriverGarde


class Poste:
    """Facade etroite sur un driver garde."""

    def __init__(self, garde: DriverGarde):
        self.__garde = garde

    # -- identite et releve ---------------------------------------------

    def screen(self) -> Identite:
        return self.__garde.screen()

    def fields(self, fenetre: str = "wnd[0]") -> Ecran:
        return self.__garde.fields(fenetre)

    def windows(self) -> tuple[Fenetre, ...]:
        return self.__garde.windows()

    def status(self) -> Statut:
        return self.__garde.status()

    # -- lecture et saisie -----------------------------------------------

    def read(self, id: str) -> str:
        return self.__garde.read(id)

    def write(self, id: str, valeur: str) -> None:
        self.__garde.write(id, valeur)

    def set_checked(self, id: str, coche: bool) -> None:
        self.__garde.set_checked(id, coche)

    # -- actions -----------------------------------------------------------

    def press(self, id: str) -> None:
        self.__garde.press(id)

    def select(self, id: str) -> None:
        self.__garde.select(id)

    def vkey(self, n: int, fenetre: str = "wnd[0]") -> None:
        self.__garde.vkey(n, fenetre)

    # -- ALV ----------------------------------------------------------------

    def grid_rows(self, id: str) -> int:
        return self.__garde.grid_rows(id)

    def grid_columns(self, id: str) -> tuple[str, ...]:
        return self.__garde.grid_columns(id)

    def grid_read(self, id: str, ligne: int, colonne: str) -> str:
        return self.__garde.grid_read(id, ligne, colonne)

    def grid_select_rows(self, id: str, rangs: tuple[int, ...]) -> None:
        self.__garde.grid_select_rows(id, rangs)

    def grid_set_current_row(self, id: str, ligne: int) -> None:
        self.__garde.grid_set_current_row(id, ligne)

    def grid_double_click(self, id: str) -> None:
        self.__garde.grid_double_click(id)

    # -- table control -------------------------------------------------------

    def table_visible_rows(self, id: str) -> int:
        return self.__garde.table_visible_rows(id)

    def table_scroll(self, id: str, position: int) -> None:
        self.__garde.table_scroll(id, position)
