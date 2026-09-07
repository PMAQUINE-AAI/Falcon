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
from importlib.resources import files
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


def _ressource(paquet: str, nom: str) -> str:
    """Lit un YAML LIVRE AVEC LE PAQUET, depuis les sources ou depuis le zip.

    `Path(__file__).parent / "x.yaml"` marche depuis un depot et pas depuis
    `falcon.pyz` : dans un zipapp, `__file__` n'est pas un chemin de systeme
    de fichiers. Le fichier n'existait donc pas, et comme `Registre.charger()`
    est appele a CHAQUE execution de pipeline, le bundle — qui est la forme de
    livraison arretee au §6 — ne pouvait executer aucune pipeline.

    Rien ne levait a la construction, et la suite du bundle n'exercait que des
    commandes qui ne chargent pas le registre : le defaut ne se serait vu
    qu'au premier lot reel, sur le poste de quelqu'un.

    `importlib.resources` lit les deux, et c'est sa raison d'etre.
    """
    return files(paquet).joinpath(nom).read_text(encoding="utf-8")


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
        """Plus une entree porte de contexte, plus elle est specifique.

        Compter les clefs et non leur simple presence : deux entrees
        contextuelles de finesse differente doivent se departager, sinon
        l'ordre du fichier decide.
        """
        return len(self.contexte)


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
        # L'identite du message, quand l'entree la declare. C'est ce qui rend
        # la liste blanche utilisable sur une etape qui declare un statut
        # attendu : sans elle, une entree d'ecart apparierait indifferemment
        # tous les messages produisant le meme ecart.
        if "id" in attendus and attendus["id"] != signature.id:
            return False
        if "numero" in attendus and not meme_numero(str(attendus["numero"]),
                                                    signature.numero):
            return False
        return True

    # canaux com et python : appariement sur le nom d'exception
    return attendus.get("exception", "") == signature.exception


def _contextes_departageables(gauche: Entree, droite: Entree) -> bool:
    """Deux entrees contextuelles peuvent-elles etre departagees sans arbitraire ?

    Oui dans deux cas seulement : soit leurs contextes se contredisent — ils
    ne peuvent alors jamais etre vrais ensemble — soit l'un contient l'autre,
    et la specificite tranche.

    Le cas dangereux est celui de deux contextes qui ne se contredisent pas et
    dont aucun ne contient l'autre : `{transaction: IA08}` et
    `{dynpro: "1000"}` sont tous deux vrais sur l'ecran de selection de IA08,
    et c'est alors l'ordre des entrees dans le fichier qui decide de la
    politique appliquee. Intervertir deux blocs de YAML changerait le
    comportement, sans erreur — exactement ce que la verification au
    chargement existe pour empecher.
    """
    cg, cd = gauche.contexte, droite.contexte
    communes = set(cg) & set(cd)
    if any(cg[cle] != cd[cle] for cle in communes):
        return True                       # incompatibles : jamais vrais ensemble

    # Contextes identiques : la specificite est egale, donc c'est l'ordre du
    # fichier qui trancherait. Ce n'est pas un departage.
    return set(cg) != set(cd) and (set(cg) <= set(cd) or set(cd) <= set(cg))


def _memes_criteres(gauche: Entree, droite: Entree) -> bool:
    """Les deux entrees visent-elles le meme signal, contexte mis a part ?"""
    if gauche.canal != droite.canal:
        return False
    g, d = gauche.correspondance, droite.correspondance
    if gauche.canal == "statut":
        return (g.get("id") == d.get("id")
                and meme_numero(str(g.get("numero", "")), str(d.get("numero", "")))
                and (not _types_declares(gauche) or not _types_declares(droite)
                     or bool(_types_declares(gauche) & _types_declares(droite))))
    if gauche.canal == "garde":
        if any(g.get(cle) != d.get(cle)
               for cle in ("garde", "attendu", "observe")):
            return False
        if "id" in g and "id" in d and g["id"] != d["id"]:
            return False
        if "numero" in g and "numero" in d:
            return meme_numero(str(g["numero"]), str(d["numero"]))
        return True
    return g.get("exception") == d.get("exception")


