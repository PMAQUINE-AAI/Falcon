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
    ACTIONS, AVEC_SOURCE, MARQUEUR_BROUILLON, SOURCE_CONSTANTE,
    ExtensionInconnue, Pipeline, PipelineInvalide, charger, connues,
    etape_python, oublier_tout, resoudre,
)
from falcon.pipeline.chargeur import _etape

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


#: `VALIDE` se termine par l'indentation de sa triple-quote fermante. Y
#: concatener une etape la decalerait de quatre espaces et casserait le YAML —
#: sur une erreur d'indentation, pas sur ce que le test voulait verifier.
SOCLE = VALIDE.rstrip() + "\n"


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

    def test_une_derogation_ne_peut_porter_que_sur_SON_etape(self):
        """Le controleur n'en accorde une que si sa portee vaut `*` ou
        `etape:<son propre nom>`. Visant une autre, elle est MORTE PAR
        CONSTRUCTION — et elle etait pourtant acceptee, avec un journal qui
        annoncait « derogee » pendant que la garde restait armee."""
        # La derogation est portee par « executer » et vise « saisir_division ».
        # Les deux etapes existent : rien ne signalait la faute.
        avec = SOCLE + (
            '        derogations:\n'
            '          - garde: relecture\n'
            '            portee: "etape:saisir_division"\n'
            '            motif: "Un motif suffisamment long pour le seuil."\n')
        with self.assertRaises(PipelineInvalide) as capture:
            self._charger(avec)
        message = str(capture.exception)
        self.assertIn("SON etape", message)
        self.assertIn("resterait armee", message)

    def test_les_TROIS_composantes_de_l_ecran_exigent_une_chaine(self):
        """Seul `dynpro` etait type ; les deux autres passaient par `str()`.

        C'est l'operation que l'en-tete de `yaml_strict` designe comme
        « precisement ce qu'il ne faut pas ici », employee a trois lignes du
        commentaire qui l'interdit pour `dynpro`. Mesure avant correction :

            transaction: on   -> ('True', 'RIPLKO10', '1000')
            programme: 1.50   -> ('IA08', '1.5', '1000')

        Le triplet est ce que la garde d'identite compare a CHAQUE etape.
        """
        for cle, avant, apres in (("transaction", "transaction: IA08",
                                   "transaction: on"),
                                  ("programme", "programme: RIPLKO10",
                                   "programme: 1.50"),
                                  ("dynpro", 'dynpro: "1000"',
                                   "dynpro: 1000")):
            with self.subTest(composante=cle):
                self.assertIn(avant, VALIDE, "l'ancre du test n'a pas mordu")
                with self.assertRaises(PipelineInvalide) as capture:
                    self._charger(VALIDE.replace(avant, apres))
                self.assertIn(f"ecran.{cle}", str(capture.exception))

    def test_une_cle_RETIREE_dit_ce_qui_s_est_passe(self):
        """`validation_reelle` etait acceptee, stockee, et lue NULLE PART.

        Ni en production, ni en test, ni dans la specification, qui ne la
        nomme pas. Un utilisateur qui la declarait croyait avoir arme quelque
        chose ; il n'avait rien arme. La retirer en silence ferait « cle
        inconnue », qui envoie chercher une faute de frappe — d'ou un refus
        qui dit ce qui s'est passe et vers quoi se tourner.
        """
        with self.assertRaises(PipelineInvalide) as capture:
            self._charger(VALIDE + "\n    validation_reelle: {actif: true}\n")
        message = str(capture.exception)
        self.assertIn("validation_reelle", message)
        self.assertIn("n'armait rien", message)
        self.assertIn("plafond_sauvegardes", message)

    def test_la_source_est_typee(self):
        source = self._charger(VALIDE).etapes[0].source
        self.assertEqual((source.genre, source.valeur), ("colonne", "site"))


