#!/usr/bin/env python3
"""CL24N — affecter des points de mesure a une classe, une passe par classe.

Programme AUTONOME. Un seul fichier, aucune dependance : ni FALCON, ni PyYAML,
rien d'autre que la bibliotheque standard de Python et `pywin32` pour parler a
SAP. On le copie ou on veut, on double-clique sur `CL24N.bat`, et il affiche un
menu.

    python cl24n.py                      le menu
    python cl24n.py --aide               les options, pour un lancement scripte

**Ce qu'il fait.** Pour chaque classe : `/nCL24N`, la classe et son type,
le type d'objet « point de mesure », puis chaque point dans la premiere
ligne vide du tableau, Entree, et UNE sauvegarde en fin de passe.

**Ce qu'il refuse de faire.** Trois gardes, parce qu'un automate qui ecrit
dans un ERP sans elles n'est pas simple, il est nu :

- **a blanc par defaut.** Sans `--executer`, presser « Sauvegarder » leve une
  exception : c'est refuse mecaniquement, pas seulement evite. Les saisies
  restent a l'ecran, jamais sauvegardees — on quitte CL24N a la main.
- **plafond obligatoire.** Le nombre de points par passe est borne, et le
  fichier est refuse AVANT tout contact avec SAP s'il le depasse.
- **l'inconnu arrete.** Une fenetre surgissante qu'aucune regle ne reconnait
  arrete tout avant la sauvegarde. A blanc, si elle suit l'Entree d'un point,
  elle est annulee (F12), la ligne du point est videe et la passe continue :
  le but d'un passage a blanc est d'en voir le plus possible.

**Rien ici n'a encore parle a un SAP.** Ce que le programme SAIT vient de la
trace du recorder ; ce qu'il SUPPOSE est marque HYPOTHESE dans `Cibles` et
dans les regles de fenetre surgissante, et se tranche en relisant le rapport
du premier passage a blanc. Les champs sont cherches par la FIN de leur
identifiant, jamais par un chemin complet : le numero de sous-ecran change
avec le type d'objet affiche.

Chaque lancement ecrit deux fichiers dans `sorties`, a cote du programme : le
**journal** (CSV, une ligne par evenement) et le **rapport** (texte, chaque
ecran et chaque fenetre surgissante rencontres). Les deux s'ecrivent au fil de
l'eau : une coupure ne les perd pas.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

#: Le dossier du programme. Les sorties et le jeu d'exemple s'y rapportent,
#: pas au dossier courant : un double-clic n'a pas de dossier courant lisible.
ICI = Path(__file__).resolve().parent

VERSION = "1.0"


# =====================================================================
# Erreurs
# =====================================================================

class ErreurCL24N(Exception):
    """Racine commune."""


class SapIndisponible(ErreurCL24N):
    """Aucun SAP GUI joignable : pas de pywin32, pas de session, pas de
    scripting autorise."""


class ObjetIntrouvable(ErreurCL24N):
    """`findById` n'a rien rendu : le controle est absent de l'ecran courant."""


class ErreurCouture(ErreurCL24N):
    """SAP a refuse un geste, ou la session ne repond plus."""


class RefusSauvegarde(ErreurCL24N):
    """Une sauvegarde a ete demandee en mode a blanc.

    Le mode a blanc est MECANIQUE : ce n'est pas le programme qui s'abstient
    d'appeler, c'est l'appel qui refuse. Un oubli dans la logique ne peut donc
    pas sauvegarder par accident.
    """


class Arret(ErreurCL24N):
    """Arret propre : la passe s'interrompt et rien n'est sauvegarde apres."""


class Prevol(ErreurCL24N):
    """Refus avant tout contact avec SAP."""


class JeuInvalide(Prevol):
    """Le fichier de points ne peut pas etre lu."""


# =====================================================================
# Ce qu'on sait d'un ecran SAP
# =====================================================================

def maintenant() -> str:
    return (datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"))


def empreinte(identifiants: Iterable[str]) -> str:
    """Empreinte stable d'un ensemble d'identifiants, pour ne relever un
    ecran en entier qu'une fois."""
    uniques = sorted(set(identifiants))
    return hashlib.sha256("\n".join(uniques).encode("utf-8")).hexdigest()[:16]


#: Le segment de fenetre dans un identifiant SAP, cherche en SOUS-CHAINE.
#: SAP rend un chemin ABSOLU — `/app/con[0]/ses[0]/wnd[0]` — la ou la trace du
#: recorder ecrit `wnd[0]`. Les deux designent la meme fenetre et `findById`
#: accepte les deux : c'est une difference d'ECRITURE, pas de sens. Comparer
#: la forme longue a la forme courte ferait de la fenetre principale une
#: intruse a chaque geste.
_SEGMENT_DE_FENETRE = re.compile(r"wnd\[\d+\]")
FENETRE_PRINCIPALE = "wnd[0]"
CHAMP_DE_COMMANDE = "wnd[0]/tbar[0]/okcd"


def fenetre_de(identifiant: str) -> str:
    """`wnd[N]` lu dans un identifiant, quelle qu'en soit l'ecriture.

    Rend la chaine VIDE quand l'identifiant n'en nomme aucune — et c'est un
    refus, pas un defaut : un controle qu'on ne sait pas situer ne doit pas
    etre repute etre dans la fenetre principale.
    """
    trouve = _SEGMENT_DE_FENETRE.search(identifiant)
    return trouve.group(0) if trouve else ""


@dataclass(frozen=True)
class Identite:
    """Ou l'on est : le systeme, le mandant, et l'ecran affiche."""

    systeme: str = ""
    mandant: str = ""
    langue: str = ""
    transaction: str = ""
    programme: str = ""
    dynpro: str = ""            # chaine : « 0100 » n'est pas « 100 »


@dataclass(frozen=True)
class Champ:
    id: str
    type: str = ""              # GuiTextField, GuiButton, GuiRadioButton...
    soustype: str = ""
    nom: str = ""
    texte: str = ""
    #: `None` = on ne sait pas. Un champ jamais observe ne doit pas se
    #: presenter comme modifiable.
    modifiable: bool | None = None
    infobulle: str = ""         # le seul libelle d'un bouton a icone


@dataclass(frozen=True)
class Ecran:
    """Le releve complet d'une fenetre, a plat.

    A plat et non en arbre : les identifiants SONT des chemins, et la
    recherche par FIN d'identifiant — imposee par la variabilite des numeros
    de sous-ecran — est triviale sur une liste.
    """

    identite: Identite
    fenetre: str = "wnd[0]"
    titre: str = ""
    champs: tuple[Champ, ...] = ()

    @property
    def empreinte(self) -> str:
        return empreinte(c.id for c in self.champs)

    def par_suffixe(self, suffixe: str) -> tuple[Champ, ...]:
        return tuple(c for c in self.champs if c.id.endswith(suffixe))


