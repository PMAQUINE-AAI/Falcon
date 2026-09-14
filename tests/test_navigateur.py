"""Le navigateur de catalogue : ce qu'il montre, et ce qu'il REFUSE de montrer.

Trois proprietes portent ce lot, et aucune n'est cosmetique.

**La hauteur est une contrainte au meme titre que la largeur.** Le rendu
reaffiche tout a chaque tour et ne repositionne jamais rien : une vue plus
haute que la fenetre fait defiler son propre en-tete, et l'invite apparait sous
un tableau dont on ne voit plus de quel rayon il vient. La pagination est donc
calculee — `(lignes - chrome) // cout` — et jamais constante. Une constante de
vingt lignes, celle que les maquettes suggerent parce qu'elles sont dessinees
sur une grande fenetre, donne SIX champs de trop sur le cmd.exe par defaut.

**Aucune vue ne concatene a la main.** `PeintreNu` coupe la ligne entiere en
dernier recours : une rangee composee a la main ne deborde donc pas, elle perd
sa DERNIERE colonne, en silence, et la ligne garde l'aspect d'une ligne
complete. Le test de propriete verifie qu'aucun bloc ne depasse la largeur
AVANT le peintre — c'est-a-dire que le filet du peintre ne sert jamais.

**La promotion n'est pas un lot.** Un mot tape ne peut pas certifier N ecrans
que personne n'a lus. `garde_de_la_promotion` refuse de promouvoir ce qui n'a
pas ete affiche, et `p` n'existe que dans la fiche ouverte.

Chaque test nomme, dans sa docstring, la ligne de production a casser pour le
faire tomber.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from falcon.catalogue import (
    ESQUISSE, QUARANTAINE, Critere, Depot, Fiche, charger, comparer, filtrer,
    variante_de,
)
from falcon.console import navigateur as N
from falcon.console import racine
from falcon.console.ecrans import Environnement
from falcon.console.menu import CONTINUER, Menu
from falcon.noyau import Champ, Ecran, Identite
from falcon.toile import (
    ENTETE, LIGNE, MARQUE, MESUREE, SEPARATEUR, VIDE, Bloc, Capacites, Gabarit,
    PeintreNu, gabarit_pour, peintre_pour, texte_nu,
)

from tests.test_console import Journal

#: Les fenetres a couvrir. (79, 24) est le cmd.exe par defaut moins la colonne
#: de marge ; (79, 25) est celle que le plan nomme pour le controle negatif ;
#: (40, 16) est le plancher de largeur, ou la plupart des vues ne tiennent plus
#: et doivent le DIRE.
GABARITS = (
    Gabarit(colonnes=79, lignes=24, source=MESUREE),
    Gabarit(colonnes=79, lignes=25, source=MESUREE),
    Gabarit(colonnes=79, lignes=50, source=MESUREE),
    Gabarit(colonnes=110, lignes=30, source=MESUREE),
    Gabarit(colonnes=40, lignes=16, source=MESUREE),
)

IH06 = Identite(transaction="IH06", programme="SAPLIH06", dynpro="1000")

#: Un champ dont chaque attribut deborde largement la plus grande fenetre de la
#: matrice. C'est la fixture du test de propriete.
TROP_LONG = "x" * 200


def _ecran(identite: Identite, *champs: Champ, titre: str = "") -> Ecran:
    return Ecran(identite=identite, champs=champs, titre=titre,
                 capture_le="2026-09-11T18:10:54.370Z")


def _fiche(*champs: Champ, titre: str = "Liste multi-niveaux",
           rayon: str = QUARANTAINE, source: str = "observee",
           au_cure: bool = False, identite: Identite = IH06) -> Fiche:
    return Fiche(variante=variante_de(_ecran(identite, *champs, titre=titre),
                                      source=source),
                 rayon=rayon, fichier=Path("quarantaine/IH06.yaml"),
                 au_cure=au_cure)


def _champs(combien: int, *, type_: str = "GuiCTextField") -> tuple[Champ, ...]:
    return tuple(Champ(id=f"wnd[0]/usr/ctxtCHAMP-{rang:02d}", type=type_,
                       texte=f"libelle {rang}", modifiable=True)
                 for rang in range(combien))


def _champs_demesures(combien: int) -> tuple[Champ, ...]:
    return tuple(Champ(id=f"wnd[0]/usr/{TROP_LONG}-{rang:02d}",
                       type=TROP_LONG, soustype=TROP_LONG, nom=TROP_LONG,
                       texte=TROP_LONG, infobulle=TROP_LONG, modifiable=True)
                 for rang in range(combien))


def _bac() -> Path:
    return Path(tempfile.mkdtemp())


def _inventaire_jetable(nombre: int = 30):
    racine_bac = _bac()
    depot = Depot(racine_bac)
    for rang in range(nombre):
        depot.mettre_en_quarantaine(variante_de(_ecran(
            Identite(transaction=f"T{rang:02d}", programme="SAPLX",
                     dynpro="1000"),
            *_champs(3), titre=f"ecran numero {rang}")))
    return depot, charger(depot)


# =========================================================================
# Les vues, une par une
# =========================================================================

def _toutes_les_vues() -> list[tuple[str, object]]:
    """(nom, fabrique) pour chaque vue, AVEC et SANS son bloc conditionnel.

    Le bloc conditionnel est ce qui fait varier le chrome : sans lui la fiche
    tient sept champs sur un cmd.exe, avec lui deux. Une matrice qui ne
    testerait qu'un des deux cas laisserait passer exactement le defaut que la
    pagination calculee existe pour eviter.
    """
    depot, inventaire = _inventaire_jetable()

    fiche = _fiche(*_champs(30))
    fiche_shell = _fiche(*(_champs(29)
                           + (Champ(id="wnd[0]/usr/cntlALV/shellcont/shell",
                                    type="GuiShell", soustype="GridView",
                                    texte="SAP.GridView.1", modifiable=True),)))
    voisine = _fiche(*_champs(4), titre="une autre variante")

    gauche = _fiche(*_champs(12))
    droite = _fiche(*tuple(Champ(id=f"wnd[1]/usr/btn{r}", type="GuiButton")
                           for r in range(9)))
    modale = comparer(gauche, droite)
    meme_fenetre = comparer(gauche, _fiche(*_champs(12, type_="GuiButton")))

    fiches = tuple(t.fiche for t in filtrer(inventaire, Critere())[0])
    trouvailles, total = filtrer(inventaire,
                                 Critere(motif="champ", portee="champ"))

    vue = N.Vue()
    casse = Depot(_bac())
    casse.quarantaine.mkdir(parents=True)
    (casse.quarantaine / "CASSE.yaml").write_text("version: 9\n",
                                                  encoding="utf-8")
    inv_casse = charger(casse)

    return [
        ("accueil sans illisible",
         lambda g: N.vue_accueil(inventaire, g, racine=depot.racine,
                                 comptes_rendus=3)),
        ("accueil avec illisible",
         lambda g: N.vue_accueil(inv_casse, g, racine=casse.racine,
                                 comptes_rendus=0)),
        ("liste pleine", lambda g: N.vue_liste(vue, fiches, len(fiches), g)),
        ("liste vide", lambda g: N.vue_liste(vue, (), 0, g)),
        # Le filtre et l'alerte de troncature ajoutent chacun une ligne de
        # chrome : une matrice qui ne verrait que la liste sans eux laisserait
        # passer exactement le defaut que la pagination calculee evite.
        ("liste filtree",
         lambda g: N.vue_liste(N.Vue(critere=Critere(motif="T0",
                                                     a_decider=True)),
                               fiches, len(fiches), g)),
        ("liste tronquee",
         lambda g: N.vue_liste(vue, fiches, len(fiches) + 100, g)),
        ("fiche sans voisine ni shell",
         lambda g: N.vue_fiche(vue, fiche, (), g)),
        ("fiche avec voisine et shell",
         lambda g: N.vue_fiche(vue, fiche_shell, (voisine,), g)),
        ("champ ordinaire",
         lambda g: N.vue_champ(fiche, fiche.variante.champs[0], g)),
        ("champ GuiShell",
         lambda g: N.vue_champ(fiche_shell, fiche_shell.variante.champs[-1],
                               g)),
        ("comparaison sans bloc modale",
         lambda g: N.vue_comparaison(meme_fenetre, vue, g)),
        ("comparaison avec bloc modale",
         lambda g: N.vue_comparaison(modale, vue, g)),
        ("recherche avec resultats",
         lambda g: N.vue_recherche(trouvailles, total, Critere(motif="champ",
                                                               portee="champ"),
                                   30, vue, g)),
        ("recherche sans resultat",
         lambda g: N.vue_recherche((), 0, Critere(motif="rien",
                                                  portee="champ"),
                                   30, vue, g)),
        ("recherche filtree a decider",
         lambda g: N.vue_recherche(trouvailles, total,
                                   Critere(motif="champ", portee="champ",
                                           a_decider=True), 30, vue, g)),
        ("recherche tronquee",
         lambda g: N.vue_recherche(trouvailles, total + 500,
                                   Critere(motif="champ", portee="champ"),
                                   30, vue, g)),
        ("recherche de portee ECRAN, qui REFUSE",
         lambda g: N.vue_recherche((), 0, Critere(motif="x"), 30, vue, g)),
        ("rapports dont un fichier a disparu",
         lambda g: N.vue_rapports([Path("2026-09-11-t.vbs.txt")], [None],
                                  vue, g)),
        ("champ GuiShell verrouille",
         lambda g: N.vue_champ(
             fiche, Champ(id="wnd[0]/usr/cntlALV/shellcont/shell",
                          type="GuiShell", soustype="GridView",
                          texte="SAP.GridView.1", modifiable=False), g)),
        ("rapports pleins",
         lambda g: N.vue_rapports([Path(f"2026-09-1{r}-t.vbs.txt")
                                   for r in range(9)],
                                  [1024] * 9, vue, g)),
        ("rapports vides", lambda g: N.vue_rapports([], [], vue, g)),
        ("aide", lambda g: N.vue_aide(g)),
    ]


class TestLaGeometrieDesVues(unittest.TestCase):

    def test_la_table_des_hauteurs_dit_ce_que_le_peintre_FAIT(self):
        """`LIGNES_PAR_FORME` duplique une connaissance de `toile/peintre.py`.

        Une vue doit savoir combien de place elle prend AVANT d'avoir un
        peintre, sans quoi la pagination ne se calcule pas. Mais une
        declaration prise pour une mesure est exactement ce que ce depot
        traque : le jour ou l'entete passerait a quatre lignes, chaque vue
        deborderait d'une ligne sans que rien ne leve.

        CONTROLE NEGATIF : ecrire `ENTETE: 2` fait tomber ce test.
        """
        gabarit = Gabarit(colonnes=79, lignes=24, source=MESUREE)
        peintre = PeintreNu()
        for forme, attendu in N.LIGNES_PAR_FORME.items():
            with self.subTest(forme=forme):
                bloc = Bloc(forme=forme)
                self.assertEqual(len(peintre.peindre(bloc, gabarit)), attendu)
        self.assertEqual(set(N.LIGNES_PAR_FORME),
                         {LIGNE, VIDE, SEPARATEUR, ENTETE})

    def test_aucune_vue_ne_deborde_de_la_hauteur(self):
        """CONTROLE NEGATIF n°1 : remplacer, dans `paginer`,
        `par_page = (gabarit.lignes - chrome) // cout` par une constante
        (vingt, celle que suggerent les maquettes) fait tomber ce test — sur la
        fiche comme sur la liste, des (79, 25).

        La matrice couvre chaque vue AVEC et SANS son bloc conditionnel :
        c'est lui qui fait varier le chrome, donc la pagination.
        """
        for nom, fabrique in _toutes_les_vues():
            for gabarit in GABARITS:
                with self.subTest(vue=nom, gabarit=(gabarit.colonnes,
                                                    gabarit.lignes)):
                    rendu = fabrique(gabarit)
                    self.assertLessEqual(N.hauteur(rendu), gabarit.lignes)

    def test_une_vue_qui_ne_tient_pas_REFUSE_au_lieu_d_en_montrer_la_moitie(self):
        """Dans un rendu qui reaffiche tout, une demi-page se lit comme une
        page entiere : rien ne signale la moitie manquante.

        CONTROLE NEGATIF : remplacer le `return None` de `paginer` par
        `par_page = 1` fait tomber ce test — la vue sortirait vingt lignes dans
        une fenetre de seize.
        """
        etroit = Gabarit(colonnes=40, lignes=16, source=MESUREE)
        haut = Gabarit(colonnes=40, lignes=60, source=MESUREE)
        fiche = _fiche(*_champs(30))
        rendu = N.vue_fiche(N.Vue(), fiche, (), etroit)
        texte = "\n".join(texte_nu(b) for b in rendu)
        self.assertIn("ne tient pas", texte)
        self.assertLessEqual(N.hauteur(rendu), etroit.lignes)

        # La VALEUR, et pas seulement l'etiquette : remplacer `{demandees}`
        # par « ? » laissait le test vert, et le refus n'apprenait plus rien.
        # Le nombre attendu est le chrome de la vue plus UN champ, et le
        # chrome se mesure en comptant les lignes de la meme vue rendue sur
        # une fenetre ou tout tient, moins ses trente champs.
        chrome = N.hauteur(N.vue_fiche(N.Vue(), fiche, (), haut)) - 30
        self.assertIn(f"lignes necessaires   {chrome + 1}", texte)
        self.assertIn(f"lignes disponibles   {etroit.lignes}", texte)

    def test_la_pagination_suit_la_hauteur_mesuree(self):
        """La meme fiche tient plus de champs sur une fenetre plus haute. Sans
        cette propriete, la formule pourrait etre n'importe quoi."""
        fiche = _fiche(*_champs(30))
        courtes = N.vue_fiche(N.Vue(), fiche, (),
                              Gabarit(colonnes=79, lignes=24, source=MESUREE))
        longues = N.vue_fiche(N.Vue(), fiche, (),
                              Gabarit(colonnes=79, lignes=50, source=MESUREE))
        self.assertGreater(N.hauteur(longues), N.hauteur(courtes))
        self.assertIn("sur 30", "\n".join(texte_nu(b) for b in courtes))


