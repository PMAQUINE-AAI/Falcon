"""Double de driver pour les tests. **N'etablit aucune fidelite.**

Ce n'est PAS le harness de rejeu. Le harness rejoue un catalogue capture sur
un vrai systeme ; ce double sert des reponses ecrites a la main. Son unique
role est de permettre a une garde de se declencher : les tests qui l'utilisent
verifient le comportement de FALCON ETANT DONNE une reponse de driver, jamais
que SAP se comporterait ainsi.

Cette distinction n'est pas rhetorique. Un mock nourri d'hypotheses confirme
les hypotheses ; le confondre avec une source de verite, c'est se donner une
couverture imaginaire sur la partie du systeme qu'on comprend le moins.
"""

from __future__ import annotations

from typing import Callable

from falcon.noyau import Champ, Ecran, Fenetre, Identite, ObjetIntrouvable, Statut

from .interface import Driver


class DriverScripte(Driver):
    """Driver dont l'etat est pose directement par le test.

    Les attributs publics sont faits pour etre modifies en cours de scenario :
    changer `identite` simule une navigation, changer `statut` simule ce que
    SAP a repondu, ajouter a `fenetres` simule une modale surgissante.
    """

    def __init__(self,
                 identite: Identite | None = None,
                 valeurs: dict[str, str] | None = None,
                 statut: Statut | None = None,
                 fenetres: tuple[Fenetre, ...] = (),
                 champs: tuple[Champ, ...] = ()):
        self.identite = identite or Identite()
        self.valeurs = dict(valeurs or {})
        self.statut = statut or Statut()
        self.fenetres = fenetres or (Fenetre(id="wnd[0]", type="GuiMainWindow"),)
        self.champs = champs

        #: Journal des gestes reellement effectues sur le driver brut.
        self.gestes: list[tuple[str, str, str]] = []

        #: Transforme une valeur a l'ecriture — pour simuler ce que SAP fait
        #: subir aux saisies : troncature a la longueur du champ, passage en
        #: majuscules, ou refus pur et simple.
        self.a_l_ecriture: Callable[[str, str], str] | None = None

        #: Appele apres chaque action : le test y change l'etat du monde.
        self.apres_action: Callable[["DriverScripte", str, str], None] | None = None

        #: Grilles et tables, par identifiant de controle.
        self.grilles: dict[str, list[dict[str, str]]] = {}
        self.tables: dict[str, dict[str, int]] = {}

    # -- identite et releve ---------------------------------------------

    def screen(self) -> Identite:
        return self.identite

    def fields(self, fenetre: str = "wnd[0]") -> Ecran:
        return Ecran(identite=self.identite, fenetre=fenetre, champs=self.champs)

    def windows(self) -> tuple[Fenetre, ...]:
        return tuple(self.fenetres)

    def status(self) -> Statut:
        return self.statut

    # -- lecture et saisie -----------------------------------------------

    def read(self, id: str) -> str:
        if id not in self.valeurs:
            raise ObjetIntrouvable(id)
        return self.valeurs[id]

    def write(self, id: str, valeur: str) -> None:
        retenue = self.a_l_ecriture(id, valeur) if self.a_l_ecriture else valeur
        self.valeurs[id] = retenue
        self._noter("write", id, valeur)

    def set_checked(self, id: str, coche: bool) -> None:
        self.valeurs[id] = "X" if coche else ""
        self._noter("set_checked", id, str(coche))

    # -- actions ----------------------------------------------------------

    def press(self, id: str) -> None:
        self._noter("press", id, "")

    def select(self, id: str) -> None:
        self._noter("select", id, "")

    def vkey(self, n: int, fenetre: str = "wnd[0]") -> None:
        self._noter("vkey", fenetre, str(n))

    # -- ALV ---------------------------------------------------------------

    def grid_rows(self, id: str) -> int:
        return len(self.grilles.get(id, []))

    def grid_columns(self, id: str) -> tuple[str, ...]:
        lignes = self.grilles.get(id, [])
        return tuple(lignes[0]) if lignes else ()

    def grid_read(self, id: str, ligne: int, colonne: str) -> str:
        lignes = self.grilles.get(id, [])
        if ligne >= len(lignes):
            raise ObjetIntrouvable(f"{id}[{ligne}]")
        return lignes[ligne].get(colonne, "")

    # -- table control -----------------------------------------------------

    def table_visible_rows(self, id: str) -> int:
        return self.tables.get(id, {}).get("visibles", 0)

    def table_scroll(self, id: str, position: int) -> None:
        self.tables.setdefault(id, {})["position"] = position
        self._noter("table_scroll", id, str(position))

    # -- interne ------------------------------------------------------------

    def _noter(self, geste: str, cible: str, valeur: str) -> None:
        self.gestes.append((geste, cible, valeur))
        if self.apres_action:
            self.apres_action(self, geste, cible)
