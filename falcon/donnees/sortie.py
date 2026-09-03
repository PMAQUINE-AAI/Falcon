"""Ecriture du fichier de KO, au format d'entree.

C'est l'exigence que la specification qualifie de principale : un rapport
qu'il faut retravailler a la main avant de relancer annule le benefice de
l'automatisation sur les cas difficiles — qui sont precisement ceux qui
coutent.

Le fichier produit est donc simultanement :

  - **enrichi** — quatre colonnes de diagnostic disent pourquoi chaque item a
    echoue, pour que l'humain puisse trier ;
  - **reinjectable tel quel** — ces colonnes portent le prefixe `falcon_`, que
    la lecture retire. Aucune retouche n'est necessaire avant de relancer.

Les deux tiennent ensemble grace au prefixe reserve, et a lui seul.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .entree import PREFIXE_DIAGNOSTIC, Dialecte, Item

#: Colonnes ajoutees, dans cet ordre, apres les colonnes d'origine.
COLONNES_DIAGNOSTIC = (
    f"{PREFIXE_DIAGNOSTIC}categorie",
    f"{PREFIXE_DIAGNOSTIC}entree",
    f"{PREFIXE_DIAGNOSTIC}message",
    f"{PREFIXE_DIAGNOSTIC}sauvegardes",
    f"{PREFIXE_DIAGNOSTIC}item_id",
)

#: `falcon_sauvegardes` porte le nombre de sauvegardes deja passees pour cet
#: item. Sans lui, l'humain qui relance un fichier de KO n'a aucun moyen de
#: savoir que l'item a DEJA ecrit dans SAP — et le relancer ecrit deux fois.
#: C'est le pendant, cote fichier, de l'etat « douteux » cote journal.


def ecrire_items(chemin: str | Path,
                 items: Iterable[Item],
                 dialecte: Dialecte,
                 diagnostics: Mapping[str, Mapping[str, str]] | None = None) -> Path:
    """Ecrit des items dans le format et le dialecte d'origine.

    Un item groupe rend TOUTES ses lignes source : c'est le jeu d'origine
    qu'on reconstitue, pas un resume.
    """
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    diagnostics = diagnostics or {}

    # Sans diagnostic a ecrire, la sortie est le jeu d'origine reconstitue :
    # aucune colonne ajoutee, pas meme l'identifiant d'item. C'est ce qui rend
    # l'aller-retour neutre — reexporter puis reecrire redonne l'octet pres le
    # fichier de depart.
    produire_diagnostic = bool(diagnostics)

    lignes: list[dict[str, Any]] = []
    for item in items:
        diagnostic: dict[str, Any] = {}
        if produire_diagnostic:
            diagnostic = dict(diagnostics.get(item.item_id, {}))
            diagnostic.setdefault(f"{PREFIXE_DIAGNOSTIC}item_id", item.item_id)
        for source in item.brut:
            lignes.append({**source, **diagnostic})

    colonnes = tuple(dialecte.colonnes)
    if produire_diagnostic:
        colonnes = colonnes + COLONNES_DIAGNOSTIC

    if dialecte.format == "jsonl":
        # Une clef absente le reste : pour une injection SAP, « ne touche pas
        # a ce champ » et « vide ce champ » ne sont pas la meme instruction, et
        # combler les trous par une chaine vide transforme la premiere en la
        # seconde.
        texte = "".join(
            json.dumps({c: ligne[c] for c in colonnes if c in ligne},
                       ensure_ascii=False) + dialecte.fin_de_ligne
            for ligne in lignes)
    else:
        tampon = io.StringIO()
        redacteur = csv.DictWriter(
            tampon, fieldnames=list(colonnes), delimiter=dialecte.delimiteur,
            quotechar=dialecte.guillemet, lineterminator=dialecte.fin_de_ligne,
            extrasaction="ignore")
        redacteur.writeheader()
        for ligne in lignes:
            redacteur.writerow({c: ligne.get(c, "") for c in colonnes})
        texte = tampon.getvalue()

    encodage = "utf-8-sig" if dialecte.bom else dialecte.encodage
    chemin.write_bytes(texte.encode(encodage))
    return chemin
