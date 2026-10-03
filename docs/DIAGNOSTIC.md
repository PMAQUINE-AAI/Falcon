# Diagnostic FALCON v0 (2026-10-03)

État analysé : tag `v0-archive` (`8fa0cc7`), 90 commits du 31/08 au 21/09/2026, quasi tous d'une seule session Claude.

## Les chiffres

| | Lignes |
|---|---|
| `falcon/` (85 fichiers) | 22 236, dont 37 % de prose (docstrings, commentaires) |
| `cl24n/cl24n.py` | 2 538, qui duplique une bonne part de `falcon/` |
| Tests (`tests/` + cl24n + historique) | ~24 700, soit environ 1 577 tests |
| Appels COM réels à SAP (`couture/sapgui.py`) | **325 (1,5 %)** |
| Interface terminal (`console` + `toile`) | 6 945 (31 %) |
| Cœur fonctionnel réellement utile (estimation) | **800 à 1 200** |

Le premier contact avec un vrai SAP a eu lieu le 14/09 (`2ea6fd2`), avec 1 427 tests au vert. Il a échoué dès le 2ᵉ geste : SAP rend un chemin absolu, alors que tout le dépôt comparait la forme courte.

## Pourquoi un quick fix devenait une refonte

1. **La doctrine du backlog l'imposait.** Trois règles se combinaient :
   - « chaque garde retirée doit faire tomber la suite » (BACKLOG:21-26), vérifiée en CI par `outils/neutraliser.py` ;
   - « tout écart de périmètre est inscrit au §8 dans le même commit » (BACKLOG:34) ;
   - « chaque correction porte son test de non-régression » (BACKLOG:190).

   Avec ces règles, un correctif devient : une généralisation (« corriger sept sites un par un aurait laissé le huitième », `62059ae`), une nouvelle garde, un contrôle négatif, une décision numérotée et une réécriture de la documentation.
2. **Les règles sont dupliquées partout.** Ajouter une méthode à `Driver` touche 8 fichiers. `plafond_sauvegardes` circule dans 11 fichiers. Les 83 imports locaux cachent deux cycles (console ↔ commandes, console ↔ toile), si bien qu'on ne voit pas le rayon d'impact.
3. **La prose est contractuelle.** 37 % du code est de la justification (« décision n°14 », « lot 14 »). Toute modification doit garder cette prose vraie.
4. **Les tests figent le texte.** 376 tests cherchent une phrase française littérale. Reformuler un écran casse des dizaines de tests, et l'agent réécrit alors le code et les tests ensemble.
5. **Les revues adverses n'avaient pas de critère d'arrêt.** Chaque passe trouvait N « bloquants », et chaque correction en ouvrait d'autres. Le nombre de gardes est passé de 5 à 9. `e15103f` s'intitule : « Le défaut que le commit précédent déclarait avoir corrigé ».

Pires ratios entre le problème et le diff :

| Commit | Problème | Diff |
|---|---|---|
| `b63995d` | une phrase fausse | 16 fichiers, +2 056 |
| `4bc0d5f` | un appel manquant | 11 fichiers, +520, décision n°21 |
| `4a47262` | un mot absent d'un menu | +272, plus une « garde de vocabulaire » |

## Pourquoi il fallait plusieurs prompts avant que l'agent bouge dans le terminal

- **Les consignes poussaient à s'arrêter plutôt qu'à agir** :
  - « Aucun comportement SAP n'est inventé… s'arrête et le dit » (BACKLOG:31) ;
  - « la preuve est un appel système, jamais une supposition » (décision n°21) ;
  - « ne jamais présenter une relecture à l'œil comme une vérification ».
- **L'agent mesurait au lieu de lancer.** Pour « faire tourner la console », il a écrit une sonde de terminal de 540 lignes (`0cf7629`), puis une passe pour que la sonde « cesse d'affirmer ce qu'elle n'a pas mesuré » (`b63995d`). Les menus n'étaient toujours pas colorés (`4bc0d5f`).
- **Il n'avait aucun moyen d'exécuter.** SAP GUI tourne sous Windows et l'agent n'avait que des doublures (`SapDePapier`). Il ne pouvait ni voir ni lancer le résultat. Il compensait en planifiant, en prouvant et en avouant ce qu'il n'avait pas pu vérifier.
- **La console a été écrite avant le moteur** (lot 14, puis `f08e294`). Il fallait la rebrancher à chaque évolution.

## Pourquoi des milliers de tests

1. Le ratio de 1 ligne de test pour 1 ligne de code est normal. C'est la taille du code (×20) qui était anormale.
2. **31 % des tests sont des gardes ou des refus.** Chaque garde doit avoir un test de déclenchement et un test de non-déclenchement (lot 4, `dc33400`), et la CI vérifie en plus que chaque garde « mord ».
3. **Le même comportement est testé couche par couche.** Le « plafond » est testé 24 fois dans 10 fichiers, la « reprise » 19 fois dans 6 fichiers.
4. **La forme est testée en plus du comportement** : 26 % des tests portent sur des libellés, d'autres sur l'architecture (analyse du code) ou sur la documentation.

## Cause racine

Il n'y avait **pas de boucle de retour réelle**. Pendant 14 jours, l'agent a validé des preuves contre des doublures, dans une seule session très longue qui renforçait son propre style. Une doctrine de rigueur maximale, sans critère d'arrêt ni budget, transformait chaque défaut en chantier.

## Ce qui se récupère

- `couture/sapgui.py` : l'accès COM.
- `trace/vbs.py` : le parseur de trace VBS, testé contre un enregistrement réel.
- L'idée de cl24n : une première passe dictée qui sert de recette.
- La structure du journal et du fichier de KO réinjectable.
- `historique/docs/TRAPS.md` : les pièges SAP réels.
