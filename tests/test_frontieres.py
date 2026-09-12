"""Frontieres d'import — la condition de faisabilite de la spec.

Le 3.4 dit : « Tous les appels COM vers SAP GUI sont confines dans un module
unique exposant une interface etroite. Rien d'autre dans FALCON ne connait
SAP. » Et le 3.7 fait de cette couture la condition pour que le harness de
rejeu reste ecrivable en quelques centaines de lignes.

Une regle d'architecture qu'aucun test ne verifie est une intention, pas une
regle : elle tient jusqu'au premier import presse. Ces tests la rendent
mecanique.

Ils passent a vide tant que les modules concernes n'existent pas — c'est
voulu. Ils mordent des la premiere ligne de code qui violerait la regle.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
PAQUET = RACINE / "falcon"

# Le seul module autorise a connaitre SAP.
MODULE_SAP_AUTORISE = PAQUET / "couture" / "sapgui.py"
MODULES_SAP = {"win32com", "pythoncom", "comtypes", "win32api", "win32gui"}

# Ces couches passent par le controleur, jamais par la couture nue (5.2) :
# une pipeline declare une intention, le controleur applique les gardes.
# `tableur` y figure pour la meme raison que les deux autres, et pour une de
# plus : il traduit un classeur en TEXTE, et n'a aucune raison de toucher un
# driver. S'il pouvait en nommer un, il pourrait produire une pipeline qui
# agit au lieu d'une qui declare.
#
# `exploration` y figure comme `moteur` : il RECOIT un driver deja garde, il
# n'en fabrique pas et n'en nomme pas le type. C'est ce qui empeche la
# cartographie de se donner un driver nu — donc sans dry-run ni plafond de
# sauvegardes — le jour ou ce serait commode.
#
# `toile` y figure pour une raison de plus, et c'est la plus forte : elle ne
# connait pas un mot de FALCON. Un import de couture y serait la preuve que le
# cloisonnement a cede.
COUCHES_SANS_COUTURE = ("moteur", "pipeline", "tableur", "exploration",
                        "toile")

# Une pipeline ne peut nommer aucun type de driver, gardé ou non. Ne pouvant
# pas en manipuler un, elle ne peut pas non plus desactiver une garde : la
# regle du 5.2 devient une contrainte d'import plutot qu'une convention.
COUCHES_SANS_CONTROLEUR = ("pipeline", "trace", "tableur", "toile")

# Le SEUL module ou une sequence ANSI s'ecrit, litteralement ou non.
#
# Meme discipline que pour SAP : une capacite qui depend de la plateforme
# d'affichage se confine dans un module nomme. Le reste du depot ne devient pas
# plus permissif parce que ce module existe.
MODULE_ANSI_AUTORISE = PAQUET / "toile" / "sequences.py"

# Et les seuls qui aient le droit de l'importer.
#
# Deux regles, parce qu'aucune des deux ne suffit seule : `chr(27) + "["` ne
# contient aucun `\x1b` litteral et passerait n'importe quel scan de texte,
# tandis qu'un litteral recopie a la main ne passe par aucun import. C'est la
# cicatrice de `test_aucun_sous_processus_ne_passe_par_le_shell` — « un
# controle qui confond une promesse avec son execution ne controle rien ».
IMPORTEURS_ANSI_AUTORISES = {
    PAQUET / "toile" / "peintre.py",
    PAQUET / "toile" / "__init__.py",
}

# Ce qu'aucun module de FALCON n'importe, jamais.
#
# `curses` n'est pas compile dans la distribution CPython de Windows — et la CI
# est Linux, ou il existe. Un ecran curses passerait donc la suite au VERT et
# mourrait a l'import sur la seule machine ou il sert, puisque c'est la seule
# ou SAP GUI existe. Le refus etait de la prose dans `console/menu.py:3-14` ;
# ici il devient mecanique.
#
# Les bibliotheques tierces y figurent pour une seconde raison : la livraison
# est un fichier unique (§6) et PyYAML est la seule dependance. Chacune de
# celles-ci serait une piece a embarquer, et `colorama` en particulier serait
# la reponse toute faite au probleme que `falcon/toile/capacites.py` resout en
# MESURANT.
#
# `msvcrt`, `termios` et `tty` ne sont pas des dependances mais des lectures
# clavier brutes : sous `tty.setraw`, `ISIG` est coupe et Ctrl-C arrive comme
# `\x03`, donc une boucle devient ininterruptible dans un programme qui tient
# une session SAP. Et surtout, une saisie qui ne passe pas par `Console.lire`
# est invisible a `Journal` : ce serait la premiere interface non testable du
# depot.
MODULES_INTERDITS = {
    "curses", "_curses", "windows-curses",
    "rich", "blessed", "textual", "colorama", "prompt_toolkit", "urwid",
    "msvcrt", "termios", "tty",
}

# `toile` PEINT ; `exploration` et `moteur` EMETTENT. La direction de
# dependance est celle du depot, et l'inverse rendrait un parcours intestable
# sans terminal — ce qu'il n'est pas aujourd'hui.
COUCHES_SANS_TOILE = ("exploration", "moteur")


def modules_python(base: Path) -> list[Path]:
    return sorted(base.rglob("*.py")) if base.exists() else []


def _lignes_sous_type_checking(arbre: ast.Module) -> set[int]:
    """Lignes situees dans un bloc `if TYPE_CHECKING:`.

    Un import d'annotation ne cree aucune dependance a l'execution : la regle
    de couche ne doit pas interdire de typer correctement.
    """
    lignes: set[int] = set()
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.If):
            continue
        test = noeud.test
        nom = getattr(test, "id", None) or getattr(test, "attr", None)
        if nom != "TYPE_CHECKING":
            continue
        for enfant in noeud.body:
            for sous in ast.walk(enfant):
                ligne = getattr(sous, "lineno", None)
                if ligne is not None:
                    lignes.add(ligne)
    return lignes


def _absolu(chemin: Path, noeud: ast.ImportFrom) -> str:
    """Resout un import relatif en nom de module absolu.

    Sans cette resolution, `from ..couture.sapgui import SapGui` passerait
    toutes les frontieres sans un bruit — et c'est la forme la plus naturelle
    a l'interieur d'un paquet. Une regle d'architecture aveugle a la moitie
    des imports ne vaut rien.
    """
    if noeud.level == 0:
        return noeud.module or ""

    paquet = list(chemin.relative_to(RACINE).parts[:-1])
    remonte = noeud.level - 1
    if remonte:
        paquet = paquet[:-remonte] if remonte <= len(paquet) else []
    return ".".join([*paquet, noeud.module] if noeud.module else paquet)


def imports(chemin: Path) -> list[tuple[str, int, bool]]:
    """(module importe, ligne, sous TYPE_CHECKING) pour chaque import."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"), str(chemin))
    differes = _lignes_sous_type_checking(arbre)
    trouves: list[tuple[str, int, bool]] = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            for alias in noeud.names:
                trouves.append((alias.name, noeud.lineno, noeud.lineno in differes))
        elif isinstance(noeud, ast.ImportFrom):
            nom = _absolu(chemin, noeud)
            if nom:
                trouves.append((nom, noeud.lineno, noeud.lineno in differes))
    return trouves


