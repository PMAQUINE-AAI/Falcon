"""Registre des erreurs connues, et classement de ce qui survient.

Les gardes detectent que quelque chose a mal tourne ; la taxonomie dit quoi en
faire. Trois categories, pas une de plus :

    connue_benigne   message attendu, sans consequence : on poursuit, on note
    connue_fautive   cause identifiee, politique definie : item KO, boucle
                     poursuivie
    inconnue         arret, dump complet, capture a verser au catalogue

**L'inconnu est un resultat de premiere classe**, pas un `except` fourre-tout.
Toute signature non appariee est bloquante, et le devient non-bloquante le
jour ou quelqu'un la decrit explicitement — pas avant.

Deux consequences de conception, qui sont le coeur de ce module :

1. `Registre` n'accepte AUCUN parametre de defaut, de mode strict ou permissif.
   Il n'y a pas d'interrupteur a trouver, donc pas d'interrupteur a actionner
   un vendredi soir.
2. Le fichier refuse les jokers. On ne peut pas ecrire une entree attrape-tout
   qui ferait passer l'inconnu pour du connu.

**La taxonomie se recolte, elle ne se specifie pas.** Le registre livre est
volontairement presque vide. Pretendre ecrire d'avance un traitement d'erreur
exhaustif reviendrait a pretendre connaitre des comportements que seul le
systeme reel revele.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

from falcon.noyau.types import meme_numero

# --- categories ------------------------------------------------------
BENIGNE = "connue_benigne"
FAUTIVE = "connue_fautive"
INCONNUE = "inconnue"

#: Categories declarables dans le fichier. `inconnue` n'en fait pas partie :
#: elle ne se declare pas, elle est ce qu'on obtient quand rien n'apparie.
DECLARABLES = frozenset({BENIGNE, FAUTIVE})

# --- canaux ----------------------------------------------------------
#: D'ou vient le signal. Un meme incident n'a pas la meme signature selon
#: qu'il arrive par la barre de statut ou par une exception COM.
CANAUX = frozenset({"statut", "com", "garde", "python"})

RACINE = Path(__file__).resolve().parent
CHEMIN_REGISTRE_DEFAUT = RACINE / "registre.yaml"


class RegistreInvalide(Exception):
    """Le registre ne peut pas etre charge.

    Levee au CHARGEMENT, jamais pendant une execution : une ambiguite
    decouverte au bout de deux heures de lot aurait deja fait des degats.
    """


@dataclass(frozen=True)
class Politique:
    """Ce qu'on fait quand une entree apparie."""

    poursuivre: bool = False
    item: str | None = None          # "ko" pour marquer l'item, None sinon
    arreter_chaine: bool = False


#: Politique de l'inconnu. Non configurable, et c'est le point.
ARRET = Politique(poursuivre=False, item="ko", arreter_chaine=True)


@dataclass(frozen=True)
class Signature:
    """Ce qui vient d'arriver, sous une forme appariable.

    `contexte` est le triplet d'ecran, quand on le connait : une meme erreur
    peut etre benigne sur un ecran et fautive sur un autre.
    """

    canal: str
    type: str = ""                   # S | W | I | E | A, canal statut
    id: str = ""                     # messageId
    numero: str = ""                 # messageNumber
    texte: str = ""
    exception: str = ""              # nom de classe, canaux com et python
    garde: str = ""                  # canal garde
    attendu: str = ""
    observe: str = ""
    contexte: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Entree:
    nom: str
    categorie: str
    canal: str
    politique: Politique
    origine: str                     # falcon_observe | eagleloader | conjecture
    justification: str
    correspondance: dict[str, Any] = field(default_factory=dict)
    rencontree_le: str = ""

    @property
    def contexte(self) -> dict[str, str]:
        return dict(self.correspondance.get("contexte") or {})

    @property
    def specificite(self) -> int:
        """Une entree contextuelle bat une entree globale."""
        return 1 if self.contexte else 0


@dataclass(frozen=True)
class Verdict:
    categorie: str
    politique: Politique
    entree: str | None = None

    @property
    def bloquant(self) -> bool:
        """Derive de la politique : les deux ne peuvent pas se contredire."""
        return not self.politique.poursuivre

    @property
    def inconnu(self) -> bool:
        return self.categorie == INCONNUE


# =====================================================================
# Appariement
# =====================================================================

def _types_declares(entree: Entree) -> frozenset[str]:
    bruts = entree.correspondance.get("type")
    if bruts is None:
        return frozenset()               # vide = tous types
    if isinstance(bruts, str):
        bruts = [bruts]
    return frozenset(bruts)


def _contexte_compatible(entree: Entree, signature: Signature) -> bool:
    for cle, valeur in entree.contexte.items():
        if signature.contexte.get(cle) != valeur:
            return False
    return True


def _apparie(entree: Entree, signature: Signature) -> bool:
    if entree.canal != signature.canal:
        return False
    if not _contexte_compatible(entree, signature):
        return False

    attendus = entree.correspondance

    if entree.canal == "statut":
        if attendus.get("id", "") != signature.id:
            return False
        if not meme_numero(str(attendus.get("numero", "")), signature.numero):
            return False
        types = _types_declares(entree)
        return not types or signature.type in types

    if entree.canal == "garde":
        if attendus.get("garde", "") != signature.garde:
            return False
        for cle in ("attendu", "observe"):
            if cle in attendus and attendus[cle] != getattr(signature, cle):
                return False
        return True

    # canaux com et python : appariement sur le nom d'exception
    return attendus.get("exception", "") == signature.exception


