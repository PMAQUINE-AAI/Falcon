"""D'un geste de trace vers un appel de couture — table FERMEE, sans devinette.

Ce module est la traduction que `falcon/trace/brouillon.py` ne pouvait pas
faire. Le brouillon vise les ACTIONS DE PIPELINE (`pipeline/modele.py`,
`ACTIONS`), qui n'en comptent aucune pour une grille ALV : ses vingt-deux
gestes « non rejouables » sont donc une limite du MODELE DE PIPELINE, pas de
la couture. La couture, elle, expose `grid_select_rows`,
`grid_set_current_row` et `grid_double_click` (decision n°14). Traduire au
niveau du DRIVER rend douze de ces vingt-deux rejouables. Les dix autres sont
des gestes d'ARBRE, et ceux-la sont hors de portee pour de bon : la couture
n'a aucune methode d'arbre, volontairement.

**La table est fermee sur `trace.modele.VERBES`, et le module refuse de se
charger si elle ne l'est plus.** Un verbe releve sur une trace reelle et
oublie ici serait un geste que l'explorateur passerait sous silence : le
rejeu differerait de l'enregistrement sans que rien ne leve. Ajouter un verbe
a `VERBES` oblige donc a decider, ici, ce qu'on en fait — quitte a decider
qu'on n'en fait rien, mais en l'ecrivant.

**Rien n'est « absent » : ce qui n'a pas d'issue en a une raison.** Les quatre
verbes d'arbre et les trois verbes de confort figurent nommement dans la
table, avec leur motif. Une table ou l'arbre serait simplement absent
ressemblerait a un oubli, et le prochain lecteur l'aurait « corrige ».

**Ce module ne parle a aucun driver.** Il rend la DESCRIPTION d'un appel — un
nom de methode et des arguments — que l'appelant fait, ou ne fait pas. C'est
ce qui permet a `falcon/exploration/` de ne jamais importer `falcon.couture`
(regle de frontiere), et ce qui rend la table verifiable sans SAP : un test
confronte chaque nom de methode a `couture.interface.Driver`.

**Le piege des types, qui est l'inverse de celui qu'on attend.** Un argument
de trace n'est PAS toujours du texte : le parseur rend trois types — chaine,
entier, booleen — et il les rend parce que l'API SAP les distingue. Sur le
meme objet ALV, la trace ecrit `selectedRows = "0"`, une CHAINE, et
`currentCellRow = 4`, un ENTIER (voir l'en-tete de `trace/modele.py`). La
table exige donc de chaque verbe le type observe et REFUSE l'autre, au lieu
de convertir : une conversion silencieuse est precisement la normalisation
que le lecteur de traces s'interdit.

**Ce que la table ne fait pas.**

- elle ne devine pas : aucun verbe n'est traduit « par ressemblance » d'un
  identifiant ou d'un prefixe ;
- elle ne normalise pas : elle ne convertit pas un type en un autre, ne trie
  ni ne dedoublonne les rangs, ne rogne pas les espaces d'un argument ;
- elle ne repare pas : `/nIW2ç` — la faute de frappe de l'operateur dans la
  trace de reference — est ecrite telle quelle, et c'est SAP qui la refusera ;
- elle ne juge pas de la surete : elle traduit `press` sur
  `tbar[0]/btn[11]` — le bouton Sauvegarder — comme n'importe quel autre
  bouton. Le refuser ici donnerait une exploration qui a l'air d'avoir tout
  rejoue ; c'est `DriverGarde` en dry-run, plafond de sauvegardes a zero, qui
  doit refuser, parce que c'est lui qui est teste pour ca ;
- elle n'execute rien et n'ordonne rien : conserver l'ordre des gestes —
  `currentCellRow` AVANT `selectedRows`, sans quoi le double-clic porte sur la
  premiere ligne — est le travail de l'appelant, qui les recoit dans l'ordre
  de la trace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from falcon.trace.modele import CONFORT, FENETRE_RACINE, VERBES, Geste

# -- genres de traduction ---------------------------------------------------

#: Le geste devient un appel de couture.
TRADUIT = "traduit"

#: Geste de confort : ecarte a dessein, il ne change rien dans SAP.
ECARTE_CONFORT = "confort"

#: Verbe connu de la trace, mais qu'aucune methode de couture n'exprime.
SANS_COUTURE = "sans_couture"

#: Verbe traduisible, mais dont l'argument de CE geste n'est pas utilisable.
ARGUMENT_REFUSE = "argument_refuse"

#: Verbe absent de `VERBES` : la lecture tolerante en laisse passer, et
#: `Geste.connu` les signale. La table n'a rien a en dire, et le dit.
VERBE_INCONNU = "verbe_inconnu"

GENRES = (TRADUIT, ECARTE_CONFORT, SANS_COUTURE, ARGUMENT_REFUSE,
          VERBE_INCONNU)

# -- formes d'appel ---------------------------------------------------------
#
# La forme dit COMMENT les arguments de l'appel se fabriquent depuis le geste.
# Elle ne se confond pas avec `Geste.forme`, qui decrit la syntaxe VBScript de
# la ligne lue.

#: `methode(cible)` — le geste n'a pas de valeur.
SANS_ARGUMENT = "sans_argument"

#: `methode(cible, texte)` — valeur de trace `str`.
TEXTE = "texte"

#: `methode(cible, coche)` — valeur de trace `bool`.
BOOLEEN = "booleen"

#: `methode(cible, rangs)` — valeur de trace `str`, index separes par virgule.
RANGS = "rangs"

#: `methode(cible, ligne)` — valeur de trace `int`.
LIGNE = "ligne"

#: `methode(touche, fenetre)` — valeur de trace `int`, cible = une fenetre.
TOUCHE = "touche"

#: `methode(constante, fenetre)` — la touche vient de la table, pas du geste.
TOUCHE_FIXE = "touche_fixe"

SIGNATURES = (SANS_ARGUMENT, TEXTE, BOOLEEN, RANGS, LIGNE, TOUCHE,
              TOUCHE_FIXE)

#: F12, « Annuler » : ce que la decision n°14 a arrete pour fermer une modale,
#: la couture n'ayant pas de methode `close`.
#:
#: Redefini plutot qu'importe de `trace.brouillon` : les deux traductions sont
#: independantes, et l'une ne doit pas devenir la source de l'autre par
#: commodite. Un test epingle leur egalite — c'est ce qui les empeche de
#: diverger en silence.
VKEY_ANNULER = 12

#: Une cible qui EST une fenetre, pas un champ dedans. `sendVKey` et `close`
#: n'en visent jamais d'autre dans la trace de reference — verifie.
_FENETRE_NUE = re.compile(r"^wnd\[\d+\]$")

#: Les seuls rangs d'ALV qu'on accepte de lire : des index decimaux separes
#: par des virgules, sans espace ni intervalle.
#:
#: `[0-9]` et non `\d` : en Python, `\d` couvre TOUS les chiffres Unicode, et
#: `int()` les convertit sans broncher. `selectedRows = "٠"` — un zero
#: arabo-indien — passait donc pour l'index 0 (mesure). Ce n'est pas ce que le
#: recorder SAP ecrit ; c'est un caractere qui ressemble a un chiffre et qui
#: devenait une ligne de grille en silence, ce qui est exactement la
#: normalisation muette que ce module s'interdit ailleurs.
_RANGS = re.compile(r"[0-9]+(?:,[0-9]+)*")


class TableIncoherente(Exception):
    """La table ne recouvre plus les verbes de trace, ou se contredit."""


class _Refus(Exception):
    """Refus d'un argument, interne au module. Devient une `Traduction`."""


