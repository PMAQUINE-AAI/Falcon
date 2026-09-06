"""Le moteur iteratif — la boucle qui consomme tout le reste.

C'est ici que les six sous-systemes se rencontrent enfin : le jeu de donnees
donne les items, la pipeline donne les etapes, le controleur porte les gardes,
la taxonomie classe ce qui sort de travers, le journal enregistre, et le
reexport rend les KO reinjectables.

**Quatre regles gouvernent la boucle, et aucune n'est negociable.**

1. *Un item KO n'interrompt pas le lot.* `ItemAbandonne` clot l'item et la
   boucle continue : perdre trois cents items parce que le quarantieme est
   fautif serait pire que l'absence d'automatisation.
2. *Un arret bloquant interrompt tout*, la chaine comprise. Une identite
   d'ecran violee dit que le modele du monde est faux ; continuer, c'est
   ecrire n'importe ou.
3. *Un item interrompu par un arret bloquant ne recoit PAS de fin.* Il reste
   ouvert dans le journal, et le repli decide : `en_cours` s'il n'a rien
   sauve — donc rejouable — `douteux` s'il a sauve — donc jamais rejoue. Lui
   poser un `ItemFin(ko)` le rendrait terminal et le perdrait pour de bon.
4. *Le moteur ne navigue pas entre items.* Une pipeline commence par sa propre
   navigation. C'est une limite ecrite, pas un oubli : inventer un geste de
   remise a zero, c'est inventer du comportement SAP.

**Ce que le moteur verifie AVANT de toucher a SAP.** Une source `colonne` lit
la premiere ligne de l'item. Si les lignes d'un item ne s'accordent pas sur
cette colonne, c'est que le regroupement par unite de sauvegarde ne colle pas
a ce que la pipeline lit — et une valeur serait choisie arbitrairement, sans
un mot. Le controle est fait sur tout le jeu avant la premiere action, pour
tomber a la preparation plutot qu'a l'item quarante.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from falcon.controleur import Constat, DriverGarde, Poste, contrat_pour
from falcon.donnees import (
    Dialecte, Item, empreinte_jeu, ecrire_items, lire_items,
)
from falcon.journal import (
    DOUTEUX, IGNORE, KO, OK, Ecrivain, ExecutionDebut, ExecutionFin, ItemDebut,
    ItemFin, preparer,
)
from falcon.noyau import (
    ArretBloquant, Echec, ErreurFalcon, Horloge, ItemAbandonne, PlafondAtteint,
    RefusDryRun, Refus, maintenant,
)
from falcon.pipeline import Etape, Pipeline, resoudre
from falcon.supervision import Progres
from falcon.taxonomie import Registre, Signature, appliquer

from .adaptateur import Adaptateur

if TYPE_CHECKING:                       # annotation seule : voir test_frontieres
    from falcon.couture import Driver

#: Modes d'execution (§3.3).
RUN = "run"
DRY_RUN = "dry-run"
REPRISE = "resume"
MODES = frozenset({RUN, DRY_RUN, REPRISE})

#: Etats de fin d'execution.
TERMINE = "termine"
INTERROMPU = "interrompu"
PLAFOND = "plafond"

#: Ce qui vaut « coche » dans un fichier d'entree.
#:
#: « X » y figure parce que c'est la convention de SAP lui-meme pour une case
#: cochee, et que les jeux de donnees viennent le plus souvent d'un export.
VRAI = frozenset({"true", "1", "x", "oui"})
FAUX = frozenset({"false", "0", "", "non"})


class PreparationImpossible(Exception):
    """Le jeu et la pipeline ne vont pas ensemble. Rien n'a ete tente."""


@dataclass(frozen=True)
class Resultat:
    """Ce qu'une execution rend. Aucune donnee exploitable par une suivante.

    C'est deliberé : le §3.3 ferme le perimetre de la chaine en interdisant
    tout passage de donnees entre pipelines. Un `Resultat` qui porterait des
    valeurs metier ferait de la chaine un orchestrateur.
    """

    run_id: str
    etat: str                              # termine | interrompu | plafond
    compteurs: dict[str, int] = field(default_factory=dict)
    raison: str = ""
    journal: str = ""
    ko: str | None = None
    duree_ms: int = 0

    @property
    def interrompu(self) -> bool:
        return self.etat != TERMINE


# ---------------------------------------------------------------------------
# Valeurs
# ---------------------------------------------------------------------------

