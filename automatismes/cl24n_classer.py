#!/usr/bin/env python3
"""CL24N — affecter des points de mesure a une classe, une passe par classe.

Depuis la racine du depot, SAP GUI ouvert et authentifie par vous-meme :

    python automatismes/cl24n_classer.py points.csv --type-classe 0XX --plafond-points 20 --classe MA_CLASSE
    python automatismes/cl24n_classer.py points.csv --type-classe 0XX --plafond-points 500 --executer

`points.csv` porte deux colonnes, `point` et `classe`, une ligne par
affectation. Une passe par classe : `/nCL24N`, classe et type de classe,
type d'objet « point de mesure », puis chaque point dans la premiere ligne
vide du table control, Entree, et UNE sauvegarde en fin de passe.

**Version simplifiee.** Un fichier, sur la couture FALCON (`falcon.couture`)
et rien d'autre du moteur : ni pipeline YAML, ni contrat d'etape, ni
taxonomie. Trois gardes sont reprises ici parce qu'elles ne coutent rien et
qu'un automate qui ecrit dans un ERP sans elles n'est pas simplifie, il est nu :

- **a blanc par defaut.** Sans `--executer`, presser « Sauvegarder » est
  refuse mecaniquement (`RefusDryRun`), pas seulement evite. Les saisies
  restent a l'ecran, jamais sauvegardees : on quitte CL24N a la main, une
  classe par lancement.
- **plafond obligatoire.** `--plafond-points` borne chaque passe, et le jeu est
  refuse AVANT tout contact avec SAP s'il le depasse.
- **l'inconnu arrete.** Une modale qu'aucune regle ne reconnait arrete le
  lancement avant toute sauvegarde (`--executer`). A blanc, si elle suit
  l'Entree d'un point, elle est annulee (F12), la ligne du point est videe
  et la passe continue, pour en voir le plus possible dans le rapport ;
  ailleurs, elle arrete aussi.

**Rien ici n'a encore parle a un SAP.** Ce que le programme SAIT vient de la
trace du recorder ; ce qu'il SUPPOSE est marque HYPOTHESE dans `Cibles` et
dans les regles de modale, et se tranche en relisant le rapport du premier
lancement a blanc. Les champs sont resolus par SUFFIXE, jamais par chemin
complet : le numero de sous-ecran varie avec le type d'objet (piege n°4 de
`historique/docs/TRAPS.md`).

Chaque lancement ecrit deux fichiers dans `--sortie` (defaut `sorties/`) : le
**journal** CSV, une ligne par point avec son etat, et le **rapport** texte,
qui releve chaque ecran et chaque modale rencontres — c'est lui qu'on relit
pour adapter les regles. Les deux s'ecrivent au fil de l'eau : un plantage ne
les perd pas.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from falcon.couture import Driver, DriverLecture                      # noqa: E402
from falcon.donnees.entree import JeuInvalide                          # noqa: E402
from falcon.noyau import (                                             # noqa: E402
    CHAMP_DE_COMMANDE, Champ, Ecran, ErreurFalcon, Fenetre, Identite,
    ObjetIntrouvable, RefusDryRun, SapIndisponible, Statut, maintenant,
)


# =====================================================================
# Ce que le programme sait, et ce qu'il suppose
# =====================================================================

@dataclass(frozen=True)
class Cibles:
    """Ou le programme agit. Chaque valeur dit d'ou elle vient.

    « trace » : lu dans l'enregistrement du recorder, donc observe une fois
    sur un vrai systeme. « HYPOTHESE » : jamais observe ; le programme le
    cherche par suffixe et S'ARRETE en nommant ce qu'il a trouve a la place.
    """

    transaction: str = "CL24N"

    # HYPOTHESE — l'ecran initial. La trace ne saisit ni la classe ni son
    # type (SAP les avait memorises) ; les noms viennent de la structure
    # RMCLF que la trace emploie pour tout le reste. Resolus par suffixe
    # parmi les champs de SAISIE de wnd[0] : un libelle ne compte pas.
    champ_classe: str = "RMCLF-CLASS"
    champ_type_classe: str = "RMCLF-KLART"

    # trace — le bouton qui ouvre le choix du type d'objet. La radio est
    # choisie par son LIBELLE ; l'index de la trace (suffixe : le sous-ecran
    # 0602 n'est pas fige) n'est qu'un repli, quand aucun libelle n'apparie.
    bouton_type_objet: str = "wnd[0]/tbar[1]/btn[33]"
    libelle_point: str = r"point de mesure|measuring point|messpunkt"
    radio_point: str = "radRMCLF-RADIO[1,0]"

    # trace — le table control et sa colonne « point de mesure ».
    table: str = "tblSAPLCBCMTC_OBJ_CLASS"
    colonne_point: str = "ctxtRMCLF-POINT"

    # trace — la sauvegarde. C'est le SEUL geste que le mode a blanc refuse.
    bouton_sauvegarde: str = "wnd[0]/tbar[0]/btn[11]"

    # trace — dans la modale qui suit une validation quand la classe a des
    # caracteristiques obligatoires : « poursuivre » puis « valider ».
    bouton_poursuivre: str = "tbar[0]/btn[8]"
    bouton_valider: str = "tbar[0]/btn[0]"


#: HYPOTHESE — ce que dit la modale d'un point deja affecte a la classe.
#: Cherche dans le titre et les textes de la modale, dans la langue de
#: connexion. Le rapport du premier lancement donne le texte exact.
MOTIF_DEJA_AFFECTE = re.compile(r"d[ée]j[àa]\b|already|bereits", re.IGNORECASE)

#: Types de champ dont le `texte` est une valeur ou un libelle — les autres
#: (shells, boutons, barres) repondent leur nom de classe ou leur icone.
SAISISSABLES = frozenset({"GuiCTextField", "GuiTextField"})
SANS_TEXTE = frozenset({
    "GuiShell", "GuiButton", "GuiToolbar", "GuiMenu", "GuiMenubar",
    "GuiTitlebar", "GuiStatusbar", "GuiOkCodeField", "GuiContainer",
    "GuiCustomControl", "GuiUserArea", "GuiModalWindow", "GuiMainWindow",
    "GuiScrollContainer", "GuiSimpleContainer", "GuiTableControl",
})

#: Colonnes du jeu d'entree.
COLONNE_POINT = "point"
COLONNE_CLASSE = "classe"
_NUMERO = re.compile(r"[0-9]+")
#: Un numero de point de mesure est un NUMC 12 : au-dela, SAP tronque.
LONGUEUR_POINT = 12

# -- etats du journal, un par ligne ------------------------------------------
SAISI = "SAISI"                     # entre et valide, en attente de sauvegarde
DEJA_AFFECTE = "DEJA_AFFECTE"       # la modale « deja affecte » : KO, ligne videe
REFUSE = "REFUSE"                   # message E/A apres Entree : KO, ligne videe
POPUP_INCONNUE = "POPUP_INCONNUE"   # a blanc seulement : modale annulee, point douteux
SAUVEGARDE = "SAUVEGARDE"           # statut S apres sauvegarde
A_VERIFIER = "A_VERIFIER"           # sauvegarde pressee, statut non concluant
NON_SAUVEGARDE = "NON_SAUVEGARDE"   # saisi, jamais sauvegarde (a blanc, ou arret)
PASSE = "PASSE"                     # debut et fin de passe
ARRET = "ARRET"                     # la passe s'est arretee, la raison est le detail

# -- verdicts sur une modale ----------------------------------------------------
V_DEJA = "deja_affecte"
V_VALORISATION = "valorisation_ignoree"
V_INCONNUE = "modale_inconnue_annulee"


class Arret(Exception):
    """Arret propre : la passe s'interrompt et rien n'est sauvegarde apres."""


class Prevol(Exception):
    """Refus avant tout contact avec SAP."""


# =====================================================================
# Petites fonctions pures
# =====================================================================

def meme_valeur(ecrit: str, relu: str) -> bool:
    """Tolere ce que SAP fait a une saisie : espaces, casse, zeros de tete."""
    gauche, droite = ecrit.strip().upper(), relu.strip().upper()
    if gauche == droite:
        return True
    if _NUMERO.fullmatch(gauche) and _NUMERO.fullmatch(droite):
        return gauche.lstrip("0") == droite.lstrip("0")
    return False


def textes_de(ecran: Ecran) -> list[str]:
    """Le titre et les textes lisibles d'une fenetre, dans l'ordre."""
    textes = [ecran.titre.strip()] if ecran.titre.strip() else []
    for champ in ecran.champs:
        if champ.type in SANS_TEXTE:
            continue
        texte = champ.texte.strip()
        if texte:
            textes.append(texte)
    return textes


def bouton(ecran: Ecran, suffixe: str) -> str | None:
    """L'identifiant du bouton dont l'id finit par `suffixe`, ou None."""
    for champ in ecran.par_suffixe(suffixe):
        if champ.type == "GuiButton":
            return champ.id
    return None


def boutons_de_choix(ecran: Ecran) -> list[str]:
    """Les boutons de la ZONE UTILISATEUR d'une modale : Oui / Non / Annuler.

    Une boite de message n'en a pas — son seul bouton est dans `tbar[0]`. Une
    question en a, et son bouton par defaut est « Oui » : Entree y repond
    sans qu'on l'ait decide.
    """
    return [c.id for c in ecran.champs
            if c.type == "GuiButton" and "/usr/" in c.id]


def statut_texte(statut: Statut) -> str:
    return f"{statut.type or '-'} {statut.cle} « {statut.texte} »"


def resume(compte: Counter) -> str:
    return ", ".join(f"{etat} {n}" for etat, n in sorted(compte.items())) or "rien"


# =====================================================================
# Journal et rapport : deux fichiers, ecrits au fil de l'eau
# =====================================================================

class Journal:
    """Une ligne par point. UTF-8 avec BOM et `;` : ce qu'Excel lit tel quel."""

    COLONNES = ("horodatage", "classe", "point", "etat", "detail")

    def __init__(self, chemin: Path):
        self.chemin = chemin
        self._fichier = chemin.open("w", encoding="utf-8-sig", newline="")
        self._ecrivain = csv.writer(self._fichier, delimiter=";",
                                    lineterminator="\r\n")
        self._ecrivain.writerow(self.COLONNES)
        self._fichier.flush()

    def noter(self, classe: str, point: str, etat: str, detail: str = "") -> None:
        self._ecrivain.writerow((maintenant(), classe, point, etat, detail))
        self._fichier.flush()
        os.fsync(self._fichier.fileno())

    def fermer(self) -> None:
        self._fichier.close()