@dataclass(frozen=True)
class Statut:
    """La barre de statut apres une validation."""

    type: str = ""              # "" (vide) | S | W | I | E | A
    id: str = ""
    numero: str = ""            # chaine : « 045 » n'est pas 45
    texte: str = ""

    @property
    def cle(self) -> str:
        return f"{self.id}:{self.numero}"


@dataclass(frozen=True)
class Fenetre:
    id: str
    type: str = ""              # GuiMainWindow | GuiModalWindow
    titre: str = ""

    @property
    def nom(self) -> str:
        return fenetre_de(self.id)

    @property
    def surgissante(self) -> bool:
        """VRAI seulement si l'on a LU une fenetre qui n'est pas la principale.

        Un identifiant qu'on ne sait pas situer rend FAUX : « je ne sais pas »
        ne se journalise pas comme « c'est une boite de dialogue ».
        """
        nom = self.nom
        return bool(nom) and nom != FENETRE_PRINCIPALE


# =====================================================================
# Le seul endroit qui parle a SAP
# =====================================================================

#: Defauts des attributs facultatifs d'un objet d'ecran. La surface d'un
#: controle varie avec son type : un shell n'a pas de `Changeable`, un
#: conteneur pas de `Tooltip`. Un releve doit noter l'absence, pas
#: s'interrompre dessus.
FACULTATIFS: dict[str, Any] = {
    "SubType": "", "Name": "", "Text": "", "Changeable": True, "Tooltip": "",
}


def _importer() -> Any:
    try:
        import win32com.client                              # noqa: PLC0415
    except ImportError as erreur:
        raise SapIndisponible(
            f"pywin32 n'est pas installe ({erreur}). Ce programme ne parle a "
            f"SAP que depuis Windows : taper `pip install pywin32`, et "
            f"activer le scripting des deux cotes — client (Options > "
            f"Accessibilite et scripting) et serveur (sapgui/user_scripting)"
        ) from erreur
    return win32com.client


def _erreur_com() -> type[BaseException]:
    try:
        import pywintypes                                   # noqa: PLC0415
    except ImportError:
        return Exception
    return pywintypes.com_error                             # type: ignore[attr-defined]


def connecter(*, connexion: int = 0, session: int = 0) -> "SapGui":
    """Se greffe sur une session SAP DEJA ouverte.

    N'ouvre aucune session et ne demande aucun mot de passe : vous ouvrez SAP
    et vous vous authentifiez vous-meme. Aucun identifiant ne transite par ce
    programme, et c'est delibere.
    """
    client = _importer()
    try:
        moteur = client.GetObject("SAPGUI").GetScriptingEngine
        brute = moteur.Children(connexion).Children(session)
    except Exception as erreur:
        raise SapIndisponible(
            f"aucune session SAP joignable (connexion {connexion}, session "
            f"{session}) : {erreur}. Verifier qu'un SAP GUI est ouvert, "
            f"connecte, et que le scripting est autorise des deux cotes"
        ) from erreur
    return SapGui(brute)


class SapGui:
    """SAP GUI Scripting, reduit aux douze gestes que ce programme fait.

    Les noms d'attributs COM viennent de la documentation du SAP GUI Scripting
    API. Ils ne sont pas devines — mais ils ne sont pas verifies non plus, et
    la difference compte : le premier contact reel les corrigera peut-etre, et
    il faut que ce soit un diagnostic lisible, pas un plantage opaque.
    """

    BARRE_DE_STATUT = "wnd[0]/sbar"

    def __init__(self, session: Any):
        self._session = session
        self._com = _erreur_com()

    # -- resolution et traduction d'erreurs ---------------------------------

    def _objet(self, id: str) -> Any:
        try:
            return self._session.findById(id)
        except Exception as erreur:
            if isinstance(erreur, self._com) or self._com is Exception:
                raise ObjetIntrouvable(
                    f"{id} : absent de l'ecran courant ({erreur})") from erreur
            raise

    def _appeler(self, quoi: str, action) -> Any:
        try:
            return action()
        except Exception as erreur:
            if isinstance(erreur, self._com) or self._com is Exception:
                raise ErreurCouture(f"{quoi} : {erreur}") from erreur
            raise

    @staticmethod
    def _facultatif(objet: Any, nom: str, defaut: Any = "") -> Any:
        try:
            valeur = getattr(objet, nom)
        except Exception:
            return defaut
        return defaut if valeur is None else valeur

    # -- observation ---------------------------------------------------------

    def screen(self) -> Identite:
        info = self._appeler("screen", lambda: self._session.Info)
        return Identite(
            systeme=str(self._facultatif(info, "SystemName")),
            mandant=str(self._facultatif(info, "Client")),
            langue=str(self._facultatif(info, "Language")),
            transaction=str(self._facultatif(info, "Transaction")),
            programme=str(self._facultatif(info, "Program")),
            dynpro=str(self._facultatif(info, "ScreenNumber")),
        )

    def fields(self, fenetre: str = "wnd[0]") -> Ecran:
        racine = self._objet(fenetre)
        champs: list[Champ] = []
        self._parcourir(racine, champs)
        return Ecran(identite=self.screen(), fenetre=fenetre,
                     titre=str(self._facultatif(racine, "Text")),
                     champs=tuple(champs))

    def _parcourir(self, objet: Any, trouves: list[Champ]) -> None:
        trouves.append(Champ(
            id=str(objet.Id), type=str(objet.Type),
            soustype=str(self._facultatif(objet, "SubType", FACULTATIFS["SubType"])),
            nom=str(self._facultatif(objet, "Name", FACULTATIFS["Name"])),
            texte=str(self._facultatif(objet, "Text", FACULTATIFS["Text"])),
            modifiable=bool(self._facultatif(objet, "Changeable",
                                             FACULTATIFS["Changeable"])),
            infobulle=str(self._facultatif(objet, "Tooltip", FACULTATIFS["Tooltip"])),
        ))
        enfants = self._facultatif(objet, "Children", None)
        if enfants is None:
            return
        for rang in range(int(getattr(enfants, "Count", 0) or 0)):
            self._parcourir(enfants.ElementAt(rang), trouves)

    def windows(self) -> tuple[Fenetre, ...]:
        enfants = self._appeler("windows", lambda: self._session.Children)
        ouvertes = []
        for rang in range(int(getattr(enfants, "Count", 0) or 0)):
            fenetre = enfants.ElementAt(rang)
            ouvertes.append(Fenetre(id=str(fenetre.Id), type=str(fenetre.Type),
                                    titre=str(self._facultatif(fenetre, "Text"))))
        return tuple(ouvertes)

    def status(self) -> Statut:
        barre = self._objet(self.BARRE_DE_STATUT)
        return Statut(
            type=str(self._facultatif(barre, "MessageType")),
            id=str(self._facultatif(barre, "MessageId")),
            numero=str(self._facultatif(barre, "MessageNumber")),
            texte=str(self._facultatif(barre, "Text")),
        )

    # -- lecture et saisie ----------------------------------------------------

    def read(self, id: str) -> str:
        objet = self._objet(id)
        return str(self._appeler(f"read({id!r})", lambda: objet.Text))

    def write(self, id: str, valeur: str) -> None:
        objet = self._objet(id)

        def poser() -> None:
            objet.Text = valeur

        self._appeler(f"write({id!r})", poser)

    # -- actions ---------------------------------------------------------------

    def press(self, id: str) -> None:
        objet = self._objet(id)
        self._appeler(f"press({id!r})", objet.press)

    def select(self, id: str) -> None:
        objet = self._objet(id)
        self._appeler(f"select({id!r})", objet.select)

    def vkey(self, n: int, fenetre: str = "wnd[0]") -> None:
        objet = self._objet(fenetre)
        self._appeler(f"vkey({n}, {fenetre!r})", lambda: objet.sendVKey(n))

    # -- le tableau : index VISIBLE, defilement explicite -----------------------

    def table_visible_rows(self, id: str) -> int:
        """La hauteur de la fenetre visible.

        Ce n'est PAS le nombre de lignes du tableau : au-dela de cette
        hauteur, une cellule ne resout pas tant qu'on n'a pas defile.
        """
        objet = self._objet(id)
        return int(self._appeler(f"table_visible_rows({id!r})",
                                 lambda: objet.VisibleRowCount))

    def table_scroll(self, id: str, position: int) -> None:
        """Place l'origine du defilement sur une ligne ABSOLUE."""
        objet = self._objet(id)

        def poser() -> None:
            objet.VerticalScrollbar.Position = int(position)

        self._appeler(f"table_scroll({id!r}, {position})", poser)


