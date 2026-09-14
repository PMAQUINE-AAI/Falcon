# Démarrage — de l'installation à la première exécution

Ce document suppose un poste Windows avec SAP GUI, et te mène jusqu'à la
première pipeline exécutée. Il dit aussi, à chaque étape, ce qui peut échouer
et pourquoi.

**Lis d'abord ceci.** Aucune ligne de ce dépôt n'a jamais parlé à un système
SAP. La CI tourne sous Linux, sans SAP GUI ni pywin32, et les quatre tests de
conformité de la couture *skippent avec motif* — `outils/verifier.py` les liste en
fin de course. Tout le reste est vérifié contre un double. La première session
réelle est donc une étape à part entière, pas une formalité : garde le premier
lot petit, et regarde dans SAP ce qui s'y est écrit.

---

## 1. Installer

Deux modes de livraison. Le premier suffit.

### Le fichier unique

```bash
python outils/embarquer.py          # produit falcon.pyz, la taille s'imprime
python falcon.pyz --aide
```

`falcon.pyz` embarque FALCON **et** PyYAML : il tourne sans `site-packages`,
donc sans rien installer. C'est le mode retenu par la spécification (§6).

Deux branches de la console — « Vérification » et « Traces » — lisent des
fichiers du dépôt et sont donc vides depuis le bundle. Elles le disent.

### Ou par `pip`

```bash
pip install .
python -m falcon --aide
```

### Et, pour parler à SAP

```bash
pip install pywin32
```

`pywin32` n'est **pas** embarqué et ne doit pas l'être : c'est une extension
binaire Windows liée à une version d'interpréteur. Seule la commande
`diagnostiquer` l'exige, et elle donne la ligne à taper si elle manque.

### Côté SAP GUI

Le scripting doit être autorisé **des deux côtés** :

- **serveur** : paramètre `sapgui/user_scripting = TRUE` (transaction `RZ11`) —
  c'est un geste d'administrateur, pas le tien ;
