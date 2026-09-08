"""Lecture des jeux, regroupement par unite de sauvegarde, et reexport des KO.

Le test central de ce fichier est l'aller-retour : lire un jeu, tout marquer
KO, reexporter, relire — et retrouver exactement le meme contenu. C'est
l'exigence que la specification qualifie de principale, parce qu'un rapport
qu'il faut retravailler a la main avant de relancer annule le benefice de
l'automatisation sur les cas difficiles.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from falcon.donnees import (
    COLONNES_DIAGNOSTIC, JeuInvalide, ecrire_items, empreinte_jeu,
    grouper, identifiant, lire, lire_items,
)
from falcon.journal import (
    Ecrivain, Etape, ExecutionDebut, ExecutionFin, Garde, ItemDebut, ItemFin,
    depuis_journal, rendre,
)
from falcon.noyau import horloge_figee

RUN = "r-test"


class TestLecture(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.racine = Path(self.dossier.name)
        self.addCleanup(self.dossier.cleanup)

    def _poser(self, nom: str, contenu: bytes) -> Path:
        chemin = self.racine / nom
        chemin.write_bytes(contenu)
        return chemin

    def test_csv_simple(self):
        chemin = self._poser("j.csv", b"site,variante\nFR12,/BCP01\nFR13,/BCP02\n")
        lignes, dialecte = lire(chemin)
        self.assertEqual(len(lignes), 2)
        self.assertEqual(dialecte.colonnes, ("site", "variante"))
        self.assertEqual(lignes[0], {"site": "FR12", "variante": "/BCP01"})

    def test_le_delimiteur_est_detecte(self):
        chemin = self._poser("j.csv", b"site;variante\nFR12;/BCP01\n")
        _, dialecte = lire(chemin)
        self.assertEqual(dialecte.delimiteur, ";")

    def test_le_bom_et_les_fins_de_ligne_windows_sont_retenus(self):
        """Un export SAP passe par un poste Windows."""
        chemin = self._poser("j.csv", b"\xef\xbb\xbfsite\r\nFR12\r\n")
        _, dialecte = lire(chemin)
        self.assertTrue(dialecte.bom)
        self.assertEqual(dialecte.fin_de_ligne, "\r\n")

    def test_repli_sur_cp1252(self):
        chemin = self._poser("j.csv", "site\nQu\xe9bec\n".encode("cp1252"))
        lignes, dialecte = lire(chemin)
        self.assertEqual(dialecte.encodage, "cp1252")
        self.assertEqual(lignes[0]["site"], "Québec")

    def test_les_colonnes_de_diagnostic_sont_retirees(self):
        """C'est ce qui rend un fichier de KO relisible sans retouche."""
        chemin = self._poser(
            "ko.csv", b"site,falcon_categorie,falcon_item_id\nFR12,fautive,ab\n")
        lignes, dialecte = lire(chemin)
        self.assertEqual(dialecte.colonnes, ("site",))
        self.assertEqual(lignes[0], {"site": "FR12"})

    def test_jsonl(self):
        chemin = self._poser(
            "j.jsonl",
            b'{"site":"FR12","variante":"/BCP01"}\n'
            b'{"site":"FR13","variante":"/BCP02"}\n')
        lignes, dialecte = lire(chemin)
        self.assertEqual(dialecte.format, "jsonl")
        self.assertEqual(dialecte.colonnes, ("site", "variante"))
        self.assertEqual(len(lignes), 2)
        self.assertEqual(lignes[1], {"site": "FR13", "variante": "/BCP02"})

    def test_une_valeur_JSONL_doit_etre_une_chaine(self):
        """Le chemin JSONL ne convertissait ni ne verifiait rien.

        Le chemin CSV rend toujours du texte — un CSV n'a pas de types. Le
        JSONL gardait le type JSON jusqu'au `str()` du moteur, si bien que la
        barriere etait posee du cote qu'on ecrit a la main et grande ouverte
        du cote qui vient de l'ERP. Mesure de bout en bout avant correction :

            "site": null -> « None » tape dans le champ SAP
            "site": 1.50 -> « 1.5 », le cadrage perdu
            "site": true -> « True »
        """
        for brut in (b'{"site":null}\n', b'{"site":1.50}\n',
                     b'{"site":true}\n', b'{"site":12}\n'):
            with self.subTest(valeur=brut):
                with self.assertRaises(JeuInvalide) as capture:
                    lire(self._poser("j.jsonl", brut))
                self.assertIn("CHAINE", str(capture.exception))

    def test_une_clef_JSON_ecrite_deux_fois_est_refusee(self):
        """`json.loads` garde la DERNIERE, comme PyYAML et comme DictReader
        sur deux colonnes homonymes. Les deux autres etaient deja refuses."""
        with self.assertRaises(JeuInvalide) as capture:
            lire(self._poser("j.jsonl", b'{"site":"FR12","site":"FR13"}\n'))
        self.assertIn("deux fois", str(capture.exception))

    def test_une_ligne_JSONL_doit_etre_un_objet(self):
        with self.assertRaises(JeuInvalide) as capture:
            lire(self._poser("j.jsonl", b'["FR12"]\n'))
        self.assertIn("OBJET", str(capture.exception))

    def test_jsonl_heterogene_garde_l_absence(self):
        """L'absence porte du sens et n'est PAS comblee par une chaine vide :
        « ne touche pas a ce champ » n'est pas « vide ce champ »."""
        lignes, dialecte = lire(self._poser(
            "j.jsonl", b'{"site":"FR12","variante":"B"}\n{"site":"FR13"}\n'))
        self.assertEqual(dialecte.colonnes, ("site", "variante"))
        self.assertNotIn("variante", lignes[1])

    def test_colonne_dupliquee_refusee(self):
        """Constat de revue : DictReader garde la DERNIERE valeur, donc la
        premiere colonne homonyme etait perdue et remplacee par la seconde —
        dans les deux positions au reexport. Sur un export SE16N avec deux
        colonnes de meme nom, c'est une reinjection de valeurs fausses."""
        chemin = self._poser("j.csv", b"site,site,variante\nFR12,FR13,BCP\n")
        with self.assertRaises(JeuInvalide) as capture:
            lire(chemin)
        self.assertIn("double", str(capture.exception))

    def test_ligne_plus_longue_que_l_entete_refusee(self):
        """Le surplus etait jete sans erreur : perte pure."""
        chemin = self._poser("j.csv", b"a,b\n1,2,3\n")
        with self.assertRaises(JeuInvalide):
            lire(chemin)

    def test_ligne_plus_courte_que_l_entete_refusee(self):
        chemin = self._poser("j.csv", b"a,b,c\n1,2\n")
        with self.assertRaises(JeuInvalide):
            lire(chemin)

    def test_colonne_sans_nom_refusee(self):
        chemin = self._poser("j.csv", b"a,,c\n1,2,3\n")
        with self.assertRaises(JeuInvalide):
            lire(chemin)

    def test_octet_indefini_en_cp1252_ne_fait_pas_echouer_la_lecture(self):
        """0x81 n'est pas defini en cp1252 : le repli final est latin-1."""
        lignes, dialecte = lire(self._poser("j.csv", b"site\n\x81\n"))
        self.assertEqual(dialecte.encodage, "latin-1")
        self.assertEqual(len(lignes), 1)

    def test_jeu_absent(self):
        with self.assertRaises(JeuInvalide):
            lire(self.racine / "nexiste_pas.csv")


