# FALCON — Spécification fonctionnelle

Framework d'automatisation SAP Front End (SAP GUI Scripting).

---

## 1. Objet

FALCON exécute des séquences d'actions dans SAP GUI à la place d'un utilisateur, de façon répétable et surveillée.

Deux usages cibles :

1. **Corrections de masse** que LSMW ne couvre pas et que LTMC ne couvre pas encore — quelques centaines à quelques milliers d'objets, sans passer par un ticket dev.
2. **Extractions de données** vers un format pivot (JSONL/CSV) exploitable par un programme tiers pour croisement et analyse.

Dans la pratique ces deux usages n'en font qu'un. La forme canonique d'un travail FALCON est une **paire** :

```
passe d'audit  →  fichier de constats (relisible, éditable)  →  passe de remédiation
```

L'humain valide le fichier intermédiaire avant toute écriture. C'est à la fois le contrat entre les deux passes, la trace d'audit, et la garde de sécurité la plus efficace du dispositif. Ce motif a déjà été validé sur EagleLoader (extraction anglaise → JSONL → injection espagnole) et couvre tous les cas d'usage identifiés au §7.

**Non-objectifs.** FALCON ne remplace pas un développement ABAP, ne gère pas les traitements de fond, et ne supprime pas l'expertise métier : il supprime la replomberie technique entre deux automatisations.

---

## 2. Justification

**Outil personnel.** Utilisateur unique, pas de contrainte d'ergonomie pour un tiers.

Le comparatif avec Power Automate Desktop a déjà été tranché sur le terrain : le PMV développé pour les gammes s'est révélé nettement plus praticable. S'y ajoutent un coût de licence nul, aucune validation IT (un script Python pilote la session SAP de l'utilisateur sous ses propres autorisations), et une portabilité totale.

---

## 3. Architecture

Quatre couches, indépendantes :

| Couche | Rôle | Persistance |
|---|---|---|
| **Catalogue** | Cartographie des écrans SAP rencontrés | YAML versionné |
| **Pipeline** | Définition déclarative d'une automatisation | Fichier YAML versionnable |
| **Moteur** | Exécute une pipeline contre une session SAP | — |
| **Journal** | Trace d'exécution, reprise, métriques | JSONL append-only |

Le découplage catalogue / pipeline est le point clé : le catalogue est un actif réutilisable qui grossit à chaque projet, la pipeline est jetable.

### 3.1 Catalogue d'écrans

Un écran est identifié par le triplet **`transaction / program / screenNumber`** (`session.info.*`), pas par son titre ni sa position dans une trace.

Pour chaque écran, FALCON stocke l'arbre des objets obtenu par parcours récursif depuis `wnd[0]` : `id`, `type`, `name`, `text`, `changeable`, `tooltip`.

**Variantes.** Un même dynpro ne rend pas toujours les mêmes champs (onglets, layouts ALV, contrôles tableaux, paramètres utilisateur). Le catalogue stocke donc des *variantes* d'écran, clé = triplet + empreinte de l'ensemble des `id` présents. Ne pas traiter cette variabilité est la première cause d'échec d'un framework de ce type.

### 3.2 Définition de pipeline

Une pipeline est un fichier YAML : une liste d'étapes, chacune référençant un écran attendu, une action (`set`, `press`, `select`, `read`), une cible (`id` de champ) et une source de données (colonne d'entrée, constante, valeur lue précédemment).

**Échappatoire obligatoire.** Une étape peut être un appel Python arbitraire. Toutes les manipulations SAP ne sont pas exprimables en séquence déclarative — cf. `PLPO-TXTSP` sur EagleLoader, où la langue de lecture du texte long impose « supprimer / sauver / rouvrir / écrire / sauver ». Une pipeline purement déclarative ne peut pas découvrir cette contrainte ; l'utilisateur doit pouvoir la coder.

### 3.3 Moteur

Entrée : une pipeline + un fichier de données (une ligne = une itération). Sortie : un journal + éventuellement un fichier d'extraction.