class TestEmpreinteObligatoire(unittest.TestCase):
    """Aucune pipeline ne peut exister sans empreinte.

    C'est elle que la reprise compare pour verifier que ni la pipeline ni le
    jeu n'ont change. `charger()` est aujourd'hui le seul constructeur du
    depot et la remplit toujours ; ce controle existe pour que ca reste vrai
    si un second chemin de construction apparait — un convertisseur, par
    exemple.
    """

    def test_une_pipeline_sans_empreinte_ne_se_construit_pas(self):
        from falcon.pipeline.modele import Etape, Pipeline

        etape = Etape(nom="x", action="press", cible="wnd[0]/tbar[0]/btn[11]",
                      navigation_libre=True)
        for empreinte in ("", "   "):
            with self.subTest(empreinte=empreinte):
                with self.assertRaises(ValueError) as capture:
                    Pipeline(nom="p", classe="iterative", etapes=(etape,),
                             plafond_items=1, plafond_sauvegardes=1,
                             empreinte=empreinte)
                self.assertIn("empreinte", str(capture.exception))

    def test_une_pipeline_chargee_en_porte_toujours_une(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        chemin = Path(dossier.name) / "p.yaml"
        chemin.write_text(textwrap.dedent(VALIDE), encoding="utf-8")
        self.assertTrue(charger(chemin).empreinte.strip())


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

    def test_un_dynpro_non_quote_est_refuse(self):
        """Le meme defaut que dans la carte SE16N, trouve au meme moment :
        YAML lit « 0100 » comme de l'OCTAL et en fait 64. Le dynpro etait
        corrompu sans un mot, et la garde d'identite aurait compare contre un
        numero d'ecran qui n'existe pas.
        """
        message = self._refus(VALIDE.replace('dynpro: "1000"', "dynpro: 0100"))
        self.assertIn("octal", message)
        self.assertIn("guillemets", message)
        self.assertIn("p.yaml", message)
        self.assertIn("ligne", message)      # a defaut de l'etape : la ligne

    def test_une_source_non_quotee_est_refusee(self):
        """Meme defaut que le dynpro, consequence pire : ce n'est pas une
        comparaison qui devient fausse, c'est une valeur TAPEE DANS SAP.

        YAML n'est pas du texte. Cinq de ces six formes s'ecrivaient dans un
        champ SAP sans que rien ne leve — et « 007 » vaut 7, alors que les
        codes SAP sont remplis de zeros.
        """
        pieges = {
            "0100": "64",        # octal
            "007": "7",          # zeros de tete perdus
            "12:30": "750",      # sexagesimal
            "1.50": "1.5",       # flottant
            "on": "True",        # booleen
            "2026-09-07": "",    # date
        }
        for brut in pieges:
            with self.subTest(yaml=brut):
                message = self._refus(
                    VALIDE.replace("{colonne: site}", f"{{constante: {brut}}}"))
                # Deux barrieres, deux messages, et les deux disent quoi faire.
                # Le lecteur strict attrape l'octal et le sexagesimal des
                # l'analyse — donc plus tot, et en nommant la ligne ; les
                # autres formes tombent sur l'accesseur, qui exige le type.
                self.assertIn("guillemets", message)
                self.assertIn("p.yaml", message)

    def test_une_source_quotee_traverse_intacte(self):
        """L'autre moitie : ce que l'utilisateur a ecrit doit arriver tel quel
        jusqu'au champ SAP, zeros de tete compris."""
        for valeur in ("0100", "007", "12:30", "1.50", "on"):
            with self.subTest(valeur=valeur):
                pipeline = self._charger(VALIDE.replace(
                    "{colonne: site}", f'{{constante: "{valeur}"}}'))
                self.assertEqual(pipeline.etapes[0].source.valeur, valeur)

    def test_un_refus_d_accesseur_dit_ou_est_l_etape(self):
        """Ce que l'accesseur refuse, il le situe a l'etape. Ce que le lecteur
        refuse a l'analyse ne le peut pas — les etapes n'existent pas encore —
        et nomme la ligne a la place."""
        message = self._refus(
            VALIDE.replace("{colonne: site}", "{constante: 1.50}"))
        self.assertIn("etape 1", message)
        self.assertIn("saisir_division", message)

    def test_une_cible_booleenne_est_refusee(self):
        message = self._refus(VALIDE.replace(
            '        cible: "wnd[0]/usr/ctxtWERKS-LOW"', "        cible: on"))
        self.assertIn("cible", message)
        self.assertIn("CHAINE", message)

    def test_un_nom_d_etape_booleen_est_refuse(self):
        message = self._refus(VALIDE.replace("      - nom: saisir_division",
                                             "      - nom: on"))
        self.assertIn("nom", message)
        self.assertIn("CHAINE", message)

    def test_une_navigation_libre_non_booleenne_nomme_LA_VRAIE_faute(self):
        """Elle etait lue deux fois : un `bool()` permissif pour le XOR, un
        `booleen()` strict pour ce qui est stocke. Un `navigation_libre: "non"`
        accompagne d'un `ecran` rendait donc « ensemble n'ont pas de sens » —
        un message qui envoie SUPPRIMER L'ECRAN, alors que la faute est le
        « non ». Un refus qui nomme la mauvaise faute envoie corriger au
        mauvais endroit."""
        message = self._refus(VALIDE.replace(
            "        statut_attendu: \"S\"",
            "        navigation_libre: \"non\""))
        self.assertIn("navigation_libre", message)
        self.assertIn("true", message)
        self.assertNotIn("ensemble n'ont pas de sens", message)

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


class TestToucheDeFonction(Base):
    """`vkey` etait declarable et chargeable, et muette sur la touche a
    envoyer : aucun champ ne la portait. Le moteur ne pouvait pas l'executer,
    et le trou n'est apparu qu'au moment de l'ecrire."""

    #: La touche est CITEE. Le chargeur exige une chaine pour toute source :
    #: YAML lit « 0100 » comme de l'octal, et c'est la valeur ecrite dans SAP.
    ETAPE = ('      - nom: valider\n'
             '        action: vkey\n'
             '        source: {constante: "%s"}\n'
             '        navigation_libre: true\n')

    def _avec(self, valeur: str, **options) -> str:
        return SOCLE + (self.ETAPE % valeur)

    def test_une_touche_se_declare_et_se_charge(self):
        pipeline = self._charger(self._avec("11"))
        etape = pipeline.etapes[-1]
        self.assertEqual(etape.action, "vkey")
        self.assertEqual(etape.source.valeur, "11")

    def test_une_touche_manquante_est_refusee(self):
        message = self._refus(SOCLE + ('      - nom: valider\n'
                                        '        action: vkey\n'
                                        '        navigation_libre: true\n'))
        self.assertIn("exige une `source`", message)

    def test_une_touche_qui_n_est_pas_un_entier_est_refusee(self):
        """Refuse au chargement, pas au moment ou le moteur enverrait une
        touche fantome."""
        message = self._refus(self._avec("F11"))   # `ETAPE` pose les guillemets
        self.assertIn("entier est attendu", message)
        self.assertIn("valider", message)

    def test_une_touche_ne_peut_pas_venir_d_une_colonne(self):
        """Une touche de fonction est une propriete de la pipeline, pas de
        l'item : la faire varier d'une ligne a l'autre rend le geste
        imprevisible, et hors de portee de toute relecture."""
        message = self._refus(SOCLE + ('      - nom: valider\n'
                                        '        action: vkey\n'
                                        '        source: {colonne: touche}\n'
                                        '        navigation_libre: true\n'))
        self.assertIn("constante", message)


class TestSourceLue(Base):
    """Une source « lue » designe le nom d'une etape `lire` anterieure.

    Rien ne le verifiait : une reference pendante produisait une saisie vide
    a l'execution, sans erreur — la classe de defaut que ce projet traque.
    """

    LIRE = ('      - nom: numero_ordre\n'
            '        action: lire\n'
            '        cible: "wnd[0]/usr/txtAUFNR"\n'
            '        navigation_libre: true\n')
    ECRIRE = ('      - nom: recopier\n'
              '        action: set\n'
              '        cible: "wnd[0]/usr/txtCIBLE"\n'
              '        source: {lue: %s}\n'
              '        navigation_libre: true\n')

    def test_une_lecture_puis_sa_reutilisation_se_chargent(self):
        pipeline = self._charger(SOCLE + self.LIRE
                                 + (self.ECRIRE % "numero_ordre"))
        self.assertEqual(pipeline.etapes[-1].source.genre, "lue")

    def test_une_reference_pendante_est_refusee(self):
        message = self._refus(SOCLE + (self.ECRIRE % "jamais_lu"))
        self.assertIn("aucune etape `lire` de ce nom ne precede", message)
        self.assertIn("recopier", message)

    def test_une_reference_a_une_etape_posterieure_est_refusee(self):
        """L'ordre compte : lire apres avoir ecrit ne lie rien."""
        message = self._refus(SOCLE + (self.ECRIRE % "numero_ordre")
                              + self.LIRE)
        self.assertIn("numero_ordre", message)

    def test_une_reference_a_une_etape_qui_ne_lit_pas_est_refusee(self):
        """`executer` existe, mais c'est un `press` : il ne lie rien."""
        message = self._refus(SOCLE + (self.ECRIRE % "executer"))
        self.assertIn("aucune etape `lire`", message)


class TestMarqueurDeBrouillon(Base):
    """`fonction: TODO` charge en brouillon, et seulement la.

    Le generateur du lot 7b pose ce marqueur la ou une trace contient un
    geste qu'aucune action ne sait exprimer. Sans cette tolerance, un
    brouillon genere serait impossible a relire, meme explicitement comme
    brouillon ; avec elle sans garde-fou, un fichier livre passerait avec des
    etapes qui ne font rien.
    """

    ETAPE = ('      - nom: charger_variante\n'
             '        action: python\n'
             '        fonction: TODO\n'
             '        navigation_libre: true\n')

    def test_le_marqueur_charge_en_brouillon(self):
        pipeline = self._charger(SOCLE + self.ETAPE, brouillon=True)
        self.assertEqual(pipeline.etapes[-1].fonction, "TODO")

    def test_le_marqueur_est_refuse_hors_brouillon(self):
        message = self._refus(SOCLE + self.ETAPE)
        self.assertIn("TODO", message)
        self.assertIn("brouillon", message)

    def test_une_fonction_inconnue_reste_refusee_meme_en_brouillon(self):
        """La tolerance porte sur le marqueur, pas sur n'importe quel nom."""
        message = self._refus(
            SOCLE + self.ETAPE.replace("TODO", "charger_la_variante"),
            brouillon=True)
        self.assertIn("non enregistree", message)

    def test_la_seconde_barriere_tient_toute_seule(self):
        """Deux barrieres independantes, et il faut les tester separement.

        `charger()` refuse le fichier des le premier marqueur, donc bien
        avant d'examiner l'etape : le controle au niveau de l'etape n'est
        jamais atteint par ce chemin. Un controle negatif ne le voyait pas
        tomber — autrement dit, cette seconde barriere ne garantissait rien.
        On l'exerce donc directement.
        """
        brute = {"nom": "charger_variante", "action": "python",
                 "fonction": MARQUEUR_BROUILLON, "navigation_libre": True}
        self.assertEqual(
            _etape(brute, "p.yaml", 1, brouillon=True).fonction,
            MARQUEUR_BROUILLON)
        with self.assertRaises(PipelineInvalide) as capture:
            _etape(brute, "p.yaml", 1, brouillon=False)
        self.assertIn("non enregistree", str(capture.exception))


class TestModele(unittest.TestCase):

    def test_les_actions_couvrent_la_specification(self):
        """Les quatre de la specification, plus celles que le terrain impose."""
        for action in ("set", "press", "select", "lire"):
            self.assertIn(action, ACTIONS)
        for action in ("cocher", "vkey", "python"):
            self.assertIn(action, ACTIONS)

    def test_toute_action_a_source_constante_exige_une_source(self):
        """Sinon la contrainte de constance porterait sur rien."""
        self.assertLessEqual(SOURCE_CONSTANTE, AVEC_SOURCE)

    def test_le_champ_de_commande_a_une_seule_definition(self):
        """Le moteur et le lecteur de traces en ont besoin tous les deux.
        Deux definitions finiraient par diverger."""
        from falcon.noyau import CHAMP_DE_COMMANDE, SUFFIXE_CHAMP_DE_COMMANDE
        from falcon.trace.esquisse import CHAMP_DE_COMMANDE as SUFFIXE_TRACE
        self.assertEqual(SUFFIXE_TRACE, SUFFIXE_CHAMP_DE_COMMANDE)
        self.assertTrue(CHAMP_DE_COMMANDE.endswith(SUFFIXE_CHAMP_DE_COMMANDE))
        self.assertTrue(CHAMP_DE_COMMANDE.startswith("wnd[0]"))


if __name__ == "__main__":
    unittest.main()


GRILLE = "wnd[1]/usr/cntlALV_CONTAINER_1/shellcont/shell"

ECRAN = 'ecran: {transaction: IA08, programme: RIPLKO10, dynpro: "1000"}'


class TestActionsDeGrille(Base):
    """Les trois actions qui referment le piege de la selection par index.

    `couture/interface.py` porte la regle depuis toujours — « lire la grille
    pour retrouver la ligne voulue par son CONTENU » — et personne ne
    l'appliquait, faute d'une action qui le permette. La regle etait une
    phrase ; elle devient un vocabulaire.
    """

    def _avec(self, etape: str):
        return self._charger(SOCLE + textwrap.indent(
            textwrap.dedent(etape), "      "))

    def test_les_trois_actions_se_chargent(self):
        pipeline = self._avec(f"""
            - nom: lister
              action: extraire
              cible: "{GRILLE}"
              {ECRAN}
            - nom: choisir_la_variante
              action: choisir
              cible: "{GRILLE}"
              colonne: VARIANT
              source: {{colonne: site}}
              {ECRAN}
            - nom: l_ouvrir
              action: ouvrir
              cible: "{GRILLE}"
              {ECRAN}
        """)
        actions = [e.action for e in pipeline.etapes[-3:]]
        self.assertEqual(actions, ["extraire", "choisir", "ouvrir"])
        self.assertEqual(pipeline.etapes[-2].colonne, "VARIANT")

    # -- `ouvrir` ne peut pas partir seul --------------------------------

    def test_ouvrir_sans_choisir_qui_precede_est_refuse(self):
        """CONTROLE NEGATIF : retirer le controle fait tomber ce test.

        `grid_double_click` agit sur la cellule COURANTE. Sans positionnement,
        c'est la ligne 0 qui s'ouvre — **sans erreur**. Une autre variante,
        en silence.
        """
        message = self._refus(SOCLE + textwrap.indent(textwrap.dedent(f"""
            - nom: l_ouvrir
              action: ouvrir
              cible: "{GRILLE}"
              {ECRAN}
        """), "      "))
        self.assertIn("cellule COURANTE", message)
        self.assertIn("ligne 0", message)

    def test_ouvrir_apres_une_etape_intercalee_est_refuse(self):
        """« Immediatement », et non « quelque part avant ».

        Rien ici ne prouve qu'une etape intercalee laisse la cellule courante
        en place. La megatrace montre les trois gestes consecutifs ; on s'en
        tient a ce qu'elle montre.
        """
        message = self._refus(SOCLE + textwrap.indent(textwrap.dedent(f"""
            - nom: choisir_la_variante
              action: choisir
              cible: "{GRILLE}"
              colonne: VARIANT
              source: {{colonne: site}}
              {ECRAN}
            - nom: souffler
              action: press
              cible: "wnd[0]/tbar[0]/btn[3]"
              {ECRAN}
            - nom: l_ouvrir
              action: ouvrir
              cible: "{GRILLE}"
              {ECRAN}
        """), "      "))
        self.assertIn("cellule COURANTE", message)

    def test_ouvrir_sur_une_AUTRE_grille_que_le_choisir_est_refuse(self):
        message = self._refus(SOCLE + textwrap.indent(textwrap.dedent(f"""
            - nom: choisir_la_variante
              action: choisir
              cible: "{GRILLE}"
              colonne: VARIANT
              source: {{colonne: site}}
              {ECRAN}
            - nom: l_ouvrir
              action: ouvrir
              cible: "wnd[0]/usr/cntlAUTRE/shellcont/shell"
              {ECRAN}
        """), "      "))
        self.assertIn("dont personne n'a positionne la cellule courante",
                      message)

    # -- `colonne` --------------------------------------------------------

    def test_choisir_sans_colonne_est_refuse(self):
        """Se rabattre sur la premiere colonne chercherait dans la premiere
        colonne de la MISE EN PAGE du poste, qui change d'un poste a l'autre."""
        message = self._refus(SOCLE + textwrap.indent(textwrap.dedent(f"""
            - nom: choisir_la_variante
              action: choisir
              cible: "{GRILLE}"
              source: {{colonne: site}}
              {ECRAN}
        """), "      "))
        self.assertIn("exige une `colonne`", message)
        self.assertIn("MISE EN PAGE", message)

    def test_choisir_sans_source_est_refuse(self):
        message = self._refus(SOCLE + textwrap.indent(textwrap.dedent(f"""
            - nom: choisir_la_variante
              action: choisir
              cible: "{GRILLE}"
              colonne: VARIANT
              {ECRAN}
        """), "      "))
        self.assertIn("exige une `source`", message)

    def test_colonne_sur_une_action_qui_n_en_veut_pas_est_refusee(self):
        """Une clef acceptee et lue nulle part est une intention qui n'arme
        rien — le defaut que `CLES_REFUSEES` traque deja ailleurs."""
        message = self._refus(SOCLE + textwrap.indent(textwrap.dedent(f"""
            - nom: presser
              action: press
              cible: "wnd[0]/tbar[0]/btn[8]"
              colonne: VARIANT
              {ECRAN}
        """), "      "))
        self.assertIn("`colonne` n'a pas de sens", message)

    def test_colonnes_sur_une_action_qui_n_en_veut_pas_est_refusee(self):
        message = self._refus(SOCLE + textwrap.indent(textwrap.dedent(f"""
            - nom: choisir_la_variante
              action: choisir
              cible: "{GRILLE}"
              colonne: VARIANT
              colonnes: [VARIANT, TEXT]
              source: {{colonne: site}}
              {ECRAN}
        """), "      "))
        self.assertIn("`colonnes` n'a pas de sens", message)

    # -- `extraire` exige son ecran ---------------------------------------

    def test_extraire_en_navigation_libre_est_refuse(self):
        """CONTROLE NEGATIF : autoriser `navigation_libre` fait tomber ce test.

        C'est la garde d'identite qui distingue « la recherche n'a rien
        remonte » de « SAP a ouvert l'objet directement parce qu'il n'y en
        avait qu'un » — deux conclusions OPPOSEES qui produisent la meme
        grille introuvable. La desarmer, c'est perdre la seule chose qui les
        separe.
        """
        message = self._refus(SOCLE + textwrap.indent(textwrap.dedent(f"""
            - nom: lister
              action: extraire
              cible: "{GRILLE}"
              navigation_libre: true
        """), "      "))
        self.assertIn("`navigation_libre` y est interdit", message)
        self.assertIn("deux conclusions opposees", message)

    def test_choisir_et_ouvrir_acceptent_la_navigation_libre(self):
        """Le refus porte sur `extraire` SEULE, et il faut que ce soit visible.

        Un refus trop large se relacherait globalement le jour ou il generait.
        """
        pipeline = self._avec(f"""
            - nom: choisir_la_variante
              action: choisir
              cible: "{GRILLE}"
              colonne: VARIANT
              source: {{colonne: site}}
              navigation_libre: true
            - nom: l_ouvrir
              action: ouvrir
              cible: "{GRILLE}"
              navigation_libre: true
        """)
        self.assertTrue(pipeline.etapes[-1].navigation_libre)

    # -- les colonnes d'extraction ----------------------------------------

    def test_les_colonnes_declarees_sont_conservees_dans_l_ordre(self):
        pipeline = self._avec(f"""
            - nom: lister
              action: extraire
              cible: "{GRILLE}"
              colonnes: [VARIANT, TEXT, ENAME]
              {ECRAN}
        """)
        self.assertEqual(pipeline.etapes[-1].colonnes,
                         ("VARIANT", "TEXT", "ENAME"))

    def test_colonnes_en_scalaire_est_refuse(self):
        """Le piege de `fenetres` : « VARIANT » en scalaire donnerait sept
        colonnes nommees V, A, R, I, A, N, T."""
        message = self._refus(SOCLE + textwrap.indent(textwrap.dedent(f"""
            - nom: lister
              action: extraire
              cible: "{GRILLE}"
              colonnes: VARIANT
              {ECRAN}
        """), "      "))
        self.assertIn("colonnes", message)

    def test_extraire_sans_colonnes_est_licite(self):
        """La premiere extraction est justement celle ou l'on ne connait pas
        encore les noms de colonnes. Les exiger la rendrait impossible."""
        pipeline = self._avec(f"""
            - nom: lister
              action: extraire
              cible: "{GRILLE}"
              {ECRAN}
        """)
        self.assertEqual(pipeline.etapes[-1].colonnes, ())

    # -- les trois exigent une cible --------------------------------------

    def test_les_trois_actions_exigent_une_cible(self):
        """Une action de grille sans grille n'a rien a nommer."""
        corps = {
            "extraire": f"""
            - nom: sans_cible
              action: extraire
              {ECRAN}
        """,
            "choisir": f"""
            - nom: sans_cible
              action: choisir
              colonne: VARIANT
              source: {{colonne: site}}
              {ECRAN}
        """,
            "ouvrir": f"""
            - nom: sans_cible
              action: ouvrir
              {ECRAN}
        """,
        }
        for action, texte in corps.items():
            with self.subTest(action):
                message = self._refus(
                    SOCLE + textwrap.indent(textwrap.dedent(texte), "      "))
                self.assertIn("exige une `cible`", message)


class TestCeQuOnNAJoutePas(unittest.TestCase):
    """Trois actions absentes, et leur absence est une decision."""

    def test_aucune_action_ne_selectionne_par_index(self):
        """Ce serait rendre declaratif exactement ce que la couture demande de
        ne pas faire : « l'index depend du contenu de la base au moment ou on
        regarde »."""
        for nom in ACTIONS:
            with self.subTest(nom):
                self.assertNotIn("index", nom)
                self.assertNotIn("rang", nom)

    def test_aucune_action_ne_compte_les_lignes(self):
        """Piege 7 : « ne jamais piloter une boucle par un compteur ». Une
        action qui exposerait le compte inviterait a le piloter."""
        self.assertNotIn("compter", ACTIONS)
