# Backlog V1 — état des lots

Fichier de pilotage de la boucle de travail. Il est versionné parce qu'un état
gardé en session ne survivrait pas au conteneur : c'est ici, et nulle part
ailleurs, que se lit l'avancement.

Référence : [SPEC_FALCON.md](../SPEC_FALCON.md). Les numéros de section entre
parenthèses y renvoient.

## Protocole d'une itération

1. Lire ce fichier, prendre le **premier lot non fait dont les dépendances sont
   satisfaites**. Un lot par itération, jamais deux à moitié.
2. L'implémenter, avec ses tests.
3. Lancer la vérification. Si elle n'est pas verte : ni commit, ni case cochée.
4. Commiter, pousser sur la branche courante, cocher la ligne ici même dans le
   même commit.

```bash
python outils/verifier.py       # les deux suites, FALCON et l'archive
python outils/neutraliser.py    # chaque garde retirée doit faire tomber la suite
```

La seconde commande existe parce qu'une garde couverte par des tests qui
passent n'est pas une garde vérifiée : le test passerait aussi si la garde ne
faisait rien.

## Garde-fous

- `historique/` n'est jamais modifié.
- **Aucun comportement SAP n'est inventé.** Un lot qui exige une trace réelle
  ou un système réel s'arrête et le dit, plutôt que de deviner. Un mock nourri
  d'hypothèses confirme les hypothèses (§3.7).
- Tout écart de périmètre par rapport à la spec est inscrit au §8 dans le même
  commit que le code qui l'introduit.
- Une pipeline ne peut jamais désactiver une garde (§5.2). Si un lot rend ça
  possible, le lot est faux.

## Lots

Légende : `[ ]` à faire · `[~]` en cours · `[x]` fait · `[!]` bloqué

| # | État | Lot | Dépend de | Critère d'acceptation |
|---|---|---|---|---|
| 0 | `[x]` | Squelette : arborescence, `pyproject.toml`, tests de frontière, CI | — | la vérification est verte sur un dépôt neuf |
| 1 | `[x]` | Modèles et interface de couture, erreurs typées (§3.4) | 0 | surface épinglée à 15 méthodes ; une implémentation partielle ne s'instancie pas ; `Refus` n'hérite pas d'`Echec` |
| 2 | `[x]` | Journal : schéma JSONL, écriture append-only, reprise (§3.3) | 1 | 30 tests sur cinq axes ; un item interrompu **après** sauvegarde sort en `douteux` et n'est jamais rejoué ; reprise refusée sur jeu modifié |
| 3 | `[x]` | Taxonomie : registre YAML, classement, inconnu bloquant (§5.1) | 2 | 30 tests ; `Registre.__init__` n'accepte que `entrees` ; joker et catégorie `inconnue` refusés au chargement ; ambiguïté détectée **au chargement** ; registre livré à 3 entrées, aucune n'inventant de message SAP |
| 4 | `[x]` | Les cinq gardes + dérogations, sur un driver factice (§5) | 1, 3 | 34 tests ; `python outils/neutraliser.py` prouve en CI que chaque garde retirée fait tomber la suite ; `Poste` n'expose que la surface de `Driver` |
| 5 | `[x]` | Rapport de fin + réexport des KO au format d'entrée (§4.7) | 2 | 24 tests ; aller-retour prouvé champ à champ **et** octet pour octet une fois le diagnostic retiré ; dialecte (BOM, délimiteur, fins de ligne, ordre des colonnes) conservé |
| 6 | `[x]` | Parseur de trace VBScript (§4.1) | 0, **traces réelles** | 66 tests ; `megatrace_2026-09.vbs` lue intégralement, zéro ligne non appariée ; aller-retour geste ↔ ligne **et** fichier entier octet pour octet ; `.press()` **refusée** (décision n°13) |
| 7 | `[ ]` | Brouillon de pipeline depuis une trace (§4.3) | 6 | une trace produit un YAML chargeable par le lot 8 |
| 8 | `[x]` | Pipeline : modèle, chargement, validation (§3.2) | 1 | 39 tests ; chaque refus nomme le fichier, le rang et le nom de l'étape ; la frontière pipeline→contrôleur mord en import absolu **et** relatif |
| 9 | `[x]` | Catalogue : modèle, empreinte de variante, dépôt YAML (§3.1) | 1 | 20 tests ; deux rendus du même dynpro donnent deux variantes ; `pour_garde` refuse une esquisse **et** une variante absente ; quarantaine avec promotion explicite |
| 10 | `[ ]` | Moteur itératif + chaîne de pipelines (§3.3) | 2, 4, 8 | un KO au milieu du lot ne l'interrompt pas ; une garde d'identité arrête la chaîne |
| 11 | `[ ]` | Reporting terminal stdlib + ETA glissant (§4.6) | 10 | muet hors terminal, testable sans capture ANSI |
| 12 | `[ ]` | Moteur volumique + primitive d'export `SE16N` (§3.6) | 8, 9 | en-tête de provenance complet ; delta avec l'export précédent |
| 13 | `[ ]` | Implémentation `win32com` de la couture + bundle (§6) | 1 | non testable hors Windows — validation en système réel, marquée comme telle |

