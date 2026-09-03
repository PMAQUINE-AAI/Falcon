# Backlog V1 — état des lots

Fichier de pilotage de la boucle de travail. Il est versionné parce qu'un état
gardé en session ne survivrait pas au conteneur : c'est ici, et nulle part
ailleurs, que se lit l'avancement.

Référence : [SPEC_FALCON.md](../SPEC_FALCON.md). Les numéros de section entre
parenthèses y renvoient.

## Protocole d'une itération

1. Lire ce fichier, prendre le **premier lot non fait dont les dépendances sont
   satisfaites**. Un lot par itération, jamais deux à moitié.
2. L'implémenter, avec ses tests.
3. Lancer la vérification. Si elle n'est pas verte : ni commit, ni case cochée.
4. Commiter, pousser sur la branche courante, cocher la ligne ici même dans le
   même commit.

```bash
python -m unittest discover -s tests -t .                        # FALCON
python -m unittest discover -s historique/tests -t historique    # l'archive ne régresse pas
```

## Garde-fous

- `historique/` n'est jamais modifié.
- **Aucun comportement SAP n'est inventé.** Un lot qui exige une trace réelle
  ou un système réel s'arrête et le dit, plutôt que de deviner. Un mock nourri
  d'hypothèses confirme les hypothèses (§3.7).
- Tout écart de périmètre par rapport à la spec est inscrit au §8 dans le même
  commit que le code qui l'introduit.
- Une pipeline ne peut jamais désactiver une garde (§5.2). Si un lot rend ça
  possible, le lot est faux.

## Lots

Légende : `[ ]` à faire · `[~]` en cours · `[x]` fait · `[!]` bloqué

| # | État | Lot | Dépend de | Critère d'acceptation |
|---|---|---|---|---|
| 0 | `[x]` | Squelette : arborescence, `pyproject.toml`, tests de frontière, CI | — | la vérification est verte sur un dépôt neuf |
| 1 | `[x]` | Modèles et interface de couture, erreurs typées (§3.4) | 0 | surface épinglée à 15 méthodes ; une implémentation partielle ne s'instancie pas ; `Refus` n'hérite pas d'`Echec` |
| 2 | `[ ]` | Journal : schéma JSONL, écriture append-only, reprise (§3.3) | 1 | reprise après interruption simulée : aucun item retraité, aucun perdu ; un item interrompu **après** sauvegarde sort en `douteux`, jamais rejoué |
| 3 | `[ ]` | Taxonomie : registre YAML, classement, inconnu bloquant (§5.1) | 2 | un message non répertorié bloque et produit un dump ; aucun joker ni réglage permissif n'existe ; ambiguïté entre deux entrées détectée **au chargement** |
| 4 | `[ ]` | Les cinq gardes + dérogations, sur un driver factice (§5) | 1, 3 | chaque garde a un test qui échoue si on la retire ; une pipeline ne peut en désactiver aucune |
| 5 | `[ ]` | Rapport de fin + réexport des KO au format d'entrée (§4.7) | 2 | aller-retour prouvé : lire un jeu, tout marquer KO, réexporter, relire ⇒ identique champ à champ |
| 6 | `[!]` | Parseur de trace VBScript (§4.1) | 0, **traces réelles** | rejoue les traces fournies ; formes `.press` et `.press()` couvertes |
| 7 | `[ ]` | Brouillon de pipeline depuis une trace (§4.3) | 6 | une trace produit un YAML chargeable par le lot 8 |
| 8 | `[ ]` | Pipeline : modèle, chargement, validation (§3.2) | 1 | un YAML invalide échoue avec un message situé, jamais en silence |
| 9 | `[ ]` | Catalogue : modèle, empreinte de variante, dépôt YAML (§3.1) | 1 | deux rendus du même dynpro avec des `id` différents donnent deux variantes |
| 10 | `[ ]` | Moteur itératif + chaîne de pipelines (§3.3) | 2, 4, 8 | un KO au milieu du lot ne l'interrompt pas ; une garde d'identité arrête la chaîne |
| 11 | `[ ]` | Reporting terminal stdlib + ETA glissant (§4.6) | 10 | muet hors terminal, testable sans capture ANSI |
| 12 | `[ ]` | Moteur volumique + primitive d'export `SE16N` (§3.6) | 8, 9 | en-tête de provenance complet ; delta avec l'export précédent |
| 13 | `[ ]` | Implémentation `win32com` de la couture + bundle (§6) | 1 | non testable hors Windows — validation en système réel, marquée comme telle |

