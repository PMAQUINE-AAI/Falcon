"""Journal par ligne (JSONL) et CSV des KO au format d'entrée, rejouable tel quel."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

STATUTS = ("OK", "KO")
NOM_JOURNAL = "journal.jsonl"
NOM_KO = "ko.csv"


class Journal:
    def __init__(self, dossier: Path, entetes: list[str]):
        self.dossier = Path(dossier)
        self.entetes = list(entetes)
        self.chemin_journal = self.dossier / NOM_JOURNAL
        self.chemin_ko = self.dossier / NOM_KO
        self.dossier.mkdir(parents=True, exist_ok=True)
        if not self.chemin_ko.exists():
            # BOM + « ; » : Excel français ouvre le fichier sans assistant d'import.
            with open(self.chemin_ko, "w", encoding="utf-8-sig", newline="") as f:
                self._csv(f).writerow(self.entetes)

    def _csv(self, f):
        return csv.writer(f, delimiter=";")

    def ecrire(self, numero: int, donnees: dict[str, str], statut: str, message: str = "") -> None:
        if statut not in STATUTS:
            raise ValueError(f"statut invalide : {statut!r} (attendu : OK ou KO)")
        ligne = {
            "horodatage": datetime.now().isoformat(timespec="seconds"),
            "numero": numero,
            "statut": statut,
            "message": message,
            "donnees": donnees,
        }
        # Ouverture/fermeture à chaque ligne : rien n'est perdu en cas de crash.
        with open(self.chemin_journal, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        if statut == "KO":
            with open(self.chemin_ko, "a", encoding="utf-8", newline="") as f:
                self._csv(f).writerow([donnees.get(e, "") for e in self.entetes])


def lire(chemin: Path) -> list[dict]:
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]
