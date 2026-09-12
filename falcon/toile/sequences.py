"""Les sequences ANSI, et le SEUL endroit de FALCON ou elles s'ecrivent.

Meme discipline que `falcon/couture/sapgui.py` pour COM : une capacite qui
depend de la plateforme se confine dans un module nomme, et un test de
frontiere verifie qu'elle n'en sort ni par un litteral, ni par un import. Deux
regles, parce qu'aucune des deux ne suffit seule : `chr(27) + "["` ne
contient aucun `\\x1b` litteral et passerait n'importe quel scan de texte.
C'est la cicatrice de `test_aucun_sous_processus_ne_passe_par_le_shell` —
« un controle qui confond une promesse avec son execution ne controle rien ».

Le reste du depot ne devient PAS plus permissif pour que ce module existe.
`falcon/console/*.py` reste sous la garde AST qui interdit `\\x1b` dans ses
litteraux, et c'est elle qui garantit que le code d'ecran est lisible sans
decor — la propriete qui fait que les deux niveaux ne peuvent pas diverger.

Le vocabulaire est volontairement minuscule : SGR, et rien d'autre. Pas de
positionnement de curseur, pas d'effacement, pas d'ecran alterne. Ces trois-la
supposent un ancrage que rien ne nous donne sur un conhost, et leur echec est
silencieux : un ecran a moitie dessine se lit comme un ecran correct.

**Seize couleurs, jamais 256 ni 24 bits.** `COLORTERM` est une declaration, et
ce paquet ne traite pas une declaration comme une mesure. Seize est ce que
toute console qui interprete SGR tient, conhost compris : un plafond de moins
auquel se tromper.
"""

from __future__ import annotations

import re

from .fragment import ALERTE, ATTENUE, DANGER, NEUTRE, SUCCES, TITRE, TONS

ECHAP = "\x1b"
CSI = ECHAP + "["

#: Fin de toute mise en forme. Pose apres chaque teinte, jamais omise : une
#: sequence ouverte qui n'est pas refermee teint tout ce qui suit, y compris
#: l'invite du shell une fois FALCON sorti.
NEUTRALISATION = 0

#: Ton -> codes SGR. Seize couleurs, et le gras/l'attenuation qui n'en sont
#: pas. La table est FERMEE sur `TONS` (test), parce qu'un ton sans entree
#: sortirait sans decor : un avertissement qui perd sa marque reste lisible, et
#: personne ne s'en apercoit.
CODES: dict[str, tuple[int, ...]] = {
    NEUTRE: (),
    TITRE: (1,),            # gras
    ATTENUE: (2,),          # demi-intensite
    SUCCES: (32,),          # vert
    ALERTE: (33,),          # jaune
    DANGER: (31,),          # rouge
}


def sgr(*codes: int) -> str:
    """Une sequence SGR, ou la chaine vide si on ne demande rien.

    La chaine vide est le cas utile : elle permet a l'appelant d'ecrire
    `sgr(*CODES[ton]) + texte` sans se demander si le ton est neutre, et sans
    poser un `CSI m` qui reinitialiserait la mise en forme de ce qui precede.
    """
    if not codes:
        return ""
    return CSI + ";".join(str(code) for code in codes) + "m"


def teinter(texte: str, ton: str) -> str:
    """Enveloppe `texte` du decor de `ton`. LEVE sur un ton inconnu.

    Retomber au neutre serait le defaut exact que `Fragment` refuse deja :
    une ligne « AGIT DANS SAP » qui perd son marquage reste parfaitement
    lisible, donc rien ne signale la perte.
    """
    if ton not in TONS:
        raise ValueError(f"ton inconnu : {ton!r} ; connus : "
                         f"{sorted(TONS)}")
    codes = CODES[ton]
    if not codes or not texte:
        return texte
    return sgr(*codes) + texte + sgr(NEUTRALISATION)


#: Toute sequence CSI, pas seulement SGR.
#:
#: Large a dessein : `retirer` sert a PROUVER qu'il ne reste rien, et une
#: expression qui ne connaitrait que `m` laisserait passer ce que ce module
#: s'interdit d'ecrire mais qu'un jour quelqu'un pourrait y ajouter.
_SEQUENCE = re.compile(re.escape(ECHAP) + r"\[[0-?]*[ -/]*[@-~]")


def retirer(texte: str) -> str:
    """Le texte sans aucune sequence. L'outil de l'invariant.

    Sans lui, « la couleur n'ajoute et ne retire rien » resterait une
    affirmation. Avec lui, c'est une EGALITE qu'un test evalue bloc par bloc,
    sur chaque ecran : `retirer(colore.peindre(b)) == nu.peindre(b)`.
    """
    return _SEQUENCE.sub("", texte)
