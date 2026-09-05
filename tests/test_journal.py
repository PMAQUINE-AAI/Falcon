"""Journal : schema, ecriture append-only, relecture, repli, reprise.

Le journal porte la reprise. Une erreur ici ne se voit pas : elle se traduit
par un item retraite — donc une double ecriture dans SAP — ou par un item
saute. Les deux sont silencieux. D'ou le niveau de detail de ces tests.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from falcon.journal import (
    DOUTEUX, EN_COURS, KO, OK, Ecrivain, Etape, ExecutionDebut, ExecutionFin,
    Garde, Incident, ItemDebut, ItemFin, depuis_dict, etats, lire, preparer,
)
from falcon.noyau import JournalCorrompu, RepriseIncoherente, horloge_figee

RUN = "r-2026-09-03T12-00-00Z-aaaa"


def _ouverture(**extra) -> ExecutionDebut:
    defauts = dict(run_id=RUN, mode="run", classe="iterative",
                   pipeline="bcp_ia08", pipeline_empreinte="pipe1",
                   jeu="sites.csv", jeu_empreinte="jeu1")
    return ExecutionDebut(**{**defauts, **extra})


class TestSchema(unittest.TestCase):

    def test_aller_retour_de_chaque_type(self):
        exemples = [
            _ouverture(),
            ItemDebut(run_id=RUN, item_id="a1", index=3,
                      cle={"site": "FR12"}, brut=[{"site": "FR12"}]),
            Etape(run_id=RUN, etape="saisir", rang=1, action="write",
                  cible="wnd[0]/usr/ctxtWERKS-LOW", valeur="FR12",
                  sauvegarde=False, item_id="a1",
                  ecran={"transaction": "IA08", "dynpro": "1000"},
                  relecture={"attendu": "FR12", "lu": "FR12",
                             "verdict": "conforme"}),
            Garde(run_id=RUN, garde="relecture", verdict="derogee",
                  item_id="a1", derogation={"motif": "editeur non adressable"}),
            Incident(run_id=RUN, categorie="inconnue", bloquant=True,
                     signature={"canal": "statut", "type": "E"}),
            ItemFin(run_id=RUN, item_id="a1", etat=OK, sauvegardes=1),
            ExecutionFin(run_id=RUN, etat="termine",
                         compteurs={"ok": 1, "ko": 0}),
        ]
        for original in exemples:
            with self.subTest(type=type(original).__name__):
                refait = depuis_dict(json.loads(json.dumps(original.vers_dict())))
                self.assertEqual(refait, original)

    def test_l_entete_est_en_tete(self):
        clefs = list(_ouverture().vers_dict())
        self.assertEqual(clefs[:4], ["v", "type", "horodatage", "run_id"])

    def test_type_inconnu_refuse(self):
        with self.assertRaises(JournalCorrompu):
            depuis_dict({"v": 1, "type": "chose", "run_id": RUN})

    def test_version_inattendue_refusee(self):
        """Un journal d'une autre version de FALCON ne se reprend pas."""
        donnees = _ouverture().vers_dict()
        donnees["v"] = 99
        with self.assertRaises(JournalCorrompu):
            depuis_dict(donnees)

    def test_cle_inconnue_refusee(self):
        donnees = _ouverture().vers_dict()
        donnees["surprise"] = 1
        with self.assertRaises(JournalCorrompu):
            depuis_dict(donnees)


