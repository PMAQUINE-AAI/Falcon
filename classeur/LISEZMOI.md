# Le classeur FALCON

`FALCON.xlsx` — les feuilles où tu choisis les champs, l'ordre, ce qui
sauvegarde. Le bouton écrit quatre CSV ; `falcon composer` en fait une
pipeline.

---

## À lire d'abord : pourquoi c'est un `.xlsx` et pas un `.xlsm`

Un projet VBA est un flux binaire OLE (`vbaProject.bin`). La bibliothèque qui
a fabriqué ce classeur sait **conserver** un tel projet dans un fichier qui en
a déjà un ; elle ne sait pas en **créer**. Et je ne peux ouvrir Excel nulle
part dans cet environnement, donc je ne pourrais pas établir qu'un `.xlsm`
fabriqué à la main s'ouvre.

Livrer un binaire dont on ne sait pas s'il s'ouvre serait exactement le défaut
que ce dépôt traque : un artefact d'aspect normal, faux, et dont l'erreur ne
se verrait qu'au moment où quelqu'un en a besoin.

Le classeur est donc un `.xlsx`, et la macro s'importe en deux gestes
(ci-dessous). Ce que je **peux** affirmer et que j'ai vérifié : le fichier est
un ZIP valide, toutes ses parties XML se parsent, les cinq feuilles portent
les bons en-têtes, et les listes déroulantes sont en place.

---

## Importer la macro — deux gestes

1. Ouvre `FALCON.xlsx`, puis **Enregistrer sous** → *Classeur Excel prenant en
   charge les macros (`*.xlsm`)*. C'est Excel qui crée le projet VBA, donc il
   est valide par construction.
2. `Alt+F11` (éditeur VBA) → clic droit sur `VBAProject (FALCON.xlsm)` →
   **Importer un fichier** → choisis `ExportFalcon.bas`.

Pour un bouton : onglet *Développeur* → *Insérer* → bouton de formulaire →
affecte la macro `ExporterTout`.

Si l'onglet *Développeur* n'apparaît pas : *Fichier* → *Options* →
*Personnaliser le ruban* → coche **Développeur**.

---

## Les feuilles

| Feuille | Ce qu'on y fait | Exportée ? |
|---|---|---|
| `Dictionnaire` | on **colle** le CSV de `falcon dictionnaire` | non |
| `Pipeline` | nom, classe, clés, les deux plafonds | → `pipeline.csv` |
| `Etapes` | une ligne par étape, dans l'ordre du `rang` | → `etapes.csv` |
| `Exemple` | des étapes remplies, à recopier | **non** |
| `Derogations` | une ligne par dérogation | → `derogations.csv` |
| `Donnees` | le jeu — **une ligne = une itération** | → `jeu.csv` |

`Exemple` n'est pas exportée, et c'est délibéré : une ligne d'exemple laissée
dans une feuille exportée deviendrait une **étape**, et la pipeline porterait
une saisie que personne n'a voulue.

---

## Les deux conventions

**Les valeurs tapées dans SAP s'écrivent entre crochets** — `[0100]`, `[S]`,
`[]`.

Une cellule qui contient `[` et `]` n'est jamais un nombre pour Excel : elle
survit à la saisie, à l'enregistrement et au copier-coller quel que soit le
format de la colonne. Les colonnes concernées sont aussi mises au format
*Texte*, mais c'est la ceinture et non les bretelles : le format se perd au
copier-coller, les crochets non.

Un **nom de colonne** n'en prend pas — ce n'est pas une valeur tapée, c'est
une référence.

**L'écran tient dans une cellule** — `IA08::RIPLKO10::0100`, le jeton que la
feuille `Dictionnaire` porte en colonne `ecran`. On le colle. Si l'étape ne
sait pas encore où elle atterrit : `libre`.

---

## Le `rang`

Il doit **croître**. Numérote de dix en dix pour pouvoir insérer.

Cliquer sur un en-tête pour trier est le geste le plus banal d'un tableur, et
il réordonne les étapes en silence — or l'ordre des étapes est ce qui est tapé
dans SAP, dans quel ordre, et à quel moment on sauvegarde. `falcon composer`
refuse un rang décroissant plutôt que de jouer une pipeline réordonnée.

---

## Ce que la macro fait, et ce qu'elle ne fait pas

Elle écrit quatre CSV en UTF-8 avec BOM, délimités par `;`. **Elle ne valide
rien**, et c'est voulu.

Ce module VBA n'est pas testé et ne peut pas l'être — aucune machine de ce
projet n'exécute Excel. La parade est architecturale : **le garder bête**.
Toute la validation vit dans `falcon/tableur/`, qui est testé. Une macro
fausse produit donc un CSV que `falcon composer` **refuse**, avec un message
qui nomme le fichier et la ligne. Elle ne peut pas produire un YAML plausible
et faux.

Si le module faisait la moindre validation, une erreur dedans deviendrait une
pipeline qui se charge et fait autre chose.

**La limite de cette parade, et il faut la connaître :** elle ne couvre pas
une valeur altérée *à la lecture de la cellule*. Le convertisseur recevrait
alors une valeur déjà fausse et parfaitement plausible, et il n'aurait aucun
moyen de le savoir.

C'est pourquoi la macro lit `.Value2` — la valeur sous la cellule — et non
`.Text`, qui rend le texte **affiché** : celui-ci dépend du format de nombre
et de la largeur de colonne, si bien qu'une colonne trop étroite donnerait
`######` et un format de date donnerait la date formatée. Elle calcule aussi
la dernière ligne sur **toutes** les colonnes, et non sur la seule colonne A,
qui peut légitimement être vide sur une ligne de données.

Ces deux points sont les seuls du module où une erreur ne serait pas
rattrapée en aval. Je ne peux ni exécuter ni tester ce code — aucune machine
de ce projet n'a Excel — donc je le signale plutôt que de le passer sous
silence : si le CSV produit te surprend, regarde d'abord ce que la cellule
contient vraiment (`=CELLULE("format";A1)` ou la barre de formule) avant de
soupçonner FALCON.

---

## Ensuite

```bash
python -m falcon composer <dossier-des-csv> -o <ma-pipeline>.yaml
```

FALCON relit le YAML qu'il vient de produire et **n'écrit le fichier que s'il
le recharge sans rien refuser**. Un YAML cassé à côté d'un YAML valide plus
ancien, c'est le mauvais fichier lancé un jour de fatigue.

Puis la console : répétition à blanc d'abord — c'est une garde, pas une
suggestion — et l'exécution ensuite.

---

## Reconstruire le classeur

```bash
pip install openpyxl        # outil de CONSTRUCTION, pas une dépendance
python outils/classeur.py
```

`openpyxl` n'entre ni dans `pyproject.toml`, ni dans le bundle. FALCON ne lit
jamais un classeur : il lit les CSV que le classeur écrit.
