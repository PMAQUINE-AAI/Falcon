"""`cl24n.py`, contre un CL24N de theatre.

Le theatre ci-dessous joue les reponses qu'on lui a ecrites : ecran initial,
choix du type d'objet, tableau qui defile, fenetres « valorisation » et
« deja affecte », sauvegarde. **Il n'etablit aucune fidelite a SAP.** Ces
tests prouvent que le programme fait ce qu'il dit ETANT DONNE ces reponses :
qu'il s'arrete sur l'inconnu, qu'il ne sauvegarde jamais a blanc, qu'il ne
vide pas une ligne qui ne porte plus le point refuse, qu'il cherche la ligne
libre au-dela de la page visible. Ils ne prouvent PAS que SAP repond ainsi —
un theatre nourri d'hypotheses confirme les hypotheses. Le rapport du premier
passage a blanc sur un vrai systeme, lui, le dira.

    python test_cl24n.py
"""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cl24n import (                                          # noqa: E402
    A_VERIFIER, ARRET, CLOTURE, COLONNE_CLASSE, COLONNE_POINT, CORPS,
    DEJA_AFFECTE, ECRIRE, ECRIRE_LIGNE_LIBRE, ENTETE, NON_SAUVEGARDE, PASSE,
    POPUP_INCONNUE, PRESSER, REFUSE, SAISI, SAUVEGARDE, SELECTIONNER, TOUCHE,
    Arret, Automate, Champ, Ecran, ErreurCouture, Fenetre, Geste, Identite,
    JeuInvalide, Journal, ObjetIntrouvable, Pilote, Prevol, Rapport, Recette,
    RecetteInvalide, RefusSauvegarde, SapIndisponible, Source, Statut,
    confirmer, dicter_sur, inventorier, lire_points, menu, meme_valeur,
    prevol, rejouer_sur,
)


class DriverDeTheatre:
    """Le socle d'un driver joue : il note les gestes, il n'etablit rien.

    Un test qui s'appuie sur ce que ce double repond verifie le comportement
    du programme ETANT DONNE cette reponse, jamais que SAP repondrait ainsi.
    """

    def __init__(self, identite: Identite):
        self.identite = identite
        self.statut = Statut()
        #: (geste, cible, valeur) — ce qui a reellement ete fait.
        self.gestes: list[tuple[str, str, str]] = []
        #: Transforme une valeur a l'ecriture, pour jouer ce que SAP fait
        #: subir aux saisies : troncature, majuscules, refus.
        self.a_l_ecriture: Callable[[str, str], str] | None = None

    def _noter(self, geste: str, cible: str, valeur: str) -> None:
        self.gestes.append((geste, cible, valeur))


PREFIXE = "/app/con[0]/ses[0]/"          # SAP rend des chemins ABSOLUS
TABLE = ("wnd[0]/usr/subSUBSCR_ZUORD:SAPLCLFM:1512/subOBJEKT:SAPLCBCM:{dynpro}"
         "/tblSAPLCBCMTC_OBJ_CLASS")
COLONNE = {"EQUI": "ctxtRMCLF-EQUNR", "POINT": "ctxtRMCLF-POINT"}
DYNPRO = {"EQUI": "0210", "POINT": "0230"}
RADIO = "wnd[1]/usr/sub:SAPLCLFM:0602/radRMCLF-RADIO[{rang},0]"

#: Des points qui font reagir le theatre d'une facon precise.
INEXISTANT = "999999"        # statut E apres Entree
AVERTI = "777777"            # statut W, puis accepte a la seconde Entree
QUESTION = "666666"          # une modale que l'automate ne connait pas


