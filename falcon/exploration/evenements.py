"""Ce qu'un parcours RACONTE pendant qu'il court. Des faits, pas un affichage.

Ces types vivent ici et non dans `falcon/toile/` parce que le vocabulaire —
geste, ecran verse, branche, reprise, sauvegarde refusee — est celui de
l'exploration et de personne d'autre. `toile` existe precisement pour ne
connaitre aucun de ces mots. La direction de dependance est celle du depot :
celui qui PEINT importe celui qui EMET, jamais l'inverse, et un test de
frontiere interdit a `falcon/exploration/` et a `falcon/moteur/` d'importer
`falcon.toile`. Un parcours qui saurait a qui il parle deviendrait
intestable sans terminal, ce qu'il n'est pas aujourd'hui.

**Tout est plat, scalaire et immuable, et rien n'est une reference sur l'etat
vivant du parcours.** Ni `branches`, ni `versees`, ni `constats`, ni
`ordres_sautes` : `_sauter_vers_reprise` REECRIT `p.branches[-1]` apres coup,
et un observateur qui tiendrait la liste verrait une branche changer dans son
dos — ou en modifierait une autre.

**Et rien ne se lit sur le driver.** Les fenetres ouvertes sont deja calculees
juste avant l'action ; l'evenement les transporte. Les redemander doublerait
le trafic COM sur le chemin le plus chaud, et ce trafic n'est PAS compte par
`p.actions` : la docstring d'`explorer` — « `plafond_gestes` compte les ACTIONS
envoyees au driver [...] c'est ce qu'on fait au systeme » — deviendrait fausse,
ce qui est un defaut a part entiere ici. Un test le verifie a l'execution sur
les evenements de la trace de reference : aucun champ n'est une liste, un
`dict`, un `set` ou un objet du parcours.

**L'horloge est `time.monotonic`, jamais `p.horloge`.** Celle-ci nomme les
dumps et date les variantes ; l'appeler depuis un affichage decalerait la
fausse horloge sequentielle des tests, et deux suites d'exploration
deviendraient instables. `moteur/boucle.py` fait deja `time.monotonic()`.
"""

from __future__ import annotations

from dataclasses import dataclass, fields as champs_de

#: Ce qui commence : l'ecran de depart, les plafonds, la trace, le catalogue.
DEPART = "depart"

#: Un geste de la trace est ABORDE. Ni joue ni refuse : aborde. C'est une
#: POSITION dans le fichier, et le direct le dit en toutes lettres, parce que
#: `034/090` se lit spontanement comme un avancement alors que 46 des 90
#: gestes de la trace de reference partent en bloc quand une branche tombe.
GESTE = "geste"

#: L'appel est parvenu au driver garde et en est revenu sans exception.
ENVOYE = "envoye"

#: Geste de confort ecarte — position de curseur, focus, selection de texte.
CONFORT = "confort"

#: Entree que la trace envoie et que la reprise avait deja envoyee.
VALIDATION = "validation"

#: Une variante distincte est partie en quarantaine.
ECRAN_VERSE = "ecran_verse"

#: Une variante distincte etait deja au catalogue ou en quarantaine.
ECRAN_CONNU = "ecran_connu"

#: Un plafond declare a mordu. `motif` dit lequel : « gestes » ou « ecrans ».
#: Deux plafonds, un seul genre : ils ont la meme consequence — la fin — et
#: les distinguer par le genre obligerait chaque lecteur a connaitre les deux.
PLAFOND = "plafond"

#: Le dry-run a refuse un geste qui aurait ecrit dans SAP.
SAUVEGARDE_REFUSEE = "sauvegarde_refusee"

#: L'exploration a cesse de suivre la trace. `reprise` porte la transaction
#: visee, et elle n'est renseignee qu'APRES la reecriture de `p.branches[-1]`
#: par `_sauter_vers_reprise` : emis avant, cet evenement afficherait
#: « reprise visee (aucune) » sur une branche qui reprend tres bien.
BRANCHE = "branche"

#: Des gestes ont ete emportes sans avoir ete abordes. DEUX chemins de saut
#: dans le parcours, et non un seul — voir `_sans_point_de_reprise`.
SAUT = "saut"

