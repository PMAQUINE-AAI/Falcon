"""Ce qu'un parcours raconte — et surtout : qu'il ne raconte RIEN de faux.

Ce lot n'ajoute aucune fonctionnalite visible. Il ajoute treize points
d'emission dans `_parcourir`, c'est-a-dire dans la fonction la plus
verrouillee du depot : une partition verifiee au geste pres, sept sorties de
boucle, et un `try` dont les `except` fabriquent des `Branche`. **Ce qui
compte ici n'est donc pas l'affichage, c'est de ne rien casser**, et ces tests
sont la partie importante du lot.

Trois classes de defaut les motivent, et chacune a son test :

1. **Un afficheur qui leve dans le `try` de `_parcourir`.** L'exception y
   serait attrapee par `except Refus` ou `except Echec`, convertie en
   `Branche` dont le motif ACCUSE SAP, et `_dump_si_inconnu` ecrirait sur le
   disque le dump d'un incident qui n'a jamais eu lieu. Aucune exception, un
   compte rendu plausible et FAUX.

   La precision qui manque au plan, et elle a ete MESUREE : les `except` de
   `_parcourir` sont TYPES. Une `ZeroDivisionError` levee dans le `try` n'y
   devient pas une `Branche`, elle traverse `explorer` — ce qui est deja
   grave, mais bruyant. Ce qui devient une branche muette est une exception de
   la famille `Refus` / `Echec`, et un afficheur en leve tres bien : il appelle
   du code FALCON. Mesure faite en cassant les deux protections a la fois :
   quatre `Branche(incident)` dont le motif est le message de l'AFFICHEUR, sur
   une exploration ou SAP n'a rien refuse du tout.
2. **Une emission MAL PLACEE qui ne change aucun resultat.** Le `SAUT` pose
   avant la reecriture de `p.branches[-1]` afficherait « reprise visee
   (aucune) » sur une branche qui reprend tres bien. Ni l'enveloppe
   d'`emettre` ni la garde AST ne le voient : le seul filet est le test qui
   compare le flux ENTIER de la megatrace a une sequence attendue, evenement
   par evenement. Il est long, il se perime au premier changement de la trace
   de reference, et c'est le prix.
3. **Un point OUBLIE.** `_sans_point_de_reprise` a l'air d'un constructeur de
   message et mute l'etat : mesure faite, il porte 8 des 46 gestes sautes de
   la megatrace. Sans lui, tout compteur reconstruit depuis le flux tombe a 38
   et affirme « 8 gestes non explores » sur un parcours qui n'en a aucun.

Chaque test nomme, dans sa docstring, la ligne de production a casser pour le
faire tomber. Un test dont on ne sait pas ce qui le ferait tomber ne prouve
rien.
"""

from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

from falcon.exploration import evenements as E
from falcon.exploration import parcours as P
from falcon.exploration.evenements import Evenement, GenreInconnu
from falcon.trace import lire

from tests.test_exploration_parcours import (
    Bac, REGISTRE, SapDePapier, trace_de,
)
from tests.test_trace import MEGATRACE


class SapQuiCompteSesLectures(SapDePapier):
    """Un `SapDePapier` qui compte AUSSI ce qu'on lui demande de lire.

    Indispensable pour la seule question qui vaille sur le cout d'un
    observateur : `p.actions` n'incremente pas sur `screen`, `fields` ni
    `windows`, donc un compteur d'ACTIONS ne verrait pas un afficheur bavard
    qui redemanderait l'etat du monde a chaque ligne. Or c'est exactement le
    trafic COM qu'il ne faut pas doubler : `fields()` descend tout l'arbre des
    controles, et sur un ALV reel cela tient des secondes.
    """

    def __init__(self, *arguments, **nommes):
        super().__init__(*arguments, **nommes)
        self.lectures = 0

    def screen(self):
        self.lectures += 1
        return super().screen()

    def fields(self, fenetre: str = "wnd[0]"):
        self.lectures += 1
        return super().fields(fenetre)

    def windows(self):
        self.lectures += 1
        return super().windows()

    def status(self):
        self.lectures += 1
        return super().status()


#: Ce qu'on retient d'un evenement pour le comparer. Un projecteur par genre,
#: et non un `repr` : l'horodatage monotone varie d'une execution a l'autre, et
#: comparer l'evenement entier rendrait la sequence attendue increvable a
#: maintenir pour la seule raison qu'une machine est plus lente qu'une autre.
_DETAIL = {
    E.DEPART: lambda e: f"{e.systeme}/{e.mandant}/{e.langue} {e.total} gestes",
    E.GESTE: lambda e: e.verbe,
    E.ENVOYE: lambda e: e.appel,
    E.CONFORT: lambda e: e.verbe,
    E.VALIDATION: lambda e: e.verbe,
    E.ECRAN_VERSE: lambda e: f"{e.fenetre} {e.champs} {e.clef}",
    E.ECRAN_CONNU: lambda e: f"{e.fenetre} {e.champs} {e.clef}",
    E.PLAFOND: lambda e: e.motif,
    E.SAUVEGARDE_REFUSEE: lambda e: e.cible,
    E.BRANCHE: lambda e: f"{e.categorie} -> {e.reprise or '(aucune)'}",
    E.SAUT: lambda e: f"{e.sautes} -> {e.reprise or '(aucune)'}",
    E.REPRISE: lambda e: (f"{e.reprise} -> {e.transaction} "
                          f"{'acceptee' if e.acceptee else 'REFUSEE'}"),
    E.FIN: lambda e: e.etat,
}