class TestAucuneVueNeConcatene(unittest.TestCase):
    """Le test de PROPRIETE du lot : nourrir chaque vue de champs demesures."""

    def _vues_demesurees(self):
        fiche = Fiche(
            variante=variante_de(_ecran(
                Identite(transaction=TROP_LONG, programme=TROP_LONG,
                         dynpro=TROP_LONG),
                *_champs_demesures(12), titre=TROP_LONG)),
            rayon=QUARANTAINE, fichier=Path("/" + TROP_LONG + "/x.yaml"))
        autre = Fiche(
            variante=variante_de(_ecran(
                Identite(transaction=TROP_LONG, programme=TROP_LONG,
                         dynpro=TROP_LONG),
                *tuple(Champ(id=f"wnd[1]/{TROP_LONG}-{r}", type=TROP_LONG)
                       for r in range(9)), titre=TROP_LONG)),
            rayon=QUARANTAINE, fichier=Path("/" + TROP_LONG + "/y.yaml"))
        mesure = comparer(fiche, autre)
        vue = N.Vue()
        trouvailles = tuple(N.Trouvaille(fiche=fiche, champ=c)
                            for c in fiche.variante.champs)
        return [
            ("liste", lambda g: N.vue_liste(vue, (fiche, autre), 2, g)),
            ("fiche", lambda g: N.vue_fiche(vue, fiche, (autre,), g)),
            ("champ", lambda g: N.vue_champ(fiche,
                                            fiche.variante.champs[0], g)),
            ("comparaison", lambda g: N.vue_comparaison(mesure, vue, g)),
            ("recherche",
             lambda g: N.vue_recherche(trouvailles, len(trouvailles),
                                       Critere(motif=TROP_LONG,
                                               portee="champ"), 2, vue, g)),
            ("rapports",
             lambda g: N.vue_rapports([Path(TROP_LONG + ".txt")], [1], vue,
                                      g)),
        ]

    def test_aucun_bloc_ne_depasse_la_largeur_AVANT_le_peintre(self):
        """C'est la forme utile de « aucune vue ne concatene a la main ».

        `PeintreNu` coupe la ligne entiere en dernier recours : une rangee
        composee a la main ne DEBORDE donc pas, elle perd sa derniere colonne
        en silence, et la ligne garde l'aspect d'une ligne complete. Mesurer
        apres le peintre ne verrait rien. On mesure donc AVANT : le filet du
        peintre ne doit jamais servir.

        CONTROLE NEGATIF : remplacer une rangee par une f-string — par exemple
        `texte(g, f"empreinte   {fiche.clef.empreinte}   {fiche.variante.titre}")`
        dans `vue_fiche` — fait tomber ce test sur la fixture demesuree.
        """
        for nom, fabrique in self._vues_demesurees():
            for gabarit in GABARITS:
                with self.subTest(vue=nom, largeur=gabarit.colonnes):
                    for bloc in fabrique(gabarit):
                        retrait = bloc.marge + (2 if bloc.forme == ENTETE
                                                else 0)
                        self.assertLessEqual(
                            retrait + len(texte_nu(bloc)), gabarit.colonnes,
                            f"{nom} : « {texte_nu(bloc)} »")

    def test_la_troncature_se_VOIT(self):
        """Une vue qui perdrait du contenu sans marque serait indiscernable
        d'une vue dont la donnee est courte."""
        for nom, fabrique in self._vues_demesurees():
            with self.subTest(vue=nom):
                # Une fenetre assez HAUTE pour que chaque vue se peigne :
                # une vue qui refuse faute de place ne tronque rien, et le
                # test ne mesurerait alors que le refus.
                haute = Gabarit(colonnes=79, lignes=60, source=MESUREE)
                lignes = [texte_nu(b) for b in fabrique(haute)]
                self.assertTrue(any(MARQUE in ligne for ligne in lignes),
                                f"{nom} n'a pose aucune marque de coupe")

    def test_apres_le_peintre_aucune_ligne_ne_depasse_non_plus(self):
        peintre = PeintreNu()
        for nom, fabrique in self._vues_demesurees():
            for gabarit in GABARITS:
                with self.subTest(vue=nom, largeur=gabarit.colonnes):
                    for bloc in fabrique(gabarit):
                        for ligne in peintre.peindre(bloc, gabarit):
                            self.assertLessEqual(len(ligne), gabarit.colonnes)


class TestLaLargeurEstUneContrainteAuMemeTitreQueLaHauteur(unittest.TestCase):
    """La hauteur avait un refus ; la largeur n'en avait AUCUN."""

    def test_aucune_vue_ne_LEVE_sous_le_plancher_de_largeur(self):
        """CONTROLE NEGATIF : retirer l'appel a `gabarit.trop_etroit` en tete
        des vues fait tomber ce test.

        Mesure, par balayage avant correction : a 30 colonnes `vue_liste`,
        `vue_fiche`, `vue_champ` et `vue_comparaison` levent
        `ValueError: il reste -2 colonne(s) pour 2 colonne(s) souples` ; a 15
        `vue_rapports` et `vue_aide` ; a 5 l'accueil. `menu.parcourir`
        n'attrape rien et `ERREURS_LISIBLES` de `principal.py` ne contient pas
        `ValueError` : l'utilisateur qui a retreci sa fenetre recevait une
        trace de pile et perdait sa session de console. La matrice de test
        s'arretait pile sur (40, 16), c'est-a-dire sur la derniere valeur qui
        marche.
        """
        peintre = PeintreNu()
        for largeur in range(N.LARGEUR_PLANCHER - 1, 4, -1):
            gabarit = Gabarit(colonnes=largeur, lignes=24, source=MESUREE)
            for nom, fabrique in _toutes_les_vues():
                with self.subTest(vue=nom, largeur=largeur):
                    rendu = fabrique(gabarit)
                    self.assertLessEqual(N.hauteur(rendu), gabarit.lignes)
                    for bloc in rendu:
                        for ligne in peintre.peindre(bloc, gabarit):
                            self.assertLessEqual(len(ligne), gabarit.colonnes)

    def test_le_refus_DIT_la_largeur_mesuree_et_celle_qu_il_faut(self):
        """Un refus qui ne dit pas de combien on manque n'apprend rien."""
        rendu = N.vue_liste(N.Vue(), (), 0,
                            Gabarit(colonnes=30, lignes=24, source=MESUREE))
        rendu = "\n".join(texte_nu(b) for b in rendu)
        self.assertIn("trop etroite", rendu)
        self.assertIn("30", rendu)
        self.assertIn(str(N.LARGEUR_PLANCHER), rendu)

    def test_le_refus_ne_se_compose_PAS_par_rangee(self):
        """Sinon il leverait pour la meme raison que ce qu'il refuse.

        C'est le meme piege que `PeintreNu` a deja resolu en bornant ses deux
        retraits : un refus qui passe par `colonnes()` tombe sur le
        `ValueError` qu'il existe pour eviter.
        """
        for largeur in (1, 2, 3):
            with self.subTest(largeur=largeur):
                gabarit = Gabarit(colonnes=largeur, lignes=24, source=MESUREE)
                rendu = N.trop_etroit(gabarit)
                for bloc in rendu:
                    for ligne in PeintreNu().peindre(bloc, gabarit):
                        self.assertLessEqual(len(ligne), largeur)


class TestAucuneValeurNeDeformeLaPage(unittest.TestCase):
    """Un `\\n` ou un `\\t` dans une donnee du catalogue traverse tout."""

    def _fiche_a_controles(self) -> Fiche:
        return Fiche(
            variante=variante_de(_ecran(
                Identite(transaction="IH06\tX", programme="SAPL\nIH06",
                         dynpro="1000"),
                Champ(id="wnd[0]/usr/a\tb", type="Gui\nTextField",
                      soustype="Grid\rView", nom="n\tom",
                      texte="premiere\nseconde", infobulle="a\r\nb",
                      modifiable=True),
                titre="premiere\nseconde")),
            rayon=QUARANTAINE, fichier=Path("quarantaine/a\tb.yaml"))

    def test_le_depot_rend_bien_ces_caracteres_tels_quels(self):
        """La precondition, mesuree : `charger` ne les refuse ni ne les
        nettoie, et `illisibles` reste vide."""
        depot = Depot(_bac())
        depot.mettre_en_quarantaine(variante_de(_ecran(
            IH06, Champ(id="wnd[0]/usr/a", texte="col1\tcol2"),
            titre="premiere\nseconde")))
        inventaire = charger(depot)
        self.assertEqual(inventaire.illisibles, ())
        fiche = inventaire.rayon(QUARANTAINE)[0]
        self.assertIn("\n", fiche.variante.titre)
        self.assertIn("\t", fiche.variante.champs[0].texte)

    def test_aucune_ligne_rendue_ne_porte_un_caractere_de_controle(self):
        """CONTROLE NEGATIF : retirer `_une_seule_ligne` de `rangee` fait
        tomber ce test.

        Sans lui, `couper` compte un `\\n` pour UNE colonne et
        `LIGNES_PAR_FORME` compte le bloc pour UNE ligne : la rangee sort sur
        deux lignes physiques dont la seconde commence en colonne zero,
        `hauteur()` sous-compte, `paginer` calcule une page qui ne tient pas,
        et l'en-tete qui dit sur quel rayon on est defile hors de l'ecran. Un
        `\\t` occupe en outre jusqu'a huit colonnes a l'affichage.
        """
        fiche = self._fiche_a_controles()
        champ = fiche.variante.champs[0]
        vue = N.Vue()
        vues = [
            ("liste", lambda g: N.vue_liste(vue, (fiche,), 1, g)),
            ("fiche", lambda g: N.vue_fiche(vue, fiche, (), g)),
            ("champ", lambda g: N.vue_champ(fiche, champ, g)),
            ("recherche",
             lambda g: N.vue_recherche((N.Trouvaille(fiche=fiche,
                                                     champ=champ),), 1,
                                       Critere(motif="a", portee="champ"),
                                       1, vue, g)),
        ]
        peintre = PeintreNu()
        for nom, fabrique in vues:
            for gabarit in GABARITS:
                with self.subTest(vue=nom, gabarit=(gabarit.colonnes,
                                                    gabarit.lignes)):
                    for bloc in fabrique(gabarit):
                        for ligne in peintre.peindre(bloc, gabarit):
                            self.assertFalse(
                                any(ord(c) < 32 for c in ligne),
                                f"{nom} : « {ligne!r} »")
                            self.assertLessEqual(len(ligne), gabarit.colonnes)

    def test_le_recollement_se_VOIT(self):
        """Un espace ferait passer deux lignes pour une phrase."""
        self.assertEqual(N._une_seule_ligne("a\nb"), "a · b")
        self.assertEqual(N._une_seule_ligne("a\r\nb"), "a · b")
        self.assertEqual(N._une_seule_ligne("a\tb"), "a b")


