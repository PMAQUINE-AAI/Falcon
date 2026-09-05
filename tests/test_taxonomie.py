"""Taxonomie : chargement strict, appariement, et inconnu bloquant.

Le point sensible n'est pas l'appariement — c'est qu'il n'existe aucun moyen
de rendre l'inconnu inoffensif. Une bonne partie de ces tests verifie des
ABSENCES : pas de reglage permissif, pas de joker, pas de categorie
attrape-tout. Ce sont les portes qu'on serait tente d'ouvrir un vendredi soir.
"""

from __future__ import annotations

import inspect
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from falcon.taxonomie import (
    ARRET, BENIGNE, CHEMIN_REGISTRE_DEFAUT, FAUTIVE, INCONNUE, Politique,
    Registre, RegistreInvalide, Signature, Verdict, ecrire_dump,
)
from falcon.noyau import horloge_figee


def _ecrire(dossier: Path, texte: str, nom: str = "r.yaml") -> Path:
    chemin = dossier / nom
    chemin.write_text(textwrap.dedent(texte), encoding="utf-8")
    return chemin


ENTREE_MINIMALE = """
    version: 1
    entrees:
      - nom: exemple
        categorie: connue_benigne
        canal: statut
        correspondance: {id: CP, numero: "045"}
        politique: {poursuivre: true}
        origine: falcon_observe
        justification: une raison
    """


class TestInconnuBloquant(unittest.TestCase):
    """« L'inconnu est un resultat de premiere classe, pas un except
    fourre-tout. »"""

    def setUp(self):
        self.registre = Registre.charger()

    def test_signature_non_appariee_donne_inconnue(self):
        verdict = self.registre.classer(
            Signature(canal="statut", type="E", id="ZZ", numero="999"))
        self.assertEqual(verdict.categorie, INCONNUE)
        self.assertIsNone(verdict.entree)

    def test_l_inconnu_est_bloquant(self):
        verdict = self.registre.classer(
            Signature(canal="statut", type="E", id="ZZ", numero="999"))
        self.assertTrue(verdict.bloquant)
        self.assertTrue(verdict.inconnu)

    def test_aucun_reglage_ne_permet_d_assouplir_le_defaut(self):
        """Il ne doit pas exister d'interrupteur a trouver."""
        parametres = set(inspect.signature(Registre.__init__).parameters)
        for interdit in ("defaut", "strict", "permissif", "tolerant",
                         "categorie_par_defaut", "ignorer_inconnus"):
            self.assertNotIn(interdit, parametres)
        self.assertEqual(parametres, {"self", "entrees"})

    def test_le_bloquant_derive_de_la_politique(self):
        """Les deux ne peuvent pas se contredire : bloquant est calcule."""
        self.assertTrue(Verdict(INCONNUE, ARRET).bloquant)
        self.assertFalse(
            Verdict(BENIGNE, Politique(poursuivre=True)).bloquant)


