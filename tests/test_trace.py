import pytest

from falcon.trace import Etape, lire_trace

VBS = (
    'If Not IsObject(session) Then\n'
    '   Set session = connection.Children(0)\n'
    'End If\n'
    'session.findById("wnd[0]/tbar[0]/okcd").text = "a ""b"" c"\n'
    'session.findById("wnd[0]").sendVKey 0\n'
    'session.findById("wnd[0]/tbar[1]/btn[8]").press\n'
    'session.findById("wnd[0]/usr/shell").selectedRows = "0"\n'
    'session.findById("wnd[0]/usr/shell").doubleClickCurrentCell\n'
)
ATTENDU = [
    Etape("wnd[0]/tbar[0]/okcd", "text", "set", 'a "b" c', 4),
    Etape("wnd[0]", "sendVKey", "vkey", "0", 5),
    Etape("wnd[0]/tbar[1]/btn[8]", "press", "press", None, 6),
    Etape("wnd[0]/usr/shell", "selectedRows", "select", "0", 7),
    Etape("wnd[0]/usr/shell", "doubleClickCurrentCell", "other", None, 8),
]


@pytest.mark.parametrize("octets", [
    VBS.encode("utf-8"), VBS.encode("utf-8-sig"), VBS.encode("utf-16"),
])
def test_encodages(tmp_path, octets):
    f = tmp_path / "t.vbs"
    f.write_bytes(octets)
    assert lire_trace(f) == ATTENDU


def test_ligne_inconnue(tmp_path):
    f = tmp_path / "t.vbs"
    f.write_text('session.findById("a").text = "x"\nsession.findById("b") ???\n')
    with pytest.raises(ValueError, match="ligne 2"):
        lire_trace(f)


def test_vraie_trace():
    etapes = lire_trace("exemples/traces/megatrace_2026-09.vbs")
    assert len(etapes) > 0
    assert etapes[0] == Etape("wnd[0]", "maximize", "other", None, 15)
    assert etapes[1] == Etape("wnd[0]/tbar[0]/okcd", "text", "set", "/nIH06", 16)