@dataclass(frozen=True)
class Regle:
    """Ce que la table dit d'un VERBE — independamment de tout geste.

    `raison` est obligatoire des qu'il n'y a pas de methode, et des que le
    verbe rendu n'est pas celui de la trace : ce sont les deux seuls endroits
    ou la table s'ecarte de l'enregistrement, et aucun ne doit etre muet.
    """

    verbe: str
    genre: str                       # TRADUIT | ECARTE_CONFORT | SANS_COUTURE
    methode: str = ""                # nom d'une methode de couture.Driver
    signature: str = ""              # l'une des SIGNATURES
    constante: int | None = None     # pour TOUCHE_FIXE seulement
    substitue: bool = False          # le verbe rendu n'est pas celui lu
    raison: str = ""

    def __post_init__(self) -> None:
        if self.genre not in (TRADUIT, ECARTE_CONFORT, SANS_COUTURE):
            raise TableIncoherente(
                f"{self.verbe} : genre {self.genre!r} inconnu")
        if self.genre == TRADUIT:
            if not self.methode or self.signature not in SIGNATURES:
                raise TableIncoherente(
                    f"{self.verbe} : traduit, mais sans methode ni signature "
                    f"utilisable")
            if self.substitue and not self.raison:
                raise TableIncoherente(
                    f"{self.verbe} : substitution muette. Une traduction qui "
                    f"rend un autre verbe que celui de la trace doit dire "
                    f"lequel et pourquoi")
            if (self.signature == TOUCHE_FIXE) != (self.constante is not None):
                raise TableIncoherente(
                    f"{self.verbe} : une constante n'a de sens que pour "
                    f"{TOUCHE_FIXE!r}, et {TOUCHE_FIXE!r} en exige une")
        else:
            if self.methode or self.signature:
                raise TableIncoherente(
                    f"{self.verbe} : sans issue, mais nomme une methode")
            if not self.raison:
                raise TableIncoherente(
                    f"{self.verbe} : sans issue et sans raison. Un verbe sans "
                    f"issue doit dire pourquoi, sinon il ressemble a un oubli")