def _branche(branche) -> tuple:
    """Une `Branche` en tuple, champ par champ.

    Comparer les `Branche` directement marcherait — elles sont gelees — mais
    un echec afficherait deux `repr` de deux cents caracteres cote a cote.
    Le tuple nomme l'endroit ou les deux parcours ont diverge.
    """
    return (branche.ordre, branche.ligne, branche.verbe, branche.categorie,
            branche.motif, branche.entree, branche.dump, branche.reprise)


def resume(evenement: Evenement) -> str:
    return (f"{evenement.genre} {evenement.ordre:03d} "
            f"{_DETAIL[evenement.genre](evenement)}")


#: Le flux COMPLET de la megatrace rejouee contre un SAP qui refuse « IW2ç »,
#: evenement par evenement, dans l'ordre. Ce n'est pas une redondance des
#: mesures de `test_exploration_parcours` : celles-ci portent sur le RESULTAT,
#: et une emission posee au mauvais endroit ne change aucun resultat.
#:
#: Trois choses s'y lisent et chacune est une garde :
#:
#:   - `ecran_verse` PRECEDE la `reprise` du meme geste : `_reprendre` releve
#:     avant de lire `screen()`, donc l'ecran obtenu est verse avant d'etre
#:     nomme. L'inverse ferait croire qu'une reprise verse.
#:   - chaque `branche` PRECEDE son `saut` et porte deja la reprise visee :
#:     c'est ce que garantit la pose des deux emissions APRES la reecriture de
#:     `p.branches[-1]`.
#:   - le dernier couple `branche` / `saut` porte `(aucune)` et 8 gestes :
#:     c'est `_sans_point_de_reprise`, le second chemin de saut.
SEQUENCE_DE_LA_MEGATRACE = (
    'depart 000 // 90 gestes',
    'ecran_verse 000 wnd[0] 1 SESSION_MANAGER/SAPLSMTR_NAVIGATION/0100#1a6cd6a24334c8bd',
    'geste 001 maximize',
    'confort 001 maximize',
    'geste 002 text',
    'ecran_verse 000 wnd[0] 2 IH06/SAPLIH06/1000#e1cded0d231284d6',
    'reprise 002 IH06 -> IH06 acceptee',
    'geste 003 sendVKey',
    'validation 003 sendVKey',
    'geste 004 press',
    'envoye 004 press',
    'geste 005 text',
    'envoye 005 write',
    'geste 006 caretPosition',
    'confort 006 caretPosition',
    'geste 007 press',
    'envoye 007 press',
    'geste 008 selectedRows',
    'envoye 008 grid_select_rows',
    'geste 009 doubleClickCurrentCell',
    'envoye 009 grid_double_click',
    'geste 010 press',
    'sauvegarde_refusee 010 wnd[0]/tbar[0]/btn[11]',
    'branche 010 sauvegarde -> IH08',
    'saut 010 4 -> IH08',
    'geste 015 text',
    'ecran_verse 000 wnd[0] 2 IH08/SAPLIH08/1000#60133328a51f25e7',
    'reprise 015 IH08 -> IH08 acceptee',
    'geste 016 sendVKey',
    'validation 016 sendVKey',
    'geste 017 press',
    'envoye 017 press',
    'geste 018 text',
    'envoye 018 write',
    'geste 019 caretPosition',
    'confort 019 caretPosition',
    'geste 020 sendVKey',
    'envoye 020 vkey',
    'geste 021 text',
    'envoye 021 write',
    'geste 022 setFocus',
    'confort 022 setFocus',
    'geste 023 caretPosition',
    'confort 023 caretPosition',
    'geste 024 press',
    'envoye 024 press',
    'geste 025 selectedRows',
    'envoye 025 grid_select_rows',
    'geste 026 doubleClickCurrentCell',
    'envoye 026 grid_double_click',
    'geste 027 press',
    'sauvegarde_refusee 027 wnd[0]/tbar[0]/btn[11]',
    'branche 027 sauvegarde -> IW39',
    'saut 027 27 -> IW39',
    'geste 055 text',
    'ecran_verse 000 wnd[0] 2 IW39/SAPLIW39/1000#f26e6c215f4ce6a9',
    'reprise 055 IW39 -> IW39 acceptee',
    'geste 056 setFocus',
    'confort 056 setFocus',
    'geste 057 sendVKey',
    'envoye 057 vkey',
    'geste 058 selected',
    'envoye 058 set_checked',
    'geste 059 selected',
    'envoye 059 set_checked',
    'geste 060 setFocus',
    'confort 060 setFocus',
    'geste 061 press',
    'envoye 061 press',
    'geste 062 text',
    'envoye 062 write',
    'geste 063 text',
    'envoye 063 write',
    'geste 064 caretPosition',
    'confort 064 caretPosition',
    'geste 065 sendVKey',
    'envoye 065 vkey',
    'geste 066 press',
    'branche 066 action_aveugle -> IW2ç',
    'saut 066 6 -> IW2ç',
    'geste 073 text',
    'reprise 073 IW2ç -> IW39 REFUSEE',
    'branche 073 reprise_refusee -> IW29',
    'saut 073 1 -> IW29',
    'geste 075 text',
    'ecran_verse 000 wnd[0] 2 IW29/SAPLIW29/1000#7ccb87a3462f4b6b',
    'reprise 075 IW29 -> IW29 acceptee',
    'geste 076 sendVKey',
    'validation 076 sendVKey',
    'geste 077 press',
    'envoye 077 press',
    'geste 078 text',
    'envoye 078 write',
    'geste 079 text',
    'envoye 079 write',
    'geste 080 caretPosition',
    'confort 080 caretPosition',
    'geste 081 sendVKey',
    'envoye 081 vkey',
    'geste 082 press',
    'branche 082 action_aveugle -> (aucune)',
    'saut 082 8 -> (aucune)',
    'fin 000 interrompue',
)