class TestLaCoupeDesIdentifiants(unittest.TestCase):

    def test_deux_identifiants_coupes_restent_distincts(self):
        """CONTROLE NEGATIF n°2 : faire couper `couper_chemin` a DROITE — ou
        lui retirer sa marque — fait tomber ce test.

        `wnd[0]/usr/ctxtWERKS-LOW` et `wnd[0]/usr/ctxtWERKS-HIGH` coupes a
        droite donnent la meme chaine, d'aspect complet. L'un est la borne
        basse d'un intervalle, l'autre la haute, et la confusion se recopie
        dans une pipeline — c'est SAP qui la decouvre.
        """
        # Les deux champs sont IDENTIQUES hors identifiant : sans cela, la
        # colonne « libelle » les distinguerait toute seule et le test
        # resterait vert avec une coupe a droite — c'est-a-dire qu'il ne
        # prouverait rien de la coupe.
        fiche = _fiche(
            Champ(id="wnd[0]/usr/subSOUS_ECRAN/ctxtWERKS-LOW",
                  type="GuiCTextField", texte="Division", modifiable=True),
            Champ(id="wnd[0]/usr/subSOUS_ECRAN/ctxtWERKS-HIGH",
                  type="GuiCTextField", texte="Division", modifiable=True))
        rendu = N.vue_fiche(N.Vue(), fiche, (),
                            Gabarit(colonnes=40, lignes=40, source=MESUREE))
        lignes = [texte_nu(b) for b in rendu]
        # Le numero de rang est retire : il distingue les lignes sans rien
        # dire de l'identifiant, et c'est justement ce qu'on mesure ici.
        interessantes = [l.split(None, 1)[1]
                         for l in lignes if "GuiCTextField" in l]
        self.assertEqual(len(interessantes), 2, lignes)
        self.assertNotEqual(interessantes[0], interessantes[1],
                            "les deux bornes d'un intervalle sont devenues la "
                            "meme ligne, d'aspect complet")
        # La marque est assertee sur la CELLULE d'identifiant, et pas sur la
        # ligne entiere : le `~` que `couper()` pose sur la colonne
        # « libelle » de la MEME ligne satisfaisait l'assertion, donc elle
        # restait verte quand on retirait la marque de `couper_chemin`. Le
        # commentaire ci-dessus avait deja corrige la fixture pour cette raison
        # exacte ; la correction n'etait pas allee jusqu'a l'assertion.
        identifiants = [l.split()[0] for l in interessantes]
        self.assertTrue(all(MARQUE in i for i in identifiants),
                        f"sans marque, la coupe est invisible : {identifiants}")


class TestCeQueLaVueDitEtNeDitPas(unittest.TestCase):

    def test_une_esquisse_compte_en_IDENTIFIANTS_et_pas_en_champs(self):
        """« 2 id. » contre « 12 ch » : deux unites, deux mots.

        CONTROLE NEGATIF : ecrire « ch » dans les deux cas fait tomber ce
        test. Une esquisse porte les identifiants TOUCHES par la trace sur un
        ecran de taille inconnue ; un releve porte les champs PRESENTS.
        """
        relevee = _fiche(*_champs(12))
        esquisse = _fiche(*_champs(2), source=ESQUISSE)
        rendu = "\n".join(texte_nu(b) for b in N.vue_liste(
            N.Vue(), (relevee, esquisse), 2, GABARITS[3]))
        self.assertIn("12 ch", rendu)
        self.assertIn("2 id.", rendu)

    def test_une_variante_sans_fenetre_ecrit_un_point_d_interrogation(self):
        """CONTROLE NEGATIF : ecrire `wnd[0]` faute de mieux fait tomber ce
        test — et c'est l'affirmation que la modale rend dangereuse."""
        muette = _fiche(Champ(id="usr/ctxtSANS_FENETRE"))
        lignes = [texte_nu(b) for b in N.vue_liste(N.Vue(), (muette,), 1,
                                                   GABARITS[3])]
        self.assertNotIn("wnd[", "\n".join(lignes))
        # Sur la ligne de DONNEES, et pas sur le rendu entier : le chrome
        # porte deja deux « ? » — la legende « fen : ... « ? » si aucun ne la
        # nomme » et le pied « ? aide » — donc `assertIn("?", rendu)` ne
        # pouvait PAS echouer. Mesure : `INCONNU = ""` laissait le test vert et
        # blanchissait la colonne.
        donnee = [l for l in lignes if "IH06::SAPLIH06::1000" in l]
        self.assertEqual(len(donnee), 1, lignes)
        # Le caractere LITTERAL, et pas `N.INCONNU` : avec `INCONNU = ""`
        # l'assertion serait vide de sens — `"" in ligne` ne peut pas echouer,
        # et la colonne `fen` deviendrait blanche sans qu'un test bronche.
        self.assertEqual(N.INCONNU, "?")
        self.assertIn("?", donnee[0])

    def test_un_GuiShell_n_affiche_pas_oui_dans_la_colonne_modifiable(self):
        """Le « oui » d'un shell vient du defaut de `couture/sapgui.py`.

        CONTROLE NEGATIF : faire rendre « oui » a `_modifiable` pour un shell
        fait tomber ce test — la colonne donnerait alors a une valeur inscrite
        l'aspect d'une valeur lue.
        """
        shell = Champ(id="wnd[0]/usr/cntlALV/shellcont/shell", type="GuiShell",
                      soustype="GridView", texte="SAP.GridView.1",
                      modifiable=True)
        fiche = _fiche(shell)
        rendu = "\n".join(texte_nu(b) for b in N.vue_fiche(N.Vue(), fiche, (),
                                                            GABARITS[3]))
        self.assertIn("(1)", rendu)
        self.assertIn("n'expose pas", rendu)

    def test_le_detail_d_un_shell_ne_conclut_pas_a_la_place_du_lecteur(self):
        shell = Champ(id="wnd[0]/usr/cntlALV/shellcont/shell", type="GuiShell",
                      soustype="GridView", texte="SAP.GridView.1",
                      modifiable=True)
        rendu = "\n".join(texte_nu(b) for b in N.vue_champ(
            _fiche(shell), shell, Gabarit(colonnes=79, lignes=40,
                                          source=MESUREE)))
        self.assertIn("ne vaut pas preuve", rendu)
        self.assertIn("GridView", rendu)

    def test_le_bloc_modale_ne_parait_que_sur_la_MESURE(self):
        """CONTROLE NEGATIF n°4, vu de l'ecran : retirer la condition
        `aucun_identifiant_commun and fenetres_disjointes` fait tomber ce
        test, et le paragraphe « signature du couple modale / porteur » se
        poserait sur deux variantes qui partagent tous leurs identifiants.
        """
        gauche = _fiche(*_champs(4))
        meme = _fiche(*_champs(4, type_="GuiButton"))
        autre_fenetre = _fiche(*tuple(
            Champ(id=f"wnd[1]/usr/btn{r}", type="GuiButton") for r in range(3)))
        grand = Gabarit(colonnes=79, lignes=60, source=MESUREE)

        sans = "\n".join(texte_nu(b) for b in N.vue_comparaison(
            comparer(gauche, meme), N.Vue(), grand))
        avec = "\n".join(texte_nu(b) for b in N.vue_comparaison(
            comparer(gauche, autre_fenetre), N.Vue(), grand))
        self.assertNotIn("CE QUE FALCON NE SAIT PAS", sans)
        self.assertIn("CE QUE FALCON NE SAIT PAS", avec)
        self.assertIn("PAS sa preuve", avec)

    def test_la_comparaison_affiche_le_cote_sur_CHAQUE_ligne(self):
        """Un groupe coupe entre deux pages laisserait une page entiere
        d'identifiants sans dire de quel cote ils sont : plausible, et faux
        une page sur deux."""
        gauche = _fiche(*_champs(12))
        droite = _fiche(*tuple(Champ(id=f"wnd[1]/usr/btn{r}", type="GuiButton")
                               for r in range(9)))
        rendu = [texte_nu(b) for b in N.vue_comparaison(
            comparer(gauche, droite), N.Vue(page=1),
            Gabarit(colonnes=110, lignes=30, source=MESUREE))]
        items = [l for l in rendu if "ctxtCHAMP" in l or "usr/btn" in l]
        self.assertTrue(items)
        self.assertTrue(all(l.strip().startswith(("gauche", "droite",
                                                  "commun")) for l in items),
                        items)

    def test_le_fichier_illisible_est_nomme_a_l_accueil_et_hors_des_comptes(self):
        casse = Depot(_bac())
        casse.quarantaine.mkdir(parents=True)
        (casse.quarantaine / "IW29__SAPLIW29__0100.yaml").write_text(
            "version: 9\n", encoding="utf-8")
        rendu = "\n".join(texte_nu(b) for b in N.vue_accueil(
            charger(casse), Gabarit(colonnes=79, lignes=40, source=MESUREE),
            racine=casse.racine, comptes_rendus=0))
        self.assertIn("IW29__SAPLIW29__0100.yaml", rendu)
        self.assertIn("n'entrent dans aucun compte", rendu)
        self.assertIn("0 fichier(s) lus", rendu)

    def test_la_liste_vide_ne_se_lit_pas_comme_un_catalogue_vide(self):
        rendu = "\n".join(texte_nu(b) for b in N.vue_liste(
            N.Vue(critere=Critere(motif="introuvable")), (), 0, GABARITS[3]))
        self.assertIn("introuvable", rendu)
        self.assertIn("Aucune variante ici", rendu)

    def test_la_liste_annonce_TOUJOURS_son_filtre(self):
        rendu = "\n".join(texte_nu(b) for b in N.vue_liste(
            N.Vue(), (_fiche(*_champs(2)),), 1, GABARITS[3]))
        self.assertIn("filtre : (aucun)", rendu)


