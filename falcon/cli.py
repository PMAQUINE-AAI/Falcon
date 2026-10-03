"""Commandes en ligne. Aucune logique métier."""
import argparse
import logging
import tempfile
from pathlib import Path

from falcon import report, sap

log = logging.getLogger("falcon.cli")

def _smoke() -> int:
    with report.Rapport("smoke") as rapport:
        try:
            s = sap.attacher()
            infos = s.infos()
            rapport.environnement(**infos)
            log.info("infos %s", infos)
            log.info("titre %s", s.titre())
            log.info("statut %s", s.statut())
            log.info("fenetres %s", s.fenetres())
            lignes: list[str] = []
            try:
                lignes = [f"{n['id']}\t{n['type']}\t{n['texte']}" for n in s.arbre("wnd[0]/usr")]
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
