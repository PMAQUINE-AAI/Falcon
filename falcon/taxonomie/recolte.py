"""D'un inconnu bloquant a l'entree de registre qui le classera.

**Le trou que ce module bouche.** L'en-tete du registre dit que la taxonomie
« se recolte et ne se specifie pas » : une entree s'ajoute APRES avoir observe
la signature, depuis le dump que l'incident inconnu a produit. Le mecanisme de
recolte etait cependant inatteignable de bout en bout — le dump n'etait ecrit
que si un appelant fournissait `dossier_dumps`, ce qu'aucun appelant de
production ne faisait, et rien ne transformait un dump en entree.

Consequence sur un systeme reel : tout incident non apparie est `inconnue`,
donc bloquant, et la garde de statut y route tout message `E`/`A`. Le premier
message d'erreur metier arrete donc le lot entier — c'est le comportement
voulu — mais ne laissait aucune sortie, sinon relancer a l'aveugle.

**Ce que ce module fait, et ce qu'il ne fait pas.**

Il PROPOSE le squelette d'une entree, rempli avec ce qui a ete reellement
observe. Il ne DECIDE pas : `categorie` et `politique` restent a completer a la
main, et la `justification` est un marqueur. C'est deliberé et ce n'est pas de
la prudence de facade — decider a la place de l'utilisateur qu'un message est
benin, c'est ecrire une regle de securite a partir d'une seule observation.
`origine: falcon_observe` dit d'ou vient l'entree.

Le marqueur `A COMPLETER` est ce qui empeche une proposition d'etre collee
sans etre lue : `_exiger_texte` accepterait n'importe quel texte, mais un
humain qui relit voit ce qui manque, et c'est exactement le point.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Ce qu'une entree proposee porte en clair a la place d'une decision.
MARQUEUR = "A COMPLETER"


@dataclass(frozen=True)
class Inconnu:
    """Un dump relu, sous la forme dont on tire une entree."""

    chemin: Path
    horodatage: str
    run_id: str
    item_id: str
    garde: str
    detail: dict[str, Any]

    #: La signature TELLE QU'ELLE A ETE SOUMISE au registre.
    #:
    #: C'est la piece maitresse, et elle a manque. Sans elle, il fallait
    #: reconstruire la signature depuis `detail` — une conjecture, et une
    #: conjecture fausse : `garde` porte le NOM de la garde qui a parle, pas
    #: le canal. Un message `E` sans `statut_attendu` etait donc propose sur
    #: le canal `garde` alors que le registre l'avait classe sur le canal
    #: `statut`, et l'entree ecrite d'apres cette proposition n'aurait
    #: JAMAIS apparie. Le defaut a ete trouve en deroulant le parcours
    #: complet contre le double ; aucune relecture ne l'aurait montre.
    signature: dict[str, Any] | None = None

    @property
    def statut(self) -> dict[str, str]:
        """Le message SAP, quand l'incident en portait un."""
        if self.signature:
            return {c: str(self.signature.get(c) or "")
                    for c in ("type", "id", "numero", "texte")}
        brut = self.detail.get("statut")
        return {k: str(v) for k, v in brut.items()} if isinstance(brut, dict) else {}

    @property
    def canal(self) -> str:
        """Le canal de l'entree a ecrire — LU, jamais devine.

        Un dump ecrit par une version anterieure ne porte pas de signature ;
        on retombe alors sur une lecture du detail, en le disant.
        """
        if self.signature and self.signature.get("canal"):
            return str(self.signature["canal"])
        # Sans signature — un dump ecrit par une version anterieure — on
        # DEDUIT, et on ne peut pas faire mieux : le champ `garde` du dump
        # porte le nom de la garde, qui vaut le canal pour `com` et `python`
        # mais pas pour les autres.
        if self.garde in ("com", "python"):
            return self.garde
        if self.detail.get("exception"):
            return "com"
        return "statut" if not self.garde else "garde"

    @property
    def correspondance(self) -> dict[str, Any]:
        """Ce sur quoi la future entree apparierait, et RIEN de plus.

        On ne recopie pas tout le detail. Une correspondance trop large
        n'apparie plus rien ; une correspondance qui embarque une valeur
        d'item — un numero d'equipement, un site — n'apparierait que cet
        item-la. Les deux produisent une entree qui a l'air ecrite et qui ne
        sert jamais, ce qui est pire que pas d'entree du tout.

        `etape` est volontairement ecartee : elle lierait l'entree au nom
        d'une etape d'une pipeline, alors que la meme erreur SAP se produira
        sous un autre nom dans la pipeline d'a cote.
        """
        statut = self.statut
        signature = self.signature or {}
        # `com` ET `python` apparient sur le nom d'exception — c'est ce que
        # `_apparie` fait pour les deux. Les traiter separement produisait,
        # pour une `action: python` qui leve, une correspondance batie sur
        # `garde`, que le comparateur ne regarde jamais sur ce canal.
        if self.canal in ("com", "python"):
            return {"exception": str(signature.get("exception")
                                     or self.detail.get("exception") or "")}

        if self.canal == "statut":
            propose: dict[str, Any] = {"id": statut.get("id", ""),
                                       "numero": statut.get("numero", "")}
            if statut.get("type"):
                propose["type"] = statut["type"]
            return propose

        propose = {"garde": str(signature.get("garde") or self.garde)}
        for cle in ("attendu", "observe"):
            valeur = signature.get(cle, self.detail.get(cle))
            if valeur is not None:
                propose[cle] = str(valeur)
        # L'identite du message, quand la garde en a rattrape un. Le
        # comparateur la lit — « sans elle, une entree d'ecart apparierait
        # indifferemment tous les messages produisant le meme ecart ».
        if statut.get("id"):
            propose["id"] = statut["id"]
        if statut.get("numero"):
            propose["numero"] = statut["numero"]
        return propose

    @property
    def nom_propose(self) -> str:
        """Un nom lisible, tire de la signature — jamais de l'item.

        Un nom qui porterait le site ou l'equipement ferait une entree par
        item ; un nom qui ne porterait que la garde ferait une entree pour
        toutes les erreurs du monde, et le registre refuse deux entrees
        appariant la meme chose. Celui-ci porte ce qui se repetera : la garde
        ET le message.
        """
        statut = self.statut
        signature = self.signature or {}
        garde = str(signature.get("garde") or self.garde)
        morceaux = [garde] if garde else []
        if statut.get("id") or statut.get("numero"):
            morceaux += [statut.get("id", ""), statut.get("numero", "")]
        elif signature.get("exception") or self.detail.get("exception"):
            morceaux.append(str(signature.get("exception")
                                or self.detail["exception"]))
        # Sur `com` et `python`, le nom de la garde ne dit rien d'utile — il
        # vaut le canal. C'est l'exception qui nomme l'entree.
        if self.canal in ("com", "python") and len(morceaux) > 1:
            morceaux = morceaux[1:]
        elif self.detail.get("observe"):
            morceaux.append(f"observe_{self.detail['observe']}")
        brut = "_".join(m for m in morceaux if m)
        propre = "".join(c if c.isalnum() else "_" for c in brut.lower())
        return "_".join(filter(None, propre.split("_"))) or "a_nommer"

    @property
    def contexte(self) -> dict[str, str]:
        """Le triplet d'ecran, quand la signature le portait."""
        brut = (self.signature or {}).get("contexte")
        return ({k: str(v) for k, v in brut.items()}
                if isinstance(brut, dict) else {})

    @property
    def texte_du_message(self) -> str:
        """Le libelle SAP, pour la justification. Jamais dans l'appariement.

        Un libelle porte souvent la valeur de l'item — « Equipement 10023456
        inexistant » — et apparier dessus ferait une entree par item.
        """
        return self.statut.get("texte", "")


