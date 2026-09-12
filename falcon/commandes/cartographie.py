"""La cartographie, du fichier de trace au catalogue — l'orchestration.

Ce module est le seul endroit ou la lecture d'une trace, le rejeu et le
versement des esquisses se rencontrent. La CLI et la console l'appellent tous
les deux : recopier l'enchainement produirait deux confirmations qui
divergeraient, et c'est la confirmation qui protege ici.

**Le driver est un PARAMETRE.** `cartographier(..., driver=...)` recoit un
driver deja construit ; il n'est connecte que si l'appelant n'en fournit pas.
C'est ce qui rend cette fonction testable sans SAP, et c'est aussi ce qui
permet a `falcon.exploration` de ne jamais importer `falcon.couture`.

**Rien ici ne peut relever le plafond de sauvegardes.** Il vaut zero dans
`exploration.parcours`, en constante de module, et cette couche-ci n'a aucun
moyen de le changer : elle ne construit pas le `DriverGarde`.

**Le compte rendu est ECRIT a cote du catalogue**, et pas seulement imprime.
C'est le seul endroit ou vivent la partition des gestes, les branches, les
reprises et les visites non atteintes : il defilait a l'ecran, puis
disparaissait avec la fenetre. Un `<catalogue>/rapports/` invisible du
`Depot` — qui globe `racine/*.yaml` sans recursion — et du `.txt`, c'est-a-dire
le texte de `rapport.rendre` verbatim : pas de format nouveau, donc pas de
classe de defaut nouvelle.
"""

from __future__ import annotations

from pathlib import Path

from falcon.exploration import Exploration, explorer
from falcon.exploration.rapport import ordres_manquants, rendre
from falcon.noyau import Horloge, maintenant
from falcon.taxonomie import Registre
from falcon.trace import Trace, lire
from falcon.trace.esquisse import deposer

#: Le sous-dossier ou les comptes rendus sont conserves.
DOSSIER_RAPPORTS = "rapports"

#: Codes de retour. 0 seulement si la trace a ete parcourue jusqu'au bout.
#:
#: Une cartographie qui s'arrete a la visite 17 sur 40 et rend 0 serait un
#: succes annonce sur un travail a moitie fait — et sur la trace de reference,
#: le parcours s'interrompt TOUJOURS, parce qu'elle sauvegarde. `explorer`
#: rend donc 1 sur cette trace, et c'est le bon resultat.
TERMINE = 0
INCOMPLET = 1


def annoncer_la_session(driver) -> str:
    """Sur QUOI on s'apprete a agir, lu par une facade en LECTURE SEULE.

    Montre avant la confirmation, et pas seulement dans le compte rendu :
    l'endroit ou quelqu'un decide de lancer est l'endroit ou il doit voir le
    mandant. Rien ici ne sait lequel est la production — ce depot ne le sait
    pas — mais un humain, lui, reconnait le sien.

    `DriverLecture` et non le driver : cette fonction ne peut pas agir, au
    sens ou `write` et `press` n'existent pas sur l'objet qu'elle tient.
    """
    from falcon.couture import DriverLecture

    identite = DriverLecture(driver).screen()
    return (f"  systeme {identite.systeme or '?'}   "
            f"mandant {identite.mandant or '?'}   "
            f"langue {identite.langue or '?'}\n"
            f"  ecran courant : {identite.transaction or '?'} / "
            f"{identite.programme or '?'} / {identite.dynpro or '?'}")


def cartographier(trace: str | Path,
                  catalogue: str | Path,
                  *,
                  plafond_gestes: int,
                  plafond_ecrans: int,
                  esquisses: bool = False,
                  registre: Registre | None = None,
                  driver=None,
                  connexion: int = 0,
                  session: int = 0,
                  observateur=None,
                  horloge: Horloge = maintenant) -> tuple[Trace, Exploration,
                                                          str]:
    """Rejoue une trace et rend (trace lue, exploration, compte rendu).

    Lecture STRICTE de la trace : une cartographie batie sur des lignes non
    appariees rejouerait autre chose que ce qui a ete enregistre. Une trace
    que `lire` refuse passe par `inventaire`, qui nomme ce qui manque.

    `observateur` n'est qu'un PASSE-PLAT vers `explorer` : cette couche ne
    sait pas ce qu'est un terminal, et c'est ce qui lui permet de servir la
    CLI et la console sans les distinguer. Le defaut est `None`, c'est-a-dire
    le comportement d'avant au fait pres.
    """
    chemin = Path(trace)
    lue = lire(chemin)

    if driver is None:
        # Import local : `sapgui` charge pywin32 quand on lui demande de se
        # connecter, et rien avant.
        from falcon.couture.sapgui import connecter
        driver = connecter(connexion=connexion, session=session)

    exploration = explorer(
        lue, driver, catalogue=catalogue, plafond_gestes=plafond_gestes,
        plafond_ecrans=plafond_ecrans, registre=registre,
        observateur=observateur)

    compte_rendu = rendre(exploration, lue)
    if esquisses:
        compte_rendu += "\n" + _verser_les_esquisses(lue, exploration,
                                                     catalogue)
    conserve = _conserver(catalogue, chemin.name, compte_rendu, horloge)
    compte_rendu += f"\n\n  compte rendu conserve : {conserve}"
    return lue, exploration, compte_rendu


