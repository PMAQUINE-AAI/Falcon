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
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
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
    """La seule chose que le programme sait d'avance : ce qui sauvegarde.

    Tout le reste — les champs, les boutons, les fenetres, l'enchainement —
    se dicte et vit dans une recette. Ceci ne reste ici que parce que le
    mode a blanc doit pouvoir REFUSER la sauvegarde, et qu'une garde qu'on
    pourrait dicter ne serait plus une garde.
    """

    bouton_sauvegarde: str = "tbar[0]/btn[11]"
    touche_sauvegarde: int = 11


# =====================================================================
# Un geste, et la recette qui les enchaine
# =====================================================================

#: Les cinq gestes qu'une recette peut porter. Table FERMEE : un geste que
#: le pilotage saurait faire mais que le rejeu ne saurait pas refaire serait
#: un piege — la passe dictee marcherait, le rejeu ferait autre chose.
ECRIRE = "ecrire"                           # une valeur dans un champ
ECRIRE_LIGNE_LIBRE = "ecrire_ligne_libre"   # dans la 1re cellule libre d'un tableau
PRESSER = "presser"                         # un bouton
SELECTIONNER = "selectionner"               # une radio, une case, un onglet
TOUCHE = "touche"                           # Entree, F8, F11...
MARQUER_KO = "marquer_ko"                   # « cette fenetre veut dire : refuse »
GESTES = (ECRIRE, ECRIRE_LIGNE_LIBRE, PRESSER, SELECTIONNER, TOUCHE, MARQUER_KO)

#: Les trois moments d'une recette. Une passe CL24N n'est pas une boucle
#: plate : ouvrir la transaction et saisir la classe se font UNE fois, chaque
#: point se saisit N fois, et la sauvegarde se fait une fois a la fin.
ENTETE = "entete"
CORPS = "corps"
CLOTURE = "cloture"
MOMENTS = (ENTETE, CORPS, CLOTURE)

#: Ce qu'on tape pour changer de moment. `boucle` dit mieux que `corps` ce
#: qui se passe — ce qui suit se repete — et c'est le mot de l'aide.
ALIAS_DE_MOMENT = {"entete": ENTETE, "boucle": CORPS, "corps": CORPS,
                   "cloture": CLOTURE, "fin de classe": CLOTURE}


@dataclass(frozen=True)
class Source:
    """D'ou vient la valeur tapee : une colonne du fichier, ou une constante."""

    colonne: str = ""
    constante: str = ""

    def valeur(self, ligne: dict[str, str]) -> str:
        if self.colonne:
            if self.colonne not in ligne:
                raise Arret(f"colonne {self.colonne!r} absente de la ligne "
                            f"{sorted(ligne)} : la recette la demande")
            return ligne[self.colonne]
        return self.constante

    def __str__(self) -> str:
        return f"colonne {self.colonne}" if self.colonne else f"« {self.constante} »"

    def en_json(self) -> dict:
        return ({"colonne": self.colonne} if self.colonne
                else {"constante": self.constante})

    @staticmethod
    def de_json(brut: dict) -> "Source":
        return Source(colonne=str(brut.get("colonne", "")),
                      constante=str(brut.get("constante", "")))


@dataclass(frozen=True)
class Geste:
    """Un geste dicte, tel qu'il sera rejoue.

    **La cible est gardee sous DEUX formes.** L'identifiant complet, tel que
    SAP l'a rendu au moment de la dictee, et son SUFFIXE. Au rejeu on essaie
    l'identifiant, puis le suffixe : le numero de sous-ecran change avec le
    type d'objet affiche, et un chemin fige cesse de resoudre sans que rien
    ne le dise.

    `si_fenetre` porte le TITRE de la fenetre surgissante dans laquelle le
    geste a ete dicte. Au rejeu, le geste n'est joue que si cette fenetre est
    la : une fenetre de valorisation qui ne surgit que pour certaines classes
    ne doit pas faire echouer les autres.
    """

    type: str
    cible: str = ""             # l'identifiant complet, au moment de la dictee
    suffixe: str = ""           # de quoi le retrouver si le chemin a change
    fenetre: str = "wnd[0]"
    source: Source | None = None
    touche: int = 0
    table: str = ""             # ECRIRE_LIGNE_LIBRE : le tableau
    colonne_cible: str = ""     # ECRIRE_LIGNE_LIBRE : le nom de la colonne
    #: L'index de la colonne DANS l'identifiant SAP : `COLONNE[x,ligne]`.
    #: Il ne vaut pas toujours zero — la deuxieme colonne d'un tableau
    #: s'ecrit `[1,ligne]` — et le supposer tapait dans la mauvaise colonne.
    index_colonne: int = 0
    #: Une ligne VISIBLE precise ; `None` veut dire « la premiere libre ».
    ligne: int | None = None
    libelle: str = ""           # ce qu'un humain lit a l'ecran
    si_fenetre: str = ""        # titre de la fenetre surgissante exigee

    def __post_init__(self) -> None:
        if self.type not in GESTES:
            raise ValueError(f"geste {self.type!r}, attendu l'un de {list(GESTES)}")

    def resume(self) -> str:
        condition = f" [si « {self.si_fenetre} »]" if self.si_fenetre else ""
        if self.type == ECRIRE:
            return f"ecrire {self.source} dans {self.libelle or self.suffixe}{condition}"
        if self.type == ECRIRE_LIGNE_LIBRE:
            ou = ("la premiere ligne libre" if self.ligne is None
                  else f"la ligne {self.ligne}")
            return (f"ecrire {self.source} dans {ou} de "
                    f"{self.colonne_cible}{condition}")
        if self.type == TOUCHE:
            nom = {0: "Entree", 11: "Sauvegarder (F11)", 12: "Annuler (F12)"}.get(
                self.touche, f"touche {self.touche}")
            return f"{nom} sur {self.fenetre}{condition}"
        if self.type == MARQUER_KO:
            return f"marquer le point REFUSE{condition}"
        verbe = "presser" if self.type == PRESSER else "selectionner"
        return f"{verbe} {self.libelle or self.suffixe}{condition}"

    def en_json(self) -> dict:
        brut: dict = {"type": self.type, "fenetre": self.fenetre}
        for nom in ("cible", "suffixe", "libelle", "si_fenetre", "table",
                    "colonne_cible"):
            if getattr(self, nom):
                brut[nom] = getattr(self, nom)
        if self.type == TOUCHE:
            brut["touche"] = self.touche
        if self.type == ECRIRE_LIGNE_LIBRE:
            brut["index_colonne"] = self.index_colonne
            if self.ligne is not None:
                brut["ligne"] = self.ligne
        if self.source is not None:
            brut["source"] = self.source.en_json()
        return brut

    @staticmethod
    def de_json(brut: dict) -> "Geste":
        source = brut.get("source")
        return Geste(
            type=str(brut.get("type", "")),
            cible=str(brut.get("cible", "")),
            suffixe=str(brut.get("suffixe", "")),
            fenetre=str(brut.get("fenetre", "wnd[0]")),
            source=Source.de_json(source) if isinstance(source, dict) else None,
            touche=int(brut.get("touche", 0)),
            table=str(brut.get("table", "")),
            colonne_cible=str(brut.get("colonne_cible", "")),
            index_colonne=int(brut.get("index_colonne", 0)),
            ligne=(int(brut["ligne"]) if brut.get("ligne") is not None else None),
            libelle=str(brut.get("libelle", "")),
            si_fenetre=str(brut.get("si_fenetre", "")),
        )


class RecetteInvalide(Prevol):
    """La recette ne peut pas etre lue, ou ne dit pas ce qu'il faut."""


