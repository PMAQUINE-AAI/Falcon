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

L'état vivant des lots est dans [docs/BACKLOG_V1.md](docs/BACKLOG_V1.md), et
nulle part ailleurs. Ce README dit ce que FALCON *est* ; le backlog dit où il
en est. Dupliquer l'avancement ici garantirait qu'une des deux versions soit
fausse — ça a déjà été le cas.

Les modules livrés :

| Module | Rôle |
|---|---|
| `falcon/noyau/` | types de la couture, hiérarchie d'erreurs, vocabulaire des gardes |
| `falcon/couture/` | l'interface étroite par laquelle tout FALCON parle à SAP |
| `falcon/controleur/` | les cinq gardes, les contrats d'étape, les dérogations |
| `falcon/journal/` | JSONL append-only, repli des états, reprise, rapport |
| `falcon/taxonomie/` | registre des erreurs connues, classement, dump d'inconnu |
| `falcon/donnees/` | lecture des jeux, regroupement par unité de sauvegarde, réexport des KO |
| `falcon/pipeline/` | modèle déclaratif, chargeur strict, échappatoire Python |
| `falcon/moteur/` | la boucle itérative, la chaîne de pipelines, la reprise |
| `falcon/supervision/` | progression et ETA glissant, muets hors terminal |
| `falcon/volumique/` | export de table, provenance obligatoire, delta contre le précédent |
| `falcon/catalogue/` | écrans, variantes, dépôt YAML, quarantaine |
| `falcon/trace/` | lecture des enregistrements du SAP GUI Recorder, couverture, esquisses d'écran, brouillon de pipeline |
| `falcon/commandes/` | ligne de commande : `console`, `diagnostiquer`, `inventaire`, `brouillon` — aucune n'écrit dans SAP |
| `falcon/console/` | menus interactifs : tests, traces, pipelines et jeux de données, catalogue, diagnostic |

**Ce que le vert des tests ne prouve pas.** Aucune ligne de ce dépôt n'a
encore parlé à un système SAP. `falcon/couture/sapgui.py` existe désormais,
mais ni la suite locale ni la CI ne peuvent l'exécuter : elles tournent sur
Linux, sans SAP GUI ni pywin32. Sa conformité réelle est marquée `skip` avec
un motif lisible, et `python outils/verifier.py` liste en fin de course tout
ce qui n'a **pas** été vérifié — un test qui ne s'exécute pas doit le dire. Les tests établissent que FALCON se comporte
correctement *étant donné* une réponse de driver — pas que SAP réponde ainsi.
Le double de test le dit lui-même dans sa docstring, et la spec le dit au
§3.7 : un mock nourri d'hypothèses confirme les hypothèses. La validation en
système réel reste entière.

## Développement

État des lots et protocole de travail : [docs/BACKLOG_V1.md](docs/BACKLOG_V1.md).

```bash
python outils/verifier.py
```

Tout depuis un seul endroit :

```bash
python -m falcon console
```

Menus numérotés — vérification, traces, pipelines et données, catalogue,
session SAP. Pas de
`curses` et pas de dépendance : `curses` n'est pas fourni avec CPython sous
Windows, or c'est la seule machine où SAP GUI existe. Le décor s'encode en
cp1252, ce qu'écrit une console Windows française redirigée.

Les mêmes choses en scriptable, hors terminal :

```bash
python -m falcon inventaire tests/fixtures/traces/megatrace_2026-09.vbs
python -m falcon brouillon tests/fixtures/traces/megatrace_2026-09.vbs
python -m falcon diagnostiquer --catalogue <dossier-du-catalogue>
```

`brouillon` produit une ébauche de pipeline **inachevée à dessein** : tout ce
que la trace ne dit pas — l'identité des écrans, avant tout — porte un
marqueur, et `charger()` refuse le fichier tant qu'il en reste un. Le
générateur n'émet jamais `navigation_libre` : ce serait désarmer la garde
d'identité sur toute pipeline née d'une trace, sans que personne l'ait décidé.

`inventaire` est la première chose à passer sur toute nouvelle trace : il dit
ce que le parseur sait en lire, et ce qu'il n'en sait pas.

`diagnostiquer` est le **premier contact réel** — il se greffe sur une session
SAP que vous avez ouverte et sur laquelle vous vous êtes authentifié
vous-même. Aucun mot de passe ne transite par FALCON. La commande ne reçoit
qu'un `DriverLecture`, une façade qui n'a ni `write`, ni `press`, ni `vkey` :
elle est en lecture seule par construction, pas par discipline. Avec
`--catalogue`, le relevé est versé en **quarantaine** ; le promouvoir reste un
geste explicite, celui par lequel un humain dit avoir relu l'écran.

## Livraison

Le dépôt est modulaire, la livraison est **un fichier unique** (§6) :

```bash
python outils/embarquer.py        # produit falcon.pyz, ~160 Kio
python falcon.pyz inventaire trace.vbs
```

`zipapp` est dans la stdlib : construire le bundle n'ajoute aucune dépendance,
pas même de construction. PyYAML — la seule dépendance d'exécution — voyage
dans l'archive ; la suite le prouve en lançant le bundle avec `-S`, donc sans
les paquets de la machine.

`pywin32` n'est **pas** embarqué et ne doit pas l'être : c'est une extension
binaire Windows liée à une version d'interpréteur. Il s'installe sur le poste,
et `diagnostiquer` — la seule commande qui l'exige — le dit avec la ligne de
commande à taper.

Deux règles d'architecture sont vérifiées mécaniquement par
`tests/test_frontieres.py`, parce qu'une règle que rien ne vérifie tient
jusqu'au premier import pressé :

- un seul module de FALCON importe `win32com` — celui de la couture. Rien
  d'autre ne connaît SAP (§3.4) ;
- le moteur et les pipelines ne touchent jamais la couture nue : ils passent
  par le contrôleur, qui porte les gardes. Une pipeline ne peut donc pas en
  désactiver une (§5.2).

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
