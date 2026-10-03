"""Rapport d'exécution : un seul zip par exécution, même en cas de crash."""
import json
import logging
import os
import platform
import sys
import tempfile
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

log = logging.getLogger("falcon.report")


def _version() -> str:
    try:
        from falcon import __version__
        return __version__
    except ImportError:
        pass
    try:
        from importlib.metadata import version
        return version("falcon")
    except Exception:
        return "inconnue"


class Rapport:
    def __init__(self, commande: str, dossier: Path = Path("rapports")):
        self.commande = commande
        self.dossier = Path(dossier)
        self.chemin_zip: Path | None = None
        self._fichiers: list[tuple[Path, str]] = []
        self._infos: dict = {}
        self._handler: logging.Handler | None = None
        self._log = Path()

    def ajouter(self, chemin, nom: str | None = None) -> None:
        chemin = Path(chemin)
        self._fichiers.append((chemin, nom or chemin.name))

    def environnement(self, **infos) -> None:
        self._infos.update(infos)

    def __enter__(self):
        fd, nom = tempfile.mkstemp(prefix="falcon_", suffix=".log")
        self._log = Path(nom)
        h = logging.FileHandler(nom, encoding="utf-8")
        os.close(fd)
        h.setLevel(logging.DEBUG)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        racine = logging.getLogger("falcon")
        self._niveau = racine.level
        racine.setLevel(logging.DEBUG)
        racine.addHandler(h)
        self._handler = h
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            log.error("Exception non rattrapée\n%s",
                      "".join(traceback.format_exception(exc_type, exc, tb)))
        try:
            self._ecrire_zip()
        finally:
            racine = logging.getLogger("falcon")
            racine.removeHandler(self._handler)
            racine.setLevel(self._niveau)
            self._handler.close()
            self._log.unlink(missing_ok=True)
        print(f"Rapport : {self.chemin_zip}", file=sys.stderr)
        return False

    def _ecrire_zip(self) -> None:
        env = {"falcon": _version(), "python": sys.version,
               "platform": platform.platform(), **self._infos}
        presents = []
        for chemin, nom in self._fichiers:
            if chemin.is_file():
                presents.append((chemin, nom))
            else:
                log.warning("Fichier absent, non inclus : %s", chemin)
        self._handler.flush()
        horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dossier.mkdir(parents=True, exist_ok=True)
        base = f"falcon_{horodatage}_{self.commande}"
        zip_path = self.dossier / f"{base}.zip"
        n = 2
        while zip_path.exists():
            zip_path = self.dossier / f"{base}_{n}.zip"
            n += 1
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(self._log, "falcon.log")
            z.writestr("environnement.json",
                       json.dumps(env, indent=2, ensure_ascii=False, default=str))
            for chemin, nom in presents:
                z.write(chemin, nom)
        self.chemin_zip = zip_path