def lire_dump(chemin: str | Path) -> Inconnu:
    """Relit un dump ecrit par `ecrire_dump`."""
    chemin = Path(chemin)
    charge = json.loads(chemin.read_text(encoding="utf-8"))
    detail = charge.get("detail")
    return Inconnu(
        chemin=chemin,
        horodatage=str(charge.get("horodatage") or ""),
        run_id=str(charge.get("run_id") or ""),
        item_id=str(charge.get("item_id") or ""),
        garde=str(charge.get("garde") or ""),
        signature=(charge.get("signature")
                   if isinstance(charge.get("signature"), dict) else None),
        detail=detail if isinstance(detail, dict) else {})


def dumps_de(dossier: str | Path) -> list[Path]:
    """Les dumps d'un dossier, du plus recent au plus ancien.

    Le nom porte l'horodatage en tete, donc l'ordre alphabetique inverse est
    l'ordre chronologique inverse — pas besoin de lire les fichiers pour les
    classer, ni de se fier a une date de systeme de fichiers qu'une copie
    modifie.
    """
    dossier = Path(dossier)
    if not dossier.is_dir():
        return []
    return sorted(dossier.glob("*.json"), reverse=True)


def _valeur_yaml(valeur: Any) -> str:
    """Toujours entre guillemets. C'est le sujet meme de `yaml_strict`.

    Un numero de message `010` sans guillemets se relit 8, un `id` valant `on`
    se relit `True` : une proposition qui se colle dans un fichier doit etre
    ecrite comme ce fichier doit etre ecrit.
    """
    texte = str(valeur).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{texte}"'