class TestCeQueLesCOMPTES_disent(unittest.TestCase):
    """Chaque nombre affiche compte quelque chose de nommable."""

    def test_la_liste_ecrit_le_TOTAL_et_pas_la_longueur_tronquee(self):
        """CONTROLE NEGATIF : faire ecrire `len(fiches)` a la place de
        `total` dans l'en-tete de `vue_liste` fait tomber ce test.

        Mesure avant correction, sur six cents variantes en quarantaine :
        l'ecran ecrivait « 500 variante(s)   ·   500 relevee(s) » puis
        « page 1/21  —  24 affichee(s) sur 500 ». Les cent dernieres etaient
        invisibles, injoignables par `<n>`, `m <n>` et `p`, et rien ne le
        disait. C'est mot pour mot le defaut que la docstring de `filtrer` dit
        exister pour eviter.
        """
        fiches = tuple(_fiche(*_champs(2),
                              identite=Identite(transaction=f"T{r:03d}",
                                                programme="SAPLX",
                                                dynpro="1000"))
                       for r in range(24))
        rendu = "\n".join(texte_nu(b) for b in N.vue_liste(
            N.Vue(), fiches, 600, GABARITS[0]))
        self.assertIn("600 variante(s)", rendu)
        self.assertIn("576 variante(s) ne sont PAS dans cette liste", rendu)

    def test_la_liste_NE_PASSE_PAS_par_la_limite_par_defaut_de_filtrer(self):
        """CONTROLE NEGATIF : revenir a `limite=500` dans `_fiches_de` fait
        tomber ce test.

        Six cents variantes : avec le defaut de `filtrer`, `_fiches_de` en
        rendait cinq cents et l'ecran affichait cette longueur aux deux
        places. Les cent dernieres n'etaient ni comptees, ni nommees, ni
        joignables par `<n>`, `m <n>` ou `p`. On construit l'inventaire en
        MEMOIRE : six cents fichiers YAML sur disque couteraient une minute
        pour mesurer une borne.
        """
        fiches = tuple(
            Fiche(variante=variante_de(_ecran(
                Identite(transaction=f"T{rang:03d}", programme="SAPLX",
                         dynpro="1000"), Champ(id=f"wnd[0]/usr/x{rang}"))),
                  rayon=QUARANTAINE, fichier=Path(f"q/{rang}.yaml"))
            for rang in range(600))
        inventaire = N.Inventaire(fiches=fiches)
        montrees, total = N._fiches_de(inventaire, N.Vue())
        self.assertEqual(total, 600)
        self.assertEqual(len(montrees), 600,
                         "la pagination doit etre la SEULE troncature")
        rendu = "\n".join(texte_nu(b) for b in N.vue_liste(
            N.Vue(), montrees, total, GABARITS[0]))
        self.assertIn("600 variante(s)", rendu)
        self.assertNotIn("ne sont PAS dans cette liste", rendu)
        self.assertIn("sur 600", rendu)

    def test_la_liste_NON_tronquee_ne_pose_aucune_alerte(self):
        rendu = "\n".join(texte_nu(b) for b in N.vue_liste(
            N.Vue(), (_fiche(*_champs(2)),), 1, GABARITS[0]))
        self.assertNotIn("ne sont PAS dans cette liste", rendu)

    def test_le_compteur_au_cure_ne_ment_pas_sur_le_rayon_CURE(self):
        """`charger` ne pose `au_cure` que sur les fiches de QUARANTAINE.

        Mesure avant correction, sur le rayon CURE : « 3 variante(s)   ·   3
        relevee(s), 0 esquisse(s)   ·   0 deja au cure » pour trois variantes
        qui y sont TOUTES. Le sens du compteur changeait avec l'ecran sans que
        l'etiquette change.
        """
        curees = tuple(_fiche(*_champs(2), rayon="cure") for _ in range(3))
        lignes = [texte_nu(b) for b in N.vue_liste(
            N.Vue(critere=Critere(rayon="cure")), curees, 3, GABARITS[0])]
        synthese = [l for l in lignes if "variante(s)" in l and "esquisse" in l]
        self.assertEqual(len(synthese), 1, lignes)
        self.assertNotIn("au cure", synthese[0])
        quarantaine = (_fiche(*_champs(2), au_cure=True),)
        rendu = "\n".join(texte_nu(b) for b in N.vue_liste(
            N.Vue(), quarantaine, 1, GABARITS[0]))
        self.assertIn("1 aussi au cure", rendu)

    def test_la_colonne_ry_ecrit_Q_plus_quand_la_clef_est_aussi_au_cure(self):
        """CONTROLE NEGATIF : retirer le « + » de `_rayon_court` fait tomber
        ce test.

        `Q+` est une decision nommee dans la maquette — « la meme clef existe
        aussi au cure » — et seul le champ modele etait teste, jamais son
        RENDU.
        """
        lignes = [texte_nu(b) for b in N.vue_liste(
            N.Vue(), (_fiche(*_champs(2), au_cure=True),), 1, GABARITS[3])]
        donnee = [l for l in lignes if "IH06::SAPLIH06::1000" in l][0]
        self.assertIn("Q+", donnee)

    def test_l_accueil_ecrit_la_duree_en_SECONDES(self):
        """CONTROLE NEGATIF : ecrire `{inventaire.duree_ms} s` fait tomber ce
        test — l'accueil annoncerait « 412 s » pour 0.4 s, et c'est le chiffre
        sur lequel quelqu'un decidera si le catalogue est trop gros."""
        depot = Depot(_bac())
        depot.mettre_en_quarantaine(variante_de(_ecran(IH06,
                                                       Champ(id="wnd[0]/a"))))
        tics = iter([0.0, 0.412])
        inventaire = charger(depot, horloge=lambda: next(tics))
        self.assertEqual(inventaire.duree_ms, 412)
        rendu = "\n".join(texte_nu(b) for b in N.vue_accueil(
            inventaire, Gabarit(colonnes=79, lignes=40, source=MESUREE),
            racine=depot.racine, comptes_rendus=0))
        self.assertIn("0.4 s", rendu)
        self.assertNotIn("412 s", rendu)

    def test_l_accueil_dit_combien_d_illisibles_il_ne_NOMME_pas(self):
        """Le COMPTE est toujours exact ; c'est la liste qui se tronque."""
        casse = Depot(_bac())
        casse.quarantaine.mkdir(parents=True)
        for rang in range(N.ILLISIBLES_MONTRES + 2):
            (casse.quarantaine / f"CASSE{rang}.yaml").write_text(
                "version: 9\n", encoding="utf-8")
        rendu = "\n".join(texte_nu(b) for b in N.vue_accueil(
            charger(casse), Gabarit(colonnes=79, lignes=60, source=MESUREE),
            racine=casse.racine, comptes_rendus=0))
        self.assertIn("5 fichier(s) n'ont pas pu etre lus", rendu)
        self.assertIn("et 2 autre(s), non nomme(s) ici faute de place",
                      rendu)

    def test_la_pagination_ne_depasse_JAMAIS_la_derniere_page(self):
        """CONTROLE NEGATIF : retirer le plafond de
        `page = min(max(page, 0), pages - 1)` fait tomber ce test.

        Taper `+` au-dela de la derniere page afficherait « page 7/3 » avec un
        corps vide — un ecran qui dit exister au-dela de ce qu'il porte.
        """
        fiches = tuple(_fiche(*_champs(2),
                              identite=Identite(transaction=f"T{r:02d}",
                                                programme="SAPLX",
                                                dynpro="1000"))
                       for r in range(6))
        lignes = [texte_nu(b) for b in N.vue_liste(N.Vue(page=99), fiches, 6,
                                                   GABARITS[0])]
        pied = [l for l in lignes if l.startswith("page ")]
        self.assertEqual(len(pied), 1, lignes)
        numero, total = pied[0].split()[1].split("/")
        self.assertEqual(numero, total)
        self.assertTrue(any("T0" in l for l in lignes),
                        "la derniere page est vide")

    def test_le_couple_du_pied_de_recherche_cite_la_page_AFFICHEE(self):
        """CONTROLE NEGATIF : remplacer `trouvailles[page.debut]` par
        `trouvailles[0]` fait tomber ce test.

        Sur la page 3, recopier une cible qui n'est plus a l'ecran donnerait un
        couple juste et invisible : la raison etait ECRITE en commentaire et
        rien ne la verifiait.
        """
        fiche = _fiche(*_champs(12))
        trouvailles = tuple(N.Trouvaille(fiche=fiche, champ=c)
                            for c in fiche.variante.champs)
        rendu = "\n".join(texte_nu(b) for b in N.vue_recherche(
            trouvailles, len(trouvailles), Critere(motif="champ",
                                                   portee="champ"),
            1, N.Vue(page=1), GABARITS[0]))
        affichees = [c.id for c in fiche.variante.champs
                     if c.id in rendu.split("classeur attend")[0]]
        self.assertTrue(affichees)
        cible = [l for l in rendu.split("\n") if l.strip().startswith("cible")]
        self.assertEqual(len(cible), 1, rendu)
        self.assertIn(affichees[0].split("/")[-1], cible[0])

    def test_le_denominateur_de_la_recherche_est_ce_qui_a_ete_PARCOURU(self):
        """CONTROLE NEGATIF : ecrire `len(inventaire.rayon(rayon))` a la place
        de `len(parcourues(...))` dans `_peindre` fait tomber ce test.

        Le pied sommait deux choses differentes : le numerateur passe par
        `a_decider`, le denominateur non. « 2 trouvee(s) sur 6 variante(s)
        relues » se lit « le motif est rare » la ou la mesure vraie est « 2 sur
        2, il est partout ».
        """
        depot = Depot(_bac())
        commun = _ecran(IH06, Champ(id="wnd[0]/usr/ctxtWERKS",
                                    type="GuiCTextField", texte="Division"))
        depot.enregistrer(variante_de(commun))
        depot.mettre_en_quarantaine(variante_de(commun))
        depot.mettre_en_quarantaine(variante_de(_ecran(
            Identite(transaction="IW39", programme="SAPLIW39", dynpro="1000"),
            Champ(id="wnd[0]/usr/ctxtWERKS2", type="GuiCTextField",
                  texte="Division"))))
        capacites = Capacites()
        journal = Journal("", "a", "//werks", "0", "0", "0")
        N.naviguer(journal.console(), depot,
                   gabarit=lambda: gabarit_pour(capacites),
                   peintre=peintre_pour(capacites))
        self.assertIn("1 trouvee(s) sur 1 variante(s) relues", journal.texte)
        self.assertNotIn("sur 2 variante(s) relues", journal.texte)

    def test_la_recherche_ECRIT_le_filtre_a_decider(self):
        """Un filtre qui retire des lignes sans le dire est ce que la
        docstring de `Critere` appelle le reglage le plus dangereux."""
        rendu = "\n".join(texte_nu(b) for b in N.vue_recherche(
            (), 0, Critere(motif="x", portee="champ", a_decider=True), 0,
            N.Vue(), GABARITS[0]))
        self.assertIn("a decider seulement", rendu)

    def test_la_recherche_REFUSE_un_critere_de_portee_ECRAN(self):
        """`premiere.champ` vaudrait `None` et le pied leverait un
        `AttributeError` en plein rendu. Aucun chemin de la boucle n'y mene
        aujourd'hui ; rien ne l'interdit structurellement."""
        rendu = "\n".join(texte_nu(b) for b in N.vue_recherche(
            (), 0, Critere(motif="x"), 0, N.Vue(), GABARITS[0]))
        self.assertIn("Tape //motif", rendu)

    def test_la_liste_annonce_OU_elle_a_cherche_quand_un_motif_est_pose(self):
        """« filtre : werks » ne dit pas si `werks` a ete cherche dans
        l'identite de l'ecran ou dans ses champs, et les deux ne rendent pas
        du tout la meme chose."""
        rendu = "\n".join(texte_nu(b) for b in N.vue_liste(
            N.Vue(critere=Critere(motif="werks")), (), 0, GABARITS[3]))
        self.assertIn("cherche dans", rendu)
        for attribut in ("transaction", "programme", "dynpro", "empreinte",
                         "titre"):
            self.assertIn(attribut, rendu)


class TestCeQueLaComparaisonIDENTIFIE(unittest.TestCase):

    def test_les_DEUX_cotes_portent_leur_ecran(self):
        """Le titre ne nommait que le triplet de GAUCHE, et `_rangee_cote`
        n'affichait aucun triplet : celui de droite n'apparaissait nulle
        part."""
        gauche = _fiche(*_champs(4))
        droite = _fiche(*_champs(4, type_="GuiButton"))
        lignes = [texte_nu(b) for b in N.vue_comparaison(
            comparer(gauche, droite), N.Vue(),
            Gabarit(colonnes=110, lignes=60, source=MESUREE))]
        cotes = [l for l in lignes if l.startswith(("gauche", "droite"))]
        self.assertEqual(len(cotes), 2, lignes)
        for ligne in cotes:
            self.assertIn("IH06::SAPLIH06::1000", ligne)

    def test_les_ecarts_sont_comptes_en_IDENTIFIANTS_et_en_ATTRIBUTS(self):
        """`len(comparaison.ecarts)` compte des couples (id, attribut) ; le
        tableau dessous compte des identifiants. « ecarts 4 » sous « lignes
        1-1 sur 1 » sont deux comptes justes qu'on lit comme
        contradictoires."""
        gauche = _fiche(Champ(id="wnd[0]/usr/a", type="GuiTextField",
                              nom="n", texte="t", infobulle="i",
                              modifiable=True))
        droite = _fiche(Champ(id="wnd[0]/usr/a", type="GuiTextField",
                              nom="N", texte="T", infobulle="I",
                              modifiable=False))
        mesure = comparer(gauche, droite)
        self.assertEqual(len(mesure.ecarts), 4)
        rendu = "\n".join(texte_nu(b) for b in N.vue_comparaison(
            mesure, N.Vue(), Gabarit(colonnes=110, lignes=60,
                                     source=MESUREE)))
        self.assertIn("1 identifiant(s) commun(s), 4 attribut(s)", rendu)

    def test_la_ligne_de_synthese_TIENT_a_79_colonnes(self):
        """Mesure avant correction : « ... ecarts~ » — le nombre d'ecarts
        etait coupe, et aucune vue plus large n'est atteignable depuis le
        navigateur."""
        gauche = _fiche(*_champs(12))
        droite = _fiche(*_champs(12, type_="GuiButton"))
        lignes = [texte_nu(b) for b in N.vue_comparaison(
            comparer(gauche, droite), N.Vue(),
            Gabarit(colonnes=79, lignes=60, source=MESUREE))]
        synthese = [l for l in lignes if "a droite seulement" in l
                    or "ecarts" in l]
        self.assertTrue(synthese)
        for ligne in synthese:
            self.assertNotIn(MARQUE, ligne, ligne)


