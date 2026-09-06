"""Ce qu'on fait d'un verdict — une fois, et au meme endroit pour tous.

Le controleur classe ce que disent les gardes ; le moteur classe ce que levent
la couture et les etapes Python. Les deux appliquent ensuite la MEME regle :
un verdict bloquant interrompt, un verdict « connue fautive » perd l'item, un
verdict benin laisse passer.

Ecrire cette regle a deux endroits, c'est se donner rendez-vous avec le jour
ou l'une des deux copies changera. Elle est donc ici, et les deux l'appellent.

Les exceptions levees viennent du noyau et portent la doctrine dans leur
typage : `ItemAbandonne` est un `Refus` — un repli n'a pas le droit de le
rattraper pour retenter l'item — et `IncidentBloquant` est un `ArretBloquant`.
"""

from __future__ import annotations

from falcon.noyau import IncidentBloquant, ItemAbandonne

from .registre import Verdict


def appliquer(verdict: Verdict, origine: str) -> None:
    """Leve ce que le verdict impose, ou rend la main.

    `origine` est le texte porte par l'exception : il doit dire l'etape, la
    categorie et le detail, parce que c'est ce qu'un humain lira dans le
    rapport de fin sans avoir le journal sous les yeux.
    """
    if verdict.bloquant:
        raise IncidentBloquant(origine)

    if verdict.politique.item == "ko":
        # « Connue fautive » : l'item est perdu, le lot continue. Sans cette
        # levee, l'appel rendrait la main normalement et l'etape suivante —
        # typiquement la sauvegarde — s'executerait sur un ecran dont on vient
        # justement de constater qu'il est faux.
        raise ItemAbandonne(origine)
