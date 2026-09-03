"""La carte des controles doit rester chargeable et complete.

Les adaptateurs d'ecran lisent ces cles : si l'une disparait, le programme
echouerait en session SAP, la ou c'est le plus cher.
"""

import unittest

from sapharness import CHEMIN_CARTE_DEFAUT, charger_carte


class TestCarte(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.carte = charger_carte()

    def test_carte_par_defaut_presente(self):
        self.assertTrue(CHEMIN_CARTE_DEFAUT.exists(), CHEMIN_CARTE_DEFAUT)

    def test_sections_attendues(self):
        for section in ("systeme", "ia08_selection", "ia08_resultat",
                        "operations_synthese", "operation_detail",
                        "editeur_sapscript", "dialogue_fichier", "textes_longs"):
            with self.subTest(section=section):
                self.assertIn(section, self.carte)

    def test_indexation_declaree_par_tableau(self):
        """ALV et table control ne se pilotent pas de la meme facon."""
        self.assertEqual(self.carte["ia08_resultat"]["indexation"], "absolue")
        self.assertEqual(self.carte["operations_synthese"]["indexation"],
                         "visible_avec_defilement")

    def test_boutons_dangereux_documentes(self):
        """btn[7] change de sens d'un ecran a l'autre : il doit rester signale."""
        self.assertIn("wnd[0]/tbar[1]/btn[7]",
                      self.carte["operations_synthese"]["boutons_dangereux"])
        self.assertIn("wnd[0]/tbar[1]/btn[7]",
                      self.carte["editeur_sapscript"]["boutons_dangereux"])

    def test_detail_resolu_par_suffixe(self):
        """Le numero de sous-ecran varie : aucun chemin fige."""
        self.assertEqual(self.carte["operation_detail"]["resolution"],
                         "par_suffixe")

    def test_editeur_non_adressable(self):
        self.assertIs(self.carte["editeur_sapscript"]["adressable"], False)


if __name__ == "__main__":
    unittest.main()
