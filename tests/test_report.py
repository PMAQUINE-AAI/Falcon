import json
import logging
import zipfile

import pytest

from falcon.report import Rapport


def test_crash_produit_le_zip(tmp_path):
    entree = tmp_path / "recette.yaml"
    entree.write_text("a: 1")
    r = Rapport("run", tmp_path / "rapports")
    with pytest.raises(ValueError):
        with r:
            r.ajouter(entree)
            r.ajouter(tmp_path / "absent.csv")
            r.environnement(sap_gui="8.0")
            logging.getLogger("falcon.sap").debug("appel SAP")
            raise ValueError("boum")
    with zipfile.ZipFile(r.chemin_zip) as z:
        assert set(z.namelist()) == {"falcon.log", "environnement.json", "recette.yaml"}
        log = z.read("falcon.log").decode()
        assert "Traceback" in log and "boum" in log and "appel SAP" in log
        assert "absent.csv" in log
        assert json.loads(z.read("environnement.json"))["sap_gui"] == "8.0"
    assert not logging.getLogger("falcon").handlers
