"""Table de traduction geste -> couture : fermee, motivee, sans devinette.

Trois proprietes portent ce lot, et les trois sont verifiees ici.

**Fermeture.** La table recouvre exactement `trace.modele.VERBES`. Un verbe
releve sur une trace reelle et oublie dans la table serait un geste que
l'explorateur passerait sous silence : le rejeu differerait de
l'enregistrement sans que rien ne leve.

**Motivation.** Un verbe sans issue n'est pas absent, il est present avec sa
raison — les quatre verbes d'arbre nommement. Une table ou l'arbre manquerait
ressemblerait a un oubli, et quelqu'un l'aurait « corrigee ».

**Refus plutot que conversion.** Un argument de trace n'est pas toujours du
texte : le parseur rend trois types, et l'API SAP les distingue —
`selectedRows` est une CHAINE la ou `currentCellRow` est un ENTIER, sur le
meme objet ALV. La table exige le type observe et refuse l'autre.

Ce qui est mesure sur `megatrace_2026-09.vbs` l'est par execution, pas par
conjecture : 90 gestes, 15 de confort, 10 d'arbre sans issue, 65 traduits —
dont les 12 gestes de grille que `trace/brouillon.py` compte parmi ses 22
« non rejouables », faute d'action de pipeline pour les exprimer.
"""

from __future__ import annotations

import inspect
import unittest

from falcon.couture.interface import Driver
from falcon.exploration import gestes as G
from falcon.trace import lire
from falcon.trace.brouillon import SANS_ACTION, SUBSTITUTIONS, brouillon_de
from falcon.trace.modele import CONFORT, VERBES

from tests.test_trace import MEGATRACE, geste, vbs

ARBRE = ("expandNode", "selectedNode", "doubleClickNode", "topNode")

GRILLE = ("selectedRows", "currentCellRow", "doubleClickCurrentCell")

ALV = "wnd[1]/usr/cntlALV_CONTAINER_1/shellcont/shell"


def _un(ligne: str) -> G.Traduction:
    """La traduction d'une ligne de trace, LUE par le vrai parseur.

    Les gestes ne sont jamais batis a la main : un `Geste` fabrique
    directement pourrait porter une combinaison verbe/forme/type que le
    recorder n'ecrit pas, et le test prouverait alors quelque chose sur une
    trace qui n'existe pas.
    """
    return G.traduire(geste(vbs(ligne)))


def _methodes_de_driver() -> frozenset[str]:
    return frozenset(nom for nom, membre in vars(Driver).items()
                     if getattr(membre, "__isabstractmethod__", False))


class TestFermeture(unittest.TestCase):
    """Le coeur du lot : rien ne peut disparaitre en silence."""

    def test_la_table_recouvre_exactement_les_verbes_de_trace(self):
        self.assertEqual(set(G.TABLE), set(VERBES))

    def test_un_verbe_ajoute_a_la_trace_et_oublie_ici_est_refuse(self):
        """La verification a lieu a l'import, pas seulement dans les tests :
        c'est ce qui empeche un rejeu de sauter un geste sans le dire."""
        with self.assertRaises(G.TableIncoherente) as capture:
            sans = dict(G.TABLE)
            sans.pop("press")
            veritable, G.TABLE = G.TABLE, sans
            try:
                G._verifier_fermeture()
            finally:
                G.TABLE = veritable
        self.assertIn("press", str(capture.exception))

    def test_aucune_traduction_muette(self):
        """Appel, ou raison — jamais ni l'un ni l'autre."""
        for traduction in G.traduire_tous(lire(MEGATRACE).gestes):
            with self.subTest(ligne=traduction.geste.ligne):
                self.assertTrue(traduction.appel is not None or traduction.raison)

    def test_rien_n_est_omis_et_l_ordre_est_conserve(self):
        """`currentCellRow` avant `selectedRows` : reordonner ou filtrer ici
        ferait double-cliquer la premiere ligne, sans lever."""
        trace = lire(MEGATRACE)
        traductions = G.traduire_tous(trace.gestes)
        self.assertEqual([t.geste.ligne for t in traductions],
                         [g.ligne for g in trace.gestes])