class Rapport:
    """Le releve de chaque ecran et de chaque modale rencontres.

    Un ecran est releve EN ENTIER la premiere fois que son empreinte est vue :
    identite, fenetres, statut, et une ligne par champ avec son type, son
    texte, son INFOBULLE — le seul libelle d'un bouton a icone, donc ce qui
    dit ce que `btn[8]` ou `btn[33]` font vraiment — et s'il est modifiable.
    Ensuite, seulement son titre, ses textes et la barre de statut : ce sont
    eux qui changent d'un point a l'autre, et eux qu'on relit pour ecrire
    une regle.
    """

    def __init__(self, chemin: Path, driver: Driver):
        self.chemin = chemin
        self._lecteur = DriverLecture(driver)
        self._fichier = chemin.open("w", encoding="utf-8-sig")
        self._vues: set[str] = set()
        self.releves = 0

    def ligne(self, texte: str) -> None:
        self._fichier.write(texte + "\n")
        self._fichier.flush()

    def relever(self, fenetre: str, contexte: str) -> Ecran:
        ecran = self._lecteur.fields(fenetre)
        self.releves += 1
        self.ligne(f"\n=== releve {self.releves} | {contexte} | {fenetre} "
                   f"« {ecran.titre} » | empreinte {ecran.empreinte} ===")
        if ecran.empreinte in self._vues:
            self.ligne("  (deja relevee en entier plus haut)")
            for texte in textes_de(ecran):
                self.ligne(f"  « {texte} »")
            self.ligne(f"  statut {statut_texte(self._lecteur.status())}")
        else:
            self._vues.add(ecran.empreinte)
            self._entier(ecran)
        return ecran

    def _entier(self, ecran: Ecran) -> None:
        identite = ecran.identite
        self.ligne(f"  identite  systeme {identite.systeme or '-'}  mandant "
                   f"{identite.mandant or '-'}  langue {identite.langue or '-'}  "
                   f"transaction {identite.transaction or '-'}  programme "
                   f"{identite.programme or '-'}  dynpro {identite.dynpro or '-'}")
        for ouverte in self._lecteur.windows():
            self.ligne(f"  fenetre   {ouverte.id}  {ouverte.type}  "
                       f"{'modale' if ouverte.modale else 'principale'}  "
                       f"« {ouverte.titre} »")
        self.ligne(f"  statut    {statut_texte(self._lecteur.status())}")
        self.ligne(f"  champs de {ecran.fenetre} ({len(ecran.champs)}) : "
                   f"id | type | nom | « texte » | infobulle | modifiable")
        for champ in ecran.champs:
            soustype = f"/{champ.soustype}" if champ.soustype else ""
            modifiable = {True: "oui", False: "non"}.get(champ.modifiable, "?")
            self.ligne(f"    {champ.id} | {champ.type}{soustype} | {champ.nom} | "
                       f"« {champ.texte} » | {champ.infobulle} | {modifiable}")

    def fermer(self) -> None:
        self._fichier.close()


