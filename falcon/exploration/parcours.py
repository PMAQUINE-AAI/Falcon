"""Rejouer une trace en OBSERVATION, et verser chaque ecran distinct.

C'est l'etape 2 du cycle de vie (`SPEC_FALCON.md:159`) : « FALCON rejoue la
trace en mode observation, dumpe chaque ecran traverse et alimente le
catalogue. » Jusqu'ici le catalogue ne se peuplait que par `diagnostiquer`,
un ecran a la fois, a la main.

**C'est la chose la plus dangereuse que FALCON fasse** : piloter un ERP depuis
un enregistrement, sans qu'un humain ait valide chaque geste. Six refus la
bornent, et aucun n'est un parametre.

1. **Aucune sauvegarde, par le mecanisme qui existe deja.** Le driver est
   enveloppe dans `DriverGarde(mode="dry-run", plafond_sauvegardes=0)`. Tout
   `vkey(11)`, tout `press` sur `tbar[0]/btn[11]` leve `RefusDryRun` avant que
   le driver brut ne soit touche, et le plafond a zero est la ceinture si le
   mode etait un jour errone. `MODE` et `PLAFOND_SAUVEGARDES` sont des
   constantes de module et **ne figurent pas dans la signature d'`explorer`** :
   un defaut se change en un mot sur une ligne de commande, par quelqu'un qui
   veut « juste voir ».

2. **La garde d'identite est desarmee, et c'est le seul endroit ou ce soit
   juste.** On explore parce qu'on ne sait pas quel ecran vient. Le contrat
   porte `navigation_libre=True`, ce qui laisse un constat par geste.

3. **La fenetre imprevue est l'objet de la sortie, pas une violation** — mais
   par une DEROGATION nommee et motivee, pas par un elargissement de
   `fenetres_attendues`. La difference se mesure : un elargissement emet un
   constat a la pose du contrat puis se tait, la derogation en emet un par
   action, avec la liste des intruses. Une modale surgie serait invisible
   autrement, et c'est precisement ce qu'on vient observer.

4. **Les gardes de statut et de relecture restent ARMEES.** Le statut est la
   seule chose que SAP dit ; y deroger rendrait l'exploration aveugle. Un
   incident bloquant n'arrete pas l'exploration : il arrete la BRANCHE.

5. **On ne repart que sur un code transaction qu'on a tape soi-meme, valide
   par Entree, et VERIFIE.** C'est le coeur de ce module et il faut le dire
   en entier : `okcd.text = "/nIW39"` seul ne demarre rien. La transaction ne
   part qu'a Entree. Reprendre la lecture au geste de commande laisserait
   l'Entree a la charge de la trace, et rien ne garantit qu'une trace valide
   ses codes ; sans verification, tous les gestes suivants se rejoueraient sur
   l'ecran precedent — sur des cibles qui existent souvent aussi ailleurs —
   pendant que le rapport annoncerait « IW39 explore ». Aucune exception, un
   resultat plausible, et faux.

6. **Aucune action ACTIVANTE dans une fenetre qu'on vient pas d'identifier.**
   C'est le refus que `DriverGarde` ne porte PAS, et il fallait l'ajouter :
   `_est_sauvegarde` ne connait que `vkey(11)` et le bouton `btn[11]` —
   **Entree n'en fait pas partie, et `usr/btnBUTTON_1` non plus**, alors que
   c'est le nom standard du premier bouton d'une popup generique, donc le
   « Oui » de « Donnees modifiees, enregistrer ? ». Voir `_action_a_l_aveugle`
   pour la regle exacte et son cout mesure.

**Ce que l'assouplissement de la taxonomie coute, et ce qui l'achete.** Le
moteur arrete tout sur un inconnu bloquant, parce que l'action suivante
s'executerait sur un ecran qu'on ne comprend plus, et pourrait ecrire. Ici
l'action suivante n'est pas la suivante de la trace : c'est un retour par code
transaction, verifie, dans une session ou aucune sauvegarde n'est possible. La
branche est abandonnee exactement comme la taxonomie l'exige. **C'est la
verification de la reprise qui achete le droit de continuer ; la retirer
rouvre le trou.**

**Ce que ce module ne peut pas prouver.** Aucune ligne n'a parle a un SAP
reel. « Aucune sauvegarde » ne veut pas dire « sans effet » : l'exploration
presse des boutons, lance des selections qui peuvent tourner longtemps, et
peut poser des verrous en ouvrant une transaction en modification. Personne
ici ne l'a mesure. A lancer sur un mandant de qualite avant la production.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from falcon.catalogue import ClefVariante, Depot, Variante, variante_de
from falcon.controleur import Constat, Contrat, Derogation, DriverGarde
from falcon.controleur.gardes import est_sauvegarde
from falcon.noyau import (
    CHAMP_DE_COMMANDE, Echec, Horloge, PORTEE_TOTALE, Refus, RefusDryRun,
    maintenant,
)
from falcon.taxonomie import INCONNUE, Registre, ecrire_dump
from falcon.trace import Geste, Trace
from falcon.trace.modele import FENETRE_RACINE
from falcon.trace.esquisse import code_transaction, vise_le_champ_de_commande

from .gestes import ARGUMENT_REFUSE, ECARTE_CONFORT, TRADUIT, Traduction
from .gestes import SANS_COUTURE as GENRE_SANS_COUTURE
from .gestes import traduire

if TYPE_CHECKING:                   # annotation seule : voir test_frontieres
    from falcon.couture import Driver

#: Mode et rayon d'action. Des CONSTANTES, pas des parametres : decision 1.
MODE = "dry-run"
PLAFOND_SAUVEGARDES = 0

#: La touche « Entree ». C'est elle qui fait partir la transaction.
VKEY_ENTREE = 0

#: Etat de fin d'une exploration.
TERMINEE = "terminee"           # la trace a ete parcourue jusqu'au bout
INTERROMPUE = "interrompue"     # arret avant la fin, motif dans `raison`
PLAFOND = "plafond"             # un plafond declare a ete atteint
ETATS = (TERMINEE, INTERROMPUE, PLAFOND)

#: Pourquoi une branche s'est arretee.
SANS_COUTURE = "sans_couture"   # verbe sans methode de couture : l'arbre
SANS_REPRISE = "sans_reprise"   # code de commande qui n'est pas /n<transaction>
ARGUMENT = "argument"           # argument que la table refuse de convertir
VERBE = "verbe"                 # verbe absent de la table
SAUVEGARDE = "sauvegarde"       # RefusDryRun : la trace sauvegarde ici
INCIDENT = "incident"           # garde : statut E/A, ecart de relecture...
COUTURE = "couture"             # Echec de la couture : ObjetIntrouvable...
REPRISE_REFUSEE = "reprise_refusee"     # le code tape n'a pas pris
ACTION_AVEUGLE = "action_aveugle"       # activee dans une fenetre non identifiee
MOTIFS = (SANS_COUTURE, SANS_REPRISE, ARGUMENT, VERBE, SAUVEGARDE, INCIDENT,
          COUTURE, REPRISE_REFUSEE, ACTION_AVEUGLE)

#: Codes du champ de commande qui ne demarrent pas une transaction mais
#: agissent sur la SESSION. `_CODE` d'`esquisse` les laisse passer — `/nex`
#: rend « ex » — et les taper terminerait la session pendant que le rapport
#: annoncerait une reprise.
#:
#: La liste est courte a dessein : elle ne contient que ce dont l'effet
#: destructeur est connu. Tout le reste — une faute de frappe comme `/nIW2ç` —
#: est tape et laisse a la VERIFICATION, qui constate que SAP n'a pas suivi.
#: Refuser d'avance sur une regle de forme demanderait d'affirmer ce que SAP
#: accepte, ce que ce depot ne peut pas etablir.
CODES_DE_SESSION = frozenset({"EX", "END", "I", "O", "H", "NEX", "NEND"})

#: La derogation qui fait de la fenetre imprevue une OBSERVATION.
DEROGATION_FENETRE = Derogation(
    garde="fenetre", portee=PORTEE_TOTALE,
    motif=("cartographie : l'ecran suivant est inconnu par construction, une "
           "fenetre imprevue est ce qu'on vient observer, pas une violation. "
           "La garde s'execute et trace a chaque action ; seule l'issue "
           "change"))


class ExplorationImpossible(Exception):
    """La trace ou les plafonds ne permettent pas d'explorer.

    Levee au pre-vol, avant tout contact avec le driver : rien n'a ete tente.
    """


@dataclass(frozen=True)
class Branche:
    """Un endroit ou l'exploration a cesse de suivre la trace, et pourquoi."""

    ordre: int                  # rang du geste parmi les gestes de la trace
    ligne: int                  # rang dans le fichier .vbs
    verbe: str
    categorie: str              # l'un de MOTIFS
    motif: str
    entree: str = ""            # entree de registre appariee, "" si inconnue
    dump: str = ""              # chemin du dump ecrit, "" s'il n'y en a pas
    reprise: str = ""           # transaction ou l'on est reparti, "" si arret


