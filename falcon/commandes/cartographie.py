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
`Depot` — qui globe `racine/*.yaml` sans recursion — et du `.txt` : pas de
format nouveau, donc pas de classe de defaut nouvelle.

Le fichier porte le texte de `rapport.rendre` SUIVI du bloc des esquisses
quand `--esquisses` a ete demande. Il ne porte pas la derniere ligne de ce que
la commande imprime — « compte rendu conserve : <chemin> » — puisque cette
ligne parle du fichier lui-meme : ecrite dedans, elle serait la seule phrase
du document a ne rien dire de la cartographie. Le texte imprime et le texte
conserve ne sont donc pas identiques, et le dire vaut mieux que de promettre
un « verbatim » qu'un `read_text()` dement.
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

    `horloge` ne va PAS a `explorer`, et il faut le dire ici parce que c'est
    ce qu'on suppose en lisant la signature. Elle ne sert qu'a dater le nom du
    compte rendu conserve. Celle du parcours est un autre objet : elle nomme
    les dumps et date les variantes, `explorer` la tient de son propre defaut,
    et les confondre ferait qu'une suite qui fige l'heure pour obtenir un nom
    de fichier stable figerait du meme geste l'horodatage des captures.
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
    conserve, refus = _conserver(catalogue, chemin.name, compte_rendu, horloge)
    if conserve is not None:
        compte_rendu += f"\n\n  compte rendu conserve : {conserve}"
    else:
        compte_rendu += (
            f"\n\n  compte rendu NON conserve ({refus}).\n"
            f"  RECOPIE-LE DEPUIS CET ECRAN : il est le seul endroit ou "
            f"vivent la partition\n"
            f"  des gestes, les branches, les reprises et les visites non "
            f"atteintes, et\n"
            f"  cette cartographie a DEJA agi dans SAP.")
    return lue, exploration, compte_rendu


def _conserver(catalogue: str | Path, trace: str, texte: str,
               horloge: Horloge) -> tuple[Path | None, str]:
    """Ecrit le compte rendu dans `<catalogue>/rapports/`.

    Rend (chemin, refus) : l'un des deux est toujours vide.

    **L'echec est NOMME, jamais leve, et surtout jamais silencieux.** La
    justification precedente — « le parcours vient d'ecrire des variantes
    ce meme dossier, un disque qui refuserait le compte rendu aurait deja
    refuse la quarantaine » — a ete mesuree et elle est FAUSSE : au second
    passage sur un catalogue deja peuple, tous les ecrans sont deja connus,
    zero variante est versee, et `Depot` ne cree meme pas sa racine. Le
    `mkdir` et le `write_text` d'ici sont alors la PREMIERE et la SEULE
    ecriture de la commande, sur le chemin par defaut (`--esquisses` est
    optionnel). Un partage en lecture seule, un fichier verrouille par
    l'antivirus, un `rapports` deja occupe par un fichier ordinaire : un
    `OSError` qui traverserait ici emporterait le compte rendu d'une
    cartographie qui a deja pilote SAP pendant trois minutes — et ni
    `ERREURS_LISIBLES` de la CLI ni le `except ErreurFalcon` de la console ne
    connaissent `OSError`, donc l'utilisateur recevrait une pile Python a la
    place de sa partition.

    Rendre un chemin de fichier qui n'existe pas serait le defaut inverse, et
    il reste refuse : on ne rend PAS de chemin, on rend le motif, et
    l'appelant ecrit « NON conserve » avec lui.

    Le rang en suffixe reprend la parade d'`ecrire_dump` : deux cartographies
    lancees dans la meme milliseconde ecraseraient le premier compte rendu, et
    un compte rendu perdu est une partition perdue.

    `trace` entre tel quel dans le nom : seul l'horodatage est desinfecte, et
    c'est assume. Un nom de trace venu d'un disque Windows y est deja legal ;
    un nom venu d'un partage Samba ou d'un chemin WSL pourrait porter `: ? *`,
    et c'est justement l'`OSError` ci-dessus qui le dira, avec le nom fautif
    dans son message.
    """
    dossier = Path(catalogue) / DOSSIER_RAPPORTS
    base = f"{_pour_un_nom(horloge())}-{trace}"
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / f"{base}.txt"
        rang = 1
        while chemin.exists():
            rang += 1
            chemin = dossier / f"{base}_{rang}.txt"

        # Le meme encodage que tout ce que ce depot ecrit, et des fins de
        # ligne `\n` explicites : un compte rendu relu par le navigateur ne
        # doit pas dependre de la plateforme qui l'a produit.
        chemin.write_text(texte + "\n", encoding="utf-8", newline="\n")
    except OSError as erreur:
        return None, f"{type(erreur).__name__} : {erreur}"
    return chemin, ""


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
