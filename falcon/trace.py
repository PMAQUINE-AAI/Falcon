"""Lecture d'une trace .vbs du SAP GUI Recorder : une liste d'étapes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SET = {"text", "key", "selected"}
SELECT = {"selectedRows", "selectedNode", "selectedColumn", "currentCellRow", "currentCellColumn"}

_LIGNE = re.compile(
    r'\s*session\.findById\("(?P<id>(?:[^"]|"")*)"\)'
    r'(?:\.(?P<verbe>\w+))?'
    r'(?:\s*=\s*(?P<affecte>\S.*?)|\s+(?P<argument>\S.*?))?\s*$'
)
_CHAINE = re.compile(r'"((?:[^"]|"")*)"')


@dataclass(frozen=True)
class Etape:
    id: str
    verbe: str  # propriété ou méthode après findById(...).
    action: str  # set, press, vkey, select, other
    valeur: str | None
    ligne: int


def _decoder(octets: bytes) -> str:
    if octets.startswith((b"\xff\xfe", b"\xfe\xff")):
        return octets.decode("utf-16")
    return octets.decode("utf-8-sig")


def _litteral(brut: str) -> str:
    m = _CHAINE.fullmatch(brut)
    return m.group(1).replace('""', '"') if m else brut


def lire_trace(chemin: str | Path) -> list[Etape]:
    texte = _decoder(Path(chemin).read_bytes())
    etapes: list[Etape] = []
    for numero, ligne in enumerate(texte.splitlines(), 1):
        if "findById" not in ligne:
            continue
        m = _LIGNE.fullmatch(ligne)
        if not m or not m["verbe"]:
            raise ValueError(f"ligne {numero} non reconnue : {ligne.strip()}")
        verbe = m["verbe"]
        brut = m["affecte"] or m["argument"]
        valeur = _litteral(brut) if brut else None
        if verbe == "press":
            action = "press"
        elif verbe == "sendVKey":
            action = "vkey"
        elif verbe in SET and m["affecte"]:
            action = "set"
        elif verbe in SELECT and m["affecte"]:
            action = "select"
        else:
            action = "other"
        etapes.append(Etape(m["id"].replace('""', '"'), verbe, action, valeur, numero))
    return etapes
