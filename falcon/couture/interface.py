"""L'interface etroite par laquelle tout FALCON parle a SAP.

Surface volontairement fermee. Toute implementation — la vraie (win32com), le
double de test, le harness de rejeu — doit fournir ces methodes et rien de
plus. C'est ce qui rend le harness ecrivable en quelques centaines de lignes
au lieu d'etre penible.

Pourquoi cette interface deborde les huit methodes de la specification
initiale : ses huit methodes ne suffisaient pas a exprimer la premiere
pipeline livree. L'audit du cas 1 lit une grille ALV, et le corollaire du
piege des cases remanentes impose de positionner explicitement les trois
cases de selection a chaque appel. Elle a ete etendue une seconde fois quand
une trace reelle a montre que le flux « Obtenir variante » ECRIT dans la
grille — `selectedRows`, `currentCellRow`, `doubleClickCurrentCell` — la ou la
couture ne savait que la lire (decision n°14). La couture etant irreversible, l'etendre
apres coup aurait coute la retrofit qu'on cherche a eviter — et, entretemps,
quelqu'un aurait contourne en appelant COM ailleurs.

Les noms restent dans le registre du scripting SAP, en anglais, parce que six
d'entre eux sont fixes par la specification et que les verbes de pipeline
(`set`, `press`, `select`, `read`) le sont aussi. Le reste de FALCON est en
francais.

**Les deux familles de tableau portent des noms distincts a dessein.**
Confondre l'ALV et le table control est un piege documente qui ne leve
aucune exception : l'ALV s'indexe en ABSOLU sans defilement, le table control
en index VISIBLE avec defilement explicite. Un code qui prend l'un pour
l'autre lit des lignes lointaines en croyant repartir du debut.
"""

from __future__ import annotations

import abc

from falcon.noyau import Ecran, Fenetre, Identite, Statut


class Driver(abc.ABC):
    """Contrat que toute implementation de couture doit remplir.

    Les implementations levent les erreurs de `falcon.noyau.erreurs` :
    `ObjetIntrouvable` quand un identifiant ne resout pas, `SessionPerdue`
    quand la session ne repond plus, `DelaiDepasse` a l'expiration.
    """

    # -- identite et releve -------------------------------------------

    @abc.abstractmethod
    def screen(self) -> Identite:
        """Identite de l'ecran courant. Base de la garde d'identite."""

    @abc.abstractmethod
    def fields(self, fenetre: str = "wnd[0]") -> Ecran:
        """Releve complet d'une fenetre, en liste plate ordonnee."""

    @abc.abstractmethod
    def windows(self) -> tuple[Fenetre, ...]:
        """Fenetres ouvertes, `wnd[0]` en tete."""

    @abc.abstractmethod
    def status(self) -> Statut:
        """Barre de statut. `Statut.vide` quand il n'y a pas de message."""

    # -- lecture et saisie ---------------------------------------------

    @abc.abstractmethod
    def read(self, id: str) -> str:
        """Valeur d'un champ."""

    @abc.abstractmethod
    def write(self, id: str, valeur: str) -> None:
        """Saisie. La relecture de controle est du ressort du contrôleur."""

    @abc.abstractmethod
    def set_checked(self, id: str, coche: bool) -> None:
        """Positionne une case a cocher.

        Toujours positionner explicitement, jamais basculer : SAP conserve
        les valeurs d'ecran d'un appel a l'autre, et cocher la bonne case
        sans decocher les autres laisse la selection precedente active.
        """

    # -- actions --------------------------------------------------------

    @abc.abstractmethod
    def press(self, id: str) -> None:
        """Presse un bouton."""

    @abc.abstractmethod
    def select(self, id: str) -> None:
        """Selectionne une entree de menu ou un onglet."""

    @abc.abstractmethod
    def vkey(self, n: int, fenetre: str = "wnd[0]") -> None:
        """Envoie une touche de fonction."""

    # -- ALV : index ABSOLU, aucun defilement ---------------------------

    @abc.abstractmethod
    def grid_rows(self, id: str) -> int:
        """Nombre de lignes de la grille."""

    @abc.abstractmethod
    def grid_columns(self, id: str) -> tuple[str, ...]:
        """Noms techniques des colonnes, dans l'ordre d'affichage."""

    @abc.abstractmethod
    def grid_read(self, id: str, ligne: int, colonne: str) -> str:
        """Valeur d'une cellule, par index ABSOLU. Aucun defilement requis."""

    @abc.abstractmethod
    def grid_select_rows(self, id: str, rangs: tuple[int, ...]) -> None:
        """Selectionne des lignes, par index ABSOLU.

        **Selectionner par index est un piege, pas une commodite.** L'index
        depend du contenu de la base au moment ou on regarde. Une pipeline qui
        fige un index traite la mauvaise ligne des que la liste change, et ne
        leve pas. La regle : lire la grille avec `grid_read` pour retrouver la
        ligne voulue par son contenu, et n'appeler ceci qu'avec l'index ainsi
        obtenu.

        La couture doit neanmoins l'exposer : c'est ce que SAP offre, et le
        traduire ailleurs mettrait de la logique metier dans la couture.
        """

    @abc.abstractmethod
    def grid_set_current_row(self, id: str, ligne: int) -> None:
        """Place la cellule courante sur une ligne, par index ABSOLU.

        **Ce n'est pas la meme chose que selectionner**, et c'est le piege que
        la trace du recorder revele : `grid_double_click` agit sur la cellule
        COURANTE, pas sur la selection. Omettre cet appel double-clique la
        premiere ligne — sans erreur, sur la mauvaise donnee.
        """

    @abc.abstractmethod
    def grid_double_click(self, id: str) -> None:
        """Double-clique la cellule COURANTE. Declenche une navigation.

        Positionner la cellule courante d'abord : voir `grid_set_current_row`.
        """

    # -- table control : index VISIBLE, defilement explicite ------------

    @abc.abstractmethod
    def table_visible_rows(self, id: str) -> int:
        """Hauteur de la fenetre visible.

        Ce n'est PAS le nombre de lignes du tableau : au-dela de cette
        hauteur, une cellule ne resout pas tant qu'on n'a pas defile.
        """

    @abc.abstractmethod
    def table_scroll(self, id: str, position: int) -> None:
        """Place l'origine du defilement sur une ligne ABSOLUE.

        Apres defilement, la ligne visible 0 n'est plus la premiere du
        tableau. Remettre l'origine a zero avant tout balayage.
        """
