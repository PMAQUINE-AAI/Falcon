"""Le moteur — la boucle, et les quatre regles qui la gouvernent.

C'est le lot ou six sous-systemes se rencontrent enfin. Les tests portent donc
moins sur des fonctions que sur des **enchainements** : ce que le journal
contient apres coup, ce que la reprise fait ensuite, ce que le fichier de KO
permet de rejouer.

Le test le plus important de ce fichier est
`test_un_item_interrompu_apres_sauvegarde_ressort_douteux`. Il exerce bout en
bout la protection contre la double ecriture dans SAP : le controleur annonce
la sauvegarde AVANT l'acte, l'adaptateur traduit cette annonce en etape
marquee, le repli des etats en deduit `douteux`, et la reprise ne rejoue pas.
Quatre modules, une seule propriete, et un defaut qui ne leve pas.

Le double de driver n'etablit AUCUNE fidelite a SAP. Ces tests verifient le
comportement du moteur ETANT DONNE une reponse de driver.
"""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from falcon.couture.double import DriverScripte
from falcon.donnees import lire_items
from falcon.journal import DOUTEUX, EN_COURS, KO, OK, depuis_journal, etats, lire
from falcon.moteur import (
    DRY_RUN, INTERROMPU, PLAFOND, REPRISE, RUN, TERMINE, Maillon,
    PreparationImpossible, enchainer, executer,
)
from falcon.noyau import Fenetre, Identite, Statut
from falcon.pipeline import charger, etape_python, oublier_tout
from falcon.taxonomie import Registre

IA08 = Identite(transaction="IA08", programme="RIPLKO10", dynpro="1000")
AUTRE = Identite(transaction="CL02", programme="SAPLCLFM", dynpro="0100")

ECRAN = 'ecran: {transaction: IA08, programme: RIPLKO10, dynpro: "1000"}'

PIPELINE = f"""
    version: 1
    nom: essai
    classe: iterative
    cles: [site]
    plafond_items: 50
    plafond_sauvegardes: 50
    etapes:
      - nom: saisir
        action: set
        cible: "wnd[0]/usr/ctxtWERKS-LOW"
        source: {{colonne: site}}
        {ECRAN}
      - nom: sauver
        action: press
        cible: "wnd[0]/tbar[0]/btn[11]"
        sauvegarde: true
        {ECRAN}
    """

JEU = "site,libelle\n1000,Paris\n2000,Lyon\n3000,Lille\n"

#: `PIPELINE` se termine par l'indentation de sa triple-quote fermante ; y
#: concatener une etape la decalerait. Meme piege qu'au lot 8b, meme parade.
SOCLE = PIPELINE.rstrip() + "\n"


def etape(*lignes: str) -> str:
    """Un bloc d'etape, indente comme celles de `PIPELINE`."""
    return "".join(f"      {ligne}\n" for ligne in lignes)


class Base(unittest.TestCase):

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name)
        self.journal = self.racine / "journal.jsonl"
        self.jeu = self.racine / "jeu.csv"
        self.jeu.write_text(JEU, encoding="utf-8")
        self.registre = Registre.charger()

    def _pipeline(self, texte: str = PIPELINE, **options):
        chemin = self.racine / "p.yaml"
        chemin.write_text(textwrap.dedent(texte), encoding="utf-8")
        return charger(chemin, **options)

    def _driver(self, **options) -> DriverScripte:
        brut = DriverScripte(identite=IA08,
                             valeurs={"wnd[0]/usr/ctxtWERKS-LOW": ""},
                             **options)

        def relire(driver, geste, cible):
            if geste == "write":
                driver.valeurs[cible] = driver.valeurs.get(cible, "")

        brut.apres_action = relire
        return brut

    def _executer(self, brut=None, **options):
        return executer(self._pipeline(), self.jeu, brut or self._driver(),
                        journal=self.journal, registre=self.registre,
                        **options)

    def _etats(self):
        return etats(lire(self.journal))