class TestSansIssueNommement(unittest.TestCase):

    def test_les_quatre_verbes_d_arbre_figurent_avec_leur_raison(self):
        for verbe in ARBRE:
            with self.subTest(verbe=verbe):
                regle = G.TABLE[verbe]
                self.assertEqual(regle.genre, G.SANS_COUTURE)
                self.assertEqual(regle.methode, "")
                self.assertIn("arbre", regle.raison)
                self.assertIn("n°14", regle.raison)

    def test_la_couture_n_a_effectivement_aucune_methode_d_arbre(self):
        """La raison invoquee est verifiee, pas recopiee."""
        methodes = _methodes_de_driver()
        self.assertFalse([m for m in methodes if "node" in m.lower()
                          or "tree" in m.lower() or "arbre" in m.lower()])

    def test_les_verbes_de_confort_sont_ceux_du_lecteur_de_traces(self):
        ecartes = {v for v, r in G.TABLE.items() if r.genre == G.ECARTE_CONFORT}
        self.assertEqual(ecartes, set(CONFORT))

    def test_tout_verbe_sans_issue_porte_une_raison(self):
        for verbe, regle in G.TABLE.items():
            if regle.genre != G.TRADUIT:
                with self.subTest(verbe=verbe):
                    self.assertTrue(regle.raison)


class TestLesMethodesNommeesExistent(unittest.TestCase):
    """La table nomme des methodes ; ce test les confronte a la couture.

    C'est le seul endroit du lot ou `falcon.couture` est importe — le paquet
    `exploration` ne le fait pas, et `tests/test_frontieres.py` le verifie.
    """

    def test_chaque_methode_de_la_table_est_une_methode_de_driver(self):
        methodes = _methodes_de_driver()
        for verbe, regle in G.TABLE.items():
            if regle.methode:
                with self.subTest(verbe=verbe):
                    self.assertIn(regle.methode, methodes)

    def test_chaque_appel_de_la_megatrace_se_lie_a_sa_signature(self):
        """Les arguments sont positionnels : une arite fausse doit tomber ici,
        pas devant un SAP de production."""
        for traduction in G.traduire_tous(lire(MEGATRACE).gestes):
            if traduction.appel is None:
                continue
            with self.subTest(ligne=traduction.geste.ligne):
                signature = inspect.signature(
                    getattr(Driver, traduction.appel.methode))
                signature.bind(object(), *traduction.appel.arguments)


class TestCeQueLaMegatraceDonne(unittest.TestCase):
    """Chiffres mesures sur la trace de reference."""

    def setUp(self):
        self.trace = lire(MEGATRACE)
        self.traductions = G.traduire_tous(self.trace.gestes)

    def _genres(self) -> dict[str, int]:
        comptes: dict[str, int] = {}
        for traduction in self.traductions:
            comptes[traduction.genre] = comptes.get(traduction.genre, 0) + 1
        return comptes

    def test_les_comptes(self):
        self.assertEqual(len(self.traductions), 90)
        self.assertEqual(self._genres(),
                         {G.TRADUIT: 65, G.ECARTE_CONFORT: 15,
                          G.SANS_COUTURE: 10})

    def test_douze_des_vingt_deux_non_rejouables_du_brouillon_le_redeviennent(self):
        """La difference est de PIPELINE, pas de couture : `ACTIONS` n'a
        aucune action de grille, la couture a les trois methodes."""
        refuses = brouillon_de(self.trace).non_rejouables
        self.assertEqual(len(refuses), 22)
        rejoues = [g for g in refuses if G.traduire(g).rejouable]
        self.assertEqual(len(rejoues), 12)
        self.assertEqual({g.verbe for g in rejoues}, set(GRILLE))

    def test_les_dix_autres_sont_les_gestes_d_arbre(self):
        refuses = brouillon_de(self.trace).non_rejouables
        restants = [g for g in refuses if not G.traduire(g).rejouable]
        self.assertEqual(len(restants), 10)
        self.assertEqual({g.verbe for g in restants}, set(ARBRE))

    def test_les_deux_tables_partagent_le_meme_perimetre(self):
        """`SANS_ACTION` du brouillon = grille + arbre. La table les separe."""
        self.assertEqual(set(GRILLE) | set(ARBRE), set(SANS_ACTION))


