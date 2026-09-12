"""Progression d'un lot : les faits, l'estimation, et leur rendu.

**Trois choses separees, et la separation est le point du module.** Le moteur
emet des FAITS — quel item, quel rang, combien de temps. `Suivi` en tire une
ESTIMATION. `ligne` en fait une CHAINE. Personne ici n'ecrit nulle part : le
choix du flux et du redessin appartient a `terminal.py`.

C'est ce qui rend le lot testable sans terminal et sans capture : les tests
comparent des chaines, pas des octets sortis d'un `tty`.

**Un rendu encodable en cp1252, et aucune sequence emise ICI** — memes
contraintes que la console, et pour la meme raison : la machine ou ce reporting
servira est une machine Windows, et un decor qui ne s'encode pas y tue le
programme qu'il decore.

Que ce module n'emette aucune sequence ne dit plus rien du depot entier : la
couleur y est desormais permise la ou elle a ete PROUVEE (voir
`falcon/toile/`). Elle ne l'est pas ici parce que `ligne` rend une CHAINE que
des tests comparent caractere par caractere, et qu'un module qui ne choisit ni
son flux ni son terminal n'a rien lu qui lui permette de decider.

**L'ETA est une moyenne GLISSANTE**, pas une moyenne generale. Un lot dont les
premiers items sont rapides et les suivants lents donnerait, avec une moyenne
generale, une estimation qui se degrade en permanence sans jamais coller. La
fenetre glissante suit le regime courant.

Le §4.6 demande de memoriser les durees entre executions ; le §6 range cette
historisation en V2. Ce module fait le glissant intra-execution, et s'arrete
la.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

#: Nombre d'items sur lesquels la moyenne glisse.
#:
#: Assez court pour suivre un changement de regime, assez long pour qu'un
#: item anormalement lent ne fasse pas bondir l'estimation.
FENETRE = 20

#: Encodage que le rendu doit supporter. Voir `console.menu`.
ENCODAGE_MINIMAL = "cp1252"


@dataclass(frozen=True)
class Progres:
    """Les faits, tels que le moteur les connait. Aucune estimation ici."""

    item: str
    rang: int
    total: int
    duree_ms: int = 0
    compteurs: dict[str, int] = field(default_factory=dict)

    @property
    def restants(self) -> int:
        return max(0, self.total - self.rang)


@dataclass(frozen=True)
class Estimation:
    """Ce que `Suivi` en deduit."""

    moyenne_ms: int = 0
    eta_s: int = 0
    echantillon: int = 0

    @property
    def fiable(self) -> bool:
        """Une estimation batie sur un seul item n'en est pas une."""
        return self.echantillon >= 3


class Suivi:
    """Garde les dernieres durees et en tire une estimation glissante."""

    def __init__(self, fenetre: int = FENETRE):
        if fenetre < 1:
            raise ValueError("la fenetre glissante doit valoir au moins 1")
        self._durees: deque[int] = deque(maxlen=fenetre)

    def ajouter(self, progres: Progres) -> Estimation:
        # Une duree nulle ou negative n'apprend rien et fausserait la moyenne
        # vers le bas — typiquement un item ignore en dry-run.
        if progres.duree_ms > 0:
            self._durees.append(progres.duree_ms)
        if not self._durees:
            return Estimation()
        moyenne = sum(self._durees) // len(self._durees)
        return Estimation(moyenne_ms=moyenne,
                          eta_s=(moyenne * progres.restants) // 1000,
                          echantillon=len(self._durees))


def duree(secondes: int) -> str:
    """`00:01:23`. Sans unite exotique : ca se lit d'un coup d'oeil."""
    secondes = max(0, int(secondes))
    heures, reste = divmod(secondes, 3600)
    minutes, restantes = divmod(reste, 60)
    return f"{heures:02d}:{minutes:02d}:{restantes:02d}"


def ligne(progres: Progres, estimation: Estimation) -> str:
    """Une ligne de progression. Fonction PURE : rien n'est ecrit ici.

    Tant que l'estimation n'est pas fiable, l'ETA affiche `--:--:--` plutot
    qu'un chiffre. Un ETA faux est pire qu'un ETA absent : on planifie
    dessus.
    """
    compteurs = progres.compteurs
    morceaux = [
        f"[{progres.rang:>{len(str(progres.total))}}/{progres.total}]",
        f"ok {compteurs.get('ok', 0)}",
        f"ko {compteurs.get('ko', 0)}",
        f"douteux {compteurs.get('douteux', 0)}",
    ]
    if estimation.moyenne_ms:
        morceaux.append(f"{estimation.moyenne_ms / 1000:.1f} s/item")
    morceaux.append(
        f"ETA {duree(estimation.eta_s) if estimation.fiable else '--:--:--'}")
    if progres.item:
        morceaux.append(progres.item)
    return "  ".join(morceaux)


def bilan(progres: Progres, estimation: Estimation) -> str:
    """La ligne de fin, sans ETA — il n'y a plus rien a estimer."""
    compteurs = progres.compteurs
    total = sum(v for c, v in compteurs.items() if c != "deja_faits")
    morceaux = [f"{total} item(s) traite(s)"]
    for etat in ("ok", "ko", "ignore", "douteux"):
        if compteurs.get(etat):
            morceaux.append(f"{etat} {compteurs[etat]}")
    if compteurs.get("deja_faits"):
        morceaux.append(f"deja faits {compteurs['deja_faits']}")
    if estimation.moyenne_ms:
        morceaux.append(f"{estimation.moyenne_ms / 1000:.1f} s/item")
    return "  ".join(morceaux)
