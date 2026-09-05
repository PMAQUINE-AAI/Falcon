"""Esquisses d'ecran depuis une trace : une liste de travail, pas un releve.

Le lot precedent a etabli qu'une trace ne dit ni l'identite des ecrans, ni les
champs presents. Ce lot en tire les consequences, et la propriete centrale est
negative : **rien de ce qui sort d'ici ne peut satisfaire une garde
d'identite**, et pas par convention — par deux mecanismes independants.

Le decoupage en visites, lui, porte un piege d'un cran : `/nIH06` se tape
depuis l'ecran d'AVANT. L'attribuer a l'ecran de saisie etiquette une esquisse
d'une transaction ou elle n'a jamais ete vue, sans que rien ne leve.
"""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path

from falcon.catalogue import (
    ESQUISSE, OBSERVEE, CatalogueInvalide, Depot, clef_de,
)
from falcon.noyau import Champ, Ecran, Identite, empreinte
from falcon.trace import lire
from falcon.trace.esquisse import (
    CHAMP_DE_COMMANDE, NAVIGATION, NON_RENSEIGNE, apercu, deposer, esquisses,
    visites,
)

from tests.test_trace import MEGATRACE, vbs


class TestDecoupage(unittest.TestCase):

    def test_une_visite_se_termine_sur_le_geste_de_navigation(self):
        """C'est sur l'ecran d'AVANT qu'on a appuye sur le bouton."""
        trace = lire(vbs('session.findById("wnd[0]/usr/txtA").text = "x"',
                         'session.findById("wnd[0]/tbar[0]/btn[11]").press',
                         'session.findById("wnd[0]/usr/txtB").text = "y"'))
        premiere, seconde = visites(trace)
        self.assertEqual([g.verbe for g in premiere.gestes], ["text", "press"])
        self.assertEqual([g.verbe for g in seconde.gestes], ["text"])

    def test_un_changement_de_fenetre_ouvre_une_visite(self):
        trace = lire(vbs('session.findById("wnd[0]/usr/txtA").text = "x"',
                         'session.findById("wnd[1]/usr/txtB").text = "y"'))
        self.assertEqual([v.fenetre for v in visites(trace)],
                         ["wnd[0]", "wnd[1]"])

    def test_le_code_transaction_vaut_pour_la_visite_suivante(self):
        """Le piege d'un cran.

        Taper `/nIH06` se fait depuis le menu ou la transaction precedente.
        L'attribuer a l'ecran de saisie etiquetterait une esquisse d'une
        transaction ou elle n'a jamais ete vue — et rien ne leverait.
        """
        trace = lire(vbs(
            f'session.findById("wnd[0]{CHAMP_DE_COMMANDE}").text = "/nIH06"',
            'session.findById("wnd[0]").sendVKey 0',
            'session.findById("wnd[0]/usr/chkDY_MAB").selected = true',
            'session.findById("wnd[0]/tbar[1]/btn[17]").press'))
        saisie, suivante = visites(trace)
        self.assertEqual(saisie.transaction, "")
        self.assertEqual(suivante.transaction, "IH06")

    def test_un_retour_au_menu_rend_la_transaction_inconnue(self):
        """`/n` seul ne nomme aucune transaction : on ne la conserve pas."""
        trace = lire(vbs(
            f'session.findById("wnd[0]{CHAMP_DE_COMMANDE}").text = "/nIH06"',
            'session.findById("wnd[0]").sendVKey 0',
            f'session.findById("wnd[0]{CHAMP_DE_COMMANDE}").text = "/n"',
            'session.findById("wnd[0]").sendVKey 0',
            'session.findById("wnd[0]/usr/txtA").text = "x"',
            'session.findById("wnd[0]").sendVKey 0'))
        self.assertEqual([v.transaction for v in visites(trace)],
                         ["", "IH06", ""])

    def test_une_fenetre_nue_n_est_pas_un_champ(self):
        """`sendVKey` et `maximize` s'adressent a la fenetre, pas a un champ."""
        trace = lire(vbs('session.findById("wnd[0]").maximize',
                         'session.findById("wnd[0]").sendVKey 0'))
        self.assertEqual(visites(trace)[0].cibles, ())

    def test_les_cibles_sont_dedoublonnees_dans_l_ordre(self):
        trace = lire(vbs('session.findById("wnd[0]/usr/txtA").text = "x"',
                         'session.findById("wnd[0]/usr/txtA").setFocus',
                         'session.findById("wnd[0]/usr/txtB").text = "y"'))
        self.assertEqual(visites(trace)[0].cibles,
                         ("wnd[0]/usr/txtA", "wnd[0]/usr/txtB"))

    def test_le_decoupage_est_pessimiste_pas_optimiste(self):
        """Une coupure de trop fragmente ; une coupure de moins melange deux
        ecrans en un et produit une empreinte qui ne correspond a rien. Des
        deux erreurs, seule la seconde est silencieuse."""
        self.assertIn("sendVKey", NAVIGATION)