@dataclass(frozen=True)
class Reprise:
    """Un code transaction tape PAR l'explorateur, et ce que SAP en a fait.

    `obtenue` n'est renseignee qu'APRES la lecture de `screen()` : renseigner
    l'une ou l'autre d'apres la trace ferait dire au compte rendu qu'on a mis
    les pieds dans une transaction ou l'on n'est peut-etre jamais alle.
    """

    ordre: int
    ligne: int
    demandee: str
    obtenue: str
    acceptee: bool


@dataclass(frozen=True)
class SauvegardeRefusee:
    """Un geste de la trace qui aurait ecrit dans SAP, et que le dry-run a
    refuse. Compte a part : c'est le chiffre qu'on relit pour se convaincre."""

    ordre: int
    ligne: int
    verbe: str
    cible: str
    texte_source: str


@dataclass(frozen=True)
class Exploration:
    """Ce qu'un parcours rend. Aucun ecran n'y figure : ils sont au depot.

    Les sept compteurs de gestes forment une PARTITION de `gestes_lus` : si
    leur somme ne fait pas le total, le rapport peut annoncer « 34 rejoues »
    sur 90 sans que les 56 autres apparaissent nulle part. `partition_coherente`
    le verifie, et un test l'exerce sur la trace de reference.
    """

    trace: str
    etat: str                                   # l'un de ETATS
    catalogue: str = ""
    raison: str = ""

    versees: tuple[ClefVariante, ...] = ()
    deja_connues: tuple[ClefVariante, ...] = ()
    branches: tuple[Branche, ...] = ()
    reprises: tuple[Reprise, ...] = ()
    sauvegardes_refusees: tuple[SauvegardeRefusee, ...] = ()
    constats: tuple[Constat, ...] = ()
    dumps: tuple[str, ...] = ()

    #: Les ORDRES des gestes que le parcours n'a pas joues, sautes entre une
    #: interruption et le point de reprise suivant. Une liste et pas seulement
    #: un compte : sans elle, le rapport ne peut pas dire que les dix gestes
    #: d'arbre de la trace de reference n'ont jamais ete ATTEINTS — ils sont
    #: sautes bien avant, la branche tombant sur une sauvegarde.
    ordres_sautes: tuple[int, ...] = ()

    #: Les ORDRES des gestes ou le parcours est effectivement PASSE — rejoues,
    #: ecartes comme confort, consommes par une reprise, ou porteurs d'une
    #: branche. Le complement de `ordres_sautes` et de la queue non exploree.
    #:
    #: C'est ce qui permet au rapport de dire quelle VISITE de la trace a ete
    #: atteinte. Le rapprochement se fait par POSITION et jamais par clef :
    #: l'empreinte d'une esquisse porte sur les identifiants TOUCHES, celle
    #: d'un releve sur les identifiants PRESENTS, et les deux ne peuvent pas
    #: coincider (`trace/esquisse.py`). Une difference d'ensembles sur les
    #: `ClefVariante` annoncerait « 35 conjecturees, 0 relevee, 35 restantes »
    #: sur une cartographie parfaitement reussie.
    ordres_atteints: tuple[int, ...] = ()

    gestes_lus: int = 0
    gestes_rejoues: int = 0
    gestes_confort: int = 0
    gestes_interrompus: int = 0
    gestes_de_reprise: int = 0
    validations_consommees: int = 0
    gestes_sautes: int = 0
    gestes_non_explores: int = 0

    actions_envoyees: int = 0
    releves: int = 0

    #: Systeme, mandant et langue LUS sur l'ecran de depart.
    #:
    #: `Identite` les porte depuis le noyau et rien ne les lisait : un compte
    #: rendu de cartographie ne disait donc pas SUR QUOI elle avait agi. Rien
    #: ici ne peut distinguer un bac a sable d'une production — ce depot ne
    #: sait pas quel mandant est lequel — mais il peut le NOMMER, et c'est ce
    #: qu'un humain relit pour s'en apercevoir.
    systeme: str = ""
    mandant: str = ""
    langue: str = ""

    @property
    def interrompue(self) -> bool:
        return self.etat != TERMINEE

    @property
    def au_plafond(self) -> bool:
        return self.etat == PLAFOND

    @property
    def partition(self) -> dict[str, int]:
        return {
            "rejoues": self.gestes_rejoues,
            "confort": self.gestes_confort,
            "interrompus": self.gestes_interrompus,
            "reprises": self.gestes_de_reprise,
            "validations consommees": self.validations_consommees,
            "sautes": self.gestes_sautes,
            "non explores": self.gestes_non_explores,
        }

    @property
    def partition_coherente(self) -> bool:
        return sum(self.partition.values()) == self.gestes_lus


