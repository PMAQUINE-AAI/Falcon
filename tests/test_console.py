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
