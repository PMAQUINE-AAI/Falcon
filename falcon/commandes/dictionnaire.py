"""Le catalogue, mis a plat pour un tableur.

**A quoi ca sert.** Un automatisme nouveau se declare en choisissant, pour
chaque etape, un ecran et un champ de cet ecran. La specification decrit ce
geste au §4, etape 3 : « l'utilisateur associe champs et donnees, ordonne les
actions […] assiste par le catalogue (autocompletion des `id` disponibles sur
l'ecran attendu) ».

Le catalogue porte deja tout ce qu'il faut pour cette assistance. Il ne savait
pas le rendre : son format sur disque est un YAML par triplet, avec les
variantes rangees sous une empreinte `sha256` tronquee qu'il faut decouvrir en
listant. Un tableur ne lit pas ca.

Ce module rend le meme contenu en **une ligne par champ**, ce qu'un tableur
lit, trie et filtre nativement.

**Les deux premieres colonnes sont les seules qu'on copie.** `ecran` et
`cible` portent le nom de la colonne de destination, pas celui du concept :
tout le reste du fichier sert a TROUVER la bonne ligne, ces deux-la servent a
la coller.

**Ce qui rend le selecteur intelligent, et pas seulement long.** Un ecran SAP
porte des dizaines de controles. Les proposer tous en vrac ne serait pas une
aide. Trois colonnes font le tri :

  `modifiable`  n'offrir que les champs ecrivables pour un `set`
  `type`        distinguer un bouton d'un champ de saisie d'une case
  `texte`       le libelle affiche a l'ecran, seul nom qu'un humain reconnait

Sans `texte`, un selecteur affiche `wnd[0]/usr/ctxtWERKS-LOW` et laisse
l'utilisateur deviner qu'il s'agit de la division.

**Pourquoi ici et pas dans `falcon/catalogue/`.** Ce paquet-la n'importe que
`falcon.noyau`, et sa docstring le dit — un catalogue se lit et s'ecrit sans
savoir ce qu'est le reste. Rendre son contenu pour un tableur est de la
PRESENTATION, pas de la logique de catalogue : ca vit ici, a cote du rendu de
`diagnostiquer`, et la frontiere du catalogue reste vraie.

**Le dialecte n'est pas un detail.** Le fichier est destine a un Excel
francais : delimiteur `;`, et UTF-8 **avec BOM**. Sans le BOM, Excel lit le
fichier en ANSI et massacre les accents des libelles ; sans le `;`, il pose
tout en colonne A. Un export « correct » qu'Excel affiche de travers ne sert a
rien — c'est le meme principe que le reste du projet : ce qui compte est ce
qui arrive a l'autre bout.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable, Iterator

from falcon.catalogue import Depot, Variante
from falcon.donnees import Dialecte

#: Une ligne par champ, dans cet ordre.
#:
#: Les cinq premieres colonnes identifient l'ecran et la variante — c'est la
#: clef sur laquelle un tableur regroupe. Les suivantes decrivent le champ.
COLONNES = (
    "ecran", "cible",
    "transaction", "programme", "dynpro", "empreinte", "titre",
    "type", "soustype", "nom", "texte", "modifiable", "infobulle", "releve",
)

#: Separateur du triplet d'ecran, dans la colonne `ecran`.
#:
#: Ni `/` — les noms de programme SAP en contiennent (`/BCP/SAPLXXX`) — ni
#: `|`, qui est l'un des delimiteurs que `donnees.lire` renifle : un fichier
#: qui en serait plein pourrait etre lu comme delimite par `|`.
#:
#: Le triplet tient dans UNE cellule, et c'est deliberé. Une colonne `dynpro`
#: seule est nue : Excel y recadre « 0100 » en « 100 », a la saisie comme a
#: l'enregistrement. Noye dans un jeton qui porte des lettres et des `::`, le
#: dynpro n'est plus recadrable — Excel y voit du texte.
SEPARATEUR_ECRAN = "::"

#: Les colonnes NUES, que le tableur retyperait, et leur parade.
#:
#: Le commentaire ci-dessus decrit exactement le probleme — « une colonne
#: `dynpro` seule est nue : Excel y recadre 0100 en 100 » — et la colonne
#: etait livree nue trois lignes plus bas. `empreinte` est pire encore, et
#: n'avait pas eu ce soin du tout : c'est un prefixe de `sha256` sur seize
#: caracteres hexadecimaux, ecrit dans une colonne qu'Excel type comme un
#: nombre. Mesure sur 400 000 empreintes reelles :
#:
#:      203 entierement numeriques   (0,051 %)  4694198984395866 -> 4,694199E+15
#:      284 en notation scientifique (0,071 %)  86e5014965866131 -> INF
#:      ---
#:      1 empreinte sur 821 silencieusement corrompue
#:
#: `86e5014965866131` est un prefixe de sha256 parfaitement ordinaire. Sur un
#: catalogue de quelques milliers de variantes, c'est plusieurs lignes
#: detruites a chaque export — et l'empreinte est la SEULE colonne qui
#: distingue deux variantes d'un meme triplet.
#:
#: Les crochets sont la meme parade que le jeton `::`, sous une autre forme :
#: une cellule qui contient `[` et `]` n'est jamais un nombre pour Excel, et
#: elle survit a la saisie, a l'enregistrement et au copier-coller quel que
#: soit le format de la colonne. C'est aussi la convention que le
#: convertisseur attend pour les valeurs, donc rien de nouveau a apprendre.
ENCADREES = ("dynpro", "empreinte")

#: Caracteres qui font d'une cellule une FORMULE pour un tableur.
#:
#: Les libelles SAP commencant par `-` sont frequents, et `texte` est la
#: colonne dont on dit qu'elle porte « le seul nom qu'un humain reconnait ».
#: Affichee comme le resultat d'un calcul, elle fait choisir le mauvais champ
#: — le defaut de ce projet, applique au choix du champ plutot qu'a sa valeur.
FORMULE = ("=", "+", "-", "@", "\t", "\r")


def _pour_tableur(valeur: str) -> str:
    """Neutralise une cellule qu'un tableur evaluerait au lieu de l'afficher.

    L'apostrophe de tete est la convention des tableurs pour « ceci est du
    texte » ; elle ne s'affiche pas et disparait a la copie. Elle reste
    visible d'un lecteur qui ouvre le CSV en brut, ce qui est assume : ces
    colonnes sont faites pour etre LUES dans un tableur, et aucune n'est
    relue par FALCON — celles qu'on recopie sont `ecran` et `cible`, qui ne
    commencent ni par `=` ni par `-`.
    """
    return f"'{valeur}" if valeur.startswith(FORMULE) else valeur

#: Ce qu'ecrit une console Windows francaise, et ce que lit Excel sans rien
#: demander. Le BOM n'est pas decoratif : sans lui, Excel lit en ANSI.
DIALECTE_TABLEUR = Dialecte(
    encodage="utf-8", bom=True, delimiteur=";", guillemet='"',
    fin_de_ligne="\r\n", colonnes=COLONNES, format="csv",
)


def lignes_de(variante: Variante) -> Iterator[dict[str, str]]:
    """Une variante de catalogue, en une ligne par champ."""
    clef = variante.clef
    for champ in variante.champs:
        yield {
            # Les deux colonnes qu'on COPIE, en tete. Elles portent le nom de
            # la colonne de destination dans le CSV d'etapes — `ecran` et
            # `cible` — et pas le nom du concept : on les colle, on ne les
            # retape pas.
            "ecran": SEPARATEUR_ECRAN.join(
                (clef.transaction, clef.programme, clef.dynpro)),
            "cible": champ.id,
            "transaction": clef.transaction,
            "programme": clef.programme,
            "dynpro": clef.dynpro,
            "empreinte": clef.empreinte,
            "titre": variante.titre,
            "type": champ.type,
            "soustype": champ.soustype,
            "nom": champ.nom,
            "texte": champ.texte,
            # « oui » / « non » plutot que True/False : c'est ce qu'un
            # utilisateur francais filtre dans un tableur, et ca evite le
            # VRAI/FAUX localise d'Excel, qui ne se relit pas d'une locale a
            # l'autre.
            # Trois valeurs, parce qu'il y a trois etats. « ? » est ce que
            # porte un champ d'ESQUISSE : personne n'a vu l'ecran, et repondre
            # « oui » offrirait au selecteur un champ pour un `set` sur la foi
            # d'un defaut de dataclass.
            "modifiable": {True: "oui", False: "non"}.get(champ.modifiable,
                                                          "?"),
            "infobulle": champ.infobulle,
            # Une esquisse vient d'une trace : elle porte les champs TOUCHES,
            # pas les champs presents, et son `type` est vide. Un selecteur
            # doit pouvoir l'ecarter — d'ou la colonne, plutot qu'un filtre
            # decide ici a la place de l'utilisateur.
            "releve": "observee" if variante.observee else "esquisse",
        }


def _protegee(ligne: dict[str, str]) -> dict[str, str]:
    """Une ligne prete pour un tableur : rien qu'Excel puisse retyper."""
    return {colonne: (f"[{valeur}]" if colonne in ENCADREES and valeur
                      else _pour_tableur(valeur))
            for colonne, valeur in ligne.items()}


