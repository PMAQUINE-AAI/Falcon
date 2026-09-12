"""La toile : ce qu'un terminal sait faire, et ce qu'on a le droit d'y peindre.

**Cette suite est 100 % injectee, et c'est une exigence, pas une elegance.**
Aucun test ne lit le terminal de qui la lance : `sonder` prend un `Systeme`
obligatoire, le banc ci-dessous en fabrique autant qu'il en faut, et
`test_la_suite_ne_touche_jamais_le_vrai_terminal` verifie sur l'arbre
syntaxique que ce fichier n'a meme pas de quoi le faire.

Le motif n'est pas la purete. Cette suite est celle que `outils/neutraliser.py`
relance pour la neuvieme garde, et son `main()` exige que chaque suite citee
PASSE avant neutralisation. Une suite sensible au terminal ferait donc rougir
la verification des huit gardes SAP un jour ou quelqu'un lance l'outil depuis
un tube — pour un motif sans le moindre rapport avec SAP.

Le banc reproduit des terminaux que la CI ne verra jamais. Il prouve que la
sonde est coherente avec NOTRE modele de Windows ; il ne prouve rien sur
Windows, et `falcon/toile/__init__.py` dit ou s'arrete cette reserve. Son
compte n'est ecrit nulle part : `BANC` le porte, et un chiffre recopie dans
une docstring se perime au premier ajout.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from falcon.toile import (
    ALERTE, COULEUR, DANGER, DECLAREE, ENTETE, FORMES, INCONNUE,
    LARGEUR_PLAFOND, LARGEUR_SANS_MESURE, MARQUE, MESUREE, NEUTRE, NU,
    SEPARATEUR, STD_SORTIE, TONS, VIDE, Bloc, Capacites, Fragment, Gabarit, PeintreColore,
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


def _console_qui_leve(erreur, *, sur="lire"):
    """Un kernel32 dont un appel PART EN EXCEPTION.

    Le chemin Windows ne s'execute sur aucune CI : sans ce double, une
    exception venue de `ctypes` resterait invisible jusqu'au jour ou elle
    tuerait `falcon sonde` sur la machine de l'utilisateur — et l'ecran de
    console avec, donc la session entiere. C'est la seule facon de rendre ce
    chemin non regressif depuis Linux.
    """

    class ConsoleCassee:
        def __init__(self) -> None:
            self.modes = {STD_SORTIE: 0x0003}

        def lire_mode(self, handle: int) -> int | None:
            if sur == "lire":
                raise erreur
            return self.modes.get(handle)

        def poser_mode(self, handle: int, mode: int) -> bool:
            if sur == "poser":
                raise erreur
            self.modes[handle] = mode
            return True

    return ConsoleCassee()


def _console_qui_refuse_de_restaurer(modes):
    """`SetConsoleMode` accepte de poser le bit, puis refuse de le reposer.

    Le verdict ne change pas — la capacite EST prouvee — mais le RECIT si, et
    c'est le recit qu'on lit au telephone. Une page qui ecrirait « mode
    restaure » alors que le bit est reste pose serait une affirmation non
    mesuree dans le seul module dont le contrat est de n'en produire aucune.
    """

    class ConsoleTetue:
        def __init__(self) -> None:
            self.modes = dict(modes)
            self.poses = 0

        def lire_mode(self, handle: int) -> int | None:
            return self.modes.get(handle)

        def poser_mode(self, handle: int, mode: int) -> bool:
            self.poses += 1
            if self.poses >= 2:
                return False
            self.modes[handle] = mode
            return True

    return ConsoleTetue()


def _taille_qui_leve(erreur):
    def mesurer(_descripteur):
        raise erreur
    return mesurer


# ---------------------------------------------------------------------------
# Le banc : des terminaux, aucun reel
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
def linux_declare() -> Systeme:
    """L'ioctl echoue et `COLUMNS`/`LINES` sont poses : le dernier recours.

    Le cas vivant est Git Bash / MSYS, qui EXPORTE les deux. Il n'etait
    represente par aucun `Systeme` du banc, si bien qu'on pouvait etiqueter la
    declaration `MESUREE` — le peche exact de `shutil` — sans qu'une seule
    assertion bouge.
    """
    return Systeme(
        plateforme="linux",
        variables={"TERM": "xterm", "COLUMNS": "100", "LINES": "30"},
        nom_du_flux="stdout", fileno=1, isatty=True, encodage="utf-8",
        taille=_taille_qui_leve(
            OSError(25, "Inappropriate ioctl for device")))


def linux_colonnes_seules() -> Systeme:
    """`COLUMNS` sans `LINES` : le cas courant de `bash`, et il est REFUSE.

    Accepter la largeur seule obligerait a inventer une hauteur. La
    precondition etait la, cachee dans un `int('')` qui levait ; elle est
    desormais nommee, motivee et figee par un test.
    """
    return Systeme(
        plateforme="linux", variables={"TERM": "xterm", "COLUMNS": "100"},
        nom_du_flux="stdout", fileno=1, isatty=True, encodage="utf-8",
        taille=_taille_qui_leve(
            OSError(25, "Inappropriate ioctl for device")))


def linux_sans_TERM() -> Systeme:
    """Un cron, un service systemd : un vrai terminal que rien ne declare."""
    return Systeme(
        plateforme="linux", variables={}, nom_du_flux="stdout",
        fileno=1, isatty=True, encodage="utf-8", taille=lambda _: (100, 40))


def linux_etranger() -> Systeme:
    """Un `TERM` et un `strerror` que cp1252 ne sait pas ecrire.

    Le cas qui PROUVE la docstring de `rendre_capacites`. Les neuf premiers
    cas du banc portent des chaines ASCII ecrites a la main : ils prouvent
    moins que ce que cette docstring affirme. Un Windows japonais localise
    `strerror`, et `TERM` vient de l'environnement — deux textes que personne
    ne controle, dans une page qui promet cp1252 et qui s'imprime par `print`.
    """
    return Systeme(
        plateforme="linux", variables={"TERM": "ターミナル"},
        nom_du_flux="stdout", fileno=1, isatty=True, encodage="utf-8",
        taille=_taille_qui_leve(
            OSError(9, "ハンドルが無効です")))


def windows_sans_encodage() -> Systeme:
    """Un flux qui ne declare aucun encodage : on n'en invente pas un."""
    return Systeme(
        plateforme="win32", variables={}, nom_du_flux="stdout",
        fileno=1, isatty=False, encodage="", console=_console({}),
        taille=lambda _: (80, 25))


