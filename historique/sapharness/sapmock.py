"""sapmock — simulateur SAP GUI pour tester du scripting hors SAP.

Pourquoi ce module existe
-------------------------
Le developpement d'EagleLoader a produit une dizaine de simulateurs COM
jetables, reecrits a chaque fois. Chacun encodait a la main les mecaniques
pieges de SAP GUI, et chaque oubli laissait passer un bug.

Ce module fige ces mecaniques une bonne fois :

  - table control : index de ligne VISIBLE, defilement explicite ;
  - ALV : index ABSOLU, pas d'ID par cellule ;
  - pile de fenetres modales (wnd[1], wnd[2]...) ;
  - boutons dont le sens change selon l'ecran ;
  - journal d'actions permettant d'asserter des invariants.

Le but n'est pas de simuler SAP fidelement. Il est de rendre AUTOMATIQUEMENT
detectables les erreurs qui, en production, ne produisent aucune exception.

Usage
-----
    monde = Monde()
    monde.ajouter_ecran(Ecran("synthese", programme="SAPLCPDI", dynpro=3400))
    ...
    session = monde.session()
    session.findById("wnd[0]/tbar[1]/btn[34]").press()
    monde.journal.assert_jamais("wnd[0]/tbar[1]/btn[7]", hors_ecran="detail")

Ce fichier est autonome et se teste lui-meme : `python sapmock.py`.
"""

from __future__ import annotations


class ErreurSimulee(Exception):
    """Equivalent d'une exception COM : controle absent ou inutilisable."""


# =====================================================================
# Journal d'actions
# =====================================================================

class Journal:
    """Trace ce que le programme teste a REELLEMENT fait.

    Les invariants les plus utiles ne portent pas sur le resultat mais sur
    les gestes : ne jamais presser tel bouton hors de tel ecran, ne
    sauvegarder qu'une fois par objet, ne pas ecrire en dry-run.
    """

    def __init__(self):
        self.entrees: list[tuple[str, str, str]] = []   # (ecran, action, cible)

    def noter(self, ecran: str, action: str, cible: str) -> None:
        self.entrees.append((ecran, action, cible))

    def actions(self, action: str | None = None) -> list[tuple[str, str, str]]:
        return [e for e in self.entrees if action is None or e[1] == action]

    def compter(self, action: str, cible: str | None = None) -> int:
        return sum(1 for e, a, c in self.entrees
                   if a == action and (cible is None or c == cible))

    def assert_jamais(self, cible: str, hors_ecran: str) -> None:
        """Echoue si `cible` a ete actionnee ailleurs que sur `hors_ecran`.

        C'est l'assertion qui protege des collisions d'indices de boutons :
        btn[7] vaut "operation suivante" sur un ecran et "inserer" sur un
        autre.
        """
        fautes = [e for e in self.entrees
                  if e[2] == cible and e[0] != hors_ecran]
        if fautes:
            raise AssertionError(
                f"{cible} actionne hors de l'ecran {hors_ecran!r} : {fautes}")

    def assert_au_plus(self, action: str, nombre: int) -> None:
        reel = self.compter(action)
        if reel > nombre:
            raise AssertionError(
                f"{action} effectue {reel} fois, maximum attendu {nombre}")

    def resume(self) -> str:
        return " | ".join(f"{a}:{c.split('/')[-1]}" for _, a, c in self.entrees)


# =====================================================================
# Controles
# =====================================================================

class Controle:
    """Controle GUI minimal. `Text` et `Selected` respectent la casse COM."""

    def __init__(self, identifiant, type_="GuiTextField", texte="",
                 selectionne=False, actif=True, action=None, monde=None):
        self.Id = identifiant
        self.Type = type_
        self._texte = texte
        self._selectionne = selectionne
        self.Changeable = actif
        self._action = action
        self._monde = monde

    # -- COM est insensible a la casse : on expose les deux graphies ----
    @property
    def Text(self): return self._texte

    @Text.setter
    def Text(self, valeur):
        self._texte = valeur
        self._tracer("saisie")

    text = Text

    @property
    def Selected(self): return self._selectionne

    @Selected.setter
    def Selected(self, valeur):
        self._selectionne = bool(valeur)
        self._tracer("coche")

    selected = Selected

    def _tracer(self, action):
        if self._monde is not None:
            self._monde.journal.noter(self._monde.ecran_courant, action, self.Id)

    def press(self):
        if not self.Changeable:
            raise ErreurSimulee(f"{self.Id} inactif")
        self._tracer("press")
        if self._action:
            self._action()

    def select(self):
        self._tracer("select")
        if self._action:
            self._action()

    def setFocus(self):
        self._tracer("focus")


