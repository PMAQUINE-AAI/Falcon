"""Brouillon de pipeline depuis une trace — inacheve par construction.

La propriete qui porte ce lot est **negative** : le generateur n'emet jamais
`navigation_libre: true`. Il aurait ete commode de le faire, puisqu'une trace
ne dit pas l'identite des ecrans et que c'est exactement la declaration qui
dispense d'en donner une. Mais c'est aussi celle qui DESARME la garde
d'identite : un generateur qui la poserait automatiquement la desarmerait sur
toute pipeline nee d'une trace, sans que personne l'ait decide.

Le fichier produit est donc refuse par `charger()` tant qu'un humain n'a pas
rempli les ecrans, et accepte par `charger(brouillon=True)`. C'est le
raccordement des lots 6, 8 et 8b, et il tient par les marqueurs.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from falcon.pipeline import MARQUEUR_BROUILLON, PipelineInvalide, charger
from falcon.trace import lire
from falcon.trace.brouillon import (
    ACTIONS, INDEX_ALV, SANS_ACTION, SUBSTITUTIONS, TODO, BrouillonImpossible,
    apercu, brouillon_de,
)
from falcon.trace.modele import CONFORT, VERBES

from tests.test_trace import MEGATRACE, vbs


def _brouillon(*lignes: str, nom: str = "essai"):
    return brouillon_de(lire(vbs(*lignes)), nom=nom)


def _charge(ebauche, **options):
    """Ecrit le brouillon et le charge. Le parametre ne s'appelle pas
    `brouillon` : `charger` a une option de ce nom, et la collision produisait
    un `TypeError` au lieu du test qu'on voulait ecrire."""
    dossier = tempfile.TemporaryDirectory()
    chemin = Path(dossier.name) / "b.yaml"
    chemin.write_text(ebauche.yaml, encoding="utf-8")
    try:
        return charger(chemin, **options)
    finally:
        dossier.cleanup()


class TestLaGardeNEstJamaisDesarmee(unittest.TestCase):
    """Le coeur du lot."""

    def test_le_generateur_n_emet_jamais_navigation_libre(self):
        """Sur le YAML ANALYSE, pas sur le texte brut : l'en-tete du fichier
        explique justement pourquoi le generateur ne l'emet pas, et une
        recherche de texte attrapait cette explication."""
        contenu = yaml.safe_load(brouillon_de(lire(MEGATRACE)).yaml)
        for etape in contenu["etapes"]:
            with self.subTest(etape=etape["nom"]):
                self.assertNotIn("navigation_libre", etape)

    def test_chaque_etape_declare_un_ecran_a_completer(self):
        pipeline = _charge(brouillon_de(lire(MEGATRACE)), brouillon=True)
        for etape in pipeline.etapes:
            with self.subTest(etape=etape.nom):
                self.assertIsNotNone(etape.ecran)
                self.assertFalse(etape.navigation_libre)
                self.assertIn(TODO, etape.ecran)

    def test_la_transaction_connue_est_reportee(self):
        """Ce que la trace sait, elle le dit ; le reste porte un marqueur."""
        brouillon = brouillon_de(lire(MEGATRACE))
        self.assertIn("transaction: IH06", brouillon.yaml)
        self.assertIn(f"programme: {TODO}", brouillon.yaml)

    def test_le_generateur_ne_pose_aucune_derogation(self):
        """Une derogation exige un motif ecrit par un humain. Un generateur
        qui en poserait produirait des motifs vides de sens."""
        contenu = yaml.safe_load(brouillon_de(lire(MEGATRACE)).yaml)
        for etape in contenu["etapes"]:
            with self.subTest(etape=etape["nom"]):
                self.assertNotIn("derogations", etape)


class TestRaccordementAuChargeur(unittest.TestCase):

    def setUp(self):
        self.brouillon = brouillon_de(lire(MEGATRACE), nom="bcp_variantes")

    def test_charger_refuse_le_brouillon(self):
        with self.assertRaises(PipelineInvalide) as capture:
            _charge(self.brouillon)
        self.assertIn(MARQUEUR_BROUILLON, str(capture.exception))

    def test_charger_en_brouillon_l_accepte(self):
        pipeline = _charge(self.brouillon, brouillon=True)
        self.assertEqual(pipeline.nom, "bcp_variantes")
        self.assertEqual(len(pipeline.etapes), self.brouillon.etapes)

    def test_les_noms_d_etape_sont_uniques(self):
        """Le chargeur refuse les doublons, et les derogations se designent
        par ce nom."""
        pipeline = _charge(self.brouillon, brouillon=True)
        noms = [e.nom for e in pipeline.etapes]
        self.assertEqual(len(noms), len(set(noms)))

    def test_le_yaml_produit_est_relisible(self):
        contenu = yaml.safe_load(self.brouillon.yaml)
        self.assertEqual(contenu["version"], 1)
        self.assertTrue(contenu["etapes"])


