"""La console interactive : navigation, innocuite, et robustesse d'affichage.

Trois proprietes portent ce lot, et aucune n'est cosmetique.

**Rien ici n'ecrit dans SAP.** La branche SAP ne manipule qu'un
`DriverLecture` ; le test le verifie non par relecture, mais en lui donnant un
double et en constatant qu'aucun geste ne l'a atteint.

**Rien de ce qu'on tape n'atteint un interpreteur.** Les sous-processus
partent en liste d'arguments, jamais par le shell, et les choix de fichier
viennent d'une liste decouverte sur le disque.

**Le decor doit s'encoder en cp1252.** C'est ce qu'ecrit une console Windows
francaise redirigee vers un fichier. Un cadre semi-graphique y leverait, et
l'outil mourrait sur son propre decor — sur la seule machine ou il sert,
puisque c'est la seule ou SAP GUI existe.
"""

from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

from falcon.catalogue import ESQUISSE, Depot, variante_de
from falcon.console import (
    CONTINUER, ENCODAGE_MINIMAL, QUITTER, RETOUR, Console, Entree, Menu,
    parcourir, racine, rendre,
)
from falcon.console import ecrans
from falcon.console.ecrans import Environnement
from falcon.couture.double import DriverScripte
from falcon.noyau import Champ, Ecran, Identite, SapIndisponible

from tests.test_gardes import MUTATIONS

RACINE = Path(__file__).resolve().parent.parent
IA08 = Identite(transaction="IA08", programme="RIPLKO10", dynpro="1000")


class Journal:
    """Une console pilotee par un script, sans terminal."""

    def __init__(self, *saisies: str):
        self.saisies = list(saisies)
        self.lignes: list[str] = []
        self.invites: list[str] = []

    def console(self) -> Console:
        return Console(lire=self._lire, ecrire=self.lignes.append)

    def _lire(self, invite: str) -> str:
        self.invites.append(invite)
        if not self.saisies:
            raise EOFError
        return self.saisies.pop(0)

    @property
    def texte(self) -> str:
        return "\n".join(self.lignes)


def _arbres() -> list[tuple[str, ast.Module]]:
    """(nom, arbre syntaxique) de chaque module de la console."""
    return [(chemin.name, ast.parse(chemin.read_text(encoding="utf-8"),
                                    str(chemin)))
            for chemin in sorted(Path(ecrans.__file__).parent.glob("*.py"))]


def _menus(menu: Menu) -> list[Menu]:
    """Tous les menus atteignables, y compris la racine."""
    trouves = [menu]
    for entree in menu.entrees:
        if isinstance(entree.cible, Menu):
            trouves += _menus(entree.cible)
    return trouves


class TestNavigation(unittest.TestCase):

    def _arbre(self, action) -> Menu:
        feuille = Menu(titre="feuille", entrees=(Entree("1", "agir", action),))
        return Menu(titre="racine",
                    entrees=(Entree("1", "descendre", feuille),))

    def test_on_descend_et_on_remonte(self):
        journal = Journal("1", "0", "0")
        code = parcourir(self._arbre(lambda c: CONTINUER), journal.console())
        self.assertEqual(code, 0)
        self.assertEqual(journal.texte.count("feuille"), 1)
        self.assertEqual(journal.texte.count("racine"), 2)

    def test_la_racine_affiche_quitter_et_un_sous_menu_retour(self):
        journal = Journal("1", "0", "0")
        parcourir(self._arbre(lambda c: CONTINUER), journal.console())
        self.assertIn("Quitter", journal.texte)
        self.assertIn("Retour", journal.texte)

    def test_une_option_inconnue_ne_fait_pas_sortir(self):
        """Une faute de frappe qui ferme l'outil est une faute de l'outil."""
        journal = Journal("42", "0")
        parcourir(self._arbre(lambda c: CONTINUER), journal.console())
        self.assertIn("n'est pas une option", journal.texte)
        self.assertEqual(journal.texte.count("racine"), 2)

    def test_la_fin_de_flux_sort_proprement(self):
        """Sans ca, une console pilotee par un script epuise boucle a vide."""
        journal = Journal()
        self.assertEqual(parcourir(self._arbre(lambda c: CONTINUER),
                                   journal.console()), 0)
        self.assertIn("Fin de session", journal.texte)

    def test_ctrl_c_sort_proprement(self):
        def interrompre(invite: str) -> str:
            raise KeyboardInterrupt

        console = Console(lire=interrompre, ecrire=lambda t: None)
        self.assertEqual(parcourir(self._arbre(lambda c: CONTINUER), console), 0)

    def test_une_action_peut_faire_remonter_ou_quitter(self):
        journal = Journal("1", "1")
        parcourir(self._arbre(lambda c: QUITTER), journal.console())
        self.assertEqual(journal.texte.count("racine"), 1)

        journal = Journal("1", "1", "0")
        parcourir(self._arbre(lambda c: RETOUR), journal.console())
        self.assertEqual(journal.texte.count("racine"), 2)

    def test_un_verdict_inattendu_est_une_erreur_de_programmation(self):
        """Une action qui rend n'importe quoi laisserait l'utilisateur dans un
        menu dont rien ne le sort. Mieux vaut que ca leve ici."""
        journal = Journal("1", "1")
        with self.assertRaises(ValueError):
            parcourir(self._arbre(lambda c: "peut-etre"), journal.console())


