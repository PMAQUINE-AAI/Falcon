"""La ligne de commande, et le premier contact reel — en lecture seule.

La propriete de ce lot est structurelle, pas documentaire : `diagnostiquer`
ne recoit qu'un `DriverLecture`, une facade qui n'a ni `write`, ni `press`,
ni `vkey`. Ajouter une ecriture dans la commande ne se contenterait pas d'etre
mal vu — l'attribut n'existe pas, et l'appel leve.

C'est le troisieme controle negatif prevu au plan : « un appel d'ecriture dans
`diagnostiquer` doit faire tomber un test ». Il tombe, et pour une raison
mecanique.
"""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from falcon.catalogue import ESQUISSE, OBSERVEE, Depot, clef_de
from falcon.commandes import analyseur, diagnostiquer, main, rapport
from falcon.couture import OBSERVATION, Driver, DriverLecture
from falcon.couture.double import DriverScripte
from falcon.noyau import Champ, Fenetre, Identite, Statut

from tests.test_gardes import LECTURES, MUTATIONS

IA08 = Identite(systeme="K75", mandant="210", langue="FR",
                transaction="IA08", programme="RIPLKO10", dynpro="1000")

MEGATRACE = "tests/fixtures/traces/megatrace_2026-09.vbs"


def _brut() -> DriverScripte:
    return DriverScripte(
        identite=IA08,
        statut=Statut(type="S", id="CP", numero="045", texte="Enregistre"),
        fenetres=(Fenetre(id="wnd[0]", type="GuiMainWindow", titre="Ordres"),
                  Fenetre(id="wnd[1]", type="GuiModalWindow", titre="Variante")),
        champs=(Champ(id="wnd[0]/usr/ctxtWERKS-LOW", type="GuiCTextField",
                      nom="WERKS-LOW", texte="1000", infobulle="Division"),
                Champ(id="wnd[0]/usr/chkDY_MAB", type="GuiCheckBox",
                      nom="DY_MAB", modifiable=False)))


def _lancer(*arguments: str) -> tuple[int, str, str]:
    sortie, erreurs = io.StringIO(), io.StringIO()
    with redirect_stdout(sortie), redirect_stderr(erreurs):
        code = main(list(arguments))
    return code, sortie.getvalue(), erreurs.getvalue()


class TestLectureSeule(unittest.TestCase):
    """« Aucune ecriture » tenu par la structure, pas par la relecture."""

    def test_la_facade_n_expose_que_l_observation(self):
        exposees = {n for n in dir(DriverLecture) if not n.startswith("_")}
        self.assertEqual(exposees, set(OBSERVATION))

    def test_aucune_methode_mutante_n_est_atteignable(self):
        """Epingle contre la surface de couture, pas contre une liste locale.

        Une methode mutante ajoutee a la couture et recopiee par megarde dans
        la facade ferait tomber ce test.
        """
        lecteur = DriverLecture(_brut())
        for methode in sorted(MUTATIONS):
            with self.subTest(methode=methode):
                self.assertFalse(hasattr(lecteur, methode))

    def test_la_facade_couvre_toutes_les_lectures_sans_effet(self):
        self.assertLessEqual(set(OBSERVATION), LECTURES)

    def test_la_facade_n_est_pas_un_driver(self):
        """Si elle en etait un, il faudrait lui donner les dix-huit methodes —
        c'est-a-dire exactement celles qu'on cherche a retirer."""
        self.assertFalse(issubclass(DriverLecture, Driver))

    def test_le_driver_sous_jacent_n_est_pas_accessible(self):
        lecteur = DriverLecture(_brut())
        self.assertEqual([n for n in vars(lecteur) if "driver" in n.lower()
                          and not n.startswith("_DriverLecture")], [])

    def test_un_diagnostic_ne_touche_a_rien(self):
        """Le controle negatif du plan, verifie sur les gestes reellement
        effectues sur le driver brut."""
        brut = _brut()
        diagnostiquer(DriverLecture(brut))
        self.assertEqual(brut.gestes, [])


class TestRapport(unittest.TestCase):

    def setUp(self):
        self.texte = rapport(DriverLecture(_brut()))

    def test_l_identite_complete_est_rendue(self):
        for attendu in ("K75", "210", "FR", "IA08", "RIPLKO10", "1000"):
            with self.subTest(valeur=attendu):
                self.assertIn(attendu, self.texte)

    def test_l_empreinte_de_variante_est_rendue(self):
        """C'est la clef par laquelle le catalogue distinguera ce rendu-ci
        d'un autre rendu du meme dynpro."""
        brut = _brut()
        self.assertIn(brut.fields().empreinte, self.texte)

    def test_les_fenetres_ouvertes_et_leur_nature_sont_rendues(self):
        self.assertIn("wnd[1]", self.texte)
        self.assertIn("modale", self.texte)

    def test_le_statut_est_rendu_avec_sa_clef(self):
        self.assertIn("CP:045", self.texte)

    def test_une_barre_vide_est_dite_vide(self):
        brut = _brut()
        brut.statut = Statut()
        self.assertIn("barre vide", rapport(DriverLecture(brut)))

    def test_un_champ_fige_est_signale(self):
        """Ecrire dans un champ non modifiable est un echec silencieux
        classique : la valeur ne prend pas, et rien ne leve."""
        self.assertIn("(fige)", self.texte)

    def test_chaque_champ_apparait_avec_son_identifiant_complet(self):
        for champ in _brut().champs:
            with self.subTest(champ=champ.id):
                self.assertIn(champ.id, self.texte)


