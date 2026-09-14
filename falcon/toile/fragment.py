"""Une intention de lecture, jamais une couleur. Et une troncature qui se voit.

Un ecran produit des `Fragment`, chacun portant un TON — « danger »,
« attenue », « alerte ». Il ne nomme aucune couleur, donc il ne peut pas
nommer une couleur que le terminal n'a pas : il deciderait a la place du
peintre, et il le deciderait a l'aveugle, depuis un module qui n'a pas lu la
sonde. Le ton dit ce que la ligne VEUT dire ; la traduction appartient au
peintre, qui est le seul a savoir ce qu'il y a en face.

Un ton inconnu LEVE au lieu de retomber au neutre : une ligne « AGIT DANS
SAP » qui perdrait son marquage resterait parfaitement lisible, et personne ne
s'en apercevrait. Un avertissement qui s'efface en silence est exactement le
defaut de ce depot. `Bloc` a la meme garde sur sa FORME, pour la meme raison —
un separateur mal orthographie sortirait en ligne ordinaire et deformerait le
tableau sans bruit.

**La troncature est le seul endroit ou ce module peut perdre du contenu.** Elle
laisse donc toujours une marque, et elle a deux formes :

  - `couper` coupe a droite et pose `~`. Pour de la prose, ou la fin porte
    moins que le debut.
  - `couper_chemin` coupe au MILIEU. Un identifiant SAP est un chemin dont la
    FIN discrimine : `wnd[0]/usr/ctxtWERKS-LOW` et `wnd[0]/usr/ctxtWERKS-HIGH`
    coupes a droite donnent la meme chaine, d'aspect complet — l'un est la
    borne basse d'un intervalle, l'autre la haute, et c'est le genre de
    confusion qui se recopie dans une pipeline.

La marque est `~` et pas `…` : `…` s'encode en cp1252, mais rien ne garantit
qu'une police raster de console Windows en ait le glyphe, et un carre vide ne
se distingue pas d'un caractere de donnee. `~` est de l'ASCII.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

#: Ce qu'une ligne VEUT dire. Jamais ce dont elle a l'air.
NEUTRE = "neutre"
TITRE = "titre"
ATTENUE = "attenue"
SUCCES = "succes"
ALERTE = "alerte"
DANGER = "danger"

TONS = frozenset({NEUTRE, TITRE, ATTENUE, SUCCES, ALERTE, DANGER})

#: Le role d'un bloc dans la page. `ENTETE` et `SEPARATEUR` portent un decor
#: que le bloc ne contient pas : c'est le peintre qui le pose, parce que lui
#: seul connait la largeur.
LIGNE = "ligne"
ENTETE = "entete"
SEPARATEUR = "separateur"
VIDE = "vide"

FORMES = frozenset({LIGNE, ENTETE, SEPARATEUR, VIDE})

#: La marque d'une coupe. De l'ASCII, et ce n'est pas indifferent : voir la
#: docstring du module.
MARQUE = "~"


@dataclass(frozen=True)
class Fragment:
    """Un morceau de ligne et ce qu'il veut dire."""

    texte: str
    ton: str = NEUTRE

    def __post_init__(self) -> None:
        if self.ton not in TONS:
            raise ValueError(
                f"ton inconnu : {self.ton!r}. Les tons connus sont "
                f"{sorted(TONS)}. Retomber au neutre serait pire que lever : "
                f"la ligne resterait lisible et la perte invisible.")


@dataclass(frozen=True)
class Bloc:
    """Une intention de ligne : des fragments, une forme, une marge.

    `marge` est en colonnes a gauche, et elle est portee par le BLOC et non par
    le peintre : c'est une information de mise en page — « ceci est une note de
    bas d'ecran », « ceci est un item de liste » — et le peintre n'a aucun moyen
    de la deviner.
    """

    fragments: tuple[Fragment, ...] = ()
    forme: str = LIGNE
    marge: int = 2

    def __post_init__(self) -> None:
        if self.forme not in FORMES:
            raise ValueError(
                f"forme inconnue : {self.forme!r}. Les formes connues sont "
                f"{sorted(FORMES)}. Un separateur mal orthographie sortirait "
                f"en ligne ordinaire et deformerait le tableau sans bruit.")
        if self.marge < 0:
            raise ValueError(f"marge negative : {self.marge}")