@dataclass
class Recette:
    """Ce que la passe dictee a appris, et que le rejeu execute."""

    entete: list[Geste] = field(default_factory=list)
    corps: list[Geste] = field(default_factory=list)
    cloture: list[Geste] = field(default_factory=list)
    creee_le: str = ""
    systeme: str = ""
    mandant: str = ""
    transaction: str = ""       # relevee a la dictee : la garde d'identite
    note: str = ""

    def moment(self, nom: str) -> list[Geste]:
        return {ENTETE: self.entete, CORPS: self.corps, CLOTURE: self.cloture}[nom]

    @property
    def colonnes(self) -> list[str]:
        """Les colonnes du fichier que cette recette exige."""
        vues: dict[str, None] = {}
        for geste in (*self.entete, *self.corps, *self.cloture):
            if geste.source is not None and geste.source.colonne:
                vues.setdefault(geste.source.colonne, None)
        return list(vues)

    def rendre(self) -> str:
        lignes = [f"recette du {self.creee_le or '?'} — transaction "
                  f"{self.transaction or '?'}, systeme {self.systeme or '?'}, "
                  f"mandant {self.mandant or '?'}"]
        if self.note:
            lignes.append(f"  note : {self.note}")
        for nom, titre in ((ENTETE, "UNE FOIS par classe"),
                           (CORPS, "pour CHAQUE point"),
                           (CLOTURE, "une fois a la FIN de la classe")):
            gestes = self.moment(nom)
            lignes.append(f"  {nom} — {titre} ({len(gestes)} geste(s))")
            for rang, geste in enumerate(gestes, start=1):
                lignes.append(f"    {rang:>2}. {geste.resume()}")
        return "\n".join(lignes)

    def en_json(self) -> dict:
        return {
            "version": 1, "creee_le": self.creee_le, "systeme": self.systeme,
            "mandant": self.mandant, "transaction": self.transaction,
            "note": self.note, "colonnes": self.colonnes,
            ENTETE: [g.en_json() for g in self.entete],
            CORPS: [g.en_json() for g in self.corps],
            CLOTURE: [g.en_json() for g in self.cloture],
        }

    def ecrire_dans(self, chemin: Path) -> Path:
        chemin = Path(chemin)
        chemin.write_text(json.dumps(self.en_json(), indent=2,
                                     ensure_ascii=False) + "\n",
                          encoding="utf-8")
        return chemin

    @staticmethod
    def lire(chemin: Path) -> "Recette":
        chemin = Path(chemin)
        if not chemin.exists():
            raise RecetteInvalide(f"recette introuvable : {chemin}")
        try:
            brut = json.loads(chemin.read_text(encoding="utf-8"))
        except json.JSONDecodeError as erreur:
            raise RecetteInvalide(f"{chemin} : {erreur}") from None
        if not isinstance(brut, dict):
            raise RecetteInvalide(f"{chemin} : attendu un objet JSON")
        try:
            recette = Recette(
                entete=[Geste.de_json(g) for g in brut.get(ENTETE, [])],
                corps=[Geste.de_json(g) for g in brut.get(CORPS, [])],
                cloture=[Geste.de_json(g) for g in brut.get(CLOTURE, [])],
                creee_le=str(brut.get("creee_le", "")),
                systeme=str(brut.get("systeme", "")),
                mandant=str(brut.get("mandant", "")),
                transaction=str(brut.get("transaction", "")),
                note=str(brut.get("note", "")),
            )
        except (ValueError, TypeError, AttributeError) as erreur:
            raise RecetteInvalide(f"{chemin} : {erreur}") from None
        if not recette.entete and not recette.corps:
            raise RecetteInvalide(f"{chemin} : recette vide")
        return recette


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
V_KO = "refus_dicte"                # un geste `ko` a marque la fenetre
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
    """Un ecran, en texte. Lecture seule, aucun geste.

    **Les tableaux y sont replies en grilles.** Un tableau de trois cents
    lignes sur cinq colonnes expose mille cinq cents champs : les lister un
    par un noyait le releve, au point qu'on n'y retrouvait plus les champs de
    saisie ni les boutons. Les colonnes sont nommees une fois, les lignes
    sont un apercu.
    """
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

    inventaire = inventorier(ecran)
    dans_un_tableau = {champ.id
                       for tableau in inventaire.tableaux
                       for cellules in tableau.lignes.values()
                       for champ in cellules.values()}
    hors_tableau = [c for c in ecran.champs if c.id not in dans_un_tableau]
    lignes.append(f"  champs de {ecran.fenetre} ({len(hors_tableau)} hors "
                  f"tableau, {len(ecran.champs)} en tout) : "
                  f"id | type | nom | « texte » | infobulle | modifiable")
    for champ in hors_tableau:
        soustype = f"/{champ.soustype}" if champ.soustype else ""
        modifiable = {True: "oui", False: "non"}.get(champ.modifiable, "?")
        lignes.append(f"    {champ.id} | {champ.type}{soustype} | {champ.nom} | "
                      f"« {champ.texte} » | {champ.infobulle} | {modifiable}")
    for rang, tableau in enumerate(inventaire.tableaux, start=1):
        lignes.append("")
        lignes.append(f"  {tableau.id}")
        lignes.extend(rendre_tableau(tableau, rang))
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
        self._depart = 0
        #: (tableau, cellule) de la derniere ligne libre ecrite, ou None.
        self._derniere_cellule: tuple[str, str] | None = None
        #: Les textes de la fenetre qu'un geste `ko` a marquee, ou "".
        self._ko = ""
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

    # -- resoudre la cible d'un geste ---------------------------------------------

    def _resoudre(self, geste: "Geste") -> str:
        """L'identifiant a viser MAINTENANT, pour ce geste.

        L'identifiant complet d'abord, tel que SAP l'a rendu a la dictee ; son
        SUFFIXE ensuite. Le numero de sous-ecran change avec le type d'objet
        affiche : un chemin fige cesse de resoudre, et sans ce repli le rejeu
        echouerait sur un ecran pourtant correct.
        """
        ecran = self.d.fields(geste.fenetre)
        if geste.cible and any(c.id == geste.cible for c in ecran.champs):
            return geste.cible
        if geste.suffixe:
            candidats = [c.id for c in ecran.par_suffixe(geste.suffixe)]
            if len(candidats) == 1:
                self.rapport.ligne(f"  cible retrouvee par son suffixe : "
                                   f"{candidats[0]}")
                return candidats[0]
            if len(candidats) > 1:
                raise Arret(f"{geste.resume()} : {len(candidats)} champs "
                            f"finissent par {geste.suffixe!r} dans "
                            f"{geste.fenetre} {candidats} ; la recette ne dit "
                            f"pas lequel")
        self.rapport.relever(geste.fenetre, f"cible introuvable : {geste.resume()}")
        raise Arret(f"{geste.resume()} : ni {geste.cible!r} ni aucun champ "
                    f"finissant par {geste.suffixe!r} dans {geste.fenetre} ; "
                    f"l'ecran n'est pas celui de la dictee, voir le rapport")

    # -- le tableau : index VISIBLE, defilement explicite ------------------------

    @staticmethod
    def _cellule(table: str, colonne: str, rang: int, index: int = 0) -> str:
        return f"{table}/{colonne}[{index},{rang}]"

    def _page(self, table: str, colonne: str, position: int,
              visibles: int, index: int = 0) -> list[str]:
        """Les textes des cellules visibles, apres defilement.

        Par `read`, cellule par cellule, et non par `fields`, qui traverse
        TOUT l'ecran a chaque page : sur une classe de trois cents points,
        c'est la difference entre quelques secondes et une heure par passe.
        """
        self.d.table_scroll(table, position)
        page: list[str] = []
        for rang in range(visibles):
            try:
                page.append(self.d.read(
                    self._cellule(table, colonne, rang, index)))
            except ObjetIntrouvable:
                break
        return page

    def _ligne_vide_depuis(self, table: str, colonne: str, depart: int,
                           visibles: int, index: int = 0) -> int | None:
        """Rang VISIBLE d'une cellule vide, le defilement laisse dessus ; None
        si rien depuis `depart`.

        S'arrete quand le defilement ne progresse plus : aucun compteur de SAP
        n'est fiable — `RowCount` compte les lignes vides de saisie, et la
        barre de defilement aussi.
        """
        position, precedente = depart, None
        while position < self.PLAFOND_LIGNES:
            page = self._page(table, colonne, position, visibles, index)
            if not page:
                raise Arret(f"tableau {table} : aucune cellule lisible a la "
                            f"position {position}")
            for rang, valeur in enumerate(page):
                if not valeur.strip():
                    self._depart = position
                    return rang
            if page == precedente:
                return None
            precedente = page
            position += len(page)
        raise Arret(f"tableau {table} : aucune ligne vide dans les "
                    f"{self.PLAFOND_LIGNES} premieres lignes")

    def _premiere_ligne_vide(self, table: str, colonne: str,
                             index: int = 0) -> int:
        """Le balayage part de la page ou la derniere ligne vide a ete trouvee.

        Le tableau ne fait que grandir sous nos ecritures, et les lignes
        libres sont derriere les lignes prises. Ce n'est qu'un point de
        depart — la cellule est RELUE vide juste avant d'y ecrire — et s'il ne
        mene a rien, on repart de zero une fois.
        """
        visibles = self.d.table_visible_rows(table)
        if visibles <= 0:
            raise Arret(f"tableau {table} : aucune ligne visible")
        rang = self._ligne_vide_depuis(table, colonne, self._depart, visibles,
                                       index)
        if rang is None and self._depart:
            self._depart = 0
            rang = self._ligne_vide_depuis(table, colonne, 0, visibles, index)
        if rang is None:
            raise Arret(f"tableau {table} : aucune ligne vide, le defilement "
                        f"ne progresse plus")
        return rang

    # -- les fenetres surgissantes ------------------------------------------------

    def _appliquer_regle(self, fenetre: str, ecran: Ecran, contexte: str) -> str:
        """Ce qu'on fait d'une fenetre que PERSONNE n'a dictee.

        **Il n'y a pas de regle ici, et c'est le point.** Ce qu'il faut faire
        d'une fenetre surgissante se dicte — un geste conditionne a son titre
        la ferme, un `ko` dit qu'elle signe un refus. Une fenetre qui arrive
        jusqu'ici n'a ete prevue par personne : la supposer benigne, c'est
        presser un bouton par defaut sur une boite qu'on n'a pas lue.
        """
        textes = " | ".join(textes_de(ecran))
        if self.executer:
            suite = ("la sauvegarde a ete PRESSEE, son etat est a verifier "
                     "dans SAP" if self._sauvegarde_en_cours
                     else "les saisies en attente ne sont pas sauvegardees")
            raise Arret(f"{contexte} : fenetre inconnue « {ecran.titre} » "
                        f"({textes[:300]}) ; voir le rapport ; {suite}. "
                        f"Redicter la passe en disant quoi en faire")
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

    def _vider(self, table: str, cellule: str, point: str) -> str:
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
        self.d.table_scroll(table, self._depart)
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
        self._ko = ""           # ce qui suit doit parler de l'EFFACEMENT
        self._touche(0)
        verdicts = self._traiter_popups(f"point {point} : apres effacement")
        statut = self.d.status()
        if statut.type in ("E", "A") or self._ko:
            raise Arret(f"point {point} : la ligne refusee ne se laisse pas "
                        f"vider ({statut_texte(statut)} ; fenetres {verdicts})")
        return "ligne videe" + (f" ; fenetres {verdicts}" if verdicts else "")

    # -- jouer les gestes d'une recette ------------------------------------------

    def _fenetre_ouverte(self, titre: str) -> str:
        """Le nom de la fenetre surgissante dont le titre correspond, ou "".

        La correspondance est laxiste — l'un contient l'autre, casse et
        espaces ignores — parce qu'un titre SAP porte souvent la classe ou
        l'objet courant, qui change d'une passe a l'autre.
        """
        cherche = " ".join(titre.split()).casefold()
        if not cherche:
            return ""
        for popup in self._popups():
            vu = " ".join(popup.titre.split()).casefold()
            if vu and (vu in cherche or cherche in vu):
                return popup.nom or popup.id
        return ""

    def _jouer(self, geste: Geste, ligne: dict[str, str]) -> None:
        """Fait un geste. La condition de fenetre a deja ete verifiee."""
        if geste.si_fenetre:
            # Une fenetre que la RECETTE gere ne passe pas par
            # `_traiter_popups` : sans ce releve, elle serait la seule a
            # traverser une passe sans laisser de trace dans le rapport.
            self.rapport.relever(self._fenetre_ouverte(geste.si_fenetre),
                                 f"geste dicte : {geste.resume()}")
        valeur = geste.source.valeur(ligne) if geste.source is not None else ""
        if geste.type == MARQUER_KO:
            self._ko = " | ".join(textes_de(self.d.fields(geste.fenetre)))
            self.rapport.ligne(f"  refus dicte : {self._ko[:200]}")
        elif geste.type == TOUCHE:
            self._touche(geste.touche, geste.fenetre)
        elif geste.type == ECRIRE_LIGNE_LIBRE:
            if geste.ligne is None:
                rang = self._premiere_ligne_vide(geste.table,
                                                 geste.colonne_cible,
                                                 geste.index_colonne)
            else:
                rang = geste.ligne
            cellule = self._cellule(geste.table, geste.colonne_cible, rang,
                                    geste.index_colonne)
            self._derniere_cellule = (geste.table, cellule)
            self._ecrire(cellule, valeur)
        elif geste.type == ECRIRE:
            self._ecrire(self._resoudre(geste), valeur)
        elif geste.type == PRESSER:
            self._presser(self._resoudre(geste))
        else:                                       # SELECTIONNER
            self.d.select(self._resoudre(geste))

    def _jouer_moment(self, gestes: list[Geste], ligne: dict[str, str],
                      contexte: str) -> list[str]:
        """Joue une suite de gestes, en traitant ce qui surgit entre deux.

        **C'est la fenetre presente qui decide, pas le rang du geste.** Quand
        une fenetre surgissante est ouverte, seul un geste qui la VISE peut
        agir, ou qu'il soit dans la liste ; les autres attendent. Sans cela,
        deux fenetres qui ne surgissent pas toujours dans le meme ordre —
        « deja affecte » pour un point, « valorisation » pour le suivant —
        auraient exige d'etre dictees dans l'ordre exact de chaque cas, ce
        qui est impossible a dicter.

        **Les regles ne passent jamais devant la recette.** Ce n'est qu'une
        fois qu'aucun geste ne vise la fenetre ouverte qu'elle est traitee
        comme inconnue : arret, ou F12 a blanc.
        """
        verdicts: list[str] = []
        restants = list(gestes)
        plafond = len(gestes) + 2 * self.PLAFOND_POPUPS + 2
        for _ in range(plafond):
            if self._popups():
                vise = next((g for g in restants if g.si_fenetre
                             and self._fenetre_ouverte(g.si_fenetre)), None)
                if vise is not None:
                    restants.remove(vise)
                    self._jouer(vise, ligne)
                    continue
                verdicts += self._traiter_popups(contexte)
                continue
            if not restants:
                return verdicts
            geste = restants.pop(0)
            if geste.si_fenetre:
                self.rapport.ligne(f"  saute (« {geste.si_fenetre} » absente) : "
                                   f"{geste.resume()}")
                continue
            self._jouer(geste, ligne)
        raise Arret(f"{contexte} : {plafond} tours sans venir a bout des "
                    f"gestes restants {[g.resume() for g in restants]} ; "
                    f"voir le rapport")

    def _garde_transaction(self, recette: Recette, quand: str) -> None:
        """La garde d'identite, apprise plutot que codee."""
        if not recette.transaction:
            return
        courante = self.d.screen().transaction
        if courante != recette.transaction:
            raise Arret(f"{quand} : transaction {courante!r}, alors que la "
                        f"recette a ete dictee sur {recette.transaction!r}")

    # -- un point -------------------------------------------------------------------

    def point(self, classe: str, point: str, recette: Recette) -> str:
        """Joue le corps de la recette pour un point. Rend son etat."""
        ligne = {COLONNE_POINT: point, COLONNE_CLASSE: classe}
        self._derniere_cellule = None
        self._ko = ""
        verdicts = self._jouer_moment(recette.corps, ligne, f"point {point}")
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

        if self._ko:
            etat = DEJA_AFFECTE
            detail = f"refus dicte « {self._ko[:200]} » ; " + self._retirer(point)
        elif statut.type in ("E", "A"):
            etat = REFUSE
            detail = f"{statut_texte(statut)} ; " + self._retirer(point)
        elif V_INCONNUE in verdicts:
            etat = POPUP_INCONNUE
            detail = ("fenetre inconnue annulee (a blanc), voir le rapport ; "
                      + self._retirer(point))
        else:
            etat = SAISI
            detail = (f"avertissement accepte par une seconde Entree : "
                      f"{statut_texte(avertissement)}"
                      if avertissement is not None else "")
        self.journal.noter(classe, point, etat, detail)
        return etat

    def _retirer(self, point: str) -> str:
        """Retire du tableau la ligne refusee, si la recette en a ecrit une."""
        if self._derniere_cellule is None:
            return "aucune ligne a retirer : la recette n'ecrit dans aucun tableau"
        table, cellule = self._derniere_cellule
        return self._vider(table, cellule, point)

    # -- la cloture : c'est la que la sauvegarde a ete dictee ------------------------

    def cloturer(self, classe: str, recette: Recette) -> None:
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
        if not recette.cloture:
            for point in saisis:
                self.journal.noter(classe, point, NON_SAUVEGARDE,
                                   "la recette ne porte aucune cloture : rien "
                                   "n'a ete sauvegarde")
            self._en_attente = []
            raise Arret(f"classe {classe} : la recette ne dit pas comment "
                        f"sauvegarder. Redicter la passe, et donner le geste "
                        f"de sauvegarde apres la commande `cloture`")

        self._garde_transaction(recette, f"classe {classe} : avant de sauvegarder")
        self._sauvegarde_en_cours = True
        ligne = {COLONNE_CLASSE: classe, COLONNE_POINT: ""}
        verdicts = self._jouer_moment(recette.cloture, ligne,
                                      f"classe {classe} : cloture")
        statut = self.d.status()
        avertissement = None
        if statut.type == "W":
            avertissement = statut
            self.rapport.ligne(f"  cloture : avertissement "
                               f"{statut_texte(statut)}, seconde Entree")
            self._touche(0)
            verdicts += self._traiter_popups(
                f"classe {classe} : apres la cloture, seconde Entree")
            statut = self.d.status()
        self.rapport.ligne(f"  cloture : statut {statut_texte(statut)} ; "
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
            detail = (f"statut non concluant apres la cloture "
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

    def passe(self, recette: Recette, classe: str, points: list[str]) -> Counter:
        """Une classe : l'entete une fois, le corps par point, puis la cloture."""
        mode = ("EXECUTION (sauvegarde)" if self.executer
                else "A BLANC (aucune sauvegarde)")
        self.journal.noter(classe, "", PASSE,
                           f"debut : {len(points)} point(s), {mode}")
        self.rapport.ligne(f"\n##### classe {classe} : {len(points)} point(s), "
                           f"{mode}")
        compte: Counter = Counter()
        self._depart = 0
        self._en_attente = []
        self._sauvegarde_en_cours = False
        try:
            self._jouer_moment(recette.entete,
                               {COLONNE_CLASSE: classe, COLONNE_POINT: ""},
                               f"classe {classe} : entete")
            self._garde_transaction(recette, f"classe {classe} : apres l'entete")
            for point in points:
                etat = self.point(classe, point, recette)
                compte[etat] += 1
                if etat == SAISI:
                    self._en_attente.append(point)
                if self.par_lot and len(self._en_attente) >= self.par_lot:
                    self.cloturer(classe, recette)
            self.cloturer(classe, recette)
        except KeyboardInterrupt:
            self._journaliser_arret(classe, "interrompu au clavier (Ctrl-C)")
            raise
        except Exception as erreur:
            self._journaliser_arret(classe, f"{type(erreur).__name__} : {erreur}")
            raise
        self.journal.noter(classe, "", PASSE, f"fin : {resume(compte)}")
        return compte



# =====================================================================
# Le pilotage dicte : la premiere passe, geste par geste
# =====================================================================

#: Une cellule de tableau : `.../tblNOM/COLONNE[colonne,ligne]`.
_CELLULE = re.compile(r"^(?P<table>.*/tbl[^/]+)/(?P<colonne>[^/\[]+)"
                      r"\[(?P<x>\d+),(?P<y>\d+)\]$")

#: Comment on designe une cellule au clavier : `T1.C2` vise la colonne 2 du
#: tableau 1, dans la premiere ligne LIBRE ; `T1.L5.C2` vise la ligne 5.
#: `T1` seul vise la colonne 1 — commode quand le tableau n'en a qu'une.
_DESIGNATION = re.compile(
    r"^T(?P<tableau>\d+)(?:\.?L(?P<ligne>\d+))?(?:\.?C(?P<colonne>\d+))?$",
    re.IGNORECASE)

#: Ce qu'on peut selectionner : une radio, une case, un onglet.
SELECTIONNABLES = frozenset({"GuiRadioButton", "GuiCheckBox", "GuiTab"})

#: Ce qu'on peut dicter une valeur dedans. Le CHAMP DE COMMANDE en fait
#: partie : c'est par lui qu'on ouvre la transaction, et c'est donc le tout
#: premier geste de presque toute recette.
SAISISSABLES_DICTEES = SAISISSABLES | {"GuiOkCodeField"}

AIDE = """  COMMANDES

    1 = "015"      ecrire la constante « 015 » dans le champ 1
    1 = classe     ecrire la colonne `classe` du fichier dans le champ 1
    T1.C2 = point  ecrire la colonne `point` du fichier dans la colonne C2
                   du tableau T1, a sa premiere LIGNE LIBRE — c'est ce
                   qu'il faut pour alimenter une liste
    T1.L5.C2 = ... la meme chose, mais dans la ligne visible L5
    b2             presser le bouton 2
    r1             selectionner le choix 1 (radio, case, onglet)
    e              Entree
    t11            touche de fonction 11 (11 = sauvegarder, 12 = annuler)
    ko             dans une fenetre surgissante : « celle-ci veut dire que
                   le point est REFUSE ». Au rejeu, le point sortira KO et
                   sa ligne sera retiree. A dire avant le geste qui ferme

    v              revoir l'ecran     v wnd[1]  voir une autre fenetre
    liste          revoir la recette dictee jusqu'ici
    annuler        retirer le dernier geste de la recette (ne defait RIEN
                   dans SAP : c'est la recette qu'on corrige, pas l'ecran)
    note ...       ajouter une note a la recette

    boucle         ce qui suit se repete POUR CHAQUE POINT
    cloture        ce qui suit se fait UNE FOIS, a la fin de la classe
    fin            enregistrer la recette et sortir
    abandon        sortir sans rien enregistrer
    ?              cette aide"""


@dataclass
class Tableau:
    """Un tableau vu comme une GRILLE : ses colonnes, puis ses lignes.

    **C'est le point qui rendait un releve illisible.** Un tableau de trois
    cents lignes sur cinq colonnes expose mille cinq cents champs, et les
    lister un par un noyait l'ecran — on n'y retrouvait ni les vrais champs
    de saisie, ni les boutons. Ici les colonnes sont nommees UNE fois, et les
    lignes ne sont qu'un apercu : on designe ensuite une cellule par sa
    colonne et sa ligne, pas par son identifiant.
    """

    id: str
    #: (nom de la colonne, index dans l'identifiant `NOM[index,ligne]`).
    colonnes: list[tuple[str, int]] = field(default_factory=list)
    #: ligne visible -> {nom de colonne: champ}
    lignes: dict[int, dict[str, Champ]] = field(default_factory=dict)

    @property
    def nom(self) -> str:
        return self.id.rsplit("/", 1)[-1]

    def colonne(self, rang: int) -> tuple[str, int] | None:
        """La colonne numero `rang` (1 pour la premiere), ou None."""
        if 1 <= rang <= len(self.colonnes):
            return self.colonnes[rang - 1]
        return None

    def libres(self, nom: str) -> int:
        """Combien de lignes VISIBLES ont cette colonne vide."""
        return sum(1 for cellules in self.lignes.values()
                   if not (cellules.get(nom).texte.strip()
                           if cellules.get(nom) else ""))


@dataclass
class Inventaire:
    """Ce qu'un ecran offre, numerote pour etre designe au clavier."""

    champs: list[Champ] = field(default_factory=list)
    tableaux: list[Tableau] = field(default_factory=list)
    boutons: list[Champ] = field(default_factory=list)
    choix: list[Champ] = field(default_factory=list)


def inventorier(ecran: Ecran) -> Inventaire:
    """Trie les champs d'un ecran en quatre familles designables.

    Les cellules de tableau sont repliees en grilles : on ne dicte pas un
    identifiant de cellule, on dicte « tableau 1, colonne 2, premiere ligne
    libre ». Un identifiant fige traiterait la mauvaise ligne des que la
    liste change, sans rien lever.
    """
    inventaire = Inventaire()
    tableaux: dict[str, Tableau] = {}
    for champ in ecran.champs:
        trouve = _CELLULE.match(champ.id)
        if trouve is not None and champ.type in SAISISSABLES_DICTEES:
            tableau = tableaux.setdefault(trouve.group("table"),
                                          Tableau(id=trouve.group("table")))
            nom = trouve.group("colonne")
            index, ligne = int(trouve.group("x")), int(trouve.group("y"))
            if (nom, index) not in tableau.colonnes:
                tableau.colonnes.append((nom, index))
            tableau.lignes.setdefault(ligne, {})[nom] = champ
        elif champ.type in SAISISSABLES_DICTEES:
            inventaire.champs.append(champ)
        elif champ.type == "GuiButton":
            inventaire.boutons.append(champ)
        elif champ.type in SELECTIONNABLES:
            inventaire.choix.append(champ)
    for tableau in tableaux.values():
        tableau.colonnes.sort(key=lambda paire: paire[1])
    inventaire.tableaux = list(tableaux.values())
    return inventaire


#: Au-dela, l'apercu d'un tableau est tronque : il sert a DESIGNER une
#: cellule, pas a lire les donnees. Le tableau entier se lit dans SAP.
APERCU_LIGNES = 6
APERCU_COLONNES = 6


def rendre_tableau(tableau: Tableau, numero: int) -> list[str]:
    """Un tableau en grille : ses colonnes nommees une fois, puis un apercu."""
    colonnes = tableau.colonnes[:APERCU_COLONNES]
    largeur = 22
    lignes = [f" TABLEAU T{numero}  {tableau.nom}   "
              f"{len(tableau.lignes)} ligne(s) visible(s)"
              + (f", {len(tableau.colonnes)} colonnes dont "
                 f"{len(colonnes)} montrees"
                 if len(tableau.colonnes) > len(colonnes)
                 else f", {len(tableau.colonnes)} colonne(s)")]
    entete = "       " + "".join(
        f"C{rang}:{nom}"[:largeur].ljust(largeur + 1)
        for rang, (nom, _) in enumerate(colonnes, start=1))
    lignes.append(entete.rstrip())
    for ligne in sorted(tableau.lignes)[:APERCU_LIGNES]:
        cellules = tableau.lignes[ligne]
        rendu = f"   L{ligne:<3} "
        for nom, _ in colonnes:
            champ = cellules.get(nom)
            texte = (champ.texte.strip() if champ else "")
            rendu += (texte or "·")[:largeur].ljust(largeur + 1)
        lignes.append(rendu.rstrip())
    if len(tableau.lignes) > APERCU_LIGNES:
        lignes.append(f"   ... {len(tableau.lignes) - APERCU_LIGNES} "
                      f"ligne(s) visible(s) de plus")
    return lignes


def _court(identifiant: str) -> str:
    """L'identifiant sans son chemin de session, pour tenir sur une ligne."""
    coupe = identifiant.find("wnd[")
    return identifiant[coupe:] if coupe >= 0 else identifiant


def _fin(identifiant: str) -> str:
    """Le dernier segment : le nom du champ, ce qu'un humain reconnait."""
    return identifiant.rsplit("/", 1)[-1]


def rendre_inventaire(driver: Any, ecran: Ecran,
                      inventaire: Inventaire) -> list[str]:
    """L'ecran tel que le pilotage le montre : numerote, et rien d'autre."""
    identite = ecran.identite
    lignes = [
        "-" * 70,
        f" {ecran.fenetre} « {ecran.titre} »",
        f" {identite.transaction or '-'} / {identite.programme or '-'} / "
        f"{identite.dynpro or '-'}     statut : {statut_texte(driver.status())}",
    ]
    if inventaire.champs:
        lignes.append("")
        lignes.append(" CHAMPS")
        for rang, champ in enumerate(inventaire.champs, start=1):
            fige = "" if champ.modifiable is not False else "   (fige)"
            lignes.append(f"   {rang:>3}  {_fin(champ.id):<28} "
                          f"« {champ.texte[:24]} »{fige}")
    for rang, tableau in enumerate(inventaire.tableaux, start=1):
        lignes.append("")
        lignes.extend(rendre_tableau(tableau, rang))
    if inventaire.choix:
        lignes.append("")
        lignes.append(" CHOIX")
        for rang, champ in enumerate(inventaire.choix, start=1):
            lignes.append(f"    r{rang:<2}  {_fin(champ.id):<28} "
                          f"« {champ.texte[:24]} »")
    if inventaire.boutons:
        lignes.append("")
        lignes.append(" BOUTONS")
        for rang, champ in enumerate(inventaire.boutons, start=1):
            nom = champ.texte.strip() or champ.infobulle.strip() or "(icone)"
            lignes.append(f"    b{rang:<2}  {_court(champ.id).split('/', 1)[-1]:<28} "
                          f"« {nom[:24]} »")
    lignes.append("-" * 70)
    return lignes


class Pilote:
    """La premiere passe, dictee geste par geste.

    Le programme montre ce qu'il voit ; vous dites quoi faire ; il le fait
    dans SAP et l'ECRIT dans une recette. A la fin, la recette rejoue la
    meme chose pour tous les points, sans vous.

    **Ce mode agit vraiment dans SAP, y compris la sauvegarde** — c'est le
    but : rien ne serait appris d'une passe qui n'aboutit pas. La seule
    barriere est que le geste de sauvegarde demande un mot en toutes lettres
    au moment ou il est dicte.
    """

    def __init__(self, driver: Any, rapport: Rapport, *,
                 colonnes: list[str],
                 lire: Callable[[str], str] = input,
                 ecrire: Callable[[str], None] = print,
                 cibles: Cibles = Cibles()):
        self.d = driver
        self.rapport = rapport
        self.colonnes = colonnes
        self.lire = lire
        self.ecrire = ecrire
        self.c = cibles
        self.recette = Recette()
        self.moment = ENTETE
        self._fenetre = "wnd[0]"
        self._inventaire = Inventaire()
        self._ecran: Ecran | None = None

    # -- ce que le pilote voit ------------------------------------------------

    def _fenetre_active(self) -> str:
        """La fenetre la plus haute : c'est celle qui a le focus dans SAP."""
        ouvertes = self.d.windows()
        for fenetre in reversed(ouvertes):
            nom = fenetre.nom or fenetre.id
            if nom:
                return nom
        return "wnd[0]"

    def _titre_surgissante(self) -> str:
        """Le titre de la fenetre surgissante active, ou "" s'il n'y en a pas.

        C'est ce qui rend un geste CONDITIONNEL : dicte dans une fenetre qui
        ne surgit pas toujours, il ne sera rejoue que quand elle est la.
        """
        for fenetre in self.d.windows():
            if fenetre.surgissante and (fenetre.nom or fenetre.id) == self._fenetre:
                return fenetre.titre
        return ""

    def montrer(self, fenetre: str = "") -> None:
        self._fenetre = fenetre or self._fenetre_active()
        self._ecran = self.d.fields(self._fenetre)
        self._inventaire = inventorier(self._ecran)
        for ligne in rendre_inventaire(self.d, self._ecran, self._inventaire):
            self.ecrire(ligne)
        dictes = len(self.recette.moment(self.moment))
        surgissante = self._titre_surgissante()
        condition = (f"   [les gestes seront conditionnes a « {surgissante} »]"
                     if surgissante else "")
        self.ecrire(f" moment : {self.moment}  ({dictes} geste(s) dicte(s))"
                    f"{condition}")

    # -- enregistrer et faire --------------------------------------------------

    def _noter(self, geste: Geste) -> None:
        self.recette.moment(self.moment).append(geste)
        self.rapport.ligne(f"  [{self.moment}] {geste.resume()}")
        self.ecrire(f"   -> {geste.resume()}")

    def _est_sauvegarde(self, geste: Geste) -> bool:
        if geste.type == TOUCHE:
            return geste.touche == self.c.touche_sauvegarde
        return (geste.type == PRESSER
                and geste.suffixe.endswith(self.c.bouton_sauvegarde))

    def _autorise(self, geste: Geste) -> bool:
        """Un geste de sauvegarde se confirme en toutes lettres, a l'instant."""
        if not self._est_sauvegarde(geste):
            return True
        self.ecrire("   ce geste SAUVEGARDE dans SAP, pour de vrai.")
        try:
            reponse = self.lire("   taper « sauvegarder » pour le faire : ")
        except EOFError:
            return False
        if reponse.strip().casefold() != "sauvegarder":
            self.ecrire("   annule : le geste n'est ni fait ni enregistre.")
            return False
        return True

    def _faire(self, geste: Geste) -> None:
        """Fait le geste dans SAP, puis l'enregistre. L'ordre compte : un
        geste qui echoue n'entre pas dans la recette."""
        if not self._autorise(geste):
            return
        valeur = geste.source.valeur(self._exemple()) if geste.source else ""
        if geste.type == MARQUER_KO:
            pass                # il ne touche a rien : il CLASSE, au rejeu
        elif geste.type == TOUCHE:
            self.d.vkey(geste.touche, geste.fenetre)
        elif geste.type == ECRIRE_LIGNE_LIBRE:
            rang = (geste.ligne if geste.ligne is not None
                    else self._ligne_libre(geste.table, geste.colonne_cible,
                                           geste.index_colonne))
            self._ecrire_et_relire(
                f"{geste.table}/{geste.colonne_cible}"
                f"[{geste.index_colonne},{rang}]", valeur)
        elif geste.type == ECRIRE:
            self._ecrire_et_relire(geste.cible, valeur)
        elif geste.type == PRESSER:
            self.d.press(geste.cible)
        else:
            self.d.select(geste.cible)
        self._noter(geste)
        self.montrer()

    def _exemple(self) -> dict[str, str]:
        """Les valeurs tapees PENDANT la dictee : la premiere ligne du fichier.

        Dicter avec de vraies valeurs et non des jetons est ce qui fait que la
        passe aboutit : SAP valide ce qu'on lui donne, et un jeton serait
        refuse au premier controle.
        """
        return dict(self._valeurs)

    def _ligne_libre(self, table: str, colonne: str, index: int = 0) -> int:
        """Le rang VISIBLE de la premiere cellule libre, defilement laisse dessus."""
        visibles = self.d.table_visible_rows(table)
        position = 0
        precedente = None
        while position < 5000:
            self.d.table_scroll(table, position)
            page = []
            for rang in range(visibles):
                try:
                    page.append(self.d.read(
                        f"{table}/{colonne}[{index},{rang}]"))
                except ObjetIntrouvable:
                    break
            if not page:
                raise Arret(f"tableau {table} : aucune cellule lisible")
            for rang, valeur in enumerate(page):
                if not valeur.strip():
                    return rang
            if page == precedente:
                raise Arret(f"tableau {table} : aucune ligne libre")
            precedente = page
            position += len(page)
        raise Arret(f"tableau {table} : aucune ligne libre")

    def _ecrire_et_relire(self, cible: str, valeur: str) -> None:
        self.d.write(cible, valeur)
        relu = self.d.read(cible)
        if not meme_valeur(valeur, relu):
            raise Arret(f"ecrit {valeur!r} dans {_court(cible)}, relu {relu!r} : "
                        f"la saisie n'a pas pris")

    # -- lire un ordre -----------------------------------------------------------

    def _source(self, mot: str) -> Source | None:
        mot = mot.strip()
        if len(mot) >= 2 and mot[0] == mot[-1] and mot[0] in "\"'":
            return Source(constante=mot[1:-1])
        if mot in self.colonnes:
            return Source(colonne=mot)
        self.ecrire(f"   {mot!r} n'est ni une constante entre guillemets ni "
                    f"une colonne du fichier ({', '.join(self.colonnes)}).")
        return None

    def _champ(self, numero: str) -> Champ | None:
        if not numero.isdigit() or not 1 <= int(numero) <= len(self._inventaire.champs):
            self.ecrire(f"   il n'y a pas de champ {numero}.")
            return None
        return self._inventaire.champs[int(numero) - 1]

    def _cellule_designee(self, gauche: str):
        """(tableau, nom de colonne, index, ligne) pour un `T1.L5.C2`, ou None."""
        trouve = _DESIGNATION.match(gauche)
        if trouve is None:
            return None
        rang = int(trouve.group("tableau"))
        if not 1 <= rang <= len(self._inventaire.tableaux):
            self.ecrire(f"   il n'y a pas de tableau T{rang}.")
            return None
        tableau = self._inventaire.tableaux[rang - 1]
        numero = int(trouve.group("colonne") or 1)
        colonne = tableau.colonne(numero)
        if colonne is None:
            self.ecrire(f"   le tableau T{rang} n'a pas de colonne C{numero} "
                        f"(il en a {len(tableau.colonnes)}).")
            return None
        ligne = trouve.group("ligne")
        if ligne is not None and int(ligne) not in tableau.lignes:
            self.ecrire(f"   la ligne L{ligne} n'est pas visible dans T{rang} "
                        f"(visibles : {sorted(tableau.lignes)}).")
            return None
        nom, index = colonne
        return tableau, nom, index, (int(ligne) if ligne is not None else None)

    def _affectation(self, ordre: str) -> None:
        gauche, _, droite = ordre.partition("=")
        gauche, droite = gauche.strip(), droite.strip()
        source = self._source(droite)
        if source is None:
            return
        condition = self._titre_surgissante()
        if gauche.upper().startswith("T"):
            designee = self._cellule_designee(gauche)
            if designee is None:
                return
            tableau, nom, index, ligne = designee
            self._faire(Geste(type=ECRIRE_LIGNE_LIBRE, table=tableau.id,
                              colonne_cible=nom, index_colonne=index,
                              ligne=ligne, fenetre=self._fenetre,
                              source=source, si_fenetre=condition,
                              libelle=f"{tableau.nom}/{nom}"))
            return
        champ = self._champ(gauche)
        if champ is None:
            return
        self._faire(Geste(type=ECRIRE, cible=champ.id, suffixe=_fin(champ.id),
                          fenetre=self._fenetre, source=source,
                          si_fenetre=condition, libelle=_fin(champ.id)))

    def _par_numero(self, ordre: str) -> None:
        """b<n>, r<n>, t<n> — un bouton, un choix, une touche."""
        tete, numero = ordre[0].lower(), ordre[1:].strip()
        condition = self._titre_surgissante()
        if tete == "t":
            if not numero.lstrip("-").isdigit():
                self.ecrire(f"   {ordre!r} : t doit etre suivi d'un numero de touche.")
                return
            self._faire(Geste(type=TOUCHE, touche=int(numero),
                              fenetre=self._fenetre, si_fenetre=condition))
            return
        famille = self._inventaire.boutons if tete == "b" else self._inventaire.choix
        if not numero.isdigit() or not 1 <= int(numero) <= len(famille):
            self.ecrire(f"   il n'y a pas de {ordre}.")
            return
        champ = famille[int(numero) - 1]
        nom = champ.texte.strip() or champ.infobulle.strip() or _fin(champ.id)
        self._faire(Geste(type=PRESSER if tete == "b" else SELECTIONNER,
                          cible=champ.id,
                          suffixe=_court(champ.id).split("/", 1)[-1],
                          fenetre=self._fenetre, si_fenetre=condition,
                          libelle=nom))

    def _marquer_ko(self) -> None:
        """« cette fenetre veut dire que le point est refuse ».

        Refuse hors d'une fenetre surgissante : un refus qui ne serait
        conditionne a rien marquerait TOUS les points, y compris ceux qui
        passent.
        """
        condition = self._titre_surgissante()
        if not condition:
            self.ecrire("   `ko` ne se dit que dans une fenetre surgissante : "
                        "c'est elle qui signe le refus.")
            return
        if self.moment != CORPS:
            self.ecrire("   `ko` ne vaut que dans « corps » : c'est un point "
                        "qui est refuse, pas une classe.")
            return
        self._faire(Geste(type=MARQUER_KO, fenetre=self._fenetre,
                          si_fenetre=condition))

    def _annuler(self) -> None:
        gestes = self.recette.moment(self.moment)
        if not gestes:
            self.ecrire("   aucun geste a retirer de ce moment.")
            return
        retire = gestes.pop()
        self.ecrire(f"   retire de la recette : {retire.resume()}")
        self.ecrire("   (SAP n'a PAS ete defait : c'est la recette qu'on corrige)")

    def _changer_de_moment(self, moment: str) -> None:
        self.moment = moment
        quoi = {ENTETE: "une fois par classe",
                CORPS: "pour CHAQUE point",
                CLOTURE: "une fois a la fin de la classe"}[moment]
        self.ecrire(f"   ce qui suit est enregistre dans « {moment} » — {quoi}.")

    # -- la boucle -----------------------------------------------------------------

    def _ouvrir(self, transaction: str) -> None:
        """Pose les deux premiers gestes de toute recette : `/nXXXX`, Entree.

        Les dicter serait deux lignes a taper a chaque fois, et surtout on
        pourrait les oublier : sans eux la recette ne dit pas sur quelle
        transaction elle travaille, et la garde d'identite n'a plus rien a
        comparer avant une sauvegarde.
        """
        code = transaction.strip().upper()
        champ = next((c for c in self._inventaire.champs
                      if c.id.endswith("okcd")), None)
        if champ is None:
            self.ecrire("   pas de champ de commande sur cet ecran : ouvrir "
                        f"{code} a la main, puis dicter la suite.")
            return
        self._faire(Geste(type=ECRIRE, cible=champ.id, suffixe="okcd",
                          fenetre=self._fenetre,
                          source=Source(constante=f"/n{code}"), libelle="okcd"))
        self._faire(Geste(type=TOUCHE, touche=0, fenetre="wnd[0]"))
        courante = self.d.screen().transaction
        if courante != code:
            self.ecrire(f"   ATTENTION : l'ecran annonce {courante or '-'}, pas "
                        f"{code}.")

    def piloter(self, valeurs: dict[str, str],
                transaction: str = "") -> Recette | None:
        """Dicte la passe. Rend la recette, ou None si on a abandonne.

        `valeurs` est la ligne du fichier avec laquelle on dicte : de vraies
        valeurs, pour que SAP accepte et que la passe aboutisse. `transaction`,
        si elle est donnee, est ouverte d'emblee — les deux gestes entrent
        dans la recette comme s'ils avaient ete dictes.
        """
        self._valeurs = dict(valeurs)
        identite = self.d.screen()
        self.recette.creee_le = maintenant()
        self.recette.systeme = identite.systeme
        self.recette.mandant = identite.mandant
        self.ecrire("")
        self.ecrire(f"  PILOTAGE — systeme {identite.systeme or '-'}, mandant "
                    f"{identite.mandant or '-'}")
        self.ecrire(f"  les valeurs tapees sont celles-ci : "
                    + ", ".join(f"{c} = {v}" for c, v in valeurs.items()))
        self.ecrire("  `?` pour l'aide, `fin` pour enregistrer.")
        self.montrer()
        if transaction:
            self._ouvrir(transaction)
        while True:
            try:
                ordre = self.lire("  > ").strip()
            except EOFError:
                self.ecrire("   entree fermee : on abandonne sans enregistrer.")
                return None
            if not ordre:
                continue
            bas = ordre.casefold()
            try:
                if bas in ("fin", "f"):
                    self.recette.transaction = self.d.screen().transaction
                    return self.recette
                if bas == "abandon":
                    return None
                if bas == "?":
                    self.ecrire(AIDE)
                elif bas in ("v", "voir"):
                    self.montrer()
                elif bas.startswith(("v ", "voir ")):
                    self.montrer(ordre.split(None, 1)[1].strip())
                elif bas == "liste":
                    self.ecrire(self.recette.rendre())
                elif bas == "annuler":
                    self._annuler()
                elif bas.startswith("note"):
                    self.recette.note = ordre[4:].strip()
                    self.ecrire(f"   note : {self.recette.note}")
                elif bas in ALIAS_DE_MOMENT:
                    self._changer_de_moment(ALIAS_DE_MOMENT[bas])
                elif bas == "ko":
                    self._marquer_ko()
                elif bas == "e":
                    self._faire(Geste(type=TOUCHE, touche=0,
                                      fenetre=self._fenetre,
                                      si_fenetre=self._titre_surgissante()))
                elif "=" in ordre:
                    self._affectation(ordre)
                elif ordre[0].lower() in "brt" and len(ordre) > 1:
                    self._par_numero(ordre)
                else:
                    self.ecrire("   ordre inconnu. `?` pour l'aide.")
            except ErreurCL24N as erreur:
                self.ecrire(f"   {type(erreur).__name__} : {erreur}")
                self.ecrire("   rien n'a ete enregistre pour cet ordre.")


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


def _sorties(sortie: Path, driver: Any) -> tuple[Journal, Rapport, str]:
    sortie.mkdir(parents=True, exist_ok=True)
    horodatage = re.sub(r"[^0-9TZ]", "", maintenant())
    journal = Journal(sortie / f"cl24n_{horodatage}_journal.csv")
    rapport = Rapport(sortie / f"cl24n_{horodatage}_rapport.txt", driver)
    return journal, rapport, horodatage


def dicter_sur(driver: Any, valeurs: dict[str, str], *, colonnes: list[str],
               sortie: Path, transaction: str = "",
               lire: Callable[[str], str] = input,
               ecrire: Callable[[str], None] = print) -> Path | None:
    """La premiere passe, dictee. Rend le chemin de la recette, ou None."""
    sortie.mkdir(parents=True, exist_ok=True)
    horodatage = re.sub(r"[^0-9TZ]", "", maintenant())
    rapport = Rapport(sortie / f"cl24n_{horodatage}_dictee.txt", driver)
    try:
        pilote = Pilote(driver, rapport, colonnes=colonnes, lire=lire,
                        ecrire=ecrire)
        recette = pilote.piloter(valeurs, transaction)
    finally:
        rapport.fermer()
    if recette is None:
        ecrire("  abandonne : aucune recette enregistree.")
        ecrire(f"  ce qui a ete vu reste dans {rapport.chemin}")
        return None
    chemin = recette.ecrire_dans(sortie / f"cl24n_{horodatage}_recette.json")
    ecrire("")
    ecrire(recette.rendre())
    ecrire("")
    ecrire(f"  recette  {chemin}")
    ecrire(f"  dictee   {rapport.chemin}")
    return chemin


def rejouer_sur(driver: Any, recette: Recette, retenues: dict[str, list[str]],
                *, executer: bool, sortie: Path, par_lot: int = 0,
                lire: Callable[[str], str] = input,
                ecrire: Callable[[str], None] = print) -> int:
    """Rejoue la recette pour chaque classe retenue. Rend le code de sortie."""
    journal, rapport, _ = _sorties(sortie, driver)

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
        f"  recette dictee le {recette.creee_le or '?'} sur "
        f"{recette.systeme or '?'}/{recette.mandant or '?'}, transaction "
        f"{recette.transaction or '?'}",
        *(f"  classe {classe} : {len(points)} point(s)"
          for classe, points in retenues.items()),
        f"  journal {journal.chemin}",
        f"  rapport {rapport.chemin}",
    ]
    for ligne in entete:
        ecrire(ligne)
        rapport.ligne(ligne)
    rapport.ligne(recette.rendre())

    if recette.systeme and recette.systeme != identite.systeme:
        ecrire(f"  ATTENTION : recette dictee sur {recette.systeme}, session "
               f"sur {identite.systeme}.")

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
            compte = automate.passe(recette, classe, points)
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
        ecrire("  Quitter la transaction a la main, sans sauvegarder.")
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


def _parametres(lire, ecrire, jeu_defaut: Path):
    """(chemin, par_classe) lus au clavier, ou None si ca n'aboutit pas."""
    chemin = Path(_demander(lire, ecrire, "fichier des points :", str(jeu_defaut)))
    try:
        par_classe = lire_points(chemin)
    except JeuInvalide as refus:
        ecrire(f"  REFUS : {refus}")
        return None
    total = sum(len(p) for p in par_classe.values())
    ecrire(f"  {chemin} : {total} point(s), {len(par_classe)} classe(s)")
    return chemin, par_classe


def _derniere_recette(sortie: Path) -> Path | None:
    recettes = sorted(sortie.glob("cl24n_*_recette.json")) if sortie.is_dir() else []
    return recettes[-1] if recettes else None


def _choisir_recette(lire, ecrire, sortie: Path) -> Recette | None:
    defaut = _derniere_recette(sortie)
    if defaut is None:
        ecrire("  aucune recette dans les sorties : dicter d'abord une passe "
               "(choix 3).")
        return None
    chemin = Path(_demander(lire, ecrire, "recette :", str(defaut)))
    try:
        recette = Recette.lire(chemin)
    except RecetteInvalide as refus:
        ecrire(f"  REFUS : {refus}")
        return None
    ecrire("")
    ecrire(recette.rendre())
    return recette


def _dicter(driver, lire, ecrire, sortie: Path, jeu_defaut: Path) -> None:
    """La premiere passe : le programme montre, vous dictez, il enregistre."""
    parametres = _parametres(lire, ecrire, jeu_defaut)
    if parametres is None:
        return
    _, par_classe = parametres
    classe = _choisir_classe(lire, ecrire, list(par_classe))
    if classe is None:
        return
    points = par_classe[classe]
    transaction = _demander(lire, ecrire, "transaction a ouvrir :", "CL24N")
    ecrire(f"  la dictee se fait avec le premier point de {classe} : "
           f"{points[0]}")
    ecrire("  ce point sera REELLEMENT saisi dans SAP — c'est ce qui fait que "
           "la passe aboutit.")
    identite = driver.screen()
    if not confirmer(classe, identite, executer=True, lire=lire, ecrire=ecrire):
        ecrire("  non confirmee : rien n'a ete fait.")
        return
    dicter_sur(driver, {COLONNE_POINT: points[0], COLONNE_CLASSE: classe},
               colonnes=[COLONNE_POINT, COLONNE_CLASSE], sortie=sortie,
               transaction=transaction, lire=lire, ecrire=ecrire)


def _rejouer(driver, lire, ecrire, sortie: Path, jeu_defaut: Path, *,
             executer: bool) -> None:
    recette = _choisir_recette(lire, ecrire, sortie)
    if recette is None:
        return
    parametres = _parametres(lire, ecrire, jeu_defaut)
    if parametres is None:
        return
    _, par_classe = parametres
    manquantes = [c for c in recette.colonnes
                  if c not in (COLONNE_POINT, COLONNE_CLASSE)]
    if manquantes:
        ecrire(f"  REFUS : la recette demande les colonnes {manquantes}, que "
               f"le fichier ne porte pas.")
        return

    classes: list[str] = []
    if not executer:
        choisie = _choisir_classe(lire, ecrire, list(par_classe))
        if choisie is None:
            return
        classes = [choisie]

    concernees = {c: p for c, p in par_classe.items() if not classes or c in classes}
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
    rejouer_sur(driver, recette, retenues, executer=executer, sortie=sortie,
                lire=lire, ecrire=ecrire)


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
        ecrire("   3  DICTER la premiere passe — vous guidez, il apprend")
        ecrire("   4  Rejouer A BLANC — une classe, aucune sauvegarde")
        ecrire("   5  Rejouer et EXECUTER — toutes les classes, avec sauvegarde")
        ecrire("   6  Lister les sorties")
        ecrire("   0  Quitter")
        try:
            choix = lire("  choix : ").strip()
        except EOFError:
            return 0
        if choix in ("0", "q", "Q"):
            return 0
        if choix == "6":
            _lister(ecrire, sortie)
            continue
        if choix not in ("1", "2", "3", "4", "5"):
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
            elif choix == "3":
                _dicter(actif, lire, ecrire, sortie, jeu_defaut)
            else:
                _rejouer(actif, lire, ecrire, sortie, jeu_defaut,
                         executer=(choix == "5"))
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
    parseur.add_argument("--recette", type=Path,
                         help="la recette a rejouer (dictee par le menu)")
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

    if args.recette is None or args.plafond_points is None:
        print("refus : --recette et --plafond-points sont obligatoires pour "
              "un lancement scripte. Sans argument, le programme affiche un "
              "menu, et c'est lui qui fait dicter la premiere passe.")
        return 2
    if args.par_lot < 0:
        print("refus : --par-lot doit etre positif ou nul")
        return 2
    try:
        recette = Recette.lire(args.recette)
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
    return rejouer_sur(driver, recette, retenues, executer=args.executer,
                       sortie=args.sortie, par_lot=args.par_lot)


if __name__ == "__main__":
    raise SystemExit(main())