class TestEcriture(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.chemin = Path(self.dossier.name) / "sorties" / "journal.jsonl"
        self.addCleanup(self.dossier.cleanup)

    def test_cree_les_dossiers_parents(self):
        with Ecrivain(self.chemin) as journal:
            journal.ecrire(_ouverture())
        self.assertTrue(self.chemin.exists())

    def test_ajoute_sans_ecraser(self):
        """Deux executions ecrivent dans le meme fichier : c'est ce qui rend
        la reprise possible."""
        with Ecrivain(self.chemin) as journal:
            journal.ecrire(_ouverture())
        with Ecrivain(self.chemin) as journal:
            journal.ecrire(ItemDebut(run_id=RUN, item_id="a1"))
        self.assertEqual(len(lire(self.chemin)), 2)

    def test_horodatage_pose_si_absent_conserve_sinon(self):
        with Ecrivain(self.chemin, horloge=horloge_figee("T1", "T2")) as journal:
            premier = journal.ecrire(_ouverture())
            second = journal.ecrire(
                ItemDebut(run_id=RUN, item_id="a1", horodatage="DEJA"))
        self.assertEqual(premier.horodatage, "T1")
        self.assertEqual(second.horodatage, "DEJA")

    def test_ligne_poussee_sur_le_disque_avant_fermeture(self):
        """Un journal qui perd ses dernieres lignes est inutile au moment
        precis ou il servirait."""
        with Ecrivain(self.chemin) as journal:
            journal.ecrire(_ouverture())
            self.assertEqual(len(lire(self.chemin)), 1)   # lu sans fermer

    def test_ecrire_hors_contexte_leve(self):
        with self.assertRaises(RuntimeError):
            Ecrivain(self.chemin).ecrire(_ouverture())


class TestRelecture(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.chemin = Path(self.dossier.name) / "journal.jsonl"
        self.addCleanup(self.dossier.cleanup)

    def _poser(self, texte: str) -> None:
        self.chemin.write_text(texte, encoding="utf-8")

    def test_journal_absent_rend_une_liste_vide(self):
        self.assertEqual(lire(self.chemin), [])

    def test_derniere_ligne_tronquee_toleree(self):
        """Signature d'une coupure pendant l'ecriture : l'evenement perdu est
        celui qu'on allait ecrire."""
        entiere = json.dumps(_ouverture().date("T1").vers_dict())
        self._poser(entiere + "\n" + '{"v":1,"type":"item_deb')
        relus = lire(self.chemin)
        self.assertEqual(len(relus), 1)

    def test_ligne_tronquee_au_milieu_refusee(self):
        """La, le fichier ne dit plus ce qui a ete fait."""
        entiere = json.dumps(_ouverture().date("T1").vers_dict())
        self._poser('{"v":1,"type":"item_deb' + "\n" + entiere + "\n")
        with self.assertRaises(JournalCorrompu) as capture:
            lire(self.chemin)
        self.assertIn("ligne 1", str(capture.exception))

    def test_lignes_vides_ignorees(self):
        entiere = json.dumps(_ouverture().date("T1").vers_dict())
        self._poser(entiere + "\n\n" + entiere + "\n")
        self.assertEqual(len(lire(self.chemin)), 2)


class TestRepli(unittest.TestCase):
    """Le dernier enregistrement fait foi."""

    def test_item_ferme_prend_son_etat_final(self):
        connus = etats([ItemDebut(run_id=RUN, item_id="a1"),
                        ItemFin(run_id=RUN, item_id="a1", etat=OK)])
        self.assertEqual(connus["a1"].etat, OK)

    def test_le_dernier_etat_gagne(self):
        connus = etats([ItemDebut(run_id=RUN, item_id="a1"),
                        ItemFin(run_id=RUN, item_id="a1", etat=KO),
                        ItemDebut(run_id=RUN, item_id="a1"),
                        ItemFin(run_id=RUN, item_id="a1", etat=OK)])
        self.assertEqual(connus["a1"].etat, OK)

    def test_item_ouvert_sans_fin_est_en_cours(self):
        connus = etats([ItemDebut(run_id=RUN, item_id="a1")])
        self.assertEqual(connus["a1"].etat, EN_COURS)

    def test_interruption_apres_sauvegarde_devient_douteux(self):
        """SAP a peut-etre enregistre : rejouer serait la double ecriture."""
        connus = etats([
            ItemDebut(run_id=RUN, item_id="a1"),
            Etape(run_id=RUN, etape="valider", item_id="a1", sauvegarde=True),
        ])
        self.assertEqual(connus["a1"].etat, DOUTEUX)
        self.assertEqual(connus["a1"].sauvegardes, 1)

    def test_une_sauvegarde_sans_item_id_est_rattachee_a_l_item_ouvert(self):
        """Constat de revue : `Etape.item_id` est facultatif, et son oubli
        faisait basculer l'item de « jamais rejoue » a « rejoue » — donc vers
        une double ecriture. Le defaut du schema penchait du mauvais cote."""
        connus = etats([
            ItemDebut(run_id=RUN, item_id="a1"),
            Etape(run_id=RUN, etape="valider", sauvegarde=True),   # sans item_id
        ])
        self.assertEqual(connus["a1"].etat, DOUTEUX)

    def test_une_sauvegarde_hors_de_tout_item_n_est_rattachee_a_rien(self):
        """Une pipeline volumique n'a pas d'items : rien a rattacher."""
        connus = etats([
            ItemDebut(run_id=RUN, item_id="a1"),
            ItemFin(run_id=RUN, item_id="a1", etat=OK),
            Etape(run_id=RUN, etape="exporter", sauvegarde=True),
        ])
        self.assertEqual(connus["a1"].etat, OK)
        self.assertEqual(connus["a1"].sauvegardes, 0)

    def test_sauvegarde_puis_fin_normale_reste_ok(self):
        """Le doute ne porte que sur l'interruption, pas sur la sauvegarde."""
        connus = etats([
            ItemDebut(run_id=RUN, item_id="a1"),
            Etape(run_id=RUN, etape="valider", item_id="a1", sauvegarde=True),
            ItemFin(run_id=RUN, item_id="a1", etat=OK, sauvegardes=1),
        ])
        self.assertEqual(connus["a1"].etat, OK)

    def test_nouvelle_tentative_rouvre_l_item(self):
        connus = etats([ItemDebut(run_id=RUN, item_id="a1"),
                        ItemFin(run_id=RUN, item_id="a1", etat=KO),
                        ItemDebut(run_id=RUN, item_id="a1")])
        self.assertEqual(connus["a1"].etat, EN_COURS)


class TestReprise(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.chemin = Path(self.dossier.name) / "journal.jsonl"
        self.addCleanup(self.dossier.cleanup)

    def _journal(self, *enregistrements) -> None:
        with Ecrivain(self.chemin, horloge=horloge_figee("T")) as journal:
            for enregistrement in enregistrements:
                journal.ecrire(enregistrement)

    def test_les_empreintes_sont_obligatoires(self):
        """Constat de revue : elles valaient « » par defaut et la comparaison
        etait gardee par un `if`, si bien qu'un appel distrait ne verifiait
        rien. La garde la plus severe s'obtenait a l'envers, par omission."""
        with self.assertRaises(TypeError):
            preparer(self.chemin, ["a1"])           # type: ignore[call-arg]

    def test_journal_absent_tout_est_a_traiter(self):
        reprise = preparer(self.chemin, ["a1", "a2"],
                           pipeline_empreinte="pipe1", jeu_empreinte="jeu1")
        self.assertEqual(reprise.a_traiter, ("a1", "a2"))

    def test_les_items_termines_ne_sont_pas_repris(self):
        self._journal(_ouverture(),
                      ItemDebut(run_id=RUN, item_id="a1"),
                      ItemFin(run_id=RUN, item_id="a1", etat=OK))
        reprise = preparer(self.chemin, ["a1", "a2", "a3"],
                           pipeline_empreinte="pipe1", jeu_empreinte="jeu1")
        self.assertEqual(reprise.a_traiter, ("a2", "a3"))

    def test_un_ko_n_est_pas_rejoue_par_la_reprise(self):
        """Il repasse par le fichier de KO reinjecte, pas par la reprise :
        sinon l'humain ne sait plus lequel des deux il execute."""
        self._journal(_ouverture(),
                      ItemDebut(run_id=RUN, item_id="a1"),
                      ItemFin(run_id=RUN, item_id="a1", etat=KO))
        self.assertEqual(
            preparer(self.chemin, ["a1", "a2"], pipeline_empreinte="pipe1",
                     jeu_empreinte="jeu1").a_traiter, ("a2",))

    def test_les_douteux_sont_ecartes_et_listes(self):
        self._journal(_ouverture(),
                      ItemDebut(run_id=RUN, item_id="a1"),
                      Etape(run_id=RUN, etape="valider", item_id="a1",
                            sauvegarde=True))
        reprise = preparer(self.chemin, ["a1", "a2"],
                           pipeline_empreinte="pipe1", jeu_empreinte="jeu1")
        self.assertEqual(reprise.a_traiter, ("a2",))
        self.assertEqual(reprise.douteux, ("a1",))

    def test_un_item_interrompu_sans_sauvegarde_est_repris(self):
        self._journal(_ouverture(), ItemDebut(run_id=RUN, item_id="a1"))
        self.assertEqual(
            preparer(self.chemin, ["a1"], pipeline_empreinte="pipe1",
                     jeu_empreinte="jeu1").a_traiter, ("a1",))

    def test_jeu_modifie_refuse_la_reprise(self):
        """Garde d'identite appliquee a la reprise : reprendre sur un jeu
        modifie, c'est avoir un modele du monde faux."""
        self._journal(_ouverture())
        with self.assertRaises(RepriseIncoherente):
            preparer(self.chemin, ["a1"], pipeline_empreinte="pipe1",
                     jeu_empreinte="AUTRE")

    def test_pipeline_modifiee_refuse_la_reprise(self):
        self._journal(_ouverture())
        with self.assertRaises(RepriseIncoherente):
            preparer(self.chemin, ["a1"], pipeline_empreinte="AUTRE",
                     jeu_empreinte="jeu1")

    def test_empreintes_identiques_acceptent_la_reprise(self):
        self._journal(_ouverture())
        reprise = preparer(self.chemin, ["a1"],
                           pipeline_empreinte="pipe1", jeu_empreinte="jeu1")
        self.assertEqual(reprise.a_traiter, ("a1",))

    def test_forcer_exige_un_motif(self):
        self._journal(_ouverture())
        with self.assertRaises(ValueError):
            preparer(self.chemin, ["a1"], pipeline_empreinte="pipe1",
                     jeu_empreinte="AUTRE", forcer=True)

    def test_forcer_avec_motif_passe(self):
        self._journal(_ouverture())
        reprise = preparer(self.chemin, ["a1"], pipeline_empreinte="pipe1",
                           jeu_empreinte="AUTRE", forcer=True,
                           motif="lignes deja traitees retirees")
        self.assertEqual(reprise.a_traiter, ("a1",))

    def test_le_refus_de_reprise_est_bloquant(self):
        """Il ne doit pas etre rattrapable par un repli."""
        from falcon.noyau import ArretBloquant, Echec
        self.assertTrue(issubclass(RepriseIncoherente, ArretBloquant))
        self.assertFalse(issubclass(RepriseIncoherente, Echec))


if __name__ == "__main__":
    unittest.main()
