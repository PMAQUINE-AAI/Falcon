"""Composer une valeur sans ecrire de Python.

**Le probleme, dans les mots de l'utilisateur :** « Il faut que le programme
puisse etre multi usage, pas specifique au point ou je dois revoir avec toi le
code des que j'ai besoin de faire une nouvelle automatisation. »

Une pipeline ne savait tirer une valeur que de trois endroits : une colonne du
jeu, une constante, ou une etape `lire` anterieure. Elle ne savait pas les
COMBINER. Or le cas le plus banal d'une correction de masse SAP en a besoin :
un nom de variante porte le site quelque part dedans — `/BCP01_K75` — et un
numero d'equipement se saisit cadre a douze positions.

Six besoins courants etaient hors de portee, et le seul chemin restant etait
`action: python`, c'est-a-dire ecrire une fonction, la faire entrer dans le
depot, et la faire relire. Pour concatener deux colonnes.

**Ce que ce module ajoute, et ce qu'il refuse de devenir.**

Il ajoute un genre de source `gabarit` et une liste `format`. Rien d'autre.

Il n'ajoute AUCUNE facon d'exprimer une condition, une boucle, un calcul, ni
une expression evaluee. C'est delibere, et ce n'est pas de la timidite : une
expression evaluee dans un YAML de pipeline serait du code arbitraire qui
n'aurait traverse ni la relecture d'un humain, ni les gardes — exactement
l'echappatoire que le §5.2 interdit. Les transformations forment un registre
FERME, chacune nommee ici, chacune une fonction pure du texte vers le texte.

La contrepartie est assumee : ce qui ne s'exprime pas avec ces briques passe
par `action: python`, qui recoit un `Poste` garde. La frontiere reste nette.

**Ce que ca ne relache pas.** La valeur composee est calculee AVANT l'ecriture.
La garde de relecture compare donc ce qui a ete tape a ce que SAP rend, comme
avant. Une composition ne peut pas desarmer une garde ; elle ne fait que dire
quoi taper.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

#: `{site}`, `{numero_serie}` — un nom de colonne entre accolades.
#:
#: Volontairement etroit : lettres, chiffres, tiret bas. Une accolade qui ne
#: correspond pas a ca est une faute de frappe, pas une syntaxe a deviner.
JETON = re.compile(r"\{([A-Za-z0-9_]+)\}")

#: Accolades litterales, comme dans les gabarits de Python.
DOUBLES = (("{{", "\0LEFT\0"), ("}}", "\0RIGHT\0"))


class CompositionInvalide(Exception):
    """Le gabarit ou le format ne decrit pas une transformation exploitable."""


# ---------------------------------------------------------------------------
# Gabarit
# ---------------------------------------------------------------------------

def jetons(gabarit: str) -> tuple[str, ...]:
    """Les noms de colonne cites par le gabarit, dans l'ordre, sans doublon."""
    vus: list[str] = []
    for nom in JETON.findall(_masquer(gabarit)):
        if nom not in vus:
            vus.append(nom)
    return tuple(vus)


def _masquer(gabarit: str) -> str:
    for litteral, marque in DOUBLES:
        gabarit = gabarit.replace(litteral, marque)
    return gabarit


def _demasquer(texte: str) -> str:
    return texte.replace("\0LEFT\0", "{").replace("\0RIGHT\0", "}")