class TestTypesDArguments(unittest.TestCase):
    """Le piege : les arguments de trace ne sont pas tous du texte."""

    def test_selectedRows_est_une_chaine_et_devient_des_entiers(self):
        traduction = _un(f'session.findById("{ALV}").selectedRows = "0"')
        self.assertEqual(traduction.appel.methode, "grid_select_rows")
        self.assertEqual(traduction.appel.arguments, (ALV, (0,)))

    def test_currentCellRow_est_un_entier_et_le_reste(self):
        traduction = _un(f'session.findById("{ALV}").currentCellRow = 4')
        self.assertEqual(traduction.appel.methode, "grid_set_current_row")
        self.assertEqual(traduction.appel.arguments, (ALV, 4))

    def test_un_selectedRows_entier_est_refuse_et_non_converti(self):
        traduction = _un(f'session.findById("{ALV}").selectedRows = 0')
        self.assertEqual(traduction.genre, G.ARGUMENT_REFUSE)
        self.assertIsNone(traduction.appel)
        self.assertIn("CHAINE", traduction.raison)

    def test_un_currentCellRow_texte_est_refuse_et_non_converti(self):
        traduction = _un(f'session.findById("{ALV}").currentCellRow = "4"')
        self.assertEqual(traduction.genre, G.ARGUMENT_REFUSE)
        self.assertIn("ENTIER", traduction.raison)

    def test_un_text_entier_est_refuse(self):
        traduction = _un('session.findById("wnd[0]/usr/txtV-LOW").text = 4')
        self.assertEqual(traduction.genre, G.ARGUMENT_REFUSE)

    def test_un_selected_non_booleen_est_refuse(self):
        traduction = _un('session.findById("wnd[0]/usr/chkDY_MAB").selected = 1')
        self.assertEqual(traduction.genre, G.ARGUMENT_REFUSE)

    def test_un_index_negatif_est_refuse(self):
        """En Python, -1 designe la derniere ligne : il agirait ailleurs."""
        traduction = _un(f'session.findById("{ALV}").currentCellRow = -1')
        self.assertEqual(traduction.genre, G.ARGUMENT_REFUSE)
        self.assertIn("negatif", traduction.raison)


class TestRangsDAlv(unittest.TestCase):

    def _rangs(self, litteral: str):
        return _un(f'session.findById("{ALV}").selectedRows = {litteral}')

    def test_plusieurs_index(self):
        self.assertEqual(self._rangs('"0,2,5"').appel.arguments,
                         (ALV, (0, 2, 5)))

    def test_l_ordre_et_les_repetitions_sont_conserves(self):
        """Trier ou dedoublonner rendrait autre chose que l'enregistrement."""
        self.assertEqual(self._rangs('"5,2,2"').appel.arguments,
                         (ALV, (5, 2, 2)))

    def test_un_intervalle_est_refuse(self):
        traduction = self._rangs('"0-4"')
        self.assertEqual(traduction.genre, G.ARGUMENT_REFUSE)
        self.assertIn("intervalle", traduction.raison)

    def test_une_chaine_vide_est_refusee(self):
        self.assertEqual(self._rangs('""').genre, G.ARGUMENT_REFUSE)

    def test_les_espaces_ne_sont_pas_rognes(self):
        self.assertEqual(self._rangs('"0, 2"').genre, G.ARGUMENT_REFUSE)

    def test_un_chiffre_unicode_n_est_pas_un_index(self):
        """`\\d` couvre tous les chiffres Unicode, et `int()` les convertit.

        Mesure avant correction : `selectedRows = "٠"` — zero arabo-indien —
        etait accepte et rendait l'index 0. Le recorder SAP n'ecrit pas cela ;
        un caractere qui RESSEMBLE a un chiffre devenait donc une ligne de
        grille en silence. C'est le controle negatif de `[0-9]` : remettre
        `\\d` dans `_RANGS` fait tomber ce test.
        """
        for exotique in ("٠", "٠,٣", "𝟛"):
            with self.subTest(exotique):
                traduction = self._rangs(f'"{exotique}"')
                self.assertEqual(traduction.genre, G.ARGUMENT_REFUSE)
                self.assertIsNone(traduction.appel)