@dataclass(frozen=True)
class Previsualisation:
    """Ce que la trace permet de dire AVANT de toucher SAP.

    Calculee avec les MEMES predicats que le rejeu — `traduire`,
    `_est_sauvegarde`, `_code_de_reprise` — sinon l'ecran de confirmation
    annonce des refus que le rejeu ne fait pas, ou tait ceux qu'il fera.

    **Elle ne predit pas les branches.** Ou une branche tombe depend de ce que
    SAP repond, et personne ici ne le sait. Elle dit ce que la TRACE contient.
    """

    gestes: int = 0
    confort: int = 0
    sauvegardes: tuple[int, ...] = ()       # ordres refuses par le dry-run
    sans_couture: tuple[int, ...] = ()      # ordres des gestes d'arbre
    verbes_inconnus: tuple[int, ...] = ()   # ordres des verbes hors de la table
    sans_reprise: tuple[int, ...] = ()      # ordres des codes de session
    codes: tuple[str, ...] = ()             # transactions nommees, dans l'ordre

    @property
    def reprises_possibles(self) -> int:
        return len(self.codes)


# =========================================================================
# Predicats partages
# =========================================================================

#: Verbe de trace -> nom du geste, tel que le controleur le nomme.
_GESTES = {"sendVKey": "vkey", "press": "press",
           "doubleClickCurrentCell": "grid_double_click"}


def _est_sauvegarde(geste: Geste) -> bool:
    """Ce geste declencherait-il une sauvegarde.

    **Appelle la fonction du controleur, il n'en garde pas de copie.** Elle
    n'est lue ici que pour la PREVISUALISATION : le refus, lui, est prononce
    par `DriverGarde` et par personne d'autre. Une copie aurait fini par
    diverger de l'original — c'est le raisonnement que la decision n°14 tient
    deja pour le code transaction.
    """
    nom = _GESTES.get(geste.verbe)
    if nom is None:
        return False
    n = geste.valeur if isinstance(geste.valeur, int) else 0
    return est_sauvegarde(nom, cible=geste.cible, n=n)


def _code_de_reprise(geste: Geste) -> str:
    """Le code transaction sur lequel on accepte de repartir, ou "".

    Rend "" pour un geste qui ne vise pas le champ de commande, pour `/n` seul
    — qui ne nomme aucune transaction, donc ne se verifie pas — et pour un
    code de SESSION, qui terminerait ou dedoublerait la session.
    """
    code = code_transaction(geste)
    if not code or code.upper() in CODES_DE_SESSION:
        return ""
    if "/" in code or "*" in code:
        # `/n/nex` et `/n*VA01` ne demarrent pas la transaction qu'ils ont
        # l'air de nommer : le premier enchaine une commande de session, le
        # second saute le premier ecran. Dans les deux cas la verification
        # echouerait, mais le geste aurait deja ete tape.
        return ""
    return code


def previsualiser(trace: Trace) -> Previsualisation:
    """Ce que la trace contient, sans toucher a SAP."""
    confort = 0
    ordres_sauvegarde: list[int] = []
    sans_couture: list[int] = []
    inconnus: list[int] = []
    sans_reprise: list[int] = []
    codes: list[str] = []

    for geste in trace.gestes:
        if _est_sauvegarde(geste):
            ordres_sauvegarde.append(geste.ordre)
        if vise_le_champ_de_commande(geste):
            code = _code_de_reprise(geste)
            if code:
                codes.append(code)
            else:
                sans_reprise.append(geste.ordre)
            continue
        traduction = traduire(geste)
        if traduction.genre == ECARTE_CONFORT:
            confort += 1
        elif traduction.genre == GENRE_SANS_COUTURE:
            sans_couture.append(geste.ordre)
        elif traduction.genre != TRADUIT:
            # `verbe inconnu` et `argument refuse` ne sont PAS « sans
            # couture » : le premier se corrige en relisant la trace, le
            # second en la relisant aussi — pas en elargissant la couture.
            # Les confondre annoncerait « geste d'arbre » d'un verbe que le
            # recorder n'a jamais ecrit, ce qui est une affirmation fausse.
            inconnus.append(geste.ordre)

    return Previsualisation(
        gestes=len(trace.gestes), confort=confort,
        sauvegardes=tuple(ordres_sauvegarde), sans_couture=tuple(sans_couture),
        verbes_inconnus=tuple(inconnus),
        sans_reprise=tuple(sans_reprise), codes=tuple(codes))


