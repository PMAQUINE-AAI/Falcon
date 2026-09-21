"""`automatismes/cl24n_classer.py`, contre un CL24N de theatre.

Le theatre ci-dessous est un `DriverScripte` qui joue les reponses qu'on lui a
ecrites : ecran initial, choix du type d'objet, table control qui defile,
modales « valorisation » et « deja affecte », sauvegarde. **Il n'etablit
aucune fidelite a SAP** — c'est la regle de `falcon/couture/double.py`, et elle
vaut ici mot pour mot. Ces tests prouvent que l'automate fait ce qu'il dit
ETANT DONNE ces reponses : qu'il s'arrete sur l'inconnu, qu'il ne sauvegarde
jamais a blanc, qu'il ne vide pas une ligne qui ne porte plus le point refuse.
Ils ne prouvent pas que SAP repond ainsi. Le rapport du premier lancement reel
le dira.
"""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from automatismes.cl24n_classer import (
    A_VERIFIER, ARRET, DEJA_AFFECTE, NON_SAUVEGARDE, PASSE, POPUP_INCONNUE,
    REFUSE, SAISI, SAUVEGARDE, V_DEJA, V_VALORISATION, Arret, Automate,
    Journal, Prevol, Rapport, executer_sur, lire_points, meme_valeur, prevol,
    confirmer,
)
from falcon.couture.double import DriverScripte
from falcon.donnees.entree import JeuInvalide
from falcon.noyau import (
    Champ, Ecran, ErreurCouture, Fenetre, Identite, ObjetIntrouvable,
    RefusDryRun, Statut,
)

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