def entree_proposee(inconnu: Inconnu) -> str:
    """Le bloc YAML a coller dans une surcouche de registre.

    Ce qui est OBSERVE est rempli ; ce qui se DECIDE porte le marqueur. Un
    utilisateur qui colle sans lire obtient un fichier qui refuse de charger
    plutot qu'une regle de securite ecrite au hasard — c'est le meme choix que
    partout ailleurs dans ce projet.
    """
    lignes = [
        f"  - nom: {inconnu.nom_propose}",
        f"    categorie: {MARQUEUR}"
        f"        # connue_benigne | connue_fautive",
        f"    canal: {inconnu.canal}",
        "    correspondance:",
    ]
    for cle, valeur in inconnu.correspondance.items():
        lignes.append(f"      {cle}: {_valeur_yaml(valeur)}")

    # Le contexte d'ecran, PROPOSE mais COMMENTE. Le registre s'en sert — « une
    # meme erreur peut etre benigne sur un ecran et fautive sur un autre » —
    # mais l'activer restreint l'entree a cet ecran-la, et c'est un choix qui
    # depend de ce qu'on sait du message. L'offrir sans le prendre.
    if inconnu.contexte:
        lignes.append("      # Decommente pour restreindre a CET ecran :")
        lignes.append("      # contexte:")
        for cle, valeur in sorted(inconnu.contexte.items()):
            lignes.append(f"      #   {cle}: {_valeur_yaml(valeur)}")
    lignes += [
        "    politique:",
        f"      poursuivre: {MARQUEUR}   # true : le lot continue",
        # DEUX valeurs, pas trois. `politique.appliquer` ne compare qu'a
        # « ko » : « ignore » n'avait aucun effet distinct, et l'annoncer
        # etait une declaration qui n'arme rien — la classe de defaut que ce
        # projet traque, sous forme de commentaire d'aide.
        f"      item: {MARQUEUR}         # ko abandonne l'item, ok le laisse "
        f"continuer",
        "    origine: falcon_observe",
    ]
    if inconnu.horodatage:
        lignes.append(f"    rencontree_le: {_valeur_yaml(inconnu.horodatage[:10])}")
    lignes.append("    justification: >")
    if inconnu.texte_du_message:
        # Le libelle observe, en clair, parce qu'il est ce qui permet de
        # DECIDER — et en commentaire de justification, jamais dans
        # l'appariement : un libelle porte souvent la valeur de l'item.
        lignes.append(f"      SAP a repondu : « {inconnu.texte_du_message} ».")
    lignes += [
        f"      {MARQUEUR} — pourquoi cette categorie et cette politique.",
        "      Une entree sans justification lisible est une regle de securite",
        "      que personne ne pourra reexaminer.",
    ]
    return "\n".join(lignes)


def surcouche_proposee(inconnus: list[Inconnu]) -> str:
    """Un fichier de surcouche complet, pret a etre enregistre puis complete."""
    entete = [
        "# Surcouche de registre proposee par FALCON.",
        "#",
        "# Chaque entree vient d'un incident REELLEMENT observe, dont le dump",
        "# est nomme en commentaire. Rien n'a ete devine : ce qui se decide",
        f"# porte le marqueur {MARQUEUR}, et le fichier refuse de charger tant",
        "# qu'il en reste un.",
        "#",
        "# Une surcouche ENRICHIT le registre livre : elle ne peut ni en",
        "# retirer une entree, ni en assouplir une.",
        "",
        "version: 1",
        "",
        "entrees:",
    ]
    corps: list[str] = []
    for inconnu in inconnus:
        corps.append("")
        corps.append(f"  # {inconnu.chemin.name}")
        corps.append(entree_proposee(inconnu))
    return "\n".join(entete + corps) + "\n"
