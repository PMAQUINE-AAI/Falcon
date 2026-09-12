"""La toile : ce qu'un terminal sait faire, et ce qu'on a le droit d'y peindre.

**Cette suite est 100 % injectee, et c'est une exigence, pas une elegance.**
Aucun test ne lit le terminal de qui la lance : `sonder` prend un `Systeme`
obligatoire, le banc ci-dessous en fabrique neuf, et
`test_la_suite_ne_touche_jamais_le_vrai_terminal` verifie sur l'arbre
syntaxique que ce fichier n'a meme pas de quoi le faire.

Le motif n'est pas la purete. Cette suite est celle que `outils/neutraliser.py`
relance pour la neuvieme garde, et son `main()` exige que chaque suite citee
PASSE avant neutralisation. Une suite sensible au terminal ferait donc rougir
la verification des huit gardes SAP un jour ou quelqu'un lance l'outil depuis
un tube — pour un motif sans le moindre rapport avec SAP.

Le banc reproduit neuf terminaux que la CI ne verra jamais. Il prouve que la
sonde est coherente avec NOTRE modele de Windows ; il ne prouve rien sur
Windows, et `falcon/toile/__init__.py` dit ou s'arrete cette reserve.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from falcon.toile import (
    ALERTE, COULEUR, DANGER, ENTETE, INCONNUE, LARGEUR_PLAFOND,
    LARGEUR_SANS_MESURE, LIGNE, MARQUE, MESUREE, NEUTRE, NU, SEPARATEUR,
    STD_SORTIE, TONS, VIDE, Bloc, Capacites, Fragment, Gabarit, PeintreColore,
    PeintreNu, RenduRefuse, Systeme, colonnes, couper, couper_chemin,
    gabarit_pour, peintre_pour, rendre_capacites, rendre_sonde, retirer,
    sonder, texte_nu,
)
from falcon.toile import peintre as module_peintre
from falcon.toile import sequences

ENCODAGE_MINIMAL = "cp1252"

#: Ce que ce fichier n'a pas le droit d'importer.
#:
#: Sans `os`, `sys` ni `ctypes`, il n'a litteralement aucun moyen d'atteindre un
#: terminal : la garantie devient structurelle au lieu d'etre une promesse.
MODULES_HORS_DE_PORTEE = frozenset({"os", "sys", "ctypes", "shutil",
                                    "subprocess", "termios", "curses"})


def _console(modes, *, pose=True, sourde=False):
    """Un kernel32 de papier : un mode par handle, et le journal des appels.

    `sourde` est le cas qui compte : `SetConsoleMode` rend vrai et le bit ne
    prend pas. C'est exactement ce contre quoi la relecture existe, et c'est
    aussi le seul comportement de Windows que la documentation ne promet pas
    de ne pas avoir.
    """

    class ConsoleDePapier:
        def __init__(self) -> None:
            self.modes = dict(modes)
            self.journal: list[tuple] = []

        def lire_mode(self, handle: int) -> int | None:
            self.journal.append(("lire", handle))
            return self.modes.get(handle)

        def poser_mode(self, handle: int, mode: int) -> bool:
            self.journal.append(("poser", handle, mode))
            if not pose or handle not in self.modes:
                return False
            if not sourde:
                self.modes[handle] = mode
            return True

    return ConsoleDePapier()


def _taille_qui_leve(erreur):
    def mesurer(_descripteur):
        raise erreur
    return mesurer


# ---------------------------------------------------------------------------
# Le banc : neuf terminaux, aucun reel
# ---------------------------------------------------------------------------

def windows_terminal() -> Systeme:
    """Windows 11 / Windows Terminal : l'hote a deja pose le bit VT."""
    return Systeme(
        plateforme="win32", variables={"TERM": ""}, nom_du_flux="stdout",
        fileno=1, isatty=True, encodage="utf-8",
        console=_console({STD_SORTIE: 0x0007}), taille=lambda _: (137, 44))


def windows_10() -> Systeme:
    """Windows 10 1511 / cmd.exe : mode 3, le bit se pose et se relit."""
    return Systeme(
        plateforme="win32", variables={}, nom_du_flux="stdout",
        fileno=1, isatty=True, encodage="cp1252",
        console=_console({STD_SORTIE: 0x0003}), taille=lambda _: (80, 25))


