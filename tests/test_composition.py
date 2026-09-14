"""Composer une valeur sans ecrire de Python.

**Le probleme, dans les mots de l'utilisateur :** « Il faut que le programme
puisse etre multi usage, pas specifique au point ou je dois revoir avec toi le
code des que j'ai besoin de faire une nouvelle automatisation. »

Une pipeline ne savait tirer une valeur que d'une colonne, d'une constante ou
d'une etape `lire`. Elle ne savait pas les COMBINER — et le cas le plus banal
d'une correction de masse SAP en a besoin : un nom de variante porte le site
dedans, un numero d'equipement se saisit cadre a douze positions.

Le seul chemin restant etait `action: python` : ecrire une fonction, la faire
entrer dans le depot, la faire relire. Pour concatener deux colonnes.

Deux proprietes portent cette suite. **Les besoins courants s'expriment en
YAML** — c'est la moitie utile. **Et rien de plus ne s'y exprime** : pas de
condition, pas de calcul, pas d'expression evaluee. Un registre ferme, sinon
c'est une echappatoire qui contourne les gardes.
"""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from falcon.couture.double import DriverScripte
from falcon.moteur import PreparationImpossible, executer

#: Ces tests portent sur la COMPOSITION des valeurs, pas sur la garde de
#: repetition a blanc (§5.5) que `run` exige desormais. Le forcage est
#: explicite et motive, comme il l'est pour un utilisateur.
SANS_REPETITION = {
    "forcer_sans_repetition": True,
    "motif_forcage": "Test cible sur la composition des valeurs.",
}
from falcon.noyau import Identite
from falcon.pipeline import PipelineInvalide, charger
from falcon.pipeline.composition import (
    CompositionInvalide, Transformation, appliquer, appliquer_gabarit, jetons,
    lire_transformation, verifier_gabarit,
)

IA08 = Identite(transaction="IA08", programme="R", dynpro="1000")

SOCLE = """
    version: 1
    nom: p
    classe: iterative
    cles: [site]
    plafond_items: 50
    plafond_sauvegardes: 50
    etapes:
      - nom: taper
        action: set
        cible: "wnd[0]/usr/ctxtX"
%s
        ecran: {transaction: IA08, programme: R, dynpro: "1000"}
"""


class Base(unittest.TestCase):

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name)
        self.jeu = self.racine / "jeu.csv"
        self.jeu.write_text(
            "site,prefixe,equipement,libelle\n"
            "k75, zv ,300,Pompe centrifuge\n", encoding="utf-8")

    def _charger(self, bloc: str):
        chemin = self.racine / "p.yaml"
        chemin.write_text(textwrap.dedent(SOCLE % bloc), encoding="utf-8")
        return charger(chemin)

    def _refus(self, bloc: str) -> str:
        with self.assertRaises(PipelineInvalide) as capture:
            self._charger(bloc)
        return str(capture.exception)

    def _tape(self, bloc: str) -> str:
        """Ce qui finit reellement dans le champ SAP, via le moteur."""
        brut = DriverScripte(identite=IA08, valeurs={"wnd[0]/usr/ctxtX": ""})

        def relire(pilote, geste, cible):
            if geste == "write":
                pilote.valeurs[cible] = pilote.valeurs.get(cible, "")
        brut.apres_action = relire

        executer(self._charger(bloc), self.jeu, brut,
                 journal=self.racine / "j.jsonl", **SANS_REPETITION)
        ecrits = [valeur for geste, _, valeur in brut.gestes if geste == "write"]
        return ecrits[0]


