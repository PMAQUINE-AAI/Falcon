"""Noyau : types de la couture et hierarchie d'erreurs."""

from __future__ import annotations

import unittest

from falcon.noyau import (
    ArretBloquant, Champ, Echec, EcartIdentite, Ecran, Fenetre, Identite,
    ObjetIntrouvable, Refus, RefusDryRun, Statut, empreinte,
)
from falcon.noyau.types import meme_numero


class TestSeparationEchecRefus(unittest.TestCase):
    """« Un repli ne doit jamais avaler un refus. »

    La regle vient du terrain : quand un mecanisme A echoue et qu'on bascule
    sur B, un refus delibere emis par A serait rattrape par la bascule et
    retente par un mecanisme moins sur. Ici elle est portee par le typage,
    pas par la vigilance du relecteur.
    """

    def test_les_deux_branches_sont_disjointes(self):
        self.assertFalse(issubclass(Refus, Echec))
        self.assertFalse(issubclass(Echec, Refus))

    def test_un_repli_ne_rattrape_pas_un_refus(self):
        with self.assertRaises(RefusDryRun):
            try:
                raise RefusDryRun("sauvegarde demandee en dry-run")
            except Echec:                      # le repli typique
                self.fail("le repli a avale un refus")

    def test_un_repli_rattrape_bien_un_echec(self):
        try:
            raise ObjetIntrouvable("wnd[0]/usr/txtABSENT")
        except Echec:
            pass
        else:
            self.fail("l'echec aurait du etre rattrape")

    def test_les_arrets_bloquants_sont_des_refus(self):
        self.assertTrue(issubclass(EcartIdentite, ArretBloquant))
        self.assertTrue(issubclass(ArretBloquant, Refus))


class TestEmpreinte(unittest.TestCase):
    """Clef de variante d'ecran : un meme dynpro ne rend pas toujours les
    memes champs, et ne pas traiter cette variabilite est la premiere cause
    d'echec d'un framework de ce type."""

    def test_insensible_a_l_ordre_et_aux_doublons(self):
        self.assertEqual(empreinte(["b", "a"]), empreinte(["a", "b", "a"]))

    def test_deux_ensembles_differents_donnent_deux_empreintes(self):
        self.assertNotEqual(empreinte(["a", "b"]), empreinte(["a", "c"]))

    def test_stable_entre_deux_appels(self):
        self.assertEqual(empreinte(["x"]), empreinte(["x"]))

    def test_un_champ_de_plus_change_l_empreinte(self):
        """C'est ce qui distingue deux variantes du meme dynpro."""
        self.assertNotEqual(empreinte(["a", "b"]), empreinte(["a", "b", "c"]))


class TestNumerosSAP(unittest.TestCase):

    def test_le_zero_de_tete_est_conserve(self):
        """« 0100 » n'est pas « 100 » : le catalogue doit rester diffable."""
        self.assertEqual(Identite(dynpro="0100").dynpro, "0100")
        self.assertIsInstance(Statut(numero="045").numero, str)

    def test_la_comparaison_ignore_les_zeros_de_tete(self):
        self.assertTrue(meme_numero("045", "45"))
        self.assertFalse(meme_numero("045", "46"))


class TestTypes(unittest.TestCase):

    def test_triplet_d_identite(self):
        identite = Identite(transaction="IA08", programme="RIPLKO10", dynpro="1000")
        self.assertEqual(identite.triplet, ("IA08", "RIPLKO10", "1000"))

    def test_cle_de_statut_et_barre_vide(self):
        self.assertEqual(Statut(type="E", id="CP", numero="045").cle, "CP:045")
        self.assertTrue(Statut().vide)
        self.assertFalse(Statut(type="S").vide)

    def test_resolution_par_suffixe(self):
        """Le numero de sous-ecran figure dans l'identifiant et change avec le
        type d'objet affiche : un chemin fige cesse de resoudre."""
        ecran = Ecran(
            identite=Identite(),
            champs=(
                Champ(id="wnd[0]/usr/subDET:SAPLCPDO:3300/txtPLPOD-VORNR"),
                Champ(id="wnd[0]/usr/subDET:SAPLCPDO:3305/txtPLPOD-VORNR"),
                Champ(id="wnd[0]/usr/txtAUTRE"),
            ))
        trouves = ecran.par_suffixe("txtPLPOD-VORNR")
        self.assertEqual(len(trouves), 2)
        self.assertEqual(ecran.par_suffixe("txtINEXISTANT"), ())

    def test_empreinte_d_ecran(self):
        ecran = Ecran(identite=Identite(), champs=(Champ(id="a"), Champ(id="b")))
        self.assertEqual(ecran.empreinte, empreinte(["a", "b"]))

    def test_fenetre_modale(self):
        self.assertFalse(Fenetre(id="wnd[0]").modale)
        self.assertTrue(Fenetre(id="wnd[1]").modale)

    def test_les_types_sont_figes(self):
        """Immuables : un releve d'ecran ne se modifie pas apres capture."""
        with self.assertRaises(Exception):
            Identite().transaction = "IA08"      # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
