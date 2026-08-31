"""Canaux d'echange de texte avec SAP (a construire).

L'editeur SAPscript n'est pas adressable par `findById` : toute lecture ou
ecriture de texte long passe par un canal externe. Les trois voies visees
sont interchangeables derriere une meme interface `lire()` / `ecrire()` :

  - controle direct  : quand un vrai `GuiTextedit` est disponible ;
  - fichier RTF      : teledechargement / import via les dialogues fichier ;
  - presse-papier    : dernier recours, etat global partage (cf. TRAPS.md 12).

Voir docs/HARNESS.md, section "Decoupage modulaire propose".
"""