# =====================================================================
# Ce que le programme sait, et ce qu'il suppose
# =====================================================================

@dataclass(frozen=True)
class Cibles:
    """Ou le programme agit. Chaque valeur dit d'ou elle vient.

    « trace » : lu dans l'enregistrement du recorder, donc observe une fois
    sur un vrai systeme. « HYPOTHESE » : jamais observe ; le programme le
    cherche par la fin de l'identifiant et S'ARRETE en nommant ce qu'il a
    trouve a la place.
    """

    transaction: str = "CL24N"

    # HYPOTHESE — l'ecran initial. La trace ne saisit ni la classe ni son
    # type (SAP les avait memorises) ; les noms viennent de la structure
    # RMCLF que la trace emploie pour tout le reste.
    champ_classe: str = "RMCLF-CLASS"
    champ_type_classe: str = "RMCLF-KLART"

    # trace — le bouton qui ouvre le choix du type d'objet. La radio est
    # choisie par son LIBELLE ; l'index de la trace n'est qu'un repli.
    bouton_type_objet: str = "wnd[0]/tbar[1]/btn[33]"
    libelle_point: str = r"point de mesure|measuring point|messpunkt"
    radio_point: str = "radRMCLF-RADIO[1,0]"

    # trace — le tableau et sa colonne « point de mesure ».
    table: str = "tblSAPLCBCMTC_OBJ_CLASS"
    colonne_point: str = "ctxtRMCLF-POINT"

    # trace — la sauvegarde. C'est le SEUL geste que le mode a blanc refuse.
    bouton_sauvegarde: str = "wnd[0]/tbar[0]/btn[11]"

    # trace — dans la fenetre qui suit une validation quand la classe a des
    # caracteristiques obligatoires : « poursuivre » puis « valider ».
    bouton_poursuivre: str = "tbar[0]/btn[8]"
    bouton_valider: str = "tbar[0]/btn[0]"


#: HYPOTHESE — ce que dit la fenetre d'un point deja affecte a la classe.
#: Cherche dans le titre et les textes, dans la langue de connexion. Le
#: rapport du premier lancement donne le texte exact.
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

#: Colonnes du fichier de points.
COLONNE_POINT = "point"
COLONNE_CLASSE = "classe"
_NUMERO = re.compile(r"[0-9]+")
#: Un numero de point de mesure est un NUMC 12 : au-dela, SAP tronque.
LONGUEUR_POINT = 12

# -- etats du journal --------------------------------------------------------
SAISI = "SAISI"                     # entre et valide, en attente de sauvegarde
DEJA_AFFECTE = "DEJA_AFFECTE"       # le point etait deja dans la classe : KO
REFUSE = "REFUSE"                   # message E/A apres Entree : KO, ligne videe
POPUP_INCONNUE = "POPUP_INCONNUE"   # a blanc seulement : fenetre annulee
SAUVEGARDE = "SAUVEGARDE"           # statut S apres sauvegarde
A_VERIFIER = "A_VERIFIER"           # sauvegarde pressee, statut non concluant
NON_SAUVEGARDE = "NON_SAUVEGARDE"   # saisi, jamais sauvegarde
PASSE = "PASSE"                     # debut et fin de passe
ARRET = "ARRET"                     # la passe s'est arretee ; le detail dit pourquoi

