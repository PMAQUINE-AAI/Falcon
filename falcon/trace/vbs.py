"""Lecture d'un enregistrement du SAP GUI Recorder.

Deux entrees, deux contrats, et la difference est deliberee.

`lire` est **stricte** : une ligne dont la forme n'est reconnue par rien fait
echouer la lecture, elle n'est pas ignoree. C'est la seule facon d'apprendre ce
qu'on ne sait pas encore lire. Elle rend une `Trace`, dont l'existence vaut
donc certificat que chaque ligne a ete appariee.

`inventorier` est tolerante, et rend un `Inventaire` — un type qui ne contient
aucun geste. Une trace a moitie comprise ne peut donc pas etre rejouee par
inadvertance : pour obtenir des gestes, il faut passer par la lecture stricte,
qui aura echoue.

**L'encodage est detecte puis inscrit dans le resultat, jamais devine en
silence.** La trace observee est en UTF-16LE avec BOM et fins de ligne CRLF ;
un autre poste ou une autre version pourra en produire une autre, et le jour
ou une lecture ira de travers, le rapport dira sous quel encodage elle a ete
lue.

**Le prologue est reconnu explicitement.** Les quatre blocs `If Not
IsObject(...)` que le recorder pose en tete ne sont pas ecartes parce qu'ils
« ne ressemblent pas a un geste » : ils sont apparies par des motifs nommes.
La difference se voit le jour ou une ligne inattendue s'y glisse — elle
echoue, au lieu de disparaitre dans un filtre fourre-tout.
"""

from __future__ import annotations

import re
from pathlib import Path

from .modele import (
    AFFECTATION, APPEL, APPEL_ARGUMENT, FENETRE_RACINE, VERBES, Geste,
    Inventaire, Trace, TraceInvalide,
)

#: Encodages refuses, mais reconnus — et refuses PAR LEUR NOM.
#:
#: `FF FE 00 00` commence par la meme paire d'octets que l'UTF-16LE. Lu comme
#: tel, un fichier UTF-32LE se decode sans lever, en semant des caracteres nuls
#: partout : le parseur n'apparierait plus rien et accuserait la trace. Le cas
#: est peu probable ; le diagnostic qu'il produirait serait faux, et c'est ca
#: qui justifie les quatre lignes.
REFUSES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
)

#: Encodages reconnus par leur marque d'ordre des octets.
BOMS: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
    (b"\xef\xbb\xbf", "utf-8"),
)

#: Encodage suppose en l'absence de BOM. Ecrit dans le resultat comme tous les
#: autres : « suppose » doit rester lisible dans le rapport.
SANS_BOM = "utf-8"

#: Lignes de prologue posees par le recorder. Chacune est nommee, pour qu'une
#: ligne etrangere au prologue ne s'y fonde pas.
PROLOGUE: tuple[re.Pattern[str], ...] = (
    re.compile(r"If\s+(?:Not\s+)?IsObject\(\w+\)\s+Then"),
    re.compile(r"End\s+If"),
    re.compile(r"Set\s+\w+\s*=\s*\S.*"),
    re.compile(r"WScript\.ConnectObject\s+\w+\s*,\s*\S.*"),
)

#: `session.findById("<cible>").<verbe><reste>`
GESTE = re.compile(
    r'(?P<retrait>[ \t]*)'
    r'session\.findById\((?P<cible>"(?:[^"]|"")*")\)'
    r'\.(?P<verbe>[A-Za-z_][A-Za-z0-9_]*)'
    r'(?P<reste>.*)$'
)

#: Un commentaire VBScript. Reconnu, donc compte — pas avale par un filtre.
COMMENTAIRE = re.compile(r"[ \t]*'.*")

_AFFECTE = re.compile(r"[ \t]*=[ \t]*(?P<litteral>\S.*)$")
_ARGUMENT = re.compile(r"[ \t]+(?P<litteral>\S.*)$")
_ENTIER = re.compile(r"-?\d+")
_CHAINE = re.compile(r'"(?:[^"]|"")*"')

_COUPURE = re.compile(r"\r\n|\r|\n")


# -- decodage --------------------------------------------------------------

