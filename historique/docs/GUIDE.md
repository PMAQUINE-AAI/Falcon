# Guide du harness

Ce guide est la référence d'usage du simulateur. Il complète deux documents
qu'il ne remplace pas : [HARNESS.md](HARNESS.md) dit *pourquoi* le harness
existe et ce qu'il reste à construire ; [TRAPS.md](TRAPS.md) documente les
pièges du terrain, symptôme par symptôme.

**Ce guide ne peut pas mentir.** Tous ses blocs `python` sont exécutés par
`tests/test_documentation.py`, et chacun contient ses propres assertions. Un
exemple qui cesse d'être vrai fait tomber la suite. C'est le même principe que
le harness applique au code testé : un document qui se périme sans bruit est
de la même famille que les bugs que ce projet traque.

---

## 1. Ce que le harness fait — et ce qu'il ne fait pas

Il **ne simule pas SAP**. Il n'y a ni transaction, ni base, ni verrou, ni
ABAP. Vouloir la fidélité serait sans fin et sans intérêt.

Il reproduit exactement **cinq mécaniques**, celles qui produisent des défauts
silencieux :

| Mécanique | Reproduite par |
|---|---|
| index de ligne **visible** + défilement explicite | `TableControl` |
| index de ligne **absolu**, sans ID par cellule | `Grille` |
| pile de fenêtres modales `wnd[1]`, `wnd[2]`… | `Monde.empiler` / `depiler` |
| un même ID de bouton, deux sens selon l'écran | `Ecran` |
| trace des gestes réellement effectués | `Journal` |

Tout le reste est décor. Si votre test échoue pour une raison qui n'est pas
dans ce tableau, suspectez le test avant le simulateur.

---

## 2. Le modèle mental

```text
        Monde                       ce que voit le code testé
   ┌──────────────────────┐
   │ ecran_courant  ──────┼──────►  wnd[0]
   │ modales [a, b]  ─────┼──────►  wnd[1], wnd[2]
   │ journal              │
   │ ecrans {nom: Ecran}  │
   └──────────┬───────────┘
              │  .session()
              ▼
           Session  ──  findById(id)  ──►  Controle | TableControl | Grille
                                                │
                                    tout geste  │  se note dans
                                                ▼
                                            Journal
```

Trois idées suffisent :

1. Le **`Monde`** porte l'état. Le test le manipule directement (`aller`,
   `empiler`) pour placer le code sous test dans la situation voulue.
2. La **`Session`** est la seule chose que le code testé reçoit. Elle expose
   `findById`, `Info`, `Busy` — rien d'autre.
3. Le **`Journal`** enregistre les gestes. C'est sur lui que portent les
   assertions les plus utiles, pas sur les valeurs produites.

---

## 3. Premier scénario

Vingt lignes, de bout en bout :

```python
from sapharness import Ecran, Monde, TableControl

monde = Monde()
table = TableControl(
    "wnd[0]/usr/tblSAPLCPDITCTRL_3400",
    ["PLPOD-VORNR", "PLPOD-LTXA1"],
    [{"PLPOD-VORNR": "0010", "PLPOD-LTXA1": "Controle visuel"},
     {"PLPOD-VORNR": "0020", "PLPOD-LTXA1": "Serrage"}],
    visibles=8,
    monde=monde,
)
synthese = Ecran("synthese", programme="SAPLCPDI", dynpro=3400)
synthese.objet("wnd[0]/usr/tblSAPLCPDITCTRL_3400", table)
synthese.bouton("wnd[0]/tbar[1]/btn[34]")          # marquer tout
monde.ajouter_ecran(synthese)

session = monde.session()

# --- ce que ferait le code sous test ---
session.findById("wnd[0]/tbar[1]/btn[34]").press()
cellule = session.findById("wnd[0]/usr/tblSAPLCPDITCTRL_3400/txtPLPOD-VORNR[0,1]")

# --- ce que le test vérifie ---
assert cellule.Text == "0020"
assert monde.journal.compter("press", "wnd[0]/tbar[1]/btn[34]") == 1
```

---

## 4. Référence

### `Monde`

L'état global. Un `Monde` par scénario.

