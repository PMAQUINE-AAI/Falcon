"""Relecture du journal, repli des etats, et preparation d'une reprise."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from falcon.noyau import JournalCorrompu, RepriseIncoherente

from .enregistrement import (
    DOUTEUX, EN_COURS, TERMINAUX, Enregistrement, Etape, ExecutionDebut,
    ItemDebut, ItemFin, depuis_dict,
)


def lire(chemin: str | Path) -> list[Enregistrement]:
    """Relit un journal de bout en bout.

    Tolere une DERNIERE ligne tronquee — c'est la signature d'une coupure
    pendant l'ecriture, et l'evenement perdu est celui qu'on allait ecrire.
    Refuse une ligne tronquee ailleurs : la, le fichier ne dit plus ce qui a
    ete fait, et reprendre dessus serait travailler sur un passe faux.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        return []

    contenu = chemin.read_text(encoding="utf-8")
    if not contenu:
        return []

    lignes = contenu.split("\n")
    complet = contenu.endswith("\n")
    if complet:
        lignes.pop()                      # le dernier morceau est vide

    enregistrements: list[Enregistrement] = []
    for rang, ligne in enumerate(lignes, start=1):
        derniere = rang == len(lignes)
        if not ligne.strip():
            continue
        try:
            donnees = json.loads(ligne)
        except json.JSONDecodeError as erreur:
            if derniere and not complet:
                break                     # coupure pendant l'ecriture : toleree
            raise JournalCorrompu(
                f"{chemin}, ligne {rang} : illisible ({erreur})") from erreur
        enregistrements.append(depuis_dict(donnees))

    return enregistrements


@dataclass(frozen=True)
class EtatItem:
    item_id: str
    etat: str
    sauvegardes: int = 0


def etats(enregistrements: Iterable[Enregistrement]) -> dict[str, EtatItem]:
    """Replie le journal en un etat par item. Le dernier fait foi.

    Un item ouvert et jamais referme est `en_cours` — sauf si une etape de
    sauvegarde a reussi entre-temps : il devient alors `douteux`, parce que
    SAP a peut-etre enregistre et que le rejouer serait une double ecriture.
    """
    ouverts: set[str] = set()
    sauvegardes: dict[str, int] = {}
    fins: dict[str, str] = {}
    courant: str | None = None

    for enregistrement in enregistrements:
        if isinstance(enregistrement, ItemDebut):
            ouverts.add(enregistrement.item_id)
            sauvegardes.setdefault(enregistrement.item_id, 0)
            fins.pop(enregistrement.item_id, None)      # nouvelle tentative
            courant = enregistrement.item_id
        elif isinstance(enregistrement, Etape) and enregistrement.sauvegarde:
            # `Etape.item_id` est facultatif — une pipeline volumique n'a pas
            # d'items du tout. Mais entre un ItemDebut et son ItemFin, une
            # sauvegarde appartient forcement a l'item ouvert : la rattacher
            # est le seul moyen d'eviter qu'un oubli de `item_id` fasse
            # basculer l'item de « jamais rejoue » a « rejoue ».
            porteur = enregistrement.item_id or courant
            if porteur is not None:
                sauvegardes[porteur] = sauvegardes.get(porteur, 0) + 1
        elif isinstance(enregistrement, ItemFin):
            fins[enregistrement.item_id] = enregistrement.etat
            if courant == enregistrement.item_id:
                courant = None

    resultat: dict[str, EtatItem] = {}
    for item_id in ouverts | set(fins):
        compte = sauvegardes.get(item_id, 0)
        if item_id in fins:
            etat = fins[item_id]
        elif compte > 0:
            etat = DOUTEUX
        else:
            etat = EN_COURS
        resultat[item_id] = EtatItem(item_id, etat, compte)
    return resultat


@dataclass(frozen=True)
class Reprise:
    """Ce que la reprise a decide, avant toute action."""

    a_traiter: tuple[str, ...]
    douteux: tuple[str, ...]
    etats: dict[str, EtatItem]

    #: Items du jeu courant deja termines. Ne compte QUE le jeu courant :
    #: `etats` couvre tout le journal, executions et jeux confondus, et
    #: melanger les deux pouvait donner un compteur superieur au nombre
    #: d'items a traiter.
    deja_faits: int = 0


def preparer(chemin: str | Path,
             items: Sequence[str],
             *,
             pipeline_empreinte: str,
             jeu_empreinte: str,
             forcer: bool = False,
             motif: str = "") -> Reprise:
    """Prepare une reprise sur un journal existant.

    `items` est la suite ordonnee des identifiants du jeu courant. Les
    identifiants sont calcules a partir des colonnes de clef declarees par la
    pipeline, jamais a partir du rang de la ligne : un fichier de KO reinjecte
    n'a plus les memes rangs, et la reprise doit rester juste malgre ca.

    La comparaison des empreintes est la garde d'identite appliquee a la
    reprise. Passer outre demande `forcer` ET un motif, qui sera trace.

    Les empreintes n'ont deliberement PAS de valeur par defaut : les omettre
    est une `TypeError` a l'appel, pas un silence. La version precedente les
    laissait vides et gardait la comparaison derriere un `if`, si bien qu'un
    `preparer(chemin, items)` distrait ne verifiait rien — la garde la plus
    severe du dispositif s'obtenait a l'envers, par omission.
    """
    enregistrements = lire(chemin)

    if forcer and not motif.strip():
        raise ValueError("forcer une reprise exige un motif")

    # Un journal absent ou muet ne fonde AUCUNE reprise.
    #
    # `lire` rend une liste vide pour un fichier qui n'existe pas. La suite
    # concluait alors « rien n'a ete fait, tout est a traiter » — et la
    # reprise se degradait en execution complete, sans un mot. Un chemin mal
    # tape lancait donc un lot entier la ou l'utilisateur croyait n'en
    # reprendre que la fin.
    ouvertures = [e for e in enregistrements if isinstance(e, ExecutionDebut)]
    if not ouvertures:
        raise RepriseIncoherente(
            f"{chemin} ne porte aucune execution : il n'y a rien a reprendre. "
            f"Un journal absent ou vide ne dit pas « tout est a faire », il "
            f"dit qu'on ne sait pas ce qui a ete fait. Pour lancer un lot "
            f"neuf, c'est le mode `run`")

    if not forcer:
        if ouvertures:
            origine = ouvertures[0]
            ecarts = []
            if pipeline_empreinte and origine.pipeline_empreinte != pipeline_empreinte:
                ecarts.append(
                    f"pipeline {origine.pipeline_empreinte!r} -> {pipeline_empreinte!r}")
            if jeu_empreinte and origine.jeu_empreinte != jeu_empreinte:
                ecarts.append(
                    f"jeu {origine.jeu_empreinte!r} -> {jeu_empreinte!r}")
            if ecarts:
                raise RepriseIncoherente(
                    "reprise refusee, le monde a change depuis : "
                    + " ; ".join(ecarts))

    connus = etats(enregistrements)
    a_traiter = tuple(i for i in items
                      if connus.get(i) is None
                      or connus[i].etat not in TERMINAUX)
    douteux = tuple(i for i in items
                    if connus.get(i) is not None and connus[i].etat == DOUTEUX)
    faits = sum(1 for i in items
                if connus.get(i) is not None and connus[i].etat in TERMINAUX)
    return Reprise(a_traiter=a_traiter, douteux=douteux, etats=connus,
                   deja_faits=faits)