class TestTraduction(unittest.TestCase):

    def test_une_saisie_devient_un_set_a_valeur_constante(self):
        brouillon = _brouillon(
            'session.findById("wnd[1]/usr/txtV-LOW").text = "*BCP*"')
        etape = _charge(brouillon, brouillon=True).etapes[0]
        self.assertEqual(etape.action, "set")
        self.assertEqual(etape.cible, "wnd[1]/usr/txtV-LOW")
        self.assertEqual((etape.source.genre, etape.source.valeur),
                         ("constante", "*BCP*"))

    def test_une_case_devient_un_cocher(self):
        brouillon = _brouillon(
            'session.findById("wnd[0]/usr/chkDY_MAB").selected = true')
        self.assertEqual(_charge(brouillon, brouillon=True).etapes[0].action,
                         "cocher")

    def test_un_bouton_devient_un_press(self):
        brouillon = _brouillon(
            'session.findById("wnd[0]/tbar[0]/btn[11]").press')
        self.assertEqual(_charge(brouillon, brouillon=True).etapes[0].action,
                         "press")

    def test_une_touche_devient_un_vkey_portant_son_numero(self):
        """C'est ce que le lot 8b a rendu exprimable."""
        brouillon = _brouillon('session.findById("wnd[0]").sendVKey 11')
        etape = _charge(brouillon, brouillon=True).etapes[0]
        self.assertEqual(etape.action, "vkey")
        self.assertEqual(etape.source.valeur, "11")

    def test_les_gestes_de_confort_sont_ecartes(self):
        """Ils sont conserves dans la TRACE pour qu'elle reste rejouable a
        l'identique. Une pipeline n'est pas un rejeu."""
        brouillon = _brouillon(
            'session.findById("wnd[0]/usr/txtA").text = "x"',
            'session.findById("wnd[0]/usr/txtA").setFocus',
            'session.findById("wnd[0]/usr/txtA").caretPosition = 3')
        self.assertEqual(brouillon.etapes, 1)
        self.assertEqual(brouillon.ecarte_confort, 2)

    def test_une_trace_sans_geste_est_refusee(self):
        with self.assertRaises(BrouillonImpossible):
            brouillon_de(lire(vbs("If Not IsObject(application) Then",
                                  "End If")))


class TestCeQuiNEstPasRejouable(unittest.TestCase):

    def test_un_geste_sans_action_devient_une_etape_a_completer(self):
        brouillon = _brouillon(
            'session.findById("wnd[1]/usr/cntlALV/shellcont/shell")'
            '.doubleClickCurrentCell')
        etape = _charge(brouillon, brouillon=True).etapes[0]
        self.assertEqual(etape.action, "python")
        self.assertEqual(etape.fonction, TODO)
        self.assertEqual(len(brouillon.non_rejouables), 1)

    def test_la_ligne_de_trace_figure_verbatim_en_commentaire(self):
        ligne = ('session.findById("wnd[1]/usr/cntlALV/shellcont/shell")'
                 '.doubleClickCurrentCell')
        self.assertIn(ligne, _brouillon(ligne).yaml)

    def test_la_selection_par_index_est_signalee_nommement(self):
        """Le defaut ne leve pas : l'index depend du contenu de la base au
        moment de l'enregistrement. Rejoue tel quel, il traite la mauvaise
        ligne — et la pipeline continue comme si de rien n'etait.
        """
        brouillon = _brouillon(
            'session.findById("wnd[1]/usr/cntlALV/shellcont/shell")'
            '.selectedRows = "4"')
        self.assertEqual(len(brouillon.selections_par_index), 1)
        self.assertIn("INDEX", brouillon.yaml)
        self.assertIn("mauvaise ligne", brouillon.yaml)

    def test_la_trace_observee_signale_ses_sept_selections_par_index(self):
        brouillon = brouillon_de(lire(MEGATRACE))
        self.assertEqual(len(brouillon.selections_par_index), 7)
        self.assertFalse(brouillon.complet)

    def test_une_substitution_est_appliquee_et_tracee(self):
        """`close` n'a pas de methode de couture — decision n°14 : c'est
        `vkey(12)`. La substitution est faite, et dite."""
        brouillon = _brouillon('session.findById("wnd[1]").close')
        etape = _charge(brouillon, brouillon=True).etapes[0]
        self.assertEqual((etape.action, etape.source.valeur), ("vkey", "12"))
        self.assertEqual(len(brouillon.substitutions), 1)
        self.assertIn("substitution", brouillon.yaml)

    def test_tout_verbe_releve_est_classe(self):
        """Detecteur de derive : un verbe ajoute a `VERBES` sans decider de
        son sort ici produirait une etape `python`/TODO muette sur la raison.
        """
        classes = set(ACTIONS) | SANS_ACTION | set(SUBSTITUTIONS) | CONFORT
        self.assertEqual(set(VERBES) - classes, set(),
                         "verbe releve mais non classe par le generateur")

    def test_les_index_alv_sont_bien_des_verbes_connus(self):
        self.assertLessEqual(INDEX_ALV, SANS_ACTION)


class TestApercu(unittest.TestCase):

    def test_l_apercu_compte_ce_qui_manque(self):
        texte = apercu(brouillon_de(lire(MEGATRACE)))
        self.assertIn("non rejouables", texte)
        self.assertIn("INDEX", texte)

    def test_l_apercu_dit_comment_charger_le_fichier(self):
        texte = apercu(brouillon_de(lire(MEGATRACE)))
        self.assertIn("brouillon=True", texte)


class TestMarqueurPartage(unittest.TestCase):

    def test_le_marqueur_est_le_meme_des_deux_cotes(self):
        """Le lecteur de traces ne peut pas importer la pipeline — ce serait
        une dependance a l'envers. Le marqueur est donc redefini, et ce test
        est ce qui empeche les deux definitions de diverger.
        """
        self.assertEqual(TODO, MARQUEUR_BROUILLON)


if __name__ == "__main__":
    unittest.main()
