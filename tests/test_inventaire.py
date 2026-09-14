"""Le catalogue relu, compte, cherche et compare — et ce qu'il REFUSE.

Ce module est un modele pur : il ne produit pas une ligne de texte. Ce qu'on
lui demande ici tient en quatre refus, et chacun protege contre un resultat
plausible et FAUX plutot que contre une exception :

1. **Un fichier casse ne fait perdre aucun autre.** `Depot.triplets()` leve sur
   le premier et perd les neuf suivants, sans jamais dire lequel a fache.
   « 21 variantes » au lieu de « 22 dont une illisible » est un compte
   plausible et faux — et celui-la se recopie dans une decision.
2. **`comparer` refuse une esquisse.** Mesure faite sur la quarantaine que
   produit la trace de reference : six paires y satisferaient, sans cette
   garde, la condition exacte du paragraphe « signature du couple modale /
   porteur ». Une heuristique fausse des le premier jour, sur la fixture du
   depot.
3. **Une fenetre se LIT dans les identifiants.** Une variante qui n'en nomme
   aucune rend un tuple vide, jamais `wnd[0]` : c'est precisement
   l'affirmation que la modale rend dangereuse.
4. **`au_cure` ne cache rien.** Le catalogue ne garde aucune trace d'une
   promotion ; la meme empreinte des deux cotes est un fait de fichier, et
   filtrer dessus par defaut cacherait des lignes sur une inference.

Chaque test nomme, dans sa docstring, la ligne de production a casser pour le
faire tomber. Un test dont on ne sait pas ce qui le ferait tomber ne prouve
rien.
"""

from __future__ import annotations

import ast
import itertools
import tempfile
import unittest
from pathlib import Path

from falcon.catalogue import (
    CHAMP, ECRAN, ESQUISSE, QUARANTAINE, TOUS, CatalogueInvalide,
    ComparaisonRefusee, Critere, Depot, Fiche, charger, comparer,
    fenetres_citees, filtrer, rapports, sans_mesure, variante_de,
)
from falcon.catalogue import inventaire as I
from falcon.commandes.cartographie import DOSSIER_RAPPORTS, cartographier
from falcon.couture.sapgui import FACULTATIFS
from falcon.noyau import Champ, Ecran, Identite

from tests.test_exploration_parcours import REGISTRE, SapDePapier
from tests.test_trace import MEGATRACE

IA08 = Identite(transaction="IA08", programme="RIPLKO10", dynpro="1000")
IH06 = Identite(transaction="IH06", programme="SAPLIH06", dynpro="1000")


def _ecran(identite: Identite, *champs: Champ, titre: str = "") -> Ecran:
    return Ecran(identite=identite, champs=champs, titre=titre,
                 capture_le="2026-09-11T18:10:54.370Z")


def _bac() -> Path:
    return Path(tempfile.mkdtemp())


