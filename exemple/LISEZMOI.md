# Un exemple complet, rejouable sans SAP

Copie ce dossier, change les valeurs, tu as ton automatisme. C'est là toute
l'idée : **un automatisme nouveau est un fichier, pas un commit.**

```bash
python exemple/rejouer.py
```

Ça déroule le parcours entier contre le double de test — conversion, chargement,
répétition à blanc, exécution, journal — et ça n'écrit dans aucun SAP.

---

## Ce qu'il y a dans le dossier

| Fichier | Rôle |
|---|---|
| `pipeline.csv` | les propriétés : nom, classe, clés, les deux plafonds |
| `etapes.csv` | une ligne par étape, dans l'ordre du `rang` |
| `derogations.csv` | une ligne par dérogation, rattachée à une étape |
| `jeu.csv` | les données : **une ligne = une itération** |
| `rejouer.py` | déroule tout, contre le double |

Les trois premiers sont ce que le classeur produit. Le quatrième est ce que tu
remplis. Le cinquième n'existe que pour cette démonstration : sur un poste
réel, on ouvre la console.

---

## Les deux conventions à retenir

**Les valeurs tapées dans SAP s'écrivent entre crochets** — `[0100]`, `[S]`,
`[]`.

Une cellule qui contient `[` et `]` n'est jamais un nombre pour Excel. Elle
survit à la saisie, à l'enregistrement et au copier-coller, quel que soit le
format de la colonne. Sans les crochets, `0100` devient `100` et `on` devient
`VRAI` — et FALCON ne voit jamais le classeur, donc il ne peut pas le
rattraper : un `0100` déjà mangé est indiscernable d'un `100` légitime.

`[]` exprime la chaîne vide, qui n'est pas la même chose que « pas de valeur ».

Un **nom de colonne** n'en prend pas : ce n'est pas une valeur tapée, c'est une
référence. `[site]` ferait chercher une colonne appelée `[site]`.

**L'écran tient dans une cellule** — `IA08::RIPLKO10::0100`.

C'est le jeton que `falcon dictionnaire` met dans la colonne `ecran` : on le
**colle**, on ne le retape pas. Si l'étape ne sait pas encore où elle atterrit,
on écrit `libre`. Il n'y a pas de troisième possibilité, et c'est voulu : une
étape muette neutraliserait la garde d'identité sans que personne ne le voie.

---

## Le parcours, commande par commande

### 1. Peupler le dictionnaire *(demande un vrai SAP)*

```bash
python -m falcon diagnostiquer --catalogue <dossier-catalogue>
python -m falcon dictionnaire <dossier-catalogue> -o <dictionnaire>.csv
```

`diagnostiquer` se greffe sur une session SAP **que tu as ouverte toi-même**,
relève l'écran courant, et le verse en quarantaine. Rien d'autre ne peut
peupler le catalogue : les cibles SAP ne s'inventent pas.

`dictionnaire` l'aplatit en CSV — une ligne par champ — pour que le classeur
propose les écrans et les cibles dans des listes déroulantes.

**Ce dossier n'inclut pas de catalogue**, et c'est délibéré : en écrire un de
mémoire produirait des cibles qui ont l'air justes et qui échouent au premier
appel réel. Les cibles de `etapes.csv` viennent de la trace de référence.

### 2. Convertir

```bash
python -m falcon composer exemple/                          # montre, n'écrit rien
python -m falcon composer exemple/ -o <ma-pipeline>.yaml
```

Le YAML n'est écrit **que si FALCON le recharge sans rien refuser**. Un YAML
cassé à côté d'un YAML valide plus ancien, c'est le mauvais fichier lancé un
jour de fatigue.

### 3. Répéter à blanc, puis exécuter

```bash
python -m falcon console
```

Branche « 3 — Pipelines et données » :

- **4 — Répétition à blanc** : tout sauf la validation. Aucune écriture.
- **5 — Exécuter** : écrit dans SAP, après confirmation du nom de la pipeline
  **en toutes lettres**.
- **6 — Reprendre** : repart d'un journal existant. Les douteux ne sont jamais
  rejoués.

### 4. Quand un lot s'arrête sur un incident inconnu

C'est le cas **normal** au premier run réel : le registre livré ne contient
aucun message SAP — personne n'en a observé — et tout ce qui n'est pas
répertorié est bloquant.

Les dumps sont écrits dans un dossier `dumps` **à côté du journal**, sans
que tu aies rien à demander :

```bash
python -m falcon recolter <dossier-du-journal>/dumps -o <surcouche>.yaml
```

(La console accepte aussi le chemin du journal lui-même — branche
« 7 — Taxonomie des incidents » — et va chercher `dumps` à côté.)

Le fichier proposé porte ce qui a été **observé**, et un marqueur
`A COMPLETER` partout où il faut **décider**. Il refuse de charger tant qu'il
en reste un : décider à ta place qu'un message est bénin reviendrait à écrire
une règle de sécurité sur une seule observation.

Une fois complété, on le joint à l'exécution : la console le demande juste
après le journal.

---

## Ce que l'exemple montre, et ce qu'il ne montre pas

Il montre l'enchaînement, les transformations, le regroupement en items, le
journal et sa reprise.

Il ne montre **pas** que FALCON parle correctement à SAP. Le driver de
`rejouer.py` est un double : il répond ce qu'on lui a dit de répondre. Aucune
ligne de ce dépôt n'a jamais parlé à un système SAP réel, et ce dossier n'y
change rien.
