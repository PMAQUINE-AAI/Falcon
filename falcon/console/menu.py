"""Moteur de menus : une boucle, une pile, aucune dependance.

**Ni `curses`, ni bibliotheque tierce, et ce n'est pas un choix d'ascese.**
`curses` n'existe pas dans la distribution CPython de Windows — il faudrait
`windows-curses` — et Windows est precisement la machine ou cet outil doit
tourner, puisque c'est la seule ou SAP GUI existe. Une console qui ne
demarrerait pas la ou elle sert ne servirait a rien. Le reste de FALCON tient
avec `PyYAML` pour seule dependance ; une interface n'est pas une raison d'en
ajouter.

Le rendu est donc un menu numerote sur un flux texte : ca marche dans `cmd`,
dans PowerShell, dans un terminal Linux, a travers RDP, et dans un journal
rediriges. Aucune sequence ANSI, aucun caractere semi-graphique — voir
`ENCODAGE_MINIMAL`.

**Les entrees/sorties sont injectees**, pas cablees sur `input` et `print`.
C'est ce qui rend la console testable : une suite lui joue une session
complete sans terminal, et sans capturer quoi que ce soit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Union

#: Verdicts qu'une action rend au moteur.
CONTINUER = "continuer"     # rester sur le menu courant
RETOUR = "retour"           # remonter d'un cran
QUITTER = "quitter"         # sortir de la console

VERDICTS = frozenset({CONTINUER, RETOUR, QUITTER})

#: Encodage que le rendu doit supporter.
#:
#: Une console Windows francaise redirigee vers un fichier ecrit en cp1252. Un
#: cadre semi-graphique — U+2500 et compagnie — y leve `UnicodeEncodeError`,
#: et l'outil meurt sur son propre decor. Les guillemets francais, les tirets
#: cadratins et les lettres accentuees passent : cp1252 les couvre.
ENCODAGE_MINIMAL = "cp1252"

LARGEUR = 72


class Console:
    """Les deux gestes d'une interface texte, injectables.

    `lire` doit lever `EOFError` en fin de flux : c'est ainsi qu'une console
    pilotee par un script se termine proprement au lieu de boucler a vide.
    """

    def __init__(self,
                 lire: Callable[[str], str] | None = None,
                 ecrire: Callable[[str], None] | None = None):
        self._lire = lire or input
        self._ecrire = ecrire or print

    def lire(self, invite: str = "  > ") -> str:
        return self._lire(invite)

    def ecrire(self, texte: str = "") -> None:
        self._ecrire(texte)

    def titre(self, texte: str) -> None:
        self.ecrire()
        self.ecrire("=" * LARGEUR)
        self.ecrire(f"  {texte}")
        self.ecrire("=" * LARGEUR)

    def section(self, texte: str) -> None:
        self.ecrire()
        self.ecrire(f"  {texte}")
        self.ecrire("  " + "-" * (LARGEUR - 4))

    def pause(self) -> None:
        """Laisse le temps de lire avant de reafficher le menu."""
        try:
            self.lire("\n  [Entree] pour revenir au menu ")
        except (EOFError, KeyboardInterrupt):
            pass


Action = Callable[[Console], str]


@dataclass(frozen=True)
class Entree:
    """Une ligne de menu : une clef, un libelle, et ce qu'elle declenche.

    `cible` est soit une action, soit un sous-menu. Les deux cas sont
    distingues par le type et non par une convention, pour qu'un sous-menu
    oublie ne se retrouve pas appele comme une fonction.
    """

    clef: str
    libelle: str
    cible: Union[Action, "Menu"]
    detail: str = ""


@dataclass(frozen=True)
class Menu:
    titre: str
    entrees: tuple[Entree, ...]
    preambule: str = ""
    clefs_libres: tuple[str, ...] = field(default_factory=tuple)

    def entree(self, clef: str) -> Entree | None:
        for entree in self.entrees:
            if entree.clef == clef.strip().lower():
                return entree
        return None


def rendre(menu: Menu, *, racine: bool) -> list[str]:
    """Le menu, en lignes. Separe de l'affichage pour rester verifiable."""
    lignes = ["", "=" * LARGEUR, f"  {menu.titre}", "=" * LARGEUR]
    if menu.preambule:
        lignes.append("")
        lignes += [f"  {ligne}" for ligne in menu.preambule.splitlines()]
    lignes.append("")
    for entree in menu.entrees:
        lignes.append(f"  {entree.clef:>2}  {entree.libelle}")
        if entree.detail:
            lignes.append(f"      {entree.detail}")
    lignes.append(f"  {'0':>2}  {'Quitter' if racine else 'Retour'}")
    lignes.append("")
    return lignes


def parcourir(racine: Menu, console: Console) -> int:
    """Boucle principale. Rend le code de sortie du processus.

    Une pile de menus plutot que des appels imbriques : la profondeur reste
    lisible, `0` remonte toujours d'un cran, et une action ne peut pas
    enfermer l'utilisateur dans un sous-menu dont elle serait la seule sortie.
    """
    pile: list[Menu] = [racine]
    while pile:
        for ligne in rendre(pile[-1], racine=len(pile) == 1):
            console.ecrire(ligne)
        try:
            saisie = console.lire().strip().lower()
        except (EOFError, KeyboardInterrupt):
            # Fin de flux ou Ctrl-C : on sort proprement. Une console qui
            # boucle sur un flux epuise est un processus a tuer a la main.
            console.ecrire("\n  Fin de session.")
            return 0

        if saisie in ("0", "q", "quitter"):
            pile.pop()
            continue

        entree = pile[-1].entree(saisie)
        if entree is None:
            console.ecrire(f"\n  « {saisie} » n'est pas une option de ce menu.")
            continue

        if isinstance(entree.cible, Menu):
            pile.append(entree.cible)
            continue

        verdict = entree.cible(console)
        if verdict not in VERDICTS:
            raise ValueError(
                f"l'action {entree.clef!r} a rendu {verdict!r} ; attendu "
                f"{sorted(VERDICTS)}")
        if verdict == QUITTER:
            return 0
        if verdict == RETOUR and len(pile) > 1:
            pile.pop()
    return 0