| Membre | Effet |
|---|---|
| `ajouter_ecran(ecran)` | enregistre l'écran ; le **premier ajouté devient l'écran courant** |
| `aller(nom)` | change l'écran courant (= `wnd[0]`) |
| `empiler(nom)` | ouvre une modale : elle devient `wnd[1]`, puis `wnd[2]`… |
| `depiler()` | ferme la modale la plus interne ; sans effet si la pile est vide |
| `vider_modales()` | ferme tout |
| `session()` | fabrique la `Session` à passer au code testé |
| `journal` | le `Journal` de ce monde |

```python
from sapharness import Ecran, Monde

monde = Monde()
monde.ajouter_ecran(Ecran("premier"))
monde.ajouter_ecran(Ecran("second"))
assert monde.ecran_courant == "premier"        # le premier ajouté

monde.aller("second")
monde.empiler("premier")                        # une modale peut réutiliser un écran
assert monde.modales == ["premier"]
monde.depiler()
monde.depiler()                                 # dépiler à vide ne lève pas
assert monde.modales == []
```

### `Ecran`

Un écran = un programme, un dynpro, des contrôles. Les trois méthodes de
déclaration renvoient `self`, donc s'enchaînent.

| Méthode | Signature |
|---|---|
| `bouton` | `(identifiant, action=None, actif=True, libelle="")` |
| `champ` | `(identifiant, texte="", au_changement=None)` |
| `objet` | `(identifiant, instance)` — pour un `TableControl` ou une `Grille` |

`action` est appelée à la pression : c'est par elle qu'on décrit ce que SAP
ferait (changer d'écran, ouvrir une modale, remplir la barre d'état).

```python
from sapharness import Ecran, ErreurSimulee, Monde

monde = Monde()
detail = (Ecran("detail", programme="SAPLCPDO", dynpro=3370, transaction="IA08")
          .bouton("wnd[0]/tbar[1]/btn[35]", action=lambda: monde.aller("synthese"))
          .bouton("wnd[0]/tbar[0]/btn[11]", actif=False, libelle="Sauvegarder")
          .champ("wnd[0]/usr/txtPLPOD-LTXA1", texte="Serrage"))
monde.ajouter_ecran(detail)
monde.ajouter_ecran(Ecran("synthese", "SAPLCPDI", 3400))
session = monde.session()

assert session.findById("wnd[0]/usr/txtPLPOD-LTXA1").Text == "Serrage"

# Un bouton déclaré inactif lève, comme un contrôle grisé en SAP.
try:
    session.findById("wnd[0]/tbar[0]/btn[11]").press()
    raise AssertionError("un bouton inactif aurait dû lever")
except ErreurSimulee:
    pass

session.findById("wnd[0]/tbar[1]/btn[35]").press()
assert monde.ecran_courant == "synthese"
```

La barre d'état se pose directement sur l'écran, et se lit toujours par
`wnd[0]/sbar` :

```python
from sapharness import Ecran, Monde

monde = Monde()
ecran = Ecran("liste", "RIPLKO10", 1000)
ecran.statusbar = ("E", "Aucune donnée trouvée")
monde.ajouter_ecran(ecran)

barre = monde.session().findById("wnd[0]/sbar")
assert (barre.MessageType, barre.Text) == ("E", "Aucune donnée trouvée")
```

### `Session`

Ce que reçoit le code testé.

| Membre | Comportement |
|---|---|
| `findById(id)` | résout sur `wnd[0]` = écran courant, `wnd[n]` = n-ième modale |
| `Info` | `.Program`, `.ScreenNumber`, `.Transaction` de l'écran **courant** |
| `Busy` | toujours `False` |
| `Children` | collection minimale, présente pour que le code qui la sonde ne casse pas |

Un contrôle absent, ou une fenêtre non empilée, lève `ErreurSimulee` — c'est
l'équivalent de l'exception COM :

```python
from sapharness import Ecran, ErreurSimulee, Monde

monde = Monde()
monde.ajouter_ecran(Ecran("editeur", "SAPLSTXX", 2101))
session = monde.session()

assert (session.Info.Program, session.Info.ScreenNumber) == ("SAPLSTXX", 2101)
assert session.Busy is False

for absent in ("wnd[0]/usr/txtINEXISTANT", "wnd[1]/tbar[0]/btn[0]"):
    try:
        session.findById(absent)
        raise AssertionError(f"{absent} aurait dû lever")
    except ErreurSimulee:
        pass
```

### `Controle`