def windows_8_1() -> Systeme:
    """Windows 8.1 : `SetConsoleMode` refuse le bit inconnu (erreur 87)."""
    return Systeme(
        plateforme="win32", variables={}, nom_du_flux="stdout",
        fileno=1, isatty=True, encodage="cp1252",
        console=_console({STD_SORTIE: 0x0003}, pose=False),
        taille=lambda _: (80, 25))


def windows_menteur() -> Systeme:
    """`SetConsoleMode` rend vrai, et le bit n'est pas la a la relecture."""
    return Systeme(
        plateforme="win32", variables={}, nom_du_flux="stdout",
        fileno=1, isatty=True, encodage="cp1252",
        console=_console({STD_SORTIE: 0x0003}, sourde=True),
        taille=lambda _: (80, 25))


def windows_redirige() -> Systeme:
    """Sortie dans un fichier : `fileno()` reste 1, et l'ioctl echoue.

    C'est le cas qui distingue ce module de `shutil` : elle rendrait (80, 24)
    sans un mot, la sonde rend `None` et nomme l'`OSError`.
    """
    return Systeme(
        plateforme="win32", variables={}, nom_du_flux="stdout",
        fileno=1, isatty=False, encodage="cp1252", console=_console({}),
        taille=_taille_qui_leve(
            OSError(25, "Inappropriate ioctl for device")))


def windows_flux_tiers() -> Systeme:
    """Un flux ouvert a la main : descripteur >= 3, pas de handle standard."""
    return Systeme(
        plateforme="win32", variables={}, nom_du_flux="stdout",
        fileno=3, isatty=False, encodage="cp1252", console=_console({}),
        taille=_taille_qui_leve(ValueError("bad file descriptor")))


def pty_muet() -> Systeme:
    """Un pty sans TIOCSWINSZ : (0, 0) rendu SANS lever."""
    return Systeme(
        plateforme="linux", variables={"TERM": "xterm"}, nom_du_flux="stdout",
        fileno=1, isatty=True, encodage="utf-8", taille=lambda _: (0, 0))


def linux_dumb() -> Systeme:
    """Le terminal se declare lui-meme sans capacite."""
    return Systeme(
        plateforme="linux", variables={"TERM": "dumb"}, nom_du_flux="stdout",
        fileno=1, isatty=True, encodage="utf-8", taille=lambda _: (100, 40))


def linux_sans_couleur() -> Systeme:
    """NO_COLOR sur un vrai terminal : ANSI reste vrai, la couleur non."""
    return Systeme(
        plateforme="linux",
        variables={"TERM": "xterm-256color", "NO_COLOR": "1"},
        nom_du_flux="stderr", fileno=2, isatty=True, encodage="utf-8",
        taille=lambda _: (100, 40))


#: Le banc porte des FABRIQUES et non des `Systeme` tout faits.
#:
#: Les consoles de papier tiennent le journal de ce qu'on leur a demande, et
#: c'est precisement ce qu'un des tests verifie. Partager un `Systeme` entre
#: deux tests ferait dependre ce journal de l'ordre d'execution — un resultat
#: plausible et faux, dans la suite meme qui existe pour les traquer.
BANC = {
    "windows terminal": windows_terminal,
    "windows 10": windows_10,
    "windows 8.1": windows_8_1,
    "windows menteur": windows_menteur,
    "windows redirige": windows_redirige,
    "flux tiers": windows_flux_tiers,
    "pty muet": pty_muet,
    "linux dumb": linux_dumb,
    "no_color": linux_sans_couleur,
}

PROUVE = Capacites(flux="stdout", interactif=True, colonnes=100, lignes=40,
                   source_taille=MESUREE, ansi=True, couleur=True,
                   motifs=("bit VT pose, relu, mode restaure",))

