"""Export de table : provenance obligatoire, conservation, delta.

Deux proprietes portent ce lot.

**Un export sans provenance complete est refuse a l'ecriture.** Le §3.6 en
fait le contrat minimal vis-a-vis du programme d'analyse tiers : sans systeme,
mandant, table, horodatage et utilisateur, le rapprochement inter-systeme du
cas 3 devient invérifiable. Un export dont on ignore l'origine est pire qu'un
export absent — il a l'air exploitable.

**Le delta rapproche par CLEF DECLAREE, jamais par rang.** Deux exports d'une
meme table n'ont aucune raison de sortir dans le meme ordre ; rapprocher par
rang produirait des modifications imaginaires en masse, c'est-a-dire un audit
recurrent qui crie au loup a chaque execution.

Rien ici ne touche a SAP : ce lot est entierement verifiable hors systeme.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from falcon.donnees import JeuInvalide, lire_items
from falcon.volumique import (
    OBLIGATOIRES, PREFIXE, Delta, DeltaImpossible, Export, ExportInvalide,
    Provenance, chemin_d_export, delta, dernier_export, ecrire_export,
    enregistrer, exports, lire_export, rendre,
)

LIGNES = [{"MATNR": "A", "MAKTX": "Vis"}, {"MATNR": "B", "MAKTX": "Ecrou"}]


def _provenance(**remplacements) -> Provenance:
    champs = dict(systeme="K75", mandant="210", table="MARA",
                  horodatage="2026-09-05T10:00:00.000Z",
                  utilisateur="pmaquine", criteres={"WERKS": "1000"})
    champs.update(remplacements)
    return Provenance(**champs)           # type: ignore[arg-type]


class Base(unittest.TestCase):

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name)


class TestProvenanceObligatoire(Base):

    def test_un_export_complet_s_ecrit(self):
        chemin = ecrire_export(self.racine / "e.jsonl", _provenance(), LIGNES)
        self.assertTrue(chemin.exists())

    def test_chaque_champ_obligatoire_est_exige(self):
        for champ in OBLIGATOIRES:
            with self.subTest(champ=champ):
                with self.assertRaises(ExportInvalide) as capture:
                    ecrire_export(self.racine / "e.jsonl",
                                  _provenance(**{champ: ""}), LIGNES)
                self.assertIn(champ, str(capture.exception))

    def test_des_criteres_vides_sont_licites(self):
        """Un export sans critere est un export de table complete : c'est une
        information, pas une omission."""
        chemin = ecrire_export(self.racine / "e.jsonl",
                               _provenance(criteres={}), LIGNES)
        self.assertEqual(lire_export(chemin).provenance.criteres, {})

    def test_le_refus_precede_l_ecriture(self):
        """Un fichier a moitie ecrit serait pire qu'aucun fichier."""
        chemin = self.racine / "e.jsonl"
        with self.assertRaises(ExportInvalide):
            ecrire_export(chemin, _provenance(systeme=""), LIGNES)
        self.assertFalse(chemin.exists())

    def test_un_fichier_sans_provenance_est_refuse_a_la_lecture(self):
        chemin = self.racine / "nu.jsonl"
        chemin.write_text('{"MATNR": "A"}\n', encoding="utf-8")
        with self.assertRaises(ExportInvalide) as capture:
            lire_export(chemin)
        self.assertIn("pire qu'un export absent", str(capture.exception))

    def test_un_fichier_vide_est_refuse(self):
        chemin = self.racine / "vide.jsonl"
        chemin.write_text("", encoding="utf-8")
        with self.assertRaises(ExportInvalide):
            lire_export(chemin)

    def test_un_champ_de_provenance_inconnu_est_refuse(self):
        chemin = self.racine / "e.jsonl"
        chemin.write_text(
            json.dumps({f"{PREFIXE}systeme": "K75", f"{PREFIXE}surprise": 1})
            + "\n", encoding="utf-8")
        with self.assertRaises(ExportInvalide) as capture:
            lire_export(chemin)
        self.assertIn("surprise", str(capture.exception))