class TestFrontiereSAP(unittest.TestCase):

    def test_paquet_present(self):
        """Sans ce controle, les tests de frontiere passeraient a jamais a vide."""
        self.assertTrue(PAQUET.is_dir(), f"{PAQUET} absent")

    def test_seul_le_module_de_couture_importe_sap(self):
        for module in modules_python(PAQUET):
            for importe, ligne, _ in imports(module):
                racine_importee = importe.split(".")[0]
                if racine_importee not in MODULES_SAP:
                    continue
                with self.subTest(module=str(module.relative_to(RACINE)), ligne=ligne):
                    self.assertEqual(
                        module, MODULE_SAP_AUTORISE,
                        f"{module.relative_to(RACINE)}:{ligne} importe {importe!r}. "
                        f"Seul {MODULE_SAP_AUTORISE.relative_to(RACINE)} y est autorise (3.4).")


class TestFrontiereControleur(unittest.TestCase):

    def test_moteur_et_pipeline_ne_touchent_pas_la_couture(self):
        for couche in COUCHES_SANS_COUTURE:
            for module in modules_python(PAQUET / couche):
                for importe, ligne, differe in imports(module):
                    if differe:
                        continue        # annotation seule, aucune dependance a l'execution
                    if not importe.startswith("falcon.couture"):
                        continue
                    with self.subTest(module=str(module.relative_to(RACINE)), ligne=ligne):
                        self.fail(
                            f"{module.relative_to(RACINE)}:{ligne} importe {importe!r}. "
                            f"La couche {couche!r} passe par le controleur, qui porte "
                            f"les gardes : une pipeline ne peut pas les contourner (5.2).")


class TestFrontierePipeline(unittest.TestCase):

    def test_une_pipeline_ne_nomme_aucun_driver(self):
        """Ne pouvant nommer aucun driver, elle ne peut en desactiver la garde."""
        for couche in COUCHES_SANS_CONTROLEUR:
            for module in modules_python(PAQUET / couche):
                for importe, ligne, differe in imports(module):
                    if differe:
                        continue
                    if not importe.startswith(("falcon.controleur", "falcon.couture")):
                        continue
                    with self.subTest(module=str(module.relative_to(RACINE)), ligne=ligne):
                        self.fail(
                            f"{module.relative_to(RACINE)}:{ligne} importe {importe!r}. "
                            f"La couche {couche!r} declare une intention ; elle ne "
                            f"doit pouvoir nommer aucun driver (5.2).")