#: Des blocs de toutes les formes, dont un marque : sans ton, un peintre colore
#: ne poserait rien et l'invariant serait vrai pour la mauvaise raison.
BLOCS = (
    Bloc((Fragment("FALCON — navigateur de catalogue"),), forme=ENTETE),
    Bloc((Fragment("AGIT DANS SAP", ton=DANGER),)),
    Bloc((Fragment("1 fichier n'a pas pu etre lu", ton=ALERTE),
          Fragment(" et il n'entre dans aucun compte"))),
    Bloc(forme=SEPARATEUR),
    Bloc(forme=VIDE),
    Bloc((Fragment("un identifiant tres long " * 8),), marge=4),
)


class TestLaSuiteEstInjectee(unittest.TestCase):
    """Le pre-controle de `neutraliser.py` depend de cette propriete."""

    def test_la_suite_ne_touche_jamais_le_vrai_terminal(self):
        """Ni par la fonction qui mesure, ni par les modules qui pourraient.

        Le nom interdit est assemble en deux morceaux : ecrit d'une piece, il
        se trouverait lui-meme et le test serait toujours rouge. On regarde les
        IDENTIFIANTS de l'arbre, jamais les chaines — une docstring a le droit
        de nommer ce qu'elle interdit, et c'est meme ce qu'on lui demande.
        """
        interdit = "systeme" + "_reel"
        source = Path(__file__).read_text(encoding="utf-8")
        arbre = ast.parse(source, __file__)

        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Name):
                nom, ligne = noeud.id, noeud.lineno
            elif isinstance(noeud, ast.Attribute):
                nom, ligne = noeud.attr, noeud.lineno
            elif isinstance(noeud, ast.alias):
                nom, ligne = noeud.name.split(".")[0], 0
            else:
                continue
            with self.subTest(identifiant=nom, ligne=ligne):
                self.assertNotEqual(
                    nom, interdit,
                    "cette suite cite la seule fonction du paquet qui touche "
                    "le monde : elle lirait alors le terminal de qui la lance")

        for noeud in ast.walk(arbre):
            if not isinstance(noeud, (ast.Import, ast.ImportFrom)):
                continue
            noms = ([a.name for a in noeud.names]
                    if isinstance(noeud, ast.Import)
                    else [noeud.module or ""])
            for nom in noms:
                with self.subTest(module=nom, ligne=noeud.lineno):
                    self.assertNotIn(
                        nom.split(".")[0], MODULES_HORS_DE_PORTEE,
                        f"ligne {noeud.lineno} : {nom!r} donnerait a cette "
                        f"suite les moyens d'atteindre un vrai terminal")