class Theatre(DriverDeTheatre):
    """CL24N de theatre. Voir l'en-tete : aucune fidelite."""

    def __init__(self, *, existants=(), obligatoire=False, deja_en_popup=True,
                 trie=False, visibles=3, libres=2, plein=False,
                 type_objet="EQUI", sap_remet_le_defilement_a_zero=False,
                 sap_deplace_le_refus=False, valorisation_reste_ouverte=False,
                 question_apres_poursuivre=False,
                 libelles_de_radio=("Equipement", "Point de mesure")):
        super().__init__(Identite(systeme="K62", mandant="060", langue="FR",
                                  transaction="SESSION_MANAGER",
                                  programme="SAPLSMTR_NAVIGATION",
                                  dynpro="0100"))
        self.ecran = "accueil"
        self.type_objet = type_objet
        self.existants = list(existants)
        self.valides: list[str] = []
        self.en_erreur: set[str] = set()
        self.avertis: set[str] = set()
        self.lignes: list[str] = []
        self.visibles, self.libres, self.plein = visibles, libres, plein
        self.position = 0
        self.modale: dict | None = None
        self.obligatoire = obligatoire
        self.deja_en_popup = deja_en_popup
        self.trie = trie
        self.sap_remet_le_defilement_a_zero = sap_remet_le_defilement_a_zero
        self.sap_deplace_le_refus = sap_deplace_le_refus
        self.valorisation_reste_ouverte = valorisation_reste_ouverte
        self.question_apres_poursuivre = question_apres_poursuivre
        self.libelles_de_radio = list(libelles_de_radio)
        self.sauvegardes = 0
        self.sauvegarde_en_attente = False
        self.saisies: dict[str, str] = {}
        self.choix_radio = "EQUI"

    # -- outils ----------------------------------------------------------------

    @staticmethod
    def _court(id: str) -> str:
        return id[len(PREFIXE):] if id.startswith(PREFIXE) else id

    def _table(self) -> str:
        return TABLE.format(dynpro=DYNPRO[self.type_objet])

    def _cellule(self, id: str) -> int | None:
        """Le rang VISIBLE si `id` est une cellule de la colonne objet."""
        prefixe = f"{self._table()}/{COLONNE[self.type_objet]}[0,"
        court = self._court(id)
        if court.startswith(prefixe) and court.endswith("]"):
            return int(court[len(prefixe):-1])
        return None

    def _reconstruire(self) -> None:
        """Ce que le theatre fait de la table apres un geste qui la change.

        Les lignes non vides restent (une ligne en erreur garde sa valeur),
        les lignes prises manquantes sont ajoutees, `libres` lignes vides
        suivent — sauf `plein`. Avec `trie`, les lignes prises passent devant,
        triees : c'est le cas ou SAP reordonne apres Entree.
        """
        pris = list(self.existants) + list(self.valides)
        if self.trie:
            pris = sorted(pris)
            lignes = pris + [v for v in self.lignes if v.strip() and v not in pris]
        else:
            lignes = [v for v in self.lignes if v.strip()]
            lignes += [p for p in pris if p not in lignes]
        if not self.plein:
            lignes += [""] * self.libres
        self.lignes = lignes
        self.position = min(self.position, max(0, len(self.lignes) - self.visibles))

    # -- identite et releve -----------------------------------------------------

    def screen(self) -> Identite:
        if self.ecran == "accueil":
            return self.identite
        dynpro = "0100" if self.ecran == "initial" else "1512"
        return Identite(systeme="K62", mandant="060", langue="FR",
                        transaction="CL24N", programme="SAPLCLFM", dynpro=dynpro)

    def windows(self) -> tuple[Fenetre, ...]:
        principale = Fenetre(id=PREFIXE + "wnd[0]", type="GuiMainWindow",
                             titre="Affecter objets a une classe")
        if self.modale is None:
            return (principale,)
        return (principale, Fenetre(id=PREFIXE + "wnd[1]", type="GuiModalWindow",
                                    titre=self.modale["titre"]))

    def fields(self, fenetre: str = "wnd[0]") -> Ecran:
        if fenetre.endswith("wnd[1]"):
            return self._fields_modale()
        # Les boutons des barres d'outils font partie de l'arbre de wnd[0] :
        # sans eux, un geste dicte sur « Sauvegarder » ou « Type d'objet » ne
        # se resoudrait pas — et c'est ainsi qu'un vrai SAP les rend.
        champs = [Champ(id=PREFIXE + "wnd[0]", type="GuiMainWindow",
                        texte="Affecter objets a une classe", modifiable=False),
                  Champ(id=PREFIXE + "wnd[0]/tbar[0]/okcd", type="GuiOkCodeField",
                        modifiable=True),
                  Champ(id=PREFIXE + "wnd[0]/tbar[0]/btn[11]", type="GuiButton",
                        texte="", infobulle="Sauvegarder (Ctrl+S)",
                        modifiable=True),
                  Champ(id=PREFIXE + "wnd[0]/tbar[1]/btn[33]", type="GuiButton",
                        texte="", infobulle="Type d'objet (Ctrl+F9)",
                        modifiable=True)]
        if self.ecran == "initial":
            champs += [
                Champ(id=PREFIXE + "wnd[0]/usr/lblRMCLF-CLASS", type="GuiLabel",
                      texte="Classe", modifiable=False),
                Champ(id=PREFIXE + "wnd[0]/usr/ctxtRMCLF-CLASS",
                      type="GuiCTextField", texte=self.saisies.get("CLASS", ""),
                      modifiable=True),
                Champ(id=PREFIXE + "wnd[0]/usr/ctxtRMCLF-KLART",
                      type="GuiCTextField", texte=self.saisies.get("KLART", ""),
                      modifiable=True),
            ]
        elif self.ecran == "affectation":
            table = PREFIXE + self._table()
            champs.append(Champ(id=table, type="GuiTableControl", modifiable=True))
            for rang in range(self.visibles):
                absolu = self.position + rang
                if absolu >= len(self.lignes):
                    break
                valeur = self.lignes[absolu]
                champs.append(Champ(
                    id=f"{table}/{COLONNE[self.type_objet]}[0,{rang}]",
                    type="GuiCTextField", texte=valeur,
                    modifiable=valeur not in self.existants))
        return Ecran(identite=self.screen(), fenetre=fenetre,
                     titre="Affecter objets a une classe", champs=tuple(champs))

    def _fields_modale(self) -> Ecran:
        modale = self.modale
        champs = [Champ(id=PREFIXE + "wnd[1]", type="GuiModalWindow",
                        texte=modale["titre"], modifiable=False)]
        for rang, texte in enumerate(modale.get("textes", ())):
            champs.append(Champ(id=PREFIXE + f"wnd[1]/usr/txtMESSTXT{rang + 1}",
                                type="GuiTextField", texte=texte, modifiable=False))
        for rang, libelle in enumerate(modale.get("radios", ())):
            libelle = self.libelles_de_radio[rang]
            champs.append(Champ(id=PREFIXE + RADIO.format(rang=rang),
                                type="GuiRadioButton", texte=libelle, modifiable=True))
        for bouton in modale.get("boutons", ()):
            champs.append(Champ(id=PREFIXE + f"wnd[1]/tbar[0]/{bouton}",
                                type="GuiButton", texte=bouton, modifiable=True))
        if modale.get("choix"):
            champs += [Champ(id=PREFIXE + "wnd[1]/usr/btnSPOP-OPTION1",
                             type="GuiButton", texte="Oui", modifiable=True),
                       Champ(id=PREFIXE + "wnd[1]/usr/btnSPOP-OPTION2",
                             type="GuiButton", texte="Non", modifiable=True)]
        return Ecran(identite=self.screen(), fenetre="wnd[1]",
                     titre=modale["titre"], champs=tuple(champs))

    def status(self) -> Statut:
        return self.statut

    # -- lecture et saisie -------------------------------------------------------

    def read(self, id: str) -> str:
        rang = self._cellule(id)
        if rang is not None:
            absolu = self.position + rang
            if self.ecran != "affectation" or absolu >= len(self.lignes):
                raise ObjetIntrouvable(id)
            return self.lignes[absolu]
        court = self._court(id)
        if court.endswith("ctxtRMCLF-CLASS"):
            return self.saisies.get("CLASS", "")
        if court.endswith("ctxtRMCLF-KLART"):
            return self.saisies.get("KLART", "")
        if court.endswith("okcd"):
            return self.saisies.get("okcd", "")
        raise ObjetIntrouvable(id)

    def write(self, id: str, valeur: str) -> None:
        retenue = self.a_l_ecriture(id, valeur) if self.a_l_ecriture else valeur
        rang = self._cellule(id)
        if rang is not None:
            absolu = self.position + rang
            if self.ecran != "affectation" or absolu >= len(self.lignes):
                raise ObjetIntrouvable(id)
            self.lignes[absolu] = retenue
        else:
            court = self._court(id)
            if court.endswith("ctxtRMCLF-CLASS"):
                self.saisies["CLASS"] = retenue
            elif court.endswith("ctxtRMCLF-KLART"):
                self.saisies["KLART"] = retenue
            elif court.endswith("okcd"):
                self.saisies["okcd"] = retenue
            else:
                raise ObjetIntrouvable(id)
        self._noter("write", id, valeur)

    # -- actions ---------------------------------------------------------------------

    def _fermer_modale(self, par: str) -> None:
        modale, self.modale = self.modale, None
        if modale is None:
            return
        if modale["type"] == "type_objet" and par == "valider":
            self.type_objet = self.choix_radio
            self._reconstruire()
        elif modale["type"] in ("confirmation", "valorisation") and par == "valider":
            if self.sauvegarde_en_attente:
                self._commettre()
        elif modale["type"] == "question" and par == "valider":
            self.valides.append(modale["point"])
            self.en_erreur.discard(modale["point"])
            self._reconstruire()

    def _commettre(self) -> None:
        self.sauvegarde_en_attente = False
        self.existants += self.valides
        self.valides = []
        self.sauvegardes += 1
        self.statut = Statut(type="S", id="CL", numero="123",
                             texte="Affectations sauvegardees")
        self._reconstruire()

    def vkey(self, n: int, fenetre: str = "wnd[0]") -> None:
        self._noter("vkey", fenetre, str(n))
        self.statut = Statut()
        if fenetre.endswith("wnd[1]"):
            self._fermer_modale("valider" if n == 0 else "annuler")
            return
        if n == 11:
            self._sauvegarder()
        elif n == 0:
            self._entree()

    def _entree(self) -> None:
        okcd = self.saisies.pop("okcd", "")
        if okcd.startswith("/n"):
            if okcd == "/nCL24N":
                if self.valides:
                    self.modale = {"type": "perte", "titre": "Quitter",
                                   "textes": ["Les donnees seront perdues"],
                                   "boutons": ["btn[0]", "btn[12]"]}
                    return
                self.ecran = "initial"
                self.type_objet = "EQUI"
                self.saisies = {}
            return
        if self.ecran == "initial":
            classe = self.saisies.get("CLASS", "").strip()
            if not classe:
                self.statut = Statut(type="E", id="CL", numero="001",
                                     texte="Indiquer une classe")
            elif classe.upper() == "INCONNUE":
                self.statut = Statut(type="E", id="CL", numero="002",
                                     texte=f"La classe {classe} n'existe pas")
            else:
                self.ecran = "affectation"
                self.en_erreur = set()
                self._reconstruire()
        elif self.ecran == "affectation":
            self._valider_table()

    def _valider_table(self) -> None:
        for rang, valeur in enumerate(list(self.lignes)):
            point = valeur.strip()
            if not point or point in self.valides:
                continue
            if point in self.existants:
                if self.lignes.index(point) == rang:
                    continue                       # la ligne existante elle-meme
                # SAP revalide les lignes visibles a CHAQUE Entree : une ligne
                # refusee et laissee la est refusee a nouveau.
                self.en_erreur.add(point)
                if self.deja_en_popup:
                    self.modale = {"type": "deja", "titre": "Information",
                                   "textes": [f"Le point {point} est deja affecte "
                                              f"a cette classe"],
                                   "boutons": ["btn[0]"]}
                else:
                    self.statut = Statut(type="E", id="CL", numero="045",
                                         texte=f"Point {point} deja affecte")
                if self.sap_remet_le_defilement_a_zero:
                    self.position = 0
                if self.sap_deplace_le_refus and rang > 0:
                    self.lignes[rang], self.lignes[rang - 1] = (
                        self.lignes[rang - 1], self.lignes[rang])
                return
            if point == INEXISTANT:
                self.en_erreur.add(point)
                self.statut = Statut(type="E", id="IR", numero="004",
                                     texte=f"Le point {point} n'existe pas")
                return
            if point == AVERTI and point not in self.avertis:
                self.avertis.add(point)
                self.statut = Statut(type="W", id="CL", numero="077",
                                     texte=f"Point {point} : verifier le type")
                return
            if point == QUESTION and point not in self.avertis:
                self.en_erreur.add(point)
                self.modale = {"type": "question", "titre": "Question",
                               "textes": ["Voulez-vous vraiment ?"],
                               "boutons": ["btn[0]", "btn[12]"], "point": point}
                return
            self.valides.append(point)
            self._reconstruire()
            if self.obligatoire:
                self.modale = {"type": "valorisation", "titre": "Valorisation",
                               "textes": ["Caracteristique CARAC_OBLIG obligatoire"],
                               "boutons": ["btn[8]", "btn[12]"]}
            return
        # Rien de nouveau : une ligne videe est compactee.
        self._reconstruire()

    def _sauvegarder(self) -> None:
        if self.modale is not None:
            return
        if self.obligatoire and self.valides:
            self.sauvegarde_en_attente = True
            self.modale = {"type": "valorisation", "titre": "Valorisation",
                           "textes": ["Caracteristique CARAC_OBLIG obligatoire"],
                           "boutons": ["btn[8]", "btn[12]"]}
            return
        self._commettre()

    def press(self, id: str) -> None:
        self._noter("press", id, "")
        self.statut = Statut()
        court = self._court(id)
        if court.endswith("wnd[0]/tbar[1]/btn[33]") and self.ecran == "affectation":
            self.choix_radio = self.type_objet
            self.modale = {"type": "type_objet", "titre": "Type d'objet",
                           "radios": self.libelles_de_radio,
                           "boutons": ["btn[0]", "btn[12]"]}
        elif court.endswith("wnd[0]/tbar[0]/btn[11]"):
            self._sauvegarder()
        elif court.startswith("wnd[1]/tbar[0]/"):
            if self.modale is None:
                raise ObjetIntrouvable(id)
            bouton = court.rsplit("/", 1)[1]
            if bouton not in self.modale.get("boutons", ()):
                raise ObjetIntrouvable(id)
            if bouton == "btn[8]" and self.modale["type"] == "valorisation":
                if self.valorisation_reste_ouverte:
                    # F8 fait un controle DANS le dialogue ; Entree le ferme.
                    self.modale = dict(self.modale, boutons=["btn[8]", "btn[0]",
                                                             "btn[12]"])
                elif self.question_apres_poursuivre:
                    self.modale = {"type": "question", "titre": "Confirmation",
                                   "textes": ["Les valeurs saisies seront "
                                              "perdues. Continuer ?"],
                                   "boutons": ["btn[0]", "btn[12]"],
                                   "choix": True, "point": ""}
                else:
                    self.modale = {"type": "confirmation",
                                   "titre": "Valeurs manquantes",
                                   "textes": ["Des caracteristiques obligatoires "
                                              "n'ont pas de valeur"],
                                   "boutons": ["btn[0]", "btn[12]"]}
            elif bouton == "btn[0]":
                self._fermer_modale("valider")
            elif bouton == "btn[12]":
                self._fermer_modale("annuler")
        else:
            raise ObjetIntrouvable(id)

    def select(self, id: str) -> None:
        self._noter("select", id, "")
        if self.modale is None or self.modale["type"] != "type_objet":
            raise ObjetIntrouvable(id)
        court = self._court(id)
        if court == RADIO.format(rang=1):
            self.choix_radio = "POINT"
        elif court == RADIO.format(rang=0):
            self.choix_radio = "EQUI"
        else:
            raise ObjetIntrouvable(id)

    # -- table control ------------------------------------------------------------

    def table_visible_rows(self, id: str) -> int:
        if self.ecran != "affectation" or self._court(id) != self._table():
            raise ObjetIntrouvable(id)
        return self.visibles

    def table_scroll(self, id: str, position: int) -> None:
        if self.ecran != "affectation" or self._court(id) != self._table():
            raise ObjetIntrouvable(id)
        self.position = max(0, min(position, max(0, len(self.lignes) - self.visibles)))
        self._noter("table_scroll", id, str(position))