@dataclass(frozen=True)
class Appel:
    """Un appel de couture DECRIT, pas fait.

    L'appelant le realise par `getattr(driver, appel.methode)(*arguments)`.
    Le module n'a donc besoin d'aucun driver, et n'en importe aucun.
    """

    methode: str
    arguments: tuple[object, ...]
    substitue: bool = False

    def rendu(self) -> str:
        """`grid_select_rows('wnd[1]/...', (0,))` — pour les comptes rendus."""
        return f"{self.methode}({', '.join(repr(a) for a in self.arguments)})"


@dataclass(frozen=True)
class Traduction:
    """Ce que la table repond d'UN geste : un appel, ou un refus motive.

    Il n'y a pas de troisieme etat. Un geste sans appel porte toujours une
    raison, et c'est ce que verifie `__post_init__` : une traduction vide et
    muette se compterait comme « rien a faire » dans un compte rendu.
    """

    geste: Geste
    genre: str
    appel: Appel | None = None
    raison: str = ""

    def __post_init__(self) -> None:
        if self.genre not in GENRES:
            raise TableIncoherente(f"genre {self.genre!r} inconnu")
        if self.appel is None and not self.raison:
            raise TableIncoherente(
                f"ligne {self.geste.ligne} : traduction sans appel et sans "
                f"raison")
        if self.appel is not None and self.genre != TRADUIT:
            raise TableIncoherente(
                f"ligne {self.geste.ligne} : un appel sous le genre "
                f"{self.genre!r}")

    @property
    def rejouable(self) -> bool:
        return self.appel is not None


