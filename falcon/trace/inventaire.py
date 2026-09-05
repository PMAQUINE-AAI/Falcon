"""Rapport de couverture d'une trace — la premiere chose a passer dessus.

« La taxonomie se recolte », dit la specification des erreurs. Ce module
applique la meme regle au parseur : au lieu de theoriser sur ce que le
recorder produit, on lui fait dire ce qu'il produit, et ce qu'on ne sait pas
encore en lire.

Le rapport nomme trois choses distinctes, qu'il ne faut pas confondre :

- **les lignes non appariees**, rendues VERBATIM — le parseur ne connait pas
  leur forme, et la lecture stricte echouerait dessus ;
- **les verbes inconnus** — la forme est comprise, le verbe ne figure pas
  parmi ceux releves. La lecture stricte les accepte ; c'est le generateur
  d'esquisse qui devra refuser d'en faire une etape ;
- **l'encodage retenu** — pour qu'une lecture de travers soit diagnosticable.

Quand toutes les lignes sont appariees, il ajoute l'apercu des ecrans
conjectures. Quand elles ne le sont pas, il ne l'ajoute PAS : un decoupage
d'ecrans fait sur des lignes manquantes serait faux sans le dire.

    python -m falcon.trace trace.vbs
"""

from __future__ import annotations

import sys
from pathlib import Path

from .esquisse import apercu
from .modele import CONFORT, Inventaire
from .vbs import inventorier, lire

AIDE = """Usage : python -m falcon.trace <trace.vbs> [...]

Rapport de couverture d'un enregistrement du SAP GUI Recorder : ce que le
parseur sait en lire, et ce qu'il n'en sait pas.

Code de retour : 0 si toutes les lignes sont appariees, 1 sinon."""


def rapport(inventaire: Inventaire) -> str:
    """Le rapport, en texte, sans couleur ni ANSI."""
    lignes = [
        f"{inventaire.source}",
        f"  encodage         {inventaire.encodage}"
        f"{' + BOM' if inventaire.bom else ' (suppose, aucun BOM)'}",
        f"  fins de ligne    {inventaire.fin_de_ligne!r}",
        f"  lignes           {inventaire.lignes}",
        f"    gestes         {inventaire.gestes}",
        f"    prologue       {inventaire.prologue}",
        f"    commentaires   {inventaire.commentaires}",
        f"    vides          {inventaire.vides}",
        f"    non appariees  {len(inventaire.inconnues)}",
    ]

    if inventaire.par_verbe:
        lignes.append("")
        lignes.append("  verbes")
        largeur = max(len(v) for v, _ in inventaire.par_verbe)
        for verbe, combien in inventaire.par_verbe:
            marques = []
            if verbe in inventaire.verbes_inconnus:
                marques.append("INCONNU")
            elif verbe in CONFORT:
                marques.append("confort")
            suffixe = ("   " + " ".join(marques)) if marques else ""
            lignes.append(f"    {verbe.ljust(largeur)}  {combien:>4}{suffixe}")

    if inventaire.verbes_inconnus:
        lignes.append("")
        lignes.append(
            f"  {len(inventaire.verbes_inconnus)} verbe(s) hors du releve : "
            f"{', '.join(inventaire.verbes_inconnus)}")
        lignes.append(
            "  La forme est comprise, le verbe non. La lecture les accepte ; "
            "un brouillon")
        lignes.append(
            "  de pipeline devra refuser d'en faire une etape.")

    if inventaire.inconnues:
        lignes.append("")
        lignes.append(f"  {len(inventaire.inconnues)} ligne(s) non appariee(s), "
                      f"verbatim :")
        for rang, texte in inventaire.inconnues:
            lignes.append(f"    {rang:>5}  {texte}")
        lignes.append("")
        lignes.append("  La lecture stricte echouerait sur ces lignes. Elles "
                      "sont ce que le")
        lignes.append("  parseur doit apprendre avant que cette trace serve a "
                      "quoi que ce soit.")
    else:
        lignes.append("")
        lignes.append("  Toutes les lignes sont appariees.")

    return "\n".join(lignes)


def main(arguments: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if not arguments or arguments[0] in ("-h", "--help", "--aide"):
        print(AIDE)
        return 0 if arguments else 2

    code = 0
    for chemin in arguments:
        inventaire = inventorier(Path(chemin))
        print(rapport(inventaire))
        if inventaire.complet:
            # L'apercu se rend depuis une lecture stricte : un decoupage fait
            # sur des lignes manquantes serait faux sans le dire.
            print()
            print(apercu(lire(Path(chemin))))
        else:
            code = 1
        print()
    return code


if __name__ == "__main__":                      # pragma: no cover
    raise SystemExit(main())