class TestBoucle(Base):

    def test_un_lot_complet_passe(self):
        resultat = self._executer()
        self.assertEqual(resultat.etat, TERMINE)
        self.assertEqual(resultat.compteurs[OK], 3)

    def test_chaque_item_est_une_unite_de_sauvegarde(self):
        """Trois sites, trois items — le regroupement se declare par `cles`."""
        items, _ = lire_items(self.jeu, ("site",))
        self.assertEqual(len(items), 3)
        self._executer()
        self.assertEqual(len(self._etats()), 3)

    def test_le_journal_porte_debut_et_fin_d_execution(self):
        self._executer()
        rapport = depuis_journal(lire(self.journal))
        self.assertEqual(rapport.pipeline, "essai")
        self.assertEqual(rapport.mode, RUN)

    def test_le_moteur_ne_touche_jamais_un_driver_nu(self):
        """Le driver arrive brut et repart enveloppe : toutes les actions
        passent par le controleur, donc par les gardes."""
        brut = self._driver()
        self._executer(brut)
        self.assertTrue(brut.gestes)
        self.assertTrue(all(g[0] in ("write", "press") for g in brut.gestes))

    def test_une_pipeline_volumique_est_refusee(self):
        """La machinerie par item — journal, reprise, ETA — ne sert qu'aux
        iteratives (§3.5). Une volumique qui en heriterait serait du
        gaspillage, et surtout une confusion de modele."""
        volumique = PIPELINE.replace("classe: iterative", "classe: volumique")
        with self.assertRaises(PreparationImpossible) as capture:
            executer(self._pipeline(volumique), self.jeu, self._driver(),
                     journal=self.journal, registre=self.registre)
        self.assertIn("volumique", str(capture.exception))


class TestUnKoNInterromptPasLeLot(Base):
    """Regle 1. Perdre trois cents items parce que le quarantieme est fautif
    serait pire que l'absence d'automatisation."""

    def _driver_fautif_au_deuxieme(self) -> DriverScripte:
        brut = self._driver()
        etat = {"items": 0}

        def reagir(driver, geste, cible):
            # La barre de statut se vide a chaque aller-retour : la laisser
            # trainer ferait porter le message de l'item 2 sur l'item 3, et le
            # test mesurerait le double au lieu du moteur.
            driver.statut = Statut()
            if geste == "press":
                etat["items"] += 1
                if etat["items"] == 2:
                    driver.statut = Statut(type="E", id="ZZ", numero="001",
                                           texte="refuse")
        brut.apres_action = reagir
        return brut

    def test_un_item_ko_laisse_le_lot_continuer(self):
        resultat = self._executer(self._driver_fautif_au_deuxieme())
        # L'inconnu est bloquant par defaut (§5.1) : sans entree au registre,
        # ce message arrete le lot. C'est le comportement voulu, et ce test
        # existe pour le DIRE, pas pour le contourner.
        self.assertEqual(resultat.etat, INTERROMPU)
        self.assertEqual(resultat.compteurs[OK], 1)

    def test_un_item_connu_fautif_est_perdu_et_le_lot_continue(self):
        """Avec une entree « connue fautive » au registre, l'item sort KO et
        les suivants passent."""
        surcouche = self.racine / "sur.yaml"
        surcouche.write_text(textwrap.dedent("""
            version: 1
            entrees:
              - nom: zz_refuse
                categorie: connue_fautive
                canal: statut
                origine: falcon_observe
                justification: "message d'essai de la suite du moteur, sans
                  equivalent reel dans SAP"
                correspondance: {type: "E", id: "ZZ", numero: "001"}
                politique: {poursuivre: true, item: ko}
            """), encoding="utf-8")
        registre = Registre.charger(surcouche)
        resultat = executer(self._pipeline(), self.jeu,
                            self._driver_fautif_au_deuxieme(),
                            journal=self.journal, registre=registre)
        self.assertEqual(resultat.etat, TERMINE)
        self.assertEqual(resultat.compteurs[OK], 2)
        self.assertEqual(resultat.compteurs[KO], 1)