`Text` et `Selected` respectent la casse COM, et les graphies minuscules
(`text`, `selected`) sont le **même** attribut.

| Geste | Action journalisée |
|---|---|
| `Text = ...` | `saisie` |
| `Selected = ...` | `coche` |
| `press()` | `press` |
| `select()` | `select` |
| `setFocus()` | `focus` |

```python
from sapharness import Ecran, Monde

monde = Monde()
monde.ajouter_ecran(Ecran("ia08", "RIPLKO10", 1000)
                    .champ("wnd[0]/usr/ctxtWERKS-LOW")
                    .bouton("wnd[0]/usr/chkPN_IHAN"))
session = monde.session()

champ = session.findById("wnd[0]/usr/ctxtWERKS-LOW")
champ.text = "1000"                    # graphie minuscule : même propriété
assert champ.Text == "1000"

assert monde.journal.compter("saisie", "wnd[0]/usr/ctxtWERKS-LOW") == 1
```

### `TableControl`

Index de ligne **visible**, défilement explicite. Une cellule s'adresse par
`<table>/<gabarit><COLONNE>[colonne, ligne_visible]`, avec `txt`, `ctxt` ou
`chk` comme gabarit. Une valeur booléenne remonte en case à cocher.

| Membre | Sens |
|---|---|
| `VisibleRowCount` | hauteur de la fenêtre ; au-delà, `findById` lève |
| `RowCount` | `max(nombre de lignes, visibles)` — **inclut les lignes vides de saisie** |
| `VerticalScrollbar.Position` | origine du défilement, en index absolu |
| `VerticalScrollbar.Maximum` | `RowCount - 1` |
| `Columns` | collection de colonnes, `.Count` et `.Name` |

```python
from sapharness import Ecran, ErreurSimulee, Monde, TableControl

monde = Monde()
table = TableControl("wnd[0]/usr/tbl", ["VORNR", "TXTKZ"],
                     [{"VORNR": f"{10 * (i + 1):04d}", "TXTKZ": i == 0}
                      for i in range(12)],
                     visibles=5, monde=monde)
monde.ajouter_ecran(Ecran("synthese", "SAPLCPDI", 3400)
                    .objet("wnd[0]/usr/tbl", table))
session = monde.session()

assert session.findById("wnd[0]/usr/tbl/txtVORNR[0,0]").Text == "0010"
assert session.findById("wnd[0]/usr/tbl/chkTXTKZ[1,0]").Selected is True

# Au-delà de la fenêtre visible : ça lève. C'est ce qui force à défiler.
try:
    session.findById("wnd[0]/usr/tbl/txtVORNR[0,7]")
    raise AssertionError("hors fenêtre visible : aurait dû lever")
except ErreurSimulee:
    pass

# Défiler déplace l'origine ; le rang visible 0 n'est plus la première ligne.
table.VerticalScrollbar.Position = 5
assert session.findById("wnd[0]/usr/tbl/txtVORNR[0,0]").Text == "0060"
```

Les lignes vides de saisie se lisent comme du texte vide — jamais comme une
erreur. C'est ce qui permet de tester l'arrêt de boucle sur ligne vide :

```python
from sapharness import Ecran, Monde, TableControl

monde = Monde()
table = TableControl("wnd[0]/usr/tbl", ["VORNR"],
                     [{"VORNR": "0010"}, {"VORNR": "0020"}, {"VORNR": "0030"}],
                     visibles=20, monde=monde)
monde.ajouter_ecran(Ecran("synthese", "SAPLCPDI", 3400)
                    .objet("wnd[0]/usr/tbl", table))
session = monde.session()

assert table.RowCount == 20                     # 3 opérations, 20 lignes annoncées
assert session.findById("wnd[0]/usr/tbl/txtVORNR[0,3]").Text == ""

lues = []
for rang in range(table.VisibleRowCount):
    valeur = session.findById(f"wnd[0]/usr/tbl/txtVORNR[0,{rang}]").Text
    if not valeur:
        break                                   # arrêt sur ligne vide
    lues.append(valeur)
assert lues == ["0010", "0020", "0030"]
```

### `Grille`

L'ALV. Index **absolu**, aucun ID par cellule, aucun défilement.