Modes : `dry-run` (s'arrête avant toute validation), `run`, `resume` (reprend au premier item non terminé du journal).

**Chaîne de pipelines.** Le moteur accepte une liste ordonnée de pipelines et les exécute à la suite dans une même session, avec un retour à l'écran d'accueil entre chacune. Périmètre volontairement fermé :

- journal, rapport et fichier de KO **par pipeline**, jamais fusionnés ;
- reprise au niveau de la pipeline, la reprise fine restant interne à chacune ;
- un arrêt bloquant (garde d'identité violée) interrompt toute la chaîne, un item KO ne l'interrompt pas ;
- **aucun passage de données entre pipelines.**

Ce dernier point est la limite qui empêche la chaîne de devenir un orchestrateur. Si une pipeline a besoin de la sortie d'une autre, ce n'est pas une chaîne : c'est un item composite (§7), et il se traite dans une pipeline unique.

**Liaison de session.** Le système et le mandant cibles sont un paramètre de passe, jamais une constante du code. Une paire audit/remédiation peut traverser deux systèmes (comparaison inter-système) ou deux sessions de langues différentes dans le même système.

**Unité d'itération.** L'item du journal est l'**unité de sauvegarde SAP**, pas l'unité de constat. Trois cents caractéristiques fautives réparties sur quarante classes font quarante items, pas trois cents : `CL02` traite toutes les caractéristiques d'une classe dans un même écran et une seule validation. La règle vaut partout — regrouper les constats par objet sauvegardable avant d'exécuter divise le volume, et fait coïncider la granularité de reprise avec la frontière transactionnelle réelle (une sauvegarde passe ou échoue en entier, jamais à moitié).

### 3.4 Couture de driver

Tous les appels COM (`win32com`) vers SAP GUI sont confinés dans un module unique exposant une interface étroite. Rien d'autre dans FALCON ne connaît SAP.

| Méthode | Rôle |
|---|---|
| `screen()` | identité courante : transaction / programme / dynpro |
| `fields()` | arbre des objets de l'écran courant |
| `read(id)` | valeur d'un champ |
| `write(id, valeur)` | saisie |
| `press(id)` / `vkey(n)` | action |
| `status()` | type, id et numéro du message de la barre de statut |
| `windows()` | fenêtres ouvertes |
| `select(id)` / `set_checked(id, bool)` | sélection, case à cocher |
| `grid_*` | ALV : nombre de lignes, lecture par index **absolu**, colonnes |
| `table_*` | table control : hauteur visible, défilement — index **visible** |

Les huit premières ne suffisent pas au cas 1 lui-même : son audit lit une
grille ALV, et le corollaire du §9 des pièges de terrain impose de positionner
explicitement trois cases à chaque appel de IA08. Les deux familles de tableau
portent des noms distincts parce que les confondre est un piège documenté :
l'ALV s'indexe en absolu sans défilement, le table control en index visible
avec défilement explicite.

Trois bénéfices, dont un seul concerne les tests :

1. **Les gardes du §5 s'implémentent ici, une fois.** Vérification d'identité d'écran avant action, relecture après écriture, lecture du statut après validation, détection de fenêtre imprévue : centralisées dans la couture, elles s'appliquent à toutes les pipelines sans que celles-ci aient à y penser. Dispersées, elles seraient recopiées et oubliées.
2. **Les erreurs COM se traitent au même endroit** — session perdue, objet introuvable, timeout — au lieu d'être rattrapées au petit bonheur.
3. **Le harness (§3.7) devient une seconde implémentation de cette interface**, sans rien changer au reste.

### 3.5 Deux classes de pipeline

Ne pas les confondre — c'est le principal risque de sur-abstraction ici.

| | **Itérative** | **Volumique** |
|---|---|---|
| Forme | une itération par objet | une navigation, un export |
| Exemples | correction de variante, injection de texte traduit | dump SE16N d'une table, extraction de classes |
| Gardes | toutes (§5) | identité d'écran + barre de statut |
| Journal | par item, reprise fine | par exécution |
| Coût de développement | élevé | faible |

Les passes d'audit sont presque toujours volumiques, les passes de remédiation presque toujours itératives. La machinerie lourde — journal par item, reprise, ETA glissant — ne sert qu'aux secondes. Une pipeline volumique qui hérite de tout l'appareillage itératif est du gaspillage.

### 3.6 Primitive d'export de table

Les pipelines volumiques se ramènent presque toutes à une boucle sur des triplets `(système, table, critères de sélection)` suivie d'un téléchargement. FALCON expose donc l'export de table comme **primitive de premier niveau**, pas comme une pipeline générique à recartographier à chaque fois : ni catalogue d'écrans, ni trace enregistrée, ni gardes complètes ne sont nécessaires ici.

**Provenance obligatoire.** Chaque export porte un en-tête : système, mandant, table, critères appliqués, horodatage, utilisateur. Sans ça, le rapprochement inter-système en aval devient invérifiable — on ne sait plus ce qu'on compare à quoi. C'est le contrat minimal vis-à-vis du programme d'analyse tiers.

**Comparaison au dernier export.** Certains audits sont récurrents plutôt que ponctuels (cas 2 : détection d'écrasements introduits au fil de l'eau). Les exports sont donc conservés, et l'audit produit un delta par rapport au précédent en plus de l'état complet. Aucune planification automatique : l'exécution reste déclenchée à la main.

---

### 3.7 Stratégie de test

Le harness de test rejoue le **catalogue** au lieu de piloter une session SAP réelle : il expose la même surface COM que SAP GUI Scripting (`findById`, `session.info`, `sbar`, `wnd[]`) mais sert les écrans capturés au §3.1. Il n'implémente que la surface effectivement utilisée par FALCON, rien de plus.

**Condition de faisabilité : la couture.** Tout accès à SAP passe par une interface unique et étroite — une poignée de méthodes — jamais par des appels `win32com` dispersés dans le code. Le harness est alors une seconde implémentation de cette même interface. Sans cette couture, écrire le harness devient effectivement pénible ; avec elle, c'est quelques centaines de lignes. La couture est de toute façon nécessaire au moteur, harness ou pas.

**Le harness est un magnétophone, pas un émulateur.** Il ne simule aucune logique serveur : il rejoue une séquence enregistrée. Le catalogue stocke des écrans, une *traversée* enregistrée stocke leur ordre pour un item donné. Le harness sert l'écran courant et avance quand FALCON envoie l'action attendue. Si FALCON fait autre chose, il lève une erreur « hors piste » — ce qui est exactement le comportement voulu, puisque c'est le même modèle que les gardes du §5.

Les scénarios d'échec s'obtiennent en éditant une traversée réelle : y insérer un popup capturé, changer le type de message de la barre de statut, tronquer la séquence. Le matériau reste une capture, pas une invention.

Ce que ça valide : le moteur — boucle, journal, reprise, gardes, ETA, regroupement par unité de sauvegarde — soit la majorité du code, qui n'a rien de spécifiquement SAP. Et surtout les chemins d'échec, impossibles à provoquer à la demande en système réel : popup imprévu, message de type `E`, champ qui n'accepte pas la valeur, session perdue en cours de lot.

Ce que ça ne valide **pas** : qu'une pipeline fonctionne. Un mock nourri par des hypothèses confirme les hypothèses. La fidélité du harness est donc bornée par des captures réelles, jamais par des fixtures écrites à la main — c'est la différence avec un simulateur artisanal.

**Règle.** Toute pipeline exige une validation en système réel sur un échantillon avant tout passage à l'échelle. Le harness ne dispense jamais de ce passage.

**Séquencement.** La couture est en V1 : elle est irréversible au sens où la rétrofiter sur du code déjà écrit coûte cher. Le harness lui-même peut attendre le premier chemin d'échec réellement rencontré — inutile de l'écrire avant d'avoir quelque chose à y rejouer.

---

## 4. Cycle de vie d'une pipeline

1. **Enregistrement.** L'utilisateur produit une trace avec l'enregistreur natif SAP GUI (sortie VBScript). FALCON parse les lignes `findById` pour en extraire la séquence d'actions.
2. **Cartographie.** FALCON rejoue la trace en mode observation, dumpe chaque écran traversé et alimente le catalogue.
3. **Mapping.** L'utilisateur associe champs et données, ordonne les actions, définit les boucles — édition directe du YAML, assistée par le catalogue (autocomplétion des `id` disponibles sur l'écran attendu).
4. **Sécurisation.** L'utilisateur ajoute les gardes (§5) — certaines sont générées par défaut.
5. **Exécution.** Unitaire ou par lot de pipelines enchaînées.
6. **Supervision.** Reporting terminal temps réel (Rich) : item courant, compteurs OK/KO, durée moyenne par itération, ETA en moyenne glissante, mémorisé entre exécutions.
7. **Clôture.** Le rapport de fin liste les items KO avec leur catégorie d'erreur (§5.1) et — exigence principale — **les réexporte au format d'entrée**, directement réinjectable dans une exécution corrective. Un rapport qu'il faut retravailler à la main avant de relancer annule le bénéfice de l'automatisation sur les cas difficiles, qui sont précisément ceux qui coûtent.

---

## 5. Modèle de sécurité

> Réponse à la question ouverte du brouillon : « comment repérer quelque chose de traduisible en algo ? »

Cinq gardes, toutes mécaniques, toutes vérifiables sans compréhension métier :

1. **Identité d'écran.** Avant chaque action, `program`/`screenNumber` doit correspondre à l'écran attendu. Sinon : arrêt. Cette seule garde attrape la majorité des dérives (popup imprévu, transaction refusée, autorisation manquante, données inattendues).
2. **Barre de statut.** Après chaque validation, lecture de `sbar.messageType` (`S`/`W`/`I`/`E`/`A`). `E` et `A` → échec de l'item. `messageId` + `messageNumber` permettent une liste blanche de messages bénins connus.
3. **Fenêtres inattendues.** Toute `wnd[1]` non prévue par l'étape → arrêt, avec dump de la fenêtre pour enrichir le catalogue.
4. **Relecture.** Après écriture d'un champ critique, relecture de la valeur avant validation. Écrire sans que ça prenne est une classe de bug déjà rencontrée.
5. **Rayon d'action.** Plafond d'items par exécution, obligatoire. `dry-run` obligatoire avant tout premier passage en production.

Un item en échec n'interrompt pas le lot par défaut : il est marqué dans le journal et l'exécution continue. Une garde d'identité d'écran violée, elle, interrompt tout — c'est le signe que le modèle du monde est faux.

### 5.1 Taxonomie d'erreurs

Les gardes détectent que quelque chose a mal tourné ; la taxonomie dit quoi en faire. Trois catégories seulement :

| Catégorie | Traitement |
|---|---|
| **Connue bénigne** | message attendu, sans conséquence — on poursuit, on note |
| **Connue fautive** | cause identifiée, politique définie — item marqué KO, boucle poursuivie |
| **Inconnue** | arrêt, dump complet de l'écran et du contexte, capture ajoutée au catalogue |

L'**inconnu est un résultat de première classe**, pas un `except` fourre-tout. Toute erreur non classée est bloquante par défaut ; elle ne devient non bloquante que le jour où elle est décrite explicitement.

La taxonomie se **récolte, elle ne se spécifie pas**. Les douze pièges de terrain d'EagleLoader n'ont pas été prévus, ils ont été rencontrés. Chacun devient ici une entrée nommée avec sa politique. Prétendre écrire un traitement d'erreur exhaustif avant la première exécution reviendrait à prétendre connaître d'avance des comportements que seul le système réel révèle.

### 5.2 Séparation pipeline / contrôleur

La pipeline **déclare** une intention ; le contrôleur **applique** les règles. Conséquence directe : une pipeline ne peut pas désactiver une garde. Une dérogation est possible mais doit être nommée, motivée dans le YAML, et tracée dans le journal à chaque exécution. Sans cette asymétrie, la première pipeline pressée contournera le dispositif et l'ensemble ne vaudra plus rien.

---

## 6. Périmètre

**V1**
Catalogue (YAML versionné), primitive d'export via `SE16N`, pipelines YAML, moteur derrière une couture de driver unique, chaîne de pipelines bornée, **les cinq gardes du §5**, journal + reprise, reporting terminal.

**Première pipeline livrée : cas 1** (variantes d'affichage, BCP). Priorité imposée par la charge en cours.

**Découpage obligatoire du cas 1.** Une seule transaction traitée de bout en bout — audit, remédiation, validation sur un site — avant d'en cartographier une deuxième. Les six transactions ne se cartographient pas en amont : ce serait cinq sixièmes du travail engagés avant la première preuve que le dispositif fonctionne.

**V2**
Harness de rejeu (§3.7), parseur de trace VBScript (supprime l'écriture manuelle de la première ébauche de pipeline), historisation des durées.

**Packaging.** Le dépôt est modulaire, la livraison est un fichier unique exécutable (bundle). La contrainte d'autonomie au déploiement qui avait conduit EagleLoader à un fichier de 4500 lignes reste valable, mais elle se traite à la construction, pas dans l'organisation du code source.

**Hors périmètre**
Interface graphique. Ordonnancement autonome, exécution sans session utilisateur, multi-poste, tout ce qui touche au batch SAP.

---

## 7. Cas d'usage identifiés

| # | Cas | Audit | Remédiation | Volume |
|---|---|---|---|---|
| 1 | Variantes d'affichage de 6 transactions à remettre à la norme client (Business Continuity Protocol, requêtes de sauvegarde) | volumique | itérative | ~8 variantes × 50+ sites × 6 transactions |
| 2 | Caractéristiques assignées aux classes en écrasement par erreur | volumique | itérative (`CL02`) | à mesurer |
| 3 | Comparaison classes/caractéristiques inter-système pour anticiper les écarts avec la prod | volumique (multi-tables, multi-systèmes) | néant — sortie vers programme d'analyse tiers | à mesurer |
| 4 | Chargement de textes de description dans d'autres langues | volumique | itérative | variable |

Le cas 1 seul justifie l'investissement : le volume interdit le traitement manuel et LSMW ne le couvre pas. Le cas 4 est la généralisation directe d'EagleLoader.

**Actif produit par le cas 1.** Le traitement des six transactions cartographie au passage les écrans de sélection et de liste d'objets techniques. Ces écrans reviennent dans la plupart des automatisations futures : c'est la partie du catalogue à la plus longue durée de vie, et une raison supplémentaire de commencer par là.

**Unité de travail à déterminer.** Six transactions × un site : s'agit-il de six pipelines indépendantes exécutées l'une après l'autre, ou d'un seul item composite par site ? La question n'est pas cosmétique. S'il existe une dépendance — une transaction dont la remédiation conditionne la suivante sur le même site — alors ce n'est pas du chaînage mais un item composite, avec une frontière transactionnelle et une reprise différentes (§3.3). S'il n'y a aucune dépendance, ce sont six pipelines indépendantes que le moteur enchaîne — le chaînage est en V1 (décision n°6) et se réduit alors à un déclenchement successif, sans passage de données. La question de l'unité de travail reste entière : elle porte sur la frontière transactionnelle et la granularité de reprise, pas sur la disponibilité du chaînage.

Le cas 2 a une remédiation simple à l'unité — le retrait de l'écrasement passe par `CL02` — mais le volume la rend impraticable à la main : trois cents caractéristiques fautives sont hors de portée d'un traitement manuel. Il relève donc pleinement du moteur itératif, avec regroupement préalable des constats par classe (§3.3, unité d'itération).

Le cas 3 ne produit pas de remédiation : FALCON automatise l'extraction, un programme tiers rapproche les tables entre elles pour rendre la classification lisible. Les données brutes ne sont pas exploitables telles quelles. Ce cas relève entièrement de la primitive d'export (§3.6) et fixe son exigence de provenance.

---

## 8. Décisions arrêtées

| # | Question | Décision |
|---|---|---|
| 1 | Format du catalogue | **YAML versionné** — diffable et relisible |
| 2 | Socle EagleLoader | **Réutilisé**, sous contrôle strict de la doc de handoff existante |
| 3 | Harness de test | **Rejeu du catalogue** (§3.7), pas un simulateur écrit à la main |
| 4 | Canal d'export | **`SE16N`** — disponibilité et autorisation confirmées sur les systèmes visés |
| 5 | Déclencheur de la V1 | Cas 1 (BCP), priorité de la charge en cours. Le cas 2 reste un besoin récurrent, traité ensuite |
| 6 | Chaînage de pipelines | **V1** — le chaînage n'est qu'un déclenchement successif de pipelines ; le périmètre fermé du §3.3 (aucun passage de données) le rend peu coûteux |
| 7 | Garde 4, relecture après écriture | **V1** — implémentée dans la couture avec les quatre autres, plutôt que rétrofitée |
| 8 | Parseur de trace VBScript | **V1** — avancé depuis la V2 : il alimente le brouillon de pipeline du §4.3, et ne dépend d'aucune autre brique |
| 9 | Étendue de la couture | **Élargie** au-delà des huit méthodes du §3.4 : `select`, case à cocher, accès ALV et accès table control. La couture étant irréversible, l'étendre après coup coûterait la rétrofit que le §3.4 dit vouloir éviter — et, entretemps, quelqu'un contournerait en appelant COM ailleurs |

**Reste ouvert :**

- périmètre exact du cas 1 — quelle transaction traitée en premier, et quelle est la norme client de référence pour les variantes (existe-t-elle sous forme exploitable, ou faut-il la reconstituer ?) ;
- unité de travail du cas 1 — six pipelines enchaînées ou un item composite par site (§7), question de frontière transactionnelle et non de chaînage ;
- définition de « champ critique » pour la garde 4, maintenant qu'elle est en V1 : relecture de tout champ écrit par défaut, ou champs désignés étape par étape dans le YAML ;
- convention de conservation des exports, que la comparaison au dernier export (§3.6) suppose sans la fixer.
