"""Le compte rendu d'une cartographie : ce qui a ete vu, ce qui ne l'a pas ete.

Fonction pure d'un objet de donnees, comme `journal.rendre` : aucun driver,
aucun depot, aucun fichier. Elle recoit l'`Exploration` qu'un parcours a rendue
et la `Trace` qu'il a rejouee.

**LE PIEGE, et c'est le seul qui compte ici : ne jamais rapprocher une esquisse
d'un releve par la CLEF.** `trace/esquisse.py` pose deux protections
independantes pour qu'une esquisse ne puisse jamais porter la clef d'un relevé,
et la seconde est arithmetique : l'empreinte d'une esquisse porte sur les
identifiants TOUCHES, celle d'un releve sur les identifiants PRESENTS. Les deux
ne coincident jamais. Un rapport qui ferait `set(esquisses) - set(releves)`
afficherait donc **« 35 conjecturees, 0 relevee, 35 restantes » sur une
cartographie parfaitement reussie** — un chiffre d'aspect normal, faux, et
decourageant au point qu'on relancerait indefiniment un travail deja fait.

Le rapprochement se fait donc **par position** : une visite est « atteinte »
si le parcours est passe par au moins un de ses gestes. Le rapport ecrit cette
phrase, parce qu'un lecteur qui lirait « couverte » sans elle comprendrait
« la meme clef existe des deux cotes ».

**Ce que « atteinte » ne dit pas non plus.** Ce n'est pas un pourcentage
d'ecrans du parcours metier, et ce n'est pas un nombre d'ecrans distincts :
plusieurs visites tombent sur le meme ecran, et le nombre de variantes versees
est nettement inferieur au nombre de visites atteintes. Les deux chiffres sont
donnes cote a cote, sous des noms differents, pour qu'on ne les additionne pas.
"""

from __future__ import annotations

from falcon.catalogue import Variante
from falcon.trace import Trace
from falcon.trace.esquisse import Visite, esquisse_de, visites

from .gestes import TRADUIT, traduire
from .parcours import PLAFOND, TERMINEE, Exploration, previsualiser

#: Ce que le rapport dit d'une visite de la trace.
ATTEINTE = "atteinte"           # le parcours est passe par un de ses gestes
SAUTEE = "sautee"               # emportee par un saut vers un point de reprise
NON_EXPLOREE = "non_exploree"   # le parcours s'est arrete avant elle
ETATS_DE_VISITE = (ATTEINTE, SAUTEE, NON_EXPLOREE)


def etat_des_visites(exploration: Exploration,
                     trace: Trace) -> tuple[tuple[Visite, str], ...]:
    """(visite, etat) pour chaque visite de la trace, dans l'ordre.

    **Par position, jamais par clef** — voir l'en-tete du module. Une visite
    est ATTEINTE des qu'un seul de ses gestes figure dans `ordres_atteints` :
    le parcours y a mis les pieds, et le releve pris apres ce geste porte
    l'ecran qu'elle decrit. Elle est SAUTEE si tous ses gestes ont ete
    emportes par un saut, et NON_EXPLOREE si le parcours s'est arrete avant.
    """
    atteints = set(exploration.ordres_atteints)
    sautes = set(exploration.ordres_sautes)
    etats: list[tuple[Visite, str]] = []
    for visite in visites(trace):
        ordres = {geste.ordre for geste in visite.gestes}
        if ordres & atteints:
            etats.append((visite, ATTEINTE))
        elif ordres <= sautes:
            etats.append((visite, SAUTEE))
        else:
            etats.append((visite, NON_EXPLOREE))
    return tuple(etats)


def visites_manquantes(exploration: Exploration,
                       trace: Trace) -> tuple[Visite, ...]:
    """Les visites que le parcours n'a pas atteintes."""
    return tuple(visite for visite, etat in etat_des_visites(exploration, trace)
                 if etat != ATTEINTE)


def esquisses_manquantes(exploration: Exploration, trace: Trace, *,
                         capture_le: str = "") -> tuple[Variante, ...]:
    """Les esquisses des visites non atteintes — la liste de courses.

    Ce sont elles, et elles seules, que `explorer --esquisses` verse en
    quarantaine. Verser les autres poserait a cote du releve REEL du meme
    ecran une conjecture qui, par construction, n'en a ni le programme, ni le
    dynpro, ni l'empreinte — c'est-a-dire du bruit a relire.
    """
    retenues: list[Variante] = []
    vues = set()
    for visite in visites_manquantes(exploration, trace):
        esquisse = esquisse_de(visite, capture_le=capture_le)
        if esquisse is None or esquisse.clef in vues:
            continue
        vues.add(esquisse.clef)
        retenues.append(esquisse)
    return tuple(retenues)


