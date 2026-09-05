"""Les cinq gardes, et l'impossibilite pour une pipeline de les contourner.

Chaque garde a un test de declenchement ET un de non-declenchement. Une garde
qui ne se declenche jamais ne protege rien ; une garde qui se declenche
toujours sera desactivee avant la fin de la semaine.

Le double de driver utilise ici n'etablit AUCUNE fidelite a SAP. Ces tests
verifient le comportement de FALCON etant donne une reponse de driver — jamais
que SAP repondrait ainsi.
"""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from dataclasses import fields

from falcon.controleur import (
    DEROGEABLES, Contrat, ContratIncomplet, Derogation, DerogationRefusee,
    DriverGarde, Poste,
)
from falcon.couture import Driver
from falcon.couture.double import DriverScripte
from falcon.noyau import (
    EcartIdentite, Fenetre, FenetreImprevue, Identite, IncidentBloquant,
    ItemAbandonne, PlafondAtteint, RefusDryRun, Statut,
)
from falcon.taxonomie import Registre

IA08 = Identite(transaction="IA08", programme="RIPLKO10", dynpro="1000")
AUTRE = Identite(transaction="CL02", programme="SAPLCLFM", dynpro="0100")

MOTIF = "l'editeur SAPscript n'est pas adressable, verifie par retelechargement"

#: Classement EXHAUSTIF de la surface de couture. Toute methode nouvelle doit
#: etre rangee d'un cote ou de l'autre, sinon
#: `test_toute_methode_de_la_surface_est_classee_lecture_ou_mutation` tombe.
LECTURES = {"screen", "fields", "windows", "status", "read",
            "grid_rows", "grid_columns", "grid_read", "table_visible_rows"}
MUTATIONS = {"write", "set_checked", "press", "select", "vkey", "table_scroll",
             "grid_select_rows", "grid_set_current_row", "grid_double_click"}


def _garde(brut: DriverScripte, *, mode: str = "run",
           plafond: int = 100) -> DriverGarde:
    return DriverGarde(brut, Registre.charger(), mode=mode,
                       plafond_sauvegardes=plafond)


class TestGarde1Identite(unittest.TestCase):
    """« Cette seule garde attrape la majorite des derives. »"""

    def test_se_declenche_sur_le_mauvais_ecran(self):
        brut = DriverScripte(identite=AUTRE, valeurs={"champ": "x"})
        garde = _garde(brut)
        contrat = Contrat(nom="lire", ecran_attendu=IA08.triplet)
        with garde.sous_contrat(contrat):
            with self.assertRaises(EcartIdentite):
                garde.read("champ")

    def test_ne_se_declenche_pas_sur_le_bon_ecran(self):
        brut = DriverScripte(identite=IA08, valeurs={"champ": "x"})
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            self.assertEqual(garde.read("champ"), "x")

    def test_navigation_libre_se_declare_et_se_trace(self):
        """Le besoin reste legitime — une etape qui ne sait pas encore ou elle
        atterrit — mais il devient une decision, pas un oubli."""
        brut = DriverScripte(identite=AUTRE, valeurs={"champ": "x"})
        garde = _garde(brut)
        contrat = Contrat(nom="atterrir", navigation_libre=True)
        with garde.sous_contrat(contrat):
            self.assertEqual(garde.read("champ"), "x")
        self.assertEqual([(c.garde, c.verdict) for c in garde.constats],
                         [("identite", "non_gardee")])

    def test_une_etape_muette_est_refusee(self):
        """Constat de revue : `ecran_attendu=None` etait le DEFAUT, donc une
        etape distraite neutralisait sans un mot la garde qui attrape a elle
        seule la majorite des derives."""
        with self.assertRaises(ContratIncomplet):
            Contrat(nom="distraite")

    def test_declarer_les_deux_est_refuse(self):
        with self.assertRaises(ContratIncomplet):
            Contrat(nom="x", ecran_attendu=IA08.triplet, navigation_libre=True)

    def test_l_ecart_est_trace(self):
        brut = DriverScripte(identite=AUTRE, valeurs={"champ": "x"})
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            with self.assertRaises(EcartIdentite):
                garde.read("champ")
        self.assertEqual(garde.constats[0].garde, "identite")
        self.assertEqual(garde.constats[0].verdict, "violation")

    def test_aucune_derogation_n_est_possible(self):
        """Une identite violee signale que le modele du monde est faux."""
        self.assertNotIn("identite", DEROGEABLES)
        with self.assertRaises(DerogationRefusee):
            Derogation(garde="identite", portee="etape:x", motif=MOTIF)


