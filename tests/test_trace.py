"""Parseur de trace VBScript : ce que le recorder ecrit, et rien d'autre.

Ce lot est reste bloque tant qu'aucun enregistrement reel n'etait disponible,
parce que l'archive documentait `.press()` la ou le recorder ecrit `.press`.
La trace `megatrace_2026-09.vbs` a tranche ; ces tests l'epinglent, et
epinglent surtout les trois pieges qu'elle a reveles :

- le meme objet ALV recoit `selectedRows = "0"` (une CHAINE) et
  `currentCellRow = 4` (un ENTIER). Normaliser les deux produirait un rejeu
  que SAP refuse ;
- `doubleClickCurrentCell` agit sur la cellule courante, pas sur la selection.
  Omettre `currentCellRow` double-cliquerait la premiere ligne, en silence ;
- vider `ENAME-LOW` elargit la recherche de variantes a tous les auteurs. Le
  premier bloc de la trace ne le fait pas : ses resultats ne sont pas
  comparables aux quatre autres.

Les trois defauts ne levent pas. C'est pour ca qu'ils sont ici.
"""

from __future__ import annotations

import dataclasses
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import yaml

from falcon.trace import (
    AFFECTATION, APPEL, APPEL_ARGUMENT, CONFORT, VERBES, Geste, Inventaire,
    Trace, TraceInvalide, decoder, decouper, inventorier, lire, litteral,
    rendre_litteral,
)
from falcon.trace.inventaire import main, rapport

RACINE = Path(__file__).resolve().parent.parent
TRACES = RACINE / "tests" / "fixtures" / "traces"
MEGATRACE = TRACES / "megatrace_2026-09.vbs"

PROLOGUE = (
    'If Not IsObject(application) Then\r\n'
    '   Set SapGuiAuto  = GetObject("SAPGUI")\r\n'
    '   Set application = SapGuiAuto.GetScriptingEngine\r\n'
    'End If\r\n'
)


def vbs(*lignes: str, prologue: bool = False, bom: bool = True) -> bytes:
    """Une trace synthetique, dans l'encodage du recorder."""
    texte = (PROLOGUE if prologue else "") + "".join(l + "\r\n" for l in lignes)
    return (b"\xff\xfe" if bom else b"") + texte.encode("utf-16-le")


def geste(source: bytes) -> Geste:
    trace = lire(source)
    assert len(trace.gestes) == 1, trace.gestes
    return trace.gestes[0]


class TestDecodage(unittest.TestCase):
    """L'encodage est detecte puis inscrit, jamais devine en silence."""

    def test_utf16le_avec_bom(self):
        trace = lire(vbs('session.findById("wnd[0]").maximize'))
        self.assertEqual((trace.encodage, trace.bom), ("utf-16-le", True))

    def test_utf16be_avec_bom(self):
        octets = b"\xfe\xff" + 'session.findById("wnd[0]").maximize\r\n'.encode("utf-16-be")
        self.assertEqual(lire(octets).encodage, "utf-16-be")

    def test_utf8_avec_bom(self):
        octets = b"\xef\xbb\xbf" + b'session.findById("wnd[0]").maximize\r\n'
        trace = lire(octets)
        self.assertEqual((trace.encodage, trace.bom), ("utf-8", True))

    def test_utf8_sans_bom_est_dit_suppose(self):
        trace = lire(b'session.findById("wnd[0]").maximize\n')
        self.assertEqual((trace.encodage, trace.bom), ("utf-8", False))

    def test_un_contenu_indecodable_leve_en_nommant_l_encodage(self):
        with self.assertRaises(TraceInvalide) as capture:
            lire(b"\xff\xfe\x41")           # UTF-16 sur un nombre impair d'octets
        self.assertIn("utf-16-le", str(capture.exception))

    def test_un_bom_utf32_est_refuse_par_son_nom(self):
        """`FF FE 00 00` commence comme un BOM UTF-16LE.

        Lu comme tel, le fichier se decode sans lever en semant des caracteres
        nuls : plus rien ne s'apparie, et le rapport accuse la trace au lieu de
        l'encodage.
        """
        octets = b"\xff\xfe\x00\x00" + "abc\r\n".encode("utf-32-le")[4:]
        with self.assertRaises(TraceInvalide) as capture:
            lire(octets)
        self.assertIn("utf-32-le", str(capture.exception))

    def test_l_encodage_figure_dans_le_rapport(self):
        """Le jour ou une lecture ira de travers, il faudra savoir sous quel
        encodage elle a ete faite."""
        self.assertIn("utf-16-le", rapport(inventorier(MEGATRACE)))