def ordres_manquants(exploration: Exploration, trace: Trace) -> tuple[int, ...]:
    """Les ORDRES des visites non atteintes — ce que `deposer` sait filtrer."""
    return tuple(v.ordre for v in visites_manquantes(exploration, trace))


def _partition(exploration: Exploration) -> list[str]:
    lignes = ["  gestes de la trace"]
    for nom, compte in exploration.partition.items():
        if compte:
            lignes.append(f"    {nom:<22} {compte:>4}")
    lignes.append(f"    {'TOTAL':<22} {exploration.gestes_lus:>4}")
    if not exploration.partition_coherente:
        # Ne peut pas arriver — un test l'exerce sur la trace de reference —
        # mais si cela arrivait, le rapport doit le dire plutot que de
        # presenter des chiffres qui ne se rejoignent pas.
        lignes.append("    *** LA PARTITION NE SOMME PAS AU TOTAL : des "
                      "gestes ont disparu du compte rendu ***")
    lignes.append(f"    actions envoyees au driver : "
                  f"{exploration.actions_envoyees}")
    return lignes


def rendre(exploration: Exploration, trace: Trace) -> str:
    """Le compte rendu, en texte."""
    etats = etat_des_visites(exploration, trace)
    atteintes = [v for v, e in etats if e == ATTEINTE]
    manquantes = [(v, e) for v, e in etats if e != ATTEINTE]
    apercu = previsualiser(trace)

    lignes = [
        f"cartographie de {exploration.trace}",
        f"  catalogue      {exploration.catalogue}",
        f"  etat           {exploration.etat}",
    ]
    if exploration.raison:
        lignes.append(f"  raison         {exploration.raison}")

    # -- les ecrans ------------------------------------------------------
    lignes += [
        "",
        "  ecrans",
        f"    verses en quarantaine  {len(exploration.versees):>4}",
        f"    deja connus            {len(exploration.deja_connues):>4}",
        f"    releves pris           {exploration.releves:>4}",
        "",
        "    Un releve par fenetre ouverte, apres chaque action. Le nombre",
        "    d'ecrans VERSES est inferieur : plusieurs releves tombent sur la",
        "    meme variante, et le depot n'en garde qu'une.",
    ]

    # -- conjecture contre observation ------------------------------------
    lignes += [
        "",
        f"  visites de la trace : {len(etats)} — "
        f"{len(atteintes)} atteinte(s), {len(manquantes)} non atteinte(s)",
        "",
        "    « Atteinte » veut dire : le parcours est passe par au moins un",
        "    geste de cette visite. Ce n'est PAS « la meme clef existe des",
        "    deux cotes » — une esquisse et un releve ne peuvent pas porter la",
        "    meme clef, l'une porte les champs TOUCHES et l'autre les champs",
        "    PRESENTS. Et ce n'est pas un compte d'ecrans distincts : plusieurs",
        "    visites tombent sur le meme ecran.",
    ]

    if manquantes:
        lignes.append("")
        lignes.append("    non atteintes :")
        for visite, etat in manquantes:
            transaction = visite.transaction or "?"
            lignes.append(
                f"      visite {visite.ordre:>3}  {etat:<13} "
                f"transaction conjecturee {transaction}  "
                f"({len(visite.gestes)} geste(s), "
                f"{len(visite.cibles)} champ(s) touche(s))")
        lignes.append("")
        lignes.append("      « transaction conjecturee » : lue dans le champ de "
                      "commande de la")
        lignes.append("      trace, en supposant que SAP a accepte le code. La "
                      "trace ne dit pas")
        lignes.append("      ce que SAP a repondu.")

    # -- ce qui a interrompu ---------------------------------------------
    if exploration.branches:
        lignes += ["", f"  branches interrompues ({len(exploration.branches)})"]
        for branche in exploration.branches:
            suite = (f"reprise sur {branche.reprise}" if branche.reprise
                     else "ARRET — plus aucun point de reprise")
            lignes.append(f"    geste {branche.ordre:03d} (ligne "
                          f"{branche.ligne}, {branche.verbe}) "
                          f"[{branche.categorie}] — {suite}")
            lignes.append(f"        {branche.motif}")
            if branche.dump:
                lignes.append(f"        dump : {branche.dump}")

    # -- les reprises ------------------------------------------------------
    if exploration.reprises:
        lignes += ["", f"  reprises ({len(exploration.reprises)})"]
        for reprise in exploration.reprises:
            verdict = ("acceptee" if reprise.acceptee
                       else f"REFUSEE — SAP est reste sur {reprise.obtenue!r}")
            lignes.append(f"    geste {reprise.ordre:03d}  "
                          f"{reprise.demandee:<10} {verdict}")
        lignes.append("")
        lignes.append("    Chaque reprise a ete TAPEE par l'explorateur dans le "
                      "champ de commande,")
        lignes.append("    validee par Entree, et verifiee contre l'ecran "
                      "obtenu. Les deux gestes")
        lignes.append("    qu'elle envoie ne figurent pas dans la trace.")

    # -- ce qui n'a pas ete ecrit -----------------------------------------
    lignes += ["", "  sauvegardes"]
    if exploration.sauvegardes_refusees:
        for refus in exploration.sauvegardes_refusees:
            lignes.append(f"    REFUSEE  geste {refus.ordre:03d} (ligne "
                          f"{refus.ligne})  {refus.verbe} {refus.cible}")
    lignes.append(f"    {len(exploration.sauvegardes_refusees)} refusee(s) sur "
                  f"{len(apercu.sauvegardes)} que la trace contient.")
    lignes.append("    Les autres n'ont pas ete atteintes — la branche etait "
                  "deja tombee.")
    lignes.append("")
    lignes.append("    Rejouer cette trace SANS le dry-run ecrirait "
                  f"{len(apercu.sauvegardes)} fois dans SAP.")

    lignes.append("")
    lignes += _partition(exploration)

    # -- ce que le rapport ne dit pas -------------------------------------
    lignes += [
        "",
        "  ce que ce rapport ne dit pas",
        "    - que la trace a ete SUIVIE : elle ne l'a pas ete. Il dit quels",
        "      ecrans ont ete VUS. Un index de grille rejoue tel quel peut",
        "      ouvrir le detail d'un autre objet qu'a l'enregistrement, sans",
        "      erreur, et la suite du parcours diverge alors en silence.",
        "    - que les ecrans verses sont justes : ils sont en QUARANTAINE,",
        "      c'est-a-dire en attente qu'un humain les relise et les promeuve.",
        "    - qu'aucun effet n'a eu lieu dans SAP. Aucune sauvegarde n'est",
        "      partie ; l'exploration a tout de meme presse des boutons, lance",
        "      des selections, et peut avoir pose des verrous.",
    ]

    if exploration.etat == PLAFOND:
        lignes.append("    - combien d'ecrans restaient : un plafond a mordu, "
                      "et ce qui suit")
        lignes.append("      n'a pas ete explore du tout.")
    elif exploration.etat == TERMINEE:
        lignes.append("    - il n'y a rien de plus : la trace a ete parcourue "
                      "jusqu'au bout.")

    return "\n".join(lignes)