class TestLeShellEtSaValeur(unittest.TestCase):
    """Le « (1) » nomme un OUI. Les deux autres etats ne sont pas lui."""

    def _shell(self, modifiable):
        return Champ(id="wnd[0]/usr/cntlALV/shellcont/shell", type="GuiShell",
                     soustype="GridView", texte="SAP.GridView.1",
                     modifiable=modifiable)

    def test_un_shell_VERROUILLE_s_affiche_non_et_sans_note(self):
        """CONTROLE NEGATIF : revenir a `champ.type == TYPE_SANS_CHANGEABLE`
        seul dans `sans_mesure` fait tomber ce test.

        Un champ que le fichier declare VERROUILLE presente comme un « oui »
        sans preuve est l'inverse de la donnee, et qui redige un `set` y lit
        l'inverse de ce qu'il y a.
        """
        fiche = _fiche(self._shell(False))
        lignes = [texte_nu(b) for b in N.vue_fiche(N.Vue(), fiche, (),
                                                   GABARITS[3])]
        donnee = [l for l in lignes if "shellcont" in l and "GuiShell" in l]
        self.assertEqual(len(donnee), 1, lignes)
        self.assertIn("non", donnee[0])
        self.assertNotIn("(1)", donnee[0])
        self.assertNotIn("n'expose pas", "\n".join(lignes))

    def test_un_shell_NON_RENSEIGNE_s_affiche_point_d_interrogation(self):
        """Le meme ecran disait deux choses du meme champ : « (1) » dans la
        colonne, et « 1 non renseigne(s) au fichier » dans l'en-tete."""
        fiche = _fiche(self._shell(None))
        lignes = [texte_nu(b) for b in N.vue_fiche(N.Vue(), fiche, (),
                                                   GABARITS[3])]
        donnee = [l for l in lignes if "shellcont" in l and "GuiShell" in l]
        self.assertIn("?", donnee[0])
        self.assertNotIn("(1)", donnee[0])
        self.assertIn("1 non renseigne(s) au fichier", "\n".join(lignes))

    def test_le_detail_d_un_shell_sans_oui_ne_parle_PAS_de_oui(self):
        """Le paragraphe sur `modifiable` ecrivait « `modifiable` est
        renseigne ici » quatre lignes sous une ligne qui affichait
        « modifiable  ? »."""
        for valeur, attendu in ((False, "non"), (None, "?")):
            with self.subTest(modifiable=valeur):
                champ = self._shell(valeur)
                rendu = "\n".join(texte_nu(b) for b in N.vue_champ(
                    _fiche(champ), champ,
                    Gabarit(colonnes=79, lignes=60, source=MESUREE)))
                self.assertIn(f"modifiable  {attendu}", rendu)
                self.assertNotEqual(attendu, "")
                self.assertNotIn("ne vaut pas preuve", rendu)
                # Le paragraphe sur `texte`, lui, reste VRAI de tout GuiShell.
                self.assertIn("nom de classe ActiveX", rendu)

    def test_le_detail_d_un_shell_avec_oui_porte_les_DEUX_paragraphes(self):
        champ = self._shell(True)
        rendu = "\n".join(texte_nu(b) for b in N.vue_champ(
            _fiche(champ), champ,
            Gabarit(colonnes=79, lignes=60, source=MESUREE)))
        self.assertIn("nom de classe ActiveX", rendu)
        self.assertIn("ne vaut pas preuve", rendu)


class TestLaPaireQueLeClasseurAttend(unittest.TestCase):

    def test_l_ecran_est_ecrit_dans_la_forme_du_CLASSEUR(self):
        """CONTROLE NEGATIF : remplacer `SEPARATEUR_ECRAN` par « / » dans
        `_ecran_du` fait tomber ce test — la paire sortirait dans une forme
        que `commandes/dictionnaire.py` n'utilise pas, donc increcopiable."""
        from falcon.commandes.dictionnaire import SEPARATEUR_ECRAN
        self.assertEqual(SEPARATEUR_ECRAN, "::")
        fiche = _fiche(*_champs(2))
        champ = fiche.variante.champs[0]
        detail = "\n".join(texte_nu(b) for b in N.vue_champ(
            fiche, champ, Gabarit(colonnes=79, lignes=60, source=MESUREE)))
        self.assertIn("IH06::SAPLIH06::1000", detail)
        recherche = "\n".join(texte_nu(b) for b in N.vue_recherche(
            (N.Trouvaille(fiche=fiche, champ=champ),), 1,
            Critere(motif="champ", portee="champ"), 1, N.Vue(), GABARITS[0]))
        self.assertIn("IH06::SAPLIH06::1000", recherche)


class TestLaGardeDeLaPromotion(unittest.TestCase):

    def setUp(self):
        self.racine = _bac()
        depot = Depot(self.racine)
        depot.mettre_en_quarantaine(variante_de(_ecran(
            IH06, Champ(id="wnd[0]/usr/txtA"), Champ(id="wnd[0]/usr/txtB"),
            titre="Liste multi-niveaux")))
        self.depot = depot
        self.fiche = charger(depot).rayon(QUARANTAINE)[0]
        self.empreinte = self.fiche.clef.empreinte

    def _jouer(self, *saisies: str) -> Journal:
        journal = Journal(*saisies)
        capacites = Capacites()
        N.naviguer(journal.console(), self.depot,
                   gabarit=lambda: gabarit_pour(capacites),
                   peintre=peintre_pour(capacites))
        return journal

    def _au_cure(self) -> list[str]:
        cure = Depot(self.racine)
        return [v.clef.empreinte for t in cure.triplets()
                for v in cure.variantes(t)]

    def test_la_promotion_refuse_depuis_la_liste(self):
        """CONTROLE NEGATIF n°3 : retirer l'appel a `garde_de_la_promotion`
        dans `_promouvoir` fait tomber ce test.

        Sans elle, l'empreinte de la liste serait recopiable sans avoir rien
        regarde : la ceremonie resterait, son sens partirait. Le scenario
        DONNE l'empreinte juste apres, precisement pour que le test tombe si
        la garde disparait.
        """
        journal = self._jouer("", "p 1", self.empreinte, "0", "0")
        self.assertIn("n'est pas la fiche ouverte", journal.texte)
        self.assertNotIn(self.empreinte, self._au_cure())

    def test_la_promotion_depuis_la_fiche_OUVERTE_promeut(self):
        """Et la garde ne doit pas tout interdire : le geste existe."""
        journal = self._jouer("", "1", "p", self.empreinte, "0", "0")
        self.assertIn("Promue", journal.texte)
        self.assertIn(self.empreinte, self._au_cure())

    def test_un_mot_faux_annule_et_ne_promeut_rien(self):
        journal = self._jouer("", "1", "p", "oui", "0", "0")
        self.assertIn("Annule", journal.texte)
        self.assertNotIn(self.empreinte, self._au_cure())

    def test_la_promotion_dit_que_la_capture_RESTE_en_quarantaine(self):
        journal = self._jouer("", "1", "p", self.empreinte, "0", "0")
        self.assertIn("promouvoir COPIE, ne deplace pas", journal.texte)
        ecarte = Depot(self.depot.quarantaine)
        self.assertIn(self.empreinte,
                      [v.clef.empreinte for t in ecarte.triplets()
                       for v in ecarte.variantes(t)])

    def test_la_garde_mord_sur_une_AUTRE_fiche_que_celle_ouverte(self):
        """Ouvrir la premiere et promouvoir la seconde : la ceremonie porte
        alors sur un ecran que personne n'a affiche."""
        self.depot.mettre_en_quarantaine(variante_de(_ecran(
            IH06, Champ(id="wnd[0]/usr/txtC"), titre="autre")))
        inventaire = charger(self.depot)
        ouverte, autre = inventaire.rayon(QUARANTAINE)[:2]
        vue = N.Vue(ecran=N.FICHE, ouverte=ouverte)
        N.garde_de_la_promotion(vue, ouverte)
        with self.assertRaises(N.PromotionHorsFiche):
            N.garde_de_la_promotion(vue, autre)

    def test_la_garde_refuse_depuis_tout_ecran_qui_n_est_pas_la_fiche(self):
        for ecran in (N.ACCUEIL, N.LISTE, N.RECHERCHE, N.COMPARAISON,
                      N.RAPPORTS, N.AIDE, N.DETAIL):
            with self.subTest(ecran=ecran):
                with self.assertRaises(N.PromotionHorsFiche):
                    N.garde_de_la_promotion(N.Vue(ecran=ecran,
                                                  ouverte=self.fiche),
                                            self.fiche)


class TestLaBoucle(unittest.TestCase):

    def setUp(self):
        self.depot, self.inventaire = _inventaire_jetable(8)

    def _jouer(self, *saisies: str, capacites=None):
        capacites = capacites or Capacites()
        journal = Journal(*saisies)
        verdict = N.naviguer(journal.console(), self.depot,
                             gabarit=lambda: gabarit_pour(capacites),
                             peintre=peintre_pour(capacites))
        return journal, verdict

    def test_une_fin_de_flux_rend_CONTINUER_sans_lever(self):
        journal, verdict = self._jouer()
        self.assertEqual(verdict, CONTINUER)
        self.assertIn("Fin de session", journal.texte)

    def test_zero_a_l_accueil_sort_du_navigateur(self):
        journal, verdict = self._jouer("0")
        self.assertEqual(verdict, CONTINUER)
        self.assertNotIn("Fin de session", journal.texte)

    def test_zero_remonte_d_un_cran_et_ne_cherche_aucun_numero(self):
        """CONTROLE NEGATIF : tester `bas.isdigit()` avant les lettres dans
        `_decouper` fait tomber ce test — « 0 » ouvrirait « la variante numero
        zero », et l'ecran repondrait qu'elle n'existe pas a quelqu'un qui
        voulait remonter."""
        journal, _ = self._jouer("", "1", "0", "0", "0")
        self.assertNotIn("n'est pas dans cette liste", journal.texte)
        self.assertNotIn("n'en est pas un", journal.texte)

    def test_zero_depuis_le_DETAIL_remonte_a_la_FICHE_et_pas_a_la_liste(self):
        """CONTROLE NEGATIF : retirer la branche `DETAIL` de `_remonter` fait
        tomber ce test.

        `0` remonte d'UN cran. Depuis le detail d'un champ, un cran est la
        fiche — celle qu'on etait en train de lire champ par champ — et pas la
        liste : y retomber ferait recommencer la lecture, et c'est cette
        lecture qui fonde la promotion.
        """
        journal, _ = self._jouer("", "1", "1", "0", "0", "0", "0")
        # Apres le dernier « 0 » du detail, l'ecran suivant porte le tableau
        # des champs de la fiche, pas l'en-tete de la liste.
        ecrans = journal.texte.split("FALCON — navigateur de catalogue")
        detail = journal.texte.split("ecran       T00::SAPLX::1000")[-1]
        self.assertIn("p PROMOUVOIR", detail,
                      "on est retombe sur la liste, pas sur la fiche")
        self.assertTrue(ecrans)

    def test_la_geometrie_est_remesuree_a_CHAQUE_tour(self):
        """Windows n'a pas de `SIGWINCH` : une reconnexion RDP a une autre
        resolution redimensionne la console en pleine session.

        CONTROLE NEGATIF : mesurer une seule fois avant la boucle fait tomber
        ce test.
        """
        mesures = []
        capacites = Capacites()

        def gabarit():
            mesures.append(len(mesures))
            return gabarit_pour(capacites)

        journal = Journal("", "1", "0", "0")
        N.naviguer(journal.console(), self.depot, gabarit=gabarit,
                   peintre=peintre_pour(capacites))
        self.assertEqual(len(mesures), 5,
                         "un tour de boucle sans remesure, ou un de trop")

    def test_aucune_session_de_navigateur_n_emet_de_sequence(self):
        """Le niveau NU est le seul que ce lot cable, et il n'a pas de decor.

        CONTROLE NEGATIF : cabler `Environnement.capacites` sur la sonde
        reelle fait tomber ce test des qu'un developpeur lance la suite depuis
        un vrai terminal.
        """
        journal, _ = self._jouer("", "1", "1", "0", "0", "//champ", "0", "?",
                                 "0", "r", "0", "f", "f", "a", "m 1", "d",
                                 "0", "0")
        self.assertNotIn("\x1b", journal.texte)
        self.assertNotIn("[0m", journal.texte)

    def test_une_commande_inconnue_ne_fait_pas_sortir(self):
        journal, _ = self._jouer("", "zzz", "0", "0")
        self.assertIn("n'est pas une commande d'ici", journal.texte)

    def test_un_mot_qui_commence_par_p_ne_promeut_pas(self):
        """CONTROLE NEGATIF : revenir a `bas.startswith("p")` fait tomber ce
        test — « page » declencherait la ceremonie de promotion."""
        journal, _ = self._jouer("", "1", "page", "0", "0", "0")
        self.assertNotIn("Promouvoir, c'est dire", journal.texte)
        self.assertIn("n'est pas une commande d'ici", journal.texte)

    def test_comparer_exige_DEUX_marquees(self):
        journal, _ = self._jouer("", "m 1", "d", "0", "0")
        self.assertIn("Il en faut DEUX", journal.texte)

    def test_comparer_refuse_une_esquisse_et_le_DIT(self):
        depot = Depot(_bac())
        depot.mettre_en_quarantaine(variante_de(_ecran(
            IH06, Champ(id="wnd[0]/usr/txtA"))))
        depot.mettre_en_quarantaine(variante_de(_ecran(
            IH06, Champ(id="wnd[1]/usr/txtB")), source=ESQUISSE))
        capacites = Capacites()
        journal = Journal("", "m 1", "m 2", "d", "0", "0")
        N.naviguer(journal.console(), depot,
                   gabarit=lambda: gabarit_pour(capacites),
                   peintre=peintre_pour(capacites))
        self.assertIn("Refuse", journal.texte)
        self.assertIn("ESQUISSE", journal.texte)
        self.assertNotIn("CE QUE FALCON NE SAIT PAS", journal.texte)

    def test_chaque_commande_annoncee_est_DECOUPEE(self):
        """Le nom dit ce que le test mesure : la TOKENISATION, rien de plus.

        Il s'appelait « est_reconnue_par_la_boucle » et n'appelait jamais la
        boucle : il appelle `_decouper` et rien d'autre. Une declaration prise
        pour une mesure. Une lettre ajoutee a `LETTRES` ET a `COMMANDES` sans
        branche dans `_repondre` passerait ce test-ci ; c'est
        `test_chaque_commande_annoncee_a_un_EFFET` qui l'attrape.

        CONTROLE NEGATIF : ajouter `("x", "exporter", "exporter en CSV")` a
        `COMMANDES` sans l'ajouter a `LETTRES` fait tomber ce test.
        """
        for clef, _, _quoi in N.COMMANDES:
            if clef in ("<n>", "/motif", "//motif"):
                continue
            with self.subTest(commande=clef):
                commande, _ = N._decouper(clef)
                self.assertEqual(commande, clef.lower(),
                                 f"« {clef} » est annoncee et non reconnue")

    def test_un_pied_d_ecran_ne_peut_PAS_nommer_une_touche_inconnue(self):
        """Le controle vu de l'autre bout, et il est STRUCTUREL.

        Les pieds sont composes par `commandes()` depuis `COMMANDES` : une
        clef absente de la table leve au rendu au lieu de s'afficher. La
        maquette de ce lot annoncait « x exporter » et « f filtres » ; la
        premiere n'existe pas, et ce test est ce qui empeche de la reecrire a
        la main dans un pied.
        """
        with self.assertRaises(KeyError):
            N.commandes(GABARITS[0], ("x",))
        annoncees = {clef for clef, _, _ in N.COMMANDES}
        self.assertNotIn("x", annoncees)
        self.assertNotIn("f filtres",
                         "\n".join(texte_nu(b) for b in N.vue_liste(
                             N.Vue(), (), 0, GABARITS[3])))

    def test_le_pied_se_replie_sur_une_fenetre_etroite(self):
        """La largeur mesuree change le nombre de lignes du pied, donc le
        chrome, donc la pagination. Une longueur figee serait fausse a 40
        colonnes comme a 110."""
        clefs = tuple(clef for clef, _, _ in N.COMMANDES)
        etroit = N.commandes(Gabarit(colonnes=40, lignes=24, source=MESUREE),
                             clefs)
        large = N.commandes(Gabarit(colonnes=110, lignes=24, source=MESUREE),
                            clefs)
        self.assertGreater(len(etroit), len(large))


