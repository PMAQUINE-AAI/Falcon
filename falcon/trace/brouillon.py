"""D'une trace vers un brouillon de pipeline — inachevé par construction.

Ce que produit ce module **ne peut pas etre execute tel quel**, et c'est
voulu. Le fichier porte des marqueurs `TODO` a tous les endroits ou la trace
ne dit rien, ce qui fait que `pipeline.charger()` le refuse : il faut le
charger explicitement comme brouillon, ou le completer.

**La propriete qui porte ce lot est negative : le generateur n'emet jamais
`navigation_libre: true`.** Il aurait ete commode de le faire — une trace ne
dit pas l'identite des ecrans, et `navigation_libre` est precisement la
declaration qui dispense d'en donner une. Mais c'est aussi la declaration qui
DESARME la garde d'identite, et un generateur qui la poserait automatiquement
desarmerait la premiere garde du dispositif sur toute pipeline nee d'une
trace, sans que personne l'ait decide. Le generateur emet donc un ecran a
completer. Le fichier est inutilisable tant qu'un humain n'a pas rempli les
trois cases — ce qui est le comportement recherche.

**Trois familles de gestes, trois traitements distincts :**

- ceux qu'une action de pipeline exprime — `text`, `selected`, `press`,
  `sendVKey` — deviennent des etapes ;
- ceux qu'aucune action n'exprime — l'ALV en ecriture, l'arbre, dont la
  couture connait pourtant les methodes — deviennent des etapes `python` a
  `TODO`, avec la ligne de trace en commentaire ;
- les gestes de confort — focus, curseur, agrandissement — sont ECARTES. Ils
  sont conserves dans la trace pour qu'elle reste rejouable a l'identique,
  mais une pipeline n'est pas un rejeu : les recopier produirait du bruit
  dans un fichier destine a etre relu et edite a la main.

**Le piege que ce module doit signaler et ne peut pas resoudre.** La trace
selectionne ses lignes d'ALV par INDEX. Cet index depend du contenu de la base
au moment de l'enregistrement ; rejoue tel quel, il traite la mauvaise ligne
et ne leve pas. La vraie pipeline devra lire la grille pour retrouver sa ligne
par son contenu. Le brouillon le dit, en commentaire et dans l'objet rendu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from .esquisse import Visite, visites
from .modele import CONFORT, Geste, Trace

#: Marqueur laisse partout ou la trace ne dit rien. Doit rester identique a
#: `pipeline.chargeur.MARQUEUR_BROUILLON` — un test l'epingle, plutot qu'un
#: import qui ferait dependre le lecteur de traces de la pipeline.
TODO = "TODO"

#: Geste du recorder -> action de pipeline, pour ce qu'une pipeline exprime.
ACTIONS: dict[str, str] = {
    "text": "set",
    "selected": "cocher",
    "press": "press",
    "sendVKey": "vkey",
}

#: Gestes qu'aucune action de pipeline n'exprime aujourd'hui.
#:
#: La couture SAIT les faire — decision n°14 pour l'ALV en ecriture — mais le
#: modele de pipeline ne les declare pas. Les emettre en `python`/`TODO`
#: plutot que de les taire garde la trace de ce qui manque a l'endroit exact
#: ou il manque.
SANS_ACTION = frozenset({
    "selectedRows", "currentCellRow", "doubleClickCurrentCell",
    "expandNode", "selectedNode", "doubleClickNode", "topNode",
})

#: Substitutions decidees, appliquees et TRACEES.
#:
#: `close` ferme une modale ; la decision n°14 a arrete que `vkey(12)` — F12,
#: Annuler — la couvre, et que la couture n'aurait pas de methode `close`. Le
#: brouillon applique donc la substitution, mais la signale : c'est un geste
#: que la trace ne contient pas litteralement.
SUBSTITUTIONS: dict[str, tuple[str, str]] = {
    "close": ("vkey", "12"),
}

#: Verbes dont la valeur est un index de ligne d'ALV.
INDEX_ALV = frozenset({"selectedRows", "currentCellRow"})

_PREFIXES = ("ctxt", "txt", "chk", "btn", "cntl", "rad", "cmb", "lbl", "tbl")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class BrouillonImpossible(Exception):
    """La trace ne permet pas de produire un brouillon."""


@dataclass(frozen=True)
class Brouillon:
    """Un brouillon de pipeline, et l'inventaire de ce qu'il n'a pas su faire.

    `non_rejouables` et `substitutions` ne sont pas de la decoration : ce sont
    les deux endroits ou le fichier produit s'ecarte de ce que la trace dit,
    et un appelant doit pouvoir les compter sans relire le YAML.
    """

    nom: str
    yaml: str
    etapes: int = 0
    non_rejouables: tuple[Geste, ...] = ()
    substitutions: tuple[Geste, ...] = ()
    selections_par_index: tuple[Geste, ...] = ()
    ecarte_confort: int = 0

    @property
    def complet(self) -> bool:
        """Vrai si rien n'a echappe a la traduction. Jamais un feu vert :
        le fichier porte de toute facon des `TODO` d'ecran."""
        return not self.non_rejouables