class TestRegroupement(unittest.TestCase):
    """L'item est l'unite de sauvegarde SAP, pas l'unite de constat."""

    def test_les_lignes_se_groupent_par_clef(self):
        """Trois cents caracteristiques sur quarante classes font quarante
        items, pas trois cents."""
        lignes = [{"classe": "A", "carac": "c1"},
                  {"classe": "A", "carac": "c2"},
                  {"classe": "B", "carac": "c3"}]
        items = grouper(lignes, ["classe"])
        self.assertEqual(len(items), 2)
        self.assertEqual(len(items[0].brut), 2)
        self.assertEqual(items[0].cle, {"classe": "A"})

    def test_l_ordre_d_apparition_est_conserve(self):
        lignes = [{"c": "B"}, {"c": "A"}, {"c": "B"}]
        self.assertEqual([i.cle["c"] for i in grouper(lignes, ["c"])], ["B", "A"])

    def test_l_identifiant_ne_depend_pas_du_rang(self):
        """Un fichier de KO reinjecte n'a plus les memes rangs."""
        avant = grouper([{"c": "X"}, {"c": "Y"}], ["c"])
        apres = grouper([{"c": "Y"}], ["c"])
        self.assertEqual(avant[1].item_id, apres[0].item_id)

    def test_clef_composee(self):
        items = grouper([{"a": "1", "b": "2"}], ["a", "b"])
        self.assertEqual(items[0].item_id, identifiant(["1", "2"]))

    def test_sans_clef_declaree_la_lecture_refuse(self):
        with self.assertRaises(JeuInvalide) as capture:
            grouper([{"c": "X"}], [])
        self.assertIn("clef", str(capture.exception))

    def test_colonne_de_clef_absente_du_jeu(self):
        with self.assertRaises(JeuInvalide):
            grouper([{"c": "X"}], ["autre"])


