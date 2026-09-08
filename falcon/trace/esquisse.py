"""D'une trace vers des esquisses d'ecran — une liste de travail, pas un relevé.

**Ce que ce module produit n'est pas un catalogue, et ne peut jamais le
devenir.** Le recorder enregistre des actions. Il ne dit ni l'identite des
ecrans traverses, ni les champs presents sur chacun. Une esquisse dit donc
seulement : « sur cet ecran-la, tu as touche ces identifiants-ci ». C'est une
liste de ce qu'il reste a aller observer, et c'est deja beaucoup.

Deux protections independantes empechent une esquisse de satisfaire une garde
d'identite, et il en faut deux parce que la premiere seule serait une
convention :

1. `source = esquisse`, que `Depot.pour_garde` refuse explicitement (lot 9) ;
2. **son empreinte ne peut pas coincider avec celle d'un releve reel.**
   L'empreinte porte sur l'ensemble des identifiants PRESENTS ; une esquisse
   n'en connait qu'un sous-ensemble — ceux qui ont ete TOUCHES. Meme si
   quelqu'un forcait la source, la clef ne tomberait pas sur la meme variante.

**Ce que le module refuse de conjecturer.** Le type d'un champ (`GuiTextField`,
`GuiShell`...) se devine assez bien du prefixe de l'identifiant — `txt`, `btn`,
`chk`. Assez bien n'est pas assez : `cntlALV_CONTAINER_1/shellcont/shell` est
un shell, mais lequel ? Un type faux serait pire qu'un type absent, parce qu'il
aurait l'air d'un releve. Les champs d'une esquisse n'ont donc pas de type.

Le programme et le dynpro ne sont pas conjectures non plus : ils sont marques
`NON_RENSEIGNE`, visiblement, pour que personne ne les prenne pour un relevé.
Seule la transaction se lit — dans le champ de commande, `/nIH06`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from falcon.catalogue import ESQUISSE, ClefVariante, Variante
from falcon.noyau import SUFFIXE_CHAMP_DE_COMMANDE, Champ, empreinte

from .modele import Geste, Trace

#: Ce que la trace ne dit pas, et qu'on refuse de deviner. Visible a l'oeil nu
#: dans le YAML du catalogue : personne ne le confondra avec un releve.
NON_RENSEIGNE = "?"

#: Gestes qui font repartir SAP — donc changer d'ecran.
#:
#: `sendVKey` y figure en entier, alors que certaines touches sont purement
#: locales. Le decoupage est volontairement pessimiste : une coupure de trop
#: fragmente l'esquisse, une coupure de moins melange deux ecrans en un seul et
#: produit une empreinte qui ne correspond a rien. Des deux erreurs, seule la
#: seconde est silencieuse.
NAVIGATION = frozenset({
    "press", "sendVKey", "doubleClickCurrentCell", "doubleClickNode", "close",
})

#: Le champ de commande : la seule source de la transaction dans une trace.
#:
#: Defini au noyau, pas ici : le moteur en a besoin lui aussi, pour le retour
#: a l'ecran d'accueil entre deux pipelines d'une chaine. Deux definitions
#: finiraient par diverger.
CHAMP_DE_COMMANDE = SUFFIXE_CHAMP_DE_COMMANDE

#: `/nIH06` → `IH06`. `/n` seul ramene au menu, et ne nomme aucune transaction.
_CODE = re.compile(r"^/n(?P<transaction>\S+)$")

#: Une cible qui EST une fenetre, pas un champ dedans.
_FENETRE_NUE = re.compile(r"^wnd\[\d+\]$")


def vise_le_champ_de_commande(geste: Geste) -> bool:
    """Ce geste ecrit-il dans le champ de commande.

    Reconnu par le SUFFIXE, parce que c'est ce qu'une trace porte. Pour y
    ECRIRE, c'est l'identifiant complet `CHAMP_DE_COMMANDE` qu'il faut — la
    distinction est ecrite au vocabulaire du noyau, et la confondre ferait
    ecrire dans un champ qui n'existe pas.
    """
    return geste.cible.endswith(CHAMP_DE_COMMANDE) and isinstance(
        geste.valeur, str)


def code_transaction(geste: Geste) -> str:
    """La transaction que ce geste nomme dans le champ de commande, ou "".

    `/nIH06` → `IH06`. `/n` seul → `""` : il ramene au menu et ne nomme
    aucune transaction. Un geste qui ne vise pas le champ de commande → `""`.

    **Public, et lu par deux modules.** `visites()` s'en sert pour etiqueter
    l'esquisse SUIVANTE — jamais celle ou le code est tape, le piege que ce
    module documente plus bas — et `exploration/parcours.py` pour savoir sur
    quel code transaction une branche interrompue peut reprendre. Deux
    expressions regulieres finiraient par diverger, et le jour ou l'une
    accepterait `/o` sans l'autre, une reprise ouvrirait une seconde session
    SAP pendant que le driver continuerait de parler a la premiere.
    """
    if not vise_le_champ_de_commande(geste):
        return ""
    trouve = _CODE.match(geste.valeur)                  # type: ignore[arg-type]
    return trouve.group("transaction") if trouve else ""


@dataclass(frozen=True)
class Visite:
    """Un passage sur un ecran, tel que la trace permet de le decouper.

    « Tel que la trace permet » : la coupure est deduite des gestes de
    navigation, pas observee. Deux visites successives peuvent etre le meme
    ecran, et rien dans la trace ne permet de le dire.
    """

    ordre: int
    fenetre: str
    transaction: str                # conjecturee, "" si inconnue
    gestes: tuple[Geste, ...]

    @property
    def cibles(self) -> tuple[str, ...]:
        """Identifiants touches, dans l'ordre, sans doublon.

        Les fenetres nues (`wnd[0]`) sont ecartees : `maximize` et `sendVKey`
        s'adressent a la fenetre, pas a un champ, et les compter comme champs
        peuplerait l'esquisse d'objets qui n'en sont pas.
        """
        vues: list[str] = []
        for geste in self.gestes:
            if _FENETRE_NUE.match(geste.cible) or geste.cible in vues:
                continue
            vues.append(geste.cible)
        return tuple(vues)


def visites(trace: Trace) -> tuple[Visite, ...]:
    """Decoupe la trace en passages d'ecran.

    Une visite se termine sur un geste de navigation, ou sur un changement de
    fenetre. Le geste de navigation appartient a la visite qu'il termine :
    c'est sur l'ecran d'AVANT qu'on a appuye sur le bouton.

    **Un code saisi dans le champ de commande vaut pour la visite SUIVANTE**,
    jamais pour celle ou il est tape. Taper `/nIH06` se fait depuis l'ecran
    d'avant — le menu, ou la transaction precedente. Attribuer l'ecran de
    saisie a IH06 produirait une esquisse etiquetee d'une transaction ou elle
    n'a jamais ete vue, sans que rien ne leve.

    **La conjecture suppose que le code est accepte.** La trace observee
    contient `/nIW2ç`, une faute de frappe : SAP refuse, reste sur la
    transaction courante, et affiche une erreur. La trace ne le dit pas, et
    aucune lecture ne peut le savoir. Une transaction conjecturee reste donc
    une conjecture — c'est aussi pour ca que l'esquisse ne peut pas garder un
    ecran.
    """
    decoupees: list[Visite] = []
    courants: list[Geste] = []
    courante = ""                   # transaction en vigueur pour cette visite
    prochaine = ""                  # celle que le champ de commande annonce

    def clore() -> None:
        nonlocal courante
        if courants:
            decoupees.append(Visite(
                ordre=len(decoupees) + 1, fenetre=courants[0].fenetre,
                transaction=courante, gestes=tuple(courants)))
            courants.clear()
        courante = prochaine

    for geste in trace.gestes:
        if courants and geste.fenetre != courants[0].fenetre:
            clore()
        courants.append(geste)
        if vise_le_champ_de_commande(geste):
            # `/n` seul ramene au menu : la transaction redevient inconnue.
            prochaine = code_transaction(geste)
        if geste.verbe in NAVIGATION:
            clore()
    clore()
    return tuple(decoupees)


def esquisse_de(visite: Visite, *, capture_le: str = "") -> Variante | None:
    """L'esquisse d'une visite, ou rien si elle n'a touche aucun champ."""
    cibles = visite.cibles
    if not cibles:
        return None
    return Variante(
        clef=ClefVariante(
            transaction=visite.transaction or NON_RENSEIGNE,
            programme=NON_RENSEIGNE, dynpro=NON_RENSEIGNE,
            empreinte=empreinte(cibles)),
        champs=tuple(Champ(id=cible, type="") for cible in cibles),
        titre="", capture_le=capture_le, source=ESQUISSE,
    )


