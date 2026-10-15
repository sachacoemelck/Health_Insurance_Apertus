"""Parcours complet dans l'application, avec un faux Apertus (aucun appel réseau) :
entretien -> résultats -> question sur les subsides -> caisse actuelle -> économie -> lettre de
résiliation (bonne lettre d'Apertus, puis mauvaise lettre remplacée par la lettre modèle) ; nom de
groupe (« Groupe Mutuel ») -> choix de la caisse ; bouton « Passer ».
Lancer depuis track_2b/ : python tests/test_parcours_faux.py"""
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
at = AppTest.from_file(os.path.abspath("src/app.py"), default_timeout=120).run()
# Écran de profil : ce parcours passe par le chat (« Je préfère décrire ma situation dans le chat »)
at.button(key="f_chat").click().run()

def dire(t):
    at.chat_input[0].set_value(t).run()
    s = at.session_state
    for m in s.messages[-3:]:
        print("   ", m["role"], m["type"], (m.get("contenu") or m.get("texte") or "")[:200].replace("\n", " | "))
    print(f"   attente={s.attente}")

for t in ["J'ai 35 ans, j'habite à Lausanne 1004", "avec accidents", "tous les modèles", "pas de limite", "1500"]:
    dire(t)
at.button(key="confirmer").click().run()
s = at.session_state
assert s.etape == "resultats" and s.attente == "caisse", (s.etape, s.attente)
print("QUESTION :", s.messages[-1]["contenu"][:90])
dire("Ai-je droit à un subside ?"); print("SUBSIDE:", at.session_state.messages[-1]["contenu"]); assert "Office vaudois" in at.session_state.messages[-1]["contenu"]
dire("Je suis chez Helsana depuis 10 ans")
assert s.attente is None and "Choisir cette offre" in s.messages[-1]["contenu"], s.messages[-1]
assert "CHF" in s.messages[-2]["contenu"]
dire("rédigez ma lettre de résiliation")   # demandée par écrit : toujours possible dans la conversation
m = at.session_state.messages[-1]
assert m["type"] == "lettre" and m["par"] == "apertus", m
print("LETTRE (apertus) :", m["texte"][:120].replace("\n", " | "))
assert "Helsana\nPostfach\n8081 Zürich" in m["texte"]  # adresse officielle (liste OFSP) remplie
assert not changement.problemes_lettre(m["texte"].replace("Postfach\n8081 Zürich", "[Adresse de la caisse]"),
                                       "Helsana", "fr", 2027)
assert len(at.get("download_button")) == 1 if hasattr(at, "get") else True
# question libre après la lettre : le fil normal reprend
dire("c'est quoi la quote-part ?")
assert at.session_state.etape == "resultats"
# une mauvaise lettre d'Apertus est remplacée par la lettre modèle
MODE["lettre"] = "mauvaise"
dire("pouvez-vous refaire la lettre de résiliation ?")
m = at.session_state.messages[-1]
assert m["type"] == "lettre" and m["par"] == "modele", m
print("LETTRE (modèle après refus) OK")
# nom de groupe -> choix de la caisse
at2 = AppTest.from_file(os.path.abspath("src/app.py"), default_timeout=120).run()
at2.button(key="f_chat").click().run()
at = at2
for t in ["J'ai 35 ans, j'habite à Lausanne 1004", "avec accidents", "tous les modèles", "pas de limite", "1500"]:
    dire(t)
at.button(key="confirmer").click().run()
dire("Groupe Mutuel")
assert at.session_state.attente == "caisse_choix", at.session_state.attente
at.button(key="caisse_1479").click().run()
print("APRÈS CHOIX :", at.session_state.messages[-2].get("contenu", "")[:150])
assert at.session_state.attente in ("lettre", None)
# « Passer »
at3 = AppTest.from_file(os.path.abspath("src/app.py"), default_timeout=120).run(); at = at3
at3.button(key="f_chat").click().run()
for t in ["J'ai 35 ans, j'habite à Lausanne 1004", "avec accidents", "tous les modèles", "pas de limite", "1500"]:
    dire(t)
at.button(key="confirmer").click().run()
at.button(key="caisse_passer").click().run()
assert at.session_state.attente is None
print("\nErreurs :", [e.value for e in at.exception] + [e.value for e in at2.exception])
assert not at.exception and not at2.exception
print("1 parcours réussi")
