"""Supervision : progression, ETA glissant, et silence hors terminal.

Trois proprietes, et la premiere conditionne les deux autres.

**Le rendu est une fonction pure.** Les tests comparent des chaines. Aucun ne
capture de terminal, aucun ne desassemble de sequence ANSI — parce qu'il n'y
en a pas : le redessin tient a un retour chariot, qui marche dans `cmd`, dans
PowerShell et a travers RDP.

**Muet hors terminal.** Un lot dont la sortie part dans un journal de CI n'a
rien a gagner a recevoir une ligne par item.

**L'ETA se tait tant qu'il n'est pas fiable.** Un ETA faux est pire qu'un ETA
absent : on planifie dessus.
"""

from __future__ import annotations

import io
import unittest

from falcon.supervision import (
    ENCODAGE_MINIMAL, Estimation, Progres, Rapporteur, Suivi, bilan, duree,
    encodable, ligne,
)


def _progres(rang: int = 1, total: int = 10, duree_ms: int = 1000,
             **compteurs) -> Progres:
    return Progres(item=f"site{rang}", rang=rang, total=total,
                   duree_ms=duree_ms,
                   compteurs=compteurs or {"ok": rang, "ko": 0})


class TestSuivi(unittest.TestCase):

    def test_la_moyenne_glisse_sur_la_fenetre(self):
        """Une moyenne generale se degraderait en permanence sur un lot dont
        le regime change ; la fenetre suit le regime courant."""
        suivi = Suivi(fenetre=3)
        for duree_ms in (10_000, 10_000, 10_000):
            suivi.ajouter(_progres(duree_ms=duree_ms))
        estimation = suivi.ajouter(_progres(duree_ms=1_000))
        # Les trois dernieres : 10s, 10s, 1s. La premiere est sortie.
        self.assertEqual(estimation.moyenne_ms, 7_000)

    def test_l_eta_est_la_moyenne_fois_les_restants(self):
        suivi = Suivi()
        for _ in range(3):
            suivi.ajouter(_progres(duree_ms=2_000))
        estimation = suivi.ajouter(_progres(rang=6, total=10, duree_ms=2_000))
        self.assertEqual(estimation.eta_s, 8)        # 4 restants x 2 s

    def test_une_duree_nulle_n_entre_pas_dans_la_moyenne(self):
        """Un item ignore en dry-run tirerait la moyenne vers le bas et
        promettrait un lot deux fois plus rapide qu'il ne sera."""
        suivi = Suivi()
        suivi.ajouter(_progres(duree_ms=2_000))
        estimation = suivi.ajouter(_progres(duree_ms=0))
        self.assertEqual(estimation.moyenne_ms, 2_000)
        self.assertEqual(estimation.echantillon, 1)

    def test_sans_aucune_duree_l_estimation_est_vide(self):
        self.assertEqual(Suivi().ajouter(_progres(duree_ms=0)), Estimation())

    def test_une_estimation_sur_deux_items_n_est_pas_fiable(self):
        suivi = Suivi()
        suivi.ajouter(_progres(duree_ms=1_000))
        self.assertFalse(suivi.ajouter(_progres(duree_ms=1_000)).fiable)
        self.assertTrue(suivi.ajouter(_progres(duree_ms=1_000)).fiable)

    def test_une_fenetre_nulle_est_refusee(self):
        with self.assertRaises(ValueError):
            Suivi(fenetre=0)

    def test_les_restants_ne_deviennent_jamais_negatifs(self):
        self.assertEqual(_progres(rang=12, total=10).restants, 0)


class TestRendu(unittest.TestCase):

    def test_la_ligne_porte_le_rang_les_compteurs_et_l_item(self):
        texte = ligne(_progres(rang=3, total=50, ok=2, ko=1),
                      Estimation(moyenne_ms=1400, eta_s=65, echantillon=5))
        for attendu in ("3/50", "ok 2", "ko 1", "1.4 s/item", "00:01:05",
                        "site3"):
            with self.subTest(attendu=attendu):
                self.assertIn(attendu, texte)

    def test_l_eta_se_tait_tant_qu_il_n_est_pas_fiable(self):
        """Un ETA faux est pire qu'un ETA absent : on planifie dessus."""
        texte = ligne(_progres(), Estimation(moyenne_ms=1000, eta_s=99,
                                             echantillon=1))
        self.assertIn("--:--:--", texte)
        self.assertNotIn("00:01:39", texte)

    def test_le_rang_est_aligne_sur_la_largeur_du_total(self):
        """Sinon la ligne saute d'un caractere au centieme item, et l'oeil
        perd le fil."""
        self.assertIn("[  7/100]", ligne(_progres(rang=7, total=100),
                                         Estimation()))

    def test_aucune_sequence_ansi_dans_le_rendu(self):
        texte = ligne(_progres(), Estimation(moyenne_ms=1, eta_s=1,
                                             echantillon=9))
        self.assertNotIn("\x1b", texte)

    def test_le_rendu_s_encode_en_cp1252(self):
        """La machine ou ce reporting servira est une machine Windows. Un
        decor qui ne s'y encode pas tue le programme qu'il decore."""
        self.assertTrue(encodable(ligne(_progres(), Estimation(
            moyenne_ms=1400, eta_s=65, echantillon=5))))
        self.assertTrue(encodable(bilan(_progres(), Estimation())))

    def test_la_duree_se_lit_d_un_coup_d_oeil(self):
        self.assertEqual(duree(0), "00:00:00")
        self.assertEqual(duree(3_725), "01:02:05")
        self.assertEqual(duree(-5), "00:00:00")

    def test_le_bilan_ne_porte_pas_d_eta(self):
        """Il n'y a plus rien a estimer."""
        texte = bilan(_progres(ok=8, ko=2), Estimation(moyenne_ms=1400,
                                                       eta_s=99,
                                                       echantillon=9))
        self.assertNotIn("ETA", texte)
        self.assertIn("10 item(s)", texte)
        self.assertIn("ok 8", texte)

    def test_le_bilan_ne_compte_pas_les_deja_faits_comme_traites(self):
        """Une reprise qui annoncerait « 50 items traites » alors qu'elle en a
        repris trois mentirait sur ce qu'elle vient de faire."""
        progres = Progres(item="x", rang=3, total=3,
                          compteurs={"ok": 3, "deja_faits": 47})
        texte = bilan(progres, Estimation())
        self.assertIn("3 item(s)", texte)
        self.assertIn("deja faits 47", texte)