```python
from sapharness import ErreurSimulee, Grille

grille = Grille("wnd[0]/usr/cntlGRID1/shellcont/shell", ["PLNNR", "PLNAL"],
                [{"PLNNR": f"MEMAC{100 + i}", "PLNAL": "1"} for i in range(60)])

assert grille.RowCount == 60
assert grille.GetCellValue(57, "PLNNR") == "MEMAC157"   # sans défiler
assert grille.ColumnOrder == ["PLNNR", "PLNAL"]

try:
    grille.GetCellValue(60, "PLNNR")
    raise AssertionError("ligne hors grille : aurait dû lever")
except ErreurSimulee:
    pass
```

### `Journal`

| Méthode | Usage |
|---|---|
| `noter(ecran, action, cible)` | ajoute une entrée à la main (gestes hors GUI : `save`, `dump`…) |
| `actions(action=None)` | les entrées `(ecran, action, cible)`, filtrées |
| `compter(action, cible=None)` | combien de fois |
| `assert_jamais(cible, hors_ecran=…)` | échoue si `cible` a été actionnée ailleurs |
| `assert_au_plus(action, nombre)` | échoue au-delà de `nombre` |
| `resume()` | trace lisible, pour le message d'échec |

### `ErreurSimulee`

L'unique exception du simulateur : contrôle absent, fenêtre non empilée,
ligne hors du tableau, contrôle inactif. Elle joue le rôle de l'exception COM.
Elle ne signale **jamais** un défaut de logique métier — ceux-là sont
silencieux, et c'est le `Journal` qui les révèle.

---

## 5. Écrire un scénario : la recette

1. **Construire le monde** dans l'état exact qui a produit le bug. Un bug =
   un scénario.
2. **Passer `monde.session()`** au code testé — jamais le `Monde` lui-même :
   le code de production ne connaît que la session.
3. **Asserter sur le `Journal` d'abord**, sur les valeurs ensuite. Un résultat
   juste obtenu par un geste dangereux reste un bug.
4. **Nommer le test par le défaut qu'il empêche**, pas par la méthode
   appelée : `test_bouton_ambigu_hors_de_son_ecran_detecte`.

---

## 6. Catalogue d'invariants

Chaque ligne renvoie au piège correspondant de [TRAPS.md](TRAPS.md).

| Piège | Invariant à écrire |
|---|---|
| 2 — l'import ajoute au lieu de remplacer | `journal.compter("import", cible) <= 1` après vidage vérifié |
| 3 — les flèches ne parcourent que le marqué | `press` sur `btn[34]` précède tout `btn[17]` |
| 5 — les indices changent de sens | `journal.assert_jamais("wnd[0]/tbar[1]/btn[7]", hors_ecran="detail")` |
| 7 — aucun comptage n'est fiable | le nombre d'opérations lues ne dépend d'aucun champ compteur |
| 9 — cases rémanentes | les trois cases reçoivent une valeur explicite : `compter("coche") == 3` |
| 11 — sélection non scriptable | après échec, `compter("import") == 0` |
| 12 — presse-papier partagé | la sentinelle survivante donne un texte vide, jamais le résidu |
| dry-run | `journal.compter("saisie") == 0` **et** `compter("save") == 0` |

Les deux premiers gestes se journalisent à la main via `noter`, puisqu'ils
n'ont pas de contrôle GUI dédié.

L'invariant le plus rentable du lot, en démonstration : `btn[7]` vaut
« opération suivante » sur le détail et « **Insérer une opération** » sur la
synthèse.

```python
from sapharness import Ecran, Monde

monde = Monde()
monde.ajouter_ecran(Ecran("detail", "SAPLCPDO", 3370)
                    .bouton("wnd[0]/tbar[1]/btn[7]"))
monde.ajouter_ecran(Ecran("synthese", "SAPLCPDI", 3400)
                    .bouton("wnd[0]/tbar[1]/btn[7]"))
session = monde.session()

monde.aller("detail")
session.findById("wnd[0]/tbar[1]/btn[7]").press()          # légitime
monde.journal.assert_jamais("wnd[0]/tbar[1]/btn[7]", hors_ecran="detail")

monde.aller("synthese")
session.findById("wnd[0]/tbar[1]/btn[7]").press()          # insère une opération !
try:
    monde.journal.assert_jamais("wnd[0]/tbar[1]/btn[7]", hors_ecran="detail")
    raise AssertionError("la pression fautive aurait dû être détectée")
except AssertionError as echec:
    assert "hors de l'ecran" in str(echec)
```