class TestChargementStrict(unittest.TestCase):
    """Tout ce qui cloche doit tomber au chargement, pas en pleine execution."""

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.racine = Path(self.dossier.name)
        self.addCleanup(self.dossier.cleanup)

    def _charger(self, texte: str) -> Registre:
        return Registre.charger(_ecrire(self.racine, texte))

    def test_registre_valide_se_charge(self):
        self.assertEqual(len(self._charger(ENTREE_MINIMALE)), 1)

    def test_joker_refuse(self):
        """Une entree attrape-tout ferait passer l'inconnu pour du connu."""
        with self.assertRaises(RegistreInvalide) as capture:
            self._charger("""
                version: 1
                entrees:
                  - nom: fourre_tout
                    categorie: connue_benigne
                    canal: statut
                    correspondance: {id: "*", numero: "045"}
                    politique: {poursuivre: true}
                    origine: conjecture
                    justification: une raison
                """)
        self.assertIn("joker", str(capture.exception))

    def test_categorie_inconnue_ne_se_declare_pas(self):
        with self.assertRaises(RegistreInvalide):
            self._charger(ENTREE_MINIMALE.replace(
                "connue_benigne", "inconnue"))

    def test_categorie_hors_liste_refusee(self):
        with self.assertRaises(RegistreInvalide):
            self._charger(ENTREE_MINIMALE.replace(
                "connue_benigne", "pas_grave"))

    def test_canal_inconnu_refuse(self):
        with self.assertRaises(RegistreInvalide):
            self._charger(ENTREE_MINIMALE.replace(
                "canal: statut", "canal: telepathie"))

    def test_justification_exigee(self):
        """Rendre un incident non bloquant demande de dire pourquoi."""
        with self.assertRaises(RegistreInvalide):
            self._charger(
                ENTREE_MINIMALE.replace("        justification: une raison\n", ""))

    def test_origine_exigee(self):
        with self.assertRaises(RegistreInvalide):
            self._charger(
                ENTREE_MINIMALE.replace("        origine: falcon_observe\n", ""))

    def test_entree_sans_nom_refusee(self):
        with self.assertRaises(RegistreInvalide):
            self._charger(ENTREE_MINIMALE.replace("nom: exemple", "libelle: x"))

    def test_fichier_absent_refuse(self):
        with self.assertRaises(RegistreInvalide):
            Registre.charger(self.racine / "nexiste_pas.yaml")

    def test_ambiguite_detectee_au_chargement(self):
        """Deux politiques departagees au hasard, c'est pire que pas de regle."""
        with self.assertRaises(RegistreInvalide) as capture:
            self._charger("""
                version: 1
                entrees:
                  - nom: premiere
                    categorie: connue_benigne
                    canal: statut
                    correspondance: {id: CP, numero: "045"}
                    politique: {poursuivre: true}
                    origine: falcon_observe
                    justification: une raison
                  - nom: seconde
                    categorie: connue_fautive
                    canal: statut
                    correspondance: {id: CP, numero: "0045"}
                    politique: {poursuivre: true, item: ko}
                    origine: falcon_observe
                    justification: une autre raison
                """)
        self.assertIn("meme signature", str(capture.exception))

    def test_deux_contextes_simultanement_vrais_sont_ambigus(self):
        """Constat de revue : `{transaction: IA08}` et `{dynpro: "1000"}` sont
        tous deux vrais sur l'ecran de selection de IA08. Aucun ne contient
        l'autre, donc l'ordre du fichier decidait de la politique — et
        intervertir deux blocs de YAML changeait le comportement, sans erreur."""
        with self.assertRaises(RegistreInvalide):
            self._charger("""
                version: 1
                entrees:
                  - nom: benigne_sur_ia08
                    categorie: connue_benigne
                    canal: statut
                    correspondance:
                      id: CP
                      numero: "045"
                      contexte: {transaction: IA08}
                    politique: {poursuivre: true}
                    origine: falcon_observe
                    justification: une raison
                  - nom: fautive_sur_dynpro_1000
                    categorie: connue_fautive
                    canal: statut
                    correspondance:
                      id: CP
                      numero: "045"
                      contexte: {dynpro: "1000"}
                    politique: {poursuivre: true, item: ko}
                    origine: falcon_observe
                    justification: une autre raison
                """)

    def test_contextes_qui_se_contredisent_acceptes(self):
        """Ils ne peuvent jamais etre vrais ensemble : rien a departager."""
        registre = self._charger("""
            version: 1
            entrees:
              - nom: sur_ia08
                categorie: connue_benigne
                canal: statut
                correspondance:
                  id: CP
                  numero: "045"
                  contexte: {transaction: IA08}
                politique: {poursuivre: true}
                origine: falcon_observe
                justification: une raison
              - nom: sur_cl02
                categorie: connue_fautive
                canal: statut
                correspondance:
                  id: CP
                  numero: "045"
                  contexte: {transaction: CL02}
                politique: {poursuivre: true, item: ko}
                origine: falcon_observe
                justification: une autre raison
            """)
        self.assertEqual(len(registre), 2)

    def test_une_surcouche_ne_peut_pas_assouplir_le_registre_commun(self):
        """Constat de revue : ajouter un contexte suffisait a rendre
        `session_perdue` non bloquante — sans code, sans motif, sans trace.
        C'etait la porte la plus praticable du dispositif."""
        commun = _ecrire(self.racine, """
            version: 1
            entrees:
              - nom: session_perdue
                categorie: connue_fautive
                canal: com
                correspondance: {exception: SessionPerdue}
                politique: {poursuivre: false, item: ko, arreter_chaine: true}
                origine: eagleloader
                justification: la session ne repond plus
            """, "commun.yaml")
        projet = _ecrire(self.racine, """
            version: 1
            entrees:
              - nom: assouplissement
                categorie: connue_benigne
                canal: com
                correspondance:
                  exception: SessionPerdue
                  contexte: {transaction: IA08}
                politique: {poursuivre: true}
                origine: conjecture
                justification: on a decide que ce cas passe
            """, "projet.yaml")
        with self.assertRaises(RegistreInvalide):
            Registre.charger(commun, projet)

    def test_meme_message_types_disjoints_accepte(self):
        """Le meme message peut etre benin en S et fautif en E."""
        registre = self._charger("""
            version: 1
            entrees:
              - nom: en_succes
                categorie: connue_benigne
                canal: statut
                correspondance: {id: CP, numero: "045", type: [S]}
                politique: {poursuivre: true}
                origine: falcon_observe
                justification: une raison
              - nom: en_erreur
                categorie: connue_fautive
                canal: statut
                correspondance: {id: CP, numero: "045", type: [E]}
                politique: {poursuivre: true, item: ko}
                origine: falcon_observe
                justification: une autre raison
            """)
        self.assertEqual(len(registre), 2)
        self.assertEqual(
            registre.classer(Signature(canal="statut", type="S", id="CP",
                                       numero="045")).entree, "en_succes")
        self.assertEqual(
            registre.classer(Signature(canal="statut", type="E", id="CP",
                                       numero="045")).entree, "en_erreur")


