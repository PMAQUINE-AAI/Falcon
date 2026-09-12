"""Le direct : ce qu'il montre, ce qu'il refuse de montrer, et ce qu'il coute.

Ce lot n'ajoute aucun pouvoir sur SAP. Il ajoute un ECRAN, et un ecran ment
plus facilement qu'un parcours : il n'a pas de resultat qu'on puisse comparer,
il n'a que de la mise en page. Les trois defauts qu'on peut y introduire sans
qu'aucune exception ne se leve sont donc nommes, et chacun a son test.

1. **Un chiffre calcule sur place.** « 62 % de la trace explore » aurait
   l'aspect d'une mesure. Aucun compteur du bilan n'en est un : chacun doit se
   retrouver dans `rapport.rendre`, sur la MEME ligne que son etiquette.
   Apparier une sous-chaine de chiffre dans 127 lignes de prose ne prouverait
   rien — « 5 » s'y trouve partout — donc l'appariement se fait ligne a ligne,
   et dans les DEUX sens : aucun nombre du bilan ne sort de la liste des
   valeurs justifiees.
2. **Une ligne collante qui deborde.** `Rapporteur._ecrire` fait un `ljust`
   sans coupe. Une ligne plus large que la fenetre s'y replie, et le `\\r`
   suivant revient au debut de la ligne REPLIEE : la moitie du bandeau
   precedent reste a l'ecran, definitivement, et rien ne le signale.
3. **Un direct debranche.** La console peut parfaitement afficher son compte
   rendu complet et n'avoir rien montre pendant les trois minutes de rejeu.
   Tous les autres tests de `test_console` resteraient verts.

Et deux refus qu'il faut tenir : **aucun ETA** et **aucune jauge sur les
gestes**. Les deux se mesurent sur le texte rendu, parce qu'un refus qu'aucun
test ne verifie est une intention.
"""

from __future__ import annotations

import ast
import inspect
import re
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

from falcon.commandes import principal
from falcon.console import ecrans
from falcon.console import parcourir, racine
from falcon.exploration import evenements as E
from falcon.exploration import parcours as P
from falcon.exploration.evenements import Evenement, GenreInconnu
from falcon.exploration.rapport import rendre
from falcon.noyau import Identite
from falcon.toile import (
    COULEUR, MARQUE, MESUREE, NU, Capacites, Gabarit, PeintreNu, gabarit_pour,
    peintre_pour, retirer,
)
from falcon.toile import direct as D
from falcon.trace import lire

from tests.test_console import Journal, PORTE_SAP, vers
from tests.test_exploration_parcours import REGISTRE, SapDePapier
from tests.test_trace import MEGATRACE, PROLOGUE

#: Le terminal de la maquette A : un cmd.exe de 80 colonnes, mesure. Le
#: gabarit en retient 79 — la derniere colonne reste libre, parce que conhost
#: n'a pas le repli differe et qu'un glyphe pose dedans fait defiler.
CAPACITES_TERMINAL = Capacites(flux="stderr", interactif=True, colonnes=80,
                               lignes=25, source_taille=MESUREE, ansi=True,
                               couleur=True)

#: Le meme flux, redirige : rien n'est mesure, rien n'est prouve.
CAPACITES_FICHIER = Capacites(flux="stderr")

#: L'identite que le SAP de papier annonce. Le double n'en porte pas par
#: defaut, et un bilan qui ecrirait « systeme ? » ne prouverait rien de
#: l'appariement avec le compte rendu.
IDENTITE = Identite(systeme="QAS", mandant="200", langue="FR",
                    transaction="SESSION_MANAGER",
                    programme="SAPLSMTR_NAVIGATION", dynpro="0100")


def explorer_la_megatrace(observateur=None, *, plafond_gestes=500,
                          plafond_ecrans=500, catalogue=None):
    """La trace de reference contre un SAP qui refuse « IW2ç ».

    Le meme scenario que `test_exploration_direct` : c'est lui qui produit les
    cinq branches, la reprise refusee et la branche finale sans point de
    reprise. Rend (flux, exploration, trace, compte rendu).

    Les deux plafonds et le catalogue s'ouvrent parce que la megatrace seule
    ne produit NI `PLAFOND` — les budgets par defaut sont a 500 — NI
    `ECRAN_CONNU`, la quarantaine etant vide au depart. Les rendre a partir
    d'un `Evenement` a champs vides ne prouverait que « la ligne n'est pas
    blanche » ; un budget qui mord pour de bon et un second rejeu sur le meme
    catalogue produisent les vrais faits, avec leurs vrais champs.
    """
    flux: list[Evenement] = []

    def _noter(evenement: Evenement) -> None:
        flux.append(evenement)
        if observateur is not None:
            observateur(evenement)

    sap = SapDePapier()
    sap.identite = IDENTITE
    sap.refusees = {"IW2ç"}
    trace = lire(MEGATRACE)
    if catalogue is not None:
        exploration = P.explorer(trace, sap, catalogue=catalogue,
                                 plafond_gestes=plafond_gestes,
                                 plafond_ecrans=plafond_ecrans,
                                 registre=REGISTRE, observateur=_noter)
    else:
        with tempfile.TemporaryDirectory() as bac:
            exploration = P.explorer(trace, sap, catalogue=bac,
                                     plafond_gestes=plafond_gestes,
                                     plafond_ecrans=plafond_ecrans,
                                     registre=REGISTRE, observateur=_noter)
    return flux, exploration, trace, rendre(exploration, trace)


#: Deux gestes, aucune branche, aucune reprise, aucun saut.
#:
#: C'est la forme de rejeu la PLUS COURANTE — celle qui va au bout sans
#: incident — et c'est precisement celle sur laquelle trois des onze
#: justifications du bilan n'ont AUCUNE ligne d'appui dans le compte rendu :
#: `rapport.rendre` n'ecrit le bloc des branches que s'il y en a, celui des
#: reprises que s'il y en a, et `_partition` n'ecrit une ligne que si son
#: compte n'est pas nul. Un appariement qui ne s'exerce que sur la megatrace
#: ne rencontre jamais le cas ou l'invariant cede.
TRACE_PROPRE = (PROLOGUE
                + 'session.findById("wnd[0]/tbar[1]/btn[17]").press\r\n'
                + 'session.findById("wnd[0]/usr/txtV-LOW").text = "X"\r\n')


def explorer_une_trace_propre():
    """Le meme scenario, sur une trace qui ne casse rien. Meme retour."""
    flux: list[Evenement] = []
    sap = SapDePapier()
    sap.identite = IDENTITE
    with tempfile.TemporaryDirectory() as bac:
        chemin = Path(bac) / "propre.vbs"
        chemin.write_text(TRACE_PROPRE, encoding="utf-16")
        trace = lire(chemin)
        exploration = P.explorer(trace, sap, catalogue=bac,
                                 plafond_gestes=500, plafond_ecrans=500,
                                 registre=REGISTRE, observateur=flux.append)
    return flux, exploration, trace, rendre(exploration, trace)


def cadran_de(flux) -> D.Cadran:
    cadran = D.Cadran()
    for evenement in flux:
        cadran = D.avancer(cadran, evenement)
    return cadran


def lignes_du_flux(flux, gabarit: Gabarit, peintre=None) -> list[str]:
    """Le direct entier, en lignes, tel qu'un peintre le pose."""
    peintre = peintre or PeintreNu()
    cadran = D.Cadran()
    lignes: list[str] = []
    for evenement in flux:
        cadran = D.avancer(cadran, evenement)
        if evenement.genre == E.DEPART:
            for bloc in D.entete(cadran, gabarit):
                lignes += peintre.peindre(bloc, gabarit)
        bloc = D.ligne_evenement(evenement, gabarit)
        if bloc is not None:
            lignes += peintre.peindre(bloc, gabarit)
    return lignes


def lignes_du_bilan(cadran: D.Cadran, gabarit: Gabarit,
                    peintre=None) -> list[str]:
    peintre = peintre or PeintreNu()
    return [ligne for bloc in D.bilan(cadran, gabarit)
            for ligne in peintre.peindre(bloc, gabarit)]


def evenement(genre: str, **champs) -> Evenement:
    return Evenement(genre=genre, **champs)


class FluxDePapier:
    """Un flux de sortie qui garde tout, y compris les retours chariot."""

    def __init__(self) -> None:
        self.morceaux: list[str] = []
        self.vidages = 0

    def write(self, texte: str) -> int:
        self.morceaux.append(texte)
        return len(texte)

    def flush(self) -> None:
        self.vidages += 1

    @property
    def texte(self) -> str:
        return "".join(self.morceaux)


# =========================================================================