- **client** : *Options* → *Accessibilité et scripting* → *Scripting* →
  **Activer le scripting**. Décoche les deux avertissements (« Notifier lorsqu'un
  script s'attache » et « … se connecte ») si tu ne veux pas cliquer à chaque
  action.

FALCON **se greffe** sur une session que tu as ouverte et sur laquelle tu t'es
authentifié toi-même. Aucun mot de passe ne transite par FALCON, et il n'en
demande jamais.

---

## 2. Relever les écrans

C'est le seul geste qui exige SAP, et rien ne le remplace : les cibles ne
s'inventent pas. Deux chemins, et **le premier est celui à prendre si tu as
une trace du recorder**.

### 2a. Rejouer une trace — la cartographie

```bash
python -m falcon explorer <ma-trace>.vbs \
    --catalogue <dossier-catalogue> \
    --plafond-gestes 200 --plafond-ecrans 50
```

FALCON rejoue la trace geste par geste, relève **toutes les fenêtres
ouvertes** après chaque action et verse en quarantaine chaque écran distinct.
Trente-cinq écrans relevés en une commande au lieu de trente-cinq allers-
retours à la main.

**Les deux plafonds sont obligatoires et sans défaut** : le premier borne ce
qu'on fait au système, le second ce qu'on ajoute à ta file de relecture. Un
rayon d'action que personne n'a choisi n'en est pas un (§5.5).

**Lis ceci avant de lancer, une fois.** L'exploration **ne sauvegarde rien** :
toute sauvegarde reconnue est refusée, le mode est figé en `dry-run` et le
plafond de sauvegardes vaut zéro dans le code — ni l'un ni l'autre n'est une
option de la ligne de commande. Mais elle **agit** :

- elle **saisit des valeurs dans les champs**. Un `write` en dry-run tape bel
  et bien dans SAP ; il n'est simplement jamais validé ;
- elle navigue, presse des boutons, et lance des sélections qui peuvent
  tourner longtemps et charger le système ;
- elle peut **poser des verrous** en ouvrant une transaction en modification.

Le dry-run reconnaît deux gestes de sauvegarde : `vkey(11)` et un `press` sur
`tbar[0]/btn[11]`. Une sauvegarde déclenchée par un **chemin de menu** passe
au travers, faute de catalogue des menus. C'est pour cela que l'exploration
refuse en plus d'*activer* quoi que ce soit dans une fenêtre dont elle n'a pas
identifié un champ juste avant.

**À lancer sur un mandant de qualité avant la production.** Ce n'est pas une
formalité : c'est la première fois que FALCON enchaîne des gestes sans qu'un
humain les ait validés un par un. La commande te montre le système, le mandant
et la langue **avant** de demander confirmation, et la confirmation est le nom
du fichier de trace en toutes lettres.

La commande rend `0` **seulement** si la trace a été parcourue de bout en
bout. Sur une trace qui sauvegarde — c'est le cas de la trace de référence —
elle rend `1`, et le compte rendu dit où chaque branche est tombée et sur quel
code transaction elle a repris.

Ajoute `--esquisses` pour verser aussi, en quarantaine, les esquisses des
visites **non atteintes** : une liste de courses de ce qu'il reste à aller
relever à la main. Elles portent `programme: "?"` et `dynpro: "?"`, se
distinguent donc à l'œil nu d'un relevé, et `pour_garde` les refuse même
promues.

Depuis la console : « **2 → Explorer la trace dans SAP** », qui est la
branche des traces du recorder — c'est là qu'on va avec un `.vbs` en
main. La même entrée figure sous « 8 → Explorer la trace dans SAP »,
avec la session ; les deux lancent exactement la même chose.

**Ce que la cartographie ne fera pas pour toi.** Elle ne suit pas la trace :
elle dit quels écrans ont été **vus**. Un index de grille rejoué tel quel peut
ouvrir le détail d'un autre objet qu'à l'enregistrement — sans erreur — et la
suite du parcours diverge alors en silence. Et le relevé d'une **modale**
porte le programme et le dynpro de l'écran de dessous : avant de promouvoir
deux variantes du même triplet, vérifie laquelle était la boîte.

### 2b. Un écran à la fois — le chemin de rattrapage

Pour ce que la cartographie n'a pas atteint, et quand tu n'as pas de trace.

```bash
python -m falcon diagnostiquer
python -m falcon diagnostiquer --catalogue <dossier-catalogue>
```

Sans argument, il affiche l'écran courant : identité, fenêtres, statut, et le
relevé des champs. Avec `--catalogue`, il verse le relevé en **quarantaine**.

Va sur l'écran voulu dans SAP, lance la commande, recommence pour chaque écran
de ton parcours.

### Puis, dans les deux cas : promouvoir

```bash
python -m falcon promouvoir <dossier-catalogue>                     # liste
python -m falcon promouvoir <dossier-catalogue> --empreinte <EMPR>  # promeut
```

Promouvoir, c'est dire que **tu** as relu l'écran. La console le fait aussi
— « 5 → Promouvoir une capture » — et c'est le seul endroit d'où tu vois ce
que tu promeus avant de le promouvoir.

```bash
python -m falcon dictionnaire <dossier-catalogue> -o <dictionnaire>.csv
```

Une ligne par champ, en UTF-8 avec BOM et délimité par `;` : ce qu'un Excel
français lit sans rien demander.

---

## 3. Écrire la pipeline

Ouvre `classeur/FALCON.xlsx` (voir `classeur/LISEZMOI.md` pour importer la
macro), colle le dictionnaire dans la feuille `Dictionnaire`, remplis
`Pipeline`, `Etapes`, `Donnees`, clique sur le bouton.

```bash
python -m falcon composer <dossier-des-csv>                       # montre
python -m falcon composer <dossier-des-csv> -o <ma-pipeline>.yaml # écrit
```

FALCON **relit** le YAML qu'il produit et n'écrit le fichier que s'il le
recharge sans rien refuser.

Tu peux aussi écrire le YAML à la main : le classeur est un confort, pas un
passage obligé. `exemple/` montre les deux.

### Quand tu ne connais pas d'avance ce que SAP va trouver

Trois actions travaillent sur une **grille de résultats**, et elles existent
parce que sélectionner une ligne par son rang est un piège : l'index dépend du
contenu de la base au moment où on regarde, et une pipeline qui le fige traite
la mauvaise ligne dès que la liste change — **sans lever**.

| action | ce qu'elle fait |
|---|---|
| `extraire` | relève toute la grille dans un CSV, et **s'arrête là** |
| `choisir` | retrouve une ligne par le **contenu** d'une colonne, et la sélectionne |
| `ouvrir` | double-clique la ligne que `choisir` vient de positionner |

Elles se composent en **deux passes**, ce que la spec appelle au §1 « passe
d'audit → fichier de constats → passe de remédiation » :

```yaml
# passe 1 — l'AUDIT. Elle ne sauvegarde rien : plafond_sauvegardes: 0.
  - nom: ouvrir_la_boite
    action: press
    cible: "wnd[0]/tbar[1]/btn[17]"
    ecran: {transaction: IH06, programme: "<relevé>", dynpro: "<relevé>"}
    fenetres: ["wnd[0]", "wnd[1]"]      # l'étape qui OUVRE doit la déclarer
  - nom: chercher
    action: set
    cible: "wnd[1]/usr/txtV-LOW"
    source: {constante: "[*BCP*]"}
    ...
  - nom: variantes
    action: extraire
    cible: "wnd[1]/usr/cntlALV_CONTAINER_1/shellcont/shell"
    ...
```

Elle écrit `variantes_IH06.csv` — **un fichier par item**, nommé depuis les
valeurs de clef. Tu l'ouvres dans Excel, tu vérifies que la recherche a ramené
ce que tu voulais, tu supprimes les lignes de trop. Puis tu le donnes **tel
quel** comme jeu à la passe 2, qui `choisir` chaque ligne par son nom et la
traite.

**Le fichier ne s'écrase jamais.** Un second lancement est refusé au pré-vol,
avant tout contact avec SAP : c'est le fichier que tu viens peut-être de
corriger.

**Ce que l'extraction refuse de conclure.** Si la grille est introuvable ou
vide, elle abandonne l'item et **n'écrit aucun fichier**. Deux causes opposées
produisent exactement ça — la recherche n'a rien ramené, *ou* elle n'a ramené
qu'une ligne et SAP a ouvert l'objet directement au lieu d'afficher la liste.
Un fichier vide affirmerait la première. Il n'y a rien à affirmer.

**Une mise en garde sur Excel, et elle est assumée.** Le dictionnaire protège
ses cellules contre l'interprétation en formule ; le fichier d'extraction, non
— son apostrophe de protection partirait dans SAP au moment de retaper la
valeur. Une variante nommée `-K75` s'affichera donc peut-être de travers dans
Excel. Rien dans ce dépôt n'ouvre Excel : ce n'est pas vérifié.

---

## 4. Répéter à blanc — c'est une garde

```bash
python -m falcon console
```

Branche « 3 → Pipelines et données », entrée **4 — Répétition à blanc**. Tout
se joue sauf la validation : aucune écriture dans SAP.

Ce n'est pas une suggestion. Un `run` **refuse** si aucune répétition n'a
abouti sur **ces empreintes**, dans ce journal. On peut passer outre, et il
faut alors dire pourquoi — le motif part dans le journal.

**Ce que la répétition va révéler, et c'est normal :** le premier message
d'erreur métier arrête le lot. Le registre livré ne contient aucun message
SAP — il ne peut pas en contenir, personne n'en a observé — et tout ce qui
n'est pas répertorié est bloquant, par construction.

```bash
python -m falcon recolter <dossier-du-journal>/dumps -o <surcouche>.yaml
```

Le fichier proposé porte ce qui a été **observé**, et un marqueur
`A COMPLETER` partout où il faut **décider**. Il refuse de charger tant qu'il
en reste un : décider à ta place qu'un message est bénin reviendrait à écrire
une règle de sécurité sur une seule observation.

Complète-le, puis joins-le à l'exécution — la console le demande juste après
le journal. C'est ainsi que la taxonomie se récolte, message après message.

---

## 5. Exécuter

Entrée **5 — Exécuter**. Un récapitulatif d'abord : pipeline et jeu avec leurs
empreintes, les **deux plafonds**, le nombre d'items, chaque dérogation avec
son motif, et les valeurs composées. Puis une confirmation **en toutes
lettres** — le nom de la pipeline, qu'on ne peut pas taper sans avoir lu le
récapitulatif qui le nomme.

**Pour le premier lot réel, mets `plafond_items` à 1 ou 2.** Regarde dans SAP
ce qui s'y est écrit, puis relève le plafond. C'est le seul conseil de ce
document qui ne soit pas mécanisé, et c'est le plus important.

Interrompu ? Entrée **6 — Reprendre**. Les items `douteux` — interrompus
*après* une sauvegarde — ne sont jamais rejoués : SAP a peut-être enregistré,
et personne ne le sait. Ils sortent à l'arbitrage humain, branche « 4 →
Journaux ».

---

## Ce qui peut échouer, et ce que ça veut dire

| Message | Cause | Ce qu'il faut faire |
|---|---|---|
| `SapIndisponible` + `pywin32` | le module manque | `pip install pywin32` |
| `SapIndisponible` sans plus | pas de session, ou scripting non autorisé | ouvre une session SAP ; vérifie le scripting des deux côtés |
| `ecran attendu (…), observé (…)` | la garde d'identité — tu n'es pas où la pipeline croit | vérifie le triplet, ou déclare `navigation_libre` |
| `inconnue (non répertorié)` | un incident que le registre ne classe pas | `falcon recolter`, complète, rejoins |
| `aucune répétition à blanc n'a abouti` | garde 5.5 | lance le mode `dry-run` sur ce journal |
| `reprise refusée, le monde a changé` | pipeline ou jeu modifié depuis | c'est voulu ; refais une répétition |
| `porte N item(s) DOUTEUX` | un lot interrompu après sauvegarde | va voir dans SAP, retire ces lignes du jeu |
| `doit être une CHAÎNE, entre guillemets` | YAML retypé (`0100` → 64, `on` → vrai) | mets des guillemets |
| `doit être entre crochets` | une valeur SAP nue dans un CSV du classeur | `[0100]` plutôt que `0100` |

---

## Ce qui reste ouvert, et que rien ici ne débloque

- **Peupler le catalogue exige toujours SAP.** Ce n'est plus « un écran à la
  fois » — `explorer` en relève trente-cinq d'un coup depuis une trace — mais
  les deux producteurs, `explorer` et `diagnostiquer`, exigent Windows +
  pywin32 + une session ouverte. Rien ne relève un écran sans le regarder.
- **Aucune ligne du module de cartographie n'a parlé à un SAP réel.** Ses
  tests tournent contre un double : ils établissent l'orchestration — l'ordre
  des gestes, les refus, le dédoublonnage, la reprise vérifiée — et **zéro**
  du dialogue avec l'ERP. C'est la limite de tout le dépôt, mais elle compte
  plus ici, puisque c'est le premier module dont le métier est d'agir en
  rafale.
- **Les gestes d'ARBRE restent hors de portée.** La couture n'a aucune méthode
  d'arbre, délibérément : l'arbre de menu dépend des favoris de chacun, on
  navigue par code transaction (décision n°14). Les écrans que seuls ces
  gestes atteignent sont à relever à la main.
- **Compléter les `ecran:` d'un brouillon issu d'une trace.** Sur la trace de
  référence : 198 marqueurs pour 75 étapes, et `charger()` refuse tant qu'il en
  reste un. Ni la trace, ni le catalogue, ni le dictionnaire ne donnent
  `programme`/`dynpro` — seul `diagnostiquer`, écran par écran.
- **Relever la carte `SE16N`** (lot 12b). `falcon/volumique/carte_se16n.yaml` est livrée vide,
  et l'export refuse tant qu'il y reste un marqueur. La remplir de mémoire
  produirait un module qui a l'air complet et qui échoue au premier appel réel.
- **`action: python`** exige toujours d'éditer le dépôt. Les 7 **sélections
  ALV par index** ont maintenant une issue déclarative — `choisir` retrouve la
  ligne par son contenu — mais ce qui reste sans issue le reste : les gestes
  d'arbre, et tout ce que la couture n'expose pas.
- **`Champ` ne porte ni longueur ni caractère obligatoire**, donc un
  `tronque: N` suppose que tu connaisses N. Le relever demanderait de toucher
  la couture, dont la surface est épinglée à dix-huit méthodes.
- **Extraire un CHAMP vers un fichier.** `action: lire` existe, mais sa valeur
  vit dans un dictionnaire local détruit à la fin de l'item : elle ne ressort
  ni au journal, ni au `Resultat`, ni au fichier de KO. Ce qui sort désormais,
  c'est une **grille** entière — voir `action: extraire` au §3 — pas une
  valeur isolée.