class TestAppariement(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.racine = Path(self.dossier.name)
        self.addCleanup(self.dossier.cleanup)

    def test_le_zero_de_tete_n_empeche_pas_l_appariement(self):
        """SAP rend « 045 » ici et « 45 » la."""
        registre = Registre.charger(_ecrire(self.racine, ENTREE_MINIMALE))
        verdict = registre.classer(
            Signature(canal="statut", type="S", id="CP", numero="45"))
        self.assertEqual(verdict.entree, "exemple")

    def test_entree_contextuelle_bat_entree_globale(self):
        """Une meme erreur peut etre benigne ici et fautive la."""
        registre = Registre.charger(_ecrire(self.racine, """
            version: 1
            entrees:
              - nom: globale
                categorie: connue_benigne
                canal: statut
                correspondance: {id: CP, numero: "045"}
                politique: {poursuivre: true}
                origine: falcon_observe
                justification: une raison
              - nom: sur_ia08
                categorie: connue_fautive
                canal: statut
                correspondance:
                  id: CP
                  numero: "045"
                  contexte: {transaction: IA08}
                politique: {poursuivre: true, item: ko}
                origine: falcon_observe
                justification: une autre raison
            """))
        ailleurs = registre.classer(
            Signature(canal="statut", type="S", id="CP", numero="045",
                      contexte={"transaction": "CL02"}))
        self.assertEqual(ailleurs.entree, "globale")

        sur_place = registre.classer(
            Signature(canal="statut", type="S", id="CP", numero="045",
                      contexte={"transaction": "IA08"}))
        self.assertEqual(sur_place.entree, "sur_ia08")
        self.assertEqual(sur_place.categorie, FAUTIVE)

    def test_canal_different_n_apparie_pas(self):
        registre = Registre.charger(_ecrire(self.racine, ENTREE_MINIMALE))
        verdict = registre.classer(
            Signature(canal="com", id="CP", numero="045"))
        self.assertTrue(verdict.inconnu)

    def test_surcouche_ajoute_sans_retirer(self):
        commun = _ecrire(self.racine, ENTREE_MINIMALE, "commun.yaml")
        projet = _ecrire(self.racine, """
            version: 1
            entrees:
              - nom: propre_au_projet
                categorie: connue_fautive
                canal: garde
                correspondance: {garde: fenetre}
                politique: {poursuivre: true, item: ko}
                origine: falcon_observe
                justification: une raison
            """, "projet.yaml")
        registre = Registre.charger(commun, projet)
        self.assertEqual(len(registre), 2)
        self.assertEqual(
            registre.classer(Signature(canal="statut", type="S", id="CP",
                                       numero="045")).entree, "exemple")


class TestListeBlancheSurEcart(unittest.TestCase):
    """Constat de revue : declarer `statut_attendu` sur une etape tuait la
    liste blanche. Le message benin prenait la branche « ecart », perdait son
    id et son numero, et n'etait plus appariable — le renforcement d'une etape
    produisait son affaiblissement."""

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.racine = Path(self.dossier.name)
        self.addCleanup(self.dossier.cleanup)
        self.registre = Registre.charger(_ecrire(self.racine, """
            version: 1
            entrees:
              - nom: avertissement_benin_connu
                categorie: connue_benigne
                canal: garde
                correspondance:
                  garde: statut
                  attendu: "S"
                  observe: "W"
                  id: CP
                  numero: "042"
                politique: {poursuivre: true}
                origine: falcon_observe
                justification: une raison
            """))

    def test_un_message_connu_reste_apparie_malgre_l_ecart(self):
        verdict = self.registre.classer(
            Signature(canal="garde", garde="statut", attendu="S", observe="W",
                      id="CP", numero="042"))
        self.assertEqual(verdict.entree, "avertissement_benin_connu")
        self.assertFalse(verdict.bloquant)

    def test_un_autre_message_produisant_le_meme_ecart_reste_inconnu(self):
        """L'entree ne doit pas apparier indifferemment tout ce qui produit
        le meme ecart."""
        verdict = self.registre.classer(
            Signature(canal="garde", garde="statut", attendu="S", observe="W",
                      id="ZZ", numero="999"))
        self.assertTrue(verdict.inconnu)
        self.assertTrue(verdict.bloquant)

    def test_deux_ecarts_visant_des_messages_differents_coexistent(self):
        registre = Registre.charger(_ecrire(self.racine, """
            version: 1
            entrees:
              - nom: sur_cp_042
                categorie: connue_benigne
                canal: garde
                correspondance: {garde: statut, attendu: "S", observe: "W", id: CP, numero: "042"}
                politique: {poursuivre: true}
                origine: falcon_observe
                justification: une raison
              - nom: sur_cp_043
                categorie: connue_fautive
                canal: garde
                correspondance: {garde: statut, attendu: "S", observe: "W", id: CP, numero: "043"}
                politique: {poursuivre: true, item: ko}
                origine: falcon_observe
                justification: une autre raison
            """, "deux.yaml"))
        self.assertEqual(len(registre), 2)


class TestRegistreLivre(unittest.TestCase):
    """Le registre livre demarre presque vide — c'est voulu."""

    def setUp(self):
        self.registre = Registre.charger()

    def test_il_se_charge(self):
        self.assertTrue(CHEMIN_REGISTRE_DEFAUT.exists())
        self.assertGreater(len(self.registre), 0)

    def test_il_reste_petit(self):
        """La taxonomie se recolte : l'amorcer a douze entrees serait la
        specification anticipee que le modele de securite proscrit."""
        self.assertLessEqual(len(self.registre), 5)

    def test_chaque_entree_dit_d_ou_elle_vient(self):
        for entree in self.registre.entrees:
            with self.subTest(entree=entree.nom):
                self.assertIn(entree.origine,
                              {"falcon_observe", "eagleloader", "conjecture"})
                self.assertTrue(entree.justification.strip())

    def test_aucune_entree_n_invente_de_message_sap(self):
        """Aucun identifiant de message n'a encore ete observe : les entrees
        livrees portent sur des signaux que FALCON produit lui-meme."""
        for entree in self.registre.entrees:
            with self.subTest(entree=entree.nom):
                self.assertNotIn("id", entree.correspondance)

    def test_la_session_perdue_arrete_la_chaine(self):
        verdict = self.registre.classer(
            Signature(canal="com", exception="SessionPerdue"))
        self.assertEqual(verdict.categorie, FAUTIVE)
        self.assertTrue(verdict.politique.arreter_chaine)
        self.assertEqual(verdict.politique.item, "ko")

    def test_la_relecture_divergente_ne_stoppe_pas_le_lot(self):
        """Un champ qui refuse une valeur ne dit rien des items suivants."""
        verdict = self.registre.classer(
            Signature(canal="garde", garde="relecture"))
        self.assertEqual(verdict.entree, "relecture_divergente")
        self.assertTrue(verdict.politique.poursuivre)
        self.assertEqual(verdict.politique.item, "ko")

    def test_le_silence_de_ia08_est_rattrape(self):
        """Sans case cochee, IA08 ne remonte rien ET n'emet aucun message."""
        verdict = self.registre.classer(
            Signature(canal="garde", garde="statut", attendu="S", observe=""))
        self.assertEqual(verdict.entree, "ia08_selection_vide_sans_message")


class TestDump(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.racine = Path(self.dossier.name)
        self.addCleanup(self.dossier.cleanup)

    def test_ecrit_un_json_relisible(self):
        chemin = ecrire_dump(self.racine / "dumps",
                             {"ecran": {"transaction": "IA08"}},
                             horloge=horloge_figee("2026-09-03T12:00:00.000Z"))
        self.assertTrue(chemin.exists())
        charge = json.loads(chemin.read_text(encoding="utf-8"))
        self.assertEqual(charge["ecran"]["transaction"], "IA08")
        self.assertEqual(charge["horodatage"], "2026-09-03T12:00:00.000Z")

    def test_le_nom_de_fichier_est_utilisable(self):
        """Les deux-points d'un horodatage ISO ne passent pas partout."""
        chemin = ecrire_dump(self.racine / "dumps", {},
                             horloge=horloge_figee("2026-09-03T12:00:00.000Z"))
        self.assertNotIn(":", chemin.name)

    def test_un_objet_non_serialisable_ne_fait_pas_echouer_le_dump(self):
        """Un dump partiel vaut mieux qu'une exception pendant qu'on essaie
        de rendre compte d'un incident."""
        chemin = ecrire_dump(self.racine / "dumps", {"objet": object()})
        self.assertIn("object", chemin.read_text(encoding="utf-8"))

    def test_cree_les_dossiers_parents(self):
        chemin = ecrire_dump(self.racine / "a" / "b" / "c", {})
        self.assertTrue(chemin.parent.is_dir())


if __name__ == "__main__":
    unittest.main()
