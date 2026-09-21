@echo off
rem Double-cliquer ce fichier lance CL24N dans une fenetre de commande.
rem Le "pause" garde la fenetre ouverte pour qu'un message d'erreur reste lisible.
cd /d "%~dp0"
python cl24n.py %*
if errorlevel 1 echo.
pause