class TestAllerRetourKO(unittest.TestCase):
    """L'exigence principale : le fichier de KO est reinjectable tel quel."""

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.racine = Path(self.dossier.name)
        self.addCleanup(self.dossier.cleanup)

    def _cycle(self, contenu: bytes, nom: str, cles: list[str]):
        origine = self.racine / nom
        origine.write_bytes(contenu)
        items, dialecte = lire_items(origine, cles)

        diagnostics = {i.item_id: {"falcon_categorie": "connue_fautive",
                                   "falcon_entree": "relecture_divergente",
                                   "falcon_message": "la valeur n'a pas pris"}
                       for i in items}
        ko = ecrire_items(self.racine / f"ko_{nom}", items, dialecte, diagnostics)
        return origine, ko, items, dialecte

    def test_le_contenu_survit_a_l_aller_retour(self):
        origine, ko, items, _ = self._cycle(
            b"site,variante\nFR12,/BCP01\nFR13,/BCP02\n", "j.csv", ["site"])
        relus, dialecte = lire_items(ko, ["site"])
        self.assertEqual([i.brut for i in relus], [i.brut for i in items])
        self.assertEqual(dialecte.colonnes, ("site", "variante"))

    def test_le_fichier_de_ko_porte_le_diagnostic(self):
        _, ko, _, _ = self._cycle(b"site\nFR12\n", "j.csv", ["site"])
        entete = ko.read_text(encoding="utf-8").splitlines()[0]
        for colonne in COLONNES_DIAGNOSTIC:
            self.assertIn(colonne, entete)

    def test_le_fichier_de_ko_est_identique_a_l_origine_sans_diagnostic(self):
        """Enrichi pour l'humain ET reinjectable : les deux a la fois."""
        contenu = b"site,variante\nFR12,/BCP01\nFR13,/BCP02\n"
        origine, ko, _, _ = self._cycle(contenu, "j.csv", ["site"])
        lignes_origine, dialecte = lire(origine)
        lignes_ko, _ = lire(ko)
        self.assertEqual(lignes_ko, lignes_origine)

        # ... et octet pour octet une fois le diagnostic retire.
        items, _ = lire_items(ko, ["site"])
        remis = ecrire_items(self.racine / "remis.csv", items, dialecte)
        self.assertEqual(remis.read_bytes(), contenu)

    def test_le_dialecte_est_respecte(self):
        contenu = "site;variante\r\nFR12;/BCP01\r\n".encode("utf-8-sig")
        origine, ko, _, _ = self._cycle(contenu, "j.csv", ["site"])
        brut = ko.read_bytes()
        self.assertTrue(brut.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b";", brut)
        self.assertIn(b"\r\n", brut)

    def test_un_item_groupe_rend_toutes_ses_lignes(self):
        """C'est le jeu d'origine qu'on reconstitue, pas un resume."""
        _, ko, _, _ = self._cycle(
            b"classe,carac\nA,c1\nA,c2\nB,c3\n", "j.csv", ["classe"])
        lignes, _ = lire(ko)
        self.assertEqual(len(lignes), 3)

    def test_aller_retour_jsonl(self):
        _, ko, items, _ = self._cycle(
            b'{"site":"FR12"}\n{"site":"FR13"}\n', "j.jsonl", ["site"])
        relus, _ = lire_items(ko, ["site"])
        self.assertEqual([i.brut for i in relus], [i.brut for i in items])

    def test_une_clef_absente_en_jsonl_le_reste(self):
        """Constat de revue : combler les trous par une chaine vide
        transformait « ne touche pas a ce champ » en « vide ce champ ». Pour
        une injection SAP, ce ne sont pas les memes instructions."""
        _, ko, _, _ = self._cycle(
            b'{"site":"FR12","variante":"B"}\n{"site":"FR13"}\n',
            "j.jsonl", ["site"])
        secondes = [ligne for ligne in ko.read_text(encoding="utf-8").splitlines()
                    if "FR13" in ligne]
        self.assertNotIn("variante", secondes[0])

    def test_le_compte_de_sauvegardes_accompagne_le_ko(self):
        """Constat de revue : l'humain qui relance un fichier de KO n'avait
        aucun moyen de savoir que l'item avait DEJA ecrit dans SAP."""
        self.assertIn("falcon_sauvegardes", COLONNES_DIAGNOSTIC)

    def test_l_empreinte_du_jeu_ignore_les_FINS_DE_LIGNE(self):
        """Les deux empreintes que la reprise compare doivent poser la MEME
        question : « FALCON lirait-il la meme chose ? »

        Elles n'y repondaient pas de la meme facon. Celle de la pipeline passe
        par `read_text`, donc par les fins de ligne universelles ; celle-ci
        hachait les octets. Ouvrir le jeu dans un editeur Windows et
        l'enregistrer — le geste le plus banal du poste vise — suffisait donc
        a interdire la reprise d'un lot interrompu, sur une donnee INCHANGEE.
        Et le contournement que `preparer` decrit n'etait atteignable depuis
        aucune commande.
        """
        lf = self.racine / "lf.csv"; lf.write_bytes(b"site\nFR12\nFR13\n")
        crlf = self.racine / "crlf.csv"; crlf.write_bytes(b"site\r\nFR12\r\nFR13\r\n")
        self.assertEqual(empreinte_jeu(lf), empreinte_jeu(crlf))

    def test_l_empreinte_du_jeu_change_avec_le_contenu(self):
        """Base de la garde de reprise."""
        a = self.racine / "a.csv"; a.write_bytes(b"site\nFR12\n")
        b = self.racine / "b.csv"; b.write_bytes(b"site\nFR13\n")
        self.assertNotEqual(empreinte_jeu(a), empreinte_jeu(b))


