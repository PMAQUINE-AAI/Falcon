"""Le catalogue mis a plat pour un tableur.

Deux proprietes portent cette suite.

**Le contenu suffit a rendre un selecteur intelligent.** Un ecran SAP porte des
dizaines de controles ; les proposer en vrac n'aide personne. Trois colonnes
font le tri : `modifiable` (n'offrir que l'ecrivable pour un `set`), `type`
(distinguer un bouton d'une case), `texte` (le libelle, seul nom qu'un humain
reconnait). Sans lui, un selecteur affiche `wnd[0]/usr/ctxtWERKS-LOW` et laisse
deviner qu'il s'agit de la division.

**Le fichier arrive lisible a l'autre bout.** Il est destine a un Excel
francais : sans BOM il lit en ANSI et massacre les accents, sans `;` il pose
tout en colonne A. Un export correct qu'Excel affiche de travers ne sert a
rien.

Les identifiants et libelles de cette suite sont **synthetiques**. Ils
exercent la mise a plat ; ils n'etablissent aucune fidelite a SAP.
"""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
from pathlib import Path

from falcon.catalogue import ESQUISSE, Depot, variante_de
from falcon.commandes.dictionnaire import (
    COLONNES, DIALECTE_TABLEUR, exporter, recenser, rendre,
)
from falcon.noyau import Champ, Ecran, Identite

IA08 = Identite(transaction="IA08", programme="RIPLKO10", dynpro="1000")


def _ecran() -> Ecran:
    return Ecran(
        identite=IA08,
        titre="Gammes de maintenance : selection",
        champs=(
            Champ(id="wnd[0]/usr/ctxtWERKS-LOW", type="GuiCTextField",
                  nom="WERKS-LOW", texte="Division",
                  infobulle="Division (WERKS)"),
            Champ(id="wnd[0]/usr/chkDY_MAB", type="GuiCheckBox",
                  nom="DY_MAB", texte="Gammes equipement"),
            Champ(id="wnd[0]/tbar[1]/btn[8]", type="GuiButton",
                  texte="Executer", infobulle="Executer (F8)"),
            Champ(id="wnd[0]/usr/txtCREE", type="GuiTextField",
                  texte="Cree par", modifiable=False),
        ))


class Base(unittest.TestCase):

    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.racine = Path(dossier.name) / "catalogue"
        self.depot = Depot(self.racine)
        self.depot.enregistrer(variante_de(_ecran()))

    def _lignes(self) -> list[dict[str, str]]:
        return recenser(self.depot)

    def _par_id(self) -> dict[str, dict[str, str]]:
        return {ligne["cible"]: ligne for ligne in self._lignes()}