# =====================================================================
# La recette de reference : ce qu'une dictee produit sur ce theatre
# =====================================================================

def _table_point() -> str:
    return PREFIXE + TABLE.format(dynpro=DYNPRO["POINT"])


def recette_de_reference(*, avec_cloture: bool = True) -> Recette:
    """Ce qu'on obtient en dictant la passe CL24N sur ce theatre.

    Elle est ecrite a la main ici plutot que produite par le pilote : un
    test qui fabriquerait son attendu avec le code qu'il teste ne testerait
    rien. `test_le_pilotage_produit_la_recette_de_reference` verifie que le
    pilote, lui, produit bien celle-ci.
    """
    entete = [
        Geste(type=ECRIRE, cible=PREFIXE + "wnd[0]/tbar[0]/okcd",
              suffixe="okcd", source=Source(constante="/nCL24N"),
              libelle="okcd"),
        Geste(type=TOUCHE, touche=0),
        Geste(type=ECRIRE, cible=PREFIXE + "wnd[0]/usr/ctxtRMCLF-CLASS",
              suffixe="ctxtRMCLF-CLASS", source=Source(colonne=COLONNE_CLASSE),
              libelle="ctxtRMCLF-CLASS"),
        Geste(type=ECRIRE, cible=PREFIXE + "wnd[0]/usr/ctxtRMCLF-KLART",
              suffixe="ctxtRMCLF-KLART", source=Source(constante="015"),
              libelle="ctxtRMCLF-KLART"),
        Geste(type=TOUCHE, touche=0),
        Geste(type=PRESSER, cible=PREFIXE + "wnd[0]/tbar[1]/btn[33]",
              suffixe="tbar[1]/btn[33]", libelle="Type d'objet (Ctrl+F9)"),
        Geste(type=SELECTIONNER, cible=PREFIXE + RADIO.format(rang=1),
              suffixe="radRMCLF-RADIO[1,0]", fenetre="wnd[1]",
              si_fenetre="Type d'objet", libelle="Point de mesure"),
        Geste(type=PRESSER, cible=PREFIXE + "wnd[1]/tbar[0]/btn[0]",
              suffixe="tbar[0]/btn[0]", fenetre="wnd[1]",
              si_fenetre="Type d'objet", libelle="btn[0]"),
    ]
    corps = [
        Geste(type=ECRIRE_LIGNE_LIBRE, table=_table_point(),
              colonne_cible=COLONNE["POINT"], source=Source(colonne=COLONNE_POINT),
              libelle="points"),
        Geste(type=TOUCHE, touche=0),
    ]
    cloture = [
        Geste(type=PRESSER, cible=PREFIXE + "wnd[0]/tbar[0]/btn[11]",
              suffixe="tbar[0]/btn[11]", libelle="Sauvegarder (Ctrl+S)"),
    ] if avec_cloture else []
    return Recette(entete=entete, corps=corps, cloture=cloture,
                   creee_le="2026-09-21T00:00:00.000Z", systeme="K62",
                   mandant="060", transaction="CL24N")


# =====================================================================
# Outils de test
# =====================================================================

def _journal(chemin: Path) -> list[dict[str, str]]:
    with chemin.open(encoding="utf-8-sig", newline="") as fichier:
        return list(csv.DictReader(fichier, delimiter=";"))


def _etats(lignes, point=None):
    return [l["etat"] for l in lignes if point is None or l["point"] == point]


class Base(unittest.TestCase):

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="cl24n-"))

    def automate(self, theatre: Theatre, *, executer: bool,
                 par_lot: int = 0) -> Automate:
        self.journal = Journal(self.dossier / "journal.csv")
        self.rapport = Rapport(self.dossier / "rapport.txt", theatre)
        self.addCleanup(self.journal.fermer)
        self.addCleanup(self.rapport.fermer)
        return Automate(theatre, self.journal, self.rapport, executer=executer,
                        par_lot=par_lot)

    def passe(self, theatre: Theatre, classe: str, points: list, *,
              executer: bool, recette: Recette | None = None, par_lot: int = 0):
        automate = self.automate(theatre, executer=executer, par_lot=par_lot)
        self._automate = automate
        return automate.passe(recette or recette_de_reference(), classe, points)

    def lignes(self):
        return _journal(self.journal.chemin)

    def texte_du_rapport(self) -> str:
        return self.rapport.chemin.read_text(encoding="utf-8-sig")


# =====================================================================
# Rejouer une recette
# =====================================================================

class TestPasse(Base):

    def test_la_passe_saisit_chaque_point_puis_sauvegarde_une_fois(self):
        theatre = Theatre()
        compte = self.passe(theatre, "CLASSE_A", ["493303", "493304", "493305"],
                            executer=True)
        self.assertEqual(compte, {SAISI: 3})
        self.assertEqual(theatre.sauvegardes, 1)
        self.assertEqual(theatre.existants, ["493303", "493304", "493305"])
        self.assertEqual(theatre.saisies, {"CLASS": "CLASSE_A", "KLART": "015"})
        self.assertEqual(theatre.type_objet, "POINT")
        for point in ("493303", "493304", "493305"):
            self.assertEqual(_etats(self.lignes(), point), [SAISI, SAUVEGARDE])
        debut, fin = [l for l in self.lignes() if l["etat"] == PASSE]
        self.assertIn("debut : 3 point(s)", debut["detail"])
        self.assertIn("fin : SAISI 3", fin["detail"])

    def test_la_colonne_du_fichier_fournit_la_valeur_tapee(self):
        theatre = Theatre()
        self.passe(theatre, "AUTRE_CLASSE", ["493303"], executer=True)
        ecrits = [(c, v) for g, c, v in theatre.gestes if g == "write"]
        self.assertIn((PREFIXE + "wnd[0]/usr/ctxtRMCLF-CLASS", "AUTRE_CLASSE"),
                      ecrits)
        self.assertIn((PREFIXE + "wnd[0]/usr/ctxtRMCLF-KLART", "015"), ecrits)

    def test_une_cible_deplacee_est_retrouvee_par_la_fin_de_son_identifiant(self):
        """Le numero de sous-ecran change : le chemin dicte ne resout plus."""
        theatre = Theatre()
        recette = recette_de_reference()
        recette.entete[2] = Geste(
            type=ECRIRE, cible=PREFIXE + "wnd[0]/usr/subAUTRE:SAPLCLFM:9999/"
                                         "ctxtRMCLF-CLASS",
            suffixe="ctxtRMCLF-CLASS", source=Source(colonne=COLONNE_CLASSE),
            libelle="Classe")
        compte = self.passe(theatre, "CLASSE_A", ["493303"], executer=True,
                            recette=recette)
        self.assertEqual(compte, {SAISI: 1})
        self.assertEqual(theatre.saisies["CLASS"], "CLASSE_A")
        self.assertIn("cible retrouvee par son suffixe", self.texte_du_rapport())

    def test_une_cible_introuvable_arrete_et_releve_l_ecran(self):
        theatre = Theatre()
        recette = recette_de_reference()
        recette.entete[2] = Geste(type=ECRIRE, cible=PREFIXE + "wnd[0]/usr/ctxtNEANT",
                                  suffixe="ctxtNEANT",
                                  source=Source(colonne=COLONNE_CLASSE))
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493303"], executer=True,
                       recette=recette)
        self.assertIn("ctxtNEANT", str(arret.exception))
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertIn("cible introuvable", self.texte_du_rapport())

    def test_une_cible_ambigue_arrete_plutot_que_de_choisir(self):
        theatre = Theatre()
        recette = recette_de_reference()
        recette.entete[2] = Geste(type=ECRIRE, cible="", suffixe="RMCLF-CLASS",
                                  source=Source(colonne=COLONNE_CLASSE))
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493303"], executer=True,
                       recette=recette)
        self.assertIn("2 champs finissent par", str(arret.exception))

    def test_la_garde_de_transaction_vient_de_la_recette(self):
        theatre = Theatre()
        recette = recette_de_reference()
        recette.transaction = "IW32"
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493303"], executer=True,
                       recette=recette)
        self.assertIn("dictee sur 'IW32'", str(arret.exception))
        self.assertEqual(theatre.sauvegardes, 0)

    def test_un_geste_conditionnel_est_saute_quand_sa_fenetre_n_est_pas_la(self):
        """Le theatre est deja sur les points : la fenetre du type d'objet ne
        surgit pas, et les deux gestes qui la visent sont sautes."""
        theatre = Theatre(type_objet="POINT")
        original = theatre._entree

        def entree():
            original()
            if theatre.ecran == "initial":
                theatre.type_objet = "POINT"
        theatre._entree = entree
        original_press = theatre.press

        def press(id):
            if id.endswith("btn[33]"):
                theatre._noter("press", id, "")
                return                      # SAP n'ouvre rien : deja au bon type
            original_press(id)
        theatre.press = press
        compte = self.passe(theatre, "CLASSE_A", ["493303"], executer=True)
        self.assertEqual(compte, {SAISI: 1})
        self.assertIn("saute (« Type d'objet » absente)", self.texte_du_rapport())
        self.assertEqual(theatre.existants, ["493303"])