# =====================================================================
# L'automate
# =====================================================================

class Automate:
    """Une passe CL24N par classe, sur un `Driver` quelconque.

    Le driver est recu, jamais fabrique : les tests le remplacent par le
    double de `falcon.couture.double`, et le programme ne sait pas s'il parle
    a SAP.
    """

    #: Au-dela, on ne cherche plus de ligne vide : quelque chose ne va pas.
    PLAFOND_LIGNES = 5000
    #: Modales successives tolerees apres UNE action.
    PLAFOND_MODALES = 6

    def __init__(self, driver: Driver, journal: Journal, rapport: Rapport, *,
                 executer: bool, par_lot: int = 0, cibles: Cibles = Cibles()):
        self.d = driver
        self.journal = journal
        self.rapport = rapport
        self.executer = executer
        #: Sauvegarder toutes les N saisies ; 0 = une fois, en fin de passe.
        self.par_lot = par_lot
        self.c = cibles
        self._table = ""
        self._depart = 0
        self._textes_modale = ""
        self._en_attente: list[str] = []
        self._sauvegarde_en_cours = False

    # -- gestes gardes ------------------------------------------------------------

    def _presser(self, cible: str) -> None:
        if not self.executer and cible.endswith("tbar[0]/btn[11]"):
            raise RefusDryRun(f"a blanc : {cible} est la sauvegarde, refusee")
        self.d.press(cible)

    def _touche(self, n: int, fenetre: str = "wnd[0]") -> None:
        if not self.executer and n == 11:
            raise RefusDryRun("a blanc : F11 est la sauvegarde, refusee")
        self.d.vkey(n, fenetre)

    def _ecrire(self, cible: str, valeur: str) -> None:
        """Ecrit, puis RELIT : ecrire sans que ca prenne ne leve rien."""
        self.d.write(cible, valeur)
        relu = self.d.read(cible)
        if not meme_valeur(valeur, relu):
            raise Arret(f"relecture apres ecriture dans {cible} : ecrit "
                        f"{valeur!r}, relu {relu!r}")

    # -- observation ---------------------------------------------------------------

    def _modales(self) -> list[Fenetre]:
        return [f for f in self.d.windows() if f.modale]

    def _sans_modale(self, contexte: str) -> None:
        modales = self._modales()
        if not modales:
            return
        for modale in modales:
            self.rapport.relever(modale.nom or modale.id, contexte)
        raise Arret(f"{contexte} : fenetre(s) imprevue(s) "
                    f"{[m.nom or m.id for m in modales]} ; voir le rapport")

    @staticmethod
    def _champ_de_saisie(ecran: Ecran, suffixe: str) -> Champ:
        candidats = [c for c in ecran.par_suffixe(suffixe)
                     if c.type in SAISISSABLES]
        if len(candidats) == 1:
            return candidats[0]
        vus = [c.id for c in ecran.par_suffixe(suffixe)]
        raise Arret(
            f"champ *{suffixe} : {len(candidats)} champ(s) de saisie dans "
            f"{ecran.fenetre}, un attendu (identifiants portant ce suffixe : "
            f"{vus or 'aucun'}). Le rapport releve l'ecran : y lire le vrai "
            f"nom et corriger `Cibles`")

    # -- etapes ---------------------------------------------------------------------

    def ouvrir(self) -> Identite:
        self._sans_modale(f"avant /n{self.c.transaction} : une modale est "
                          f"ouverte, la fermer a la main")
        self.d.write(CHAMP_DE_COMMANDE, f"/n{self.c.transaction}")
        self._touche(0)
        self._sans_modale(f"apres /n{self.c.transaction}")
        identite = self.d.screen()
        if identite.transaction != self.c.transaction:
            self.rapport.relever("wnd[0]", f"apres /n{self.c.transaction}")
            raise Arret(f"transaction {identite.transaction!r} au lieu de "
                        f"{self.c.transaction!r} apres /n{self.c.transaction}")
        self.rapport.relever("wnd[0]", f"{self.c.transaction} : ecran initial")
        return identite

    def saisir_classe(self, classe: str, type_classe: str) -> None:
        ecran = self.d.fields("wnd[0]")
        champ_classe = self._champ_de_saisie(ecran, self.c.champ_classe)
        champ_type = self._champ_de_saisie(ecran, self.c.champ_type_classe)
        self._ecrire(champ_classe.id, classe)
        self._ecrire(champ_type.id, type_classe)
        self._touche(0)
        self._sans_modale(f"classe {classe} : validation de l'ecran initial")
        statut = self.d.status()
        self.rapport.ligne(f"  classe {classe} type {type_classe} : statut "
                           f"{statut_texte(statut)}")
        if statut.type in ("E", "A"):
            raise Arret(f"classe {classe!r} type {type_classe!r} : "
                        f"{statut_texte(statut)}")
        self.rapport.relever("wnd[0]", f"classe {classe} : ecran d'affectation")

    def _table_des_points(self) -> bool:
        """Resout le table control par sa cellule [0,0], et retient le prefixe."""
        ecran = self.d.fields("wnd[0]")
        fin = f"/{self.c.colonne_point}[0,0]"
        cellules = ecran.par_suffixe(f"{self.c.table}{fin}")
        if len(cellules) != 1:
            self._table = ""
            return False
        self._table = cellules[0].id[:-len(fin)]
        return True

    def choisir_type_objet(self) -> None:
        if self._table_des_points():
            self.rapport.ligne("  type d'objet : la colonne point de mesure est "
                               "deja la, bouton non presse")
            return
        self._presser(self.c.bouton_type_objet)
        modales = self._modales()
        if len(modales) > 1:
            raise Arret(f"type d'objet : {len(modales)} modales apres "
                        f"{self.c.bouton_type_objet}, une attendue")
        if modales:
            fenetre = modales[0].nom or modales[0].id
            ecran = self.rapport.relever(fenetre, "choix du type d'objet")
            radio = self._radio_point(ecran, fenetre)
            self.rapport.ligne(f"  radio choisie : {radio.id} « {radio.texte} »")
            self.d.select(radio.id)
            valider = bouton(ecran, self.c.bouton_valider)
            if valider is None:
                raise Arret(f"type d'objet : pas de bouton *{self.c.bouton_valider} "
                            f"dans {fenetre}")
            self._presser(valider)
            self._sans_modale("choix du type d'objet : apres validation")
        else:
            self.rapport.ligne(f"  type d'objet : aucune modale apres "
                               f"{self.c.bouton_type_objet}")
        if not self._table_des_points():
            self.rapport.relever("wnd[0]", "apres choix du type d'objet")
            raise Arret(f"la colonne {self.c.colonne_point} n'apparait pas "
                        f"apres le choix du type d'objet ; voir le rapport")
        self.rapport.relever("wnd[0]", "ecran d'affectation, points de mesure")

    def _radio_point(self, ecran: Ecran, fenetre: str) -> Champ:
        """La radio « point de mesure » : par LIBELLE, l'index de la trace en repli.

        L'index [1,0] est ce que le recorder a vu une fois ; le libelle est ce
        qu'un humain a lu. Quand un seul libelle apparie, c'est lui. Sinon —
        libelles vides, ou dans une langue que le motif ignore — l'index de
        la trace sert, et le rapport ecrit ce qu'il a choisi.
        """
        motif = re.compile(self.c.libelle_point, re.IGNORECASE)
        radios = [c for c in ecran.champs if c.type == "GuiRadioButton"]
        par_libelle = [c for c in radios if motif.search(c.texte)]
        if len(par_libelle) == 1:
            return par_libelle[0]
        par_index = ecran.par_suffixe(self.c.radio_point)
        if len(par_index) == 1:
            self.rapport.ligne(f"  radio : {len(par_libelle)} libelle(s) "
                               f"appariant /{self.c.libelle_point}/ parmi "
                               f"{[c.texte for c in radios]} ; repli sur "
                               f"l'index de la trace")
            return par_index[0]
        raise Arret(f"type d'objet : aucune radio « point de mesure » dans "
                    f"{fenetre} — libelles {[c.texte for c in radios]}, et "
                    f"{len(par_index)} champ(s) *{self.c.radio_point} ; voir "
                    f"le rapport")

    # -- le table control : index VISIBLE, defilement explicite --------------------

    def _cellule(self, rang: int) -> str:
        return f"{self._table}/{self.c.colonne_point}[0,{rang}]"

    def _page(self, position: int, visibles: int) -> list[str]:
        """Les textes des cellules visibles de la colonne point, apres defilement.

        Par `read`, cellule par cellule — deux appels COM chacune — et non par
        `fields`, qui traverse TOUT wnd[0] a chaque page : sur une classe de
        trois cents points, c'est la difference entre quelques secondes et
        une heure par passe.
        """
        self.d.table_scroll(self._table, position)
        page: list[str] = []
        for rang in range(visibles):
            try:
                page.append(self.d.read(self._cellule(rang)))
            except ObjetIntrouvable:
                break
        return page

    def _ligne_vide_depuis(self, depart: int, visibles: int) -> int | None:
        """(rang VISIBLE, defilement laisse dessus) ou None si rien depuis `depart`.

        S'arrete quand le defilement ne progresse plus : aucun compteur de
        SAP n'est fiable (piege n°7).
        """
        position, precedente = depart, None
        while position < self.PLAFOND_LIGNES:
            page = self._page(position, visibles)
            if not page:
                raise Arret(f"table {self._table} : aucune cellule lisible a "
                            f"la position {position}")
            for rang, valeur in enumerate(page):
                if not valeur.strip():
                    self._depart = position
                    return rang
            if page == precedente:
                return None
            precedente = page
            position += len(page)
        raise Arret(f"table {self._table} : aucune ligne vide dans les "
                    f"{self.PLAFOND_LIGNES} premieres lignes")

    def _premiere_ligne_vide(self) -> int:
        """Rang VISIBLE d'une cellule vide, le defilement laisse dessus.

        Le balayage part de la page ou la derniere ligne vide a ete trouvee :
        la table ne fait que grandir sous nos ecritures, et les lignes libres
        sont derriere les lignes prises. Ce n'est qu'un point de depart —
        la cellule est RELUE vide juste avant d'y ecrire — et s'il ne mene a
        rien, on repart de zero une fois, comme le piege n°6 le demande.
        """
        visibles = self.d.table_visible_rows(self._table)
        if visibles <= 0:
            raise Arret(f"table {self._table} : aucune ligne visible")
        rang = self._ligne_vide_depuis(self._depart, visibles)
        if rang is None and self._depart:
            self._depart = 0
            rang = self._ligne_vide_depuis(0, visibles)
        if rang is None:
            raise Arret(f"table {self._table} : aucune ligne vide, le "
                        f"defilement ne progresse plus")
        return rang

    # -- modales -------------------------------------------------------------------

    def _fermer(self, fenetre: str, ecran: Ecran) -> None:
        valider = bouton(ecran, self.c.bouton_valider)
        if valider is not None:
            self._presser(valider)
        else:
            self._touche(0, fenetre)

    def _appliquer_regle(self, fenetre: str, ecran: Ecran, contexte: str) -> str:
        """Une modale, un verdict. L'ordre des regles est celui-ci a dessein."""
        textes = " | ".join(textes_de(ecran))

        # 1. HYPOTHESE : un point deja affecte le dit dans un texte — et c'est
        #    une boite de MESSAGE, sans bouton de choix dans sa zone
        #    utilisateur. Une question (« Oui / Non ») qui contiendrait le
        #    mot reste inconnue : on n'y presse jamais le bouton par defaut.
        if MOTIF_DEJA_AFFECTE.search(textes) and not boutons_de_choix(ecran):
            self._textes_modale = textes
            self._fermer(fenetre, ecran)
            return V_DEJA

        # 2. trace : caracteristiques obligatoires — « poursuivre », puis
        #    « valider » sur le wnd[1] present ensuite, que ce soit une autre
        #    modale ou encore la meme : la trace dit btn[8] puis btn[0], et
        #    rien de plus. Reconnue par son bouton, pas par son texte. Une
        #    QUESTION (Oui / Non) apres « poursuivre » n'est jamais validee :
        #    elle reste a l'ecran, et la regle 3 en decide au tour suivant.
        poursuivre = bouton(ecran, self.c.bouton_poursuivre)
        if poursuivre is not None:
            self._presser(poursuivre)
            suite = self._modales()
            if suite:
                fenetre_suite = suite[0].nom or suite[0].id
                ecran_suite = self.rapport.relever(
                    fenetre_suite, f"{contexte} : apres « poursuivre »")
                valider = bouton(ecran_suite, self.c.bouton_valider)
                choix = boutons_de_choix(ecran_suite)
                if valider is not None and not choix:
                    self._presser(valider)
                elif choix:
                    self.rapport.ligne(f"  apres « poursuivre » : une question "
                                       f"({choix}), rien n'est presse")
            return V_VALORISATION

        # 3. inconnue.
        if self.executer:
            suite = ("la sauvegarde a ete PRESSEE, son etat est a verifier "
                     "dans SAP" if self._sauvegarde_en_cours
                     else "les saisies en attente ne sont pas sauvegardees")
            raise Arret(f"{contexte} : modale inconnue « {ecran.titre} » "
                        f"({textes[:300]}) ; voir le rapport ; {suite}")
        self._touche(12, fenetre)
        return V_INCONNUE

    def _traiter_modales(self, contexte: str) -> list[str]:
        verdicts: list[str] = []
        for _ in range(self.PLAFOND_MODALES):
            modales = self._modales()
            if not modales:
                return verdicts
            if len(modales) > 1:
                raise Arret(f"{contexte} : {len(modales)} modales ouvertes a "
                            f"la fois {[m.nom or m.id for m in modales]}")
            fenetre = modales[0].nom or modales[0].id
            ecran = self.rapport.relever(fenetre, contexte)
            verdicts.append(self._appliquer_regle(fenetre, ecran, contexte))
        raise Arret(f"{contexte} : {self.PLAFOND_MODALES} modales successives "
                    f"{verdicts}, la passe s'arrete")

    # -- un point ------------------------------------------------------------------

    def _vider(self, cellule: str, point: str) -> str:
        """Efface la ligne refusee — celle-la, et seulement si elle porte encore
        ce point.

        Le defilement est d'abord REMIS la ou la cellule a ete trouvee : un
        rang visible n'a de sens qu'a une position, et SAP peut avoir remis
        le defilement a zero en reaffichant l'ecran — la meme cellule visible
        serait alors une affectation existante, portant peut-etre la meme
        valeur. Second filet : la valeur relue doit etre ce point.

        Si la ligne refusee n'est plus la, la passe S'ARRETE, a blanc aussi :
        laissee dans la table, SAP la refuserait a chaque Entree suivante et
        le refus serait impute au point suivant, un par un, jusqu'au bout.
        """
        self.d.table_scroll(self._table, self._depart)
        try:
            actuel = self.d.read(cellule)
        except ObjetIntrouvable:
            actuel = None
        if actuel is not None and not actuel.strip():
            return "cellule deja vide"
        if actuel is None or not meme_valeur(point, actuel):
            self.rapport.relever("wnd[0]", f"point {point} : ligne refusee introuvable")
            raise Arret(f"point {point} : la ligne refusee n'est plus la ou elle a "
                        f"ete ecrite (la cellule "
                        f"{'a disparu' if actuel is None else 'porte ' + repr(actuel)}) ; "
                        f"laissee dans la table, elle serait refusee a chaque "
                        f"Entree suivante. La retirer a la main avant de "
                        f"relancer ; voir le rapport")
        self.d.write(cellule, "")
        self._touche(0)
        verdicts = self._traiter_modales(f"point {point} : apres effacement")
        statut = self.d.status()
        if statut.type in ("E", "A") or V_DEJA in verdicts:
            raise Arret(f"point {point} : la ligne refusee ne se laisse pas "
                        f"vider ({statut_texte(statut)} ; modales {verdicts})")
        return "ligne videe" + (f" ; modales {verdicts}" if verdicts else "")

    def affecter(self, classe: str, point: str) -> str:
        rang = self._premiere_ligne_vide()
        cellule = self._cellule(rang)
        self._ecrire(cellule, point)
        self._touche(0)
        verdicts = self._traiter_modales(f"point {point} : apres Entree")
        statut = self.d.status()
        avertissement = None
        if statut.type == "W":
            avertissement = statut
            self.rapport.ligne(f"  point {point} : avertissement "
                               f"{statut_texte(statut)}, seconde Entree")
            self._touche(0)
            verdicts += self._traiter_modales(f"point {point} : apres seconde Entree")
            statut = self.d.status()
        self.rapport.ligne(f"  point {point} : statut {statut_texte(statut)} ; "
                           f"modales {verdicts or '-'}")

        if V_DEJA in verdicts:
            etat = DEJA_AFFECTE
            detail = (f"modale « {self._textes_modale[:200]} » ; "
                      + self._vider(cellule, point))
        elif statut.type in ("E", "A"):
            etat = REFUSE
            detail = f"{statut_texte(statut)} ; " + self._vider(cellule, point)
        elif V_INCONNUE in verdicts:
            etat = POPUP_INCONNUE
            detail = ("modale inconnue annulee (a blanc), voir le rapport ; "
                      + self._vider(cellule, point))
        else:
            etat = SAISI
            morceaux = []
            if V_VALORISATION in verdicts:
                morceaux.append("caracteristiques obligatoires laissees vides")
            if avertissement is not None:
                morceaux.append(f"avertissement accepte par une seconde Entree : "
                                f"{statut_texte(avertissement)}")
            detail = " ; ".join(morceaux)
        self.journal.noter(classe, point, etat, detail)
        return etat

    # -- la sauvegarde, une par passe ------------------------------------------------

    def sauvegarder(self, classe: str) -> None:
        saisis = list(self._en_attente)
        if not saisis:
            self.journal.noter(classe, "", PASSE, "rien a sauvegarder")
            return
        if not self.executer:
            for point in saisis:
                self.journal.noter(classe, point, NON_SAUVEGARDE,
                                   "a blanc : saisi a l'ecran, jamais sauvegarde")
            self._en_attente = []
            return

        identite = self.d.screen()
        if identite.transaction != self.c.transaction:
            raise Arret(f"classe {classe} : transaction {identite.transaction!r} "
                        f"au moment de sauvegarder, {self.c.transaction!r} attendue")
        self._sauvegarde_en_cours = True
        self._presser(self.c.bouton_sauvegarde)
        verdicts = self._traiter_modales(f"classe {classe} : apres sauvegarde")
        statut = self.d.status()
        avertissement = None
        if statut.type == "W":
            avertissement = statut
            self.rapport.ligne(f"  sauvegarde : avertissement "
                               f"{statut_texte(statut)}, seconde Entree")
            self._touche(0)
            verdicts += self._traiter_modales(
                f"classe {classe} : apres sauvegarde, seconde Entree")
            statut = self.d.status()
        self.rapport.ligne(f"  sauvegarde : statut {statut_texte(statut)} ; "
                           f"modales {verdicts or '-'}")

        if statut.type in ("E", "A"):
            for point in saisis:
                self.journal.noter(classe, point, NON_SAUVEGARDE,
                                   f"sauvegarde refusee : {statut_texte(statut)}")
            self._en_attente = []
            self._sauvegarde_en_cours = False
            raise Arret(f"classe {classe} : sauvegarde refusee, "
                        f"{statut_texte(statut)}")

        if statut.type == "S":
            etat, detail = SAUVEGARDE, statut_texte(statut)
        else:
            etat = A_VERIFIER
            detail = (f"statut non concluant apres sauvegarde "
                      f"({statut_texte(statut)}) : verifier dans SAP")
        if avertissement is not None:
            detail += (f" ; avertissement accepte par une seconde Entree : "
                       f"{statut_texte(avertissement)}")
        if verdicts:
            detail += f" ; modales {verdicts}"
        for point in saisis:
            self.journal.noter(classe, point, etat, detail)
        self._en_attente = []
        self._sauvegarde_en_cours = False

    # -- la passe -------------------------------------------------------------------

    def _journaliser_arret(self, classe: str, raison: str) -> None:
        self.journal.noter(classe, "", ARRET, raison)
        if self._sauvegarde_en_cours:
            etat, detail = A_VERIFIER, "arret PENDANT la sauvegarde : verifier dans SAP"
        else:
            etat, detail = NON_SAUVEGARDE, "arret avant la sauvegarde"
        for point in self._en_attente:
            self.journal.noter(classe, point, etat, detail)
        self._en_attente = []

    def passe(self, classe: str, type_classe: str, points: list[str]) -> Counter:
        mode = "EXECUTION (sauvegarde)" if self.executer else "A BLANC (aucune sauvegarde)"
        self.journal.noter(classe, "", PASSE, f"debut : {len(points)} point(s), "
                                              f"type de classe {type_classe}, {mode}")
        self.rapport.ligne(f"\n##### classe {classe} (type {type_classe}) : "
                           f"{len(points)} point(s), {mode}")
        compte: Counter = Counter()
        self._depart = 0
        self._en_attente = []
        self._sauvegarde_en_cours = False
        try:
            self.ouvrir()
            self.saisir_classe(classe, type_classe)
            self.choisir_type_objet()
            for point in points:
                etat = self.affecter(classe, point)
                compte[etat] += 1
                if etat == SAISI:
                    self._en_attente.append(point)
                if self.par_lot and len(self._en_attente) >= self.par_lot:
                    self.sauvegarder(classe)
            self.sauvegarder(classe)
        except Arret as arret:
            self._journaliser_arret(classe, str(arret))
            raise
        except ErreurFalcon as erreur:
            self._journaliser_arret(classe, f"{type(erreur).__name__} : {erreur}")
            raise
        except KeyboardInterrupt:
            self._journaliser_arret(classe, "interrompu au clavier (Ctrl-C)")
            raise
        except Exception as erreur:                 # un defaut du programme
            self._journaliser_arret(classe, f"{type(erreur).__name__} : {erreur}")
            raise
        self.journal.noter(classe, "", PASSE, f"fin : {resume(compte)}")
        return compte