class TableControl:
    """Table control : index de ligne VISIBLE, defilement explicite.

    Une cellule s'adresse par `<table>/txtNOM[colonne,ligne_visible]`.
    Demander une ligne au-dela de la fenetre visible leve, exactement
    comme SAP : c'est ce qui force le programme teste a defiler.
    """

    Type = "GuiTableControl"

    def __init__(self, identifiant, colonnes, lignes, visibles=20, monde=None):
        self.Id = identifiant
        self._colonnes = list(colonnes)          # noms techniques, dans l'ordre
        self._lignes = lignes                    # liste de dicts
        self.VisibleRowCount = visibles
        self.RowCount = max(len(lignes), visibles)   # inclut les lignes vides
        self._position = 0
        self._monde = monde

    @property
    def Columns(self):
        return _Collection([Controle(n, "GuiTableColumn") for n in self._colonnes]
                           , noms=self._colonnes)

    @property
    def VerticalScrollbar(self):
        return _Scrollbar(self)

    def cellule(self, colonne, rang_visible):
        if rang_visible >= self.VisibleRowCount:
            raise ErreurSimulee("ligne hors de la fenetre visible")
        absolu = self._position + rang_visible
        if absolu >= self.RowCount:
            raise ErreurSimulee("ligne hors du tableau")
        ligne = self._lignes[absolu] if absolu < len(self._lignes) else {}
        valeur = ligne.get(colonne, "")
        if isinstance(valeur, bool):
            return Controle(f"{self.Id}/chk{colonne}", "GuiCheckBox",
                            selectionne=valeur, monde=self._monde)
        return Controle(f"{self.Id}/txt{colonne}", "GuiTextField",
                        texte=valeur, monde=self._monde)


class _Scrollbar:
    def __init__(self, table): self._t = table
    @property
    def Maximum(self): return max(0, self._t.RowCount - 1)
    @property
    def Position(self): return self._t._position
    @Position.setter
    def Position(self, valeur): self._t._position = int(valeur)


class Grille:
    """ALV : index ABSOLU, aucun ID par cellule."""

    Type = "GuiShell"
    SubType = "GridView"

    def __init__(self, identifiant, colonnes, lignes):
        self.Id = identifiant
        self._colonnes = list(colonnes)
        self._lignes = lignes
        self.selectedRows = ""

    @property
    def RowCount(self): return len(self._lignes)

    @property
    def ColumnOrder(self): return list(self._colonnes)

    def GetCellValue(self, ligne, colonne):
        if ligne >= len(self._lignes):
            raise ErreurSimulee("ligne hors grille")
        return self._lignes[ligne].get(colonne, "")

    def setCurrentCell(self, ligne, colonne):
        self._courante = (ligne, colonne)


class _Collection:
    def __init__(self, items, noms=None):
        self._i = list(items)
        self._noms = noms or []
    @property
    def Count(self): return len(self._i)
    def __call__(self, i):
        objet = self._i[i]
        if i < len(self._noms):
            objet.Name = self._noms[i]
        return objet


# =====================================================================
# Ecrans et monde
# =====================================================================

class Ecran:
    """Un ecran = un programme, un dynpro, un ensemble de controles.

    Le meme identifiant de bouton peut exister sur plusieurs ecrans avec
    des effets differents : c'est precisement le piege qu'on veut pouvoir
    reproduire.
    """

    def __init__(self, nom, programme="", dynpro=0, transaction=""):
        self.nom = nom
        self.programme = programme
        self.dynpro = dynpro
        self.transaction = transaction
        self.controles: dict = {}
        self.statusbar = ("", "")

    def bouton(self, identifiant, action=None, actif=True, libelle=""):
        self.controles[identifiant] = ("bouton", action, actif, libelle)
        return self

    def champ(self, identifiant, texte="", au_changement=None):
        self.controles[identifiant] = ("champ", au_changement, True, texte)
        return self

    def objet(self, identifiant, instance):
        self.controles[identifiant] = ("objet", instance, True, "")
        return self


