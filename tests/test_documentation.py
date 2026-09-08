"""Coherence de la documentation FALCON.

Mecanisme repris de historique/tests/test_documentation.py, ou il a fait ses
preuves : tout chemin de fichier cite dans un document doit exister. Un
document qui envoie le lecteur sur un fichier disparu echoue sans bruit, comme
les defauts que ce projet traque par ailleurs.

Perimetre : les documents de la racine et de docs/. L'archive a sa propre
suite (python -m unittest discover -s historique/tests -t historique) et n'est
pas re-verifiee ici.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from falcon.pipeline import PipelineInvalide, charger

RACINE = Path(__file__).resolve().parent.parent

# L'archive se verifie elle-meme, avec sa propre racine.
DOSSIERS_IGNORES = {"historique"}

# Le backlog decrit du travail A VENIR : il cite forcement des chemins qui
# n'existent pas encore. L'y soumettre reviendrait a interdire de planifier.
DOCUMENTS_IGNORES = {"docs/BACKLOG_V1.md"}

BLOC = re.compile(r"^```(\w+)[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
BACKTICK = re.compile(r"`([^`\n]+)`")
LIEN = re.compile(r"\]\(([^)\s]+)\)")
CHEMIN = re.compile(r"^[A-Za-z0-9_./-]+\.(?:py|md|yaml|yml|toml|cfg|json|txt)$")
DOSSIER = re.compile(r"^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*/$")


def documents() -> list[Path]:
    retenus = []
    for chemin in sorted(RACINE.rglob("*.md")):
        parties = chemin.relative_to(RACINE).parts
        if any(p.startswith(".") for p in parties) or parties[0] in DOSSIERS_IGNORES:
            continue
        if str(chemin.relative_to(RACINE)) in DOCUMENTS_IGNORES:
            continue
        retenus.append(chemin)
    return retenus


def blocs(texte: str, langage: str) -> list[str]:
    return [corps for lang, corps in BLOC.findall(texte) if lang == langage]


def _blocs_yaml(markdown: str) -> list[str]:
    """Les blocs ```yaml d'un document, dans l'ordre.

    On ne se sert pas d'une bibliotheque markdown : le README est le SEUL
    document lu ici, sa syntaxe de bloc est celle-ci, et ajouter une
    dependance d'execution pour un test irait contre la regle « PyYAML seule
    dependance ».
    """
    blocs: list[str] = []
    courant: list[str] | None = None
    for ligne in markdown.splitlines():
        if courant is None:
            if ligne.strip() in ("```yaml", "```yml"):
                courant = []
            continue
        if ligne.strip() == "```":
            blocs.append("\n".join(courant) + "\n")
            courant = None
            continue
        courant.append(ligne)
    return blocs


class TestReferencesDeFichiers(unittest.TestCase):

    @staticmethod
    def _candidats(document: Path) -> set[str]:
        texte = document.read_text(encoding="utf-8")
        trouves = set(BACKTICK.findall(texte)) | set(LIEN.findall(texte))
        for commande in blocs(texte, "bash"):
            trouves.update(commande.split())
        return trouves

    def _resoudre(self, document: Path, cible: str) -> bool:
        return (RACINE / cible).exists() or (document.parent / cible).exists()

    def test_chemins_cites_existent(self):
        verifies = 0
        for document in documents():
            for cible in sorted(self._candidats(document)):
                if cible.startswith(("http", "#")):
                    continue
                if not (CHEMIN.match(cible) or DOSSIER.match(cible)):
                    continue
                verifies += 1
                with self.subTest(document=document.name, cible=cible):
                    self.assertTrue(
                        self._resoudre(document, cible),
                        f"{document.relative_to(RACINE)} cite {cible!r}, introuvable")
        self.assertGreater(verifies, 3, "extraction des chemins suspecte")

    def test_documents_ignores_existent(self):
        """Une exception qui designe un fichier disparu se perime en silence."""
        for relatif in DOCUMENTS_IGNORES:
            self.assertTrue((RACINE / relatif).exists(),
                            f"{relatif} est dans DOCUMENTS_IGNORES mais n'existe pas")

    def test_le_readme_connait_tous_les_modules(self):
        """Detecteur de derive : le README affirmait « Aucun code FALCON n'est
        ecrit » quatorze commits apres le premier module.

        Verifier l'existence des chemins cites ne suffisait pas — le defaut
        n'etait pas un chemin mort, c'etait une affirmation perimee. Cette
        regle-ci mord dans l'autre sens : tout sous-paquet livre doit etre
        nomme quelque part dans le README.
        """
        paquet = RACINE / "falcon"
        readme = (RACINE / "README.md").read_text(encoding="utf-8")
        livres = sorted(d.name for d in paquet.iterdir()
                        if d.is_dir() and (d / "__init__.py").exists())
        self.assertTrue(livres, "aucun sous-paquet : le detecteur ne mord pas")
        for nom in livres:
            with self.subTest(module=nom):
                self.assertIn(f"falcon/{nom}/", readme,
                              f"le module falcon/{nom}/ existe mais le README "
                              f"ne le mentionne pas")

    def test_CHAQUE_exemple_de_pipeline_du_README_se_CHARGE(self):
        """Le seul exemple YAML du README ne chargeait pas.

        Ses deux etapes ne declaraient ni `ecran:` ni `navigation_libre:`, que
        le chargeur EXIGE. Il n'etait donc pas seulement inexact : il
        enseignait l'omission exacte qui neutralise la garde d'identite, dans
        le document ou quelqu'un vient chercher comment ecrire sa premiere
        pipeline.

        Verifier qu'il charge est la seule facon de l'empecher de se perimer a
        nouveau — c'est l'argument du neutraliseur, applique a la
        documentation.
        """
        blocs = _blocs_yaml((RACINE / "README.md").read_text(encoding="utf-8"))
        pipelines = [b for b in blocs if "etapes:" in b]
        self.assertTrue(pipelines,
                        "aucun exemple de pipeline : le detecteur ne mord pas")

        for rang, bloc in enumerate(pipelines, start=1):
            with self.subTest(exemple=rang):
                with tempfile.TemporaryDirectory() as dossier:
                    chemin = Path(dossier) / "exemple.yaml"
                    chemin.write_text(bloc, encoding="utf-8")
                    try:
                        charger(chemin)
                    except PipelineInvalide as erreur:
                        self.fail(
                            f"l'exemple {rang} du README ne charge pas : "
                            f"{str(erreur).replace(str(chemin), 'README')}")

    def test_specification_presente(self):
        self.assertTrue((RACINE / "SPEC_FALCON.md").exists(),
                        "la specification est le document qui fait foi")


if __name__ == "__main__":
    unittest.main()