#: Un code transaction a ete TAPE par l'explorateur, valide par Entree, et
#: verifie. `acceptee` dit ce que SAP en a fait.
REPRISE = "reprise"

#: La fin, quel que soit l'etat. Emis une fois, et une seule.
FIN = "fin"

GENRES = frozenset({
    DEPART, GESTE, ENVOYE, CONFORT, VALIDATION,
    ECRAN_VERSE, ECRAN_CONNU, PLAFOND,
    SAUVEGARDE_REFUSEE, BRANCHE, SAUT, REPRISE, FIN,
})


class GenreInconnu(Exception):
    """Genre absent de `GENRES`.

    Elle LEVE plutot que de laisser passer : un genre mal orthographie ne
    ferait rien tomber, il disparaitrait simplement de l'ecran. Une ligne qui
    manque ne se voit pas — c'est le propre d'une ligne qui manque.
    """


@dataclass(frozen=True)
class Evenement:
    """Un fait, tel que le parcours l'a constate au moment ou il le constate.

    Un seul type et des champs a defaut plutot qu'un type par genre : ce que
    l'afficheur fait de ces faits est du texte, et une hierarchie de treize
    classes lui imposerait treize branchements pour produire treize lignes.
    Le prix est qu'un champ non renseigne vaut son defaut et non « absent » ;
    il est paye par `GENRES`, qui empeche au moins qu'un genre invente ne
    traverse le flux sans bruit.

    Les champs, et qui les renseigne :

      - `ordre`, `ligne`, `verbe`, `cible`, `source` : le geste de la trace.
        `ordre` est son rang parmi les gestes, `ligne` son rang dans le
        fichier `.vbs` — les deux different des que la trace porte un
        commentaire, et le compte rendu cite les deux pour cette raison.
      - `index`, `total` : la POSITION dans la trace, jamais un avancement.
      - `appel` : la methode de couture reellement envoyee au driver.
      - `clef`, `titre`, `fenetre`, `champs` : la variante relevee.
      - `actions`, `plafond_gestes`, `versees`, `plafond_ecrans` : les deux
        seuls couples dont le denominateur est un budget tape par l'humain.
      - `transaction`, `systeme`, `mandant`, `langue` : sur QUOI l'on agit.
      - `fenetres` : les fenetres ouvertes, deja lues par le parcours.
      - `categorie`, `motif`, `reprise` : la branche et sa suite.
      - `acceptee` : ce que SAP a fait du code tape.
      - `sautes` : des gestes emportes, pas des gestes traites.
      - `etat`, `raison` : la fin.
      - `monotone_ms` : le temps ECOULE depuis le debut du parcours. Une
        mesure, et non une estimation : un ETA serait faux d'un facteur cinq
        sur une trace ou une branche qui tombe emporte quarante gestes.
    """

    genre: str
    ordre: int = 0
    ligne: int = 0
    index: int = 0
    total: int = 0
    verbe: str = ""
    cible: str = ""
    source: str = ""
    appel: str = ""
    clef: str = ""
    titre: str = ""
    fenetre: str = ""
    champs: int = 0
    actions: int = 0
    plafond_gestes: int = 0
    versees: int = 0
    plafond_ecrans: int = 0
    transaction: str = ""
    systeme: str = ""
    mandant: str = ""
    langue: str = ""
    fenetres: tuple[str, ...] = ()
    categorie: str = ""
    motif: str = ""
    reprise: str = ""
    acceptee: bool = False
    sautes: int = 0
    etat: str = ""
    raison: str = ""
    monotone_ms: int = 0

    def __post_init__(self) -> None:
        if self.genre not in GENRES:
            raise GenreInconnu(
                f"genre {self.genre!r}, attendu l'un de {sorted(GENRES)}")


#: Les noms de champs, dans l'ordre de declaration. Sert au test qui verifie
#: qu'aucun evenement ne transporte d'objet vivant : il les parcourt tous
#: plutot que d'en citer une liste qui se perimerait au premier ajout.
NOMS_DE_CHAMPS = tuple(c.name for c in champs_de(Evenement))
