"""Commandes en ligne. Aucune logique métier."""
import argparse
import logging
import tempfile
from pathlib import Path

from falcon import report, sap

log = logging.getLogger("falcon.cli")

PROFONDEUR = 3
TEXTE_MAX = 40


def _arbre(objet, niveau: int, lignes: list[str]) -> None:
    # Id, Type, Text, Children (Count, indexation) : non vérifié sur SAP
    try:
        texte = str(objet.Text)[:TEXTE_MAX]
    except Exception:
        texte = ""
    lignes.append(f"{'  ' * niveau}{objet.Id}\t{objet.Type}\t{texte}")
    if niveau >= PROFONDEUR - 1:
        return
    enfants = objet.Children
    for i in range(enfants.Count):
        try:
            _arbre(enfants(i), niveau + 1, lignes)
        except Exception as e:
            log.warning("arborescence : enfant %d de %s illisible : %s", i, objet.Id, e)


def _smoke() -> int:
    with report.Rapport("smoke") as rapport:
        try:
            s = sap.attacher()
            log.info("infos %s", s.infos())
            log.info("titre %s", s.titre())
            log.info("statut %s", s.statut())
            log.info("fenetres %s", s.fenetres())
            lignes: list[str] = []
            try:
                _arbre(s.objet("wnd[0]/usr"), 0, lignes)
            except Exception as e:
                log.warning("arborescence illisible : %s", e)
            log.info("arborescence wnd[0]/usr\n%s", "\n".join(lignes))
            fichier = Path(tempfile.mkdtemp()) / "smoke.txt"
            fichier.write_text("\n".join(lignes), encoding="utf-8")
            rapport.ajouter(fichier)
        except Exception as e:
            print(f"smoke KO : {type(e).__name__}: {e}")
            raise
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="falcon")
    p.add_subparsers(dest="commande", required=True).add_parser(
        "smoke", help="lecture seule : attache SAP et décrit l'écran")
    p.parse_args(argv)
    try:
        return _smoke()
    except Exception:
        return 1
