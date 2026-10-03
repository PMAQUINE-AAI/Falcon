# AGENTS.md — règles pour tout agent (Claude, GPT/Codex)

FALCON rejoue des traces VBS de SAP GUI sur les lignes d'un CSV, depuis Windows. Utilisateur unique, SAP sandbox.
Architecture et budgets : `ARCHITECTURE.md`. Pièges SAP connus : `docs/TRAPS.md`. Pourquoi ces règles : `docs/DIAGNOSTIC.md`.

## 1. Agir d'abord
- On te demande de lancer, d'afficher ou de corriger : tu le fais tout de suite, puis tu commentes. Pas de plan, de sonde ni d'audit préalable.
- Doute mineur : choisis l'option la plus simple et note-la en une ligne dans ton compte rendu. Ne t'arrête que si l'action peut détruire des données.

## 2. Pas de simulation de SAP
- Il n'existe ni faux SAP, ni double, ni mock de session COM, et tu n'en crées pas.
- Tout comportement SAP affirmé doit venir d'un **rapport d'exécution réel** (`rapports/*.zip`) ou de `docs/TRAPS.md`. Sinon, écris « non vérifié sur SAP » et demande une exécution à Philippe.
- Le code qui touche SAP (`falcon/sap.py`) n'a pas de tests unitaires. Il se valide en exécution réelle, en lisant le rapport.

## 3. Périmètre d'un correctif
- Un bug, un module. Le diff le plus petit qui corrige le cas observé.
- Interdit dans un correctif : généraliser à « la classe de défauts », ajouter une garde ou une couche de validation, renommer, déplacer, reformuler la doc, toucher un autre module.
- Si le correctif exige vraiment plus d'un module : arrête-toi et explique pourquoi en 3 lignes, avant d'écrire.
- Tu vois autre chose en passant : note-le dans « À signaler », ne le corrige pas.

## 4. Tests
- Tu ne testes que la logique pure (`trace`, `recipe`, `journal`, `report`) : entrée, puis sortie attendue.
- Ne fige jamais un libellé, un message ou un affichage. Pas de test sur l'architecture, la doc ou le code source.
- Un correctif ajoute au plus 1 test, celui qui reproduit le bug.
- Budget : lignes de tests ≤ lignes de code du module testé.
- Commande : `python -m pytest -q`.

## 5. Code
- Un fichier par responsabilité, 300 lignes maximum. Respecte le sens des dépendances de `ARCHITECTURE.md`.
- Commentaires rares et courts : le *pourquoi* non évident, jamais l'historique (« décision n°X », « lot Y », « avant on faisait… »).
- Pas de nouvelle dépendance sans accord.
- Les erreurs remontent avec leur contexte vers le rapport d'exécution. On ne les avale pas, et on ne crée pas de hiérarchie d'exceptions maison.

## 6. Compte rendu et commits
- Compte rendu : 5 lignes maximum (ce qui a changé, fichiers touchés, commande de vérification et son résultat, À signaler).
- Commit : un sujet court à l'impératif, et 3 lignes de corps maximum. Pas de récit.
- Ne modifie pas `AGENTS.md`, `ARCHITECTURE.md` ni `docs/` sauf si la tâche le demande explicitement.