---

## 7. Les douze scénarios de non-régression

Chacun correspond à un bug rencontré en production. Ils doivent survivre à
toute réécriture. La colonne « monde à construire » dit comment les poser avec
les primitives ci-dessus.

| # | Scénario | Monde à construire | Ce qu'on assère |
|---|---|---|---|
| 1 | compteur menteur | `TableControl` à 3 lignes + champ `RC27X-ENTRIES` valant `"1"` | 3 opérations traitées |
| 2 | deux sous-écrans | deux `Ecran` détail, préfixes `…:3300` et `…:3305` | résolution par suffixe, aucune sortie de boucle |
| 3 | lignes vides | 3 lignes, `visibles=20` | arrêt sur ligne vide, pas sur `RowCount` |
| 4 | tableau laissé défilé | `VerticalScrollbar.Position = 4` avant l'appel | le scan remet l'origine à 0 |
| 5 | opération piégée | une `action` qui empile l'éditeur sans le dépiler | F3 émis, opérations suivantes traitées |
| 6 | sélection totale défaillante | `btn[34]` sans effet + cible non vide | refus avant import, `compter("import") == 0` |
| 7 | import qui concatène | zone cible non vide | vidage vérifié avant écriture |
| 8 | cible portant le texte source | même empreinte des deux côtés | traité, non protégé (piège 1) |
| 9 | `--ecraser` absent | cible remplie | `compter("saisie") == 0`, ligne tracée au rapport |
| 10 | toolbar exposant `Text` | contrôle `GuiShell` sans `SubType == "TextEdit"` | non retenu comme éditeur |
| 11 | copie muette | sentinelle posée avant copie | texte vide, jamais le résidu |
| 12 | dry-run | monde complet, option dry-run | `compter("saisie") == 0` et `compter("save") == 0` |

Les scénarios 1, 3 et 4 sont couverts aujourd'hui par
`tests/test_sapmock.py`. Les autres attendent le code qu'ils doivent
protéger : ils ne sont pas écrivables tant que le pipeline correspondant
n'existe pas, et les inventer à vide donnerait une fausse couverture.

---

## 8. Ce que le simulateur ne modélise pas

**La section la plus importante de ce guide.** Un harness inspire confiance ;
une confiance mal placée est pire que pas de test du tout. Chacune des limites
ci-dessous est vérifiée par les blocs exécutés — elles sont réelles, pas
supposées.

### 8.1 Les écritures ne persistent pas

`findById` fabrique un contrôle **neuf** à chaque appel. Écrire dans un champ,
puis le relire, rend la valeur initiale. Le geste est journalisé ; il n'a pas
d'effet mémorisé.

```python
from sapharness import Ecran, Monde

monde = Monde()
monde.ajouter_ecran(Ecran("ia08", "RIPLKO10", 1000)
                    .champ("wnd[0]/usr/ctxtWERKS-LOW", texte="1000"))
session = monde.session()

session.findById("wnd[0]/usr/ctxtWERKS-LOW").Text = "2000"
assert session.findById("wnd[0]/usr/ctxtWERKS-LOW").Text == "1000"   # pas 2000
assert monde.journal.compter("saisie", "wnd[0]/usr/ctxtWERKS-LOW") == 1
```

**Conséquence.** Ne jamais asserter par relecture. Un test qui vérifie
« le champ contient bien ce que j'ai écrit » échouera toujours, et un test qui
vérifie « le champ est resté vide » réussira toujours — pour la mauvaise
raison. **Le `Journal` est le seul témoin d'une écriture.** Pour qu'une saisie
ait un effet, la lui donner explicitement via `action`.

### 8.2 La `Grille` ne journalise rien

`Grille` ne reçoit pas le monde : `setCurrentCell`, `selectedRows` et
`GetCellValue` n'apparaissent dans aucune trace. Les invariants de gestes ne
couvrent pas l'ALV.

```python
from sapharness import Grille, Monde

monde = Monde()
grille = Grille("wnd[0]/usr/cntlGRID1/shellcont/shell", ["PLNNR"],
                [{"PLNNR": "MEMAC100"}])
grille.setCurrentCell(0, "PLNNR")
grille.selectedRows = "0"
assert monde.journal.entrees == []          # aucun geste tracé
```