class TestRapport(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.chemin = Path(self.dossier.name) / "journal.jsonl"
        self.addCleanup(self.dossier.cleanup)

    def _journal(self, *enregistrements):
        with Ecrivain(self.chemin, horloge=horloge_figee("T")) as journal:
            for enregistrement in enregistrements:
                journal.ecrire(enregistrement)
        from falcon.journal import lire as lire_journal
        return lire_journal(self.chemin)

    def test_compteurs_replies_depuis_le_journal(self):
        enregistrements = self._journal(
            ExecutionDebut(run_id=RUN, mode="run", classe="iterative",
                           pipeline="bcp", pipeline_empreinte="p",
                           systeme="K75", mandant="210"),
            ItemDebut(run_id=RUN, item_id="a1"),
            ItemFin(run_id=RUN, item_id="a1", etat="ok"),
            ItemDebut(run_id=RUN, item_id="a2"),
            ItemFin(run_id=RUN, item_id="a2", etat="ko",
                    incident="relecture_divergente"),
            ExecutionFin(run_id=RUN, etat="termine", duree_ms=4200),
        )
        rapport = depuis_journal(enregistrements)
        self.assertEqual(rapport.compteurs, {"ko": 1, "ok": 1})
        self.assertEqual(rapport.incidents, {"relecture_divergente": 1})
        self.assertEqual(rapport.pipeline, "bcp")
        self.assertEqual(rapport.systeme, "K75")

    def test_les_douteux_sont_signales(self):
        enregistrements = self._journal(
            ItemDebut(run_id=RUN, item_id="a1"),
            Etape(run_id=RUN, etape="valider", item_id="a1", sauvegarde=True),
        )
        rapport = depuis_journal(enregistrements)
        self.assertEqual(rapport.douteux, ["a1"])
        self.assertIn("double ecriture", rendre(rapport))

    def test_les_derogations_sont_repetees_a_chaque_execution(self):
        """Une garde assouplie doit rester visible."""
        enregistrements = self._journal(
            Garde(run_id=RUN, garde="relecture", verdict="derogee",
                  derogation={"motif": "editeur non adressable"}),
        )
        rapport = depuis_journal(enregistrements)
        self.assertEqual(len(rapport.derogations), 1)
        self.assertIn("editeur non adressable", rendre(rapport))

    def test_la_provenance_et_la_duree_viennent_du_meme_run(self):
        """Constat de revue : le journal etant partage entre executions,
        prendre la premiere ouverture avec la derniere cloture affichait la
        provenance d'un run et la duree d'un autre."""
        enregistrements = self._journal(
            ExecutionDebut(run_id="r1", mode="run", classe="iterative",
                           pipeline="ancienne", pipeline_empreinte="p",
                           systeme="K75"),
            ExecutionFin(run_id="r1", etat="interrompu", duree_ms=100),
            ExecutionDebut(run_id="r2", mode="resume", classe="iterative",
                           pipeline="courante", pipeline_empreinte="p",
                           systeme="P75"),
            ExecutionFin(run_id="r2", etat="termine", duree_ms=4200),
        )
        rapport = depuis_journal(enregistrements)
        self.assertEqual(rapport.pipeline, "courante")
        self.assertEqual(rapport.systeme, "P75")
        self.assertEqual(rapport.duree_ms, 4200)

    def test_un_journal_vide_ne_fait_pas_echouer_le_rapport(self):
        self.assertIn("aucun", rendre(depuis_journal([])))


if __name__ == "__main__":
    unittest.main()
