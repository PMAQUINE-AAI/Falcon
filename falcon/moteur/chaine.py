"""Chaine de pipelines — un declenchement successif, et rien de plus.

Le §3.3 ferme le perimetre volontairement, et chaque limite a sa raison :

- **journal, rapport et fichier de KO par pipeline, jamais fusionnes.** Une
  reprise se fait sur un journal ; fusionner rendrait la reprise fine
  impossible ;
- **aucun passage de donnees entre pipelines.** C'est la limite qui empeche
  la chaine de devenir un orchestrateur. Si une pipeline a besoin de la sortie
  d'une autre, ce n'est pas une chaine : c'est un item composite, et il se
  traite dans une pipeline unique ;
- **un arret bloquant interrompt toute la chaine**, un item KO ne
  l'interrompt pas.

**Le seul geste SAP que le moteur connaisse.** Entre deux pipelines, le §3.3
impose un retour a l'ecran d'accueil. Il passe forcement par le champ de
commande, seul identifiant d'ecran connu de FALCON en dehors du catalogue. Il
est nomme, constant, et remplacable — mais il existe, et le taire serait
pretendre que le moteur ignore SAP alors qu'il en sait exactement une chose.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from falcon.controleur import Contrat, DriverGarde, Poste
from falcon.noyau import CHAMP_DE_COMMANDE, RETOUR_ACCUEIL
from falcon.pipeline import Pipeline
from falcon.taxonomie import Registre

from .boucle import Resultat, executer

if TYPE_CHECKING:                       # annotation seule
    from falcon.couture import Driver


@dataclass(frozen=True)
class Maillon:
    """Une pipeline et son jeu, avec ses fichiers a elle."""

    pipeline: Pipeline
    jeu: str | Path
    journal: str | Path
    sortie_ko: str | Path | None = None


def retour_accueil(brut: "Driver", registre: Registre) -> None:
    """Ramene la session a l'ecran d'accueil entre deux pipelines.

    Passe par un `DriverGarde` en navigation libre : on ne sait pas d'ou l'on
    part — c'est justement le probleme que ce geste resout — mais les gardes
    de fenetre et de statut, elles, s'appliquent.

    LE PLAFOND EST A ZERO. Il etait a 1, et le commentaire disait deja « ce
    geste ne doit jamais sauvegarder quoi que ce soit » : la garde de rayon
    refuse a partir de la N-ieme, donc un plafond a 1 en autorisait une. Taper
    un code transaction dans le champ de commande ne sauvegarde rien ; si SAP
    annonce une sauvegarde ici, c'est qu'on n'est pas ou l'on croit, et c'est
    exactement ce qu'il faut arreter.
    """
    garde = DriverGarde(brut, registre, plafond_sauvegardes=0)
    poste = Poste(garde)
    with garde.sous_contrat(Contrat(nom="(retour accueil)",
                                    navigation_libre=True)):
        poste.write(CHAMP_DE_COMMANDE, RETOUR_ACCUEIL)
        poste.vkey(0)


def enchainer(maillons: list[Maillon],
              brut: "Driver",
              *,
              registre: Registre | None = None,
              accueil: Callable[["Driver", Registre], None] = retour_accueil,
              **options: Any) -> list[Resultat]:
    """Execute les maillons a la suite. Rend un resultat par maillon.

    Rend une LISTE de resultats, pas un resultat agrege : chaque pipeline a
    son journal et son sort. Et rien de ce que rend un maillon n'est passe au
    suivant — un test l'epingle, parce que c'est la limite qui empeche la
    chaine de devenir un orchestrateur.
    """
    connu = registre or Registre.charger()
    rendus: list[Resultat] = []

    for rang, maillon in enumerate(maillons):
        if rang:
            # Entre deux pipelines, jamais avant la premiere : on se greffe
            # sur une session ou l'humain est deja quelque part, et le §3.3 ne
            # demande pas de le deloger.
            accueil(brut, connu)

        resultat = executer(maillon.pipeline, maillon.jeu, brut,
                            journal=maillon.journal, registre=connu,
                            sortie_ko=maillon.sortie_ko, **options)
        rendus.append(resultat)
        if resultat.interrompu:
            # Un arret bloquant dit que le modele du monde est faux. Passer au
            # maillon suivant, c'est ecrire n'importe ou avec entrain.
            break

    return rendus