class TestDecoupage(unittest.TestCase):

    def test_crlf(self):
        self.assertEqual(decouper("a\r\nb\r\n"), (["a", "b"], "\r\n"))

    def test_lf(self):
        self.assertEqual(decouper("a\nb\n"), (["a", "b"], "\n"))

    def test_mixte_est_signale(self):
        self.assertEqual(decouper("a\r\nb\n")[1], "mixte")

    def test_derniere_ligne_sans_fin_de_ligne(self):
        self.assertEqual(decouper("a\r\nb")[0], ["a", "b"])

    def test_pas_de_coupure_sur_un_separateur_unicode(self):
        """`splitlines` coupe sur U+2028, qui peut se trouver DANS une chaine.

        Une ligne coupee en deux au milieu d'un litteral produirait deux
        moities, dont aucune ne s'apparie — ou pire, dont l'une s'apparie.
        """
        self.assertEqual(decouper("a b\r\n")[0], ["a b"])


class TestFormes(unittest.TestCase):
    """Trois formes, relevees sur la trace reelle. Une quatrieme fait echouer."""

    def test_appel_nu(self):
        g = geste(vbs('session.findById("wnd[0]/tbar[0]/btn[11]").press'))
        self.assertEqual((g.forme, g.verbe, g.valeur), (APPEL, "press", None))

    def test_affectation(self):
        g = geste(vbs('session.findById("wnd[1]/usr/txtV-LOW").text = "*BCP*"'))
        self.assertEqual((g.forme, g.verbe, g.valeur),
                         (AFFECTATION, "text", "*BCP*"))

    def test_appel_a_argument_separe_par_une_espace(self):
        g = geste(vbs('session.findById("wnd[0]").sendVKey 0'))
        self.assertEqual((g.forme, g.verbe, g.valeur),
                         (APPEL_ARGUMENT, "sendVKey", 0))

    def test_la_forme_a_parentheses_est_refusee(self):
        """L'archive documentait `.press()`. Le recorder ecrit `.press`.

        On refuse plutot que de tolerer les deux : accepter une forme que le
        recorder ne produit pas, c'est accepter un fichier retouche a la main
        sans le savoir.
        """
        with self.assertRaises(TraceInvalide) as capture:
            lire(vbs('session.findById("wnd[0]/tbar[0]/btn[11]").press()'))
        self.assertIn("trois formes connues", str(capture.exception))

    def test_une_forme_inconnue_fait_echouer_la_lecture(self):
        """Controle negatif : une ligne non comprise ne doit pas etre ignoree."""
        with self.assertRaises(TraceInvalide) as capture:
            lire(vbs('session.findById("wnd[0]").press',
                     'MsgBox "on continue ?"'))
        message = str(capture.exception)
        self.assertIn("ligne 2", message)
        self.assertIn('MsgBox "on continue ?"', message)   # verbatim

    def test_le_prologue_est_appariE_pas_ignorE(self):
        trace = lire(vbs('session.findById("wnd[0]").maximize', prologue=True))
        self.assertEqual(trace.prologue, (1, 2, 3, 4))
        self.assertEqual(len(trace.gestes), 1)

    def test_une_ligne_etrangere_au_prologue_ne_s_y_fond_pas(self):
        with self.assertRaises(TraceInvalide):
            lire(vbs("If Not IsObject(application) Then",
                     "   Shell \"cmd.exe\"",
                     "End If"))

    def test_lignes_vides_et_commentaires_sont_comptes(self):
        trace = lire(vbs('session.findById("wnd[0]").press', "", "' un mot"))
        self.assertEqual((trace.vides, trace.commentaires), ((2,), (3,)))


class TestLitteraux(unittest.TestCase):

    def test_chaine(self):
        self.assertEqual(litteral('"*BCP*"'), "*BCP*")

    def test_chaine_vide(self):
        self.assertEqual(litteral('""'), "")

    def test_entier(self):
        self.assertEqual(litteral("4"), 4)

    def test_booleen_minuscule(self):
        self.assertEqual((litteral("true"), litteral("false")), (True, False))

    def test_booleen_capitalise_est_refuse(self):
        """Valide en VBScript, jamais observe. On l'apprendra d'une trace."""
        with self.assertRaises(TraceInvalide):
            litteral("True")

    def test_guillemet_echappe(self):
        self.assertEqual(litteral('"a""b"'), 'a"b')

    def test_guillemets_desequilibres_refuses(self):
        with self.assertRaises(TraceInvalide):
            litteral('"a"b"')

    def test_un_booleen_ne_se_rend_pas_comme_un_entier(self):
        """En Python, `True` EST un entier : l'ordre des tests de type compte."""
        self.assertEqual(rendre_litteral(True), "true")

    def test_le_meme_objet_alv_recoit_une_chaine_et_un_entier(self):
        """Le piege central du typage, releve sur la trace.

        `selectedRows` est une chaine, `currentCellRow` un entier, sur le meme
        shell. Normaliser les deux en entier produirait un rejeu refuse.
        """
        alv = 'wnd[1]/usr/cntlALV_CONTAINER_1/shellcont/shell'
        trace = lire(vbs(f'session.findById("{alv}").currentCellRow = 4',
                         f'session.findById("{alv}").selectedRows = "4"'))
        rang, selection = trace.gestes
        self.assertIsInstance(rang.valeur, int)
        self.assertIsInstance(selection.valeur, str)


