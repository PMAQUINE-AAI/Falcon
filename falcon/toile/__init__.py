"""De quoi peindre une interface sur le terminal qu'on a REELLEMENT en face.

Ce paquet ne connait pas un mot de FALCON : ni SAP, ni trace, ni catalogue. Il
sait mesurer ce qu'un terminal tient, et transformer des intentions de lecture
en lignes de texte. C'est ce cloisonnement qui permet d'y confiner la seule
capacite du depot qui depende de la plateforme d'affichage — les sequences
ANSI — comme `falcon/couture/sapgui.py` confine COM.

**Le refus d'ANSI du depot n'etait pas une ascese, c'etait un refus faute de
savoir.** `console/menu.py` le dit : la machine cible est Windows, `curses`
n'y est pas fourni, une sequence marcherait sur la moitie des terminaux et
laisserait des caracteres parasites sur l'autre. C'est vrai TANT QU'ON NE
MESURE PAS. Windows repond a la question depuis 2015 : on pose
`ENABLE_VIRTUAL_TERMINAL_PROCESSING`, **on le relit**, et l'echec de
`GetConsoleMode` est lui-meme la reponse. Un refus qu'on sait lever sur preuve
n'est plus un plafond : c'est une garantie.

**Aucune decision de `SPEC_FALCON.md` n'est encore amendee, et ce paragraphe
ne fait pas semblant du contraire.** Les n°15 et n°16 affirment toujours
« aucune sequence ANSI », et elles restent vraies tant que rien ne peint —
aucun appelant de ce paquet n'emet une seule sequence aujourd'hui. Le lot qui
peindra devra l'ecrire, sous un numero qui n'existe pas encore : la table
s'arrete a la vingtieme. Citer la dix-septieme, qui parle de navigation entre
unites de travail, enverrait le lecteur lire un paragraphe sans rapport et lui
apprendrait que les docstrings de ce depot ne citent pas juste.

**Deux niveaux, et pas quatre.** `NU` est le cas de BASE, pas un repli :
`PeintreNu` est l'identite, et `PeintreColore` n'ajoute que des enveloppes
autour des lignes que `PeintreNu` a produites. Il n'y a pas de demi-DECOR : le
peintre colore n'existe qu'au-dessus du nu, et la composition d'un niveau
intermediaire de decor rendrait une interface cassee, pas une demi-interface.

La largeur et la couleur, en revanche, se mesurent SEPAREMENT et echouent
separement. Un pty sans TIOCSWINSZ donne « taille inconnue » et « niveau
retenu COULEUR » — mesure, pas suppose : `falcon sonde` le rend tel quel — et
un `pythonw` sans descripteur fait de meme sur Windows. Un gabarit de 72 non
mesure peut donc etre peint en couleur, et c'est bien ainsi : refuser la
couleur parce qu'on ignore la largeur n'apprendrait la largeur a personne.

**Rien ici n'ecrit nulle part.** Le choix du flux appartient a l'appelant :
`Console.ecrire` pour le dialogue, un flux et un retour chariot pour la ligne
collante du direct. Les deux ne peuvent pas passer par la meme porte —
`Console.ecrire` vaut `print`, il pose une ligne entiere — et pretendre le
contraire donnerait une abstraction qui ment sur l'un des deux cas.

**Ce que la CI ne prouvera jamais, et qu'il faut lire avant de croire un test
vert.** Meme reserve, et meme forme, que pour `couture/sapgui.py` :

1. Que `GetConsoleMode` / `SetConsoleMode` se comportent comme le double le
   suppose. Le banc prouve que la sonde est coherente avec NOTRE modele de
   Windows, bati sur la source C de CPython. Pas avec Windows.
2. Que la coupure `OSError` / `ValueError` d'`os.get_terminal_size` soit bien
   celle decrite. Lue dans `Modules/posixmodule.c`, jamais executee la-bas.
3. A partir de quelle version de Windows le bit VT existe. Aucun numero de
   build n'est ecrit dans ce code : le protocole ne demande jamais sa version
   a Windows, il pose le bit et le relit.
4. Que le decor s'AFFICHE. L'encodage ne promet que l'encodage : une console en
   police raster affiche un carre vide la ou la police n'a pas le glyphe, sans
   erreur et sans code retour. C'est pourquoi tout le decor est ASCII et
   cp1252, et qu'aucun caractere semi-graphique n'est pose nulle part.
5. Que conhost n'ajoute pas une rangee fantome sur une ligne pleine. La marge
   d'une colonne (`colonnes - 1`) est une parade a cout nul contre un
   comportement que la CI Linux ne verra jamais.
6. Que seize couleurs SGR passent a travers une liaison RDP.

**Le premier geste apres livraison est `falcon sonde` sur la machine cible**,
pas `falcon explorer`. Le pire cas de ce paquet n'est pas qu'il refuse la
couleur : c'est qu'il l'accepte a tort.
"""

from __future__ import annotations

from .capacites import (
    COULEUR, DECLAREE, ENCODAGE_MINIMAL, HAUTEUR_SANS_MESURE, INCONNUE,
    LARGEUR_PLAFOND, LARGEUR_PLANCHER, LARGEUR_SANS_MESURE, MESUREE, NU,
    NOTE_DE_LECTURE, STD_ERREUR, STD_SORTIE, VT_SORTIE, Capacites,
    ConsoleWindows, Gabarit, Systeme, gabarit_pour, rendre_capacites,
    rendre_sonde, sonder, systeme_reel,
)
from .fragment import (
    ALERTE, ATTENUE, DANGER, ENTETE, FORMES, LIGNE, MARQUE, NEUTRE,
    SEPARATEUR, SUCCES, TITRE, TONS, VIDE, Bloc, Fragment, colonnes, couper,
    couper_chemin, texte_nu,
)
from .peintre import (
    Peintre, PeintreColore, PeintreNu, RenduRefuse, peintre_pour,
)
from .sequences import retirer

__all__ = [
    # la sonde
    "Systeme", "systeme_reel", "ConsoleWindows", "Capacites", "sonder",
    "rendre_capacites", "rendre_sonde", "NOTE_DE_LECTURE",
    "Gabarit", "gabarit_pour",
    "NU", "COULEUR", "MESUREE", "DECLAREE", "INCONNUE",
    "LARGEUR_SANS_MESURE", "LARGEUR_PLANCHER", "LARGEUR_PLAFOND",
    "HAUTEUR_SANS_MESURE", "ENCODAGE_MINIMAL",
    "STD_SORTIE", "STD_ERREUR", "VT_SORTIE",
    # les intentions de lecture
    "Fragment", "Bloc", "texte_nu", "couper", "couper_chemin", "colonnes",
    "TONS", "FORMES", "MARQUE",
    "NEUTRE", "TITRE", "ATTENUE", "SUCCES", "ALERTE", "DANGER",
    "LIGNE", "ENTETE", "SEPARATEUR", "VIDE",
    # les peintres
    "Peintre", "PeintreNu", "PeintreColore", "peintre_pour", "RenduRefuse",
    "retirer",
]
