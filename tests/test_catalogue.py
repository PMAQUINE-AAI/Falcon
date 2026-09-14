"""Catalogue : variantes d'ecran, depot YAML, quarantaine.

Deux proprietes portent ce lot. Un meme dynpro rendu differemment donne deux
variantes — ne pas traiter cette variabilite est, dit la specification, la
premiere cause d'echec d'un framework de ce type. Et une esquisse ne peut
jamais satisfaire une garde d'identite : elle certifierait un ecran que
personne n'a observe.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from falcon.catalogue import (
    ATTRIBUTS, ESQUISSE, OBSERVEE, CatalogueInvalide, ClefVariante, Depot,
    Variante, clef_de, variante_de,
)
from falcon.noyau import Champ, Ecran, Identite

IA08 = Identite(transaction="IA08", programme="RIPLKO10", dynpro="1000")


def _ecran(*identifiants: str, titre: str = "", identite: Identite = IA08) -> Ecran:
    return Ecran(identite=identite, titre=titre,
                 champs=tuple(Champ(id=i, type="GuiTextField") for i in identifiants),
                 capture_le="2026-09-03T12:00:00.000Z")


class Base(unittest.TestCase):

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self.dossier.cleanup)
        self.depot = Depot(Path(self.dossier.name) / "catalogue")


class TestVariantes(Base):

    def test_deux_rendus_du_meme_dynpro_donnent_deux_variantes(self):
        """Onglets, layouts ALV, parametres utilisateur : le meme dynpro ne
        rend pas toujours les memes champs."""
        self.depot.enregistrer(variante_de(_ecran("a", "b")))
        self.depot.enregistrer(variante_de(_ecran("a", "b", "c")))
        self.assertEqual(len(self.depot.variantes(IA08.triplet)), 2)

    def test_le_meme_rendu_ne_cree_pas_de_doublon(self):
        self.depot.enregistrer(variante_de(_ecran("a", "b")))
        self.depot.enregistrer(variante_de(_ecran("b", "a")))   # meme ensemble
        self.assertEqual(len(self.depot.variantes(IA08.triplet)), 1)

    def test_la_clef_porte_le_triplet_et_l_empreinte(self):
        clef = clef_de(_ecran("a"))
        self.assertEqual(clef.triplet, ("IA08", "RIPLKO10", "1000"))
        self.assertTrue(clef.empreinte)

    def test_deux_dynpros_differents_ne_se_melangent_pas(self):
        autre = Identite(transaction="IA08", programme="RIPLKO10", dynpro="0100")
        self.depot.enregistrer(variante_de(_ecran("a", identite=IA08)))
        self.depot.enregistrer(variante_de(_ecran("a", identite=autre)))
        self.assertEqual(len(self.depot.variantes(IA08.triplet)), 1)
        self.assertEqual(len(self.depot.variantes(autre.triplet)), 1)

    def test_le_dynpro_reste_une_chaine(self):
        """« 0100 » n'est pas « 100 » : le catalogue doit rester diffable."""
        autre = Identite(transaction="X", programme="Y", dynpro="0100")
        self.depot.enregistrer(variante_de(_ecran("a", identite=autre)))
        self.assertEqual(list(self.depot.triplets())[0][2], "0100")


class TestDepotYaml(Base):

    def test_l_aller_retour_conserve_les_champs(self):
        ecran = Ecran(identite=IA08, titre="Selection", capture_le="T",
                      champs=(Champ(id="wnd[0]/usr/ctxtWERKS-LOW",
                                    type="GuiCTextField", soustype="",
                                    nom="WERKS-LOW", texte="1000",
                                    modifiable=True, infobulle="Division"),))
        self.depot.enregistrer(variante_de(ecran))
        relue = self.depot.pour_edition(clef_de(ecran))
        self.assertEqual(relue.champs, ecran.champs)
        self.assertEqual(relue.titre, "Selection")

    def test_les_six_attributs_de_la_specification_sont_stockes(self):
        self.depot.enregistrer(variante_de(_ecran("a")))
        chemin = next(self.depot.racine.glob("*.yaml"))
        contenu = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        champ = next(iter(contenu["variantes"].values()))["champs"][0]
        for attribut in ("id", "type", "nom", "texte", "modifiable", "infobulle"):
            self.assertIn(attribut, champ)

    def test_le_fichier_est_diffable(self):
        """Decision n°1 : YAML versionne, diffable et relisible."""
        self.depot.enregistrer(variante_de(_ecran("a")))
        texte = next(self.depot.racine.glob("*.yaml")).read_text(encoding="utf-8")
        self.assertIn("version: 1", texte)
        self.assertIn("transaction: IA08", texte)

    def test_une_version_inattendue_est_refusee(self):
        self.depot.enregistrer(variante_de(_ecran("a")))
        chemin = next(self.depot.racine.glob("*.yaml"))
        chemin.write_text(chemin.read_text(encoding="utf-8")
                          .replace("version: 1", "version: 99"), encoding="utf-8")
        with self.assertRaises(CatalogueInvalide):
            self.depot.variantes(IA08.triplet)

    def test_un_triplet_absent_rend_un_ensemble_vide(self):
        self.assertEqual(self.depot.variantes(("X", "Y", "0")), ())

    def test_le_nom_de_fichier_supporte_un_triplet_biscornu(self):
        bizarre = Identite(transaction="/N SE16", programme="SAP/LX", dynpro="1")
        self.depot.enregistrer(variante_de(_ecran("a", identite=bizarre)))
        self.assertEqual(len(self.depot.variantes(bizarre.triplet)), 1)

    def test_resolution_par_suffixe(self):
        """Le numero de sous-ecran change avec le type d'objet affiche."""
        self.depot.enregistrer(variante_de(_ecran(
            "wnd[0]/usr/subDET:SAPLCPDO:3300/txtPLPOD-VORNR",
            "wnd[0]/usr/txtAUTRE")))
        variante = self.depot.variantes(IA08.triplet)[0]
        self.assertEqual(len(variante.par_suffixe("txtPLPOD-VORNR")), 1)