class TestPointsRefuses(Base):

    def test_un_point_deja_affecte_en_popup_est_KO_et_sa_ligne_est_videe(self):
        theatre = Theatre(existants=["493253"])
        compte = self.passe(theatre, "CLASSE_A", ["493253", "493303"],
                            executer=True)
        self.assertEqual(compte, {DEJA_AFFECTE: 1, SAISI: 1})
        self.assertEqual(_etats(self.lignes(), "493253"), [DEJA_AFFECTE])
        refus = [l for l in self.lignes() if l["point"] == "493253"][0]
        self.assertIn("ligne videe", refus["detail"])
        self.assertIn("Le point 493253 est deja affecte", refus["detail"])
        self.assertEqual(theatre.existants, ["493253", "493303"])
        self.assertEqual(theatre.lignes.count("493253"), 1)

    def test_un_point_deja_affecte_en_barre_de_statut_est_KO_de_la_meme_facon(self):
        theatre = Theatre(existants=["493253"], deja_en_popup=False)
        compte = self.passe(theatre, "CLASSE_A", ["493253", "493303"],
                            executer=True)
        self.assertEqual(compte, {REFUSE: 1, SAISI: 1})
        refus = [l for l in self.lignes() if l["point"] == "493253"][0]
        self.assertIn("CL:045", refus["detail"])
        self.assertIn("ligne videe", refus["detail"])
        self.assertEqual(theatre.existants, ["493253", "493303"])

    def test_un_point_inexistant_est_REFUSE_et_le_lot_continue(self):
        theatre = Theatre()
        compte = self.passe(theatre, "CLASSE_A", [INEXISTANT, "493303"],
                            executer=True)
        self.assertEqual(compte, {REFUSE: 1, SAISI: 1})
        self.assertEqual(theatre.existants, ["493303"])
        self.assertNotIn(INEXISTANT, theatre.lignes)

    def test_la_ligne_videe_est_celle_du_refus_meme_si_SAP_a_remis_le_defilement_a_zero(self):
        existants = ["000001", "493253", "000003", "000004", "000005"]
        theatre = Theatre(existants=existants, visibles=3,
                          sap_remet_le_defilement_a_zero=True)
        apres_effacement = []
        original = theatre.write

        def write(id, valeur):
            original(id, valeur)
            if valeur == "":
                apres_effacement.append((theatre.position, list(theatre.lignes)))
        theatre.write = write
        compte = self.passe(theatre, "CLASSE_A", ["493253", "493303"],
                            executer=True)
        self.assertEqual(compte, {DEJA_AFFECTE: 1, SAISI: 1})
        self.assertEqual(len(apres_effacement), 1)
        position, lignes = apres_effacement[0]
        self.assertEqual(position, 3, "le defilement n'a pas ete remis a la "
                                      "position d'ecriture")
        self.assertEqual(lignes[:5], existants, "une ligne existante a ete videe")
        self.assertEqual(theatre.existants, existants + ["493303"])

    def test_une_ligne_refusee_qui_n_est_plus_a_sa_place_arrete_sans_rien_vider(self):
        existants = ["493253", "000002", "000003"]
        theatre = Theatre(existants=existants, visibles=3,
                          sap_deplace_le_refus=True)
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493253", "493303"], executer=True)
        self.assertIn("n'est plus la ou elle a ete ecrite", str(arret.exception))
        effacements = [(c, v) for g, c, v in theatre.gestes
                       if g == "write" and v == ""]
        self.assertEqual(effacements, [])
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertIn(ARRET, _etats(self.lignes()))

    def test_un_avertissement_est_confirme_par_une_seconde_Entree(self):
        theatre = Theatre()
        compte = self.passe(theatre, "CLASSE_A", [AVERTI], executer=True)
        self.assertEqual(compte, {SAISI: 1})
        self.assertEqual(theatre.existants, [AVERTI])
        saisi = [l for l in self.lignes() if l["point"] == AVERTI][0]
        self.assertIn("avertissement accepte par une seconde Entree : W CL:077",
                      saisi["detail"])


class TestValorisationObligatoire(Base):

    def test_la_valorisation_est_passee_par_poursuivre_puis_valider(self):
        theatre = Theatre(obligatoire=True)
        compte = self.passe(theatre, "CLASSE_A", ["493303", "493304"],
                            executer=True)
        self.assertEqual(compte, {SAISI: 2})
        self.assertEqual(theatre.sauvegardes, 1)
        self.assertEqual(theatre.existants, ["493303", "493304"])
        pressions = [Theatre._court(c) for g, c, _ in theatre.gestes if g == "press"]
        self.assertEqual(pressions.count("wnd[1]/tbar[0]/btn[8]"), 3)
        saisi = [l for l in self.lignes() if l["point"] == "493303"][0]
        self.assertIn("caracteristiques obligatoires laissees vides", saisi["detail"])

    def test_si_poursuivre_laisse_le_meme_dialogue_ouvert_valider_le_ferme(self):
        theatre = Theatre(obligatoire=True, valorisation_reste_ouverte=True)
        compte = self.passe(theatre, "CLASSE_A", ["493303", "493304"],
                            executer=True)
        self.assertEqual(compte, {SAISI: 2})
        self.assertEqual(theatre.sauvegardes, 1)

    def test_une_question_apres_poursuivre_n_est_jamais_validee(self):
        theatre = Theatre(obligatoire=True, question_apres_poursuivre=True)
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493303"], executer=True)
        self.assertIn("fenetre inconnue « Confirmation »", str(arret.exception))
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertIn("une question", self.texte_du_rapport())


class TestPopupInconnue(Base):

    def test_en_execution_une_popup_inconnue_arrete_avant_toute_sauvegarde(self):
        theatre = Theatre()
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493303", QUESTION, "493304"],
                       executer=True)
        self.assertIn("fenetre inconnue « Question »", str(arret.exception))
        self.assertIn("ne sont pas sauvegardees", str(arret.exception))
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertIsNotNone(theatre.modale)
        lignes = self.lignes()
        self.assertEqual(_etats(lignes, "493303"), [SAISI, NON_SAUVEGARDE])
        self.assertEqual(_etats(lignes, "493304"), [])

    def test_a_blanc_une_popup_inconnue_est_annulee_sa_ligne_videe_et_on_continue(self):
        theatre = Theatre()
        compte = self.passe(theatre, "CLASSE_A", ["493303", QUESTION, "493304"],
                            executer=False)
        self.assertEqual(compte, {SAISI: 2, POPUP_INCONNUE: 1})
        self.assertIn(("vkey", "wnd[1]", "12"), theatre.gestes)
        self.assertIsNone(theatre.modale)
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertNotIn(QUESTION, theatre.lignes)
        self.assertEqual(theatre.valides, ["493303", "493304"])

    def test_une_question_qui_contient_deja_n_est_pas_fermee_par_Entree(self):
        theatre = Theatre(existants=["493253"])
        original = theatre._valider_table

        def question():
            original()
            if theatre.modale and theatre.modale["type"] == "deja":
                theatre.modale = {"type": "question", "titre": "Confirmation",
                                  "textes": ["Le point 493253 est deja affecte. "
                                             "Continuer quand meme ?"],
                                  "boutons": ["btn[0]", "btn[12]"],
                                  "point": "493253", "choix": True}
        theatre._valider_table = question
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493253"], executer=True)
        self.assertIn("fenetre inconnue « Confirmation »", str(arret.exception))
        self.assertIsNotNone(theatre.modale)

    def test_une_popup_a_l_ouverture_arrete(self):
        theatre = Theatre()
        theatre.valides = ["111111"]        # des saisies non sauvegardees
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493303"], executer=True)
        self.assertIn("fenetre inconnue « Quitter »", str(arret.exception))
        self.assertIn("Les donnees seront perdues", self.texte_du_rapport())


