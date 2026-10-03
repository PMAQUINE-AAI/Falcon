# Architecture FALCON v1

## Flux
```
trace .vbs ──trace.py──> étapes ──recipe.py──> recette (YAML, colonnes CSV liées aux champs)
                                                   │
CSV de données ──────────────────────────> runner.py ──sap.py──> SAP GUI (COM, Windows)
                                                   │
                                     journal.py (OK/KO par ligne, CSV des KO réinjectable)
                                                   │
                                     report.py (rapport d'exécution .zip à envoyer)
ui.py (menu riche) / cli.py ──> appellent runner, recipe, trace, report. Aucune logique métier.
```

## Modules (`falcon/`) — 300 lignes max chacun

| Module | Rôle | Dépend de | Tests |
|---|---|---|---|
| `trace.py` | Lire un .vbs du recorder (UTF-16 ou UTF-8) et produire une liste d'étapes | – | oui |
| `recipe.py` | Étapes plus liaisons de colonnes donnent une recette ; lecture et écriture YAML | trace | oui |
| `sap.py` | Seul fichier qui touche `win32com` : attacher la session, `findById`, set, press, sendVKey, barre de statut | – | **non, validé en réel** |
| `journal.py` | Écrire le résultat par ligne (JSONL) et le CSV des KO au format d'entrée | – | oui |
| `report.py` | Log complet de l'exécution et paquet .zip à envoyer | – | oui |
| `runner.py` | Boucler sur le CSV, appliquer la recette via `sap`, contrôler statut et popup ; mode à blanc et plafond | recipe, sap, journal, report | logique pure seulement |
| `cli.py` | Commandes : `run`, `smoke`, `rapport`… | runner, report | non |
| `ui.py` | Menu riche | runner, report | non |

Sens unique : `ui`/`cli` → `runner` → (`recipe` → `trace`), `sap`, `journal`, `report`. Jamais l'inverse.

## Rapport d'exécution (exigence centrale)
Le PC client n'a pas git. **Chaque exécution, y compris un crash, produit un seul fichier** `rapports/falcon_<date>_<cmd>.zip` contenant :
- le log complet niveau DEBUG : chaque appel SAP (id, action, valeur), le texte et le type de la barre de statut, le titre de la fenêtre, la traceback complète ;
- l'environnement : version de FALCON, de Python, de Windows et de SAP GUI, et l'état du scripting ;
- les entrées : trace, recette, CSV ;
- les sorties : journal, KO.

Le chemin du zip s'affiche à la fin et une entrée du menu l'ouvre dans l'Explorateur. Philippe l'envoie et l'agent le lit. C'est la seule boucle de retour avec SAP.

## Livraison
`falcon.pyz` (zipapp, dépendances incluses) copié sur le PC client. Python 3.11+ sur le client, pas de git.
