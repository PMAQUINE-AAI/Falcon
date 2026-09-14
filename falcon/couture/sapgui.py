"""Implementation reelle de la couture, par SAP GUI Scripting (COM).

**Le seul module de FALCON autorise a importer `win32com`.** La regle est
verifiee mecaniquement par `tests/test_frontieres.py`, qui epingle ce chemin
de fichier.

**Aucune ligne de ce module n'a jamais parle a un systeme SAP.** Ni la suite
locale ni la CI ne peuvent l'executer : elles tournent sur Linux, sans SAP GUI
et sans pywin32. Ce qui est verifiable ici l'est — le module s'importe, la
classe remplit le contrat des dix-huit methodes, les erreurs se traduisent, le
releve d'ecran se parcourt — et ce qui ne l'est pas est marque `skip` avec un
motif lisible, jamais passe sous silence. La seule validation reelle est de
lancer `python -m falcon diagnostiquer` sur un poste equipe.

**L'import de `win32com` est paresseux, et ce n'est pas une precaution
esthetique.** Un import en tete de module rendrait ce fichier inimportable sur
Linux ; `tests/test_frontieres.py`, qui parcourt tous les modules du paquet, ne
pourrait plus le lire, et la frontiere qu'il garde tomberait avec lui. La regle
d'architecture serait cassee par le module meme qu'elle protege.

Les noms d'attributs COM viennent de la documentation du SAP GUI Scripting API.
Ils ne sont pas devines — mais ils ne sont pas verifies non plus, et la
difference compte : le premier contact reel les corrigera peut-etre, et il faut
que ce soit un diagnostic lisible, pas un plantage opaque. C'est pourquoi les
attributs descriptifs facultatifs sont lus avec un defaut explicite, et les
attributs essentiels sans filet.
"""

from __future__ import annotations

from typing import Any

from falcon.noyau import (
    Champ, Ecran, ErreurCouture, Fenetre, Identite, ObjetIntrouvable,
    SapIndisponible, Statut,
)

from .interface import Driver

#: Le point d'entree du scripting cote client.
OBJET_SAPGUI = "SAPGUI"

#: Barre de statut de la fenetre principale.
BARRE_DE_STATUT = "wnd[0]/sbar"

#: Defauts des attributs facultatifs d'un OBJET D'ECRAN.
#:
#: C'est une reference de valeurs, pas une table de resolution : `_facultatif`
#: prend son defaut en parametre. Une table indexee par nom leverait sur le
#: premier attribut auquel personne n'a pense, transformant un attribut
#: manquant — cas prevu — en plantage de la lecture d'ecran.
#:
#: Ils sont facultatifs parce que la surface d'un `GuiVComponent` varie avec son type :
#: un shell n'a pas de `Changeable`, un conteneur pas de `Tooltip`. Un releve
#: doit noter l'absence, pas s'interrompre dessus — c'est de la cartographie,
#: et une cartographie qui s'arrete a la premiere case vide ne cartographie
#: rien. Les attributs ESSENTIELS (`Id`, `Type`) sont lus sans filet : s'ils
#: manquent, ce n'est pas un objet d'ecran.
FACULTATIFS: dict[str, Any] = {
    "SubType": "", "Name": "", "Text": "", "Changeable": True, "Tooltip": "",
}


def _importer() -> Any:
    """Charge pywin32, ou leve une erreur qui dit quoi faire."""
    try:
        import win32com.client                     # noqa: PLC0415
    except ImportError as erreur:
        raise SapIndisponible(
            f"pywin32 n'est pas installe ({erreur}). FALCON ne parle a SAP que "
            f"depuis Windows, avec `pip install pywin32` et le scripting "
            f"active des deux cotes — client (Options > Accessibilite et "
            f"scripting) et serveur (sapgui/user_scripting)") from erreur
    return win32com.client


def _erreur_com() -> type[BaseException]:
    """Le type d'erreur que leve pywin32. `Exception` a defaut."""
    try:
        import pywintypes                          # noqa: PLC0415
    except ImportError:
        return Exception
    return pywintypes.com_error                    # type: ignore[attr-defined]


def connecter(*, connexion: int = 0, session: int = 0) -> "SapGui":
    """Ouvre une session sur le SAP GUI deja lance.

    N'ouvre PAS de session : FALCON se greffe sur une session que l'humain a
    ouverte et sur laquelle il s'est authentifie lui-meme. Aucun mot de passe
    ne transite par ce code, et c'est deliberé — un framework d'automatisation
    qui detient des identifiants SAP est un probleme de securite avant d'etre
    un outil.
    """
    client = _importer()
    try:
        moteur = client.GetObject(OBJET_SAPGUI).GetScriptingEngine
        brute = moteur.Children(connexion).Children(session)
    except Exception as erreur:                    # com_error, ou son absence
        raise SapIndisponible(
            f"aucune session SAP joignable (connexion {connexion}, session "
            f"{session}) : {erreur}. Verifier qu'un SAP GUI est ouvert, "
            f"connecte, et que le scripting est autorise des deux cotes"
        ) from erreur
    return SapGui(brute)