# =========================================================================
# Le parcours
# =========================================================================

#: Appels de couture qui ACTIVENT : ils peuvent presser un bouton, donc
#: valider une boite de dialogue.
METHODES_ACTIVANTES = ("press", "select", "vkey", "grid_double_click")

#: Appels qui n'attendent aucune cible nommee. Une touche ne designe rien :
#: elle actionne ce que la fenetre au premier plan propose par defaut.
METHODES_AVEUGLES = ("vkey",)


def _fenetre_de(appel) -> str:
    """La fenetre a laquelle cet appel s'adresse.

    Pour une touche, c'est le dernier argument — la couture prend la fenetre
    explicitement. Pour tout le reste, c'est la racine de l'identifiant.
    """
    if appel.methode in METHODES_AVEUGLES:
        return str(appel.arguments[-1])
    trouve = FENETRE_RACINE.match(str(appel.arguments[0]))
    return trouve.group(1) if trouve else ""


def _action_a_l_aveugle(appel, ouvertes: tuple[str, ...],
                        derniere_cible: str) -> str:
    """Motif de refus d'une action portee sur une fenetre inconnue, ou "".

    **C'est le trou que `DriverGarde` ne bouche pas, et il faut le dire en
    entier.** `_est_sauvegarde` (gardes.py) ne connait que trois choses : un
    contrat qui se declare `sauvegarde`, `vkey(11)`, et un `press` sur
    `tbar[0]/btn[11]`. **Entree n'en fait pas partie, et `usr/btnBUTTON_1` non
    plus.** Or Entree sur la boite « Donnees modifiees. Enregistrer ? »
    actionne le bouton par defaut — Oui — et `usr/btnBUTTON_1` EST ce
    bouton-la : c'est le nom SAP standard du premier bouton d'une popup
    generique. Le commentaire de `gardes.py` le dit deja de lui-meme : la
    reconnaissance d'office est « une securite contre l'oubli, pas une
    detection complete ».

    Une pipeline peut vivre avec cette limite : un humain a ecrit chaque etape
    et declare `sauvegarde` la ou elle sauve. Une exploration, non — personne
    n'a valide un seul de ses gestes. Elle doit donc etre PLUS stricte que le
    controleur, et c'est ici que ca se joue.

    **La regle : on n'ACTIVE rien dans une fenetre qu'on vient pas
    d'identifier.** Une action activante visant une fenetre autre que `wnd[0]`
    n'est envoyee que si l'action PRECEDENTE parvenue au driver a nomme un
    controle de cette meme fenetre et l'a atteint.

    « Precedente », et non « une fois quelque part avant » : une modale fermee
    puis rouverte n'est pas la meme boite, et rien ne dit qu'elle porte les
    memes controles. Se fier a `windows()` pour detecter la fermeture
    demanderait au surplus de savoir QUAND SAP ferme une modale — ce que ce
    depot ne sait pas et refuse de conjecturer.

    **Ce que cela etablit, exactement.** Pas que la boite est celle de
    l'enregistrement — rien ici ne peut l'etablir. Cela etablit que la fenetre
    ouverte porte le controle que la trace y nommait au meme point de la
    sequence, ce qui est un fait OBSERVE : une boite de confirmation
    d'enregistrement ne porte pas `usr/txtV-LOW`, et l'ecriture aurait leve
    avant qu'on en arrive au bouton.

    **Pourquoi une ecriture peut s'y risquer et pas un bouton.** Un `write`
    qui tombe sur la mauvaise boite ne resout pas : il leve, la branche tombe,
    rien n'est arrive. Un `press` ou une touche qui tombent sur la mauvaise
    boite REUSSISSENT — c'est toute la difference, et c'est pourquoi la
    premiere action dans une modale doit etre une action qui nomme.

    Une touche adressee a `wnd[0]` exige en plus que `wnd[0]` soit la SEULE
    fenetre ouverte : c'est la fenetre au premier plan qui recevrait la
    frappe, et ce ne serait pas celle que la trace visait.

    **Cout mesure sur la trace de reference, et il n'est pas nul :** neuf
    gestes rejoues en moins (32 -> 23), zero ecran verse en moins. Les refus
    portent sur des `press` dans `wnd[1]` qui suivent immediatement une
    Entree dans cette meme fenetre — l'Entree a pu changer la boite, donc le
    bouton suivant est presse a l'aveugle au sens strict.

    Ce cout est assume : un refus vaut toujours mieux qu'un enregistrement
    qu'on ne saurait pas avoir declenche. Il se paie en ecrans qu'il faudra
    aller relever a la main, ce que le rapport nomme.
    """
    if appel.methode not in METHODES_ACTIVANTES:
        return ""
    fenetre = _fenetre_de(appel)
    if fenetre != "wnd[0]":
        if not derniere_cible.startswith(f"{fenetre}/"):
            return (f"{appel.methode} dans {fenetre!r}, alors que la derniere "
                    f"action parvenue au driver visait "
                    f"{derniere_cible or 'aucune cible'!r}. Une action qui "
                    f"ACTIVE reussit sur n'importe quelle boite : si "
                    f"l'exploration a diverge et que celle-ci est « Donnees "
                    f"modifiees, enregistrer ? », le bouton presse vaut Oui. "
                    f"Une ecriture, elle, aurait leve — c'est pourquoi la "
                    f"premiere action dans une modale doit nommer un champ")
        return ""
    if appel.methode in METHODES_AVEUGLES and ouvertes != ("wnd[0]",):
        intruses = [f for f in ouvertes if f != "wnd[0]"]
        return (f"touche destinee a wnd[0] alors que {intruses} est/sont "
                f"ouverte(s) : c'est la fenetre au premier plan qui la "
                f"recevrait, et ce n'est pas celle que la trace visait")
    return ""


