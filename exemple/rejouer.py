"""Deroule l'exemple de bout en bout, SANS SAP, contre le double.

    python exemple/rejouer.py

**A quoi ca sert.** Le reste du depot prouve que chaque piece marche. Ceci
montre l'enchainement : convertir les CSV, charger, repeter a blanc, executer,
lire le journal. C'est la difference entre « le logiciel est complet » et « je
sais m'en servir ».

**Ce que ca ne prouve PAS.** Le driver employe ici est `DriverScripte`, le
double de test. Il repond ce qu'on lui a dit de repondre. Aucune ligne de ce
depot n'a jamais parle a un vrai SAP, et ce script n'y change rien : il
verifie l'enchainement, pas le dialogue avec l'ERP.

Sur un poste reel, on ne lance pas ce script : on ouvre la console
(`python -m falcon console`), qui se greffe sur une session SAP ouverte.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE.parent))

from falcon.couture.double import DriverScripte           # noqa: E402
from falcon.donnees import lire_items                     # noqa: E402
from falcon.journal import lire, rendre                    # noqa: E402
from falcon.journal.rapport import depuis_journal          # noqa: E402
from falcon.noyau import Identite, Statut                  # noqa: E402
from falcon.moteur import executer                         # noqa: E402
from falcon.pipeline import charger                        # noqa: E402
from falcon.tableur import convertir_fichiers              # noqa: E402

#: L'ecran que les etapes de l'exemple declarent. Le double le rend tel quel :
#: la garde d'identite compare CE triplet a chaque etape, et une pipeline dont
#: l'ecran ne correspond pas s'arrete avant d'agir.
IA08 = Identite(transaction="IA08", programme="RIPLKO10", dynpro="1000")


def _titre(texte: str) -> None:
    print(f"\n{'=' * 70}\n  {texte}\n{'=' * 70}")


def _driver() -> DriverScripte:
    """Un SAP de theatre : il accepte les saisies et les relit a l'identique.

    `apres_action` est le point ou un test — ou cet exemple — decide de ce que
    le monde repond. Ici il fait le minimum honnete : ce qu'on ecrit se relit,
    donc la garde de relecture est satisfaite, et la barre de statut annonce
    un succes apres la sauvegarde.
    """
    pilote = DriverScripte(identite=IA08, valeurs={})

    def apres(brut: DriverScripte, geste: str, cible: str) -> None:
        if geste == "write":
            brut.valeurs[cible] = brut.valeurs.get(cible, "")
        if geste == "press" and "btn[11]" in cible:
            brut.statut = Statut(type="S", id="IW", numero="001",
                                 texte="Enregistrement effectue")

    pilote.apres_action = apres
    return pilote


def main() -> int:
    travail = Path(tempfile.mkdtemp(prefix="falcon-exemple-"))
    for nom in ("pipeline.csv", "etapes.csv", "derogations.csv", "jeu.csv"):
        shutil.copy(RACINE / nom, travail / nom)

    _titre("1. Les trois CSV du classeur deviennent une pipeline")
    yaml = convertir_fichiers(travail, travail / "exemple_variantes.yaml")
    print(f"  {yaml.name} ecrit — et RELU par `charger()` avant l'ecriture.")
    print("  Un YAML refuse ne serait pas ecrit du tout.")

    pipeline = charger(yaml)
    print(f"\n  nom        {pipeline.nom}")
    print(f"  empreinte  {pipeline.empreinte}")
    print(f"  etapes     {len(pipeline.etapes)}")
    print(f"  plafonds   {pipeline.plafond_items} items, "
          f"{pipeline.plafond_sauvegardes} sauvegardes")

    _titre("2. Le jeu, regroupe par unite de sauvegarde SAP")
    items, dialecte = lire_items(travail / "jeu.csv", pipeline.cles)
    print(f"  colonnes   {list(dialecte.colonnes)}")
    print(f"  items      {len(items)}  (une ligne = un item ici, car `site` "
          f"est unique)")
    for item in items:
        print(f"    {item.item_id[:12]}…  {item.cle}")

    _titre("3. Repetition a blanc — tout, SAUF la validation")
    resultat = executer(pipeline, travail / "jeu.csv", _driver(),
                        journal=travail / "journal.jsonl", mode="dry-run")
    print(f"  etat       {resultat.etat}")
    print(f"  compteurs  {resultat.compteurs}")
    print("\n  Aucune sauvegarde n'a eu lieu : le mode `dry-run` s'arrete")
    print("  avant, et la garde de rayon d'action le verifie.")

    _titre("4. Execution — ce que le double a reellement recu")
    pilote = _driver()
    resultat = executer(pipeline, travail / "jeu.csv", pilote,
                        journal=travail / "journal.jsonl", mode="run",
                        sortie_ko=str(travail / "journal.ko.csv"))
    print(f"  etat       {resultat.etat}")
    print(f"  compteurs  {resultat.compteurs}")

    print("\n  Les valeurs tapees, pour le premier item :")
    for geste, cible, valeur in pilote.gestes[:5]:
        if geste == "write":
            print(f"    {cible:<32} « {valeur} »")

    print("\n  Ce que les transformations ont fait :")
    print("    - `site` est passe en MAJUSCULES        (format: majuscules)")
    print("    - la variante compose le site           (gabarit)")
    print("    - l'equipement est cadre a 18 positions (zeros: 18),")
    print("      apres elagage des espaces de l'export (sans_espaces_autour)")
    print("\n  Et la regle qu'il faut avoir en tete : un `gabarit` lit le JEU,")
    print("  pas le resultat d'une etape precedente. Le `majuscules` de la")
    print("  premiere etape ne remonte donc pas dans la variante — celle-ci")
    print("  declare le sien. Pour reutiliser une valeur LUE dans SAP, c'est")
    print("  `action: lire` puis `source: {lue: <nom de l etape>}`.")

    _titre("5. Le journal fait foi")
    for ligne in rendre(depuis_journal(lire(travail / "journal.jsonl"))).splitlines():
        print(f"  {ligne}")

    print(f"\n  Tout est reste dans {travail}")
    print("  Rien n'a ete ecrit dans un SAP : le driver est un double.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
