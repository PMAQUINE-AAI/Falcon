"""La lecture d'une grille ALV, et la recherche d'une ligne par son contenu.

Deux propietes portent ce lot.

**Une seule boucle de lecture dans tout le depot.** Elle etait dans
`volumique/se16n.py` et le rejeu declaratif en avait besoin aussi. Un test AST
refuse tout appel a `grid_read` hors de `controleur/grille.py` : c'est ce qui
rend « pas de recopie » mecanique plutot que discipline.

**Une colonne qu'on ne trouve pas est un refus, pas une valeur vide.**
`couture/double.py` rend `""` pour une colonne inconnue ; sans le refus, une
colonne mal orthographiee apparie TOUTES les lignes dont la cellule est vide, et
la recherche rend un rang. Ce que fait `GetCellValue` en production, personne ici
ne le sait — et c'est precisement pourquoi le refus existe.

Rien ici ne touche a SAP : tout se verifie contre `DriverScripte`.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from falcon.controleur import DriverGarde, GrilleIllisible, Poste
from falcon.controleur.grille import chercher, colonnes_de, relever
from falcon.couture.double import DriverScripte
from falcon.noyau import Identite
from falcon.taxonomie import Registre

RACINE = Path(__file__).resolve().parent.parent
PAQUET = RACINE / "falcon"

#: Le SEUL module de production autorise a lire une cellule de grille.
LECTEUR_AUTORISE = "falcon/controleur/grille.py"

IA08 = Identite(transaction="IA08", programme="RIPLKO10", dynpro="1000")

GRILLE = "wnd[1]/usr/cntlALV_CONTAINER_1/shellcont/shell"

#: Trois variantes, dont deux homonymes a la casse pres — le cas qui decide.
VARIANTES = [
    {"VARIANT": "/BCP01_K75", "TEXT": "BCP site K75", "ENAME": "DUPONT"},
    {"VARIANT": "/BCP02_K75", "TEXT": "BCP site K75 bis", "ENAME": "DUPONT"},
    {"VARIANT": "/bcp01_k75", "TEXT": "doublon de casse", "ENAME": "MARTIN"},
]


def poste_avec(lignes: list[dict[str, str]]) -> tuple[Poste, DriverScripte]:
    """Un `Poste` garde, servant la grille demandee. Aucune fidelite etablie."""
    brut = DriverScripte(identite=IA08)
    brut.grilles[GRILLE] = lignes
    garde = DriverGarde(brut, Registre.charger(), plafond_sauvegardes=0)
    return Poste(garde), brut


class TestUneSeuleBoucleDansLeDepot(unittest.TestCase):

    def test_grid_read_n_est_appele_que_dans_le_module_de_lecture(self):
        """CONTROLE NEGATIF : remettre une boucle `grid_read` dans `se16n.py`.

        Le test tombe. C'est ce qui rend l'absence de recopie mecanique : la
        decision n°14 refuse deja de recopier le code transaction au motif que
        deux copies finissent par diverger, et ca vaut a plus forte raison pour
        la lecture qui produit les donnees.

        La plomberie est exclue nommement : la couture DECLARE la methode,
        `Poste` et `DriverGarde` la RELAIENT. Aucun des trois ne construit de
        donnees.
        """
        plomberie = {
            "falcon/couture/interface.py",       # la declaration abstraite
            "falcon/couture/sapgui.py",          # l'implementation COM
            "falcon/couture/double.py",          # le double de test
            "falcon/controleur/poste.py",        # la facade
            "falcon/controleur/gardes.py",       # l'enveloppe gardee
            LECTEUR_AUTORISE,
        }
        coupables = []
        for chemin in sorted(PAQUET.rglob("*.py")):
            module = str(chemin.relative_to(RACINE))
            if module in plomberie:
                continue
            arbre = ast.parse(chemin.read_text(encoding="utf-8"), str(chemin))
            for noeud in ast.walk(arbre):
                if not isinstance(noeud, ast.Call):
                    continue
                if getattr(noeud.func, "attr", None) == "grid_read":
                    coupables.append(f"{module}:{noeud.lineno}")
        self.assertEqual(
            coupables, [],
            f"{coupables} lisent une cellule de grille hors de "
            f"{LECTEUR_AUTORISE}. Une seconde boucle de lecture finira par "
            f"diverger de la premiere")

    def test_l_export_se16n_passe_par_la_meme_lecture(self):
        """Le detecteur de derive : si `se16n` cesse d'appeler `relever`, la
        boucle est revenue quelque part."""
        source = (PAQUET / "volumique" / "se16n.py").read_text(encoding="utf-8")
        arbre = ast.parse(source)
        appels = [n for n in ast.walk(arbre) if isinstance(n, ast.Call)]
        self.assertTrue(
            any(getattr(a.func, "id", None) == "relever" for a in appels),
            "`se16n` doit lire par `controleur.grille.relever`")


class TestRelever(unittest.TestCase):

    def test_toutes_les_lignes_et_toutes_les_colonnes_exposees(self):
        poste, _ = poste_avec(VARIANTES)
        self.assertEqual(relever(poste, GRILLE), VARIANTES)

    def test_une_grille_vide_rend_une_liste_vide_sans_lever(self):
        """`relever` ne conclut rien : « zero ligne » est une donnee, pas un
        verdict. C'est l'appelant qui sait ce que zero veut dire chez lui."""
        poste, _ = poste_avec([])
        self.assertEqual(relever(poste, GRILLE), [])

    def test_les_colonnes_declarees_restreignent_la_lecture(self):
        poste, brut = poste_avec(VARIANTES)
        lignes = relever(poste, GRILLE, colonnes=("VARIANT",))
        self.assertEqual([l["VARIANT"] for l in lignes],
                         ["/BCP01_K75", "/BCP02_K75", "/bcp01_k75"])
        self.assertEqual(set(lignes[0]), {"VARIANT"})

    def test_une_colonne_declaree_absente_est_refusee(self):
        """CONTROLE NEGATIF n°1 : retirer `_retenir` fait tomber ce test.

        Sans lui, `double.py` rend `""` et la colonne sort vide — une colonne
        d'aspect normal, sans valeur, dans un fichier qu'un humain relira.
        """
        poste, _ = poste_avec(VARIANTES)
        with self.assertRaises(GrilleIllisible) as leve:
            relever(poste, GRILLE, colonnes=("VARIANTE",))
        self.assertIn("VARIANTE", str(leve.exception))
        self.assertIn("VARIANT", str(leve.exception))     # ce qu'elle expose

    def test_les_colonnes_exposees_sont_celles_de_la_grille(self):
        poste, _ = poste_avec(VARIANTES)
        self.assertEqual(colonnes_de(poste, GRILLE),
                         ("VARIANT", "TEXT", "ENAME"))


class TestChercher(unittest.TestCase):

    def test_un_appariement_rend_son_rang(self):
        poste, _ = poste_avec(VARIANTES)
        self.assertEqual(
            chercher(poste, GRILLE, "VARIANT", "/BCP02_K75",
                     comparaison="exact"),
            (1,))

    def test_aucun_appariement_rend_le_vide_sans_lever(self):
        """`chercher` ne decide pas : « aucune » est une donnee.

        La politique — abandonner l'item — appartient au moteur, ou vivent
        `ItemAbandonne` et `ArretBloquant`. Un module du controleur qui
        leverait `ItemAbandonne` importerait une notion de moteur.
        """
        poste, _ = poste_avec(VARIANTES)
        self.assertEqual(
            chercher(poste, GRILLE, "VARIANT", "/ZZZ", comparaison="exact"),
            ())

    def test_TOUS_les_rangs_sont_rendus_jamais_le_premier(self):
        """CONTROLE NEGATIF : rendre le premier rang fait tomber ce test.

        Rendre le premier, c'est choisir au hasard la ligne qu'on va modifier
        — et l'appelant n'aurait aucun moyen de savoir qu'elles etaient deux.
        """
        poste, _ = poste_avec(VARIANTES)
        self.assertEqual(
            chercher(poste, GRILLE, "VARIANT", "/BCP01_K75",
                     comparaison="casse"),
            (0, 2))

    def test_la_casse_est_celle_des_gardes_pas_un_second_dialecte(self):
        poste, _ = poste_avec(VARIANTES)
        self.assertEqual(
            chercher(poste, GRILLE, "VARIANT", "/BCP01_K75",
                     comparaison="exact"),
            (0,))
        self.assertEqual(
            chercher(poste, GRILLE, "VARIANT", "/BCP01_K75",
                     comparaison="casse"),
            (0, 2))

    def test_une_troncature_n_est_PAS_un_appariement(self):
        """« 1000 » et « 1 » ne designent pas la meme variante.

        `_comparer` rend « tronque » sous le mode `prefixe` ; c'est une
        tolerance a ce que SAP fait subir a une SAISIE, pas une egalite. La
        retenir ici ferait ouvrir une variante pour une autre.
        """
        poste, _ = poste_avec([{"VARIANT": "/BCP"}, {"VARIANT": "/BCP01_K75"}])
        self.assertEqual(
            chercher(poste, GRILLE, "VARIANT", "/BCP01_K75",
                     comparaison="prefixe"),
            (1,))

    def test_chercher_dans_une_colonne_inexistante_est_refuse(self):
        """LE contrôle négatif du lot.

        Mesure sans le refus, contre le double : `grid_read` rend `""` pour
        toute colonne inconnue, donc chercher `""` dans « VARIANTE » apparie
        les TROIS lignes, et un appelant qui prend le premier rang ouvre la
        ligne 0. Aucune exception. Le refus existe pour que ce chemin n'existe
        pas.
        """
        poste, _ = poste_avec(VARIANTES)
        with self.assertRaises(GrilleIllisible):
            chercher(poste, GRILLE, "VARIANTE", "", comparaison="exact")

    def test_la_mesure_de_ce_que_le_refus_empeche(self):
        """Ce que le double ferait SANS le refus — exécuté, pas raconté."""
        poste, _ = poste_avec(VARIANTES)
        vides = [poste.grid_read(GRILLE, rang, "VARIANTE")
                 for rang in range(len(VARIANTES))]
        self.assertEqual(vides, ["", "", ""],
                         "si le double cessait de rendre une chaine vide, le "
                         "refus de `chercher` perdrait sa raison mesuree")


class TestLesGardesRestentArmees(unittest.TestCase):

    def test_lire_une_grille_passe_par_la_garde_d_identite(self):
        """La lecture n'echappe pas au contrat : c'est ce qui distinguera un
        atterrissage sur la liste d'un atterrissage dans l'objet."""
        from falcon.controleur import Contrat
        from falcon.noyau import EcartIdentite

        poste, _ = poste_avec(VARIANTES)
        garde = poste._Poste__garde                     # noqa: SLF001 — test
        autre = Contrat(nom="ailleurs",
                        ecran_attendu=("IW39", "RIIFLO20", "1000"))
        with garde.sous_contrat(autre):
            with self.assertRaises(EcartIdentite):
                relever(poste, GRILLE)


if __name__ == "__main__":
    unittest.main()