class TestEsquisseEtGarde(Base):
    """Une esquisse ne peut jamais certifier un ecran que personne n'a vu."""

    def test_pour_garde_sert_une_variante_observee(self):
        ecran = _ecran("a", titre="Selection")
        self.depot.enregistrer(variante_de(ecran))
        self.assertEqual(self.depot.pour_garde(clef_de(ecran)).titre, "Selection")

    def test_pour_garde_refuse_une_esquisse(self):
        ecran = _ecran("a")
        self.depot.enregistrer(variante_de(ecran, source=ESQUISSE))
        with self.assertRaises(CatalogueInvalide) as capture:
            self.depot.pour_garde(clef_de(ecran))
        self.assertIn("esquisse", str(capture.exception))

    def test_pour_edition_sert_une_esquisse(self):
        """L'humain qui cartographie a besoin de la voir."""
        ecran = _ecran("a")
        self.depot.enregistrer(variante_de(ecran, source=ESQUISSE))
        self.assertEqual(self.depot.pour_edition(clef_de(ecran)).source, ESQUISSE)

    def test_pour_garde_refuse_une_variante_absente(self):
        """Une garde d'identite sans reference n'est pas une garde."""
        with self.assertRaises(CatalogueInvalide) as capture:
            self.depot.pour_garde(ClefVariante("X", "Y", "0", "abcdef"))
        self.assertIn("absente", str(capture.exception))

    def test_une_source_inconnue_est_refusee(self):
        with self.assertRaises(CatalogueInvalide):
            Variante(clef=ClefVariante("X", "Y", "0", "a"), source="devinee")


class TestQuarantaine(Base):
    """Une capture non relue ne pollue pas le catalogue cure."""

    def test_une_capture_va_en_quarantaine_pas_au_catalogue(self):
        ecran = _ecran("a")
        self.depot.mettre_en_quarantaine(variante_de(ecran))
        self.assertEqual(self.depot.variantes(IA08.triplet), ())
        self.assertEqual(
            len(Depot(self.depot.quarantaine).variantes(IA08.triplet)), 1)

    def test_la_promotion_est_un_geste_explicite(self):
        ecran = _ecran("a")
        self.depot.mettre_en_quarantaine(variante_de(ecran))
        self.depot.promouvoir(clef_de(ecran))
        self.assertEqual(self.depot.pour_garde(clef_de(ecran)).clef,
                         clef_de(ecran))

    def test_promouvoir_ce_qui_n_est_pas_en_quarantaine_leve(self):
        with self.assertRaises(CatalogueInvalide):
            self.depot.promouvoir(ClefVariante("X", "Y", "0", "abcdef"))


class TestLEnTeteFaitFoiSurLeNomDeFichier(Base):
    """`variantes(triplet)` passe par `contenu(chemin)` : la clef vient de
    l'EN-TETE du fichier, pas du triplet demande.

    C'est un changement de comportement, et il vaut mieux que l'ancien —
    l'ancien re-etiquetait silencieusement la variante avec le triplet
    demande, donc un fichier renomme a la main ou recopie d'un autre catalogue
    prenait l'identite de son nom de fichier, et la garde d'identite opposait
    ensuite un ecran a un autre. Mais aucun test ne le fixait dans un sens ni
    dans l'autre, et un comportement que rien ne tient n'est pas un
    comportement : c'est ce que le code fait aujourd'hui.

    CONTROLE NEGATIF : re-etiqueter la variante avec le triplet DEMANDE dans
    `variantes()` fait tomber ce test.
    """

    def _fichier_menteur(self) -> Path:
        self.depot.enregistrer(variante_de(_ecran("wnd[0]/usr/a")))
        chemin = self.depot.racine / "IA08__RIPLKO10__1000.yaml"
        contenu = yaml.safe_load(chemin.read_text(encoding="utf-8"))
        contenu["transaction"] = "IW39"
        contenu["programme"] = "SAPLIW39"
        contenu["dynpro"] = "2000"
        chemin.write_text(yaml.safe_dump(contenu, allow_unicode=True),
                          encoding="utf-8")
        return chemin

    def test_la_clef_rendue_est_celle_de_l_en_tete(self):
        self._fichier_menteur()
        variantes = self.depot.variantes(IA08.triplet)
        self.assertEqual(len(variantes), 1)
        self.assertEqual(variantes[0].clef.triplet,
                         ("IW39", "SAPLIW39", "2000"))

    def test_et_l_ecran_demande_devient_alors_INTROUVABLE(self):
        """Le prix du refus, ecrit : `pour_edition` ne trouve plus rien sous
        le triplet demande. Un refus vaut mieux qu'une valeur devinee — mais
        il faut savoir que c'est celui-la."""
        self._fichier_menteur()
        self.assertIsNone(
            self.depot.pour_edition(ClefVariante(*IA08.triplet,
                                                 empreinte="0" * 16)))


if __name__ == "__main__":
    unittest.main()