### 8.3 `wnd[0]/sbar` lit toujours l'écran courant

Même modale ouverte, la barre d'état résolue est celle de l'écran de fond. Un
message porté par une modale doit être posé sur l'écran courant pour être vu.

```python
from sapharness import Ecran, Monde

monde = Monde()
fond = Ecran("fond", "SAPLCPDI", 3400)
fond.statusbar = ("S", "message du fond")
modale = Ecran("modale", "SAPLSTXX", 0)
modale.statusbar = ("W", "message de la modale")
monde.ajouter_ecran(fond)
monde.ajouter_ecran(modale)
monde.empiler("modale")

assert monde.session().findById("wnd[0]/sbar").Text == "message du fond"
```

### 8.4 Les autres angles morts

- **Aucune notion de temps.** `Busy` vaut toujours `False` ; les attentes et
  les resynchronisations ne se testent pas ici.
- **Aucun typage de saisie.** Un champ accepte n'importe quelle chaîne ;
  longueurs, formats et conversions SAP ne sont pas simulés.
- **Aucune modale spontanée.** SAP en ouvre à l'improviste ; ici une modale
  n'apparaît que si une `action` l'empile. Le comportement face aux popups
  inconnus se teste en les empilant délibérément.
- **`Info` suit l'écran courant, pas la modale.** Comme `sbar`.
- **Aucun canal externe.** Fichier RTF et presse-papier sont hors simulateur :
  ils relèvent de `sapharness/backends/`, à construire, et se testent par
  substitution d'implémentation.

---

## 9. Charger la carte des contrôles

Les identifiants sont des **données**. Ils changent avec le système, le
mandant et la release ; les coder en dur, c'est refaire le relevé à chaque
portage.

```python
from sapharness import charger_carte

carte = charger_carte()                     # cartes/sap_map.yaml par défaut
assert carte["systeme"]["nom"] == "K75"
assert carte["operations_synthese"]["indexation"] == "visible_avec_defilement"
assert carte["ia08_resultat"]["indexation"] == "absolue"

marquer_tout = carte["operations_synthese"]["boutons"]["marquer_tout"]
assert marquer_tout == "wnd[0]/tbar[1]/btn[34]"
```

`charger_carte` n'injecte aucune valeur par défaut : une clé absente lève chez
l'appelant plutôt que d'être devinée. Une carte de test se passe en argument —
`charger_carte(chemin)` — ce qui permet de simuler un autre mandant sans
toucher au code.

---

## 10. Faire évoluer le harness

**Toute mécanique piège ajoutée vient avec un test qui échoue sans elle.** Le
simulateur n'a de valeur que par ce qu'il rend détectable ; une fonctionnalité
sans test de détection est du décor.

Trois règles de méthode, héritées d'erreurs réelles :

1. **Un patch par remplacement de texte vérifie que son ancre existe et est
   unique**, puis relance la suite. Un `str.replace` qui ne trouve rien
   annonce « appliqué » sans rien faire.
2. **Supprimer une fonction se fait par découpe AST**, jamais par intervalle
   de lignes : un intervalle emporte du code vivant.
3. **Le recorder est la vérité terrain.** Quand un comportement résiste,
   demander un enregistrement plutôt que théoriser — en sachant qu'il capture
   les actions, pas les lectures ni les sélections souris.

---

## 11. Comment ce guide est vérifié

`tests/test_documentation.py` fait deux choses :

- il extrait **tous** les blocs `python` de ce fichier et les exécute dans
  l'ordre, dans un espace de noms partagé — comme le lecteur les lit. Les
  assertions qu'ils contiennent sont la vérification ;
- il contrôle que **tout chemin de fichier cité** dans la documentation —
  ce guide, le README, HARNESS.md, TRAPS.md — existe réellement dans le dépôt.

Les blocs des autres documents ne sont **pas** exécutés : ce sont des
fragments d'illustration délibérément incomplets, et les rendre exécutables
les alourdirait au détriment de la lecture. Ce guide est donc le seul endroit
où un exemple engage le dépôt.

Un bloc qui ne peut pas s'exécuter — parce qu'il décrit du code à construire —
porte `# guide: skip` en première ligne, et n'est alors pas une garantie. Il
n'y en a aujourd'hui aucun dans ce fichier.

```bash
python -m unittest discover -s tests
```