class TestVerbes(unittest.TestCase):

    def test_un_verbe_connu_sous_une_autre_forme_est_refuse(self):
        """Aucun verbe n'apparait sous deux formes dans une trace.

        `text` employe comme appel nu ne serait pas la meme chose ; laisser
        passer la confusion rejouerait autre chose que l'enregistrement.
        """
        with self.assertRaises(TraceInvalide) as capture:
            lire(vbs('session.findById("wnd[1]/usr/txtV-LOW").text'))
        self.assertIn("deux formes", str(capture.exception))

    def test_un_verbe_inconnu_se_lit_et_se_signale(self):
        """La forme est comprise, le verbe non. Refuser la trace entiere
        empecherait `inventaire` de nommer ce qu'il faut apprendre."""
        g = geste(vbs('session.findById("wnd[0]/usr/x").pressF4'))
        self.assertFalse(g.connu)

    def test_un_verbe_inconnu_est_significatif_par_defaut(self):
        """Le presumer anodin serait la supposition que ce projet refuse."""
        self.assertTrue(geste(vbs('session.findById("wnd[0]/usr/x").pressF4'))
                        .significatif)

    def test_les_gestes_de_confort_sont_conserves_mais_marques(self):
        trace = lire(MEGATRACE)
        confort = [g for g in trace.gestes if g.verbe in CONFORT]
        self.assertTrue(confort)
        self.assertTrue(all(not g.significatif for g in confort))
        self.assertEqual(len(trace.significatifs),
                         len(trace.gestes) - len(confort))

    def test_current_cell_row_n_est_pas_un_geste_de_confort(self):
        """Regression de conception, pas de code.

        `doubleClickCurrentCell` agit sur la cellule COURANTE. Ranger
        `currentCellRow` parmi les gestes de confort — ce que j'avais fait —
        aurait produit des brouillons qui double-cliquent la premiere ligne.
        """
        self.assertNotIn("currentCellRow", CONFORT)

    def test_la_fenetre_se_deduit_de_la_cible(self):
        g = geste(vbs('session.findById("wnd[1]/tbar[0]/btn[8]").press'))
        self.assertEqual(g.fenetre, "wnd[1]")

    def test_une_cible_hors_fenetre_est_refusee(self):
        """Sinon `fenetre` vaudrait la chaine vide, qui ne ressemble a aucune
        fenetre declaree — et la garde des fenetres imprevues comparerait ca."""
        with self.assertRaises(TraceInvalide) as capture:
            lire(vbs('session.findById("usr/txtV-LOW").text = "x"'))
        self.assertIn("wnd[N]", str(capture.exception))

    def test_aucun_geste_de_la_trace_observee_n_est_sans_fenetre(self):
        self.assertTrue(all(g.fenetre for g in lire(MEGATRACE).gestes))


class TestAllerRetour(unittest.TestCase):
    """Le seul controle serieux : reconstruire la trace depuis le modele."""

    def test_chaque_geste_se_rend_a_l_identique(self):
        for g in lire(MEGATRACE).gestes:
            with self.subTest(ligne=g.ligne):
                self.assertEqual(g.rendu(), g.texte_source)

    def test_le_fichier_entier_se_reconstruit_octet_pour_octet(self):
        octets = MEGATRACE.read_bytes()
        texte, encodage, bom = decoder(octets)
        lignes, style = decouper(texte)

        trace = lire(MEGATRACE)
        for g in trace.gestes:
            lignes[g.ligne - 1] = g.rendu()

        refait = "".join(l + style for l in lignes).encode(encodage)
        if bom:
            refait = b"\xff\xfe" + refait
        self.assertEqual(refait, octets)

    def test_un_guillemet_echappe_survit_a_l_aller_retour(self):
        ligne = 'session.findById("wnd[0]/usr/txtX").text = "a""b"'
        g = geste(vbs(ligne))
        self.assertEqual(g.valeur, 'a"b')
        self.assertEqual(g.rendu(), ligne)

    def test_le_retrait_est_conserve(self):
        ligne = '   session.findById("wnd[0]").press'
        self.assertEqual(geste(vbs(ligne)).rendu(), ligne)