def _contextes_compatibles(gauche: Entree, droite: Entree) -> bool:
    """Les deux contextes peuvent-ils etre vrais en meme temps ?"""
    cg, cd = gauche.contexte, droite.contexte
    return all(cg[cle] == cd[cle] for cle in set(cg) & set(cd))


def _plus_permissive(posterieure: Politique, anterieure: Politique) -> bool:
    """La seconde politique laisse-t-elle passer ce que la premiere arretait ?"""
    return ((posterieure.poursuivre and not anterieure.poursuivre)
            or (anterieure.arreter_chaine and not posterieure.arreter_chaine)
            or (anterieure.item == "ko" and posterieure.item != "ko"))


def _peuvent_se_confondre(gauche: Entree, droite: Entree) -> bool:
    """Deux entrees peuvent-elles apparier une meme signature ?

    Verifie a la construction plutot qu'a l'execution. Une ambiguite
    decouverte en pleine execution obligerait a choisir au hasard entre deux
    politiques — ou pire, a en appliquer une silencieusement.
    """
    if gauche.canal != droite.canal:
        return False
    if _contextes_departageables(gauche, droite):
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
        if any(g.get(cle) != d.get(cle)
               for cle in ("garde", "attendu", "observe")):
            return False
        if "id" in g and "id" in d and g["id"] != d["id"]:
            return False
        if "numero" in g and "numero" in d:
            return meme_numero(str(g["numero"]), str(d["numero"]))
        return True

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
        entrees: list[Entree] = []
        if not chemins:
            # Le registre livre avec le paquet, lu par `importlib.resources` :
            # depuis un depot ET depuis `falcon.pyz`. Voir `_ressource`.
            entrees.extend(_lire_texte(_ressource(__package__, "registre.yaml"),
                                       Path(CHEMIN_REGISTRE_DEFAUT)))
            return cls(entrees)
        for chemin in chemins:
            nouvelles = _lire_fichier(Path(chemin))
            _verifier_absence_d_assouplissement(entrees, nouvelles, Path(chemin))
            entrees.extend(nouvelles)
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


def _verifier_absence_d_assouplissement(anterieures: Sequence[Entree],
                                        nouvelles: Sequence[Entree],
                                        chemin: Path) -> None:
    """Une surcouche ajoute ; elle n'assouplit pas.

    Sans cette verification, la promesse de `charger` etait fausse : il
    suffisait a un fichier de projet d'ajouter une entree PLUS SPECIFIQUE et
    plus permissive pour desactiver une entree commune. Une entree
    `{exception: SessionPerdue, contexte: {transaction: IA08}}` en
    `connue_benigne` rendait `session_perdue` non bloquante sur IA08 — sans
    une ligne de code, sans motif, sans trace dans le rapport.

    C'etait le contournement le plus praticable du dispositif : la separation
    pipeline / controleur interdit a une pipeline de desactiver une garde,
    mais rien n'interdisait a un YAML de neutraliser la politique qui la rend
    bloquante.
    """
    for nouvelle in nouvelles:
        for anterieure in anterieures:
            if not _memes_criteres(anterieure, nouvelle):
                continue
            if not _contextes_compatibles(anterieure, nouvelle):
                continue
            if _plus_permissive(nouvelle.politique, anterieure.politique):
                raise RegistreInvalide(
                    f"{chemin} : {nouvelle.nom!r} assouplit {anterieure.nom!r}. "
                    f"Une surcouche ajoute des entrees, elle n'en affaiblit "
                    f"aucune — sinon la politique la plus stricte se contourne "
                    f"par un fichier de configuration")


# =====================================================================
# Lecture du fichier
# =====================================================================

_JOKERS = {"*", "?", ".*"}


def _lire_fichier(chemin: Path) -> list[Entree]:
    if not chemin.exists():
        raise RegistreInvalide(f"registre introuvable : {chemin}")
    return _lire_texte(chemin.read_text(encoding="utf-8"), chemin)


def _lire_texte(brut: str, chemin: Path) -> list[Entree]:
    """Le contenu, d'ou qu'il vienne. `chemin` ne sert qu'aux messages."""
    contenu = yaml.safe_load(brut) or {}
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