def decoder(octets: bytes) -> tuple[str, str, bool]:
    """(texte, encodage, bom present) — sans jamais deviner en silence."""
    for marque, encodage in REFUSES:
        if octets.startswith(marque):
            raise TraceInvalide(
                f"BOM {encodage} : encodage non pris en charge. Aucune trace "
                f"du recorder n'en a produit ; le lire comme de l'UTF-16 "
                f"donnerait un texte truffe de caracteres nuls et un "
                f"diagnostic faux")
    for marque, encodage in BOMS:
        if octets.startswith(marque):
            reste = octets[len(marque):]
            try:
                return reste.decode(encodage), encodage, True
            except UnicodeDecodeError as erreur:
                raise TraceInvalide(
                    f"BOM {encodage} present, mais le contenu ne s'y decode "
                    f"pas ({erreur})") from erreur
    try:
        return octets.decode(SANS_BOM), SANS_BOM, False
    except UnicodeDecodeError as erreur:
        raise TraceInvalide(
            f"aucun BOM, et le contenu ne se decode pas en {SANS_BOM} "
            f"({erreur}). Preciser l'encodage plutot que le deviner") from erreur


def decouper(texte: str) -> tuple[list[str], str]:
    """(lignes sans leur fin, style de fin de ligne).

    Decoupage sur les trois fins de ligne reelles, pas sur `splitlines` : ce
    dernier coupe aussi sur U+2028 et consorts, qui peuvent legitimement se
    trouver DANS un litteral de chaine.
    """
    morceaux = _COUPURE.split(texte)
    fins = _COUPURE.findall(texte)
    if fins and morceaux and morceaux[-1] == "":
        morceaux = morceaux[:-1]        # le fichier se termine par une fin de ligne
    distinctes = set(fins)
    if not distinctes:
        style = ""
    elif len(distinctes) == 1:
        style = next(iter(distinctes))
    else:
        style = "mixte"
    return morceaux, style


# -- litteraux -------------------------------------------------------------

def litteral(brut: str) -> str | int | bool:
    """Un litteral VBScript, dans son type.

    Trois types, et trois seulement, releves sur la trace : chaine entre
    guillemets, entier nu, booleen nu en minuscules. `True` capitalise est
    valide en VBScript mais n'a jamais ete observe : il echoue, pour qu'on
    l'apprenne de la premiere trace qui en contiendra plutot que d'un rejeu
    de travers.
    """
    if brut == "true":
        return True
    if brut == "false":
        return False
    if _ENTIER.fullmatch(brut):
        return int(brut)
    if _CHAINE.fullmatch(brut):
        # `""` a l'interieur d'une chaine est un guillemet echappe ; les `""`
        # de la trace observee sont, eux, des chaines vides.
        return brut[1:-1].replace('""', '"')
    raise TraceInvalide(
        f"litteral non reconnu : {brut!r}. Attendu une chaine entre "
        f"guillemets, un entier, ou true/false")


# -- appariement d'une ligne ----------------------------------------------

def _geste(ligne: str, rang: int, ordre: int) -> Geste:
    trouve = GESTE.fullmatch(ligne)
    if trouve is None:                          # pragma: no cover - appelant
        raise TraceInvalide(f"ligne {rang} : pas un geste")

    verbe = trouve.group("verbe")
    reste = trouve.group("reste")

    if reste == "":
        forme, valeur = APPEL, None
    elif (affecte := _AFFECTE.fullmatch(reste)) is not None:
        forme, valeur = AFFECTATION, litteral(affecte.group("litteral"))
    elif (argument := _ARGUMENT.fullmatch(reste)) is not None:
        forme, valeur = APPEL_ARGUMENT, litteral(argument.group("litteral"))
    else:
        raise TraceInvalide(
            f"ligne {rang} : apres {verbe!r}, {reste!r} ne ressemble a aucune "
            f"des trois formes connues (appel nu, « = valeur », « valeur »)")

    attendue = VERBES.get(verbe)
    if attendue is not None and attendue != forme:
        raise TraceInvalide(
            f"ligne {rang} : {verbe!r} est un(e) {attendue}, employe ici "
            f"comme {forme}. Aucun verbe n'apparait sous deux formes dans "
            f"une trace du recorder : lire celle-ci comme l'autre rejouerait "
            f"autre chose que ce qui a ete enregistre")

    cible = litteral(trouve.group("cible"))
    if not FENETRE_RACINE.match(str(cible)):
        raise TraceInvalide(
            f"ligne {rang} : la cible {cible!r} n'est pas enracinee dans une "
            f"fenetre `wnd[N]`. La fenetre d'un geste n'est pas un ornement : "
            f"c'est ce que la garde des fenetres imprevues compare. Un geste "
            f"sans fenetre determinable se comparerait a tout et a rien")

    return Geste(
        ordre=ordre, ligne=rang, texte_source=ligne,
        retrait=trouve.group("retrait"),
        cible=str(cible), verbe=verbe, forme=forme, valeur=valeur,
    )


