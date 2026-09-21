# CL24N — affecter des points de mesure à une classe

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

## 1. Installer, une fois

Python 3.11 ou plus récent, puis :

```
pip install pywin32
```

Et côté SAP GUI, le scripting doit être autorisé **des deux côtés** : serveur
(`sapgui/user_scripting = TRUE`, c'est un geste d'administrateur) et client
(*Options* → *Accessibilité et scripting* → **Activer le scripting**, en
décochant les deux avertissements si tu ne veux pas cliquer à chaque action).

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
même classe est refusé. Le type de classe est le même pour tout le fichier et
se demande au lancement.

---

## 3. Lancer

Double-clic sur `CL24N.bat`, ou depuis un terminal :

```
python cl24n.py
```

Le menu :

```
   1  Verifier la connexion SAP
   2  Relever l'ecran courant (lecture seule)
   3  Passage A BLANC — une classe, aucune sauvegarde
   4  EXECUTER — toutes les classes du fichier, avec sauvegarde
   5  Lister les sorties
   0  Quitter
```

**Commence par 3.** Une seule classe, rien n'est sauvegardé, et le programme
écrit tout ce qu'il a vu. Mets dans le fichier **un point déjà affecté et un
point nouveau** : c'est ce qui fait apparaître les deux fenêtres surgissantes
qu'il faut reconnaître. À la fin, quitte CL24N à la main sans sauvegarder.

Puis envoie les deux fichiers écrits dans le dossier `sorties`, créé à côté du
programme :

- `cl24n_<horodatage>_journal.csv` — une ligne par événement ; chaque point y
  a sa ligne à la saisie, puis une autre à la sauvegarde ; les lignes `PASSE`
  et `ARRET` n'ont pas de point ;
- `cl24n_<horodatage>_rapport.txt` — chaque écran et chaque fenêtre
  rencontrés, une fois en entier (identité, fenêtres ouvertes, barre de
  statut, et une ligne par champ avec son type, son texte, son infobulle et
  s'il est modifiable), puis en bref. **C'est lui qui tranche les hypothèses
  ci-dessous.**

Le choix **2** sert quand quelque chose coince : va sur l'écran dans SAP,
prends le relevé, envoie-le. Il ne fait aucun geste.

Pour un lancement scripté, sans menu :

```
python cl24n.py points.csv --type-classe 0XX --plafond-points 20 --classe MA_CLASSE_1
python cl24n.py points.csv --type-classe 0XX --plafond-points 500 --executer
python cl24n.py --aide
```

---

## 4. Ce que le programme refuse de faire

Trois gardes, parce qu'un automate qui écrit dans un ERP sans elles n'est pas
simple, il est nu.

**À blanc par défaut.** Presser « Sauvegarder » lève une exception tant que
`--executer` n'est pas demandé : c'est refusé mécaniquement, pas seulement
évité. Un oubli dans la logique ne peut donc pas sauvegarder par accident.

**Plafond obligatoire.** Le nombre de points par classe est borné, et le
fichier est refusé **avant tout contact avec SAP** s'il le dépasse.

**L'inconnu arrête.** Une fenêtre surgissante qu'aucune règle ne reconnaît
arrête tout avant la sauvegarde, et reste ouverte à l'écran pour que tu la
voies. À blanc, si elle suit l'Entrée d'un point, elle est annulée (F12), la
ligne du point est vidée et la passe continue : le but d'un passage à blanc
est d'en voir le plus possible.

S'y ajoutent deux choses qui ne sont pas des options : chaque passe demande
**le nom de la classe en toutes lettres** après avoir affiché le système et le
mandant — un `o/n` se tape sans lire — et chaque valeur écrite est **relue**
avant qu'on aille plus loin, parce qu'une saisie qui ne prend pas ne lève rien
toute seule.

---

## 5. Les états du journal

| état | sens |
|---|---|
| `SAISI` | entré et validé par Entrée, en attente de sauvegarde ; un avertissement accepté par une seconde Entrée est dans le détail |
| `SAUVEGARDE` | statut `S` après la sauvegarde |
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

## 6. Ce qui est su, et ce qui est supposé

**Aucune ligne de ce programme n'a encore parlé à un SAP.** Ce qu'il sait
vient de la trace du recorder : le bouton du type d'objet, la radio, le
tableau, sa colonne, la sauvegarde, et la paire « poursuivre / valider » des
caractéristiques obligatoires.

Le reste est une **hypothèse**, marquée telle quelle dans le code :

- les champs de l'écran initial, cherchés par la fin de leur identifiant
  (`RMCLF-CLASS`, `RMCLF-KLART`) parmi les champs de saisie — s'ils ne sont
  pas là, la passe s'arrête en nommant ce qu'elle a trouvé à la place ;
- la fenêtre « déjà affecté », reconnue par le mot *déjà* (ou *already*,
  *bereits*) dans son titre ou ses textes, **et** par l'absence de boutons
  Oui / Non : une question n'est jamais fermée par Entrée, elle arrête. Le
  même refus arrivant en barre de statut (`E`) est traité pareil ;
- la fenêtre des caractéristiques obligatoires, reconnue par son bouton
  `btn[8]` — c'est celui que la trace presse, suivi de `btn[0]` sur la fenêtre
  présente ensuite, la même ou une autre. Là encore, jamais sur une question.

Le rapport du passage à blanc dit ce qu'il en est ; les règles s'ajustent
ensuite, avant la première exécution.

---

## 7. Les tests

```
python test_cl24n.py
```

Quatre-vingts tests contre un CL24N de théâtre qui **n'établit aucune
fidélité** : il répond ce qu'on lui a dit de répondre. Ils prouvent que le
programme s'arrête sur l'inconnu, qu'il ne sauvegarde jamais à blanc, qu'il ne
vide pas une ligne qui ne porte plus le point refusé, qu'il cherche la ligne
libre au-delà de la page visible, et que le menu ne touche à rien quand un
fichier est refusé. Ils ne prouvent pas que SAP répond ainsi.