class TestLeBancDeNeufSystemes(unittest.TestCase):
    """Neuf terminaux que la CI ne verra jamais, et ce que la sonde en dit."""

    def test_windows_terminal_dont_le_bit_VT_est_deja_pose(self):
        systeme = windows_terminal()
        capacites = sonder(systeme)
        self.assertTrue(capacites.ansi)
        self.assertEqual(capacites.niveau, COULEUR)
        self.assertIn("bit VT deja pose par l'hote", capacites.motifs)
        # L'hote l'avait pose : on ne le repose pas, et on ne le retire pas.
        self.assertEqual(systeme.console.journal, [("lire", STD_SORTIE)])

    def test_windows_10_pose_le_bit_le_relit_et_restaure_le_mode(self):
        """Les trois temps, dans l'ordre, et le quatrieme qui rend le terrain.

        Une sonde est une mesure : elle repond « ce terminal SAIT », elle ne
        decide pas qu'il le fera. Laisser le mode modifie derriere elle
        changerait le comportement d'un programme qui n'a demande qu'un
        diagnostic.
        """
        systeme = windows_10()
        capacites = sonder(systeme)
        self.assertTrue(capacites.ansi)
        self.assertEqual(capacites.niveau, COULEUR)
        self.assertEqual(
            systeme.console.journal,
            [("lire", STD_SORTIE), ("poser", STD_SORTIE, 0x0007),
             ("lire", STD_SORTIE), ("poser", STD_SORTIE, 0x0003)])
        self.assertEqual(systeme.console.modes[STD_SORTIE], 0x0003)

    def test_windows_8_1_dont_SetConsoleMode_refuse(self):
        capacites = sonder(windows_8_1())
        self.assertFalse(capacites.ansi)
        self.assertEqual(capacites.niveau, NU)
        self.assertTrue(any("SetConsoleMode" in m for m in capacites.motifs))
        # La taille, elle, reste mesuree : refuser VT n'aveugle pas la sonde.
        self.assertEqual((capacites.colonnes, capacites.lignes), (80, 25))
        self.assertEqual(capacites.source_taille, MESUREE)

    def test_une_console_qui_ment_sur_SetConsoleMode_est_refusee(self):
        """CONTROLE NEGATIF : retirer la relecture fait passer ce cas a vrai.

        `SetConsoleMode` a rendu vrai et le bit n'est pas la. Sans le troisieme
        temps, la sonde annoncerait « ANSI oui » a une console qui affichera la
        sequence en toutes lettres — un resultat plausible et faux, produit par
        un appel systeme qui a repondu « d'accord ».
        """
        capacites = sonder(windows_menteur())
        self.assertFalse(capacites.ansi)
        self.assertEqual(capacites.niveau, NU)
        self.assertTrue(any("ment" in m for m in capacites.motifs),
                        capacites.motifs)

    def test_une_sortie_redirigee_vers_un_fichier_ne_sait_pas_sa_taille(self):
        capacites = sonder(windows_redirige())
        self.assertIsNone(capacites.colonnes)
        self.assertIsNone(capacites.lignes)
        self.assertEqual(capacites.source_taille, INCONNUE)
        self.assertTrue(any("OSError" in m for m in capacites.motifs),
                        capacites.motifs)
        self.assertEqual(capacites.niveau, NU)

    def test_un_flux_tiers_sur_windows_donne_un_ValueError(self):
        """L'autre moitie de la coupure, et elle n'a pas la meme cause.

        `> journal.txt` laisse `fileno()` a 1 et donne un `OSError` ; c'est un
        descripteur >= 3, ouvert a la main, qui n'a pas de handle standard a
        qui parler. Attraper les deux sans savoir laquelle vient d'ou
        conduirait a ecrire n'importe quoi dans le motif.
        """
        capacites = sonder(windows_flux_tiers())
        self.assertIsNone(capacites.colonnes)
        self.assertTrue(any("ValueError" in m for m in capacites.motifs),
                        capacites.motifs)

    def test_un_pty_sans_TIOCSWINSZ_ne_fournit_aucune_taille(self):
        """(0, 0) rendu SANS lever : le seul cas ou l'echec est muet."""
        capacites = sonder(pty_muet())
        self.assertIsNone(capacites.colonnes)
        self.assertEqual(capacites.source_taille, INCONNUE)
        gabarit = gabarit_pour(capacites)
        self.assertEqual(gabarit.colonnes, LARGEUR_SANS_MESURE)
        self.assertFalse(gabarit.mesuree)

    def test_un_TERM_dumb_reste_au_niveau_NU(self):
        capacites = sonder(linux_dumb())
        self.assertFalse(capacites.ansi)
        self.assertEqual(capacites.niveau, NU)
        self.assertTrue(any("dumb" in m for m in capacites.motifs))

    def test_NO_COLOR_laisse_ANSI_vrai_et_coupe_la_couleur(self):
        """ANSI est une mesure, la couleur est un choix : les deux ne cedent
        pas pour la meme raison, et la sonde ne les confond pas."""
        capacites = sonder(linux_sans_couleur())
        self.assertTrue(capacites.ansi)
        self.assertFalse(capacites.couleur)
        self.assertEqual(capacites.niveau, NU)
        self.assertEqual(capacites.flux, "stderr")

    def test_aucun_releve_n_affirme_sans_nommer_ce_qui_l_a_prouve(self):
        for nom, fabrique in BANC.items():
            with self.subTest(cas=nom):
                capacites = sonder(fabrique())
                self.assertTrue(
                    capacites.motifs,
                    "un releve sans un seul motif ne permet pas de repondre "
                    "« elle a repondu quoi » a distance")
                if not capacites.ansi:
                    self.assertTrue(
                        any(mot in " ".join(capacites.motifs)
                            for mot in ("isatty", "GetConsoleMode",
                                        "SetConsoleMode", "TERM")),
                        capacites.motifs)

    def test_aucun_releve_n_invente_une_taille(self):
        """80x24 devine est le defaut que ce module existe pour ne pas avoir.

        `shutil.get_terminal_size` rend `(80, 24)` dans un tube, sans un mot.
        Ici, faute de mesure, la taille vaut `None` et se propage jusqu'a une
        DECISION — le cadre de 72, annonce non mesure.
        """
        for nom, fabrique in BANC.items():
            with self.subTest(cas=nom):
                capacites = sonder(fabrique())
                if capacites.source_taille == INCONNUE:
                    self.assertIsNone(capacites.colonnes)
                    self.assertIsNone(capacites.lignes)
                else:
                    self.assertIsNotNone(capacites.colonnes)
                    self.assertGreater(capacites.colonnes, 0)

    def test_le_flux_mesure_est_toujours_nomme(self):
        """VT est un mode par HANDLE. Une capacite mesuree sur stdout et
        affirmee sur stderr deverserait de l'ANSI dans le journal de qui
        redirige `2>`."""
        for nom, fabrique in BANC.items():
            with self.subTest(cas=nom):
                systeme = fabrique()
                self.assertEqual(sonder(systeme).flux, systeme.nom_du_flux)

    def test_la_sonde_interroge_le_handle_du_flux_qu_on_lui_donne(self):
        erreur = Systeme(plateforme="win32", variables={},
                         nom_du_flux="stderr", fileno=2, isatty=True,
                         encodage="cp1252",
                         console=_console({STD_SORTIE: 0x0007}),
                         taille=lambda _: (80, 25))
        capacites = sonder(erreur)
        # Le bit est pose sur la SORTIE, pas sur l'ERREUR : rien n'est prouve.
        self.assertFalse(capacites.ansi)
        self.assertEqual([appel[1] for appel in erreur.console.journal],
                         [-12])