class TestABlanc(Base):

    def test_a_blanc_ne_presse_jamais_sauvegarder(self):
        theatre = Theatre(obligatoire=True)
        compte = self.passe(theatre, "CLASSE_A", ["493303", "493304"],
                            executer=False)
        self.assertEqual(compte, {SAISI: 2})
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertEqual(theatre.valides, ["493303", "493304"])
        pressions = [c for g, c, _ in theatre.gestes if g == "press"]
        self.assertFalse(any(c.endswith("btn[11]") for c in pressions), pressions)
        self.assertNotIn(("vkey", "wnd[0]", "11"), theatre.gestes)
        for point in ("493303", "493304"):
            self.assertEqual(_etats(self.lignes(), point), [SAISI, NON_SAUVEGARDE])

    def test_la_sauvegarde_est_refusee_mecaniquement_a_blanc(self):
        automate = self.automate(Theatre(), executer=False)
        with self.assertRaises(RefusSauvegarde):
            automate._presser(PREFIXE + "wnd[0]/tbar[0]/btn[11]")
        with self.assertRaises(RefusSauvegarde):
            automate._touche(11)

    def test_une_exception_de_couture_est_journalisee_avant_de_remonter(self):
        theatre = Theatre()
        theatre.table_visible_rows = lambda id: (_ for _ in ()).throw(
            ObjetIntrouvable(id))
        with self.assertRaises(ObjetIntrouvable):
            self.passe(theatre, "CLASSE_A", ["493303"], executer=True)
        arret = [l for l in self.lignes() if l["etat"] == ARRET][0]
        self.assertIn("ObjetIntrouvable", arret["detail"])


class TestTableau(Base):

    def test_la_premiere_ligne_libre_est_cherchee_au_dela_de_la_page_visible(self):
        theatre = Theatre(existants=[f"{n:06d}" for n in range(1, 8)], visibles=3)
        compte = self.passe(theatre, "CLASSE_A", ["493303"], executer=True)
        self.assertEqual(compte, {SAISI: 1})
        self.assertEqual(theatre.existants[-1], "493303")
        ecriture = [c for g, c, v in theatre.gestes
                    if g == "write" and v == "493303"][0]
        self.assertTrue(ecriture.endswith("ctxtRMCLF-POINT[0,1]"), ecriture)
        defilements = [v for g, c, v in theatre.gestes if g == "table_scroll"]
        self.assertEqual(defilements[:3], ["0", "3", "6"])

    def test_un_tableau_sans_ligne_libre_arrete(self):
        theatre = Theatre(existants=[f"{n:06d}" for n in range(1, 8)], visibles=3,
                          plein=True)
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493303"], executer=True)
        self.assertIn("ne progresse plus", str(arret.exception))
        self.assertEqual(theatre.sauvegardes, 0)

    def test_le_balayage_repart_de_la_derniere_page_libre(self):
        theatre = Theatre(existants=[f"{n:06d}" for n in range(1, 8)], visibles=3)
        self.passe(theatre, "CLASSE_A", ["493303", "493304", "493305"],
                   executer=True)
        defilements = [int(v) for g, c, v in theatre.gestes if g == "table_scroll"]
        self.assertEqual(defilements[:3], [0, 3, 6])
        self.assertNotIn(0, defilements[3:])

    def test_une_ecriture_qui_ne_prend_pas_arrete(self):
        theatre = Theatre()
        theatre.a_l_ecriture = lambda id, v: v[:3] if "POINT" in id else v
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493303"], executer=True)
        self.assertIn("relecture", str(arret.exception))
        self.assertIn("relu '493'", str(arret.exception))

    def test_les_zeros_de_tete_ne_font_pas_echouer_la_relecture(self):
        self.assertTrue(meme_valeur("493303", "000000493303"))
        self.assertTrue(meme_valeur(" classe_a ", "CLASSE_A"))
        self.assertFalse(meme_valeur("493303", "493304"))
        self.assertFalse(meme_valeur("0ABC", "ABC"))


class TestCloture(Base):

    def test_une_sauvegarde_refusee_journalise_NON_SAUVEGARDE_et_arrete(self):
        theatre = Theatre()
        theatre._commettre = lambda: setattr(
            theatre, "statut", Statut(type="E", id="CL", numero="900",
                                      texte="Verrou pose par MARTIN"))
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493303"], executer=True)
        self.assertIn("sauvegarde refusee", str(arret.exception))
        self.assertEqual(_etats(self.lignes(), "493303"), [SAISI, NON_SAUVEGARDE])

    def test_un_statut_muet_apres_la_cloture_sort_A_VERIFIER(self):
        theatre = Theatre()
        original = theatre._commettre

        def muet():
            original()
            theatre.statut = Statut()
        theatre._commettre = muet
        self.passe(theatre, "CLASSE_A", ["493303"], executer=True)
        self.assertEqual(_etats(self.lignes(), "493303"), [SAISI, A_VERIFIER])

    def test_une_popup_inconnue_pendant_la_cloture_sort_A_VERIFIER(self):
        theatre = Theatre()
        original = theatre._commettre

        def question():
            original()
            theatre.modale = {"type": "question", "titre": "Question",
                              "textes": ["Imprimer ?"], "boutons": ["btn[0]"],
                              "point": ""}
        theatre._commettre = question
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493303"], executer=True)
        self.assertEqual(_etats(self.lignes(), "493303"), [SAISI, A_VERIFIER])
        self.assertIn("PRESSEE", str(arret.exception))

    def test_une_recette_sans_cloture_ne_sauvegarde_pas_et_le_dit(self):
        theatre = Theatre()
        with self.assertRaises(Arret) as arret:
            self.passe(theatre, "CLASSE_A", ["493303"], executer=True,
                       recette=recette_de_reference(avec_cloture=False))
        self.assertIn("ne dit pas comment sauvegarder", str(arret.exception))
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertEqual(_etats(self.lignes(), "493303"), [SAISI, NON_SAUVEGARDE])

    def test_par_lot_sauvegarde_toutes_les_N_saisies(self):
        theatre = Theatre()
        compte = self.passe(theatre, "CLASSE_A",
                            ["493303", "493304", "493305", "493306", "493307"],
                            executer=True, par_lot=2)
        self.assertEqual(compte, {SAISI: 5})
        self.assertEqual(theatre.sauvegardes, 3)
        for point in ("493303", "493307"):
            self.assertEqual(_etats(self.lignes(), point), [SAISI, SAUVEGARDE])

    def test_deux_passes_s_enchainent(self):
        theatre = Theatre()
        automate = self.automate(theatre, executer=True)
        recette = recette_de_reference()
        self.assertEqual(automate.passe(recette, "CLASSE_A", ["493303"]),
                         {SAISI: 1})
        self.assertEqual(automate.passe(recette, "CLASSE_B", ["493304", "493305"]),
                         {SAISI: 2})
        self.assertEqual(theatre.sauvegardes, 2)
        self.assertEqual(theatre.saisies["CLASS"], "CLASSE_B")


class TestRapport(Base):

    def test_le_rapport_releve_une_fenetre_en_entier_une_fois_puis_en_bref(self):
        theatre = Theatre(obligatoire=True)
        self.passe(theatre, "CLASSE_A", ["493303", "493304"], executer=True)
        texte = self.texte_du_rapport()
        self.assertEqual(texte.count("champs de wnd[1]"), 3,
                         "type d'objet, valorisation, valeurs manquantes : "
                         "chacune en entier une seule fois")
        self.assertIn("(deja relevee en entier plus haut)", texte)
        self.assertIn("| GuiButton | ", texte)
        self.assertIn("point 493303 : statut", texte)
        self.assertIn("cloture : statut S CL:123", texte)
class TestJeu(unittest.TestCase):

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="cl24n-jeu-"))

    def _jeu(self, texte: str, nom="points.csv") -> Path:
        chemin = self.dossier / nom
        chemin.write_text(texte, encoding="utf-8")
        return chemin

    def test_le_jeu_est_regroupe_par_classe_dans_l_ordre(self):
        jeu = self._jeu("point;classe\r\n493303;B\r\n493304;A\r\n493305;B\r\n")
        self.assertEqual(lire_points(jeu), {"B": ["493303", "493305"],
                                            "A": ["493304"]})

    def test_le_jeu_accepte_la_virgule_et_le_BOM(self):
        jeu = self.dossier / "excel.csv"
        jeu.write_bytes("﻿classe,point\r\nA,493303\r\n".encode("utf-8"))
        self.assertEqual(lire_points(jeu), {"A": ["493303"]})

    def test_une_ligne_vide_finale_et_des_cellules_vides_sont_ignorees(self):
        jeu = self._jeu("point;classe\r\n493303;A\r\n\r\n;\r\n")
        self.assertEqual(lire_points(jeu), {"A": ["493303"]})

    def test_un_en_tete_sans_delimiteur_est_refuse(self):
        jeu = self._jeu("point classe\r\n493303 A\r\n")
        with self.assertRaises(JeuInvalide) as refus:
            lire_points(jeu)
        self.assertIn("ni « ; » ni « , »", str(refus.exception))

    def test_un_export_cp1252_est_lu(self):
        jeu = self.dossier / "ansi.csv"
        jeu.write_bytes("point;classe\r\n493303;CLASSE_\xc9T\xc9\r\n".encode("cp1252"))
        self.assertEqual(lire_points(jeu), {"CLASSE_\xc9T\xc9": ["493303"]})

    def test_un_point_de_plus_de_douze_chiffres_est_refuse(self):
        jeu = self._jeu("point;classe\r\n1234567890123;A\r\n")
        with self.assertRaises(JeuInvalide) as refus:
            lire_points(jeu)
        self.assertIn("13 chiffres, 12 au plus", str(refus.exception))

    def test_un_point_qui_n_est_pas_un_numero_est_refuse(self):
        jeu = self._jeu("point;classe\r\n493303.0;A\r\n")
        with self.assertRaises(JeuInvalide) as refus:
            lire_points(jeu)
        self.assertIn("ligne 2", str(refus.exception))
        self.assertIn("'493303.0'", str(refus.exception))

    def test_un_doublon_par_classe_est_refuse(self):
        jeu = self._jeu("point;classe\r\n493303;A\r\n0493303;A\r\n")
        with self.assertRaises(JeuInvalide) as refus:
            lire_points(jeu)
        self.assertIn("en double", str(refus.exception))

    def test_une_colonne_absente_est_refusee(self):
        jeu = self._jeu("pdm;classe\r\n493303;A\r\n")
        with self.assertRaises(JeuInvalide) as refus:
            lire_points(jeu)
        self.assertIn("'point' absente", str(refus.exception))

    def test_une_classe_vide_est_refusee(self):
        jeu = self._jeu("point;classe\r\n493303;\r\n")
        with self.assertRaises(JeuInvalide):
            lire_points(jeu)