class TestGarde2Statut(unittest.TestCase):

    def test_un_message_d_erreur_non_repertorie_bloque(self):
        brut = DriverScripte(identite=IA08,
                             statut=Statut(type="E", id="ZZ", numero="999"))
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            with self.assertRaises(IncidentBloquant):
                garde.press("bouton")

    def test_un_message_de_succes_ne_bloque_pas(self):
        brut = DriverScripte(identite=IA08, statut=Statut(type="S", id="CP",
                                                          numero="001"))
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            garde.press("bouton")
        self.assertEqual(garde.constats, [])

    def test_le_silence_est_un_signal_quand_un_statut_est_attendu(self):
        """Une selection qui ne remonte rien et n'emet aucun message n'est pas
        une preuve d'absence de donnees."""
        brut = DriverScripte(identite=IA08, statut=Statut())
        garde = _garde(brut)
        contrat = Contrat(ecran_attendu=IA08.triplet, statut_attendu="S")
        with garde.sous_contrat(contrat):
            # « connue fautive » : l'item est perdu, le lot continue.
            with self.assertRaises(ItemAbandonne):
                garde.press("executer")
        constat = garde.constats[0]
        self.assertEqual(constat.garde, "statut")
        self.assertEqual(constat.taxonomie.entree,
                         "ia08_selection_vide_sans_message")
        self.assertEqual(constat.taxonomie.politique.item, "ko")

    def test_une_derogation_evite_le_blocage_et_laisse_une_trace(self):
        brut = DriverScripte(identite=IA08,
                             statut=Statut(type="E", id="ZZ", numero="999"))
        garde = _garde(brut)
        contrat = Contrat(nom="x", ecran_attendu=IA08.triplet,
                          derogations=(Derogation("statut", "etape:x", MOTIF),))
        with garde.sous_contrat(contrat):
            garde.press("bouton")            # ne leve pas
        self.assertEqual(garde.constats[0].verdict, "derogee")
        self.assertEqual(garde.constats[0].derogation.motif, MOTIF)


class TestGarde3Fenetres(unittest.TestCase):

    def test_une_fenetre_imprevue_arrete_tout(self):
        brut = DriverScripte(identite=IA08)

        def surgir(driver, geste, cible):
            driver.fenetres = (Fenetre(id="wnd[0]"), Fenetre(id="wnd[1]"))

        brut.apres_action = surgir
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            with self.assertRaises(FenetreImprevue):
                garde.press("bouton")

    def test_une_fenetre_prevue_par_l_etape_passe(self):
        brut = DriverScripte(identite=IA08,
                             fenetres=(Fenetre(id="wnd[0]"), Fenetre(id="wnd[1]")))
        garde = _garde(brut)
        contrat = Contrat(nom="modale", ecran_attendu=IA08.triplet,
                          fenetres_attendues=("wnd[0]", "wnd[1]"))
        with garde.sous_contrat(contrat):
            garde.press("bouton")
        # La modale est acceptee, mais l'elargissement laisse une trace : une
        # garde relachee doit rester visible au rapport.
        self.assertEqual([(c.garde, c.verdict) for c in garde.constats],
                         [("fenetre", "elargie")])