class TestGabarit(unittest.TestCase):

    def test_une_mesure_perd_une_colonne(self):
        """conhost n'a pas le repli differe : un glyphe dans la derniere
        colonne y fait defiler, et le saut de ligne de `print` une seconde
        fois."""
        gabarit = gabarit_pour(sonder(windows_10()))
        self.assertEqual(gabarit.colonnes, 79)
        self.assertTrue(gabarit.mesuree)

    def test_sans_mesure_le_cadre_vaut_72_et_se_dit_non_mesure(self):
        gabarit = gabarit_pour(sonder(windows_redirige()))
        self.assertEqual(gabarit.colonnes, LARGEUR_SANS_MESURE)
        self.assertFalse(gabarit.mesuree)

    def test_aucun_plancher_ne_surpasse_une_mesure_plus_petite(self):
        """Une mesure a 60 donne 59, pas 72. Reprocher son repli a `shutil`
        puis faire le meme geste dans l'autre sens serait la meme faute."""
        etroit = Capacites(colonnes=60, lignes=20, source_taille=MESUREE)
        self.assertEqual(gabarit_pour(etroit).colonnes, 59)

    def test_le_plafond_borne_une_fenetre_tres_large(self):
        large = Capacites(colonnes=240, lignes=60, source_taille=MESUREE)
        self.assertEqual(gabarit_pour(large).colonnes, LARGEUR_PLAFOND - 1)

    def test_forcer_nu_ne_touche_pas_a_la_largeur(self):
        """Refuser la couleur n'est pas refuser de savoir ou finit l'ecran."""
        gabarit = gabarit_pour(PROUVE, forcer_nu=True)
        self.assertEqual(gabarit.niveau, NU)
        self.assertEqual(gabarit.colonnes, 99)
        self.assertEqual(gabarit_pour(PROUVE).niveau, COULEUR)

    def test_trop_etroit_se_dit_au_lieu_de_se_degrader(self):
        self.assertTrue(Gabarit(colonnes=39).trop_etroit)
        self.assertFalse(Gabarit(colonnes=40).trop_etroit)