# =====================================================================
# Le jeu, le pre-vol, la confirmation
# =====================================================================

def _decoder(brut: bytes) -> str:
    if brut.startswith(b"\xef\xbb\xbf"):
        return brut[3:].decode("utf-8")
    try:
        return brut.decode("utf-8")
    except UnicodeDecodeError:
        return brut.decode("cp1252")        # un export d'un poste Windows


def _lire_lignes(chemin: Path) -> tuple[list[str], list[dict[str, str]]]:
    """(colonnes, lignes) — le delimiteur est lu dans l'EN-TETE, pas devine.

    `csv.Sniffer` se trompe sur un petit fichier qui finit par une ligne vide
    — ce qu'Excel produit — et le refus qui suivait parlait d'une colonne
    absente. Un en-tete `point;classe` contient son delimiteur : on le lit.
    """
    if not chemin.exists():
        raise JeuInvalide(f"jeu introuvable : {chemin}")
    texte = _decoder(chemin.read_bytes())
    premiere = texte.split("\n", 1)[0].rstrip("\r")
    delimiteur = next((d for d in (";", ",", "\t") if d in premiere), None)
    if delimiteur is None:
        raise JeuInvalide(f"{chemin} : l'en-tete {premiere!r} ne porte ni « ; » "
                          f"ni « , » ni tabulation")
    lecteur = csv.DictReader(texte.splitlines(), delimiter=delimiteur,
                             restkey="\x00surplus")
    colonnes = [c.strip() for c in (lecteur.fieldnames or [])]
    lignes = []
    for ligne in lecteur:
        if all(not (v or "").strip() for v in ligne.values()
               if isinstance(v, str) or v is None):
            continue                                    # ligne vide
        lignes.append({c.strip(): (v or "").strip() for c, v in ligne.items()
                       if isinstance(c, str)})
    return colonnes, lignes


