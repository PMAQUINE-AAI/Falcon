"""Le dialecte YAML de FALCON : ce qui est ambigu est refuse, jamais devine.

**C'est l'UTILISATEUR qui ecrit ces fichiers.** Il declare un automatisme
nouveau en ecrivant un YAML et un CSV, sans passer par nous — c'est la
promesse du projet. Un format qui le trahit en silence sur un zero de tete est
un format qui l'oblige a nous appeler.

Les valeurs dont il est question ici sont tapees dans un ERP de production,
comparees a des identites d'ecran, ou lues comme des politiques de securite.
Aucune ne peut se permettre d'etre « a peu pres ».

Cette suite verifie les deux barrieres, et le fait qu'il en faille deux : le
lecteur attrape a l'ANALYSE ce qui devient indistinguable une fois lu (l'octal
et le sexagesimal) ; les accesseurs exigent le TYPE au lieu de le forcer.
"""

from __future__ import annotations

import unittest

from falcon.noyau.yaml_strict import (
    YamlAmbigu, booleen, entier, liste_de_texte, lire, texte,
)


class TestLecteur(unittest.TestCase):
    """Ce que YAML resout d'une facon que personne n'a en tete."""

    def test_un_entier_a_zero_de_tete_est_refuse(self):
        """« 010 » vaut 8. Et meme sans l'octal, le zero disparait — or les
        codes SAP en sont remplis : numeros de message, references
        d'equipement, codes de division."""
        for brut in ("010", "007", "0100", "-0700"):
            with self.subTest(yaml=brut):
                with self.assertRaises(YamlAmbigu) as capture:
                    lire(f"n: {brut}", "f.yaml")
                self.assertIn("zero de tete", str(capture.exception))

    def test_le_sexagesimal_est_refuse(self):
        """« 12:30 » vaut 750. Une heure ecrite naturellement devient un
        nombre a quatre chiffres."""
        with self.assertRaises(YamlAmbigu) as capture:
            lire("n: 12:30", "f.yaml")
        self.assertIn("base 60", str(capture.exception))

    def test_un_entier_ordinaire_passe(self):
        """Le lecteur refuse l'AMBIGUITE, pas les nombres. Un plafond reste un
        plafond."""
        self.assertEqual(lire("n: 50", "f.yaml"), {"n": 50})
        self.assertEqual(lire("n: 0", "f.yaml"), {"n": 0})

    def test_la_forme_citee_passe_intacte(self):
        """C'est la sortie que le refus indique : mets des guillemets."""
        self.assertEqual(lire('n: "010"', "f.yaml"), {"n": "010"})
        self.assertEqual(lire('n: "12:30"', "f.yaml"), {"n": "12:30"})

    def test_le_refus_nomme_le_fichier_ET_la_ligne(self):
        """« Un message d'erreur qu'il faut aller chercher dans un fichier de
        trois cents lignes coute autant qu'une absence de message. »

        Un refus a l'analyse ne peut pas nommer l'etape — les etapes n'existent
        pas encore. Il nomme la ligne, ce qui remplit le meme office.
        """
        with self.assertRaises(YamlAmbigu) as capture:
            lire("a: 1\nb: 2\nc: 010\n", "p.yaml")
        message = str(capture.exception)
        self.assertIn("p.yaml", message)
        self.assertIn("ligne 3", message)