class TestCeQueLeBilanAFFIRME(unittest.TestCase):
    """Le compte rendu est le seul juge. Le direct n'en est que l'avance."""

    def _apparier(self, flux, compte_rendu):
        """Chaque valeur du bilan, et la ligne du compte rendu qui la porte.

        Dans les deux sens, et avec l'exemption DECLAREE au milieu :

          - une justification ordinaire doit trouver une ligne qui porte a la
            fois son repere et sa valeur ;
          - une justification `absent_si_zero` dont la valeur est zero doit
            trouver le CONTRAIRE : aucune ligne ne porte son repere. Ce n'est
            pas un test qu'on saute, c'est la mesure de l'exemption ;
          - aucun nombre rendu par le bilan ne sort des valeurs declarees.
        """
        cadran = cadran_de(flux)
        gabarit = gabarit_pour(CAPACITES_TERMINAL)
        lignes_du_rapport = compte_rendu.splitlines()

        justifiees = D.justifications(cadran)
        self.assertTrue(justifiees, "aucune justification : le test passerait "
                                    "a vide")
        for justification in justifiees:
            with self.subTest(etiquette=justification.etiquette):
                portant = [ligne for ligne in lignes_du_rapport
                           if justification.repere in ligne]
                if justification.absent_si_zero and justification.valeur == "0":
                    self.assertEqual(
                        portant, [],
                        f"« {justification.etiquette} » se declare exemptee "
                        f"a zero — le compte rendu ne nomme pas ce qui n'a "
                        f"pas eu lieu — et pourtant une ligne porte "
                        f"{justification.repere!r}. L'exemption est fausse : "
                        f"l'appariement doit alors etre exige.")
                    continue
                appariees = [
                    ligne for ligne in portant
                    if justification.valeur in re.findall(r"[\w?]+", ligne)]
                self.assertTrue(
                    appariees,
                    f"« {justification.etiquette} » vaut "
                    f"{justification.valeur!r} au bilan, et AUCUNE ligne du "
                    f"compte rendu ne porte a la fois "
                    f"{justification.repere!r} et cette valeur. Un compteur "
                    f"que le compte rendu ne dit pas est un compteur calcule "
                    f"sur place.")

        # L'autre sens : tout nombre du bilan sort de cette liste, ou d'un
        # plafond tape par l'humain. La duree est retiree AVANT : ce n'est pas
        # un compteur de l'exploration, c'est l'horloge monotone, et le compte
        # rendu n'en porte aucune. `\d+` et non `\d\d` sur les heures : au-dela
        # de 99 h, `100:00:00` laisserait un « 1 » orphelin qui ferait tomber
        # l'assertion pour une raison etrangere a ce qu'elle verifie.
        rendu = "\n".join(lignes_du_bilan(cadran, gabarit))
        sans_duree = re.sub(r"\d+:\d\d:\d\d", "", rendu)
        nombres = set(re.findall(r"\d+", sans_duree))
        permis = {j.valeur for j in justifiees if j.valeur.isdigit()}
        permis |= {str(cadran.plafond_gestes), str(cadran.plafond_ecrans)}
        self.assertEqual(
            nombres - permis, set(),
            "le bilan affiche un nombre qui n'est justifie par aucune ligne "
            "du compte rendu")

        # Et le trou que la valeur seule laisserait ouvert : « ecrans non
        # explores  5 » recyclerait un nombre PERMIS sous une etiquette
        # inventee, et passerait le controle ci-dessus sans broncher. Toute
        # ligne du bilan qui porte un chiffre doit donc porter aussi une
        # etiquette declaree.
        etiquettes = [j.etiquette for j in justifiees]
        for ligne in sans_duree.splitlines():
            if not re.search(r"\d", ligne):
                continue
            with self.subTest(ligne=ligne):
                self.assertTrue(
                    [e for e in etiquettes if e in ligne],
                    f"la ligne porte un chiffre sous une etiquette que "
                    f"`justifications` ne declare pas : {ligne!r}")

        # Un « / 0 » se lirait comme un budget epuise, alors qu'il veut dire
        # « personne n'en a declare » : trois lignes du bilan sur cinq passent
        # par ce cas, et rien ne l'epinglait.
        self.assertNotIn(" / 0", rendu)
        return rendu

    def test_le_direct_n_affiche_aucun_chiffre_que_le_rapport_ne_dise(self):
        """CONTROLE NEGATIF : faire afficher au bilan un compteur calcule sur
        place — « 62 % de la trace explore » — fait tomber ce test.

        Il apparie ETIQUETTE ET VALEUR SUR LA MEME LIGNE du compte rendu,
        jamais une sous-chaine de chiffre dans 127 lignes de prose : « 5 » s'y
        trouve dans un numero de geste, dans une ligne de partition et dans un
        identifiant, et un test qui se contenterait de `assertIn` serait vert
        quoi qu'on affiche.

        Et il mord DANS LES DEUX SENS, ce qui est la moitie qui manquait :
        chaque valeur declaree doit se retrouver dans le compte rendu, ET
        aucun nombre rendu par le bilan ne doit sortir des valeurs declarees.
        Sans le second sens, une ligne inventee ajoutee au bilan n'aurait
        simplement pas de justification a verifier.
        """
        flux, _, _, compte_rendu = explorer_la_megatrace()
        self._apparier(flux, compte_rendu)

    def test_l_appariement_tient_AUSSI_sur_un_rejeu_sans_incident(self):
        """La forme la plus courante, et celle ou l'invariant cedait.

        Sur la megatrace, les onze justifications trouvent leur ligne parce
        que tout est arrive : cinq branches, cinq reprises, quarante-six
        gestes sautes. Sur une trace de deux gestes qui se termine
        proprement, `rapport.rendre` n'ecrit ni le bloc des branches, ni
        celui des reprises, et `_partition` n'ecrit pas la ligne des sautes :
        TROIS des onze reperes sont introuvables. Le chiffre affiche (zero)
        restait vrai, mais la garantie « chaque valeur nomme une ligne du
        compte rendu » ne tenait pas, et le test qui la prouvait ne visitait
        jamais le cas.

        CONTROLE NEGATIF : retirer `absent_si_zero=True` d'une des trois
        entrees de `justifications` fait tomber ce test, et lui seul.
        """
        flux, exploration, _, compte_rendu = explorer_une_trace_propre()
        self.assertEqual(len(exploration.branches), 0)
        self.assertEqual(len(exploration.reprises), 0)
        self.assertEqual(exploration.gestes_sautes, 0)
        self._apparier(flux, compte_rendu)
        # Et le bilan continue de dire ces trois zeros : zero est une reponse,
        # et taire une ligne qui vaut zero rendrait son absence ambigue avec
        # un champ oublie.
        rendu = "\n".join(lignes_du_bilan(cadran_de(flux),
                                          gabarit_pour(CAPACITES_TERMINAL)))
        for etiquette in ("branches tombees", "reprises tapees",
                          "gestes emportes par un saut"):
            self.assertIn(etiquette, rendu)

    def test_les_trois_exemptions_sont_exactement_celles_que_le_rapport_tait(
            self):
        """L'exemption ne doit pas devenir une porte de sortie.

        Sur la megatrace, ou tout est arrive, les onze justifications — les
        trois exemptees comprises — ont une valeur NON NULLE et doivent donc
        toutes s'apparier. C'est ce qui empeche qu'on marque `absent_si_zero`
        sur une entree pour se dispenser de la justifier.
        """
        flux, _, _, _ = explorer_la_megatrace()
        cadran = cadran_de(flux)
        exemptees = [j for j in D.justifications(cadran) if j.absent_si_zero]
        self.assertEqual(
            {j.etiquette for j in exemptees},
            {"branches tombees", "reprises tapees",
             "gestes emportes par un saut"})
        for justification in exemptees:
            with self.subTest(etiquette=justification.etiquette):
                self.assertNotEqual(justification.valeur, "0")

    def test_le_bilan_ne_pretend_pas_compter_les_releves(self):
        """`p.releves` vaut 29 sur la trace de reference, et le flux ne porte
        aucun fait par releve : un releve qui ne verse rien et ne reconnait
        rien n'emet rien du tout.

        Reconstruire le compte depuis les ecrans verses et connus donnerait
        cinq. Un chiffre d'aspect normal, faux d'un facteur six — donc le
        bilan n'en parle pas, et ce test epingle le silence.
        """
        flux, exploration, _, _ = explorer_la_megatrace()
        cadran = cadran_de(flux)
        self.assertEqual(exploration.releves, 29)
        self.assertEqual(cadran.versees + cadran.connues, 5)
        rendu = "\n".join(lignes_du_bilan(cadran,
                                          gabarit_pour(CAPACITES_TERMINAL)))
        self.assertNotIn("releve", rendu)

    def test_le_bilan_compte_ce_que_le_parcours_a_compte(self):
        """Les compteurs du cadran sont ceux de l'`Exploration`, un par un.

        CONTROLE NEGATIF : compter les `ECRAN_VERSE` au lieu de recopier
        `evenement.versees` fait tomber ce test le jour ou un versement
        n'emet pas — c'est-a-dire au premier plafond.
        """
        flux, exploration, _, _ = explorer_la_megatrace()
        cadran = cadran_de(flux)
        self.assertEqual(cadran.versees, len(exploration.versees))
        self.assertEqual(cadran.connues, len(exploration.deja_connues))
        self.assertEqual(cadran.branches, len(exploration.branches))
        self.assertEqual(cadran.reprises, len(exploration.reprises))
        self.assertEqual(cadran.sauvegardes_refusees,
                         len(exploration.sauvegardes_refusees))
        self.assertEqual(cadran.sautes, exploration.gestes_sautes)
        self.assertEqual(cadran.actions, exploration.actions_envoyees)
        self.assertEqual(cadran.etat, exploration.etat)

    def test_le_cadran_est_immuable(self):
        cadran = D.Cadran()
        with self.assertRaises(FrozenInstanceError):
            cadran.actions = 12                     # type: ignore[misc]
        suivant = D.avancer(cadran, evenement(E.GESTE, ordre=4, actions=2))
        self.assertEqual(cadran.ordre, 0)
        self.assertEqual(suivant.ordre, 4)


