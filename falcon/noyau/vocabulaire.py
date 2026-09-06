"""Vocabulaire partage : les noms des gardes, et ce qui est derogeable.

Ces constantes vivaient dans le controleur. Elles descendent ici pour une
raison de frontiere : `falcon/pipeline/` ne peut importer ni la couture ni le
controleur — c'est ce qui garantit qu'une pipeline ne peut nommer aucun driver
— mais son chargeur doit pouvoir REFUSER une derogation a une garde non
derogeable, et le refuser **au chargement**, pas au bout de deux heures de lot.

Ce sont des noms, pas du mecanisme : les faire descendre au noyau ne donne a
personne le moyen de contourner quoi que ce soit. Le mecanisme, lui, reste
entierement dans le controleur.
"""

from __future__ import annotations

# --- les cinq gardes du modele de securite ---------------------------
IDENTITE = "identite"
STATUT = "statut"
FENETRE = "fenetre"
RELECTURE = "relecture"
RAYON = "rayon"

GARDES = (IDENTITE, STATUT, FENETRE, RELECTURE, RAYON)

#: Gardes sur lesquelles une derogation est concevable.
#:
#: L'identite d'ecran et le rayon d'action n'y sont pas, et ne peuvent pas y
#: etre ajoutees par un fichier : une identite violee signale que le modele du
#: monde est faux, et un plafond est la derniere barriere avant le lot entier.
#: Deroger a l'une ou l'autre reviendrait a retirer le fond du filet.
DEROGEABLES = frozenset({STATUT, FENETRE, RELECTURE})

#: Un motif doit dire quelque chose. Ce seuil n'empeche pas d'ecrire une
#: betise, il empeche d'ecrire « ok » et de passer a autre chose.
MOTIF_MINIMAL = 30

#: Portee d'une derogation qui vaut pour toutes les etapes du contrat.
PORTEE_TOTALE = "*"

#: Le champ de commande SAP, par lequel on saisit un code transaction.
#:
#: Il vit ici, et non dans le moteur ni dans le lecteur de traces, parce que
#: les deux en ont besoin et qu'une seconde definition finirait par diverger.
#: C'est le seul identifiant d'ecran connu de FALCON en dehors du catalogue :
#: le §3.3 impose un retour a l'ecran d'accueil entre deux pipelines d'une
#: chaine, et ce retour passe forcement par ce champ.
#:
#: Le suffixe sert a RECONNAITRE le champ dans une trace, ou la fenetre peut
#: varier ; l'identifiant complet sert a y ECRIRE.
SUFFIXE_CHAMP_DE_COMMANDE = "/tbar[0]/okcd"
CHAMP_DE_COMMANDE = "wnd[0]" + SUFFIXE_CHAMP_DE_COMMANDE

#: Code transaction qui ramene a l'ecran d'accueil.
RETOUR_ACCUEIL = "/n"

#: Comment comparer ce qu'on a ecrit a ce qu'on relit.
#:
#: `casse` est le defaut et n'accepte QUE les differences de casse et
#: d'espaces. `prefixe` accepte la troncature, pour les champs dont on SAIT
#: qu'ils sont plus courts que la valeur ecrite ; il se declare etape par
#: etape, la charge de la preuve revenant a qui sait.
COMPARAISONS = frozenset({"exact", "casse", "prefixe"})
