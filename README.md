# FALCON

Framework d'automatisation SAP Front End (SAP GUI Scripting).

FALCON exécute des séquences d'actions dans SAP GUI à la place d'un
utilisateur, de façon répétable et surveillée : corrections de masse que LSMW
ne couvre pas, et extractions vers un format pivot exploitable par un
programme tiers.

La forme canonique d'un travail FALCON est une **paire** :

```
passe d'audit  →  fichier de constats (relisible, éditable)  →  passe de remédiation
```

L'humain valide le fichier intermédiaire avant toute écriture. C'est à la fois
le contrat entre les deux passes, la trace d'audit, et la garde de sécurité la
plus efficace du dispositif.

**Pour commencer :** [docs/DEMARRAGE.md](docs/DEMARRAGE.md) mène de
l'installation à la première exécution sur un poste Windows, et dit à chaque
étape ce qui peut échouer et pourquoi. [exemple/](exemple/) est un automatisme
complet qu'on copie, et qui se rejoue ici sans SAP :

```bash
python exemple/rejouer.py
```

## La référence

**[SPEC_FALCON.md](SPEC_FALCON.md)** — spécification fonctionnelle complète :
architecture en quatre couches, modèle de sécurité, périmètre V1/V2, cas
d'usage et décisions arrêtées. C'est le document qui fait foi ; tout ce qui
suit n'en est qu'un index.

| Section | Sujet |
|---|---|
| §3.1 | catalogue d'écrans, et ses **variantes** — première cause d'échec d'un framework de ce type |
| §3.3 | moteur : modes, chaîne de pipelines, unité d'itération = unité de sauvegarde SAP |
| §3.4 | **couture de driver** — le seul module qui connaît SAP |
| §3.5 | pipelines itératives vs volumiques : ne pas les confondre |
| §3.7 | harness = rejeu du catalogue, magnétophone et non émulateur |
| §5 | les cinq gardes, et la taxonomie d'erreurs qui se récolte |
| §6 | périmètre V1 / V2 |

## État

L'état vivant des lots est dans [docs/BACKLOG_V1.md](docs/BACKLOG_V1.md), et
nulle part ailleurs. Ce README dit ce que FALCON *est* ; le backlog dit où il
en est. Dupliquer l'avancement ici garantirait qu'une des deux versions soit
fausse — ça a déjà été le cas.

Les modules livrés :

| Module | Rôle |
|---|---|
| `falcon/noyau/` | types de la couture, hiérarchie d'erreurs, vocabulaire des gardes, **dialecte YAML strict** |
| `falcon/couture/` | l'interface étroite par laquelle tout FALCON parle à SAP |
| `falcon/controleur/` | les cinq gardes, les contrats d'étape, les dérogations, la lecture d'une grille ALV |
| `falcon/journal/` | JSONL append-only, repli des états, reprise, rapport |
| `falcon/taxonomie/` | registre des erreurs connues, classement, dump d'inconnu |
| `falcon/donnees/` | lecture des jeux, regroupement par unité de sauvegarde, réexport des KO |
| `falcon/pipeline/` | modèle déclaratif, chargeur strict, échappatoire Python |
| `falcon/moteur/` | la boucle itérative, la chaîne de pipelines, la reprise, l'extraction d'une grille vers un CSV |
| `falcon/supervision/` | progression et ETA glissant, muets hors terminal |
| `falcon/volumique/` | export de table, provenance obligatoire, delta contre le précédent |
| `falcon/catalogue/` | écrans, variantes, dépôt YAML, quarantaine |
| `falcon/trace/` | lecture des enregistrements du SAP GUI Recorder, couverture, esquisses d'écran, brouillon de pipeline |
| `falcon/exploration/` | cartographie (§4.3, étape 2) : traduction d'un geste de trace en appel de couture, rejeu en observation sous dry-run, relevé de chaque écran traversé, compte rendu |
| `falcon/tableur/` | les trois CSV du classeur → une pipeline YAML, relue avant d'être écrite |
| `falcon/commandes/` | ligne de commande : `console`, `explorer`, `diagnostiquer`, `inventaire`, `brouillon`, `dictionnaire`, `composer`, `recolter`, `sonde` — seule `console` peut **écrire** dans SAP, et `explorer` y **agit** sans y écrire |
| `falcon/console/` | menus interactifs : tests, traces, pipelines et jeux de données, **exécution**, journaux, catalogue, exports de table, taxonomie, diagnostic |
| `falcon/toile/` | ce que le terminal sait faire, **mesuré** et jamais supposé : taille de fenêtre, bit VT relu, et le seul module du dépôt où une séquence ANSI s'écrit |