def _valeur(etape: Etape, item: Item, lues: dict[str, str]) -> str:
    source = etape.source
    assert source is not None            # garanti par le chargeur
    if source.genre == "constante":
        return str(source.valeur)
    if source.genre == "lue":
        # Le chargeur a verifie qu'une etape `lire` de ce nom precede.
        return lues[source.valeur]
    return str(item.brut[0].get(source.valeur, ""))


def _booleen(brut: str, etape: str) -> bool:
    nettoye = brut.strip().lower()
    if nettoye in VRAI:
        return True
    if nettoye in FAUX:
        return False
    raise PreparationImpossible(
        f"etape {etape!r} : {brut!r} n'est ni vrai ni faux. Attendu l'un de "
        f"{sorted(VRAI | FAUX)}. Deviner ici, c'est cocher ou decocher une "
        f"case de selection au hasard")


def _colonnes_lues(pipeline: Pipeline) -> tuple[str, ...]:
    return tuple(sorted({e.source.valeur for e in pipeline.etapes
                         if e.source is not None and e.source.genre == "colonne"}))


def _verifier_coherence(pipeline: Pipeline, items: list[Item]) -> None:
    """Tout ce qui se verifie AVANT de toucher a SAP.

    Deux controles, et les deux tombent a la preparation plutot qu'a l'item
    quarante — c'est-a-dire avant qu'une seule ecriture ait eu lieu.
    """
    for colonne in _colonnes_lues(pipeline):
        for item in items:
            # Une source `colonne` lit la PREMIERE ligne de l'item. Si les
            # lignes se contredisent, c'est que le regroupement par unite de
            # sauvegarde ne colle pas a ce que la pipeline lit : la premiere
            # l'emporterait, et les autres seraient perdues sans un mot.
            valeurs = {str(ligne.get(colonne, "")) for ligne in item.brut}
            if len(valeurs) > 1:
                raise PreparationImpossible(
                    f"item {item.item_id} : {len(item.brut)} lignes ne "
                    f"s'accordent pas sur la colonne {colonne!r} "
                    f"({sorted(valeurs)}). Le regroupement par unite de "
                    f"sauvegarde ne colle pas a ce que la pipeline lit — "
                    f"revoir `cles`, ou la colonne")

    for etape in pipeline.etapes:
        if etape.action != "cocher" or etape.source is None:
            continue
        if etape.source.genre == "lue":
            continue            # valeur inconnue avant l'execution
        for item in items:
            # Une case dont la valeur n'est ni vraie ni fausse serait cochee
            # ou decochee au hasard. Le savoir maintenant vaut mieux que de
            # l'apprendre a l'item quarante, apres trente-neuf sauvegardes.
            _booleen(_valeur(etape, item, {}), etape.nom)


# ---------------------------------------------------------------------------
# Une etape
# ---------------------------------------------------------------------------

def _jouer_etape(etape: Etape, item: Item, garde: DriverGarde, poste: Poste,
                 lues: dict[str, str]) -> None:
    """Execute une etape SOUS SON CONTRAT. Rien ne s'execute hors contrat."""
    with garde.sous_contrat(contrat_pour(etape)):
        action = etape.action
        if action == "set":
            poste.write(etape.cible, _valeur(etape, item, lues))
        elif action == "cocher":
            poste.set_checked(
                etape.cible, _booleen(_valeur(etape, item, lues), etape.nom))
        elif action == "press":
            poste.press(etape.cible)
        elif action == "select":
            poste.select(etape.cible)
        elif action == "vkey":
            poste.vkey(int(_valeur(etape, item, lues)),
                       etape.cible or "wnd[0]")
        elif action == "lire":
            # L'etape lie sa lecture SOUS SON PROPRE NOM : c'est ce que le
            # chargeur a valide pour les sources « lue ».
            lues[etape.nom] = poste.read(etape.cible)
        elif action == "python":
            resoudre(etape.fonction)(poste, item, lues)
        else:                                       # pragma: no cover
            raise PreparationImpossible(
                f"etape {etape.nom!r} : action {action!r} sans execution")