def _contrat(geste: Geste) -> Contrat:
    """Un contrat PAR GESTE, nomme, plutot qu'un seul pour tout le parcours.

    `Contrat.relachements` est trace a la pose : un contrat unique donnerait
    deux constats pour toute l'exploration, et le detail des constats de
    fenetre porterait `etape: exploration` — impossible de savoir quel geste a
    fait surgir quelle modale. Le bruit est ici la matiere premiere du compte
    rendu ; c'est `rapport.py` qui le resume.
    """
    return Contrat(nom=f"geste {geste.ordre:03d} ({geste.verbe})",
                   navigation_libre=True,
                   derogations=(DEROGATION_FENETRE,))


class _Parcours:
    """L'etat d'un rejeu. Une classe pour ne pas passer douze compteurs.

    Rien ici n'est public : `explorer` est la seule entree.
    """

    def __init__(self, trace: Trace, brut: "Driver", *,
                 catalogue: str | Path, plafond_gestes: int,
                 plafond_ecrans: int, registre: Registre,
                 horloge: Horloge = maintenant):
        self.trace = trace
        self.gestes = trace.gestes
        self.plafond_gestes = plafond_gestes
        self.plafond_ecrans = plafond_ecrans
        self.horloge = horloge

        self.catalogue = Path(catalogue)
        self.depot = Depot(self.catalogue)
        self.quarantaine = Depot(self.depot.quarantaine)
        self.dossier_dumps = self.catalogue / "dumps"

        self.constats: list[Constat] = []
        self.garde = DriverGarde(
            brut, registre, mode=MODE,
            plafond_sauvegardes=PLAFOND_SAUVEGARDES,
            noter=self.constats.append)

        self.vues: set[ClefVariante] = set()
        self.versees: list[ClefVariante] = []
        self.deja_connues: list[ClefVariante] = []
        self.branches: list[Branche] = []
        self.ordres_sautes: list[int] = []
        self.ordres_atteints: list[int] = []
        self.reprises: list[Reprise] = []
        self.sauvegardes: list[SauvegardeRefusee] = []
        self.dumps: list[str] = []

        self.rejoues = 0
        self.confort = 0
        self.interrompus = 0
        self.gestes_de_reprise = 0
        self.validations = 0
        self.sautes = 0
        self.actions = 0
        self.releves = 0

        #: Pose des que `relever` a du renoncer a verser. Un booleen plutot
        #: qu'une exception : le plafond n'est pas une erreur, c'est une fin.
        #: Et un booleen ne peut pas etre avale par un `except` trop large.
        self.plafond_ecrans_atteint = False

        #: Index du geste dont l'Entree a deja ete envoyee par une reprise.
        self.validation_consommee: int | None = None

        #: Identifiant NOMME de la derniere action parvenue au driver.
        #: Une action ACTIVANTE la remet a "" : elle aurait reussi sur
        #: n'importe quelle boite, donc elle n'identifie rien.
        self.derniere_cible = ""

    # -- releve ------------------------------------------------------------

    def relever(self) -> bool:
        """Releve TOUTES les fenetres ouvertes. Rend False si le plafond tombe.

        Toutes les fenetres, pas seulement `wnd[0]` : la moitie de la trace de
        reference se passe dans `wnd[1]`, et un releve restreint a la fenetre
        principale ne verrait aucune boite de selection de variante.

        Le dedoublonnage porte sur la `ClefVariante` — donc sur les champs
        PRESENTS, pas sur le seul triplet : deux variantes du meme dynpro ne se
        distinguent que par la, et le catalogue existe pour les variantes.

        Trois barrieres avant tout versement : les clefs deja vues dans ce
        parcours, le catalogue CURE, et la quarantaine. La consultation du
        catalogue cure est celle qui compte : sans elle, un ecran qu'un humain
        a relu et promu reapparaitrait en quarantaine au parcours suivant.

        **La limite qu'il faut connaitre, et que l'explorateur MULTIPLIE.**
        `fields(fenetre)` rend un `Ecran` dont l'identite est celle de
        `screen()` — c'est-a-dire de la fenetre PRINCIPALE. Le releve d'une
        modale porte donc le programme et le dynpro de l'ecran de DESSOUS, et
        la `Variante` ne porte pas la fenetre : une modale et l'ecran qui la
        porte deviennent deux variantes du meme triplet, distinguees par leur
        seule empreinte, et rien dans le YAML ne dit laquelle etait la modale.

        La limite prexiste — `diagnostiquer --fenetre wnd[1] --catalogue` fait
        deja cela — mais elle etait rare et devient courante : la moitie de la
        trace de reference se passe dans `wnd[1]`. Elle est signalee au
        rapport plutot que corrigee en douce ici, parce que la corriger veut
        dire ajouter la fenetre a `ClefVariante`, donc changer toutes les
        empreintes deja ecrites.
        """
        self.releves += 1
        for fenetre in self.garde.windows():
            ecran = self.garde.fields(fenetre.id)
            variante = variante_de(ecran)
            if not variante.capture_le:
                # Un releve sans date est indistinguable d'un ecran arrive de
                # nulle part. `diagnostiquer` remplit deja le champ quand
                # `fields()` ne l'a pas fait.
                variante = Variante(
                    clef=variante.clef, champs=variante.champs,
                    titre=variante.titre, capture_le=self.horloge(),
                    source=variante.source)
            clef = variante.clef
            if clef in self.vues:
                continue
            self.vues.add(clef)
            if (self.depot.pour_edition(clef) is not None
                    or self.quarantaine.pour_edition(clef) is not None):
                self.deja_connues.append(clef)
                continue
            if len(self.versees) >= self.plafond_ecrans:
                # AVANT le versement, jamais apres : un plafond verifie apres
                # coup laisse passer un ecran de plus que celui annonce.
                self.plafond_ecrans_atteint = True
                return False
            self.depot.mettre_en_quarantaine(variante)
            self.versees.append(clef)
        return True

    # -- incidents ---------------------------------------------------------

    def _dernier_constat_bloquant(self) -> Constat | None:
        for constat in reversed(self.constats):
            if constat.taxonomie is not None:
                return constat
        return None

    def _dump_si_inconnu(self) -> tuple[str, str]:
        """(chemin du dump, entree appariee) pour le dernier incident classe.

        La SIGNATURE est ecrite, pas seulement le detail : c'est elle que le
        registre apparie, et la reconstruire depuis `detail` est une conjecture
        fausse — `garde` porte le NOM de la garde, pas le canal. C'est ce dump
        que `falcon recolter` lit pour proposer l'entree manquante.
        """
        constat = self._dernier_constat_bloquant()
        if constat is None or constat.taxonomie is None:
            return "", ""
        verdict = constat.taxonomie
        if verdict.categorie != INCONNUE:
            return "", verdict.entree or ""
        chemin = str(ecrire_dump(
            self.dossier_dumps,
            {"trace": self.trace.source, "garde": constat.garde,
             "signature": (asdict(constat.signature)
                           if constat.signature is not None else None),
             "detail": constat.detail},
            nom="exploration", horloge=self.horloge))
        self.dumps.append(chemin)
        return chemin, verdict.entree or ""

    # -- reprise -----------------------------------------------------------

    def _prochaine_reprise(self, depart: int) -> int | None:
        """L'index du prochain geste sur lequel on accepte de repartir.

        `depart` est STRICTEMENT apres le geste qui a echoue : sans cela, deux
        codes refuses se renverraient la balle et l'exploration tournerait en
        rond sur un SAP qui refuse a chaque fois.
        """
        for index in range(depart, len(self.gestes)):
            if _code_de_reprise(self.gestes[index]):
                return index
        return None

    def _reprendre(self, index: int) -> Reprise | None:
        """Tape le code, valide par Entree, et VERIFIE qu'il a pris.

        Rend `None` si la reprise n'a meme pas pu etre tentee — une fenetre
        autre que `wnd[0]` est ouverte, et le champ de commande n'y est pas
        atteignable. Fermer la modale demanderait d'inventer un geste que la
        trace ne contient pas.
        """
        geste = self.gestes[index]
        code = _code_de_reprise(geste)
        ouvertes = tuple(f.id for f in self.garde.windows())
        if ouvertes != ("wnd[0]",):
            return None

        with self.garde.sous_contrat(_contrat(geste)):
            # `CHAMP_DE_COMMANDE`, l'identifiant COMPLET, et non `geste.cible` :
            # le suffixe sert a reconnaitre le champ dans une trace, pas a y
            # ecrire.
            self.garde.write(CHAMP_DE_COMMANDE, str(geste.valeur))
            self.actions += 1
            self.garde.vkey(VKEY_ENTREE, "wnd[0]")
            self.actions += 1
        self.derniere_cible = ""

        self.relever()
        obtenue = self.garde.screen().transaction
        # Le mot ENTIER, des deux cotes : « IW3 » apparierait « IW39 », et
        # « IH0 » apparierait « IH06 » comme « IH08 ».
        acceptee = obtenue.strip().upper() == code.strip().upper()
        return Reprise(ordre=geste.ordre, ligne=geste.ligne, demandee=code,
                       obtenue=obtenue, acceptee=acceptee)

    # -- un geste ----------------------------------------------------------

    def executer(self, traduction: Traduction) -> None:
        """Envoie l'appel au driver garde, sous le contrat de ce geste."""
        appel = traduction.appel
        assert appel is not None                    # garanti par le genre
        with self.garde.sous_contrat(_contrat(traduction.geste)):
            getattr(self.garde, appel.methode)(*appel.arguments)
        self.actions += 1
        # Une action qui a NOMME un controle et l'a atteint identifie sa
        # fenetre. Une action activante, elle, n'etablit rien : elle aurait
        # reussi sur n'importe quelle boite.
        self.derniere_cible = ("" if appel.methode in METHODES_ACTIVANTES
                               else str(appel.arguments[0]))