def _prologue(ligne: str) -> bool:
    nu = ligne.strip()
    return any(motif.fullmatch(nu) for motif in PROLOGUE)


# -- lecture ---------------------------------------------------------------

def _octets(source: str | Path | bytes) -> tuple[bytes, str]:
    if isinstance(source, bytes):
        return source, "<octets>"
    chemin = Path(source)
    if not chemin.exists():
        raise TraceInvalide(f"trace introuvable : {chemin}")
    return chemin.read_bytes(), str(chemin)


def lire(source: str | Path | bytes) -> Trace:
    """Lecture stricte. Une ligne non appariee fait echouer la lecture.

    Rendre une `Trace` amputee serait le pire des deux mondes : on croirait
    tenir l'enregistrement, et il en manquerait un morceau qu'aucune erreur
    n'aurait signale.
    """
    octets, nom = _octets(source)
    texte, encodage, bom = decoder(octets)
    lignes, style = decouper(texte)

    gestes: list[Geste] = []
    prologue: list[int] = []
    commentaires: list[int] = []
    vides: list[int] = []

    for rang, brute in enumerate(lignes, start=1):
        ligne = brute.rstrip()
        if not ligne:
            vides.append(rang)
        elif GESTE.fullmatch(ligne):
            gestes.append(_geste(ligne, rang, len(gestes) + 1))
        elif _prologue(ligne):
            prologue.append(rang)
        elif COMMENTAIRE.fullmatch(ligne):
            commentaires.append(rang)
        else:
            raise TraceInvalide(
                f"{nom}, ligne {rang} : forme inconnue.\n  {ligne}\n"
                f"Le parseur refuse d'ignorer une ligne qu'il ne comprend "
                f"pas. Passer `inventaire` sur la trace pour voir tout ce "
                f"qu'elle contient d'inconnu d'un coup")

    return Trace(
        source=nom, encodage=encodage, bom=bom, fin_de_ligne=style,
        lignes=len(lignes), gestes=tuple(gestes), prologue=tuple(prologue),
        commentaires=tuple(commentaires), vides=tuple(vides),
    )


def inventorier(source: str | Path | bytes) -> Inventaire:
    """Lecture tolerante, pour le rapport de couverture.

    Rend un `Inventaire`, qui ne porte aucun geste : ce qui se decouvre ici ne
    peut pas etre rejoue. Les lignes non appariees y figurent **verbatim** —
    c'est ce qu'on veut lire pour etendre le parseur.
    """
    octets, nom = _octets(source)
    texte, encodage, bom = decoder(octets)
    lignes, style = decouper(texte)

    decompte: dict[str, int] = {}
    inconnues: list[tuple[int, str]] = []
    inconnus: set[str] = set()
    gestes = prologue = commentaires = vides = 0

    for rang, brute in enumerate(lignes, start=1):
        ligne = brute.rstrip()
        if not ligne:
            vides += 1
            continue
        if GESTE.fullmatch(ligne):
            try:
                geste = _geste(ligne, rang, gestes + 1)
            except TraceInvalide:
                inconnues.append((rang, brute))
                continue
            gestes += 1
            decompte[geste.verbe] = decompte.get(geste.verbe, 0) + 1
            if not geste.connu:
                inconnus.add(geste.verbe)
        elif _prologue(ligne):
            prologue += 1
        elif COMMENTAIRE.fullmatch(ligne):
            commentaires += 1
        else:
            inconnues.append((rang, brute))

    return Inventaire(
        source=nom, encodage=encodage, bom=bom, fin_de_ligne=style,
        lignes=len(lignes), gestes=gestes, prologue=prologue,
        commentaires=commentaires, vides=vides,
        par_verbe=tuple(sorted(decompte.items())),
        verbes_inconnus=tuple(sorted(inconnus)),
        inconnues=tuple(inconnues),
    )