class TestLaBoucleAGIT(unittest.TestCase):
    """Un tiers du module n'etait exerce par AUCUN test.

    Mesure : rendre `+`, `-`, `L`, `g` et `h` completement inoperants — des
    retours identite — laissait la suite entiere verte, alors que `commandes()`
    IMPRIME ces cinq touches dans les pieds de cinq ecrans. Cinq touches
    annoncees qui peuvent cesser de fonctionner sans qu'un test bronche.
    """

    def setUp(self):
        self.racine = _bac()
        self.depot = Depot(self.racine)
        for rang in range(22):
            self.depot.mettre_en_quarantaine(variante_de(_ecran(
                Identite(transaction=f"T{rang:02d}", programme="SAPLX",
                         dynpro="1000"),
                *_champs(3), titre=f"ecran numero {rang}")))

    def _jouer(self, *saisies: str, colonnes=79, lignes=24):
        capacites = Capacites(colonnes=colonnes, lignes=lignes,
                              source_taille=MESUREE)
        journal = Journal(*saisies)
        N.naviguer(journal.console(), self.depot,
                   gabarit=lambda: gabarit_pour(capacites),
                   peintre=peintre_pour(capacites))
        return journal

    def test_chaque_commande_annoncee_a_un_EFFET(self):
        """Le controle dans le sens que `_decouper` ne mesure pas.

        `test_chaque_commande_annoncee_est_DECOUPEE` appelle `_decouper` et
        rien d'autre : il mesure le decoupage lexical, jamais la boucle. Une
        lettre ajoutee a `LETTRES` ET a `COMMANDES` sans branche dans
        `_repondre` passerait ce test-la et tomberait sur `int("")` au
        runtime. Ici on JOUE chaque touche a travers `naviguer`, et l'on exige
        qu'aucune ne reponde « n'est pas une commande d'ici ».

        CONTROLE NEGATIF : retirer la branche d'une touche de `_repondre` fait
        tomber ce test.
        """
        for clef, _, _quoi in N.COMMANDES:
            if clef in ("0", "q"):
                continue
            saisie = {"<n>": "1", "/motif": "/T0",
                      "//motif": "//champ"}.get(clef, clef)
            with self.subTest(commande=clef):
                journal = self._jouer("", "1", saisie, "0", "0", "0", "0")
                self.assertNotIn("n'est pas une commande d'ici",
                                 journal.texte,
                                 f"« {saisie} » est annoncee et non traitee")

    def test_plus_et_moins_paginent_VRAIMENT(self):
        """CONTROLE NEGATIF : faire de `+` et `-` des retours identite fait
        tomber ce test.

        Sur un cmd.exe, la liste des vingt-deux variantes tient sur quatre
        pages : `+` est la SEULE facon d'atteindre la page 2, et sans elle
        les deux tiers de la quarantaine sont invisibles pendant que l'ecran
        annonce « page 1/4 ».
        """
        journal = self._jouer("", "+", "0", "0")
        self.assertIn("page 2/", journal.texte)
        self.assertNotIn("page 3/", journal.texte)
        retour = self._jouer("", "+", "+", "-", "0", "0")
        pages = [l for l in retour.lignes if l.strip().startswith("page ")]
        self.assertEqual([p.split()[1] for p in pages][-1].split("/")[0], "2")

    def test_g_et_h_ouvrent_les_deux_cotes_de_la_comparaison(self):
        """CONTROLE NEGATIF : faire de `g` et `h` des retours identite fait
        tomber ce test. Elles sont le SEUL chemin de la comparaison vers une
        fiche.

        Le discriminant est l'EMPREINTE, sur une ligne de FICHE, APRES l'ecran
        de comparaison. Asserter le titre sur le journal entier ne prouvait
        rien : le titre d'une variante est deja dans la colonne « titre » de
        la liste, donc l'assertion restait verte avec `g` inoperante.
        """
        depot = Depot(_bac())
        for suffixe in ("A", "B"):
            depot.mettre_en_quarantaine(variante_de(_ecran(
                IH06, Champ(id=f"wnd[0]/usr/txt{suffixe}"),
                titre=f"variante {suffixe}")))
        fiches = charger(depot).rayon(QUARANTAINE)
        self.assertEqual(len(fiches), 2)
        capacites = Capacites()
        for touche, rang in (("g", 0), ("h", 1)):
            with self.subTest(touche=touche):
                journal = Journal("", "m 1", "m 2", "d", touche, "0", "0", "0")
                N.naviguer(journal.console(), depot,
                           gabarit=lambda: gabarit_pour(capacites),
                           peintre=peintre_pour(capacites))
                self.assertIn("Comparaison", journal.texte)
                apres_la_comparaison = journal.texte.split("Comparaison")[-1]
                self.assertIn(f"empreinte   {fiches[rang].clef.empreinte}",
                              apres_la_comparaison)
                self.assertNotIn(
                    f"empreinte   {fiches[1 - rang].clef.empreinte}",
                    apres_la_comparaison,
                    f"« {touche} » a ouvert l'autre cote")

    def test_g_et_h_REFUSENT_hors_d_une_comparaison(self):
        journal = self._jouer("", "g", "0", "0")
        self.assertIn("n'ouvrent un cote que depuis une comparaison",
                      journal.texte)

    def test_f_fait_tourner_les_trois_rayons(self):
        journal = self._jouer("", "f", "f", "f", "0", "0")
        self.assertIn("CURE", journal.texte)
        self.assertIn("QUARANTAINE + CURE", journal.texte)

    def test_a_bascule_le_filtre_et_le_DIT(self):
        journal = self._jouer("", "a", "0", "0")
        self.assertIn("a decider seulement", journal.texte)

    def test_r_mene_aux_rapports(self):
        journal = self._jouer("", "r", "0", "0")
        self.assertIn("Comptes rendus d'exploration", journal.texte)

    def test_point_d_interrogation_mene_a_l_aide(self):
        journal = self._jouer("", "?", "0", "0")
        self.assertIn("Navigateur de catalogue — les commandes", journal.texte)


class TestLeFiltreDeLaLISTE(unittest.TestCase):
    """Le CORPS de la liste, pas seulement son en-tete."""

    def setUp(self):
        self.depot, _ = _inventaire_jetable(8)

    def _jouer(self, *saisies: str):
        capacites = Capacites()
        journal = Journal(*saisies)
        N.naviguer(journal.console(), self.depot,
                   gabarit=lambda: gabarit_pour(capacites),
                   peintre=peintre_pour(capacites))
        return journal

    def test_le_motif_de_la_liste_filtre_le_CORPS_et_pas_l_en_tete_seul(self):
        """CONTROLE NEGATIF : retirer `replace(..., portee=ECRAN)` de
        `_fiches_de`, ou y passer un `Critere()` neuf, fait tomber ce test.

        L'en-tete « filtre : « T03 » » etait epingle ; le corps ne l'etait
        pas. Aucune session ne tapait jamais `/motif` — la seule saisie de
        recherche jouee etait `//champ`, qui passe par le `filtrer` de
        `_peindre` et non par `_fiches_de`. Une liste pouvait donc afficher
        les huit variantes sous un en-tete qui jure qu'elle est filtree, et
        « 1 » ouvrirait alors une variante que le filtre etait cense retirer.
        """
        journal = self._jouer("", "/T03", "1", "0", "0", "0")
        self.assertIn("filtre : « T03 »", journal.texte)
        # Apres la pose du filtre : la premiere liste, non filtree, porte
        # evidemment les huit.
        apres = journal.texte.split("filtre : « T03 »", 1)[1]
        self.assertIn("1 affichee(s) sur 1", apres)
        self.assertIn("ecran numero 3", apres)
        self.assertNotIn("ecran numero 0", apres)
        # Et « 1 » ouvre bien T03, pas T00 : les numeros sont ceux du corps
        # filtre, et c'est sur eux que `<n>`, `m <n>` et `p` portent.
        self.assertIn("T03 / SAPLX / 1000", apres)
        self.assertNotIn("T00 / SAPLX / 1000", apres)

    def test_un_motif_sans_resultat_le_DIT_au_lieu_de_paraitre_vide(self):
        journal = self._jouer("", "/introuvable", "0", "0")
        self.assertIn("Aucune variante ici", journal.texte)
        self.assertIn("filtre : « introuvable »", journal.texte)

    def test_remonter_de_la_RECHERCHE_vide_le_motif_de_champ(self):
        """Le motif de la recherche porte sur les CHAMPS ; la liste le
        reinterprete en portee ECRAN. Chercher « champ » dans les champs puis
        remonter donnait une liste filtree sur l'IDENTITE d'ecran par
        « champ » — vide."""
        journal = self._jouer("", "//champ", "0", "0", "0")
        self.assertIn("filtre : (aucun)", journal.texte)
        self.assertNotIn("Aucune variante ici", journal.texte)


