# Phenix

Outillage de scripting SAP GUI : un **harness de test** qui rend détectables,
hors SAP et en quelques secondes, les erreurs qui en production ne lèvent
aucune exception.

Phenix reprend l'expérience du développement d'EagleLoader — une dizaine de
simulateurs COM jetables, réécrits à chaque fois, chacun réencodant à la main
les mécaniques pièges de SAP GUI. Ces mécaniques sont ici figées une bonne
fois, dans le simulateur et dans la carte des contrôles.

## Le problème

Les erreurs les plus graves du scripting SAP GUI sont **silencieuses**. Un
bouton pressé sur le mauvais écran insère une opération. Un compteur mal lu
arrête une boucle après le premier élément. Un contrôle mal identifié retourne
`SAP.Toolbar.1` comme s'il s'agissait d'un texte métier. Le programme continue,
produit un résultat plausible, et le défaut se découvre au contrôle qualité —
ou jamais.

Tester contre le vrai SAP est impraticable : c'est lent, ça nécessite un
système, et ça écrit dans des données de production.

## Démarrage

```bash
python sapharness/sapmock.py          # auto-test du simulateur
python -m unittest discover -s tests  # suite de non-régression
```

Seule dépendance externe : `PyYAML`, pour lire les cartes de contrôles.

Pour écrire un scénario, lire [docs/GUIDE.md](docs/GUIDE.md) : référence
complète du simulateur, catalogue d'invariants, et surtout la liste de ce que
le simulateur **ne** modélise **pas**.

## Organisation

| Chemin | Contenu |
|---|---|
| `sapharness/sapmock.py` | simulateur SAP GUI : `Monde`, `Ecran`, `TableControl`, `Grille`, `Session`, `Journal` |
| `sapharness/carte.py` | chargement des cartes de contrôles depuis YAML |
| `sapharness/backends/` | canaux d'échange de texte (contrôle direct, fichier RTF, presse-papier) — à construire |
| `cartes/sap_map.yaml` | identifiants réels relevés sur le système K75, mandant 210 |
| `pipelines/` | enchaînements de bout en bout — à construire |
| `programmes/` | points d'entrée exécutables — à construire |
| `tests/` | non-régression du simulateur et de la carte |
| `docs/GUIDE.md` | référence d'usage du simulateur — exemples exécutés par les tests |
| `docs/HARNESS.md` | ce que fournit le harness, et ce qu'il reste à construire |
| `docs/TRAPS.md` | les douze pièges du terrain : symptôme, cause, règle |

## Deux principes structurants

**Les identifiants sont des données.** `cartes/sap_map.yaml` est chargé, jamais
codé en dur : les IDs changent avec le système, le mandant et la release. C'est
ce qui rend le portage vers un autre mandant trivial.

**Les assertions portent sur les gestes, pas sur le résultat.** Le `Journal`
trace ce que le programme a réellement fait, et permet d'asserter des
invariants :

```python
# btn[7] = "opération suivante" sur le détail, "Insérer" sur la synthèse
journal.assert_jamais("wnd[0]/tbar[1]/btn[7]", hors_ecran="detail")

# SAP enregistre la gamme entière : une sauvegarde par gamme, pas par texte
journal.assert_au_plus("save", 1)

# en dry-run, aucune écriture ne doit avoir lieu
assert journal.compter("saisie") == 0
```

Ces trois assertions auraient détecté hors SAP trois défauts qui ont
effectivement atteint la production.

## Avant d'écrire du code SAP

Lire `docs/TRAPS.md`. Chacun des pièges qui y figurent a coûté au moins un
cycle complet de développement, et aucun ne produit d'erreur.
