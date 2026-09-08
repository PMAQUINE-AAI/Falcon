"""Le rejeu d'une trace en observation, et la reprise sur code transaction.

Ces tests etablissent l'ORCHESTRATION — l'ordre des gestes, les refus, le
dedoublonnage, la reprise verifiee — et **rien du dialogue avec l'ERP**. Ils
tournent contre un double de papier. Aucune ligne de ce depot n'a parle a un
SAP reel, et cela compte davantage ici que partout ailleurs, puisque c'est le
premier module dont le metier est d'agir en rafale.

Les six controles negatifs du plan sont nommes dans les docstrings des tests
qui les portent : chacun dit ce qu'il faut casser dans le code de production
pour le faire tomber. Un test dont on ne sait pas ce qui le ferait tomber ne
prouve rien.
"""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from falcon.catalogue import Depot, clef_de
from falcon.controleur.gardes import BOUTON_SAUVEGARDE, VKEY_SAUVEGARDE
from falcon.couture.double import DriverScripte
from falcon.exploration import parcours as P
from falcon.noyau import CHAMP_DE_COMMANDE, Champ, Ecran, Fenetre, Identite
from falcon.taxonomie import Registre
from falcon.trace import lire
from falcon.trace.vbs import decouper

from tests.test_trace import MEGATRACE

#: Un registre vide de surcouche : celui du depot, tel qu'il est livre.
REGISTRE = Registre.charger()


def trace_de(lignes: str, nom: str = "essai.vbs"):
    """Une trace LUE par le vrai parseur, depuis du texte VBScript.

    Jamais de `Geste` bati a la main : un geste fabrique directement pourrait
    porter une combinaison verbe/forme/type que le recorder n'ecrit pas, et le
    test prouverait quelque chose sur une trace qui n'existe pas.
    """
    dossier = Path(tempfile.mkdtemp()) / nom
    dossier.write_text(lignes, encoding="utf-8", newline="\r\n")
    return lire(dossier)


def _champs(*ids: str) -> tuple[Champ, ...]:
    return tuple(Champ(id=i, type="GuiTextField") for i in ids)


class SapDePapier(DriverScripte):
    """Un SAP de papier. **N'etablit aucune fidelite.**

    Il sert deux choses que `DriverScripte` ne sait pas faire, et les deux
    sont indispensables ici :

    1. **des champs PAR FENETRE.** `DriverScripte.fields()` rend les memes
       champs pour toutes les fenetres ; un test de dedoublonnage passerait
       alors sur un double incapable de distinguer `wnd[0]` de `wnd[1]`, et
       « prouverait » un comportement que le vrai driver n'aura pas.
    2. **le demarrage d'une transaction a l'Entree**, et pas a l'ecriture dans
       le champ de commande. C'est le piege central du module teste : si le
       double demarrait des l'ecriture, un rejeu qui oublie l'Entree passerait.
    """

    ACCUEIL = Identite(transaction="SESSION_MANAGER",
                       programme="SAPLSMTR_NAVIGATION", dynpro="0100")

    def __init__(self, ecrans: dict[str, Identite] | None = None):
        super().__init__(identite=self.ACCUEIL)
        self.par_fenetre: dict[str, tuple[Champ, ...]] = {
            "wnd[0]": _champs("wnd[0]/usr/ctxtACCUEIL")}
        self.ecrans = dict(ecrans or {})
        #: Transactions que ce SAP refuse : il reste ou il est.
        self.refusees: set[str] = set()
        #: Compte des demarrages effectifs, pour distinguer « tape » de « parti ».
        self.demarrages = 0

    # -- observation -----------------------------------------------------

    def fields(self, fenetre: str = "wnd[0]") -> Ecran:
        return Ecran(identite=self.identite, fenetre=fenetre,
                     champs=self.par_fenetre.get(fenetre, ()),
                     titre=f"{self.identite.transaction} {fenetre}")

    # -- actions ----------------------------------------------------------

    def vkey(self, n: int, fenetre: str = "wnd[0]") -> None:
        super().vkey(n, fenetre)
        if n == 0 and fenetre == "wnd[0]":
            self._demarrer()

    def _demarrer(self) -> None:
        commande = self.valeurs.get(CHAMP_DE_COMMANDE, "")
        if not commande.startswith("/n") or commande == "/n":
            return
        code = commande[2:]
        self.valeurs[CHAMP_DE_COMMANDE] = ""
        if code in self.refusees:
            return                       # SAP reste ou il est
        self.demarrages += 1
        self.identite = self.ecrans.get(
            code, Identite(transaction=code, programme=f"SAPL{code}",
                           dynpro="1000"))
        self.par_fenetre = {
            "wnd[0]": _champs(f"wnd[0]/usr/ctxt{code}-LOW",
                              f"wnd[0]/usr/ctxt{code}-HIGH")}

    def ouvrir_modale(self, *ids: str) -> None:
        self.fenetres = (Fenetre(id="wnd[0]", type="GuiMainWindow"),
                         Fenetre(id="wnd[1]", type="GuiModalWindow"))
        self.par_fenetre["wnd[1]"] = _champs(*ids)


