"""Verification de la documentation elle-meme.

Un document qui se perime sans bruit est de la meme famille que les bugs que
ce projet traque : rien ne leve, et le lecteur applique une consigne fausse.
Deux garde-fous :

  - les blocs `python` du guide sont EXECUTES, avec leurs assertions ;
  - tout chemin de fichier cite dans la documentation doit exister.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

# Documents dont les blocs python sont executes. Les autres (HARNESS.md,
# TRAPS.md, README.md) portent des fragments d'illustration volontairement
# incomplets : les executer demanderait de les alourdir d'un contexte qui
# nuirait a leur lecture. Ils restent controles pour leurs chemins.
DOCUMENTS_EXECUTES = ["docs/GUIDE.md"]

MARQUEUR_SKIP = "# guide: skip"

BLOC = re.compile(r"^```(\w+)[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
BACKTICK = re.compile(r"`([^`\n]+)`")
LIEN = re.compile(r"\]\(([^)\s]+)\)")
CHEMIN = re.compile(r"^[A-Za-z0-9_./-]+\.(?:py|md|yaml|yml|toml|cfg|json|txt)$")
DOSSIER = re.compile(r"^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*/$")


def documents() -> list[Path]:
    """Tous les markdown du depot, hors dossiers techniques."""
    return sorted(p for p in RACINE.rglob("*.md")
                  if not any(part.startswith(".") for part in p.parts))


def blocs(texte: str, langage: str) -> list[str]:
    return [corps for lang, corps in BLOC.findall(texte) if lang == langage]


def _ligne_fautive(erreur: BaseException, code: str, origine: str) -> str:
    """Retrouve la ligne du bloc qui a echoue.

    Un `assert` nu ne porte aucun message : sans cette ligne, le lecteur
    saurait qu'un exemple est faux mais pas lequel.
    """
    import traceback

    cadres = [c for c in traceback.extract_tb(erreur.__traceback__)
              if c.filename == origine]
    if not cadres:
        return "  (ligne non localisee)"
    numero = cadres[-1].lineno
    lignes = code.splitlines()
    source = lignes[numero - 1].strip() if 0 < numero <= len(lignes) else "?"
    return f"  ligne {numero} du bloc : {source}"


class TestBlocsExecutables(unittest.TestCase):
    """Chaque exemple du guide est une assertion, et elle doit passer."""

    def test_documents_executes_presents(self):
        for relatif in DOCUMENTS_EXECUTES:
            self.assertTrue((RACINE / relatif).exists(), relatif)

    def test_blocs_python_du_guide_sexecutent(self):
        for relatif in DOCUMENTS_EXECUTES:
            document = RACINE / relatif
            morceaux = blocs(document.read_text(encoding="utf-8"), "python")
            self.assertGreater(len(morceaux), 5,
                               f"{relatif} : trop peu de blocs, extraction suspecte")

            # Un espace de noms par document : les blocs se lisent dans l'ordre,
            # comme le lecteur les lit.
            espace = {"__name__": f"doc:{relatif}"}
            for numero, code in enumerate(morceaux, start=1):
                if code.lstrip().startswith(MARQUEUR_SKIP):
                    continue
                with self.subTest(document=relatif, bloc=numero):
                    origine = f"{relatif}#bloc{numero}"
                    try:
                        exec(compile(code, origine, "exec"), espace)
                    except Exception as erreur:      # noqa: BLE001 - on re-emet
                        self.fail(f"{relatif}, bloc {numero} : "
                                  f"{type(erreur).__name__}: {erreur}\n"
                                  f"{_ligne_fautive(erreur, code, origine)}")

    def test_aucun_bloc_marque_skip_sans_justification(self):
        """Un bloc non execute n'est pas une garantie : il doit rester rare."""
        for relatif in DOCUMENTS_EXECUTES:
            texte = (RACINE / relatif).read_text(encoding="utf-8")
            ignores = [c for c in blocs(texte, "python")
                       if c.lstrip().startswith(MARQUEUR_SKIP)]
            self.assertEqual(
                ignores, [],
                f"{relatif} : bloc non execute — le guide annonce qu'il n'y en a aucun")


class TestReferencesDeFichiers(unittest.TestCase):
    """Un chemin cite qui n'existe plus envoie le lecteur dans le vide."""

    @staticmethod
    def _candidats(document: Path) -> set[str]:
        texte = document.read_text(encoding="utf-8")
        trouves = set(BACKTICK.findall(texte)) | set(LIEN.findall(texte))
        for commande in blocs(texte, "bash"):
            trouves.update(commande.split())
        return trouves

    def _resoudre(self, document: Path, cible: str) -> bool:
        """Relatif au depot, relatif au document, ou par nom de fichier."""
        if (RACINE / cible).exists() or (document.parent / cible).exists():
            return True
        if "/" not in cible:      # nom nu : accepte s'il existe quelque part
            return any(p for p in RACINE.rglob(cible)
                       if not any(part.startswith(".") for part in p.parts))
        return False

    def test_chemins_cites_existent(self):
        verifies = 0
        for document in documents():
            for cible in self._candidats(document):
                if not (CHEMIN.match(cible) or DOSSIER.match(cible)):
                    continue
                if cible.startswith(("http", "#")):
                    continue
                verifies += 1
                with self.subTest(document=document.name, cible=cible):
                    self.assertTrue(
                        self._resoudre(document, cible),
                        f"{document.relative_to(RACINE)} cite {cible!r}, introuvable")
        self.assertGreater(verifies, 10, "extraction des chemins suspecte")

    def test_guide_reference_depuis_le_readme(self):
        readme = (RACINE / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/GUIDE.md", readme,
                      "le guide doit etre atteignable depuis la page d'accueil")


if __name__ == "__main__":
    unittest.main()
