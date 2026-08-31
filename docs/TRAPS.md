# Pièges SAP GUI Scripting — règles issues du terrain

Chacun de ces pièges a coûté au moins un cycle complet de développement sur
le projet EagleLoader. Ils partagent une propriété : **ils ne produisent pas
d'erreur.** Le programme continue, produit un résultat plausible, et le
défaut n'apparaît qu'au contrôle qualité — ou jamais.

Format : symptôme observé, cause réelle, règle à appliquer.

---

## 1. `TXTSP` fige la langue du texte long

**Symptôme.** Connecté en espagnol, l'éditeur de texte long ouvre le texte
anglais. Les modifications repartent en anglais. L'espagnol n'est jamais créé.

**Cause.** `PLPO-TXTSP` (opération) et `PLKO-TXTSP` (en-tête) stockent la
langue dans laquelle le texte a été saisi. La transaction lit le texte avec
cette langue, **pas avec la langue de connexion**. Ce champ n'est maintenable
ni par transaction ni par BAPI.

**Règle.** Pour basculer un texte de langue sans ABAP : supprimer le texte,
sauvegarder la gamme (`TXTSP` repasse à blanc), rouvrir, écrire, sauvegarder.
Deux entrées complètes et deux sauvegardes par opération.

**Conséquence à ne pas manquer.** Tant que `TXTSP` pointe sur la langue
source, la cible *affiche le texte source*. Un contrôle naïf « la cible n'est
pas vide, je protège » ferait sauter tout le lot. Comparer l'empreinte de la
cible à celle de la source : si elles coïncident, c'est le cas à traiter, pas
une traduction à protéger.

---

## 2. L'import de texte ajoute, il ne remplace pas

**Symptôme.** Après injection, le texte cible contient l'ancien suivi du
nouveau.

**Cause.** `Texte > Téléchargement (importer)` concatène le fichier à la fin
du contenu existant.

**Règle.** Ne jamais importer sur une zone non vide sans l'avoir vidée **et
vérifié** qu'elle est vide. Le vidage se vérifie en retéléchargeant.

---

## 3. Les flèches ne parcourent que les opérations marquées

**Symptôme.** Une gamme à plusieurs opérations n'en rend qu'une. « Opération
suivante » ne change rien, ce qui ressemble à une fin de gamme.

**Cause.** Le périmètre de navigation du détail est la **sélection** faite sur
la synthèse. Entrer par F2 sur une cellule réduit ce périmètre à cette seule
opération.

**Règle.** Marquer tout (`btn[34]`) puis ouvrir le détail (`btn[17]`). Jamais
F2 sur une cellule si l'on compte naviguer ensuite.

---

## 4. Le numéro de sous-écran varie avec le type d'opération

**Symptôme.** Le parcours s'arrête après la première opération, sur les
gammes qui mélangent activités internes et externes.

**Cause.** L'ID du détail contient le numéro du sous-écran
(`subOPR_DETAIL:SAPLCPDO:3300`), et ce numéro change selon le type
d'opération. Un ID figé cesse de résoudre, la lecture lève, la boucle sort.

**Règle.** Résoudre les champs par **suffixe** (`txtPLPOD-VORNR`) dans l'arbre
de `wnd[0]/usr`, jamais par un chemin complet figé. Mémoriser le préfixe
trouvé, le réinitialiser à chaque objet.

---

## 5. Les indices de boutons changent de sens selon l'écran

| Bouton | Synthèse | Détail | Éditeur |
|---|---|---|---|
| `btn[7]` | **Insérer une opération** | Opération suivante | Afficher formats |
| `btn[35]` | — | Retour synthèse | Supprimer commande |
| `btn[8]` | Démarquer tout | Dernière opération | — |

**Règle.** Toute pression d'un bouton ambigu est précédée d'une vérification
d'écran, avec récupération (F3) si l'on est resté sur l'éditeur. Sans ce
garde, une boucle insère une opération à chaque tour, silencieusement.

---

## 6. Deux mécaniques de tableau à ne pas confondre

