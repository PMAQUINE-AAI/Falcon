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
"""

from __future__ import annotations

from pathlib import Path

from falcon.exploration import Exploration, explorer
from falcon.exploration.rapport import ordres_manquants, rendre
from falcon.taxonomie import Registre
from falcon.trace import Trace, lire
from falcon.trace.esquisse import deposer

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
                  session: int = 0) -> tuple[Trace, Exploration, str]:
    """Rejoue une trace et rend (trace lue, exploration, compte rendu).

    Lecture STRICTE de la trace : une cartographie batie sur des lignes non
    appariees rejouerait autre chose que ce qui a ete enregistre. Une trace
    que `lire` refuse passe par `inventaire`, qui nomme ce qui manque.
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
        plafond_ecrans=plafond_ecrans, registre=registre)

    compte_rendu = rendre(exploration, lue)
    if esquisses:
        compte_rendu += "\n" + _verser_les_esquisses(lue, exploration,
                                                     catalogue)
    return lue, exploration, compte_rendu


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
