"""Le direct d'une cartographie : une ligne collante, et un flux de faits.

Pendant un `press` sur un ALV reel, SAP peut tenir plusieurs secondes ; sur la
trace de reference, 33 actions et 29 releves font une a trois minutes de
silence complet. Aujourd'hui `falcon explorer` n'affiche RIEN avant le compte
rendu. Ce module comble ce trou, avec le seul redessin que ce depot autorise et
qui marche dans `cmd`, dans PowerShell et a travers RDP : un retour chariot et
du remplissage, exactement le geste de `supervision/terminal.py`.

**Aucun ETA, et c'est un refus.** `supervision/modele.py` en calcule un parce
qu'un lot iteratif traite n items comparables. Une exploration, non : mesure
faite sur la trace de reference, 46 des 90 gestes partent EN BLOC quand une
branche tombe. `moyenne x restants` y serait faux d'un facteur cinq et
s'effondrerait en un pas. Un ETA faux est pire qu'un ETA absent — on planifie
dessus. Le bandeau affiche le temps ECOULE, qui est une mesure.

**Aucune jauge sur les gestes.** Elle avancerait sur des gestes SAUTES, donc
se remplirait a 100 % d'une trace vue a moitie. Les deux seules jauges
permises sont `actions/plafond` et `ecrans/plafond` : deux compteurs monotones
dont le denominateur est un budget que l'utilisateur a lui-meme tape. Et une
jauge dont le denominateur vaut zero n'est pas dessinee du tout — pas mise a
zero, pas mise a cent : absente. Diviser par la serait la seule ligne de ce
module capable de lever pendant qu'une session SAP tourne.

**Le rang est une POSITION dans la trace, jamais un avancement**, et la
premiere ligne du direct le dit une fois. `034/090` veut dire « on en est au
34e geste du fichier », pas « 34 gestes sur 90 ont ete traites » : la partition
des sept compteurs ne somme qu'a la fin, et `Exploration.partition_coherente`
existe precisement pour empecher qu'un total soit affirme avant.

**La ligne collante ne remplit JAMAIS la derniere colonne** et elle est
TRONQUEE, pas seulement rembourree. `Rapporteur._ecrire` fait un `ljust` sans
coupe : une ligne plus large que la fenetre s'y replierait, et le `\\r` suivant
reviendrait au debut de la ligne REPLIEE — l'effacement laisserait la moitie du
bandeau precedent a l'ecran, definitivement. Sans largeur mesuree, pas de
bandeau du tout : seulement le flux, qui n'a jamais ce probleme.

Et la garantie porte sur la largeur mesuree AU LANCEMENT, pas sur la largeur
du moment. Windows n'a pas de `SIGWINCH`, le direct n'a pas de tour de boucle
ou remesurer, et apres une reconnexion RDP a une autre resolution le bandeau
est cadre sur l'ancienne : mesure faite sur un pty ramene de 110 a 40
colonnes, les lignes se replient et le retour chariot revient au debut d'une
ligne REPLIEE. Le seul recours est `--muet`. C'est aussi pourquoi
`gabarit.trop_etroit` n'est consulte nulle part ici : un flux qui defile n'a
pas de refus a opposer — il coupe, et la marque le dit — la ou une vue qu'on
reaffiche peut refuser de se dessiner.

**Le flux, lui, sort meme hors terminal, et ce n'est pas une inattention.**
`Rapporteur` se tait entierement hors terminal parce qu'il n'ecrit QUE du
redessin ; ici les deux sorties sont de natures differentes. Le flux de faits
est fait de lignes entieres terminees par un saut de ligne : `falcon explorer
... 2> journal.txt` donne le meme texte, sans un caractere de controle, et
c'est exactement ce qu'on veut relire apres coup. Le bandeau, lui, n'a de sens
que la ou un retour chariot repositionne le curseur — c'est lui, et lui seul,
qui se tait hors terminal. Pour ne rien emettre du tout, `--muet`.

**Et dans la console, pas de bandeau — ce n'est pas un oubli.**
`Console.ecrire` vaut `print` : il pose une ligne entiere, et il n'existe aucun
moyen d'en reprendre une sans sortir de l'injection qui rend la console
testable. Le prix est ECRIT a l'ecran plutot que tu : la console affiche un
geste une fois qu'il est FAIT.

**Aucun compteur du bilan n'est calcule ici**, et `justifications` est ce qui
rend la phrase verifiable plutot qu'affirmee : chaque valeur y nomme le
REPERE qui doit se lire sur la MEME ligne du compte rendu. Le compte rendu
reste le seul juge, et un test apparie les deux.

**Trois compteurs font exception, et l'exception est DECLAREE** plutot que
laissee au hasard d'une trace. `rapport.rendre` n'ecrit le bloc des branches
que s'il y a des branches, celui des reprises que s'il y a des reprises, et
`_partition` n'ecrit une ligne que si son compte n'est pas nul : sur un rejeu
qui va au bout sans incident — la forme la plus courante — aucune ligne ne
porte « branches interrompues », « reprises ( » ni « sautes ». Le bilan
continue d'afficher ces trois zeros, parce que zero est une reponse ; mais
`Justification.absent_si_zero` le dit, et le test EXIGE alors que le repere
soit introuvable dans le compte rendu. L'exemption est ainsi mesuree elle
aussi, au lieu d'etre un test qui ne visite jamais le cas.

Trois chiffres de la maquette n'y figurent donc pas, et il vaut mieux le dire
que de les inventer :

  - **les releves pris.** `_Parcours.relever` incremente son compteur a chaque
    appel, et le flux ne porte AUCUN fait par releve : un releve qui ne verse
    rien et ne reconnait rien n'emet pas un evenement. Reconstruire « 29 » en
    comptant les ecrans verses et connus donnerait 5 sur la trace de
    reference. Un compte d'aspect normal, faux d'un facteur six.
  - **les reprises refusees.** Le compte rendu les nomme une par une, sans en
    donner le total sur aucune ligne. Le direct sait pourtant les compter — il
    voit passer chaque `REPRISE` et son `acceptee` — mais afficher un total
    qu'aucune ligne du compte rendu ne porte reviendrait a le calculer ici.
    Chaque refus se lit dans le flux, a la ligne ou il arrive.
  - **la valeur ecrite par un `text`.** `Evenement` ne transporte pas
    l'argument d'un geste ; la retrouver demanderait d'apparier l'`ENVOYE` a
    l'evenement `GESTE` qui l'a precede, c'est-a-dire de rapprocher deux faits
    sur une supposition d'ordre. Le flux montre le verbe et la cible.

**La duree, elle, n'a pas de repere dans le compte rendu, et c'est normal** :
il n'en porte aucune. Ce n'est pas un compteur de l'exploration, c'est la
mesure de l'horloge monotone que `_Parcours.chrono` transporte sur chaque
fait. Elle est exemptee nommement, et par le test aussi.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, TextIO

from falcon.exploration import evenements as E
from falcon.exploration.evenements import Evenement

from .capacites import COULEUR, Capacites, Gabarit, gabarit_pour
from .fragment import (
    ALERTE, ATTENUE, DANGER, ENTETE, MARQUE, NEUTRE, SEPARATEUR, SUCCES,
    TITRE, VIDE, Bloc, Fragment, couper, couper_chemin,
)
from .peintre import Peintre, peintre_pour

if TYPE_CHECKING:               # annotation seule : voir test_frontieres
    from falcon.console.menu import Console

#: La marge gauche de tout ce que le direct ecrit, en colonnes.
MARGE = 2

#: Un caractere par genre, en tete de ligne. Il sert a l'oeil qui balaie une
#: colonne, pas a la lecture : c'est l'etiquette en toutes lettres qui dit ce
#: qui s'est passe. De l'ASCII, pour la raison qui vaut partout ici — une
#: police raster de console Windows affiche un carre vide la ou elle n'a pas
#: le glyphe, sans erreur et sans code retour.
#:
#: `SAUVEGARDE_REFUSEE` et `BRANCHE` partagent la meme marque : le refus et la
#: chute qu'il provoque sont un seul evenement pour qui regarde, et inventer
#: un caractere de plus pour les distinguer ferait deux colonnes a apprendre
#: la ou l'etiquette suffit.
MARQUES = {
    E.ENVOYE: "#",
    E.CONFORT: "~",
    E.VALIDATION: "+",
    E.ECRAN_VERSE: "*",
    E.ECRAN_CONNU: "*",
    E.REPRISE: ">",
    E.BRANCHE: "$",
    E.SAUVEGARDE_REFUSEE: "$",
    E.SAUT: "_",
    E.PLAFOND: "=",
}

#: Ce que chaque genre VEUT dire. Les tons de `falcon.toile.fragment`, et pas
#: ceux de `supervision.modele` : un geste de confort ecarte n'est pas un
#: `ko`, une branche tombee n'est pas un `douteux`. Reutiliser la ligne de la
#: supervision aurait ete de la reutilisation qui ment.
#:
#: `REPRISE` n'y figure PAS, et ce n'est pas un oubli : son ton ne depend pas
#: du genre mais du verdict. Une reprise ACCEPTEE est un succes, une reprise
#: REFUSEE est ce qui change tout ce qui sera explore ensuite — sur la trace
#: de reference c'est elle qui produit la branche finale sans point de
#: reprise. Poser `SUCCES` a plat sur le genre mentirait sur la moitie des
#: lignes ; le ton se decide donc au site qui connait `acceptee`, dans
#: `ligne_evenement`. La table est lue par INDEXATION et non par `.get` :
#: un genre oublie leve, au lieu de se peindre neutre en silence.
TONS_DU_DIRECT = {
    E.ENVOYE: NEUTRE,
    E.CONFORT: ATTENUE,
    E.VALIDATION: ATTENUE,
    E.ECRAN_VERSE: SUCCES,
    E.ECRAN_CONNU: ATTENUE,
    E.BRANCHE: ALERTE,
    E.SAUVEGARDE_REFUSEE: ALERTE,
    E.SAUT: ATTENUE,
    E.PLAFOND: ALERTE,
}

#: Les genres qui ne font PAS une ligne, et pourquoi chacun.
#:
#:   - `GESTE` : il dit qu'un geste est ABORDE. Une ligne par geste aborde
#:     doublerait le flux pour n'annoncer que ce que la ligne suivante dit
#:     deja — et sur les gestes de confort elle le dirait deux fois. Il fait
#:     avancer le rang du bandeau, ce qui est tout son office.
#:   - `DEPART` : c'est l'en-tete, quatre lignes, un filet, et non une.
#:   - `FIN` : c'est le bilan, et il se pose a la cloture.
SANS_LIGNE = frozenset({E.GESTE, E.DEPART, E.FIN})

#: Largeur de la jauge, en caracteres. Dix : un caractere par dixieme, ce qui
#: se lit sans compter.
JAUGE = 10


@dataclass(frozen=True)
class Cadran:
    """L'etat accumule. Immuable : `avancer` en rend un neuf.

    Rien ici n'est calcule : chaque champ est soit recopie d'un evenement, soit
    incremente d'un fait vu passer. Le `Cadran` ne sait rien que le flux ne lui
    ait dit, et c'est ce qui permet au bilan de ne rien affirmer de plus que le
    compte rendu.

    Quatre compteurs viennent du PARCOURS lui-meme et non d'un decompte local :
    `actions`, `plafond_gestes`, `versees` et `plafond_ecrans` sont renseignes
    par `_Parcours.emettre` sur tous les genres. Les recompter ici donnerait
    deux sources pour un seul fait, et c'est toujours celle qui se trompe qu'on
    lit.
    """

    trace: str = ""
    catalogue: str = ""
    systeme: str = ""
    mandant: str = ""
    langue: str = ""
    transaction: str = ""

    #: Rang du dernier geste ABORDE, et le nombre de gestes du fichier. Une
    #: POSITION, jamais un avancement.
    ordre: int = 0
    total: int = 0

    actions: int = 0
    plafond_gestes: int = 0
    versees: int = 0
    plafond_ecrans: int = 0

    connues: int = 0
    branches: int = 0
    sauvegardes_refusees: int = 0
    reprises: int = 0
    sautes: int = 0

    etat: str = ""
    monotone_ms: int = 0

    #: Vrai des que le `DEPART` est passe. Sans lui, un bandeau pose avant le
    #: premier fait afficherait « 000/000 » et « 00:00:00 », ce qui se lit
    #: comme une exploration vide plutot que comme une exploration qui n'a pas
    #: encore commence.
    commence: bool = False


def avancer(cadran: Cadran, evenement: Evenement) -> Cadran:
    """L'etat d'apres. Fonction PURE : elle ne touche ni flux ni horloge.

    Les compteurs du parcours sont recopies a CHAQUE fait, quel qu'il soit :
    ils sont portes par tous les genres, et les lire seulement sur les genres
    qui les concernent laisserait le bandeau en retard d'un evenement sur
    lui-meme.
    """
    champs: dict[str, Any] = {
        "monotone_ms": evenement.monotone_ms,
        "actions": evenement.actions,
        "plafond_gestes": evenement.plafond_gestes,
        "versees": evenement.versees,
        "plafond_ecrans": evenement.plafond_ecrans,
    }

    if evenement.genre == E.DEPART:
        champs.update(trace=evenement.source, catalogue=evenement.cible,
                      systeme=evenement.systeme, mandant=evenement.mandant,
                      langue=evenement.langue,
                      transaction=evenement.transaction,
                      total=evenement.total, commence=True)
    elif evenement.genre == E.GESTE:
        champs.update(ordre=evenement.ordre)
    elif evenement.genre == E.ECRAN_CONNU:
        champs.update(connues=cadran.connues + 1)
    elif evenement.genre == E.BRANCHE:
        champs.update(branches=cadran.branches + 1)
    elif evenement.genre == E.SAUVEGARDE_REFUSEE:
        champs.update(sauvegardes_refusees=cadran.sauvegardes_refusees + 1)
    elif evenement.genre == E.REPRISE:
        champs.update(reprises=cadran.reprises + 1)
    elif evenement.genre == E.SAUT:
        champs.update(sautes=cadran.sautes + evenement.sautes)
    elif evenement.genre == E.FIN:
        champs.update(etat=evenement.etat)

    return replace(cadran, **champs)


# -- le temps ---------------------------------------------------------------

def duree(monotone_ms: int) -> str:
    """`hh:mm:ss` du temps ECOULE. Jamais une prevision.

    Au-dela de 99 heures la premiere paire deborde, et c'est voulu : une
    exploration qui dure quatre jours doit se lire comme telle, pas revenir a
    zero. Un temps negatif ne peut pas arriver : `time.monotonic` ne recule
    pas, et rien ici ne le fabrique. S'il arrivait, les trois paires seraient
    INCOHERENTES entre elles — mesure : `duree(-1)` rend `-1:59:59`, une heure
    negative et des minutes positives — parce que `//` et `%` arrondissent
    vers le bas. Ce n'est pas « tel quel ». On ne le corrige pas : une
    troisieme branche pour un cas que rien ne peut produire serait un chemin
    de plus a maintenir et a ne jamais exercer. La phrase est ici pour que
    personne ne lise ce rendu comme une mesure.
    """
    secondes = monotone_ms // 1000
    return (f"{secondes // 3600:02d}:"
            f"{secondes % 3600 // 60:02d}:"
            f"{secondes % 60:02d}")


def jauge(fait: int, plafond: int, largeur: int = JAUGE) -> str:
    """`[####------]`, ou la chaine VIDE si le denominateur n'en est pas un.

    Pas de jauge plutot qu'une jauge fausse : un plafond nul ou negatif ne
    donne pas une barre vide — qui se lirait « rien n'est fait » — il ne donne
    rien du tout, et la fraction a cote reste lisible.
    """
    if plafond <= 0 or largeur <= 0:
        return ""
    pleins = min(max(fait * largeur // plafond, 0), largeur)
    return "[" + "#" * pleins + "-" * (largeur - pleins) + "]"


# -- l'en-tete --------------------------------------------------------------

def entete(cadran: Cadran, gabarit: Gabarit) -> list[Bloc]:
    """Les lignes de tete, posees une fois, au DEPART : quatre et un filet.

    Et une cinquieme ligne AVANT elles, au seul niveau COULEUR : la banniere
    en texte nu. C'est la parade nommee du plan contre le seul defaut que la
    sonde peut produire sans que rien ne le signale — non pas qu'elle refuse
    la couleur, mais qu'elle l'ACCEPTE A TORT. La sonde est un modele de
    Windows ecrit ailleurs ; si elle se trompe, l'utilisateur lit
    `<-[1m` a chaque ligne et conclut que l'outil est casse. Une ligne
    SANS TON, donc sans une seule sequence, ecrite avant toute autre, lui
    donne le nom de l'option qui le sauve. Au niveau NU elle n'est pas emise
    du tout : elle n'aurait rien a dementir, et ce serait du bruit dans un
    fichier redirige.

    La troisieme et la quatrieme disent ce que `034/090` ne peut pas dire de
    lui-meme. Elles sont ecrites UNE fois : repetees a chaque ligne elles
    seraient du bruit, absentes elles laisseraient chacun conclure que le
    direct montre un avancement.

    La deuxieme porte le ton `DANGER` parce qu'elle nomme le mandant : c'est
    la seule ligne du direct sur laquelle quelqu'un peut s'apercevoir qu'il
    agit sur le mauvais systeme, et rien ici ne sait lequel est lequel.

    **Les deux chemins se partagent la place, et se coupent au MILIEU.** Ce
    sont des chemins : leur fin discrimine autant que leur debut, et
    `D:\\catalogues\\qas` coupe a droite donne la meme chaine que
    `D:\\catalogues\\prd`. Le partage n'est pas fait par `fragment.colonnes` :
    celle-la REFUSE une rangee qui ne tient pas, ce qui est le bon geste pour
    une vue qu'on reaffiche et le mauvais pour un direct qui tourne pendant
    qu'une session SAP est pilotee — la levee serait avalee par
    `_Parcours.emettre`, comptee en panne d'affichage a chaque fait, et
    l'ecran accuserait le terminal. Ici la place manquante se paie en `~`,
    c'est-a-dire visiblement.

    Le partage cesse en dessous de vingt-huit colonnes : `reste` y devient nul
    ou negatif, les deux chemins tombent a un caractere chacun, et c'est
    `couper` — qui coupe A DROITE — qui tranche la ligne composee. Le
    catalogue disparait alors entierement. C'est mesure, ce n'est pas
    rattrape, et c'est dit ici plutot que promis a l'envers : une fenetre de
    vingt colonnes n'a la place d'aucun des deux chemins.
    """
    largeur = max(gabarit.colonnes - MARGE, 1)
    tete, fleche = "FALCON explorer  ·  ", "  ->  "
    reste = largeur - len(tete) - len(fleche)
    pour_la_trace = max(reste * 3 // 5, 1)
    trace = couper_chemin(cadran.trace or "?", pour_la_trace)
    cible = couper_chemin(cadran.catalogue or "?",
                          max(reste - pour_la_trace, 1))
    lignes: list[Bloc] = []
    if gabarit.niveau == COULEUR:
        lignes.append(Bloc((Fragment(couper(
            "Si les lignes qui suivent sont illisibles : --sans-couleur.",
            largeur)),), marge=MARGE))
    return lignes + [
        Bloc((Fragment(couper(f"{tete}{trace}{fleche}{cible}", largeur),
                       TITRE),), marge=MARGE),
        Bloc((Fragment(couper(
            f"{cadran.systeme or '?'} / {cadran.mandant or '?'} / "
            f"{cadran.langue or '?'}   ·  dry-run fige, plafond de "
            f"sauvegardes 0", largeur), DANGER),), marge=MARGE),
        Bloc((Fragment(couper("Le rang est une POSITION dans la trace, pas un "
                              "avancement : une branche", largeur)),),
             marge=MARGE),
        Bloc((Fragment(couper("qui tombe en emporte plusieurs d'un coup.",
                              largeur)),), marge=MARGE),
        Bloc(forme=SEPARATEUR, marge=MARGE),
    ]


# -- une ligne par fait -----------------------------------------------------

def ligne_evenement(evenement: Evenement, gabarit: Gabarit) -> Bloc | None:
    """Le fait, en une ligne — ou `None` s'il n'en fait pas une.

    Fonction PURE, et c'est ce qui permet aux tests de comparer des chaines
    plutot qu'une capture de terminal. Elle ne connait ni flux, ni console, ni
    couleur : le ton dit ce que la ligne veut dire, et le peintre seul sait ce
    qu'il y a en face.
    """
    if evenement.genre in SANS_LIGNE:
        return None

    largeur = max(gabarit.colonnes - MARGE, 1)
    # Indexation et non `.get` : un genre absent de la table leve ici, au
    # lieu de sortir sans marque et sans ton — c'est-a-dire d'un aspect
    # normal. L'exhaustivite de la table est verifiee par un test.
    marque = MARQUES[evenement.genre]
    # Un rang BLANC quand il n'y a pas de position a montrer. Une seule
    # regle, et trois faits qui l'appellent. `SAUT` porte l'ordre de la branche qui vient d'etre annoncee, et
    # le repeter sur deux lignes de suite ferait croire a deux faits sur le
    # meme geste. `PLAFOND` ne porte pas d'ordre du tout — il porte `index`
    # et `total` — et son `000` se lirait comme la position zero sur l'unique
    # ligne qui cloture une exploration arretee par un budget. Le releve de
    # l'ecran de DEPART est pris avant le premier geste, et les gestes sont
    # numerotes a partir de 001 : il n'existe aucun geste 000. L'en-tete
    # vient de dire que ce nombre est une POSITION dans la trace ; ecrire
    # `000` serait en annoncer une qui n'existe pas.
    rang = ("   " if evenement.genre == E.SAUT or not evenement.ordre
            else f"{evenement.ordre:03d}")
    tete = f"{rang} {marque}  "
    corps = _corps(evenement, max(largeur - len(tete), 1))
    return Bloc((Fragment(couper(tete + corps, largeur),
                          _ton(evenement)),), marge=MARGE)


def _ton(evenement: Evenement) -> str:
    """Le ton de la ligne. Le genre le donne, sauf pour une REPRISE.

    Une reprise ACCEPTEE et une reprise REFUSEE sont deux faits opposes : la
    seconde est ce qui change tout ce qui sera explore ensuite. Les peindre
    pareil au niveau COULEUR serait la seule categorie de ligne du direct a
    perdre sa distinction a l'oeil, et c'est justement celle qui ne doit pas
    la perdre.
    """
    if evenement.genre == E.REPRISE:
        return SUCCES if evenement.acceptee else ALERTE
    return TONS_DU_DIRECT[evenement.genre]


def _corps(evenement: Evenement, largeur: int) -> str:
    """Le texte du fait, sans le rang ni la marque, tronque a `largeur`.

    Chaque genre a sa forme, et les identifiants passent par `couper_chemin` :
    `wnd[0]/usr/ctxtWERKS-LOW` et `wnd[0]/usr/ctxtWERKS-HIGH` coupes a droite
    donnent la meme chaine, d'aspect complet.
    """
    genre = evenement.genre

    if genre == E.ENVOYE:
        prefixe = f"{evenement.verbe:<8} "
        return prefixe + couper_chemin(evenement.cible,
                                       max(largeur - len(prefixe), 1))
    if genre == E.CONFORT:
        prefixe = "confort  "
        return prefixe + couper(evenement.motif or "geste de confort ecarte",
                                max(largeur - len(prefixe), 1))
    if genre == E.VALIDATION:
        return couper("entree deja envoyee par la reprise", largeur)
    if genre in (E.ECRAN_VERSE, E.ECRAN_CONNU):
        return _corps_ecran(evenement, largeur)
    if genre == E.REPRISE:
        verdict = "ACCEPTEE" if evenement.acceptee else "REFUSEE"
        return couper(f"REPRISE  {evenement.reprise or '?'} demandee -> "
                      f"obtenue {evenement.transaction or '?'}   {verdict}",
                      largeur)
    if genre == E.SAUVEGARDE_REFUSEE:
        prefixe = f"REFUSE   {evenement.verbe:<8} "
        return prefixe + couper_chemin(evenement.cible,
                                       max(largeur - len(prefixe), 1))
    if genre == E.BRANCHE:
        prefixe = f"BRANCHE  {evenement.categorie:<16} "
        return prefixe + couper(evenement.motif,
                                max(largeur - len(prefixe), 1))
    if genre == E.SAUT:
        suite = (f"reprise visee {evenement.reprise}" if evenement.reprise
                 else "plus aucun point de reprise")
        return couper(f"saut     {evenement.sautes} geste(s) emportes   ->  "
                      f"{suite}", largeur)
    if genre == E.PLAFOND:
        prefixe = f"PLAFOND  {evenement.motif:<8} "
        return prefixe + couper(evenement.raison or evenement.clef,
                                max(largeur - len(prefixe), 1))
    # Aucun repli en clair : il aurait donne au lecteur l'impression d'une
    # securite que rien n'exerce, et personne ne l'aurait jamais vu tourner.
    # L'exhaustivite est verifiee au lieu d'etre rattrapee — un test exige
    # `set(GENRES) == set(MARQUES) | SANS_LIGNE`, et il tombe le jour de
    # l'oubli, ce qu'un repli n'aurait pas fait. Ici, un refus : mieux vaut
    # lever pendant la mise au point qu'inventer une ligne plausible.
    raise ValueError(
        f"genre sans forme de ligne : {genre!r}. Les genres qui font une "
        f"ligne sont ceux de `MARQUES` moins `SANS_LIGNE` ; en ajouter un "
        f"demande de dire ICI ce qu'il affiche.")


def _corps_ecran(evenement: Evenement, largeur: int) -> str:
    """La ligne d'un ecran releve. L'empreinte y est COURTE, et le dit.

    Huit caracteres sur seize, SUIVIS DE LA MARQUE — `#e1cded0d~` et non
    `#e1cded0d`. C'est ce qu'on recopie a l'oeil pour retrouver la variante
    dans la quarantaine, et le fichier porte l'empreinte entiere. Les couper
    sans marque donnerait deux empreintes d'aspect complet : deux variantes
    qui partagent huit chiffres hexadecimaux seraient indiscernables a
    l'ecran, et surtout la ceremonie de promotion exige l'empreinte EN
    TOUTES LETTRES — celui qui recopie les huit chiffres lus ici serait
    refuse sans savoir pourquoi. La marque est la regle de
    `falcon.toile.fragment` : la troncature est le seul endroit ou ce module
    peut perdre du contenu, elle laisse donc TOUJOURS une trace.
    """
    triplet, _, empreinte = evenement.clef.partition("#")
    verdict = ("verse" if evenement.genre == E.ECRAN_VERSE else "deja connu")
    compte = (f"   {evenement.versees}/{evenement.plafond_ecrans}"
              if evenement.genre == E.ECRAN_VERSE else "")
    queue = (f"  {verdict}  {evenement.fenetre or '?'}  "
             f"{evenement.champs} ch{compte}")
    prefixe = "ECRAN    "
    reste = max(largeur - len(prefixe) - len(queue), 8)
    court = f"{triplet} #{empreinte[:8]}{MARQUE}" if empreinte else triplet
    return prefixe + couper_chemin(court, reste) + queue


# -- la ligne collante ------------------------------------------------------

def ligne_collante(cadran: Cadran, gabarit: Gabarit) -> str:
    """Le bandeau, en une chaine sans saut de ligne, TRONQUEE a la largeur.

    **La troncature est le point de ce module.** `Rapporteur._ecrire` fait un
    `ljust` sans coupe : une ligne plus large que la fenetre s'y replie, et le
    `\\r` suivant revient au debut de la ligne REPLIEE. L'effacement laisse
    alors la moitie du bandeau precedent a l'ecran, definitivement, et rien ne
    le signale. `gabarit.colonnes` vaut deja la mesure moins une colonne : ce
    qui sort d'ici ne remplit donc jamais la derniere colonne de la fenetre.

    La jauge est la premiere chose qu'on sacrifie quand la place manque : elle
    redit, en dessin, ce que la fraction dit en chiffres. Mais le sacrifice ne
    rend une ligne COMPLETE que dans une bande etroite de largeurs — mesure :
    de 60 a 72 colonnes. En dessous, le retrait de la jauge ne suffit plus et
    c'est `couper` qui tranche : a 40 colonnes il ne reste que
    `[geste 034/090]  actions 021/500  ecr~`, sans horloge et sans fraction
    d'ecrans. Ecrire « la jauge saute » comme si la ligne tenait alors
    entiere serait faire dire au code plus qu'il ne fait.
    """
    rang = f"[geste {cadran.ordre:03d}/{cadran.total:03d}]"
    actions = (f"actions {cadran.actions:03d}/{cadran.plafond_gestes:03d}")
    ecrans = f"ecrans {cadran.versees:03d}/{cadran.plafond_ecrans:03d}"
    horloge = duree(cadran.monotone_ms)
    barre = jauge(cadran.actions, cadran.plafond_gestes)

    complet = (f"{' ' * MARGE}{rang}  {actions} {barre}  {ecrans}  {horloge}"
               if barre else
               f"{' ' * MARGE}{rang}  {actions}  {ecrans}  {horloge}")
    if len(complet) > gabarit.colonnes and barre:
        complet = f"{' ' * MARGE}{rang}  {actions}  {ecrans}  {horloge}"
    return couper(complet, gabarit.colonnes)


# -- le bilan ---------------------------------------------------------------

@dataclass(frozen=True)
class Justification:
    """Une valeur du bilan, et OU le compte rendu la confirme.

    `repere` est ce qui doit se lire sur la MEME ligne du compte rendu que la
    valeur. Sur la meme ligne, et non quelque part dans le document : sur 127
    lignes de prose, le chiffre « 5 » se trouve partout, et un test qui se
    contenterait d'une sous-chaine serait vert quoi qu'on affiche.

    `absent_si_zero` est le troisieme etat, et il existe parce que le compte
    rendu ne nomme pas ce qui n'a pas eu lieu : `rapport.rendre` n'ecrit le
    bloc des branches que `if exploration.branches`, celui des reprises que
    `if exploration.reprises`, et `_partition` n'ecrit une ligne que
    `if compte`. Sur un rejeu qui va au bout sans incident — la forme la plus
    courante, mesuree sur une trace de deux gestes — ces trois reperes sont
    introuvables dans le compte rendu. La valeur affichee (zero) reste vraie ;
    c'est la GARANTIE qui cederait si on n'en disait rien. Le test ne se
    contente donc pas d'exempter : quand la valeur vaut zero il exige que le
    repere soit ABSENT du compte rendu, et quand elle ne vaut pas zero il
    exige l'appariement comme pour les autres. L'exemption est mesuree des
    deux cotes.
    """

    etiquette: str
    valeur: str
    repere: str
    absent_si_zero: bool = False


def justifications(cadran: Cadran) -> tuple[Justification, ...]:
    """Tout ce que le bilan AFFIRME, et ou le compte rendu le dit.

    C'est la liste que le test apparie ligne a ligne avec `rapport.rendre`. Y
    ajouter une entree sans repere reel la ferait tomber ; afficher un chiffre
    sans l'inscrire ici la fait tomber aussi, par l'autre bout — le test
    verifie qu'aucun nombre du bilan ne sort de cette liste.

    Les deux plafonds n'y sont pas : ils ne sont pas des mesures, ce sont les
    budgets que l'utilisateur a tapes lui-meme sur la ligne de commande, et le
    compte rendu ne les rappelle que s'ils ont mordu.

    Trois entrees portent `absent_si_zero` : le compte rendu ne nomme leur
    repere que si le fait a eu lieu. « chaque valeur nomme son repere » reste
    vrai ; ce qui change est que pour ces trois-la, a zero, le repere doit
    etre INTROUVABLE — et c'est ce que le test verifie, sur une trace qui va
    au bout sans incident autant que sur la megatrace.
    """
    return (
        Justification("systeme", cadran.systeme or "?", "systeme"),
        Justification("mandant", cadran.mandant or "?", "mandant"),
        Justification("langue", cadran.langue or "?", "langue"),
        Justification("etat", cadran.etat or "?", "etat"),
        Justification("actions envoyees au driver", str(cadran.actions),
                      "actions envoyees au driver"),
        Justification("ecrans verses en quarantaine", str(cadran.versees),
                      "verses en quarantaine"),
        Justification("deja connus", str(cadran.connues), "deja connus"),
        Justification("branches tombees", str(cadran.branches),
                      "branches interrompues", absent_si_zero=True),
        Justification("dont sauvegardes refusees",
                      str(cadran.sauvegardes_refusees), "refusee(s) sur"),
        Justification("reprises tapees", str(cadran.reprises), "reprises (",
                      absent_si_zero=True),
        Justification("gestes emportes par un saut", str(cadran.sautes),
                      "sautes", absent_si_zero=True),
    )


def bilan(cadran: Cadran, gabarit: Gabarit) -> list[Bloc]:
    """Ce que le direct a vu passer, et rien de plus.

    Chaque chiffre d'ici vient de `justifications` — donc d'une ligne du
    compte rendu, ou, pour les trois compteurs marques `absent_si_zero`, d'un
    repere que le compte rendu tait tant que le fait n'a pas eu lieu. Aucun
    n'est calcule ici. La derniere phrase renvoie au compte rendu
    explicitement : la partition des
    gestes ne somme qu'a la fin, et c'est le compte rendu qui fait foi.
    """
    largeur = max(gabarit.colonnes - MARGE, 1)
    par_etiquette = {j.etiquette: j.valeur for j in justifications(cadran)}

    def _valeur(etiquette: str) -> str:
        return par_etiquette[etiquette]

    lignes: list[Bloc] = [
        Bloc((Fragment("DIRECT — bilan de la cartographie", TITRE),),
             forme=ENTETE, marge=MARGE),
        Bloc((Fragment(couper(
            f"systeme {_valeur('systeme')}   "
            f"mandant {_valeur('mandant')}   "
            f"langue {_valeur('langue')}        "
            f"duree {duree(cadran.monotone_ms)}", largeur)),), marge=MARGE + 2),
        Bloc((Fragment(couper(f"etat  {_valeur('etat')}", largeur)),),
             marge=MARGE + 2),
        Bloc(forme=VIDE),
        _compteur("actions envoyees au driver", _valeur(
            "actions envoyees au driver"), cadran.plafond_gestes, largeur),
        _compteur("ecrans verses en quarantaine",
                  _valeur("ecrans verses en quarantaine"),
                  cadran.plafond_ecrans, largeur,
                  suffixe=f"        deja connus  {_valeur('deja connus')}"),
        _compteur("branches tombees", _valeur("branches tombees"), 0, largeur,
                  suffixe=f"   dont sauvegardes refusees  "
                          f"{_valeur('dont sauvegardes refusees')}"),
        _compteur("reprises tapees", _valeur("reprises tapees"), 0, largeur),
        _compteur("gestes emportes par un saut",
                  _valeur("gestes emportes par un saut"), 0, largeur),
        Bloc(forme=VIDE),
        Bloc((Fragment(couper("Le decompte des gestes de la trace est dans le "
                              "compte rendu ci-dessous :", largeur)),),
             marge=MARGE),
        Bloc((Fragment(couper("la partition ne somme qu'a la fin, et c'est lui "
                              "qui fait foi.", largeur)),), marge=MARGE),
        Bloc(forme=SEPARATEUR, marge=MARGE),
    ]
    return lignes


def _compteur(etiquette: str, valeur: str, plafond: int, largeur: int, *,
              suffixe: str = "") -> Bloc:
    """Une ligne « etiquette  valeur / plafond  suffixe ».

    Le plafond n'est ecrit que s'il en est un : un « / 0 » se lirait comme un
    budget epuise, alors qu'il veut dire « personne n'en a declare ».
    """
    fraction = f"{valeur:>4} / {plafond}" if plafond > 0 else f"{valeur:>4}"
    return Bloc((Fragment(couper(f"{etiquette:<30}{fraction}{suffixe}",
                                 largeur)),), marge=MARGE + 2)


# -- les deux sorties -------------------------------------------------------

class Diffuseur:
    """Le direct sur un flux : le flux de faits, et le bandeau collant.

    S'utilise comme `observateur=`. Le FLUX sort toujours — c'est du texte
    entier, et `falcon explorer ... 2> journal.txt` doit donner un fichier qui
    se lit tel quel. Le BANDEAU, lui, exige les deux choses dont il depend :
    un terminal, ou le retour chariot repositionne le curseur, et une largeur
    MESUREE, faute de quoi une ligne trop longue se replierait et l'effacement
    laisserait la moitie du bandeau precedent a l'ecran pour toujours.

    **Rien n'est rattrape ici.** Un flux qui se ferme, un peintre qui leve :
    `_Parcours.emettre` enveloppe deja chaque appel, compte les pannes et le
    dit au compte rendu. Attraper une seconde fois ici rendrait ce compte
    faux, et le compte rendu affirmerait par son silence qu'on a tout vu.

    **Avec une exception, et elle est nommee : `clore`.** Elle n'est pas
    appelee par le parcours — elle l'est par le `finally` de
    `commandes/principal.py:_explorer` et par `console/ecrans.py`, APRES que
    le parcours a rendu la main — donc `emettre` ne l'enveloppe pas. Et elle
    ECRIT : sur un flux qui s'est ferme en cours de route, elle leve. Depuis
    un `finally`, cette levee sauterait par-dessus l'impression du compte
    rendu, c'est-a-dire du seul endroit ou vivent la partition, les branches,
    les reprises et les visites non atteintes — sur une exploration qui a
    DEJA agi dans SAP. Ce sont donc ses DEUX appelants qui l'enveloppent,
    chacun avec la raison ecrite sur place, et c'est le compte rendu qui
    passe en premier. Ecrire ici « rien n'est rattrape » sans cette phrase
    serait une docstring qui affirme plus que le code ne fait, quatre lignes
    au-dessus du code qui la dement.
    """

    def __init__(self, flux: TextIO, capacites: Capacites, *,
                 forcer_nu: bool = False):
        self._flux = flux
        self._gabarit = gabarit_pour(capacites, forcer_nu=forcer_nu)
        self._peintre = peintre_pour(capacites, forcer_nu=forcer_nu)
        self._cadran = Cadran()
        self._largeur_posee = 0
        self._clos = False

        #: Le bandeau demande les DEUX : un terminal et une mesure. Ni l'un
        #: sans l'autre — un bandeau dans un fichier est un plat de `\r`, un
        #: bandeau sans largeur connue est une ligne qui se replie.
        self.bandeau = bool(capacites.interactif and self._gabarit.mesuree)

    def __call__(self, evenement: Evenement) -> None:
        self._cadran = avancer(self._cadran, evenement)
        if evenement.genre == E.DEPART:
            self._poser(entete(self._cadran, self._gabarit))
        bloc = ligne_evenement(evenement, self._gabarit)
        if bloc is not None:
            self._poser([bloc])
        self._redessiner()

    def _poser(self, blocs: list[Bloc]) -> None:
        """Ecrit des lignes entieres, apres avoir efface le bandeau.

        L'effacement d'abord : sans lui, la ligne de fait s'ecrirait par-dessus
        le bandeau, dont la queue resterait accrochee a droite.
        """
        self._effacer()
        for bloc in blocs:
            for ligne in self._peintre.peindre(bloc, self._gabarit):
                self._flux.write(ligne + "\n")
        self._flux.flush()

    def _redessiner(self) -> None:
        if not self.bandeau:
            return
        texte = ligne_collante(self._cadran, self._gabarit)
        # Le remplissage ne peut pas depasser la largeur : la ligne precedente
        # etait elle-meme tronquee au gabarit.
        self._flux.write("\r" + texte.ljust(self._largeur_posee))
        self._largeur_posee = max(self._largeur_posee, len(texte))
        self._flux.flush()

    def _effacer(self) -> None:
        if not self.bandeau or not self._largeur_posee:
            return
        self._flux.write("\r" + " " * self._largeur_posee + "\r")

    def clore(self) -> None:
        """Efface le bandeau et pose le bilan. Idempotente.

        Idempotente parce qu'elle est appelee depuis un `finally` : une
        exploration qui leve doit quand meme rendre son terminal propre, et
        celle qui n'a pas leve ne doit pas poser deux bilans.

        Elle LEVE si le flux s'est ferme, comme tout le reste de cette
        classe — et c'est son appelant, seul, qui decide quoi en faire. Voir
        la docstring de la classe : ce sont les deux `finally` qui
        l'enveloppent, parce que c'est la, et seulement la, qu'on sait que le
        compte rendu vaut plus qu'un bandeau qu'on n'arrive plus a effacer.
        """
        if self._clos:
            return
        self._clos = True
        self._effacer()
        self._largeur_posee = 0
        if not self._cadran.commence:
            # Rien n'a commence : pas de bilan d'une exploration qui n'a pas
            # eu lieu. Un bilan a zero se lirait comme une exploration vide.
            self._flux.flush()
            return
        for bloc in bilan(self._cadran, self._gabarit):
            for ligne in self._peintre.peindre(bloc, self._gabarit):
                self._flux.write(ligne + "\n")
        self._flux.flush()


class EnConsole:
    """Le direct au travers de `Console.ecrire` — une ligne, un appel.

    Aucun bandeau, et le prix est ECRIT a l'ecran plutot que tu : `ecrire`
    vaut `print`, il pose une ligne entiere, et reprendre une ligne deja posee
    demanderait de sortir de l'injection qui rend toute la console testable.
    Le gain — voir SAP travailler PENDANT qu'il travaille — se paie en ligne
    de commande, et l'en-tete le dit.

    Le peintre et le gabarit sont fournis par l'appelant : cette classe ne
    sonde rien. C'est l'ecran de console qui sait de quelles capacites il
    dispose, et tant que rien ne les mesure elles sont toutes fausses, donc le
    niveau est NU et aucune sequence n'atteint `Console.ecrire`.
    """

    def __init__(self, console: "Console", peintre: Peintre,
                 gabarit: Gabarit):
        self._console = console
        self._peintre = peintre
        self._gabarit = gabarit
        self._cadran = Cadran()
        self._clos = False

    def __call__(self, evenement: Evenement) -> None:
        self._cadran = avancer(self._cadran, evenement)
        if evenement.genre == E.DEPART:
            self._poser(entete(self._cadran, self._gabarit))
            self._poser(_PRIX_DE_LA_CONSOLE)
        bloc = ligne_evenement(evenement, self._gabarit)
        if bloc is not None:
            self._poser([bloc])

    def _poser(self, blocs: list[Bloc]) -> None:
        for bloc in blocs:
            for ligne in self._peintre.peindre(bloc, self._gabarit):
                self._console.ecrire(ligne)

    def clore(self) -> None:
        """Pose le bilan. Idempotente, et muette sur ce qui n'a pas commence.

        Les deux garde-fous du `Diffuseur`, pour les deux memes raisons, et
        chacun a son test de ce cote-ci aussi : deux `clore()` poseraient deux
        bilans sous les yeux de l'operateur, et un bilan pose sur une
        exploration qui n'a jamais commence — un `connecter()` qui leve avant
        le premier ecran, chemin que `_cartographier` emprunte pour de bon —
        ecrirait « actions 0, ecrans 0 » sur une exploration qui n'a rien
        TENTE, ce qui se lit comme une exploration qui n'a rien TROUVE.
        """
        if self._clos or not self._cadran.commence:
            self._clos = True
            return
        self._clos = True
        self._poser(bilan(self._cadran, self._gabarit))


#: Ce que la console ne peut pas faire, ecrit a l'endroit ou l'on s'en apercoit.
#:
#: Une interface qui tait sa limite laisse conclure qu'elle est en panne : le
#: direct de la console n'affiche un geste qu'une fois qu'il est FAIT, et
#: pendant un `press` de dix secondes l'ecran ne bouge pas. Dire pourquoi, et
#: dire ou se trouve l'autre, coute quatre lignes.
_PRIX_DE_LA_CONSOLE = [
    Bloc((Fragment("Le direct suit. La console affiche un geste une fois "
                   "qu'il est FAIT :"),), marge=MARGE),
    Bloc((Fragment("elle ne peut pas reprendre une ligne deja posee. Pour "
                   "voir SAP travailler"),), marge=MARGE),
    Bloc((Fragment("pendant qu'il travaille, c'est `python -m falcon "
                   "explorer` en ligne de"),), marge=MARGE),
    Bloc((Fragment("commande."),), marge=MARGE),
    Bloc(forme=SEPARATEUR, marge=MARGE),
]
