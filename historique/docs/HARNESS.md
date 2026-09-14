# Harness de test pour le scripting SAP GUI

## Le problème que ce harness résout

Le scripting SAP GUI a une propriété désagréable : **les erreurs les plus
graves ne lèvent aucune exception.** Un bouton pressé sur le mauvais écran
insère une opération. Un compteur mal lu arrête une boucle après le premier
élément. Un contrôle mal identifié retourne `SAP.Toolbar.1` comme s'il
s'agissait d'un texte métier. Le programme continue, produit un résultat
plausible, et le défaut se découvre au contrôle qualité — ou jamais.

Tester contre le vrai SAP est impraticable : c'est lent, ça nécessite un
système, et ça écrit dans des données de production. Le harness rend ces
erreurs détectables hors SAP, en quelques secondes.

## Ce qui existe déjà

`sapharness/sapmock.py` est autonome et se teste lui-même :

```bash
python sapharness/sapmock.py
```

Il fournit :

| Composant | Rôle |
|---|---|
| `Monde` | état global : écran courant, pile de modales, journal |
| `Ecran` | programme, dynpro, contrôles — un même ID de bouton peut exister sur plusieurs écrans avec des effets différents |
| `TableControl` | index de ligne **visible**, défilement explicite, cellules adressées par ID |
| `Grille` | ALV, index **absolu**, `GetCellValue` |
| `Session` | objet passé au code testé : `findById`, `Info`, `Busy` |
| `Journal` | trace des gestes, avec assertions d'invariants |

Les mécaniques pièges sont **dans le simulateur**. Demander une ligne au-delà
de la fenêtre visible d'un table control lève, comme SAP. Lire une ligne
lointaine d'un ALV fonctionne, comme SAP. Un code qui confond les deux échoue
au test.

## Les invariants, cœur du dispositif

Les assertions les plus utiles ne portent pas sur le résultat produit mais sur
**les gestes effectués**. Trois exemples tirés de bugs réels :

```python
# btn[7] = "opération suivante" sur le détail, "Insérer" sur la synthèse
journal.assert_jamais("wnd[0]/tbar[1]/btn[7]", hors_ecran="detail")

# SAP enregistre la gamme entière : une sauvegarde par gamme, pas par texte
journal.assert_au_plus("save", 1)

# en dry-run, aucune écriture ne doit avoir lieu
assert journal.compter("saisie") == 0
```

Ces trois assertions auraient détecté, hors SAP, trois défauts qui ont
effectivement atteint la production pendant le développement d'EagleLoader.

## Ce qu'il reste à construire

### 1. Convertisseur enregistrement → scénario

Les fichiers `.vbs` produits par le SAP GUI Recorder sont la **vérité
terrain** : ils décrivent une session manuelle qui a fonctionné. Un
convertisseur qui les transforme en séquence d'actions attendues permettrait
de comparer ce que fait le programme à ce qu'a fait l'humain.

Format d'entrée : UTF-16LE, lignes `session.findById("...").press()`,
`.text = "..."`, `.sendVKey(n)`, `.select()`.

Sortie utile : liste ordonnée `(action, cible)`, à comparer au `Journal`.

Limite à documenter : le recorder enregistre les **actions**, pas les
lectures ni les sélections souris. Une absence dans un enregistrement ne
prouve pas qu'un geste n'a pas eu lieu.

### 2. Générateur de simulateur depuis les cartes d'exploration

Les fichiers `explo_*.md` listent les contrôles réels d'un écran avec leur
type et leur ID. Les convertir directement en `Ecran` peuplé éviterait de
retaper les IDs à la main — et supprimerait les divergences entre le
simulateur et la réalité.

### 3. Scénarios de non-régression à conserver

Chacun correspond à un bug rencontré. Ils doivent survivre à toute
réécriture :

| Scénario | Ce qu'il protège |
|---|---|
| Gamme à 3 opérations, `RC27X-ENTRIES` annonce 1 | le parcours ne dépend d'aucun compteur |
| Opérations sur deux sous-écrans différents (3300 et 3305) | résolution des champs par suffixe |
| Table control avec 20 lignes vides après 3 opérations | arrêt sur lignes vides, pas sur `RowCount` |
| Fenêtre à 8 lignes visibles, tableau laissé défilé | remise à zéro du défilement avant scan |
| Une opération piégée sur l'éditeur | récupération F3, les suivantes sont traitées |
| Sélection totale défaillante + zone non vide | refus avant import, cible intacte |
| Import qui concatène | vidage vérifié avant écriture |
| Cible portant le texte source | reconnu comme cas à traiter, pas comme protection |
| `--ecraser` absent + cible remplie | rien n'est écrit, ligne tracée |
| Toolbar exposant `Text` | non retenue comme éditeur |
| Copie muette + presse-papier occupé | sentinelle, texte vide et non résidu |
| Dry-run | aucune saisie, aucune sauvegarde |

### 4. Audit statique systématique

Indépendant du simulateur, et il a rattrapé plusieurs erreurs de refactoring :

```python
# tout appel de fonction se résout-il ?
# chaque commande reçoit-elle tous les attributs qu'elle lit ?
# reste-t-il du code mort après suppression ?
```

Le cas le plus coûteux rencontré : un `Namespace` construit à la main auquel
manquait un attribut ajouté au CLI. 152 échecs identiques en production, pour
une erreur détectable en une seconde par analyse de l'AST.

**Règle de méthode qui en découle.** Tout patch appliqué par remplacement de
texte doit vérifier que l'ancre existe et est unique, puis relancer l'audit.
Un `str.replace` silencieux qui ne trouve rien annonce « appliqué » sans rien
faire — et un découpage par intervalle de lignes peut emporter du code vivant.
Préférer la découpe par AST pour supprimer une fonction.

## Découpage modulaire proposé

Le programme actuel est monolithique — un choix délibéré au départ, pour
éviter les problèmes d'import chez l'utilisateur. Pour la suite :

```
sapgui/        connexion, session, attente, statusbar, popups, resynchronisation
screens/       un adaptateur par écran (ia08, synthese_operations, detail_operation,
               editeur_sapscript), chargés depuis sap_map.yaml
transport/     échange de texte : controle direct | fichier RTF | presse-papier,
               derrière une interface unique lire()/ecrire()
rtf/           conversion RTF ↔ texte, testable sans SAP
runner/        boucle par lot, journal, reprise, rapports, UI terminal
diagnostics/   dump, menus, champs, ops
```

Le point le plus important de ce découpage est `transport` : c'est là qu'on a
le plus tâtonné, et l'interchangeabilité des trois voies est ce qui a permis
de basculer sans réécrire le reste.

`screens` doit charger `sap_map.yaml` plutôt que porter des IDs en dur : c'est
ce qui rend le portage vers un autre système ou mandant trivial.