## Ce qui bloque, et sur quoi

**Plus rien n'est bloqué.** Le lot 6 l'a été jusqu'à l'arrivée d'un
enregistrement réel : l'archive documentait `.press()`, le recorder écrit
`.press`. Refuser de trancher par hypothèse était le bon choix — la trace a
tranché, et dans l'autre sens que la documentation.

Écart assumé par rapport au critère d'origine, qui demandait de couvrir les
deux formes : `.press()` est **refusée**, pas tolérée (décision n°13). Accepter
une forme que le recorder ne produit pas, ce serait lire sans le savoir un
fichier retouché à la main — et rejouer sur un système réel ce que personne
n'a enregistré.

Ce que la trace a appris, et qui n'était pas déductible :

| | |
|---|---|
| `selectedRows = "0"` est une **chaîne**, `currentCellRow = 4` un **entier** | sur le même shell ALV. Normaliser les deux produit un rejeu que SAP refuse |
| `doubleClickCurrentCell` agit sur la cellule **courante** | omettre `currentCellRow` double-clique la première ligne, sans lever |
| la sélection ALV se fait **par index** | l'index dépend du contenu de la base à l'enregistrement : un brouillon qui le rejoue traite la mauvaise variante, en silence. Le lot 7 doit marquer ces gestes non rejouables |
| vider `ENAME-LOW` **élargit** la recherche de variantes | le premier bloc de la trace ne le fait pas : ses résultats ne sont pas comparables aux quatre autres |
| les cases `DY_*` sont repositionnées **après** le chargement de la variante | le piège des cases rémanentes, observé plutôt que déduit |

Les cinq sont épinglés par des tests dans `tests/test_trace.py`, sur la trace
elle-même — pas sur une reformulation.

**Ce que le parseur ne fera jamais.** Le recorder enregistre des actions : ni
l'identité des écrans traversés, ni les champs présents. Une trace ne peut
donc pas peupler le catalogue — elle produit une *esquisse*, que
`Depot.pour_garde` refuse déjà de servir (lot 9). Le raccordement était prêt
avant le producteur.

Reste demandé, non bloquant ici : la **convention de nommage des variantes**.
Trois ou quatre noms réels suffisent. Ça bloquera la pipeline d'audit.

## Mode dégradé : quand la vérification locale est impossible

Il est arrivé que l'outillage d'exécution du conteneur soit indisponible, donc
que la suite ne puisse pas tourner sur place. La règle dans ce cas :

- pousser quand même — le conteneur est éphémère, et perdre le travail est
  pire que le livrer non vérifié sur une branche de développement ;