class TestLaMarqueDesigneCeQueLEcranNumerote(unittest.TestCase):

    def setUp(self):
        self.depot = Depot(_bac())
        self.depot.mettre_en_quarantaine(variante_de(_ecran(
            IH06, Champ(id="wnd[0]/usr/ctxtIH06X", type="GuiCTextField"),
            titre="la premiere")))
        self.depot.mettre_en_quarantaine(variante_de(_ecran(
            Identite(transaction="IW39", programme="SAPLIW39", dynpro="1000"),
            Champ(id="wnd[0]/usr/ctxtIH06X", type="GuiCTextField"),
            Champ(id="wnd[0]/usr/autre", type="GuiCTextField"),
            titre="la seconde")))

    def _jouer(self, *saisies: str):
        capacites = Capacites()
        journal = Journal(*saisies)
        N.naviguer(journal.console(), self.depot,
                   gabarit=lambda: gabarit_pour(capacites),
                   peintre=peintre_pour(capacites))
        return journal

    def test_m_n_depuis_la_RECHERCHE_marque_la_trouvaille_affichee(self):
        """CONTROLE NEGATIF : faire indexer `fiches` a `_marquer` sur l'ecran
        RECHERCHE fait tomber ce test.

        Mesure avant correction : `//autre` affiche exactement une trouvaille,
        `wnd[0]/usr/autre` de IW39::SAPLIW39::1000 — la SECONDE ligne de la
        liste. Taper `m 1` en la regardant marquait IH06, la premiere ligne
        d'une liste NON affichee, sans un mot. La marque alimente `d`, puis
        `g`/`h` ouvrent une fiche que personne n'a choisie.

        Le discriminant : on remarque ensuite la MEME fiche depuis la liste.
        Si la premiere marque portait sur la bonne, la seconde la RETIRE et
        `d` repond « il y en a 0 » ; si elle portait sur IH06, `d` a deux
        marquees de triplets differents et REFUSE.
        """
        journal = self._jouer("", "//autre", "m 1", "0", "2", "m", "d", "0",
                              "0")
        self.assertIn("il y en a 0", journal.texte)
        self.assertNotIn("MEME ecran", journal.texte)

    def test_m_n_sur_une_FICHE_refuse_au_lieu_de_marquer_une_autre(self):
        """Les numeros affiches y sont des CHAMPS, et le pied annonce pourtant
        « m marquer » : `m 2` y marquait la 2e ligne d'une liste NON
        affichee."""
        journal = self._jouer("", "1", "m 2", "0", "0", "0")
        self.assertIn("Ici les numeros sont des champs", journal.texte)

    def test_m_seul_sur_une_fiche_marque_la_fiche_OUVERTE(self):
        """CONTROLE NEGATIF : faire ne rien marquer a `m` sans argument sur
        une fiche ouverte fait tomber ce test — `d` repondrait « il en faut
        DEUX »."""
        journal = self._jouer("", "1", "m", "0", "2", "m", "d", "0", "0", "0")
        self.assertNotIn("Il en faut DEUX", journal.texte)
        self.assertIn("Refuse", journal.texte)

    def test_m_deux_fois_sur_la_meme_fiche_RETIRE_la_marque(self):
        journal = self._jouer("", "m 1", "m 1", "d", "0", "0")
        self.assertIn("il y en a 0", journal.texte)

    def test_m_sans_argument_hors_d_une_fiche_REFUSE(self):
        journal = self._jouer("", "m", "0", "0")
        self.assertIn("Rien a marquer ici", journal.texte)

    def test_m_n_hors_bornes_REFUSE_en_disant_combien_il_y_a_de_lignes(self):
        journal = self._jouer("", "m 99", "0", "0")
        self.assertIn("n'est pas un numero de cette liste (2 ligne(s))",
                      journal.texte)

    def test_seules_les_DEUX_dernieres_marques_comptent(self):
        """CONTROLE NEGATIF : retirer le `[-2:]` de `_marquer` fait tomber ce
        test — `comparer(*vue.marques)` leverait un `TypeError` a la
        troisieme."""
        self.depot.mettre_en_quarantaine(variante_de(_ecran(
            Identite(transaction="IA08", programme="RIPLKO10", dynpro="1000"),
            Champ(id="wnd[0]/usr/a"), titre="la troisieme")))
        journal = self._jouer("", "m 1", "m 2", "m 3", "d", "0", "0")
        self.assertNotIn("Il en faut DEUX", journal.texte)

    def test_d_refuse_deux_ecrans_DIFFERENTS_et_le_DIT(self):
        """La garde de triplet, vue de la boucle."""
        journal = self._jouer("", "m 1", "m 2", "d", "0", "0")
        self.assertIn("Refuse", journal.texte)
        self.assertIn("MEME ecran", journal.texte)
        self.assertNotIn("CE QUE FALCON NE SAIT PAS", journal.texte)

    def test_ouvrir_une_trouvaille_depuis_la_RECHERCHE_ouvre_la_bonne(self):
        """CONTROLE NEGATIF : faire ouvrir `trouvailles[0]` a `_ouvrir` sur
        l'ecran RECHERCHE fait tomber ce test."""
        journal = self._jouer("", "//autre", "1", "0", "0", "0")
        self.assertIn("la seconde", journal.texte)

    def test_un_numero_hors_liste_depuis_la_RECHERCHE_REFUSE(self):
        journal = self._jouer("", "//autre", "9", "0", "0", "0")
        self.assertIn("n'est pas dans cette liste", journal.texte)


class TestLaRelectureREREND_ce_que_l_ecran_montre(unittest.TestCase):

    def setUp(self):
        self.racine = _bac()
        self.depot = Depot(self.racine)
        self.depot.mettre_en_quarantaine(variante_de(_ecran(
            IH06, Champ(id="wnd[0]/usr/txtA", texte="AVANT"),
            titre="titre d'avant")))

    def _fichier(self) -> Path:
        return self.depot.quarantaine / "IH06__SAPLIH06__1000.yaml"

    def _jouer(self, *saisies: str):
        capacites = Capacites()
        journal = Journal(*saisies)
        N.naviguer(journal.console(), self.depot,
                   gabarit=lambda: gabarit_pour(capacites),
                   peintre=peintre_pour(capacites))
        return journal

    def test_L_re_resout_la_fiche_OUVERTE(self):
        """CONTROLE NEGATIF : faire rendre `charger(depot)` seul a la branche
        `l` — sans re-resoudre `vue.ouverte` — fait tomber ce test.

        `L` ecrivait « Catalogue relu sur le disque » et remplacait
        l'inventaire, mais `_peindre` rend la fiche depuis `vue.ouverte`, qui
        portait la `Fiche` capturee AVANT. Le message affirmait plus que ce
        que le code faisait — et `p` promeut par `depot.promouvoir`, qui relit
        le DISQUE : on certifiait « TU as relu cet ecran » sur un affichage qui
        n'etait plus ce qui allait etre promu.
        """
        class Relisant(Journal):
            """Modifie le YAML a cote JUSTE avant que « l » soit lu."""

            def __init__(self, fichier, *saisies):
                super().__init__(*saisies)
                self.fichier = fichier
                self.faite = False

            def _lire(self, invite):
                if self.saisies[:1] == ["l"] and not self.faite:
                    contenu = self.fichier.read_text(encoding="utf-8")
                    self.fichier.write_text(
                        contenu.replace("AVANT", "APRES")
                               .replace("titre d'avant", "titre d'apres"),
                        encoding="utf-8")
                    self.faite = True
                return super()._lire(invite)

        capacites = Capacites()
        journal = Relisant(self._fichier(), "", "1", "l", "0", "0", "0")
        N.naviguer(journal.console(), self.depot,
                   gabarit=lambda: gabarit_pour(capacites),
                   peintre=peintre_pour(capacites))
        self.assertTrue(journal.faite, "le fichier n'a pas ete modifie")
        self.assertIn("Catalogue relu sur le disque", journal.texte)
        apres = journal.texte.split("Catalogue relu sur le disque")[1]
        self.assertIn("APRES", apres)
        self.assertIn("titre d'apres", apres)

    def test_une_fiche_marquee_qui_DISPARAIT_sort_des_marques_et_l_ecran_le_dit(self):
        class Effacant(Journal):
            def __init__(self, fichier, *saisies):
                super().__init__(*saisies)
                self.fichier = fichier

            def _lire(self, invite):
                if self.saisies[:1] == ["l"] and self.fichier.exists():
                    self.fichier.unlink()
                return super()._lire(invite)

        capacites = Capacites()
        journal = Effacant(self._fichier(), "", "m 1", "l", "d", "0")
        N.naviguer(journal.console(), self.depot,
                   gabarit=lambda: gabarit_pour(capacites),
                   peintre=peintre_pour(capacites))
        self.assertIn("n'est plus dans le catalogue relu", journal.texte)
        self.assertIn("il y en a 0", journal.texte)


class TestLesComptesRendusSAffichent(unittest.TestCase):

    def setUp(self):
        self.racine = _bac()
        self.depot = Depot(self.racine)
        self.depot.mettre_en_quarantaine(variante_de(_ecran(
            IH06, Champ(id="wnd[0]/usr/txtA"))))
        self.dossier = self.racine / "rapports"
        self.dossier.mkdir(parents=True)

    def _rapport(self, nom: str, contenu, *, octets=False) -> Path:
        chemin = self.dossier / nom
        if octets:
            chemin.write_bytes(contenu)
        else:
            chemin.write_text(contenu, encoding="utf-8")
        return chemin

    def _jouer(self, *saisies: str, ecrire=None):
        capacites = Capacites()
        journal = Journal(*saisies)
        console = journal.console()
        if ecrire is not None:
            console = type(console)(lire=console.lire, ecrire=ecrire)
        N.naviguer(console, self.depot,
                   gabarit=lambda: gabarit_pour(capacites),
                   peintre=peintre_pour(capacites))
        return journal

    def test_la_liste_des_rapports_ecrit_la_taille_MESUREE(self):
        """CONTROLE NEGATIF : faire rendre 0 a `_taille` fait tomber ce test.

        Un compte rendu de quatre kilo-octets affiche « 0 o » se lit « il est
        vide » : personne ne l'ouvre.
        """
        self._rapport("2026-09-11T18-10-54-t.vbs.txt", "x" * 4096)
        journal = self._jouer("", "r", "0", "0", "0")
        self.assertIn("4096 o", journal.texte)

    def test_un_rapport_disparu_affiche_un_point_d_interrogation(self):
        """`None` et pas zero : le repli a zero est pire qu'une remontee."""
        rendu = "\n".join(texte_nu(b) for b in N.vue_rapports(
            [Path("parti.txt")], [N._taille(Path("/n/existe/pas.txt"))],
            N.Vue(), GABARITS[0]))
        self.assertIn("? o", rendu)
        self.assertNotIn("0 o", rendu)

    def test_afficher_un_rapport_le_deverse_VERBATIM(self):
        """CONTROLE NEGATIF : remplacer le corps d'`_afficher_rapport` par un
        `return` nu fait tomber ce test."""
        self._rapport("2026-09-11T18-10-54-t.vbs.txt",
                      "PARTITION\n  gestes rejoues   12 / 12\n")
        journal = self._jouer("", "r", "1", "0", "0", "0")
        self.assertIn("gestes rejoues   12 / 12", journal.texte)
        self.assertIn("verbatim", journal.texte)

    def test_un_numero_hors_liste_de_rapports_REFUSE(self):
        self._rapport("2026-09-11T18-10-54-t.vbs.txt", "x")
        journal = self._jouer("", "r", "9", "0", "0", "0")
        self.assertIn("n'est pas dans cette liste", journal.texte)

    def test_un_rapport_qui_n_est_PAS_de_l_UTF8_refuse_sans_tuer_la_session(self):
        """CONTROLE NEGATIF : revenir a `except OSError` seul fait tomber ce
        test.

        `UnicodeDecodeError` est un `ValueError`, pas un `OSError` : un
        `.txt` recopie ou retouche au Bloc-notes en ANSI faisait sortir la
        levee de `naviguer`, de `parcourir`, jusqu'a la trace de pile — sur un
        ecran dont le seul role est de RELIRE, apres une cartographie qui a
        deja agi dans SAP pendant trois minutes.
        """
        self._rapport("2026-09-11T18-10-54-t.vbs.txt",
                      b"branche : sauvegarde refus\xe9e\n", octets=True)
        journal = self._jouer("", "r", "1", "0", "0", "0")
        self.assertIn("Illisible : UnicodeDecodeError", journal.texte)

    def test_un_rapport_que_le_TERMINAL_ne_sait_pas_ecrire_renvoie_au_fichier(self):
        """Symetrique, cote ecriture : une sortie redirigee en cp1252 — le cas
        Windows FR — sur un compte rendu qui porte un caractere hors cp1252.
        """
        self._rapport("2026-09-11T18-10-54-t.vbs.txt",
                      "branche : sauvegarde refus\u0142e\n")
        recues: list[str] = []

        def ecrire(ligne: str = "") -> None:
            ligne.encode("cp1252")
            recues.append(ligne)

        journal = self._jouer("", "r", "1", "0", "0", "0", ecrire=ecrire)
        texte = "\n".join(recues)
        self.assertIn("ne sait pas ecrire", texte)
        self.assertIn("Ouvre-le dans un editeur", texte)