#: Verbe de trace -> ce qu'on en fait. FERMEE sur `VERBES` (voir plus bas).
#:
#: Huit verbes se traduisent, quatre sont hors de portee, trois sont ecartes.
#: Sur la trace de reference, cela fait 22 gestes non rejouables par le
#: brouillon dont 12 le redeviennent ici, et 10 qui ne le redeviennent pas.
TABLE: dict[str, Regle] = {
    # -- navigation et saisie ------------------------------------------
    "press": Regle("press", TRADUIT, "press", SANS_ARGUMENT),
    "text": Regle("text", TRADUIT, "write", TEXTE),
    "selected": Regle("selected", TRADUIT, "set_checked", BOOLEEN),
    "sendVKey": Regle("sendVKey", TRADUIT, "vkey", TOUCHE),
    "close": Regle(
        "close", TRADUIT, "vkey", TOUCHE_FIXE, constante=VKEY_ANNULER,
        substitue=True,
        raison=(f"la couture n'a pas de methode `close` : la decision n°14 "
                f"arrete que vkey({VKEY_ANNULER}) — F12, Annuler — ferme une "
                f"modale. Le geste rejoue n'est donc pas celui de la trace")),

    # -- grille ALV : ce que le brouillon ne pouvait pas exprimer -------
    #
    # Ces trois verbes sont refuses par `trace/brouillon.py` parce que
    # `pipeline/modele.py:ACTIONS` n'a aucune action de grille. La couture,
    # elle, les a — decision n°14. Selectionner par INDEX reste un piege pour
    # une pipeline, et n'en est pas un pour une cartographie : l'empreinte du
    # catalogue porte sur les identifiants des champs presents, pas sur la
    # ligne touchee.
    "selectedRows": Regle("selectedRows", TRADUIT, "grid_select_rows", RANGS),
    "currentCellRow": Regle(
        "currentCellRow", TRADUIT, "grid_set_current_row", LIGNE),
    "doubleClickCurrentCell": Regle(
        "doubleClickCurrentCell", TRADUIT, "grid_double_click", SANS_ARGUMENT),

    # -- arbre : hors de portee, et pas par oubli -----------------------
    #
    # La couture n'expose aucune methode d'arbre, et la decision n°14 dit
    # pourquoi : l'arbre de menu depend des favoris de chacun, une pipeline
    # qui en dependrait casserait sur un autre poste ; on navigue par code
    # transaction dans `okcd`, ce qui est deterministe. Rejouer ces gestes
    # demanderait d'elargir la couture, qui est epinglee.
    "expandNode": Regle(
        "expandNode", SANS_COUTURE,
        raison="geste d'arbre : la couture n'a aucune methode d'arbre "
               "(decision n°14 — on navigue par code transaction dans okcd, "
               "l'arbre depend des favoris du poste)"),
    "selectedNode": Regle(
        "selectedNode", SANS_COUTURE,
        raison="geste d'arbre : la couture n'a aucune methode d'arbre "
               "(decision n°14 — on navigue par code transaction dans okcd, "
               "l'arbre depend des favoris du poste)"),
    "doubleClickNode": Regle(
        "doubleClickNode", SANS_COUTURE,
        raison="geste d'arbre : la couture n'a aucune methode d'arbre "
               "(decision n°14 — on navigue par code transaction dans okcd, "
               "l'arbre depend des favoris du poste). Il NAVIGUE : le sauter "
               "laisse l'exploration sur un autre ecran que la trace"),
    "topNode": Regle(
        "topNode", SANS_COUTURE,
        raison="geste d'arbre : la couture n'a aucune methode d'arbre "
               "(decision n°14 — on navigue par code transaction dans okcd, "
               "l'arbre depend des favoris du poste)"),

    # -- confort : ecartes, et sans consequence -------------------------
    "setFocus": Regle(
        "setFocus", ECARTE_CONFORT,
        raison="geste de confort : deplace le curseur, ne change rien dans "
               "SAP"),
    "caretPosition": Regle(
        "caretPosition", ECARTE_CONFORT,
        raison="geste de confort : position du curseur dans un champ, ne "
               "change rien dans SAP"),
    "maximize": Regle(
        "maximize", ECARTE_CONFORT,
        raison="geste de confort : agrandit la fenetre, ne change rien dans "
               "SAP"),
}


def _fenetre(geste: Geste) -> str:
    """La fenetre visee par un geste qui s'adresse a une fenetre.

    Refuse une cible qui n'est pas exactement `wnd[N]`. La couture ne sait
    envoyer une touche qu'a une fenetre ; si la trace en visait autre chose,
    ne garder que la racine enverrait la touche ailleurs qu'a
    l'enregistrement — le defaut exact que `trace/brouillon.py` a deja eu, ou
    quatre touches destinees a `wnd[1]` partaient dans `wnd[0]`.
    """
    if not _FENETRE_NUE.match(geste.cible):
        raise _Refus(
            f"{geste.verbe} s'adresse a une fenetre, mais la cible est "
            f"{geste.cible!r}. La couture n'envoie une touche qu'a une "
            f"fenetre `wnd[N]` : n'en garder que la racine enverrait la "
            f"touche ailleurs que la ou elle a ete enregistree")
    return geste.cible


def _entier(geste: Geste, quoi: str) -> int:
    """Un entier positif LU, jamais converti depuis autre chose."""
    valeur = geste.valeur
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        raise _Refus(
            f"{geste.verbe} : {quoi} attendu comme ENTIER, la trace porte "
            f"{valeur!r} ({type(valeur).__name__}). La trace de reference "
            f"type ce verbe en entier ; convertir ici serait deviner que "
            f"l'API SAP accepte l'autre type")
    if valeur < 0:
        raise _Refus(
            f"{geste.verbe} : {quoi} negatif ({valeur}). Un index negatif "
            f"designe la fin en Python et rien du tout en SAP : il agirait "
            f"sur une autre ligne, ou sur aucune, sans lever")
    return valeur


