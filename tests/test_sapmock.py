"""Non-regression du simulateur : les mecaniques pieges doivent rester pieges.

Chaque test correspond a un defaut qui, en production, ne leve aucune
exception. Si le simulateur cesse de reproduire la mecanique, le test tombe.
"""

import unittest

from sapharness import Ecran, ErreurSimulee, Grille, Journal, Monde, TableControl


def _monde_synthese(nb_lignes=12, visibles=5):
    lignes = [{"VORNR": f"{10 * (i + 1):04d}", "TXTKZ": i % 2 == 0}
              for i in range(nb_lignes)]
    monde = Monde()
    table = TableControl("wnd[0]/usr/tbl", ["VORNR", "TXTKZ"], lignes,
                         visibles=visibles, monde=monde)
    ecran = Ecran("synthese", "SAPLCPDI", 3400)
    ecran.objet("wnd[0]/usr/tbl", table)
    monde.ajouter_ecran(ecran)
    return monde, table


class TestTableControl(unittest.TestCase):
    """Table control : index de ligne VISIBLE, defilement explicite."""

    def setUp(self):
        self.monde, self.table = _monde_synthese()
        self.session = self.monde.session()

    def test_rang_zero_est_la_premiere_ligne(self):
        self.assertEqual(
            self.session.findById("wnd[0]/usr/tbl/txtVORNR[0,0]").Text, "0010")

    def test_rang_hors_fenetre_visible_leve(self):
        with self.assertRaises(ErreurSimulee):
            self.session.findById("wnd[0]/usr/tbl/txtVORNR[0,7]")

    def test_defilement_decale_l_origine(self):
        self.table.VerticalScrollbar.Position = 5
        self.assertEqual(
            self.session.findById("wnd[0]/usr/tbl/txtVORNR[0,0]").Text, "0060")

    def test_case_a_cocher_lue_comme_booleen(self):
        """TXTKZ vaut True une ligne sur deux : lu comme bool, pas comme texte."""
        self.assertIs(
            self.session.findById("wnd[0]/usr/tbl/chkTXTKZ[1,0]").Selected, True)
        self.assertIs(
            self.session.findById("wnd[0]/usr/tbl/chkTXTKZ[1,1]").Selected, False)

    def test_case_a_cocher_suit_le_defilement(self):
        """Apres defilement, la ligne visible 0 est la 6e ligne absolue."""
        self.table.VerticalScrollbar.Position = 5
        self.assertIs(
            self.session.findById("wnd[0]/usr/tbl/chkTXTKZ[1,0]").Selected, False)

    def test_rowcount_compte_les_lignes_vides(self):
        """RowCount n'est pas un nombre d'operations : il ne pilote rien."""
        monde, table = _monde_synthese(nb_lignes=3, visibles=20)
        self.assertEqual(table.RowCount, 20)


class TestGrilleALV(unittest.TestCase):
    """ALV : index ABSOLU, aucun defilement, aucun ID par cellule."""

    def setUp(self):
        self.grille = Grille(
            "wnd[0]/usr/cntlGRID1/shellcont/shell",
            ["PLNNR", "PLNAL"],
            [{"PLNNR": f"MEMAC{100 + i}", "PLNAL": "1"} for i in range(60)])

    def test_ligne_lointaine_lisible_sans_defilement(self):
        self.assertEqual(self.grille.GetCellValue(57, "PLNNR"), "MEMAC157")

    def test_ligne_inexistante_leve(self):
        with self.assertRaises(ErreurSimulee):
            self.grille.GetCellValue(60, "PLNNR")


class TestPileModale(unittest.TestCase):
    """L'export enchaine deux modales : la pile doit etre traversee, pas devinee."""

    def setUp(self):
        self.monde = Monde()
        self.monde.ajouter_ecran(Ecran("editeur", "SAPLSTXX", 2101))
        self.monde.ajouter_ecran(
            Ecran("format", "SAPLSTXX", 0).bouton(
                "wnd[1]/tbar[0]/btn[0]", action=lambda: self.monde.empiler("fichier")))
        self.monde.ajouter_ecran(
            Ecran("fichier", "SAPLSTXX", 0)
            .champ("wnd[2]/usr/ctxtITCTK-TDFILENAME")
            .bouton("wnd[2]/tbar[0]/btn[0]", action=self.monde.vider_modales))
        self.session = self.monde.session()

    def test_fenetre_non_empilee_leve(self):
        with self.assertRaises(ErreurSimulee):
            self.session.findById("wnd[1]/tbar[0]/btn[0]")

    def test_sequence_format_puis_fichier(self):
        self.monde.empiler("format")
        self.session.findById("wnd[1]/tbar[0]/btn[0]").press()
        self.session.findById(
            "wnd[2]/usr/ctxtITCTK-TDFILENAME").Text = r"C:\Temp\x.rtf"
        self.session.findById("wnd[2]/tbar[0]/btn[0]").press()
        self.assertEqual(self.monde.modales, [])


class TestInvariantsJournal(unittest.TestCase):
    """Les assertions portent sur les GESTES, pas sur le resultat produit."""

    def setUp(self):
        self.monde = Monde()
        self.monde.ajouter_ecran(
            Ecran("detail", "SAPLCPDO", 3370).bouton("wnd[0]/tbar[1]/btn[7]"))
        self.monde.ajouter_ecran(
            Ecran("synthese", "SAPLCPDI", 3400).bouton("wnd[0]/tbar[1]/btn[7]"))
        self.session = self.monde.session()

    def test_pression_legitime_acceptee(self):
        self.monde.aller("detail")
        self.session.findById("wnd[0]/tbar[1]/btn[7]").press()
        self.monde.journal.assert_jamais("wnd[0]/tbar[1]/btn[7]",
                                         hors_ecran="detail")

    def test_bouton_ambigu_hors_de_son_ecran_detecte(self):
        """Sur la synthese, btn[7] insere une operation : silencieux en SAP."""
        self.monde.aller("synthese")
        self.session.findById("wnd[0]/tbar[1]/btn[7]").press()
        with self.assertRaises(AssertionError):
            self.monde.journal.assert_jamais("wnd[0]/tbar[1]/btn[7]",
                                             hors_ecran="detail")

    def test_sauvegarde_surnumeraire_detectee(self):
        journal = Journal()
        journal.noter("synthese", "save", "wnd[0]/tbar[0]/btn[11]")
        journal.assert_au_plus("save", 1)
        journal.noter("synthese", "save", "wnd[0]/tbar[0]/btn[11]")
        with self.assertRaises(AssertionError):
            journal.assert_au_plus("save", 1)

    def test_dry_run_n_ecrit_rien(self):
        monde, _ = _monde_synthese()
        session = monde.session()
        session.findById("wnd[0]/usr/tbl/txtVORNR[0,0]").Text  # lecture seule
        self.assertEqual(monde.journal.compter("saisie"), 0)


if __name__ == "__main__":
    unittest.main()