**ALV** (`GuiShell` / GridView) : pas d'ID par cellule. `grid.GetCellValue(ligne,
"COL")`, index **absolu**, aucun défilement.

**Table control** (`GuiTableControl`) : chaque cellule est un objet GUI avec
son ID, index de ligne **visible** (0..VisibleRowCount-1). Au-delà :
`table.VerticalScrollbar.Position = n` puis repartir à 0.

**Règle.** Traiter les deux séparément. Et remettre le défilement à zéro avant
tout scan : un tableau laissé défilé fait lire des lignes lointaines à un scan
qui croit repartir du début.

---

## 7. Aucun comptage n'est fiable

- `RowCount` compte les lignes vides de saisie du table control.
- La barre de défilement aussi.
- `RC27X-ENTRY_ACT` est l'entrée **courante**, pas le total : elle vaut 1 à
  l'ouverture.
- `RC27X-ENTRIES` peut être illisible, ou contenir plusieurs nombres
  (« 1 / 23 » — concaténer les chiffres donnerait 123).

**Règle.** Ne jamais piloter une boucle par un compteur. Avancer tant que SAP
avance, s'arrêter quand l'objet affiché ne change plus. Les compteurs servent
à signaler un écart dans le rapport, jamais à décider.

---

## 8. Un résultat unique saute l'écran de liste

**Symptôme.** « Grille ALV introuvable » alors que la sélection a fonctionné.

**Cause.** Quand la sélection ne remonte qu'une ligne, SAP ouvre directement
l'objet au lieu d'afficher la liste.

**Règle.** Après exécution, chercher d'abord l'écran de destination, puis la
grille. Gérer les deux atterrissages.

---

## 9. Les cases de sélection sont rémanentes

**Symptôme.** Une extraction de gammes poste technique remonte aussi des
gammes générales.

**Cause.** SAP conserve les valeurs d'écran d'un appel à l'autre. Cocher la
bonne case sans décocher les autres laisse la sélection précédente active.

**Règle.** Positionner **toutes** les options explicitement à chaque appel,
`True` pour celle qu'on veut, `False` pour les autres.

**Corollaire.** Sans aucune case cochée, IA08 ne remonte rien **et n'émet
aucun message**. L'absence de résultat n'est pas une preuve d'absence de
données.

---

## 10. L'éditeur SAPscript n'est pas adressable

**Symptôme.** `findById` ne trouve aucun contrôle d'édition. Une recherche
d'arbre trop permissive retourne `SAP.Toolbar.1` comme « texte ».

**Cause.** L'écran ne contient que des boutons. Et les `GuiShell` répondent à
la propriété `Text` avec leur nom de classe ActiveX.

**Règle.** N'accepter comme éditeur que `GuiTextedit` ou `GuiShell` de
`SubType == "TextEdit"`. **Jamais « tout shell qui expose Text ».** À défaut,
passer par un canal externe : fichier RTF (préféré) ou presse-papier.

---

## 11. La sélection de texte n'est pas scriptable

**Symptôme.** Copier et Couper ne font rien. Un enregistrement du recorder ne
montre aucune trace de la sélection faite à la souris.

**Cause.** La sélection dans le contrôle d'édition échappe au scripting SAP.

**Règle.** La fiabilité ne vient pas du mécanisme mais du contrôle. Essayer en
cascade (menu de suppression, sélection totale + Couper, Ctrl+A système), et
**retélécharger après chaque tentative** pour prouver le résultat. Trois
essais, puis refus explicite.

---

## 12. Le presse-papier est un état global partagé

**Symptôme.** Un texte identique ressort sur toutes les opérations.

**Cause.** Une copie qui échoue silencieusement laisse le contenu précédent en
place, qui est relu comme s'il était le texte de l'opération.

**Règle.** Écrire une sentinelle avant chaque copie. Si elle survit, la copie
n'a rien produit : traiter comme vide, **jamais** comme le résidu. Et ajouter
un détecteur de fin de run : si un même texte non vide domine l'extraction,
c'est un symptôme, pas une donnée.

---

## Règles transverses

**Un repli ne doit jamais avaler un refus.** Si un mécanisme A échoue et qu'on
bascule sur B, un *refus délibéré* émis par A serait rattrapé par la bascule
et retenté par un mécanisme moins sûr. Utiliser une exception distincte pour
les refus, que les replis laissent passer.

**Échouer bruyamment sur l'inconnu.** Une modale non reconnue fait échouer
l'objet en cours. La liste des popups sûrs se remplit depuis les dry-runs
observés, jamais par anticipation.

**Le recorder est la vérité terrain.** Un enregistrement d'une session
manuelle réussie vaut mieux que n'importe quelle déduction sur les IDs. Quand
un comportement résiste, demander un enregistrement plutôt que théoriser.

**Ce que le recorder ne capture pas.** Il enregistre les actions, pas les
lectures ni les sélections souris. Une absence dans un enregistrement ne
prouve pas qu'un geste n'a pas eu lieu.
