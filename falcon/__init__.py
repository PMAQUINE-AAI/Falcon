"""FALCON — framework d'automatisation SAP Front End.

La specification fait foi : voir SPEC_FALCON.md a la racine du depot.

Regle d'architecture verifiee par tests/test_frontieres.py : le seul module
autorise a importer win32com est falcon/couture/sapgui.py. Tout le reste de
FALCON depend de l'interface de couture, jamais de SAP.
"""

__version__ = "0.1.0"
