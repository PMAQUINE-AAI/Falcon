import csv

import pytest

from falcon.journal import Journal, lire


def test_ko_relu_donne_la_ligne_d_origine(tmp_path):
    entetes = ["Matériel", "Qté", "Note"]
    ligne = {"Matériel": "Écrou; M8", "Qté": "", "Note": "à revoir"}
    j = Journal(tmp_path, entetes)
    j.ecrire(1, {"Matériel": "A", "Qté": "2", "Note": "x"}, "OK")
    j.ecrire(2, ligne, "KO", "popup")
    with open(j.chemin_ko, encoding="utf-8-sig", newline="") as f:
        assert list(csv.DictReader(f, delimiter=";")) == [ligne]
    assert j.chemin_ko.read_bytes().startswith(b"\xef\xbb\xbf")
    lues = lire(j.chemin_journal)
    assert [(e["numero"], e["statut"]) for e in lues] == [(1, "OK"), (2, "KO")]
    assert lues[1]["donnees"] == ligne


def test_statut_invalide(tmp_path):
    with pytest.raises(ValueError):
        Journal(tmp_path, ["a"]).ecrire(1, {"a": "1"}, "PEUT-ETRE")