class TestToutesLesMutationsSontGardees(unittest.TestCase):
    """Constat de revue : fenetres et statut n'etaient releves qu'apres
    `press`, `select` et `vkey`. `write`, `set_checked` et `table_scroll`
    mutent pourtant l'ecran — un `table_scroll` declenche un aller-retour
    serveur — et un popup surgi la n'etait vu qu'a l'action suivante, donc
    attribue a la mauvaise etape."""

    def _surgissement(self):
        brut = DriverScripte(identite=IA08, valeurs={"champ": "x"})
        brut.tables = {"tbl": {"visibles": 5}}

        def surgir(driver, geste, cible):
            driver.fenetres = (Fenetre(id="wnd[0]"), Fenetre(id="wnd[1]"))

        brut.apres_action = surgir
        return brut

    def test_une_ecriture_voit_la_fenetre_imprevue(self):
        garde = _garde(self._surgissement())
        with garde.sous_contrat(Contrat(nom="e", ecran_attendu=IA08.triplet)):
            with self.assertRaises(FenetreImprevue):
                garde.write("champ", "x")

    def test_une_case_a_cocher_voit_la_fenetre_imprevue(self):
        garde = _garde(self._surgissement())
        with garde.sous_contrat(Contrat(nom="c", ecran_attendu=IA08.triplet)):
            with self.assertRaises(FenetreImprevue):
                garde.set_checked("case", True)

    def test_un_defilement_voit_la_fenetre_imprevue(self):
        garde = _garde(self._surgissement())
        with garde.sous_contrat(Contrat(nom="d", ecran_attendu=IA08.triplet)):
            with self.assertRaises(FenetreImprevue):
                garde.table_scroll("tbl", 5)

    def test_une_selection_alv_voit_la_fenetre_imprevue(self):
        garde = _garde(self._surgissement())
        with garde.sous_contrat(Contrat(nom="s", ecran_attendu=IA08.triplet)):
            with self.assertRaises(FenetreImprevue):
                garde.grid_select_rows("alv", (0,))

    def test_un_positionnement_de_cellule_voit_la_fenetre_imprevue(self):
        garde = _garde(self._surgissement())
        with garde.sous_contrat(Contrat(nom="p", ecran_attendu=IA08.triplet)):
            with self.assertRaises(FenetreImprevue):
                garde.grid_set_current_row("alv", 4)

    def test_un_double_clic_voit_la_fenetre_imprevue(self):
        garde = _garde(self._surgissement())
        with garde.sous_contrat(Contrat(nom="d", ecran_attendu=IA08.triplet)):
            with self.assertRaises(FenetreImprevue):
                garde.grid_double_click("alv")

    def test_toute_methode_de_la_surface_est_classee_lecture_ou_mutation(self):
        """Le classement doit etre EXHAUSTIF, pas une liste tenue a la main.

        La version precedente enumerait les mutantes connues : ajouter une
        methode de couture sans la garder ne cassait rien, il suffisait de ne
        pas penser a la liste. C'est ce qui est arrive aux trois methodes ALV
        en ecriture. Desormais toute methode nouvelle doit etre rangee d'un
        cote ou de l'autre pour que ce test passe.
        """
        self.assertEqual(LECTURES & MUTATIONS, set())
        self.assertEqual(LECTURES | MUTATIONS, set(Driver.__abstractmethods__),
                         "une methode de couture n'est ni classee lecture ni "
                         "classee mutation")

    def test_toute_mutation_de_la_surface_releve_l_ecran(self):
        source = Path("falcon/controleur/gardes.py").read_text(encoding="utf-8")
        for methode in sorted(MUTATIONS):
            corps = source.split(f"def {methode}(self")[1].split("\n    def ")[0]
            with self.subTest(methode=methode):
                self.assertIn("_apres_action()", corps)

    def test_toute_methode_de_la_surface_verifie_l_identite(self):
        """Lecture comprise : lire le mauvais ecran rend une valeur qui a
        l'air bonne, et c'est le pire des resultats."""
        source = Path("falcon/controleur/gardes.py").read_text(encoding="utf-8")
        observation = {"screen", "fields", "windows", "status"}
        for methode in sorted(LECTURES | MUTATIONS):
            if methode in observation:
                continue        # les gardes elles-memes s'en servent
            corps = source.split(f"def {methode}(self")[1].split("\n    def ")[0]
            with self.subTest(methode=methode):
                self.assertIn("_garde_identite()", corps)