class TestCatalogage(unittest.TestCase):
    """Un releve va en quarantaine, jamais au catalogue cure."""

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name) / "catalogue"
        self.brut = _brut()
        self.texte = diagnostiquer(DriverLecture(self.brut),
                                   catalogue=self.racine)

    def test_le_releve_va_en_quarantaine(self):
        depot = Depot(self.racine)
        clef = clef_de(self.brut.fields())
        self.assertIsNone(depot.pour_edition(clef))
        self.assertIsNotNone(Depot(depot.quarantaine).pour_edition(clef))

    def test_le_releve_est_marque_observe_pas_esquisse(self):
        """Il vient d'un systeme reel : c'est la difference avec ce qu'une
        trace produit."""
        variante = Depot(Depot(self.racine).quarantaine).pour_edition(
            clef_de(self.brut.fields()))
        self.assertEqual(variante.source, OBSERVEE)
        self.assertNotEqual(variante.source, ESQUISSE)

    def test_le_releve_porte_une_date_de_capture(self):
        variante = Depot(Depot(self.racine).quarantaine).pour_edition(
            clef_de(self.brut.fields()))
        self.assertTrue(variante.capture_le)

    def test_la_promotion_est_annoncee_comme_un_geste_explicite(self):
        self.assertIn("quarantaine", self.texte)
        self.assertIn("explicite", self.texte)

    def test_sans_option_rien_n_est_ecrit_sur_le_disque(self):
        diagnostiquer(DriverLecture(_brut()))
        self.assertFalse(self.racine.parent.joinpath("ailleurs").exists())


class TestLigneDeCommande(unittest.TestCase):

    def test_sans_commande_l_aide_sort_en_erreur(self):
        code, sortie, _ = _lancer()
        self.assertEqual(code, 2)
        self.assertIn("diagnostiquer", sortie)

    def test_l_aide_repond(self):
        with self.assertRaises(SystemExit) as capture:
            _lancer("--aide")
        self.assertEqual(capture.exception.code, 0)

    def test_l_aide_dit_LAQUELLE_des_commandes_peut_ecrire(self):
        """Ce test epinglait « aucune n'ecrit dans SAP », et c'etait faux.

        `console` ecrit, sur trois de ses ecrans, depuis le lot d'execution.
        Un texte rassurant a l'endroit exact ou quelqu'un decide qu'il peut
        cliquer sans reflechir est la meme classe de defaut que le reste de ce
        projet traque — et le fait qu'un test le garantissait le rendait
        durable.
        """
        aide = analyseur().format_help()
        self.assertIn("Une seule commande peut ecrire dans SAP", aide)
        self.assertIn("console", aide)
        self.assertNotIn("aucune n'ecrit dans SAP", aide)

    def test_inventaire_marche_sans_sap(self):
        """Le sous-module SAP n'est importe que par `diagnostiquer` : une
        machine qui n'aura jamais de SAP GUI doit pouvoir lire une trace."""
        code, sortie, _ = _lancer("inventaire", MEGATRACE)
        self.assertEqual(code, 0)
        self.assertIn("Toutes les lignes sont appariees", sortie)

    def test_une_erreur_falcon_se_rend_lisible_sans_trace_de_pile(self):
        """Une trace de pile ferait croire a un defaut du programme, alors que
        l'erreur dit deja ce qui ne va pas."""
        code, _, erreurs = _lancer("diagnostiquer")
        self.assertEqual(code, 1)
        self.assertIn("SapIndisponible", erreurs)
        self.assertIn("pywin32", erreurs)
        self.assertNotIn("Traceback", erreurs)

    def test_le_diagnostic_ne_propose_aucune_option_d_ecriture(self):
        aide = analyseur().parse_known_args(["diagnostiquer"])
        options = {a.dest for a in analyseur()._subparsers._group_actions[0]
                   .choices["diagnostiquer"]._actions}
        self.assertEqual(options,
                         {"help", "fenetre", "catalogue", "connexion", "session"})
        self.assertIsNotNone(aide)


if __name__ == "__main__":
    unittest.main()
