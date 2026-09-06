"""Le bundle : un fichier unique executable (§6).

« Le depot est modulaire, la livraison est un fichier unique executable. » La
contrainte d'autonomie au deploiement se traite **a la construction**, pas
dans l'organisation du code source.

**La preuve tient a un drapeau : `-S`.** Le bundle est lance sans
`site-packages`, donc sans le PyYAML de la machine. S'il tourne quand meme,
c'est que PyYAML voyage bien dans l'archive — et pas que l'interpreteur de
test se debrouille. Lancer sans ce drapeau ne prouverait rien du tout.

Ces tests construisent reellement l'archive. Ils sont donc plus lents que le
reste de la suite ; c'est le prix d'une verification qui porte sur le
livrable, et non sur l'intention de le produire.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from outils.embarquer import ENTREE, EXCLUS, POINT_D_ENTREE, construire

RACINE = Path(__file__).resolve().parent.parent
TRACE = RACINE / "tests" / "fixtures" / "traces" / "megatrace_2026-09.vbs"


class Base(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._dossier = tempfile.TemporaryDirectory()
        cls.bundle = construire(Path(cls._dossier.name) / "falcon.pyz")

    @classmethod
    def tearDownClass(cls):
        cls._dossier.cleanup()

    def _lancer(self, *arguments: str, isole: bool = True):
        """Lance le bundle. `isole` retire site-packages : c'est la preuve."""
        commande = [sys.executable]
        if isole:
            commande.append("-S")
        return subprocess.run([*commande, str(self.bundle), *arguments],
                              cwd=RACINE, capture_output=True, text=True)


class TestArchive(Base):

    def test_le_bundle_est_un_fichier_unique(self):
        self.assertTrue(self.bundle.is_file())
        self.assertTrue(zipfile.is_zipfile(self.bundle))

    def test_falcon_et_pyyaml_y_sont(self):
        noms = zipfile.ZipFile(self.bundle).namelist()
        self.assertTrue(any(n.startswith("falcon/") for n in noms))
        self.assertTrue(any(n.startswith("yaml/") for n in noms),
                        "PyYAML n'est pas embarque : le bundle exigerait un "
                        "`pip install` sur le poste")

    def test_aucun_pycache_ni_binaire(self):
        """Les `__pycache__` sont lies a une version d'interpreteur, les
        extensions binaires a une plateforme. Le bundle traverse les deux."""
        for nom in zipfile.ZipFile(self.bundle).namelist():
            with self.subTest(entree=nom):
                self.assertNotIn("__pycache__", nom)
                self.assertFalse(nom.endswith((".pyc", ".so", ".pyd", ".dll")))

    def test_l_accelerateur_c_de_pyyaml_est_ecarte(self):
        """Embarquer un `_yaml` compile sous Linux dans un bundle destine a
        Windows produirait une archive qui a l'air complete et qui echoue a
        l'import."""
        for nom in zipfile.ZipFile(self.bundle).namelist():
            self.assertNotIn("_yaml", nom)

    def test_les_exclusions_couvrent_les_deux_familles(self):
        self.assertIn("__pycache__", EXCLUS)
        for extension in ("*.pyc", "*.so", "*.pyd", "*.dll"):
            self.assertIn(extension, EXCLUS)

    def test_le_point_d_entree_est_la_ligne_de_commande(self):
        self.assertEqual(ENTREE, "falcon.commandes.principal:main")

    def test_le_point_d_entree_transmet_le_code_de_retour(self):
        """Defaut trouve en ecrivant les tests d'execution : le gabarit de
        `zipapp` appelle `main()` en jetant ce qu'elle rend. Le bundle sortait
        toujours a 0 — une trace illisible, une session absente, une commande
        refusee, tout ressortait « reussi ». Un script qui s'appuie sur le code
        de retour aurait cru le lot passe.
        """
        self.assertIn("sys.exit(main())", POINT_D_ENTREE)
        ecrit = zipfile.ZipFile(self.bundle).read("__main__.py").decode("utf-8")
        self.assertIn("sys.exit(main())", ecrit)


class TestExecution(Base):
    """Sans `site-packages`. C'est ce qui rend ces tests probants."""

    def test_l_aide_repond(self):
        fini = self._lancer("--aide")
        self.assertEqual(fini.returncode, 0, fini.stderr)
        self.assertIn("FALCON", fini.stdout)

    def test_une_trace_se_lit_sans_installation(self):
        fini = self._lancer("inventaire", str(TRACE))
        self.assertEqual(fini.returncode, 0, fini.stderr)
        self.assertIn("Toutes les lignes sont appariees", fini.stdout)

    def test_pyyaml_vient_bien_de_l_archive(self):
        """`brouillon` produit du YAML : sans PyYAML embarque, la commande
        leverait un `ImportError` que `-S` rend certain."""
        fini = self._lancer("brouillon", str(TRACE))
        self.assertEqual(fini.returncode, 0, fini.stderr)
        self.assertIn("version: 1", fini.stdout)
        self.assertNotIn("ImportError", fini.stderr)

    def test_sans_commande_l_aide_sort_en_erreur(self):
        self.assertEqual(self._lancer().returncode, 2)

    def test_la_console_refuse_un_flux_non_interactif(self):
        """Meme comportement que depuis les sources : le bundle ne change pas
        ce que fait le programme, seulement la facon dont il voyage."""
        fini = self._lancer("console")
        self.assertEqual(fini.returncode, 2)
        self.assertIn("terminal interactif", fini.stderr)

    def test_diagnostiquer_dit_ce_qui_manque_sur_le_poste(self):
        """pywin32 n'est pas embarque — une extension binaire Windows liee a
        une version d'interpreteur ne s'embarque pas. L'erreur doit donner la
        ligne de commande a taper."""
        fini = self._lancer("diagnostiquer")
        self.assertEqual(fini.returncode, 1)
        self.assertIn("pywin32", fini.stderr)
        self.assertNotIn("Traceback", fini.stderr)


if __name__ == "__main__":
    unittest.main()