class TestLesBesoinsQuiEtaientHorsDePortee(Base):
    """Les six cas mesures avant d'ecrire ce module. Tous impossibles."""

    def test_un_nom_de_variante_porte_le_site(self):
        """Le cas exact de l'utilisateur, et celui qui a motive tout ceci."""
        self.assertEqual(
            self._tape('        source: {gabarit: "/BCP01_{site}"}'),
            "/BCP01_k75")

    def test_deux_colonnes_se_concatenent(self):
        self.assertEqual(
            self._tape('        source: {gabarit: "{prefixe}-{site}"}'),
            " zv -k75")

    def test_une_valeur_se_met_en_capitales(self):
        self.assertEqual(
            self._tape('        source: {colonne: site}\n'
                       '        format: [majuscules]'),
            "K75")

    def test_un_numero_sap_se_cadre_a_douze_zeros(self):
        """La convention SAP pour un MATNR. La largeur est DECLAREE : la
        deviner serait inventer du comportement SAP."""
        self.assertEqual(
            self._tape('        source: {colonne: equipement}\n'
                       '        format: [{zeros: 12}]'),
            "000000000300")

    def test_une_valeur_se_tronque_a_la_longueur_du_champ(self):
        self.assertEqual(
            self._tape('        source: {colonne: libelle}\n'
                       '        format: [{tronque: 4}]'),
            "Pomp")

    def test_un_defaut_remplace_une_colonne_vide(self):
        self.jeu.write_text("site,libelle\nk75,\n", encoding="utf-8")
        self.assertEqual(
            self._tape('        source: {colonne: libelle}\n'
                       '        defaut: "SANS OBJET"'),
            "SANS OBJET")

    def test_un_defaut_ne_remplace_PAS_une_valeur_presente(self):
        self.assertEqual(
            self._tape('        source: {colonne: libelle}\n'
                       '        defaut: "SANS OBJET"'),
            "Pompe centrifuge")

    def test_les_transformations_s_enchainent_dans_l_ORDRE_DECLARE(self):
        """L'ordre n'est pas normalise : reordonner pour l'utilisateur serait
        decider a sa place."""
        self.assertEqual(
            self._tape('        source: {gabarit: "{prefixe}{site}"}\n'
                       '        format: [sans_espaces_autour, majuscules,'
                       ' {zeros: 12}]'),
            "000000ZV K75")

    def test_l_ordre_inverse_donne_autre_chose(self):
        self.assertEqual(
            appliquer("7", (Transformation("zeros", 4),
                            Transformation("tronque", 2))),
            "00")
        self.assertEqual(
            appliquer("7", (Transformation("tronque", 2),
                            Transformation("zeros", 4))),
            "0007")