class TestAlvEnEcriture(unittest.TestCase):
    """Decision n°14 : ecrire dans une grille ALV.

    Sans ces trois methodes, le flux « Obtenir variante » — le premier flux
    reel du projet, releve sur une trace du recorder — n'etait pas exprimable
    en dehors d'un appel COM sauvage.
    """

    def _alv(self) -> DriverScripte:
        brut = DriverScripte(identite=IA08)
        brut.grilles = {"alv": [{"VARIANT": "BCP_FR12"},
                                {"VARIANT": "BCP_FR13"}]}
        return brut

    def test_le_double_clic_est_traite_comme_une_navigation(self):
        """Il charge une variante, ouvre un detail, descend dans une ligne."""
        source = Path("falcon/controleur/gardes.py").read_text(encoding="utf-8")
        corps = source.split("def grid_double_click(self")[1]
        self.assertIn("_est_sauvegarde", corps.split("\n    def ")[0])

    def test_une_etape_declaree_sauvegarde_est_honoree_au_double_clic(self):
        """Le geste par lequel une etape sauve ne change pas le fait qu'elle
        sauve : le plafond doit la compter."""
        garde = _garde(self._alv(), plafond=1)
        contrat = Contrat(nom="charger", ecran_attendu=IA08.triplet,
                          sauvegarde=True)
        with garde.sous_contrat(contrat):
            garde.grid_double_click("alv")
            with self.assertRaises(PlafondAtteint):
                garde.grid_double_click("alv")
        self.assertEqual(garde.sauvegardes, 1)

    def test_un_double_clic_sauvegardant_est_refuse_en_dry_run(self):
        garde = _garde(self._alv(), mode="dry-run")
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet,
                                        sauvegarde=True)):
            with self.assertRaises(RefusDryRun):
                garde.grid_double_click("alv")

    def test_la_selection_et_le_positionnement_ne_sauvent_jamais_d_office(self):
        """Ni l'un ni l'autre n'ecrit dans SAP : les compter consommerait le
        plafond avant la premiere vraie sauvegarde."""
        garde = _garde(self._alv(), plafond=1)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            garde.grid_select_rows("alv", (0, 1))
            garde.grid_set_current_row("alv", 1)
        self.assertEqual(garde.sauvegardes, 0)

    def test_le_mauvais_ecran_arrete_le_double_clic(self):
        brut = self._alv()
        brut.identite = AUTRE
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(nom="c", ecran_attendu=IA08.triplet)):
            with self.assertRaises(EcartIdentite):
                garde.grid_double_click("alv")

    def test_le_double_clic_agit_sur_la_cellule_courante_pas_sur_la_selection(self):
        """Le piege releve sur la trace, exerce bout a bout.

        Selectionner la ligne 1 ne suffit pas : sans positionnement, le
        double-clic porte sur la ligne 0. C'est une valeur fausse traitee sans
        la moindre erreur.
        """
        brut = self._alv()
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            garde.grid_select_rows("alv", (1,))
            garde.grid_double_click("alv")
        self.assertEqual(brut.gestes[-1], ("grid_double_click", "alv", "0"))

        brut.gestes.clear()
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            garde.grid_set_current_row("alv", 1)
            garde.grid_select_rows("alv", (1,))
            garde.grid_double_click("alv")
        self.assertEqual(brut.gestes[-1], ("grid_double_click", "alv", "1"))


