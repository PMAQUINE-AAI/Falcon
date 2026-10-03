import pytest

from falcon.recipe import appliquer, depuis_trace, ecrire, lier, lire

TRACE = "exemples/traces/megatrace_2026-09.vbs"


def test_aller_retour_et_application(tmp_path):
    r = lier(depuis_trace(TRACE, "équipement"), 1, "poste")
    assert r.etapes[1].action == "set" and r.liaisons == {1: "poste"}
    f = tmp_path / "r.yaml"
    ecrire(r, f)
    assert "équipement" in f.read_text(encoding="utf-8")
    assert lire(f) == r
    etapes = appliquer(r, {"poste": "é42"})
    assert etapes[1].valeur == "é42"
    assert etapes[0] == r.etapes[0] and etapes[2:] == r.etapes[2:]


def test_lier_refuse_press():
    r = depuis_trace(TRACE, "x")
    i = next(i for i, e in enumerate(r.etapes) if e.action == "press")
    with pytest.raises(ValueError):
        lier(r, i, "c")


def test_colonne_absente():
    r = lier(depuis_trace(TRACE, "x"), 1, "poste")
    with pytest.raises(KeyError, match="poste"):
        appliquer(r, {"autre": "1"})
