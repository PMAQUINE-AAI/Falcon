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

from falcon.controleur import (
    DEROGEABLES, Contrat, Derogation, DerogationRefusee, DriverGarde, Poste,
)
from falcon.couture import Driver
from falcon.couture.double import DriverScripte
from falcon.noyau import (
    EcartIdentite, Fenetre, FenetreImprevue, Identite, IncidentBloquant,
    PlafondAtteint, RefusDryRun, Statut,
)
from falcon.taxonomie import Registre

IA08 = Identite(transaction="IA08", programme="RIPLKO10", dynpro="1000")
AUTRE = Identite(transaction="CL02", programme="SAPLCLFM", dynpro="0100")

MOTIF = "l'editeur SAPscript n'est pas adressable, verifie par retelechargement"


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

    def test_navigation_libre_n_est_pas_gardee(self):
        """Une etape qui ne sait pas encore ou elle atterrit."""
        brut = DriverScripte(identite=AUTRE, valeurs={"champ": "x"})
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=None)):
            self.assertEqual(garde.read("champ"), "x")

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
            garde.press("executer")          # entree connue : poursuit
        constat = garde.constats[0]
        self.assertEqual(constat.garde, "statut")
        self.assertEqual(constat.taxonomie.entree,
                         "ia08_selection_vide_sans_message")
        self.assertEqual(constat.taxonomie.politique.item, "ko")

    def test_une_derogation_evite_le_blocage_et_laisse_une_trace(self):
        brut = DriverScripte(identite=IA08,
                             statut=Statut(type="E", id="ZZ", numero="999"))
        garde = _garde(brut)
        contrat = Contrat(ecran_attendu=IA08.triplet,
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
        contrat = Contrat(ecran_attendu=IA08.triplet,
                          fenetres_attendues=("wnd[0]", "wnd[1]"))
        with garde.sous_contrat(contrat):
            garde.press("bouton")
        self.assertEqual(garde.constats, [])


class TestGarde4Relecture(unittest.TestCase):
    """« Ecrire sans que ca prenne est une classe de bug deja rencontree. »"""

    def test_une_ecriture_qui_ne_prend_pas_est_detectee(self):
        brut = DriverScripte(identite=IA08)
        brut.a_l_ecriture = lambda id, valeur: ""      # SAP refuse la saisie
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            garde.write("champ", "FR12")               # entree connue : poursuit
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

    def test_la_troncature_de_sap_est_toleree_mais_tracee(self):
        """Une comparaison stricte rendrait la garde insupportable et
        quelqu'un la desactiverait ; une comparaison laxiste et muette
        laisserait passer une vraie divergence."""
        brut = DriverScripte(identite=IA08)
        brut.a_l_ecriture = lambda id, valeur: valeur[:4].upper()
        garde = _garde(brut)
        with garde.sous_contrat(Contrat(ecran_attendu=IA08.triplet)):
            garde.write("champ", "fr1234567")
        self.assertEqual(garde.constats[0].verdict, "normalise")

    def test_la_comparaison_exacte_refuse_la_troncature(self):
        brut = DriverScripte(identite=IA08)
        brut.a_l_ecriture = lambda id, valeur: valeur[:4].upper()
        garde = _garde(brut)
        contrat = Contrat(ecran_attendu=IA08.triplet, comparaison="exact")
        with garde.sous_contrat(contrat):
            garde.write("champ", "fr1234567")
        self.assertEqual(garde.constats[0].verdict, "violation")

    def test_la_relecture_est_active_par_defaut(self):
        """Le defaut penche du cote sur : l'oubli doit couter, pas passer."""
        self.assertTrue(Contrat().relire)


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
