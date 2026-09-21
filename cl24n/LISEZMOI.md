# CL24N — remplir une transaction SAP au guidage

Programme autonome. **Quatre fichiers, aucune dépendance** : ni Falcon, ni
PyYAML, rien d'autre que Python et `pywin32` pour parler à SAP. On copie le
dossier où on veut sur le poste Windows, on double-clique sur `CL24N.bat`, et
il affiche un menu.

| Fichier | Rôle |
|---|---|
| `cl24n.py` | le programme |
| `CL24N.bat` | le double-clic, sous Windows |
| `points.csv` | l'exemple à remplacer par tes points |
| `test_cl24n.py` | les tests, qui tournent sans SAP |

---

## La méthode : tu dictes une fois, il rejoue

**Le programme ne sait rien de CL24N, ni d'aucune transaction.** Il ne devine
aucun champ, aucun bouton, aucun enchaînement, et il n'y a aucune règle SAP
écrite dans son code. Tu lui donnes une transaction, il l'ouvre. La première
passe est **dictée** : il affiche les champs et les boutons qu'il voit à
l'écran, tu lui dis geste par geste quoi taper et où, il le fait dans SAP sous
tes yeux, et il l'**écrit dans une recette**. Ensuite, la recette rejoue
exactement la même chose pour tous les points et toutes les classes, sans toi.

Le nom du programme vient du premier cas traité. Rien ne le lie à CL24N : une
autre transaction se dicte de la même façon.

```
    1.  DICTER          tu guides, il apprend      ->  recette.json
    2.  REJOUER À BLANC une classe, rien de sauvé  ->  tu relis le journal
    3.  REJOUER         toutes les classes, sauvé
```

Si SAP change, ou si tu t'es trompé, tu redictes. Il n'y a rien à recoder.

---

## 1. Installer, une fois

Python 3.11 ou plus récent, puis :

```
pip install pywin32
```

Et côté SAP GUI, le scripting doit être autorisé **des deux côtés** : serveur
(`sapgui/user_scripting = TRUE`, c'est un geste d'administrateur) et client
(*Options* → *Accessibilité et scripting* → **Activer le scripting**).

Le programme **se greffe** sur une session SAP que tu as ouverte et sur
laquelle tu t'es authentifié toi-même. Il ne demande jamais de mot de passe et
n'en fait transiter aucun.

---

## 2. Le fichier des points

Deux colonnes, une ligne par affectation. Le séparateur peut être `;`, `,` ou
une tabulation — il est lu dans l'en-tête.

```
point;classe
493303;MA_CLASSE_1
493304;MA_CLASSE_1
493305;MA_CLASSE_2
```

Un point est un numéro, chiffres seulement, douze au plus. Un doublon dans une
même classe est refusé.

---

## 3. Dicter la première passe

Double-clic sur `CL24N.bat`, puis le choix **3**. Il demande le fichier, la
classe avec laquelle dicter, **la transaction à ouvrir**, et le nom de la
classe en toutes lettres pour confirmer. Il ouvre la transaction lui-même —
les deux premiers gestes entrent dans la recette comme si tu les avais dictés,
et c'est ce qui arme la garde d'identité. Puis il affiche l'écran :

```
----------------------------------------------------------------------
 wnd[0] « Affecter objets a une classe »
 CL24N / SAPLCLFM / 1512     statut : - : «  »

 CHAMPS
     1  okcd                         «  »

 TABLEAU T1  tblSAPLCBCMTC_OBJ_CLASS   3 ligne(s) visible(s), 2 colonne(s)
       C1:ctxtRMCLF-POINT     C2:ctxtRMCLF-KTEXT
   L0   493253                 Pompe alimentaire
   L1   ·                      ·
   L2   ·                      ·

 BOUTONS
    b1   tbar[0]/btn[11]              « Sauvegarder (Ctrl+S) »
    b2   tbar[1]/btn[33]              « Type d'objet (Ctrl+F9) »
----------------------------------------------------------------------
 moment : entete  (5 geste(s) dicte(s))
  >
```

**Un tableau s'affiche en grille, jamais cellule par cellule.** Ses colonnes
sont nommées une fois, `C1`, `C2`, et quelques lignes servent d'aperçu, `L0`,
`L1`. C'est ce qui rend l'écran lisible : un tableau de trois cents lignes sur
cinq colonnes expose mille cinq cents champs, et les lister noyait tout le
reste. Tu désignes ensuite une cellule par sa colonne et sa ligne.

