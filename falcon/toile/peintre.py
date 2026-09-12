"""Du sens vers des lignes — et la garde qui interdit de peindre a l'aveugle.

`PeintreNu` n'est pas un repli : c'est la DEFINITION de ce que l'autre doit
rendre une fois le decor retire. `PeintreColore` appelle `super().peindre` puis
enveloppe : la structure — le nombre de lignes, leur decoupage, leur contenu —
reste celle du niveau NU par CONSTRUCTION, et pas par relecture. Un peintre qui
reconstruirait ses lignes pourrait en produire un nombre different, et c'est le
premier endroit ou les deux niveaux divergeraient sans que personne ne leve.

`_exiger_la_preuve` est une garde NOMMEE, et elle est appelee depuis ce module
meme — pas importee ailleurs. C'est la condition pour qu'elle se neutralise :
`outils/neutraliser.py` fait `setattr` sur le module porteur, et une reference
figee par un `from ... import` a l'exterieur ne verrait jamais le
remplacement. C'est exactement pour cela que `lecteur.garde_du_monde` est
appelee dans son propre module.

Et elle LEVE au lieu de rendre un booleen. Une garde qui rendrait `False` en
cas de doute deviendrait, une fois remplacee par `lambda *a, **k: None`, une
garde qui rend `None` — donc faux, donc le refus tiendrait quand meme, et
l'outil la declarerait muette a tort. **Une neutralisation doit rendre le code
PERMISSIF, sinon elle ne prouve rien.**

Ce qu'elle empeche, concretement : `<-[31m` en toutes lettres dans le journal
de qui a redirige sa sortie, et un ecran de vomi sur un conhost qui
n'interprete pas VT. Aucune exception, aucun code retour : l'utilisateur
conclut que l'outil est casse et n'y revient pas.

**Le ton qui sort est celui du BLOC**, c'est-a-dire de son premier fragment
marque. Teindre fragment par fragment obligerait a retrouver, dans une ligne
deja fondue et deja tronquee, les bornes de chacun : une reconstruction, donc
la porte exacte par laquelle les deux niveaux finiraient par diverger. Les
maquettes n'annotent que des lignes entieres ; le jour ou une vue aura besoin
de deux tons sur une meme ligne, c'est le niveau NU qu'il faudra changer, sous
l'invariant, et pas le peintre colore en cachette.
"""

from __future__ import annotations

from typing import Protocol

from .capacites import COULEUR, NU, Capacites, Gabarit
from .fragment import (
    ENTETE, NEUTRE, SEPARATEUR, VIDE, Bloc, couper, texte_nu,
)
from .sequences import teinter


class RenduRefuse(Exception):
    """Peindre plus haut qu'on n'a prouve. Un refus, jamais une degradation."""


def _exiger_la_preuve(capacites: Capacites, niveau: int) -> None:
    """GARDE n°9. Leve `RenduRefuse` si l'on peint plus haut qu'on n'a prouve.

    Elle n'est pas de la meme espece que les huit autres : elle ne refuse rien
    a SAP. Ce qu'elle protege est le TERMINAL de celui qui vient de faire agir
    un ERP — et un compte rendu illisible est la pire chose qui puisse arriver
    juste apres.
    """
    if niveau <= NU:
        return
    if capacites.niveau >= niveau:
        return
    raise RenduRefuse(
        f"rendu de niveau {niveau} demande sur le flux "
        f"{capacites.flux or '(sans nom)'}, qui n'a prouve que "
        f"{capacites.niveau} : interactif={capacites.interactif}, "
        f"ansi={capacites.ansi}, couleur={capacites.couleur}. "
        f"Motifs : {'; '.join(capacites.motifs) or 'aucune mesure faite'}.")


class Peintre(Protocol):
    """Ce qu'un ecran attend de son peintre, et rien de plus."""

    niveau: int

    def peindre(self, bloc: Bloc, gabarit: Gabarit) -> list[str]: ...


class PeintreNu:
    """L'identite : des blocs vers des lignes, sans un octet de decor.

    C'est ce module qui decide de la geometrie — marge, cadre, troncature — et
    c'est le seul. Tout ce qui se voit a l'ecran passe par ici, y compris au
    niveau COULEUR, et c'est ce qui rend l'invariant demontrable plutot
    qu'espere.
    """

    niveau = NU

    def peindre(self, bloc: Bloc, gabarit: Gabarit) -> list[str]:
        largeur = gabarit.colonnes
        marge = min(bloc.marge, max(largeur - 1, 0))

        if bloc.forme == VIDE:
            return [""]
        if bloc.forme == SEPARATEUR:
            return [" " * marge + "-" * (largeur - marge)]
        if bloc.forme == ENTETE:
            cadre = " " * marge + "=" * (largeur - marge)
            retrait = marge + 2
            return [cadre,
                    " " * retrait + couper(texte_nu(bloc), largeur - retrait),
                    cadre]
        return [" " * marge + couper(texte_nu(bloc), largeur - marge)]


class PeintreColore(PeintreNu):
    """`super().peindre`, puis une enveloppe. Jamais une ligne de plus.

    La teinte se pose sur la ligne ENTIERE, blancs de marge compris : c'est ce
    qui garantit que `retirer` rende exactement ce que le niveau NU avait
    produit. Une teinte posee sur le seul texte utile obligerait a recalculer
    ou il commence, donc a reconstruire la ligne.
    """

    niveau = COULEUR

    def peindre(self, bloc: Bloc, gabarit: Gabarit) -> list[str]:
        lignes = super().peindre(bloc, gabarit)
        ton = _ton_du_bloc(bloc)
        if ton == NEUTRE:
            return lignes
        return [teinter(ligne, ton) if ligne.strip() else ligne
                for ligne in lignes]


def _ton_du_bloc(bloc: Bloc) -> str:
    """Le premier ton marque du bloc, ou `NEUTRE`.

    « Le premier » et pas « le dernier » : une vue qui veut marquer une ligne
    pose le fragment qui porte l'avertissement en tete, comme les maquettes le
    font. Prendre le dernier ferait dependre le marquage d'un suffixe de mise
    en page ajoute plus tard.
    """
    for fragment in bloc.fragments:
        if fragment.ton != NEUTRE:
            return fragment.ton
    return NEUTRE


def peintre_pour(capacites: Capacites, *, forcer_nu: bool = False) -> Peintre:
    """Le peintre que CE flux a merite.

    La forme du code n'est pas indifferente : on demande la COULEUR, et c'est
    la garde qui refuse. Un `if capacites.niveau == COULEUR` rendrait la garde
    tautologique — elle ne pourrait plus jamais lever, donc la neutraliser ne
    changerait rien, donc `outils/neutraliser.py` la declarerait muette. Une
    garde dont le retrait ne se voit pas ne garde rien.
    """
    if forcer_nu:
        return PeintreNu()
    try:
        _exiger_la_preuve(capacites, COULEUR)
    except RenduRefuse:
        return PeintreNu()
    return PeintreColore()
