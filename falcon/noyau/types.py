"""Types de retour de la couture.

Ces dataclasses sont ce que tout FALCON connait de SAP. Elles sont figees
tot parce que tout le reste s'y adosse : le catalogue les serialise, les
gardes les comparent, le journal les enregistre.

Trois choix meritent leur justification.

**`dynpro` et `numero` sont des chaines.** SAP rend « 045 » ici et « 45 » la.
Les convertir en entier perd le zero de tete que le catalogue doit rendre
diffable ; les comparer bruts produit des faux negatifs. Regle : stockage
verbatim, comparaison par `meme_numero`.

**`Ecran.champs` est une liste plate ordonnee, pas un arbre.** Les
identifiants SONT des chemins, l'arbre se reconstruit ; l'empreinte du
catalogue porte sur l'ensemble des identifiants, donc sur un plat ; et la
resolution par SUFFIXE — imposee par la variabilite des numeros de
sous-ecran — est triviale sur une liste et penible sur un arbre. Le mot
« arbre » de la spec decrit le parcours, pas la structure rendue.

**`Champ.texte` d'un `GuiShell` ne veut rien dire.** Un shell repond a la
propriete `Text` avec son nom de classe ActiveX : une toolbar rend
`SAP.Toolbar.1`. La couture le releve quand meme — c'est un releve fidele —
mais ni le catalogue ni les gardes ne doivent s'en servir pour un shell.
C'est `soustype` qui distingue un vrai editeur d'une barre d'outils.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable


def empreinte(identifiants: Iterable[str]) -> str:
    """Empreinte stable d'un ensemble d'identifiants.

    Clef de variante d'ecran : un meme dynpro ne rend pas toujours les memes
    champs (onglets, layouts, parametres utilisateur), et ne pas traiter cette
    variabilite est la premiere cause d'echec d'un framework de ce type.

    L'empreinte ne depend ni de l'ordre ni des doublons : deux relevés du meme
    ecran donnent la meme valeur.
    """
    uniques = sorted(set(identifiants))
    condense = hashlib.sha256("\n".join(uniques).encode("utf-8"))
    return condense.hexdigest()[:16]


def meme_numero(gauche: str, droite: str) -> bool:
    """Compare deux numeros SAP en ignorant les zeros de tete ('045' == '45')."""
    return gauche.lstrip("0") == droite.lstrip("0")


@dataclass(frozen=True)
class Identite:
    """Ce que rend `screen()` — l'identite de l'ecran courant.

    Le triplet transaction / programme / dynpro est la clef d'ecran de la
    spec. Systeme, mandant et langue s'y ajoutent parce qu'une paire
    audit/remediation peut traverser deux systemes ou deux langues.
    """

    systeme: str = ""
    mandant: str = ""
    langue: str = ""
    transaction: str = ""
    programme: str = ""
    dynpro: str = ""            # chaine : « 0100 » n'est pas « 100 »

    @property
    def triplet(self) -> tuple[str, str, str]:
        return (self.transaction, self.programme, self.dynpro)


@dataclass(frozen=True)
class Champ:
    id: str
    type: str = ""              # GuiTextField, GuiButton, GuiShell...
    soustype: str = ""          # GuiShell.subType — seul moyen de reconnaitre
                                # un vrai editeur de texte parmi les shells
    nom: str = ""
    texte: str = ""             # sans valeur sur un GuiShell : voir l'entete
    modifiable: bool = True
    infobulle: str = ""


@dataclass(frozen=True)
class Ecran:
    """Ce que rend `fields()` — le releve complet d'une fenetre."""

    identite: Identite
    fenetre: str = "wnd[0]"
    titre: str = ""
    champs: tuple[Champ, ...] = ()
    capture_le: str = ""        # ISO 8601 UTC, pose par l'appelant

    @property
    def empreinte(self) -> str:
        return empreinte(c.id for c in self.champs)

    def par_suffixe(self, suffixe: str) -> tuple[Champ, ...]:
        """Champs dont l'identifiant se termine par `suffixe`.

        La resolution par suffixe n'est pas une commodite : le numero de
        sous-ecran figure dans l'identifiant et change avec le type d'objet
        affiche. Un chemin fige cesse de resoudre, la lecture leve, et la
        boucle sort en croyant avoir fini.
        """
        return tuple(c for c in self.champs if c.id.endswith(suffixe))


@dataclass(frozen=True)
class Statut:
    """Ce que rend `status()` — la barre de statut apres une validation."""

    type: str = ""              # "" (barre vide) | S | W | I | E | A
    id: str = ""                # messageId
    numero: str = ""            # messageNumber, chaine : « 045 »
    texte: str = ""
    parametre: str = ""

    @property
    def cle(self) -> str:
        """Clef d'appariement de la taxonomie : « CP:045 »."""
        return f"{self.id}:{self.numero}"

    @property
    def vide(self) -> bool:
        return self.type == ""


@dataclass(frozen=True)
class Fenetre:
    id: str                     # wnd[0], wnd[1]...
    type: str = ""              # GuiMainWindow | GuiModalWindow
    titre: str = ""
    texte: str = ""

    @property
    def modale(self) -> bool:
        return self.id != "wnd[0]"