class TestGarde4Relecture(unittest.TestCase):
    """« Ecrire sans que ca prenne est une classe de bug deja rencontree. »"""

    def test_une_ecriture_qui_ne_prend_pas_est_detectee(self):
        brut = DriverScripte(identite=IA08)
        brut.a_l_ecriture = lambda id, valeur: ""      # SAP refuse la saisie
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            with self.assertRaises(ItemAbandonne):
                garde.write("champ", "FR12")
        constat = garde.constats[0]
        self.assertEqual(constat.garde, "relecture")
        self.assertEqual(constat.taxonomie.entree, "relecture_divergente")
        self.assertEqual(constat.taxonomie.politique.item, "ko")

    def test_une_ecriture_qui_prend_ne_dit_rien(self):
        brut = DriverScripte(identite=IA08)
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            garde.write("champ", "FR12")
        self.assertEqual(garde.constats, [])

    def test_la_casse_et_les_espaces_sont_normalises(self):
        """Ce que SAP fait subir a toute saisie, sans perte d'information."""
        brut = DriverScripte(identite=IA08)
        brut.a_l_ecriture = lambda id, valeur: f"  {valeur.upper()} "
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            garde.write("champ", "fr12")
        self.assertEqual(garde.constats[0].verdict, "normalise")

    def test_la_troncature_est_refusee_par_defaut(self):
        """Constat de revue : accepter n'importe quel prefixe validait « 1 »
        comme normalisation de « 1000 » — une valeur fausse ecrite en
        production sans un mot."""
        brut = DriverScripte(identite=IA08)
        brut.a_l_ecriture = lambda id, valeur: valeur[:1]
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            with self.assertRaises(ItemAbandonne):
                garde.write("quantite", "1000")
        self.assertEqual(garde.constats[0].verdict, "violation")

    def test_la_troncature_n_est_acceptee_que_si_l_etape_la_declare(self):
        """La charge de la preuve revient a qui sait, pas au defaut."""
        brut = DriverScripte(identite=IA08)
        brut.a_l_ecriture = lambda id, valeur: valeur[:4].upper()
        garde = _garde(brut)
        contrat = Contrat(ecran_attendu=IA08.triplet, comparaison="prefixe")
        with garde.sous_contrat(contrat):
            garde.write("champ", "fr1234567")
        self.assertEqual(garde.constats[0].verdict, "tronque")

    def test_la_comparaison_exacte_refuse_toute_transformation(self):
        brut = DriverScripte(identite=IA08)
        brut.a_l_ecriture = lambda id, valeur: valeur.upper()
        garde = _garde(brut)
        contrat = Contrat(ecran_attendu=IA08.triplet, comparaison="exact")
        with garde.sous_contrat(contrat):
            with self.assertRaises(ItemAbandonne):
                garde.write("champ", "fr12")

    def test_la_relecture_ne_se_saute_que_par_derogation(self):
        """Il n'existe plus de drapeau booleen pour la sauter en silence."""
        self.assertNotIn("relire", {c.name for c in fields(Contrat)})

        brut = DriverScripte(identite=IA08)
        brut.a_l_ecriture = lambda id, valeur: ""       # SAP refuse la saisie
        garde = _garde(brut)
        contrat = Contrat(nom="coller", ecran_attendu=IA08.triplet,
                          derogations=(Derogation("relecture", "etape:coller",
                                                  MOTIF),))
        with garde.sous_contrat(contrat):
            garde.write("champ", "FR12")                # ne leve pas
        self.assertEqual([c.verdict for c in garde.constats], ["derogee"])


class TestGarde5Rayon(unittest.TestCase):

    def test_le_plafond_arrete_l_execution(self):
        brut = DriverScripte(identite=IA08)
        garde = _garde(brut, plafond=2)
        contrat = Contrat(ecran_attendu=IA08.triplet, sauvegarde=True)
        with garde.sous_contrat(contrat):
            garde.press("valider")
            garde.press("valider")
            with self.assertRaises(PlafondAtteint):
                garde.press("valider")
        self.assertEqual(garde.sauvegardes, 2)

    def test_sous_le_plafond_rien_ne_bloque(self):
        brut = DriverScripte(identite=IA08)
        garde = _garde(brut, plafond=2)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet,
                                        sauvegarde=True)):
            garde.press("valider")
        self.assertEqual(garde.sauvegardes, 1)

    def test_le_plafond_est_obligatoire(self):
        """Pas de valeur par defaut : l'appelant doit le decider."""
        parametres = inspect.signature(DriverGarde.__init__).parameters
        self.assertIs(parametres["plafond_sauvegardes"].default,
                      inspect.Parameter.empty)

    def test_aucune_derogation_n_est_possible(self):
        self.assertNotIn("rayon", DEROGEABLES)
        with self.assertRaises(DerogationRefusee):
            Derogation(garde="rayon", portee="lot", motif=MOTIF)