def recenser(depot: Depot) -> list[dict[str, str]]:
    """Tout le depot, a plat. Ordre stable : triplet, puis empreinte."""
    lignes: list[dict[str, str]] = []
    for triplet in depot.triplets():
        for variante in depot.variantes(triplet):
            lignes.extend(lignes_de(variante))
    return lignes


def rendre(lignes: Iterable[dict[str, str]],
           dialecte: Dialecte = DIALECTE_TABLEUR) -> bytes:
    """Le CSV, en octets — BOM compris.

    Rend des octets et pas du texte : le BOM et les fins de ligne font partie
    du livrable, et les confier a un `write_text` les laisserait a la merci de
    la plateforme.
    """
    tampon = io.StringIO()
    redacteur = csv.DictWriter(
        tampon, fieldnames=list(dialecte.colonnes),
        delimiter=dialecte.delimiteur, quotechar=dialecte.guillemet,
        lineterminator=dialecte.fin_de_ligne, extrasaction="raise")
    redacteur.writeheader()
    for ligne in lignes:
        redacteur.writerow(_protegee(ligne))

    brut = tampon.getvalue().encode(dialecte.encodage)
    return (b"\xef\xbb\xbf" + brut) if dialecte.bom else brut


def exporter(depot: Depot, chemin: str | Path,
             dialecte: Dialecte = DIALECTE_TABLEUR) -> Path:
    """Recense et ecrit. Rend le chemin ecrit."""
    cible = Path(chemin)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(rendre(recenser(depot), dialecte))
    return cible