class Monde:
    """Etat global du simulateur : ecran courant, pile de modales, journal."""

    def __init__(self):
        self.ecrans: dict = {}
        self.ecran_courant = ""
        self.modales: list[str] = []     # noms d'ecrans empiles en wnd[1..]
        self.journal = Journal()

    def ajouter_ecran(self, ecran: Ecran) -> Ecran:
        self.ecrans[ecran.nom] = ecran
        if not self.ecran_courant:
            self.ecran_courant = ecran.nom
        return ecran

    def aller(self, nom): self.ecran_courant = nom
    def empiler(self, nom): self.modales.append(nom)
    def depiler(self):
        if self.modales:
            self.modales.pop()
    def vider_modales(self): self.modales.clear()

    def session(self): return Session(self)


class Session:
    """Objet passe au programme teste. Imite session.findById / Info / Busy."""

    Busy = False

    def __init__(self, monde: Monde):
        self._m = monde

    @property
    def Info(self):
        return _Info(self._m.ecrans[self._m.ecran_courant])

    @property
    def Children(self): return _Collection([object()])

    def _ecran_pour(self, identifiant: str) -> Ecran:
        """wnd[0] = ecran courant ; wnd[n] = n-ieme modale empilee."""
        if identifiant.startswith("wnd[") and not identifiant.startswith("wnd[0]"):
            indice = int(identifiant[4:identifiant.index("]")])
            if indice > len(self._m.modales):
                raise ErreurSimulee(f"{identifiant} : fenetre absente")
            return self._m.ecrans[self._m.modales[indice - 1]]
        return self._m.ecrans[self._m.ecran_courant]

    def findById(self, identifiant: str):
        if identifiant == "wnd[0]/sbar":
            typ, message = self._m.ecrans[self._m.ecran_courant].statusbar
            barre = Controle("sbar", "GuiStatusbar", texte=message)
            barre.MessageType = typ
            return barre

        ecran = self._ecran_pour(identifiant)

        # Cellule de table control : <table>/gabaritCOLONNE[c,l]
        if "[" in identifiant and identifiant.count("/") > 1:
            base, queue = identifiant.rsplit("/", 1)
            if base in ecran.controles and ecran.controles[base][0] == "objet":
                table = ecran.controles[base][1]
                if isinstance(table, TableControl):
                    for gabarit in ("ctxt", "chk", "txt"):
                        if queue.startswith(gabarit):
                            nom, indices = queue[len(gabarit):].split("[")
                            rang = int(indices.rstrip("]").split(",")[1])
                            return table.cellule(nom, rang)

        if identifiant not in ecran.controles:
            raise ErreurSimulee(f"{identifiant} introuvable sur {ecran.nom}")

        genre, charge, actif, extra = ecran.controles[identifiant]
        if genre == "bouton":
            return Controle(identifiant, "GuiButton", texte=extra,
                            actif=actif, action=charge, monde=self._m)
        if genre == "champ":
            controle = Controle(identifiant, "GuiTextField", texte=extra,
                                monde=self._m)
            if charge:
                controle._action = charge
            return controle
        return charge          # objet deja instancie (table, grille)


class _Info:
    def __init__(self, ecran):
        self.Program = ecran.programme
        self.ScreenNumber = ecran.dynpro
        self.Transaction = ecran.transaction


# =====================================================================
# Auto-test
# =====================================================================

