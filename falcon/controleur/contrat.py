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

from falcon.noyau import (
    COMPARAISONS, DEROGEABLES, MOTIF_MINIMAL, PORTEE_TOTALE,
)



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


class ContratIncomplet(Exception):
    """Une etape qui ne dit pas ou elle s'execute."""


@dataclass(frozen=True)
class Contrat:
    """Ce qu'une etape declare, et que les gardes verifient.

    **Une etape doit dire ou elle s'execute.** L'ecran attendu est obligatoire,
    ou bien la navigation libre est declaree explicitement. La version
    precedente laissait `ecran_attendu` a None PAR DEFAUT, ce qui faisait
    qu'une etape distraite neutralisait sans un mot la garde qui attrape a
    elle seule la majorite des derives.

    Trois relachements sont possibles, et les trois laissent une trace au
    moment ou le contrat est pose :

        navigation_libre=True       la garde d'identite ne s'applique pas
        Derogation("relecture")     la relecture apres ecriture est sautee
        fenetres_attendues elargie  une modale est prevue par l'etape

    Aucun n'est silencieux, et aucun ne s'obtient par omission : c'est la
    difference entre une decision et un oubli.
    """

    nom: str = ""
    ecran_attendu: tuple[str, str, str] | None = None    # transaction, programme, dynpro
    navigation_libre: bool = False
    fenetres_attendues: tuple[str, ...] = ("wnd[0]",)
    comparaison: str = "casse"
    statut_attendu: str | None = None      # « S » si l'etape DOIT produire un message
    sauvegarde: bool = False
    derogations: tuple[Derogation, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.comparaison not in COMPARAISONS:
            raise ValueError(
                f"comparaison {self.comparaison!r} inconnue, "
                f"attendu {sorted(COMPARAISONS)}")

        if self.ecran_attendu is None and not self.navigation_libre:
            raise ContratIncomplet(
                f"etape {self.nom!r} : declarer `ecran_attendu`, ou "
                f"`navigation_libre=True` si l'etape ne sait pas encore ou "
                f"elle atterrit. Une etape muette neutralise la garde "
                f"d'identite sans que personne ne le voie")

        if self.ecran_attendu is not None and self.navigation_libre:
            raise ContratIncomplet(
                f"etape {self.nom!r} : `navigation_libre` et `ecran_attendu` "
                f"ensemble n'ont pas de sens — l'un des deux est de trop")

    def derogation_pour(self, garde: str) -> Derogation | None:
        """La derogation applicable a cette garde, si sa portee couvre l'etape.

        `portee` etait declaree et jamais lue : une derogation ecrite pour une
        etape valait pour toutes celles qui partageaient le contrat.
        """
        for derogation in self.derogations:
            if derogation.garde != garde:
                continue
            if derogation.portee in (PORTEE_TOTALE, f"etape:{self.nom}"):
                return derogation
        return None

    @property
    def relachements(self) -> tuple[tuple[str, str, dict], ...]:
        """(garde, verdict, detail) pour chaque garde relachee par ce contrat.

        Lu une fois par etape, au moment ou le contrat est pose — pas a chaque
        action, ce qui noierait le journal.
        """
        traces: list[tuple[str, str, dict]] = []

        if self.navigation_libre:
            traces.append(("identite", "non_gardee", {"etape": self.nom}))

        elargies = [f for f in self.fenetres_attendues if f != "wnd[0]"]
        if elargies:
            traces.append(("fenetre", "elargie",
                           {"etape": self.nom, "attendues": elargies}))

        for derogation in self.derogations:
            # Ce qui est TRACE doit etre ce qui S'APPLIQUE.
            #
            # La boucle ecrivait « derogee » pour chaque derogation portee par
            # l'etape, sans consulter `portee` — alors que `derogation_pour`,
            # elle, la consulte. Une derogation visant une autre etape faisait
            # donc ecrire au journal qu'une garde etait relachee pendant
            # qu'elle restait armee : le journal disait le contraire de ce qui
            # se passait, sur la ligne meme qu'un humain relit pour savoir
            # quelles gardes ont ete assouplies.
            #
            # Le chargeur refuse desormais ce cas ; ce filtre est la seconde
            # barriere, et il fait coincider les deux lectures de `portee`.
            if derogation.portee not in (PORTEE_TOTALE, f"etape:{self.nom}"):
                continue
            traces.append((derogation.garde, "derogee",
                           {"etape": self.nom, "portee": derogation.portee,
                            "motif": derogation.motif}))

        return tuple(traces)


def contrat_pour(etape: "Etape") -> Contrat:
    """Traduit une etape declaree en contrat de garde.

    La conversion vit ici, dans le controleur, et non dans la pipeline. C'est
    l'asymetrie du modele de securite rendue structurelle : le controleur
    connait la pipeline, la pipeline ignore le controleur. Une derogation
    DEMANDEE dans le YAML ne devient une derogation ACCORDEE qu'en passant par
    ce point, ou `Derogation.__post_init__` la revalide.
    """
    from falcon.pipeline.modele import Etape       # noqa: F401 — annotation

    return Contrat(
        nom=etape.nom,
        ecran_attendu=etape.ecran,
        navigation_libre=etape.navigation_libre,
        fenetres_attendues=etape.fenetres,
        comparaison=etape.comparaison,
        statut_attendu=etape.statut_attendu,
        sauvegarde=etape.sauvegarde,
        derogations=tuple(
            Derogation(garde=d.garde, portee=d.portee, motif=d.motif)
            for d in etape.derogations),
    )