def lire_points(chemin: Path) -> dict[str, list[str]]:
    """{classe: [points]} dans l'ordre du fichier. Refuse plutot que deviner."""
    colonnes, lignes = _lire_lignes(chemin)
    for colonne in (COLONNE_POINT, COLONNE_CLASSE):
        if colonne not in colonnes:
            raise JeuInvalide(f"{chemin} : colonne {colonne!r} absente "
                              f"(colonnes lues : {colonnes})")
    par_classe: dict[str, list[str]] = {}
    for rang, ligne in enumerate(lignes, start=2):
        point = ligne.get(COLONNE_POINT, "")
        classe = ligne.get(COLONNE_CLASSE, "")
        if not classe:
            raise JeuInvalide(f"{chemin}, ligne {rang} : classe vide")
        if not _NUMERO.fullmatch(point):
            raise JeuInvalide(f"{chemin}, ligne {rang} : point {point!r} n'est "
                              f"pas un numero (chiffres seulement)")
        if len(point) > LONGUEUR_POINT:
            raise JeuInvalide(f"{chemin}, ligne {rang} : point {point!r} a "
                              f"{len(point)} chiffres, {LONGUEUR_POINT} au plus")
        deja = par_classe.setdefault(classe, [])
        if any(meme_valeur(point, p) for p in deja):
            raise JeuInvalide(f"{chemin}, ligne {rang} : point {point} en "
                              f"double pour la classe {classe}")
        deja.append(point)
    if not par_classe:
        raise JeuInvalide(f"{chemin} : aucune ligne")
    return par_classe


