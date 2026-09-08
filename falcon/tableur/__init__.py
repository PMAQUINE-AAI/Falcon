"""Du tableur a la pipeline : trois CSV, un YAML.

**Le grief qui a produit ce paquet**, dans les mots de l'utilisateur : « Il
faut que le programme puisse etre multi usage, pas specifique au point ou je
dois revoir avec toi le code des que j'ai besoin de faire une nouvelle
automatisation. » Un automatisme nouveau doit etre un FICHIER, jamais un
commit.

Le YAML de pipeline etait deja ce fichier. Il reste penible a ecrire a la main
— une cible SAP fait soixante caracteres, un ecran est un triplet — et
personne ne veut le taper pour trois cents lignes. Le classeur choisit les
champs dans le dictionnaire du catalogue et ecrit trois CSV ; ce paquet les
convertit.

**Ce que ce paquet NE FAIT PAS, et c'est le plus important.** Il ne construit
jamais de `Pipeline`. Il emet du TEXTE, puis relit ce texte avec `charger()`
et n'ecrit sur le disque que si le chargement passe. C'est ce qui garantit
qu'il n'ouvre pas un second chemin de validation a cote du premier : tout ce
que `charger()` refuse est refuse ici, sans avoir a etre redit.

Il ne refuse par lui-meme que ce qu'il est SEUL a pouvoir situer — une colonne
inconnue, un rang decroissant, des crochets manquants, une derogation
orpheline — parce qu'a ces endroits-la un message qui parle du YAML enverrait
corriger un fichier que l'utilisateur n'a pas ecrit.
"""

from .conversion import (
    CSV_DEROGATIONS, CSV_ETAPES, CSV_PIPELINE, TableurInvalide, convertir,
    convertir_fichiers,
)
from .lecture import COLONNES_DEROGATIONS, COLONNES_ETAPES, JETON_LIBRE

__all__ = [
    "CSV_DEROGATIONS", "CSV_ETAPES", "CSV_PIPELINE", "COLONNES_DEROGATIONS",
    "COLONNES_ETAPES", "JETON_LIBRE", "TableurInvalide", "convertir",
    "convertir_fichiers",
]