# -- verdicts sur une fenetre surgissante ------------------------------------
V_DEJA = "deja_affecte"
V_VALORISATION = "valorisation_ignoree"
V_INCONNUE = "popup_inconnue_annulee"


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
    """Les boutons de la ZONE UTILISATEUR : Oui / Non / Annuler.

    Une boite de message n'en a pas — son seul bouton est dans la barre. Une
    QUESTION en a, et son bouton par defaut est « Oui » : Entree y repondrait
    sans qu'on l'ait decide. C'est pourquoi une question n'est jamais fermee
    automatiquement.
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
    """Une ligne par evenement. UTF-8 avec BOM et `;` : ce qu'Excel francais
    ouvre sans rien demander."""

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
    """Le releve de chaque ecran et de chaque fenetre surgissante rencontres.

    Un ecran est releve EN ENTIER la premiere fois qu'il est vu : identite,
    fenetres ouvertes, barre de statut, et une ligne par champ avec son type,
    son texte, son INFOBULLE — le seul libelle d'un bouton a icone, donc ce
    qui dit ce que `btn[8]` ou `btn[33]` font vraiment — et s'il est
    modifiable. Ensuite, seulement son titre, ses textes et la barre de
    statut : ce sont eux qui changent d'un point a l'autre, et eux qu'on
    relit pour ecrire une regle.
    """

    def __init__(self, chemin: Path, driver: Any):
        self.chemin = chemin
        self.d = driver
        self._fichier = chemin.open("w", encoding="utf-8-sig")
        self._vues: set[str] = set()
        self.releves = 0

    def ligne(self, texte: str) -> None:
        self._fichier.write(texte + "\n")
        self._fichier.flush()

    def relever(self, fenetre: str, contexte: str) -> Ecran:
        ecran = self.d.fields(fenetre)
        self.releves += 1
        self.ligne(f"\n=== releve {self.releves} | {contexte} | {fenetre} "
                   f"« {ecran.titre} » | empreinte {ecran.empreinte} ===")
        if ecran.empreinte in self._vues:
            self.ligne("  (deja relevee en entier plus haut)")
            for texte in textes_de(ecran):
                self.ligne(f"  « {texte} »")
            self.ligne(f"  statut {statut_texte(self.d.status())}")
        else:
            self._vues.add(ecran.empreinte)
            self.ligne(rendre_ecran(self.d, ecran))
        return ecran

    def fermer(self) -> None:
        self._fichier.close()


def rendre_ecran(driver: Any, ecran: Ecran) -> str:
    """Un ecran, en texte. Lecture seule, aucun geste."""
    identite = ecran.identite
    lignes = [
        f"  identite  systeme {identite.systeme or '-'}  mandant "
        f"{identite.mandant or '-'}  langue {identite.langue or '-'}  "
        f"transaction {identite.transaction or '-'}  programme "
        f"{identite.programme or '-'}  dynpro {identite.dynpro or '-'}",
    ]
    for ouverte in driver.windows():
        lignes.append(f"  fenetre   {ouverte.id}  {ouverte.type}  "
                      f"{'surgissante' if ouverte.surgissante else 'principale'}"
                      f"  « {ouverte.titre} »")
    lignes.append(f"  statut    {statut_texte(driver.status())}")
    lignes.append(f"  champs de {ecran.fenetre} ({len(ecran.champs)}) : "
                  f"id | type | nom | « texte » | infobulle | modifiable")
    for champ in ecran.champs:
        soustype = f"/{champ.soustype}" if champ.soustype else ""
        modifiable = {True: "oui", False: "non"}.get(champ.modifiable, "?")
        lignes.append(f"    {champ.id} | {champ.type}{soustype} | {champ.nom} | "
                      f"« {champ.texte} » | {champ.infobulle} | {modifiable}")
    return "\n".join(lignes)


# =====================================================================
# L'automate
# =====================================================================

class Automate:
    """Une passe CL24N par classe.

    Le driver est RECU, jamais fabrique : les tests le remplacent par un
    theatre, et l'automate ne sait pas s'il parle a SAP.
    """

    #: Au-dela, on ne cherche plus de ligne vide : quelque chose ne va pas.
    PLAFOND_LIGNES = 5000
    #: Fenetres surgissantes successives tolerees apres UN geste.
    PLAFOND_POPUPS = 6

    def __init__(self, driver: Any, journal: Journal, rapport: Rapport, *,
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
        self._textes_popup = ""
        self._en_attente: list[str] = []
        self._sauvegarde_en_cours = False

    # -- gestes gardes --------------------------------------------------------

    def _presser(self, cible: str) -> None:
        if not self.executer and cible.endswith("tbar[0]/btn[11]"):
            raise RefusSauvegarde(f"a blanc : {cible} est la sauvegarde, refusee")
        self.d.press(cible)

    def _touche(self, n: int, fenetre: str = "wnd[0]") -> None:
        if not self.executer and n == 11:
            raise RefusSauvegarde("a blanc : F11 est la sauvegarde, refusee")
        self.d.vkey(n, fenetre)

    def _ecrire(self, cible: str, valeur: str) -> None:
        """Ecrit, puis RELIT : ecrire sans que ca prenne ne leve rien."""
        self.d.write(cible, valeur)
        relu = self.d.read(cible)
        if not meme_valeur(valeur, relu):
            raise Arret(f"relecture apres ecriture dans {cible} : ecrit "
                        f"{valeur!r}, relu {relu!r}")

    # -- observation ------------------------------------------------------------

    def _popups(self) -> list[Fenetre]:
        return [f for f in self.d.windows() if f.surgissante]

    def _sans_popup(self, contexte: str) -> None:
        popups = self._popups()
        if not popups:
            return
        for popup in popups:
            self.rapport.relever(popup.nom or popup.id, contexte)
        raise Arret(f"{contexte} : fenetre(s) imprevue(s) "
                    f"{[p.nom or p.id for p in popups]} ; voir le rapport")

    @staticmethod
    def _champ_de_saisie(ecran: Ecran, suffixe: str) -> Champ:
        candidats = [c for c in ecran.par_suffixe(suffixe)
                     if c.type in SAISISSABLES]
        if len(candidats) == 1:
            return candidats[0]
        vus = [c.id for c in ecran.par_suffixe(suffixe)]
        raise Arret(
            f"champ *{suffixe} : {len(candidats)} champ(s) de saisie dans "
            f"{ecran.fenetre}, un attendu (identifiants finissant ainsi : "
            f"{vus or 'aucun'}). Le rapport releve l'ecran : y lire le vrai "
            f"nom et corriger `Cibles`")

    # -- etapes ------------------------------------------------------------------

    def ouvrir(self) -> Identite:
        self._sans_popup(f"avant /n{self.c.transaction} : une fenetre est "
                         f"ouverte, la fermer a la main")
        self.d.write(CHAMP_DE_COMMANDE, f"/n{self.c.transaction}")
        self._touche(0)
        self._sans_popup(f"apres /n{self.c.transaction}")
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
        self._sans_popup(f"classe {classe} : validation de l'ecran initial")
        statut = self.d.status()
        self.rapport.ligne(f"  classe {classe} type {type_classe} : statut "
                           f"{statut_texte(statut)}")
        if statut.type in ("E", "A"):
            raise Arret(f"classe {classe!r} type {type_classe!r} : "
                        f"{statut_texte(statut)}")
        self.rapport.relever("wnd[0]", f"classe {classe} : ecran d'affectation")

    def _table_des_points(self) -> bool:
        """Resout le tableau par sa cellule [0,0], et retient le prefixe."""
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
        popups = self._popups()
        if len(popups) > 1:
            raise Arret(f"type d'objet : {len(popups)} fenetres apres "
                        f"{self.c.bouton_type_objet}, une attendue")
        if popups:
            fenetre = popups[0].nom or popups[0].id
            ecran = self.rapport.relever(fenetre, "choix du type d'objet")
            radio = self._radio_point(ecran, fenetre)
            self.rapport.ligne(f"  radio choisie : {radio.id} « {radio.texte} »")
            self.d.select(radio.id)
            valider = bouton(ecran, self.c.bouton_valider)
            if valider is None:
                raise Arret(f"type d'objet : pas de bouton *{self.c.bouton_valider} "
                            f"dans {fenetre}")
            self._presser(valider)
            self._sans_popup("choix du type d'objet : apres validation")
        else:
            self.rapport.ligne(f"  type d'objet : aucune fenetre apres "
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
        libelles vides, ou dans une langue que le motif ignore — l'index de la
        trace sert, et le rapport ecrit ce qu'il a choisi.
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
                    f"{len(par_index)} champ(s) finissant par "
                    f"{self.c.radio_point} ; voir le rapport")

    # -- le tableau : index VISIBLE, defilement explicite ------------------------

    def _cellule(self, rang: int) -> str:
        return f"{self._table}/{self.c.colonne_point}[0,{rang}]"

    def _page(self, position: int, visibles: int) -> list[str]:
        """Les textes des cellules visibles, apres defilement.

        Par `read`, cellule par cellule, et non par `fields`, qui traverse
        TOUT l'ecran a chaque page : sur une classe de trois cents points,
        c'est la difference entre quelques secondes et une heure par passe.
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
        """Rang VISIBLE d'une cellule vide, le defilement laisse dessus ; None
        si rien depuis `depart`.

        S'arrete quand le defilement ne progresse plus : aucun compteur de SAP
        n'est fiable — `RowCount` compte les lignes vides de saisie, et la
        barre de defilement aussi.
        """
        position, precedente = depart, None
        while position < self.PLAFOND_LIGNES:
            page = self._page(position, visibles)
            if not page:
                raise Arret(f"tableau {self._table} : aucune cellule lisible a "
                            f"la position {position}")
            for rang, valeur in enumerate(page):
                if not valeur.strip():
                    self._depart = position
                    return rang
            if page == precedente:
                return None
            precedente = page
            position += len(page)
        raise Arret(f"tableau {self._table} : aucune ligne vide dans les "
                    f"{self.PLAFOND_LIGNES} premieres lignes")

    def _premiere_ligne_vide(self) -> int:
        """Le balayage part de la page ou la derniere ligne vide a ete trouvee.

        Le tableau ne fait que grandir sous nos ecritures, et les lignes
        libres sont derriere les lignes prises. Ce n'est qu'un point de
        depart — la cellule est RELUE vide juste avant d'y ecrire — et s'il
        ne mene a rien, on repart de zero une fois.
        """
        visibles = self.d.table_visible_rows(self._table)
        if visibles <= 0:
            raise Arret(f"tableau {self._table} : aucune ligne visible")
        rang = self._ligne_vide_depuis(self._depart, visibles)
        if rang is None and self._depart:
            self._depart = 0
            rang = self._ligne_vide_depuis(0, visibles)
        if rang is None:
            raise Arret(f"tableau {self._table} : aucune ligne vide, le "
                        f"defilement ne progresse plus")
        return rang

    # -- les fenetres surgissantes ------------------------------------------------

    def _fermer(self, fenetre: str, ecran: Ecran) -> None:
        valider = bouton(ecran, self.c.bouton_valider)
        if valider is not None:
            self._presser(valider)
        else:
            self._touche(0, fenetre)

    def _appliquer_regle(self, fenetre: str, ecran: Ecran, contexte: str) -> str:
        """Une fenetre, un verdict. L'ordre des regles est celui-ci a dessein."""
        textes = " | ".join(textes_de(ecran))

        # 1. HYPOTHESE : un point deja affecte le dit dans un texte — et c'est
        #    une boite de MESSAGE, sans bouton de choix. Une QUESTION qui
        #    contiendrait le mot reste inconnue : on n'y presse jamais le
        #    bouton par defaut.
        if MOTIF_DEJA_AFFECTE.search(textes) and not boutons_de_choix(ecran):
            self._textes_popup = textes
            self._fermer(fenetre, ecran)
            return V_DEJA

        # 2. trace : caracteristiques obligatoires — « poursuivre », puis
        #    « valider » sur la fenetre presente ensuite, que ce soit une
        #    autre ou encore la meme : la trace dit btn[8] puis btn[0], et
        #    rien de plus. Reconnue par son bouton, pas par son texte. Une
        #    QUESTION apres « poursuivre » n'est jamais validee : elle reste
        #    a l'ecran, et la regle 3 en decide au tour suivant.
        poursuivre = bouton(ecran, self.c.bouton_poursuivre)
        if poursuivre is not None:
            self._presser(poursuivre)
            suite = self._popups()
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
            raise Arret(f"{contexte} : fenetre inconnue « {ecran.titre} » "
                        f"({textes[:300]}) ; voir le rapport ; {suite}")
        self._touche(12, fenetre)
        return V_INCONNUE

    def _traiter_popups(self, contexte: str) -> list[str]:
        verdicts: list[str] = []
        for _ in range(self.PLAFOND_POPUPS):
            popups = self._popups()
            if not popups:
                return verdicts
            if len(popups) > 1:
                raise Arret(f"{contexte} : {len(popups)} fenetres ouvertes a la "
                            f"fois {[p.nom or p.id for p in popups]}")
            fenetre = popups[0].nom or popups[0].id
            ecran = self.rapport.relever(fenetre, contexte)
            verdicts.append(self._appliquer_regle(fenetre, ecran, contexte))
        raise Arret(f"{contexte} : {self.PLAFOND_POPUPS} fenetres successives "
                    f"{verdicts}, la passe s'arrete")

    # -- un point -----------------------------------------------------------------

    def _vider(self, cellule: str, point: str) -> str:
        """Efface la ligne refusee — celle-la, et seulement si elle porte
        encore ce point.

        Le defilement est d'abord REMIS la ou la cellule a ete trouvee : un
        rang visible n'a de sens qu'a une position, et SAP peut avoir remis le
        defilement a zero en reaffichant l'ecran — la meme cellule visible
        serait alors une affectation existante, portant peut-etre la meme
        valeur. Second filet : la valeur relue doit etre ce point.

        Si la ligne refusee n'est plus la, la passe S'ARRETE, a blanc aussi :
        laissee dans le tableau, SAP la refuserait a chaque Entree suivante et
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
            raise Arret(f"point {point} : la ligne refusee n'est plus la ou elle "
                        f"a ete ecrite (la cellule "
                        f"{'a disparu' if actuel is None else 'porte ' + repr(actuel)}) ; "
                        f"laissee dans le tableau, elle serait refusee a chaque "
                        f"Entree suivante. La retirer a la main avant de "
                        f"relancer ; voir le rapport")
        self.d.write(cellule, "")
        self._touche(0)
        verdicts = self._traiter_popups(f"point {point} : apres effacement")
        statut = self.d.status()
        if statut.type in ("E", "A") or V_DEJA in verdicts:
            raise Arret(f"point {point} : la ligne refusee ne se laisse pas "
                        f"vider ({statut_texte(statut)} ; fenetres {verdicts})")
        return "ligne videe" + (f" ; fenetres {verdicts}" if verdicts else "")

    def affecter(self, classe: str, point: str) -> str:
        rang = self._premiere_ligne_vide()
        cellule = self._cellule(rang)
        self._ecrire(cellule, point)
        self._touche(0)
        verdicts = self._traiter_popups(f"point {point} : apres Entree")
        statut = self.d.status()
        avertissement = None
        if statut.type == "W":
            avertissement = statut
            self.rapport.ligne(f"  point {point} : avertissement "
                               f"{statut_texte(statut)}, seconde Entree")
            self._touche(0)
            verdicts += self._traiter_popups(f"point {point} : apres seconde Entree")
            statut = self.d.status()
        self.rapport.ligne(f"  point {point} : statut {statut_texte(statut)} ; "
                           f"fenetres {verdicts or '-'}")

        if V_DEJA in verdicts:
            etat = DEJA_AFFECTE
            detail = (f"fenetre « {self._textes_popup[:200]} » ; "
                      + self._vider(cellule, point))
        elif statut.type in ("E", "A"):
            etat = REFUSE
            detail = f"{statut_texte(statut)} ; " + self._vider(cellule, point)
        elif V_INCONNUE in verdicts:
            etat = POPUP_INCONNUE
            detail = ("fenetre inconnue annulee (a blanc), voir le rapport ; "
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

    # -- la sauvegarde --------------------------------------------------------------

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
        verdicts = self._traiter_popups(f"classe {classe} : apres sauvegarde")
        statut = self.d.status()
        avertissement = None
        if statut.type == "W":
            avertissement = statut
            self.rapport.ligne(f"  sauvegarde : avertissement "
                               f"{statut_texte(statut)}, seconde Entree")
            self._touche(0)
            verdicts += self._traiter_popups(
                f"classe {classe} : apres sauvegarde, seconde Entree")
            statut = self.d.status()
        self.rapport.ligne(f"  sauvegarde : statut {statut_texte(statut)} ; "
                           f"fenetres {verdicts or '-'}")

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
            detail += f" ; fenetres {verdicts}"
        for point in saisis:
            self.journal.noter(classe, point, etat, detail)
        self._en_attente = []
        self._sauvegarde_en_cours = False

    # -- la passe ---------------------------------------------------------------------

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
        mode = ("EXECUTION (sauvegarde)" if self.executer
                else "A BLANC (aucune sauvegarde)")
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
        except KeyboardInterrupt:
            self._journaliser_arret(classe, "interrompu au clavier (Ctrl-C)")
            raise
        except Exception as erreur:
            self._journaliser_arret(classe, f"{type(erreur).__name__} : {erreur}")
            raise
        self.journal.noter(classe, "", PASSE, f"fin : {resume(compte)}")
        return compte


# =====================================================================
# Le fichier de points
# =====================================================================

def _decoder(brut: bytes) -> str:
    if brut.startswith(b"\xef\xbb\xbf"):
        return brut[3:].decode("utf-8")
    try:
        return brut.decode("utf-8")
    except UnicodeDecodeError:
        return brut.decode("cp1252")        # un export d'un poste Windows


def lire_points(chemin: Path) -> dict[str, list[str]]:
    """{classe: [points]} dans l'ordre du fichier. Refuse plutot que deviner.

    Le delimiteur est lu dans l'EN-TETE, jamais renifle : un reniflage se
    trompe sur un petit fichier qui finit par une ligne vide — ce qu'Excel
    produit — et le refus qui suit parle alors d'une colonne absente.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise JeuInvalide(f"fichier introuvable : {chemin}")
    texte = _decoder(chemin.read_bytes())
    premiere = texte.split("\n", 1)[0].rstrip("\r")
    delimiteur = next((d for d in (";", ",", "\t") if d in premiere), None)
    if delimiteur is None:
        raise JeuInvalide(f"{chemin} : l'en-tete {premiere!r} ne porte ni "
                          f"« ; » ni « , » ni tabulation")

    lecteur = csv.DictReader(texte.splitlines(), delimiter=delimiteur)
    colonnes = [c.strip() for c in (lecteur.fieldnames or [])]
    for colonne in (COLONNE_POINT, COLONNE_CLASSE):
        if colonne not in colonnes:
            raise JeuInvalide(f"{chemin} : colonne {colonne!r} absente "
                              f"(colonnes lues : {colonnes})")

    par_classe: dict[str, list[str]] = {}
    for rang, brute in enumerate(lecteur, start=2):
        ligne = {c.strip(): (v or "").strip() for c, v in brute.items()
                 if isinstance(c, str)}
        if not any(ligne.values()):
            continue                                    # ligne vide
        point, classe = ligne.get(COLONNE_POINT, ""), ligne.get(COLONNE_CLASSE, "")
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
    """Ce qu'on refuse AVANT tout contact avec SAP."""
    if plafond <= 0:
        raise Prevol(f"plafond {plafond} : il faut un entier strictement positif")
    manquantes = [c for c in classes if c not in par_classe]
    if manquantes:
        raise Prevol(f"classe(s) {manquantes} absente(s) du fichier "
                     f"(presentes : {list(par_classe)})")
    retenues = {c: p for c, p in par_classe.items() if not classes or c in classes}
    if not executer and len(retenues) > 1:
        raise Prevol(f"a blanc, une seule classe par lancement : les saisies "
                     f"restent a l'ecran sans etre sauvegardees, et quitter "
                     f"CL24N est un geste a faire a la main entre deux "
                     f"classes. Choisir parmi {list(retenues)}")
    for classe, points in retenues.items():
        if len(points) > plafond:
            raise Prevol(f"classe {classe} : {len(points)} point(s), plafond "
                         f"{plafond}")
    return retenues