def prevol(par_classe: dict[str, list[str]], *, classes: list[str],
           plafond: int, executer: bool) -> dict[str, list[str]]:
    """Ce qu'on refuse avant tout contact avec SAP."""
    if plafond <= 0:
        raise Prevol(f"plafond {plafond} : il faut un entier strictement positif")
    manquantes = [c for c in classes if c not in par_classe]
    if manquantes:
        raise Prevol(f"classe(s) {manquantes} absente(s) du jeu "
                     f"(presentes : {list(par_classe)})")
    retenues = {c: p for c, p in par_classe.items() if not classes or c in classes}
    if not executer and len(retenues) > 1:
        raise Prevol(f"a blanc, une seule classe par lancement : les saisies "
                     f"restent a l'ecran sans etre sauvegardees, et quitter "
                     f"CL24N est un geste a faire a la main entre deux "
                     f"classes. Preciser --classe parmi {list(retenues)}")
    for classe, points in retenues.items():
        if len(points) > plafond:
            raise Prevol(f"classe {classe} : {len(points)} point(s), plafond "
                         f"{plafond}")
    return retenues


def confirmer(classe: str, identite: Identite, *,
              lire: Callable[[str], str] = input,
              ecrire: Callable[[str], None] = print) -> bool:
    """Le nom de la classe en toutes lettres — pas un o/n, qui se tape sans lire."""
    ecrire(f"  systeme {identite.systeme or '-'}  mandant {identite.mandant or '-'}"
           f"  langue {identite.langue or '-'}")
    ecrire(f"  cette passe va SAUVEGARDER dans CL24N les affectations a la "
           f"classe {classe}")
    try:
        reponse = lire("  tapez le nom de la classe pour confirmer, autre chose "
                       "annule : ")
    except EOFError:
        return False
    return reponse.strip().upper() == classe.strip().upper()


