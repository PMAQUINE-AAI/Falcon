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
import textwrap
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

    #: Sonde lancee AVEC LE BUNDLE POUR SEULE SOURCE de `falcon`.
    #:
    #: Chaque sonde verifie d'abord d'ou vient le paquet. Sans cette
    #: assertion, un `sys.path` mal isole laisse le depot repondre a la place
    #: de l'archive — et le test passe en ne prouvant rien. C'est exactement
    #: ce qui est arrive en ecrivant ces tests.
    SONDE_REGISTRE = textwrap.dedent("""
        import sys
        from falcon.taxonomie import Registre
        assert ".pyz" in sys.modules["falcon"].__file__, \\
            sys.modules["falcon"].__file__
        print("entrees", len(Registre.charger().entrees))
        """)

    SONDE_CARTE = textwrap.dedent("""
        import sys
        from falcon.volumique import charger_carte
        assert ".pyz" in sys.modules["falcon"].__file__, \\
            sys.modules["falcon"].__file__
        print("manquants", len(charger_carte().manquants))
        """)

    SONDE_EXECUTION = textwrap.dedent("""
        import sys, tempfile, pathlib
        from falcon.couture.double import DriverScripte
        from falcon.moteur import executer
        from falcon.noyau import Identite
        from falcon.pipeline import charger
        assert ".pyz" in sys.modules["falcon"].__file__, \\
            sys.modules["falcon"].__file__

        d = pathlib.Path(tempfile.mkdtemp())
        (d / "p.yaml").write_text(
            'version: 1\\n'
            'nom: essai\\n'
            'classe: iterative\\n'
            'cles: [site]\\n'
            'plafond_items: 9\\n'
            'plafond_sauvegardes: 9\\n'
            'etapes:\\n'
            '  - nom: sauver\\n'
            '    action: press\\n'
            '    cible: "wnd[0]/tbar[0]/btn[11]"\\n'
            '    sauvegarde: true\\n'
            '    ecran: {transaction: IA08, programme: R, dynpro: "1000"}\\n',
            encoding="utf-8")
        (d / "jeu.csv").write_text("site\\nK75\\n", encoding="utf-8")

        def brut():
            return DriverScripte(identite=Identite(
                transaction="IA08", programme="R", dynpro="1000"))

        # Repetition a blanc PUIS run : la garde 5.5 l'exige, et le parcours
        # doit valoir depuis l'archive comme depuis le depot.
        pipeline = charger(d / "p.yaml")
        blanc = executer(pipeline, d / "jeu.csv", brut(),
                         journal=d / "j.jsonl", mode="dry-run")
        resultat = executer(pipeline, d / "jeu.csv", brut(),
                            journal=d / "j.jsonl")
        print("blanc", blanc.etat, "etat", resultat.etat,
              "ok", resultat.compteurs["ok"])
        """)

    def _sonder(self, code: str):
        """Lance `code` avec le bundle pour seule source de `falcon`.

        `cwd` est ailleurs que le depot et `-S` retire site-packages : si
        quelque chose s'importe, ca vient de l'archive.
        """
        return subprocess.run(
            [sys.executable, "-S", "-c", code],
            cwd=tempfile.gettempdir(), capture_output=True, text=True,
            env={"PYTHONPATH": str(self.bundle), "PATH": "/usr/bin:/bin"})

    def test_le_registre_de_taxonomie_se_lit_DEPUIS_l_archive(self):
        """Le defaut le plus couteux du bundle, et le plus silencieux.

        `Registre.charger()` lisait `Path(__file__).parent / "registre.yaml"`.
        Dans un zipapp, `__file__` n'est pas un chemin de systeme de fichiers :
        le fichier « n'existait pas ». Or le registre est charge a CHAQUE
        execution de pipeline — donc `falcon.pyz`, qui est la forme de
        livraison arretee au §6, ne pouvait executer aucune pipeline.

        Rien ne levait a la construction, et cette suite n'exercait que des
        commandes qui ne chargent pas le registre. Le defaut ne se serait vu
        qu'au premier lot reel, sur le poste de quelqu'un.
        """
        fini = self._sonder(self.SONDE_REGISTRE)
        self.assertEqual(fini.returncode, 0, fini.stderr)
        self.assertIn("entrees", fini.stdout)

    def test_la_carte_se16n_se_lit_DEPUIS_l_archive(self):
        fini = self._sonder(self.SONDE_CARTE)
        self.assertEqual(fini.returncode, 0, fini.stderr)
        self.assertIn("manquants", fini.stdout)

    def test_une_pipeline_s_EXECUTE_depuis_l_archive(self):
        """Le bout du bout : c'est ce que le bundle est cense faire.

        Contre le double de test, donc sans SAP — mais en traversant le
        chargeur, le moteur, le controleur, la taxonomie et le journal, tous
        depuis l'archive.
        """
        fini = self._sonder(self.SONDE_EXECUTION)
        self.assertEqual(fini.returncode, 0, fini.stderr)
        self.assertIn("blanc termine etat termine ok 1", fini.stdout)

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