def windows_ctypes_casse() -> Systeme:
    """`GetConsoleMode` part en exception. Un refus motive, jamais une trace."""
    return Systeme(
        plateforme="win32", variables={}, nom_du_flux="stdout",
        fileno=1, isatty=True, encodage="cp1252",
        console=_console_qui_leve(OSError(127, "procedure introuvable")),
        taille=lambda _: (80, 25))


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
    "linux declare": linux_declare,
    "linux colonnes seules": linux_colonnes_seules,
    "linux sans TERM": linux_sans_TERM,
    "linux etranger": linux_etranger,
    "windows sans encodage": windows_sans_encodage,
    "windows ctypes casse": windows_ctypes_casse,
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


class TestLeBanc(unittest.TestCase):
    """Des terminaux que la CI ne verra jamais, et ce que la sonde en dit."""

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

    def test_un_nom_de_flux_inconnu_est_REFUSE_au_lieu_d_etre_devine(self):
        """Le defaut le plus discret que ce module ait porte.

        `STD_ERREUR if nom == "stderr" else STD_SORTIE` mesurait le handle de
        la SORTIE pour tout autre nom — « STDERR », « erreur standard »,
        « log » — puis estampillait le releve du nom recu. VT etant un mode par
        HANDLE, la page annoncait alors « flux mesure STDERR / ANSI oui » sur
        une mesure faite ailleurs : aucune exception, un ecran plausible et
        faux, et de l'ANSI deverse dans le journal de qui redirige `2>`.

        Les deux appelants d'aujourd'hui passent les bonnes chaines ; c'est
        donc une bombe a retardement, amorcee pile ou le direct branchera
        `stderr`. Un refus vaut mieux qu'une valeur devinee.
        """
        for nom in ("STDERR", "erreur standard", "log", ""):
            with self.subTest(nom_du_flux=nom):
                with self.assertRaises(ValueError):
                    Systeme(plateforme="win32", variables={}, nom_du_flux=nom,
                            fileno=2, isatty=True, encodage="cp1252")

    def test_le_chemin_windows_refuse_aussi_un_nom_de_flux_inconnu(self):
        """La SECONDE mesure, et il en faut deux.

        `Systeme` valide a la construction ; on force ici le champ par-dessus
        le gel du dataclass pour atteindre le chemin Windows lui-meme. Si la
        validation sautait un jour, la table doit LEVER et non retomber sur le
        handle de la sortie — sans quoi le releve porterait « flux mesure
        STDERR / ANSI oui » sur une mesure faite ailleurs.
        """
        systeme = Systeme(plateforme="win32", variables={},
                          nom_du_flux="stderr", fileno=2, isatty=True,
                          encodage="cp1252",
                          console=_console({STD_SORTIE: 0x0007}),
                          taille=lambda _: (80, 25))
        object.__setattr__(systeme, "nom_du_flux", "STDERR")
        with self.assertRaises(ValueError):
            sonder(systeme)
        self.assertEqual(systeme.console.journal, [])

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

    def test_une_declaration_COLUMNS_ne_se_donne_jamais_pour_une_mesure(self):
        """CONTROLE NEGATIF : etiqueter ce chemin `MESUREE` doit faire tomber.

        C'est le peche de `shutil`, et il etait possible ici sans qu'une seule
        assertion bouge : aucun `Systeme` du banc ne portait `COLUMNS`. Le
        chemin entier — une vingtaine de lignes, une constante publique et
        trois docstrings — n'etait exerce par rien.
        """
        capacites = sonder(linux_declare())
        self.assertEqual(capacites.source_taille, DECLAREE)
        self.assertEqual((capacites.colonnes, capacites.lignes), (100, 30))
        self.assertTrue(any("jamais verifies" in m for m in capacites.motifs),
                        capacites.motifs)

    def test_COLUMNS_sans_LINES_est_refuse_et_le_dit(self):
        """La precondition cachee, nommee et figee.

        `int(brut_colonnes), int(brut_lignes)` exigeait les DEUX : `bash`
        n'exporte que `COLUMNS`, et la declaration retombait donc sur INCONNUE
        par l'effet de bord d'un `int('')`, sans un mot. Celui qui pose
        `COLUMNS` pour se faire entendre doit pouvoir lire pourquoi il ne l'a
        pas ete.
        """
        capacites = sonder(linux_colonnes_seules())
        self.assertEqual(capacites.source_taille, INCONNUE)
        self.assertIsNone(capacites.colonnes)
        self.assertTrue(any("les DEUX" in m for m in capacites.motifs),
                        capacites.motifs)
        # Et le motif ne sort QUE la : celui qui n'a rien pose n'a rien a
        # lire sur `COLUMNS`, et une page qui expliquerait tout ce qu'elle
        # n'a pas trouve ne se lirait plus.
        muet = sonder(windows_redirige())
        self.assertFalse(any("les DEUX" in m for m in muet.motifs),
                         muet.motifs)

    def test_un_TERM_absent_sur_un_vrai_terminal_refuse_l_ANSI(self):
        """Un cron ou un service systemd : le banc n'en avait aucun.

        CONTROLE NEGATIF : supprimer la branche « TERM n'est pas defini » de
        `_ansi_posix` ne faisait tomber aucun test.
        """
        capacites = sonder(linux_sans_TERM())
        self.assertFalse(capacites.ansi)
        self.assertEqual(capacites.niveau, NU)
        self.assertTrue(any("TERM n'est pas defini" in m
                            for m in capacites.motifs), capacites.motifs)

    def test_chaque_cas_du_banc_a_la_provenance_ANSI_qu_on_attend(self):
        """La table est ECRITE ici, cas par cas, et pas deduite du code.

        Un test qui se contenterait de verifier que l'annotation s'accorde au
        champ `source_ansi` serait vide : il suffirait de mentir des deux
        cotes a la fois. Ce qui doit etre fige, c'est QUEL CHEMIN produit
        QUELLE provenance — un verdict POSIX vient de `TERM`, donc il est
        DECLARE, et aucune retouche ne doit pouvoir le promouvoir en mesure.
        """
        attendu = {
            "windows terminal": MESUREE,     # GetConsoleMode a repondu
            "windows 10": MESUREE,           # pose, relu, restaure
            "windows 8.1": MESUREE,          # SetConsoleMode a refuse
            "windows menteur": MESUREE,      # la relecture a dement
            "windows redirige": MESUREE,     # isatty() est faux
            "flux tiers": MESUREE,           # isatty() est faux
            "windows sans encodage": MESUREE,
            "windows ctypes casse": MESUREE,
            "pty muet": DECLAREE,            # TERM, et rien d'autre
            "linux dumb": DECLAREE,
            "no_color": DECLAREE,
            "linux declare": DECLAREE,
            "linux colonnes seules": DECLAREE,
            "linux sans TERM": DECLAREE,
            "linux etranger": DECLAREE,
        }
        self.assertEqual(set(attendu), set(BANC),
                         "un cas du banc sans provenance attendue")
        for nom, source in attendu.items():
            with self.subTest(cas=nom):
                self.assertEqual(sonder(BANC[nom]()).source_ansi, source)

    def test_un_flux_sans_encodage_n_en_recoit_pas_un_de_confort(self):
        """`ENCODAGE_MINIMAL` est le plancher de qui CHOISIT quoi ecrire.

        Le rapporter comme un releve ferait imprimer « encodage de sortie
        cp1252 » sur une machine Linux en UTF-8, sous une etiquette qui dit le
        contraire, et le lot qui peint s'en servirait pour decider quels
        caracteres il peut poser.
        """
        capacites = sonder(windows_sans_encodage())
        self.assertEqual(capacites.encodage, "")
        self.assertTrue(any("aucun encodage" in m for m in capacites.motifs),
                        capacites.motifs)
        page = "\n".join(rendre_capacites(capacites))
        self.assertIn("inconnu", page)
        self.assertNotIn(ENCODAGE_MINIMAL, page)

    def test_une_console_qui_part_en_exception_donne_un_refus_motive(self):
        """Le chemin Windows n'est garde par aucune CI : il l'est par ici.

        Sans enveloppe, `sonder` PROPAGE l'`OSError`, `main()` n'attrape que
        `ERREURS_LISIBLES`, donc `falcon sonde` sort en trace de pile — sur le
        terminal cabosse qu'on l'appelait justement pour decrire. Et dans la
        console, ce n'est pas l'ecran qui tombe, c'est la session.
        """
        capacites = sonder(windows_ctypes_casse())
        self.assertFalse(capacites.ansi)
        self.assertEqual(capacites.niveau, NU)
        joints = " ".join(capacites.motifs)
        self.assertIn("GetConsoleMode", joints)
        self.assertIn("OSError", joints)

    def test_une_restauration_refusee_ne_s_ecrit_pas_restauree(self):
        """Le verdict ne change pas, le RECIT si — et c'est lui qu'on lit.

        `poser_mode` rendait un booleen qu'on jetait, puis le motif annoncait
        « mode restaure » sans condition. Un bit VT laisse pose est benin ;
        l'affirmation non mesuree ne l'est pas, dans le module dont le contrat
        ecrit est qu'il n'en produit aucune. Et le lot qui peindra a besoin de
        savoir si le bit est encore la.
        """
        systeme = Systeme(
            plateforme="win32", variables={}, nom_du_flux="stdout",
            fileno=1, isatty=True, encodage="cp1252",
            console=_console_qui_refuse_de_restaurer({STD_SORTIE: 0x0003}),
            taille=lambda _: (80, 25))
        capacites = sonder(systeme)
        self.assertTrue(capacites.ansi)
        joints = " ".join(capacites.motifs)
        self.assertIn("le bit reste pose", joints)
        self.assertNotIn("restaure", joints.replace("reposer", ""))
        # Le mode d'origine n'a PAS ete remis : c'est le fait qu'on rapporte.
        self.assertEqual(systeme.console.modes[STD_SORTIE], 0x0007)

    def test_la_console_kernel32_a_la_forme_du_protocole(self):
        """Le seul controle possible depuis Linux sur du code qui n'y tourne
        pas.

        `__init__` est la seule ligne qui touche `ctypes` ; les methodes
        s'introspectent telles quelles. Le test compare les NOMS et l'ORDRE
        des parametres, donc il mord sur un renommage comme sur une inversion
        de `poser_mode(self, handle, mode)` en `(self, mode, handle)` — cette
        derniere poserait un mode sur le mauvais handle, sans aucune
        exception, et la sonde repondrait « ANSI oui » sur une mesure qu'elle
        n'a pas faite.
        """
        import inspect

        from falcon.toile.capacites import ConsoleWindows, _ConsoleKernel32

        for nom in ("lire_mode", "poser_mode"):
            with self.subTest(methode=nom):
                attendu = inspect.signature(getattr(ConsoleWindows, nom))
                obtenu = inspect.signature(getattr(_ConsoleKernel32, nom))
                self.assertEqual(list(attendu.parameters),
                                 list(obtenu.parameters))


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

    def test_une_largeur_declaree_ne_franchit_pas_la_frontiere_en_mesuree(self):
        """LA propriete qui empeche le mensonge de passer au rendu.

        Avec un booleen unique, la distinction mourait ici : plus aucune vue
        ne pouvait separer « 72, je ne sais rien » de « 109, quelqu'un a dit
        300 ». Le navigateur annoncerait « largeur non mesuree » puis mettrait
        en page sur 109 colonnes dans une fenetre de 80, et chaque ligne se
        replierait — le repli etant precisement ce que la marge d'une colonne
        existe pour eviter.
        """
        gabarit = gabarit_pour(sonder(linux_declare()))
        self.assertEqual(gabarit.source, DECLAREE)
        self.assertFalse(gabarit.mesuree)
        self.assertEqual(gabarit.colonnes, 99)
        self.assertEqual(gabarit.lignes, 30)

    def test_les_trois_provenances_arrivent_distinctes_au_gabarit(self):
        for cas, attendu in (("windows 10", MESUREE),
                             ("linux declare", DECLAREE),
                             ("windows redirige", INCONNUE)):
            with self.subTest(cas=cas):
                gabarit = gabarit_pour(sonder(BANC[cas]()))
                self.assertEqual(gabarit.source, attendu)
                self.assertEqual(gabarit.mesuree, attendu == MESUREE)

    def test_aucun_gabarit_ne_rend_une_largeur_nulle(self):
        """Une mesure a 1 donnait 0, et `peindre` levait en plein rendu.

        Le declencheur Windows plausible est une fenetre reduite pendant une
        reconnexion RDP, ou un `COLUMNS` absurde. Le plancher ne surpasse
        aucune mesure : il refuse de rendre une largeur qui n'en est pas une,
        et `trop_etroit` reste vrai pour que la vue refuse d'elle-meme.
        """
        for mesure in (1, 2, 3, 41):
            with self.subTest(colonnes=mesure):
                gabarit = gabarit_pour(Capacites(colonnes=mesure, lignes=10,
                                                 source_taille=MESUREE))
                self.assertGreaterEqual(gabarit.colonnes, 1)
                PeintreNu().peindre(Bloc((Fragment("x"),)), gabarit)
        self.assertTrue(
            gabarit_pour(Capacites(colonnes=1, lignes=10,
                                   source_taille=MESUREE)).trop_etroit)


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

    def test_une_marge_negative_leve(self):
        """CONTROLE NEGATIF : retirer la garde ne faisait tomber aucun test.

        Avec `marge=-1`, `' ' * -1` rend '' et `couper(texte, largeur + 1)`
        ELARGIT la coupe : une ligne qui deborde d'une colonne, sans un mot,
        exactement la que la marge d'une colonne existe pour proteger.
        """
        with self.assertRaises(ValueError):
            Bloc((Fragment("x"),), marge=-1)

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
        de plus large que ce qu'il a.

        **La boucle porte sur les QUATRE formes**, et c'est le defaut que ce
        test avait : sa docstring affirmait une propriete qu'il n'evaluait que
        pour `LIGNE`. Mesure avant correction :
        `PeintreNu().peindre(Bloc(..., forme=ENTETE, marge=38),
        Gabarit(colonnes=40))` levait « largeur de coupe absurde : 0 », sur le
        gabarit meme que ce test utilise — la branche ENTETE calculait
        `retrait = marge + 2` sans reborner. La borne basse (40, 16) de la
        matrice des vues est exactement ce cas, et `PeintreColore` delegue a
        `super().peindre`, donc les deux niveaux seraient morts ensemble.
        """
        for forme in sorted(FORMES):
            for largeur in (40, 72, 79):
                for marge in (0, 2, 38, 39, 60):
                    bloc = Bloc((Fragment("texte tres long " * 6),),
                                forme=forme, marge=marge)
                    with self.subTest(forme=forme, largeur=largeur,
                                      marge=marge):
                        for ligne in PeintreNu().peindre(
                                bloc, Gabarit(colonnes=largeur)):
                            self.assertLessEqual(len(ligne), largeur)

    def test_un_flux_non_interactif_ne_peut_pas_atteindre_la_couleur(self):
        """CONTROLE NEGATIF : retirer `self.interactif and` de `niveau`.

        La clause est inatteignable par `sonder`, qui force deja `ansi=False`
        quand `isatty` est faux — donc rien ne la protegeait. Mais `Capacites`
        est un dataclass PUBLIC que les appelants construisent a la main, et
        c'est ce que la propriete promet en toutes lettres : « COULEUR
        seulement si TOUT a ete prouve sur CE flux ».
        """
        menteur = Capacites(interactif=False, ansi=True, couleur=True)
        self.assertEqual(menteur.niveau, NU)
        self.assertEqual(peintre_pour(menteur).niveau, NU)


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

    def test_une_taille_declaree_se_dit_declaree(self):
        """Le mot de provenance, sur la LIGNE, et pas seulement dans un motif.

        Qui lit la page en diagonale lit la colonne de droite : c'est elle qui
        doit porter le fait que personne n'a verifie ces 100 x 30.
        """
        page = "\n".join(rendre_capacites(sonder(linux_declare())))
        self.assertIn("100 x 30", page)
        self.assertIn(DECLAREE, page)

    def test_chaque_verdict_ANSI_porte_sa_provenance(self):
        """LE defaut que ce lot a livre, et que ce test rend impossible.

        La page jurait que « chaque oui est un appel systeme », quatre lignes
        sous un motif qui dit « POSIX ne mesure pas ». Sur POSIX, `ANSI oui`
        sort de `TERM` : une variable, precisement. La commande qu'on lance
        PARCE QU'ON DOUTE de son terminal repondait une certitude la ou elle
        n'avait qu'une declaration — et un `TERM` herite d'un ssh ou d'un
        editeur suffisait a obtenir COULEUR sans qu'aucun appel n'ait rien
        prouve.
        """
        for nom, fabrique in BANC.items():
            capacites = sonder(fabrique())
            page = "\n".join(rendre_capacites(capacites))
            with self.subTest(cas=nom):
                ligne = [l for l in page.splitlines() if "ANSI" in l]
                self.assertEqual(len(ligne), 1, page)
                self.assertTrue(ligne[0].split()[-1],
                                "la ligne ANSI ne dit pas d'ou elle sort")
                if capacites.source_ansi == DECLAREE:
                    self.assertIn("non mesure", ligne[0])
                elif capacites.source_ansi == MESUREE:
                    self.assertIn("appel systeme", ligne[0])
                    # Et jamais « bit VT » sur un flux POSIX : le meme verdict
                    # sort d'`isatty()` d'un cote et du bit de l'autre.
                    self.assertNotIn("bit VT", ligne[0])

    def test_un_TERM_non_latin1_ne_tue_pas_la_page(self):
        """Ce cas-la, et pas les neuf ASCII, prouve la docstring.

        `Console.ecrire` vaut `print` et `_sonde` imprime par `print` : sur un
        Windows japonais, russe ou grec — exactement le genre de poste ou l'on
        demande `falcon sonde` — une page non encodable meurt sur une trace de
        pile au lieu de rendre son releve, et l'ecran de console casse au
        milieu. Le `strerror` de ce cas est localise, comme Windows le fait.
        """
        capacites = sonder(linux_etranger())
        page = "\n".join(rendre_sonde((capacites,)))
        page.encode(ENCODAGE_MINIMAL)
        # L'errno et le nom de l'appel survivent : c'est ce qu'on lit.
        self.assertIn("OSError", page)
        self.assertIn("TERM=", page)

    def test_un_Capacites_construit_a_la_main_n_echappe_pas_a_la_promesse(self):
        """La page promet cp1252 ; elle le tient sur ce qu'on lui donne.

        `Capacites` est un dataclass public : ses motifs ne viennent pas tous
        de `sonder`. La promesse est faite par `rendre_capacites`, donc c'est
        elle qui doit la tenir, pour toute entree.
        """
        page = rendre_capacites(Capacites(
            flux="stdout", encodage="日本語",
            motifs=("ハンドルが無効",)))
        "\n".join(page).encode(ENCODAGE_MINIMAL)

    def test_la_page_ne_promet_pas_seize_couleurs_comme_un_releve(self):
        """Rien n'a jamais compte seize couleurs, nulle part.

        Sur Windows le bit VT prouve l'interpretation de SGR, pas la palette ;
        sur POSIX c'est TERM. L'annotation dit donc une INTENTION — ce que
        FALCON emettra — et pas un releve.
        """
        page = "\n".join(rendre_capacites(sonder(windows_10())))
        self.assertIn("seize couleurs seront emises", page)

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
