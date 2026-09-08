"""Emettre le texte YAML. Deterministe a l'octet.

**Pourquoi l'octet, et pas « un YAML equivalent ».** L'empreinte d'une pipeline
est un `sha256` de son TEXTE INTEGRAL, et c'est sur elle que la garde de
reprise verifie que le monde n'a pas change. Deux conversions du meme CSV qui
differeraient d'une espace donneraient deux empreintes, donc une reprise
refusee sur une pipeline pourtant identique — et l'utilisateur apprendrait a
passer outre avec `forcer`, ce qui desarmerait la garde pour de bon.

D'ou : ordre des clefs fixe, toutes les chaines entre guillemets, `\\n`
litteraux, pas de BOM, et surtout RIEN qui ne vienne du CSV. Pas
d'horodatage, pas de chemin source, pas de numero de version de FALCON — trois
choses qu'il serait naturel de mettre en en-tete et qui feraient changer
l'empreinte a chaque conversion.

On n'emploie pas `yaml.dump` : il ordonne, replie et cite selon des reglages
qui evoluent d'une version de PyYAML a l'autre. Le format de sortie de FALCON
ne peut pas dependre de la version d'une bibliotheque installee sur le poste.
"""

from __future__ import annotations

from typing import Any

from falcon.noyau.yaml_strict import citer as _citer

#: L'ordre des clefs d'une etape. Fixe, et lisible : ce qu'on fait, sur quoi,
#: avec quelle valeur, puis ce que les gardes verront.
ORDRE_ETAPE = (
    "nom", "action", "cible", "source", "format", "defaut", "ecran",
    "navigation_libre", "fenetres", "statut_attendu", "sauvegarde",
    "comparaison", "fonction", "derogations",
)


#: Le quoteur vit dans `noyau/yaml_strict` : c'est le module de la surete
#: YAML, et `taxonomie/recolte` en a besoin aussi. En garder une copie ici
#: garantissait qu'une des deux se perime — celle-ci n'echappait pas U+0085,
#: que PyYAML replie en ESPACE a l'interieur d'un scalaire entre guillemets.
citer = _citer


def _scalaire(valeur: Any) -> str:
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    if isinstance(valeur, int):
        return str(valeur)
    return citer(valeur)


def _en_ligne(valeur: dict[str, Any]) -> str:
    """Un mapping court, sur une ligne : `{colonne: "site"}`."""
    corps = ", ".join(f"{c}: {_scalaire(v)}" for c, v in valeur.items())
    return "{" + corps + "}"


def _liste_en_ligne(valeurs: list[Any]) -> str:
    return "[" + ", ".join(
        _en_ligne(v) if isinstance(v, dict) else _scalaire(v)
        for v in valeurs) + "]"


def rendre_etape(etape: dict[str, Any]) -> list[str]:
    """Une etape, en lignes. Les clefs absentes ne sont pas emises."""
    lignes: list[str] = []
    for clef in ORDRE_ETAPE:
        if clef not in etape:
            continue
        valeur = etape[clef]
        prefixe = "  - " if not lignes else "    "

        if clef == "derogations":
            lignes.append(f"{prefixe}derogations:")
            for derogation in valeur:
                lignes.append(f"      - garde: {citer(derogation['garde'])}")
                lignes.append(f"        portee: {citer(derogation['portee'])}")
                lignes.append(f"        motif: {citer(derogation['motif'])}")
            continue

        if isinstance(valeur, dict):
            lignes.append(f"{prefixe}{clef}: {_en_ligne(valeur)}")
        elif isinstance(valeur, list):
            lignes.append(f"{prefixe}{clef}: {_liste_en_ligne(valeur)}")
        else:
            lignes.append(f"{prefixe}{clef}: {_scalaire(valeur)}")
    return lignes


def rendre(pipeline: dict[str, Any]) -> str:
    """Le YAML complet, en texte.

    Aucun commentaire d'en-tete, et c'est delibere : un commentaire qui
    nommerait le CSV d'origine ou la date de conversion entrerait dans
    l'empreinte, qu'il ferait changer a chaque conversion.
    """
    lignes = [
        f"version: {pipeline['version']}",
        f"nom: {citer(pipeline['nom'])}",
        f"classe: {citer(pipeline['classe'])}",
    ]
    if pipeline.get("cles"):
        lignes.append(f"cles: {_liste_en_ligne(list(pipeline['cles']))}")
    lignes += [
        f"plafond_items: {pipeline['plafond_items']}",
        f"plafond_sauvegardes: {pipeline['plafond_sauvegardes']}",
        "etapes:",
    ]
    for etape in pipeline["etapes"]:
        lignes.extend(rendre_etape(etape))
    return "\n".join(lignes) + "\n"