class TestTraceObservee(unittest.TestCase):
    """Ce que l'enregistrement reel etablit. Modifier ces chiffres, c'est
    affirmer que la trace dit autre chose — a verifier sur le fichier."""

    def setUp(self):
        self.trace = lire(MEGATRACE)

    def test_toutes_les_lignes_sont_appariees(self):
        t = self.trace
        self.assertEqual(t.lignes, 104)
        self.assertEqual(len(t.gestes) + len(t.prologue), t.lignes)
        self.assertEqual((len(t.gestes), len(t.prologue)), (90, 14))

    def test_aucun_verbe_hors_du_releve(self):
        self.assertEqual(self.trace.verbes_inconnus, ())

    def test_le_releve_de_verbes_ne_contient_pas_de_verbe_jamais_vu(self):
        """Detecteur de derive dans l'autre sens : la table `VERBES` ne doit
        pas accumuler des verbes conjectures."""
        vus = {v for v, _ in self.trace.par_verbe()}
        self.assertEqual(set(VERBES), vus)

    def test_deux_fenetres_seulement(self):
        self.assertEqual(self.trace.fenetres(), ("wnd[0]", "wnd[1]"))

    def test_le_motif_de_chargement_de_variante_revient_cinq_fois(self):
        charges = [g for g in self.trace.gestes
                   if g.verbe == "doubleClickCurrentCell"]
        self.assertEqual(len(charges), 5)

    def test_current_cell_row_precede_toute_selection_d_index_non_nul(self):
        """Le piege, sous forme executable.

        Des que l'index vise n'est pas 0, la trace positionne `currentCellRow`
        juste avant `selectedRows` — et jamais pour l'index 0.
        """
        gestes = self.trace.gestes
        for rang, g in enumerate(gestes):
            if g.verbe != "selectedRows":
                continue
            precedent = gestes[rang - 1]
            with self.subTest(ligne=g.ligne, index=g.valeur):
                if g.valeur == "0":
                    self.assertNotEqual(precedent.verbe, "currentCellRow")
                else:
                    self.assertEqual(precedent.verbe, "currentCellRow")
                    self.assertEqual(precedent.valeur, int(g.valeur))

    def test_la_selection_alv_se_fait_par_index(self):
        """Ce qu'un brouillon ne devra PAS rejouer tel quel.

        L'index depend du contenu de la base au moment de l'enregistrement.
        Le rejouer selectionnerait la mauvaise variante des que la liste
        change — sans lever. Le lot suivant doit marquer ces gestes non
        rejouables ; ce test dit combien il y en a a traiter.
        """
        index = [g.valeur for g in self.trace.gestes
                 if g.verbe == "selectedRows"]
        self.assertEqual(index, ["0", "0", "0", "4", "2"])

    def test_le_createur_est_vide_dans_quatre_blocs_sur_cinq(self):
        """Vider `ENAME-LOW` elargit la recherche a toutes les variantes.

        Le premier bloc ne le fait pas : ses resultats ne sont pas comparables
        aux quatre autres. C'est une difference de perimetre metier, invisible
        a la lecture rapide de la trace.
        """
        vidages = [g for g in self.trace.gestes
                   if g.cible.endswith("txtENAME-LOW") and g.valeur == ""]
        self.assertEqual(len(vidages), 4)

    def test_les_cases_de_selection_sont_repositionnees_apres_le_chargement(self):
        """Le piege des cases remanentes, observe plutot que deduit : charger
        une variante ecrase les cases `DY_*` deja posees."""
        gestes = self.trace.gestes
        charges = [r for r, g in enumerate(gestes)
                   if g.verbe == "doubleClickCurrentCell"]
        apres = [g for r in charges for g in gestes[r + 1:r + 2]
                 if "chkDY_" in g.cible]
        self.assertTrue(apres, "aucune case repositionnee juste apres un "
                               "chargement de variante")

    def test_le_caractere_non_ascii_du_terrain_est_conserve(self):
        """Une faute de frappe AZERTY, corrigee a la ligne suivante. Elle
        reste : une trace observee n'est pas retouchee."""
        codes = [g.valeur for g in self.trace.gestes if g.cible.endswith("okcd")]
        self.assertIn("/nIW2ç", codes)