class TestLaConsoleDepuisLArchive(Base):
    """Deux branches de la console etaient CASSEES dans le bundle.

    `RACINE` et `FIXTURES` se calculent par `Path(__file__)`, qui depuis
    `falcon.pyz` designe un chemin A L'INTERIEUR de l'archive : `RACINE` vaut
    le fichier `.pyz` lui-meme, et `FIXTURES` ne designe rien.

    Consequence mesuree sur la livraison que le README recommande : « Traces »
    affichait une liste vide sans un mot, et « Verification » passait
    `cwd=<un fichier>` a `subprocess`, ce qui leve une `NotADirectoryError`
    que rien n'attrape — sur l'ecran meme auquel on demande si tout va bien.

    Ces branches ne PEUVENT pas marcher depuis l'archive : elles lisent le
    depot, qui n'y est pas et n'a aucune raison d'y etre. Le bon comportement
    est de le dire.
    """

    def _dans_l_archive(self, expression: str) -> str:
        rendu = subprocess.run(
            [sys.executable, "-S", "-c", textwrap.dedent(f"""\
                import sys
                sys.path.insert(0, {str(self.bundle)!r})
                import falcon.console.ecrans as e
                print({expression})
                """)],
            cwd=tempfile.gettempdir(), capture_output=True, text=True)
        self.assertEqual(rendu.returncode, 0, rendu.stderr)
        return rendu.stdout.strip()

    def test_l_archive_se_sait_hors_du_depot(self):
        self.assertEqual(self._dans_l_archive("e.depuis_le_depot()"), "False")

    def test_lancer_un_outil_DIT_pourquoi_au_lieu_de_lever(self):
        sortie = self._dans_l_archive("e._lancer(['-c', 'print(1)'])")
        self.assertIn("DEPOT", sortie)
        self.assertNotIn("NotADirectoryError", sortie)

    def test_les_listes_du_depot_sont_vides_sans_lever(self):
        """`Path.glob` sur un dossier inexistant ne leve pas : la liste etait
        vide, et l'utilisateur en concluait qu'il n'y avait aucune trace."""
        for quoi in ("_traces", "_suites"):
            with self.subTest(liste=quoi):
                self.assertEqual(
                    self._dans_l_archive(f"len(e.{quoi}(e.Environnement()))"),
                    "0")


class TestPaquetInstallable(unittest.TestCase):
    """L'AUTRE chemin de livraison, et il etait casse des deux facons.

    Le bundle est le mode retenu par le §6, donc ces defauts etaient latents.
    Mais `pip install -e .` est ce qu'on fait pour DEVELOPPER, et il donnait
    un import casse sans un mot :

    - `packages = ["falcon"]` ne RECURSE PAS : une roue livrait
      `falcon/__init__.py` et aucun des quinze sous-paquets ;
    - et aucun `package-data` : la roue ne portait AUCUN fichier YAML, donc
      `Registre.charger()` ne trouvait pas `registre.yaml` et un FALCON
      installe n'avait plus de taxonomie du tout — exactement le defaut deja
      corrige sur le bundle, par l'autre chemin.

    On CONSTRUIT la roue, comme les tests ci-dessus construisent l'archive :
    verifier l'intention de livrer ne prouve rien sur le livrable.
    """

    @classmethod
    def setUpClass(cls):
        cls._dossier = tempfile.TemporaryDirectory()
        rendu = subprocess.run(
            [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w",
             cls._dossier.name],
            cwd=RACINE, capture_output=True, text=True, timeout=300)
        if rendu.returncode != 0:
            raise unittest.SkipTest(
                f"construction de la roue impossible : {rendu.stderr[-400:]}")
        roues = list(Path(cls._dossier.name).glob("*.whl"))
        if not roues:
            raise unittest.SkipTest("aucune roue produite")
        cls.roue = roues[0]
        cls.noms = zipfile.ZipFile(cls.roue).namelist()

    @classmethod
    def tearDownClass(cls):
        cls._dossier.cleanup()

    def test_TOUS_les_sous_paquets_sont_dans_la_roue(self):
        livres = sorted(d.name for d in (RACINE / "falcon").iterdir()
                        if d.is_dir() and (d / "__init__.py").exists())
        embarques = {n.split("/")[1] for n in self.noms
                     if n.startswith("falcon/") and n.count("/") > 1}
        manquants = sorted(set(livres) - embarques)
        self.assertEqual(manquants, [],
                         f"la roue ne porte pas {manquants} : "
                         f"`import falcon.<paquet>` echouerait apres "
                         f"`pip install`")

    def test_les_YAML_livres_sont_dans_la_roue(self):
        """Sans eux, `Registre.charger()` echoue et FALCON n'a plus de
        taxonomie — un lot ne pourrait plus classer le moindre incident."""
        attendus = sorted(str(c.relative_to(RACINE)).replace("\\", "/")
                          for c in (RACINE / "falcon").rglob("*.yaml"))
        presents = sorted(n for n in self.noms if n.endswith(".yaml"))
        self.assertEqual(presents, attendus)