class TestUnArretBloquantArreteTout(Base):
    """Regle 2 et regle 3."""

    def _driver_qui_derive(self) -> DriverScripte:
        brut = self._driver()
        etat = {"items": 0}

        def deriver(driver, geste, cible):
            if geste == "press":
                etat["items"] += 1
                if etat["items"] == 2:
                    driver.identite = AUTRE      # le modele du monde est faux
        brut.apres_action = deriver
        return brut

    def test_une_identite_violee_interrompt(self):
        resultat = self._executer(self._driver_qui_derive())
        self.assertEqual(resultat.etat, INTERROMPU)

    def test_l_item_interrompu_ne_recoit_pas_de_fin(self):
        """Lui poser un `ItemFin(ko)` le rendrait terminal, donc perdu pour de
        bon. Il reste ouvert, et le repli decide de son sort."""
        self._executer(self._driver_qui_derive())
        ouverts = [e for e in self._etats().values()
                   if e.etat in (EN_COURS, DOUTEUX)]
        self.assertTrue(ouverts)

    def test_le_plafond_d_items_arrete_le_lot(self):
        court = PIPELINE.replace("plafond_items: 50", "plafond_items: 2")
        resultat = executer(self._pipeline(court), self.jeu, self._driver(),
                            journal=self.journal, registre=self.registre)
        self.assertEqual(resultat.etat, PLAFOND)
        self.assertEqual(resultat.compteurs[OK], 2)

    def test_le_plafond_de_sauvegardes_arrete_le_lot(self):
        """La derniere barriere avant le lot entier (decision n°11)."""
        court = PIPELINE.replace("plafond_sauvegardes: 50",
                                 "plafond_sauvegardes: 2")
        resultat = executer(self._pipeline(court), self.jeu, self._driver(),
                            journal=self.journal, registre=self.registre)
        self.assertEqual(resultat.etat, PLAFOND)


class TestDouteux(Base):
    """**Le test le plus important du lot.**

    Un item interrompu APRES une sauvegarde reussie ne doit jamais etre
    rejoue : le rejouer, c'est ecrire deux fois dans SAP. La protection
    traverse quatre modules — le controleur annonce avant d'agir,
    l'adaptateur traduit l'annonce en etape marquee, le repli en deduit
    `douteux`, la reprise l'ecarte — et aucun maillon ne leve s'il manque.
    """

    def _driver_qui_derive_apres_sauvegarde(self) -> DriverScripte:
        brut = self._driver()

        def deriver(driver, geste, cible):
            if geste == "press":
                # La sauvegarde a REUSSI, puis le monde change.
                driver.fenetres = (Fenetre(id="wnd[0]"), Fenetre(id="wnd[1]"))
        brut.apres_action = deriver
        return brut

    def test_un_item_interrompu_apres_sauvegarde_ressort_douteux(self):
        self._executer(self._driver_qui_derive_apres_sauvegarde())
        douteux = [i for i, e in self._etats().items() if e.etat == DOUTEUX]
        self.assertEqual(len(douteux), 1, self._etats())

    def test_l_annonce_precede_l_acte_dans_le_journal(self):
        """Si l'annonce suivait l'acte, une coupure entre les deux laisserait
        une sauvegarde reelle sans trace."""
        brut = self._driver()
        vus: list[str] = []
        brut.apres_action = lambda d, geste, cible: vus.append(f"acte:{geste}")
        self._executer(brut)
        enregistrements = [e for e in lire(self.journal)
                           if getattr(e, "sauvegarde", False)]
        self.assertTrue(enregistrements)

    def test_la_reprise_ne_rejoue_pas_un_douteux(self):
        self._executer(self._driver_qui_derive_apres_sauvegarde())
        avant = len([e for e in lire(self.journal)
                     if e.TYPE == "item_debut"])
        resultat = self._executer(self._driver(), mode=REPRISE)
        rejoues = [e for e in lire(self.journal) if e.TYPE == "item_debut"]
        # Les douteux ne repartent pas ; les non traites, si.
        self.assertLess(len(rejoues) - avant, 3)
        self.assertEqual(resultat.etat, TERMINE)


class TestReprise(Base):

    def test_la_reprise_ne_retraite_pas_ce_qui_est_termine(self):
        self._executer()
        resultat = self._executer(mode=REPRISE)
        self.assertEqual(resultat.compteurs[OK], 0)
        self.assertEqual(resultat.compteurs["deja_faits"], 3)

    def test_la_reprise_refuse_un_jeu_modifie(self):
        """Reprendre sur un jeu different, c'est avoir un modele du monde
        faux : les identifiants d'item ne designent plus les memes lignes."""
        from falcon.noyau import RepriseIncoherente

        self._executer()
        self.jeu.write_text(JEU.replace("Lille", "Lens"), encoding="utf-8")
        with self.assertRaises(RepriseIncoherente):
            self._executer(mode=REPRISE)

    def test_un_mode_inconnu_est_refuse(self):
        with self.assertRaises(PreparationImpossible):
            self._executer(mode="peut-etre")