class TestPrevol(unittest.TestCase):

    JEU = {"A": ["1", "2", "3"], "B": ["4"]}

    def test_le_plafond_refuse_avant_tout_contact(self):
        with self.assertRaises(Prevol) as refus:
            prevol(self.JEU, classes=[], plafond=2, executer=True)
        self.assertIn("classe A : 3 point(s), plafond 2", str(refus.exception))

    def test_a_blanc_exige_une_seule_classe(self):
        with self.assertRaises(Prevol) as refus:
            prevol(self.JEU, classes=[], plafond=10, executer=False)
        self.assertIn("Choisir parmi", str(refus.exception))
        self.assertEqual(prevol(self.JEU, classes=["B"], plafond=10, executer=False),
                         {"B": ["4"]})

    def test_en_execution_toutes_les_classes_passent(self):
        self.assertEqual(prevol(self.JEU, classes=[], plafond=10, executer=True),
                         self.JEU)

    def test_une_classe_demandee_absente_est_refusee(self):
        with self.assertRaises(Prevol) as refus:
            prevol(self.JEU, classes=["C"], plafond=10, executer=True)
        self.assertIn("['C']", str(refus.exception))

    def test_un_plafond_nul_est_refuse(self):
        with self.assertRaises(Prevol):
            prevol(self.JEU, classes=[], plafond=0, executer=True)


class TestConfirmation(unittest.TestCase):

    def test_le_nom_de_la_classe_en_toutes_lettres(self):
        identite = Identite(systeme="K62", mandant="060")
        dits = []

        def demander(reponse):
            return confirmer("CLASSE_A", identite, executer=True,
                             lire=lambda _: reponse, ecrire=dits.append)

        self.assertTrue(demander(" classe_a "))
        self.assertFalse(demander("o"))
        self.assertFalse(demander(""))
        self.assertFalse(demander("oui"))

        def fermee(_):
            raise EOFError
        self.assertFalse(confirmer("CLASSE_A", identite, executer=True,
                                   lire=fermee, ecrire=dits.append))
        self.assertTrue(any("K62" in d and "060" in d for d in dits))

    def test_le_mode_est_dit_avant_de_demander(self):
        identite = Identite(systeme="K62", mandant="060")
        execution, blanc = [], []
        confirmer("A", identite, executer=True, lire=lambda _: "A",
                  ecrire=execution.append)
        confirmer("A", identite, executer=False, lire=lambda _: "A",
                  ecrire=blanc.append)
        self.assertTrue(any("SAUVEGARDER" in d for d in execution))
        self.assertTrue(any("SANS RIEN SAUVEGARDER" in d for d in blanc))


# =====================================================================
# La recette : elle survit a un aller-retour sur le disque
# =====================================================================

class TestRecette(unittest.TestCase):

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="cl24n-recette-"))

    def test_un_aller_retour_sur_le_disque_ne_perd_rien(self):
        avant = recette_de_reference()
        chemin = avant.ecrire_dans(self.dossier / "r.json")
        apres = Recette.lire(chemin)
        self.assertEqual(apres.en_json(), avant.en_json())
        for moment in (ENTETE, CORPS, CLOTURE):
            self.assertEqual([g.resume() for g in apres.moment(moment)],
                             [g.resume() for g in avant.moment(moment)])

    def test_les_colonnes_exigees_sont_celles_des_gestes(self):
        self.assertEqual(recette_de_reference().colonnes,
                         [COLONNE_CLASSE, COLONNE_POINT])

    def test_une_recette_illisible_est_refusee_en_nommant_le_fichier(self):
        chemin = self.dossier / "casse.json"
        chemin.write_text("{ pas du json", encoding="utf-8")
        with self.assertRaises(RecetteInvalide) as refus:
            Recette.lire(chemin)
        self.assertIn("casse.json", str(refus.exception))

    def test_une_recette_vide_est_refusee(self):
        chemin = self.dossier / "vide.json"
        chemin.write_text('{"entete": [], "corps": []}', encoding="utf-8")
        with self.assertRaises(RecetteInvalide) as refus:
            Recette.lire(chemin)
        self.assertIn("vide", str(refus.exception))

    def test_une_recette_absente_est_refusee(self):
        with self.assertRaises(RecetteInvalide):
            Recette.lire(self.dossier / "neant.json")

    def test_un_geste_de_type_inconnu_est_refuse_au_chargement(self):
        chemin = self.dossier / "faux.json"
        chemin.write_text('{"entete": [{"type": "danser"}], "corps": []}',
                          encoding="utf-8")
        with self.assertRaises(RecetteInvalide) as refus:
            Recette.lire(chemin)
        self.assertIn("danser", str(refus.exception))

    def test_une_source_absente_de_la_ligne_arrete(self):
        source = Source(colonne="site")
        with self.assertRaises(Arret) as arret:
            source.valeur({COLONNE_POINT: "1"})
        self.assertIn("'site' absente", str(arret.exception))

    def test_la_recette_se_lit_en_francais(self):
        rendu = recette_de_reference().rendre()
        self.assertIn("UNE FOIS par classe", rendu)
        self.assertIn("pour CHAQUE point", rendu)
        self.assertIn("premiere ligne libre", rendu)
        self.assertIn("[si « Type d'objet »]", rendu)


# =====================================================================
# Le pilotage dicte
# =====================================================================

class TestInventaire(unittest.TestCase):

    def test_les_cellules_de_tableau_sont_mises_a_part(self):
        theatre = Theatre(type_objet="POINT")
        theatre.ecran = "affectation"
        theatre._reconstruire()
        inventaire = inventorier(theatre.fields("wnd[0]"))
        self.assertEqual(len(inventaire.tableaux), 1)
        table, colonne, cellules = inventaire.tableaux[0]
        self.assertTrue(table.endswith("tblSAPLCBCMTC_OBJ_CLASS"), table)
        self.assertEqual(colonne, "ctxtRMCLF-POINT")
        self.assertEqual(len(cellules), 2)
        # Le champ de commande reste designable : c'est par lui qu'on ouvre
        # une transaction, donc il ne doit jamais disparaitre de la liste.
        self.assertEqual([_fin(c.id) for c in inventaire.champs], ["okcd"])
        self.assertEqual(len(inventaire.boutons), 2)

    def test_les_champs_de_saisie_hors_tableau_sont_numerotes(self):
        theatre = Theatre()
        theatre.ecran = "initial"
        inventaire = inventorier(theatre.fields("wnd[0]"))
        self.assertEqual([_fin(c.id) for c in inventaire.champs],
                         ["okcd", "ctxtRMCLF-CLASS", "ctxtRMCLF-KLART"])

    def test_les_choix_d_une_fenetre_surgissante_sont_numerotes(self):
        theatre = Theatre()
        theatre.ecran = "affectation"
        theatre.modale = {"type": "type_objet", "titre": "Type d'objet",
                          "radios": theatre.libelles_de_radio,
                          "boutons": ["btn[0]", "btn[12]"]}
        inventaire = inventorier(theatre.fields("wnd[1]"))
        self.assertEqual([c.texte for c in inventaire.choix],
                         ["Equipement", "Point de mesure"])
        self.assertEqual(len(inventaire.boutons), 2)


def _fin(identifiant: str) -> str:
    return identifiant.rsplit("/", 1)[-1]


