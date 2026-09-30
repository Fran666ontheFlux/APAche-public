"""Point d'entrée : `python -m memoire` (lancé par « Ouvrir APAche.bat »)."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import webbrowser

from .application import Application
from .serveur import PORT_PAR_DEFAUT, creer_serveur


def _deja_lance(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/etat", timeout=2) as r:
            return "ouvert" in json.load(r)
    except (OSError, ValueError):
        return False


def _fermer_avec_la_fenetre(app: Application) -> None:
    """Fermer la fenêtre noire doit rendre le verrou et faire la sauvegarde.

    Windows prévient le programme quelques secondes avant de le tuer ; Python
    ne transmet pas cet avertissement tout seul, d'où l'appel direct à l'API Windows.
    """
    if sys.platform != "win32":
        return
    import ctypes

    type_gestionnaire = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

    def gestionnaire(_evenement):
        try:
            app.fermer()
        except Exception:
            pass
        return False  # laisser Windows (ou Ctrl+C) poursuivre la fermeture

    _fermer_avec_la_fenetre.reference = type_gestionnaire(gestionnaire)  # éviter le ramasse-miettes
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_fermer_avec_la_fenetre.reference, True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestionnaire de sources du mémoire")
    parser.add_argument("--port", type=int, default=PORT_PAR_DEFAUT)
    parser.add_argument("--sans-navigateur", action="store_true")
    args = parser.parse_args()
    adresse = f"http://127.0.0.1:{args.port}/"

    try:
        app = Application()
        serveur = creer_serveur(app, args.port)
    except OSError:
        if _deja_lance(args.port):
            print("L'outil tourne déjà : j'ouvre simplement le navigateur.")
            webbrowser.open(adresse)
            return
        print(f"Le port {args.port} est occupé par un autre programme. "
              f"Ferme-le, ou relance avec --port 8766.")
        sys.exit(1)

    app.ouvrir()
    _fermer_avec_la_fenetre(app)
    print("Le mémoire est ouvert dans ton navigateur :", adresse)
    print("Pour quitter : bouton « Fermer » dans l'outil, ou ferme cette fenêtre.")
    print("Laisse cette fenêtre ouverte pendant que tu travailles.")
    if not args.sans_navigateur:
        webbrowser.open(adresse)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.fermer()
        serveur.server_close()
        print("APAche fermé, sauvegarde faite.")


if __name__ == "__main__":
    main()
