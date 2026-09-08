"""Le compte rendu de cartographie, et le cablage de `deposer`.

Deux choses se verifient ici, et la seconde est un garde-fou.

**Le rapport ne rapproche jamais une esquisse d'un releve par la clef.** Les
deux ne peuvent pas coincider — l'une porte les identifiants TOUCHES, l'autre
les PRESENTS — et un rapport qui ferait une difference d'ensembles annoncerait
« 0 relevee, 35 restantes » sur une cartographie parfaitement reussie.

**`deposer` a un appelant de production, et un test AST l'exige.** La fonction
existait depuis le lot 8, appelee par ses seuls tests. Le meme trou avait ete
trouve sur `promouvoir` ; le garde-fou est donc un test, pas une intention.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from falcon.catalogue import Depot
from falcon.exploration import explorer
from falcon.exploration import rapport as R
from falcon.taxonomie import Registre
from falcon.trace import lire

from tests.test_exploration_parcours import Bac, SapDePapier, trace_de
from tests.test_trace import MEGATRACE

RACINE = Path(__file__).resolve().parent.parent
PAQUET = RACINE / "falcon"

REGISTRE = Registre.charger()


def _arbres():
    """(chemin relatif, AST) de chaque module de production."""
    for chemin in sorted(PAQUET.rglob("*.py")):
        yield (str(chemin.relative_to(RACINE)),
               ast.parse(chemin.read_text(encoding="utf-8"), str(chemin)))


class TestLeGardeFouDeDeposer(unittest.TestCase):

    def test_deposer_a_un_appelant_de_production(self):
        """CONTROLE NEGATIF n°6 : `deposer` sans appelant de production.

        Retirer l'appel de `commandes/cartographie.py` fait tomber ce test.
        C'est ce test qui manquait, et c'est pour ca que le trou a dure : une
        capacite annoncee dans la documentation et injoignable depuis le
        programme est un mensonge de plus, pas une fonctionnalite en attente.
        """
        appelants = []
        for module, arbre in _arbres():
            if module.endswith("trace/esquisse.py"):
                continue                    # c'est la definition, pas un appel
            for noeud in ast.walk(arbre):
                if not isinstance(noeud, ast.Call):
                    continue
                nom = (getattr(noeud.func, "id", None)
                       or getattr(noeud.func, "attr", None))
                if nom == "deposer":
                    appelants.append(module)
        self.assertTrue(
            appelants,
            "`trace.esquisse.deposer` n'a aucun appelant de production : "
            "les esquisses d'une trace ne pourraient etre versees en "
            "quarantaine par aucune commande, alors que la documentation "
            "l'annonce")

    def test_le_depot_des_esquisses_est_reexporte(self):
        """Un module que le paquet ne reexporte pas se retrouve vite oublie."""
        import falcon.trace as T
        self.assertIn("deposer", dir(T))
        self.assertIn("code_transaction", dir(T))


class TestLeRapprochementParPosition(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.trace = lire(MEGATRACE)

    def _explorer(self, bac):
        sap = SapDePapier()
        sap.refusees = {"IW2ç"}
        return explorer(self.trace, sap, catalogue=bac, plafond_gestes=500,
                        plafond_ecrans=500, registre=REGISTRE)

    def test_toute_visite_recoit_un_etat_et_un_seul(self):
        with Bac() as bac:
            etats = R.etat_des_visites(self._explorer(bac), self.trace)
        from falcon.trace.esquisse import visites
        self.assertEqual(len(etats), len(visites(self.trace)))
        for visite, etat in etats:
            with self.subTest(visite=visite.ordre):
                self.assertIn(etat, R.ETATS_DE_VISITE)

    def test_une_difference_de_clefs_donnerait_zero_et_ce_serait_faux(self):
        """Le piege, montre plutot que raconte.

        Les deux empreintes ne se rencontrent JAMAIS : un rapport bati sur
        `set(esquisses) - set(releves)` annoncerait que tout reste a faire
        alors que les ecrans sont au depot. C'est ce que ce test mesure — et
        c'est pourquoi `etat_des_visites` raisonne par position.
        """
        from falcon.trace.esquisse import esquisses
        with Bac() as bac:
            resultat = self._explorer(bac)
        conjecturees = {e.clef for e in esquisses(self.trace)}
        relevees = set(resultat.versees)
        self.assertTrue(relevees, "le parcours doit avoir verse des ecrans")
        self.assertEqual(conjecturees & relevees, set(),
                         "une esquisse et un releve ne peuvent pas partager "
                         "une clef ; s'ils le pouvaient, tout le raisonnement "
                         "de `esquisse.py` tomberait")
        # Et pourtant, par position, la cartographie a bien couvert du terrain.
        atteintes = [v for v, e in R.etat_des_visites(resultat, self.trace)
                     if e == R.ATTEINTE]
        self.assertGreater(len(atteintes), 20)

    def test_le_rapport_ecrit_la_phrase_qui_evite_le_contresens(self):
        """« Atteinte » sans explication se lit « meme clef des deux cotes »."""
        with Bac() as bac:
            texte = R.rendre(self._explorer(bac), self.trace)
        self.assertIn("Ce n'est PAS « la meme clef existe des", texte)
        self.assertIn("pas un compte d'ecrans distincts", texte)

    def test_le_rapport_dit_ce_qu_il_ne_dit_pas(self):
        with Bac() as bac:
            texte = R.rendre(self._explorer(bac), self.trace)
        self.assertIn("ce que ce rapport ne dit pas", texte)
        self.assertIn("que la trace a ete SUIVIE : elle ne l'a pas ete", texte)
        self.assertIn("QUARANTAINE", texte)

    def test_le_rapport_compte_les_sauvegardes_atteintes_ET_contenues(self):
        """3 refusees sur 8 : les cinq autres n'ont pas ete atteintes.

        Annoncer « 3 sauvegardes » sans dire que la trace en contient 8
        laisserait croire que la rejouer sans dry-run en ecrirait 3.
        """
        with Bac() as bac:
            texte = R.rendre(self._explorer(bac), self.trace)
        self.assertIn("3 refusee(s) sur 8 que la trace contient", texte)
        self.assertIn("ecrirait 8 fois dans SAP", texte)

    def test_la_previsualisation_annonce_les_sauvegardes_avant_de_lancer(self):
        texte = R.previsualisation(self.trace)
        self.assertIn("8 geste(s) de SAUVEGARDE", texte)
        self.assertIn("mandant de qualite", texte)
        self.assertIn("IH06, IH08, IW39, IW2ç, IW29", texte)


class TestLesEsquissesManquantes(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.trace = lire(MEGATRACE)

    def test_seules_les_visites_NON_atteintes_sont_versees(self):
        """Verser les autres poserait la conjecture a cote du releve reel."""
        from falcon.commandes.cartographie import cartographier
        sap = SapDePapier()
        sap.refusees = {"IW2ç"}
        with Bac() as bac:
            _, exploration, compte_rendu = cartographier(
                MEGATRACE, bac, plafond_gestes=500, plafond_ecrans=500,
                esquisses=True, registre=REGISTRE, driver=sap)
            quarantaine = Depot(Depot(bac).quarantaine)
            esquissees = [v for triplet in quarantaine.triplets()
                          for v in quarantaine.variantes(triplet)
                          if not v.observee]
            relevees = [v for triplet in quarantaine.triplets()
                        for v in quarantaine.variantes(triplet)
                        if v.observee]

        manquantes = R.esquisses_manquantes(exploration, self.trace)
        self.assertEqual(len(esquissees), len(manquantes))
        self.assertTrue(relevees)
        self.assertIn("LISTE DE COURSES", compte_rendu)
        # Une esquisse se distingue a l'oeil nu d'un releve.
        for variante in esquissees:
            self.assertEqual(variante.clef.programme, "?")
            self.assertEqual(variante.clef.dynpro, "?")
            for champ in variante.champs:
                self.assertEqual(champ.type, "")
                self.assertIsNone(champ.modifiable)

    def test_sans_visite_manquante_rien_n_est_verse(self):
        trace = trace_de(
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "A"\r\n')
        from falcon.commandes.cartographie import cartographier
        with Bac() as bac:
            _, _, compte_rendu = cartographier(
                trace.source, bac, plafond_gestes=50, plafond_ecrans=50,
                esquisses=True, registre=REGISTRE, driver=SapDePapier())
            quarantaine = Depot(Depot(bac).quarantaine)
            esquissees = [v for triplet in quarantaine.triplets()
                          for v in quarantaine.variantes(triplet)
                          if not v.observee]
        self.assertEqual(esquissees, [])
        self.assertIn("aucune visite non atteinte", compte_rendu)

    def test_deposer_filtre_par_ordre_de_visite_et_dedoublonne(self):
        from falcon.trace.esquisse import deposer, visites
        toutes = [v.ordre for v in visites(self.trace)]
        with Bac() as bac:
            depot = Depot(bac)
            partielles = deposer(self.trace, depot, seulement=toutes[:5])
            completes = deposer(self.trace, depot)
        self.assertLess(len(partielles), len(completes))
        self.assertEqual(len(set(completes)), len(completes))


class TestLaLigneDeCommande(unittest.TestCase):

    def test_explorer_n_expose_ni_mode_ni_plafond_de_sauvegardes(self):
        """Une option est une chose que quelqu'un finit par regler."""
        import contextlib
        import io

        from falcon.commandes.principal import analyseur
        tampon = io.StringIO()
        with contextlib.redirect_stdout(tampon):
            try:
                analyseur().parse_args(["explorer", "--help"])
            except SystemExit:
                pass
        texte = tampon.getvalue()
        self.assertNotIn("--mode", texte)
        self.assertNotIn("--plafond-sauvegardes", texte)
        self.assertIn("--plafond-gestes", texte)
        self.assertIn("--plafond-ecrans", texte)

    def test_les_deux_plafonds_sont_obligatoires(self):
        """Le §5.5 : le rayon d'action est obligatoire, pas optionnel."""
        from falcon.commandes.principal import analyseur
        for arguments in (["explorer", "t.vbs", "--catalogue", "c"],
                          ["explorer", "t.vbs", "--catalogue", "c",
                           "--plafond-gestes", "10"],
                          ["explorer", "t.vbs", "--catalogue", "c",
                           "--plafond-ecrans", "10"]):
            with self.subTest(arguments):
                with self.assertRaises(SystemExit):
                    import contextlib
                    import io
                    with contextlib.redirect_stderr(io.StringIO()):
                        analyseur().parse_args(arguments)

    def test_le_preambule_ne_dit_plus_que_tout_est_en_lecture_seule(self):
        """`explorer` n'ecrit pas, mais elle AGIT. « Lecture seule » serait faux.

        Le texte rassurant est exactement ce que ce depot traque : il aurait
        laisse quelqu'un lancer une exploration sur la production en croyant
        qu'elle ne pouvait rien faire.
        """
        from falcon.commandes import principal
        self.assertIn("deux\nd'entre elles y AGISSENT", principal.__doc__)
        self.assertIn("AGIT", principal.DESCRIPTION)
        self.assertIn("explorer", principal.DESCRIPTION)


if __name__ == "__main__":
    unittest.main()