class Theatre(DriverScripte):
    """CL24N de theatre. Voir l'en-tete : aucune fidelite."""

    def __init__(self, *, existants=(), obligatoire=False, deja_en_popup=True,
                 trie=False, visibles=3, libres=2, plein=False,
                 type_objet="EQUI", sap_remet_le_defilement_a_zero=False,
                 libelles_de_radio=("Equipement", "Point de mesure")):
        super().__init__(identite=Identite(systeme="K62", mandant="060",
                                           langue="FR",
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
        champs = [Champ(id=PREFIXE + "wnd[0]", type="GuiMainWindow",
                        texte="Affecter objets a une classe", modifiable=False),
                  Champ(id=PREFIXE + "wnd[0]/tbar[0]/okcd", type="GuiOkCodeField",
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
        elif modale["type"] == "confirmation" and par == "valider":
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
            if not point or point in self.valides or point in self.en_erreur:
                continue
            if point in self.existants:
                if self.lignes.index(point) == rang:
                    continue                       # la ligne existante elle-meme
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
            if point == QUESTION:
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
        # Rien de nouveau : une ligne videe sort de l'erreur.
        self.en_erreur = {v for v in self.en_erreur if v in self.lignes}
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

    def automate(self, theatre: Theatre, *, executer: bool) -> Automate:
        self.journal = Journal(self.dossier / "journal.csv")
        self.rapport = Rapport(self.dossier / "rapport.txt", theatre)
        self.addCleanup(self.journal.fermer)
        self.addCleanup(self.rapport.fermer)
        return Automate(theatre, self.journal, self.rapport, executer=executer)

    def lignes(self):
        return _journal(self.journal.chemin)

    def texte_du_rapport(self) -> str:
        return self.rapport.chemin.read_text(encoding="utf-8-sig")


# =====================================================================
# La passe
# =====================================================================

class TestPasse(Base):

    def test_la_passe_saisit_chaque_point_puis_sauvegarde_une_fois(self):
        theatre = Theatre()
        compte = self.automate(theatre, executer=True).passe(
            "CLASSE_A", "015", ["493303", "493304", "493305"])

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

    def test_la_classe_et_le_type_sont_resolus_par_suffixe_parmi_les_champs_de_saisie(self):
        """Le libelle `lblRMCLF-CLASS` porte le meme suffixe : il ne compte pas."""
        theatre = Theatre()
        self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        ecrits = [(c, v) for g, c, v in theatre.gestes if g == "write"]
        self.assertIn((PREFIXE + "wnd[0]/usr/ctxtRMCLF-CLASS", "CLASSE_A"), ecrits)
        self.assertIn((PREFIXE + "wnd[0]/usr/ctxtRMCLF-KLART", "015"), ecrits)

    def test_une_classe_refusee_arrete_avant_tout_point(self):
        theatre = Theatre()
        with self.assertRaises(Arret) as arret:
            self.automate(theatre, executer=True).passe("INCONNUE", "015", ["493303"])
        self.assertIn("n'existe pas", str(arret.exception))
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertNotIn("493303", theatre.lignes)
        self.assertEqual(_etats(self.lignes())[-1], ARRET)

    def test_un_ecran_initial_sans_champ_classe_arrete_en_nommant_le_suffixe(self):
        theatre = Theatre()
        original = theatre.fields

        def sans_classe(fenetre="wnd[0]"):
            ecran = original(fenetre)
            return Ecran(identite=ecran.identite, fenetre=ecran.fenetre,
                         titre=ecran.titre,
                         champs=tuple(c for c in ecran.champs
                                      if not c.id.endswith("ctxtRMCLF-CLASS")))
        theatre.fields = sans_classe
        with self.assertRaises(Arret) as arret:
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertIn("*RMCLF-CLASS", str(arret.exception))
        self.assertIn("lblRMCLF-CLASS", str(arret.exception))

    def test_le_type_d_objet_est_choisi_par_le_bouton_et_la_radio_de_la_trace(self):
        theatre = Theatre()
        self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        gestes = [(g, Theatre._court(c)) for g, c, _ in theatre.gestes]
        self.assertIn(("press", "wnd[0]/tbar[1]/btn[33]"), gestes)
        self.assertIn(("select", RADIO.format(rang=1)), gestes)
        self.assertIn("« Point de mesure »", self.texte_du_rapport())

    def test_le_bouton_type_d_objet_n_est_pas_presse_si_la_colonne_est_deja_la(self):
        theatre = Theatre(type_objet="POINT")
        # Le theatre repasse en EQUI a /nCL24N ; on neutralise cette ligne-la.
        theatre._entree_originale = theatre._entree

        def entree():
            theatre._entree_originale()
            if theatre.ecran == "initial":
                theatre.type_objet = "POINT"
        theatre._entree = entree
        self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertNotIn(("press", PREFIXE + "wnd[0]/tbar[1]/btn[33]", ""),
                         theatre.gestes)
        self.assertEqual(theatre.existants, ["493303"])

    def test_la_radio_est_choisie_par_son_libelle_avant_l_index_de_la_trace(self):
        """Les libelles inverses par rapport a la trace : le libelle gagne."""
        theatre = Theatre(libelles_de_radio=("Point de mesure", "Equipement"))
        original = theatre.select

        def select(id):
            original(id)
            # rang 0 porte « Point de mesure » dans ce theatre-ci
            theatre.choix_radio = "POINT" if id.endswith("[0,0]") else "EQUI"
        theatre.select = select
        self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertEqual(theatre.type_objet, "POINT")
        self.assertIn(("select", PREFIXE + RADIO.format(rang=0), ""), theatre.gestes)

    def test_sans_libelle_la_radio_de_la_trace_sert_de_repli(self):
        theatre = Theatre(libelles_de_radio=("", ""))
        self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertEqual(theatre.type_objet, "POINT")
        self.assertIn("repli sur l'index de la trace", self.texte_du_rapport())

    def test_sans_radio_reconnaissable_la_passe_s_arrete(self):
        theatre = Theatre(libelles_de_radio=("Equipement", "Poste technique"))
        original = theatre._fields_modale

        def sans_index():
            ecran = original()
            return Ecran(identite=ecran.identite, fenetre=ecran.fenetre,
                         titre=ecran.titre,
                         champs=tuple(c for c in ecran.champs
                                      if not c.id.endswith("RADIO[1,0]")))
        theatre._fields_modale = sans_index
        with self.assertRaises(Arret) as arret:
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertIn("aucune radio", str(arret.exception))
        self.assertIn("['Equipement']", str(arret.exception))
        self.assertIn("0 champ(s) *radRMCLF-RADIO[1,0]", str(arret.exception))

    def test_sans_modale_apres_le_bouton_type_d_objet_la_passe_continue_si_la_colonne_est_la(self):
        theatre = Theatre()
        original = theatre.press

        def press(id):
            if id.endswith("btn[33]"):
                theatre._noter("press", id, "")
                theatre.type_objet = "POINT"       # SAP l'a fait sans demander
                theatre._reconstruire()
                return
            original(id)
        theatre.press = press
        compte = self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertEqual(compte, {SAISI: 1})
        self.assertIn("aucune modale apres", self.texte_du_rapport())

    def test_une_transaction_qui_ne_demarre_pas_arrete(self):
        theatre = Theatre()
        theatre.screen = lambda: Identite(transaction="SESSION_MANAGER")
        with self.assertRaises(Arret) as arret:
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertIn("'SESSION_MANAGER' au lieu de 'CL24N'", str(arret.exception))


class TestPointsRefuses(Base):

    def test_un_point_deja_affecte_en_modale_est_KO_et_sa_ligne_est_videe(self):
        theatre = Theatre(existants=["493253"])
        compte = self.automate(theatre, executer=True).passe(
            "CLASSE_A", "015", ["493253", "493303"])

        self.assertEqual(compte, {DEJA_AFFECTE: 1, SAISI: 1})
        self.assertEqual(_etats(self.lignes(), "493253"), [DEJA_AFFECTE])
        self.assertIn("ligne videe", [l for l in self.lignes()
                                      if l["point"] == "493253"][0]["detail"])
        self.assertEqual(theatre.existants, ["493253", "493303"])
        self.assertEqual(theatre.lignes.count("493253"), 1)

    def test_un_point_deja_affecte_en_barre_de_statut_est_KO_de_la_meme_facon(self):
        theatre = Theatre(existants=["493253"], deja_en_popup=False)
        compte = self.automate(theatre, executer=True).passe(
            "CLASSE_A", "015", ["493253", "493303"])
        self.assertEqual(compte, {REFUSE: 1, SAISI: 1})
        refus = [l for l in self.lignes() if l["point"] == "493253"][0]
        self.assertIn("CL:045", refus["detail"])
        self.assertIn("ligne videe", refus["detail"])
        self.assertEqual(theatre.existants, ["493253", "493303"])

    def test_un_point_inexistant_est_REFUSE_et_le_lot_continue(self):
        theatre = Theatre()
        compte = self.automate(theatre, executer=True).passe(
            "CLASSE_A", "015", [INEXISTANT, "493303"])
        self.assertEqual(compte, {REFUSE: 1, SAISI: 1})
        self.assertEqual(theatre.existants, ["493303"])
        self.assertNotIn(INEXISTANT, theatre.lignes)

    def test_la_ligne_n_est_videe_que_si_elle_porte_encore_le_point_refuse(self):
        """SAP a remis le defilement a zero : la meme cellule VISIBLE porte
        maintenant une affectation existante. L'effacer a l'aveugle la
        viderait.
        """
        existants = [f"{n:06d}" for n in range(1, 6)] + ["493253"]
        theatre = Theatre(existants=existants, visibles=3,
                          sap_remet_le_defilement_a_zero=True)
        compte = self.automate(theatre, executer=True).passe(
            "CLASSE_A", "015", ["493253", "493303"])
        self.assertEqual(compte, {DEJA_AFFECTE: 1, SAISI: 1})
        effacements = [(c, v) for g, c, v in theatre.gestes if g == "write" and v == ""]
        self.assertEqual(effacements, [], "une cellule a ete videe a l'aveugle")
        refus = [l for l in self.lignes() if l["point"] == "493253"][0]
        # ecrit en visible 1 apres defilement a 5 (ligne 6) ; SAP remet le
        # defilement a zero : la visible 1 est alors la ligne 1, « 000002 ».
        self.assertIn("cellule non videe : elle porte '000002'", refus["detail"])
        self.assertEqual(theatre.existants, existants + ["493303"])
        for point in existants:
            self.assertIn(point, theatre.lignes)

    def test_un_avertissement_est_confirme_par_une_seconde_Entree(self):
        theatre = Theatre()
        compte = self.automate(theatre, executer=True).passe(
            "CLASSE_A", "015", [AVERTI])
        self.assertEqual(compte, {SAISI: 1})
        self.assertEqual(theatre.existants, [AVERTI])
        self.assertIn("avertissement W CL:077", self.texte_du_rapport())


class TestValorisationObligatoire(Base):

    def test_la_modale_de_valorisation_est_passee_par_poursuivre_puis_valider(self):
        theatre = Theatre(obligatoire=True)
        compte = self.automate(theatre, executer=True).passe(
            "CLASSE_A", "015", ["493303", "493304"])

        self.assertEqual(compte, {SAISI: 2})
        self.assertEqual(theatre.sauvegardes, 1)
        self.assertEqual(theatre.existants, ["493303", "493304"])
        pressions = [Theatre._court(c) for g, c, _ in theatre.gestes if g == "press"]
        # Apres chaque Entree, et apres la sauvegarde : btn[8] puis btn[0].
        self.assertEqual(pressions.count("wnd[1]/tbar[0]/btn[8]"), 3)
        self.assertEqual(
            [p for p in pressions if p.startswith("wnd[1]/tbar[0]/btn[8]")
             or p == "wnd[1]/tbar[0]/btn[0]"][-6:],
            ["wnd[1]/tbar[0]/btn[8]", "wnd[1]/tbar[0]/btn[0]"] * 3)
        saisi = [l for l in self.lignes() if l["point"] == "493303"][0]
        self.assertIn("caracteristiques obligatoires laissees vides", saisi["detail"])
        sauve = [l for l in self.lignes()
                 if l["point"] == "493303" and l["etat"] == SAUVEGARDE][0]
        self.assertIn(V_VALORISATION, sauve["detail"])


class TestModaleInconnue(Base):

    def test_une_question_qui_contient_deja_n_est_pas_fermee_par_Entree(self):
        theatre = Theatre(existants=["493253"])
        original = theatre._valider_table

        def question():
            original()
            if theatre.modale and theatre.modale["type"] == "deja":
                theatre.modale = {"type": "question", "titre": "Confirmation",
                                  "textes": ["Le point 493253 est deja affecte. "
                                             "Continuer quand meme ?"],
                                  "boutons": ["btn[0]", "btn[12]"], "point": "493253",
                                  "choix": True}
        theatre._valider_table = question
        original_fields = theatre._fields_modale

        def avec_choix():
            ecran = original_fields()
            if theatre.modale and theatre.modale.get("choix"):
                champs = ecran.champs + (
                    Champ(id=PREFIXE + "wnd[1]/usr/btnSPOP-OPTION1", type="GuiButton",
                          texte="Oui", modifiable=True),
                    Champ(id=PREFIXE + "wnd[1]/usr/btnSPOP-OPTION2", type="GuiButton",
                          texte="Non", modifiable=True))
                return Ecran(identite=ecran.identite, fenetre=ecran.fenetre,
                             titre=ecran.titre, champs=champs)
            return ecran
        theatre._fields_modale = avec_choix
        with self.assertRaises(Arret) as arret:
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493253"])
        self.assertIn("modale inconnue « Confirmation »", str(arret.exception))
        apres = theatre.gestes[[g[2] for g in theatre.gestes].index("493253"):]
        self.assertEqual([g for g in apres if g[0] in ("press", "select")], [],
                         "un bouton a ete presse sur la question")
        self.assertIsNotNone(theatre.modale)

    def test_en_execution_une_modale_inconnue_arrete_avant_toute_sauvegarde(self):
        theatre = Theatre()
        with self.assertRaises(Arret) as arret:
            self.automate(theatre, executer=True).passe(
                "CLASSE_A", "015", ["493303", QUESTION, "493304"])
        self.assertIn("modale inconnue « Question »", str(arret.exception))
        self.assertIn("Voulez-vous vraiment ?", str(arret.exception))
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertIsNotNone(theatre.modale, "la modale est laissee telle quelle")
        lignes = self.lignes()
        self.assertEqual(_etats(lignes, "493303"), [SAISI, NON_SAUVEGARDE])
        self.assertEqual(_etats(lignes, "493304"), [])
        self.assertEqual(_etats(lignes)[-2], ARRET)

    def test_a_blanc_une_modale_inconnue_est_annulee_et_la_passe_continue(self):
        theatre = Theatre()
        compte = self.automate(theatre, executer=False).passe(
            "CLASSE_A", "015", ["493303", QUESTION, "493304"])
        self.assertEqual(compte, {SAISI: 2, POPUP_INCONNUE: 1})
        self.assertIn(("vkey", "wnd[1]", "12"), theatre.gestes)
        self.assertIsNone(theatre.modale)
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertEqual(_etats(self.lignes(), QUESTION), [POPUP_INCONNUE])

    def test_une_modale_a_l_ouverture_de_la_transaction_arrete(self):
        theatre = Theatre()
        theatre.valides = ["111111"]        # des saisies non sauvegardees
        with self.assertRaises(Arret) as arret:
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertIn("apres /nCL24N", str(arret.exception))
        self.assertIn("Les donnees seront perdues", self.texte_du_rapport())

    def test_une_modale_deja_ouverte_avant_la_transaction_arrete_sans_rien_taper(self):
        theatre = Theatre()
        theatre.modale = {"type": "question", "titre": "Reste d'hier",
                          "textes": ["?"], "boutons": ["btn[0]"], "point": ""}
        with self.assertRaises(Arret) as arret:
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertIn("avant /nCL24N", str(arret.exception))
        self.assertIn("« Reste d'hier »", self.texte_du_rapport())
        self.assertEqual([g for g in theatre.gestes if g[0] == "write"], [])


class TestABlanc(Base):

    def test_a_blanc_ne_presse_jamais_sauvegarder(self):
        theatre = Theatre(obligatoire=True)
        compte = self.automate(theatre, executer=False).passe(
            "CLASSE_A", "015", ["493303", "493304"])
        self.assertEqual(compte, {SAISI: 2})
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertEqual(theatre.valides, ["493303", "493304"])
        self.assertNotIn("btn[11]", [Theatre._court(c) for g, c, _ in theatre.gestes
                                     if g == "press"])
        for point in ("493303", "493304"):
            self.assertEqual(_etats(self.lignes(), point), [SAISI, NON_SAUVEGARDE])

    def test_la_sauvegarde_est_refusee_mecaniquement_a_blanc(self):
        automate = self.automate(Theatre(), executer=False)
        with self.assertRaises(RefusDryRun):
            automate._presser("/app/con[0]/ses[0]/wnd[0]/tbar[0]/btn[11]")
        with self.assertRaises(RefusDryRun):
            automate._touche(11)

    def test_une_exception_de_couture_est_journalisee_avant_de_remonter(self):
        theatre = Theatre()
        theatre.table_visible_rows = lambda id: (_ for _ in ()).throw(ObjetIntrouvable(id))
        with self.assertRaises(ObjetIntrouvable):
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        arret = [l for l in self.lignes() if l["etat"] == ARRET][0]
        self.assertIn("ObjetIntrouvable", arret["detail"])


class TestTableControl(Base):

    def test_la_premiere_ligne_vide_est_cherchee_au_dela_de_la_page_visible(self):
        theatre = Theatre(existants=[f"{n:06d}" for n in range(1, 8)], visibles=3)
        compte = self.automate(theatre, executer=True).passe(
            "CLASSE_A", "015", ["493303"])
        self.assertEqual(compte, {SAISI: 1})
        self.assertEqual(theatre.existants[-1], "493303")
        ecriture = [(c, v) for g, c, v in theatre.gestes
                    if g == "write" and v == "493303"][0]
        self.assertTrue(ecriture[0].endswith("ctxtRMCLF-POINT[0,1]"),
                        f"ecrit dans {ecriture[0]} : la ligne 7 est la visible 1 "
                        f"apres defilement a 6")
        defilements = [v for g, c, v in theatre.gestes if g == "table_scroll"]
        self.assertEqual(defilements[:3], ["0", "3", "6"])

    def test_une_table_sans_ligne_vide_arrete_quand_le_defilement_ne_progresse_plus(self):
        theatre = Theatre(existants=[f"{n:06d}" for n in range(1, 8)], visibles=3,
                          plein=True)
        with self.assertRaises(Arret) as arret:
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertIn("ne progresse plus", str(arret.exception))
        self.assertEqual(theatre.sauvegardes, 0)

    def test_une_ecriture_qui_ne_prend_pas_arrete(self):
        theatre = Theatre()
        theatre.a_l_ecriture = lambda id, v: v[:3] if "POINT" in id else v
        with self.assertRaises(Arret) as arret:
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertIn("relecture", str(arret.exception))
        self.assertIn("relu '493'", str(arret.exception))

    def test_les_zeros_de_tete_ne_font_pas_echouer_la_relecture(self):
        self.assertTrue(meme_valeur("493303", "000000493303"))
        self.assertTrue(meme_valeur(" classe_a ", "CLASSE_A"))
        self.assertFalse(meme_valeur("493303", "493304"))
        self.assertFalse(meme_valeur("0ABC", "ABC"))


class TestSauvegarde(Base):

    def test_une_sauvegarde_refusee_journalise_NON_SAUVEGARDE_et_arrete(self):
        theatre = Theatre()
        theatre._commettre = lambda: setattr(
            theatre, "statut", Statut(type="E", id="CL", numero="900",
                                      texte="Verrou pose par MARTIN"))
        with self.assertRaises(Arret) as arret:
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertIn("sauvegarde refusee", str(arret.exception))
        self.assertEqual(_etats(self.lignes(), "493303"), [SAISI, NON_SAUVEGARDE])

    def test_un_statut_muet_apres_sauvegarde_sort_A_VERIFIER(self):
        theatre = Theatre()
        original = theatre._commettre

        def muet():
            original()
            theatre.statut = Statut()
        theatre._commettre = muet
        self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertEqual(_etats(self.lignes(), "493303"), [SAISI, A_VERIFIER])

    def test_une_modale_inconnue_pendant_la_sauvegarde_sort_A_VERIFIER(self):
        theatre = Theatre()
        original = theatre._commettre

        def question():
            original()
            theatre.modale = {"type": "question", "titre": "Question",
                              "textes": ["Imprimer ?"], "boutons": ["btn[0]"],
                              "point": ""}
        theatre._commettre = question
        with self.assertRaises(Arret):
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertEqual(_etats(self.lignes(), "493303"), [SAISI, A_VERIFIER])

    def test_par_lot_sauvegarde_toutes_les_N_saisies_puis_le_reste(self):
        theatre = Theatre()
        journal = Journal(self.dossier / "journal.csv")
        rapport = Rapport(self.dossier / "rapport.txt", theatre)
        self.journal, self.rapport = journal, rapport
        self.addCleanup(journal.fermer)
        self.addCleanup(rapport.fermer)
        automate = Automate(theatre, journal, rapport, executer=True, par_lot=2)
        compte = automate.passe("CLASSE_A", "015",
                                ["493303", "493304", "493305", "493306", "493307"])
        self.assertEqual(compte, {SAISI: 5})
        self.assertEqual(theatre.sauvegardes, 3)
        for point in ("493303", "493307"):
            self.assertEqual(_etats(self.lignes(), point), [SAISI, SAUVEGARDE])

    def test_la_sauvegarde_verifie_la_transaction_avant_de_presser(self):
        theatre = Theatre()
        original = theatre.screen
        theatre.screen = lambda: (Identite(transaction="SESSION_MANAGER")
                                  if theatre.valides else original())
        with self.assertRaises(Arret) as arret:
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertIn("au moment de sauvegarder", str(arret.exception))
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertEqual(_etats(self.lignes(), "493303"), [SAISI, NON_SAUVEGARDE])

    def test_une_cellule_vide_que_SAP_refuse_d_ecrire_arrete_proprement(self):
        """Une ligne vide non modifiable : l'ecriture leve, la passe s'arrete
        avant toute sauvegarde, et le journal le dit."""
        theatre = Theatre(existants=["100000"])
        original = theatre.write

        def refuse(id, valeur):
            if id.endswith("ctxtRMCLF-POINT[0,1]") and valeur:
                raise ErreurCouture(f"write({id!r}) : The control cannot be changed")
            original(id, valeur)
        theatre.write = refuse
        with self.assertRaises(ErreurCouture):
            self.automate(theatre, executer=True).passe("CLASSE_A", "015", ["493303"])
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertIn("ErreurCouture", [l for l in self.lignes() if l["etat"] == ARRET][0]["detail"])

    def test_le_balayage_repart_de_la_derniere_page_libre_puis_de_zero_au_besoin(self):
        theatre = Theatre(existants=[f"{n:06d}" for n in range(1, 8)], visibles=3)
        automate = self.automate(theatre, executer=True)
        automate.passe("CLASSE_A", "015", ["493303", "493304", "493305"])
        defilements = [int(v) for g, c, v in theatre.gestes if g == "table_scroll"]
        # premier point : 0, 3, 6 ; les suivants repartent de 6, pas de 0
        self.assertEqual(defilements[:3], [0, 3, 6])
        self.assertNotIn(0, defilements[3:])
        self.assertEqual(theatre.existants[-3:], ["493303", "493304", "493305"])

    def test_un_indice_de_depart_qui_ne_mene_a_rien_fait_repartir_de_zero(self):
        """Derniere page pleine, mais une ligne vide plus haut : l'indice est
        faux, le balayage repart de zero une fois, et trouve."""
        theatre = Theatre(existants=[f"{n:06d}" for n in range(1, 8)], visibles=3,
                          plein=True)
        automate = self.automate(theatre, executer=True)
        automate.ouvrir()
        automate.saisir_classe("CLASSE_A", "015")
        automate.choisir_type_objet()
        theatre.lignes[1] = ""                     # une ligne liberee au milieu
        automate._depart = 40                      # un indice devenu faux
        self.assertEqual(automate.affecter("CLASSE_A", "493303"), SAISI)
        defilements = [int(v) for g, c, v in theatre.gestes if g == "table_scroll"]
        self.assertEqual(defilements[0], 40)
        self.assertIn(0, defilements)
        ecriture = [c for g, c, v in theatre.gestes if g == "write" and v == "493303"][0]
        self.assertTrue(ecriture.endswith("ctxtRMCLF-POINT[0,1]"), ecriture)
        self.assertEqual(theatre.valides, ["493303"])

    def test_deux_passes_s_enchainent_apres_une_sauvegarde(self):
        theatre = Theatre(obligatoire=True)
        automate = self.automate(theatre, executer=True)
        automate.passe("CLASSE_A", "015", ["493303"])
        automate.passe("CLASSE_B", "015", ["493303", "493304"])
        self.assertEqual(theatre.sauvegardes, 2)
        self.assertEqual(theatre.saisies["CLASS"], "CLASSE_B")


class TestRapport(Base):

    def test_le_rapport_releve_une_modale_en_entier_une_fois_puis_en_bref(self):
        theatre = Theatre(obligatoire=True)
        self.automate(theatre, executer=True).passe(
            "CLASSE_A", "015", ["493303", "493304"])
        texte = self.texte_du_rapport()
        self.assertEqual(texte.count("| wnd[1] « Valorisation » |"), 3)
        self.assertEqual(texte.count("champs de wnd[1]"), 3,
                         "type d'objet, valorisation, valeurs manquantes : "
                         "chacune en entier une seule fois")
        self.assertIn("| GuiButton | ", texte)
        self.assertIn("| oui", texte)
        self.assertIn("| non", texte)
        self.assertIn("(deja relevee en entier plus haut)", texte)
        self.assertIn("wnd[1]/tbar[0]/btn[8]", texte)
        self.assertIn("point 493303 : statut", texte)
        self.assertIn("sauvegarde : statut S CL:123", texte)


# =====================================================================
# Le jeu, le pre-vol, la confirmation, la commande
# =====================================================================

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
        self.assertIn("--classe", str(refus.exception))
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
        self.assertTrue(confirmer("CLASSE_A", identite, lire=lambda _: " classe_a ",
                                  ecrire=dits.append))
        self.assertFalse(confirmer("CLASSE_A", identite, lire=lambda _: "o",
                                   ecrire=dits.append))
        self.assertFalse(confirmer("CLASSE_A", identite, lire=lambda _: "",
                                   ecrire=dits.append))
        self.assertTrue(any("K62" in d and "060" in d for d in dits))


class TestCommande(unittest.TestCase):

    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp(prefix="cl24n-cmd-"))

    def test_executer_sur_deroule_les_passes_et_ecrit_les_deux_fichiers(self):
        theatre = Theatre()
        dits = []
        reponses = iter(["A", "B"])
        code = executer_sur(theatre, {"A": ["493303"], "B": ["493304"]},
                            type_classe="015", executer=True, sortie=self.dossier,
                            lire=lambda _: next(reponses), ecrire=dits.append)
        self.assertEqual(code, 0)
        self.assertEqual(theatre.sauvegardes, 2)
        journaux = sorted(self.dossier.glob("cl24n_*_journal.csv"))
        rapports = sorted(self.dossier.glob("cl24n_*_rapport.txt"))
        self.assertEqual(len(journaux), 1)
        self.assertEqual(len(rapports), 1)
        self.assertTrue(any("classe A : SAISI 1" in d for d in dits))
        self.assertTrue(any("EXECUTION" in d for d in dits))

    def test_une_confirmation_refusee_ne_lance_pas_la_passe(self):
        theatre = Theatre()
        dits = []
        code = executer_sur(theatre, {"A": ["493303"]}, type_classe="015",
                            executer=True, sortie=self.dossier,
                            lire=lambda _: "non", ecrire=dits.append)
        self.assertEqual(code, 1)
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertEqual(theatre.gestes, [])
        journal = _journal(next(self.dossier.glob("*_journal.csv")))
        self.assertEqual(_etats(journal), [ARRET])

    def test_a_blanc_ne_demande_rien_et_le_dit(self):
        theatre = Theatre()
        dits = []
        code = executer_sur(theatre, {"A": ["493303"]}, type_classe="015",
                            executer=False, sortie=self.dossier,
                            lire=lambda _: self.fail("aucune saisie attendue"),
                            ecrire=dits.append)
        self.assertEqual(code, 0)
        self.assertEqual(theatre.sauvegardes, 0)
        self.assertTrue(any("ne sont PAS sauvegardees" in d for d in dits))

    def test_un_arret_rend_1_et_les_fichiers_sont_fermes(self):
        theatre = Theatre()
        dits = []
        code = executer_sur(theatre, {"A": [QUESTION]}, type_classe="015",
                            executer=True, sortie=self.dossier,
                            lire=lambda _: "A", ecrire=dits.append)
        self.assertEqual(code, 1)
        self.assertTrue(any(d.startswith("ARRET : ") for d in dits))
        rapport = next(self.dossier.glob("*_rapport.txt")).read_text(encoding="utf-8-sig")
        self.assertIn("« Question »", rapport)


if __name__ == "__main__":
    unittest.main()
