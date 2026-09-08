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
s'inventent pas.

```bash
python -m falcon diagnostiquer
python -m falcon diagnostiquer --catalogue <dossier-catalogue>
```

Sans argument, il affiche l'écran courant : identité, fenêtres, statut, et le
relevé des champs. Avec `--catalogue`, il verse le relevé en **quarantaine**.

Va sur l'écran voulu dans SAP, lance la commande, recommence pour chaque écran
de ton parcours.

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

- **Peupler le catalogue.** `diagnostiquer` en est le seul producteur, et il
  exige Windows + pywin32 + une session ouverte.
- **Compléter les `ecran:` d'un brouillon issu d'une trace.** Sur la trace de
  référence : 198 marqueurs pour 75 étapes, et `charger()` refuse tant qu'il en
  reste un. Ni la trace, ni le catalogue, ni le dictionnaire ne donnent
  `programme`/`dynpro` — seul `diagnostiquer`, écran par écran.
- **Relever la carte `SE16N`** (lot 12b). `falcon/volumique/carte_se16n.yaml` est livrée vide,
  et l'export refuse tant qu'il y reste un marqueur. La remplir de mémoire
  produirait un module qui a l'air complet et qui échoue au premier appel réel.
- **`action: python`** exige toujours d'éditer le dépôt. Corollaire : les 22
  gestes non rejouables et les 7 sélections ALV par index que le brouillon
  signale sur la trace réelle n'ont pas d'issue déclarative.
- **`Champ` ne porte ni longueur ni caractère obligatoire**, donc un
  `tronque: N` suppose que tu connaisses N. Le relever demanderait de toucher
  la couture, dont la surface est épinglée à dix-huit méthodes.
- **Extraire des champs vers un fichier** (le V1.5 que tu annonçais).
  `action: lire` existe, mais la valeur vit dans un dictionnaire local détruit
  à la fin de l'item : elle ne ressort ni au journal, ni au `Resultat`, ni au
  fichier de KO.
