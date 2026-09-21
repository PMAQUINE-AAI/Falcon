# Automatismes hors moteur

Des programmes d'un seul fichier, ecrits sur la couture FALCON
(`falcon/couture/`) sans le moteur de pipeline. Ils existent quand une trace
demande ce que le YAML ne sait pas dire — attraper une modale et decider — et
qu'on ne veut pas refondre le moteur pour ca. Ils reprennent trois gardes,
parce qu'un automate qui ecrit dans un ERP sans elles n'est pas simplifie, il
est nu : **a blanc par defaut**, **plafond obligatoire**, **l'inconnu arrete**.

## `cl24n_classer.py` — affecter des points de mesure a une classe

Rejoue la trace `CL24N` : une passe par classe, chaque point de mesure dans la
premiere ligne vide du table control, Entree, une sauvegarde en fin de passe.
Un point deja affecte est marque `DEJA_AFFECTE` et sa ligne videe ; la modale
des caracteristiques obligatoires est passee comme dans la trace
(« poursuivre » puis « valider »).

### Le jeu

Un CSV, deux colonnes, une ligne par affectation. Voir
`cl24n_points.exemple.csv`.

```
point;classe
493303;MA_CLASSE_1
493304;MA_CLASSE_1
493303;MA_CLASSE_2
```

Un point est un numero, chiffres seulement, douze au plus : `493303.0` est
refuse. Un doublon par classe est refuse. Le type de classe est le meme pour toutes les classes
du jeu et se donne sur la ligne de commande.

### 1. A blanc — c'est le run de reconnaissance

```bash
python automatismes/cl24n_classer.py points.csv --type-classe 0XX --plafond-points 20 --classe MA_CLASSE_1
```

Rien n'est sauvegarde : la sauvegarde est **refusee** mecaniquement, pas
seulement evitee. Une seule classe par lancement — les saisies restent a
l'ecran et quitter CL24N sans sauvegarder est un geste a faire a la main
entre deux classes. Une modale inconnue est annulee (F12) et la passe
continue : le but est d'en voir le plus possible.

Mettre dans ce jeu **un point deja affecte et un point nouveau**, pour que
les deux modales apparaissent. Puis envoyer les deux fichiers ecrits dans
le dossier `--sortie` (`sorties` par defaut, ignore par git) :

- `cl24n_<horodatage>_journal.csv` — une ligne par point, avec son etat ;
- `cl24n_<horodatage>_rapport.txt` — **chaque ecran et chaque modale**
  rencontres, une fois en entier (identite, fenetres, statut, et une ligne par
  champ : id, type, texte, infobulle, modifiable), puis en bref. C'est lui
  qui tranche les hypotheses ci-dessous.

### 2. Executer

```bash
python automatismes/cl24n_classer.py points.csv --type-classe 0XX --plafond-points 500 --executer
```

Toutes les classes du jeu, dans l'ordre ; avant chaque passe, la commande
montre le systeme et le mandant et demande **le nom de la classe en toutes
lettres**. Une modale inconnue **arrete** la passe avant la sauvegarde et la
laisse ouverte a l'ecran : ce qui etait saisi sort `NON_SAUVEGARDE` dans le
journal, et se relance tel quel — a la relance, ces points sortent
`DEJA_AFFECTE` s'ils ont ete sauvegardes a la main entretemps.

`--par-lot 50` sauvegarde toutes les cinquante saisies au lieu d'une fois en
fin de passe : un arret au trois-centieme point n'en perd alors pas trois
cents.

### Les etats du journal

| etat | sens |
|---|---|
| `SAISI` | entre et valide par Entree, en attente de sauvegarde |
| `SAUVEGARDE` | statut `S` apres la sauvegarde |
| `A_VERIFIER` | sauvegarde pressee, statut non concluant — regarder dans SAP |
| `DEJA_AFFECTE` | la modale « deja affecte » : KO, ligne videe |
| `REFUSE` | message `E`/`A` apres Entree (point inexistant…) : KO, ligne videe |
| `POPUP_INCONNUE` | a blanc seulement : modale annulee, point douteux |
| `NON_SAUVEGARDE` | saisi, jamais sauvegarde (a blanc, ou arret) |
| `PASSE`, `ARRET` | debut et fin de passe ; la raison d'un arret |

### Ce qui est su, et ce qui est suppose

**Rien de ce fichier n'a encore parle a un SAP.** La trace du recorder donne
le bouton du type d'objet, la radio, le table control, sa colonne, la
sauvegarde et la paire « poursuivre / valider ». Le reste est HYPOTHESE, et
marque tel quel dans `Cibles` et dans les regles de modale du programme :

- les champs de l'ecran initial, cherches par suffixe `RMCLF-CLASS` et
  `RMCLF-KLART` parmi les champs de saisie — s'ils ne sont pas la, la passe
  s'arrete en nommant ce qu'elle a trouve ;
- la modale « deja affecte », reconnue par le mot *deja* (ou *already*,
  *bereits*) dans son titre ou ses textes ; le meme refus en barre de statut
  (`E`) est traite pareil ;
- la modale des caracteristiques obligatoires, reconnue par son bouton
  `tbar[0]/btn[8]` — c'est celui que la trace presse.

Le rapport du run a blanc dit ce qu'il en est ; les regles s'ajustent
ensuite, dans le programme, avant la premiere execution.

### Tests

```bash
python -m unittest tests.test_cl24n_classer
```

Contre un CL24N de theatre qui **n'etablit aucune fidelite** : il prouve que
le programme s'arrete sur l'inconnu, ne sauvegarde jamais a blanc, ne vide pas
une ligne qui ne porte plus le point refuse, et cherche la ligne vide au-dela
de la page visible. Il ne prouve pas que SAP repond ainsi.