class TestDryRun(unittest.TestCase):
    """« Le dry-run est mecanique, pas conventionnel. »"""

    def test_une_sauvegarde_declaree_est_refusee(self):
        brut = DriverScripte(identite=IA08)
        garde = _garde(brut, mode="dry-run")
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet,
                                        sauvegarde=True)):
            with self.assertRaises(RefusDryRun):
                garde.press("valider")

    def test_une_sauvegarde_non_declaree_est_reconnue_d_office(self):
        """Securite contre l'oubli : F11 et le bouton de barre sont connus."""
        brut = DriverScripte(identite=IA08)
        garde = _garde(brut, mode="dry-run")
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            with self.assertRaises(RefusDryRun):
                garde.vkey(11)
            with self.assertRaises(RefusDryRun):
                garde.press("wnd[0]/tbar[0]/btn[11]")

    def test_le_refus_de_dry_run_n_est_pas_un_echec_rattrapable(self):
        from falcon.noyau import Echec, Refus
        self.assertTrue(issubclass(RefusDryRun, Refus))
        self.assertFalse(issubclass(RefusDryRun, Echec))

    def test_la_lecture_reste_possible_en_dry_run(self):
        brut = DriverScripte(identite=IA08, valeurs={"champ": "x"})
        garde = _garde(brut, mode="dry-run")
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            self.assertEqual(garde.read("champ"), "x")


class TestSauvegardeAnnonceeAvantLActe(unittest.TestCase):
    """Constat de revue : une sauvegarde reussie suivie d'une garde qui leve
    ne laissait aucune trace, et l'item repartait en `en_cours` — donc rejoue,
    donc ecrit deux fois dans SAP."""

    def test_la_sauvegarde_est_annoncee_avant_l_action(self):
        brut = DriverScripte(identite=IA08)
        vus: list[str] = []
        brut.apres_action = lambda d, geste, cible: vus.append("action")
        garde = DriverGarde(brut, Registre.charger(), plafond_sauvegardes=10,
                            noter=lambda c: vus.append(c.verdict))
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet,
                                        sauvegarde=True)):
            garde.press("valider")
        self.assertEqual(vus[0], "sauvegarde_imminente")
        self.assertEqual(vus[1], "action")

    def test_l_annonce_survit_a_une_garde_qui_leve_apres_coup(self):
        """Le cas exact : SAP a ecrit, puis une modale imprevue arrete tout."""
        brut = DriverScripte(identite=IA08)

        def surgir(driver, geste, cible):
            driver.fenetres = (Fenetre(id="wnd[0]"), Fenetre(id="wnd[1]"))

        brut.apres_action = surgir
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet,
                                        sauvegarde=True)):
            with self.assertRaises(FenetreImprevue):
                garde.press("valider")

        annonces = [c for c in garde.constats
                    if c.verdict == "sauvegarde_imminente"]
        self.assertEqual(len(annonces), 1)


class TestPipelineNePeutPasContourner(unittest.TestCase):
    """Les barrieres cumulees du 5.2, verifiees mecaniquement."""

    def test_le_poste_n_expose_que_la_surface_du_driver(self):
        """Pas de sous_contrat, pas d'acces au driver brut, pas de compteur."""
        exposees = {n for n in dir(Poste) if not n.startswith("_")}
        self.assertEqual(exposees, set(Driver.__abstractmethods__))

    def test_le_poste_ne_permet_pas_de_changer_de_contrat(self):
        brut = DriverScripte(identite=AUTRE, valeurs={"champ": "x"})
        garde = _garde(brut)
        poste = Poste(garde)
        self.assertFalse(hasattr(poste, "sous_contrat"))
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            with self.assertRaises(EcartIdentite):
                poste.read("champ")          # l'etape reste sous les gardes

    def test_le_driver_brut_n_est_pas_accessible_par_inadvertance(self):
        brut = DriverScripte(identite=IA08)
        garde = _garde(brut)
        for nom in ("brut", "driver", "_brut", "sous_jacent"):
            self.assertFalse(hasattr(garde, nom), nom)

    def test_le_driver_garde_est_substituable_a_un_driver(self):
        """Meme surface : le code appelant ne sait pas s'il est garde."""
        garde = _garde(DriverScripte(identite=IA08))
        self.assertIsInstance(garde, Driver)

    def test_une_derogation_exige_un_motif_qui_dit_quelque_chose(self):
        with self.assertRaises(DerogationRefusee):
            Derogation(garde="relecture", portee="etape:x", motif="ok")

    def test_les_gardes_non_derogeables_sont_celles_qui_arretent_tout(self):
        self.assertEqual(DEROGEABLES, {"statut", "fenetre", "relecture"})


if __name__ == "__main__":
    unittest.main()