class TestUnFichierCasseNEmporteRien(unittest.TestCase):
    """Le refus qui distingue « 21 » de « 22 dont une illisible »."""

    def setUp(self):
        self.racine = _bac()
        depot = Depot(self.racine)
        depot.mettre_en_quarantaine(variante_de(_ecran(
            IA08, Champ(id="wnd[0]/usr/txtA"), titre="A")))
        depot.mettre_en_quarantaine(variante_de(_ecran(
            IH06, Champ(id="wnd[0]/usr/txtB"), titre="B")))
        self.casse = depot.quarantaine / "CASSE__X__0100.yaml"
        self.casse.write_text("version: 9\nvariantes: {}\n", encoding="utf-8")

    def test_un_fichier_casse_ne_fait_perdre_aucun_autre(self):
        """CONTROLE NEGATIF n°5 : remplacer le `except (CatalogueInvalide,
        OSError)` de `charger` par une remontee — c'est-a-dire le comportement
        de `Depot.triplets()` — fait tomber ce test.

        Aujourd'hui, un catalogue dont un fichier sur dix est illisible ne se
        liste pas du tout depuis la console : la premiere lecture leve, et les
        neuf autres n'existent plus pour personne.
        """
        inventaire = charger(Depot(self.racine))
        self.assertEqual(len(inventaire.fiches), 2)
        self.assertEqual(inventaire.fichiers_lus, 2)

    def test_l_illisible_est_nomme_avec_son_motif(self):
        """Un compte a part ne suffit pas : il faut pouvoir aller le reparer.

        CONTROLE NEGATIF : remplacer `illisibles.append((chemin, str(erreur)))`
        par un simple compteur fait tomber ce test.
        """
        inventaire = charger(Depot(self.racine))
        self.assertEqual(len(inventaire.illisibles), 1)
        chemin, motif = inventaire.illisibles[0]
        self.assertEqual(chemin, self.casse)
        self.assertIn("version 9", motif)

    def test_l_illisible_n_entre_dans_aucun_total(self):
        inventaire = charger(Depot(self.racine))
        self.assertEqual(inventaire.fichiers_lus, 2,
                         "le fichier casse est compte parmi les fichiers lus")
        self.assertNotIn(self.casse, [f.fichier for f in inventaire.fiches])

    def test_un_fichier_qui_n_est_pas_du_YAML_est_compte_a_part_lui_aussi(self):
        """Un fichier tronque par une copie interrompue n'est pas du YAML.

        MESURE, et elle a corrige une supposition : `Depot._lire_fichier`
        appelle `yaml.safe_load` DIRECTEMENT, pas `noyau/yaml_strict.py`. Une
        troncature y leve une `yaml.parser.ParserError` nue, que ni
        `CatalogueInvalide` ni `OSError` n'attrapent. CONTROLE NEGATIF :
        retirer `yaml.YAMLError` du `except` de `charger` fait tomber ce test,
        et l'inventaire entier tombe pour un fichier sur dix.
        """
        (Depot(self.racine).quarantaine / "TRONQUE.yaml").write_text(
            "version: 1\nvariantes: {\n", encoding="utf-8")
        inventaire = charger(Depot(self.racine))
        self.assertEqual(len(inventaire.fiches), 2)
        self.assertEqual(len(inventaire.illisibles), 2)

    #: Quatre formes de fichier casse qui traversaient les trois familles
    #: attrapees par `charger` et emportaient l'inventaire ENTIER. Mesurees en
    #: ecrivant les fichiers : `UnicodeDecodeError` (un `ValueError`),
    #: `AttributeError` deux fois, `TypeError`.
    FORMES_CASSEES = (
        ("cp1252", b"version: 1\nvariantes:\n  abc:\n    titre: caf\xe9\n",
         "pas de l'UTF-8"),
        ("variantes en liste", b"version: 1\nvariantes:\n  - a\n  - b\n",
         "est un list"),
        ("corps scalaire", b"version: 1\nvariantes:\n  abc: 3\n",
         "est un int"),
        ("champs scalaire",
         b"version: 1\nvariantes:\n  abc:\n    champs: 3\n",
         "une liste est attendue"),
        ("champ scalaire",
         b"version: 1\nvariantes:\n  abc:\n    champs: [3]\n",
         "un dictionnaire est attendu"),
    )

    def test_cinq_AUTRES_formes_de_fichier_casse_sont_comptees_a_part(self):
        """Les trois familles de `charger` ne suffisaient PAS, et la docstring
        promettait « sans jamais lever ».

        Chacune de ces cinq formes fait sortir, sans la correction, une
        exception qui n'est ni `CatalogueInvalide`, ni `OSError`, ni
        `yaml.YAMLError` : elle traverse `charger`, `naviguer`, `parcourir` et
        `_console`, et l'utilisateur recoit une trace de pile a la place de son
        catalogue. Le cas le plus probable sur la cible est le premier : un
        YAML rouvert et resauvegarde par le Bloc-notes d'un poste Windows
        francais sort en cp1252.

        CONTROLE NEGATIF : retirer une des validations de forme de
        `Depot.contenu`, ou le rattrapage d'`UnicodeDecodeError` de
        `Depot._lire_fichier`, fait tomber ce test — et fait remonter la levee
        jusqu'a la console.
        """
        for nom, octets, attendu in self.FORMES_CASSEES:
            with self.subTest(forme=nom):
                fichier = Depot(self.racine).quarantaine / "FORME.yaml"
                fichier.write_bytes(octets)
                inventaire = charger(Depot(self.racine))
                self.assertEqual(len(inventaire.fiches), 2,
                                 "les autres fichiers ont ete perdus")
                motifs = [motif for chemin, motif in inventaire.illisibles
                          if chemin == fichier]
                self.assertEqual(len(motifs), 1, inventaire.illisibles)
                self.assertIn(attendu, motifs[0])
                self.assertIn("FORME.yaml", motifs[0],
                              "le refus ne nomme pas le fichier a reparer")
                fichier.unlink()

    def test_la_forme_cassee_est_refusee_par_le_DEPOT_lui_meme(self):
        """Et pas seulement par l'inventaire : `falcon inventaire`,
        `pour_edition` et `promouvoir` passent par le meme `contenu`.

        Elargir l'`except` de `charger` aurait laisse tous les autres
        appelants de `Depot` tomber sur les memes fichiers.
        """
        for nom, octets, _attendu in self.FORMES_CASSEES:
            with self.subTest(forme=nom):
                fichier = Depot(self.racine).quarantaine / "FORME.yaml"
                fichier.write_bytes(octets)
                ecarte = Depot(Depot(self.racine).quarantaine)
                with self.assertRaises(CatalogueInvalide):
                    ecarte.contenu(fichier)
                fichier.unlink()


class TestLesFenetresSeLisent(unittest.TestCase):
    """On lit la fenetre dans l'identifiant. On ne la devine jamais."""

    def test_une_variante_sans_segment_de_fenetre_rend_un_tuple_VIDE(self):
        """CONTROLE NEGATIF : faire rendre `("wnd[0]",)` au cas vide — le
        « defaut raisonnable » — fait tomber ce test.

        C'est exactement l'affirmation que la modale rend dangereuse : le
        releve d'une modale porte le programme et le dynpro de l'ecran de
        DESSOUS, et ses identifiants sont le seul endroit ou la fenetre se
        lise.
        """
        self.assertEqual(fenetres_citees((Champ(id="usr/ctxtSANS_FENETRE"),)),
                         ())

    def test_la_fenetre_se_lit_dans_un_identifiant_ABSOLU(self):
        """SAP GUI rend usuellement `/app/con[0]/ses[0]/wnd[0]/usr/...`.

        CONTROLE NEGATIF : ancrer la regex au debut (`^wnd\\[`) fait tomber ce
        test. Elle continuerait de passer sur toutes les fixtures du depot, qui
        ecrivent la forme courte, et rendrait « ? » partout sur un catalogue
        releve contre un vrai systeme.
        """
        self.assertEqual(
            fenetres_citees((Champ(id="/app/con[0]/ses[0]/wnd[1]/usr/txtA"),)),
            ("wnd[1]",))

    def test_les_fenetres_sont_dedoublonnees_et_triees(self):
        champs = (Champ(id="wnd[1]/usr/a"), Champ(id="wnd[0]/usr/b"),
                  Champ(id="wnd[1]/usr/c"))
        self.assertEqual(fenetres_citees(champs), ("wnd[0]", "wnd[1]"))