class TestLesDeuxRefus(unittest.TestCase):
    """Un ETA faux est pire qu'un ETA absent : on planifie dessus."""

    def test_le_direct_n_annonce_aucun_temps_restant(self):
        """46 des 90 gestes de la trace de reference partent EN BLOC quand une
        branche tombe : `moyenne x restants` y serait faux d'un facteur cinq.

        Le bandeau affiche le temps ECOULE, qui est une mesure. Ce test
        epingle le refus sur le TEXTE, parce qu'un refus qu'aucun test ne
        verifie est une intention.
        """
        flux, _, _, _ = explorer_la_megatrace()
        cadran = cadran_de(flux)
        gabarit = gabarit_pour(CAPACITES_TERMINAL)
        # Sur le BANDEAU et le BILAN, et pas sur le flux : le flux recopie les
        # motifs du parcours, ou « SAP est reste sur 'IW39' » est une phrase
        # de SAP et non une prevision. Un test qui chercherait le mot partout
        # tomberait pour une raison qui n'a rien a voir avec ce qu'il verifie.
        rendu = "\n".join([D.ligne_collante(cadran, gabarit)]
                          + lignes_du_bilan(cadran, gabarit))
        for interdit in ("reste", "restant", "ETA", "fini dans", "%"):
            with self.subTest(interdit=interdit):
                self.assertNotIn(interdit, rendu)
        # Et ce qu'il affiche a la place : une duree ecoulee, qui se lit.
        self.assertRegex(D.ligne_collante(cadran, gabarit),
                         r"\d\d:\d\d:\d\d$")

    def test_aucune_jauge_ne_porte_sur_les_gestes(self):
        """Elle avancerait sur des gestes SAUTES : 100 % d'une trace vue a
        moitie. Les deux seuls denominateurs permis sont des budgets tapes.

        Le test porte sur la barre REELLEMENT dessinee, et non sur une barre
        recalculee a cote. La version precedente faisait
        `ligne.partition(D.jauge(21, 500))` : des que la barre dessinee
        differait, `partition` rendait `(ligne, "", "")`, donc `avant` etait
        la ligne entiere — qui contient « actions » — et `apres` la chaine
        vide — qui ne contient pas « geste ». Les deux assertions etaient
        vraies quoi qu'on dessine, et la jauge interdite passait.

        CONTROLE NEGATIF, en deux moities, chacune mordant dans son regime de
        largeur : remplacer le denominateur par `cadran.total` fait tomber
        l'egalite sur la barre ; poser une SECONDE jauge sur les gestes fait
        tomber le compte de barres a 110 colonnes, et l'absence de la jauge
        d'actions le fait tomber a 79.
        """
        cadran = D.Cadran(commence=True, ordre=34, total=90, actions=21,
                          plafond_gestes=500, versees=4, plafond_ecrans=500,
                          monotone_ms=161_000)
        for largeur in (79, 110):
            with self.subTest(largeur=largeur):
                ligne = D.ligne_collante(
                    cadran, Gabarit(colonnes=largeur, source=MESUREE))
                self.assertIn("[geste 034/090]", ligne)
                self.assertIn("actions 021/500", ligne)
                self.assertIn("ecrans 004/500", ligne)
                self.assertIn("00:02:41", ligne)

                # UNE barre, et c'est celle des actions : le numerateur et le
                # denominateur sont epingles tous les deux.
                barres = re.findall(r"\[[#-]+\]", ligne)
                self.assertEqual(len(barres), 1, ligne)
                self.assertEqual(
                    barres[0], D.jauge(21, 500),
                    "la barre dessinee n'a pas pour denominateur un budget "
                    "tape : elle porte sur les gestes")

                avant, _, apres = ligne.partition(barres[0])
                self.assertIn("actions", avant)
                self.assertNotIn("geste", apres)

    def test_une_jauge_sans_denominateur_n_est_pas_dessinee(self):
        """Ni vide, ni pleine : absente. Et surtout, elle ne divise pas.

        `Cadran()` neuf porte des plafonds a zero — c'est l'etat d'avant le
        premier fait. Une jauge qui diviserait la leverait une
        `ZeroDivisionError`, que `_Parcours.emettre` avalerait en la comptant
        comme une panne d'AFFICHEUR : le compte rendu accuserait le terminal
        pour une division par zero de ce fichier-ci.
        """
        self.assertEqual(D.jauge(3, 0), "")
        self.assertEqual(D.jauge(3, -1), "")
        # Les deux autres garde-fous de la fonction, qu'aucun appelant
        # n'atteint aujourd'hui : une largeur nulle ne dessine pas un cadre
        # vide `[]`, et un numerateur negatif ne dessine pas une barre a
        # l'envers. Les laisser sans assertion laissait deux lignes qu'on
        # pouvait retirer sans qu'un test bronche.
        self.assertEqual(D.jauge(3, 10, 0), "")
        self.assertEqual(D.jauge(-5, 10), "[----------]")
        self.assertEqual(D.jauge(0, 10), "[----------]")
        self.assertEqual(D.jauge(10, 10), "[##########]")
        # Et au-dela du plafond, la barre ne deborde pas de son cadre.
        self.assertEqual(D.jauge(99, 10), "[##########]")
        ligne = D.ligne_collante(D.Cadran(), Gabarit(colonnes=79,
                                                     source=MESUREE))
        self.assertIn("[geste 000/000]", ligne)
        self.assertNotIn("[#", ligne)
        self.assertNotIn("[-", ligne)

    def test_le_rang_est_dit_POSITION_une_fois_et_une_seule(self):
        """`034/090` se lit spontanement comme un avancement. L'en-tete le
        dementit, et il le fait UNE fois : repete a chaque ligne il serait du
        bruit, absent il laisserait chacun conclure."""
        flux, _, _, _ = explorer_la_megatrace()
        lignes = lignes_du_flux(flux, gabarit_pour(CAPACITES_TERMINAL))
        portant = [ligne for ligne in lignes if "POSITION" in ligne]
        self.assertEqual(len(portant), 1, portant)
        self.assertIn("pas un avancement", portant[0])


class TestLaLigneCollante(unittest.TestCase):

    def test_la_ligne_collante_ne_remplit_jamais_la_derniere_colonne(self):
        """CONTROLE NEGATIF : remplacer la troncature a `gabarit.colonnes` par
        le `ljust` seul de `Rapporteur` fait tomber ce test.

        Le cas est construit pour etre indiscutable : des compteurs a
        soixante chiffres donnent une ligne de plus de deux cents caracteres
        sur un gabarit de 79. Ce qui se passerait sans coupe n'est pas une
        ligne laide : la ligne se replie, le `\\r` suivant revient au debut de
        la ligne REPLIEE, et la moitie du bandeau precedent reste a l'ecran
        pour toujours.
        """
        enorme = 10 ** 60
        cadran = D.Cadran(commence=True, ordre=enorme, total=enorme,
                          actions=enorme, plafond_gestes=enorme,
                          versees=enorme, plafond_ecrans=enorme)
        gabarit = Gabarit(colonnes=79, source=MESUREE)
        ligne = D.ligne_collante(cadran, gabarit)
        self.assertGreater(len(D.ligne_collante(
            replace(cadran, plafond_gestes=0), Gabarit(colonnes=10_000))), 200,
            "le cas de mesure ne produit plus une ligne trop longue : ce test "
            "ne prouverait plus rien")
        self.assertLessEqual(len(ligne), gabarit.colonnes)
        self.assertTrue(ligne.endswith(MARQUE))
        self.assertNotIn("\n", ligne)
        self.assertNotIn("\r", ligne)

    def test_la_ligne_collante_tient_sur_toute_la_matrice_des_largeurs(self):
        """La matrice du plan, plus les deux largeurs qui bornent la jauge.

        Et ce que le sacrifice de la jauge fait VRAIMENT, mesure : il rend
        une ligne COMPLETE de 60 a 72 colonnes, et rien de plus. A 73 la
        jauge tient. En dessous de 60, la retirer ne suffit plus et c'est
        `couper` qui tranche — a 40 colonnes il ne reste ni horloge ni
        fraction d'ecrans. Ecrire « a 40 colonnes c'est la jauge qui saute »
        faisait dire au code plus qu'il ne fait, et la branche du sacrifice
        n'etait exercee par rien : la neutraliser laissait tout au vert.
        """
        cadran = D.Cadran(commence=True, ordre=34, total=90, actions=21,
                          plafond_gestes=500, versees=4, plafond_ecrans=500,
                          monotone_ms=161_000)
        barre = D.jauge(21, 500)
        for largeur in (79, 73, 72, 60, 50, 110, 40, 20, 1):
            with self.subTest(largeur=largeur):
                ligne = D.ligne_collante(cadran,
                                         Gabarit(colonnes=largeur,
                                                 source=MESUREE))
                self.assertLessEqual(len(ligne), largeur)
        def _ligne(largeur):
            return D.ligne_collante(cadran, Gabarit(colonnes=largeur,
                                                    source=MESUREE))
        self.assertIn(barre, _ligne(73))
        self.assertIn(barre, _ligne(79))
        self.assertNotIn(barre, _ligne(72))
        self.assertNotIn(barre, _ligne(40))
        # Sacrifiee, la ligne est COMPLETE jusqu'a 60 colonnes : l'horloge y
        # est encore. En dessous, elle ne l'est plus.
        self.assertTrue(_ligne(60).endswith("00:02:41"))
        self.assertTrue(_ligne(72).endswith("00:02:41"))
        self.assertTrue(_ligne(59).endswith(MARQUE))

    def test_sans_largeur_mesuree_aucun_bandeau(self):
        """Une largeur devinee donne une ligne qui se replie, et le repli est
        exactement ce que le retour chariot ne sait pas defaire.

        Le flux, lui, sort quand meme : il n'a jamais ce probleme.
        """
        flux, _, _, _ = explorer_la_megatrace()
        sortie = FluxDePapier()
        diffuseur = D.Diffuseur(sortie, Capacites(flux="stderr",
                                                  interactif=True))
        self.assertFalse(diffuseur.bandeau)
        for evenement_ in flux:
            diffuseur(evenement_)
        diffuseur.clore()
        self.assertNotIn("\r", sortie.texte)
        self.assertIn("BRANCHE  sauvegarde", sortie.texte)

        # L'AUTRE moitie de la condition, qu'aucune fixture n'exercait : une
        # largeur parfaitement mesuree sur un flux qui n'est PAS un terminal.
        # Un `cron` qui redirige, un service. Le retour chariot n'y
        # repositionne rien : le bandeau y serait un plat de `\r` dans un
        # fichier. Sans ce cas, retirer `capacites.interactif and` de la
        # condition ne faisait rien tomber.
        muet = D.Diffuseur(FluxDePapier(),
                           Capacites(flux="stderr", interactif=False,
                                     colonnes=80, lignes=25,
                                     source_taille=MESUREE))
        self.assertTrue(muet._gabarit.mesuree,
                        "la largeur EST mesuree : sans cela le test prouve "
                        "l'autre moitie de la condition")
        self.assertFalse(muet.bandeau)


