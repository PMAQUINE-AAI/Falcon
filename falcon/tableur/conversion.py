"""Assembler les trois CSV, emettre, RELIRE, puis ecrire — dans cet ordre.

L'ordre est la garantie principale de ce module, et il tient en une phrase :
**rien n'est ecrit sur le disque avant d'avoir ete recharge par `charger()`.**

Un YAML casse a cote d'un YAML valide plus ancien, c'est le mauvais fichier
lance un jour de fatigue. Et comme la conversion est un geste qu'on repete —
on corrige une cellule, on reconvertit — le repertoire de sortie accumulerait
les demi-fichiers.

Ce module ne construit jamais de `Pipeline` lui-meme. Il produit du TEXTE et
laisse `charger()` decider. C'est ce qui garantit qu'il n'ouvre pas un second
chemin de validation a cote du premier : tout ce que le chargeur refuse est
refuse ici, sans avoir a etre redit — et sans risquer de diverger le jour ou
une regle change d'un cote seulement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from falcon.noyau import DEROGEABLES, MOTIF_MINIMAL, PORTEE_TOTALE

from .emission import rendre
from .lecture import (
    COLONNES_DEROGATIONS, COLONNES_ETAPES, COLONNES_PIPELINE, Feuille, Ligne,
    TableurInvalide, lire_ecran, lire_feuille, lire_liste, valeur_sap,
    verifier_rangs,
)

#: Les trois fichiers que le classeur produit.
CSV_PIPELINE = "pipeline.csv"
CSV_ETAPES = "etapes.csv"
CSV_DEROGATIONS = "derogations.csv"

#: Proprietes attendues dans `pipeline.csv`, et lesquelles sont des entiers.
PROPRIETES = ("nom", "classe", "cles", "plafond_items", "plafond_sauvegardes")
PROPRIETES_ENTIERES = ("plafond_items", "plafond_sauvegardes")

#: Genres de source, tels qu'ils s'ecrivent dans la colonne `source_genre`.
#: Vide = pas de source, ce que les actions sans valeur exigent.
GENRES = ("colonne", "constante", "lue", "gabarit")


def _proprietes(chemin: Path) -> dict[str, Any]:
    """`pipeline.csv` : deux colonnes, `propriete` et `valeur`."""
    feuille = lire_feuille(chemin, COLONNES_PIPELINE)
    brutes: dict[str, tuple[str, Ligne]] = {}
    for ligne in feuille.lignes:
        nom = ligne.brute("propriete")
        if nom not in PROPRIETES:
            raise feuille.situer(
                ligne, f"propriete {nom!r} inconnue. Attendues : "
                       f"{list(PROPRIETES)}")
        if nom in brutes:
            # Meme refus que pour une clef YAML dupliquee, et pour la meme
            # raison : la derniere gagnerait, et un plafond recopie de travers
            # multiplierait le rayon d'action sans un mot.
            raise feuille.situer(
                ligne, f"propriete {nom!r} declaree deux fois. La seconde "
                       f"l'emporterait en silence")
        brutes[nom] = (ligne.brute("valeur"), ligne)

    manquantes = [p for p in PROPRIETES
                  if p not in brutes and p != "cles"]
    if manquantes:
        raise TableurInvalide(
            f"{chemin} : propriete(s) manquante(s) {manquantes}")

    proprietes: dict[str, Any] = {"version": 1}
    for nom, (valeur, ligne) in brutes.items():
        if nom in PROPRIETES_ENTIERES:
            try:
                proprietes[nom] = int(valeur)
            except ValueError:
                raise feuille.situer(
                    ligne, f"`{nom}` : « {valeur} » n'est pas un entier. "
                           f"C'est le rayon d'action du lot, et il est "
                           f"obligatoire") from None
        elif nom == "cles":
            proprietes["cles"] = lire_liste(valeur)
        else:
            proprietes[nom] = valeur
    return proprietes


def _source(ligne: Ligne, feuille: Feuille) -> dict[str, str] | None:
    """`source_genre` + `source_valeur`, ou rien.

    Deux colonnes plutot qu'une cellule `colonne: site` : le classeur peut
    alors proposer le genre dans une liste deroulante, et la valeur reste une
    cellule ou l'on colle un nom de colonne pris dans le dictionnaire.
    """
    genre = ligne.brute("source_genre")
    brute = ligne.brute("source_valeur")
    if not genre:
        if brute:
            raise feuille.situer(
                ligne, f"`source_valeur` vaut « {brute} » sans "
                       f"`source_genre`. La valeur serait ignoree")
        return None
    if genre not in GENRES:
        raise feuille.situer(
            ligne, f"`source_genre` {genre!r} inconnu. Attendus : "
                   f"{list(GENRES)}")

    # Une CONSTANTE part telle quelle dans SAP : elle exige les crochets. Un
    # nom de colonne, un nom d'etape `lire` ou un gabarit sont des references
    # internes, jamais tapees — les encadrer ferait chercher une colonne
    # nommee « [site] ».
    valeur = (valeur_sap(brute, "`source_valeur`", feuille, ligne)
              if genre == "constante" else brute)
    if genre != "constante" and not valeur:
        raise feuille.situer(
            ligne, f"`source_valeur` est vide pour un genre {genre!r}")
    return {genre: valeur}


def _format(ligne: Ligne, feuille: Feuille) -> list[Any]:
    """`majuscules, zeros:12` — noms separes par des virgules.

    Les transformations elles-memes ne sont PAS validees ici : `charger()`
    appelle `lire_transformation`, qui porte deja la liste fermee et son
    message d'aide. Redire la regle ici la ferait exister a deux endroits, et
    diverger le jour ou une transformation s'ajoute.
    """
    entrees: list[Any] = []
    for morceau in lire_liste(ligne.brute("format")):
        if ":" not in morceau:
            entrees.append(morceau)
            continue
        nom, _, argument = morceau.partition(":")
        argument = argument.strip()
        try:
            entrees.append({nom.strip(): int(argument)})
        except ValueError:
            raise feuille.situer(
                ligne, f"`format` : « {morceau} » — l'argument d'une "
                       f"transformation est un ENTIER, la largeur du champ "
                       f"SAP") from None
    return entrees


def _etape(ligne: Ligne, feuille: Feuille) -> dict[str, Any]:
    etape: dict[str, Any] = {
        "nom": ligne.brute("nom"),
        "action": ligne.brute("action"),
    }
    if ligne.brute("cible"):
        etape["cible"] = ligne.brute("cible")

    source = _source(ligne, feuille)
    if source is not None:
        etape["source"] = source

    formats = _format(ligne, feuille)
    if formats:
        etape["format"] = formats

    # `defaut` part dans SAP : crochets exiges, et `[]` reste distinct de
    # « pas de defaut ». C'est la difference entre « si la case est vide, vide
    # le champ » et « si la case est vide, ne fais rien de particulier ».
    if ligne.brute("defaut"):
        etape["defaut"] = valeur_sap(ligne.brute("defaut"), "`defaut`",
                                     feuille, ligne)

    ecran = lire_ecran(ligne.brute("ecran"), feuille, ligne)
    if ecran is None:
        etape["navigation_libre"] = True
    else:
        etape["ecran"] = ecran

    fenetres = lire_liste(ligne.brute("fenetres"))
    if fenetres:
        etape["fenetres"] = fenetres

    # Le statut attendu est un type de message SAP — « S », « W ». Il est
    # compare a ce que SAP rend, donc il part sous forme de texte et subit le
    # meme risque de retypage qu'une valeur : crochets.
    if ligne.brute("statut_attendu"):
        etape["statut_attendu"] = valeur_sap(
            ligne.brute("statut_attendu"), "`statut_attendu`", feuille, ligne)

    sauvegarde = ligne.brute("sauvegarde").lower()
    if sauvegarde:
        if sauvegarde not in ("oui", "non"):
            raise feuille.situer(
                ligne, f"`sauvegarde` : « {ligne.brute('sauvegarde')} » — "
                       f"attendu « oui » ou « non ». Le VRAI/FAUX d'Excel est "
                       f"localise et ne se relit pas d'une machine a l'autre")
        etape["sauvegarde"] = sauvegarde == "oui"

    if ligne.brute("comparaison"):
        etape["comparaison"] = ligne.brute("comparaison")
    if ligne.brute("fonction"):
        etape["fonction"] = ligne.brute("fonction")
    return etape


def _derogations(chemin: Path, noms: list[str]) -> dict[str, list[dict[str, str]]]:
    """`derogations.csv`, rattachees a leur etape.

    Le refus que ce module est SEUL a pouvoir poser : une `portee` qui designe
    une etape inconnue. Le chargeur ne verifie que le prefixe `etape:`, si bien
    qu'une faute de frappe donne aujourd'hui une derogation acceptee QUI NE
    COUVRE RIEN — la garde reste armee, l'utilisateur croit l'avoir relachee,
    et le lot tombe a l'endroit meme ou il pensait etre passe.
    """
    par_etape: dict[str, list[dict[str, str]]] = {}
    if not Path(chemin).is_file():
        return par_etape          # aucune derogation : le cas nominal

    feuille = lire_feuille(chemin, COLONNES_DEROGATIONS)
    for ligne in feuille.lignes:
        etape = ligne.brute("etape")
        if etape not in noms:
            raise feuille.situer(
                ligne,
                f"`etape` {etape!r} : aucune etape de ce nom. Etapes "
                f"declarees : {noms}. Une derogation orpheline serait "
                f"acceptee et ne couvrirait RIEN — la garde resterait armee, "
                f"et le lot tomberait la ou tu le crois passe")

        garde = ligne.brute("garde")
        if garde not in DEROGEABLES:
            raise feuille.situer(
                ligne, f"`garde` {garde!r} : derogeables {sorted(DEROGEABLES)}")

        motif = ligne.brute("motif")
        if len(motif) < MOTIF_MINIMAL:
            raise feuille.situer(
                ligne,
                f"`motif` de {len(motif)} caracteres, {MOTIF_MINIMAL} minimum. "
                f"Une derogation non expliquee est une garde desactivee en "
                f"douce")

        portee = ligne.brute("portee") or f"etape:{etape}"
        if portee != PORTEE_TOTALE and not portee.startswith("etape:"):
            raise feuille.situer(
                ligne, f"`portee` {portee!r} : attendu {PORTEE_TOTALE!r} ou "
                       f"« etape:<nom> »")
        if portee.startswith("etape:") and portee[len("etape:"):] != etape:
            vise = portee[len("etape:"):]
            raison = ("une etape inconnue" if vise not in noms
                      else f"l'etape {vise!r}, pas {etape!r}")
            raise feuille.situer(
                ligne,
                f"`portee` {portee!r} designe {raison}. Une derogation ne peut "
                f"porter que sur SON etape ou sur {PORTEE_TOTALE!r} : visant "
                f"une autre, elle ne couvrirait rien — la garde resterait "
                f"armee, et le journal annoncerait pourtant « derogee »")

        par_etape.setdefault(etape, []).append(
            {"garde": garde, "portee": portee, "motif": motif})
    return par_etape


def convertir(dossier: str | Path) -> str:
    """Les trois CSV d'un dossier, en TEXTE YAML. N'ecrit rien.

    Rendre du texte plutot qu'un chemin est ce qui permet a
    `convertir_fichiers` de relire avant d'ecrire — et a un appelant qui veut
    seulement voir le resultat de ne pas salir un repertoire.
    """
    dossier = Path(dossier)
    pipeline = _proprietes(dossier / CSV_PIPELINE)

    feuille = lire_feuille(dossier / CSV_ETAPES, COLONNES_ETAPES)
    if not feuille.lignes:
        raise TableurInvalide(
            f"{dossier / CSV_ETAPES} ne porte aucune etape. Une pipeline sans "
            f"etape se charge et ne fait rien")
    verifier_rangs(feuille)

    etapes = [_etape(ligne, feuille) for ligne in feuille.lignes]
    noms = [e["nom"] for e in etapes]
    par_etape = _derogations(dossier / CSV_DEROGATIONS, noms)
    for etape in etapes:
        if etape["nom"] in par_etape:
            etape["derogations"] = par_etape[etape["nom"]]

    pipeline["etapes"] = etapes
    return rendre(pipeline)


def convertir_fichiers(dossier: str | Path, sortie: str | Path) -> Path:
    """Convertit, RELIT, puis ecrit. Jamais dans un autre ordre.

    La relecture passe par `charger()`, le seul chemin de validation du depot.
    Tout ce qu'il refuse est donc refuse ici — mais le message parlerait d'un
    YAML que l'utilisateur du classeur n'a pas ecrit, donc on le lui rend en
    disant d'ou il vient et en lui montrant le texte produit.
    """
    from falcon.pipeline import PipelineInvalide, charger

    texte = convertir(dossier)
    sortie = Path(sortie)

    # On relit depuis un fichier TEMPORAIRE, a cote de la sortie : `charger()`
    # lit un chemin, et l'empreinte se calcule sur le texte integral — donc le
    # texte relu doit etre exactement celui qu'on ecrira, aux octets pres.
    provisoire = sortie.with_name(sortie.name + ".relecture")
    provisoire.parent.mkdir(parents=True, exist_ok=True)
    provisoire.write_text(texte, encoding="utf-8", newline="\n")
    try:
        charger(provisoire)
    except PipelineInvalide as erreur:
        # Le message du chargeur, mais situe : sans ca, il envoie corriger un
        # fichier qui n'existe pas encore et que personne n'a ecrit a la main.
        detail = str(erreur).replace(str(provisoire), "le YAML produit")
        raise TableurInvalide(
            f"les CSV de {dossier} produisent un YAML que FALCON refuse, "
            f"donc RIEN n'a ete ecrit :\n\n  {detail}\n\n"
            f"Le YAML produit, pour situer :\n\n"
            + "\n".join(f"  {l}" for l in texte.splitlines())) from None
    finally:
        provisoire.unlink(missing_ok=True)

    sortie.write_text(texte, encoding="utf-8", newline="\n")
    return sortie
