# FALCON

Framework d'automatisation SAP Front End (SAP GUI Scripting).

FALCON exécute des séquences d'actions dans SAP GUI à la place d'un
utilisateur, de façon répétable et surveillée : corrections de masse que LSMW
ne couvre pas, et extractions vers un format pivot exploitable par un
programme tiers.

La forme canonique d'un travail FALCON est une **paire** :

```
passe d'audit  →  fichier de constats (relisible, éditable)  →  passe de remédiation
```

L'humain valide le fichier intermédiaire avant toute écriture. C'est à la fois
le contrat entre les deux passes, la trace d'audit, et la garde de sécurité la
plus efficace du dispositif.

## La référence

**[SPEC_FALCON.md](SPEC_FALCON.md)** — spécification fonctionnelle complète :
architecture en quatre couches, modèle de sécurité, périmètre V1/V2, cas
d'usage et décisions arrêtées. C'est le document qui fait foi ; tout ce qui
suit n'en est qu'un index.

| Section | Sujet |
|---|---|
| §3.1 | catalogue d'écrans, et ses **variantes** — première cause d'échec d'un framework de ce type |
| §3.3 | moteur : modes, chaîne de pipelines, unité d'itération = unité de sauvegarde SAP |
| §3.4 | **couture de driver** — le seul module qui connaît SAP |
| §3.5 | pipelines itératives vs volumiques : ne pas les confondre |
| §3.7 | harness = rejeu du catalogue, magnétophone et non émulateur |
| §5 | les cinq gardes, et la taxonomie d'erreurs qui se récolte |
| §6 | périmètre V1 / V2 |

## État

Le dépôt contient aujourd'hui la spécification et l'archive du travail
antérieur. Aucun code FALCON n'est écrit.

Premier élément attendu en V1, et le plus contraignant dans l'ordre : la
**couture de driver** (§3.4). La spec la qualifie d'irréversible — la
rétrofiter sur du code déjà écrit coûte cher — et elle conditionne aussi bien
les gardes du §5 que le harness du §3.7.

## `historique/`

Le socle EagleLoader et le harness artisanal développés avant cette spec.
Conservés en l'état, sous le régime de la décision n°2 : **réutilisés sous
contrôle strict**, jamais repris par défaut.

| Contenu | Statut au regard de la spec |
|---|---|
| `historique/docs/TRAPS.md` | **vivant** — les douze pièges de terrain sont le matériau de départ de la taxonomie d'erreurs (§5.1), qui se récolte et ne se spécifie pas |
| `historique/cartes/sap_map.yaml` | **référence** — relevé réel K75/210 ; parent du catalogue (§3.1), mais pas sa structure : le catalogue est clé par triplet + empreinte, et se remplit par dump, pas à la main |
| `historique/sapharness/` | **remplacé** — la décision n°3 arrête un harness par rejeu du catalogue, pas un simulateur écrit à la main (§3.7) |
| `historique/docs/GUIDE.md` | documentation de ce simulateur ; suit son sort |
| `historique/docs/HARNESS.md` | le raisonnement qui a mené à la spec ; valeur historique |

L'archive reste exécutable :

```bash
python -m unittest discover -s historique/tests -t historique
```