def _branche(geste: Geste, categorie: str, motif: str, *,
             entree: str = "", dump: str = "") -> Branche:
    return Branche(ordre=geste.ordre, ligne=geste.ligne, verbe=geste.verbe,
                   categorie=categorie, motif=motif, entree=entree, dump=dump)


def explorer(trace: Trace,
             brut: "Driver",
             *,
             catalogue: str | Path,
             plafond_gestes: int,
             plafond_ecrans: int,
             registre: Registre | None = None,
             horloge: Horloge = maintenant) -> Exploration:
    """Rejoue une trace en observation et alimente la quarantaine du catalogue.

    `brut` est un driver NU : il est enveloppe ici dans un `DriverGarde` fige
    en dry-run, plafond de sauvegardes a zero. Ni le mode ni ce plafond ne sont
    des parametres — voir l'en-tete du module.

    Les deux plafonds sont OBLIGATOIRES et sans defaut. `plafond_gestes` compte
    les ACTIONS envoyees au driver, gestes de reprise compris — c'est ce qu'on
    fait au systeme ; `plafond_ecrans` compte les clefs VERSEES — c'est ce
    qu'on ajoute a la file de relecture d'un humain. Les atteindre n'est ni une
    reussite ni une erreur : l'etat vaut `plafond` et le compte rendu dit
    combien de gestes n'ont pas ete explores. Un rapport qui annonce « 35
    ecrans » apres avoir ete coupe a 20 serait exactement le resultat plausible
    et faux que ce depot traque.
    """
    if plafond_gestes <= 0:
        raise ExplorationImpossible(
            f"plafond_gestes={plafond_gestes} : une exploration qui ne rejoue "
            f"aucun geste se terminerait en annoncant « terminee » et zero "
            f"ecran. Un parcours qui semble passer et n'a rien vu est le pire "
            f"des resultats. Donner un budget, ou ne pas explorer")
    if plafond_ecrans <= 0:
        raise ExplorationImpossible(
            f"plafond_ecrans={plafond_ecrans} : aucun ecran ne pourrait etre "
            f"verse, et le parcours agirait sur SAP pour rien")
    if not trace.gestes:
        raise ExplorationImpossible(
            f"{trace.source} : aucun geste. Il n'y a rien a rejouer, et une "
            f"exploration qui se termine sans avoir rien vu ressemble a une "
            f"exploration qui a reussi")

    parcours = _Parcours(
        trace, brut, catalogue=catalogue, plafond_gestes=plafond_gestes,
        plafond_ecrans=plafond_ecrans,
        registre=registre if registre is not None else Registre.charger(),
        horloge=horloge)

    depart = parcours.garde.screen()
    etat, raison, index = _parcourir(parcours)
    non_explores = max(0, len(parcours.gestes) - index)

    return Exploration(
        trace=trace.source, etat=etat, catalogue=str(parcours.catalogue),
        raison=raison,
        versees=tuple(parcours.versees),
        deja_connues=tuple(parcours.deja_connues),
        branches=tuple(parcours.branches),
        reprises=tuple(parcours.reprises),
        sauvegardes_refusees=tuple(parcours.sauvegardes),
        constats=tuple(parcours.constats),
        dumps=tuple(parcours.dumps),
        gestes_lus=len(parcours.gestes),
        gestes_rejoues=parcours.rejoues,
        gestes_confort=parcours.confort,
        gestes_interrompus=parcours.interrompus,
        gestes_de_reprise=parcours.gestes_de_reprise,
        validations_consommees=parcours.validations,
        gestes_sautes=parcours.sautes,
        ordres_sautes=tuple(parcours.ordres_sautes),
        ordres_atteints=tuple(parcours.ordres_atteints),
        gestes_non_explores=non_explores,
        actions_envoyees=parcours.actions,
        releves=parcours.releves,
        systeme=depart.systeme, mandant=depart.mandant, langue=depart.langue,
    )


