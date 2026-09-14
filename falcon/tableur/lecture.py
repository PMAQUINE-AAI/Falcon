"""Lire les trois CSV du classeur, et refuser ce qu'un tableur abime.

**Pourquoi TROIS fichiers, et pas un.** Trois cardinalites : une pipeline a
une ligne de proprietes, N etapes, et M derogations rattachees a des etapes.
Les aplatir dans une seule feuille obligerait a repeter le nom de la pipeline
sur chaque ligne — et une cellule recopiee de travers y ferait deux pipelines
au lieu d'une, sans un mot.

**Les deux conventions qui portent tout le reste.**

*Les valeurs tapees dans SAP s'ecrivent entre crochets* — `[0100]`, `[on]`,
`[]`. Une cellule qui contient `[` et `]` n'est jamais un nombre pour Excel :
elle survit a la saisie, a l'enregistrement et au copier-coller quel que soit
le format de la colonne. `[]` rend la chaine vide exprimable, et distincte de
« pas de source ». Prescrire un format « Texte » ne suffirait pas : FALCON ne
voit jamais le classeur, et un `0100` deja mange par Excel est indiscernable
d'un `100` legitime — il n'y a plus rien a rattraper a la lecture.

*L'ecran tient dans UNE cellule* — `IA08::RIPLKO10::0100`, le jeton que
`falcon dictionnaire` produit deja et qu'on colle. Le XOR entre `ecran` et
`navigation_libre` devient ainsi INEXPRIMABLE au lieu d'etre valide : la
cellule porte un triplet, ou le mot `libre`. On ne peut pas declarer les deux,
donc on ne peut pas se les voir refuser.

**Et la colonne `rang`.** Cliquer sur un en-tete pour trier est le geste le
plus banal d'un tableur, et il reordonne les etapes en silence — ce qui, pour
une pipeline, change ce qui est tape et dans quel ordre. Le rang doit croitre
strictement. Les trous sont permis (on numerote de dix en dix pour pouvoir
inserer), les doublons non.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: L'ecran, en une cellule. Ni `/` — les noms de programme SAP en contiennent,
#: `/BCP/SAPLXXX` — ni `|`, que `donnees.lire` renifle comme delimiteur.
SEPARATEUR_ECRAN = "::"

#: Ce qu'on ecrit dans la colonne `ecran` d'une etape qui ne sait pas encore ou
#: elle atterrit. C'est l'autre branche du XOR, et la seule.
JETON_LIBRE = "libre"

#: Colonnes de `etapes.csv`. L'ordre est celui du classeur, et il compte pour
#: la relecture humaine ; la lecture, elle, va par NOM.
#: `colonne` et `colonnes` servent aux actions de grille : la premiere dit OU
#: chercher (`choisir`), la seconde CE QU'ON LIT (`extraire`). Elles sont
#: distinctes a dessein — le singulier designe une colonne, le pluriel une
#: liste — et l'en-tete etant verifie a l'EGALITE, un CSV exporte avant leur
#: arrivee est refuse bruyamment plutot que lu de travers.
COLONNES_ETAPES = (
    "rang", "nom", "action", "cible", "ecran", "source_genre", "source_valeur",
    "format", "defaut", "statut_attendu", "sauvegarde", "comparaison",
    "fenetres", "fonction", "colonne", "colonnes",
)

#: Colonnes de `derogations.csv`.
COLONNES_DEROGATIONS = ("etape", "garde", "portee", "motif")

#: Colonnes de `pipeline.csv` — un fichier clef/valeur, pas un tableau.
COLONNES_PIPELINE = ("propriete", "valeur")


class TableurInvalide(Exception):
    """Le classeur a produit quelque chose qu'on ne peut pas convertir.

    Distincte de `PipelineInvalide` : celle-ci parle du CSV, avec le numero de
    ligne du CSV. Confondre les deux enverrait corriger le YAML — un fichier
    que l'utilisateur du classeur n'a pas ecrit et ne devrait pas avoir a lire.
    """


@dataclass
class Ligne:
    """Une ligne de CSV, avec de quoi se situer dans un refus."""

    rang: int                        # numero de ligne DANS LE FICHIER
    cellules: dict[str, str]

    def brute(self, colonne: str) -> str:
        return (self.cellules.get(colonne) or "").strip()


@dataclass
class Feuille:
    fichier: str
    lignes: list[Ligne] = field(default_factory=list)

    def situer(self, ligne: Ligne, message: str) -> TableurInvalide:
        return TableurInvalide(f"{self.fichier}, ligne {ligne.rang} : {message}")


def _decoder(brut: bytes) -> str:
    """UTF-8 avec ou sans BOM, puis cp1252 — ce qu'Excel produit sous Windows.

    Le BOM est le cas NOMINAL : c'est ce que `falcon dictionnaire` ecrit et ce
    qu'un Excel francais reecrit. Le laisser dans la premiere cellule ferait
    une colonne nommee « ﻿rang », qui n'est aucune colonne connue.
    """
    for encodage in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return brut.decode(encodage)
        except UnicodeDecodeError:
            continue
    raise TableurInvalide("encodage non reconnu")


def lire_feuille(chemin: str | Path, colonnes: tuple[str, ...]) -> Feuille:
    """Un CSV a en-tete, dont les colonnes sont EXACTEMENT celles attendues.

    Une colonne inconnue est refusee plutot qu'ignoree. C'est le cas ou le
    silence coute le plus cher : `sauvgarde` mal orthographie serait ignore, et
    l'etape n'ecrirait jamais dans SAP — un lot qui semble passer et n'a rien
    fait, ce qui est le pire des resultats.
    """
    chemin = Path(chemin)
    if not chemin.is_file():
        raise TableurInvalide(f"{chemin} est introuvable")

    texte = _decoder(chemin.read_bytes())
    lignes = texte.splitlines()
    if not lignes:
        # `splitlines()[0]` levait une `IndexError` NUE, que `_composer`
        # n'attrape pas : une trace de pile la ou l'utilisateur attend un
        # refus situe. Un fichier vide est un cas banal — la macro n'a pas
        # tourne, ou le dossier n'est pas celui qu'on croit.
        raise TableurInvalide(
            f"{chemin} est vide. Attendu au moins la ligne d'en-tete : "
            f"{list(colonnes)}")

    # Excel francais ecrit `;`. Le renifleur de `donnees` ne convient pas ici :
    # les cibles SAP sont pleines de `[`, `]` et `/`, et une feuille a une
    # seule colonne remplie ne donne aucun indice.
    delimiteur = ";" if lignes[0].count(";") >= lignes[0].count(",") else ","

    lecteur = csv.DictReader(io.StringIO(texte), delimiter=delimiteur)
    entete = tuple(lecteur.fieldnames or ())
    if not entete:
        raise TableurInvalide(f"{chemin} : aucun en-tete")

    inconnues = sorted(set(entete) - set(colonnes))
    if inconnues:
        raise TableurInvalide(
            f"{chemin} : colonne(s) inconnue(s) {inconnues}. Connues : "
            f"{list(colonnes)}. Une colonne mal orthographiee serait ignoree, "
            f"et l'etape ferait autre chose que ce que la feuille montre")

    # EXACTEMENT celles attendues — ce que cette docstring promettait, et que
    # le seul controle ci-dessus ne donnait pas : il verifiait l'inclusion,
    # pas l'egalite.
    #
    # Une colonne SUPPRIMEE etait donc acceptee, et sa valeur valait le defaut
    # partout. Mesure : `sauvegarde` retiree, l'etape `sauver` chargeait avec
    # `sauvegarde=False`. Le contrat n'annoncait plus la sauvegarde imminente,
    # donc l'etat `douteux` cessait d'exister — et un item interrompu apres
    # une sauvegarde repartait a la reprise. Double ecriture, par une colonne
    # absente. Meme famille pour `defaut` (champ vide au lieu du repli) et
    # `statut_attendu` (garde 2 muette).
    manquantes = [c for c in colonnes if c not in set(entete)]
    if manquantes:
        raise TableurInvalide(
            f"{chemin} : colonne(s) absente(s) {manquantes}. Elles vaudraient "
            f"leur defaut partout, sans un mot — une colonne `sauvegarde` "
            f"absente fait une pipeline qui n'annonce plus ses sauvegardes, "
            f"donc des items interrompus qu'on rejoue")

    # Une colonne DUPLIQUEE : `DictReader` garde la DERNIERE, donc la valeur
    # de la premiere est perdue. C'est mot pour mot ce que `donnees/entree.py`
    # refuse du cote jeu de donnees, et pour la meme raison — sauf qu'ici la
    # valeur perdue est une CIBLE : la saisie partirait dans un autre champ
    # SAP que celui que la feuille montre en premiere position.
    doublons = sorted({c for c in entete if entete.count(c) > 1})
    if doublons:
        raise TableurInvalide(
            f"{chemin} : colonne(s) en double {doublons}. La valeur de la "
            f"premiere serait perdue au profit de la seconde, sans erreur")

    feuille = Feuille(fichier=str(chemin))
    for rang, cellules in enumerate(lecteur, start=2):      # 1 = l'en-tete
        if all(not (v or "").strip() for v in cellules.values()):
            continue            # une ligne vide sous le tableau : un tableur
        feuille.lignes.append(Ligne(rang=rang,
                                    cellules={c: cellules.get(c) or ""
                                              for c in entete}))
    return feuille


# ---------------------------------------------------------------------------
# Les crochets
# ---------------------------------------------------------------------------

def valeur_sap(brute: str, quoi: str, feuille: Feuille,
               ligne: Ligne) -> str:
    """Une valeur destinee a SAP : entre crochets, et rendue sans eux.

    Le refus vaut mieux que la tolerance, et c'est mesurable : accepter
    `0100` nu reviendrait a accepter ce qu'Excel a peut-etre deja transforme
    en `100`. Les deux se ressemblent, l'un est faux, et rien en aval ne peut
    plus les distinguer. Les crochets sont la preuve que la cellule n'a pas
    ete retypee.
    """
    if not (brute.startswith("[") and brute.endswith("]")):
        raise feuille.situer(
            ligne,
            f"{quoi} : « {brute} » doit etre entre crochets — « [{brute}] ». "
            f"Sans eux, Excel retype la cellule : « 0100 » devient « 100 », "
            f"« on » devient VRAI, et rien en aval ne peut plus le voir. "
            f"Pour une valeur vide, ecrire « [] »")
    return brute[1:-1]


# ---------------------------------------------------------------------------
# L'ecran
# ---------------------------------------------------------------------------

def lire_ecran(brute: str, feuille: Feuille, ligne: Ligne
               ) -> dict[str, str] | None:
    """`IA08::RIPLKO10::0100`, ou `libre`. Rend None pour la seconde.

    Le jeton vient du dictionnaire du catalogue : on le COLLE, on ne le retape
    pas. C'est aussi ce qui rend le XOR inexprimable — une cellule ne peut pas
    porter a la fois un triplet et le mot `libre`.
    """
    if not brute:
        raise feuille.situer(
            ligne,
            "`ecran` est vide. Colle le jeton du dictionnaire — "
            "« IA08::RIPLKO10::0100 » — ou ecris « libre » si l'etape ne sait "
            "pas encore ou elle atterrit. Une etape muette neutraliserait la "
            "garde d'identite sans que personne ne le voie")
    if brute == JETON_LIBRE:
        return None

    morceaux = brute.split(SEPARATEUR_ECRAN)
    if len(morceaux) != 3 or not all(m.strip() for m in morceaux):
        raise feuille.situer(
            ligne,
            f"`ecran` : « {brute} » n'est pas un jeton d'ecran. Attendu "
            f"« transaction{SEPARATEUR_ECRAN}programme{SEPARATEUR_ECRAN}dynpro » "
            f"— celui que `falcon dictionnaire` met dans la colonne `ecran` — "
            f"ou « {JETON_LIBRE} »")
    transaction, programme, dynpro = (m.strip() for m in morceaux)
    return {"transaction": transaction, "programme": programme,
            "dynpro": dynpro}


# ---------------------------------------------------------------------------
# Le rang
# ---------------------------------------------------------------------------

def verifier_rangs(feuille: Feuille) -> None:
    """Le rang doit croitre STRICTEMENT, d'une ligne a la suivante.

    Cliquer sur un en-tete pour trier est le geste le plus banal d'un tableur.
    Il reordonne les etapes en silence — et l'ordre des etapes est ce qui est
    tape dans SAP, dans quel ordre, et a quel moment on sauvegarde. Un tri sur
    `nom` produirait une pipeline qui charge, qui tourne, et qui fait autre
    chose.

    Les trous sont permis : on numerote de dix en dix pour pouvoir inserer.
    """
    precedent: int | None = None
    for ligne in feuille.lignes:
        brut = ligne.brute("rang")
        try:
            rang = int(brut)
        except ValueError:
            raise feuille.situer(
                ligne, f"`rang` : « {brut} » n'est pas un entier") from None
        if precedent is not None and rang <= precedent:
            raise feuille.situer(
                ligne,
                f"`rang` {rang} apres {precedent} : les rangs doivent CROITRE. "
                f"Un tri sur une autre colonne — le geste le plus banal d'un "
                f"tableur — reordonne les etapes en silence, et l'ordre des "
                f"etapes est ce qui est tape dans SAP")
        precedent = rang


def lire_liste(brute: str) -> list[str]:
    """Une cellule qui porte plusieurs valeurs, separees par des virgules.

    Employe pour `cles`, `fenetres` et `format`. Une cellule vide rend une
    liste vide, jamais `[""]` : une fenetre nommee « » serait attendue et
    jamais trouvee, et une colonne de clef nommee « » ferait un `item_id`
    calcule sur rien.
    """
    return [m.strip() for m in brute.split(",") if m.strip()]