def _classer_echec(erreur: Exception, canal: str, registre: Registre,
                   etape: str, adapter: Adaptateur) -> None:
    """Fait classer ce qui a leve hors des gardes, et applique la politique.

    Le moteur est le premier appelant de la taxonomie en dehors du controleur.
    Les canaux `com` et `python` du registre existaient depuis le lot 3 sans
    que rien ne les alimente ; c'est ici qu'ils prennent vie.
    """
    verdict = registre.classer(Signature(canal=canal,
                                         exception=type(erreur).__name__,
                                         texte=str(erreur)))
    adapter(Constat(garde=canal, verdict="violation",
                    detail={"etape": etape, "exception": type(erreur).__name__,
                            "message": str(erreur)},
                    taxonomie=verdict))
    appliquer(verdict, f"etape {etape!r} : {type(erreur).__name__} — {erreur}")


def _jouer_item(pipeline: Pipeline, item: Item, garde: DriverGarde,
                poste: Poste, registre: Registre,
                adapter: Adaptateur) -> None:
    lues: dict[str, str] = {}
    for etape in pipeline.etapes:
        adapter.etape = etape.nom
        try:
            _jouer_etape(etape, item, garde, poste, lues)
        except Refus:
            # RefusDryRun, ItemAbandonne, ArretBloquant : deja typés par la
            # doctrine. Un repli n'a pas le droit de les rattraper.
            raise
        except PreparationImpossible:
            # Un defaut de la pipeline ou du jeu, pas un comportement de SAP.
            # Le faire classer par la taxonomie le deguiserait en incident
            # metier, et l'auteur de la pipeline chercherait au mauvais
            # endroit. La plupart de ces cas tombent deja au pre-vol ; celui-ci
            # est la ceinture pour ceux qui n'y sont pas verifiables.
            raise
        except Echec as erreur:
            _classer_echec(erreur, "com", registre, etape.nom, adapter)
        except ErreurFalcon:
            raise
        except Exception as erreur:
            # Une etape Python maison. Elle passe par la taxonomie comme le
            # reste : l'inconnu y est bloquant, et c'est voulu.
            _classer_echec(erreur, "python", registre, etape.nom, adapter)


# ---------------------------------------------------------------------------
# L'execution
# ---------------------------------------------------------------------------