class TestInnocuite(unittest.TestCase):
    """Aucun ecran n'ecrit dans SAP, et rien de saisi n'atteint un shell."""

    def test_aucun_sous_processus_ne_passe_par_le_shell(self):
        """Verifie sur l'arbre syntaxique, pas par recherche de texte.

        Premiere version : `assertNotIn("shell=True", source)`. Elle est
        tombee sur la docstring qui promet de ne pas s'en servir. Un controle
        qui confond une promesse avec son execution ne controle rien.
        """
        for module, arbre in _arbres():
            for noeud in ast.walk(arbre):
                if not isinstance(noeud, ast.Call):
                    continue
                for mot in noeud.keywords:
                    with self.subTest(module=module, ligne=noeud.lineno):
                        self.assertNotEqual(
                            mot.arg, "shell",
                            f"{module}:{noeud.lineno} passe par le shell")

    def test_aucune_methode_mutante_n_est_appelee(self):
        """Egalement sur l'arbre : un nom cite en prose n'est pas un appel."""
        for module, arbre in _arbres():
            for noeud in ast.walk(arbre):
                if not isinstance(noeud, ast.Call):
                    continue
                nom = getattr(noeud.func, "attr", None)
                if nom in MUTATIONS:
                    self.fail(f"{module}:{noeud.lineno} appelle .{nom}()")

    def test_un_diagnostic_depuis_la_console_ne_touche_a_rien(self):
        """La preuve par le double : aucun geste ne l'a atteint."""
        brut = DriverScripte(identite=IA08,
                             champs=(Champ(id="wnd[0]/usr/txtA"),))
        env = Environnement(connecter=lambda: brut)
        journal = Journal("4", "1", "", "0", "0")
        parcourir(racine(env), journal.console())
        self.assertIn("IA08", journal.texte)
        self.assertEqual(brut.gestes, [])

    def test_une_session_indisponible_se_dit_sans_trace_de_pile(self):
        def refuser():
            raise SapIndisponible("pywin32 n'est pas installe")

        journal = Journal("4", "1", "", "0", "0")
        parcourir(racine(Environnement(connecter=refuser)), journal.console())
        self.assertIn("SapIndisponible", journal.texte)
        self.assertNotIn("Traceback", journal.texte)

    def test_les_suites_proposees_viennent_du_disque(self):
        """Aucun nom de module ne se construit a partir d'une saisie."""
        proposes = {clef for clef, _ in ecrans._suites(Environnement())}
        sur_disque = {f"tests.{c.stem}"
                      for c in (RACINE / "tests").glob("test_*.py")}
        self.assertEqual(proposes, sur_disque)
        self.assertIn("tests.test_console", proposes)


class TestAffichage(unittest.TestCase):

    def test_tout_le_decor_s_encode_en_cp1252(self):
        """Une console Windows francaise redirigee ecrit en cp1252.

        Un cadre semi-graphique y leverait `UnicodeEncodeError` : l'outil
        mourrait sur son propre decor, sur la seule machine ou il sert.
        """
        for menu in _menus(racine()):
            for ligne in rendre(menu, racine=True):
                with self.subTest(menu=menu.titre, ligne=ligne):
                    ligne.encode(ENCODAGE_MINIMAL)

    def test_aucun_caractere_semi_graphique(self):
        for menu in _menus(racine()):
            for ligne in rendre(menu, racine=False):
                with self.subTest(ligne=ligne):
                    self.assertFalse(
                        any("─" <= c <= "╿" for c in ligne),
                        "caractere de cadre semi-graphique")

    def test_aucune_sequence_ansi_dans_les_chaines(self):
        """Sur les litteraux, pas sur le fichier : le mot « ANSI » ecrit dans
        un commentaire n'est pas une sequence ANSI."""
        for module, arbre in _arbres():
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                    with self.subTest(module=module, ligne=noeud.lineno):
                        self.assertNotIn("\x1b", noeud.value)

    def test_chaque_menu_annonce_une_sortie(self):
        for menu in _menus(racine()):
            with self.subTest(menu=menu.titre):
                rendu = rendre(menu, racine=False)
                self.assertTrue(any(" 0 " in l for l in rendu))


