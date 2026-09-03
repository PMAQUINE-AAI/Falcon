"""Contrat d'etape et derogations.

Le contrat est ce que le controleur donne aux gardes pour une etape : quel
ecran est attendu, quelles fenetres sont prevues, si l'etape sauvegarde. Les
gardes ne decident rien d'elles-memes, elles verifient ce contrat.

**La pipeline declare une intention ; le controleur applique les regles.**
Consequence directe, et c'est tout l'objet de ce module : une pipeline ne peut
pas desactiver une garde. Elle peut demander une derogation, qui doit etre
nommee, motivee, et sera tracee a chaque execution. Sans cette asymetrie, la
premiere pipeline pressee contournerait le dispositif et l'ensemble ne
vaudrait plus rien.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Gardes sur lesquelles une derogation est concevable.
#:
#: L'identite d'ecran et le rayon d'action n'y sont PAS, et ne peuvent pas y
#: etre ajoutees par un fichier : une identite violee signale que le modele du
#: monde est faux, et un plafond est la derniere barriere avant le lot entier.
#: Deroger a l'une ou l'autre reviendrait a retirer le fond du filet.
DEROGEABLES = frozenset({"statut", "fenetre", "relecture"})

#: Un motif doit dire quelque chose. Ce seuil n'empeche pas d'ecrire une
#: betise, il empeche d'ecrire « ok » et de passer a autre chose.
MOTIF_MINIMAL = 30

#: Comment comparer ce qu'on a ecrit a ce qu'on relit.
#:
#: `casse` est le defaut et n'accepte QUE les differences de casse et
#: d'espaces. Une troncature n'y passe pas : accepter n'importe quel prefixe
#: revenait a valider « 1 » comme normalisation de « 1000 », c'est-a-dire a
#: laisser ecrire une valeur fausse en production sans un mot.
#:
#: `prefixe` accepte la troncature, pour les champs dont on SAIT qu'ils sont
#: plus courts que la valeur ecrite. Il se declare etape par etape : la charge
#: de la preuve revient a qui sait, pas au defaut.
COMPARAISONS = frozenset({"exact", "casse", "prefixe"})


class DerogationRefusee(Exception):
    """Une derogation impossible ou insuffisamment motivee."""


@dataclass(frozen=True)
class Derogation:
    """Demande nommee de ne pas bloquer sur une garde precise.

    Ne desactive rien : la garde s'execute toujours et son constat est
    toujours trace. Seule change l'issue — noter au lieu d'interrompre.
    """

    garde: str
    portee: str
    motif: str

    def __post_init__(self) -> None:
        if self.garde not in DEROGEABLES:
            raise DerogationRefusee(
                f"aucune derogation possible a la garde {self.garde!r}. "
                f"Derogeables : {sorted(DEROGEABLES)}")
        if len(self.motif.strip()) < MOTIF_MINIMAL:
            raise DerogationRefusee(
                f"derogation a {self.garde!r} : motif trop court "
                f"({len(self.motif.strip())} caracteres, {MOTIF_MINIMAL} "
                f"minimum). Une derogation non expliquee est une garde "
                f"desactivee en douce")


@dataclass(frozen=True)
class Contrat:
    """Ce qu'une etape declare, et que les gardes verifient.

    `ecran_attendu` a None signifie navigation libre : l'etape ne sait pas
    encore ou elle atterrit. C'est le seul cas ou la garde d'identite ne
    s'applique pas, et il doit rester rare.
    """

    nom: str = ""
    ecran_attendu: tuple[str, str, str] | None = None    # transaction, programme, dynpro
    fenetres_attendues: tuple[str, ...] = ("wnd[0]",)
    relire: bool = True                    # garde 4, active par defaut
    comparaison: str = "casse"
    statut_attendu: str | None = None      # « S » si l'etape DOIT produire un message
    sauvegarde: bool = False
    derogations: tuple[Derogation, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.comparaison not in COMPARAISONS:
            raise ValueError(
                f"comparaison {self.comparaison!r} inconnue, "
                f"attendu {sorted(COMPARAISONS)}")

    def derogation_pour(self, garde: str) -> Derogation | None:
        for derogation in self.derogations:
            if derogation.garde == garde:
                return derogation
        return None