class TestFenetreEtSubstitution(unittest.TestCase):

    def test_sendVKey_garde_sa_fenetre(self):
        """Le defaut connu du brouillon : quatre touches destinees a `wnd[1]`
        partaient dans `wnd[0]`, sans exception."""
        traduction = _un('session.findById("wnd[1]").sendVKey 0')
        self.assertEqual(traduction.appel.arguments, (0, "wnd[1]"))

    def test_sendVKey_sur_autre_chose_qu_une_fenetre_est_refuse(self):
        traduction = _un('session.findById("wnd[0]/usr/txtV-LOW").sendVKey 0')
        self.assertEqual(traduction.genre, G.ARGUMENT_REFUSE)

    def test_close_devient_vkey_12_et_le_dit(self):
        traduction = _un('session.findById("wnd[1]").close')
        self.assertEqual(traduction.appel.methode, "vkey")
        self.assertEqual(traduction.appel.arguments, (12, "wnd[1]"))
        self.assertTrue(traduction.appel.substitue)
        self.assertIn("n°14", traduction.raison)

    def test_la_touche_d_annulation_est_la_meme_que_dans_le_brouillon(self):
        """Deux traductions independantes, une seule decision. Ce test est ce
        qui les empeche de diverger en silence."""
        verbe, valeur = SUBSTITUTIONS["close"]
        self.assertEqual(verbe, "vkey")
        self.assertEqual(int(valeur), G.VKEY_ANNULER)


class TestCeQueLaTableNeFaitPas(unittest.TestCase):

    def test_elle_ne_repare_pas_la_faute_de_frappe_de_l_operateur(self):
        """`/nIW2ç` est ecrit tel quel ; c'est SAP qui le refusera."""
        traduction = _un('session.findById("wnd[0]/tbar[0]/okcd").text = "/nIW2ç"')
        self.assertEqual(traduction.appel.arguments[1], "/nIW2ç")

    def test_elle_ne_fait_pas_la_police_de_la_sauvegarde(self):
        """Refuser ici le bouton Sauvegarder donnerait une exploration qui a
        l'air d'avoir tout rejoue. C'est `DriverGarde` qui doit refuser."""
        traduction = _un('session.findById("wnd[0]/tbar[0]/btn[11]").press')
        self.assertTrue(traduction.rejouable)

    def test_un_verbe_inconnu_n_est_pas_devine(self):
        traduction = _un('session.findById("wnd[0]/usr/txtX").wiggle')
        self.assertEqual(traduction.genre, G.VERBE_INCONNU)
        self.assertIsNone(traduction.appel)
        self.assertIn("wiggle", traduction.raison)

    def test_elle_n_appelle_aucun_driver(self):
        """Elle DECRIT l'appel. Le module ne connait aucun driver, et c'est ce
        qui lui permet de ne jamais importer la couture."""
        traduction = _un('session.findById("wnd[0]/tbar[1]/btn[17]").press')
        self.assertEqual(traduction.appel.rendu(),
                         "press('wnd[0]/tbar[1]/btn[17]')")


class TestInvariantsDesTypes(unittest.TestCase):

    def test_une_traduction_sans_appel_ni_raison_est_impossible(self):
        with self.assertRaises(G.TableIncoherente):
            G.Traduction(geste(vbs('session.findById("wnd[0]").maximize')),
                         G.ECARTE_CONFORT)

    def test_une_regle_sans_issue_et_sans_raison_est_impossible(self):
        with self.assertRaises(G.TableIncoherente):
            G.Regle("essai", G.SANS_COUTURE)

    def test_une_substitution_muette_est_impossible(self):
        with self.assertRaises(G.TableIncoherente):
            G.Regle("essai", G.TRADUIT, "vkey", G.TOUCHE_FIXE, constante=12,
                    substitue=True)


if __name__ == "__main__":
    unittest.main()
