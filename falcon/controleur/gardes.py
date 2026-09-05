"""Les cinq gardes, appliquees une fois pour toutes.

Elles vivent ici et nulle part ailleurs. Dispersees dans les pipelines, elles
seraient recopiees, puis oubliees dans celle qu'on ecrit tard le soir. En les
placant dans l'objet par lequel tout passe, elles s'appliquent a toutes les
pipelines sans que celles-ci aient a y penser — et sans qu'elles puissent y
echapper.

    1. identite   avant chaque action, l'ecran doit etre celui attendu
    2. statut     apres chaque validation, la barre de statut est lue
    3. fenetres   une fenetre imprevue arrete tout
    4. relecture  ce qu'on ecrit est relu avant de valider
    5. rayon      un plafond de sauvegardes, obligatoire

`DriverGarde` implemente `Driver` : meme surface, donc substituable partout,
et le code qui l'utilise ne sait pas s'il parle a SAP ou a un double.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from falcon.couture import Driver
from falcon.noyau import (
    Ecran, EcartIdentite, Fenetre, FenetreImprevue, Identite, IncidentBloquant,
    ItemAbandonne, PlafondAtteint, RefusDryRun, Statut,
)
from falcon.taxonomie import Registre, Signature, Verdict

from .contrat import Contrat, Derogation

#: Touche de fonction et bouton de barre correspondant a « Sauvegarder ».
#:
#: Reconnus d'office, meme si le contrat ne declare pas l'etape comme une
#: sauvegarde. C'est une securite contre l'oubli, pas une detection complete :
#: une sauvegarde declenchee par un chemin de menu passe au travers, faute de
#: catalogue des menus. La limite est reelle et vaut mieux enoncee que masquee.
VKEY_SAUVEGARDE = 11
BOUTON_SAUVEGARDE = "tbar[0]/btn[11]"


@dataclass(frozen=True)
class Constat:
    """Trace d'une garde qui a eu quelque chose a dire.

    Emis uniquement sur violation, derogation ou normalisation : journaliser
    chaque garde satisfaite noierait le fichier, elles se declenchent a chaque
    action.
    """

    garde: str
    verdict: str                     # violation | derogee | normalise
    detail: dict[str, Any] = field(default_factory=dict)
    derogation: Derogation | None = None
    taxonomie: Verdict | None = None


class DriverGarde(Driver):
    """Enveloppe un driver brut et applique les gardes a chaque appel.

    Le driver brut est sous nom mangle et n'a aucun accesseur : on ne le
    recupere pas par inadvertance. Ce n'est pas une protection contre un
    developpeur determine — c'en est une contre la commodite d'un soir.
    """

    def __init__(self,
                 brut: Driver,
                 registre: Registre,
                 *,
                 mode: str = "run",
                 plafond_sauvegardes: int,
                 noter: Callable[[Constat], None] | None = None):
        self.__brut = brut
        self._registre = registre
        self._mode = mode
        self._plafond = plafond_sauvegardes
        self._sauvegardes = 0
        # Hors etape : aucun ecran n'est attendu parce qu'aucune etape ne
        # tourne. Ce contrat n'est jamais pose par `sous_contrat`, donc il ne
        # trace rien — et toute action reelle passe par un contrat d'etape.
        self._contrat = Contrat(nom="(hors etape)", navigation_libre=True)
        self.constats: list[Constat] = []
        self._noter_externe = noter

    # -- contrat -----------------------------------------------------------

    @contextmanager
    def sous_contrat(self, contrat: Contrat) -> Iterator["DriverGarde"]:
        """Applique un contrat le temps d'une etape.

        N'est PAS expose par `Poste` : une etape Python ne peut pas se donner
        un contrat plus permissif que celui que le controleur lui a fixe.
        """
        precedent = self._contrat
        self._contrat = contrat
        for garde, verdict, detail in contrat.relachements:
            self._noter(Constat(garde=garde, verdict=verdict, detail=detail,
                                derogation=contrat.derogation_pour(garde)))
        try:
            yield self
        finally:
            self._contrat = precedent

    @property
    def contrat(self) -> Contrat:
        return self._contrat

    @property
    def sauvegardes(self) -> int:
        return self._sauvegardes

    def _noter(self, constat: Constat) -> Constat:
        self.constats.append(constat)
        if self._noter_externe:
            self._noter_externe(constat)
        return constat

    # =====================================================================
    # Gardes
    # =====================================================================

    def _garde_identite(self) -> None:
        """Garde 1. Non derogeable.

        Attrape a elle seule la majorite des derives : popup imprevu,
        transaction refusee, autorisation manquante, donnees inattendues.
        """
        attendu = self._contrat.ecran_attendu
        if attendu is None:
            # Navigation libre : declaree explicitement par l'etape, et deja
            # tracee au moment ou le contrat a ete pose.
            return
        observe = self.__brut.screen().triplet
        if tuple(attendu) != observe:
            self._noter(Constat(garde="identite", verdict="violation",
                                detail={"attendu": list(attendu),
                                        "observe": list(observe),
                                        "etape": self._contrat.nom}))
            raise EcartIdentite(
                f"etape {self._contrat.nom!r} : ecran attendu {tuple(attendu)}, "
                f"observe {observe}")

    def _garde_rayon(self) -> None:
        """Garde 5. Non derogeable : derniere barriere avant le lot entier."""
        if self._sauvegardes >= self._plafond:
            raise PlafondAtteint(
                f"plafond de {self._plafond} sauvegarde(s) atteint")

    def _garde_fenetres(self) -> None:
        """Garde 3. Une fenetre non prevue par l'etape arrete tout."""
        ouvertes = tuple(f.id for f in self.__brut.windows())
        intruses = [f for f in ouvertes if f not in self._contrat.fenetres_attendues]
        if not intruses:
            return

        derogation = self._contrat.derogation_pour("fenetre")
        detail = {"attendues": list(self._contrat.fenetres_attendues),
                  "ouvertes": list(ouvertes), "intruses": intruses,
                  "etape": self._contrat.nom}
        if derogation is not None:
            self._noter(Constat(garde="fenetre", verdict="derogee",
                                detail=detail, derogation=derogation))
            return
        self._noter(Constat(garde="fenetre", verdict="violation", detail=detail))
        raise FenetreImprevue(
            f"etape {self._contrat.nom!r} : fenetre(s) imprevue(s) {intruses}")

    def _garde_statut(self) -> None:
        """Garde 2. Lit la barre de statut et fait classer ce qu'elle dit."""
        statut = self.__brut.status()
        attendu = self._contrat.statut_attendu

        if attendu is not None and statut.type != attendu:
            # Le silence est un signal : une selection qui ne remonte rien et
            # n'emet aucun message n'est pas une preuve d'absence de donnees.
            signature = Signature(canal="garde", garde="statut",
                                  attendu=attendu, observe=statut.type,
                                  contexte=self._contexte())
        elif statut.type in {"E", "A"}:
            signature = Signature(canal="statut", type=statut.type,
                                  id=statut.id, numero=statut.numero,
                                  texte=statut.texte, contexte=self._contexte())
        else:
            return

        self._traiter("statut", signature,
                      {"statut": {"type": statut.type, "id": statut.id,
                                  "numero": statut.numero,
                                  "texte": statut.texte},
                       "attendu": attendu, "etape": self._contrat.nom})

    def _garde_relecture(self, id: str, ecrit: str) -> None:
        """Garde 4. Ecrire sans que ca prenne est une classe de bug connue.

        La comparaison tolere ce que SAP fait subir aux saisies — troncature,
        majuscules — et TRACE cette tolerance. Une comparaison stricte rendrait
        la garde insupportable des le premier jour, et quelqu'un la
        desactiverait ; une comparaison laxiste et muette laisserait passer une
        vraie divergence.
        """
        # Une etape qui ne PEUT pas relire — l'editeur SAPscript n'est pas
        # adressable — le declare par une derogation nommee et motivee, deja
        # tracee a la pose du contrat. Il n'existe plus de drapeau booleen
        # pour sauter la relecture en silence.
        if self._contrat.derogation_pour("relecture") is not None:
            return

        lu = self.__brut.read(id)
        verdict = _comparer(ecrit, lu, self._contrat.comparaison)
        if verdict == "conforme":
            return

        detail = {"cible": id, "attendu": ecrit, "lu": lu,
                  "comparaison": self._contrat.comparaison,
                  "etape": self._contrat.nom}

        if verdict in {"normalise", "tronque"}:
            self._noter(Constat(garde="relecture", verdict=verdict,
                                detail=detail))
            return

        self._traiter("relecture",
                      Signature(canal="garde", garde="relecture",
                                contexte=self._contexte()),
                      detail)

    # -- classement commun --------------------------------------------------

    def _contexte(self) -> dict[str, str]:
        identite = self.__brut.screen()
        return {"transaction": identite.transaction,
                "programme": identite.programme,
                "dynpro": identite.dynpro}

    def _traiter(self, garde: str, signature: Signature,
                 detail: dict[str, Any]) -> None:
        """Fait classer une signature, puis applique la politique obtenue."""
        derogation = self._contrat.derogation_pour(garde)
        if derogation is not None:
            self._noter(Constat(garde=garde, verdict="derogee", detail=detail,
                                derogation=derogation))
            return

        verdict = self._registre.classer(signature)
        self._noter(Constat(garde=garde, verdict="violation", detail=detail,
                            taxonomie=verdict))

        origine = f"etape {self._contrat.nom!r} : {verdict.categorie} " \
                  f"({verdict.entree or 'non repertorie'}) — {detail}"

        if verdict.bloquant:
            raise IncidentBloquant(origine)

        if verdict.politique.item == "ko":
            # « Connue fautive » : l'item est perdu, le lot continue. Sans
            # cette levee, l'appel rendrait la main normalement et l'etape
            # suivante — typiquement la sauvegarde — s'executerait sur un
            # ecran dont on vient justement de constater qu'il est faux.
            raise ItemAbandonne(origine)

    # -- sauvegarde et dry-run ----------------------------------------------

    def _avant_sauvegarde(self, geste: str) -> None:
        """Verifie le rayon d'action, puis ANNONCE la sauvegarde a venir.

        L'annonce precede l'acte, et c'est le point important. Si une garde
        levait apres coup — une modale imprevue, un message d'erreur —
        l'ecriture SAP aurait deja eu lieu et rien n'en garderait la trace :
        le repli du journal classerait l'item `en_cours`, la reprise le
        rejouerait, et SAP ecrirait deux fois. Journaliser l'intention est la
        seule chose qui survive a une garde qui leve au milieu.
        """
        if self._mode == "dry-run":
            raise RefusDryRun(
                f"{geste} declencherait une sauvegarde, refuse en dry-run")
        self._garde_rayon()
        self._sauvegardes += 1
        self._noter(Constat(garde="rayon", verdict="sauvegarde_imminente",
                            detail={"geste": geste, "etape": self._contrat.nom,
                                    "rang": self._sauvegardes}))

    def _est_sauvegarde(self, geste: str, cible: str = "", n: int = 0) -> bool:
        if self._contrat.sauvegarde:
            return True
        if geste == "vkey" and n == VKEY_SAUVEGARDE:
            return True
        return geste == "press" and cible.endswith(BOUTON_SAUVEGARDE)

    def _apres_action(self) -> None:
        self._garde_fenetres()
        self._garde_statut()

    # =====================================================================
    # Surface Driver
    # =====================================================================

    # -- observation : non gardee, les gardes s'en servent ------------------

    def screen(self) -> Identite:
        return self.__brut.screen()

    def fields(self, fenetre: str = "wnd[0]") -> Ecran:
        return self.__brut.fields(fenetre)

    def windows(self) -> tuple[Fenetre, ...]:
        return self.__brut.windows()

    def status(self) -> Statut:
        return self.__brut.status()

    # -- lecture et saisie ---------------------------------------------------

    def read(self, id: str) -> str:
        self._garde_identite()
        return self.__brut.read(id)

    def write(self, id: str, valeur: str) -> None:
        self._garde_identite()
        self.__brut.write(id, valeur)
        self._garde_relecture(id, valeur)

    def set_checked(self, id: str, coche: bool) -> None:
        self._garde_identite()
        self.__brut.set_checked(id, coche)

    # -- actions --------------------------------------------------------------

    def press(self, id: str) -> None:
        self._garde_identite()
        if self._est_sauvegarde("press", cible=id):
            self._avant_sauvegarde(f"press({id!r})")
        self.__brut.press(id)
        self._apres_action()

    def select(self, id: str) -> None:
        self._garde_identite()
        if self._est_sauvegarde("select", cible=id):
            self._avant_sauvegarde(f"select({id!r})")
        self.__brut.select(id)
        self._apres_action()

    def vkey(self, n: int, fenetre: str = "wnd[0]") -> None:
        self._garde_identite()
        if self._est_sauvegarde("vkey", n=n):
            self._avant_sauvegarde(f"vkey({n})")
        self.__brut.vkey(n, fenetre)
        self._apres_action()

    # -- ALV --------------------------------------------------------------------

    def grid_rows(self, id: str) -> int:
        self._garde_identite()
        return self.__brut.grid_rows(id)

    def grid_columns(self, id: str) -> tuple[str, ...]:
        self._garde_identite()
        return self.__brut.grid_columns(id)

    def grid_read(self, id: str, ligne: int, colonne: str) -> str:
        self._garde_identite()
        return self.__brut.grid_read(id, ligne, colonne)

    # -- table control -----------------------------------------------------------

    def table_visible_rows(self, id: str) -> int:
        self._garde_identite()
        return self.__brut.table_visible_rows(id)

    def table_scroll(self, id: str, position: int) -> None:
        self._garde_identite()
        self.__brut.table_scroll(id, position)


def _comparer(ecrit: str, lu: str, mode: str) -> str:
    """« conforme » | « normalise » | « tronque » | « divergent ».

    `normalise` ne couvre que la casse et les espaces — ce que SAP fait subir
    a toute saisie, sans perte d'information.

    `tronque` couvre la perte de fin, et n'est accepte que sous le mode
    `prefixe`, declare etape par etape. La version precedente acceptait
    n'importe quel prefixe sous le nom de « normalisation » : ecrire « 1000 »
    et relire « 1 » passait pour une troncature legitime. Sur une quantite, un
    poste ou un numero de gamme, c'est une valeur fausse ecrite en production
    sans un mot — exactement le genre de defaut que ce projet traque.
    """
    if ecrit == lu:
        return "conforme"
    if mode == "exact":
        return "divergent"

    attendu, obtenu = ecrit.strip(), lu.strip()
    if attendu.upper() == obtenu.upper():
        return "normalise"

    if mode == "prefixe" and obtenu and attendu.upper().startswith(obtenu.upper()):
        return "tronque"
    return "divergent"