class TestAllerRetour(Base):

    def test_les_lignes_et_la_provenance_survivent(self):
        chemin = ecrire_export(self.racine / "e.jsonl", _provenance(), LIGNES)
        relu = lire_export(chemin)
        self.assertEqual(list(relu.lignes), LIGNES)
        self.assertEqual(relu.provenance.systeme, "K75")
        self.assertEqual(relu.provenance.criteres, {"WERKS": "1000"})
        self.assertEqual(len(relu), 2)

    def test_une_colonne_reservee_dans_les_donnees_est_refusee(self):
        """Elle serait retiree a la relecture, en silence."""
        with self.assertRaises(ExportInvalide) as capture:
            ecrire_export(self.racine / "e.jsonl", _provenance(),
                          [{f"{PREFIXE}triche": "1"}])
        self.assertIn("silence", str(capture.exception))

    def test_un_export_passe_au_lecteur_de_jeux_ne_livre_pas_de_ligne_fantome(self):
        """La provenance ne porte que des clefs prefixees `falcon_`, celles
        que `falcon.donnees` retire. Un export passe par megarde au lecteur de
        jeux y rend une ligne VIDE, que le regroupement refuse aussitot —
        plutot qu'une ligne de donnees fantome glissee dans un lot.
        """
        chemin = ecrire_export(self.racine / "e.jsonl", _provenance(), LIGNES)
        with self.assertRaises(JeuInvalide):
            lire_items(chemin, ("MATNR",))

    def test_une_ligne_de_donnees_illisible_est_situee(self):
        chemin = self.racine / "e.jsonl"
        ecrire_export(chemin, _provenance(), LIGNES)
        chemin.write_text(chemin.read_text(encoding="utf-8") + "{pas du json\n",
                          encoding="utf-8")
        with self.assertRaises(ExportInvalide) as capture:
            lire_export(chemin)
        self.assertIn("ligne 4", str(capture.exception))


class TestConservation(Base):
    """Un dossier par systeme, un fichier horodate par execution."""

    def test_un_dossier_par_systeme(self):
        """Melanger deux systemes rendrait le rapprochement inter-systeme
        dependant d'un nom de fichier bien lu."""
        chemin = chemin_d_export(self.racine, "K75", "MARA", "2026-09-05T10Z")
        self.assertEqual(chemin.parent.name, "K75")
        self.assertIn("MARA", chemin.name)

    def test_les_exports_se_listent_du_plus_ancien_au_plus_recent(self):
        for jour in ("2026-09-03", "2026-09-05", "2026-09-04"):
            enregistrer(self.racine,
                        _provenance(horodatage=f"{jour}T10:00:00.000Z"), LIGNES)
        connus = exports(self.racine, "K75", "MARA")
        self.assertEqual(len(connus), 3)
        self.assertIn("2026-09-05", connus[-1].name)
        self.assertNotIn(":", connus[-1].name)   # interdit sous Windows

    def test_le_tri_porte_sur_le_nom_pas_sur_la_date_du_fichier(self):
        """Une copie ou une restauration change la date du fichier, pas
        l'horodatage inscrit dans son nom."""
        vieux = enregistrer(self.racine,
                            _provenance(horodatage="2026-01-01T10:00:00.000Z"),
                            LIGNES)
        enregistrer(self.racine,
                    _provenance(horodatage="2026-09-05T10:00:00.000Z"), LIGNES)
        vieux.touch()               # comme une restauration le ferait
        self.assertIn("2026-09-05",
                      dernier_export(self.racine, "K75", "MARA").name)

    def test_aucun_export_rend_rien(self):
        self.assertEqual(exports(self.racine, "K75", "MARA"), [])
        self.assertIsNone(dernier_export(self.racine, "K75", "MARA"))

    def test_un_nom_de_table_biscornu_ne_casse_pas_le_chemin(self):
        chemin = chemin_d_export(self.racine, "K/75", "/BCP/TABLE", "2026Z")
        self.assertNotIn("/", chemin.name)
        self.assertEqual(chemin.parent.name, "K_75")

    def test_deux_tables_ne_se_melangent_pas(self):
        enregistrer(self.racine, _provenance(table="MARA"), LIGNES)
        enregistrer(self.racine, _provenance(table="MARC"), LIGNES)
        self.assertEqual(len(exports(self.racine, "K75", "MARA")), 1)
        self.assertEqual(len(exports(self.racine, "K75", "MARC")), 1)