def _peuvent_se_confondre(gauche: Entree, droite: Entree) -> bool:
    """Deux entrees peuvent-elles apparier une meme signature ?

    Verifie a la construction plutot qu'a l'execution. Une ambiguite
    decouverte en pleine execution obligerait a choisir au hasard entre deux
    politiques — ou pire, a en appliquer une silencieusement.
    """
    if gauche.canal != droite.canal or gauche.contexte != droite.contexte:
        return False

    g, d = gauche.correspondance, droite.correspondance

    if gauche.canal == "statut":
        if g.get("id") != d.get("id"):
            return False
        if not meme_numero(str(g.get("numero", "")), str(d.get("numero", ""))):
            return False
        types_g, types_d = _types_declares(gauche), _types_declares(droite)
        # Un ensemble vide signifie « tous types », donc recouvre l'autre.
        return not types_g or not types_d or bool(types_g & types_d)

    if gauche.canal == "garde":
        return all(g.get(cle) == d.get(cle)
                   for cle in ("garde", "attendu", "observe"))

    return g.get("exception") == d.get("exception")


# =====================================================================
# Le registre
# =====================================================================

class Registre:
    """Classe une signature. Aucun reglage, aucun defaut configurable.

    La signature du constructeur est volontairement nue : lui ajouter un
    parametre `defaut=` ou `permissif=` reviendrait a offrir un moyen de
    rendre l'inconnu inoffensif, ce que le modele de securite interdit.
    """

    def __init__(self, entrees: Sequence[Entree]):
        self._entrees = tuple(entrees)
        self._verifier_absence_d_ambiguite()

    # -- construction ----------------------------------------------------

    @classmethod
    def charger(cls, *chemins: str | Path) -> "Registre":
        """Charge un ou plusieurs fichiers. Les suivants AJOUTENT au premier.

        Une surcouche de projet peut enrichir le registre commun ; elle ne
        peut pas en retirer une entree, ni en assouplir une.
        """
        sources = chemins or (CHEMIN_REGISTRE_DEFAUT,)
        entrees: list[Entree] = []
        for chemin in sources:
            entrees.extend(_lire_fichier(Path(chemin)))
        return cls(entrees)

    def _verifier_absence_d_ambiguite(self) -> None:
        for rang, gauche in enumerate(self._entrees):
            for droite in self._entrees[rang + 1:]:
                if _peuvent_se_confondre(gauche, droite):
                    raise RegistreInvalide(
                        f"{gauche.nom!r} et {droite.nom!r} peuvent apparier la "
                        f"meme signature : leurs politiques seraient "
                        f"departagees au hasard")

    # -- usage ------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._entrees)

    @property
    def entrees(self) -> tuple[Entree, ...]:
        return self._entrees

    def classer(self, signature: Signature) -> Verdict:
        """Rend le verdict. Rien n'apparie => inconnu, donc bloquant."""
        candidates = [e for e in self._entrees if _apparie(e, signature)]
        if not candidates:
            return Verdict(categorie=INCONNUE, politique=ARRET, entree=None)

        retenue = max(candidates, key=lambda e: e.specificite)
        return Verdict(categorie=retenue.categorie,
                       politique=retenue.politique,
                       entree=retenue.nom)


# =====================================================================
# Lecture du fichier
# =====================================================================

_JOKERS = {"*", "?", ".*"}


def _lire_fichier(chemin: Path) -> list[Entree]:
    if not chemin.exists():
        raise RegistreInvalide(f"registre introuvable : {chemin}")

    contenu = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    if not isinstance(contenu, dict):
        raise RegistreInvalide(f"{chemin} : un dictionnaire est attendu")

    brutes = contenu.get("entrees") or []
    return [_construire(brute, chemin) for brute in brutes]


def _construire(brute: dict[str, Any], chemin: Path) -> Entree:
    nom = brute.get("nom")
    if not nom:
        raise RegistreInvalide(f"{chemin} : une entree sans nom")

    def exiger(cle: str) -> Any:
        valeur = brute.get(cle)
        if not valeur:
            raise RegistreInvalide(f"{chemin} : {nom!r} sans {cle}")
        return valeur

    categorie = exiger("categorie")
    if categorie not in DECLARABLES:
        raise RegistreInvalide(
            f"{chemin} : {nom!r} a la categorie {categorie!r}. "
            f"Declarables : {sorted(DECLARABLES)} — `inconnue` ne se declare "
            f"pas, elle est ce qu'on obtient quand rien n'apparie")

    canal = exiger("canal")
    if canal not in CANAUX:
        raise RegistreInvalide(
            f"{chemin} : {nom!r} a le canal {canal!r}, hors de {sorted(CANAUX)}")

    # Justification et origine sont exigees : une entree qui rend un incident
    # non bloquant doit dire pourquoi, et d'ou vient cette certitude.
    justification = exiger("justification")
    origine = exiger("origine")

    correspondance = brute.get("correspondance") or {}
    if not isinstance(correspondance, dict):
        raise RegistreInvalide(f"{chemin} : {nom!r}, correspondance invalide")
    for cle, valeur in correspondance.items():
        if isinstance(valeur, str) and valeur.strip() in _JOKERS:
            raise RegistreInvalide(
                f"{chemin} : {nom!r} utilise un joker sur {cle!r}. "
                f"Une entree attrape-tout ferait passer l'inconnu pour du "
                f"connu, ce que le modele de securite interdit")

    politique_brute = brute.get("politique") or {}
    politique = Politique(
        poursuivre=bool(politique_brute.get("poursuivre", False)),
        item=politique_brute.get("item"),
        arreter_chaine=bool(politique_brute.get("arreter_chaine", False)),
    )

    return Entree(nom=nom, categorie=categorie, canal=canal,
                  politique=politique, origine=origine,
                  justification=justification,
                  correspondance=correspondance,
                  rencontree_le=str(brute.get("rencontree_le", "")))
