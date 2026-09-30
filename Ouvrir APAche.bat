@echo off
rem Double-cliquer ce fichier pour ouvrir l'outil.
chcp 65001 > nul
cd /d "%~dp0"
title APAche - laisser cette fenetre ouverte

if not exist ".venv\Scripts\python.exe" (
    echo Premiere ouverture sur ce PC : preparation de l'environnement Python...
    py -3 -m venv .venv 2> nul || python -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo Python est introuvable. Installe-le depuis python.org
        echo en cochant "Add python.exe to PATH", puis relance ce fichier.
        pause
        exit /b 1
    )
)
rem N'installer les dependances que si la liste a change depuis la derniere fois :
rem l'outil doit demarrer hors ligne (train, bibliotheque sans wifi).
if exist requirements.txt (
    fc /b requirements.txt ".venv\requirements-installe.txt" > nul 2>&1 || (
        echo Installation des dependances...
        ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt && copy /y requirements.txt ".venv\requirements-installe.txt" > nul
    )
)

".venv\Scripts\python.exe" -m memoire %*
if errorlevel 1 pause