def explorer_la_megatrace(bac: Path, *, observateur=None, sap=None):
    """La megatrace contre un SAP qui refuse la faute de frappe de l'operateur.

    Le meme scenario que `test_le_parcours_mesure_de_la_trace_de_reference` :
    c'est lui qui produit les cinq branches, dont la reprise refusee et la
    branche finale sans point de reprise. Sans le refus d'« IW2ç », le second
    chemin de saut existe toujours mais la reprise refusee disparait, et avec
    elle un evenement sur deux de ce qui compte ici.
    """
    if sap is None:
        sap = SapDePapier()
    sap.refusees = {"IW2ç"}
    return P.explorer(lire(MEGATRACE), sap, catalogue=bac,
                      plafond_gestes=500, plafond_ecrans=500,
                      registre=REGISTRE, observateur=observateur)


# =========================================================================


class TestLeFluxNeChangeRienAuParcours(unittest.TestCase):
    """Le seul sujet de ce lot : la production ne bouge pas d'un geste."""

    def test_un_observateur_qui_LEVE_ne_fabrique_aucune_branche(self):
        """Le defaut le plus grave que ce lot peut introduire.

        CONTROLE NEGATIF : retirer le `except Exception` d'`emettre`, OU sortir
        la construction de l'`Evenement` du `try`, OU deplacer une seule
        emission dans le corps du `try` de `_parcourir` — chacun des trois fait
        tomber ce test, avec une `ZeroDivisionError` convertie en
        `Branche(INCIDENT)` et un dump ecrit pour un incident invente.

        C'est pour cela que `dumps` est verifie : un flux de branches juste et
        un dossier `dumps/` qui se remplit est exactement la panne qu'on ne
        remarque pas avant d'ouvrir le dossier.
        """
        with Bac() as bac:
            resultat = explorer_la_megatrace(bac, observateur=lambda _: 1 / 0)
        self.assertEqual(resultat.partition,
                         {"rejoues": 23, "confort": 9, "interrompus": 4,
                          "reprises": 5, "validations consommees": 3,
                          "sautes": 46, "non explores": 0})
        self.assertEqual([b.categorie for b in resultat.branches],
                         ["sauvegarde", "sauvegarde", "action_aveugle",
                          "reprise_refusee", "action_aveugle"])
        self.assertEqual(resultat.dumps, ())
        self.assertGreater(resultat.pannes_d_affichage, 0)

    def test_les_trois_parcours_rendent_la_meme_chose(self):
        """Sans observateur, avec un observateur muet, avec un qui leve.

        **On ne compare PAS les `Exploration` entieres par `assertEqual`**, et
        ce n'est pas une facilite : `catalogue` porte trois chemins temporaires
        differents, et un bac reutilise rendrait les versements du second
        parcours `deja_connues` au lieu de `versees`. Le test serait
        inexecutable et l'on conclurait que le lot casse le parcours. On
        compare donc la PARTITION, les BRANCHES, les DUMPS et les CLEFS
        VERSEES, une par une.
        """
        recueilli = []
        observateurs = {"aucun": None,
                        "muet": recueilli.append,
                        "qui leve": lambda _: 1 / 0}
        with Bac() as bac:
            temoin = explorer_la_megatrace(bac, observateur=None)

        for nom, observateur in observateurs.items():
            with self.subTest(observateur=nom):
                with Bac() as bac:
                    obtenu = explorer_la_megatrace(bac,
                                                   observateur=observateur)
                self.assertEqual(obtenu.partition, temoin.partition)
                self.assertEqual([_branche(b) for b in obtenu.branches],
                                 [_branche(b) for b in temoin.branches])
                self.assertEqual(obtenu.dumps, temoin.dumps)
                self.assertEqual(list(obtenu.versees), list(temoin.versees))
                self.assertEqual(obtenu.etat, temoin.etat)
                self.assertEqual(obtenu.raison, temoin.raison)
                self.assertEqual(obtenu.ordres_sautes, temoin.ordres_sautes)
                self.assertEqual(obtenu.ordres_atteints,
                                 temoin.ordres_atteints)
                self.assertEqual(obtenu.actions_envoyees,
                                 temoin.actions_envoyees)
                self.assertEqual(obtenu.releves, temoin.releves)
        self.assertTrue(recueilli, "l'observateur muet n'a rien recu")

    def test_un_evenement_qu_on_ne_peut_pas_construire_est_avale_et_compte(self):
        """La SECONDE moitie de l'enveloppe : la CONSTRUCTION est dans le `try`.

        CONTROLE NEGATIF : sortir la construction de l'`Evenement` du `try`
        d'`emettre` fait tomber ce test. L'exception traverse alors `explorer`,
        et une cartographie qui a deja agi dans SAP s'arrete sur une mise en
        forme d'affichage — sans compte rendu, donc sans partition, donc sans
        rien de ce qu'elle vient de faire. Et si une emission se trouvait en
        plus dans le `try` de `_parcourir`, l'exception deviendrait une
        `Branche` dont le motif ACCUSE SAP.

        Le cas n'est pas theorique : `champs` porte des valeurs lues sur la
        trace et sur l'ecran, et c'est `Evenement.__post_init__` qui les juge.
        La construction peut donc lever AVANT que l'observateur n'ait rien vu,
        et c'est pour cela qu'elle est dedans et non au site d'appel.
        """
        vraie = P.Evenement

        def refuser(**champs):
            if champs.get("genre") == E.ENVOYE:
                raise ValueError("mise en forme impossible")
            return vraie(**champs)

        P.Evenement = refuser
        try:
            with Bac() as bac:
                resultat = explorer_la_megatrace(bac,
                                                 observateur=lambda _: None)
        finally:
            P.Evenement = vraie

        self.assertEqual(resultat.partition,
                         {"rejoues": 23, "confort": 9, "interrompus": 4,
                          "reprises": 5, "validations consommees": 3,
                          "sautes": 46, "non explores": 0})
        self.assertEqual(resultat.dumps, ())
        # Un par `ENVOYE`, c'est-a-dire un par geste parvenu au driver.
        self.assertEqual(resultat.pannes_d_affichage, 23)

    def test_l_observateur_n_ajoute_aucune_action_au_driver(self):
        """33 actions, observe ou non — et aussi : pas une lecture de plus.

        Le double COMPTE AUSSI SES LECTURES, parce que `p.actions` n'incremente
        pas sur `screen` / `fields` / `windows` : un observateur qui
        redemanderait l'etat du monde a chaque ligne ne serait vu par aucun
        compteur d'actions, et doublerait pourtant le trafic COM sur le chemin
        le plus chaud. C'est ce qui rend vraie la phrase d'`explorer` :
        « `plafond_gestes` compte les ACTIONS envoyees au driver ».

        **Le compte de lectures est FIGE, et il le faut.** Comparer les deux
        parcours ne suffit pas, et c'est une mesure qui l'a montre : les
        arguments d'une emission sont evalues AU SITE D'APPEL, donc AVANT que
        `emettre` ne regarde s'il y a un observateur. Un `p.garde.windows()`
        glisse dans un appel a `emettre` coute donc autant sans observateur
        qu'avec, et les deux parcours restent egaux — pendant que le trafic
        COM aurait double pour tout le monde, observateur ou pas.

        CONTROLE NEGATIF : ajouter `fenetres=tuple(f.id for f in
        p.garde.windows())` a l'emission d'`ENVOYE` fait tomber le chiffre
        fige, et rien d'autre dans la suite.
        """
        mesures = []
        for observe in (False, True):
            sap = SapQuiCompteSesLectures()
            with Bac() as bac:
                resultat = explorer_la_megatrace(
                    bac, sap=sap,
                    observateur=(lambda _: None) if observe else None)
            mesures.append((resultat.actions_envoyees, len(sap.gestes),
                            sap.lectures, resultat.releves))
        self.assertEqual(mesures[0], mesures[1])
        self.assertEqual(mesures[0][0], 33)
        self.assertEqual(mesures[0][3], 29)
        # 162 lectures : `screen`, `fields`, `windows` et `status`, celles des
        # gardes comprises. Un chiffre en docstring se demode en silence ; un
        # chiffre en test tombe.
        self.assertEqual(mesures[0][2], 162)

    def test_un_ctrl_c_pendant_une_emission_arrete_le_parcours(self):
        """`KeyboardInterrupt` n'est pas avale, et ce n'est pas un detail.

        Un KeyboardInterrupt attrape est CONSOMME : le gestionnaire de signal a
        deja tourne, il n'en reste rien, et « on le reverra au tour suivant »
        est faux. Avale, un Ctrl-C tape pendant une emission disparaitrait
        pendant que FALCON continue de presser des boutons dans un ERP.

        CONTROLE NEGATIF, et il n'est PAS celui qu'on croit : retirer la clause
        `except (KeyboardInterrupt, SystemExit): raise` ne fait rien tomber,
        parce que `except Exception` epargne deja les `BaseException`. Mesure
        faite. Ce qui fait tomber ce test est d'ELARGIR l'attrape-tout a
        `except BaseException` — la retouche d'apparence anodine qu'un jour
        quelqu'un fera « pour etre sur de tout attraper ». Le couple de clauses
        est donc une intention ECRITE plutot qu'un mecanisme a lui seul, et
        c'est ce test-ci qui tient le mecanisme.
        """
        trace = trace_de(
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "A"\r\n'
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "B"\r\n')

        def observateur(_):
            raise KeyboardInterrupt

        sap = SapDePapier()
        with Bac() as bac:
            with self.assertRaises(KeyboardInterrupt):
                P.explorer(trace, sap, catalogue=bac, plafond_gestes=50,
                           plafond_ecrans=50, registre=REGISTRE,
                           observateur=observateur)
        self.assertEqual(sap.gestes, [],
                         "le parcours a continue d'agir apres le Ctrl-C")


class TestLaSequenceComplete(unittest.TestCase):
    """Le seul filet contre une emission MAL PLACEE."""

    def test_le_flux_de_la_megatrace_est_exactement_cette_sequence(self):
        """Evenement par evenement, dans l'ordre, sur la trace de reference.

        CONTROLE NEGATIF : deplacer l'emission de `SAUT` AVANT la reecriture de
        `p.branches[-1]` dans `_sauter_vers_reprise` fait tomber ce test — et
        ne fait tomber que lui. Le parcours rend exactement la meme
        `Exploration` ; seul l'ecran affiche « reprise visee (aucune) » sur une
        branche qui reprend tres bien. Aucune exception, un ecran plausible et
        faux.

        Il se perime au premier changement de la trace de reference. C'est le
        prix, et il est assume : sans lui, aucune des autres protections de ce
        lot ne dit quoi que ce soit de l'ORDRE des faits.
        """
        flux = []
        with Bac() as bac:
            explorer_la_megatrace(bac, observateur=flux.append)
        obtenue = tuple(resume(evenement) for evenement in flux)
        self.assertEqual(obtenue, SEQUENCE_DE_LA_MEGATRACE)

    def test_chaque_branche_precede_son_saut_et_nomme_deja_sa_reprise(self):
        """La meme propriete, dite en intention plutot qu'en fixture.

        Elle survit a un changement de la trace de reference, la sequence
        gelee non : les deux se completent. CONTROLE NEGATIF : le meme que
        ci-dessus.
        """
        flux = []
        with Bac() as bac:
            resultat = explorer_la_megatrace(bac, observateur=flux.append)

        couples = []
        for gauche, droite in zip(flux, flux[1:]):
            if gauche.genre == E.BRANCHE:
                couples.append((gauche, droite))
        self.assertEqual(len(couples), len(resultat.branches))
        for branche, suivant in couples:
            self.assertEqual(suivant.genre, E.SAUT)
            self.assertEqual(branche.reprise, suivant.reprise)
        # Et la mesure qui compte : quatre des cinq branches reprennent, et
        # elles le DISENT des leur evenement.
        self.assertEqual([b.reprise for b, _ in couples],
                         [b.reprise for b in resultat.branches])
        self.assertEqual([b.reprise for b in resultat.branches],
                         ["IH08", "IW39", "IW2ç", "IW29", ""])

    def test_le_flux_compte_les_46_gestes_sautes(self):
        """CONTROLE NEGATIF : retirer l'emission de `_sans_point_de_reprise`
        fait tomber ce test a 38. Il y a DEUX chemins de saut, et le second est
        une fonction qui a l'air d'un constructeur de message et qui mute
        l'etat.

        La repartition est verifiee elle aussi : 38 par `_sauter_vers_reprise`,
        8 par `_sans_point_de_reprise`. Un total juste obtenu par un seul
        chemin serait une coincidence, pas une preuve.
        """
        flux = []
        with Bac() as bac:
            resultat = explorer_la_megatrace(bac, observateur=flux.append)

        sauts = [e for e in flux if e.genre == E.SAUT]
        self.assertEqual(sum(e.sautes for e in sauts), 46)
        self.assertEqual(sum(e.sautes for e in sauts), resultat.gestes_sautes)
        # Le second chemin ne nomme aucune reprise : la trace n'en redonne
        # plus. C'est a cela qu'on le reconnait dans le flux.
        vers_une_reprise = [e.sautes for e in sauts if e.reprise]
        sans_reprise = [e.sautes for e in sauts if not e.reprise]
        self.assertEqual(sum(vers_une_reprise), 38)
        self.assertEqual(sans_reprise, [8])

    def test_le_flux_dit_la_fin_une_fois_et_une_seule(self):
        """Sept sorties de boucle, une seule fin.

        CONTROLE NEGATIF : poser l'emission de `FIN` sur le
        `return TERMINEE, "", total` de `_parcourir` au lieu du retour
        d'`explorer` fait tomber ce test — la megatrace ne termine jamais, elle
        s'interrompt, et le direct resterait muet sur sa propre fin.
        """
        flux = []
        with Bac() as bac:
            resultat = explorer_la_megatrace(bac, observateur=flux.append)
        fins = [e for e in flux if e.genre == E.FIN]
        self.assertEqual(len(fins), 1)
        self.assertIs(fins[0], flux[-1])
        self.assertEqual(fins[0].etat, resultat.etat)
        self.assertEqual(fins[0].raison, resultat.raison)

    def test_le_depart_dit_sur_quoi_l_on_agit(self):
        """Le mandant est lu une fois, sur l'ecran de depart, et transporte."""
        flux = []
        trace = trace_de(
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "A"\r\n')
        with Bac() as bac:
            resultat = P.explorer(trace, SapDePapier(), catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE, observateur=flux.append)
        depart = flux[0]
        self.assertEqual(depart.genre, E.DEPART)
        self.assertEqual(depart.systeme, resultat.systeme)
        self.assertEqual(depart.mandant, resultat.mandant)
        self.assertEqual(depart.langue, resultat.langue)
        self.assertEqual(depart.total, resultat.gestes_lus)
        self.assertEqual(depart.cible, resultat.catalogue)

    def test_les_deux_plafonds_se_disent_et_se_distinguent(self):
        """Un seul genre, `motif` pour les separer — et les deux sont exerces."""
        trace = trace_de("".join(
            f'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "{n}"\r\n'
            for n in range(10)))
        flux = []
        with Bac() as bac:
            P.explorer(trace, SapDePapier(), catalogue=bac, plafond_gestes=3,
                       plafond_ecrans=50, registre=REGISTRE,
                       observateur=flux.append)
        motifs = [e.motif for e in flux if e.genre == E.PLAFOND]
        self.assertEqual(motifs, ["gestes"])

        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n'
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH08"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        flux = []
        with Bac() as bac:
            P.explorer(trace, SapDePapier(), catalogue=bac, plafond_gestes=50,
                       plafond_ecrans=1, registre=REGISTRE,
                       observateur=flux.append)
        motifs = [e.motif for e in flux if e.genre == E.PLAFOND]
        self.assertEqual(motifs, ["ecrans"])

    def test_un_ecran_deja_connu_se_distingue_d_un_ecran_verse(self):
        """Deux genres, parce que les deux n'ajoutent pas a la file de relecture."""
        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        with Bac() as bac:
            P.explorer(trace, SapDePapier(), catalogue=bac, plafond_gestes=50,
                       plafond_ecrans=50, registre=REGISTRE)
            flux = []
            resultat = P.explorer(trace, SapDePapier(), catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE, observateur=flux.append)
        connus = [e for e in flux if e.genre == E.ECRAN_CONNU]
        verses = [e for e in flux if e.genre == E.ECRAN_VERSE]
        self.assertEqual(verses, [])
        self.assertEqual([e.clef for e in connus],
                         [str(c) for c in resultat.deja_connues])
        self.assertTrue(all(e.fenetre for e in connus))


class TestLesEvenementsSontDesFaitsPlats(unittest.TestCase):

    def test_aucun_evenement_ne_transporte_d_objet_vivant(self):
        """Ni liste, ni dict, ni set, ni objet du parcours.

        `_sauter_vers_reprise` REECRIT `p.branches[-1]` apres coup : un
        observateur qui tiendrait la liste verrait une branche changer dans son
        dos, ou en modifierait une autre. Le test parcourt TOUS les champs de
        `Evenement` plutot que d'en citer une liste, qui se perimerait au
        premier champ ajoute.
        """
        permis = (str, int, bool, tuple)
        flux = []
        with Bac() as bac:
            explorer_la_megatrace(bac, observateur=flux.append)
        self.assertTrue(flux)
        for evenement in flux:
            for nom in E.NOMS_DE_CHAMPS:
                valeur = getattr(evenement, nom)
                with self.subTest(genre=evenement.genre, champ=nom):
                    self.assertIsInstance(valeur, permis)
                    if isinstance(valeur, tuple):
                        for element in valeur:
                            self.assertIsInstance(element, str)

    def test_un_evenement_est_immuable(self):
        evenement = Evenement(genre=E.GESTE, ordre=3)
        with self.assertRaises(Exception):
            evenement.ordre = 4                     # type: ignore[misc]

    def test_un_genre_invente_est_refuse(self):
        """Un genre mal orthographie ne ferait rien tomber : il disparaitrait.

        Une ligne qui manque ne se voit pas — c'est le propre d'une ligne qui
        manque. CONTROLE NEGATIF : retirer `__post_init__` d'`Evenement`.
        """
        with self.assertRaises(GenreInconnu):
            Evenement(genre="progression")

    def test_tous_les_genres_emis_sont_declares(self):
        flux = []
        with Bac() as bac:
            explorer_la_megatrace(bac, observateur=flux.append)
        self.assertTrue({e.genre for e in flux} <= E.GENRES)

    def test_l_horloge_du_parcours_n_est_pas_consommee_par_l_affichage(self):
        """`monotone_ms` vient de `time.monotonic`, jamais de `p.horloge`.

        Celle-ci nomme les dumps et date les variantes, et les tests la figent
        sur une suite d'instants : la lire depuis un affichage decalerait les
        dates ECRITES DANS LE CATALOGUE. Un afficheur qui change ce qui est sur
        le disque.
        """
        instants = iter(["2026-09-08T10:00:00Z"] * 200)
        appels = []

        def horloge():
            appels.append(1)
            return next(instants)

        trace = trace_de(
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "A"\r\n')
        with Bac() as bac:
            sans = P.explorer(trace, SapDePapier(), catalogue=bac,
                              plafond_gestes=50, plafond_ecrans=50,
                              registre=REGISTRE, horloge=horloge)
        temoin = len(appels)
        appels.clear()
        with Bac() as bac:
            avec = P.explorer(trace, SapDePapier(), catalogue=bac,
                              plafond_gestes=50, plafond_ecrans=50,
                              registre=REGISTRE, horloge=horloge,
                              observateur=lambda _: None)
        self.assertEqual(len(appels), temoin)
        self.assertEqual(sans.versees, avec.versees)


class TestLaGardeSyntaxique(unittest.TestCase):
    """Ce qu'aucune execution ne peut prouver : l'endroit du code."""

    SOURCE = Path(inspect.getsourcefile(P))

    def _fonction(self, nom: str) -> ast.FunctionDef:
        arbre = ast.parse(self.SOURCE.read_text(encoding="utf-8"),
                          str(self.SOURCE))
        trouvees = [n for n in ast.walk(arbre)
                    if isinstance(n, ast.FunctionDef) and n.name == nom]
        self.assertEqual(len(trouvees), 1,
                         f"{nom} introuvable ou en double dans {self.SOURCE}")
        return trouvees[0]

    @staticmethod
    def _emissions(noeuds) -> list[int]:
        lignes = []
        for noeud in noeuds:
            for sous in ast.walk(noeud):
                if (isinstance(sous, ast.Call)
                        and isinstance(sous.func, ast.Attribute)
                        and sous.func.attr == "emettre"):
                    lignes.append(sous.lineno)
        return sorted(lignes)

    def test_aucune_emission_dans_le_corps_d_un_try_de_parcourir(self):
        """La faute que l'enveloppe d'`emettre` ne suffit PAS a couvrir.

        Une exception levee dans le corps du `try` de `_parcourir` y serait
        attrapee par `except Refus` ou `except Echec`, convertie en `Branche`
        dont le motif ACCUSE SAP, et `_dump_si_inconnu` ecrirait le dump d'un
        incident qui n'a jamais eu lieu. Les `except` eux-memes sont permis :
        ce qui y leve remonte, il ne se deguise pas en panne de SAP.

        CONTROLE NEGATIF : deplacer l'emission d'`ENVOYE` a l'interieur du
        `try`, juste apres `p.executer(traduction)`, fait tomber ce test.
        """
        parcourir = self._fonction("_parcourir")
        essais = [n for n in ast.walk(parcourir) if isinstance(n, ast.Try)]
        self.assertTrue(essais, "le `try` de `_parcourir` a disparu : ce test "
                                "ne protege plus rien")
        for essai in essais:
            fautives = self._emissions(essai.body)
            self.assertEqual(fautives, [],
                             f"emission(s) ligne(s) {fautives} dans le corps "
                             f"d'un `try` de `_parcourir`")

    def test_aucune_emission_dans_executer(self):
        """`executer` est appelee DEPUIS le `try`, et l'AST ne voit pas a
        travers un appel de methode : la garde precedente ne dirait rien d'une
        emission posee ici. Les deux ensemble, et aucune des deux seule.

        CONTROLE NEGATIF : poser une emission apres `self.actions += 1` dans
        `_Parcours.executer` fait tomber ce test, et lui seul.
        """
        executer = self._fonction("executer")
        fautives = self._emissions([executer])
        self.assertEqual(fautives, [],
                         f"emission(s) ligne(s) {fautives} dans "
                         f"`_Parcours.executer`")

    def test_la_garde_ne_passe_pas_a_vide(self):
        """Une garde qui ne trouve rien a garder ne garde rien.

        Elle a deja sauve ce depot une fois : « un controle qui confond une
        promesse avec son execution ne controle rien ».
        """
        parcourir = self._fonction("_parcourir")
        self.assertGreaterEqual(len(self._emissions([parcourir])), 6)


class TestCeQueLeCompteRenduEnDit(unittest.TestCase):

    def test_le_compte_rendu_se_tait_quand_l_affichage_n_a_pas_leve(self):
        with Bac() as bac:
            resultat = explorer_la_megatrace(bac, observateur=lambda _: None)
        from falcon.exploration.rapport import rendre
        texte = rendre(resultat, lire(MEGATRACE))
        self.assertEqual(resultat.pannes_d_affichage, 0)
        self.assertNotIn("L'AFFICHAGE EN DIRECT A LEVE", texte)

    def test_le_compte_rendu_dit_que_le_direct_s_est_tu(self):
        """« Le direct s'est tu » et « il n'y avait plus rien a montrer » ne se
        distinguent pas a l'ecran. CONTROLE NEGATIF : rendre la ligne
        inconditionnelle, ou la retirer, fait tomber ce test.
        """
        from falcon.exploration.rapport import rendre
        with Bac() as bac:
            resultat = explorer_la_megatrace(bac, observateur=lambda _: 1 / 0)
        texte = rendre(resultat, lire(MEGATRACE))
        self.assertIn("L'AFFICHAGE EN DIRECT A LEVE "
                      f"{resultat.pannes_d_affichage} fois", texte)


class TestLeCompteRenduEstConserve(unittest.TestCase):
    """Il defilait, puis disparaissait avec la fenetre."""

    def test_la_cartographie_ecrit_son_compte_rendu_a_cote_du_catalogue(self):
        from falcon.catalogue import Depot
        from falcon.commandes.cartographie import DOSSIER_RAPPORTS, cartographier

        sap = SapDePapier()
        sap.refusees = {"IW2ç"}
        with Bac() as bac:
            _, _, compte_rendu = cartographier(
                MEGATRACE, bac, plafond_gestes=500, plafond_ecrans=500,
                registre=REGISTRE, driver=sap,
                horloge=lambda: "2026-09-11T18:10:54.370Z")
            conserves = sorted((Path(bac) / DOSSIER_RAPPORTS).glob("*.txt"))
            # Le dossier est INVISIBLE du depot : `Depot.triplets()` globe
            # `racine/*.yaml` sans recursion. Un compte rendu qui apparaitrait
            # comme un ecran du catalogue serait pire qu'un compte rendu perdu.
            triplets = Depot(bac).triplets()
            texte = conserves[0].read_text(encoding="utf-8")

        self.assertEqual(len(conserves), 1)
        self.assertEqual(conserves[0].name,
                         "2026-09-11T18-10-54-370Z-megatrace_2026-09.vbs.txt")
        self.assertIn("cartographie de", texte)
        self.assertIn("gestes de la trace", texte)
        self.assertIn(str(conserves[0]), compte_rendu)
        self.assertNotIn(conserves[0].name, [f"{t}" for t in triplets])

    def test_deux_cartographies_de_la_meme_milliseconde_se_gardent_toutes_deux(self):
        """Un compte rendu perdu est une partition perdue."""
        from falcon.commandes.cartographie import DOSSIER_RAPPORTS, cartographier

        trace = trace_de(
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "A"\r\n')
        with Bac() as bac:
            for _ in range(2):
                cartographier(trace.source, bac, plafond_gestes=50,
                              plafond_ecrans=50, registre=REGISTRE,
                              driver=SapDePapier(),
                              horloge=lambda: "2026-09-11T18:10:54.370Z")
            conserves = sorted((Path(bac) / DOSSIER_RAPPORTS).glob("*.txt"))
        self.assertEqual(len(conserves), 2)

    def test_l_observateur_est_un_simple_passe_plat(self):
        """La cartographie ne sait pas ce qu'est un terminal, et c'est voulu."""
        from falcon.commandes.cartographie import cartographier

        flux = []
        trace = trace_de(
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "A"\r\n')
        with Bac() as bac:
            cartographier(trace.source, bac, plafond_gestes=50,
                          plafond_ecrans=50, registre=REGISTRE,
                          driver=SapDePapier(), observateur=flux.append)
        self.assertEqual([e.genre for e in flux][:2], [E.DEPART, E.ECRAN_VERSE])
        self.assertEqual(flux[-1].genre, E.FIN)


if __name__ == "__main__":               # pragma: no cover
    unittest.main()