class TestSilenceHorsTerminal(unittest.TestCase):

    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    def test_un_flux_non_interactif_ne_recoit_rien(self):
        flux = io.StringIO()
        rapporteur = Rapporteur(flux)
        rapporteur(_progres())
        rapporteur.clore()
        self.assertFalse(rapporteur.actif)
        self.assertEqual(flux.getvalue(), "")

    def test_un_terminal_recoit_la_progression(self):
        flux = self.Terminal()
        rapporteur = Rapporteur(flux)
        rapporteur(_progres())
        self.assertTrue(rapporteur.actif)
        self.assertIn("site1", flux.getvalue())

    def test_forcer_parle_meme_hors_terminal(self):
        """Pour un lot long lance dans un `nohup`. Choix explicite, pas
        defaut."""
        flux = io.StringIO()
        rapporteur = Rapporteur(flux, forcer=True)
        rapporteur(_progres())
        self.assertIn("site1", flux.getvalue())

    def test_un_flux_qui_ne_sait_pas_dire_n_est_pas_interactif(self):
        class Muet:
            def isatty(self):
                raise OSError("flux ferme")

            def write(self, texte):
                raise AssertionError("rien ne doit etre ecrit")

            def flush(self):
                pass

        rapporteur = Rapporteur(Muet())          # type: ignore[arg-type]
        rapporteur(_progres())                   # ne doit pas lever
        self.assertFalse(rapporteur.actif)

    def test_le_redessin_utilise_un_retour_chariot_pas_de_l_ansi(self):
        flux = self.Terminal()
        rapporteur = Rapporteur(flux)
        rapporteur(_progres(rang=1))
        rapporteur(_progres(rang=2))
        sortie = flux.getvalue()
        self.assertEqual(sortie.count("\r"), 2)
        self.assertNotIn("\x1b", sortie)

    def test_une_ligne_plus_courte_efface_la_precedente(self):
        """Sans remplissage, la queue de la ligne longue resterait a l'ecran
        et afficherait un etat qui n'existe plus."""
        flux = self.Terminal()
        rapporteur = Rapporteur(flux)
        rapporteur(Progres(item="un_identifiant_tres_long", rang=1, total=9,
                           duree_ms=1000, compteurs={"ok": 1}))
        avant = len(flux.getvalue())
        rapporteur(Progres(item="x", rang=2, total=9, duree_ms=1000,
                           compteurs={"ok": 2}))
        ajoute = flux.getvalue()[avant:]
        self.assertTrue(ajoute.endswith(" "), "pas de remplissage")

    def test_clore_pose_le_bilan_et_passe_a_la_ligne(self):
        flux = self.Terminal()
        with Rapporteur(flux) as rapporteur:
            rapporteur(_progres(rang=2, total=2, ok=2))
        self.assertIn("item(s) traite(s)", flux.getvalue())
        self.assertTrue(flux.getvalue().endswith("\n"))

    def test_clore_sans_progression_n_ecrit_rien(self):
        flux = self.Terminal()
        Rapporteur(flux).clore()
        self.assertEqual(flux.getvalue(), "")


class TestFrontiere(unittest.TestCase):

    def test_le_moteur_ne_connait_pas_le_rendu(self):
        """Il emet des faits. Savoir s'il parle a un terminal ne le regarde
        pas — et l'y faire penser rendrait la boucle intestable sans tty."""
        import ast
        from pathlib import Path

        racine = Path(__file__).resolve().parent.parent / "falcon" / "moteur"
        for module in sorted(racine.glob("*.py")):
            arbre = ast.parse(module.read_text(encoding="utf-8"), str(module))
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.ImportFrom) and noeud.module:
                    with self.subTest(module=module.name, ligne=noeud.lineno):
                        self.assertNotIn("supervision.terminal", noeud.module)

    def test_le_moteur_emet_bien_des_progres(self):
        from falcon.moteur.boucle import executer
        import inspect

        annotation = inspect.signature(executer).parameters["observateur"]
        self.assertIn("Progres", str(annotation.annotation))


if __name__ == "__main__":
    unittest.main()
