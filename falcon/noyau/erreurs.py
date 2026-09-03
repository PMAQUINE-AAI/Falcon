"""Hierarchie d'exceptions.

La separation `Echec` / `Refus` est la traduction en code d'une regle
transverse issue du terrain : **un repli ne doit jamais avaler un refus.**

Quand un mecanisme A echoue et qu'on bascule sur B, un refus DELIBERE emis par
A serait rattrape par la bascule et retente par un mecanisme moins sur. En
faisant de `Refus` une branche qui n'herite pas d'`Echec`, aucun
`except Echec` — c'est-a-dire aucun repli — ne peut l'attraper. La regle n'est
plus une consigne de relecture, elle est portee par le typage.
"""

from __future__ import annotations


class ErreurFalcon(Exception):
    """Racine commune. Ne jamais rattraper directement : trop large."""


# =====================================================================
# Echecs : rattrapables, un repli a le droit d'essayer autre chose
# =====================================================================

class Echec(ErreurFalcon):
    """Quelque chose n'a pas marche. Un repli peut tenter une autre voie."""


class ErreurCouture(Echec):
    """Echec venant de la couche qui parle a SAP."""


class ObjetIntrouvable(ErreurCouture):
    """`findById` n'a rien rendu : controle absent de l'ecran courant."""


class SessionPerdue(ErreurCouture):
    """La session SAP ne repond plus. Rien ne peut etre repris dessus."""


class DelaiDepasse(ErreurCouture):
    """SAP n'a pas rendu la main dans le delai imparti."""


class JournalCorrompu(Echec):
    """Le journal ne peut pas etre relu de bout en bout.

    Une derniere ligne tronquee est toleree : c'est une coupure pendant
    l'ecriture, et l'evenement perdu est celui qu'on allait ecrire. Une ligne
    tronquee AILLEURS est une corruption — le fichier ne dit plus ce qui a ete
    fait, et rien ne doit etre repris dessus.
    """


# =====================================================================
# Refus : deliberes, jamais rattrapes par un repli
# =====================================================================

class Refus(ErreurFalcon):
    """Decision de ne pas agir. Un repli qui l'attrape est un bug."""


class RefusDryRun(Refus):
    """Une action de sauvegarde a ete demandee en dry-run.

    Le dry-run est mecanique : ce n'est pas la boucle qui s'abstient
    d'appeler, c'est la couture qui refuse d'agir.
    """


class ItemAbandonne(Refus):
    """Cet item est perdu ; le lot continue.

    C'est la traduction en exception de la categorie « connue fautive » :
    cause identifiee, politique definie, item marque KO, boucle poursuivie.

    Pourquoi une exception plutot qu'un drapeau a consulter : sans elle,
    chaque appelant devrait se souvenir d'inspecter les constats APRES chaque
    appel, et celui qui oublie enchaine sur la sauvegarde d'un ecran dont le
    champ critique n'a pas pris. C'est precisement le « recopie puis oublie »
    que la couture existe pour supprimer.

    Un `Refus` et non un `Echec` : la decision est deliberee, et un repli qui
    la rattraperait retenterait le meme item par un mecanisme moins sur.
    """


class ArretBloquant(Refus):
    """Le modele du monde est faux. On interrompt tout, y compris la chaine."""


class EcartIdentite(ArretBloquant):
    """Garde 1 : l'ecran courant n'est pas celui que l'etape attendait."""


class FenetreImprevue(ArretBloquant):
    """Garde 3 : une fenetre que l'etape n'avait pas prevue s'est ouverte."""


class PlafondAtteint(ArretBloquant):
    """Garde 5 : le rayon d'action de l'execution est epuise."""


class IncidentBloquant(ArretBloquant):
    """Un incident que la taxonomie ne rend pas poursuivable.

    Soit rien ne l'appariait — l'inconnu est bloquant par defaut — soit
    l'entree qui l'apparie dit explicitement de ne pas poursuivre.
    """


class RepriseIncoherente(ArretBloquant):
    """La reprise porte sur un jeu ou une pipeline qui ont change.

    C'est la garde d'identite appliquee a la reprise : reprendre sur un jeu
    modifie, c'est avoir un modele du monde faux. Meme nature, donc meme
    severite — on arrete.
    """
