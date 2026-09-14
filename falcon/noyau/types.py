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
import re
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

    #: `None` = **on ne sait pas**, et c'est le defaut a dessein.
    #:
    #: Le defaut valait `True`. Un champ d'esquisse — conjecture depuis une
    #: trace, donc jamais observe — sortait donc « modifiable : oui » au
    #: dictionnaire et `modifiable: true` au catalogue. Mesure sur la trace de
    #: reference : 45 lignes affirmant d'un champ que personne n'a vu qu'il
    #: est ecrivable. C'est le defaut que ce depot traque, dans sa forme la
    #: plus pure — une affirmation d'aspect normal, fausse, produite par un
    #: defaut de dataclass.
    #:
    #: La couture renseigne toujours l'attribut (`sapgui.py`, `Changeable`) :
    #: un releve reel n'est donc jamais `None`, et le tri-etat ne coute rien
    #: la ou l'information existe.
    modifiable: bool | None = None
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


#: Le segment de fenetre dans un identifiant SAP, cherche en SOUS-CHAINE.
#:
#: **Ancrer au debut etait le defaut, et il a mordu sur un vrai systeme.**
#: `couture/sapgui.py` fait `str(objet.Id)` ; SAP GUI rend un chemin ABSOLU —
#: `/app/con[0]/ses[0]/wnd[0]` — la ou les traces du recorder, les pipelines et
#: toutes les fixtures de ce depot ecrivent `wnd[0]`. Les deux formes designent
#: la meme fenetre, et `findById` accepte les deux : c'est une difference
#: d'ECRITURE, pas de sens.
#:
#: Tant que rien ne les rapprochait, tout ce depot comparait la forme longue a
#: la forme courte et concluait « ce n'est pas wnd[0] ». Sur K62/060, une
#: session parfaitement normale — une seule fenetre ouverte, aucune modale —
#: a donc vu son exploration refusee au deuxieme geste, au motif qu'« une
#: fenetre autre que wnd[0] est ouverte ». Aucune exception, un refus
#: parfaitement argumente, et FAUX.
#:
#: `catalogue/inventaire.py` avait deja trouve et contourne le meme ecart pour
#: son propre affichage. Le contournement local est ce qui a permis au defaut
#: de survivre ailleurs : la regle vit desormais ICI, au noyau, et les trois
#: sites qui comparent des fenetres l'appellent.
_SEGMENT_DE_FENETRE = re.compile(r"wnd\[\d+\]")

#: La fenetre principale, dans la forme canonique de ce depot.
FENETRE_PRINCIPALE = "wnd[0]"


def fenetre_de(identifiant: str) -> str:
    """`wnd[N]` lu dans un identifiant SAP, quelle qu'en soit l'ecriture.

    Rend la chaine VIDE quand l'identifiant n'en nomme aucune — et c'est un
    refus, pas un defaut. Rendre `wnd[0]` serait l'affirmation exacte que la
    modale rend dangereuse : un controle qu'on ne sait pas situer ne doit pas
    etre repute etre dans la fenetre principale.

    On prend la PREMIERE occurrence : un identifiant SAP est un chemin, et sa
    fenetre est le segment le plus haut. Aucun identifiant reel n'en porte deux,
    mais « la premiere » est une regle, « la seule » serait une supposition.
    """
    trouve = _SEGMENT_DE_FENETRE.search(identifiant)
    return trouve.group(0) if trouve else ""


@dataclass(frozen=True)
class Fenetre:
    id: str                     # wnd[0], ou /app/con[0]/ses[0]/wnd[0]
    type: str = ""              # GuiMainWindow | GuiModalWindow
    titre: str = ""
    texte: str = ""

    @property
    def nom(self) -> str:
        """`wnd[N]`, la forme que ce depot ecrit partout ailleurs.

        Vide si l'identifiant n'en nomme aucune — voir `fenetre_de`.
        """
        return fenetre_de(self.id)

    @property
    def modale(self) -> bool:
        """VRAI seulement si l'on a LU une fenetre qui n'est pas la principale.

        Un identifiant qu'on ne sait pas situer rend FAUX : « je ne sais pas »
        ne se journalise pas comme « c'est une modale ». Le nommer modale
        ferait refuser une session normale ; le nommer principale ferait
        accepter une modale. Entre les deux, la seule issue honnete est que
        l'appelant voie l'identifiant brut — et les refus le citent desormais.
        """
        nom = self.nom
        return bool(nom) and nom != FENETRE_PRINCIPALE
