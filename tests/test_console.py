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
import textwrap
import unittest
from pathlib import Path

from falcon.catalogue import ESQUISSE, Depot, variante_de
from falcon.console import (
    CONTINUER, ENCODAGE_MINIMAL, QUITTER, RETOUR, VERDICTS, Console, Entree,
    Menu, parcourir, racine, rendre,
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


#: Ce qu'un ecran qui ecrit dans SAP doit annoncer dans son detail.
MARQUE_ECRITURE = "ECRIT DANS SAP"

#: Formules par lesquelles un preambule affirme qu'on ne risque rien.
PROMESSES_D_INNOCUITE = ("n'ecrit dans SAP", "ne touche a SAP", "Lecture seule")


def _ecrit(menu: Menu) -> bool:
    """Ce menu mene-t-il, directement ou non, a un ecran qui ecrit ?"""
    for entree in menu.entrees:
        if isinstance(entree.cible, Menu):
            if _ecrit(entree.cible):
                return True
        elif MARQUE_ECRITURE in entree.detail:
            return True
    return False


def vers(menu: Menu, *libelles: str) -> list[str]:
    """Les clefs qui menent a ces libelles, resolues sur l'arbre reel.

    Un test qui tape « 3 » affirme un rang, pas une intention : le jour ou
    une entree s'insere avant, il continue de passer en visitant autre chose,
    ou il tombe pour une raison qui n'a rien a voir avec ce qu'il verifie.
    Les deux sont arrives. En resolvant le chemin par le libelle, un
    reordonnancement ne casse rien, et une entree disparue casse tout de
    suite — a l'endroit, avec le nom qu'on cherchait.
    """
    clefs: list[str] = []
    courant: object = menu
    for libelle in libelles:
        if not isinstance(courant, Menu):
            raise AssertionError(f"« {libelle} » : on est deja sur une action")
        trouvees = [entree for entree in courant.entrees
                    if libelle.lower() in entree.libelle.lower()]
        if len(trouvees) != 1:
            raise AssertionError(
                f"« {libelle} » designe {len(trouvees)} entree(s) de "
                f"« {courant.titre} » : "
                f"{[entree.libelle for entree in courant.entrees]}")
        clefs.append(trouvees[0].clef)
        courant = trouvees[0].cible
    return clefs


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
        chemin = vers(racine(env), "Session SAP", "Diagnostiquer l'ecran")
        journal = Journal(*chemin, "", "0", "0")
        parcourir(racine(env), journal.console())
        self.assertIn("IA08", journal.texte)
        self.assertEqual(brut.gestes, [])

    def test_une_session_indisponible_se_dit_sans_trace_de_pile(self):
        def refuser():
            raise SapIndisponible("pywin32 n'est pas installe")

        arbre = racine(Environnement(connecter=refuser))
        journal = Journal(*vers(arbre, "Session SAP", "Diagnostiquer l'ecran"),
                          "", "0", "0")
        parcourir(arbre, journal.console())
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

    def test_tout_ce_qu_un_ecran_peut_ecrire_s_encode_aussi(self):
        """Sur les litteraux des modules, et pas seulement sur les menus.

        Defaut trouve par controle negatif : un caractere semi-graphique pose
        dans le corps d'un ecran passait les deux tests ci-dessus. Ils ne
        voient que le rendu des menus — titres, libelles, preambules — donc
        rien de ce qu'un ecran ecrit une fois qu'on l'a choisi. Or c'est la
        que le texte est le plus abondant, et le plus recemment ecrit.
        """
        for module, arbre in _arbres():
            for noeud in ast.walk(arbre):
                if not (isinstance(noeud, ast.Constant)
                        and isinstance(noeud.value, str)):
                    continue
                with self.subTest(module=module, ligne=noeud.lineno):
                    try:
                        noeud.value.encode(ENCODAGE_MINIMAL)
                    except UnicodeEncodeError as erreur:
                        self.fail(f"{module}:{noeud.lineno} ne s'encode pas "
                                  f"en {ENCODAGE_MINIMAL} : {erreur}")

    def test_aucun_caractere_semi_graphique(self):
        rendus = [(menu.titre, ligne)
                  for menu in _menus(racine())
                  for ligne in rendre(menu, racine=False)]
        litteraux = [(f"{module}:{noeud.lineno}", noeud.value)
                     for module, arbre in _arbres()
                     for noeud in ast.walk(arbre)
                     if isinstance(noeud, ast.Constant)
                     and isinstance(noeud.value, str)]
        for ou, texte in rendus + litteraux:
            with self.subTest(ou=ou):
                self.assertFalse(
                    any("─" <= c <= "╿" for c in texte),
                    f"{ou} : caractere de cadre semi-graphique")

    def test_aucune_sequence_ansi_dans_les_chaines(self):
        """Sur les litteraux, pas sur le fichier : le mot « ANSI » ecrit dans
        un commentaire n'est pas une sequence ANSI."""
        for module, arbre in _arbres():
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
                    with self.subTest(module=module, ligne=noeud.lineno):
                        self.assertNotIn("\x1b", noeud.value)

    def test_la_racine_couvre_les_sept_domaines(self):
        """La console a ete ecrite au lot 14, AVANT le moteur : les lots 10 a
        13c y etaient inatteignables. Ce test epingle la couverture, pas
        l'ordre — il tombera le jour ou un domaine disparaitra du menu."""
        libelles = [e.libelle for e in racine().entrees]
        for attendu in ("Verification et livraison", "Traces du recorder",
                        "Pipelines et donnees", "Journaux",
                        "Catalogue d'ecrans", "Exports de table",
                        "Session SAP"):
            self.assertIn(attendu, libelles)

    def test_chaque_ecran_survit_a_un_flux_vide(self):
        """Un ecran qui leve sur une fin de flux tue la console entiere. Le
        cas arrive pour de vrai : un Ctrl-C sur la premiere invite.

        C'est un test de fumee sur TOUT l'arbre : il ne dit pas qu'un ecran
        fait ce qu'il faut, il dit qu'aucun ne meurt avant de le faire. Un
        ecran neuf y entre sans qu'on ait a y penser.

        L'environnement est INJECTE, et pas par confort : sans ca, l'ecran
        « Tout verifier » relance `outils/verifier.py` en sous-processus —
        donc cette suite, depuis cette suite. La premiere version de ce test
        a tourne jusqu'a expiration du delai.
        """
        def refuser():
            raise SapIndisponible("pas de session dans un test")

        env = Environnement(lancer=lambda arguments: (0, "OK"),
                            connecter=refuser)
        for menu in _menus(racine(env)):
            for entree in menu.entrees:
                if isinstance(entree.cible, Menu):
                    continue
                with self.subTest(menu=menu.titre, ecran=entree.libelle):
                    journal = Journal()
                    verdict = entree.cible(journal.console())
                    self.assertIn(verdict, VERDICTS)

    def test_chaque_entree_porte_un_detail(self):
        """Un libelle seul se lit trop vite. Le detail est la ou se dit ce
        qu'une entree engage — « ECRIT DANS SAP », notamment."""
        for menu in _menus(racine()):
            for entree in menu.entrees:
                with self.subTest(menu=menu.titre, entree=entree.libelle):
                    self.assertTrue(entree.detail.strip())

    def test_aucun_menu_qui_ecrit_ne_se_dit_inoffensif(self):
        """La propriete la plus importante de tout ce fichier.

        La racine promettait « aucune commande de cette console n'ecrit dans
        SAP ». C'etait vrai au lot 14 ; ca a cesse de l'etre le jour ou
        l'execution est arrivee, et la phrase est restee. C'est le pire genre
        de defaut : un texte rassurant, a l'endroit exact ou quelqu'un decide
        qu'il peut cliquer sans reflechir.

        Le test ne verifie pas une phrase, il verifie l'ACCORD entre ce qu'un
        menu mene a faire et ce qu'il en dit. Un ecran qui ecrit ajoute
        quelque part sous lui, et toute promesse d'innocuite au-dessus tombe.
        """
        for menu in _menus(racine()):
            if not _ecrit(menu):
                continue
            for promesse in PROMESSES_D_INNOCUITE:
                with self.subTest(menu=menu.titre, promesse=promesse):
                    self.assertNotIn(
                        promesse, menu.preambule,
                        f"« {menu.titre} » mene a un ecran qui ecrit dans SAP "
                        f"et promet le contraire")

    def test_un_menu_qui_ecrit_le_dit_dans_son_preambule(self):
        """L'accord dans l'autre sens : ne pas mentir ne suffit pas, il faut
        le dire. Un preambule muet laisse le libelle seul porter
        l'avertissement, et un libelle se lit trop vite."""
        for menu in _menus(racine()):
            if _ecrit(menu):
                with self.subTest(menu=menu.titre):
                    self.assertIn("ECRIVENT DANS SAP", menu.preambule)

    def test_aucune_ligne_de_menu_ne_deborde_de_80_colonnes(self):
        """Le cadre fait 72 colonnes ; une ligne plus longue se replie et
        casse l'alignement de tout le menu. Trouve a l'oeil, en parcourant les
        sept branches — ce que les tests ne disaient pas."""
        for menu in _menus(racine()):
            for ligne in rendre(menu, racine=False):
                with self.subTest(menu=menu.titre, ligne=ligne):
                    self.assertLessEqual(len(ligne), 79)

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
        journal = Journal(*vers(racine(), "Verification", "Tout verifier"),
                          "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertEqual(self.appels, [["outils/verifier.py"]])
        self.assertIn("Ran 379 tests", journal.texte)
        self.assertIn("vert", journal.texte)

    def test_les_gardes_appellent_le_neutraliseur(self):
        journal = Journal(*vers(racine(), "Verification", "gardes"), "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertEqual(self.appels, [["outils/neutraliser.py"]])

    def test_une_suite_au_choix_se_lance_par_unittest(self):
        journal = Journal(*vers(racine(), "Verification", "suite au choix"),
                          "1", "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertEqual(len(self.appels), 1)
        self.assertEqual(self.appels[0][:2], ["-m", "unittest"])

    def test_le_bundle_se_construit_depuis_le_menu(self):
        """Le depot est modulaire, la livraison est un fichier unique (§6).
        L'outil existait depuis le lot 13 et n'etait atteignable qu'en ligne
        de commande."""
        journal = Journal(*vers(racine(), "Verification", "bundle"),
                          "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertEqual(self.appels, [["outils/embarquer.py"]])

    def test_le_bundle_rappelle_ce_qui_ne_s_embarque_pas(self):
        """pywin32 est une extension binaire liee a une version
        d'interpreteur : figee dans un zip, elle serait fausse la moitie du
        temps. Le dire ici evite de livrer une archive qu'on croit complete."""
        journal = Journal(*vers(racine(), "Verification", "bundle"),
                          "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertIn("pywin32", journal.texte)
        self.assertIn("pip install pywin32", journal.texte)

    def test_un_echec_est_annonce_comme_tel(self):
        env = Environnement(lancer=lambda a: (1, "FAILED (failures=1)"))
        journal = Journal(*vers(racine(), "Verification", "Tout verifier"),
                          "", "0", "0")
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
        journal = Journal(*vers(racine(), "Traces", "Couverture"),
                          "1", "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertIn("Toutes les lignes sont appariees", journal.texte)

    def test_une_trace_illisible_est_refusee_et_l_inventaire_propose(self):
        """La lecture stricte refuse ; l'ecran le dit et renvoie vers
        l'inventaire, qui lit ce qu'il peut et nomme le reste."""
        self._poser("casse.vbs", 'MsgBox "on continue ?"')
        journal = Journal(*vers(racine(), "Traces", "Ecrans conjectures"),
                          "1", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertIn("Lecture refusee", journal.texte)
        self.assertIn('MsgBox "on continue ?"', journal.texte)
        self.assertIn("inventaire", journal.texte.lower())

    def test_les_ecrans_conjectures_disent_ce_qu_ils_ne_sont_pas(self):
        self._poser("t.vbs",
                    'session.findById("wnd[0]/usr/txtA").text = "x"',
                    'session.findById("wnd[0]").sendVKey 0')
        journal = Journal(*vers(racine(), "Traces", "Ecrans conjectures"),
                          "1", "", "0", "0")
        parcourir(racine(self.env), journal.console())
        self.assertIn("ne dit ni l'identite des ecrans", journal.texte)
        self.assertIn("esquisse", journal.texte)

    def test_les_gestes_de_confort_sont_ecartes_de_la_liste(self):
        self._poser("t.vbs",
                    'session.findById("wnd[0]/usr/txtA").text = "x"',
                    'session.findById("wnd[0]/usr/txtA").setFocus')
        journal = Journal(*vers(racine(), "Traces", "Gestes"),
                          "1", "", "0", "0")
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
        journal = Journal(*vers(racine(), "Catalogue d'ecrans", "Catalogue cure"),
                          str(self.racine), "", "0", "0")
        parcourir(racine(), journal.console())
        self.assertIn("IA08/RIPLKO10/1000", journal.texte)
        self.assertIn("observee", journal.texte)

    def test_une_esquisse_en_quarantaine_est_signalee_comme_telle(self):
        """Elle ne peut pas garder un ecran, et la console le dit a l'endroit
        ou quelqu'un serait tente de la promouvoir."""
        journal = Journal(*vers(racine(), "Catalogue d'ecrans", "Quarantaine"),
                          str(self.racine), "", "0", "0")
        parcourir(racine(), journal.console())
        self.assertIn("ESQUISSE", journal.texte)
        self.assertIn("ne peut pas garder un ecran", journal.texte)

    def test_un_dossier_inexistant_le_dit(self):
        journal = Journal(*vers(racine(), "Catalogue d'ecrans", "Catalogue cure"),
                          "/rien/du/tout", "0", "0")
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


PIPELINE = """
    version: 1
    nom: bcp_ia08_variantes
    classe: iterative
    cles: [site]
    plafond_items: 50
    plafond_sauvegardes: 50
    etapes:
      - nom: saisir_division
        action: set
        cible: "wnd[0]/usr/ctxtWERKS-LOW"
        source: {colonne: site}
        ecran: {transaction: IA08, programme: RIPLKO10, dynpro: "1000"}
      - nom: sauver
        action: press
        cible: "wnd[0]/tbar[0]/btn[11]"
        navigation_libre: true
        sauvegarde: true
        derogations:
          - garde: statut
            portee: "etape:sauver"
            motif: "IA08 ne rend aucun message sur cette validation"
    """


class TestPipelinesEtDonnees(unittest.TestCase):
    """Charger, relire, inspecter — sans SAP et sans rien ecrire.

    Ces deux ecrans existent parce que la relecture d'une pipeline doit se
    faire AVANT de lancer quoi que ce soit, et que le regroupement en items
    est la seule facon de voir qu'on a quarante unites de sauvegarde et non
    trois cents lignes. Les deux etaient jusqu'ici inatteignables autrement
    qu'en ecrivant du Python.
    """

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name)

    def _poser(self, nom: str, texte: str) -> Path:
        chemin = self.racine / nom
        chemin.write_text(textwrap.dedent(texte), encoding="utf-8")
        return chemin

    def _session(self, *libelles: str, saisies: tuple[str, ...]) -> Journal:
        journal = Journal(*vers(racine(), *libelles), *saisies, "0", "0")
        parcourir(racine(), journal.console())
        return journal

    # -- charger et valider ------------------------------------------------

    def test_une_pipeline_valide_se_rend_etape_par_etape(self):
        chemin = self._poser("p.yaml", PIPELINE)
        journal = self._session("Pipelines", "Charger et valider",
                                saisies=(str(chemin), ""))
        self.assertIn("bcp_ia08_variantes", journal.texte)
        self.assertIn("saisir_division", journal.texte)
        self.assertIn("wnd[0]/usr/ctxtWERKS-LOW", journal.texte)
        self.assertIn("ecran IA08/RIPLKO10/1000", journal.texte)
        self.assertIn("source colonne: 'site'", journal.texte)

    def test_les_deux_plafonds_sont_montres(self):
        """Un seul des deux affiche laisserait croire que l'autre n'existe
        pas — or c'est le plafond de sauvegardes qui borne les degats."""
        chemin = self._poser("p.yaml", PIPELINE)
        journal = self._session("Pipelines", "Charger et valider",
                                saisies=(str(chemin), ""))
        self.assertIn("plafond items", journal.texte)
        self.assertIn("plafond sauvegardes", journal.texte)

    def test_l_empreinte_est_montree(self):
        """C'est elle qui dit si le fichier relu est celui qui sera joue."""
        from falcon.pipeline import charger

        chemin = self._poser("p.yaml", PIPELINE)
        journal = self._session("Pipelines", "Charger et valider",
                                saisies=(str(chemin), ""))
        self.assertIn(charger(chemin).empreinte, journal.texte)

    def test_une_navigation_libre_est_annoncee_en_capitales(self):
        """Elle ne pose PAS la garde d'identite. Le rendu doit le dire la ou
        se fait la relecture, pas seulement dans le YAML."""
        chemin = self._poser("p.yaml", PIPELINE)
        journal = self._session("Pipelines", "Charger et valider",
                                saisies=(str(chemin), ""))
        self.assertIn("NAVIGATION LIBRE", journal.texte)
        self.assertIn("garde d'identite non posee", journal.texte)

    def test_une_sauvegarde_est_annoncee_en_capitales(self):
        chemin = self._poser("p.yaml", PIPELINE)
        journal = self._session("Pipelines", "Charger et valider",
                                saisies=(str(chemin), ""))
        self.assertIn("SAUVEGARDE", journal.texte)

    def test_une_derogation_est_rendue_avec_sa_portee_et_son_motif(self):
        """Une derogation sans son motif serait une case cochee. Le motif est
        la seule chose qui permette a un relecteur de la contester."""
        chemin = self._poser("p.yaml", PIPELINE)
        journal = self._session("Pipelines", "Charger et valider",
                                saisies=(str(chemin), ""))
        self.assertIn("DEROGATION", journal.texte)
        self.assertIn("etape:sauver", journal.texte)
        self.assertIn("IA08 ne rend aucun message", journal.texte)

    def test_le_bilan_compte_ce_qui_engage(self):
        chemin = self._poser("p.yaml", PIPELINE)
        journal = self._session("Pipelines", "Charger et valider",
                                saisies=(str(chemin), ""))
        self.assertIn("1 etape(s) declarent sauvegarder", journal.texte)
        self.assertIn("1 en navigation libre", journal.texte)
        self.assertIn("1 derogation(s)", journal.texte)

    def test_une_valeur_COMPOSEE_est_montree_a_la_relecture(self):
        """Ce n'est plus la colonne qui part dans SAP, c'est le resultat. Une
        relecture qui montrerait `colonne: equipement` sans dire « cadre a 18
        zeros » montrerait autre chose que ce qui sera tape."""
        chemin = self._poser("compose.yaml", """
            version: 1
            nom: composee
            classe: iterative
            cles: [site]
            plafond_items: 50
            plafond_sauvegardes: 50
            etapes:
              - nom: saisir_variante
                action: set
                cible: "wnd[0]/usr/ctxtV-LOW"
                source: {gabarit: "/BCP01_{site}"}
                format: [majuscules]
                ecran: {transaction: IA08, programme: R, dynpro: "1000"}
              - nom: saisir_equipement
                action: set
                cible: "wnd[0]/usr/ctxtEQUNR"
                source: {colonne: equipement}
                defaut: "0"
                format: [sans_espaces_autour, {zeros: 18}]
                ecran: {transaction: IA08, programme: R, dynpro: "1000"}
            """)
        journal = self._session("Pipelines", "Charger et valider",
                                saisies=(str(chemin), ""))
        self.assertIn("gabarit: '/BCP01_{site}'", journal.texte)
        self.assertIn("colonnes lues : site", journal.texte)
        self.assertIn("format majuscules", journal.texte)
        self.assertIn("defaut si vide '0'", journal.texte)
        self.assertIn("zeros: 18", journal.texte)

    def test_un_refus_du_chargeur_est_rendu_situe(self):
        """Le chargeur produit deja un refus situe — fichier, rang, nom
        d'etape. L'ecran le rend tel quel : le reformuler perdrait le seul
        renseignement qui permette d'aller corriger."""
        chemin = self._poser("casse.yaml", """
            version: 1
            nom: casse
            classe: iterative
            cles: [site]
            plafond_items: 50
            plafond_sauvegardes: 50
            etapes:
              - nom: sans_cible
                action: set
            """)
        journal = self._session("Pipelines", "Charger et valider",
                                saisies=(str(chemin), ""))
        self.assertIn("Refuse", journal.texte)
        self.assertIn("sans_cible", journal.texte)
        self.assertNotIn("Traceback", journal.texte)

    def test_un_chemin_inexistant_le_dit_sans_lever(self):
        journal = self._session("Pipelines", "Charger et valider",
                                saisies=("/rien/du/tout",))
        self.assertIn("n'existe pas", journal.texte)
        self.assertNotIn("Traceback", journal.texte)

    # -- brouillon ---------------------------------------------------------

    def test_un_brouillon_se_relit_avec_ses_marqueurs(self):
        """`charger()` refuse un marqueur ; l'ecran « brouillon » le tolere,
        et dit que le fichier n'est pas livrable pour autant."""
        from falcon.pipeline import PipelineInvalide, charger

        chemin = self._poser("b.yaml", """
            version: 1
            nom: esquisse
            classe: iterative
            cles: [site]
            plafond_items: 50
            plafond_sauvegardes: 50
            etapes:
              - nom: saisir
                action: set
                cible: "wnd[0]/usr/ctxtWERKS-LOW"
                source: {colonne: site}
                ecran: {transaction: "TODO", programme: RIPLKO10,
                        dynpro: "1000"}
            """)
        with self.assertRaises(PipelineInvalide):
            charger(chemin)

        journal = self._session("Pipelines", "Relire un brouillon",
                                saisies=(str(chemin), ""))
        self.assertIn("esquisse", journal.texte)
        self.assertIn("marqueurs sont toleres", journal.texte)
        self.assertIn("n'est pas livrable", journal.texte)

    # -- jeu de donnees ----------------------------------------------------

    def test_un_jeu_se_lit_avec_son_dialecte(self):
        """Le dialecte lu est celui qui sera reecrit : un fichier de KO
        reinjecte garde l'encodage et le delimiteur d'origine."""
        chemin = self.racine / "jeu.csv"
        chemin.write_bytes(
            "site;equipement\r\nK75;100\r\nK75;101\r\nK76;200\r\n"
            .encode("cp1252"))
        journal = self._session("Pipelines", "Inspecter un jeu",
                                saisies=(str(chemin), ""))
        self.assertIn("';'", journal.texte)
        self.assertIn("'\\r\\n'", journal.texte)
        self.assertIn("site", journal.texte)
        self.assertIn("equipement", journal.texte)

    def test_le_regroupement_montre_les_items_et_non_les_lignes(self):
        """C'est le point de tout l'ecran : trois lignes font deux unites de
        sauvegarde, et c'est sur les items que portent les plafonds."""
        chemin = self.racine / "jeu.csv"
        chemin.write_bytes(
            "site;equipement\r\nK75;100\r\nK75;101\r\nK76;200\r\n"
            .encode("cp1252"))
        journal = self._session("Pipelines", "Inspecter un jeu",
                                saisies=(str(chemin), "site", ""))
        self.assertIn("3 ligne(s) -> 2 item(s)", journal.texte)
        self.assertIn("unite de SAUVEGARDE SAP", journal.texte)

    def test_une_cle_absente_est_refusee_sans_lever(self):
        chemin = self.racine / "jeu.csv"
        chemin.write_bytes("site;equipement\r\nK75;100\r\n".encode("cp1252"))
        journal = self._session("Pipelines", "Inspecter un jeu",
                                saisies=(str(chemin), "usine", ""))
        self.assertIn("Regroupement refuse", journal.texte)
        self.assertNotIn("Traceback", journal.texte)

    # -- innocuite ---------------------------------------------------------

    def test_aucun_de_ces_ecrans_n_ecrit_sur_le_disque(self):
        """La branche entiere est en lecture. Rien de ce qu'on y fait ne doit
        laisser une trace : ni fichier neuf, ni fichier touche."""
        chemin = self._poser("p.yaml", PIPELINE)
        jeu = self.racine / "jeu.csv"
        jeu.write_bytes("site;equipement\r\nK75;100\r\n".encode("cp1252"))
        avant = {c: c.stat().st_mtime_ns for c in self.racine.iterdir()}

        for libelle, saisies in (("Charger et valider", (str(chemin), "")),
                                 ("Relire un brouillon", (str(chemin), "")),
                                 ("Inspecter un jeu", (str(jeu), "site", ""))):
            self._session("Pipelines", libelle, saisies=saisies)

        apres = {c: c.stat().st_mtime_ns for c in self.racine.iterdir()}
        self.assertEqual(avant, apres)


class TestJournaux(unittest.TestCase):
    """Relire un journal. **Jamais y ecrire.**

    Le journal est append-only et fait foi : c'est de lui que la reprise tire
    ce qu'elle a le droit de rejouer. Une console qui pourrait le retoucher
    deferait la seule chose qui empeche une double ecriture dans SAP.
    """

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name)
        self.chemin = self.racine / "journal.jsonl"
        self.jeu = self.racine / "sites.csv"
        self.jeu.write_bytes(
            "site;equipement\r\nK75;100\r\nK76;200\r\nK76;201\r\n"
            "K77;300\r\nK78;400\r\n".encode("cp1252"))
        self.items = self._items()
        self._ecrire_journal()

    def _items(self) -> dict:
        """Les items tels que le moteur les aurait groupes.

        `item_id` est une empreinte des valeurs de clef, jamais un rang : un
        fichier de KO reinjecte n'a plus les memes rangs. Un journal de test
        qui poserait `item_id="K75"` testerait un format qui n'existe pas.
        """
        from falcon.donnees import grouper, lire

        lignes, _ = lire(self.jeu)
        return {item.cle["site"]: item for item in grouper(lignes, ["site"])}

    def _ecrire_journal(self) -> None:
        """Un journal realiste : un OK, un KO, un DOUTEUX, un EN COURS.

        Le douteux n'est pas construit en posant l'etat a la main — il n'y a
        pas d'etat « douteux » dans le journal. Il se DEDUIT : un item ouvert,
        une etape de sauvegarde reussie, et pas d'`ItemFin`. C'est le repli qui
        le classe, et c'est ce repli qu'on veut voir affiche. K78, ouvert sans
        sauvegarde, reste `en_cours` : la difference entre les deux est
        exactement celle entre « rejouable » et « a arbitrer ».
        """
        from falcon.journal import (
            Ecrivain, Etape, ExecutionDebut, ExecutionFin, Incident,
            ItemDebut, ItemFin,
        )

        def debut(site: str) -> ItemDebut:
            item = self.items[site]
            return ItemDebut(run_id="R1", item_id=item.item_id,
                             index=item.index, cle=dict(item.cle),
                             brut=[dict(l) for l in item.brut])

        def sauver(site: str) -> Etape:
            return Etape(run_id="R1", item_id=self.items[site].item_id,
                         etape="sauver", action="press",
                         cible="wnd[0]/tbar[0]/btn[11]", sauvegarde=True)

        with Ecrivain(self.chemin) as journal:
            journal.ecrire(ExecutionDebut(
                run_id="R1", mode="run", classe="iterative",
                pipeline="bcp_ia08", pipeline_empreinte="pipe1",
                jeu="sites.csv", jeu_empreinte="jeu1",
                systeme="K75", mandant="210"))
            journal.ecrire(debut("K75"))
            journal.ecrire(sauver("K75"))
            journal.ecrire(ItemFin(run_id="R1", item_id=self.items["K75"].item_id,
                                   etat="ok", sauvegardes=1))
            journal.ecrire(debut("K76"))
            journal.ecrire(Incident(
                run_id="R1", item_id=self.items["K76"].item_id,
                categorie="connue_fautive", entree="relecture_divergente",
                bloquant=False,
                signature={"message": "la valeur n'a pas pris"}))
            journal.ecrire(ItemFin(run_id="R1", item_id=self.items["K76"].item_id,
                                   etat="ko", incident="champ_absent"))
            journal.ecrire(debut("K77"))
            journal.ecrire(sauver("K77"))
            journal.ecrire(debut("K78"))
            journal.ecrire(ExecutionFin(run_id="R1", etat="interrompu",
                                        raison="ecran inattendu",
                                        duree_ms=4200))

    def _session(self, libelle: str, *saisies: str) -> Journal:
        journal = Journal(*vers(racine(), "Journaux", libelle),
                          *saisies, "0", "0")
        parcourir(racine(), journal.console())
        return journal

    # -- rapport -----------------------------------------------------------

    def test_le_rapport_de_fin_se_rend(self):
        journal = self._session("Rapport de fin", str(self.chemin), "")
        self.assertIn("bcp_ia08", journal.texte)
        self.assertIn("K75/210", journal.texte)
        self.assertIn("DOUTEUX", journal.texte)

    def test_un_journal_illisible_le_dit_sans_trace_de_pile(self):
        casse = self.racine / "casse.jsonl"
        casse.write_text("ceci n'est pas du JSON\n", encoding="utf-8")
        journal = self._session("Rapport de fin", str(casse), "")
        self.assertIn("illisible", journal.texte)
        self.assertNotIn("Traceback", journal.texte)

    # -- etats -------------------------------------------------------------

    def test_les_etats_se_comptent_et_se_nomment(self):
        journal = self._session("Etats des items", str(self.chemin), "")
        for etat in ("ok", "ko", "douteux", "en_cours"):
            self.assertIn(etat, journal.texte)

    def test_un_item_est_nomme_par_sa_CLEF_et_pas_par_son_empreinte_seule(self):
        """`item_id` est une empreinte : `a3f2b1...`. Illisible pour qui doit
        aller verifier dans SAP. `ItemDebut` porte la clef ; l'ecran la remet
        en face, sinon l'affichage est exact et inutilisable."""
        journal = self._session("Etats des items", str(self.chemin), "")
        self.assertIn("site=K75", journal.texte)
        self.assertIn("site=K77", journal.texte)

    def test_un_item_sans_etat_terminal_est_signale(self):
        """K78 : ouvert, jamais referme, aucune sauvegarde. Il reste
        `en_cours` — donc rejouable — et c'est le signe qu'une execution s'est
        interrompue. Un compteur seul ne le dirait pas."""
        journal = self._session("Etats des items", str(self.chemin), "")
        self.assertIn("sans etat terminal", journal.texte)
        self.assertIn("site=K78", journal.texte)

    # -- douteux -----------------------------------------------------------

    def test_le_douteux_est_deduit_du_repli_et_montre_avec_ses_sauvegardes(self):
        """K77 n'a pas d'`ItemFin` mais une sauvegarde reussie. Le nombre de
        sauvegardes est la seule chose qui dise a un humain ce qu'il doit
        aller verifier dans SAP."""
        journal = self._session("douteux", str(self.chemin), "")
        self.assertIn("site=K77", journal.texte)
        self.assertIn("1 sauvegarde(s) passee(s)", journal.texte)
        self.assertIn("double ecriture", journal.texte)

    def test_ni_les_termines_ni_les_en_cours_ne_sont_dans_les_douteux(self):
        """K78 est ouvert lui aussi, mais sans sauvegarde : il est rejouable.
        Le confondre avec un douteux ferait arbitrer a la main un item que la
        reprise sait reprendre."""
        journal = self._session("douteux", str(self.chemin), "")
        arbitrer = journal.texte.split("a arbitrer")[-1]
        for site in ("K75", "K76", "K78"):
            self.assertNotIn(f"site={site}", arbitrer)

    def test_un_journal_sans_douteux_le_dit(self):
        from falcon.journal import Ecrivain, ItemDebut, ItemFin

        propre = self.racine / "propre.jsonl"
        with Ecrivain(propre) as ecrivain:
            ecrivain.ecrire(ItemDebut(run_id="R2", item_id="abc"))
            ecrivain.ecrire(ItemFin(run_id="R2", item_id="abc", etat="ok"))
        journal = self._session("douteux", str(propre), "")
        self.assertIn("Rien a arbitrer", journal.texte)

    # -- reexport ----------------------------------------------------------

    def test_le_reexport_ecrit_les_ko_au_format_d_origine(self):
        from falcon.donnees import lire

        cible = self.racine / "ko.csv"
        journal = self._session("Reexporter", str(self.chemin),
                                str(self.jeu), str(cible), "")
        self.assertTrue(cible.exists(), journal.texte)

        octets = cible.read_bytes()
        self.assertIn(b";", octets)
        self.assertIn(b"\r\n", octets)

        lignes, dialecte = lire(cible)
        self.assertEqual(dialecte.delimiteur, ";")
        self.assertEqual([l["site"] for l in lignes], ["K76", "K76"])

    def test_le_reexport_ECARTE_les_douteux_et_le_dit(self):
        """Le point le plus important de cet ecran. Un fichier de KO est fait
        pour etre reinjecte tel quel ; y laisser un item qui a peut-etre deja
        ecrit dans SAP en ferait un chemin vers la double ecriture, par le
        canal meme qui est cense etre sur."""
        from falcon.donnees import lire

        cible = self.racine / "ko.csv"
        journal = self._session("Reexporter", str(self.chemin),
                                str(self.jeu), str(cible), "")
        self.assertIn("ECARTE", journal.texte)
        self.assertIn("site=K77", journal.texte)

        lignes, _ = lire(cible)
        self.assertNotIn("K77", [l["site"] for l in lignes])

    def test_le_reexport_porte_le_nombre_de_sauvegardes(self):
        """Sans lui, l'humain qui relit le fichier n'a aucun moyen de savoir
        qu'un item a deja ecrit dans SAP."""
        cible = self.racine / "ko.csv"
        self._session("Reexporter", str(self.chemin), str(self.jeu),
                      str(cible), "")
        self.assertIn("falcon_sauvegardes",
                      cible.read_text(encoding="cp1252"))

    def test_le_reexport_remplit_les_CINQ_colonnes_de_diagnostic(self):
        """Une colonne vide dans un fichier de KO, c'est un tri que l'humain
        devra refaire a la main — donc le benefice annule sur les cas
        difficiles, qui sont precisement ceux qui coutent.

        `falcon_categorie` et `falcon_entree` viennent de l'`Incident`, le
        seul enregistrement ou la taxonomie ait dit ce qu'elle a reconnu.
        `ItemFin.incident` est un message libre : il va dans
        `falcon_message`, pas dans une colonne de classement.
        """
        from falcon.donnees import COLONNES_DIAGNOSTIC

        cible = self.racine / "ko.csv"
        self._session("Reexporter", str(self.chemin), str(self.jeu),
                      str(cible), "")
        texte = cible.read_text(encoding="cp1252")
        entete, premiere = texte.splitlines()[0], texte.splitlines()[1]
        for colonne in COLONNES_DIAGNOSTIC:
            self.assertIn(colonne, entete)

        valeurs = dict(zip(entete.split(";"), premiere.split(";")))
        self.assertEqual(valeurs["falcon_categorie"], "connue_fautive")
        self.assertEqual(valeurs["falcon_entree"], "relecture_divergente")
        self.assertEqual(valeurs["falcon_message"], "champ_absent")
        self.assertEqual(valeurs["falcon_sauvegardes"], "0")
        self.assertTrue(valeurs["falcon_item_id"])

    def test_le_reexport_reste_reinjectable_sans_retouche(self):
        """Les colonnes `falcon_` sont retirees a la lecture : le fichier
        produit se regroupe par les memes clefs que le jeu d'origine."""
        from falcon.donnees import grouper, lire

        cible = self.racine / "ko.csv"
        self._session("Reexporter", str(self.chemin), str(self.jeu),
                      str(cible), "")
        lignes, _ = lire(cible)
        self.assertEqual(len(grouper(lignes, ["site"])), 1)

    def test_l_item_reexporte_rend_TOUTES_ses_lignes(self):
        """K76 en a deux. Reexporter un resume au lieu du jeu d'origine
        rendrait le fichier non reinjectable — c'est tout l'item qui doit
        repartir, pas la ligne qui a echoue."""
        from falcon.donnees import lire

        cible = self.racine / "ko.csv"
        self._session("Reexporter", str(self.chemin), str(self.jeu),
                      str(cible), "")
        lignes, _ = lire(cible)
        self.assertEqual(sorted(l["equipement"] for l in lignes),
                         ["200", "201"])

    def test_le_reexport_n_ecrase_jamais_un_fichier_existant(self):
        """Le journal dont il vient est peut-etre le seul temoin de ce qui
        s'est passe. Refuser coute une saisie ; ecraser coute la trace."""
        cible = self.racine / "deja.csv"
        cible.write_bytes(b"ne pas ecraser\r\n")
        journal = self._session("Reexporter", str(self.chemin),
                                str(self.jeu), str(cible), "")
        self.assertIn("existe deja", journal.texte)
        self.assertEqual(cible.read_bytes(), b"ne pas ecraser\r\n")

    def test_un_journal_sans_ko_ne_produit_pas_de_fichier(self):
        from falcon.journal import Ecrivain, ItemDebut, ItemFin

        propre = self.racine / "propre.jsonl"
        with Ecrivain(propre) as ecrivain:
            ecrivain.ecrire(ItemDebut(run_id="R2", item_id="abc"))
            ecrivain.ecrire(ItemFin(run_id="R2", item_id="abc", etat="ok"))
        cible = self.racine / "vide.csv"
        journal = self._session("Reexporter", str(propre), str(cible), "")
        self.assertIn("Aucun KO", journal.texte)
        self.assertFalse(cible.exists())

    def test_un_ko_sans_lignes_dans_le_journal_est_nomme_et_pas_invente(self):
        """Un journal ancien peut n'avoir pas d'`ItemDebut.brut`. Reconstruire
        les lignes a partir de la clef donnerait un fichier plausible et faux ;
        le seul comportement juste est de nommer l'item et de s'arreter la."""
        from falcon.journal import Ecrivain, ItemDebut, ItemFin

        maigre = self.racine / "maigre.jsonl"
        with Ecrivain(maigre) as ecrivain:
            ecrivain.ecrire(ItemDebut(run_id="R3", item_id="abc",
                                      cle={"site": "K99"}))
            ecrivain.ecrire(ItemFin(run_id="R3", item_id="abc", etat="ko"))
        journal = self._session("Reexporter", str(maigre), "")
        self.assertIn("sans lignes d'entree", journal.texte)
        self.assertIn("site=K99", journal.texte)
        self.assertIn("Aucun KO", journal.texte)

    # -- innocuite ---------------------------------------------------------

    def test_aucun_ecran_de_cette_branche_ne_touche_au_journal(self):
        """Le journal fait foi. Ni retouche, ni cloture, ni arbitrage : ce
        sont des gestes qui se font dans SAP, pas dans un menu."""
        avant = self.chemin.read_bytes()
        horodatage = self.chemin.stat().st_mtime_ns

        for libelle, saisies in (
                ("Rapport de fin", (str(self.chemin), "")),
                ("Etats des items", (str(self.chemin), "")),
                ("douteux", (str(self.chemin), "")),
                ("Reexporter", (str(self.chemin), str(self.jeu),
                                str(self.racine / "ko.csv"), ""))):
            self._session(libelle, *saisies)

        self.assertEqual(self.chemin.read_bytes(), avant)
        self.assertEqual(self.chemin.stat().st_mtime_ns, horodatage)

    def test_aucun_ecran_de_lecture_ne_produit_de_fichier(self):
        """Seul le reexport ecrit, et seulement la ou on le lui dit."""
        avant = {c.name for c in self.racine.iterdir()}
        for libelle in ("Rapport de fin", "Etats des items", "douteux"):
            self._session(libelle, str(self.chemin), "")
        self.assertEqual({c.name for c in self.racine.iterdir()}, avant)


class TestExportsDeTable(unittest.TestCase):
    """Les exports conserves, et ce qui a bouge entre deux.

    Une volumique ne porte ni journal par item, ni reprise fine : sa valeur
    est dans le RAPPROCHEMENT. Un export seul dit l'etat d'une table a un
    instant ; deux exports disent ce qui a change — et ce sont les
    modifications, pas les ajouts, qui ne se voient pas a l'oeil.
    """

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name)

    def _provenance(self, horodatage: str, **extra):
        from falcon.volumique import Provenance

        defauts = dict(systeme="K75", mandant="210", table="EQUI",
                       horodatage=horodatage, utilisateur="DUPONT",
                       criteres={"WERKS": "K750"})
        return Provenance(**{**defauts, **extra})

    def _poser(self, horodatage: str, lignes, **extra):
        from falcon.volumique import enregistrer

        return enregistrer(self.racine, self._provenance(horodatage, **extra),
                           lignes)

    def _session(self, libelle: str, *saisies: str) -> Journal:
        journal = Journal(*vers(racine(), "Exports de table", libelle),
                          *saisies, "0", "0")
        parcourir(racine(), journal.console())
        return journal

    # -- lister ------------------------------------------------------------

    def test_les_exports_se_listent_du_plus_ancien_au_plus_recent(self):
        self._poser("2026-01-15T08-00-00", [{"EQUNR": "1", "TPLNR": "A"}])
        self._poser("2026-02-15T08-00-00", [{"EQUNR": "1", "TPLNR": "B"}])
        journal = self._session("Lister", str(self.racine), "K75", "EQUI", "")
        self.assertIn("2 export(s)", journal.texte)
        self.assertLess(journal.texte.index("2026-01-15"),
                        journal.texte.index("2026-02-15"))

    def test_la_provenance_de_chaque_export_est_rendue(self):
        """« De quoi savoir, six mois plus tard, ce qu'on est en train de
        comparer. » Un export sans sa provenance affichee, c'est un fichier
        dont on ne peut plus rien dire."""
        self._poser("2026-01-15T08-00-00", [{"EQUNR": "1"}])
        journal = self._session("Lister", str(self.racine), "K75", "EQUI", "")
        self.assertIn("K75/210", journal.texte)
        self.assertIn("EQUI", journal.texte)
        self.assertIn("DUPONT", journal.texte)
        self.assertIn("WERKS = K750", journal.texte)
        self.assertIn("1", journal.texte)

    def test_un_couple_sans_export_le_dit(self):
        journal = self._session("Lister", str(self.racine), "P01", "MARA", "")
        self.assertIn("Aucun export conserve", journal.texte)

    def test_sans_systeme_ni_table_il_n_y_a_rien_a_lister(self):
        """Un export se range par systeme ET par table. Melanger les systemes
        rendrait le rapprochement dependant d'un nom de fichier bien lu."""
        journal = self._session("Lister", str(self.racine), "", "", "")
        self.assertIn("par systeme ET par table", journal.texte)

    def test_un_export_illisible_est_signale_a_sa_place(self):
        """Et n'interrompt pas la liste : les autres restent consultables."""
        self._poser("2026-01-15T08-00-00", [{"EQUNR": "1"}])
        (self.racine / "K75" / "EQUI_2026-02-15T08-00-00.jsonl").write_text(
            "pas un export\n", encoding="utf-8")
        journal = self._session("Lister", str(self.racine), "K75", "EQUI", "")
        self.assertIn("ILLISIBLE", journal.texte)
        self.assertIn("2026-01-15", journal.texte)
        self.assertNotIn("Traceback", journal.texte)

    # -- comparer ----------------------------------------------------------

    def test_le_delta_montre_les_modifications_colonne_par_colonne(self):
        """C'est le seul des trois genres d'ecart qui ne se voit pas a l'oeil :
        une ligne toujours la, dont une colonne a change."""
        self._poser("2026-01-15T08-00-00",
                    [{"EQUNR": "1", "TPLNR": "A"},
                     {"EQUNR": "2", "TPLNR": "B"}])
        self._poser("2026-02-15T08-00-00",
                    [{"EQUNR": "1", "TPLNR": "Z"},
                     {"EQUNR": "3", "TPLNR": "C"}])
        journal = self._session("Comparer", str(self.racine), "K75", "EQUI",
                                "EQUNR", "")
        self.assertIn("ajoutes    1", journal.texte)
        self.assertIn("retires    1", journal.texte)
        self.assertIn("modifies   1", journal.texte)
        self.assertIn("'A' -> 'Z'", journal.texte)

    def test_sans_clef_la_comparaison_est_REFUSEE(self):
        """Rapprocher par rang produirait des modifications imaginaires des
        que l'ordre change. Le refus est le bon resultat."""
        self._poser("2026-01-15T08-00-00", [{"EQUNR": "1"}])
        self._poser("2026-02-15T08-00-00", [{"EQUNR": "1"}])
        journal = self._session("Comparer", str(self.racine), "K75", "EQUI",
                                "", "")
        self.assertIn("Comparaison refusee", journal.texte)
        self.assertIn("rang", journal.texte)
        self.assertNotIn("Traceback", journal.texte)

    def test_une_clef_qui_ne_resout_pas_est_refusee_situee(self):
        self._poser("2026-01-15T08-00-00", [{"EQUNR": "1"}])
        self._poser("2026-02-15T08-00-00", [{"EQUNR": "1"}])
        journal = self._session("Comparer", str(self.racine), "K75", "EQUI",
                                "MATNR", "")
        self.assertIn("Comparaison refusee", journal.texte)
        self.assertIn("MATNR", journal.texte)

    def test_un_seul_export_ne_se_compare_a_rien(self):
        self._poser("2026-01-15T08-00-00", [{"EQUNR": "1"}])
        journal = self._session("Comparer", str(self.racine), "K75", "EQUI", "")
        self.assertIn("Il en faut", journal.texte)

    def test_deux_exports_identiques_le_disent(self):
        self._poser("2026-01-15T08-00-00", [{"EQUNR": "1", "TPLNR": "A"}])
        self._poser("2026-02-15T08-00-00", [{"EQUNR": "1", "TPLNR": "A"}])
        journal = self._session("Comparer", str(self.racine), "K75", "EQUI",
                                "EQUNR", "")
        self.assertIn("Rien n'a bouge", journal.texte)

    # -- carte -------------------------------------------------------------

    def test_la_carte_livree_est_annoncee_INCOMPLETE_avec_ce_qui_manque(self):
        """Elle est livree vide, et c'est voulu : ces identifiants ne sont pas
        devinables. Un ecran qui la presenterait comme utilisable inviterait a
        piloter un ecran que personne n'a jamais vu."""
        journal = self._session("carte", "")
        self.assertIn("INCOMPLETE", journal.texte)
        self.assertIn("champ_table", journal.texte)
        self.assertIn("ecran_selection", journal.texte)

    def test_la_carte_renvoie_a_la_commande_qui_la_remplit(self):
        journal = self._session("carte", "")
        self.assertIn("python -m falcon diagnostiquer", journal.texte)

    def test_la_carte_dit_que_l_export_refuse_avant_de_naviguer(self):
        """Ce n'est pas un avertissement : c'est le comportement. Le dire ici
        evite de decouvrir le refus au moment de lancer."""
        journal = self._session("carte", "")
        self.assertIn("refuse avant toute navigation", journal.texte)

    # -- innocuite ---------------------------------------------------------

    def test_aucun_ecran_de_cette_branche_n_ecrit_ni_n_ecrase(self):
        """Un export conserve est la seule trace d'un etat de table a une
        date : le reecrire, c'est perdre le point de comparaison."""
        self._poser("2026-01-15T08-00-00", [{"EQUNR": "1", "TPLNR": "A"}])
        self._poser("2026-02-15T08-00-00", [{"EQUNR": "1", "TPLNR": "Z"}])
        avant = {c: (c.read_bytes(), c.stat().st_mtime_ns)
                 for c in (self.racine / "K75").iterdir()}

        for libelle, saisies in (
                ("Lister", (str(self.racine), "K75", "EQUI", "")),
                ("Comparer", (str(self.racine), "K75", "EQUI", "EQUNR", "")),
                ("carte", ("",))):
            self._session(libelle, *saisies)

        apres = {c: (c.read_bytes(), c.stat().st_mtime_ns)
                 for c in (self.racine / "K75").iterdir()}
        self.assertEqual(avant, apres)

    def test_la_carte_livree_avec_le_paquet_n_est_jamais_modifiee(self):
        from falcon.volumique import CHEMIN_CARTE_DEFAUT

        avant = CHEMIN_CARTE_DEFAUT.read_bytes()
        self._session("carte", "")
        self.assertEqual(CHEMIN_CARTE_DEFAUT.read_bytes(), avant)


EXECUTABLE = """
    version: 1
    nom: bcp_ia08_variantes
    classe: iterative
    cles: [site]
    plafond_items: 50
    plafond_sauvegardes: 50
    etapes:
      - nom: saisir
        action: set
        cible: "wnd[0]/usr/ctxtWERKS-LOW"
        source: {colonne: site}
        ecran: {transaction: IA08, programme: RIPLKO10, dynpro: "1000"}
      - nom: sauver
        action: press
        cible: "wnd[0]/tbar[0]/btn[11]"
        sauvegarde: true
        ecran: {transaction: IA08, programme: RIPLKO10, dynpro: "1000"}
    """


class TestExecution(unittest.TestCase):
    """Executer depuis la console. **C'est ici que ca ecrit dans un ERP.**

    Les tests de cette classe ne verifient pas que le moteur marche — le lot
    10 s'en charge, contre le meme double. Ils verifient ce que la console
    ajoute au-dessus : ce qui est montre avant, ce qui est exige pour partir,
    et ce qui ne part pas quand on ne l'exige pas.
    """

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name)
        self.pipeline = self.racine / "p.yaml"
        self.pipeline.write_text(textwrap.dedent(EXECUTABLE), encoding="utf-8")
        self.jeu = self.racine / "jeu.csv"
        self.jeu.write_text("site,libelle\n1000,Paris\n2000,Lyon\n",
                            encoding="utf-8")
        self.journal = self.racine / "journal.jsonl"
        self.progres = []
        self.driver = self._driver()

    def _driver(self) -> DriverScripte:
        driver = DriverScripte(identite=IA08,
                               valeurs={"wnd[0]/usr/ctxtWERKS-LOW": ""})

        def relire(pilote, geste, cible):
            if geste == "write":
                pilote.valeurs[cible] = pilote.valeurs.get(cible, "")

        driver.apres_action = relire
        return driver

    def _env(self, **extra) -> Environnement:
        return Environnement(
            connecter=lambda: self.driver,
            rapporteur=lambda: self.progres.append,
            **extra)

    def _session(self, libelle: str, *saisies: str, env=None) -> Journal:
        env = env if env is not None else self._env()
        arbre = racine(env)
        journal = Journal(*vers(arbre, "Pipelines", libelle), *saisies,
                          "0", "0")
        parcourir(arbre, journal.console())
        return journal

    def _saisies(self, mot: str | None = "bcp_ia08_variantes"):
        """pipeline, jeu, journal, puis la confirmation si on en attend une."""
        base = [str(self.pipeline), str(self.jeu), str(self.journal)]
        return base if mot is None else base + [mot]

    # -- l'ordre des entrees -----------------------------------------------

    def test_la_repetition_a_blanc_est_proposee_AVANT_l_execution(self):
        """L'ordre n'est pas cosmetique : c'est la seule chose qui suggere,
        a qui parcourt le menu de haut en bas, d'essayer sans ecrire d'abord.
        """
        entrees = [e.libelle for e in
                   racine().entrees[2].cible.entrees]
        blanc = next(i for i, l in enumerate(entrees) if "blanc" in l)
        executer_ = next(i for i, l in enumerate(entrees) if l == "Executer")
        reprendre = next(i for i, l in enumerate(entrees) if "Reprendre" in l)
        self.assertLess(blanc, executer_)
        self.assertLess(executer_, reprendre)

    def test_les_ecrans_qui_ecrivent_le_disent_dans_leur_libelle(self):
        """Un menu ou « Executer » ressemble a « Inspecter » est un piege."""
        entrees = racine().entrees[2].cible.entrees
        for entree in entrees:
            if entree.libelle in ("Executer", "Reprendre une execution",
                                  "Enchainer des pipelines"):
                self.assertIn("ECRIT DANS SAP", entree.detail)

    # -- la confirmation ---------------------------------------------------

    def test_une_execution_reelle_exige_le_nom_de_la_pipeline(self):
        journal = self._session("Executer", *self._saisies(), "")
        self.assertIn("Ceci va ECRIRE dans SAP", journal.texte)
        self.assertTrue(self.journal.exists(), journal.texte)
        self.assertTrue(self.driver.gestes)

    def test_un_mot_faux_ANNULE_et_rien_n_est_ecrit(self):
        """Le defaut est de ne pas ecrire dans un ERP."""
        journal = self._session("Executer", *self._saisies("oui"), "")
        self.assertIn("Annule", journal.texte)
        self.assertEqual(self.driver.gestes, [])
        self.assertFalse(self.journal.exists())

    def test_une_confirmation_VIDE_annule(self):
        journal = self._session("Executer", *self._saisies(""), "")
        self.assertIn("Annule", journal.texte)
        self.assertEqual(self.driver.gestes, [])

    def test_une_fin_de_flux_a_la_confirmation_annule(self):
        """Ni « o », ni un flux epuise, ni un Ctrl-C ne valent un accord. La
        seule chose qui vaille accord, c'est le mot exact."""
        journal = Journal(*vers(racine(), "Pipelines", "Executer"),
                          *self._saisies(None))
        parcourir(racine(self._env()), journal.console())
        self.assertEqual(self.driver.gestes, [])

    def test_o_ne_confirme_pas(self):
        """Un `o/n` se tape sans lire. C'est un reflexe, pas un consentement."""
        self._session("Executer", *self._saisies("o"), "")
        self.assertEqual(self.driver.gestes, [])

    def test_la_confirmation_n_est_demandee_qu_APRES_le_recapitulatif(self):
        journal = self._session("Executer", *self._saisies(), "")
        self.assertLess(journal.texte.index("PLAFOND sauvegardes"),
                        journal.texte.index("Ceci va ECRIRE"))

    # -- le recapitulatif --------------------------------------------------

    def test_le_recapitulatif_montre_LES_DEUX_plafonds(self):
        """Omettre l'un laisserait croire que l'autre n'existe pas — or c'est
        celui des sauvegardes qui borne ce qui part dans SAP."""
        journal = self._session("Executer", *self._saisies("non"), "")
        self.assertIn("PLAFOND items         50", journal.texte)
        self.assertIn("PLAFOND sauvegardes   50", journal.texte)

    def test_le_recapitulatif_montre_les_empreintes_et_le_nombre_d_items(self):
        from falcon.donnees import empreinte_jeu
        from falcon.pipeline import charger

        journal = self._session("Executer", *self._saisies("non"), "")
        self.assertIn(charger(self.pipeline).empreinte, journal.texte)
        self.assertIn(empreinte_jeu(self.jeu), journal.texte)
        self.assertIn("items a traiter       2", journal.texte)

    def test_le_recapitulatif_montre_les_valeurs_composees(self):
        """Avant d'ecrire dans un ERP, il faut voir ce qui sera TAPE — pas la
        colonne dont ca vient."""
        socle = textwrap.dedent(EXECUTABLE).rstrip() + "\n"
        # Quatre espaces, pas huit : `socle` est deja passe par `dedent`.
        compose = socle.replace(
            "    source: {colonne: site}",
            '    source: {gabarit: "/BCP01_{site}"}\n'
            "    format: [majuscules]")
        self.assertNotEqual(compose, socle, "le remplacement n'a rien fait")
        self.pipeline.write_text(compose, encoding="utf-8")
        journal = self._session("Executer", *self._saisies("non"), "")
        self.assertIn("valeurs COMPOSEES", journal.texte)
        self.assertIn("/BCP01_{site}", journal.texte)
        self.assertIn("majuscules", journal.texte)
        self.assertIn("ce n'est pas la colonne qui part dans SAP".lower(),
                      journal.texte.lower())

    def test_le_recapitulatif_nomme_les_etapes_qui_sauvent(self):
        journal = self._session("Executer", *self._saisies("non"), "")
        self.assertIn("etapes qui sauvent    sauver", journal.texte)

    def test_les_derogations_sortent_avec_leur_motif(self):
        """Une derogation sans son motif est une case cochee, que personne ne
        peut contester au moment ou il faudrait."""
        # `EXECUTABLE` se termine par l'indentation de sa triple-quote
        # fermante : y concatener un bloc le decalerait, et le test tomberait
        # sur une erreur d'indentation plutot que sur ce qu'il verifie.
        socle = textwrap.dedent(EXECUTABLE).rstrip() + "\n"
        derogation = (
            '    derogations:\n'
            '      - garde: statut\n'
            '        portee: "etape:sauver"\n'
            '        motif: "IA08 ne rend aucun message sur cette validation"\n')
        self.pipeline.write_text(socle + derogation, encoding="utf-8")
        journal = self._session("Executer", *self._saisies("non"), "")
        self.assertIn("DEROGATIONS", journal.texte)
        self.assertIn("IA08 ne rend aucun message", journal.texte)

    # -- la repetition a blanc ---------------------------------------------

    def test_la_repetition_a_blanc_ne_demande_AUCUNE_confirmation(self):
        """Il n'y a rien a confirmer : elle s'arrete avant toute validation."""
        journal = self._session("blanc", *self._saisies(None), "")
        self.assertNotIn("Ceci va ECRIRE dans SAP", journal.texte)
        self.assertIn("mode                  dry-run", journal.texte)

    def test_la_repetition_a_blanc_n_appuie_sur_rien(self):
        """La preuve par le double : le moteur a joue, et aucun `press` n'a
        atteint le driver."""
        self._session("blanc", *self._saisies(None), "")
        self.assertTrue(self.journal.exists())
        self.assertNotIn("press", [geste for geste, _, _ in self.driver.gestes])

    # -- la reprise --------------------------------------------------------

    def test_la_reprise_exige_aussi_la_confirmation(self):
        self._session("Executer", *self._saisies(), "")
        gestes = len(self.driver.gestes)
        self._session("Reprendre", *self._saisies("non"), "")
        self.assertEqual(len(self.driver.gestes), gestes)

    def test_une_reprise_sans_journal_le_dit_sans_trace_de_pile(self):
        journal = self._session("Reprendre", *self._saisies(), "")
        self.assertNotIn("Traceback", journal.texte)

    # -- la progression ----------------------------------------------------

    def test_le_rapporteur_est_branche_sur_le_moteur(self):
        """La barre et l'ETA glissant existent depuis le lot 11 et n'avaient
        jamais rien affiche : personne ne les appelait."""
        self._session("Executer", *self._saisies(), "")
        self.assertEqual(len(self.progres), 2)
        self.assertEqual([p.item for p in self.progres],
                         [p.item for p in self.progres])
        self.assertEqual(self.progres[-1].total, 2)

    def test_le_rapporteur_par_defaut_est_celui_du_lot_11(self):
        from falcon.supervision import Rapporteur

        self.assertIsInstance(Environnement().rapporteur(), Rapporteur)

    # -- les refus ---------------------------------------------------------

    def test_une_pipeline_volumique_est_refusee_avant_toute_connexion(self):
        """La machinerie par item ne sert qu'aux iteratives (§3.5)."""
        self.pipeline.write_text(textwrap.dedent("""
            version: 1
            nom: export_equi
            classe: volumique
            plafond_items: 50
            plafond_sauvegardes: 50
            etapes:
              - nom: saisir
                action: set
                cible: "wnd[0]/usr/ctxtTAB"
                source: {constante: EQUI}
                ecran: {transaction: SE16N, programme: X, dynpro: "0100"}
            """), encoding="utf-8")
        journal = self._session("Executer", str(self.pipeline), "")
        self.assertIn("volumique", journal.texte)
        self.assertEqual(self.driver.gestes, [])

    def test_un_jeu_illisible_est_refuse_avant_toute_connexion(self):
        """Tomber a la preparation coute une saisie ; tomber a l'item quarante
        coute trente-neuf ecritures a demeler."""
        casse = self.racine / "casse.csv"
        casse.write_text("libelle\nParis\n", encoding="utf-8")
        journal = self._session("Executer", str(self.pipeline), str(casse), "")
        self.assertIn("Refuse", journal.texte)
        self.assertEqual(self.driver.gestes, [])

    def test_une_session_indisponible_se_dit_APRES_la_confirmation(self):
        def refuser():
            raise SapIndisponible("pywin32 n'est pas installe")

        journal = self._session("Executer", *self._saisies(), "",
                                env=Environnement(connecter=refuser))
        self.assertIn("SapIndisponible", journal.texte)
        self.assertNotIn("Traceback", journal.texte)

    # -- la chaine ---------------------------------------------------------

    def test_une_chaine_se_construit_maillon_par_maillon(self):
        second = self.racine / "j2.jsonl"
        journal = self._session(
            "Enchainer",
            str(self.pipeline), str(self.jeu), str(self.journal),
            str(self.pipeline), str(self.jeu), str(second),
            "", "bcp_ia08_variantes", "")
        self.assertIn("2 maillon(s)", journal.texte)
        self.assertTrue(self.journal.exists(), journal.texte)
        self.assertTrue(second.exists(), journal.texte)

    def test_une_chaine_vide_ne_lance_rien(self):
        journal = self._session("Enchainer", "", "")
        self.assertIn("Chaine vide", journal.texte)
        self.assertEqual(self.driver.gestes, [])

    def test_une_chaine_non_confirmee_ne_lance_rien(self):
        journal = self._session(
            "Enchainer", str(self.pipeline), str(self.jeu),
            str(self.journal), "", "non", "")
        self.assertIn("Annule", journal.texte)
        self.assertEqual(self.driver.gestes, [])
        self.assertFalse(self.journal.exists())

    def test_la_chaine_annonce_qu_aucune_donnee_ne_circule(self):
        """C'est la limite qui l'empeche de devenir un orchestrateur (§3.3),
        et elle doit se lire la ou quelqu'un pourrait compter dessus."""
        journal = self._session("Enchainer", "", "")
        self.assertIn("AUCUNE donnee ne passe", journal.texte)

    # -- innocuite ---------------------------------------------------------

    def test_la_console_ne_manipule_jamais_un_driver_nu(self):
        """La propriete du lot 14, adaptee : la console appelle desormais le
        moteur, qui appelle des methodes mutantes. Ce qui reste vrai — et ce
        que ce test epingle — c'est que rien dans `falcon/console/` ne touche
        un `Driver` autrement qu'en le passant au moteur, qui l'enveloppe
        aussitot dans un `DriverGarde`.
        """
        for module, arbre in _arbres():
            for noeud in ast.walk(arbre):
                if not isinstance(noeud, ast.Call):
                    continue
                if not isinstance(noeud.func, ast.Attribute):
                    continue
                with self.subTest(module=module, ligne=noeud.lineno):
                    self.assertNotIn(
                        noeud.func.attr, MUTATIONS,
                        f"{module}:{noeud.lineno} appelle {noeud.func.attr!r} "
                        f"— une methode mutante de la couture")