class TestLeTriEtatEtLaPreuve(unittest.TestCase):
    """Ce que `modifiable` dit, et ce qu'il ne dit pas."""

    def test_compte_modifiable_distingue_les_TROIS_etats(self):
        """Les trois comptes sont DISTINCTS, et la position est assertee.

        Avec un champ par etat, l'assertion `(1, 1, 1)` est invariante par
        toute permutation du tuple : le test portait le mot « distingue » et ne
        distinguait rien. Mesure faite : rendre `(verrouilles, ecrivables,
        inconnus)` laissait la suite entiere verte, et l'en-tete de la fiche
        annoncait « 2 ecrivable(s), 9 verrouille(s) » sur un ecran qui porte
        neuf champs ecrivables — aucune exception, un resultat plausible et
        faux, sur la seule ligne de synthese que l'humain lit avant de
        certifier avoir relu l'ecran.

        CONTROLE NEGATIF : permuter deux des trois membres du tuple rendu par
        `compte_modifiable` fait tomber ce test.
        """
        fiche = Fiche(
            variante=variante_de(_ecran(
                IA08,
                Champ(id="wnd[0]/a1", modifiable=True),
                Champ(id="wnd[0]/a2", modifiable=True),
                Champ(id="wnd[0]/b1", modifiable=False),
                Champ(id="wnd[0]/b2", modifiable=False),
                Champ(id="wnd[0]/b3", modifiable=False),
                Champ(id="wnd[0]/c1", modifiable=None))),
            rayon=QUARANTAINE, fichier=Path("x.yaml"))
        self.assertEqual(fiche.compte_modifiable, (2, 3, 1))

    def test_un_GuiShell_est_signale_comme_SANS_PREUVE(self):
        """Le « oui » d'un shell vient d'un defaut de `couture/sapgui.py`.

        CONTROLE NEGATIF : faire rendre faux a `sans_mesure` fait tomber ce
        test — et l'ecran ecrirait alors « oui » sur une valeur que personne
        n'a mesuree.
        """
        self.assertTrue(sans_mesure(Champ(id="wnd[0]/s", type="GuiShell",
                                          modifiable=True)))
        self.assertFalse(sans_mesure(Champ(id="wnd[0]/t",
                                           type="GuiTextField",
                                           modifiable=True)))

    def test_sans_mesure_regarde_la_VALEUR_et_pas_le_seul_type(self):
        """Le defaut qu'on accuse est `True`. Les deux autres etats ne sont
        pas lui, et les annoter le dirait faux.

        Rien n'empeche un `GuiShell` de porter `modifiable: false` : un YAML
        relu, converti ou retouche a la main peut porter n'importe laquelle
        des trois valeurs, et `Depot._variante` pose `None` des que le fichier
        ne renseigne rien. Sur un shell VERROUILLE, l'annotation « ce oui-la
        n'a ete mesure par personne » nomme un oui qui n'est pas la, et qui
        redige un `set` y lit l'inverse de la donnee.

        CONTROLE NEGATIF : revenir a `champ.type == TYPE_SANS_CHANGEABLE` seul
        fait tomber ce test.
        """
        for valeur in (False, None):
            with self.subTest(modifiable=valeur):
                self.assertFalse(sans_mesure(Champ(id="wnd[0]/s",
                                                   type="GuiShell",
                                                   modifiable=valeur)))

    def test_le_defaut_de_la_couture_est_bien_celui_qu_on_accuse(self):
        """La docstring de `sans_mesure` AFFIRME que la couture inscrit `True`.

        Si `FACULTATIFS["Changeable"]` passait a `None` un jour, la note de
        l'ecran — « ce oui-la n'a ete mesure par personne » — deviendrait
        fausse sans que rien ne leve. Une docstring fausse est un defaut a
        part entiere ; celle-ci est epinglee.
        """
        self.assertIs(FACULTATIFS["Changeable"], True)
        self.assertEqual(I.TYPE_SANS_CHANGEABLE, "GuiShell")


class TestAuCureNeCacheRien(unittest.TestCase):

    def setUp(self):
        self.racine = _bac()
        depot = Depot(self.racine)
        commun = _ecran(IA08, Champ(id="wnd[0]/usr/txtA"))
        autre = _ecran(IA08, Champ(id="wnd[0]/usr/txtA"),
                       Champ(id="wnd[0]/usr/txtB"))
        depot.enregistrer(variante_de(commun))
        depot.mettre_en_quarantaine(variante_de(commun))
        depot.mettre_en_quarantaine(variante_de(autre))
        self.inventaire = charger(depot)

    def test_au_cure_est_un_fait_de_fichier(self):
        quarantaine = self.inventaire.rayon(QUARANTAINE)
        self.assertEqual(len(quarantaine), 2)
        self.assertEqual(sum(1 for f in quarantaine if f.au_cure), 1)

    def test_a_decider_ne_filtre_RIEN_par_defaut(self):
        """CONTROLE NEGATIF : mettre `a_decider: bool = True` dans `Critere`
        fait tomber ce test.

        Cacher des lignes sur une inference — « celle-ci est deja au cure,
        donc quelqu'un l'a vue » — est le reglage le plus dangereux possible
        pour une file de decisions, et le catalogue ne garde AUCUNE trace
        d'une promotion.
        """
        self.assertFalse(Critere().a_decider)
        trouvailles, total = filtrer(self.inventaire, Critere())
        self.assertEqual(total, 2)

    def test_a_decider_demande_ecarte_ce_qui_est_deja_au_cure(self):
        trouvailles, total = filtrer(self.inventaire,
                                     Critere(a_decider=True))
        self.assertEqual(total, 1)
        self.assertFalse(trouvailles[0].fiche.au_cure)

    def test_les_voisines_sont_du_meme_triplet_et_du_meme_rayon(self):
        quarantaine = self.inventaire.rayon(QUARANTAINE)
        voisines = self.inventaire.voisines(quarantaine[0])
        self.assertEqual(len(voisines), 1)
        self.assertEqual(voisines[0].rayon, QUARANTAINE)
        self.assertNotEqual(voisines[0].clef.empreinte,
                            quarantaine[0].clef.empreinte)


