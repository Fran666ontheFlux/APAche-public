"""Outils communs aux tests.

Les tests doivent tourner avec `python tests/test_x.py` comme sous pytest :
d'où ce petit lanceur, et des dossiers temporaires créés à la main plutôt
qu'avec les fixtures de pytest.
"""

import sys
import tempfile
import traceback
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))


def dossier_temporaire():
    return tempfile.TemporaryDirectory(prefix="memoire-test-")


def lancer(espace: dict) -> None:
    tests = [(nom, f) for nom, f in espace.items() if nom.startswith("test_") and callable(f)]
    echecs = 0
    for nom, f in tests:
        try:
            f()
            print(f"  ok     {nom}")
        except Exception:
            echecs += 1
            print(f"  ÉCHEC  {nom}")
            traceback.print_exc()
    print(f"\n{len(tests) - echecs}/{len(tests)} tests réussis")
    sys.exit(1 if echecs else 0)
