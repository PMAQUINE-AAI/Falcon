"""Pipeline : modele, chargement strict, echappatoire, frontiere.

Le critere de ce lot tient en une phrase — un YAML invalide echoue avec un
message situe, jamais en silence. La plupart de ces tests verifient donc des
REFUS, et verifient aussi que le message dit ou chercher : une erreur qu'il
faut aller trouver dans un fichier de trois cents lignes coute autant qu'une
absence d'erreur.
"""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from falcon.controleur import Contrat, contrat_pour
from falcon.noyau import DEROGEABLES
from falcon.pipeline import (
    ACTIONS, ExtensionInconnue, Pipeline, PipelineInvalide, charger, connues,
    etape_python, oublier_tout, resoudre,
)

MOTIF = "l'editeur SAPscript n'est pas adressable, verifie par retelechargement"

VALIDE = """
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
      - nom: executer
        action: press
        cible: "wnd[0]/tbar[1]/btn[8]"
        ecran: {transaction: IA08, programme: RIPLKO10, dynpro: "1000"}
        statut_attendu: "S"
    """


class Base(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.racine = Path(self.dossier.name)
        self.addCleanup(self.dossier.cleanup)

    def _charger(self, texte: str, **options) -> Pipeline:
        chemin = self.racine / "p.yaml"
        chemin.write_text(textwrap.dedent(texte), encoding="utf-8")
        return charger(chemin, **options)

    def _refus(self, texte: str, **options) -> str:
        with self.assertRaises(PipelineInvalide) as capture:
            self._charger(texte, **options)
        return str(capture.exception)


class TestChargementValide(Base):

    def test_une_pipeline_valide_se_charge(self):
        pipeline = self._charger(VALIDE)
        self.assertEqual(pipeline.nom, "bcp_ia08_variantes")
        self.assertTrue(pipeline.iterative)
        self.assertEqual(pipeline.cles, ("site",))
        self.assertEqual(len(pipeline.etapes), 2)

    def test_l_empreinte_change_avec_le_contenu(self):
        """Base de la garde de reprise : reprendre sur une pipeline modifiee,
        c'est avoir un modele du monde faux."""
        avant = self._charger(VALIDE).empreinte
        apres = self._charger(VALIDE.replace("plafond_items: 50",
                                             "plafond_items: 10")).empreinte
        self.assertNotEqual(avant, apres)

    def test_le_dynpro_reste_une_chaine(self):
        """« 0100 » n'est pas « 100 »."""
        pipeline = self._charger(VALIDE)
        self.assertEqual(pipeline.etapes[0].ecran, ("IA08", "RIPLKO10", "1000"))

    def test_la_source_est_typee(self):
        source = self._charger(VALIDE).etapes[0].source
        self.assertEqual((source.genre, source.valeur), ("colonne", "site"))


class TestRefusSitues(Base):
    """Chaque refus doit dire ou chercher."""

    def test_le_message_situe_l_etape(self):
        message = self._refus(VALIDE.replace("action: press", "action: presser"))
        self.assertIn("etape 2", message)
        self.assertIn("executer", message)
        self.assertIn("p.yaml", message)

    def test_cle_inconnue_de_pipeline(self):
        """Une cle inconnue est le plus souvent une faute de frappe sur une
        cle connue, et l'ignorer change le comportement sans un mot."""
        self.assertIn("inconnue", self._refus(VALIDE + "\n    surprise: 1\n"))

    def test_cle_inconnue_d_etape(self):
        message = self._refus(VALIDE.replace(
            "        action: set\n", "        action: set\n        sauvegader: true\n"))
        self.assertIn("sauvegader", message)

    def test_version_inattendue(self):
        self.assertIn("version", self._refus(VALIDE.replace("version: 1",
                                                            "version: 9")))

    def test_classe_inconnue(self):
        self.assertIn("classe", self._refus(VALIDE.replace("classe: iterative",
                                                           "classe: bizarre")))

    def test_une_iterative_sans_cles_est_refusee(self):
        """Sans colonnes de clef, l'identifiant d'item retomberait sur le rang
        de la ligne — et un fichier de KO reinjecte n'a plus les memes rangs."""
        self.assertIn("cles", self._refus(VALIDE.replace("    cles: [site]\n", "")))

    def test_une_volumique_sans_cles_est_acceptee(self):
        pipeline = self._charger(VALIDE.replace("classe: iterative",
                                                "classe: volumique")
                                       .replace("    cles: [site]\n", ""))
        self.assertFalse(pipeline.iterative)

    def test_les_plafonds_sont_obligatoires(self):
        for cle in ("plafond_items", "plafond_sauvegardes"):
            with self.subTest(cle=cle):
                message = self._refus(VALIDE.replace(f"    {cle}: 50\n", ""))
                self.assertIn(cle, message)

    def test_un_plafond_nul_est_refuse(self):
        self.assertIn("positif", self._refus(VALIDE.replace("plafond_items: 50",
                                                            "plafond_items: 0")))

    def test_etapes_vides(self):
        self.assertIn("etapes", self._refus(
            VALIDE.split("    etapes:")[0] + "    etapes: []\n"))

    def test_nom_d_etape_en_double(self):
        """Les derogations se designent par ce nom."""
        self.assertIn("double", self._refus(
            VALIDE.replace("nom: executer", "nom: saisir_division")))

    def test_action_sans_cible(self):
        self.assertIn("cible", self._refus(
            VALIDE.replace('        cible: "wnd[0]/tbar[1]/btn[8]"\n', "")))

    def test_action_set_sans_source(self):
        self.assertIn("source", self._refus(
            VALIDE.replace("        source: {colonne: site}\n", "")))

    def test_genre_de_source_inconnu(self):
        self.assertIn("genre", self._refus(
            VALIDE.replace("{colonne: site}", "{devine: site}")))

    def test_comparaison_inconnue(self):
        self.assertIn("comparaison", self._refus(
            VALIDE.replace("        action: press",
                           "        comparaison: approximative\n        action: press")))


class TestEtapeMuette(Base):
    """Le meme principe que pour `Contrat` : declarer ou deroger, jamais
    obtenir un relachement par omission."""

    def test_une_etape_sans_ecran_est_refusee(self):
        message = self._refus(VALIDE.replace(
            '        ecran: {transaction: IA08, programme: RIPLKO10, dynpro: "1000"}\n'
            '        statut_attendu: "S"\n', '        statut_attendu: "S"\n'))
        self.assertIn("navigation_libre", message)

    def test_la_navigation_libre_se_declare(self):
        pipeline = self._charger(VALIDE.replace(
            '        ecran: {transaction: IA08, programme: RIPLKO10, dynpro: "1000"}\n'
            '        statut_attendu: "S"\n',
            '        navigation_libre: true\n'))
        self.assertTrue(pipeline.etapes[1].navigation_libre)

    def test_declarer_les_deux_est_refuse(self):
        self.assertIn("ensemble", self._refus(VALIDE.replace(
            '        statut_attendu: "S"', "        navigation_libre: true")))

    def test_ecran_incomplet(self):
        self.assertIn("incomplet", self._refus(
            VALIDE.replace('{transaction: IA08, programme: RIPLKO10, dynpro: "1000"}',
                           "{transaction: IA08}", 1)))


class TestDerogations(Base):

    def _avec(self, garde: str, motif: str = MOTIF, portee: str = "") -> str:
        bloc = (f'        derogations:\n'
                f'          - garde: {garde}\n'
                f'            motif: "{motif}"\n')
        if portee:
            bloc += f'            portee: "{portee}"\n'
        return VALIDE.replace("        action: press\n",
                              "        action: press\n" + bloc)

    def test_une_derogation_valide_est_retenue(self):
        pipeline = self._charger(self._avec("relecture"))
        derogation = pipeline.etapes[1].derogations[0]
        self.assertEqual(derogation.garde, "relecture")
        self.assertEqual(derogation.portee, "etape:executer")

    def test_une_garde_non_derogeable_est_refusee_au_chargement(self):
        """C'est tout l'objet du vocabulaire partage : ce refus doit tomber
        au chargement, pas au bout de deux heures de lot."""
        for garde in ("identite", "rayon"):
            with self.subTest(garde=garde):
                message = self._refus(self._avec(garde))
                self.assertIn("aucune derogation possible", message)
                self.assertIn("etape 2", message)

    def test_un_motif_trop_court_est_refuse(self):
        self.assertIn("minimum", self._refus(self._avec("relecture", "ok")))

    def test_une_portee_mal_formee_est_refusee(self):
        self.assertIn("portee", self._refus(
            self._avec("relecture", MOTIF, "partout")))

    def test_les_derogeables_sont_celles_du_vocabulaire_partage(self):
        self.assertEqual(DEROGEABLES, {"statut", "fenetre", "relecture"})


class TestBrouillon(Base):

    def test_un_brouillon_est_refuse_par_defaut(self):
        """Le brouillon est une aide a la redaction, pas un livrable : il ne
        doit pas atteindre une session SAP par inadvertance."""
        message = self._refus(VALIDE.replace('cible: "wnd[0]/tbar[1]/btn[8]"',
                                             'cible: "TODO"'))
        self.assertIn("brouillon", message)

    def test_un_brouillon_se_charge_explicitement(self):
        pipeline = self._charger(
            VALIDE.replace('cible: "wnd[0]/tbar[1]/btn[8]"', 'cible: "TODO"'),
            brouillon=True)
        self.assertEqual(pipeline.etapes[1].cible, "TODO")


class TestEchappatoire(Base):

    def setUp(self):
        super().setUp()
        self.addCleanup(oublier_tout)

    def _avec_python(self, fonction: str) -> str:
        # Meme indentation de base que VALIDE : le dedent a lieu une seule
        # fois, au chargement.
        # VALIDE se termine par une ligne d'espaces : la retirer avant de
        # coller, sinon le bloc ajoute se retrouve decale.
        return VALIDE.rstrip(" \n") + "\n" + (
            f"      - nom: basculer_langue\n"
            f"        action: python\n"
            f"        fonction: {fonction}\n"
            f"        navigation_libre: true\n")

    def test_une_fonction_enregistree_est_acceptee(self):
        @etape_python("basculer_langue_texte_long")
        def basculer(poste, item, contexte):
            return None

        pipeline = self._charger(self._avec_python("basculer_langue_texte_long"))
        self.assertEqual(pipeline.etapes[2].fonction,
                         "basculer_langue_texte_long")
        self.assertIs(resoudre("basculer_langue_texte_long"), basculer)

    def test_une_fonction_inconnue_est_refusee_au_chargement(self):
        """Une pipeline ne peut pas designer du code arbitraire par son
        chemin : elle ne peut nommer que ce qui a ete enregistre."""
        message = self._refus(self._avec_python("inexistante"))
        self.assertIn("non enregistree", message)

    def test_l_action_python_exige_une_fonction(self):
        self.assertIn("fonction", self._refus(
            self._avec_python("x").replace("        fonction: x\n", "")))

    def test_deux_fonctions_sous_le_meme_nom_sont_refusees(self):
        @etape_python("doublon")
        def premiere(poste, item, contexte):
            return None

        with self.assertRaises(ValueError):
            @etape_python("doublon")
            def seconde(poste, item, contexte):
                return None

    def test_resoudre_un_nom_inconnu_leve(self):
        with self.assertRaises(ExtensionInconnue):
            resoudre("jamais_enregistree")
        self.assertEqual(connues(), frozenset())


class TestConversionEnContrat(Base):
    """La pipeline declare, le controleur dispose."""

    def test_une_etape_devient_un_contrat(self):
        etape = self._charger(VALIDE).etapes[1]
        contrat = contrat_pour(etape)
        self.assertIsInstance(contrat, Contrat)
        self.assertEqual(contrat.nom, "executer")
        self.assertEqual(contrat.ecran_attendu, ("IA08", "RIPLKO10", "1000"))
        self.assertEqual(contrat.statut_attendu, "S")

    def test_la_derogation_demandee_est_revalidee_a_la_conversion(self):
        """Une derogation DEMANDEE dans le YAML ne devient ACCORDEE qu'en
        passant par le controleur."""
        pipeline = self._charger(VALIDE.replace(
            "        action: press\n",
            f'        action: press\n'
            f'        derogations:\n'
            f'          - garde: relecture\n'
            f'            motif: "{MOTIF}"\n'))
        contrat = contrat_pour(pipeline.etapes[1])
        self.assertIsNotNone(contrat.derogation_pour("relecture"))

    def test_la_navigation_libre_se_transmet(self):
        pipeline = self._charger(VALIDE.replace(
            '        ecran: {transaction: IA08, programme: RIPLKO10, dynpro: "1000"}\n'
            '        statut_attendu: "S"\n',
            '        navigation_libre: true\n'))
        contrat = contrat_pour(pipeline.etapes[1])
        self.assertTrue(contrat.navigation_libre)
        self.assertEqual([g for g, _, _ in contrat.relachements], ["identite"])


class TestModele(unittest.TestCase):

    def test_les_actions_couvrent_la_specification(self):
        """Les quatre de la specification, plus celles que le terrain impose."""
        for action in ("set", "press", "select", "lire"):
            self.assertIn(action, ACTIONS)
        for action in ("cocher", "vkey", "python"):
            self.assertIn(action, ACTIONS)


if __name__ == "__main__":
    unittest.main()