class TestLaRecherche(unittest.TestCase):

    def setUp(self):
        self.racine = _bac()
        depot = Depot(self.racine)
        depot.mettre_en_quarantaine(variante_de(_ecran(
            IH06,
            Champ(id="wnd[0]/usr/ctxtWERKS-LOW", type="GuiCTextField",
                  texte="Division", infobulle="Division  (WERKS)",
                  modifiable=True),
            Champ(id="wnd[0]/usr/ctxtWERKS-HIGH", type="GuiCTextField",
                  texte="a", infobulle="Division  (WERKS)", modifiable=True),
            Champ(id="wnd[0]/tbar[1]/btn[8]", type="GuiButton",
                  texte="Executer", modifiable=False),
            titre="Liste multi-niveaux")))
        depot.enregistrer(variante_de(_ecran(
            IA08, Champ(id="wnd[0]/usr/ctxtDIV_SEL", type="GuiCTextField",
                        texte="Division principale"))))
        self.inventaire = charger(depot)

    def test_la_portee_CHAMP_rend_une_trouvaille_par_champ(self):
        trouvailles, total = filtrer(
            self.inventaire, Critere(motif="werks", portee=CHAMP,
                                     rayon=TOUS))
        self.assertEqual(total, 2)
        self.assertEqual([t.champ.id for t in trouvailles],
                         ["wnd[0]/usr/ctxtWERKS-LOW",
                          "wnd[0]/usr/ctxtWERKS-HIGH"])

    def test_la_portee_ECRAN_ne_rend_AUCUN_champ(self):
        """`champ=None` plutot que le premier venu : rendre un champ que rien
        n'a apparie designerait une cible que personne n'a demandee."""
        trouvailles, _ = filtrer(self.inventaire,
                                 Critere(motif="IH06", portee=ECRAN))
        self.assertEqual(len(trouvailles), 1)
        self.assertIsNone(trouvailles[0].champ)

    def test_la_recherche_de_champ_couvre_les_six_attributs_annonces(self):
        """L'ecran ANNONCE ou il cherche. Les deux listes ne peuvent pas
        diverger : celle du modele est celle que la vue imprime."""
        for motif, attendu in (("werks-low", 1), ("division", 3),
                               ("guibutton", 1), ("executer", 1)):
            with self.subTest(motif=motif):
                _, total = filtrer(self.inventaire,
                                   Critere(motif=motif, portee=CHAMP,
                                           rayon=TOUS))
                self.assertEqual(total, attendu)

    def test_le_total_n_est_PAS_la_longueur_de_la_liste_tronquee(self):
        """CONTROLE NEGATIF : faire rendre `len(retenues)` a `filtrer` fait
        tomber ce test.

        « 1 trouvee » sur trois se lit comme « il n'y en a qu'une », et ce
        compte-la se recopie dans une decision : on conclut qu'on a tout relu.
        """
        trouvailles, total = filtrer(
            self.inventaire, Critere(motif="", portee=CHAMP, rayon=TOUS),
            limite=1)
        self.assertEqual(len(trouvailles), 1)
        self.assertEqual(total, 4)

    def test_le_rayon_par_defaut_est_la_quarantaine(self):
        self.assertEqual(Critere().rayon, QUARANTAINE)
        _, total = filtrer(self.inventaire, Critere(portee=CHAMP))
        self.assertEqual(total, 3)

    def test_une_portee_inconnue_est_REFUSEE_a_la_construction(self):
        with self.assertRaises(ValueError):
            Critere(portee="tout")
        with self.assertRaises(ValueError):
            Critere(rayon="ailleurs")


class TestLaComparaison(unittest.TestCase):

    def setUp(self):
        self.racine = _bac()
        depot = Depot(self.racine)
        self.gauche_ecran = _ecran(
            IH06, Champ(id="wnd[0]/usr/ctxtWERKS-LOW", type="GuiCTextField",
                        texte="Division", modifiable=True))
        self.droite_ecran = _ecran(
            IH06, Champ(id="wnd[1]/usr/btnOK", type="GuiButton",
                        texte="OK", modifiable=False))
        # L'esquisse porte d'AUTRES identifiants : l'empreinte est celle des
        # identifiants presents, donc une esquisse batie sur les memes champs
        # ecraserait la relevee dans le meme fichier, sous la meme clef.
        self.esquisse_ecran = _ecran(
            IH06, Champ(id="wnd[1]/usr/txtCONJECTURE"))
        depot.mettre_en_quarantaine(variante_de(self.gauche_ecran))
        depot.mettre_en_quarantaine(variante_de(self.droite_ecran))
        depot.mettre_en_quarantaine(variante_de(self.esquisse_ecran,
                                                source=ESQUISSE))
        self.inventaire = charger(depot)

    def _par_empreinte(self, empreinte: str) -> Fiche:
        for fiche in self.inventaire.fiches:
            if fiche.clef.empreinte == empreinte:
                return fiche
        raise AssertionError(empreinte)

    def test_comparer_refuse_une_esquisse(self):
        """CONTROLE NEGATIF n°4 : retirer la boucle `if not fiche.relevee` de
        `comparer` fait tomber ce test.

        Une esquisse porte les identifiants TOUCHES, un releve les
        identifiants PRESENTS. « 12 a gauche seulement » sur une esquisse qui
        en cite deux ne mesure que la difference entre observer et deviner.
        """
        gauche = [f for f in self.inventaire.fiches if f.relevee]
        esquisse = [f for f in self.inventaire.fiches if not f.relevee][0]
        self.assertEqual(len(gauche), 2)
        with self.assertRaises(ComparaisonRefusee) as leve:
            comparer(gauche[0], esquisse)
        self.assertIn("ESQUISSE", str(leve.exception))
        with self.assertRaises(ComparaisonRefusee):
            comparer(esquisse, gauche[0])

    def test_la_mesure_est_rendue_et_la_conclusion_jamais(self):
        gauche, droite = [f for f in self.inventaire.fiches if f.relevee]
        mesure = comparer(gauche, droite)
        self.assertTrue(mesure.aucun_identifiant_commun)
        self.assertTrue(mesure.fenetres_disjointes)
        self.assertFalse(hasattr(mesure, "est_une_modale"),
                         "le modele conclurait a la place de l'ecran")

    def test_fenetres_disjointes_est_FAUX_quand_un_cote_ne_cite_rien(self):
        """CONTROLE NEGATIF : ecrire `not (gauche & droite)` seul fait tomber
        ce test.

        Deux ensembles dont l'un est vide sont disjoints au sens des
        ensembles ; ce n'est pas le sens utile ici, et prendre l'un pour
        l'autre ferait affirmer un ecart de fenetres sur une variante qui n'en
        nomme aucune.
        """
        muette = Fiche(variante=variante_de(_ecran(
            IH06, Champ(id="usr/ctxtSANS_FENETRE"))),
            rayon=QUARANTAINE, fichier=Path("x.yaml"))
        gauche = [f for f in self.inventaire.fiches if f.relevee][0]
        self.assertFalse(comparer(gauche, muette).fenetres_disjointes)

    def test_un_identifiant_commun_dont_un_attribut_differe_fait_un_ecart(self):
        commun = Fiche(variante=variante_de(_ecran(
            IH06, Champ(id="wnd[0]/usr/ctxtWERKS-LOW", type="GuiCTextField",
                        texte="Divisions", modifiable=True))),
            rayon=QUARANTAINE, fichier=Path("y.yaml"))
        gauche = self._par_empreinte(
            variante_de(self.gauche_ecran).clef.empreinte)
        mesure = comparer(gauche, commun)
        self.assertEqual(mesure.communs, ("wnd[0]/usr/ctxtWERKS-LOW",))
        self.assertEqual([(e.attribut, e.gauche, e.droite)
                          for e in mesure.ecarts],
                         [("texte", "Division", "Divisions")])

    def test_l_identifiant_n_est_PAS_un_attribut_compare(self):
        """Il est la CLEF du rapprochement : le comparer a lui-meme rendrait
        un ecart sur chaque ligne commune."""
        self.assertNotIn("id", I.ATTRIBUTS_COMPARES)