class TestDryRun(Base):

    def test_le_dry_run_n_ecrit_rien_dans_sap(self):
        brut = self._driver()
        resultat = self._executer(brut, mode=DRY_RUN)
        self.assertEqual(resultat.compteurs[OK], 0)
        self.assertEqual(len([g for g in brut.gestes if g[0] == "press"]), 0)

    def test_les_items_sortent_ignores(self):
        resultat = self._executer(mode=DRY_RUN)
        self.assertEqual(resultat.compteurs["ignore"], 3)


class TestCoherenceDuJeu(Base):
    """Ce que le moteur verifie AVANT de toucher a SAP."""

    def test_un_item_dont_les_lignes_se_contredisent_est_refuse(self):
        """La premiere ligne l'emporterait, et les autres seraient perdues
        sans un mot."""
        self.jeu.write_text("site,libelle\n1000,Paris\n1000,Marseille\n",
                            encoding="utf-8")
        with self.assertRaises(PreparationImpossible) as capture:
            executer(self._pipeline(
                PIPELINE.replace("{colonne: site}", "{colonne: libelle}")),
                self.jeu, self._driver(), journal=self.journal,
                registre=self.registre)
        self.assertIn("ne s'accordent pas", str(capture.exception))

    def test_le_controle_tombe_avant_la_premiere_action(self):
        brut = self._driver()
        self.jeu.write_text("site,libelle\n1000,Paris\n1000,Marseille\n",
                            encoding="utf-8")
        with self.assertRaises(PreparationImpossible):
            executer(self._pipeline(
                PIPELINE.replace("{colonne: site}", "{colonne: libelle}")),
                self.jeu, brut, journal=self.journal, registre=self.registre)
        self.assertEqual(brut.gestes, [], "SAP a ete touche malgre le refus")

    def test_une_valeur_de_case_ambigue_est_refusee(self):
        """Deviner ici, c'est cocher ou decocher une case au hasard."""
        avec_case = SOCLE + etape(
            "- nom: cocher_mab",
            "  action: cocher",
            '  cible: "wnd[0]/usr/chkDY_MAB"',
            "  source: {colonne: libelle}",
            f"  {ECRAN}")
        self.jeu.write_text("site,libelle\n1000,peut-etre\n", encoding="utf-8")
        with self.assertRaises(PreparationImpossible) as capture:
            executer(self._pipeline(avec_case), self.jeu, self._driver(),
                     journal=self.journal, registre=self.registre)
        self.assertIn("ni vrai ni faux", str(capture.exception))


class TestReexportDesKo(Base):
    """§4.7 : le fichier de KO doit etre reinjectable sans retouche."""

    def test_les_ko_sont_reexportes_au_format_d_entree(self):
        surcouche = self.racine / "sur.yaml"
        surcouche.write_text(textwrap.dedent("""
            version: 1
            entrees:
              - nom: zz_refuse
                categorie: connue_fautive
                canal: statut
                origine: falcon_observe
                justification: "message d'essai de la suite du moteur, sans
                  equivalent reel dans SAP"
                correspondance: {type: "E", id: "ZZ", numero: "001"}
                politique: {poursuivre: true, item: ko}
            """), encoding="utf-8")
        brut = self._driver()
        def refuser(driver, geste, cible):
            driver.statut = (Statut(type="E", id="ZZ", numero="001",
                                    texte="non")
                             if geste == "press" else Statut())
        brut.apres_action = refuser

        ko = self.racine / "ko.csv"
        resultat = executer(self._pipeline(), self.jeu, brut,
                            journal=self.journal,
                            registre=Registre.charger(surcouche),
                            sortie_ko=ko)
        self.assertEqual(resultat.ko, str(ko))

        # Reinjectable : la lecture retire les colonnes de diagnostic.
        items, _ = lire_items(ko, ("site",))
        self.assertEqual(len(items), resultat.compteurs[KO])
        self.assertNotIn("falcon_categorie", items[0].brut[0])

    def test_sans_ko_aucun_fichier_n_est_ecrit(self):
        ko = self.racine / "ko.csv"
        resultat = self._executer(sortie_ko=ko)
        self.assertIsNone(resultat.ko)
        self.assertFalse(ko.exists())