Tu tapes les gestes. Après chacun, il agit dans SAP et réaffiche l'écran, qui
a changé.

| tu tapes | il fait |
|---|---|
| `1 = "/nCL24N"` | écrit la constante `/nCL24N` dans le champ 1 |
| `2 = classe` | écrit la **colonne** `classe` du fichier dans le champ 2 |
| `T1.C1 = point` | écrit la colonne `point` dans la colonne C1 du tableau T1, à sa **première ligne libre** |
| `T1.L5.C2 = "Pompe"` | la même chose, mais dans la ligne visible L5 |
| `ko` | dans une fenêtre surgissante : « celle-ci veut dire que le point est **refusé** » |
| `b2` | presse le bouton 2 |
| `r2` | sélectionne le choix 2 (radio, case, onglet) |
| `e` | Entrée |
| `t11` | touche de fonction 11 |
| `v` / `v wnd[1]` | revoir l'écran, ou une autre fenêtre |
| `liste` | revoir la recette dictée jusqu'ici |
| `annuler` | retirer le dernier geste **de la recette** (ne défait rien dans SAP) |
| `note ...` | ajouter une note à la recette |
| `boucle` | ce qui suit se répète **pour chaque point** |
| `cloture` | ce qui suit se fait **une fois, à la fin de la classe** |
| `fin` | enregistrer la recette et sortir |
| `abandon` | sortir sans rien enregistrer |
| `?` | l'aide |

Trois choses à savoir en dictant.

**Les valeurs sont réelles.** Le premier point de la classe est vraiment saisi
dans SAP : c'est ce qui fait que la passe aboutit, là où un jeton serait
refusé au premier contrôle.

**Un tableau se dicte par sa ligne libre, jamais par un rang.** `T1 = point`
enregistre « la première ligne libre », pas « la ligne 3 » : un rang figé
traiterait la mauvaise ligne dès que la liste change, sans rien lever.

**Un geste dicté dans une fenêtre surgissante devient conditionnel.** Il ne
sera rejoué que quand cette fenêtre est là, reconnue par son titre. Une
fenêtre de valorisation qui ne surgit que pour certaines classes ne fera donc
pas échouer les autres. Et au rejeu, c'est la fenêtre **présente** qui décide
quel geste joue, pas le rang : deux fenêtres qui n'arrivent pas toujours dans
le même ordre n'ont pas à être dictées dans un ordre précis.

**`ko` dit qu'une fenêtre signe un refus.** Tu le tapes dans la fenêtre « ce
point est déjà affecté », avant le geste qui la ferme. Au rejeu, le point
sortira `DEJA_AFFECTE` et sa ligne sera retirée du tableau. C'est la seule
façon de classer un point en échec : rien n'est deviné d'un texte.

Une dictée complète ressemble à ceci :

```
2 = classe         3 = "015"      e
b2                 r2             b1
boucle
T1.C1 = point      e
ko                 b1             (dans « le point est deja affecte »)
b1                                (dans « valorisation », si elle surgit)
cloture
b1                                (il demande « sauvegarder » en toutes lettres)
fin
```

Les deux premiers gestes, `/nCL24N` et Entrée, sont déjà posés : la
transaction a été demandée au départ.

Elle écrit `sorties\cl24n_<horodatage>_recette.json`, que tu peux relire et
corriger à la main : c'est du texte.

---

## 4. Rejouer

Choix **4**, à blanc, une seule classe : rien n'est sauvegardé, la sauvegarde
est refusée mécaniquement. Tu relis le journal, puis choix **5** pour exécuter
sur toutes les classes du fichier. Chaque passe demande le nom de la classe en
toutes lettres après avoir affiché le système et le mandant.

Deux fichiers sont écrits dans le dossier `sorties`, à côté du programme :

- `cl24n_<horodatage>_journal.csv` — une ligne par événement ; chaque point y
  a sa ligne à la saisie, puis une autre à la sauvegarde ; les lignes `PASSE`
  et `ARRET` n'ont pas de point ;
- `cl24n_<horodatage>_rapport.txt` — chaque écran et chaque fenêtre
  rencontrés, une fois en entier, puis en bref.

Le choix **2** sert quand quelque chose coince : va sur l'écran dans SAP,
prends le relevé, envoie-le. Il ne fait aucun geste.