def executer(pipeline: Pipeline,
             jeu: str | Path,
             brut: "Driver",
             *,
             journal: str | Path,
             registre: Registre | None = None,
             mode: str = RUN,
             systeme: str = "",
             mandant: str = "",
             utilisateur: str = "",
             dossier_dumps: str | Path | None = None,
             sortie_ko: str | Path | None = None,
             observateur: Callable[[Progres], None] | None = None,
             horloge: Horloge = maintenant) -> Resultat:
    """Execute une pipeline iterative sur un jeu de donnees.

    `brut` est un driver de couture. Le moteur ne l'importe pas — la frontiere
    du §5.2 le lui interdit — il le recoit et l'enveloppe aussitot dans un
    `DriverGarde` : rien de ce qui suit ne touche un driver nu.
    """
    if mode not in MODES:
        raise PreparationImpossible(f"mode {mode!r}, attendu {sorted(MODES)}")
    if not pipeline.iterative:
        raise PreparationImpossible(
            f"{pipeline.nom!r} est une pipeline {pipeline.classe!r}. La "
            f"machinerie par item — journal, reprise, ETA — ne sert qu'aux "
            f"iteratives (§3.5)")

    items, dialecte = lire_items(jeu, pipeline.cles)
    _verifier_coherence(pipeline, items)

    run_id = uuid.uuid4().hex[:16]
    chemin_journal = Path(journal)
    deja = 0

    if mode == REPRISE:
        reprise = preparer(chemin_journal, [i.item_id for i in items],
                           pipeline_empreinte=pipeline.empreinte,
                           jeu_empreinte=empreinte_jeu(jeu))
        restants = set(reprise.a_traiter)
        items = [i for i in items if i.item_id in restants]
        deja = reprise.deja_faits

    compteurs = {OK: 0, KO: 0, IGNORE: 0, DOUTEUX: 0, "deja_faits": deja}
    diagnostics: dict[str, dict[str, str]] = {}
    perdus: list[Item] = []
    etat, raison = TERMINE, ""
    depart = time.monotonic()

    # `with` seul : `__enter__` appelle deja `ouvrir`, et l'appeler en plus
    # ouvrait un second descripteur en abandonnant le premier.
    with Ecrivain(chemin_journal, horloge=horloge) as ecrivain:
        adapter = Adaptateur(ecrivain.ecrire, run_id, dossier_dumps)
        garde = DriverGarde(brut, registre or Registre.charger(), mode=mode,
                            plafond_sauvegardes=pipeline.plafond_sauvegardes,
                            noter=adapter)
        poste = Poste(garde)

        ecrivain.ecrire(ExecutionDebut(
            run_id=run_id, mode=mode, classe=pipeline.classe,
            pipeline=pipeline.nom, pipeline_empreinte=pipeline.empreinte,
            jeu=str(jeu), jeu_empreinte=empreinte_jeu(jeu),
            systeme=systeme, mandant=mandant, utilisateur=utilisateur,
            plafond_items=pipeline.plafond_items,
            derogations=[{"etape": e.nom, "garde": d.garde, "motif": d.motif}
                         for e in pipeline.etapes for d in e.derogations]))

        for rang, item in enumerate(items, start=1):
            if rang > pipeline.plafond_items:
                etat = PLAFOND
                raison = (f"plafond de {pipeline.plafond_items} item(s) "
                          f"atteint")
                break

            adapter.item_id = item.item_id
            ecrivain.ecrire(ItemDebut(run_id=run_id, item_id=item.item_id,
                                      index=item.index, cle=dict(item.cle),
                                      brut=[dict(l) for l in item.brut]))
            debut = time.monotonic()
            try:
                _jouer_item(pipeline, item, garde, poste,
                            registre or Registre.charger(), adapter)
            except RefusDryRun as erreur:
                _clore(ecrivain, run_id, item, IGNORE, debut, garde, compteurs)
                _diagnostiquer(diagnostics, perdus, item, "dry-run", erreur)
                continue
            except ItemAbandonne as erreur:
                # Regle 1 : le lot continue.
                _clore(ecrivain, run_id, item, KO, debut, garde, compteurs,
                       str(erreur))
                _diagnostiquer(diagnostics, perdus, item, "item", erreur)
                continue
            except (ArretBloquant, PlafondAtteint) as erreur:
                # Regle 3 : PAS de fin d'item. Il reste ouvert, et le repli
                # decidera s'il est rejouable ou douteux.
                etat = PLAFOND if isinstance(erreur, PlafondAtteint) \
                    else INTERROMPU
                raison = str(erreur)
                _diagnostiquer(diagnostics, perdus, item, "arret", erreur)
                break

            _clore(ecrivain, run_id, item, OK, debut, garde, compteurs)
            if observateur is not None:
                # Le moteur emet des FAITS. L'estimation et le rendu sont
                # ailleurs : il ne sait pas s'il parle a un terminal.
                observateur(Progres(
                    item=item.item_id, rang=rang, total=len(items),
                    duree_ms=int((time.monotonic() - debut) * 1000),
                    compteurs=dict(compteurs)))

        ecrivain.ecrire(ExecutionFin(
            run_id=run_id, etat=etat, raison=raison, compteurs=dict(compteurs),
            duree_ms=int((time.monotonic() - depart) * 1000)))

    chemin_ko = None
    if sortie_ko is not None and perdus:
        chemin_ko = str(ecrire_items(sortie_ko, perdus, dialecte, diagnostics))

    return Resultat(run_id=run_id, etat=etat, compteurs=compteurs,
                    raison=raison, journal=str(chemin_journal), ko=chemin_ko,
                    duree_ms=int((time.monotonic() - depart) * 1000))


def _clore(ecrivain: Ecrivain, run_id: str, item: Item, etat: str,
           debut: float, garde: DriverGarde, compteurs: dict[str, int],
           incident: str | None = None) -> None:
    ecrivain.ecrire(ItemFin(
        run_id=run_id, item_id=item.item_id, etat=etat,
        duree_ms=int((time.monotonic() - debut) * 1000),
        sauvegardes=garde.sauvegardes, incident=incident))
    compteurs[etat] = compteurs.get(etat, 0) + 1


def _diagnostiquer(diagnostics: dict[str, dict[str, str]], perdus: list[Item],
                   item: Item, quoi: str, erreur: Exception) -> None:
    """Prepare le reexport de l'item au format d'entree (§4.7).

    Les colonnes portent le prefixe `falcon_`, que la lecture retire : le
    fichier est enrichi pour l'humain ET reinjectable sans retouche.
    """
    perdus.append(item)
    diagnostics[item.item_id] = {
        "falcon_categorie": quoi,
        "falcon_message": str(erreur),
    }