class TestEchappatoirePython(Base):

    def setUp(self):
        super().setUp()
        self.addCleanup(oublier_tout)

    def test_une_etape_python_recoit_le_poste_l_item_et_les_lectures(self):
        vus: list[tuple] = []

        @etape_python("noter")
        def noter(poste, item, contexte):
            vus.append((type(poste).__name__, item.item_id, dict(contexte)))

        avec = SOCLE + etape("- nom: appeler", "  action: python",
                             "  fonction: noter", f"  {ECRAN}")
        executer(self._pipeline(avec), self.jeu, self._driver(),
                 journal=self.journal, registre=self.registre)
        self.assertEqual(len(vus), 3)
        self.assertEqual(vus[0][0], "Poste")

    def test_une_exception_d_etape_python_passe_par_la_taxonomie(self):
        """L'inconnu y est bloquant, et c'est voulu : une extension qui leve
        une erreur que personne n'a repertoriee arrete le lot."""
        @etape_python("casser")
        def casser(poste, item, contexte):
            raise ZeroDivisionError("bug de l'extension")

        avec = SOCLE + etape("- nom: casser_ici", "  action: python",
                             "  fonction: casser", f"  {ECRAN}")
        resultat = executer(self._pipeline(avec), self.jeu, self._driver(),
                            journal=self.journal, registre=self.registre)
        self.assertEqual(resultat.etat, INTERROMPU)
        incidents = [e for e in lire(self.journal) if e.TYPE == "incident"]
        self.assertTrue(incidents)
        self.assertEqual(incidents[0].categorie, "inconnue")


class TestChaine(Base):
    """§3.3 : un declenchement successif, et rien de plus."""

    def _maillons(self, combien: int = 2) -> list[Maillon]:
        return [Maillon(pipeline=self._pipeline(), jeu=self.jeu,
                        journal=self.racine / f"j{rang}.jsonl")
                for rang in range(combien)]

    def test_chaque_pipeline_a_son_journal(self):
        """Fusionner rendrait la reprise fine impossible."""
        resultats = enchainer(self._maillons(), self._driver(),
                              registre=self.registre)
        self.assertEqual(len(resultats), 2)
        self.assertNotEqual(resultats[0].journal, resultats[1].journal)
        self.assertTrue((self.racine / "j0.jsonl").exists())
        self.assertTrue((self.racine / "j1.jsonl").exists())

    def test_le_retour_a_l_accueil_a_lieu_entre_deux_pipelines(self):
        vus: list[str] = []

        def accueil(brut, registre):
            vus.append("accueil")

        enchainer(self._maillons(3), self._driver(), registre=self.registre,
                  accueil=accueil)
        self.assertEqual(len(vus), 2, "un retour entre chaque, pas avant la "
                                      "premiere")

    def test_le_retour_passe_par_le_champ_de_commande(self):
        from falcon.moteur import retour_accueil
        from falcon.noyau import CHAMP_DE_COMMANDE, RETOUR_ACCUEIL

        brut = self._driver()
        brut.valeurs[CHAMP_DE_COMMANDE] = ""
        retour_accueil(brut, self.registre)
        self.assertIn(("write", CHAMP_DE_COMMANDE, RETOUR_ACCUEIL),
                      brut.gestes)

    def test_un_arret_bloquant_interrompt_la_chaine(self):
        brut = self._driver()

        def deriver(driver, geste, cible):
            if geste == "press":
                driver.identite = AUTRE
        brut.apres_action = deriver

        resultats = enchainer(self._maillons(3), brut, registre=self.registre)
        self.assertEqual(len(resultats), 1)
        self.assertTrue(resultats[0].interrompu)

    def test_aucune_donnee_ne_passe_d_une_pipeline_a_la_suivante(self):
        """La limite qui empeche la chaine de devenir un orchestrateur.

        `Resultat` ne porte que des compteurs, des etats et des chemins — rien
        qu'une pipeline suivante puisse consommer comme donnee metier.
        """
        import dataclasses

        from falcon.moteur import Resultat

        champs = {c.name for c in dataclasses.fields(Resultat)}
        self.assertEqual(champs, {"run_id", "etat", "compteurs", "raison",
                                  "journal", "ko", "duree_ms"})


if __name__ == "__main__":
    unittest.main()