def _parcourir(p: _Parcours) -> tuple[str, str, int]:
    """La boucle. Rend (etat, raison, index du premier geste non explore).

    Un releve est pris AVANT le premier geste — l'ecran de depart compte — puis
    apres chaque action parvenue au driver. L'ensemble des gestes qui
    declenchent un releve est exactement celui apres lequel `DriverGarde`
    appelle `_apres_action()` : la ou le controleur declare que le monde a pu
    bouger, l'explorateur regarde.
    """
    if not p.relever():
        return PLAFOND, _plafond_ecrans(p, 0), 0

    index = 0
    total = len(p.gestes)
    while index < total:
        if p.actions >= p.plafond_gestes:
            return PLAFOND, _plafond_gestes(p, index), index

        geste = p.gestes[index]

        # -- une Entree deja envoyee par une reprise -----------------------
        if p.validation_consommee == index:
            p.validation_consommee = None
            p.validations += 1
            p.ordres_atteints.append(geste.ordre)
            index += 1
            continue

        # -- le champ de commande : toujours par une reprise verifiee ------
        if vise_le_champ_de_commande(geste):
            suite = _tenter_reprise(p, index)
            if p.plafond_ecrans_atteint:
                # Le releve de la reprise a bute sur le plafond. Le geste de
                # commande, lui, est deja consomme : on repart de celui d'apres
                # pour que la partition ne le compte pas deux fois.
                repris = suite if suite is not None and suite > index else index + 1
                return PLAFOND, _plafond_ecrans(p, repris), repris
            if suite is None:
                return (INTERROMPUE,
                        f"reprise refusee au geste {geste.ordre:03d} : une "
                        f"fenetre autre que wnd[0] est ouverte, le champ de "
                        f"commande n'y est pas atteignable. Fermer une modale "
                        f"demanderait d'inventer un geste que la trace ne "
                        f"contient pas", index)
            if suite < 0:
                return (INTERROMPUE, _sans_point_de_reprise(p, geste),
                        total)
            index = suite
            continue

        # -- traduction ----------------------------------------------------
        traduction = traduire(geste)
        if traduction.genre == ECARTE_CONFORT:
            p.confort += 1
            p.ordres_atteints.append(geste.ordre)
            index += 1
            continue

        if traduction.genre != TRADUIT:
            categorie = {ARGUMENT_REFUSE: ARGUMENT,
                         GENRE_SANS_COUTURE: SANS_COUTURE}.get(
                             traduction.genre, VERBE)
            p.interrompus += 1
            suite = _abandonner(p, geste, categorie, traduction.raison, index)
            if suite < 0:
                return INTERROMPUE, _sans_point_de_reprise(p, geste), total
            index = suite
            continue

        # -- l'action a l'aveugle ------------------------------------------
        assert traduction.appel is not None             # garanti par TRADUIT
        aveugle = _action_a_l_aveugle(
            traduction.appel, tuple(f.id for f in p.garde.windows()),
            p.derniere_cible)
        if aveugle:
            p.interrompus += 1
            suite = _abandonner(p, geste, ACTION_AVEUGLE, aveugle, index)
            if suite < 0:
                return INTERROMPUE, _sans_point_de_reprise(p, geste), total
            index = suite
            continue

        # -- l'action ------------------------------------------------------
        try:
            p.executer(traduction)
        except RefusDryRun as refus:
            # Rien n'a ete envoye au driver brut : l'ecran n'a pas bouge, donc
            # pas de releve. La branche tombe TOUJOURS — continuer rejouerait
            # la suite de la trace sur l'ecran d'AVANT la sauvegarde, que la
            # trace ne decrit pas.
            p.sauvegardes.append(SauvegardeRefusee(
                ordre=geste.ordre, ligne=geste.ligne, verbe=geste.verbe,
                cible=geste.cible, texte_source=geste.texte_source))
            p.interrompus += 1
            suite = _abandonner(
                p, geste, SAUVEGARDE,
                f"la trace sauvegarde ici ({refus}). Une cartographie "
                f"n'ecrit pas, et la suite de cette branche se rejouerait sur "
                f"l'ecran d'AVANT la sauvegarde", index)
            if suite < 0:
                return INTERROMPUE, _sans_point_de_reprise(p, geste), total
            index = suite
            continue
        except Refus as arret:
            # Garde ou taxonomie : l'action a eu lieu, l'ecran a pu bouger.
            if not p.relever():
                return PLAFOND, _plafond_ecrans(p, index), index
            dump, entree = p._dump_si_inconnu()
            p.interrompus += 1
            suite = _abandonner(p, geste, INCIDENT, str(arret), index,
                                entree=entree, dump=dump)
            if suite < 0:
                return INTERROMPUE, _sans_point_de_reprise(p, geste), total
            index = suite
            continue
        except Echec as panne:
            # La couture : `ObjetIntrouvable`, `SessionPerdue`... L'etat de
            # l'ecran est incertain ; le releve est justement ce qui le dira.
            if not p.relever():
                return PLAFOND, _plafond_ecrans(p, index), index
            p.interrompus += 1
            suite = _abandonner(
                p, geste, COUTURE,
                f"{type(panne).__name__} — {panne}", index)
            if suite < 0:
                return INTERROMPUE, _sans_point_de_reprise(p, geste), total
            index = suite
            continue

        p.rejoues += 1
        p.ordres_atteints.append(geste.ordre)
        if not p.relever():
            return PLAFOND, _plafond_ecrans(p, index + 1), index + 1
        index += 1

    return TERMINEE, "", total