class TestFragmentEtBloc(unittest.TestCase):

    def test_un_ton_inconnu_leve(self):
        """Retomber au neutre laisserait « AGIT DANS SAP » parfaitement
        lisible sans son marquage : personne ne s'en apercevrait."""
        with self.assertRaises(ValueError):
            Fragment("AGIT DANS SAP", ton="rouge")

    def test_une_forme_inconnue_leve(self):
        with self.assertRaises(ValueError):
            Bloc((Fragment("x"),), forme="separateurs")

    def test_tous_les_tons_de_TONS_sont_acceptes(self):
        for ton in sorted(TONS):
            with self.subTest(ton=ton):
                self.assertEqual(Fragment("x", ton=ton).ton, ton)

    def test_texte_nu_recolle_les_fragments_sans_decor(self):
        bloc = Bloc((Fragment("a"), Fragment("b", ton=DANGER)))
        self.assertEqual(texte_nu(bloc), "ab")


class TestTroncature(unittest.TestCase):

    def test_ce_qui_tient_n_est_pas_touche(self):
        self.assertEqual(couper("court", 10), "court")
        self.assertEqual(couper_chemin("court", 10), "court")

    def test_couper_pose_la_marque_et_tient_la_largeur(self):
        coupe = couper("a" * 40, 12)
        self.assertEqual(len(coupe), 12)
        self.assertTrue(coupe.endswith(MARQUE))

    def test_deux_identifiants_coupes_restent_distincts(self):
        """La mesure qui justifie `couper_chemin`, et son controle negatif.

        Coupes A DROITE, les deux bornes d'un intervalle donnent la meme
        chaine, d'aspect complet. C'est le genre de confusion qui se recopie
        dans une pipeline, et c'est SAP qui la decouvre.
        """
        bas = "wnd[0]/usr/ctxtWERKS-LOW"
        haut = "wnd[0]/usr/ctxtWERKS-HIGH"
        self.assertEqual(couper(bas, 20), couper(haut, 20))
        self.assertNotEqual(couper_chemin(bas, 20), couper_chemin(haut, 20))
        for texte in (bas, haut):
            with self.subTest(identifiant=texte):
                coupe = couper_chemin(texte, 20)
                self.assertEqual(len(coupe), 20)
                self.assertIn(MARQUE, coupe)

    def test_la_marque_est_de_l_ascii(self):
        """Pas « … » : rien ne garantit qu'une police raster de console en ait
        le glyphe, et un carre vide ne se distingue pas d'une donnee."""
        self.assertEqual(MARQUE.encode("ascii").decode("ascii"), MARQUE)

    def test_une_largeur_absurde_est_refusee_au_lieu_de_rendre_du_vide(self):
        for coupeuse in (couper, couper_chemin):
            for largeur in (0, -3):
                with self.subTest(coupeuse=coupeuse.__name__,
                                  largeur=largeur):
                    with self.assertRaises(ValueError):
                        coupeuse("quelque chose", largeur)


class TestColonnes(unittest.TestCase):

    def test_la_somme_vaut_exactement_la_largeur(self):
        gabarit = Gabarit(colonnes=79)
        parts = colonnes(gabarit, (3, 2, 1), fixes=(10, 2))
        self.assertEqual(sum(parts) + 12, 79)
        self.assertEqual(len(parts), 3)

    def test_une_rangee_qui_ne_tient_pas_est_refusee(self):
        """Refuser plutot que tasser : une colonne de largeur nulle n'affiche
        rien, ce qui se lit comme une donnee vide."""
        with self.assertRaises(ValueError):
            colonnes(Gabarit(colonnes=40), (1, 1, 1), fixes=(39,))

    def test_aucune_colonne_rendue_n_est_nulle(self):
        for largeur in range(10, 80):
            with self.subTest(largeur=largeur):
                parts = colonnes(Gabarit(colonnes=largeur), (40, 1, 1))
                self.assertTrue(all(p > 0 for p in parts), parts)

    def test_un_poids_nul_est_refuse(self):
        with self.assertRaises(ValueError):
            colonnes(Gabarit(colonnes=79), (1, 0))