class TestTexte(unittest.TestCase):

    def test_une_cle_presente_mais_vide_est_refusee(self):
        """`str(None)` rend « None » : un identifiant de controle qui n'a pas
        l'air d'un marqueur, et qui laisse une carte se declarer complete."""
        with self.assertRaises(YamlAmbigu) as capture:
            texte(None, "champ_table", source="c.yaml")
        self.assertIn("champ_table", str(capture.exception))

    def test_un_booleen_est_refuse(self):
        """`on`, `yes`, `N` sont des booleens YAML. `str(True)` rend « True »,
        et c'est ce qui serait tape dans SAP."""
        with self.assertRaises(YamlAmbigu):
            texte(True, "constante")

    def test_un_nombre_est_refuse(self):
        for valeur in (64, 1.5, 0):
            with self.subTest(valeur=valeur):
                with self.assertRaises(YamlAmbigu):
                    texte(valeur, "constante")

    def test_une_chaine_passe_intacte_zeros_compris(self):
        self.assertEqual(texte("007", "constante"), "007")

    def test_le_defaut_ne_vaut_que_pour_une_cle_ABSENTE(self):
        """Ecrire la cle et ne rien mettre derriere n'est pas la meme chose
        que ne pas l'ecrire : c'est une omission, et elle doit se voir."""
        self.assertEqual(texte(None, "x", defaut="TODO"), "TODO")


class TestBooleen(unittest.TestCase):
    """Le defaut qui a motive ce module."""

    def test_la_chaine_non_ne_vaut_PAS_faux(self):
        """`bool("non")` vaut True : « non » n'est pas un booleen YAML, c'est
        une chaine, et toute chaine non vide vaut vrai.

        Applique a `politique.poursuivre`, ca donnait une entree de registre
        qui disait « arrete le lot » et un lot qui continuait a ecrire.
        """
        for brut in ("non", "oui", "N", "false ", "0"):
            with self.subTest(valeur=brut):
                with self.assertRaises(YamlAmbigu) as capture:
                    booleen(brut, "poursuivre", source="r.yaml")
                self.assertIn("true", str(capture.exception))

    def test_un_vrai_booleen_passe(self):
        self.assertIs(booleen(True, "poursuivre"), True)
        self.assertIs(booleen(False, "poursuivre"), False)

    def test_une_cle_absente_prend_le_defaut(self):
        self.assertIs(booleen(None, "poursuivre", defaut=False), False)


class TestEntier(unittest.TestCase):

    def test_un_booleen_n_est_pas_un_entier(self):
        """`True` vaut 1 pour Python : un `plafond_items: true` plafonnerait
        a un item, sans un mot."""
        with self.assertRaises(YamlAmbigu):
            entier(True, "plafond_items")

    def test_le_minimum_est_verifie(self):
        with self.assertRaises(YamlAmbigu) as capture:
            entier(0, "plafond_items", minimum=1)
        self.assertIn("au moins 1", str(capture.exception))

    def test_un_entier_valide_passe(self):
        self.assertEqual(entier(50, "plafond_items", minimum=1), 50)


class TestListe(unittest.TestCase):

    def test_un_scalaire_seul_est_refuse_et_pas_eclate(self):
        """`tuple("site")` rend ('s','i','t','e') : quatre colonnes de clef
        nommees s, i, t et e. L'erreur ressortait bien plus loin, sous la
        forme d'une colonne absente — et accusait le jeu de donnees."""
        with self.assertRaises(YamlAmbigu) as capture:
            liste_de_texte("site", "cles", source="p.yaml")
        message = str(capture.exception)
        self.assertIn("LISTE", message)
        self.assertIn("s, i, t, e", message)

    def test_une_liste_de_chaines_passe(self):
        self.assertEqual(liste_de_texte(["site", "usine"], "cles"),
                         ("site", "usine"))

    def test_un_element_non_texte_est_refuse_et_situe(self):
        with self.assertRaises(YamlAmbigu) as capture:
            liste_de_texte(["site", 100], "cles")
        self.assertIn("cles[1]", str(capture.exception))


