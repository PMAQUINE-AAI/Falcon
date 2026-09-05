"""`diagnostiquer` — le premier contact reel du projet, en lecture seule.

Se connecte a la session SAP ouverte, rend l'identite de l'ecran courant, les
fenetres, la barre de statut et le releve des champs. **Rien d'autre.**

La lecture seule n'est pas une promesse tenue par la relecture : la commande
ne recoit qu'un `DriverLecture`, qui n'a ni `write`, ni `press`, ni `vkey`.
Ajouter une ecriture ici ne compilerait pas — elle leverait un
`AttributeError` au premier essai, avant toute session reelle.

L'option `--catalogue` verse le releve **en quarantaine**, jamais au catalogue
cure : un releve fraichement capture n'a ete relu par personne. La promotion
reste un geste explicite, et c'est le moment ou un humain dit avoir regarde
l'ecran.
"""

from __future__ import annotations

from pathlib import Path

from falcon.catalogue import Depot, variante_de
from falcon.couture import DriverLecture
from falcon.noyau import Ecran, maintenant


def rapport(lecteur: DriverLecture, fenetre: str = "wnd[0]") -> str:
    """Le diagnostic, en texte, sans couleur ni ANSI."""
    identite = lecteur.screen()
    ecran = lecteur.fields(fenetre)
    statut = lecteur.status()

    lignes = [
        "FALCON — diagnostic (lecture seule)",
        "",
        "  ecran courant",
        f"    systeme      {identite.systeme or '-'}",
        f"    mandant      {identite.mandant or '-'}",
        f"    langue       {identite.langue or '-'}",
        f"    transaction  {identite.transaction or '-'}",
        f"    programme    {identite.programme or '-'}",
        f"    dynpro       {identite.dynpro or '-'}",
        f"    empreinte    {ecran.empreinte}",
        "",
        "  fenetres",
    ]
    for ouverte in lecteur.windows():
        marque = "modale" if ouverte.modale else "principale"
        lignes.append(f"    {ouverte.id:<8} {ouverte.type:<16} {marque:<11}"
                      f" « {ouverte.titre} »")

    lignes.append("")
    if statut.vide:
        lignes.append("  statut         (barre vide)")
    else:
        lignes.append(f"  statut         {statut.type} {statut.cle} "
                      f"« {statut.texte} »")

    lignes.append("")
    lignes.append(f"  champs de {fenetre} ({len(ecran.champs)})")
    for champ in ecran.champs:
        soustype = f"/{champ.soustype}" if champ.soustype else ""
        fige = "" if champ.modifiable else "  (fige)"
        lignes.append(f"    {champ.id}")
        lignes.append(f"        {champ.type}{soustype}"
                      f"{('  ' + champ.nom) if champ.nom else ''}"
                      f"{(' « ' + champ.texte + ' »') if champ.texte else ''}"
                      f"{fige}")
    return "\n".join(lignes)


def cataloguer(ecran: Ecran, dossier: str | Path) -> Path:
    """Verse un releve en quarantaine. Rend le fichier ecrit.

    En quarantaine et non au catalogue : personne n'a encore relu cet ecran.
    Le releve porte la source `observee` — c'en est un, pris sur un systeme
    reel — ce qui le distingue d'une esquisse conjecturee depuis une trace.
    """
    depot = Depot(dossier)
    return depot.mettre_en_quarantaine(variante_de(ecran))


def diagnostiquer(lecteur: DriverLecture, *, fenetre: str = "wnd[0]",
                  catalogue: str | Path | None = None) -> str:
    """Le diagnostic, et son eventuel versement en quarantaine."""
    texte = rapport(lecteur, fenetre)
    if catalogue is not None:
        ecran = lecteur.fields(fenetre)
        if not ecran.capture_le:
            ecran = Ecran(identite=ecran.identite, fenetre=ecran.fenetre,
                          titre=ecran.titre, champs=ecran.champs,
                          capture_le=maintenant())
        chemin = cataloguer(ecran, catalogue)
        texte += f"\n\n  releve verse en quarantaine : {chemin}"
        texte += ("\n  Le promouvoir au catalogue reste un geste explicite — "
                  "c'est celui\n  par lequel un humain dit avoir relu l'ecran.")
    return texte