## Ce qui bloque, et sur quoi

**Lot 6** — en attente des enregistrements `.vbs` réels, bruts, non reformatés.
Le format documenté dans l'archive écrit `.press()`, mais le recorder SAP
produit du VBScript, où un appel sans argument s'écrit sans parenthèses
(`.press`, `.sendVKey 8`). Le parseur tolérera les deux, et la trace réelle
tranchera. Le §3.7 et les règles transverses de l'archive disent la même
chose : le recorder est la vérité terrain, on ne théorise pas à sa place.

Aucun autre lot n'est bloqué. Les lots 1 à 5 ne dépendent ni d'une trace ni
d'un accès SAP.

## Questions ouvertes qui toucheront un lot

Reprises du §8 de la spec, avec le lot qu'elles concernent :

| Question | Lot | Défaut retenu à défaut d'arbitrage |
|---|---|---|
| définition de « champ critique » pour la garde 4 | 4 | relecture de **tout** champ écrit, exclusion nommée et motivée |
| convention de conservation des exports | 12 | un dossier par système, fichier horodaté, delta contre le plus récent |
| unité de travail du cas 1 : six pipelines ou item composite | 10 | à trancher avant le lot 10, la frontière transactionnelle en dépend |
| format d'entrée des constats | 5 | JSONL en sortie d'audit, CSV accepté en entrée de remédiation |

## Ce que la revue de conception a changé

Une revue indépendante de l'architecture a produit cinq corrections que
j'intègre. Elles ne sont pas cosmétiques.

**1. La couture du §3.4 était trop étroite pour le cas 1 lui-même** — tranché,
décision n°9, couture élargie.

L'analyse d'origine : Elle n'offre
ni `select`, ni accès ALV, ni accès table control. Or l'audit du cas 1 lit une
grille ALV, et `TRAPS #9` impose de positionner explicitement trois cases à
chaque appel de IA08. Les huit méthodes ne suffisent donc pas à exprimer la
première pipeline livrée. **Le lot 1 est bloqué sur cet arbitrage**, parce que
la spec qualifie elle-même la couture d'irréversible.

**2. L'identité d'un item ne peut pas être l'index de ligne.** Le §4.7 exige
que le fichier de KO soit réinjectable ; réinjecté, il n'a plus les mêmes
index. Toute pipeline itérative devra donc déclarer ses colonnes de clé, et
l'identifiant d'item sera l'empreinte de ces colonnes. C'est aussi ce qui rend
opérante l'unité d'itération du §3.3 : regrouper trois cents caractéristiques
en quarante classes devient une déclaration de clé, pas une gymnastique dans
la boucle.

**3. Un item interrompu après sa sauvegarde n'est pas rejouable.** Rejouer
aveuglément, c'est la double écriture. D'où un état `douteux` distinct de
`en_cours`, versé au fichier à arbitrer plutôt qu'au flux de reprise.

**4. Le réexport des KO tient par une convention de préfixe.** Les colonnes de
diagnostic ajoutées sont préfixées `falcon_`, et la lecture les retire. Le
fichier est ainsi enrichi pour l'humain *et* réinjectable sans retouche — les
deux exigences du §4.7 en même temps.

**5. Les douze pièges n'amorcent pas douze entrées de taxonomie.** La plupart
ne sont pas des messages SAP : le piège 4 est une règle de résolution, le 5
est la garde 1 elle-même, les 6 et 7 sont des méthodes de couture, et les 1,
2, 10, 11, 12 sont des étapes échappatoires. Le registre s'amorce à trois ou
quatre entrées. Prétendre l'amorcer à douze serait exactement la
spécification anticipée que le §5.1 proscrit.