Pour un lancement scripté, sans menu :

```
python cl24n.py points.csv --recette sorties\cl24n_..._recette.json --plafond-points 500 --executer
python cl24n.py --aide
```

---

## 5. Ce que le programme refuse de faire

**À blanc par défaut.** Presser « Sauvegarder » lève une exception tant que
`--executer` n'est pas demandé : c'est refusé mécaniquement, pas seulement
évité. Un oubli dans la recette ne peut donc pas sauvegarder par accident. En
dictée, où tu décides de tout, le geste de sauvegarde demande le mot
« sauvegarder » en toutes lettres au moment où tu le tapes.

**Plafond obligatoire.** Le nombre de points par classe est borné, et le
fichier est refusé **avant tout contact avec SAP** s'il le dépasse.

**L'inconnu arrête.** Une fenêtre surgissante qu'aucun geste de la recette ne
vise arrête tout avant la sauvegarde, et reste ouverte à l'écran pour que tu
la voies. Il n'y a **aucune règle de repli** : presser un bouton par défaut
sur une boîte que personne n'a lue est précisément ce qu'on refuse. À blanc,
elle est annulée (F12), la ligne du point est vidée et la passe continue : le
but d'un passage à blanc est d'en voir le plus possible, et le rapport garde
la fenêtre pour que tu saches quoi dicter.

S'y ajoutent trois choses qui ne sont pas des options. Chaque valeur écrite
est **relue** avant qu'on aille plus loin, parce qu'une saisie qui ne prend
pas ne lève rien toute seule. La **transaction** relevée à la dictée est
revérifiée avant chaque sauvegarde. Et une cible que le chemin dicté ne
retrouve plus est cherchée par la **fin de son identifiant**, parce que le
numéro de sous-écran change avec le type d'objet affiché.

---

## 6. Les états du journal

| état | sens |
|---|---|
| `SAISI` | entré et validé, en attente de sauvegarde ; un avertissement accepté par une seconde Entrée est dans le détail |
| `SAUVEGARDE` | statut `S` après la clôture |
| `A_VERIFIER` | sauvegarde pressée, statut non concluant — à regarder dans SAP |
| `DEJA_AFFECTE` | le point était déjà dans la classe (le texte de la fenêtre est dans le détail) : KO, ligne vidée |
| `REFUSE` | message `E`/`A` après Entrée, un point inexistant par exemple : KO, ligne vidée |
| `POPUP_INCONNUE` | à blanc seulement : fenêtre annulée, point douteux |
| `NON_SAUVEGARDE` | saisi, jamais sauvegardé (à blanc, ou arrêt) |
| `PASSE`, `ARRET` | début et fin de passe ; la raison d'un arrêt |

Un arrêt termine le **lancement** : les classes qui restaient sont notées
`non lancee`. Le même fichier se relance tel quel — à la relance, les points
déjà sauvegardés ressortent `DEJA_AFFECTE`.

---

## 7. Ce que le programme sait d'avance

**Une seule chose : ce qui compte comme une sauvegarde**, `tbar[0]/btn[11]` et
la touche F11. Elle reste dans le code parce que le mode à blanc doit pouvoir
la *refuser*, et qu'une garde qu'on pourrait dicter ne serait plus une garde.

Tout le reste vient de ta dictée : les champs, les boutons, les fenêtres,
l'enchaînement, et le verdict de refus. Un message `E` ou `A` en barre de
statut classe le point `REFUSE` sans rien dicter, parce que c'est vrai de
toute transaction et que ça ne suppose aucun écran.

**Aucune ligne de ce programme n'a encore parlé à un vrai SAP** : le premier
passage à blanc est ce qui le dira.

---

## 8. Les tests

```
python test_cl24n.py
```

Cent treize tests contre un CL24N de théâtre qui **n'établit aucune fidélité** :
il répond ce qu'on lui a dit de répondre. Ils prouvent qu'une dictée complète
produit la recette attendue et qu'elle se rejoue à l'identique, qu'un tableau
de mille cellules ne donne pas mille champs, que le programme s'arrête sur
l'inconnu, qu'il ne sauvegarde jamais à blanc, qu'il ne vide pas une ligne qui
ne porte plus le point refusé, et que le menu ne touche à rien quand un
fichier est refusé. Ils ne prouvent pas que SAP répond ainsi.