class TestSurLesLecteursReels(unittest.TestCase):
    """Les quatre YAML que FALCON lit passent tous par ce dialecte."""

    def test_le_registre_livre_se_charge(self):
        from falcon.taxonomie import Registre

        self.assertTrue(Registre.charger().entrees)

    def test_la_carte_livree_se_charge_et_reste_incomplete(self):
        from falcon.volumique import charger_carte

        self.assertFalse(charger_carte().complete)

    def test_une_politique_ecrite_non_ne_rend_PAS_le_lot_poursuivable(self):
        """Le pire defaut trouve par l'audit. Une entree de registre disant
        « arrete le lot » laissait le lot continuer a ecrire dans SAP, parce
        que `bool("non")` vaut True."""
        import tempfile
        from pathlib import Path

        from falcon.taxonomie import Registre
        from falcon.taxonomie.registre import RegistreInvalide

        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        chemin = Path(dossier.name) / "r.yaml"
        chemin.write_text(
            "version: 1\n"
            "entrees:\n"
            "  - nom: essai\n"
            "    categorie: connue_benigne\n"
            "    canal: statut\n"
            "    origine: falcon_observe\n"
            "    justification: \"entree d'essai, sans equivalent reel\"\n"
            "    correspondance: {type: S, id: ZZ, numero: \"001\"}\n"
            "    politique: {poursuivre: non}\n", encoding="utf-8")
        with self.assertRaises(RegistreInvalide) as capture:
            Registre.charger(chemin)
        self.assertIn("poursuivre", str(capture.exception))

    def test_un_numero_de_message_a_zero_de_tete_est_refuse(self):
        """`numero: 010` etait lu 8 : l'entree blanchissait le message 008 et
        laissait le 010 ressortir `inconnue`, donc bloquant. Les deux sens
        faux, et aucun ne levait."""
        import tempfile
        from pathlib import Path

        from falcon.taxonomie import Registre
        from falcon.taxonomie.registre import RegistreInvalide

        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        chemin = Path(dossier.name) / "r.yaml"
        chemin.write_text(
            "version: 1\n"
            "entrees:\n"
            "  - nom: essai\n"
            "    categorie: connue_benigne\n"
            "    canal: statut\n"
            "    origine: falcon_observe\n"
            "    justification: \"entree d'essai, sans equivalent reel\"\n"
            "    correspondance: {type: S, id: ZZ, numero: 010}\n"
            "    politique: {poursuivre: true}\n", encoding="utf-8")
        with self.assertRaises(RegistreInvalide) as capture:
            Registre.charger(chemin)
        self.assertIn("zero de tete", str(capture.exception))

    def test_une_carte_a_moitie_remplie_ne_se_declare_plus_complete(self):
        """Elle est livree vide et doit REFUSER tant qu'un humain n'a pas
        releve les identifiants. Une valeur vide devenait le texte « None »,
        la carte se declarait complete, et l'export naviguait vers un controle
        nomme « None »."""
        import tempfile
        from pathlib import Path

        from falcon.volumique import CarteInvalide, charger_carte

        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        chemin = Path(dossier.name) / "c.yaml"
        chemin.write_text(
            "version: 1\n"
            "champ_table:\n"
            "bouton_executer: b\n"
            "grille: g\n"
            "ecran_selection: {transaction: SE16N, programme: R, "
            "dynpro: \"1000\"}\n"
            "ecran_resultat: {transaction: SE16N, programme: R, "
            "dynpro: \"0500\"}\n", encoding="utf-8")
        with self.assertRaises(CarteInvalide) as capture:
            charger_carte(chemin)
        self.assertIn("champ_table", str(capture.exception))

    def test_des_cles_de_pipeline_en_scalaire_sont_refusees(self):
        """`cles: site` donnait quatre colonnes nommees s, i, t et e."""
        import tempfile
        import textwrap
        from pathlib import Path

        from falcon.pipeline import PipelineInvalide, charger

        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        chemin = Path(dossier.name) / "p.yaml"
        chemin.write_text(textwrap.dedent("""
            version: 1
            nom: p
            classe: iterative
            cles: site
            plafond_items: 50
            plafond_sauvegardes: 50
            etapes:
              - nom: taper
                action: set
                cible: "wnd[0]/usr/ctxtX"
                source: {colonne: site}
                ecran: {transaction: IA08, programme: R, dynpro: "1000"}
            """), encoding="utf-8")
        with self.assertRaises(PipelineInvalide) as capture:
            charger(chemin)
        self.assertIn("LISTE", str(capture.exception))


if __name__ == "__main__":
    unittest.main()