_FENETRE_NUE = re.compile(r"^wnd\[\d+\]$")


def _slug(cible: str) -> str:
    """Un nom d'etape lisible, derive de la cible."""
    if _FENETRE_NUE.match(cible):
        return "fenetre"        # `sendVKey` s'adresse a la fenetre, pas a un champ
    dernier = cible.rstrip("/").split("/")[-1]
    dernier = re.sub(r"\[\d+\]$", "", dernier)
    for prefixe in _PREFIXES:
        if dernier.startswith(prefixe) and len(dernier) > len(prefixe):
            dernier = dernier[len(prefixe):]
            break
    nettoye = _NON_ALNUM.sub("_", dernier.lower()).strip("_")
    return nettoye or "fenetre"


def _ecran(visite: Visite) -> dict[str, str]:
    """L'ecran attendu, avec ce que la trace sait et des `TODO` ailleurs.

    Jamais `navigation_libre` : voir l'en-tete du module.
    """
    return {"transaction": visite.transaction or TODO,
            "programme": TODO, "dynpro": TODO}


def _etape(geste: Geste, visite: Visite) -> tuple[dict, list[str]]:
    """(etape, commentaires) pour un geste significatif."""
    nom = f"{geste.ordre:03d}_{_slug(geste.cible)}"
    commentaires: list[str] = []
    etape: dict = {"nom": nom}

    if geste.verbe in SUBSTITUTIONS:
        action, valeur = SUBSTITUTIONS[geste.verbe]
        etape["action"] = action
        etape["source"] = {"constante": valeur}
        commentaires.append(
            f"substitution : la trace fait « {geste.verbe} », que le modele "
            f"n'exprime pas.")
        commentaires.append(
            f"La decision n°14 arrete que vkey(12) ferme une modale. "
            f"A confirmer.")
    elif geste.verbe in ACTIONS:
        etape["action"] = ACTIONS[geste.verbe]
        if geste.verbe == "sendVKey":
            etape["source"] = {"constante": geste.valeur}
        else:
            etape["cible"] = geste.cible
            if geste.verbe in ("text", "selected"):
                etape["source"] = {"constante": geste.valeur}
                commentaires.append(
                    "valeur constante relevee sur la trace ; a remplacer par "
                    "« colonne: ... » si elle varie d'un item a l'autre.")
    else:
        etape["action"] = "python"
        etape["fonction"] = TODO
        etape["cible"] = geste.cible
        commentaires.append(
            f"NON REJOUABLE : « {geste.verbe} » n'est exprimable par aucune "
            f"action de pipeline.")
        if geste.verbe in INDEX_ALV:
            commentaires.append(
                "De plus, la selection porte sur un INDEX de ligne, qui depend "
                "du contenu")
            commentaires.append(
                "de la base au moment de l'enregistrement. Le rejouer tel quel "
                "traiterait")
            commentaires.append(
                "la mauvaise ligne, sans lever. Lire la grille et retrouver la "
                "ligne par son")
            commentaires.append("contenu.")

    if geste.verbe != "sendVKey" and "cible" not in etape:
        etape["cible"] = geste.cible
    etape["ecran"] = _ecran(visite)
    commentaires.insert(0, f"trace ligne {geste.ligne} : {geste.texte_source}")
    return etape, commentaires


def _rendre(etape: dict, commentaires: list[str]) -> str:
    """Une etape en YAML indente, precedee de ses commentaires."""
    lignes = [f"  # {c}" for c in commentaires]
    brut = yaml.safe_dump([etape], sort_keys=False, allow_unicode=True,
                          default_flow_style=False, width=10 ** 6)
    lignes += [f"  {l}" if l.strip() else l
               for l in brut.rstrip("\n").splitlines()]
    return "\n".join(lignes)