def _rangs(geste: Geste) -> tuple[int, ...]:
    """Les rangs d'un `selectedRows`, dont la valeur est du TEXTE.

    C'est le seul endroit ou du texte devient des entiers, et c'est justifie :
    `grid_select_rows` prend des index absolus, et la chaine de la trace n'est
    qu'une liste d'index. Tout ce qui n'est pas exactement une liste d'index
    decimaux separes par des virgules est refuse — un intervalle « 0-4 »
    compris, dont ce depot ne peut pas prouver s'il inclut sa borne haute.

    L'ordre et les repetitions sont conserves : trier ou dedoublonner serait
    rendre autre chose que ce qui a ete enregistre.
    """
    valeur = geste.valeur
    if not isinstance(valeur, str):
        raise _Refus(
            f"selectedRows : la trace porte {valeur!r} "
            f"({type(valeur).__name__}), or l'API SAP type selectedRows en "
            f"CHAINE — c'est la distinction que `trace/modele.py` documente, "
            f"face a currentCellRow qui est un entier. Un type inattendu ici "
            f"est une observation nouvelle, pas une valeur a convertir")
    if not valeur:
        raise _Refus(
            "selectedRows : chaine vide. Elle deselectionnerait sans doute "
            "tout, ce que grid_select_rows(id, ()) exprimerait — mais aucune "
            "trace observee ne la contient et rien ici ne le prouve")
    if not _RANGS.fullmatch(valeur):
        raise _Refus(
            f"selectedRows = {valeur!r} : attendu des index decimaux separes "
            f"par des virgules, sans espace. SAP note aussi les intervalles "
            f"« 0-4 » et ce depot ne peut pas prouver si la borne haute est "
            f"incluse : une borne de trop selectionne une ligne de plus, sans "
            f"lever")
    return tuple(int(rang) for rang in valeur.split(","))


def _arguments(regle: Regle, geste: Geste) -> tuple[object, ...]:
    """Les arguments de l'appel, ou `_Refus`. Aucune valeur par defaut."""
    if regle.signature == SANS_ARGUMENT:
        if geste.valeur is not None:
            raise _Refus(
                f"{geste.verbe} est un appel nu, et ce geste porte la valeur "
                f"{geste.valeur!r}. L'appeler sans elle la jetterait en "
                f"silence")
        return (geste.cible,)
    if regle.signature == TEXTE:
        if not isinstance(geste.valeur, str):
            raise _Refus(
                f"{geste.verbe} : texte attendu, la trace porte "
                f"{geste.valeur!r} ({type(geste.valeur).__name__}). "
                f"`write` saisit une chaine ; en fabriquer une ici serait "
                f"ecrire dans SAP autre chose que ce qui a ete enregistre")
        return (geste.cible, geste.valeur)
    if regle.signature == BOOLEEN:
        if not isinstance(geste.valeur, bool):
            raise _Refus(
                f"{geste.verbe} : booleen attendu, la trace porte "
                f"{geste.valeur!r} ({type(geste.valeur).__name__}). Toute "
                f"autre valeur serait vraie ou fausse par convention Python, "
                f"pas par lecture de la trace")
        return (geste.cible, geste.valeur)
    if regle.signature == RANGS:
        return (geste.cible, _rangs(geste))
    if regle.signature == LIGNE:
        return (geste.cible, _entier(geste, "index de ligne"))
    if regle.signature == TOUCHE:
        fenetre = _fenetre(geste)
        return (_entier(geste, "numero de touche"), fenetre)
    if regle.signature == TOUCHE_FIXE:
        fenetre = _fenetre(geste)
        if fenetre == "wnd[0]":
            # La substitution n°14 vaut pour une MODALE, et la raison portee
            # par la regle le dit : « vkey(12) — F12, Annuler — ferme une
            # modale ». `wnd[0]` n'en est pas une : `close` y termine la
            # session, la ou F12 ne fait qu'annuler l'ecran courant. Traduire
            # quand meme rendrait un appel dont la justification, servie telle
            # quelle au compte rendu, decrirait un autre cas que le sien.
            #
            # Ce refus est exige par symetrie : ce module refuse deja
            # `selectedRows = ""` au motif qu'aucune trace observee ne la
            # contient. La trace de reference ne porte qu'un `close`, sur
            # `wnd[1]`. Le cas `wnd[0]` n'est pas plus observe que l'autre.
            raise _Refus(
                f"{geste.verbe} vise wnd[0] : la substitution de la decision "
                f"n°14 vaut pour une MODALE. Sur la fenetre principale, "
                f"`close` termine la session quand vkey({VKEY_ANNULER}) ne "
                f"fait qu'annuler l'ecran — ce depot ne peut pas prouver "
                f"l'equivalence, et aucune trace observee ne la contient")
        if geste.valeur is not None:
            raise _Refus(
                f"{geste.verbe} est un appel nu, et ce geste porte la valeur "
                f"{geste.valeur!r}")
        assert regle.constante is not None       # garanti par Regle
        return (regle.constante, fenetre)
    raise TableIncoherente(                      # pragma: no cover - ferme
        f"{regle.verbe} : signature {regle.signature!r} sans fabrique")