class TestLaQuarantaineDeReference(unittest.TestCase):
    """La fixture du depot, rejouee. C'est elle qui mesure, pas moi."""

    @classmethod
    def setUpClass(cls):
        cls.racine = _bac()
        sap = SapDePapier()
        sap.refusees = {"IW2ç"}
        cartographier(MEGATRACE, cls.racine, plafond_gestes=500,
                      plafond_ecrans=500, esquisses=True, registre=REGISTRE,
                      driver=sap)
        cls.inventaire = charger(Depot(cls.racine))

    def test_la_quarantaine_porte_22_variantes_dans_10_fichiers(self):
        """La mesure sur laquelle toute la mise en page est calibree."""
        self.assertEqual(len(self.inventaire.rayon(QUARANTAINE)), 22)
        self.assertEqual(self.inventaire.fichiers_lus, 10)
        self.assertEqual(self.inventaire.illisibles, ())
        relevees = sum(1 for f in self.inventaire.fiches if f.relevee)
        self.assertEqual((relevees, 22 - relevees), (5, 17))

    def test_la_quarantaine_de_reference_ne_produit_aucun_faux_couple_modale(self):
        """CONTROLE NEGATIF n°4, sur la fixture : retirer la garde `relevee`
        de `comparer` fait tomber ce test.

        La condition du paragraphe « signature du couple modale / porteur » —
        aucun identifiant commun ET des fenetres citees disjointes — est
        satisfaite par 117 paires de cette quarantaine, dont SIX dans le seul
        `_______.yaml`. Aucune ne survit a la garde : les 117 ont au moins une
        esquisse. Le faux positif serait quotidien.
        """
        fiches = self.inventaire.rayon(QUARANTAINE)
        declencheraient = [
            (a, b) for a, b in itertools.combinations(fiches, 2)
            if not ({c.id for c in a.variante.champs}
                    & {c.id for c in b.variante.champs})
            and a.fenetres and b.fenetres
            and not (set(a.fenetres) & set(b.fenetres))]
        self.assertEqual(len(declencheraient), 117)

        survivantes = 0
        for gauche, droite in declencheraient:
            try:
                comparer(gauche, droite)
            except ComparaisonRefusee:
                continue
            survivantes += 1
        self.assertEqual(survivantes, 0)

    def test_le_triplet_vide_porte_les_six_paires_que_le_plan_nomme(self):
        """Cinq esquisses sous `_______.yaml`, deux citant wnd[0] et trois
        wnd[1] : deux fois trois font les six paires."""
        vides = [f for f in self.inventaire.fiches
                 if f.clef.triplet == ("?", "?", "?")]
        self.assertEqual(len(vides), 5)
        self.assertEqual(sorted(f.fenetres for f in vides),
                         [("wnd[0]",), ("wnd[0]",), ("wnd[1]",), ("wnd[1]",),
                          ("wnd[1]",)])
        paires = [(a, b) for a, b in itertools.combinations(vides, 2)
                  if not (set(a.fenetres) & set(b.fenetres))]
        self.assertEqual(len(paires), 6)

    def test_les_comptes_rendus_sont_invisibles_du_depot_et_listes_a_part(self):
        """`Depot` globe `racine/*.yaml` sans recursion : `rapports/` lui
        echappe, et c'est pour cela qu'il peut vivre la."""
        depot = Depot(self.racine)
        self.assertNotIn(DOSSIER_RAPPORTS, [c.name for c in depot.fichiers()])
        conserves = rapports(depot)
        self.assertEqual(len(conserves), 1)
        self.assertEqual(conserves[0].suffix, ".txt")
        self.assertIn("cartographie de", conserves[0].read_text(
            encoding="utf-8"))