class TestDelta(Base):

    def _export(self, lignes, **remplacements) -> Export:
        return Export(provenance=_provenance(**remplacements),
                      lignes=tuple(lignes))

    def test_ajouts_retraits_et_modifications(self):
        ecart = delta(
            self._export([{"MATNR": "A", "MAKTX": "Vis"},
                          {"MATNR": "B", "MAKTX": "Ecrou"}]),
            self._export([{"MATNR": "A", "MAKTX": "Vis longue"},
                          {"MATNR": "C", "MAKTX": "Rondelle"}]),
            ["MATNR"])
        self.assertEqual([l["MATNR"] for l in ecart.ajoutes], ["C"])
        self.assertEqual([l["MATNR"] for l in ecart.retires], ["B"])
        self.assertEqual(len(ecart.modifies), 1)
        self.assertEqual(ecart.modifies[0].colonnes, ("MAKTX",))
        self.assertEqual(len(ecart), 3)

    def test_l_ordre_des_lignes_ne_produit_aucune_modification(self):
        """La propriete qui justifie la clef declaree : rapprocher par rang
        crierait au loup a chaque execution."""
        ecart = delta(self._export(LIGNES),
                      self._export(list(reversed(LIGNES))), ["MATNR"])
        self.assertTrue(ecart.vide)
        self.assertEqual(ecart.inchanges, 2)

    def test_une_colonne_ajoutee_est_une_modification(self):
        ecart = delta(self._export([{"MATNR": "A"}]),
                      self._export([{"MATNR": "A", "NEUF": "1"}]), ["MATNR"])
        self.assertEqual(ecart.modifies[0].colonnes, ("NEUF",))

    def test_sans_clef_le_rapprochement_est_refuse(self):
        with self.assertRaises(DeltaImpossible) as capture:
            delta(self._export(LIGNES), self._export(LIGNES), [])
        self.assertIn("par rang", str(capture.exception))

    def test_une_clef_absente_d_une_ligne_est_refusee(self):
        with self.assertRaises(DeltaImpossible) as capture:
            delta(self._export([{"AUTRE": "A"}]), self._export(LIGNES),
                  ["MATNR"])
        self.assertIn("clef absente", str(capture.exception))

    def test_deux_lignes_de_meme_clef_sont_refusees(self):
        """Le rapprochement en perdrait une, sans le dire."""
        with self.assertRaises(DeltaImpossible) as capture:
            delta(self._export([{"MATNR": "A", "X": "1"},
                                {"MATNR": "A", "X": "2"}]),
                  self._export(LIGNES), ["MATNR"])
        self.assertIn("meme clef", str(capture.exception))

    def test_deux_tables_differentes_ne_se_comparent_pas(self):
        """Tout serait ajoute et tout serait retire — un resultat qui a l'air
        d'un resultat."""
        with self.assertRaises(DeltaImpossible) as capture:
            delta(self._export(LIGNES, table="MARA"),
                  self._export(LIGNES, table="MARC"), ["MATNR"])
        self.assertIn("MARC", str(capture.exception))

    def test_une_clef_composite_fonctionne(self):
        ecart = delta(
            self._export([{"MATNR": "A", "WERKS": "1000", "X": "1"}]),
            self._export([{"MATNR": "A", "WERKS": "2000", "X": "1"}]),
            ["MATNR", "WERKS"])
        self.assertEqual(len(ecart.ajoutes), 1)
        self.assertEqual(len(ecart.retires), 1)
        self.assertEqual(ecart.modifies, ())


class TestRendu(Base):

    def test_les_modifications_sont_detaillees(self):
        ecart = delta(Export(provenance=_provenance(),
                             lignes=({"MATNR": "A", "MAKTX": "Vis"},)),
                      Export(provenance=_provenance(),
                             lignes=({"MATNR": "A", "MAKTX": "Vis longue"},)),
                      ["MATNR"])
        texte = rendre(ecart)
        self.assertIn("modifies   1", texte)
        self.assertIn("'Vis' -> 'Vis longue'", texte)

    def test_un_delta_vide_le_dit(self):
        ecart = Delta()
        self.assertIn("Rien n'a bouge", rendre(ecart))

    def test_le_rendu_ne_porte_aucune_sequence_ansi(self):
        self.assertNotIn("\x1b", rendre(Delta()))


if __name__ == "__main__":
    unittest.main()
