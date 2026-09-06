"""Du controleur vers le journal — un seul point de passage.

Le controleur constate, le journal enregistre, et ce module est la charniere.
Il est court et il porte **le point d'integration le plus important du
dispositif**.

**Une sauvegarde imminente ne se journalise pas comme une garde.** Le repli
des etats deduit l'etat `douteux` d'une `Etape(sauvegarde=True)` — jamais d'un
`Garde`. Or le controleur annonce la sauvegarde a venir par un
`Constat(garde="rayon", verdict="sauvegarde_imminente")`, et l'annonce precede
l'acte precisement pour survivre a une coupure. Traduire ce constat-la en
`Garde` laisserait le repli aveugle : un item interrompu apres une sauvegarde
reussie repartirait `en_cours`, donc rejoue, donc **ecrit deux fois dans
SAP**. Rien ne leverait.

C'est pour ca que ce module existe separement, et pour ca qu'un controle
negatif du depot casse cette traduction et exige que la suite tombe.

**Les dataclasses ne traversent pas.** Le journal est du JSONL : il attend des
dictionnaires. La conversion est faite ici, une fois, plutot que dans chaque
appelant — ou elle finirait par diverger.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Callable

from falcon.controleur import Constat
from falcon.journal import Etape as EtapeJournal
from falcon.journal import Garde, Incident
from falcon.noyau import SAUVEGARDE_IMMINENTE, VERDICTS
from falcon.taxonomie import INCONNUE, ecrire_dump

#: Garde a laquelle se rattache l'annonce de sauvegarde.
GARDE_RAYON = "rayon"


class Adaptateur:
    """Traduit les constats du controleur en enregistrements de journal.

    Porte l'item courant, que le controleur ignore : les gardes ne savent pas
    quel item tourne, et un constat sans `item_id` serait inexploitable au
    repli.
    """

    def __init__(self, ecrire: Callable[[object], object], run_id: str,
                 dossier_dumps: str | Path | None = None):
        self._ecrire = ecrire
        self._run_id = run_id
        self._dumps = Path(dossier_dumps) if dossier_dumps else None
        self.item_id: str | None = None
        self.etape: str = ""

    def __call__(self, constat: Constat) -> None:
        """Branche sur `DriverGarde(noter=...)`."""
        if constat.verdict not in VERDICTS:
            # Un verdict hors vocabulaire s'ecrirait sans bruit dans un
            # fichier cense faire foi. Mieux vaut que le lot tombe.
            raise ValueError(
                f"verdict {constat.verdict!r} hors vocabulaire ; connus : "
                f"{sorted(VERDICTS)}")

        if constat.verdict == SAUVEGARDE_IMMINENTE:
            self._annoncer_sauvegarde(constat)
            return

        self._ecrire(Garde(
            run_id=self._run_id, garde=constat.garde,
            verdict=constat.verdict, item_id=self.item_id,
            detail=dict(constat.detail),
            derogation=(asdict(constat.derogation)
                        if constat.derogation is not None else None)))

        if constat.taxonomie is not None:
            self._incident(constat)

    def _annoncer_sauvegarde(self, constat: Constat) -> None:
        """L'annonce qui fait vivre l'etat « douteux ».

        Ecrite comme une ETAPE marquee sauvegarde, parce que c'est ce que le
        repli des etats lit. La traduire en `Garde` desarmerait la protection
        contre la double ecriture — sans que rien ne leve.
        """
        self._ecrire(EtapeJournal(
            run_id=self._run_id,
            etape=str(constat.detail.get("etape") or self.etape),
            action=str(constat.detail.get("geste") or ""),
            sauvegarde=True, item_id=self.item_id))

    def _incident(self, constat: Constat) -> None:
        verdict = constat.taxonomie
        assert verdict is not None
        dump = None
        if verdict.categorie == INCONNUE and self._dumps is not None:
            # Un inconnu est bloquant : on garde de quoi le comprendre, et
            # c'est ce dump qui fera entrer une entree dans le registre.
            dump = str(ecrire_dump(self._dumps, {
                "run_id": self._run_id, "item_id": self.item_id,
                "garde": constat.garde, "detail": constat.detail}))
        self._ecrire(Incident(
            run_id=self._run_id, categorie=verdict.categorie,
            signature=dict(constat.detail), bloquant=verdict.bloquant,
            item_id=self.item_id, entree=verdict.entree, dump=dump))