def traduire(geste: Geste) -> Traduction:
    """Ce qu'on fait de ce geste-la, appel ou refus — jamais rien de muet.

    Ne leve pas sur un geste intraduisible : un refus est une donnee du compte
    rendu, pas un incident. Ne leve que si la TABLE se contredit, ce qui est un
    defaut de ce module et pas de la trace.
    """
    regle = TABLE.get(geste.verbe)
    if regle is None:
        return Traduction(
            geste, VERBE_INCONNU,
            raison=(f"verbe {geste.verbe!r} absent de la table, donc absent "
                    f"des verbes releves sur une trace reelle. Le rejouer "
                    f"demanderait de savoir ce qu'il fait"))
    if regle.genre != TRADUIT:
        return Traduction(geste, regle.genre, raison=regle.raison)
    try:
        arguments = _arguments(regle, geste)
    except _Refus as refus:
        return Traduction(geste, ARGUMENT_REFUSE, raison=str(refus))
    return Traduction(
        geste, TRADUIT,
        appel=Appel(regle.methode, arguments, substitue=regle.substitue),
        raison=regle.raison)


def traduire_tous(gestes: Iterable[Geste]) -> tuple[Traduction, ...]:
    """Les traductions, DANS L'ORDRE et sans en omettre une.

    Aucun filtrage : les gestes de confort et les refus sont rendus eux aussi.
    Un appelant qui ne garderait que les appels ne saurait pas ce qu'il a
    saute, et c'est ce qu'il faut ecrire dans le compte rendu.
    """
    return tuple(traduire(geste) for geste in gestes)


def _verifier_fermeture() -> None:
    """La table recouvre exactement `VERBES`, sinon le module ne se charge pas.

    Une verification a l'import et non seulement dans les tests : un verbe
    ajoute a `VERBES` et oublie ici produirait un rejeu qui saute un geste
    sans le dire, ce qui est exactement le defaut que ce projet traque.
    """
    manquants = sorted(set(VERBES) - set(TABLE))
    if manquants:
        raise TableIncoherente(
            f"verbes de trace sans regle de traduction : {manquants}. "
            f"Decider ce qu'on en fait — meme si c'est de n'en rien faire, "
            f"avec sa raison")
    surnumeraires = sorted(set(TABLE) - set(VERBES))
    if surnumeraires:
        raise TableIncoherente(
            f"regles pour des verbes que le lecteur de traces ne connait "
            f"pas : {surnumeraires}. Elles ne se declencheraient jamais")
    # `.get` et non `TABLE[v]` : un verbe de confort absent de `VERBES` — donc
    # non couvert par le controle ci-dessus — leverait un `KeyError` nu a
    # l'import, la ou ce module doit nommer ce qui manque.
    desaccord = sorted(v for v in CONFORT
                       if (TABLE.get(v) or Regle(v, TRADUIT, "?", TEXTE)
                           ).genre != ECARTE_CONFORT)
    if desaccord:
        raise TableIncoherente(
            f"verbes de confort traites autrement qu'en confort : {desaccord}")
    usurpateurs = sorted(v for v, r in TABLE.items()
                         if r.genre == ECARTE_CONFORT and v not in CONFORT)
    if usurpateurs:
        raise TableIncoherente(
            f"verbes ecartes comme confort sans l'etre pour le lecteur de "
            f"traces : {usurpateurs}")


_verifier_fermeture()