class TestCeQuiRendLeSelecteurIntelligent(Base):

    def test_un_champ_fige_se_distingue_d_un_champ_ecrivable(self):
        """La colonne qui compte le plus : un selecteur ne doit pas offrir un
        champ en lecture seule pour un `set`. L'ecriture echouerait — ou pire,
        passerait sans effet."""
        par_id = self._par_id()
        self.assertEqual(par_id["wnd[0]/usr/ctxtWERKS-LOW"]["modifiable"], "oui")
        self.assertEqual(par_id["wnd[0]/usr/txtCREE"]["modifiable"], "non")

    def test_oui_et_non_plutot_que_VRAI_et_FAUX(self):
        """`VRAI`/`FAUX` d'Excel est localise : il ne se relit pas d'une locale
        a l'autre. « oui »/« non » traverse."""
        for ligne in self._lignes():
            with self.subTest(champ=ligne["cible"]):
                self.assertIn(ligne["modifiable"], ("oui", "non"))

    def test_le_type_distingue_un_bouton_d_une_case_d_un_champ(self):
        """C'est ce qui permet de n'offrir que les boutons pour un `press` et
        que les cases pour un `cocher`."""
        par_id = self._par_id()
        self.assertEqual(par_id["wnd[0]/tbar[1]/btn[8]"]["type"], "GuiButton")
        self.assertEqual(par_id["wnd[0]/usr/chkDY_MAB"]["type"], "GuiCheckBox")

    def test_le_libelle_affiche_a_l_ecran_est_present(self):
        """Sans lui, le selecteur affiche `wnd[0]/usr/ctxtWERKS-LOW` et laisse
        l'utilisateur deviner qu'il s'agit de la division."""
        par_id = self._par_id()
        self.assertEqual(par_id["wnd[0]/usr/ctxtWERKS-LOW"]["texte"], "Division")
        self.assertEqual(par_id["wnd[0]/tbar[1]/btn[8]"]["texte"], "Executer")

    def test_l_ecran_est_identifie_pour_chaque_champ(self):
        """Une etape doit declarer SON ECRAN autant que son champ. Le triplet
        voyage donc sur chaque ligne, pour qu'un tableur regroupe dessus."""
        for ligne in self._lignes():
            with self.subTest(champ=ligne["cible"]):
                self.assertEqual(ligne["transaction"], "IA08")
                self.assertEqual(ligne["programme"], "RIPLKO10")
                self.assertEqual(ligne["dynpro"], "1000")
                self.assertTrue(ligne["empreinte"])

    def test_le_triplet_tient_dans_UNE_cellule_collable(self):
        """`ecran` et `cible` sont les deux seules colonnes qu'on copie : elles
        portent le nom de la colonne de destination, pas celui du concept.

        Et le triplet tient dans une seule cellule a dessein. Une colonne
        `dynpro` seule est nue — Excel y recadre « 0100 » en « 100 », a la
        saisie comme a l'enregistrement. Noye dans un jeton qui porte des
        lettres et des `::`, le dynpro n'est plus recadrable.
        """
        for ligne in self._lignes():
            with self.subTest(champ=ligne["cible"]):
                self.assertEqual(ligne["ecran"], "IA08::RIPLKO10::1000")
        self.assertEqual(COLONNES[:2], ("ecran", "cible"))

    def test_le_separateur_du_triplet_n_est_ni_barre_ni_pipe(self):
        """Pas `/` : les noms de programme SAP en contiennent (`/BCP/SAPLXXX`).
        Pas `|` : c'est l'un des delimiteurs que `donnees.lire` renifle, et un
        fichier qui en serait plein pourrait etre lu comme delimite par lui."""
        from falcon.commandes.dictionnaire import SEPARATEUR_ECRAN

        self.assertNotIn("/", SEPARATEUR_ECRAN)
        self.assertNotIn("|", SEPARATEUR_ECRAN)

    def test_un_dynpro_a_zero_de_tete_survit_dans_le_jeton(self):
        self.depot.enregistrer(variante_de(Ecran(
            identite=Identite(transaction="CL02", programme="SAPLCLFM",
                              dynpro="0100"),
            champs=(Champ(id="wnd[0]/usr/ctxtA"),))))
        jetons = {l["ecran"] for l in recenser(self.depot)}
        self.assertIn("CL02::SAPLCLFM::0100", jetons)

    def test_une_esquisse_est_signalee_comme_telle(self):
        """Une esquisse vient d'une trace : elle porte les champs TOUCHES, pas
        les champs presents, et son `type` est vide. Un selecteur doit pouvoir
        l'ecarter — d'ou la colonne, plutot qu'un filtre decide a sa place."""
        self.depot.mettre_en_quarantaine(
            variante_de(_ecran(), source=ESQUISSE))
        quarantaine = recenser(Depot(self.depot.quarantaine))
        self.assertTrue(quarantaine)
        for ligne in quarantaine:
            self.assertEqual(ligne["releve"], "esquisse")
        for ligne in self._lignes():
            self.assertEqual(ligne["releve"], "observee")