class TestVerification(unittest.TestCase):
    """La branche « tests », avec un lanceur injecte : on ne relance pas les
    quatre cents tests a l'interieur d'un test."""

    def setUp(self):
        self.appels: list[list[str]] = []

        def lancer(arguments: list[str]) -> tuple[int, str]:
            self.appels.append(arguments)
            return 0, "Ran 379 tests\nOK"

        self.env = Environnement(lancer=lancer)

    def test_tout_verifier_appelle_le_verificateur_du_depot(self):
        journal = Journal("1", "1", "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertEqual(self.appels, [["outils/verifier.py"]])
        self.assertIn("Ran 379 tests", journal.texte)
        self.assertIn("vert", journal.texte)

    def test_les_gardes_appellent_le_neutraliseur(self):
        journal = Journal("1", "2", "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertEqual(self.appels, [["outils/neutraliser.py"]])

    def test_une_suite_au_choix_se_lance_par_unittest(self):
        journal = Journal("1", "3", "1", "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertEqual(len(self.appels), 1)
        self.assertEqual(self.appels[0][:2], ["-m", "unittest"])

    def test_un_echec_est_annonce_comme_tel(self):
        env = Environnement(lancer=lambda a: (1, "FAILED (failures=1)"))
        journal = Journal("1", "1", "", "0", "0")
        parcourir(racine(env), journal.console())
        self.assertIn("ECHEC", journal.texte)


class TestTraces(unittest.TestCase):

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.fixtures = Path(dossier.name)
        self.env = Environnement(fixtures=self.fixtures)

    def _poser(self, nom: str, *lignes: str) -> None:
        contenu = "".join(l + "\r\n" for l in lignes)
        (self.fixtures / nom).write_bytes(
            b"\xff\xfe" + contenu.encode("utf-16-le"))

    def test_la_couverture_se_rend(self):
        self._poser("t.vbs", 'session.findById("wnd[0]").maximize')
        journal = Journal("2", "1", "1", "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertIn("Toutes les lignes sont appariees", journal.texte)

    def test_une_trace_illisible_est_refusee_et_l_inventaire_propose(self):
        """La lecture stricte refuse ; l'ecran le dit et renvoie vers
        l'inventaire, qui lit ce qu'il peut et nomme le reste."""
        self._poser("casse.vbs", 'MsgBox "on continue ?"')
        journal = Journal("2", "2", "1", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertIn("Lecture refusee", journal.texte)
        self.assertIn('MsgBox "on continue ?"', journal.texte)
        self.assertIn("inventaire", journal.texte.lower())

    def test_les_ecrans_conjectures_disent_ce_qu_ils_ne_sont_pas(self):
        self._poser("t.vbs",
                    'session.findById("wnd[0]/usr/txtA").text = "x"',
                    'session.findById("wnd[0]").sendVKey 0')
        journal = Journal("2", "2", "1", "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertIn("ne dit ni l'identite des ecrans", journal.texte)
        self.assertIn("esquisse", journal.texte)

    def test_les_gestes_de_confort_sont_ecartes_de_la_liste(self):
        self._poser("t.vbs",
                    'session.findById("wnd[0]/usr/txtA").text = "x"',
                    'session.findById("wnd[0]/usr/txtA").setFocus')
        journal = Journal("2", "3", "1", "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertIn("1 significatif(s) sur 2", journal.texte)


class TestCatalogue(unittest.TestCase):

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name) / "catalogue"
        ecran = Ecran(identite=IA08, champs=(Champ(id="wnd[0]/usr/txtA"),))
        depot = Depot(self.racine)
        depot.enregistrer(variante_de(ecran))
        depot.mettre_en_quarantaine(variante_de(ecran, source=ESQUISSE))

    def test_le_catalogue_cure_se_liste(self):
        journal = Journal("3", "1", str(self.racine), "", "0", "0")
        parcourir(racine(), journal.console())
        self.assertIn("IA08/RIPLKO10/1000", journal.texte)
        self.assertIn("observee", journal.texte)

    def test_une_esquisse_en_quarantaine_est_signalee_comme_telle(self):
        """Elle ne peut pas garder un ecran, et la console le dit a l'endroit
        ou quelqu'un serait tente de la promouvoir."""
        journal = Journal("3", "2", str(self.racine), "", "0", "0")
        parcourir(racine(), journal.console())
        self.assertIn("ESQUISSE", journal.texte)
        self.assertIn("ne peut pas garder un ecran", journal.texte)

    def test_un_dossier_inexistant_le_dit(self):
        journal = Journal("3", "1", "/rien/du/tout", "0", "0")
        parcourir(racine(), journal.console())
        self.assertIn("n'est pas un dossier", journal.texte)

    def test_la_console_ne_promeut_rien(self):
        """La promotion reste un geste delibere, et pas depuis un menu."""
        for module, arbre in _arbres():
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Call):
                    self.assertNotEqual(getattr(noeud.func, "attr", None),
                                        "promouvoir",
                                        f"{module}:{noeud.lineno}")


if __name__ == "__main__":
    unittest.main()
