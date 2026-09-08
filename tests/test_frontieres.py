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
COUCHES_SANS_COUTURE = ("moteur", "pipeline", "tableur", "exploration")

# Une pipeline ne peut nommer aucun type de driver, gardé ou non. Ne pouvant
# pas en manipuler un, elle ne peut pas non plus desactiver une garde : la
# regle du 5.2 devient une contrainte d'import plutot qu'une convention.
COUCHES_SANS_CONTROLEUR = ("pipeline", "trace", "tableur")


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


if __name__ == "__main__":
    unittest.main()