if __name__ == "__main__":
    echecs = []

    def verifier(libelle, condition):
        print(f"  [{'OK ' if condition else 'ECHEC'}] {libelle}")
        if not condition:
            echecs.append(libelle)

    print("=== table control : index visible et defilement ===")
    lignes = [{"VORNR": f"{10 * (i + 1):04d}", "TXTKZ": i % 2 == 0}
              for i in range(12)]
    monde = Monde()
    table = TableControl("wnd[0]/usr/tbl", ["VORNR", "TXTKZ"], lignes,
                         visibles=5, monde=monde)
    synthese = Ecran("synthese", "SAPLCPDI", 3400)
    synthese.objet("wnd[0]/usr/tbl", table)
    monde.ajouter_ecran(synthese)
    s = monde.session()

    verifier("rang 0 = premiere ligne",
             s.findById("wnd[0]/usr/tbl/txtVORNR[0,0]").Text == "0010")
    try:
        s.findById("wnd[0]/usr/tbl/txtVORNR[0,7]")
        hors = False
    except ErreurSimulee:
        hors = True
    verifier("rang au-dela du visible : leve", hors)

    table.VerticalScrollbar.Position = 5
    verifier("apres defilement, rang 0 = 6e ligne",
             s.findById("wnd[0]/usr/tbl/txtVORNR[0,0]").Text == "0060")
    verifier("case lue comme booleen",
             s.findById("wnd[0]/usr/tbl/chkTXTKZ[1,0]").Selected is False)

    print("\n=== ALV : index absolu, sans defilement ===")
    grille = Grille("wnd[0]/usr/cntlGRID1/shellcont/shell",
                    ["PLNNR", "PLNAL"],
                    [{"PLNNR": f"MEMAC{100 + i}", "PLNAL": "1"}
                     for i in range(60)])
    verifier("ligne 57 lisible directement",
             grille.GetCellValue(57, "PLNNR") == "MEMAC157")

    print("\n=== pile de fenetres modales ===")
    monde.ajouter_ecran(Ecran("format", "SAPLSTXX", 0)
                        .bouton("wnd[1]/tbar[0]/btn[0]",
                                action=lambda: monde.empiler("fichier")))
    monde.ajouter_ecran(Ecran("fichier", "SAPLSTXX", 0)
                        .champ("wnd[2]/usr/ctxtITCTK-TDFILENAME")
                        .bouton("wnd[2]/tbar[0]/btn[0]",
                                action=monde.vider_modales))
    monde.empiler("format")
    verifier("wnd[1] presente, wnd[2] absente",
             s.findById("wnd[1]/tbar[0]/btn[0]") is not None)
    s.findById("wnd[1]/tbar[0]/btn[0]").press()
    s.findById("wnd[2]/usr/ctxtITCTK-TDFILENAME").Text = r"C:\Temp\x.rtf"
    s.findById("wnd[2]/tbar[0]/btn[0]").press()
    verifier("pile videe apres transfert", monde.modales == [])

    print("\n=== invariant : bouton dangereux hors de son ecran ===")
    monde2 = Monde()
    detail = Ecran("detail", "SAPLCPDO", 3370).bouton("wnd[0]/tbar[1]/btn[7]")
    synth2 = Ecran("synthese", "SAPLCPDI", 3400).bouton("wnd[0]/tbar[1]/btn[7]")
    monde2.ajouter_ecran(detail)
    monde2.ajouter_ecran(synth2)
    s2 = monde2.session()

    monde2.aller("detail")
    s2.findById("wnd[0]/tbar[1]/btn[7]").press()          # legitime
    monde2.journal.assert_jamais("wnd[0]/tbar[1]/btn[7]", hors_ecran="detail")
    verifier("pression legitime acceptee", True)

    monde2.aller("synthese")
    s2.findById("wnd[0]/tbar[1]/btn[7]").press()          # = Inserer !
    try:
        monde2.journal.assert_jamais("wnd[0]/tbar[1]/btn[7]", hors_ecran="detail")
        detecte = False
    except AssertionError:
        detecte = True
    verifier("pression fautive detectee", detecte)

    print("\n=== invariant : nombre de sauvegardes ===")
    monde2.journal.noter("synthese", "save", "wnd[0]/tbar[0]/btn[11]")
    monde2.journal.assert_au_plus("save", 1)
    monde2.journal.noter("synthese", "save", "wnd[0]/tbar[0]/btn[11]")
    try:
        monde2.journal.assert_au_plus("save", 1)
        trop = False
    except AssertionError:
        trop = True
    verifier("sauvegarde surnumeraire detectee", trop)

    print(f"\n{'TOUT PASSE' if not echecs else 'ECHECS : ' + str(echecs)}")
    raise SystemExit(1 if echecs else 0)