class SapGui(Driver):
    """La couture reelle. Construite sur une session COM deja obtenue.

    Prendre la session en parametre plutot que de l'ouvrir dans le
    constructeur separe deux choses qui n'ont pas les memes modes d'echec : se
    connecter, et parler. C'est aussi ce qui rend la traduction COM -> FALCON
    exercable sans SAP.
    """

    def __init__(self, session: Any):
        self._session = session
        self._com = _erreur_com()

    # -- resolution et traduction d'erreurs --------------------------------

    def _objet(self, id: str) -> Any:
        try:
            return self._session.findById(id)
        except Exception as erreur:
            if isinstance(erreur, self._com) or self._com is Exception:
                raise ObjetIntrouvable(
                    f"{id} : absent de l'ecran courant ({erreur})") from erreur
            raise

    def _appeler(self, quoi: str, action) -> Any:
        """Execute une action COM et traduit ce qui en sort.

        La traduction s'arrete a `ErreurCouture` : distinguer une session
        perdue d'un delai depasse demande de lire des codes HRESULT que
        personne ici n'a observes. Les inventer donnerait une taxonomie qui a
        l'air complete et qui classe de travers — « la taxonomie se recolte ».
        """
        try:
            return action()
        except Exception as erreur:
            if isinstance(erreur, self._com) or self._com is Exception:
                raise ErreurCouture(f"{quoi} : {erreur}") from erreur
            raise

    @staticmethod
    def _facultatif(objet: Any, nom: str, defaut: Any = "") -> Any:
        """Lit un attribut COM facultatif, ou rend le defaut.

        Le defaut est passe explicitement plutot que cherche dans une table :
        une table indexee par nom leve un `KeyError` sur le premier attribut
        qu'on n'y a pas pense — ce qui transforme un attribut manquant, cas
        prevu, en plantage de la lecture d'ecran. `FACULTATIFS` reste la
        reference des defauts d'un objet d'ecran, mais c'est l'appelant qui
        nomme celui qu'il veut.
        """
        try:
            valeur = getattr(objet, nom)
        except Exception:
            return defaut
        return defaut if valeur is None else valeur

    # -- identite et releve -------------------------------------------------

    def screen(self) -> Identite:
        info = self._appeler("screen", lambda: self._session.Info)
        return Identite(
            systeme=str(self._facultatif(info, "SystemName")),
            mandant=str(self._facultatif(info, "Client")),
            langue=str(self._facultatif(info, "Language")),
            transaction=str(self._facultatif(info, "Transaction")),
            programme=str(self._facultatif(info, "Program")),
            # Le dynpro reste une CHAINE : « 0100 » n'est pas « 100 », et le
            # catalogue doit rester diffable.
            dynpro=str(self._facultatif(info, "ScreenNumber")),
        )

    def fields(self, fenetre: str = "wnd[0]") -> Ecran:
        racine = self._objet(fenetre)
        champs: list[Champ] = []
        self._parcourir(racine, champs)
        return Ecran(identite=self.screen(), fenetre=fenetre,
                     titre=str(self._facultatif(racine, "Text",
                                       FACULTATIFS["Text"])),
                     champs=tuple(champs))

    def _parcourir(self, objet: Any, trouves: list[Champ]) -> None:
        """Descend l'arbre des controles et l'aplatit.

        Aplati parce que les identifiants SONT des chemins : l'arbre se
        reconstruit, l'empreinte du catalogue porte sur un ensemble plat, et la
        resolution par SUFFIXE — imposee par la variabilite des numeros de
        sous-ecran — est triviale sur une liste.
        """
        trouves.append(Champ(
            id=str(objet.Id), type=str(objet.Type),
            soustype=str(self._facultatif(objet, "SubType", FACULTATIFS["SubType"])),
            nom=str(self._facultatif(objet, "Name", FACULTATIFS["Name"])),
            texte=str(self._facultatif(objet, "Text", FACULTATIFS["Text"])),
            modifiable=bool(self._facultatif(objet, "Changeable",
                                             FACULTATIFS["Changeable"])),
            infobulle=str(self._facultatif(objet, "Tooltip", FACULTATIFS["Tooltip"])),
        ))
        enfants = self._facultatif(objet, "Children", None)
        if enfants is None:
            return
        for rang in range(int(getattr(enfants, "Count", 0) or 0)):
            self._parcourir(enfants.ElementAt(rang), trouves)

    def windows(self) -> tuple[Fenetre, ...]:
        enfants = self._appeler("windows", lambda: self._session.Children)
        ouvertes = []
        for rang in range(int(getattr(enfants, "Count", 0) or 0)):
            fenetre = enfants.ElementAt(rang)
            ouvertes.append(Fenetre(
                id=str(fenetre.Id), type=str(fenetre.Type),
                titre=str(self._facultatif(fenetre, "Text")),
                texte=str(self._facultatif(fenetre, "Text"))))
        return tuple(ouvertes)

    def status(self) -> Statut:
        barre = self._objet(BARRE_DE_STATUT)
        return Statut(
            type=str(self._facultatif(barre, "MessageType")),
            id=str(self._facultatif(barre, "MessageId")),
            # Chaine : « 045 » n'est pas 45. La comparaison passe par
            # `meme_numero`, pas par une conversion en entier.
            numero=str(self._facultatif(barre, "MessageNumber")),
            texte=str(self._facultatif(barre, "Text")),
            parametre=str(self._facultatif(barre, "MessageParameter")),
        )

    # -- lecture et saisie ---------------------------------------------------

    def read(self, id: str) -> str:
        objet = self._objet(id)
        return str(self._appeler(f"read({id!r})", lambda: objet.Text))

    def write(self, id: str, valeur: str) -> None:
        objet = self._objet(id)

        def poser() -> None:
            objet.Text = valeur

        self._appeler(f"write({id!r})", poser)

    def set_checked(self, id: str, coche: bool) -> None:
        objet = self._objet(id)

        def poser() -> None:
            objet.Selected = bool(coche)

        self._appeler(f"set_checked({id!r})", poser)

    # -- actions ---------------------------------------------------------------

    def press(self, id: str) -> None:
        objet = self._objet(id)
        self._appeler(f"press({id!r})", objet.press)

    def select(self, id: str) -> None:
        objet = self._objet(id)
        self._appeler(f"select({id!r})", objet.select)

    def vkey(self, n: int, fenetre: str = "wnd[0]") -> None:
        objet = self._objet(fenetre)
        self._appeler(f"vkey({n})", lambda: objet.sendVKey(n))

    # -- ALV : index ABSOLU, aucun defilement ------------------------------------

    def grid_rows(self, id: str) -> int:
        objet = self._objet(id)
        return int(self._appeler(f"grid_rows({id!r})", lambda: objet.RowCount))

    def grid_columns(self, id: str) -> tuple[str, ...]:
        objet = self._objet(id)
        ordre = self._appeler(f"grid_columns({id!r})", lambda: objet.ColumnOrder)
        return tuple(str(ordre.ElementAt(rang))
                     for rang in range(int(getattr(ordre, "Count", 0) or 0)))

    def grid_read(self, id: str, ligne: int, colonne: str) -> str:
        objet = self._objet(id)
        return str(self._appeler(
            f"grid_read({id!r}, {ligne}, {colonne!r})",
            lambda: objet.GetCellValue(ligne, colonne)))

    def grid_select_rows(self, id: str, rangs: tuple[int, ...]) -> None:
        objet = self._objet(id)
        # `selectedRows` est une CHAINE, la ou `currentCellRow` est un entier —
        # relevé sur une trace du recorder, sur le meme objet. Ce n'est pas une
        # incoherence de la trace, c'est le typage de l'API.
        valeur = ",".join(str(rang) for rang in rangs)

        def poser() -> None:
            objet.selectedRows = valeur

        self._appeler(f"grid_select_rows({id!r}, {rangs})", poser)

    def grid_set_current_row(self, id: str, ligne: int) -> None:
        objet = self._objet(id)

        def poser() -> None:
            objet.currentCellRow = int(ligne)

        self._appeler(f"grid_set_current_row({id!r}, {ligne})", poser)

    def grid_double_click(self, id: str) -> None:
        objet = self._objet(id)
        self._appeler(f"grid_double_click({id!r})", objet.doubleClickCurrentCell)

    # -- table control : index VISIBLE, defilement explicite ----------------------

    def table_visible_rows(self, id: str) -> int:
        objet = self._objet(id)
        return int(self._appeler(f"table_visible_rows({id!r})",
                                 lambda: objet.VisibleRowCount))

    def table_scroll(self, id: str, position: int) -> None:
        objet = self._objet(id)

        def poser() -> None:
            objet.VerticalScrollbar.Position = int(position)

        self._appeler(f"table_scroll({id!r}, {position})", poser)