class TestLesRapports(unittest.TestCase):

    def test_du_plus_recent_au_plus_vieux(self):
        """CONTROLE NEGATIF : retirer `reverse=True` fait tomber ce test."""
        racine = _bac()
        dossier = racine / DOSSIER_RAPPORTS
        dossier.mkdir(parents=True)
        for nom in ("2026-09-09T16-05-12-a.vbs.txt",
                    "2026-09-11T18-10-54-b.vbs.txt",
                    "2026-09-10T09-22-31-c.vbs.txt"):
            (dossier / nom).write_text("x", encoding="utf-8")
        self.assertEqual([c.name for c in rapports(Depot(racine))],
                         ["2026-09-11T18-10-54-b.vbs.txt",
                          "2026-09-10T09-22-31-c.vbs.txt",
                          "2026-09-09T16-05-12-a.vbs.txt"])

    def test_le_rang_de_collision_se_range_apres_son_frere(self):
        """`cartographie._conserver` suffixe `_2` sur une collision : c'est le
        plus RECENT des deux, et le tri doit le sortir en premier."""
        racine = _bac()
        dossier = racine / DOSSIER_RAPPORTS
        dossier.mkdir(parents=True)
        for nom in ("2026-09-11T18-10-54-a.vbs.txt",
                    "2026-09-11T18-10-54-a.vbs_2.txt"):
            (dossier / nom).write_text("x", encoding="utf-8")
        self.assertEqual(rapports(Depot(racine))[0].name,
                         "2026-09-11T18-10-54-a.vbs_2.txt")

    def test_sans_dossier_il_n_y_a_pas_de_rapport(self):
        self.assertEqual(rapports(Depot(_bac())), ())

    def test_le_dossier_est_celui_que_la_cartographie_ecrit(self):
        """Les deux constantes sont RECOPIEES, pas partagees : `catalogue` ne
        connait pas `commandes`, et l'y faire dependre inverserait la seule
        direction que le depot tienne. Ce test les apparie."""
        self.assertEqual(I.DOSSIER_RAPPORTS, DOSSIER_RAPPORTS)


class TestLeDepotLitUneSeuleFois(unittest.TestCase):

    def setUp(self):
        self.racine = _bac()
        depot = Depot(self.racine)
        depot.enregistrer(variante_de(_ecran(IA08, Champ(id="wnd[0]/a"))))
        depot.enregistrer(variante_de(_ecran(IH06, Champ(id="wnd[0]/b"))))

    def test_contenu_rend_le_triplet_ET_les_variantes_en_une_lecture(self):
        """CONTROLE NEGATIF : reecrire `charger` avec `triplets()` puis
        `variantes(triplet)` fait doubler ce compte."""
        lectures: list[Path] = []
        vrai = Depot._lire_fichier

        class Compteur(Depot):
            @staticmethod
            def _lire_fichier(chemin: Path) -> dict:
                lectures.append(chemin)
                return vrai(chemin)

        depot = Compteur(self.racine)
        for chemin in depot.fichiers():
            triplet, variantes = depot.contenu(chemin)
            self.assertEqual(len(variantes), 1)
            self.assertEqual(len(triplet), 3)
        self.assertEqual(len(lectures), 2)

    def test_fichiers_ne_descend_pas_dans_les_sous_dossiers(self):
        """La quarantaine est un sous-dossier du cure, et `rapports/` en est
        un autre. Un glob recursif ferait entrer les captures non relues dans
        le catalogue cure."""
        Depot(self.racine).mettre_en_quarantaine(
            variante_de(_ecran(IA08, Champ(id="wnd[0]/z"))))
        noms = [c.name for c in Depot(self.racine).fichiers()]
        self.assertEqual(len(noms), 2)

    def test_contenu_lit_le_fichier_qu_on_lui_DONNE(self):
        """CONTROLE NEGATIF : recomposer le nom depuis le triplet lu fait
        tomber ce test.

        Un fichier renomme a la main, ou recopie d'un autre catalogue, reste
        lisible ici ; `variantes(triplet)` chercherait un nom qui n'existe pas
        et rendrait un tuple vide — un catalogue ampute, d'aspect normal.
        """
        depot = Depot(self.racine)
        original = depot.fichiers()[0]
        renomme = original.parent / "PORTE_UN_AUTRE_NOM.yaml"
        original.rename(renomme)
        triplet, variantes = depot.contenu(renomme)
        self.assertEqual(len(variantes), 1)
        self.assertEqual(depot.variantes(triplet), ())

    def test_un_fichier_absent_leve_plutot_que_de_rendre_le_vide(self):
        with self.assertRaises((CatalogueInvalide, OSError)):
            Depot(self.racine).contenu(self.racine / "rien.yaml")


class TestLaDureeEtLHorloge(unittest.TestCase):

    def test_l_horloge_est_injectee_et_la_duree_en_millisecondes(self):
        """Sans injection, l'ecran d'accueil afficherait une duree qu'aucun
        test ne pourrait asserter sans devenir instable."""
        racine = _bac()
        Depot(racine).enregistrer(variante_de(_ecran(IA08,
                                                     Champ(id="wnd[0]/a"))))
        tics = iter([10.0, 10.4])
        inventaire = charger(Depot(racine), horloge=lambda: next(tics))
        self.assertEqual(inventaire.duree_ms, 400)