class TestLeFichierArriveLisible(Base):

    def test_le_BOM_est_present(self):
        """Sans lui, Excel lit le fichier en ANSI et massacre les accents des
        libelles."""
        octets = rendre(self._lignes())
        self.assertTrue(octets.startswith(b"\xef\xbb\xbf"))

    def test_le_delimiteur_est_le_point_virgule(self):
        """Sans lui, un Excel francais pose tout en colonne A."""
        self.assertEqual(DIALECTE_TABLEUR.delimiteur, ";")
        texte = rendre(self._lignes()).decode("utf-8-sig")
        self.assertIn(";", texte.splitlines()[0])

    def test_l_entete_porte_toutes_les_colonnes_dans_l_ordre(self):
        texte = rendre(self._lignes()).decode("utf-8-sig")
        self.assertEqual(texte.splitlines()[0].split(";"), list(COLONNES))

    def test_un_libelle_accentue_survit_a_l_aller_retour(self):
        """Le vrai test du BOM et de l'encodage : ce qu'on relit est ce qu'on
        a ecrit."""
        self.depot.enregistrer(variante_de(Ecran(
            identite=Identite(transaction="CL02", programme="SAPLCLFM",
                              dynpro="0100"),
            champs=(Champ(id="wnd[0]/usr/ctxtX", texte="Créé le — n°1"),))))
        texte = rendre(recenser(self.depot)).decode("utf-8-sig")
        lignes = list(csv.DictReader(io.StringIO(texte), delimiter=";"))
        libelles = [l["texte"] for l in lignes]
        self.assertIn("Créé le — n°1", libelles)

    def test_un_libelle_portant_le_delimiteur_est_protege(self):
        """Un titre d'ecran contient «  : » et parfois un « ; ». Sans quoting,
        la ligne se decalerait d'une colonne — et le decalage est silencieux."""
        self.depot.enregistrer(variante_de(Ecran(
            identite=Identite(transaction="ZZ01", programme="Z", dynpro="0001"),
            titre="Selection ; suite",
            champs=(Champ(id="wnd[0]/usr/ctxtY", texte="a;b"),))))
        texte = rendre(recenser(self.depot)).decode("utf-8-sig")
        lignes = list(csv.DictReader(io.StringIO(texte), delimiter=";"))
        vise = [l for l in lignes if l["cible"] == "wnd[0]/usr/ctxtY"]
        self.assertEqual(len(vise), 1)
        self.assertEqual(vise[0]["texte"], "a;b")
        self.assertEqual(vise[0]["titre"], "Selection ; suite")

    def test_le_dynpro_reste_du_texte(self):
        """« 0100 » n'est pas « 100 ». Un tableur recadre ce qui ressemble a un
        nombre ; l'export ne doit pas l'y aider en le rendant nu."""
        self.depot.enregistrer(variante_de(Ecran(
            identite=Identite(transaction="CL02", programme="SAPLCLFM",
                              dynpro="0100"),
            champs=(Champ(id="wnd[0]/usr/ctxtZ"),))))
        par_dynpro = {l["dynpro"] for l in recenser(self.depot)}
        self.assertIn("0100", par_dynpro)


class TestExport(Base):

    def test_le_fichier_s_ecrit_et_se_relit(self):
        cible = self.racine.parent / "dico.csv"
        chemin = exporter(self.depot, cible)
        self.assertEqual(chemin, cible)
        texte = cible.read_bytes().decode("utf-8-sig")
        lignes = list(csv.DictReader(io.StringIO(texte), delimiter=";"))
        self.assertEqual(len(lignes), 4)

    def test_l_ordre_est_stable_d_un_export_a_l_autre(self):
        """Un dictionnaire qui change d'ordre a chaque export est indiffable,
        et le tableur qui s'y raccroche par rang casse."""
        self.assertEqual(rendre(recenser(self.depot)),
                         rendre(recenser(self.depot)))

    def test_un_catalogue_vide_ne_produit_aucune_ligne(self):
        vide = Depot(self.racine.parent / "vide")
        self.assertEqual(recenser(vide), [])


class TestLaCommande(Base):

    def _lancer(self, *arguments: str) -> int:
        from falcon.commandes.principal import main

        return main(["dictionnaire", *arguments])

    def test_la_commande_ecrit_le_fichier(self):
        cible = self.racine.parent / "dico.csv"
        self.assertEqual(self._lancer(str(self.racine), "-o", str(cible)), 0)
        self.assertTrue(cible.exists())

    def test_un_dossier_inexistant_sort_en_erreur(self):
        self.assertEqual(self._lancer("/rien/du/tout"), 1)

    def test_un_catalogue_vide_le_dit_plutot_que_d_ecrire_un_fichier_vide(self):
        """Un fichier vide serait pris pour un catalogue vide, plutot que pour
        un dossier qui n'est pas celui qu'on croit."""
        vide = self.racine.parent / "vide"
        vide.mkdir()
        cible = self.racine.parent / "dico.csv"
        self.assertEqual(self._lancer(str(vide), "-o", str(cible)), 1)
        self.assertFalse(cible.exists())


if __name__ == "__main__":
    unittest.main()
