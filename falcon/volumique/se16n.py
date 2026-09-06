"""La primitive d'export de table (§3.6).

Le §3.6 fait de l'export une primitive de premier niveau, pas une pipeline
generique a recartographier a chaque fois : « ni catalogue d'ecrans, ni trace
enregistree, ni gardes completes ne sont necessaires ici ».

Cette phrase dit ce qui n'est pas necessaire ; elle ne dit pas d'ou viennent
les identifiants de champ. **Ils viennent d'une carte relevee**, et tant
qu'elle est vide, cette fonction refuse de tourner. Voir `carte.py`.

**Ce que le volumique n'a pas** (§3.5) : ni journal par item, ni reprise fine,
ni ETA. Une navigation, une lecture, un fichier. La machinerie lourde ne sert
qu'aux remediations, et une volumique qui en heriterait serait une confusion
de modele avant d'etre du gaspillage.

**Ce qu'il a quand meme : les gardes.** Elles ne coutent rien ici et attrapent
exactement ce qu'il faut — un ecran qui n'est pas celui qu'on croit, une
popup d'autorisation, un message d'erreur. Un export fait sur le mauvais
ecran rendrait des lignes qui ont l'air de lignes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Sequence

from falcon.controleur import Contrat, DriverGarde, Poste
from falcon.noyau import CHAMP_DE_COMMANDE, Horloge, maintenant
from falcon.taxonomie import Registre

from .carte import Carte, charger_carte
from .export import Export, Provenance

if TYPE_CHECKING:                       # annotation seule
    from falcon.couture import Driver

#: Code transaction de la primitive.
TRANSACTION = "SE16N"

#: Plafond de sauvegardes d'un export : ZERO tolere.
#:
#: Un export LIT. S'il declenchait une sauvegarde, ce serait qu'il n'est pas
#: sur l'ecran qu'on croit — et le plafond a 1 le laisserait en faire une.
PLAFOND_SAUVEGARDES = 1


def _naviguer(poste: Poste, garde: DriverGarde, carte: Carte,
              table: str) -> None:
    """Ouvre `SE16N` sur la table demandee."""
    with garde.sous_contrat(Contrat(nom="(ouvrir SE16N)",
                                    navigation_libre=True)):
        poste.write(CHAMP_DE_COMMANDE, f"/n{TRANSACTION}")
        poste.vkey(0)

    with garde.sous_contrat(Contrat(nom="saisir la table",
                                    ecran_attendu=carte.ecran_selection)):
        poste.write(carte.champ_table, table)


def _filtrer(poste: Poste, garde: DriverGarde, carte: Carte,
             criteres: Mapping[str, str]) -> None:
    with garde.sous_contrat(Contrat(nom="poser les criteres",
                                    ecran_attendu=carte.ecran_selection)):
        for nom, valeur in criteres.items():
            # `champ_de_critere` refuse un critere que la carte ne nomme pas :
            # conjecturer sa position, ce serait filtrer sur autre chose.
            poste.write(carte.champ_de_critere(nom), str(valeur))


def _relever(poste: Poste, garde: DriverGarde,
             carte: Carte) -> list[dict[str, Any]]:
    """Lit la grille de resultat, par index ABSOLU et sans defilement."""
    with garde.sous_contrat(Contrat(nom="lire la liste",
                                    ecran_attendu=carte.ecran_resultat)):
        colonnes = poste.grid_columns(carte.grille)
        return [
            {colonne: poste.grid_read(carte.grille, ligne, colonne)
             for colonne in colonnes}
            for ligne in range(poste.grid_rows(carte.grille))
        ]


def exporter_table(brut: "Driver",
                   table: str,
                   *,
                   systeme: str,
                   mandant: str,
                   utilisateur: str,
                   criteres: Mapping[str, str] | None = None,
                   carte: Carte | None = None,
                   registre: Registre | None = None,
                   horloge: Horloge = maintenant) -> Export:
    """Extrait une table et rend un `Export` complet de sa provenance.

    **Refuse de tourner sur une carte incomplete**, avant toute navigation :
    echouer au milieu d'une transaction laisse une session dans un etat que
    personne n'a decrit.
    """
    connue = carte if carte is not None else charger_carte()
    connue.verifier()

    garde = DriverGarde(brut, registre or Registre.charger(),
                        plafond_sauvegardes=PLAFOND_SAUVEGARDES)
    poste = Poste(garde)

    _naviguer(poste, garde, connue, table)
    if criteres:
        _filtrer(poste, garde, connue, criteres)

    with garde.sous_contrat(Contrat(nom="executer",
                                    ecran_attendu=connue.ecran_selection)):
        poste.press(connue.bouton_executer)

    lignes = _relever(poste, garde, connue)

    return Export(
        provenance=Provenance(
            systeme=systeme, mandant=mandant, table=table,
            horodatage=horloge(), utilisateur=utilisateur,
            criteres={str(c): str(v) for c, v in (criteres or {}).items()}),
        lignes=tuple(lignes))