class TestCeQuiEstRefuse(Base):
    """L'autre moitie : ce module ne doit pas devenir un langage."""

    def test_une_accolade_non_appariee_est_refusee(self):
        """Elle serait recopiee telle quelle dans le champ SAP : « {site »."""
        message = self._refus('        source: {gabarit: "/BCP_{site"}')
        self.assertIn("accolade", message)

    def test_un_gabarit_sans_colonne_est_refuse(self):
        """C'est une constante deguisee, et `constante` existe. Un relecteur
        qui voit `gabarit` s'attend a une valeur qui varie."""
        message = self._refus('        source: {gabarit: "/BCP01"}')
        self.assertIn("constante", message)

    def test_une_transformation_inconnue_est_refusee_et_les_nomme(self):
        message = self._refus('        source: {colonne: site}\n'
                              '        format: [capitalise]')
        self.assertIn("capitalise", message)
        self.assertIn("majuscules", message)      # la liste des disponibles

    def test_aucune_expression_python_ne_passe(self):
        """Une expression evaluee serait du code arbitraire n'ayant traverse
        ni relecture ni garde — l'echappatoire que le §5.2 interdit."""
        for tentative in ("site.upper()", "{site}.strip()", "eval",
                          "lambda v: v", "__import__"):
            with self.subTest(tentative=tentative):
                message = self._refus('        source: {colonne: site}\n'
                                      f'        format: ["{tentative}"]')
                self.assertIn("inconnue", message)

    def test_une_largeur_non_entiere_est_refusee(self):
        message = self._refus('        source: {colonne: site}\n'
                              '        format: [{zeros: douze}]')
        self.assertIn("ENTIER", message)

    def test_une_transformation_sans_argument_en_refuse_un(self):
        message = self._refus('        source: {colonne: site}\n'
                              '        format: [{majuscules: 3}]')
        self.assertIn("aucun argument", message)

    def test_un_format_sans_source_est_refuse(self):
        """Il n'y a rien a transformer, et le declarer masque une erreur.

        Sur une action qui n'exige PAS de source — `set` est refusee plus tot,
        pour une autre raison.
        """
        chemin = self.racine / "p.yaml"
        chemin.write_text(textwrap.dedent("""
            version: 1
            nom: p
            classe: iterative
            cles: [site]
            plafond_items: 50
            plafond_sauvegardes: 50
            etapes:
              - nom: valider
                action: press
                cible: "wnd[0]/tbar[0]/btn[11]"
                format: [majuscules]
                ecran: {transaction: IA08, programme: R, dynpro: "1000"}
            """), encoding="utf-8")
        with self.assertRaises(PipelineInvalide) as capture:
            charger(chemin)
        self.assertIn("rien a transformer", str(capture.exception))

    def test_un_defaut_sans_source_est_refuse(self):
        chemin = self.racine / "p.yaml"
        chemin.write_text(textwrap.dedent("""
            version: 1
            nom: p
            classe: iterative
            cles: [site]
            plafond_items: 50
            plafond_sauvegardes: 50
            etapes:
              - nom: valider
                action: press
                cible: "wnd[0]/tbar[0]/btn[11]"
                defaut: "x"
                ecran: {transaction: IA08, programme: R, dynpro: "1000"}
            """), encoding="utf-8")
        with self.assertRaises(PipelineInvalide) as capture:
            charger(chemin)
        self.assertIn("rien a remplacer", str(capture.exception))

    def test_format_doit_etre_une_liste(self):
        message = self._refus('        source: {colonne: site}\n'
                              '        format: majuscules')
        self.assertIn("LISTE", message)


class TestLeRaccordementAuPreVol(Base):
    """Un gabarit cite plusieurs colonnes. Le pre-vol doit toutes les voir."""

    def test_une_colonne_de_gabarit_absente_est_refusee_AVANT_toute_action(self):
        """Les oublier rendrait le pre-vol aveugle a exactement le cas qu'il
        existe pour attraper : une colonne absente qui vaut la chaine vide."""
        brut = DriverScripte(identite=IA08, valeurs={"wnd[0]/usr/ctxtX": ""})
        with self.assertRaises(PreparationImpossible) as capture:
            executer(self._charger(
                '        source: {gabarit: "{prefixe}_{introuvable}"}'),
                self.jeu, brut, journal=self.racine / "j.jsonl",
                **SANS_REPETITION)
        self.assertIn("introuvable", str(capture.exception))
        self.assertEqual(brut.gestes, [])

    def test_les_colonnes_citees_sont_resolues_au_chargement(self):
        source = self._charger(
            '        source: {gabarit: "{prefixe}-{site}-{prefixe}"}'
        ).etapes[0].source
        self.assertEqual(source.colonnes, ("prefixe", "site"))


class TestGabarit(unittest.TestCase):
    """L'unite, hors pipeline."""

    def test_les_jetons_se_lisent_dans_l_ordre_sans_doublon(self):
        self.assertEqual(jetons("{b}-{a}-{b}"), ("b", "a"))

    def test_une_accolade_doublee_est_litterale(self):
        self.assertEqual(verifier_gabarit("{{x}}-{site}"), ("site",))
        self.assertEqual(appliquer_gabarit("{{x}}-{site}", {"site": "K75"}),
                         "{x}-K75")

    def test_une_colonne_absente_de_la_ligne_leve(self):
        """Le pre-vol l'a deja verifie : arriver ici signale une incoherence,
        pas une donnee manquante."""
        with self.assertRaises(CompositionInvalide):
            appliquer_gabarit("{site}", {"autre": "x"})