**Ce que le vert des tests ne prouve pas.** Aucune ligne de ce dépôt n'a
encore parlé à un système SAP. `falcon/couture/sapgui.py` existe désormais,
mais ni la suite locale ni la CI ne peuvent l'exécuter : elles tournent sur
Linux, sans SAP GUI ni pywin32. Sa conformité réelle est marquée `skip` avec
un motif lisible, et `python outils/verifier.py` liste en fin de course tout
ce qui n'a **pas** été vérifié — un test qui ne s'exécute pas doit le dire. Les tests établissent que FALCON se comporte
correctement *étant donné* une réponse de driver — pas que SAP réponde ainsi.
Le double de test le dit lui-même dans sa docstring, et la spec le dit au
§3.7 : un mock nourri d'hypothèses confirme les hypothèses. La validation en
système réel reste entière.

## Développement

État des lots et protocole de travail : [docs/BACKLOG_V1.md](docs/BACKLOG_V1.md).

```bash
python outils/verifier.py
```

Tout depuis un seul endroit :

```bash
python -m falcon console
```

Sept branches : vérification et livraison, traces du recorder, pipelines et
données, journaux, catalogue d'écrans, exports de table, session SAP. Pas de
`curses` et pas de dépendance : `curses` n'est pas fourni avec CPython sous
Windows, or c'est la seule machine où SAP GUI existe. Le décor s'encode en
cp1252, ce qu'écrit une console Windows française redirigée.

**C'est aussi d'ici qu'on exécute.** Une exécution réelle écrit dans un ERP :
elle est donc précédée d'un récapitulatif — pipeline et jeu avec leurs
empreintes, mode, **les deux plafonds**, nombre d'items, et chaque dérogation
avec son motif — puis d'une confirmation **en toutes lettres**. Le mot attendu
est le nom de la pipeline : on ne peut pas le taper sans avoir lu le
récapitulatif qui le nomme. Pas de `o/n`, qui se tape sans lire.

**La répétition à blanc n'est pas une suggestion : c'est une garde.** La
spécification en fait la seconde moitié du rayon d'action (§5.5), et le code
n'en faisait qu'un ordre de menu — « Répétition à blanc » au-dessus
d'« Exécuter », et c'était tout. Un ordre de menu n'arrête personne. Un `run`
refuse désormais si aucune répétition n'a **abouti** sur **ces empreintes**,
dans ce journal.

Conséquence à assumer : l'empreinte porte sur le *texte* de la pipeline, donc
corriger une virgule en exige une nouvelle. C'est le prix d'une garde qui
porte sur ce qui sera réellement exécuté, et non sur un fichier qui portait le
même nom hier. Une répétition **interrompue** ne compte pas — elle prouve
justement que quelque chose n'allait pas ; une répétition arrêtée au plafond
compte, sans quoi la garde serait impossible à satisfaire dans le cas même où
les plafonds servent.

On peut passer outre, et il faut alors dire pourquoi : le motif part dans
l'ouverture du journal, à côté des dérogations. Un contournement qui ne laisse
pas de trace n'est pas un contournement, c'est un trou.

Les mêmes choses en scriptable, hors terminal :

```bash
python -m falcon inventaire tests/fixtures/traces/megatrace_2026-09.vbs
python -m falcon brouillon tests/fixtures/traces/megatrace_2026-09.vbs
python -m falcon diagnostiquer --catalogue <dossier-du-catalogue>
python -m falcon dictionnaire <dossier-du-catalogue> -o dictionnaire.csv
python -m falcon explorer trace.vbs --catalogue <dossier-du-catalogue> \
    --plafond-gestes 200 --plafond-ecrans 50
python -m falcon sonde
```