class TestPilote(unittest.TestCase):
    """La premiere passe, dictee — sans terminal : `lire` est une liste."""

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="cl24n-pilote-"))
        self.dits = []

    def piloter(self, ordres, theatre=None, valeurs=None):
        theatre = theatre if theatre is not None else Theatre()
        self.theatre = theatre
        rapport = Rapport(self.dossier / "dictee.txt", theatre)
        self.addCleanup(rapport.fermer)
        suite = iter(ordres)
        pilote = Pilote(theatre, rapport,
                        colonnes=[COLONNE_POINT, COLONNE_CLASSE],
                        lire=lambda _: next(suite),
                        ecrire=self.dits.append)
        return pilote.piloter(valeurs or {COLONNE_POINT: "493303",
                                          COLONNE_CLASSE: "CLASSE_A"})

    @property
    def texte(self):
        return "\n".join(self.dits)

    #: La dictee complete d'une passe CL24N sur ce theatre, telle qu'un
    #: humain la taperait. Le champ 1 est toujours le champ de commande.
    DICTEE = [
        '1 = "/nCL24N"', "e",            # ouvrir la transaction
        "2 = classe", '3 = "015"', "e",  # la classe et son type
        "b2",                            # « Type d'objet »
        "r2", "b1",                      # « Point de mesure », puis valider
        "boucle",
        "T1 = point", "e",               # le point, dans la 1re ligne libre
        "cloture",
        "b1", "sauvegarder",             # Sauvegarder, confirme
        "fin",
    ]

    def test_la_dictee_complete_produit_la_recette_de_reference(self):
        recette = self.piloter(self.DICTEE + [])
        self.assertIsNotNone(recette)
        attendue = recette_de_reference()
        self.assertEqual([g.resume() for g in recette.entete],
                         [g.resume() for g in attendue.entete])
        self.assertEqual([g.resume() for g in recette.corps],
                         [g.resume() for g in attendue.corps])
        self.assertEqual([g.resume() for g in recette.cloture],
                         [g.resume() for g in attendue.cloture])
        self.assertEqual(recette.transaction, "CL24N")
        self.assertEqual(recette.systeme, "K62")

    def test_ce_qui_est_dicte_est_REELLEMENT_fait_dans_SAP(self):
        self.piloter(self.DICTEE)
        self.assertEqual(self.theatre.saisies["CLASS"], "CLASSE_A")
        self.assertEqual(self.theatre.saisies["KLART"], "015")
        self.assertEqual(self.theatre.type_objet, "POINT")
        self.assertEqual(self.theatre.existants, ["493303"])
        self.assertEqual(self.theatre.sauvegardes, 1)

    def test_la_recette_dictee_se_rejoue_a_l_identique(self):
        recette = self.piloter(self.DICTEE)
        theatre = Theatre()
        journal = Journal(self.dossier / "j.csv")
        rapport = Rapport(self.dossier / "r.txt", theatre)
        self.addCleanup(journal.fermer)
        self.addCleanup(rapport.fermer)
        automate = Automate(theatre, journal, rapport, executer=True)
        compte = automate.passe(recette, "CLASSE_B", ["493304", "493305"])
        self.assertEqual(compte, {SAISI: 2})
        self.assertEqual(theatre.existants, ["493304", "493305"])
        self.assertEqual(theatre.saisies["CLASS"], "CLASSE_B")

    def test_l_ecran_est_montre_avec_ses_champs_et_ses_boutons(self):
        self.piloter(["v", "abandon"])
        self.assertIn("CHAMPS", self.texte)
        self.assertIn("BOUTONS", self.texte)
        self.assertIn("Sauvegarder", self.texte)
        self.assertIn("moment : entete", self.texte)

    def test_le_tableau_est_montre_avec_ses_lignes_libres(self):
        ordres = ['1 = "/nCL24N"', "e", "2 = classe", '3 = "015"', "e",
                  "b2", "r2", "b1", "abandon"]
        self.piloter(ordres)
        self.assertIn("TABLEAU T1", self.texte)
        self.assertIn("2 libre(s)", self.texte)

    def test_abandonner_ne_rend_aucune_recette(self):
        self.assertIsNone(self.piloter(["abandon"]))

    def test_une_entree_fermee_abandonne(self):
        def lire(_):
            raise EOFError
        theatre = Theatre()
        rapport = Rapport(self.dossier / "d.txt", theatre)
        self.addCleanup(rapport.fermer)
        pilote = Pilote(theatre, rapport, colonnes=[COLONNE_POINT],
                        lire=lire, ecrire=self.dits.append)
        self.assertIsNone(pilote.piloter({COLONNE_POINT: "1"}))

    def test_un_ordre_inconnu_ne_fait_rien_et_redemande(self):
        self.piloter(["danser", "abandon"])
        self.assertIn("ordre inconnu", self.texte)
        self.assertEqual(self.theatre.gestes, [])

    def test_un_numero_de_champ_inexistant_ne_fait_rien(self):
        self.piloter(['9 = "x"', "abandon"])
        self.assertIn("il n'y a pas de champ 9", self.texte)
        self.assertEqual(self.theatre.gestes, [])

    def test_une_valeur_qui_n_est_ni_constante_ni_colonne_est_refusee(self):
        self.piloter(["1 = site", "abandon"])
        self.assertIn("n'est ni une constante", self.texte)
        self.assertEqual(self.theatre.gestes, [])

    def test_annuler_retire_le_dernier_geste_de_la_recette_sans_defaire_SAP(self):
        recette = self.piloter(['1 = "/nCL24N"', "e", "annuler", "fin"])
        self.assertEqual(len(recette.entete), 1)
        self.assertEqual(recette.entete[0].type, ECRIRE)
        # Entree a bien ete envoyee dans SAP : c'est la recette qu'on corrige.
        self.assertIn(("vkey", "wnd[0]", "0"), self.theatre.gestes)
        self.assertIn("SAP n'a PAS ete defait", self.texte)

    def test_la_sauvegarde_se_confirme_en_toutes_lettres(self):
        """« non » : la sauvegarde n'est ni faite ni enregistree."""
        refusee = [o for o in self.DICTEE if o != "sauvegarder"]
        refusee.insert(refusee.index("b1", refusee.index("cloture")) + 1, "non")
        recette = self.piloter(refusee)
        self.assertEqual(recette.cloture, [], "la sauvegarde est entree dans la "
                                              "recette sans avoir ete confirmee")
        self.assertEqual(self.theatre.sauvegardes, 0)
        self.assertIn("SAUVEGARDE dans SAP", self.texte)
        self.assertIn("ni fait ni enregistre", self.texte)

    def test_un_geste_dicte_dans_une_fenetre_surgissante_devient_conditionnel(self):
        recette = self.piloter(['1 = "/nCL24N"', "e", "2 = classe", '3 = "015"',
                                "e", "b2", "r2", "fin"])
        radio = recette.entete[-1]
        self.assertEqual(radio.type, SELECTIONNER)
        self.assertEqual(radio.fenetre, "wnd[1]")
        self.assertEqual(radio.si_fenetre, "Type d'objet")

    def test_une_saisie_qui_ne_prend_pas_n_entre_pas_dans_la_recette(self):
        theatre = Theatre()
        theatre.a_l_ecriture = lambda id, v: ""
        recette = self.piloter(['1 = "/nCL24N"', "fin"], theatre=theatre)
        self.assertEqual(recette.entete, [])
        self.assertIn("la saisie n'a pas pris", self.texte)

    def test_liste_montre_la_recette_en_cours(self):
        self.piloter(['1 = "/nCL24N"', "liste", "abandon"])
        self.assertIn("UNE FOIS par classe", self.texte)
        self.assertIn("(1 geste(s))", self.texte)

    def test_une_note_est_gardee_dans_la_recette(self):
        recette = self.piloter(['1 = "/nCL24N"', "note K62 mandant 060", "fin"])
        self.assertEqual(recette.note, "K62 mandant 060")


class TestDicterSur(unittest.TestCase):

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="cl24n-dictee-"))
        self.dits = []

    def test_la_dictee_ecrit_la_recette_et_le_releve(self):
        theatre = Theatre()
        ordres = iter(['1 = "/nCL24N"', "e", "fin"])
        chemin = dicter_sur(theatre, {COLONNE_POINT: "493303",
                                      COLONNE_CLASSE: "CLASSE_A"},
                            colonnes=[COLONNE_POINT, COLONNE_CLASSE],
                            sortie=self.dossier, lire=lambda _: next(ordres),
                            ecrire=self.dits.append)
        self.assertIsNotNone(chemin)
        self.assertEqual(len(list(self.dossier.glob("*_recette.json"))), 1)
        self.assertEqual(len(list(self.dossier.glob("*_dictee.txt"))), 1)
        recette = Recette.lire(chemin)
        self.assertEqual(len(recette.entete), 2)

    def test_un_abandon_n_ecrit_aucune_recette(self):
        theatre = Theatre()
        ordres = iter(["abandon"])
        chemin = dicter_sur(theatre, {COLONNE_POINT: "1"}, colonnes=[COLONNE_POINT],
                            sortie=self.dossier, lire=lambda _: next(ordres),
                            ecrire=self.dits.append)
        self.assertIsNone(chemin)
        self.assertEqual(list(self.dossier.glob("*_recette.json")), [])


# =====================================================================
# Le lancement et le menu
# =====================================================================