class TestSequences(unittest.TestCase):

    def test_retirer_annule_teinter(self):
        for ton in sorted(TONS):
            with self.subTest(ton=ton):
                teinte = sequences.teinter("AGIT DANS SAP", ton)
                self.assertEqual(retirer(teinte), "AGIT DANS SAP")

    def test_un_ton_neutre_ne_pose_aucune_sequence(self):
        self.assertEqual(sequences.teinter("rien", NEUTRE), "rien")

    def test_un_ton_inconnu_leve_au_lieu_de_se_taire(self):
        with self.assertRaises(ValueError):
            sequences.teinter("x", "rouge")

    def test_la_table_des_codes_est_fermee_sur_les_tons(self):
        """Un ton sans entree sortirait sans decor : lisible, donc invisible."""
        self.assertEqual(set(sequences.CODES), set(TONS))

    def test_retirer_ne_laisse_rien_meme_sur_une_sequence_non_SGR(self):
        self.assertEqual(retirer(sequences.CSI + "2J" + "texte"), "texte")


class TestPeintre(unittest.TestCase):

    def test_un_flux_non_prouve_ne_recoit_aucune_sequence(self):
        """GARDE n°9, et le controle negatif qui la prouve.

        `outils/neutraliser.py` remplace `_exiger_la_preuve` par
        `lambda *a, **k: None`. La garde LEVE, donc la neutraliser la rend
        PERMISSIVE : `peintre_pour` rend alors un `PeintreColore` sur des
        capacites toutes fausses, et ce test tombe. Une garde qui aurait rendu
        `False` serait devenue une garde qui rend `None` — donc faux, donc le
        refus aurait tenu, et l'outil l'aurait declaree muette a tort.
        """
        peintre = peintre_pour(Capacites())
        for bloc in BLOCS:
            for ligne in peintre.peindre(bloc, Gabarit()):
                with self.subTest(ligne=ligne):
                    self.assertNotIn(sequences.ECHAP, ligne)

    def test_un_flux_prouve_recoit_la_couleur(self):
        peintre = peintre_pour(PROUVE)
        self.assertEqual(peintre.niveau, COULEUR)
        marque = Bloc((Fragment("AGIT DANS SAP", ton=DANGER),))
        self.assertIn(sequences.ECHAP,
                      "".join(peintre.peindre(marque, Gabarit())))

    def test_forcer_nu_refuse_meme_un_flux_prouve(self):
        peintre = peintre_pour(PROUVE, forcer_nu=True)
        self.assertEqual(peintre.niveau, NU)

    def test_la_garde_LEVE_au_lieu_de_rendre_un_booleen(self):
        with self.assertRaises(RenduRefuse):
            module_peintre._exiger_la_preuve(Capacites(), COULEUR)
        # Et elle se tait quand on ne demande rien de plus que le prouve.
        self.assertIsNone(
            module_peintre._exiger_la_preuve(Capacites(), NU))
        self.assertIsNone(module_peintre._exiger_la_preuve(PROUVE, COULEUR))

    def test_le_refus_nomme_ce_qui_n_a_pas_ete_prouve(self):
        """Un refus muet se lit comme un outil casse."""
        with self.assertRaises(RenduRefuse) as capture:
            module_peintre._exiger_la_preuve(
                Capacites(flux="stderr", interactif=True,
                          motifs=("TERM=dumb : le terminal se declare sans "
                                  "capacite",)),
                COULEUR)
        message = str(capture.exception)
        self.assertIn("stderr", message)
        self.assertIn("dumb", message)

    def test_la_couleur_n_ajoute_et_ne_retire_rien(self):
        """L'invariant, evalue BLOC PAR BLOC, sans normalisateur.

        `PeintreColore` appelle `super().peindre` puis enveloppe : la structure
        reste celle du niveau NU par construction. Un peintre qui
        reconstruirait ses lignes pourrait en produire un nombre different, et
        c'est le premier endroit ou les deux niveaux divergeraient sans que
        personne ne leve.
        """
        nu, colore = PeintreNu(), PeintreColore()
        for gabarit in (Gabarit(), Gabarit(colonnes=79, lignes=24),
                        Gabarit(colonnes=40, lignes=16),
                        Gabarit(colonnes=109, lignes=30)):
            for bloc in BLOCS:
                with self.subTest(colonnes=gabarit.colonnes,
                                  forme=bloc.forme):
                    attendu = nu.peindre(bloc, gabarit)
                    obtenu = colore.peindre(bloc, gabarit)
                    self.assertEqual(len(obtenu), len(attendu))
                    self.assertEqual([retirer(l) for l in obtenu], attendu)

    def test_aucune_ligne_ne_deborde_du_gabarit(self):
        nu = PeintreNu()
        for largeur in (40, 72, 79, 109):
            gabarit = Gabarit(colonnes=largeur)
            for bloc in BLOCS:
                for ligne in nu.peindre(bloc, gabarit):
                    with self.subTest(largeur=largeur, forme=bloc.forme):
                        self.assertLessEqual(len(ligne), largeur)

    def test_une_ligne_tronquee_porte_toujours_sa_marque(self):
        long = Bloc((Fragment("z" * 300),))
        rendu = PeintreNu().peindre(long, Gabarit(colonnes=79))
        self.assertEqual(len(rendu), 1)
        self.assertTrue(rendu[0].endswith(MARQUE))

    def test_un_bloc_vide_reste_une_ligne_vide(self):
        self.assertEqual(PeintreNu().peindre(Bloc(forme=VIDE), Gabarit()),
                         [""])

    def test_une_marge_plus_large_que_le_gabarit_ne_leve_pas(self):
        """Un gabarit de 40 et une marge de 60 sont un defaut de calcul de la
        vue ; le peintre n'a pas a mourir dessus, mais il ne doit rien rendre
        de plus large que ce qu'il a."""
        bloc = Bloc((Fragment("texte"),), forme=LIGNE, marge=60)
        for ligne in PeintreNu().peindre(bloc, Gabarit(colonnes=40)):
            self.assertLessEqual(len(ligne), 40)