class TestLeModeleNeProduitAucunTexte(unittest.TestCase):

    def test_aucune_fonction_du_module_ne_rend_une_ligne_prete_a_afficher(self):
        """La regle qui tient le partage honnete : `« 2 id. »`, `« ? »` et
        « 22 variante(s) » sont composes par la vue, qui seule a mesure
        l'ecran. Un modele qui rendrait des chaines toutes faites deciderait
        de la mise en page depuis un module qui n'a jamais vu la fenetre.

        Le controle porte sur les litteraux HORS docstring : les docstrings de
        ce module citent abondamment ce que l'ecran affichera, et c'est leur
        role. Ce qu'on interdit, c'est qu'une VALEUR rendue par ce module porte
        du decor — les guillemets de citation et la marque de coupe — parce
        que ce serait une mise en page decidee par un module qui n'a jamais
        mesure la fenetre.

        CONTROLE NEGATIF : ajouter `return f"{n} ch"` quelque part dans
        `inventaire.py` fait tomber ce test.
        """
        arbre = ast.parse(Path(I.__file__).read_text(encoding="utf-8"))
        docstrings = set()
        for noeud in ast.walk(arbre):
            corps = getattr(noeud, "body", None)
            if not isinstance(noeud, (ast.Module, ast.ClassDef,
                                      ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if (corps and isinstance(corps[0], ast.Expr)
                    and isinstance(corps[0].value, ast.Constant)
                    and isinstance(corps[0].value.value, str)):
                docstrings.add(id(corps[0].value))

        litteraux = [n.value for n in ast.walk(arbre)
                     if isinstance(n, ast.Constant)
                     and isinstance(n.value, str)
                     and id(n) not in docstrings]
        self.assertTrue(litteraux,
                        "aucun litteral : le test ne verifierait rien")
        for litteral in litteraux:
            for decor in ("«", "»", "~"):
                with self.subTest(litteral=litteral, decor=decor):
                    self.assertNotIn(decor, litteral)


class TestAuCureCompareLaCLEF(unittest.TestCase):
    """L'empreinte seule ne designe pas un ecran, et s'en contenter cachait
    une ligne de la file de decisions."""

    def setUp(self):
        self.racine = _bac()
        depot = Depot(self.racine)
        # MEME identifiant des deux cotes, donc MEME empreinte : elle vaut
        # `empreinte(c.id for c in ecran.champs)` et ne depend pas du triplet.
        depot.enregistrer(variante_de(_ecran(
            IH06, Champ(id="wnd[1]/usr/btnOK"), titre="au cure")))
        self.esquisse = variante_de(
            _ecran(Identite(transaction="?", programme="?", dynpro="?"),
                   Champ(id="wnd[1]/usr/btnOK")), source=ESQUISSE)
        depot.mettre_en_quarantaine(self.esquisse)
        self.inventaire = charger(Depot(self.racine))

    def test_les_deux_cotes_portent_bien_la_MEME_empreinte(self):
        """La precondition de tout le reste, mesuree et pas supposee."""
        empreintes = {f.clef.empreinte for f in self.inventaire.fiches}
        self.assertEqual(len(empreintes), 1)
        triplets = {f.clef.triplet for f in self.inventaire.fiches}
        self.assertEqual(len(triplets), 2)

    def test_une_collision_d_empreinte_ne_marque_PAS_au_cure(self):
        """CONTROLE NEGATIF : revenir a `au_cure=fiche.clef.empreinte in
        empreintes_du_cure` fait tomber ce test.

        `Depot.promouvoir` prend une `ClefVariante` entiere ; comparer les
        empreintes seules affirmerait « cet ecran est deja au cure » sur un
        ecran qui n'y est pas.
        """
        quarantaine = self.inventaire.rayon(QUARANTAINE)
        self.assertEqual(len(quarantaine), 1)
        self.assertFalse(quarantaine[0].au_cure)

    def test_et_la_ligne_SURVIT_au_filtre_reste_a_decider(self):
        """Le vrai prix de la faute : la ligne s'evaporait de la file.

        Les cinq esquisses de `_______.yaml` de la quarantaine de reference
        portent toutes le triplet ('?', '?', '?') : le cas n'a rien de
        theorique.
        """
        trouvailles, total = filtrer(self.inventaire,
                                     Critere(a_decider=True))
        self.assertEqual(total, 1)
        self.assertEqual(len(trouvailles), 1)


class TestLaComparaisonRefuseDeuxEcransDifferents(unittest.TestCase):

    def _fiche(self, identite, *champs, source="observee"):
        return Fiche(variante=variante_de(_ecran(identite, *champs),
                                          source=source),
                     rayon=QUARANTAINE, fichier=Path("x.yaml"))

    def test_comparer_refuse_deux_triplets_DIFFERENTS(self):
        """CONTROLE NEGATIF : retirer la garde de triplet de `comparer` fait
        tomber ce test.

        Sans elle, `m` sur IH06/SAPLIH06/1000 puis `m` sur IW39/SAPLIW39/1000
        puis `d` rend une comparaison que l'ecran titre du seul triplet de
        GAUCHE — celui de droite n'apparait nulle part — et dont les deux faits
        mesures, aucun identifiant commun et fenetres disjointes, sont ce que
        deux ecrans sans rapport donnent presque toujours. Le paragraphe
        « signature du couple modale / porteur » s'affiche alors en entier,
        alors qu'il decrit une modale posee sur SON porteur, donc UN triplet.
        """
        gauche = self._fiche(IH06, Champ(id="wnd[0]/usr/ctxtIH06X"))
        droite = self._fiche(
            Identite(transaction="IW39", programme="SAPLIW39", dynpro="1000"),
            Champ(id="wnd[1]/usr/btnOK"))
        with self.assertRaises(ComparaisonRefusee) as refus:
            comparer(gauche, droite)
        self.assertIn("IH06/SAPLIH06/1000", str(refus.exception))
        self.assertIn("IW39/SAPLIW39/1000", str(refus.exception))
        self.assertIn("MEME ecran", str(refus.exception))

    def test_le_meme_triplet_reste_comparable(self):
        """Et la garde ne doit pas tout interdire : c'est le geste que la
        fiche recommande quand elle nomme une voisine."""
        gauche = self._fiche(IH06, Champ(id="wnd[0]/usr/a"))
        droite = self._fiche(IH06, Champ(id="wnd[0]/usr/b"))
        mesure = comparer(gauche, droite)
        self.assertEqual(mesure.communs, ())
        self.assertEqual(mesure.seuls_a_gauche, ("wnd[0]/usr/a",))


class TestLeDenominateurDeLaRecherche(unittest.TestCase):
    """« n sur N » : les deux comptes doivent compter la meme chose."""

    def setUp(self):
        self.racine = _bac()
        depot = Depot(self.racine)
        commun = _ecran(IH06, Champ(id="wnd[0]/usr/ctxtWERKS-LOW",
                                    type="GuiCTextField", texte="Division"))
        depot.enregistrer(variante_de(commun))
        depot.mettre_en_quarantaine(variante_de(commun))
        depot.mettre_en_quarantaine(variante_de(_ecran(
            IA08, Champ(id="wnd[0]/usr/ctxtWERKS-HIGH",
                        type="GuiCTextField", texte="Division"))))
        self.inventaire = charger(depot)

    def test_parcourues_applique_le_MEME_filtre_que_filtrer(self):
        """CONTROLE NEGATIF : faire rendre `inventaire.rayon(critere.rayon)` a
        `parcourues` fait tomber ce test.

        Le denominateur valait `len(inventaire.rayon(rayon))`, qui ignore
        `a_decider` : l'ecran ecrivait « 1 trouvee(s) sur 2 variante(s)
        relues » alors qu'une seule avait ete regardee. « le motif est rare »
        au lieu de « il est partout » — deux comptes qui ne comptent pas la
        meme chose.
        """
        critere = Critere(motif="werks", portee=CHAMP, a_decider=True)
        self.assertEqual(len(I.parcourues(self.inventaire, critere)), 1)
        self.assertEqual(len(self.inventaire.rayon(QUARANTAINE)), 2)
        _, total = filtrer(self.inventaire, critere)
        self.assertEqual(total, 1)

    def test_sans_a_decider_le_denominateur_est_le_rayon_entier(self):
        critere = Critere(motif="werks", portee=CHAMP)
        self.assertEqual(len(I.parcourues(self.inventaire, critere)), 2)


class TestCeQueLaRechercheDECRAN_annonce(unittest.TestCase):

    def test_l_appariement_d_ecran_LIT_la_constante_annoncee(self):
        """CONTROLE NEGATIF : recopier la liste a la main dans
        `_apparie_ecran` fait tomber ce test.

        La constante etait un export que personne ne lisait, sous un
        commentaire qui affirmait deux choses fausses : que l'ecran l'annonce,
        et qu'elle empeche la divergence. `_apparie_ecran` recopiait la liste
        a la main ; ajouter un attribut a la constante n'aurait rien change et
        n'aurait rien leve.
        """
        fiche = Fiche(
            variante=variante_de(_ecran(IH06, Champ(id="wnd[0]/usr/a"),
                                        titre="Liste multi-niveaux")),
            rayon=QUARANTAINE, fichier=Path("x.yaml"))
        inventaire = I.Inventaire(fiches=(fiche,))
        valeurs = {"transaction": "ih06", "programme": "saplih06",
                   "dynpro": "1000", "empreinte": fiche.clef.empreinte,
                   "titre": "multi-niveaux"}
        self.assertEqual(set(valeurs), set(I.CHERCHE_DANS_ECRAN))
        for attribut, motif in valeurs.items():
            with self.subTest(attribut=attribut):
                _, total = filtrer(inventaire, Critere(motif=motif))
                self.assertEqual(total, 1)

    def test_un_attribut_que_personne_ne_porte_est_REFUSE_et_pas_ignore(self):
        """Un attribut annonce sur lequel rien n'apparie serait une ligne
        d'ecran qui affirme plus que ce que le code fait."""
        fiche = Fiche(
            variante=variante_de(_ecran(IH06, Champ(id="wnd[0]/usr/a"))),
            rayon=QUARANTAINE, fichier=Path("x.yaml"))
        ancienne = I.CHERCHE_DANS_ECRAN
        I.CHERCHE_DANS_ECRAN = (*ancienne, "couleur_des_rideaux")
        try:
            with self.assertRaises(AttributeError):
                filtrer(I.Inventaire(fiches=(fiche,)), Critere(motif="zz"))
        finally:
            I.CHERCHE_DANS_ECRAN = ancienne


class TestLOrdreDesFiches(unittest.TestCase):

    def test_l_ordre_est_stable_et_ne_suit_pas_le_glob(self):
        """CONTROLE NEGATIF : retirer le `fiches.sort(...)` de `charger` fait
        tomber ce test.

        Les lignes de la liste sont numerotees dans cet ordre, et `<n>`,
        `m <n>` et `p` designent par ce numero. Un ordre de glob changerait
        la numerotation d'un poste a l'autre — et un numero note sur un
        papier designerait une autre variante.
        """
        racine = _bac()
        depot = Depot(racine)
        for transaction in ("IW39", "IA08", "IH06"):
            depot.mettre_en_quarantaine(variante_de(_ecran(
                Identite(transaction=transaction, programme="SAPLX",
                         dynpro="1000"),
                Champ(id=f"wnd[0]/usr/{transaction}"))))
        depot.enregistrer(variante_de(_ecran(
            Identite(transaction="ZZZ", programme="SAPLX", dynpro="1000"),
            Champ(id="wnd[0]/usr/z"))))
        fiches = charger(Depot(racine)).fiches
        self.assertEqual([(f.rayon, f.clef.transaction) for f in fiches],
                         [("cure", "ZZZ"), ("quarantaine", "IA08"),
                          ("quarantaine", "IH06"), ("quarantaine", "IW39")])


class TestLaTroncatureDeLaPorteeECRAN(unittest.TestCase):

    def test_la_branche_ECRAN_tronque_elle_aussi_et_rend_le_vrai_total(self):
        """CONTROLE NEGATIF : retirer le `if len(retenues) < limite` de la
        branche ECRAN fait tomber ce test.

        Seule la branche CHAMP etait exercee. Une branche qui ne tronque pas
        rendrait la limite sans effet, et l'appelant qui compte sur elle
        materialiserait tout.
        """
        racine = _bac()
        depot = Depot(racine)
        for rang in range(4):
            depot.mettre_en_quarantaine(variante_de(_ecran(
                Identite(transaction=f"T{rang}", programme="SAPLX",
                         dynpro="1000"),
                Champ(id=f"wnd[0]/usr/x{rang}"))))
        trouvailles, total = filtrer(charger(Depot(racine)), Critere(),
                                     limite=2)
        self.assertEqual(len(trouvailles), 2)
        self.assertEqual(total, 4)


class TestLeChampSourceNExistePlus(unittest.TestCase):

    def test_Critere_ne_porte_AUCUN_champ_source(self):
        """Un chemin de code que ne couvre aucun test, et qui portait sa
        propre classe de defaut.

        Aucun appelant de `falcon/` ne le renseignait, aucune touche ne
        l'atteignait, `__post_init__` ne le validait pas — donc
        `Critere(source="observe")`, a une lettre pres du mot attendu, rendait
        une liste VIDE en silence : un refus deguise en resultat. Le jour ou
        la touche existe, le champ revient avec sa validation et son test.
        """
        self.assertNotIn("source", Critere.__dataclass_fields__)
        with self.assertRaises(TypeError):
            Critere(source="observee")


if __name__ == "__main__":
    unittest.main()