class Bac:
    """Un dossier de catalogue jetable."""

    def __enter__(self) -> Path:
        self._bac = tempfile.TemporaryDirectory()
        return Path(self._bac.name)

    def __exit__(self, *_) -> None:
        self._bac.cleanup()


def quarantaine(racine: Path) -> Depot:
    return Depot(Depot(racine).quarantaine)


# =========================================================================


class TestLaSuretEstStructurelle(unittest.TestCase):
    """Les refus qui ne sont pas des parametres."""

    def test_la_signature_n_expose_ni_le_mode_ni_le_plafond_de_sauvegardes(self):
        """CONTROLE NEGATIF n°2 : ajouter l'un des deux fait tomber ce test.

        Un `mode="dry-run"` par defaut se change en un mot sur une ligne de
        commande, par quelqu'un qui veut « juste voir ».
        """
        parametres = set(inspect.signature(P.explorer).parameters)
        self.assertNotIn("mode", parametres)
        self.assertNotIn("plafond_sauvegardes", parametres)

    def test_les_deux_constantes_sont_celles_du_refus(self):
        self.assertEqual(P.MODE, "dry-run")
        self.assertEqual(P.PLAFOND_SAUVEGARDES, 0)

    def test_le_bouton_de_sauvegarde_est_refuse_et_la_branche_tombe(self):
        """CONTROLE NEGATIF n°1 : le `press` sur `btn[11]` ne doit pas passer.

        Faire accepter la sauvegarde — en enlevant le dry-run, ou en relevant
        le plafond — fait tomber ce test de deux facons : le driver brut verrait
        le geste, et aucune branche ne serait notee.
        """
        trace = trace_de(
            f'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            f'session.findById("wnd[0]").sendVKey 0\r\n'
            f'session.findById("wnd[0]/{BOUTON_SAUVEGARDE}").press\r\n'
            f'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH08"\r\n'
            f'session.findById("wnd[0]").sendVKey 0\r\n')
        sap = SapDePapier()
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)

        self.assertEqual(len(resultat.sauvegardes_refusees), 1)
        self.assertEqual(resultat.sauvegardes_refusees[0].cible,
                         f"wnd[0]/{BOUTON_SAUVEGARDE}")
        # Le driver BRUT n'a jamais vu le geste.
        self.assertNotIn(("press", f"wnd[0]/{BOUTON_SAUVEGARDE}", ""),
                         sap.gestes)
        motifs = [b.categorie for b in resultat.branches]
        self.assertIn(P.SAUVEGARDE, motifs)

    def test_la_touche_de_sauvegarde_est_refusee_elle_aussi(self):
        """`vkey 11` sauvegarde au clavier autant que `btn[11]` a la souris.

        Test SYNTHETIQUE, et il le faut : la trace de reference n'en contient
        aucun. S'en remettre a elle laisserait ce chemin sans controle.
        """
        trace = trace_de(
            f'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            f'session.findById("wnd[0]").sendVKey 0\r\n'
            f'session.findById("wnd[0]").sendVKey {VKEY_SAUVEGARDE}\r\n')
        sap = SapDePapier()
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual(len(resultat.sauvegardes_refusees), 1)
        self.assertNotIn(("vkey", "wnd[0]", str(VKEY_SAUVEGARDE)), sap.gestes)

    def test_un_verbe_d_arbre_n_est_jamais_envoye_au_driver(self):
        """CONTROLE NEGATIF n°3 : rendre un verbe d'arbre rejouable.

        Le faire traduire dans `gestes.TABLE` ferait tomber ce test — la
        couture n'a aucune methode d'arbre, et `getattr(driver, ...)` leverait
        un `AttributeError` au lieu de noter une branche.
        """
        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n'
            'session.findById("wnd[0]/shellcont/shell").expandNode "26"\r\n'
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH08"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        sap = SapDePapier()
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        arbre = [b for b in resultat.branches if b.categorie == P.SANS_COUTURE]
        self.assertEqual(len(arbre), 1)
        self.assertEqual(arbre[0].verbe, "expandNode")
        self.assertIn("arbre", arbre[0].motif)
        self.assertEqual(arbre[0].reprise, "IH08")
        self.assertFalse([g for g in sap.gestes if "shell" in g[1]])