def esquisses(trace: Trace, *, capture_le: str = "") -> tuple[Variante, ...]:
    """Les esquisses d'une trace, dedoublonnees sur la clef.

    Le meme ecran visite cinq fois avec les memes champs touches ne produit
    qu'une esquisse : le catalogue en garderait une de toute facon, et un
    rapport qui en annonce cinq ferait croire a cinq ecrans.
    """
    retenues: dict[ClefVariante, Variante] = {}
    for visite in visites(trace):
        esquisse = esquisse_de(visite, capture_le=capture_le)
        if esquisse is not None:
            retenues.setdefault(esquisse.clef, esquisse)
    return tuple(retenues.values())


def deposer(trace: Trace, depot, *, capture_le: str = ""
            ) -> tuple[ClefVariante, ...]:
    """Verse les esquisses d'une trace **en quarantaine**.

    En quarantaine et non au catalogue : une esquisse n'a ete relue par
    personne, et le catalogue cure ne doit contenir que ce qu'un humain a
    valide. Meme promue, elle reste une esquisse — `pour_garde` continue de la
    refuser, et c'est voulu : la promotion dit « j'ai vu le fichier », pas
    « j'ai vu l'ecran ».
    """
    clefs = []
    for esquisse in esquisses(trace, capture_le=capture_le):
        depot.mettre_en_quarantaine(esquisse)
        clefs.append(esquisse.clef)
    return tuple(clefs)


def apercu(trace: Trace) -> str:
    """Ce que la trace laisse conjecturer des ecrans traverses.

    Rendu depuis une `Trace`, donc depuis une lecture STRICTE : une trace a
    moitie comprise n'a pas d'apercu d'ecrans, parce qu'un decoupage fait sur
    des lignes manquantes serait faux sans le dire.
    """
    decoupees = visites(trace)
    conjecturees = esquisses(trace)
    lignes = [
        "  ecrans conjectures",
        f"    visites        {len(decoupees)}",
        f"    esquisses      {len(conjecturees)}  (dedoublonnees sur la clef)",
    ]

    inconnues = [v for v in decoupees if not v.transaction]
    if inconnues:
        lignes.append(f"    sans transaction {len(inconnues):>2}  "
                      f"(avant le premier code, ou apres un retour au menu)")

    lignes.append("")
    lignes.append(f"    programme et dynpro : {NON_RENSEIGNE!r} — une trace ne "
                  f"les dit pas.")
    lignes.append("    Ces esquisses sont une liste de ce qu'il reste a aller "
                  "observer ;")
    lignes.append("    aucune ne peut satisfaire une garde d'identite.")
    return "\n".join(lignes)