class TestEsquisses(unittest.TestCase):

    def test_le_programme_et_le_dynpro_ne_sont_pas_conjectures(self):
        trace = lire(vbs('session.findById("wnd[0]/usr/txtA").text = "x"'))
        clef = esquisses(trace)[0].clef
        self.assertEqual((clef.programme, clef.dynpro),
                         (NON_RENSEIGNE, NON_RENSEIGNE))

    def test_le_type_des_champs_n_est_pas_conjecture(self):
        """`txt` dit bien GuiTextField, mais `shellcont/shell` ne dit pas
        lequel. Un type faux serait pire qu'un type absent : il aurait l'air
        d'un releve."""
        trace = lire(vbs('session.findById("wnd[0]/usr/txtA").text = "x"'))
        self.assertEqual(esquisses(trace)[0].champs[0].type, "")

    def test_une_visite_sans_champ_ne_produit_pas_d_esquisse(self):
        trace = lire(vbs('session.findById("wnd[0]").maximize'))
        self.assertEqual(esquisses(trace), ())

    def test_le_meme_ecran_visite_deux_fois_ne_donne_qu_une_esquisse(self):
        ligne = 'session.findById("wnd[0]/usr/txtA").text = "x"'
        saut = 'session.findById("wnd[0]").sendVKey 0'
        trace = lire(vbs(ligne, saut, ligne, saut))
        self.assertEqual(len(visites(trace)), 2)
        self.assertEqual(len(esquisses(trace)), 1)

    def test_toute_esquisse_porte_la_source_esquisse(self):
        for esquisse in esquisses(lire(MEGATRACE)):
            self.assertEqual(esquisse.source, ESQUISSE)