ENTETE = f"""# Brouillon de pipeline, produit depuis une trace du SAP GUI Recorder.
#
# INACHEVE PAR CONSTRUCTION. Une trace enregistre des actions : elle ne dit ni
# l'identite des ecrans traverses, ni les champs presents sur chacun. Tout ce
# que ce fichier ne pouvait pas savoir porte un marqueur « {TODO} », et
# `falcon.pipeline.charger()` refuse le fichier tant qu'il en reste un.
#
# Le generateur n'emet JAMAIS `navigation_libre` : ce serait desarmer la garde
# d'identite sur toute pipeline nee d'une trace, sans que personne l'ait
# decide. Completer les trois cases de chaque `ecran` — un
# `python -m falcon diagnostiquer` sur l'ecran reel les donne.
"""


def brouillon_de(trace: Trace, *, nom: str = "") -> Brouillon:
    """Le brouillon d'une trace entierement lue.

    Prend une `Trace`, donc le produit d'une lecture STRICTE : un brouillon
    bati sur des lignes non appariees serait faux sans le dire.
    """
    decoupees = visites(trace)
    if not decoupees:
        raise BrouillonImpossible(
            f"{trace.source} : aucun geste. Rien a mettre dans une pipeline")

    corps: list[str] = []
    non_rejouables: list[Geste] = []
    substitutions: list[Geste] = []
    index: list[Geste] = []
    ecarte = 0
    combien = 0

    for visite in decoupees:
        for geste in visite.gestes:
            if geste.verbe in CONFORT:
                ecarte += 1
                continue
            etape, commentaires = _etape(geste, visite)
            if etape["action"] == "python":
                non_rejouables.append(geste)
                if geste.verbe in INDEX_ALV:
                    index.append(geste)
            elif geste.verbe in SUBSTITUTIONS:
                substitutions.append(geste)
            corps.append(_rendre(etape, commentaires))
            combien += 1

    entete = yaml.safe_dump({
        "version": 1,
        "nom": nom or f"{TODO}_nom_de_la_pipeline",
        "classe": "iterative",
        "cles": [TODO],
        "plafond_items": 1,
        "plafond_sauvegardes": 1,
    }, sort_keys=False, allow_unicode=True, default_flow_style=False)

    texte = "\n".join([
        ENTETE,
        entete.rstrip("\n"),
        f"# classe, cles et plafonds sont a decider : « iterative » et 1 sont",
        f"# des valeurs de depart, pas des choix.",
        "",
        "etapes:",
        "\n".join(corps),
        "",
    ])

    return Brouillon(
        nom=nom or f"{TODO}_nom_de_la_pipeline", yaml=texte, etapes=combien,
        non_rejouables=tuple(non_rejouables),
        substitutions=tuple(substitutions),
        selections_par_index=tuple(index), ecarte_confort=ecarte,
    )


def apercu(brouillon: Brouillon) -> str:
    """Ce que le brouillon a su faire, et ce qu'il n'a pas su faire."""
    lignes = [
        "  brouillon de pipeline",
        f"    etapes             {brouillon.etapes}",
        f"    gestes de confort  {brouillon.ecarte_confort}  (ecartes)",
        f"    non rejouables     {len(brouillon.non_rejouables)}",
        f"    substitutions      {len(brouillon.substitutions)}",
    ]
    if brouillon.selections_par_index:
        lignes.append("")
        lignes.append(f"  {len(brouillon.selections_par_index)} selection(s) "
                      f"d'ALV par INDEX :")
        for geste in brouillon.selections_par_index:
            lignes.append(f"    ligne {geste.ligne:>4}  {geste.verbe} = "
                          f"{geste.valeur!r}")
        lignes.append("  L'index depend du contenu de la base a "
                      "l'enregistrement. Rejoue tel quel,")
        lignes.append("  il traite la mauvaise ligne — sans lever.")

    lignes.append("")
    lignes.append("  Le fichier porte des marqueurs : `charger()` le refuse, "
                  "`charger(brouillon=True)`")
    lignes.append("  l'accepte. Completer les `ecran` avant de s'en servir.")
    return "\n".join(lignes)