# =====================================================================
# Ligne de commande
# =====================================================================

def analyser(argv: list[str] | None = None) -> argparse.Namespace:
    parseur = argparse.ArgumentParser(
        prog="cl24n_classer",
        description="CL24N : affecter des points de mesure a une classe, une "
                    "passe par classe. A blanc par defaut.")
    parseur.add_argument("jeu", type=Path,
                         help="CSV avec les colonnes `point` et `classe`")
    parseur.add_argument("--type-classe", required=True,
                         help="type de classe, saisi sur l'ecran initial")
    parseur.add_argument("--plafond-points", required=True, type=int,
                         help="nombre maximal de points par passe ; le jeu est "
                              "refuse au-dela, avant tout contact avec SAP")
    parseur.add_argument("--classe", action="append", default=[],
                         help="ne traiter que cette classe (repetable)")
    parseur.add_argument("--executer", action="store_true",
                         help="sauvegarder. Sans ce drapeau, rien n'est "
                              "sauvegarde et la sauvegarde est refusee")
    parseur.add_argument("--par-lot", type=int, default=0,
                         help="sauvegarder toutes les N saisies au lieu d'une "
                              "fois en fin de passe (0, le defaut)")
    parseur.add_argument("--sortie", type=Path, default=Path("sorties"),
                         help="dossier du journal et du rapport (defaut : sorties/)")
    parseur.add_argument("--connexion", type=int, default=0)
    parseur.add_argument("--session", type=int, default=0)
    return parseur.parse_args(argv)


