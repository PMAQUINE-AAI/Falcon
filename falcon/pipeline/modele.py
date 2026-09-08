"""Ce qu'une pipeline declare.

Ce module ne connait ni SAP, ni le controleur, ni les gardes. Il ne peut
importer ni `falcon.couture` ni `falcon.controleur` — regle verifiee par
`tests/test_frontieres.py`.

Ce n'est pas de l'hygiene : c'est la traduction mecanique de la separation du
modele de securite. Une pipeline qui ne peut nommer aucun driver ne peut pas
non plus, par construction, en manipuler un ni desactiver une garde. Elle
declare une intention ; c'est le controleur qui applique les regles.

La conversion d'une `Etape` en contrat de garde appartient donc au controleur,
et le sens de l'import le dit : `falcon/controleur/` importe `falcon/pipeline/`,
jamais l'inverse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Actions declarables dans une etape.
#:
#: La specification en nomme quatre — set, press, select, read. Les trois
#: autres suivent la meme logique que l'elargissement de la couture : sans
#: `cocher`, on ne peut pas positionner explicitement les trois cases de
#: selection que le terrain impose ; sans `vkey`, aucune touche de fonction ;
#: et `python` est l'echappatoire que la specification rend obligatoire.
#: Les trois dernieres sont celles de la GRILLE, et elles referment un piege
#: que la couture documente depuis toujours sans que rien ne l'applique :
#: « selectionner par index est un piege, pas une commodite […] la regle : lire
#: la grille pour retrouver la ligne voulue par son CONTENU »
#: (`couture/interface.py`). Faute d'action, la regle etait une phrase.
ACTIONS = frozenset({"set", "cocher", "press", "select", "vkey", "lire",
                     "python", "extraire", "choisir", "ouvrir"})

#: Actions de grille. Elles partagent la meme `cible` — l'identifiant du shell
#: ALV — et c'est ce qui permet au chargeur de verifier qu'un `ouvrir` porte
#: bien sur la grille que le `choisir` qui le precede vient de positionner.
GRILLE = frozenset({"extraire", "choisir", "ouvrir"})

#: Actions qui exigent une cible.
AVEC_CIBLE = frozenset({"set", "cocher", "press", "select", "lire",
                        "extraire", "choisir", "ouvrir"})

#: Actions qui exigent une source de valeur.
#:
#: `vkey` y figure parce que rien d'autre ne portait le NUMERO de la touche.
#: L'action etait declarable et chargeable, et une etape `vkey` chargee etait
#: muette sur ce qu'elle devait envoyer : le moteur ne pouvait pas l'executer.
#: Le trou n'a ete visible qu'au moment d'ecrire le moteur, ce qui est tard.
#: `choisir` y figure parce que la valeur cherchee est ce qui distingue une
#: ligne d'une autre : sans source, on ne chercherait rien.
AVEC_SOURCE = frozenset({"set", "cocher", "vkey", "choisir"})

#: Actions qui exigent le nom d'UNE colonne — celle ou l'on cherche.
#:
#: Obligatoire, et pas defaillable sur « la premiere colonne » : la premiere
#: colonne est celle de la mise en page ALV du poste, donc elle change d'un
#: utilisateur a l'autre. Chercher dans une colonne qu'on n'a pas nommee, c'est
#: chercher ailleurs que la ou on croit.
AVEC_COLONNE = frozenset({"choisir"})

#: Actions qui acceptent une LISTE de colonnes a lire.
#:
#: Facultative, a la difference de `AVEC_COLONNE`, et l'omission ne relache
#: aucune garde : elle elargit un perimetre de LECTURE. L'exiger rendrait
#: impossible la premiere extraction, qui est justement celle ou l'on ne
#: connait pas encore les noms de colonnes.
AVEC_COLONNES = frozenset({"extraire"})

#: Actions pour lesquelles `navigation_libre` est INTERDIT.
#:
#: `extraire` en fait partie, et c'est ce qui referme le piege du resultat
#: unique : quand la recherche ne remonte qu'une ligne, SAP ouvre l'objet
#: directement au lieu d'afficher la liste. La grille est alors introuvable —
#: exactement comme si la recherche n'avait rien remonte. Deux conclusions
#: opposees, qu'aucune observation de la grille ne separe.
#:
#: Avec un `ecran` declare, la garde d'identite leve `EcartIdentite` AVANT tout
#: `ObjetIntrouvable`, et les deux cas se distinguent. `navigation_libre`
#: desarmerait la seule chose qui les distingue.
SANS_NAVIGATION_LIBRE = frozenset({"extraire"})

#: Actions dont la source doit etre une constante, pas une donnee du jeu.
#:
#: Une touche de fonction est une propriete de la PIPELINE, pas de l'item.
#: La faire venir d'une colonne rendrait le geste different d'une ligne a
#: l'autre — c'est-a-dire imprevisible, et hors de portee de toute relecture.
SOURCE_CONSTANTE = frozenset({"vkey"})

CLASSES = frozenset({"iterative", "volumique"})

#: Genres de source : colonne du fichier d'entree, constante, valeur lue par
#: une etape `lire` precedente, ou GABARIT composant plusieurs colonnes.
#:
#: `gabarit` existe parce que le cas le plus banal d'une correction de masse
#: SAP en a besoin — un nom de variante porte le site dedans, « /BCP01_K75 » —
#: et que le seul chemin restant etait d'ecrire une fonction Python, de la
#: faire entrer dans le depot, et de la faire relire. Pour concatener deux
#: colonnes.
GENRES_SOURCE = frozenset({"colonne", "constante", "lue", "gabarit"})


@dataclass(frozen=True)
class Source:
    """D'ou vient la valeur d'une saisie.

    Le genre `lue` designe le NOM d'une etape `lire` anterieure : une etape
    `lire` lie sa lecture sous son propre nom, et c'est la seule lecture
    coherente d'une source « lue ». Le chargeur verifie que l'etape designee
    existe et precede — une reference pendante produirait sinon une saisie
    vide, sans erreur.
    """

    genre: str                      # colonne | constante | lue | gabarit
    valeur: str

    #: Colonnes citees par un `gabarit`, resolues au chargement. Vide pour les
    #: autres genres. Le moteur s'en sert pour son controle de pre-vol : une
    #: colonne citee que le jeu ne porte pas doit tomber AVANT la premiere
    #: action, pas devenir une chaine vide au milieu du lot.
    colonnes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DerogationDeclaree:
    """Une derogation telle que le YAML la demande.

    Distincte de `controleur.Derogation`, qui est celle que le controleur
    ACCORDE apres validation. La pipeline demande, le controleur dispose —
    et le typage le dit.
    """

    garde: str
    portee: str
    motif: str


@dataclass(frozen=True)
class Etape:
    nom: str
    action: str
    cible: str = ""
    source: Source | None = None
    fonction: str = ""                       # action « python »

    #: Colonne ou l'on cherche — action « choisir ». Obligatoire pour elle.
    colonne: str = ""

    #: Colonnes a lire — action « extraire ». Vide = celles que la grille
    #: expose, c'est-a-dire la mise en page ALV du poste qui execute.
    colonnes: tuple[str, ...] = ()

    # Ce que l'etape declare aux gardes.
    #: Transformations appliquees a la valeur, DANS L'ORDRE DECLARE, avant
    #: toute ecriture. Registre ferme : voir `pipeline/composition.py`.
    format: tuple[Any, ...] = ()

    #: Valeur de repli quand la source rend une chaine vide. Distincte de
    #: l'absence de colonne, que le pre-vol refuse : ici la colonne existe et
    #: la case est vide, ce qui est une donnee.
    defaut: str | None = None

    ecran: tuple[str, str, str] | None = None
    navigation_libre: bool = False
    fenetres: tuple[str, ...] = ("wnd[0]",)
    statut_attendu: str | None = None
    sauvegarde: bool = False
    comparaison: str = "casse"
    derogations: tuple[DerogationDeclaree, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Pipeline:
    nom: str
    classe: str                              # iterative | volumique
    etapes: tuple[Etape, ...]
    plafond_items: int
    plafond_sauvegardes: int
    cles: tuple[str, ...] = ()               # obligatoire si iterative
    #: `sha256` du texte integral du fichier, tronque a 16 hex.
    #:
    #: Le defaut vide est conserve pour l'ordre des champs de la dataclasse,
    #: mais `__post_init__` le refuse : c'est sur cette empreinte que la
    #: reprise verifie que le monde n'a pas change, et une empreinte vide
    #: rendrait la verification sans objet.
    empreinte: str = ""
    source: str = ""                         # chemin du fichier charge

    def __post_init__(self) -> None:
        # Une pipeline sans empreinte ne peut pas etre reprise : la garde qui
        # compare le monde d'avant a celui d'aujourd'hui n'aurait rien a
        # comparer. `charger()` est le seul constructeur du depot et la
        # remplit toujours ; ce controle existe pour que ca reste vrai si un
        # second chemin de construction apparait.
        if not self.empreinte.strip():
            raise ValueError(
                f"pipeline {self.nom!r} sans empreinte. C'est elle que la "
                f"reprise compare pour verifier que ni la pipeline ni le jeu "
                f"n'ont change ; vide, la garde n'aurait rien a comparer")

    @property
    def iterative(self) -> bool:
        return self.classe == "iterative"

    @property
    def sauvegarde_quelque_part(self) -> bool:
        return any(e.sauvegarde for e in self.etapes)