- **le dire dans le message de commit**, sans ambiguïté ;
- ne cocher la ligne qu'une fois la CI verte sur le commit poussé, la CI
  lançant la même commande dans un environnement propre ;
- ne jamais présenter une relecture à l'œil comme une vérification.

Ce mode reste l'exception. Enchaîner plusieurs lots à l'aveugle en comptant
sur la CI pour rattraper reviendrait à déplacer la boucle de vérification hors
de portée, ce qui est précisément ce que ce projet cherche à éviter.

## Ce que la revue adversariale a corrigé

Une revue indépendante des lots 2 à 5 a trouvé huit défauts réels, tous de la
classe qui compte ici : **aucun ne lève d'exception**. J'ai reproduit chacun
avant de corriger, et chaque correction porte son test de non-régression.

| # | Défaut | Conséquence en production |
|---|---|---|
| C1 | une sauvegarde réussie suivie d'une garde qui lève ne laissait aucune trace | item classé `en_cours`, donc rejoué : **double écriture** |
| C2 | `Etape.item_id` facultatif — une sauvegarde sans lui n'était comptée pour personne | idem, et l'oubli d'un champ optionnel suffisait |
| C3 | le compte de sauvegardes n'accompagnait pas le fichier de KO | l'humain relançait un item ayant déjà écrit, sans le savoir |
| E1 | une relecture divergente ne faisait **rien** empêcher | on sauvegardait un écran dont le champ critique n'avait pas pris |
| E2 | tout préfixe passait pour une « normalisation » | écrire `1000` et relire `1` était accepté : valeur fausse écrite en silence |
| E4a | deux contextes simultanément vrais n'étaient pas détectés | l'ordre du fichier YAML décidait de la politique appliquée |
| E4b | une surcouche projet pouvait assouplir le registre commun | `session_perdue` rendue bénigne par un fichier, sans motif ni trace |
| M5 | les tests de frontière ignoraient les imports relatifs | `from ..couture.sapgui import …` passait toutes les frontières |
| M6 | colonne dupliquée, ligne trop longue ou trop courte, clé JSONL absente | données corrompues ou perdues à la réinjection, sans erreur |

Trois corrections ont demandé un niveau de plus dans le modèle :

**`ItemAbandonne`**, un `Refus` distinct d'`ArretBloquant`. Il manquait le
moyen d'exprimer « cet item est perdu, le lot continue » — qui est pourtant la
définition même de `connue_fautive`. Sans lui, chaque appelant aurait dû se
souvenir d'inspecter les constats après chaque appel : le « recopié puis
oublié » que la couture existe pour supprimer.

**Les modes de comparaison** passent de `exact`/`tronque_casse` à
`exact`/`casse`/`prefixe`. Le défaut n'accepte plus que la casse et les
espaces ; la troncature doit être déclarée étape par étape. La charge de la
preuve revient à qui sait, pas au défaut.

**L'annonce avant l'acte.** Une sauvegarde est journalisée *avant* d'être
tentée. C'est la seule chose qui survive à une garde qui lève au milieu.

### Deuxième passe : les neuf constats restants

Les quatre moyens et les cinq mineurs de la même revue, fermés dans un second
temps. Le séquencement n'était pas libre : `Contrat` devait être refermé
**avant** le lot 8, qui mappe du YAML de pipeline sur cet objet.

