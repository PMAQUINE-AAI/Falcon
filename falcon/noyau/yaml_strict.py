"""Le dialecte YAML de FALCON : ce qui est ambigu est refuse, jamais devine.

**YAML n'est pas du texte, et c'est le probleme.** Il resout les scalaires
selon des regles qui datent de YAML 1.1 et qui surprennent tout le monde :

    0100        entier octal, vaut 64
    007         entier 7 — les zeros de tete disparaissent
    12:30       base 60, vaut 750
    1.50        flottant, se reecrit « 1.5 »
    on, N, no   booleens
    ~           None

Dans un projet ordinaire c'est une curiosite. Ici, ces valeurs sont TAPEES
DANS UN ERP DE PRODUCTION, comparees a des identites d'ecran, ou lues comme
des politiques de securite. Un `poursuivre: non` qui vaut True fait continuer
un lot apres l'erreur qu'on voulait bloquante.

Et surtout : c'est l'UTILISATEUR qui ecrit ces fichiers. Il ecrit un YAML pour
declarer un automatisme nouveau, sans passer par nous. Un format qui le
trahit en silence sur un zero de tete est un format qui l'oblige a nous
appeler — c'est-a-dire l'inverse de ce que ce projet doit etre.

**Deux barrieres, et il faut les deux.**

La premiere est ce lecteur : il refuse a l'ANALYSE les formes ou la valeur
depend d'une regle que personne n'a en tete — l'octal et le sexagesimal, qui
ne se distinguent plus d'un entier ordinaire une fois lus.

La seconde est les accesseurs ci-dessous : ils exigent le TYPE attendu au lieu
de le forcer. `str(valeur)` et `bool(valeur)` transforment n'importe quoi en
quelque chose, et c'est precisement ce qu'il ne faut pas ici.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

import yaml

#: `010`, `007`, `-0700` — un entier a zero de tete.
#:
#: YAML 1.1 lit `010` comme de l'octal (8). Meme quand il ne le fait pas, le
#: zero disparait, et les codes SAP en sont remplis : un numero de message
#: `010` devient 8, une reference d'equipement perd son cadrage. Une fois lu,
#: rien ne distingue plus le resultat d'un entier ordinaire.
OCTAL = re.compile(r"^[-+]?0[0-9_]+$")

#: `12:30`, `1:2:3` — la notation sexagesimale de YAML 1.1, qui vaut 750.
SEXAGESIMAL = re.compile(r"^[-+]?[0-9][0-9_]*(:[0-5]?[0-9])+$")


class YamlAmbigu(Exception):
    """Le fichier porte un scalaire dont la valeur depend d'une regle YAML.

    Levee a l'ANALYSE, avant que quoi que ce soit ait pu s'en servir.
    """


class LecteurStrict(yaml.SafeLoader):
    """`SafeLoader`, moins les resolutions qui surprennent."""


def _ou(noeud: yaml.Node) -> str:
    """« ligne 12 », depuis la marque que PyYAML porte sur chaque noeud.

    Un refus a l'analyse ne peut pas nommer l'etape : les etapes n'existent
    pas encore. Il peut nommer la LIGNE, ce qui remplit le meme office —
    « un message d'erreur qu'il faut aller chercher dans un fichier de trois
    cents lignes coute autant qu'une absence de message ».
    """
    marque = getattr(noeud, "start_mark", None)
    return f"ligne {marque.line + 1}" if marque is not None else "?"


def _entier_strict(lecteur: LecteurStrict, noeud: yaml.Node) -> int:
    brut = noeud.value
    if OCTAL.match(brut):
        raise YamlAmbigu(
            f"{_ou(noeud)}, « {brut} » : un entier a zero de tete. YAML le "
            f"lit comme de l'octal — « 010 » vaut 8 — et le zero disparait de "
            f"toute facon. Les codes SAP en sont remplis : ecris-le entre "
            f"guillemets si c'est un code, sans zero si c'est un nombre")
    if SEXAGESIMAL.match(brut):
        raise YamlAmbigu(
            f"{_ou(noeud)}, « {brut} » : YAML le lit en base 60 — « 12:30 » "
            f"vaut 750. Entre guillemets si c'est un texte")
    return yaml.SafeLoader.construct_yaml_int(lecteur, noeud)


LecteurStrict.add_constructor("tag:yaml.org,2002:int", _entier_strict)


def lire(brut: str, source: str) -> Any:
    """Analyse un YAML avec le dialecte strict. `source` situe le refus."""
    try:
        return yaml.load(brut, Loader=LecteurStrict)
    except YamlAmbigu as erreur:
        raise YamlAmbigu(f"{source} : {erreur}") from None


# ---------------------------------------------------------------------------
# Accesseurs
#
# Chacun EXIGE le type, au lieu de le forcer. `str(valeur)` rend « None » pour
# une cle vide et « True » pour `on` ; `bool(valeur)` rend True pour la chaine
# « non ». Les deux fabriquent une valeur plausible a partir d'une erreur, et
# c'est la classe de defaut que ce projet traque.
# ---------------------------------------------------------------------------

def _situer(quoi: str, source: str) -> str:
    return f"{source} : `{quoi}`" if source else f"`{quoi}`"


def texte(valeur: Any, quoi: str, *, source: str = "",
          defaut: str | None = None) -> str:
    """Une chaine, et rien d'autre.

    `defaut` sert aux cles absentes. Une cle PRESENTE mais vide reste refusee :
    l'ecrire et ne rien mettre derriere est une omission, pas une valeur, et
    `str(None)` en ferait le texte « None ».
    """
    if valeur is None and defaut is not None:
        return defaut
    if not isinstance(valeur, str):
        raise YamlAmbigu(
            f"{_situer(quoi, source)} doit etre une CHAINE, entre guillemets "
            f"(recu {valeur!r}). Sans eux, YAML lit « 0100 » comme de l'octal, "
            f"« on » comme un booleen, et une cle vide comme None — qui "
            f"deviendrait le texte « None »")
    return valeur


def entier(valeur: Any, quoi: str, *, source: str = "",
           minimum: int | None = None) -> int:
    """Un entier, et pas un booleen — `True` vaut 1 pour Python."""
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        raise YamlAmbigu(
            f"{_situer(quoi, source)} doit etre un ENTIER "
            f"(recu {valeur!r})")
    if minimum is not None and valeur < minimum:
        raise YamlAmbigu(
            f"{_situer(quoi, source)} doit valoir au moins {minimum} "
            f"(recu {valeur})")
    return valeur


def booleen(valeur: Any, quoi: str, *, source: str = "",
            defaut: bool | None = None) -> bool:
    """Un booleen VRAI ou FAUX, jamais un `bool()` sur autre chose.

    Le defaut qui a motive cet accesseur : `politique.poursuivre` passait par
    `bool()`. Un `poursuivre: non` — que YAML lit comme la CHAINE « non »,
    puisque « non » n'est pas un booleen YAML — valait donc True. L'entree
    disait « arrete le lot » et le lot continuait a ecrire dans SAP.
    """
    if valeur is None and defaut is not None:
        return defaut
    if not isinstance(valeur, bool):
        raise YamlAmbigu(
            f"{_situer(quoi, source)} doit etre `true` ou `false` "
            f"(recu {valeur!r}). « non », « oui » et « N » ne sont pas des "
            f"booleens YAML : ce sont des chaines, et toute chaine non vide "
            f"vaut vrai")
    return valeur


def liste_de_texte(valeur: Any, quoi: str, *, source: str = "",
                   defaut: Sequence[str] | None = None) -> tuple[str, ...]:
    """Une LISTE de chaines. Un scalaire seul est refuse, pas eclate.

    `tuple("site")` rend `('s', 'i', 't', 'e')` : quatre colonnes de clef
    nommees s, i, t et e. L'erreur ressortait bien plus loin, sous la forme
    d'une colonne absente du jeu de donnees — et accusait le fichier de
    donnees plutot que la pipeline.
    """
    if valeur is None and defaut is not None:
        return tuple(defaut)
    if isinstance(valeur, str) or not isinstance(valeur, Iterable):
        raise YamlAmbigu(
            f"{_situer(quoi, source)} doit etre une LISTE, entre crochets "
            f"(recu {valeur!r}). Un scalaire seul serait eclate caractere par "
            f"caractere : « site » donnerait quatre entrees s, i, t, e")
    return tuple(texte(element, f"{quoi}[{rang}]", source=source)
                 for rang, element in enumerate(valeur))