def _conserver(catalogue: str | Path, trace: str, texte: str,
               horloge: Horloge) -> Path:
    """Ecrit le compte rendu dans `<catalogue>/rapports/` et rend son chemin.

    Aucun `except` ici, et c'est delibere : le parcours vient d'ecrire des
    variantes dans ce meme dossier de catalogue. Un disque qui refuserait le
    compte rendu aurait deja refuse la quarantaine, et l'exploration aurait
    leve bien avant. Avaler l'erreur rendrait un chemin de fichier qui
    n'existe pas — une phrase d'aspect normal, et fausse.

    Le rang en suffixe reprend la parade d'`ecrire_dump` : deux cartographies
    lancees dans la meme milliseconde ecraseraient le premier compte rendu, et
    un compte rendu perdu est une partition perdue.
    """
    dossier = Path(catalogue) / DOSSIER_RAPPORTS
    dossier.mkdir(parents=True, exist_ok=True)

    base = f"{_pour_un_nom(horloge())}-{trace}"
    chemin = dossier / f"{base}.txt"
    rang = 1
    while chemin.exists():
        rang += 1
        chemin = dossier / f"{base}_{rang}.txt"

    # Le meme encodage que tout ce que ce depot ecrit, et des fins de ligne
    # `\n` explicites : un compte rendu relu par le navigateur ne doit pas
    # dependre de la plateforme qui l'a produit.
    chemin.write_text(texte + "\n", encoding="utf-8", newline="\n")
    return chemin


def _pour_un_nom(horodatage: str) -> str:
    """Un horodatage ISO utilisable comme nom de fichier sur Windows.

    `:` y est interdit — il separe le lecteur du chemin — et un
    `2026-09-11T18:10:54.370Z` produirait un fichier que la console refuse de
    creer, sans que rien n'ait l'air anormal dans le code.
    """
    return horodatage.replace(":", "-").replace(".", "-")


def _verser_les_esquisses(trace: Trace, exploration: Exploration,
                          catalogue: str | Path) -> str:
    """Verse en quarantaine les esquisses des visites NON ATTEINTES.

    **C'est le seul appelant de production de `trace.esquisse.deposer`**, et
    un test AST le verifie. La fonction existait depuis le lot 8 sans que rien
    ne l'appelle : une capacite annoncee dans la documentation et injoignable
    depuis le programme est un mensonge de plus, pas une fonctionnalite en
    attente. Le meme trou avait ete trouve sur `promouvoir` ; c'est pour cela
    que le garde-fou est un test et non une intention.

    Seulement les non atteintes : verser les autres poserait, dans la meme
    quarantaine, la conjecture a cote du releve reel du meme ecran. La
    quarantaine est ce qu'un humain relit une entree a la fois.
    """
    from falcon.catalogue import Depot

    manquantes = ordres_manquants(exploration, trace)
    if not manquantes:
        return ("\n  --esquisses : aucune visite non atteinte, donc aucune "
                "esquisse a verser.\n"
                "  La trace a ete parcourue en entier.")

    clefs = deposer(trace, Depot(catalogue), seulement=manquantes)
    lignes = [
        "",
        f"  --esquisses : {len(clefs)} esquisse(s) versee(s) en quarantaine "
        f"pour {len(manquantes)} visite(s)",
        "  non atteinte(s). C'est une LISTE DE COURSES, pas un relevé :",
        "",
        "    - elles portent `programme: \"?\"` et `dynpro: \"?\"`, visibles a",
        "      l'oeil nu dans le YAML — la trace ne les dit pas ;",
        "    - leurs champs n'ont pas de type, et `modifiable` y vaut « ? » :",
        "      personne n'a vu ces ecrans ;",
        "    - `pour_garde` les refuse, meme promues. Promouvoir une esquisse",
        "      dit « j'ai vu le fichier », pas « j'ai vu l'ecran ».",
        "",
        "  Pour chacune, aller voir l'ecran : `falcon diagnostiquer "
        "--catalogue`.",
    ]
    return "\n".join(lignes)