class TestRegistreFerme(unittest.TestCase):
    """Une pipeline ne peut designer que des noms inscrits dans le code."""

    def test_le_registre_est_ferme(self):
        from falcon.pipeline import TRANSFORMATIONS

        self.assertEqual(
            set(TRANSFORMATIONS),
            {"majuscules", "minuscules", "sans_espaces_autour", "zeros",
             "tronque"})

    def test_chaque_transformation_est_une_fonction_du_texte_vers_le_texte(self):
        for nom in ("majuscules", "minuscules", "sans_espaces_autour"):
            with self.subTest(nom=nom):
                rendu = Transformation(nom).appliquer(" Ab ")
                self.assertIsInstance(rendu, str)

    def test_une_forme_d_entree_inattendue_est_refusee(self):
        for brute in ([1, 2], {"a": 1, "b": 2}, 12, None):
            with self.subTest(brute=brute):
                with self.assertRaises(CompositionInvalide):
                    lire_transformation(brute)


if __name__ == "__main__":
    unittest.main()


class TestZerosSurVide(unittest.TestCase):
    """`"".rjust(12, "0")` rend douze zeros, sans une exception.

    Un numero d'article parfaitement plausible, fabrique a partir de rien. La
    signature exacte de la classe de defaut que ce projet traque — et une
    cellule vide du jeu y menait toute seule.
    """

    def test_une_valeur_vide_est_refusee(self):
        with self.assertRaises(CompositionInvalide) as capture:
            appliquer("", (Transformation("zeros", 12),))
        self.assertIn("vide", str(capture.exception))

    def test_une_valeur_d_espaces_aussi(self):
        """Un export en laisse souvent, et `" ".rjust(12, "0")` rendait
        « 00000000000 » suivi d'une espace."""
        with self.assertRaises(CompositionInvalide):
            appliquer("   ", (Transformation("zeros", 12),))

    def test_une_vraie_valeur_est_cadree(self):
        self.assertEqual(appliquer("42", (Transformation("zeros", 12),)),
                         "000000000042")

    def test_douze_zeros_restent_ecrivables_mais_se_declarent(self):
        """Le refus ne retire aucun cas legitime : il oblige a l'ecrire."""
        self.assertEqual(
            appliquer("000000000000", (Transformation("zeros", 12),)),
            "000000000000")

    def test_le_refus_tombe_AVANT_la_premiere_action(self):
        """Un refus a l'item quarante arrive apres trente-neuf sauvegardes.

        Le pre-vol calcule desormais la valeur de chaque etape pour chaque
        item : une source qui n'est pas `lue` ne depend que du jeu, donc le
        calcul est deterministe et rend exactement ce que l'execution
        taperait.
        """
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        racine = Path(dossier.name)
        jeu = racine / "jeu.csv"
        jeu.write_text("site,numero\n1000,42\n2000,\n", encoding="utf-8")

        chemin = racine / "p.yaml"
        chemin.write_text(textwrap.dedent("""\
            version: 1
            nom: cadrage
            classe: iterative
            cles: [site]
            plafond_items: 50
            plafond_sauvegardes: 50
            etapes:
              - nom: saisir
                action: set
                cible: "wnd[0]/usr/ctxtMATNR"
                source: {colonne: numero}
                format: [{zeros: 12}]
                ecran: {transaction: IA08, programme: RIPLKO10, dynpro: "1000"}
            """), encoding="utf-8")

        driver = DriverScripte(Identite("IA08", "RIPLKO10", "1000"))
        with self.assertRaises(PreparationImpossible) as capture:
            executer(charger(chemin), jeu, driver,
                     journal=racine / "j.jsonl", **SANS_REPETITION)
        self.assertIn("zeros", str(capture.exception))
        self.assertEqual(driver.gestes, [], "refuse AVANT la premiere action")