def verifier_gabarit(gabarit: str) -> tuple[str, ...]:
    """Valide un gabarit au CHARGEMENT et rend les colonnes qu'il cite.

    Deux refus, et les deux valent mieux qu'une valeur plausible :

    Une accolade non appariee, ou un contenu qui n'est pas un nom de colonne,
    serait recopiee telle quelle dans le champ SAP. `{site` finirait tape
    « {site ».

    Un gabarit sans aucune colonne est une constante deguisee. La lire comme
    un gabarit marche, mais masque l'intention : `constante` existe, et un
    relecteur qui voit `gabarit` s'attend a une valeur qui varie.
    """
    masque = _masquer(gabarit)
    restant = JETON.sub("", masque)
    if "{" in restant or "}" in restant:
        raise CompositionInvalide(
            f"gabarit {gabarit!r} : accolade non appariee, ou contenu qui "
            f"n'est pas un nom de colonne. Un nom de colonne s'ecrit "
            f"« {{site}} » — lettres, chiffres et tiret bas. Pour une "
            f"accolade litterale, la doubler : « {{{{ »")
    noms = jetons(gabarit)
    if not noms:
        raise CompositionInvalide(
            f"gabarit {gabarit!r} : aucune colonne citee. C'est une constante "
            f"deguisee — ecris `source: {{constante: ...}}`, qu'un relecteur "
            f"lira pour ce qu'elle est")
    return noms


def appliquer_gabarit(gabarit: str, ligne: Mapping[str, Any]) -> str:
    """Remplace chaque `{colonne}` par sa valeur.

    Une colonne absente est une erreur ici et pas une chaine vide : le
    pre-vol du moteur a deja verifie que le jeu porte toutes les colonnes
    citees, donc arriver ici avec une absente signale une incoherence, pas une
    donnee manquante.
    """
    def remplacer(trouve: re.Match) -> str:
        nom = trouve.group(1)
        if nom not in ligne:
            raise CompositionInvalide(
                f"gabarit {gabarit!r} : colonne {nom!r} absente de la ligne")
        return str(ligne[nom])

    return _demasquer(JETON.sub(remplacer, _masquer(gabarit)))


# ---------------------------------------------------------------------------
# Transformations
#
# REGISTRE FERME. Chaque entree est une fonction pure du texte vers le texte,
# nommee ici. Une pipeline ne peut en designer aucune autre, et n'a aucun
# moyen d'en fournir une : c'est ce qui separe une composition declarative
# d'une echappatoire.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Transformation:
    """Une transformation nommee, avec son argument eventuel."""

    nom: str
    argument: int | str | None = None

    def appliquer(self, valeur: str) -> str:
        return _TRANSFORMATIONS[self.nom].appliquer(valeur, self.argument)

    def __str__(self) -> str:
        return (f"{self.nom}: {self.argument}" if self.argument is not None
                else self.nom)


@dataclass(frozen=True)
class _Definition:
    appliquer: Callable[[str, Any], str]
    argument: str                            # "aucun" | "entier" | "texte"
    aide: str


def _zeros(valeur: str, largeur: Any) -> str:
    """Cadre a droite en remplissant de zeros — la convention SAP.

    La largeur est DECLAREE, jamais devinee. Douze pour un `MATNR`, dix-huit
    pour un `EQUNR` : une valeur par defaut serait un comportement SAP
    invente, ce que ce projet s'interdit.

    Une valeur plus longue que la largeur n'est pas tronquee ici. Tronquer
    silencieusement un numero produirait une reference valide et fausse ;
    `tronque` existe et se declare.

    UNE VALEUR VIDE EST REFUSEE, et c'est le point important.

    `"".rjust(12, "0")` rend « 000000000000 » : douze caracteres, aucune
    exception, et un numero d'article parfaitement plausible fabrique a partir
    de rien. C'est la signature exacte de la classe de defaut que ce projet
    traque — et le chemin y menait tout seul, puisqu'une cellule vide du jeu
    donne la chaine vide.

    Cadrer, c'est completer une valeur. Il n'y a rien a completer ici : le
    refus dit que la donnee manque, la ou le zero disait qu'elle valait zero.
    Pour ecrire reellement douze zeros, il faut le declarer — `defaut:
    "000000000000"`, qui se lit pour ce qu'il est.
    """
    if not valeur.strip():
        raise CompositionInvalide(
            f"`zeros: {largeur}` sur une valeur vide fabriquerait "
            f"« {'0' * int(largeur)} » — un numero d'aspect parfaitement "
            f"normal, a partir de rien. Cadrer, c'est completer une valeur ; "
            f"il n'y en a pas. Verifie la colonne, ou declare un `defaut`")
    return valeur.rjust(int(largeur), "0")