class TestRejouerSur(unittest.TestCase):

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="cl24n-rejeu-"))
        self.dits = []

    def rejouer(self, retenues, *, executer, reponses, theatre=None,
                recette=None):
        theatre = theatre if theatre is not None else Theatre()
        self.theatre = theatre
        suite = iter(reponses)
        return rejouer_sur(theatre, recette or recette_de_reference(), retenues,
                           executer=executer, sortie=self.dossier,
                           lire=lambda _: next(suite), ecrire=self.dits.append)

    @property
    def texte(self):
        return "\n".join(self.dits)

    def test_les_passes_se_deroulent_et_les_deux_fichiers_sont_ecrits(self):
        code = self.rejouer({"A": ["493303"], "B": ["493304"]}, executer=True,
                            reponses=["A", "B"])
        self.assertEqual(code, 0)
        self.assertEqual(self.theatre.sauvegardes, 2)
        self.assertEqual(len(list(self.dossier.glob("cl24n_*_journal.csv"))), 1)
        self.assertEqual(len(list(self.dossier.glob("cl24n_*_rapport.txt"))), 1)
        self.assertTrue(any("classe A : SAISI 1" in d for d in self.dits))

    def test_une_confirmation_refusee_ne_lance_pas_la_passe(self):
        code = self.rejouer({"A": ["493303"]}, executer=True, reponses=["non"])
        self.assertEqual(code, 1)
        self.assertEqual(self.theatre.sauvegardes, 0)
        self.assertEqual(self.theatre.gestes, [])
        journal = _journal(next(self.dossier.glob("*_journal.csv")))
        self.assertEqual(_etats(journal), [ARRET])

    def test_a_blanc_le_dit_et_ne_sauvegarde_pas(self):
        code = self.rejouer({"A": ["493303"]}, executer=False, reponses=["A"])
        self.assertEqual(code, 0)
        self.assertEqual(self.theatre.sauvegardes, 0)
        self.assertTrue(any("ne sont PAS sauvegardees" in d for d in self.dits))
        self.assertTrue(any("A BLANC" in d for d in self.dits))

    def test_un_arret_rend_1_et_journalise_les_classes_non_lancees(self):
        code = self.rejouer({"A": [QUESTION], "B": ["493304"]}, executer=True,
                            reponses=["A", "B"])
        self.assertEqual(code, 1)
        self.assertTrue(any(d.startswith("ARRET : ") for d in self.dits))
        journal = _journal(next(self.dossier.glob("*_journal.csv")))
        derniere = journal[-1]
        self.assertEqual((derniere["classe"], derniere["etat"]), ("B", PASSE))
        self.assertIn("non lancee", derniere["detail"])

    def test_une_recette_d_un_autre_systeme_est_signalee(self):
        recette = recette_de_reference()
        recette.systeme = "P01"
        self.rejouer({"A": ["493303"]}, executer=True, reponses=["A"],
                     recette=recette)
        self.assertIn("ATTENTION : recette dictee sur P01", self.texte)

    def test_le_rapport_porte_la_recette_rejouee(self):
        self.rejouer({"A": ["493303"]}, executer=True, reponses=["A"])
        rapport = next(self.dossier.glob("*_rapport.txt")).read_text(
            encoding="utf-8-sig")
        self.assertIn("UNE FOIS par classe", rapport)
        self.assertIn("premiere ligne libre", rapport)


class TestMenu(unittest.TestCase):
    """Le menu, sans terminal : `lire` et `ecrire` sont injectes, et la
    connexion aussi — rien ici ne touche a COM."""

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="cl24n-menu-"))
        self.jeu = self.dossier / "points.csv"
        self.jeu.write_text("point;classe\r\n493303;CLASSE_A\r\n"
                            "493304;CLASSE_B\r\n", encoding="utf-8")
        self.dits = []

    def lancer(self, reponses, theatre=None, fabrique=None):
        theatre = theatre if theatre is not None else Theatre()
        self.theatre = theatre
        suite = iter(reponses)
        code = menu(fabrique or (lambda: theatre), sortie=self.dossier,
                    jeu_defaut=self.jeu, lire=lambda _: next(suite),
                    ecrire=self.dits.append)
        return code, theatre

    @property
    def texte(self):
        return "\n".join(self.dits)

    def test_zero_quitte_sans_se_connecter(self):
        appels = []

        def fabrique():
            appels.append(1)
            return Theatre()
        code, _ = self.lancer(["0"], fabrique=fabrique)
        self.assertEqual(code, 0)
        self.assertEqual(appels, [], "le menu s'est connecte pour rien")

    def test_une_entree_fermee_quitte(self):
        def lire(_):
            raise EOFError
        code = menu(lambda: Theatre(), sortie=self.dossier, jeu_defaut=self.jeu,
                    lire=lire, ecrire=self.dits.append)
        self.assertEqual(code, 0)

    def test_un_choix_inconnu_redemande(self):
        code, _ = self.lancer(["42", "0"])
        self.assertEqual(code, 0)
        self.assertIn("choix inconnu", self.texte)

    def test_sap_injoignable_le_dit_et_rend_la_main_au_menu(self):
        def fabrique():
            raise SapIndisponible("pywin32 n'est pas installe")
        code, _ = self.lancer(["1", "0"], fabrique=fabrique)
        self.assertEqual(code, 0)
        self.assertIn("SAP injoignable", self.texte)

    def test_verifier_la_connexion_ne_fait_aucun_geste(self):
        code, theatre = self.lancer(["1", "0"])
        self.assertEqual(code, 0)
        self.assertEqual(theatre.gestes, [])
        self.assertIn("K62", self.texte)

    def test_relever_l_ecran_ecrit_un_fichier_et_ne_fait_aucun_geste(self):
        code, theatre = self.lancer(["2", "", "0"])
        self.assertEqual(code, 0)
        self.assertEqual(theatre.gestes, [])
        releves = list(self.dossier.glob("cl24n_*_ecran.txt"))
        self.assertEqual(len(releves), 1)
        self.assertIn("champs de wnd[0]",
                      releves[0].read_text(encoding="utf-8-sig"))

    #: La dictee, telle qu'on la tape depuis le menu.
    DICTEE = ['1 = "/nCL24N"', "e", "2 = classe", '3 = "015"', "e", "b2",
              "r2", "b1", "boucle", "T1 = point", "e", "cloture", "b1",
              "sauvegarder", "fin"]

    def test_dicter_puis_rejouer_de_bout_en_bout(self):
        """Le parcours entier : on dicte une classe, puis on rejoue l'autre."""
        reponses = (["3", "", "1", "CLASSE_A"] + self.DICTEE
                    + ["5", "", "", "", "CLASSE_A", "CLASSE_B", "0"])
        code, theatre = self.lancer(reponses)
        self.assertEqual(code, 0)
        self.assertEqual(len(list(self.dossier.glob("*_recette.json"))), 1)
        # La dictee a saisi et sauvegarde 493303. Le rejeu repasse CLASSE_A :
        # ce theatre ne connait qu'une classe, donc il repond « deja affecte »,
        # ce qui est exactement ce qu'on veut voir a une relance. Puis
        # CLASSE_B ajoute 493304.
        self.assertEqual(theatre.existants, ["493303", "493304"])
        self.assertEqual(theatre.sauvegardes, 2)
        journal = _journal(sorted(self.dossier.glob("*_journal.csv"))[-1])
        self.assertEqual(_etats(journal, "493303"), [DEJA_AFFECTE])

    def test_la_dictee_demande_confirmation_avant_de_toucher_a_SAP(self):
        code, theatre = self.lancer(["3", "", "1", "non", "0"])
        self.assertEqual(code, 0)
        self.assertEqual(theatre.gestes, [])
        self.assertIn("non confirmee", self.texte)
        self.assertEqual(list(self.dossier.glob("*_recette.json")), [])

    def test_rejouer_sans_recette_le_dit(self):
        code, theatre = self.lancer(["4", "0"])
        self.assertEqual(code, 0)
        self.assertIn("aucune recette", self.texte)
        self.assertEqual(theatre.gestes, [])

    def test_une_recette_illisible_est_refusee_sans_toucher_a_SAP(self):
        casse = self.dossier / "cl24n_0_recette.json"
        casse.write_text("{ non", encoding="utf-8")
        code, theatre = self.lancer(["4", "", "0"])
        self.assertEqual(code, 0)
        self.assertIn("REFUS", self.texte)
        self.assertEqual(theatre.gestes, [])

    def test_une_recette_qui_exige_une_colonne_absente_est_refusee(self):
        recette = recette_de_reference()
        recette.corps[0] = Geste(type=ECRIRE_LIGNE_LIBRE, table="t",
                                 colonne_cible="c", source=Source(colonne="site"))
        recette.ecrire_dans(self.dossier / "cl24n_0_recette.json")
        code, theatre = self.lancer(["4", "", "", "0"])
        self.assertEqual(code, 0)
        self.assertIn("['site']", self.texte)
        self.assertEqual(theatre.gestes, [])

    def test_un_fichier_illisible_est_refuse_sans_toucher_a_SAP(self):
        recette_de_reference().ecrire_dans(self.dossier / "cl24n_0_recette.json")
        casse = self.dossier / "casse.csv"
        casse.write_text("pdm;classe\r\n493303;A\r\n", encoding="utf-8")
        code, theatre = self.lancer(["4", "", str(casse), "0"])
        self.assertEqual(code, 0)
        self.assertIn("'point' absente", self.texte)
        self.assertEqual(theatre.gestes, [])

    def test_un_plafond_depasse_est_refuse_avant_tout_contact(self):
        recette_de_reference().ecrire_dans(self.dossier / "cl24n_0_recette.json")
        code, theatre = self.lancer(["5", "", "", "0", "0"])
        self.assertEqual(code, 0)
        self.assertIn("REFUS avant tout contact avec SAP", self.texte)
        self.assertEqual(theatre.gestes, [])

    def test_lister_les_sorties_dit_quand_il_n_y_en_a_pas(self):
        code, _ = self.lancer(["6", "0"])
        self.assertEqual(code, 0)
        self.assertIn("aucune sortie", self.texte)

    def test_un_arret_ne_fait_pas_tomber_le_menu(self):
        recette = recette_de_reference()
        recette.transaction = "IW32"
        recette.ecrire_dans(self.dossier / "cl24n_0_recette.json")
        code, _ = self.lancer(["4", "", "", "1", "", "CLASSE_A", "0"])
        self.assertEqual(code, 0)
        self.assertIn("ARRET", self.texte)


if __name__ == "__main__":
    unittest.main(verbosity=2)
