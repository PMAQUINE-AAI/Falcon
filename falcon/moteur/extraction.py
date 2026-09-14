"""Le fichier qu'une etape `extraire` produit — et les refus qui le gardent.

C'est l'etape intermediaire que le §1 impose : « passe d'audit → fichier de
constats (relisible, editable) → passe de remediation. L'humain valide le
fichier intermediaire avant toute ecriture. » Ce module ecrit ce fichier.

**Il doit tenir trois choses a la fois**, et c'est ce qui decide de sa forme :

1. **s'ouvrir dans Excel** — UTF-8 avec BOM, delimite par `;`, comme le
   dictionnaire (`DIALECTE_TABLEUR`) ;
2. **s'editer a la main** — on supprime des lignes, on trie, on filtre, on
   colle deux extractions dans le meme onglet ;
3. **se redonner tel quel comme JEU** a la passe suivante, sans une retouche.

**Pourquoi la provenance est en COLONNES et pas en en-tete.** Une ligne de
provenance avant l'en-tete casse la relecture : `csv.DictReader` prend la
premiere ligne comme en-tete, la provenance deviendrait les noms de colonnes,
et le fichier cesserait d'etre redonnable — la contrainte n°3 tombe. Le JSONL
de `volumique/export.py` s'en tire parce que JSONL n'a pas d'en-tete ; ce n'est
pas transposable au CSV.

Et il y a plus fort que l'argument technique. **Quelqu'un va coller deux
extractions dans le meme onglet** — huit variantes, six transactions, c'est le
geste normal. Une provenance en en-tete devient alors FAUSSE : un fichier
d'aspect parfaitement normal qui affirme que trois cents lignes viennent d'un
systeme alors que la moitie vient d'un autre. Une provenance par ligne ne peut
pas mentir de cette facon.

Le prefixe `falcon_` est celui du fichier de KO, et pour la meme raison : la
lecture le retire (`donnees/entree.py`), donc les colonnes sont visibles pour
l'humain et invisibles pour la machine. Aucun second dispositif.

**Ce que ca coute, et il faut le nommer.** Les colonnes `falcon_` etant
retirees a la lecture, la passe suivante ne VOIT pas la provenance : elle ne
peut pas verifier qu'elle rejoue sur le systeme d'ou viennent les lignes. C'est
le prix exact de la reinjectabilite, deja paye par le fichier de KO. Le
rapprochement reste faisable apres coup : le journal de la passe suivante porte
`systeme` et `mandant` dans son `ExecutionDebut`.

**Ce qu'on s'interdit, et c'est un risque assume.** `commandes/dictionnaire.py`
protege ses cellules contre Excel en prefixant `'` a tout ce qui commence par
`=`, `+`, `-` ou `@`. Sa docstring dit pourquoi c'est sur la-bas : « aucune
n'est relue par FALCON ». Ici c'est l'inverse — ce fichier est relu et ses
valeurs sont RETAPEES dans SAP. L'apostrophe partirait dans le champ. On ne
l'applique donc pas, et un test l'epingle. Ce que fait Excel d'une valeur ALV
commencant par `-`, personne ici ne l'a mesure.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from falcon.donnees.entree import PREFIXE_DIAGNOSTIC, Dialecte
from falcon.donnees.sortie import ecrire_items
from falcon.donnees import Item
from falcon.volumique.export import ExportInvalide, Provenance

from .erreurs import ExtractionImpossible

#: Le dialecte du fichier extrait : celui qu'Excel lit sans rien demander.
#:
#: Defini ici et pas importe de `dictionnaire.py` parce que ses COLONNES sont
#: celles du dictionnaire ; ce qui se partage est la CONVENTION, pas la liste.
BOM = True
DELIMITEUR = ";"
FIN_DE_LIGNE = "\r\n"

#: Ce qu'on refuse d'ecrire dans un nom de fichier.
_INTERDITS = re.compile(r"[^A-Za-z0-9_.-]")


def nom_de_fichier(etape: str, item: Item, *, mode: str) -> str:
    """`variantes_IH06.csv`, pas `variantes_a3f9c1....csv`.

    Nomme depuis les VALEURS DE CLEF de l'item, assainies, parce que ce
    fichier est fait pour etre ouvert par un humain qui doit savoir lequel
    c'est. `item_id` est une empreinte : elle identifie sans nommer.

    **Le mode figure dans le nom, et ce n'est pas cosmetique.** La garde de
    repetition exige un dry-run abouti avant tout run. Or une pipeline
    d'extraction ne sauvegarde rien : `RefusDryRun` ne se declenche jamais, et
    le dry-run ECRIT le fichier — il ecrit deja le journal et les dumps, « ne
    rien ecrire » n'a jamais voulu dire « ne pas toucher au disque ». Sans le
    suffixe, le run suivant se ferait refuser par sa propre garde
    d'ecrasement, sur un fichier qu'il vient d'ecrire lui-meme.
    """
    morceaux = [_INTERDITS.sub("_", str(v)) or "_" for v in item.cle.values()]
    base = "_".join([_INTERDITS.sub("_", etape), *morceaux]) or "extraction"
    suffixe = "" if mode == "run" else f".{_INTERDITS.sub('_', mode)}"
    return f"{base}{suffixe}.csv"


def chemins_prevus(dossier: str | Path, etapes: Sequence[str],
                   items: Sequence[Item], *, mode: str) -> list[Path]:
    """TOUS les fichiers qu'un run ecrirait, calculables AVANT de le lancer.

    C'est ce qui permet au pre-vol de refuser un ecrasement avant le premier
    contact avec SAP — donc de proteger le fichier que l'humain vient de
    corriger dans Excel d'un re-run distrait.
    """
    racine = Path(dossier)
    return [racine / nom_de_fichier(etape, item, mode=mode)
            for etape in etapes for item in items]


def verifier_les_chemins(dossier: str | Path, etapes: Sequence[str],
                         items: Sequence[Item], *, mode: str) -> None:
    """Refuse un ecrasement, et deux items qui produiraient le meme nom."""
    prevus = chemins_prevus(dossier, etapes, items, mode=mode)

    deja = sorted({str(c) for c in prevus if c.exists()})
    if deja:
        raise ExtractionImpossible(
            f"{len(deja)} fichier(s) d'extraction existent deja : {deja[:3]}"
            f"{' ...' if len(deja) > 3 else ''}. Les ecraser effacerait le "
            f"fichier que quelqu'un vient peut-etre de relire et de corriger. "
            f"Choisir un autre dossier, ou deplacer les precedents")

    vus: dict[str, int] = {}
    for chemin in prevus:
        vus[chemin.name] = vus.get(chemin.name, 0) + 1
    collisions = sorted(nom for nom, compte in vus.items() if compte > 1)
    if collisions:
        raise ExtractionImpossible(
            f"deux items produiraient le meme fichier : {collisions}. Leurs "
            f"valeurs de clef ne se distinguent qu'apres assainissement du "
            f"nom, et le second ecraserait le premier — donc la moitie de "
            f"l'extraction disparaitrait sans un mot")


class Extracteur:
    """Ce qui ecrit les fichiers d'un run, et retient ce qu'il a ecrit.

    Un collaborateur que `executer` detient et passe, comme `Adaptateur` :
    `_jouer_item` reste `-> None`, et aucune valeur metier ne remonte par un
    retour de fonction. Ce qui ressort au `Resultat` est une liste de CHEMINS,
    de la meme nature que `ko` et `journal`.
    """

    def __init__(self, dossier: str | Path | None, *, mode: str,
                 provenance: Provenance):
        self.dossier = Path(dossier) if dossier is not None else None
        self.mode = mode
        self.provenance = provenance
        self.ecrits: list[str] = []

    @property
    def actif(self) -> bool:
        return self.dossier is not None

    def ecrire(self, etape: str, item: Item, dialecte_entree: Dialecte,
               lignes: Sequence[Mapping[str, Any]]) -> Path:
        """Ecrit les lignes relevees, avec la clef de l'item et la provenance.

        L'ordre des colonnes est `[clefs de l'item] + [colonnes ALV] +
        [falcon_*]`. Les clefs sont des colonnes de DONNEES, sans prefixe :
        sans `transaction`, la passe suivante ne saurait pas dans quelle
        transaction ouvrir la variante, et l'information n'est nulle part
        ailleurs.
        """
        if self.dossier is None:                    # pragma: no cover - garde
            raise ExtractionImpossible(
                "aucun dossier d'extraction : le pre-vol aurait du refuser")

        self.provenance.verifier()
        provenance = self.provenance.vers_ligne()

        colonnes_alv = _colonnes_de(lignes)
        _refuser_les_collisions(colonnes_alv, item.cle, provenance, etape)

        colonnes = (tuple(item.cle) + colonnes_alv + tuple(provenance))
        completes = [
            {**item.cle, **{c: ligne.get(c, "") for c in colonnes_alv},
             **provenance}
            for ligne in lignes
        ]

        chemin = self.dossier / nom_de_fichier(etape, item, mode=self.mode)
        dialecte = Dialecte(
            encodage="utf-8", bom=BOM, delimiteur=DELIMITEUR,
            guillemet=dialecte_entree.guillemet, fin_de_ligne=FIN_DE_LIGNE,
            colonnes=colonnes, format="csv")

        # Les lignes passent par un item factice : `ecrire_items` sait deja
        # ecrire un CSV dans un dialecte donne, et une seconde ecriture de CSV
        # dans ce depot serait une seconde occasion de diverger.
        ecrire_items(chemin, [Item(item_id=item.item_id, cle=item.cle,
                                   brut=tuple(completes), index=item.index)],
                     dialecte)
        self.ecrits.append(str(chemin))
        return chemin


def _colonnes_de(lignes: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Les colonnes de la grille, dans l'ordre de la premiere ligne."""
    return tuple(lignes[0]) if lignes else ()


def _refuser_les_collisions(colonnes_alv: tuple[str, ...],
                            cle: Mapping[str, str],
                            provenance: Mapping[str, Any],
                            etape: str) -> None:
    """Trois refus, calques sur ceux de `volumique/export.py`."""
    prefixees = [c for c in colonnes_alv if c.startswith(PREFIXE_DIAGNOSTIC)]
    if prefixees:
        raise ExtractionImpossible(
            f"etape {etape!r} : la grille expose {prefixees}, et le prefixe "
            f"{PREFIXE_DIAGNOSTIC!r} est reserve. Ces colonnes seraient "
            f"retirees a la relecture, en silence — la passe suivante "
            f"travaillerait sur un fichier dont il manque des colonnes sans "
            f"que rien ne le dise")

    avec_la_clef = sorted(set(colonnes_alv) & set(cle))
    if avec_la_clef:
        raise ExtractionImpossible(
            f"etape {etape!r} : la grille expose {avec_la_clef}, qui est "
            f"aussi une colonne de clef de l'item. Garder l'une des deux "
            f"serait choisir au hasard entre ce que la grille dit et ce que "
            f"le jeu dit")

    avec_provenance = sorted(set(colonnes_alv) & set(provenance))
    if avec_provenance:                             # pragma: no cover - couvert
        raise ExportInvalide(
            f"etape {etape!r} : collision de provenance sur {avec_provenance}")