def _tronque(valeur: str, longueur: Any) -> str:
    return valeur[:int(longueur)]


#: Le registre. Ajouter une entree ici est un geste de developpeur, relu
#: comme tel ; une pipeline ne peut que choisir parmi ces noms.
_TRANSFORMATIONS: dict[str, _Definition] = {
    "majuscules": _Definition(
        lambda valeur, _: valeur.upper(), "aucun",
        "met en capitales — SAP stocke la plupart de ses codes ainsi"),
    "minuscules": _Definition(
        lambda valeur, _: valeur.lower(), "aucun", "met en bas de casse"),
    # Le nom dit « autour » parce que c'est un elagage des BORDS, pas une
    # suppression de tous les espaces. « sans_espaces » laissait croire le
    # contraire, et un libelle interne se serait retrouve recolle.
    "sans_espaces_autour": _Definition(
        lambda valeur, _: valeur.strip(), "aucun",
        "elague les espaces de tete et de fin — un export en laisse souvent"),
    "zeros": _Definition(
        _zeros, "entier",
        "cadre a droite en remplissant de zeros jusqu'a la largeur donnee"),
    "tronque": _Definition(
        _tronque, "entier",
        "coupe a la longueur donnee — celle du champ SAP"),
}

NOMS = tuple(sorted(_TRANSFORMATIONS))


def aide() -> str:
    """Les transformations disponibles, pour un ecran ou un message d'erreur."""
    largeur = max(len(nom) for nom in NOMS)
    return "\n".join(f"  {nom:<{largeur}}  {_TRANSFORMATIONS[nom].aide}"
                     for nom in NOMS)


def lire_transformation(brute: Any) -> Transformation:
    """Une entree de `format`, validee au CHARGEMENT.

    Deux formes, et une seule facon d'ecrire chacune :

        format: [majuscules]            sans argument
        format: [{zeros: 12}]           avec argument
    """
    if isinstance(brute, str):
        nom, argument = brute, None
    elif isinstance(brute, dict) and len(brute) == 1:
        nom, argument = next(iter(brute.items()))
    else:
        raise CompositionInvalide(
            f"transformation {brute!r} : attendu un nom, ou un couple "
            f"« nom: argument ». Disponibles :\n{aide()}")

    definition = _TRANSFORMATIONS.get(nom)
    if definition is None:
        raise CompositionInvalide(
            f"transformation {nom!r} inconnue. Disponibles :\n{aide()}")

    if definition.argument == "aucun":
        if argument is not None:
            raise CompositionInvalide(
                f"transformation {nom!r} : aucun argument attendu "
                f"(recu {argument!r})")
    elif definition.argument == "entier":
        if isinstance(argument, bool) or not isinstance(argument, int):
            raise CompositionInvalide(
                f"transformation {nom!r} : un ENTIER est attendu "
                f"(recu {argument!r}). C'est la largeur du champ SAP, et elle "
                f"se declare — la deviner serait inventer du comportement SAP")
        if argument < 1:
            raise CompositionInvalide(
                f"transformation {nom!r} : {argument} n'est pas une largeur")

    return Transformation(nom=nom, argument=argument)


def appliquer(valeur: str,
              transformations: tuple[Transformation, ...]) -> str:
    """Applique les transformations DANS L'ORDRE DECLARE.

    L'ordre compte et n'est pas normalise : `[{zeros: 12}, {tronque: 10}]` ne
    donne pas la meme chose que l'inverse. Reordonner pour l'utilisateur
    serait decider a sa place.
    """
    for transformation in transformations:
        valeur = transformation.appliquer(valeur)
    return valeur