def previsualisation(trace: Trace) -> str:
    """Ce qu'on montre AVANT de lancer — l'ecran de confirmation.

    Il ne predit pas les branches : ou une branche tombe depend de ce que SAP
    repond, et personne ici ne le sait. Il dit ce que la TRACE contient.
    """
    apercu = previsualiser(trace)
    conjecturees = visites(trace)
    rejouables = sum(1 for g in trace.gestes
                     if traduire(g).genre == TRADUIT)
    lignes = [
        f"  {apercu.gestes} geste(s) lus, {len(conjecturees)} visite(s) d'ecran "
        f"conjecturee(s)",
        f"    traduisibles en appel de couture   {rejouables:>4}",
        f"    gestes de confort, ecartes         {apercu.confort:>4}",
        f"    sans methode de couture (arbre)    {len(apercu.sans_couture):>4}",
    ]
    if apercu.verbes_inconnus:
        lignes.append(
            f"    verbe ou argument non traduisible  "
            f"{len(apercu.verbes_inconnus):>4}   ordres "
            f"{list(apercu.verbes_inconnus)}")
    lignes += [
        "",
        f"  transactions nommees : "
        f"{', '.join(apercu.codes) if apercu.codes else 'aucune'}",
        f"  points de reprise verifiables : {apercu.reprises_possibles}",
    ]
    if apercu.sans_reprise:
        lignes.append(f"  codes de commande non reprenables : "
                      f"{list(apercu.sans_reprise)} "
                      f"(`/n` seul, ou code de session)")
    lignes += [
        "",
        f"  ATTENTION — cette trace contient {len(apercu.sauvegardes)} "
        f"geste(s) de SAUVEGARDE.",
        "  Ils seront refuses : l'exploration tourne en dry-run, plafond de",
        "  sauvegardes a zero. Mais chaque refus fait TOMBER la branche, et",
        "  l'exploration ne repart qu'au prochain code transaction.",
        "",
        "  L'exploration n'ecrit aucune donnee. Elle AGIT : elle navigue, elle",
        "  presse des boutons, elle lance des selections qui peuvent tourner",
        "  longtemps et charger le systeme, et elle peut poser des verrous SAP.",
        "  A lancer sur un mandant de qualite avant la production.",
    ]
    return "\n".join(lignes)