class TestLActionAveugle(unittest.TestCase):
    """Le trou que `DriverGarde` ne bouche pas, et que l'exploration ferme.

    `gardes._est_sauvegarde` ne reconnait que `vkey(11)` et `btn[11]`.
    **Entree n'en fait pas partie, et `usr/btnBUTTON_1` non plus** — c'est
    pourtant le nom SAP standard du premier bouton d'une popup generique,
    donc le « Oui » de « Donnees modifiees, enregistrer ? ». Une pipeline vit
    avec cette limite : un humain a declare `sauvegarde` la ou elle sauve.
    Une exploration, non.
    """

    def test_un_bouton_de_popup_generique_dans_une_modale_inconnue_est_refuse(self):
        """`usr/btnBUTTON_1` : le « Oui » d'une SPOP.

        Le raisonnement « un press NOMME sa cible, donc il leve si l'ecran
        differe » tombe precisement ici : toutes les popups generiques de SAP
        portent ce meme identifiant. Le press reussirait sur la mauvaise
        boite. C'est ce qui a fait passer la regle de « aucune touche
        aveugle » a « aucune ACTION aveugle ».
        """
        trace = trace_de(
            'session.findById("wnd[0]/usr/btnGO").press\r\n'
            'session.findById("wnd[1]/usr/btnBUTTON_1").press\r\n')
        sap = SapDePapier()
        sap.apres_action = lambda double, geste, cible: (
            double.ouvrir_modale("wnd[1]/usr/btnBUTTON_1")
            if cible == "wnd[0]/usr/btnGO" else None)
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual([b.categorie for b in resultat.branches],
                         [P.ACTION_AVEUGLE])
        self.assertNotIn(("press", "wnd[1]/usr/btnBUTTON_1", ""), sap.gestes)

    def test_une_touche_vers_une_modale_non_identifiee_est_refusee(self):
        """CONTROLE NEGATIF : retirer `_touche_aveugle` fait tomber ce test.

        Le driver brut recevrait alors la frappe — c'est-a-dire, sur un vrai
        SAP dont l'exploration aurait diverge, un enregistrement.
        """
        trace = trace_de(
            'session.findById("wnd[0]/usr/btnBUTTON_1").press\r\n'
            'session.findById("wnd[1]").sendVKey 0\r\n')
        sap = SapDePapier()
        sap.apres_action = lambda double, geste, cible: (
            double.ouvrir_modale("wnd[1]/usr/txtSPOP")
            if geste == "press" else None)
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual([b.categorie for b in resultat.branches],
                         [P.ACTION_AVEUGLE])
        self.assertNotIn(("vkey", "wnd[1]", "0"), sap.gestes)

    def test_une_touche_vers_une_modale_DEJA_touchee_passe(self):
        """Un identifiant qui resout etablit que la fenetre porte ce controle.

        Ce n'est pas la preuve que la boite est celle de l'enregistrement —
        rien ici ne peut l'etablir — mais c'est un fait observe, et une boite
        de confirmation d'enregistrement ne porte pas `usr/txtV-LOW`.
        """
        trace = trace_de(
            'session.findById("wnd[0]/usr/btnBUTTON_1").press\r\n'
            'session.findById("wnd[1]/usr/txtV-LOW").text = "*BCP*"\r\n'
            'session.findById("wnd[1]").sendVKey 0\r\n')
        sap = SapDePapier()
        sap.apres_action = lambda double, geste, cible: (
            double.ouvrir_modale("wnd[1]/usr/txtV-LOW")
            if geste == "press" else None)
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual(resultat.branches, ())
        self.assertIn(("vkey", "wnd[1]", "0"), sap.gestes)

    def test_une_touche_vers_wnd0_est_refusee_si_une_modale_est_ouverte(self):
        """C'est la fenetre au premier plan qui recevrait la frappe."""
        trace = trace_de(
            'session.findById("wnd[0]/usr/btnBUTTON_1").press\r\n'
            'session.findById("wnd[0]").sendVKey 3\r\n')
        sap = SapDePapier()
        sap.apres_action = lambda double, geste, cible: (
            double.ouvrir_modale("wnd[1]/usr/txtSPOP")
            if geste == "press" else None)
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual([b.categorie for b in resultat.branches],
                         [P.ACTION_AVEUGLE])
        self.assertNotIn(("vkey", "wnd[0]", "3"), sap.gestes)

    def test_une_action_activante_n_identifie_pas_la_fenetre_pour_la_suivante(self):
        """Deux Entree d'affilee : la seconde n'herite pas de la premiere.

        Une action qui ACTIVE aurait reussi sur n'importe quelle boite : elle
        n'etablit donc rien sur celle qui est la maintenant.
        """
        trace = trace_de(
            'session.findById("wnd[0]/usr/btnBUTTON_1").press\r\n'
            'session.findById("wnd[1]/usr/txtV-LOW").text = "*BCP*"\r\n'
            'session.findById("wnd[1]").sendVKey 0\r\n'
            'session.findById("wnd[1]").sendVKey 0\r\n')
        sap = SapDePapier()
        sap.apres_action = lambda double, geste, cible: (
            double.ouvrir_modale("wnd[1]/usr/txtV-LOW")
            if geste == "press" else None)
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual([b.categorie for b in resultat.branches],
                         [P.ACTION_AVEUGLE])
        self.assertEqual(sap.gestes.count(("vkey", "wnd[1]", "0")), 1)