class TestRenduDeLaSonde(unittest.TestCase):
    """Ce qu'imprime `falcon sonde` : pur, cp1252, sans une sequence."""

    def _pages(self):
        return [(nom, rendre_sonde((sonder(fabrique()),)))
                for nom, fabrique in BANC.items()]

    def test_la_page_s_encode_en_cp1252(self):
        for nom, page in self._pages():
            for ligne in page:
                with self.subTest(cas=nom, ligne=ligne):
                    ligne.encode(ENCODAGE_MINIMAL)

    def test_aucune_sequence_dans_la_page(self):
        """`falcon sonde` est precisement ce qu'on lance quand on soupconne le
        terminal de ne rien interpreter."""
        for nom, page in self._pages():
            with self.subTest(cas=nom):
                self.assertNotIn(sequences.ECHAP, "\n".join(page))

    def test_aucune_ligne_ne_deborde_de_79_colonnes(self):
        for nom, page in self._pages():
            for ligne in page:
                with self.subTest(cas=nom, ligne=ligne):
                    self.assertLessEqual(len(ligne), 79)

    def test_le_niveau_retenu_est_ecrit_en_toutes_lettres(self):
        page = "\n".join(rendre_capacites(sonder(windows_10())))
        self.assertIn("niveau retenu", page)
        self.assertIn("COULEUR", page)
        self.assertIn("niveau retenu",
                      "\n".join(rendre_capacites(sonder(linux_dumb()))))
        self.assertIn("NU", "\n".join(rendre_capacites(sonder(linux_dumb()))))

    def test_une_taille_inconnue_se_dit_inconnue(self):
        page = "\n".join(rendre_capacites(sonder(windows_redirige())))
        self.assertIn("inconnue", page)
        self.assertNotIn("80 x 24", page)

    def test_chaque_motif_du_releve_se_retrouve_dans_la_page(self):
        """Le bloc des motifs est la moitie utile du releve quand rien ne
        marche : une sonde qui ecrirait « ANSI non » sans dire lequel des
        quatre chemins a refuse obligerait a deviner a distance."""
        for nom, fabrique in BANC.items():
            capacites = sonder(fabrique())
            page = " ".join("\n".join(rendre_capacites(capacites)).split())
            for motif in capacites.motifs:
                with self.subTest(cas=nom, motif=motif):
                    self.assertIn(motif, page)

    def test_les_deux_flux_sortent_l_un_apres_l_autre(self):
        page = rendre_sonde((sonder(windows_10()), sonder(linux_sans_couleur())))
        texte = "\n".join(page)
        self.assertIn("stdout", texte)
        self.assertIn("stderr", texte)


if __name__ == "__main__":
    unittest.main()
