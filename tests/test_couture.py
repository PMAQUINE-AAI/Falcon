"""La couture : surface figee, et rien d'implementable a moitie.

La specification qualifie la couture d'irreversible — la retrofiter sur du
code deja ecrit coute cher. Deux tests rendent ce caractere visible : la
surface est epinglee, donc l'etendre est un geste delibere qui met a jour ce
fichier ; et une implementation partielle ne s'instancie pas, donc personne
ne livre un driver a trous.
"""

from __future__ import annotations

import unittest

from falcon.couture import Driver

# Surface arretee. Toute modification de cet ensemble est un changement de
# contrat : elle doit passer par une decision inscrite dans la specification.
SURFACE = {
    # les huit de la specification initiale
    "screen", "fields", "read", "write", "press", "vkey", "status", "windows",
    # extension ratifiee : sans elles, la premiere pipeline livree n'est pas
    # exprimable — son audit lit une grille ALV, et les cases de selection
    # doivent etre positionnees explicitement a chaque appel
    "select", "set_checked",
    "grid_rows", "grid_columns", "grid_read",
    "table_visible_rows", "table_scroll",
}


class TestSurface(unittest.TestCase):

    def test_surface_figee(self):
        self.assertEqual(set(Driver.__abstractmethods__), SURFACE)

    def test_les_deux_familles_de_tableau_sont_nommees_distinctement(self):
        """Confondre l'ALV et le table control ne leve aucune exception.

        L'ALV s'indexe en absolu sans defilement, le table control en index
        visible avec defilement explicite. Des prefixes distincts rendent la
        confusion visible a la relecture.
        """
        grille = {n for n in SURFACE if n.startswith("grid_")}
        table = {n for n in SURFACE if n.startswith("table_")}
        self.assertTrue(grille and table)
        self.assertEqual(grille & table, set())
        # Le defilement n'existe que du cote table control.
        self.assertIn("table_scroll", table)
        self.assertEqual({n for n in grille if "scroll" in n}, set())


class TestImplementation(unittest.TestCase):

    def test_l_interface_ne_s_instancie_pas(self):
        with self.assertRaises(TypeError):
            Driver()                                  # type: ignore[abstract]

    def test_une_implementation_partielle_ne_s_instancie_pas(self):
        """Un driver a trous doit echouer a la construction, pas au premier
        appel manquant en pleine session."""

        class DriverIncomplet(Driver):
            def screen(self): ...

        with self.assertRaises(TypeError):
            DriverIncomplet()                         # type: ignore[abstract]

    def test_une_implementation_complete_s_instancie(self):
        corps = {nom: (lambda self, *a, **k: None) for nom in SURFACE}
        DriverComplet = type("DriverComplet", (Driver,), corps)
        self.assertIsInstance(DriverComplet(), Driver)


if __name__ == "__main__":
    unittest.main()