class TestInventaire(unittest.TestCase):
    """La lecture tolerante rend un type qui ne peut pas etre rejoue."""

    def test_l_inventaire_ne_porte_aucun_geste(self):
        champs = " ".join(str(c.type) for c in dataclasses.fields(Inventaire))
        self.assertNotIn("Geste", champs)

    def test_les_lignes_non_appariees_sont_rendues_verbatim(self):
        inventaire = inventorier(vbs('session.findById("wnd[0]").press',
                                     'MsgBox "on continue ?"'))
        self.assertEqual(inventaire.inconnues, ((2, 'MsgBox "on continue ?"'),))
        self.assertFalse(inventaire.complet)

    def test_l_inventaire_survit_a_ce_qui_fait_echouer_la_lecture(self):
        octets = vbs('session.findById("wnd[0]").press', "MsgBox 1")
        with self.assertRaises(TraceInvalide):
            lire(octets)
        self.assertEqual(inventorier(octets).gestes, 1)

    def test_un_verbe_inconnu_est_nomme_dans_le_rapport(self):
        inventaire = inventorier(vbs('session.findById("wnd[0]/usr/x").pressF4'))
        self.assertEqual(inventaire.verbes_inconnus, ("pressF4",))
        self.assertIn("INCONNU", rapport(inventaire))

    def test_la_trace_observee_est_complete(self):
        self.assertTrue(inventorier(MEGATRACE).complet)

    def test_le_rapport_compte_gestes_prologue_et_verbes(self):
        texte = rapport(inventorier(MEGATRACE))
        self.assertIn("gestes         90", texte)
        self.assertIn("prologue       14", texte)
        self.assertIn("press", texte)


class TestCommande(unittest.TestCase):

    @staticmethod
    def _lancer(*arguments: str) -> tuple[int, str]:
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            code = main(list(arguments))
        return code, sortie.getvalue()

    def test_l_aide_repond(self):
        code, texte = self._lancer("--aide")
        self.assertEqual(code, 0)
        self.assertIn("Usage", texte)

    def test_sans_argument_l_aide_sort_en_erreur(self):
        self.assertEqual(self._lancer()[0], 2)

    def test_une_trace_complete_sort_a_zero(self):
        self.assertEqual(self._lancer(str(MEGATRACE))[0], 0)

    def test_une_trace_incomplete_sort_a_un(self):
        chemin = TRACES / "_incomplete.vbs"
        chemin.write_bytes(vbs("MsgBox 1"))
        self.addCleanup(chemin.unlink)
        code, texte = self._lancer(str(chemin))
        self.assertEqual(code, 1)
        self.assertIn("MsgBox 1", texte)

    def test_une_trace_absente_leve_en_nommant_le_chemin(self):
        with self.assertRaises(TraceInvalide) as capture:
            lire(TRACES / "jamais_vue.vbs")
        self.assertIn("jamais_vue.vbs", str(capture.exception))


class TestProvenance(unittest.TestCase):
    """Savoir en permanence quelle part du parseur est validee contre du reel."""

    def setUp(self):
        contenu = yaml.safe_load(
            (TRACES / "provenance.yaml").read_text(encoding="utf-8"))
        self.assertEqual(contenu.get("version"), 1)
        self.declarees = contenu["traces"]

    def test_toute_trace_du_depot_a_sa_provenance(self):
        presentes = {c.name for c in TRACES.glob("*.vbs")}
        self.assertEqual(presentes, set(self.declarees),
                         "une trace sans provenance declaree, ou l'inverse")

    def test_chaque_provenance_est_complete(self):
        for nom, fiche in self.declarees.items():
            with self.subTest(trace=nom):
                self.assertIn(fiche.get("source"), ("observee", "synthetique"))
                self.assertTrue(fiche.get("date"))
                self.assertTrue(fiche.get("origine"))

    def test_le_parseur_est_valide_contre_au_moins_une_trace_observee(self):
        decompte = {"observee": 0, "synthetique": 0}
        for fiche in self.declarees.values():
            decompte[fiche["source"]] += 1
        print(f"\n  traces : {decompte['observee']} observee(s), "
              f"{decompte['synthetique']} synthetique(s)")
        self.assertGreater(decompte["observee"], 0,
                           "aucune trace observee : le parseur ne serait "
                           "valide que contre ses propres hypotheses")

    def test_les_traces_observees_se_lisent_entierement(self):
        for nom, fiche in self.declarees.items():
            if fiche["source"] != "observee":
                continue
            with self.subTest(trace=nom):
                self.assertTrue(inventorier(TRACES / nom).complet)


if __name__ == "__main__":
    unittest.main()