def executer_sur(driver: Driver, retenues: dict[str, list[str]], *,
                 type_classe: str, executer: bool, sortie: Path,
                 par_lot: int = 0,
                 lire: Callable[[str], str] = input,
                 ecrire: Callable[[str], None] = print) -> int:
    """Toutes les passes, sur un driver deja obtenu. Rend le code de sortie."""
    sortie.mkdir(parents=True, exist_ok=True)
    horodatage = re.sub(r"[^0-9TZ]", "", maintenant())
    journal = Journal(sortie / f"cl24n_{horodatage}_journal.csv")
    rapport = Rapport(sortie / f"cl24n_{horodatage}_rapport.txt", driver)

    identite = driver.screen()
    if not executer:
        mode = "A BLANC : aucune sauvegarde, la sauvegarde est refusee"
    elif par_lot:
        mode = f"EXECUTION : sauvegarde toutes les {par_lot} saisies"
    else:
        mode = "EXECUTION : sauvegarde en fin de passe"
    entete = [
        f"CL24N — {mode}",
        f"  systeme {identite.systeme or '-'}  mandant {identite.mandant or '-'}"
        f"  langue {identite.langue or '-'}  transaction courante "
        f"{identite.transaction or '-'}",
        f"  type de classe {type_classe}",
        *(f"  classe {classe} : {len(points)} point(s)"
          for classe, points in retenues.items()),
        f"  journal {journal.chemin}",
        f"  rapport {rapport.chemin}",
    ]
    for ligne in entete:
        ecrire(ligne)
        rapport.ligne(ligne)

    automate = Automate(driver, journal, rapport, executer=executer,
                        par_lot=par_lot)
    code = 0
    restantes = list(retenues)
    try:
        for classe, points in retenues.items():
            restantes.remove(classe)
            if executer and not confirmer(classe, identite, lire=lire, ecrire=ecrire):
                journal.noter(classe, "", ARRET, "confirmation refusee : passe non lancee")
                ecrire(f"  classe {classe} : confirmation refusee, passe non lancee")
                code = 1
                break
            compte = automate.passe(classe, type_classe, points)
            ecrire(f"  classe {classe} : {resume(compte)}")
    except Arret as arret:
        ecrire(f"ARRET : {arret}")
        code = 1
    except ErreurFalcon as erreur:
        ecrire(f"ARRET ({type(erreur).__name__}) : {erreur}")
        code = 1
    except KeyboardInterrupt:
        ecrire("ARRET : interrompu au clavier ; le journal dit ce qui a ete fait")
        code = 130
    finally:
        # Un arret termine le LANCEMENT : les classes qui restaient le disent.
        if code:
            for classe in restantes:
                journal.noter(classe, "", PASSE, "non lancee : le lancement "
                                                 "s'est arrete avant")
        journal.fermer()
        rapport.fermer()
    if not executer:
        ecrire("  a blanc : les saisies sont a l'ecran et ne sont PAS "
               "sauvegardees. Quitter CL24N a la main, sans sauvegarder")
    ecrire(f"  journal {journal.chemin}")
    ecrire(f"  rapport {rapport.chemin}")
    return code


def main(argv: list[str] | None = None) -> int:
    # Une console Windows en cp1252 ne doit pas faire tomber un lancement sur
    # un caractere du rapport : on remplace, on ne plante pas.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = analyser(argv)
    if args.par_lot < 0:
        print("refus : --par-lot doit etre positif ou nul")
        return 2
    try:
        par_classe = lire_points(args.jeu)
        retenues = prevol(par_classe, classes=args.classe,
                          plafond=args.plafond_points, executer=args.executer)
    except (JeuInvalide, Prevol) as refus:
        print(f"refus avant tout contact avec SAP : {refus}")
        return 2

    try:
        from falcon.couture.sapgui import connecter                  # noqa: PLC0415
        driver = connecter(connexion=args.connexion, session=args.session)
    except SapIndisponible as erreur:
        print(f"SAP injoignable : {erreur}")
        return 2

    return executer_sur(driver, retenues, type_classe=args.type_classe,
                        executer=args.executer, sortie=args.sortie,
                        par_lot=args.par_lot)


if __name__ == "__main__":
    raise SystemExit(main())