| # | Défaut | Conséquence |
|---|---|---|
| M1 | `Contrat` offrait trois neutralisations sans trace, dont une **par défaut** | une étape distraite désarmait la garde qui attrape le plus de dérives |
| M2 | la garde de reprise était optionnelle par défaut | `preparer(chemin, items)` ne vérifiait rien et ne levait rien |
| M3 | `write`, `set_checked`, `table_scroll` ne relevaient ni fenêtre ni statut | un popup surgi là était attribué à la mauvaise étape |
| M4 | déclarer `statut_attendu` tuait la liste blanche de messages | renforcer une étape produisait son affaiblissement |
| m1 | `Reprise.deja_faits` mélangeait deux périmètres | compteur pouvant dépasser le nombre d'items à traiter |
| m2 | rapport : première ouverture, dernière clôture | provenance d'un run, durée d'un autre |
| m3 | `Derogation.portee` déclarée et jamais lue | une dérogation d'étape valait pour tout le contrat |
| m4 | deux dumps de la même milliseconde s'écrasaient | un incident qu'on ne pourra jamais classer |
| m5 | plafond en sauvegardes là où la spec dit items | écart non inscrit — décision n°11 |

Le principe retenu pour M1 est celui de tout le dispositif : **les trois
relâchements restent possibles, mais deviennent des décisions au lieu de
s'obtenir par omission**, et les trois laissent une trace posée une fois par
étape. C'est la différence entre une décision et un oubli.

## Questions ouvertes qui toucheront un lot

Reprises du §8 de la spec, avec le lot qu'elles concernent :

| Question | Lot | Défaut retenu à défaut d'arbitrage |
|---|---|---|
| définition de « champ critique » pour la garde 4 | 4 | relecture de **tout** champ écrit, exclusion nommée et motivée |
| convention de conservation des exports | 12 | un dossier par système, fichier horodaté, delta contre le plus récent |
| unité de travail du cas 1 : six pipelines ou item composite | 10 | à trancher avant le lot 10, la frontière transactionnelle en dépend |
| ~~format d'entrée des constats~~ | 5 | **tranché** : CSV et JSONL acceptés en entrée, le dialecte lu est celui réécrit |

## Ce que la revue de conception a changé

Une revue indépendante de l'architecture a produit cinq corrections que
j'intègre. Elles ne sont pas cosmétiques.

**1. La couture du §3.4 était trop étroite pour le cas 1 lui-même.** Elle
n'offrait ni `select`, ni accès ALV, ni accès table control — alors que
l'audit du cas 1 lit une grille ALV, et que le corollaire du piège des cases
rémanentes impose de positionner explicitement les trois cases de IA08 à
chaque appel. Les huit méthodes ne suffisaient donc pas à exprimer la première
pipeline livrée. **Tranché : décision n°9, couture élargie à 15 méthodes**,
figée au lot 1.

**2. L'identité d'un item ne peut pas être l'index de ligne.** Le §4.7 exige
que le fichier de KO soit réinjectable ; réinjecté, il n'a plus les mêmes
index. Toute pipeline itérative devra donc déclarer ses colonnes de clé, et
l'identifiant d'item sera l'empreinte de ces colonnes. C'est aussi ce qui rend
opérante l'unité d'itération du §3.3 : regrouper trois cents caractéristiques
en quarante classes devient une déclaration de clé, pas une gymnastique dans
la boucle.

**3. Un item interrompu après sa sauvegarde n'est pas rejouable.** Rejouer
aveuglément, c'est la double écriture. D'où un état `douteux` distinct de
`en_cours`, versé au fichier à arbitrer plutôt qu'au flux de reprise.

**4. Le réexport des KO tient par une convention de préfixe.** Les colonnes de
diagnostic ajoutées sont préfixées `falcon_`, et la lecture les retire. Le
fichier est ainsi enrichi pour l'humain *et* réinjectable sans retouche — les
deux exigences du §4.7 en même temps.

**5. Les douze pièges n'amorcent pas douze entrées de taxonomie.** La plupart
ne sont pas des messages SAP : le piège 4 est une règle de résolution, le 5
est la garde 1 elle-même, les 6 et 7 sont des méthodes de couture, et les 1,
2, 10, 11, 12 sont des étapes échappatoires. Le registre s'amorce à trois ou
quatre entrées. Prétendre l'amorcer à douze serait exactement la
spécification anticipée que le §5.1 proscrit.