def texte_nu(bloc: Bloc) -> str:
    """Les fragments bout a bout, sans marge ni decor.

    C'est la matiere du bloc, pas son rendu : la marge et le cadre dependent
    de la largeur, donc du peintre.
    """
    return "".join(fragment.texte for fragment in bloc.fragments)


def couper(texte: str, largeur: int) -> str:
    """Coupe a droite et pose la marque. Refuse une largeur qui n'a pas de sens.

    Une largeur nulle ou negative ne rend pas la chaine vide : elle leve. Une
    vue qui se retrouve a couper a zero colonne a un defaut de calcul, et lui
    rendre `""` le lui cacherait — l'ecran sortirait vide, ce qui se lit comme
    « il n'y avait rien a montrer ».
    """
    if largeur <= 0:
        raise ValueError(f"largeur de coupe absurde : {largeur}")
    if len(texte) <= largeur:
        return texte
    return texte[:largeur - 1] + MARQUE


def couper_chemin(texte: str, largeur: int) -> str:
    """Coupe au MILIEU : la fin d'un identifiant SAP est ce qui discrimine.

    `wnd[0]/usr/ctxtWERKS-LOW` et `wnd[0]/usr/ctxtWERKS-HIGH` coupes a droite
    donnent la meme chaine, d'aspect complet. L'un est la borne basse d'un
    intervalle, l'autre la haute ; la confusion se recopie dans une pipeline,
    et c'est SAP qui la decouvre.

    La tete recoit la colonne de plus quand le reste est impair : le prefixe
    `wnd[0]/usr/` est ce qui situe, et le perdre rendrait deux lignes
    indistinctes dans l'autre sens.
    """
    if largeur <= 0:
        raise ValueError(f"largeur de coupe absurde : {largeur}")
    if len(texte) <= largeur:
        return texte
    if largeur == 1:
        return MARQUE
    reste = largeur - 1
    tete = (reste + 1) // 2
    queue = reste - tete
    return texte[:tete] + MARQUE + (texte[len(texte) - queue:] if queue else "")


def colonnes(gabarit, poids: Sequence[int],
             fixes: Sequence[int] = ()) -> tuple[int, ...]:
    """Repartit la largeur restante. Aucune vue ne concatene a la main.

    `fixes` sont les largeurs deja decidees par l'appelant — un numero de rang,
    une empreinte de seize caracteres, les espaces qui separent les colonnes.
    Elles sont RETRANCHEES et ne sont pas rendues. `poids` porte une entree par
    colonne SOUPLE, et le resultat en a autant.

    **Le total rendu plus `fixes` fait exactement `gabarit.colonnes`.** Une
    repartition au prorata qui arrondirait chaque part isolement perdrait
    jusqu'a une colonne par colonne, et la derniere de la rangee deborderait ou
    laisserait un trou — donc on attribue le reliquat aux plus gros restes.

    **On refuse plutot que de rendre une colonne de largeur nulle.** Une
    colonne a zero n'affiche rien du tout, ce qui se lit comme une donnee vide :
    un resultat plausible et faux, et il n'y a rien pour le signaler a
    l'execution.
    """
    if not poids:
        raise ValueError("aucune colonne souple a repartir")
    if any(p <= 0 for p in poids):
        raise ValueError(f"poids nul ou negatif : {tuple(poids)}")

    reste = gabarit.colonnes - sum(fixes)
    if reste < len(poids):
        raise ValueError(
            f"il reste {reste} colonne(s) pour {len(poids)} colonne(s) "
            f"souple(s) sur un gabarit de {gabarit.colonnes} : cette rangee ne "
            f"tient pas, et la tasser rendrait des colonnes vides")

    total = sum(poids)
    parts = [reste * p // total for p in poids]
    restes = sorted(range(len(poids)),
                    key=lambda i: (-(reste * poids[i] % total), i))
    manquant = reste - sum(parts)
    for rang in restes[:manquant]:
        parts[rang] += 1

    # Le prorata peut donner zero a une colonne de poids faible sur une rangee
    # etroite. On emprunte a la plus large, qui reste lisible en perdant une
    # colonne — et si personne ne peut preter, on refuse.
    for rang, part in enumerate(parts):
        if part > 0:
            continue
        preteur = max(range(len(parts)), key=lambda i: parts[i])
        if parts[preteur] <= 1:
            raise ValueError(
                f"{reste} colonne(s) ne suffisent pas a {len(poids)} colonnes "
                f"de poids {tuple(poids)}")
        parts[preteur] -= 1
        parts[rang] = 1

    return tuple(parts)