`sonde` est la première chose à lancer sur une machine neuve, et celle qu'on
demande par téléphone quand un affichage est illisible. Elle interroge — dans
ce processus-ci, sur ces flux-là — la taille de la fenêtre et la capacité à
interpréter les séquences ANSI, et **chaque ligne porte sa provenance** :

- **`mesure`** — un appel système a répondu. Sur Windows, le bit VT est posé,
  **relu**, puis restauré : c'est cette relecture qui transforme une lecture de
  documentation en mesure. `os.get_terminal_size` et `isatty()` en sont aussi.
- **`declare`** — une variable de l'hôte l'affirme, et rien ne le vérifie.
  `TERM`, `COLUMNS`, `LINES`. Sur POSIX il n'existe **aucun** appel qui réponde
  « j'interprète les séquences » : la couleur y est donc toujours accordée sur
  une déclaration, et la page l'écrit en toutes lettres — `ANSI oui / declare
  par TERM, non mesure`. Un `TERM` hérité d'une session `ssh` ou d'un éditeur
  suffit.

Chaque « non » nomme l'appel qui a refusé, avec son `errno` et son message.
La commande ne se connecte à rien et n'écrit aucun fichier ; sur Windows elle
écrit le mode de la console (`SetConsoleMode`) avant de le restaurer, faute de
quoi il n'y aurait rien à mesurer.

Trois choses qu'elle ne peut pas prouver, et qui sont écrites dans
`falcon/toile/__init__.py` plutôt que tues : que `SetConsoleMode` se comporte
comme notre modèle de Windows le suppose (la CI est Linux), que la police de
la console ait le glyphe de ce qu'on affiche (aucune API ne le signale), et
que `conhost` n'ajoute pas une rangée fantôme sur une ligne pleine — d'où la
colonne de marge, qui coûte zéro.

`dictionnaire` met le catalogue **à plat**, une ligne par champ, pour qu'un
tableur puisse proposer les écrans et les champs disponibles — ce que la spec
appelle au §4 « l'autocomplétion des `id` disponibles sur l'écran attendu ».
Trois colonnes font le tri : `modifiable` (n'offrir que l'écrivable pour un
`set`), `type` (un bouton n'est pas une case), `texte` (le libellé, seul nom
qu'un humain reconnaît).

Le fichier sort en UTF-8 **avec BOM** et délimité par `;` : c'est ce qu'un
Excel français lit sans rien demander. Sans le BOM il lit en ANSI et massacre
les accents ; sans le `;` il pose tout en colonne A.

`brouillon` produit une ébauche de pipeline **inachevée à dessein** : tout ce
que la trace ne dit pas — l'identité des écrans, avant tout — porte un
marqueur, et `charger()` refuse le fichier tant qu'il en reste un. Le
générateur n'émet jamais `navigation_libre` : ce serait désarmer la garde
d'identité sur toute pipeline née d'une trace, sans que personne l'ait décidé.

`inventaire` est la première chose à passer sur toute nouvelle trace : il dit
ce que le parseur sait en lire, et ce qu'il n'en sait pas.

`explorer` est l'**étape 2 du cycle de vie** : elle rejoue une trace en
observation et verse en quarantaine chaque écran traversé — trente-cinq
relevés en une commande, là où `diagnostiquer` en fait un à la fois.

Elle **ne sauvegarde rien** : le mode est figé en `dry-run` et le plafond de
sauvegardes vaut zéro *dans le code*, ni l'un ni l'autre n'étant une option de
la ligne de commande. Une option est une chose que quelqu'un finit par régler.

Mais elle **agit**, et le dire est la moitié du travail : elle saisit des
valeurs dans les champs — un `write` en dry-run tape bel et bien dans SAP, il
n'est simplement jamais validé — elle navigue, presse des boutons, lance des
sélections longues, et peut poser des verrous. Le dry-run ne reconnaît que
deux gestes de sauvegarde, `vkey(11)` et `press` sur `tbar[0]/btn[11]` : une
sauvegarde par un chemin de **menu** passerait au travers. C'est pourquoi
l'exploration refuse en plus d'*activer* quoi que ce soit dans une fenêtre
dont elle n'a pas identifié un champ juste avant — le « Oui » d'une popup
générique s'appelle `usr/btnBUTTON_1` sur toutes les popups à la fois, et un
`press` y réussirait sur la mauvaise boîte.

Elle ne repart **que** sur un code transaction qu'elle a tapé elle-même,
validé par Entrée, et vérifié contre l'écran obtenu : `okcd.text = "/nIW39"`
seul ne démarre rien, et une reprise non vérifiée rejouerait toute la suite de
la trace sur l'écran précédent en annonçant « IW39 exploré ».

Les deux plafonds sont **obligatoires**. La commande montre le système et le
mandant avant de demander le nom du fichier de trace en toutes lettres, et
rend `0` seulement si la trace a été parcourue de bout en bout.

Elle **écrit un fichier** à chaque lancement : le compte rendu est conservé
dans `<catalogue>/rapports/<horodatage>-<trace>.txt`, en plus d'être imprimé.
C'est le seul endroit où vivent la partition des gestes, les branches, les
reprises et les visites non atteintes — il défilait à l'écran, puis
disparaissait avec la fenêtre. Le dossier est invisible du dépôt, qui ne lit
que `<catalogue>/*.yaml` sans récursion. Si le disque le refuse, le compte
rendu est quand même rendu, avec la ligne « compte rendu NON conservé » et le
motif : une cartographie qui vient d'agir dans SAP ne perd pas sa partition
pour un partage en lecture seule.

`diagnostiquer` est le **premier contact réel** — il se greffe sur une session
SAP que vous avez ouverte et sur laquelle vous vous êtes authentifié
vous-même. Aucun mot de passe ne transite par FALCON. La commande ne reçoit
qu'un `DriverLecture`, une façade qui n'a ni `write`, ni `press`, ni `vkey` :
elle est en lecture seule par construction, pas par discipline. Avec
`--catalogue`, le relevé est versé en **quarantaine** ; le promouvoir reste un
geste explicite, celui par lequel un humain dit avoir relu l'écran.

## Livraison

Le dépôt est modulaire, la livraison est **un fichier unique** (§6) :

```bash
python outils/embarquer.py        # produit falcon.pyz — la taille est imprimee
python falcon.pyz inventaire trace.vbs
```

La console le construit aussi, depuis `1 Vérification et livraison`.

`zipapp` est dans la stdlib : construire le bundle n'ajoute aucune dépendance,
pas même de construction. PyYAML — la seule dépendance d'exécution — voyage
dans l'archive ; la suite le prouve en lançant le bundle avec `-S`, donc sans
les paquets de la machine.

`pywin32` n'est **pas** embarqué et ne doit pas l'être : c'est une extension
binaire Windows liée à une version d'interpréteur. Il s'installe sur le poste,
et `diagnostiquer` — la seule commande qui l'exige — le dit avec la ligne de
commande à taper.

## Un automatisme nouveau, c'est un YAML — pas un commit

Une pipeline sait **composer** la valeur qu'elle tape, sans qu'une ligne de
Python soit écrite ni relue :

```yaml
version: 1
nom: "corriger_variantes"
classe: "iterative"
cles: ["site"]
plafond_items: 50
plafond_sauvegardes: 50
etapes:
  - nom: "saisir_variante"
    action: "set"
    cible: "wnd[0]/usr/ctxtV-LOW"
    source: {gabarit: "/BCP01_{site}"}     # le nom porte le site
    format: [majuscules]
    ecran: {transaction: "IA08", programme: "RIPLKO10", dynpro: "1000"}

  - nom: "saisir_equipement"
    action: "set"
    cible: "wnd[0]/usr/ctxtEQUNR"
    source: {colonne: equipement}
    defaut: "1"                            # si la case est vide
    format: [sans_espaces_autour, {zeros: 18}]   # cadrage SAP, largeur déclarée
    ecran: {transaction: "IA08", programme: "RIPLKO10", dynpro: "1000"}
```

**Chaque étape déclare son `ecran`**, et ce n'est pas du remplissage : c'est ce
que la garde d'identité compare avant d'agir. Une étape qui ne le déclare pas
est refusée au chargement — sauf à écrire `navigation_libre: true`, qui dit
explicitement « je ne sais pas encore où j'atterris ». L'exemple ci-dessus est
chargé par la suite de tests à chaque exécution : un exemple que rien ne
vérifie se périme, et celui-ci enseignait précisément l'omission qui désarme
la garde.

`gabarit` compose depuis plusieurs colonnes ; `format` applique des
transformations **dans l'ordre déclaré** ; `defaut` remplace une valeur vide.

**Le registre des transformations est fermé** — `majuscules`, `minuscules`,
`sans_espaces_autour`, `zeros`, `tronque` — et il n'existe aucune façon
d'exprimer une condition, un calcul, ou une expression évaluée. Ce n'est pas
de la timidité : une expression évaluée dans un YAML de pipeline serait du
code arbitraire n'ayant traversé ni relecture ni garde, c'est-à-dire
l'échappatoire que le §5.2 interdit. Ce qui ne s'exprime pas ainsi passe par
`action: python`, qui reçoit un `Poste` gardé.

La composition ne relâche aucune garde : la valeur est calculée **avant**
l'écriture, donc la relecture compare bien ce qui a été tapé.

## Le YAML que vous écrivez

Un automatisme nouveau, c'est un YAML et un CSV — jamais un commit. Le format
doit donc être **inflexible plutôt que serviable** : ce qui est ambigu est
refusé, jamais deviné.

YAML 1.1 lit `0100` comme de l'octal (64), `007` comme 7, `12:30` en base 60
(750), `on` et `N` comme des booléens, une clé vide comme `None`. Ces valeurs
sont tapées dans un ERP de production. `falcon/noyau/yaml_strict.py` pose deux
barrières : le lecteur refuse à l'analyse les formes qui deviennent
indistinguables une fois lues, et les accesseurs exigent le type au lieu de le
forcer — `str(None)` donne `"None"`, `bool("non")` donne vrai.

Chaque refus nomme le fichier, et la ligne ou l'étape.

Deux règles d'architecture sont vérifiées mécaniquement par
`tests/test_frontieres.py`, parce qu'une règle que rien ne vérifie tient
jusqu'au premier import pressé :

- un seul module de FALCON importe `win32com` — celui de la couture. Rien
  d'autre ne connaît SAP (§3.4) ;
- le moteur et les pipelines ne touchent jamais la couture nue : ils passent
  par le contrôleur, qui porte les gardes. Une pipeline ne peut donc pas en
  désactiver une (§5.2).

## `historique/`

Le socle EagleLoader et le harness artisanal développés avant cette spec.
Conservés en l'état, sous le régime de la décision n°2 : **réutilisés sous
contrôle strict**, jamais repris par défaut.

| Contenu | Statut au regard de la spec |
|---|---|
| `historique/docs/TRAPS.md` | **vivant** — les douze pièges de terrain sont le matériau de départ de la taxonomie d'erreurs (§5.1), qui se récolte et ne se spécifie pas |
| `historique/cartes/sap_map.yaml` | **référence** — relevé réel K75/210 ; parent du catalogue (§3.1), mais pas sa structure : le catalogue est clé par triplet + empreinte, et se remplit par dump, pas à la main |
| `historique/sapharness/` | **remplacé** — la décision n°3 arrête un harness par rejeu du catalogue, pas un simulateur écrit à la main (§3.7) |
| `historique/docs/GUIDE.md` | documentation de ce simulateur ; suit son sort |
| `historique/docs/HARNESS.md` | le raisonnement qui a mené à la spec ; valeur historique |

L'archive reste exécutable :

```bash
python -m unittest discover -s historique/tests -t historique
```