class TestLaCeremonieDeLaPromotionDansLeNavigateur(unittest.TestCase):

    def setUp(self):
        self.racine = _bac()
        self.depot = Depot(self.racine)

    def _ajouter(self, transaction: str, *, source="observee", titre="x"):
        self.depot.mettre_en_quarantaine(variante_de(_ecran(
            Identite(transaction=transaction, programme="SAPLX",
                     dynpro="1000"),
            Champ(id=f"wnd[0]/usr/{transaction}"), titre=titre),
            source=source))

    def _jouer(self, *saisies: str):
        capacites = Capacites()
        journal = Journal(*saisies)
        N.naviguer(journal.console(), self.depot,
                   gabarit=lambda: gabarit_pour(capacites),
                   peintre=peintre_pour(capacites))
        return journal

    def test_promouvoir_une_ESQUISSE_dit_que_personne_n_a_vu_cet_ecran(self):
        """CONTROLE NEGATIF : remplacer la boucle sur `TEXTE_ESQUISSE` de
        `_promouvoir` par le texte du releve fait tomber ce test.

        C'est le texte qui distingue « j'ai lu l'ecran » de « j'ai lu le
        fichier » sur une esquisse — exactement ce que l'entree 3 du catalogue
        dit deja, et que rien ne tenait dans le navigateur.
        """
        self._ajouter("IH06", source=ESQUISSE)
        empreinte = charger(self.depot).rayon(QUARANTAINE)[0].clef.empreinte
        journal = self._jouer("", "1", "p", empreinte, "0", "0")
        self.assertIn("personne n'a vu cet", journal.texte)
        self.assertIn("certifier avoir lu le FICHIER", journal.texte)
        self.assertIn("Promue", journal.texte)

    def test_les_QUATRE_lignes_du_texte_d_esquisse_sont_ecrites(self):
        """Le texte est partage entre `ecrans.promouvoir` et
        `navigateur._promouvoir` pour qu'ils ne divergent pas. Seule la
        premiere ligne etait epinglee : les trois autres pouvaient diverger
        librement."""
        self._ajouter("IH06", source=ESQUISSE)
        empreinte = charger(self.depot).rayon(QUARANTAINE)[0].clef.empreinte
        journal = self._jouer("", "1", "p", empreinte, "0", "0")
        for ligne in N.TEXTE_ESQUISSE:
            self.assertIn(ligne, journal.texte)

    def test_promouvoir_ce_qui_est_DEJA_au_cure_refuse_AVANT_la_ceremonie(self):
        """CONTROLE NEGATIF : retirer le `if cible.rayon != QUARANTAINE` fait
        tomber ce test.

        Sans lui, on demande a l'utilisateur de taper l'empreinte en toutes
        lettres pour une fiche deja au cure, avant de lui repondre « Refuse » :
        une ceremonie de certification qui ne certifie rien.
        """
        self._ajouter("IH06")
        clef = charger(self.depot).rayon(QUARANTAINE)[0].clef
        self.depot.promouvoir(clef)
        journal = self._jouer("", "f", "1", "p", "0", "0", "0")
        self.assertIn("deja au catalogue cure", journal.texte)
        self.assertNotIn("Promouvoir, c'est dire", journal.texte)

    def test_p_avec_un_numero_HORS_BORNES_refuse_au_lieu_de_deviner(self):
        """CONTROLE NEGATIF : revenir a
        `if argument and 1 <= int(argument) <= len(fiches)` fait tomber ce
        test.

        Hors bornes, la condition etait fausse et `cible` restait
        silencieusement `vue.ouverte` : `p 99` depuis une fiche engageait la
        ceremonie sur la variante COURANTE, dont l'empreinte est justement a
        l'ecran. Qui s'est trompe de numero la tape et promeut un ecran qu'il
        n'avait pas designe.
        """
        self._ajouter("IH06")
        self._ajouter("IW39")
        empreinte = charger(self.depot).rayon(QUARANTAINE)[0].clef.empreinte
        journal = self._jouer("", "p 99", empreinte, "0", "0")
        self.assertIn("n'est pas un numero de cette liste (2 ligne(s))",
                      journal.texte)
        self.assertNotIn("Promouvoir, c'est dire", journal.texte)
        cure = Depot(self.racine)
        self.assertEqual([t for t in cure.triplets()], [])

    def test_p_avec_un_numero_depuis_une_fiche_OUVERTE_ne_promeut_rien(self):
        """Le scenario mesure par le relecteur : fiche IH06 ouverte, liste de
        deux lignes, `p 99`. La ceremonie s'ouvrait sur IH06 et la promouvait,
        l'empreinte demandee etant justement celle a l'ecran."""
        self._ajouter("IH06")
        self._ajouter("IW39")
        empreinte = charger(self.depot).rayon(QUARANTAINE)[0].clef.empreinte
        journal = self._jouer("", "1", "p 99", empreinte, "0", "0", "0")
        self.assertNotIn("Promouvoir, c'est dire", journal.texte)
        self.assertEqual([t for t in Depot(self.racine).triplets()], [])

    def test_p_avec_un_numero_depuis_une_FICHE_refuse_les_numeros_de_champs(self):
        self._ajouter("IH06")
        journal = self._jouer("", "1", "p 1", "0", "0", "0")
        self.assertIn("Ici les numeros sont des champs", journal.texte)

    def test_p_sans_rien_d_ouvert_refuse(self):
        self._ajouter("IH06")
        journal = self._jouer("", "p", "0", "0")
        self.assertIn("Rien a promouvoir ici", journal.texte)

    def test_un_catalogue_invalide_pendant_la_promotion_est_RATTRAPE(self):
        """CONTROLE NEGATIF : retirer le `except CatalogueInvalide` de
        `_promouvoir` fait tomber ce test — la levee sortirait de `naviguer`,
        de `parcourir`, jusqu'a la trace de pile."""
        self._ajouter("IH06")
        fiche = charger(self.depot).rayon(QUARANTAINE)[0]
        # Le fichier de quarantaine disparait entre l'affichage et le geste :
        # `promouvoir` ne trouve plus la variante et leve.
        class Effacant(Journal):
            def __init__(self, fichier, *saisies):
                super().__init__(*saisies)
                self.fichier = fichier

            def _lire(self, invite):
                if (self.saisies[:1] == [fiche.clef.empreinte]
                        and self.fichier.exists()):
                    self.fichier.unlink()
                return super()._lire(invite)

        capacites = Capacites()
        journal = Effacant(fiche.fichier, "", "1", "p",
                           fiche.clef.empreinte, "0", "0")
        N.naviguer(journal.console(), self.depot,
                   gabarit=lambda: gabarit_pour(capacites),
                   peintre=peintre_pour(capacites))
        self.assertIn("Refuse", journal.texte)
        self.assertNotIn("Promue", journal.texte)


class TestLeClavierAZERTY(unittest.TestCase):

    def test_les_chiffres_NON_ASCII_ne_tuent_pas_la_session(self):
        """CONTROLE NEGATIF : revenir a `bas.isdigit()` nu dans `_decouper`
        fait tomber ce test.

        `str.isdigit()` est VRAI pour des caracteres que `int()` refuse. Or
        `²` est une touche DEDIEE du clavier AZERTY francais, en haut a
        gauche, contre la touche `&`/1 : c'est le clavier de la machine cible.
        Mesure : `naviguer` levait `ValueError: invalid literal for int() with
        base 10: '²'` sur `²`, sur `m²` et sur `p²`, et ni `menu.parcourir` ni
        `_console` n'attrapent cette famille.
        """
        depot, _ = _inventaire_jetable(3)
        capacites = Capacites()
        journal = Journal("²", "m²", "p²", "\u00b3", "\u00b9", "0")
        verdict = N.naviguer(journal.console(), depot,
                             gabarit=lambda: gabarit_pour(capacites),
                             peintre=peintre_pour(capacites))
        self.assertEqual(verdict, CONTINUER)
        self.assertEqual(journal.texte.count("n'est pas une commande d'ici"),
                         5)

    def test_le_decoupage_refuse_tout_ce_qui_n_est_pas_un_chiffre_ASCII(self):
        """`isdigit()` et `int()` ne sont pas d'accord dans les DEUX sens.

        `²` et `①` sont `isdigit()` et `int()` les refuse — c'est la levee
        qu'on corrige. `١` (chiffre arabo-indien) est `isdigit()` et `int()`
        l'AVALE, en rendant 1 : une saisie qui ouvrirait la premiere ligne
        sans qu'on ait tape 1. Les deux cas se regroupent sous la meme regle,
        qui est de n'accepter que l'ASCII.
        """
        for saisie in ("\u00b2", "m\u00b2", "p\u00b2", "\u2460", "\u0661",
                       "m\u0661"):
            with self.subTest(saisie=saisie):
                commande, _ = N._decouper(saisie)
                self.assertEqual(commande, "")
        for accepte in ("12", "m 3", "p7"):
            with self.subTest(saisie=accepte):
                commande, argument = N._decouper(accepte)
                self.assertNotEqual(commande, "")
                self.assertEqual(int(argument), int(argument))


class TestLEntreeDuMenu(unittest.TestCase):

    def test_le_navigateur_est_la_cinquieme_entree_du_catalogue(self):
        arbre = racine(Environnement(sonde=lambda: ()))
        catalogue = [e.cible for e in arbre.entrees
                     if e.libelle == "Catalogue d'ecrans"][0]
        self.assertIsInstance(catalogue, Menu)
        entree = catalogue.entree("5")
        self.assertIsNotNone(entree)
        self.assertEqual(entree.libelle, "Naviguer le catalogue")

    def test_le_preambule_ne_parle_plus_de_trois_entrees(self):
        """Il disait « les deux premieres entrees lisent. La troisieme
        PROMEUT » — faux des qu'il y en a cinq, et c'est une docstring fausse
        a l'echelle d'un ecran."""
        arbre = racine(Environnement(sonde=lambda: ()))
        catalogue = [e.cible for e in arbre.entrees
                     if e.libelle == "Catalogue d'ecrans"][0]
        self.assertNotIn("Les deux premieres entrees lisent",
                         catalogue.preambule)
        self.assertIn("navigateur", catalogue.preambule)
        self.assertEqual(len(catalogue.entrees), 5)

    def test_les_capacites_par_defaut_sont_TOUTES_fausses(self):
        """CONTROLE NEGATIF : cabler la sonde reelle ici fait tomber ce test
        sur un poste de developpement, et reste vert en CI. C'est exactement
        le chemin non exerce par la CI qui tournerait chez l'utilisateur."""
        capacites = Environnement().capacites()
        self.assertEqual(capacites, Capacites())
        self.assertEqual(peintre_pour(capacites).niveau, PeintreNu.niveau)

    def test_la_commande_console_CABLE_la_sonde_reelle(self):
        """CONTROLE NEGATIF : revenir a `parcourir(racine(), Console())` fait
        tomber ce test.

        Sans ce cablage, `env.capacites()` vaut toujours `_capacites_nues` et
        `gabarit_pour` rend toujours `Gabarit(72, 24, INCONNUE)` : mesure
        faite en pilotant `falcon.pyz console` dans un pty regle a 80x24,
        l'accueil imprimait « largeur 72 (inconnue), hauteur 24 ». Deux
        docstrings — celle de ce module et celle de `ecrans.py` — affirmaient
        pourtant la remesure a chaque tour d'un gabarit qui etait une
        constante, et la branche MESUREE de `gabarit_pour` n'etait exercee que
        par les tests.
        """
        import argparse

        import falcon.console as console_module
        from falcon.commandes import principal
        from falcon.console.ecrans import _capacites_nues

        recus: list[object] = []
        vrai_racine = console_module.racine
        vraie_parcourir = console_module.parcourir
        vrai_isatty = principal.sys.stdin.isatty

        def racine_double(env=None):
            recus.append(env)
            return vrai_racine(Environnement(sonde=lambda: ()))

        console_module.racine = racine_double
        console_module.parcourir = lambda menu, console: CONTINUER
        principal.sys.stdin.isatty = lambda: True
        try:
            principal._console(argparse.Namespace())
        finally:
            console_module.racine = vrai_racine
            console_module.parcourir = vraie_parcourir
            principal.sys.stdin.isatty = vrai_isatty

        self.assertEqual(len(recus), 1)
        env = recus[0]
        self.assertIsNotNone(env, "`racine()` a ete appelee sans environnement")
        self.assertIsNot(env.capacites, _capacites_nues)
        # Et ce que la fonction cablee rend est bien une mesure, pas un objet
        # de circonstance : `sonder` sur le vrai `sys.stdout` de la suite.
        mesure = env.capacites()
        self.assertIsInstance(mesure, Capacites)
        self.assertEqual(mesure.flux, "stdout")

        # Le DEFAUT de la dataclass, lui, ne bouge pas : c'est ce qui garde au
        # controle negatif n°2 du lot suivant son mordant.
        self.assertIs(Environnement().capacites, _capacites_nues)

    def test_la_sonde_et_les_capacites_sont_DEUX_champs(self):
        """L'une RAPPORTE une mesure a l'ecran, l'autre DECIDE ce que le rendu
        a le droit d'emettre. Les fusionner ferait dependre tout le rendu de
        la console du terminal de qui lance la suite."""
        champs = Environnement.__dataclass_fields__
        self.assertIn("sonde", champs)
        self.assertIn("capacites", champs)


if __name__ == "__main__":
    unittest.main()