class TestGardeDIdentite(unittest.TestCase):
    """La propriete du lot, et elle est negative."""

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.depot = Depot(Path(dossier.name) / "catalogue")
        self.trace = lire(MEGATRACE)

    def test_deposer_verse_en_quarantaine_pas_au_catalogue(self):
        clefs = deposer(self.trace, self.depot)
        self.assertTrue(clefs)
        for clef in clefs:
            with self.subTest(clef=str(clef)):
                self.assertIsNone(self.depot.pour_edition(clef))
                self.assertIsNotNone(
                    Depot(self.depot.quarantaine).pour_edition(clef))

    def test_pour_garde_refuse_une_esquisse_meme_promue(self):
        """Promouvoir dit « j'ai vu le fichier », pas « j'ai vu l'ecran »."""
        clef = deposer(self.trace, self.depot)[0]
        self.depot.promouvoir(clef)
        self.assertIsNotNone(self.depot.pour_edition(clef))     # servie a l'humain
        with self.assertRaises(CatalogueInvalide) as capture:
            self.depot.pour_garde(clef)
        self.assertIn("esquisse", str(capture.exception))

    def test_l_empreinte_d_une_esquisse_ne_peut_pas_valoir_celle_d_un_releve(self):
        """La seconde protection, independante de la source.

        L'empreinte porte sur les identifiants PRESENTS ; une esquisse n'en
        connait qu'un sous-ensemble — ceux qui ont ete TOUCHES. Meme si
        quelqu'un forcait la source a « observee », la clef ne tomberait pas
        sur la meme variante.
        """
        touches = ("wnd[0]/usr/txtA", "wnd[0]/usr/txtB")
        presents = touches + ("wnd[0]/usr/txtJamaisTouche",)
        self.assertNotEqual(empreinte(touches), empreinte(presents))

    def test_une_esquisse_forcee_en_observee_ne_couvre_pas_l_ecran_reel(self):
        """La demonstration bout a bout : on retire la premiere protection,
        et la seconde tient encore.

        L'esquisse est versee au catalogue avec la source `observee` — ce que
        rien dans FALCON ne fait, mais qu'une main pourrait faire dans le
        YAML. Elle n'y couvre toujours pas l'ecran reel : sa clef n'est pas la
        meme, parce que son empreinte porte sur les champs TOUCHES.
        """
        trace = lire(vbs('session.findById("wnd[0]/usr/txtA").text = "x"'))
        forcee = dataclasses.replace(esquisses(trace)[0], source=OBSERVEE)
        self.depot.enregistrer(forcee)

        reel = Ecran(
            identite=Identite(transaction=forcee.clef.transaction,
                              programme=forcee.clef.programme,
                              dynpro=forcee.clef.dynpro),
            champs=(Champ(id="wnd[0]/usr/txtA"), Champ(id="wnd[0]/usr/txtB")))
        self.assertNotEqual(clef_de(reel).empreinte, forcee.clef.empreinte)
        with self.assertRaises(CatalogueInvalide) as capture:
            self.depot.pour_garde(clef_de(reel))
        self.assertIn("absente", str(capture.exception))


class TestApercu(unittest.TestCase):

    def test_l_apercu_compte_visites_et_esquisses(self):
        texte = apercu(lire(MEGATRACE))
        self.assertIn("visites", texte)
        self.assertIn("esquisses", texte)

    def test_l_apercu_dit_ce_que_la_trace_ne_dit_pas(self):
        self.assertIn(NON_RENSEIGNE, apercu(lire(MEGATRACE)))


class TestTraceObservee(unittest.TestCase):

    def setUp(self):
        self.trace = lire(MEGATRACE)
        self.visites = visites(self.trace)

    def test_le_decoupage_couvre_tous_les_gestes_sans_recouvrement(self):
        """Un geste perdu par le decoupage serait un champ absent de
        l'esquisse — invisible, et le catalogue serait faux d'un champ."""
        rangs = [g.ordre for v in self.visites for g in v.gestes]
        self.assertEqual(rangs, list(range(1, len(self.trace.gestes) + 1)))

    def test_les_quatre_transactions_de_la_trace_sont_retrouvees(self):
        trouvees = {v.transaction for v in self.visites if v.transaction}
        self.assertEqual(trouvees, {"IH06", "IH08", "IW39", "IW29", "IW2ç"})

    def test_la_faute_de_frappe_apparait_comme_une_transaction(self):
        """`/nIW2ç` : SAP refuse et reste ou il est, la trace ne le dit pas.

        Une transaction conjecturee reste une conjecture — la lister telle
        quelle donne a l'humain de quoi voir la faute ; la corriger en
        silence lui cacherait qu'une conjecture a ete faite.
        """
        self.assertIn("IW2ç", {v.transaction for v in self.visites})

    def test_le_premier_ecran_est_sans_transaction(self):
        """Avant le premier code, on est sur le menu : rien ne le nomme."""
        self.assertEqual(self.visites[0].transaction, "")

    def test_aucune_esquisse_n_est_observee(self):
        self.assertNotIn(OBSERVEE,
                         {e.source for e in esquisses(self.trace)})


if __name__ == "__main__":
    unittest.main()