def _tenter_reprise(p: _Parcours, index: int) -> int | None:
    """Consomme le geste de commande a `index`. Rend l'index suivant.

    `None` : la reprise n'a pas pu etre tentee, l'exploration s'arrete.
    Negatif : la reprise a echoue et plus aucun point de reprise ne suit.
    """
    geste = p.gestes[index]
    if not _code_de_reprise(geste):
        # `/n` seul, `/nex`, `/o...` : jamais execute. La seule verification
        # possible apres `/n` serait « la transaction a change », qui est vraie
        # aussi quand SAP a atterri ailleurs.
        p.interrompus += 1
        return _abandonner(
            p, geste, SANS_REPRISE,
            f"{geste.valeur!r} ne nomme aucune transaction sur laquelle on "
            f"puisse repartir de facon verifiable — code de session, ou `/n` "
            f"seul. Geste non execute", index)

    reprise = p._reprendre(index)
    if reprise is None:
        return None

    p.gestes_de_reprise += 1
    p.ordres_atteints.append(geste.ordre)
    p.reprises.append(reprise)
    if not reprise.acceptee:
        p.branches.append(_branche(
            geste, REPRISE_REFUSEE,
            f"reprise {reprise.demandee!r} : SAP est reste sur "
            f"{reprise.obtenue!r}. Le code n'a pas ete accepte — la suite de "
            f"la trace se serait rejouee sur un autre ecran que celui qu'elle "
            f"decrit"))
        return _sauter_vers_reprise(p, index + 1)

    # L'Entree que la trace envoie juste apres a deja ete envoyee ici.
    suivant = index + 1
    if (suivant < len(p.gestes) and p.gestes[suivant].verbe == "sendVKey"
            and p.gestes[suivant].valeur == VKEY_ENTREE):
        p.validation_consommee = suivant
    return suivant


def _abandonner(p: _Parcours, geste: Geste, categorie: str, motif: str,
                index: int, *, entree: str = "", dump: str = "") -> int:
    """Note la branche et rend l'index de reprise, ou -1."""
    p.ordres_atteints.append(geste.ordre)
    p.branches.append(_branche(geste, categorie, motif, entree=entree,
                               dump=dump))
    return _sauter_vers_reprise(p, index + 1)


def _sauter_vers_reprise(p: _Parcours, depart: int) -> int:
    """Avance jusqu'au prochain point de reprise, en comptant les sautes."""
    cible = p._prochaine_reprise(depart)
    if cible is None:
        return -1
    p.sautes += cible - depart
    p.ordres_sautes.extend(g.ordre for g in p.gestes[depart:cible])
    p.branches[-1] = Branche(
        **{**asdict(p.branches[-1]),
           "reprise": _code_de_reprise(p.gestes[cible])})
    return cible


def _sans_point_de_reprise(p: _Parcours, geste: Geste) -> str:
    restants = len(p.gestes) - geste.ordre
    p.sautes += restants
    p.ordres_sautes.extend(g.ordre for g in p.gestes[geste.ordre:])
    return (f"aucun code transaction apres le geste {geste.ordre:03d} : la "
            f"trace ne redonne plus de point d'entree verifiable, et repartir "
            f"sans en taper un reviendrait a deviner ou l'on est. "
            f"{restants} geste(s) non explore(s)")


def _plafond_gestes(p: _Parcours, index: int) -> str:
    return (f"plafond de {p.plafond_gestes} action(s) atteint au geste "
            f"{index + 1:03d}. Ce qui suit n'a PAS ete explore : "
            f"{len(p.gestes) - index} geste(s), et les ecrans qu'ils "
            f"traversent ne sont pas au catalogue")


def _plafond_ecrans(p: _Parcours, index: int) -> str:
    return (f"plafond de {p.plafond_ecrans} ecran(s) atteint. Le releve en "
            f"cours n'a pas ete verse, et les {len(p.gestes) - index} geste(s) "
            f"restants n'ont pas ete explores")