# =====================================================================
# Le lancement
# =====================================================================

def confirmer(classe: str, identite: Identite, *, executer: bool,
              lire: Callable[[str], str], ecrire: Callable[[str], None]) -> bool:
    """Le nom de la classe en toutes lettres — pas un o/n, qui se tape sans lire.

    Meme en mode a blanc : rien n'y est sauvegarde, mais le programme SAISIT
    dans SAP, navigue, et peut poser des verrous. On ne le lance pas sans
    avoir lu sur quel systeme et quel mandant on est.
    """
    ecrire("")
    ecrire(f"  systeme {identite.systeme or '-'}   mandant "
           f"{identite.mandant or '-'}   langue {identite.langue or '-'}")
    if executer:
        ecrire(f"  cette passe va SAUVEGARDER dans CL24N les affectations a la "
               f"classe {classe}")
    else:
        ecrire(f"  cette passe va SAISIR la classe {classe} dans CL24N SANS "
               f"RIEN SAUVEGARDER")
    try:
        reponse = lire(f"  taper le nom de la classe pour lancer, autre chose "
                       f"annule : ")
    except EOFError:
        return False
    return reponse.strip().upper() == classe.strip().upper()


def executer_sur(driver: Any, retenues: dict[str, list[str]], *,
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
        f"CL24N {VERSION} — {mode}",
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
            if not confirmer(classe, identite, executer=executer,
                             lire=lire, ecrire=ecrire):
                journal.noter(classe, "", ARRET, "non confirmee : passe non lancee")
                ecrire(f"  classe {classe} : non confirmee, passe non lancee")
                code = 1
                break
            compte = automate.passe(classe, type_classe, points)
            ecrire(f"  classe {classe} : {resume(compte)}")
    except Arret as arret:
        ecrire(f"ARRET : {arret}")
        code = 1
    except ErreurCL24N as erreur:
        ecrire(f"ARRET ({type(erreur).__name__}) : {erreur}")
        code = 1
    except KeyboardInterrupt:
        ecrire("ARRET : interrompu au clavier ; le journal dit ce qui a ete fait")
        code = 130
    except Exception as erreur:                     # un defaut du programme
        ecrire(f"ARRET ({type(erreur).__name__}) : {erreur}")
        code = 1
    finally:
        # Un arret termine le LANCEMENT : les classes qui restaient le disent.
        if code:
            for classe in restantes:
                journal.noter(classe, "", PASSE, "non lancee : le lancement "
                                                 "s'est arrete avant")
        journal.fermer()
        rapport.fermer()
    if not executer:
        ecrire("")
        ecrire("  A BLANC : les saisies sont a l'ecran et ne sont PAS "
               "sauvegardees.")
        ecrire("  Quitter CL24N a la main, sans sauvegarder.")
    ecrire("")
    ecrire(f"  journal  {journal.chemin}")
    ecrire(f"  rapport  {rapport.chemin}")
    return code


def diagnostiquer(driver: Any, *, fenetre: str = "wnd[0]") -> str:
    """L'ecran courant, en texte. LECTURE SEULE : aucun geste n'est fait."""
    return rendre_ecran(driver, driver.fields(fenetre))


# =====================================================================
# Le menu
# =====================================================================

BANNIERE = f"""
======================================================================
  CL24N {VERSION} — affecter des points de mesure a une classe
======================================================================"""


def _demander(lire, ecrire, question: str, defaut: str = "") -> str:
    invite = f"  {question}" + (f" [{defaut}] " if defaut else " ")
    try:
        reponse = lire(invite).strip()
    except EOFError:
        return defaut
    return reponse or defaut


def _choisir_classe(lire, ecrire, classes: list[str]) -> str | None:
    if len(classes) == 1:
        return classes[0]
    ecrire("")
    for rang, classe in enumerate(classes, start=1):
        ecrire(f"    {rang}  {classe}")
    reponse = _demander(lire, ecrire, "numero de la classe :")
    if not reponse.isdigit() or not 1 <= int(reponse) <= len(classes):
        ecrire("  ce n'est pas un numero de la liste.")
        return None
    return classes[int(reponse) - 1]


def _parametres(lire, ecrire, jeu_defaut: Path) -> tuple | None:
    """(par_classe, type_classe) lus au clavier, ou None si ca n'aboutit pas."""
    chemin = Path(_demander(lire, ecrire, "fichier des points :", str(jeu_defaut)))
    try:
        par_classe = lire_points(chemin)
    except JeuInvalide as refus:
        ecrire(f"  REFUS : {refus}")
        return None
    total = sum(len(p) for p in par_classe.values())
    ecrire(f"  {chemin} : {total} point(s), {len(par_classe)} classe(s)")
    type_classe = _demander(lire, ecrire, "type de classe :")
    if not type_classe:
        ecrire("  le type de classe est obligatoire : il est saisi sur l'ecran "
               "initial de CL24N.")
        return None
    return par_classe, type_classe


def _lancer(driver, lire, ecrire, sortie: Path, jeu_defaut: Path, *,
            executer: bool) -> None:
    parametres = _parametres(lire, ecrire, jeu_defaut)
    if parametres is None:
        return
    par_classe, type_classe = parametres

    classes: list[str] = []
    if not executer:
        choisie = _choisir_classe(lire, ecrire, list(par_classe))
        if choisie is None:
            return
        classes = [choisie]

    concernees = {c: p for c, p in par_classe.items()
                  if not classes or c in classes}
    defaut = str(max((len(p) for p in concernees.values()), default=1))
    plafond = _demander(lire, ecrire, "plafond de points par classe :", defaut)
    if not plafond.isdigit():
        ecrire("  le plafond est un nombre entier.")
        return
    try:
        retenues = prevol(par_classe, classes=classes, plafond=int(plafond),
                          executer=executer)
    except Prevol as refus:
        ecrire(f"  REFUS avant tout contact avec SAP : {refus}")
        return

    executer_sur(driver, retenues, type_classe=type_classe, executer=executer,
                 sortie=sortie, lire=lire, ecrire=ecrire)


def _relever(driver, lire, ecrire, sortie: Path) -> None:
    fenetre = _demander(lire, ecrire, "fenetre a relever :", "wnd[0]")
    try:
        texte = diagnostiquer(driver, fenetre=fenetre)
    except ErreurCL24N as erreur:
        ecrire(f"  {type(erreur).__name__} : {erreur}")
        return
    sortie.mkdir(parents=True, exist_ok=True)
    horodatage = re.sub(r"[^0-9TZ]", "", maintenant())
    chemin = sortie / f"cl24n_{horodatage}_ecran.txt"
    chemin.write_text(texte + "\n", encoding="utf-8-sig")
    ecrire(texte)
    ecrire("")
    ecrire(f"  releve ecrit dans {chemin}")


def _connexion(driver, ecrire) -> None:
    identite = driver.screen()
    ecrire("")
    ecrire(f"  systeme      {identite.systeme or '-'}")
    ecrire(f"  mandant      {identite.mandant or '-'}")
    ecrire(f"  langue       {identite.langue or '-'}")
    ecrire(f"  transaction  {identite.transaction or '-'}")
    ecrire(f"  programme    {identite.programme or '-'}")
    ecrire(f"  dynpro       {identite.dynpro or '-'}")
    for fenetre in driver.windows():
        ecrire(f"  fenetre      {fenetre.id}  {fenetre.type}  "
               f"{'surgissante' if fenetre.surgissante else 'principale'}  "
               f"« {fenetre.titre} »")
    ecrire(f"  statut       {statut_texte(driver.status())}")


def _lister(ecrire, sortie: Path) -> None:
    fichiers = sorted(sortie.glob("cl24n_*")) if sortie.is_dir() else []
    if not fichiers:
        ecrire(f"  aucune sortie dans {sortie}")
        return
    ecrire(f"  {sortie}")
    for fichier in fichiers[-20:]:
        ecrire(f"    {fichier.name:<44} {fichier.stat().st_size:>9} octets")


def menu(fabrique: Callable[[], Any], *, sortie: Path, jeu_defaut: Path,
         lire: Callable[[str], str] = input,
         ecrire: Callable[[str], None] = print) -> int:
    """Le menu. `fabrique` rend un driver — la connexion est PARESSEUSE.

    Paresseuse parce qu'on ouvre souvent le programme avant SAP : une
    connexion au demarrage ferait echouer le lancement au lieu d'afficher le
    menu et de dire quoi faire.
    """
    driver: Any = None

    def obtenir() -> Any:
        nonlocal driver
        if driver is None:
            driver = fabrique()
        return driver

    ecrire(BANNIERE)
    ecrire(f"  sorties : {sortie}")
    while True:
        ecrire("")
        ecrire("   1  Verifier la connexion SAP")
        ecrire("   2  Relever l'ecran courant (lecture seule)")
        ecrire("   3  Passage A BLANC — une classe, aucune sauvegarde")
        ecrire("   4  EXECUTER — toutes les classes du fichier, avec sauvegarde")
        ecrire("   5  Lister les sorties")
        ecrire("   0  Quitter")
        try:
            choix = lire("  choix : ").strip()
        except EOFError:
            return 0
        if choix in ("0", "q", "Q"):
            return 0
        if choix == "5":
            _lister(ecrire, sortie)
            continue
        if choix not in ("1", "2", "3", "4"):
            ecrire("  choix inconnu.")
            continue
        try:
            actif = obtenir()
        except SapIndisponible as erreur:
            ecrire(f"  SAP injoignable : {erreur}")
            continue
        try:
            if choix == "1":
                _connexion(actif, ecrire)
            elif choix == "2":
                _relever(actif, lire, ecrire, sortie)
            else:
                _lancer(actif, lire, ecrire, sortie, jeu_defaut,
                        executer=(choix == "4"))
        except KeyboardInterrupt:
            ecrire("")
            ecrire("  interrompu au clavier.")
        except ErreurCL24N as erreur:
            ecrire(f"  {type(erreur).__name__} : {erreur}")


# =====================================================================
# Ligne de commande
# =====================================================================

def analyser(argv: list[str] | None = None) -> argparse.Namespace:
    parseur = argparse.ArgumentParser(
        prog="cl24n", add_help=False,
        description="CL24N : affecter des points de mesure a une classe. "
                    "Sans argument, affiche un menu. A blanc par defaut.")
    parseur.add_argument("--aide", "-h", action="help",
                         help="afficher ces options")
    parseur.add_argument("jeu", nargs="?", type=Path,
                         help="CSV avec les colonnes `point` et `classe`")
    parseur.add_argument("--type-classe", help="type de classe, saisi sur "
                                               "l'ecran initial")
    parseur.add_argument("--plafond-points", type=int,
                         help="nombre maximal de points par classe ; le "
                              "fichier est refuse au-dela, avant tout contact "
                              "avec SAP")
    parseur.add_argument("--classe", action="append", default=[],
                         help="ne traiter que cette classe (repetable)")
    parseur.add_argument("--executer", action="store_true",
                         help="sauvegarder. Sans ce drapeau, rien n'est "
                              "sauvegarde et la sauvegarde est refusee")
    parseur.add_argument("--par-lot", type=int, default=0,
                         help="sauvegarder toutes les N saisies au lieu d'une "
                              "fois en fin de passe (0, le defaut)")
    parseur.add_argument("--sortie", type=Path, default=ICI / "sorties",
                         help="dossier du journal et du rapport")
    parseur.add_argument("--connexion", type=int, default=0)
    parseur.add_argument("--session", type=int, default=0)
    return parseur.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # Une console Windows en cp1252 ne doit pas faire tomber un lancement sur
    # un caractere du rapport : on remplace, on ne plante pas.
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            try:
                flux.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass
    args = analyser(argv)

    def fabrique() -> Any:
        return connecter(connexion=args.connexion, session=args.session)

    if args.jeu is None:
        return menu(fabrique, sortie=args.sortie, jeu_defaut=ICI / "points.csv")

    if args.type_classe is None or args.plafond_points is None:
        print("refus : --type-classe et --plafond-points sont obligatoires "
              "pour un lancement scripte. Sans argument, le programme affiche "
              "un menu qui les demande.")
        return 2
    if args.par_lot < 0:
        print("refus : --par-lot doit etre positif ou nul")
        return 2
    try:
        par_classe = lire_points(args.jeu)
        retenues = prevol(par_classe, classes=args.classe,
                          plafond=args.plafond_points, executer=args.executer)
    except Prevol as refus:
        print(f"refus avant tout contact avec SAP : {refus}")
        return 2
    try:
        driver = fabrique()
    except SapIndisponible as erreur:
        print(f"SAP injoignable : {erreur}")
        return 2
    return executer_sur(driver, retenues, type_classe=args.type_classe,
                        executer=args.executer, sortie=args.sortie,
                        par_lot=args.par_lot)


if __name__ == "__main__":
    raise SystemExit(main())
