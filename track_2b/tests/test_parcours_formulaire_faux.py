"""Parcours par l'écran de profil (formulaire), avec un faux Apertus (aucun appel réseau) :
formulaire -> offres -> caisse actuelle -> économie -> lettre -> question sur les subsides.
Lancer depuis track_2b/ : python tests/test_parcours_formulaire_faux.py"""
import json, os, re, sys
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(RACINE)
os.environ.update(LLM_NAME="f8", LLM_BASE_URL="http://x", LLM_API_KEY="x", LLM_NAME_RESTITUTION="f70")
sys.path.insert(0, os.path.join(RACINE, "src"))
import chatbot, changement
from streamlit.testing.v1 import AppTest

MODE = {"lettre": "bonne"}
APPELS = []

def fake(client, modele, systeme, message):
    APPELS.append((modele, systeme[:30]))
    if systeme.startswith("Tu extrais les faits"):
        d = json.loads(message); m = d["user_message"].lower(); up = {}
        k = lambda v: {"value": v, "status": "known", "correction": False}
        if "35 ans" in m: up["age"] = k(35)
        if "1004" in m: up["postal_code"] = k(1004)
        return json.dumps({"updates": up})
    if systeme.startswith("Tu analyses comment"):
        A = {"stance": "accepted", "condition": None, "evidence": None}
        return json.dumps({"care": {c: A for c in ("free_choice", "gp_first", "telemedicine", "phone_first",
                                                    "app_first", "pharmacy_first")}})
    if systeme.startswith("Tu lis la réponse"):
        caisse = "Helsana" if "helsana" in message.lower() else ("Groupe Mutuel" if "mutuel" in message.lower() else None)
        return json.dumps({"caisse": caisse, "modele": None, "prime_mois": None})
    if systeme.startswith("Tu aides à chercher"):
        return "résiliation"
    if systeme.startswith("Tu rédiges une lettre"):
        if MODE["lettre"] == "mauvaise":
            return "Je résilie toutes mes assurances chez Helsana, y compris les complémentaires. Numéro 756.1234.5678.90"
        return changement.lettre_modele("Helsana", "fr", 2027).replace("Par la présente", "Je vous écris pour vous informer que, par la présente,")
    if "Explique à la personne" in systeme:
        lignes = message.splitlines()
        prime = re.search(r"(\d+\.\d\d) CHF par mois\. C'est ce que", message)
        eco = re.search(r"soit (\d+\.\d\d) CHF par an", message)
        return (f"En restant chez votre caisse, vous paieriez {prime.group(1)} CHF par mois. "
                + (f"En changeant, vous économiseriez {eco.group(1)} CHF par an." if eco else "Aucune économie possible."))
    if systeme.startswith("Tu es le conseiller"):
        q = re.search(r"Question à poser à la fin : « (.*) »", message, re.S)
        return "Bonne question. " + (q.group(1) if q else "Voici le résumé.")
    if "complémentaire" in systeme: return '{"categories": []}'
    if "santé" in systeme: return '{"elements": []}'
    return "Voici les offres."

chatbot.demander_llm = fake; chatbot.demander_llm_json = fake

# Écran de profil (interface de Sacha) : formulaire -> offres -> caisse actuelle -> économie -> lettre
at = AppTest.from_file(os.path.abspath("src/app.py"), default_timeout=120).run()
at.number_input(key="f_naissance").set_value(1991).run()
at.text_input(key="f_npa").set_value("1004").run()
at.radio(key="f_situation").set_value("sans_emploi").run()
at.button(key="f_valider").click().run()
s = at.session_state
assert s.etape == "resultats", s.etape
assert s.messages[0]["contenu"].startswith("Merci d'avoir rempli") and "Apertus" in s.messages[0]["contenu"]  # présentation
assert sum("Je suis votre conseiller" in m.get("contenu", "") for m in s.messages) == 1  # une seule fois
assert s.attente == "caisse", s.attente
assert any(m["type"] == "resultats" for m in s.messages)
assert not [w for w in at.multiselect if w.key == "f_besoins"]   # complémentaires désactivées
at.chat_input[0].set_value("Je suis chez Helsana, médecin de famille").run()
assert at.session_state.attente == "lettre", at.session_state.attente
at.button(key="lettre_oui").click().run()
m = at.session_state.messages[-1]
assert m["type"] == "lettre", m["type"]
at.chat_input[0].set_value("Ai-je droit à un subside ?").run()
assert "Office vaudois" in at.session_state.messages[-1]["contenu"]
assert not at.exception, [e.value for e in at.exception]
print("1 parcours avec le formulaire réussi")