class TestLaReprise(unittest.TestCase):
    """Le coeur du module : on ne repart que sur du verifie."""

    def test_la_reprise_tape_le_code_ET_valide_par_entree(self):
        """Sans l'Entree, SAP resterait sur l'ecran precedent en silence."""
        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        sap = SapDePapier()
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual(sap.demarrages, 1)
        self.assertEqual(sap.identite.transaction, "IH06")
        self.assertEqual([r.demandee for r in resultat.reprises], ["IH06"])
        self.assertTrue(resultat.reprises[0].acceptee)
        # L'Entree de la trace a ete consommee par la reprise, pas rejouee.
        self.assertEqual(resultat.validations_consommees, 1)
        self.assertEqual(sap.gestes.count(("vkey", "wnd[0]", "0")), 1)

    def test_la_reprise_ecrit_dans_l_identifiant_complet(self):
        """Le suffixe sert a RECONNAITRE le champ, pas a y ecrire."""
        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        sap = SapDePapier()
        with Bac() as bac:
            P.explorer(trace, sap, catalogue=bac, plafond_gestes=50,
                       plafond_ecrans=50, registre=REGISTRE)
        ecrits = [g for g in sap.gestes if g[0] == "write"]
        self.assertEqual(ecrits, [("write", CHAMP_DE_COMMANDE, "/nIH06")])

    def test_un_code_refuse_par_sap_fait_tomber_la_branche(self):
        """La verification porte sur le MOT ENTIER, des deux cotes.

        `startswith` apparierait « IW3 » et « IW39 », `in` apparierait « IH0 »
        avec « IH06 » comme avec « IH08 ».
        """
        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIW39"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n'
            'session.findById("wnd[0]/usr/ctxtIW39-LOW").text = "10"\r\n'
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIW3"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n'
            'session.findById("wnd[0]/usr/ctxtIW3-LOW").text = "20"\r\n')
        sap = SapDePapier()
        sap.refusees = {"IW3"}
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        refusees = [r for r in resultat.reprises if not r.acceptee]
        self.assertEqual([r.demandee for r in refusees], ["IW3"])
        self.assertEqual(refusees[0].obtenue, "IW39")
        self.assertIn(P.REPRISE_REFUSEE,
                      [b.categorie for b in resultat.branches])
        # Le geste qui suivait le code refuse n'a PAS ete rejoue.
        self.assertNotIn(("write", "wnd[0]/usr/ctxtIW3-LOW", "20"), sap.gestes)

    def test_n_seul_n_est_pas_un_point_de_reprise(self):
        """Apres `/n`, la seule verification possible serait « ca a change ».

        Vraie aussi quand SAP a atterri ailleurs. Consequence assumee : les
        gestes situes entre l'interruption et le prochain code NOMME sont
        sautes.
        """
        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/n"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        sap = SapDePapier()
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual(resultat.reprises, ())
        self.assertEqual([b.categorie for b in resultat.branches],
                         [P.SANS_REPRISE])
        self.assertEqual(sap.demarrages, 0)
        self.assertFalse([g for g in sap.gestes if g[0] == "write"])

    def test_un_code_de_session_n_est_jamais_tape(self):
        """`/nex` termine la session. `_CODE` le laisse passer : il rend « ex ».

        Le taper fermerait SAP pendant que le rapport annoncerait une reprise.
        """
        for commande in ("/nex", "/nend", "/n/nex", "/n*VA01"):
            with self.subTest(commande):
                trace = trace_de(
                    f'session.findById("wnd[0]/tbar[0]/okcd").text = '
                    f'"{commande}"\r\n'
                    f'session.findById("wnd[0]").sendVKey 0\r\n')
                sap = SapDePapier()
                with Bac() as bac:
                    resultat = P.explorer(trace, sap, catalogue=bac,
                                          plafond_gestes=50, plafond_ecrans=50,
                                          registre=REGISTRE)
                self.assertEqual([b.categorie for b in resultat.branches],
                                 [P.SANS_REPRISE])
                self.assertFalse([g for g in sap.gestes if g[0] == "write"])

    def test_une_modale_ouverte_interdit_la_reprise_et_arrete_tout(self):
        """Le champ de commande n'existe pas dans `wnd[1]`.

        Le rendre atteignable demanderait de fermer la modale, donc d'inventer
        un geste que la trace ne contient pas.
        """
        trace = trace_de(
            'session.findById("wnd[0]/usr/btnBUTTON_1").press\r\n'
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        sap = SapDePapier()
        sap.apres_action = lambda double, geste, cible: (
            double.ouvrir_modale("wnd[1]/usr/txtMESSAGE")
            if geste == "press" else None)
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual(resultat.etat, P.INTERROMPUE)
        self.assertIn("wnd[0]", resultat.raison)
        self.assertEqual(sap.demarrages, 0)

    def test_une_branche_reprend_au_PROCHAIN_code_transaction(self):
        """CONTROLE NEGATIF n°5 : reprendre ailleurs qu'au prochain code.

        Reprendre au geste suivant — sans retaper de code — rejouerait la
        suite sur l'ecran d'avant l'interruption. Le test tombe alors sur
        `reprise` et sur le compte des sautes.
        """
        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n'
            'session.findById("wnd[0]/shellcont/shell").expandNode "26"\r\n'
            'session.findById("wnd[0]/usr/ctxtIH06-LOW").text = "A"\r\n'
            'session.findById("wnd[0]/usr/ctxtIH06-HIGH").text = "B"\r\n'
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIW29"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        sap = SapDePapier()
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual([b.reprise for b in resultat.branches], ["IW29"])
        # Les deux `text` entre l'arbre et le code suivant sont SAUTES.
        self.assertEqual(resultat.gestes_sautes, 2)
        self.assertNotIn(("write", "wnd[0]/usr/ctxtIH06-LOW", "A"), sap.gestes)
        self.assertEqual([r.demandee for r in resultat.reprises],
                         ["IH06", "IW29"])

    def test_deux_codes_refuses_ne_se_renvoient_pas_la_balle(self):
        """La reprise avance STRICTEMENT, sinon l'exploration tourne en rond."""
        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nZZZ1"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n'
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nZZZ2"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        sap = SapDePapier()
        sap.refusees = {"ZZZ1", "ZZZ2"}
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual([r.demandee for r in resultat.reprises],
                         ["ZZZ1", "ZZZ2"])
        self.assertEqual(resultat.etat, P.INTERROMPUE)


class TestLeReleve(unittest.TestCase):

    def test_toutes_les_fenetres_sont_relevees_pas_seulement_wnd0(self):
        """La moitie de la trace de reference se passe dans `wnd[1]`."""
        trace = trace_de(
            'session.findById("wnd[0]/usr/btnBUTTON_1").press\r\n')
        sap = SapDePapier()
        sap.apres_action = lambda double, geste, cible: (
            double.ouvrir_modale("wnd[1]/usr/txtVARIANTE")
            if geste == "press" else None)
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
            versees = quarantaine(bac)
            champs = {c.id for clef in resultat.versees
                      for c in versees.pour_edition(clef).champs}
        self.assertIn("wnd[1]/usr/txtVARIANTE", champs)

    def test_le_meme_ecran_quatre_fois_n_est_compte_qu_une_fois(self):
        """CONTROLE NEGATIF n°4 : deux ecrans identiques comptes deux fois.

        Retirer le jeu des clefs deja vues (`self.vues`) fait tomber ce test.
        **Et il ne tombait pas dans sa premiere redaction** — mesure : sans le
        jeu, `versees` valait toujours 1, parce que la consultation de la
        quarantaine rattrapait le doublon a l'ecriture. Ce qui changeait, c'est
        `deja_connues`, qui passait de 1 a 3 : le compte rendu annoncait trois
        ecrans « deja connus » la ou il y en a un seul.

        C'est exactement le resultat plausible et faux que ce depot traque, et
        un test qui ne regardait que `versees` ne le voyait pas.
        """
        trace = trace_de(
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "A"\r\n'
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "B"\r\n'
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "C"\r\n')
        sap = SapDePapier()
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual(len(resultat.versees), 1)
        self.assertEqual(resultat.gestes_rejoues, 3)
        # Quatre releves (un au depart, un par geste), un seul ecran compte.
        self.assertEqual(resultat.releves, 4)
        self.assertEqual(resultat.deja_connues, ())

    def test_relancer_l_exploration_ne_verse_rien_de_neuf(self):
        """Idempotent : le second parcours ne reecrit pas un octet."""
        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        with Bac() as bac:
            premier = P.explorer(trace, SapDePapier(), catalogue=bac,
                                 plafond_gestes=50, plafond_ecrans=50,
                                 registre=REGISTRE)
            avant = {f.name: f.read_bytes()
                     for f in sorted(Path(bac).rglob("*.yaml"))}
            second = P.explorer(trace, SapDePapier(), catalogue=bac,
                                plafond_gestes=50, plafond_ecrans=50,
                                registre=REGISTRE)
            apres = {f.name: f.read_bytes()
                     for f in sorted(Path(bac).rglob("*.yaml"))}
        self.assertTrue(premier.versees)
        self.assertEqual(second.versees, ())
        self.assertEqual(set(second.deja_connues), set(premier.versees))
        self.assertEqual(avant, apres)

    def test_un_ecran_deja_promu_ne_revient_pas_en_quarantaine(self):
        """La barriere qui compte : le catalogue CURE est consulte.

        Sans elle, un ecran qu'un humain a relu et promu reapparaitrait en
        quarantaine au parcours suivant, et sa repromotion ecraserait le
        fichier relu par un releve frais.
        """
        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        with Bac() as bac:
            premier = P.explorer(trace, SapDePapier(), catalogue=bac,
                                 plafond_gestes=50, plafond_ecrans=50,
                                 registre=REGISTRE)
            depot = Depot(bac)
            for clef in premier.versees:
                depot.promouvoir(clef)
            for fichier in Path(depot.quarantaine).glob("*.yaml"):
                fichier.unlink()
            second = P.explorer(trace, SapDePapier(), catalogue=bac,
                                plafond_gestes=50, plafond_ecrans=50,
                                registre=REGISTRE)
        self.assertEqual(second.versees, ())
        self.assertEqual(set(second.deja_connues), set(premier.versees))

    def test_le_releve_porte_une_date(self):
        """Un releve sans date est indistinguable d'un ecran venu de nulle part."""
        trace = trace_de(
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "A"\r\n')
        with Bac() as bac:
            resultat = P.explorer(trace, SapDePapier(), catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE,
                                  horloge=lambda: "2026-09-08T10:00:00Z")
            versees = quarantaine(bac)
            dates = {versees.pour_edition(c).capture_le
                     for c in resultat.versees}
        self.assertEqual(dates, {"2026-09-08T10:00:00Z"})

    def test_les_variantes_sont_des_releves_pas_des_esquisses(self):
        trace = trace_de(
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "A"\r\n')
        with Bac() as bac:
            resultat = P.explorer(trace, SapDePapier(), catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
            versees = quarantaine(bac)
            for clef in resultat.versees:
                variante = versees.pour_edition(clef)
                self.assertTrue(variante.observee)
                self.assertNotEqual(variante.clef.programme, "?")


class TestLesPlafonds(unittest.TestCase):

    def test_un_plafond_nul_est_refuse_avant_tout_contact(self):
        trace = trace_de('session.findById("wnd[0]/usr/ctxtA").text = "A"\r\n')
        sap = SapDePapier()
        with Bac() as bac:
            for gestes, ecrans in ((0, 5), (5, 0), (-1, 5)):
                with self.subTest(gestes=gestes, ecrans=ecrans):
                    with self.assertRaises(P.ExplorationImpossible):
                        P.explorer(trace, sap, catalogue=bac,
                                   plafond_gestes=gestes,
                                   plafond_ecrans=ecrans, registre=REGISTRE)
        self.assertEqual(sap.gestes, [])

    def test_une_trace_sans_geste_est_refusee(self):
        """« Terminee, zero ecran » est le pire des resultats."""
        trace = trace_de("' rien que des commentaires\r\n")
        with Bac() as bac:
            with self.assertRaises(P.ExplorationImpossible):
                P.explorer(trace, SapDePapier(), catalogue=bac,
                           plafond_gestes=5, plafond_ecrans=5,
                           registre=REGISTRE)

    def test_le_plafond_de_gestes_dit_ce_qui_n_a_pas_ete_explore(self):
        trace = trace_de("".join(
            f'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "{n}"\r\n'
            for n in range(10)))
        with Bac() as bac:
            resultat = P.explorer(trace, SapDePapier(), catalogue=bac,
                                  plafond_gestes=3, plafond_ecrans=50,
                                  registre=REGISTRE)
        self.assertEqual(resultat.etat, P.PLAFOND)
        self.assertTrue(resultat.au_plafond)
        self.assertEqual(resultat.actions_envoyees, 3)
        self.assertEqual(resultat.gestes_non_explores, 7)
        self.assertIn("n'a PAS ete explore", resultat.raison)

    def test_le_plafond_d_ecrans_est_verifie_AVANT_le_versement(self):
        """Verifie apres coup, il laisserait passer un ecran de plus."""
        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n'
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH08"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        with Bac() as bac:
            resultat = P.explorer(trace, SapDePapier(), catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=1,
                                  registre=REGISTRE)
            fichiers = sorted(p.name for p in
                              Path(Depot(bac).quarantaine).glob("*.yaml"))
        self.assertEqual(resultat.etat, P.PLAFOND)
        self.assertEqual(len(resultat.versees), 1)
        self.assertEqual(len(fichiers), 1)


class TestLaMegatrace(unittest.TestCase):
    """De bout en bout, contre le double, sur la trace de reference."""

    @classmethod
    def setUpClass(cls):
        cls.trace = lire(MEGATRACE)

    def _explorer(self, bac: Path):
        return P.explorer(self.trace, SapDePapier(), catalogue=bac,
                          plafond_gestes=500, plafond_ecrans=500,
                          registre=REGISTRE)

    def test_la_partition_des_gestes_est_complete(self):
        """Si la somme ne fait pas le total, des gestes disparaissent du rapport.

        « 34 rejoues sur 90 » sans que les 56 autres apparaissent nulle part
        est exactement le compte rendu plausible et faux que ce depot traque.
        """
        with Bac() as bac:
            resultat = self._explorer(bac)
        self.assertEqual(resultat.gestes_lus, 90)
        self.assertTrue(resultat.partition_coherente,
                        f"{resultat.partition} ne somme pas a "
                        f"{resultat.gestes_lus}")

    def test_aucune_sauvegarde_n_a_eu_lieu(self):
        """Le chiffre qu'on relit pour se convaincre."""
        with Bac() as bac:
            resultat = self._explorer(bac)
        self.assertTrue(resultat.sauvegardes_refusees)
        for refus in resultat.sauvegardes_refusees:
            self.assertTrue(refus.cible.endswith(BOUTON_SAUVEGARDE)
                            or refus.verbe == "sendVKey")

    def test_la_trace_de_reference_sauvegarde_huit_fois(self):
        """Mesure, pas conjecture : huit `press` sur le bouton Sauvegarder.

        Toutes dans un flux « obtenir/enregistrer une variante » — c'est-a-dire
        que rejouer cette trace SANS le dry-run ecrirait huit fois dans SAP.
        """
        apercu = P.previsualiser(self.trace)
        self.assertEqual(apercu.sauvegardes, (10, 13, 27, 28, 70, 71, 88, 89))

    def test_les_dix_gestes_d_arbre_sont_nommes_comme_hors_de_portee(self):
        apercu = P.previsualiser(self.trace)
        self.assertEqual(len(apercu.sans_couture), 10)
        self.assertEqual(apercu.codes,
                         ("IH06", "IH08", "IW39", "IW2ç", "IW29"))
        self.assertEqual(apercu.sans_reprise, (30,))    # le `/n` seul

    def test_ce_qui_est_verse_est_ce_que_le_double_a_servi(self):
        """Les ecrans verses sont exactement les ecrans distincts observes."""
        with Bac() as bac:
            resultat = self._explorer(bac)
            versees = quarantaine(bac)
            for clef in resultat.versees:
                self.assertIsNotNone(versees.pour_edition(clef))
        self.assertEqual(len(set(resultat.versees)), len(resultat.versees))
        self.assertTrue(resultat.versees)

    def test_le_parcours_mesure_de_la_trace_de_reference(self):
        """La marche complete, chiffree. Elle est ce qu'on relit pour juger.

        Elle est aussi ce qui perime le plus vite : un chiffre en docstring se
        demode en silence, un chiffre en test tombe. Les cinq branches sont
        nommees parce que leur NATURE compte plus que leur nombre — trois
        sauvegardes, un code refuse par SAP, une touche aveugle.
        """
        sap = SapDePapier()
        sap.refusees = {"IW2ç"}          # SAP refuse la faute de frappe
        with Bac() as bac:
            resultat = P.explorer(self.trace, sap, catalogue=bac,
                                  plafond_gestes=500, plafond_ecrans=500,
                                  registre=REGISTRE)
        self.assertEqual(
            resultat.partition,
            {"rejoues": 23, "confort": 9, "interrompus": 4, "reprises": 5,
             "validations consommees": 3, "sautes": 46, "non explores": 0})
        self.assertEqual(
            [(b.ordre, b.categorie, b.reprise) for b in resultat.branches],
            [(10, P.SAUVEGARDE, "IH08"),
             (27, P.SAUVEGARDE, "IW39"),
             (66, P.ACTION_AVEUGLE, "IW2ç"),
             (73, P.REPRISE_REFUSEE, "IW29"),
             (82, P.ACTION_AVEUGLE, "")])
        self.assertEqual(resultat.etat, P.INTERROMPUE)

    def test_les_gestes_d_arbre_ne_sont_meme_pas_ATTEINTS(self):
        """Mesure qui corrige ce que le plan supposait.

        Le plan annoncait dix branches « sans couture » pour les dix gestes
        d'arbre. Contre le double, il n'y en a aucune : la branche tombe
        AVANT, au geste 010, sur une sauvegarde, et reprend a IH08 — les
        gestes 032 a 041 sont sautes sans jamais avoir ete traduits.

        La nuance n'est pas de vocabulaire : « refuse parce que la couture ne
        sait pas » et « jamais atteint » se corrigent differemment, et le
        rapport doit pouvoir dire lequel des deux s'est produit. D'ou
        `ordres_sautes`, une liste et pas un compte.
        """
        with Bac() as bac:
            resultat = self._explorer(bac)
        arbre = set(P.previsualiser(self.trace).sans_couture)
        self.assertEqual(len(arbre), 10)
        self.assertTrue(arbre <= set(resultat.ordres_sautes),
                        "les gestes d'arbre devraient etre sautes, pas refuses")
        self.assertEqual([b.categorie for b in resultat.branches
                          if b.categorie == P.SANS_COUTURE], [])
        self.assertEqual(len(resultat.ordres_sautes), resultat.gestes_sautes)

    def test_la_faute_de_frappe_de_l_operateur_n_est_pas_reparee(self):
        """`/nIW2ç` est tape tel quel, et c'est SAP qui refuse."""
        sap = SapDePapier()
        sap.refusees = {"IW2ç"}
        with Bac() as bac:
            resultat = P.explorer(self.trace, sap, catalogue=bac,
                                  plafond_gestes=500, plafond_ecrans=500,
                                  registre=REGISTRE)
        demandees = [r.demandee for r in resultat.reprises]
        self.assertIn("IW2ç", demandees)
        refusees = [r for r in resultat.reprises if not r.acceptee]
        self.assertEqual([r.demandee for r in refusees], ["IW2ç"])


class TestLesGardes(unittest.TestCase):

    def test_la_fenetre_imprevue_est_derogee_donc_TRACEE(self):
        """Une derogation emet un constat PAR ACTION ; un elargissement, un seul.

        C'est la difference entre voir surgir chaque modale et n'en voir
        qu'une mention a la pose du contrat.
        """
        trace = trace_de(
            'session.findById("wnd[0]/usr/btnBUTTON_1").press\r\n'
            'session.findById("wnd[1]/usr/txtA").text = "X"\r\n'
            'session.findById("wnd[1]/usr/txtA").text = "Y"\r\n')
        sap = SapDePapier()
        sap.apres_action = lambda double, geste, cible: (
            double.ouvrir_modale("wnd[1]/usr/txtA")
            if geste == "press" else None)
        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        derogees = [c for c in resultat.constats
                    if c.garde == "fenetre" and c.verdict == "derogee"]
        self.assertGreater(len(derogees), 1)
        self.assertIn("wnd[1]", derogees[-1].detail["intruses"])
        self.assertEqual(resultat.gestes_rejoues, 3)

    def test_la_garde_d_identite_est_desarmee_et_le_dit(self):
        trace = trace_de(
            'session.findById("wnd[0]/usr/ctxtACCUEIL").text = "A"\r\n')
        with Bac() as bac:
            resultat = P.explorer(trace, SapDePapier(), catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
        non_gardees = [c for c in resultat.constats
                       if c.garde == "identite" and c.verdict == "non_gardee"]
        self.assertTrue(non_gardees)
        self.assertIn("geste 001", non_gardees[0].detail["etape"])

    def test_un_statut_E_inconnu_arrete_la_BRANCHE_pas_l_exploration(self):
        """L'assouplissement, et ce qui l'achete : la reprise verifiee."""
        from falcon.noyau import Statut
        trace = trace_de(
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIH06"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n'
            'session.findById("wnd[0]/usr/btnGO").press\r\n'
            'session.findById("wnd[0]/usr/ctxtIH06-LOW").text = "PERDU"\r\n'
            'session.findById("wnd[0]/tbar[0]/okcd").text = "/nIW29"\r\n'
            'session.findById("wnd[0]").sendVKey 0\r\n')
        sap = SapDePapier()

        def apres(double, geste, cible):
            if geste == "press":
                double.statut = Statut(type="E", id="ZZ", numero="042",
                                       texte="rien de connu")
            else:
                double.statut = Statut()
        sap.apres_action = apres

        with Bac() as bac:
            resultat = P.explorer(trace, sap, catalogue=bac,
                                  plafond_gestes=50, plafond_ecrans=50,
                                  registre=REGISTRE)
            dumps = sorted(p.name for p in (Path(bac) / "dumps").glob("*.json"))

        incidents = [b for b in resultat.branches if b.categorie == P.INCIDENT]
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0].reprise, "IW29")
        self.assertTrue(dumps, "un inconnu bloquant doit laisser un dump")
        self.assertTrue(incidents[0].dump)
        # La branche est tombee : le geste suivant n'a pas ete rejoue.
        self.assertNotIn(("write", "wnd[0]/usr/ctxtIH06-LOW", "PERDU"),
                         sap.gestes)
        # Et l'exploration a bien repris.
        self.assertEqual(sap.identite.transaction, "IW29")

    def test_le_dump_porte_la_signature_soumise_au_registre(self):
        """La reconstruire depuis `detail` est une conjecture, et elle est fausse."""
        import json
        from falcon.noyau import Statut
        trace = trace_de(
            'session.findById("wnd[0]/usr/btnGO").press\r\n')
        sap = SapDePapier()
        sap.apres_action = lambda double, geste, cible: setattr(
            double, "statut",
            Statut(type="E", id="ZZ", numero="042", texte="rien de connu"))
        with Bac() as bac:
            P.explorer(trace, sap, catalogue=bac, plafond_gestes=50,
                       plafond_ecrans=50, registre=REGISTRE)
            fichiers = sorted((Path(bac) / "dumps").glob("*.json"))
            charge = json.loads(fichiers[0].read_text(encoding="utf-8"))
        self.assertIsNotNone(charge["signature"])
        self.assertEqual(charge["signature"]["canal"], "statut")
        self.assertEqual(charge["signature"]["id"], "ZZ")


class TestLaPrevisualisation(unittest.TestCase):

    def test_elle_partage_les_predicats_du_rejeu(self):
        """Sinon l'ecran de confirmation annonce des refus qui n'auront pas lieu."""
        trace = lire(MEGATRACE)
        apercu = P.previsualiser(trace)
        self.assertEqual(apercu.gestes, len(trace.gestes))
        self.assertEqual(apercu.confort,
                         len([g for g in trace.gestes if not g.significatif]))
        self.assertEqual(apercu.reprises_possibles, len(apercu.codes))


if __name__ == "__main__":
    unittest.main()