class TestFrontiereANSI(unittest.TestCase):
    """Les sequences ANSI ne sortent ni par un litteral, ni par un import."""

    def test_le_module_des_sequences_existe(self):
        """Sans ce controle, les deux tests ci-dessous passeraient a vide."""
        self.assertTrue(MODULE_ANSI_AUTORISE.is_file(),
                        f"{MODULE_ANSI_AUTORISE} absent")

    def test_aucun_litteral_de_sequence_hors_du_module_dedie(self):
        """Sur les litteraux, pas sur le fichier : le mot « ANSI » ecrit dans
        un commentaire n'est pas une sequence ANSI."""
        for module in modules_python(PAQUET):
            if module == MODULE_ANSI_AUTORISE:
                continue
            arbre = ast.parse(module.read_text(encoding="utf-8"), str(module))
            for noeud in ast.walk(arbre):
                if not (isinstance(noeud, ast.Constant)
                        and isinstance(noeud.value, str)):
                    continue
                with self.subTest(module=str(module.relative_to(RACINE)),
                                  ligne=noeud.lineno):
                    self.assertNotIn(
                        "\x1b", noeud.value,
                        f"{module.relative_to(RACINE)}:{noeud.lineno} porte "
                        f"une sequence d'echappement. Seul "
                        f"{MODULE_ANSI_AUTORISE.relative_to(RACINE)} en ecrit.")

    def test_seul_un_module_importe_les_sequences(self):
        """La regle que le scan de litteraux ne peut PAS tenir.

        `chr(27) + "["` ne contient aucun `\x1b` litteral : le scan ne
        broncherait pas. Ce qu'on ne peut pas cacher, c'est l'import — un
        module qui veut poser une sequence doit nommer celui qui les fabrique.
        """
        for module in modules_python(PAQUET):
            if module in IMPORTEURS_ANSI_AUTORISES:
                continue
            for importe, ligne, differe in imports(module):
                if differe:
                    continue
                if not importe.endswith("toile.sequences"):
                    continue
                with self.subTest(module=str(module.relative_to(RACINE)),
                                  ligne=ligne):
                    self.fail(
                        f"{module.relative_to(RACINE)}:{ligne} importe "
                        f"{importe!r}. Les sequences se confinent dans "
                        f"{MODULE_ANSI_AUTORISE.relative_to(RACINE)}, et seuls "
                        f"{sorted(c.name for c in IMPORTEURS_ANSI_AUTORISES)} "
                        f"y touchent.")

    def test_aucun_module_interdit_n_est_importe(self):
        """Le refus de `curses` cesse d'etre une prose.

        La CI est Linux, ou `curses` s'importe tres bien. Un ecran qui
        l'utiliserait passerait donc au vert ici et mourrait a l'import sur
        Windows — la seule machine ou SAP GUI existe, donc la seule ou FALCON
        sert.
        """
        for module in modules_python(PAQUET):
            for importe, ligne, differe in imports(module):
                racine_importee = importe.split(".")[0]
                if racine_importee not in MODULES_INTERDITS:
                    continue
                with self.subTest(module=str(module.relative_to(RACINE)),
                                  ligne=ligne, importe=importe):
                    self.fail(
                        f"{module.relative_to(RACINE)}:{ligne} importe "
                        f"{importe!r}, qui est refuse : voir "
                        f"MODULES_INTERDITS. Un import differe sous "
                        f"TYPE_CHECKING ne le sauverait pas non plus.")


class TestFrontiereToile(unittest.TestCase):

    def test_ni_l_exploration_ni_le_moteur_ne_connaissent_la_toile(self):
        """Celui qui PEINT importe celui qui EMET, jamais l'inverse.

        Un parcours qui saurait a qui il parle deviendrait intestable sans
        terminal, ce qu'il n'est pas aujourd'hui — et le rendu se mettrait a
        dependre de l'ERP.
        """
        for couche in COUCHES_SANS_TOILE:
            for module in modules_python(PAQUET / couche):
                for importe, ligne, differe in imports(module):
                    if differe:
                        continue
                    if not importe.startswith("falcon.toile"):
                        continue
                    with self.subTest(module=str(module.relative_to(RACINE)),
                                      ligne=ligne):
                        self.fail(
                            f"{module.relative_to(RACINE)}:{ligne} importe "
                            f"{importe!r}. La couche {couche!r} EMET des "
                            f"faits ; c'est l'afficheur qui l'importe, et "
                            f"jamais le contraire.")


if __name__ == "__main__":
    unittest.main()
