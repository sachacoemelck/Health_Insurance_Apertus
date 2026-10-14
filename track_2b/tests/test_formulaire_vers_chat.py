"""Écran de profil -> « Je préfère décrire ma situation dans le chat » : ce qui est déjà rempli
(année de naissance, commune, situation) est gardé et n'est pas redemandé. Aucun appel à Apertus.
Lancer depuis track_2b/ : python -m pytest tests/test_formulaire_vers_chat.py"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(RACINE)
os.environ.update(LLM_NAME="f8", LLM_BASE_URL="http://x", LLM_API_KEY="x", LLM_NAME_RESTITUTION="f70")
sys.path.insert(0, os.path.join(RACINE, "src"))
from streamlit.testing.v1 import AppTest  # noqa: E402


def ouvrir():
    return AppTest.from_file(os.path.abspath("src/app.py"), default_timeout=120).run()


def test_annee_et_commune_gardees():
    at = ouvrir()
    at.number_input(key="f_naissance").set_value(1994).run()
    at.text_input(key="f_npa").input("1260").run()
    at.button(key="f_chat").click().run()
    s = at.session_state
    c = s.profil["contract"]
    assert c.known("birth_year") == 1994
    assert c.known("postal_code") == 1260
    assert "1994" in s.messages[0]["contenu"]
    assert s.attente not in ("birth_year", "age")  # l'âge n'est pas redemandé


def test_situation_gardee():
    at = ouvrir()
    at.number_input(key="f_naissance").set_value(1994).run()
    at.radio(key="f_situation").set_value("salarie_8h").run()
    at.button(key="f_chat").click().run()
    c = at.session_state.profil["contract"]
    assert c.known("employed") is True


def test_rien_rempli_accueil_habituel():
    at = ouvrir()
    at.button(key="f_chat").click().run()
    assert at.session_state.messages[0]["type"] == "accueil"


if __name__ == "__main__":
    tests = [f for nom, f in dict(globals()).items() if nom.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests réussis")