class TestLeDiffuseur(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # UN seul parcours pour toute la classe, et c'est necessaire : deux
        # explorations portent deux catalogues temporaires differents, et
        # l'en-tete du direct affiche le chemin du catalogue. Comparer deux
        # diffusions de deux parcours ferait echouer l'invariant de la
        # couleur sur un nom de dossier.
        cls.flux, cls.exploration, _, cls.compte_rendu = (
            explorer_la_megatrace())

    def _diffuser(self, capacites, *, forcer_nu=False):
        sortie = FluxDePapier()
        diffuseur = D.Diffuseur(sortie, capacites, forcer_nu=forcer_nu)
        for evenement_ in self.flux:
            diffuseur(evenement_)
        diffuseur.clore()
        return sortie, diffuseur, self.exploration, self.compte_rendu

    def test_redirige_le_fichier_se_lit_tel_quel(self):
        """Maquette A, second etat : le meme flux, sans la derniere ligne.

        Pas de `\\r`, pas un caractere de controle. C'est ce qui distingue ce
        module de `Rapporteur`, qui se tait entierement hors terminal : lui
        n'ecrit QUE du redessin, ici le flux est fait de lignes entieres.
        """
        sortie, diffuseur, _, _ = self._diffuser(CAPACITES_FICHIER)
        self.assertFalse(diffuseur.bandeau)
        self.assertNotIn("\r", sortie.texte)
        self.assertNotIn("\x1b", sortie.texte)
        self.assertIn("REPRISE  IH06 demandee -> obtenue IH06   ACCEPTEE",
                      sortie.texte)
        self.assertTrue(sortie.texte.endswith("\n"))

    def test_sur_un_terminal_mesure_le_bandeau_se_reecrit_sur_place(self):
        """Le bandeau est COLLANT : chaque redessin est une seule ligne.

        La mesure porte sur les APPELS a `write`, que `FluxDePapier` garde un
        par un, et non sur le texte recolle. L'assertion precedente —
        `assertNotIn("\n", morceau.split("\n")[0])` — etait TAUTOLOGIQUE :
        `s.split("\n")[0]` est par construction le prefixe de `s` avant le
        premier saut de ligne, donc il ne peut jamais en contenir un. Elle
        etait vraie pour toute entree, y compris pour un bandeau qui DEFILE.

        CONTROLE NEGATIF : ajouter un `\n` a l'ecriture de `_redessiner` fait
        tomber ce test — le direct deverserait alors un bandeau empile par
        geste au lieu d'un seul, reecrit sur place.
        """
        sortie, diffuseur, _, _ = self._diffuser(CAPACITES_TERMINAL)
        self.assertTrue(diffuseur.bandeau)
        redessins = [m for m in sortie.morceaux if m.startswith("\r")]
        self.assertTrue(redessins,
                        "aucun redessin : le test passerait a vide, et c'est "
                        "exactement le defaut qu'on corrige")
        for morceau in redessins:
            with self.subTest(morceau=morceau):
                self.assertNotIn("\n", morceau)

    def test_le_bandeau_est_efface_AVANT_chaque_ligne_de_fait(self):
        """Sans l'effacement, la queue du bandeau precedent reste accrochee a
        droite de chaque ligne de fait, sur un vrai terminal, pendant toute
        l'exploration. Invisible en CI : dans un `FluxDePapier`, un `\r`
        n'efface rien.

        L'assertion precedente — `assertIn("\r" + " " * 10, texte)` — etait
        satisfaite par le SEUL effacement de `clore()`, qui tourne toujours.
        Elle etait vraie que `_poser` efface ou non. Celle-ci compte : il y a
        au moins un effacement complet par ligne de fait.

        CONTROLE NEGATIF : retirer `self._effacer()` de `_poser` fait tomber
        ce test.
        """
        sortie, diffuseur, _, _ = self._diffuser(CAPACITES_TERMINAL)
        largeur = gabarit_pour(CAPACITES_TERMINAL).colonnes
        effacements = [m for m in sortie.morceaux
                       if m.startswith("\r") and m.endswith("\r")
                       and not m.strip()]
        lignes_de_fait = [m for m in sortie.morceaux if m.endswith("\n")]
        self.assertTrue(lignes_de_fait)
        self.assertGreaterEqual(
            len(effacements), len(lignes_de_fait) - len(effacements),
            "moins d'effacements que de poses : le bandeau n'est pas efface "
            "avant chaque ecriture de ligne entiere")
        # Et l'effacement couvre bien toute la largeur posee, jamais moins.
        self.assertTrue(any(len(m) - 2 >= 40 for m in effacements),
                        f"aucun effacement large : {effacements[:3]!r}")
        self.assertLessEqual(max(len(m) - 2 for m in effacements), largeur)

    def test_le_diffuseur_ne_peint_que_ce_que_le_flux_a_prouve(self):
        """La garde n°9, vue depuis le direct.

        CONTROLE NEGATIF : remplacer `peintre_pour(capacites)` par
        `PeintreColore()` fait tomber la premiere moitie. Et la seconde
        moitie est ce qui empeche le test d'etre vert pour rien : sur un flux
        qui a TOUT prouve, des sequences sortent bel et bien.
        """
        nu, _, _, _ = self._diffuser(CAPACITES_FICHIER)
        self.assertNotIn("\x1b", nu.texte)
        colore, _, _, _ = self._diffuser(CAPACITES_TERMINAL)
        self.assertIn("\x1b", colore.texte)

    def test_sans_couleur_retire_le_decor_et_rien_d_autre(self):
        """`--sans-couleur` : le meme texte, aux sequences pres — et a UNE
        ligne pres, qui est nommee.

        L'egalite se lit dans les deux sens, c'est `retirer` qui la rend
        demontrable plutot qu'esperee. La seule difference permise est la
        banniere en texte nu, qui n'a rien a dementir au niveau NU et qui
        serait du bruit dans un fichier redirige. Elle est soustraite ICI,
        nommement, et pas absorbee par un normalisateur : le jour ou une
        seconde ligne divergerait, ce test tomberait.
        """
        colore, _, _, _ = self._diffuser(CAPACITES_TERMINAL)
        sans, diffuseur, _, _ = self._diffuser(CAPACITES_TERMINAL,
                                               forcer_nu=True)
        self.assertNotIn("\x1b", sans.texte)
        banniere, _, reste = retirer(colore.texte).partition("\n")
        self.assertIn("--sans-couleur", banniere)
        self.assertEqual(reste, sans.texte)
        # Refuser la couleur ne refuse pas de savoir ou finit l'ecran.
        self.assertTrue(diffuseur.bandeau)

    def test_clore_deux_fois_ne_pose_qu_un_bilan(self):
        """Elle est appelee depuis un `finally` ET depuis la fin normale."""
        flux, _, _, _ = explorer_la_megatrace()
        sortie = FluxDePapier()
        diffuseur = D.Diffuseur(sortie, CAPACITES_TERMINAL)
        for evenement_ in flux:
            diffuseur(evenement_)
        diffuseur.clore()
        diffuseur.clore()
        self.assertEqual(sortie.texte.count("bilan de la cartographie"), 1)

    def test_clore_avant_le_premier_fait_ne_pose_aucun_bilan(self):
        """Une exploration qui n'a pas commence n'a pas de bilan.

        Un bilan a zero se lirait comme une exploration qui n'a rien trouve,
        alors qu'elle n'a rien tente : c'est le cas d'un `connecter()` qui
        leve avant le premier ecran.
        """
        sortie = FluxDePapier()
        D.Diffuseur(sortie, CAPACITES_TERMINAL).clore()
        self.assertEqual(sortie.texte, "")

    def test_le_diffuseur_n_avale_aucune_exception(self):
        """Le comptage des pannes appartient a `_Parcours.emettre`, et a lui
        seul : un second filet ici rendrait `pannes_d_affichage` faux, et le
        compte rendu affirmerait par son silence qu'on a tout vu.

        Le cas mesure est celui d'un flux qui se ferme — `| more` puis `q`,
        la croix de la fenetre, une liaison RDP qui lache.
        """
        class FluxFerme(FluxDePapier):
            def write(self, texte: str) -> int:
                raise BrokenPipeError(32, "Broken pipe")

        diffuseur = D.Diffuseur(FluxFerme(), CAPACITES_TERMINAL)
        with self.assertRaises(BrokenPipeError):
            diffuseur(evenement(E.ENVOYE, ordre=4, verbe="press",
                                cible="wnd[0]"))

        _, exploration, _, _ = explorer_la_megatrace(
            observateur=D.Diffuseur(FluxFerme(), CAPACITES_TERMINAL))
        self.assertTrue(exploration.coupure_d_affichage)
        self.assertEqual(exploration.pannes_d_affichage, 0)
        self.assertEqual(exploration.actions_envoyees, 33)

    def test_le_direct_ne_change_rien_au_parcours(self):
        """Le seul sujet qui compte : la production ne bouge pas d'un geste."""
        _, sans, _, _ = explorer_la_megatrace()
        _, avec, _, _ = explorer_la_megatrace(
            observateur=D.Diffuseur(FluxDePapier(), CAPACITES_TERMINAL))
        self.assertEqual(sans.partition, avec.partition)
        self.assertEqual([b.categorie for b in sans.branches],
                         [b.categorie for b in avec.branches])
        self.assertEqual(sans.dumps, avec.dumps)
        self.assertEqual(avec.pannes_d_affichage, 0)
        self.assertEqual(avec.emissions_impossibles, 0)


class TestLeRenduDesFaits(unittest.TestCase):
    """Les maquettes A et C sont le contrat visuel."""

    def test_chaque_genre_du_flux_a_sa_ligne_ou_son_silence(self):
        """Aucun genre ne disparait par accident : ceux qui ne font pas de
        ligne sont NOMMES, et les autres en font une.

        CONTROLE NEGATIF : retirer une entree de `MARQUES` ne suffit pas a
        faire disparaitre une ligne — c'est `SANS_LIGNE` qui decide — et c'est
        precisement pour cela que les deux sont testes separement.
        """
        flux, _, _, _ = explorer_la_megatrace()
        gabarit = gabarit_pour(CAPACITES_TERMINAL)
        vus = {evenement_.genre for evenement_ in flux}
        # La megatrace ne produit ni `PLAFOND` — les deux budgets sont a 500 —
        # ni `ECRAN_CONNU` : la quarantaine est vide au depart. Les deux sont
        # produits POUR DE BON plus bas, par un budget qui mord et par un
        # second rejeu sur le meme catalogue, et leurs lignes y sont lues.
        self.assertEqual(vus | {E.PLAFOND, E.ECRAN_CONNU}, set(E.GENRES))

        # L'exhaustivite est VERIFIEE et non rattrapee. C'est ce qui remplace
        # le repli « un genre connu de GENRES mais pas d'ici sort en clair » :
        # celui-la n'etait atteignable par rien, donc personne ne l'avait vu
        # tourner, et il donnait au lecteur l'impression d'une securite. Cette
        # egalite-ci tombe le jour de l'oubli.
        self.assertEqual(set(E.GENRES), set(D.MARQUES) | set(D.SANS_LIGNE))
        self.assertEqual(set(D.MARQUES) & set(D.SANS_LIGNE), set())
        # Et le ton : chaque genre qui fait une ligne en a un, sauf `REPRISE`
        # dont le ton se decide sur `acceptee`.
        self.assertEqual(set(D.TONS_DU_DIRECT) | {E.REPRISE}, set(D.MARQUES))

        for genre in sorted(E.GENRES):
            premier = next((e for e in flux if e.genre == genre),
                           evenement(genre))
            with self.subTest(genre=genre):
                bloc = D.ligne_evenement(premier, gabarit)
                if genre in D.SANS_LIGNE:
                    self.assertIsNone(bloc)
                else:
                    self.assertIsNotNone(bloc)
                    self.assertTrue(
                        PeintreNu().peindre(bloc, gabarit)[0].strip())

    def test_un_genre_sans_forme_de_ligne_est_REFUSE(self):
        """Un refus vaut mieux qu'une valeur devinee.

        Le repli precedent — « il sort en clair plutot que de disparaitre » —
        etait inatteignable : `set(GENRES) - set(MARQUES) - SANS_LIGNE` est
        vide, et `_corps` n'est appelee que pour les genres couverts par un
        `if` explicite. Le remplacer par `raise AssertionError` laissait la
        suite entiere verte. Ici, le chemin est exerce.
        """
        # `Evenement` refuse deja un genre hors `GENRES` a la construction —
        # c'est la premiere barriere, et elle tient. Le double sert a
        # atteindre la SECONDE, celle du direct : le jour ou un genre entre
        # dans `GENRES` et qu'on oublie de lui donner une ligne ici.
        class GenreNeuf:
            genre = "genre_qui_n_existe_pas"
            motif = ""

        with self.assertRaises(GenreInconnu):
            evenement("genre_qui_n_existe_pas")
        with self.assertRaises(ValueError):
            D._corps(GenreNeuf(), 70)
        with self.assertRaises(KeyError):
            # Et en amont : `MARQUES` est lue par INDEXATION, donc un genre
            # absent de la table leve au lieu de sortir sans marque et sans
            # ton, c'est-a-dire d'un aspect normal.
            D.ligne_evenement(GenreNeuf(),
                              gabarit_pour(CAPACITES_TERMINAL))

    def test_le_ton_d_une_reprise_dit_si_elle_a_ete_acceptee(self):
        """Le refus de reprise est ce qui change tout ce qui sera explore
        ensuite : sur la trace de reference, c'est lui qui produit la branche
        finale sans point de reprise.

        `REPRISE` etait le SEUL genre absent de `TONS_DU_DIRECT`, et le `.get`
        avec defaut le peignait NEUTRE : au niveau COULEUR, une reprise
        acceptee et une reprise refusee etaient typographiquement identiques,
        et le mecanisme qui aurait du le signaler le masquait.
        """
        gabarit = gabarit_pour(CAPACITES_TERMINAL)
        peintre = peintre_pour(CAPACITES_TERMINAL)
        self.assertEqual(gabarit.niveau, COULEUR)
        rendus = {}
        for acceptee in (True, False):
            bloc = D.ligne_evenement(
                evenement(E.REPRISE, ordre=2, reprise="IH06",
                          transaction="IH06", acceptee=acceptee), gabarit)
            rendus[acceptee] = peintre.peindre(bloc, gabarit)[0]
            with self.subTest(acceptee=acceptee):
                self.assertIn("\x1b", rendus[acceptee],
                              "une reprise sans ton se peint neutre, donc "
                              "sans une seule sequence")
        self.assertNotEqual(rendus[True], rendus[False])
        self.assertEqual(
            retirer(rendus[True]).replace("ACCEPTEE", "REFUSEE").rstrip(),
            retirer(rendus[False]).rstrip(),
            "seule la couleur et le verdict doivent differer")

    def test_les_lignes_de_la_maquette_A(self):
        """Les formes exactes que la maquette montre, sur la vraie trace."""
        flux, _, _, _ = explorer_la_megatrace()
        rendu = "\n".join(lignes_du_flux(flux,
                                         gabarit_pour(CAPACITES_TERMINAL)))
        for attendue in (
                "002 >  REPRISE  IH06 demandee -> obtenue IH06   ACCEPTEE",
                "003 +  entree deja envoyee par la reprise",
                "004 #  press    wnd[0]/tbar[1]/btn[17]",
                "010 $  BRANCHE  sauvegarde",
                "_  saut     4 geste(s) emportes   ->  reprise visee IH08",
                "_  saut     8 geste(s) emportes   ->  plus aucun point",
                "073 >  REPRISE  IW2ç demandee -> obtenue IW39   REFUSEE",
                "*  ECRAN    IH06/SAPLIH06/1000 #e1cded0d~  verse  wnd[0]",
        ):
            with self.subTest(attendue=attendue):
                self.assertIn(attendue, rendu)

    def test_le_saut_ne_repete_pas_le_rang_de_sa_branche(self):
        """Deux lignes portant le meme rang se lisent comme deux faits sur le
        meme geste. Le saut est la CONSEQUENCE de la branche qui precede."""
        flux, _, _, _ = explorer_la_megatrace()
        gabarit = gabarit_pour(CAPACITES_TERMINAL)
        saut = next(e for e in flux if e.genre == E.SAUT)
        self.assertTrue(saut.ordre, "l'evenement porte bien un ordre")
        ligne = PeintreNu().peindre(D.ligne_evenement(saut, gabarit),
                                    gabarit)[0]
        self.assertNotIn(f"{saut.ordre:03d}", ligne)

    def test_aucune_ligne_du_direct_ne_deborde_du_gabarit(self):
        """La matrice des largeurs, sur le flux ENTIER de la trace.

        Et la contrepartie, qui est la vraie propriete : ce qui ne tient pas
        est coupe AVEC une marque. Une ligne rognee en silence se lit comme
        une donnee complete.
        """
        flux, _, _, _ = explorer_la_megatrace()
        cadran = cadran_de(flux)
        # 28 et 20 en plus de la matrice du plan : c'est en dessous de 28
        # colonnes que le partage des deux chemins de l'en-tete cesse d'avoir
        # lieu, et la matrice s'arretait a 40, ou il fonctionne encore.
        for largeur, hauteur in ((79, 24), (79, 50), (110, 30), (40, 16),
                                 (28, 12), (20, 10)):
            gabarit = Gabarit(colonnes=largeur, lignes=hauteur, source=MESUREE)
            lignes = (lignes_du_flux(flux, gabarit)
                      + lignes_du_bilan(cadran, gabarit)
                      + [D.ligne_collante(cadran, gabarit)])
            self.assertTrue(lignes)
            for ligne in lignes:
                with self.subTest(largeur=largeur, ligne=ligne):
                    self.assertLessEqual(len(ligne), largeur)

    def test_deux_identifiants_voisins_restent_distincts_une_fois_coupes(self):
        """`ctxtWERKS-LOW` et `ctxtWERKS-HIGH` coupes A DROITE donnent la meme
        chaine, d'aspect complet : l'un est la borne basse d'un intervalle,
        l'autre la haute, et la confusion se recopie dans une pipeline.

        CONTROLE NEGATIF : rendre la cible avec `couper` au lieu de
        `couper_chemin` dans `_corps` fait tomber ce test.
        """
        gabarit = Gabarit(colonnes=44, source=MESUREE)
        lignes = []
        for cible in ("wnd[0]/usr/subSUB:SAPLIH06:1000/ctxtWERKS-LOW",
                      "wnd[0]/usr/subSUB:SAPLIH06:1000/ctxtWERKS-HIGH"):
            bloc = D.ligne_evenement(
                evenement(E.ENVOYE, ordre=5, verbe="text", cible=cible),
                gabarit)
            lignes.append(PeintreNu().peindre(bloc, gabarit)[0])
        self.assertIn(MARQUE, lignes[0])
        self.assertNotEqual(lignes[0], lignes[1])

    def test_l_empreinte_courte_du_flux_se_retrouve_au_catalogue(self):
        """Huit caracteres sur seize : c'est ce qu'on recopie a l'oeil, et le
        fichier porte l'empreinte entiere."""
        flux, exploration, _, _ = explorer_la_megatrace()
        gabarit = gabarit_pour(CAPACITES_TERMINAL)
        verse = next(e for e in flux if e.genre == E.ECRAN_VERSE)
        ligne = PeintreNu().peindre(D.ligne_evenement(verse, gabarit),
                                    gabarit)[0]
        empreinte = str(exploration.versees[0]).partition("#")[2]
        self.assertEqual(len(empreinte), 16,
                         "l'empreinte entiere fait seize caracteres : sans "
                         "cela, « courte » ne veut rien dire")
        # La MARQUE, et c'est tout le point : sans elle, `#e1cded0d` a l'aspect
        # d'une empreinte complete. Celui qui la recopie dans la ceremonie de
        # promotion — qui exige l'empreinte EN TOUTES LETTRES — est refuse
        # sans savoir pourquoi, et deux variantes partageant huit chiffres
        # hexadecimaux sont indiscernables a l'ecran.
        self.assertIn(f"#{empreinte[:8]}{MARQUE}", ligne)
        self.assertNotIn(empreinte, ligne)

    def test_le_mandant_est_annonce_au_depart(self):
        """La seule ligne du direct sur laquelle quelqu'un peut s'apercevoir
        qu'il agit sur le mauvais systeme. Rien ici ne sait lequel est
        lequel — mais un humain reconnait le sien."""
        flux, _, _, _ = explorer_la_megatrace()
        rendu = "\n".join(lignes_du_flux(flux,
                                         gabarit_pour(CAPACITES_TERMINAL)))
        self.assertIn("QAS / 200 / FR", rendu)
        self.assertIn("dry-run fige, plafond de sauvegardes 0", rendu)

    def test_les_deux_genres_que_la_megatrace_ne_produit_pas(self):
        """`PLAFOND` et `ECRAN_CONNU`, produits POUR DE BON, et lus.

        Les rendre a partir d'un `Evenement` a champs tous vides ne prouvait
        que « la ligne n'est pas blanche » : rien n'epinglait ce que ces deux
        lignes DISENT, et une branche de `_corps_ecran` restait sans aucun
        appelant. Un budget qui mord et un second rejeu sur le meme catalogue
        les produisent avec leurs vrais champs.
        """
        gabarit = gabarit_pour(CAPACITES_TERMINAL)

        def _ligne(evenement_):
            return PeintreNu().peindre(
                D.ligne_evenement(evenement_, gabarit), gabarit)[0]

        # Un plafond de GESTES : l'evenement ne porte pas d'`ordre` — il porte
        # `index` et `total` — et son rang doit donc etre BLANC. Ecrire `000`
        # annoncerait la position zero sur l'unique ligne qui cloture une
        # exploration arretee par un budget, quatre lignes sous un en-tete qui
        # vient de dire que ce nombre est une POSITION dans la trace.
        flux, _, _, _ = explorer_la_megatrace(plafond_gestes=8)
        plafonds = [e for e in flux if e.genre == E.PLAFOND]
        self.assertEqual(len(plafonds), 1)
        self.assertEqual(plafonds[0].motif, "gestes")
        self.assertEqual(plafonds[0].ordre, 0)
        ligne = _ligne(plafonds[0])
        self.assertIn("PLAFOND  gestes", ligne)
        self.assertIn("plafond de 8 action(s)", ligne)
        self.assertNotIn("000", ligne)

        # Un plafond d'ECRANS : celui-la porte bien un ordre, et l'affiche.
        flux, _, _, _ = explorer_la_megatrace(plafond_ecrans=2)
        plafonds = [e for e in flux if e.genre == E.PLAFOND]
        self.assertEqual(len(plafonds), 1)
        self.assertEqual(plafonds[0].motif, "ecrans")
        ligne = _ligne(plafonds[0])
        self.assertIn(f"{plafonds[0].ordre:03d} ", ligne)
        self.assertIn("PLAFOND  ecrans", ligne)

        # Un `ECRAN_CONNU` : un second rejeu sur le MEME catalogue, ou tout ce
        # que le premier a verse est deja la.
        with tempfile.TemporaryDirectory() as bac:
            explorer_la_megatrace(catalogue=bac)
            flux, _, _, _ = explorer_la_megatrace(catalogue=bac)
        connus = [e for e in flux if e.genre == E.ECRAN_CONNU]
        self.assertTrue(connus)
        ligne = _ligne(connus[1])
        self.assertIn("ECRAN", ligne)
        self.assertIn("deja connu", ligne)
        self.assertIn(MARQUE, ligne)
        # Un ecran deja connu ne compte pas dans la quarantaine : sa ligne ne
        # porte donc aucune fraction, la ou un ecran verse porte « 2/500 ».
        self.assertNotIn("/500", ligne)

    def test_le_rang_est_BLANC_quand_il_n_y_a_pas_de_position(self):
        """Trois cas, une seule regle : pas de position, pas de rang.

        Le releve de l'ecran de DEPART est pris avant le moindre geste, et
        les gestes sont numerotes a partir de 001 : il n'existe aucun geste
        000. Ecrire `000` annoncerait une position qui n'existe pas, sur une
        ligne qu'un en-tete vient de dire etre une position.
        """
        flux, _, _, _ = explorer_la_megatrace()
        gabarit = gabarit_pour(CAPACITES_TERMINAL)
        depart = next(e for e in flux if e.genre == E.ECRAN_VERSE)
        self.assertEqual(depart.ordre, 0,
                         "le releve de depart porte bien l'ordre zero")
        ligne = PeintreNu().peindre(D.ligne_evenement(depart, gabarit),
                                    gabarit)[0]
        self.assertNotIn("000", ligne)
        self.assertTrue(ligne.startswith("      *  ECRAN"), repr(ligne))

    def test_un_evenement_sans_identite_ne_rend_aucun_champ_vide(self):
        """Le cas d'un parcours qui tombe avant d'avoir lu l'identite.

        La fixture `IDENTITE` renseigne tout, donc dix replis `or` de ce
        module n'etaient exerces par rien : chacun pouvait etre remplace par
        une sentinelle sans qu'un test bronche. Un `?` ou une phrase de
        remplacement doit se LIRE — un vide se lit comme une donnee absente
        de l'ecran, pas comme une donnee que personne n'a pu mesurer.
        """
        gabarit = gabarit_pour(CAPACITES_TERMINAL)
        peintre = PeintreNu()

        def _lignes(blocs):
            return [peintre.peindre(bloc, gabarit)[0] for bloc in blocs]

        tete = _lignes(D.entete(D.Cadran(), gabarit))
        self.assertIn("? / ? / ?", "\n".join(tete))
        self.assertIn("?  ->  ?", "\n".join(tete))

        def _corps(genre, **champs):
            return peintre.peindre(
                D.ligne_evenement(evenement(genre, ordre=3, **champs),
                                  gabarit), gabarit)[0]

        self.assertIn("geste de confort ecarte", _corps(E.CONFORT))
        reprise = _corps(E.REPRISE, acceptee=False)
        self.assertIn("? demandee -> obtenue ?", reprise)
        self.assertIn("REFUSEE", reprise)
        self.assertIn("plus aucun point de reprise", _corps(E.SAUT))
        # Un `PLAFOND` sans raison ni clef : la ligne porte quand meme son
        # etiquette, elle ne se reduit pas a « PLAFOND » suivi de rien.
        self.assertIn("PLAFOND", _corps(E.PLAFOND, motif="gestes"))
        # Et l'ecran dont la clef ne porte pas d'empreinte : le triplet seul,
        # sans un « # » orphelin qui ferait croire a une empreinte vide.
        ecran = _corps(E.ECRAN_CONNU, clef="IH06/SAPLIH06/1000")
        self.assertIn("IH06/SAPLIH06/1000", ecran)
        self.assertNotIn("#", ecran)

        bilan = "\n".join(_lignes(D.bilan(D.Cadran(commence=True), gabarit)))
        self.assertIn("systeme ?", bilan)
        self.assertIn("etat  ?", bilan)

    def test_la_banniere_en_texte_nu_precede_toute_sequence(self):
        """Le pire cas de la sonde n'est pas qu'elle refuse : c'est qu'elle
        ACCEPTE A TORT.

        Si elle se trompe, l'utilisateur lit `<-[1m` a chaque ligne et conclut
        que l'outil est casse. La premiere ligne ecrite lui donne alors le nom
        de l'option qui le sauve — et elle ne peut le faire que si elle ne
        porte elle-meme aucune sequence.

        Au niveau NU elle n'est pas emise du tout : elle n'aurait rien a
        dementir, et ce serait du bruit dans un fichier redirige.
        """
        cadran = D.avancer(D.Cadran(), evenement(
            E.DEPART, source="t.vbs", cible="c", systeme="QAS",
            mandant="200", langue="FR", total=90))
        gabarit = gabarit_pour(CAPACITES_TERMINAL)
        self.assertEqual(gabarit.niveau, COULEUR)
        lignes = [ligne
                  for bloc in D.entete(cadran, gabarit)
                  for ligne in peintre_pour(CAPACITES_TERMINAL).peindre(
                      bloc, gabarit)]
        self.assertIn("--sans-couleur", lignes[0])
        self.assertNotIn("\x1b", lignes[0])
        self.assertIn("\x1b", "\n".join(lignes[1:]),
                      "sans une seule sequence plus bas, cette banniere ne "
                      "previendrait de rien")

        nu = D.entete(cadran, gabarit_pour(CAPACITES_FICHIER))
        self.assertNotIn("--sans-couleur", "\n".join(
            ligne for bloc in nu
            for ligne in PeintreNu().peindre(bloc, gabarit_pour(
                CAPACITES_FICHIER))))

    def test_les_deux_chemins_de_l_entete_se_partagent_la_place(self):
        """Leur FIN discrimine : `D:\\catalogues\\qas` et
        `D:\\catalogues\\prd` coupes a droite donnent la meme chaine.

        Le partage 3/5 - 2/5 n'etait exerce par rien : passer a 5/5 ou a 0/5
        ne faisait rien tomber, parce que la seule assertion portait sur la
        longueur. Ce qui compte est que les DEUX bouts survivent.
        """
        cadran = D.Cadran(
            trace="C:\\equipe\\enregistrements\\2026\\megatrace_2026-09.vbs",
            catalogue="D:\\partage\\catalogues\\ecrans\\qas")
        gabarit = Gabarit(colonnes=79, source=MESUREE)
        ligne = PeintreNu().peindre(D.entete(cadran, gabarit)[0], gabarit)[0]
        self.assertLessEqual(len(ligne), 79)
        self.assertIn("  ->  ", ligne)
        # Les deux sont coupes, et les deux gardent leur FIN : un partage 5/5
        # reduirait le catalogue a une marque, un partage 0/5 la trace.
        self.assertEqual(ligne.count(MARQUE), 2, ligne)
        self.assertIn("-09.vbs", ligne)
        self.assertIn("qas", ligne)

    def test_la_duree_est_un_temps_ecoule_et_se_lit(self):
        self.assertEqual(D.duree(0), "00:00:00")
        self.assertEqual(D.duree(161_000), "00:02:41")
        self.assertEqual(D.duree(3_600_000 * 100), "100:00:00")


class TestLeDirectDansLaConsole(unittest.TestCase):
    """Maquette B : identique, moins la ligne collante, et le prix est ECRIT."""

    def setUp(self):
        self.sap = SapDePapier()
        self.sap.identite = IDENTITE
        self.sap.refusees = {"IW2ç"}
        self.bac = tempfile.TemporaryDirectory()
        self.arbre = racine(
            ecrans.Environnement(connecter=lambda: self.sap))

    def tearDown(self):
        self.bac.cleanup()

    def _session(self) -> Journal:
        journal = Journal(*vers(self.arbre, *PORTE_SAP), str(MEGATRACE),
                          self.bac.name, "500", "500",
                          "megatrace_2026-09.vbs", "", "0", "0")
        parcourir(self.arbre, journal.console())
        return journal

    def test_la_console_montre_la_branche_pendant_le_rejeu(self):
        """CONTROLE NEGATIF : retirer `observateur=` de l'appel a
        `cartographier` dans `ecrans._cartographier` fait tomber ce test.

        Mesure : il fait tomber TROIS cas de ce fichier — celui-ci,
        `test_la_console_ecrit_le_prix_du_direct`, et
        `test_le_direct_precede_le_compte_rendu`. Ecrire « et ne fait tomber
        que lui » etait faux, et une docstring fausse est un defaut a part
        entiere. Ce qui est vrai, et mesure : aucun test de `test_console` ne
        bouge — le compte rendu final continuerait de tous les satisfaire, et
        la console serait restee muette pendant les trois minutes du rejeu.
        """
        journal = self._session()
        self.assertIn("BRANCHE  sauvegarde", journal.texte)
        self.assertIn("REPRISE  IH06 demandee -> obtenue IH06", journal.texte)
        self.assertIn("bilan de la cartographie", journal.texte)

    def test_la_console_annonce_le_mandant_et_le_prix_du_rang(self):
        """Maquette B : « identique, moins la ligne collante ».

        Rien ne le tenait. Les deux tests qui verifient ce contenu passent par
        l'aide `lignes_du_flux`, qui appelle `D.entete` directement et ne
        traverse jamais `EnConsole` : retirer la pose de l'en-tete de
        `EnConsole.__call__` laissait la suite entiere verte, et la console —
        l'entree par laquelle un operateur lance une cartographie sans ligne
        de commande — n'annoncait plus du tout sur quel systeme elle agit.
        """
        journal = self._session()
        self.assertIn("QAS / 200 / FR", journal.texte)
        self.assertIn("dry-run fige, plafond de sauvegardes 0", journal.texte)
        self.assertIn("POSITION", journal.texte)
        self.assertIn("FALCON explorer", journal.texte)

    def test_clore_deux_fois_ne_pose_qu_un_bilan_dans_la_console(self):
        """Le garde-fou du `Diffuseur`, de ce cote-ci aussi.

        `test_clore_deux_fois_ne_pose_qu_un_bilan` ne porte que sur le
        `Diffuseur` : retirer `self._clos = True` d'`EnConsole.clore` posait
        deux bilans sous les yeux de l'operateur sans qu'un test bronche.
        """
        flux, _, _, _ = explorer_la_megatrace()
        journal = Journal()
        direct = D.EnConsole(journal.console(), PeintreNu(),
                             gabarit_pour(CAPACITES_FICHIER))
        for evenement_ in flux:
            direct(evenement_)
        direct.clore()
        direct.clore()
        self.assertEqual(journal.texte.count("bilan de la cartographie"), 1)

    def test_clore_avant_le_premier_fait_n_ecrit_rien_dans_la_console(self):
        """Un bilan a zero se lit comme une exploration qui n'a rien TROUVE,
        alors qu'elle n'a rien TENTE.

        Le cas est atteignable en production : `_cartographier` appelle
        `direct.clore()` sur le chemin d'echec, et un `connecter()` qui leve
        avant le premier ecran n'a produit aucun `DEPART`. Le test equivalent
        du `Diffuseur` ne couvrait pas ce cote-ci.
        """
        journal = Journal()
        D.EnConsole(journal.console(), PeintreNu(),
                    gabarit_pour(CAPACITES_FICHIER)).clore()
        self.assertEqual(journal.lignes, [])

    def test_le_bilan_de_la_console_est_pose_meme_si_l_exploration_leve(self):
        """Le `finally` de `_cartographier`, et pas seulement son `except`.

        `except ErreurFalcon` ne rattrape que les refus de FALCON. Une
        exception qui n'en est pas une sautait par-dessus `direct.clore()` :
        le direct s'interrompait en plein vol, sans une ligne disant ou il en
        etait, alors que `principal._explorer` avait deja mis le meme appel
        dans un `finally` pour la meme raison.
        """
        import falcon.commandes.cartographie as cartographie

        def _cartographie_qui_casse(*_, observateur=None, **__):
            observateur(evenement(E.DEPART, source="t.vbs", cible="c",
                                  systeme="QAS", mandant="200", langue="FR",
                                  total=2))
            observateur(evenement(E.ENVOYE, ordre=1, verbe="press",
                                  cible="wnd[0]/tbar[0]/btn[3]"))
            raise RuntimeError("un defaut, pas un refus")

        vraie = cartographie.cartographier
        cartographie.cartographier = _cartographie_qui_casse
        try:
            journal = Journal(str(MEGATRACE), self.bac.name, "500", "500",
                              "megatrace_2026-09.vbs", "")
            with self.assertRaises(RuntimeError):
                ecrans._cartographier(
                    journal.console(),
                    ecrans.Environnement(connecter=lambda: self.sap))
        finally:
            cartographie.cartographier = vraie
        self.assertIn("press    wnd[0]/tbar[0]/btn[3]", journal.texte)
        self.assertIn("bilan de la cartographie", journal.texte)

    def test_la_console_ecrit_le_prix_du_direct(self):
        """Une interface qui tait sa limite laisse conclure qu'elle est en
        panne : pendant un `press` de dix secondes, l'ecran ne bouge pas."""
        journal = self._session()
        self.assertIn("La console affiche un geste une fois qu'il est FAIT",
                      journal.texte)
        self.assertIn("python -m falcon explorer", journal.texte)

    def test_la_console_garde_son_compte_rendu(self):
        """`console.ecrire(compte_rendu)` reste : le retirer ferait tomber
        `test_le_parcours_complet_verse_des_ecrans` et
        `test_la_porte_des_TRACES_mene_a_la_meme_exploration`."""
        journal = self._session()
        self.assertIn("cartographie de", journal.texte)
        self.assertIn("gestes de la trace", journal.texte)

    def test_le_direct_precede_le_compte_rendu(self):
        """L'ordre est tout l'interet : un direct pose APRES le compte rendu
        ne serait qu'un second compte rendu, plus pauvre.

        Ce test fait partie des trois que le controle negatif n°1 fait tomber
        — il y tombe en ERROR, sur un `ValueError` d'index, la sous-chaine
        cherchee ayant disparu.
        """
        journal = self._session()
        self.assertLess(journal.texte.index("BRANCHE  sauvegarde"),
                        journal.texte.index("cartographie de"))
        self.assertLess(journal.texte.index("bilan de la cartographie"),
                        journal.texte.index("cartographie de"))

    def test_aucune_sequence_n_atteint_la_console(self):
        """`Capacites()` est le VRAI defaut : tout est faux tant que rien n'a
        ete mesure, donc le niveau est NU et rien ne peint.

        CONTROLE NEGATIF : cabler la sonde reelle dans `_cartographier` fait
        tomber ce test des qu'un developpeur lance la suite depuis un vrai
        terminal — et le laisse vert en CI, ou la sortie part dans un tube.
        C'est exactement le chemin non exerce en CI qui tournerait chez
        l'utilisateur.
        """
        journal = self._session()
        self.assertNotIn("\x1b", journal.texte)
        self.assertNotIn("\r", journal.texte)

    def test_le_direct_de_la_console_passe_par_peintre_pour(self):
        """Garde-fou syntaxique, a l'image de celui de `confirmer`.

        Un `PeintreNu()` ecrit a la main dans `_cartographier` donnerait le
        meme ecran AUJOURD'HUI et contournerait la garde n°9 : le jour ou la
        console saura mesurer ses capacites, c'est ce site-la qui deciderait
        de peindre, sans preuve et sans refus possible.
        """
        source = inspect.getsource(ecrans._cartographier)
        arbre = ast.parse(source.lstrip())
        appeles = {getattr(noeud.func, "id", None)
                   for noeud in ast.walk(arbre) if isinstance(noeud, ast.Call)}
        self.assertIn("EnConsole", appeles)
        self.assertIn("peintre_pour", appeles)
        self.assertIn("gabarit_pour", appeles)
        self.assertNotIn("PeintreNu", appeles)
        self.assertNotIn("PeintreColore", appeles)
        # Et les capacites viennent de l'environnement injecte, jamais d'un
        # `Capacites()` construit ici : deux defauts pour une seule question
        # divergeraient au premier changement, en silence et dans le sens le
        # plus difficile a voir — un ecran qui reste nu pendant que le reste
        # de la console peint.
        self.assertNotIn("Capacites", appeles)
        self.assertIn("env.capacites()", source)


class TestLesDeuxRefusDeLaLigneDeCommande(unittest.TestCase):

    def test_les_deux_options_existent_et_sont_fausses_par_defaut(self):
        """Le defaut est le direct : c'est lui le lot. Les deux refus se
        tapent, ils ne se subissent pas.

        Ce test ne dit QUE cela : que les options existent et que leur defaut
        est faux. Ce que le programme en FAIT est mesure plus bas, en
        executant `_explorer` pour de bon — sans quoi inverser un seul mot
        (`if options.muet` au lieu de `if not options.muet`) laissait la suite
        entiere verte et donnait a l'utilisateur l'exact contraire de ce qu'il
        avait tape.
        """
        analyseur = principal.analyseur()
        options = analyseur.parse_args(
            ["explorer", "t.vbs", "--catalogue", "c", "--plafond-gestes", "5",
             "--plafond-ecrans", "5"])
        self.assertFalse(options.muet)
        self.assertFalse(options.sans_couleur)
        options = analyseur.parse_args(
            ["explorer", "t.vbs", "--catalogue", "c", "--plafond-gestes", "5",
             "--plafond-ecrans", "5", "--muet", "--sans-couleur"])
        self.assertTrue(options.muet)
        self.assertTrue(options.sans_couleur)

    def test_l_aide_de_sans_couleur_ne_promet_pas_de_retirer_le_decor(self):
        """Elle disait « sans decor ni couleur ». Mesure avec `forcer_nu` :
        les sequences disparaissent, et TOUT le decor reste — les filets
        d'`=`, les separateurs, les marques `# ~ $ _ > * +` de chaque ligne.

        Celui qui tape l'option parce qu'une police raster lui affiche des
        carres vides n'obtient aucun soulagement, et conclut que l'option est
        cassee. Le decor est en ASCII : il n'y a rien a retirer.
        """
        sous = principal.analyseur()._subparsers._group_actions[0].choices
        texte = sous["explorer"].format_help()
        self.assertIn("--sans-couleur", texte)
        self.assertNotIn("sans decor", texte)

        sortie = FluxDePapier()
        flux, _, _, _ = explorer_la_megatrace()
        diffuseur = D.Diffuseur(sortie, CAPACITES_TERMINAL, forcer_nu=True)
        for evenement_ in flux:
            diffuseur(evenement_)
        diffuseur.clore()
        self.assertNotIn("\x1b", sortie.texte)
        for decor in ("=", "-", "#", "~", "$", "_", ">", "*", "+"):
            with self.subTest(decor=decor):
                self.assertIn(decor, sortie.texte,
                              "le decor reste : l'aide ne doit pas promettre "
                              "de le retirer")


class TestLaCommandeExploreEnVRAI(unittest.TestCase):
    """`_explorer` EXECUTEE, et pas seulement lue sur son arbre syntaxique.

    Tout le cablage de la ligne de commande reposait sur de la lecture d'AST :
    `_explorer` n'etait executee par aucun test du depot. Mesure de ce que
    cela laissait passer, chaque mutation relancee sur la suite entiere sans
    qu'un seul test bronche :

      - `if options.muet` au lieu de `if not options.muet` — le drapeau qui
        ALLUME le direct et le defaut qui l'eteint ;
      - `if diffuseur is None` dans le `finally` — donc `clore()` jamais
        appelee sur un vrai diffuseur, et `None.clore()` sous `--muet`, une
        `AttributeError` levee DEPUIS un `finally`, qui remplace l'exception
        d'origine ;
      - `sonder(systeme_reel(sys.stdout, "stdout"))` — la capacite mesuree
        sur un flux et affirmee sur l'autre, c'est-a-dire de l'ANSI dans le
        journal de qui tape `2> journal.log`.

    Ici la commande tourne. `cartographier` est remplacee par un double qui
    emet quelques faits — c'est la seule chose qu'on ne peut pas executer :
    elle exige une session SAP ouverte.
    """

    def setUp(self):
        import falcon.commandes.cartographie as cartographie
        import falcon.couture.sapgui as sapgui
        import falcon.toile.capacites as capacites
        from falcon.exploration import TERMINEE

        self.cartographie = cartographie
        self.sapgui = sapgui
        self.capacites = capacites
        self.TERMINEE = TERMINEE
        self._vrais = (cartographie.cartographier, sapgui.connecter,
                       capacites.sonder, capacites.reposer_le_bit,
                       sys.stdout, sys.stderr)
        self.recu = {}

        sap = SapDePapier()
        sap.identite = IDENTITE
        sapgui.connecter = lambda **_: sap

    def tearDown(self):
        (self.cartographie.cartographier, self.sapgui.connecter,
         self.capacites.sonder, self.capacites.reposer_le_bit,
         sys.stdout, sys.stderr) = self._vrais

    #: Ce que le double emet : de quoi faire un en-tete, une ligne et un
    #: bilan. Sans `DEPART`, `clore()` ne pose aucun bilan — c'est son
    #: garde-fou — et le test ne prouverait pas que `clore` a ete appelee.
    def _faits(self):
        return [
            evenement(E.DEPART, source="megatrace_2026-09.vbs",
                      cible="D:\\catalogues\\qas", systeme="QAS",
                      mandant="200", langue="FR", total=90,
                      plafond_gestes=500, plafond_ecrans=500),
            evenement(E.BRANCHE, ordre=10, categorie="sauvegarde",
                      motif="la trace sauvegarde ici"),
            evenement(E.FIN, etat="terminee"),
        ]

    def _lancer(self, *drapeaux, capacites=None, bit=True, stderr=None):
        """Execute `_explorer`. Rend (code, stdout, stderr, observateur)."""
        import types

        journal, sortie = FluxDePapier(), stderr or FluxDePapier()

        def _double(*_, observateur=None, **__):
            self.recu["observateur"] = observateur
            for fait in self._faits():
                if observateur is None:
                    continue
                try:
                    observateur(fait)
                except Exception:
                    # Ce que `_Parcours.emettre` fait : il compte la panne et
                    # continue. Le direct ne doit jamais tuer une exploration
                    # qui a une session SAP ouverte.
                    pass
            return (None, types.SimpleNamespace(etat=self.TERMINEE), "COMPTE "
                    "RENDU : gestes de la trace, partition, branches")

        self.cartographie.cartographier = _double
        self.capacites.sonder = lambda _: (capacites or CAPACITES_FICHIER)
        self.capacites.reposer_le_bit = lambda _: bit
        sys.stdout, sys.stderr = journal, sortie
        try:
            options = principal.analyseur().parse_args(
                ["explorer", str(MEGATRACE), "--catalogue", "c",
                 "--plafond-gestes", "500", "--plafond-ecrans", "500",
                 "--oui-je-sais", "megatrace_2026-09.vbs", *drapeaux])
            code = principal._explorer(options)
        finally:
            sys.stdout, sys.stderr = self._vrais[4], self._vrais[5]
        return code, journal.texte, sortie.texte, self.recu["observateur"]

    def test_par_defaut_le_direct_sort_sur_l_erreur_standard(self):
        """Le defaut est le direct, et il sort sur `stderr`.

        `falcon explorer ... > rapport.txt` doit rendre un rapport propre : le
        compte rendu sur la sortie standard, le direct sur l'erreur standard.
        Les deux assertions croisees sont ce qui epingle le flux — mesurer
        `stdout` et peindre `stderr` est le defaut exact que le commentaire de
        six lignes du code decrit, et que rien ne verifiait.
        """
        code, journal, sortie, observateur = self._lancer()
        self.assertIsInstance(observateur, D.Diffuseur)
        self.assertIn("FALCON explorer", sortie)
        self.assertIn("BRANCHE  sauvegarde", sortie)
        self.assertIn("bilan de la cartographie", sortie,
                      "le bilan n'est pose que par `clore()` : son absence "
                      "veut dire que le `finally` ne l'a pas appelee")
        self.assertNotIn("FALCON explorer", journal)
        self.assertIn("COMPTE RENDU", journal)
        self.assertEqual(code, 0)

    def test_muet_n_affiche_rien_du_tout(self):
        """L'option entiere etait une declaration : inverser la garde laissait
        les 1307 tests verts, et donnait a l'utilisateur le contraire de ce
        qu'il avait tape — il lance `--muet` pendant qu'une session SAP
        tourne, et le direct s'allume.
        """
        code, journal, sortie, observateur = self._lancer("--muet")
        self.assertIsNone(observateur,
                          "`--muet` ne passe AUCUN observateur : ce n'est pas "
                          "un direct qu'on tait, c'est un direct qu'on ne "
                          "construit pas")
        self.assertNotIn("FALCON explorer", sortie)
        self.assertNotIn("BRANCHE", sortie)
        self.assertNotIn("bilan de la cartographie", sortie)
        # Et le compte rendu sort quand meme : c'est lui qui fait foi.
        self.assertIn("COMPTE RENDU", journal)
        self.assertEqual(code, 0)

    def test_la_couleur_ne_sort_que_si_les_deux_conditions_tiennent(self):
        """Trois cas, et le troisieme est celui que personne ne voit en CI.

        Sur un terminal qui a TOUT prouve, le direct peint. `--sans-couleur`
        le refuse. Et si le bit VT n'a pas pu etre REPOSE — la sonde restaure
        toujours le mode qu'elle a trouve, et sur un conhost Windows 10 VT est
        eteint par defaut — alors les capacites sont vraies et l'etat du
        handle ne l'est plus : peindre la-dessus deverserait `<-[1m` a chaque
        ligne. Le direct retombe en texte nu, qui est le cas de BASE.
        """
        _, _, avec, _ = self._lancer(capacites=CAPACITES_TERMINAL)
        self.assertIn("\x1b", avec)

        _, _, sans, _ = self._lancer("--sans-couleur",
                                     capacites=CAPACITES_TERMINAL)
        self.assertNotIn("\x1b", sans)
        self.assertIn("FALCON explorer", sans)

        _, _, nu, _ = self._lancer(capacites=CAPACITES_TERMINAL, bit=False)
        self.assertNotIn("\x1b", nu)
        self.assertIn("FALCON explorer", nu)

    def test_un_flux_qui_se_ferme_n_emporte_pas_le_compte_rendu(self):
        """Le defaut le plus grave du lot, et il ne leve aucune exception
        visible.

        `Diffuseur.clore()` est le SEUL appel a l'observateur que
        `_Parcours.emettre` n'enveloppe pas : il vient du `finally`. Sur un
        flux qui s'est ferme en cours de route — `| more` puis `q`, la croix
        de la fenetre, une liaison RDP qui lache — elle leve. Ce `finally`
        s'execute AVANT `print(compte_rendu)` : la levee sautait par-dessus,
        et `main` attrapait la `BrokenPipeError` pour rendre **0**.

        Resultat : FALCON avait agi dans SAP, verse des ecrans en
        quarantaine, et sortait en code 0 sans imprimer une ligne de compte
        rendu — le seul endroit ou vivent la partition, les branches, les
        visites non atteintes et le paragraphe « ce que ce rapport ne dit
        pas ». Un script qui lit le code de retour conclut que tout s'est
        bien passe.
        """
        class FluxQuiSeFerme(FluxDePapier):
            def __init__(self, apres):
                super().__init__()
                self.restantes = apres

            def write(self, texte):
                if self.restantes <= 0:
                    raise BrokenPipeError(32, "Broken pipe")
                self.restantes -= 1
                return super().write(texte)

        # Douze ecritures : le preambule de la commande en consomme huit,
        # le direct se ferme donc en plein en-tete. `clore()` leve ensuite —
        # c'est ce que verifie l'absence de bilan dans ce qui a pu s'ecrire.
        ferme = FluxQuiSeFerme(12)
        code, journal, sortie, _ = self._lancer(stderr=ferme)
        self.assertIn("FALCON explorer", sortie)
        self.assertNotIn("bilan de la cartographie", sortie,
                         "le flux s'est ferme AVANT le bilan : sans cela, "
                         "`clore()` n'a pas leve et ce test ne prouve rien")
        self.assertIn("COMPTE RENDU", journal,
                      "le compte rendu est le seul juge : le perdre pour un "
                      "bandeau qu'on n'arrive plus a effacer serait le pire "
                      "echange possible")
        self.assertEqual(code, 0)

    def test_la_commande_branche_le_direct_sur_l_erreur_standard(self):
        """Ce que l'execution ne peut pas dire : sur QUEL flux la sonde a
        mesure.

        En CI, `sys.stderr` est remplace par un flux de papier sans `fileno`,
        donc `systeme_reel` rend le meme « je ne sais rien » pour `stdout` et
        pour `stderr` : l'inversion ne se verrait pas. Or c'est precisement le
        defaut que le commentaire du code decrit — sur Windows, VT est un mode
        par HANDLE, et une capacite mesuree sur un flux puis affirmee sur
        l'autre deverse de l'ANSI dans le journal de qui tape `2> journal.log`.
        L'assertion porte donc sur le TEXTE de l'appel, en entier, et pas sur
        la seule presence du mot `systeme_reel` — qui restait vraie quel que
        soit le flux sonde.
        """
        source = inspect.getsource(principal._explorer)
        arbre = ast.parse(source.lstrip())
        appels = [noeud for noeud in ast.walk(arbre)
                  if isinstance(noeud, ast.Call)]

        cartographies = [a for a in appels
                         if getattr(a.func, "id", None) == "cartographier"]
        self.assertEqual(len(cartographies), 1)
        self.assertIn("observateur",
                      [mot.arg for mot in cartographies[0].keywords])

        systemes = [ast.unparse(a) for a in appels
                    if getattr(a.func, "id", None) == "systeme_reel"]
        self.assertEqual(systemes, ["systeme_reel(sys.stderr, 'stderr')"])

        diffuseurs = [a for a in appels
                      if getattr(a.func, "id", None) == "Diffuseur"]
        self.assertEqual(len(diffuseurs), 1)
        self.assertEqual(
            [ast.unparse(a) for a in diffuseurs[0].args][0], "sys.stderr")
        self.assertIn("forcer_nu=options.sans_couleur",
                      ast.unparse(diffuseurs[0]))
        self.assertIn("reposer_le_bit", ast.unparse(diffuseurs[0]))

    def test_le_bandeau_est_clos_meme_si_l_exploration_leve(self):
        """Une exploration qui leve a DEJA agi dans SAP : le bandeau est une
        ligne sans saut de ligne, et la laisser collerait la trace de pile a
        sa suite.

        Le `finally` est ce qui l'empeche. L'assertion porte sur le TEXTE de
        l'appel et sur sa garde, et pas sur la presence du mot « clore » :
        remplacer `if diffuseur is not None` par `if diffuseur is None`
        satisfaisait l'ancienne version mot pour mot, tout en n'appelant
        jamais `clore()` sur un vrai diffuseur et en levant une
        `AttributeError` depuis un `finally` sous `--muet`.

        Que le bilan soit REELLEMENT pose est mesure plus haut, en executant
        la commande : ici on epingle la forme, la ou l'execution ne peut pas
        distinguer une exploration qui leve.
        """
        source = inspect.getsource(principal._explorer)
        arbre = ast.parse(source.lstrip())
        essais = [n for n in ast.walk(arbre) if isinstance(n, ast.Try)
                  and any("cartographier" in ast.unparse(c)
                          for c in n.body)]
        self.assertEqual(len(essais), 1)
        corps = ast.unparse(ast.Module(body=essais[0].finalbody,
                                       type_ignores=[]))
        self.assertIn("diffuseur.clore()", corps)
        self.assertIn("diffuseur is not None", corps)
        # Et la levee de `clore` sur un flux ferme ne doit pas emporter le
        # compte rendu : c'est l'autre moitie, mesuree par
        # `test_un_flux_qui_se_ferme_n_emporte_pas_le_compte_rendu`.
        self.assertIn("except OSError", corps)

        gardes = [n for n in ast.walk(arbre) if isinstance(n, ast.If)
                  and "options.muet" in ast.unparse(n.test)]
        self.assertEqual(len(gardes), 1)
        self.assertEqual(ast.unparse(gardes[0].test), "not options.muet")


class TestLeNiveauNuEstLeDefaut(unittest.TestCase):

    def test_un_gabarit_non_prouve_reste_au_niveau_NU(self):
        """Le direct ne decide pas : il demande, et la garde n°9 refuse."""
        self.assertEqual(gabarit_pour(CAPACITES_FICHIER).niveau, NU)
        self.assertEqual(peintre_pour(CAPACITES_FICHIER).niveau, NU)
        self.assertEqual(gabarit_pour(CAPACITES_TERMINAL,
                                      forcer_nu=True).niveau, NU)


if __name__ == "__main__":
    unittest.main()
