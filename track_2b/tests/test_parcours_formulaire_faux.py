"""Parcours par l'écran de profil (formulaire), avec un faux Apertus (aucun appel réseau) :
formulaire -> offres -> caisse actuelle -> économie -> lettre -> question sur les subsides.
Lancer depuis track_2b/ : python tests/test_parcours_formulaire_faux.py"""
import json, os, re, sys
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(RACINE)
os.environ.update(LLM_NAME="f8", LLM_BASE_URL="http://x", LLM_API_KEY="x", LLM_NAME_RESTITUTION="f70")
sys.path.insert(0, os.path.join(RACINE, "src"))
import affiliation, chatbot, changement
from streamlit.testing.v1 import AppTest

MODE = {"lettre": "bonne"}
OUVERTURES = []
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
    if systeme.startswith("Tu rédiges, au nom d'une personne"):  # demande d'affiliation
        if MODE.get("affiliation") == "mauvaise":
            return "Je veux m'affilier chez vous. Mon numéro AVS est 756.1234.5678.97."
        f = dict(re.findall(r"^([^:\n]+) : (.+)$", message, re.M))
        ch = {"caisse": f["Nouvelle caisse"], "produit": f["Produit"], "modele": "Médecin de famille / HMO",
              "franchise": int(f["Franchise"].split()[0]), "accident": f["Couverture accidents"].startswith(("incl", "eing", "incl")),
              "prime_mois": float(re.search(r"([\d.]+) CHF", f[next(k for k in f if k.startswith("Prime"))]).group(1)),
              "annee": 2027, "ancienne": f.get("Caisse actuelle (à résilier)")}
        langue = "de" if "allemand" in systeme else "it" if "italien" in systeme else "fr"
        return affiliation.demande_modele(ch, langue).replace("Par la présente", "Je vous écris car, par la présente,")
    if systeme.startswith("Tu ouvres la conversation"):  # ouverture après le formulaire
        OUVERTURES.append(message)
        if MODE.get("ouverture") == "inventee":
            return "Merci ! Vous paierez 99.95 CHF par mois."  # montant absent des faits -> secours
        age = re.search(r"(\d+) ans en 2027", message).group(1)
        commune = re.search(r"Domicile : ([^(]+) \(", message).group(1).strip()
        return (f"Merci d'avoir rempli le formulaire ! Je suis votre conseiller, propulsé par Apertus. Vous aurez "
                f"{age} ans en 2027 et vous habitez à {commune}, donc la couverture accidents est incluse.")
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
# Apertus ouvre la conversation en reprenant le formulaire, juste au-dessus des offres
assert [m["type"] for m in s.messages[:2]] == ["ouverture", "resultats"], s.messages[:2]
intro = s.ouverture["texte"]
assert s.ouverture["suggestions"][0] == "Quelle franchise est la plus avantageuse pour moi ?"
assert "Comment fonctionne le modèle médecin de famille ?" in s.ouverture["suggestions"]   # offre la moins chère : HMO
assert "Ai-je droit à un subside pour payer ma prime ?" in s.ouverture["suggestions"]      # sans emploi
assert at.button(key="suggestion_0") and not s.resultats[0]["intro"]
assert intro.startswith("Merci d'avoir rempli") and "36 ans" in intro and "Lausanne" in intro, intro
faits = OUVERTURES[-1]
assert "Année de naissance 1991 : 36 ans en 2027" in faits and "Sans emploi" in faits and "incluse" in faits, faits
assert "Proposition 1" in faits and "toutes les franchises sont comparées" in faits, faits
assert s.attente == "caisse", s.attente
assert any(m["type"] == "resultats" for m in s.messages)
assert not [w for w in at.multiselect if w.key == "f_besoins"]   # complémentaires désactivées
at.chat_input[0].set_value("Je suis chez Helsana, médecin de famille").run()
assert at.session_state.attente == "lettre", at.session_state.attente
at.button(key="lettre_oui").click().run()
m = at.session_state.messages[-1]
assert m["type"] == "lettre", m["type"]
assert "8081 Zürich" in m["texte"] and "[Adresse de la caisse]" not in m["texte"], m["texte"]  # adresse OFSP de Helsana
# « Choisir cette offre » -> demande d'affiliation rédigée (Apertus), vérifiée, e-mail prêt
at.button(key="choisir_0_0").click().run()
m = at.session_state.messages[-1]
assert m["type"] == "affiliation" and m["par"] == "apertus", (m["type"], m.get("par"))
assert m["choix"]["caisse"].startswith("Atupri") and m["choix"]["ancienne"] == "Helsana", m["choix"]
assert "Helsana" in m["texte"] and "[Numéro AVS]" in m["texte"] and "1er janvier 2027" in m["texte"]
liens = [b for b in at.get("link_button")]
assert liens and liens[0].proto.url.startswith("mailto:info@atupri.ch?subject="), [b.proto.url for b in liens]
assert not at.exception, [e.value for e in at.exception]
MODE["affiliation"] = "mauvaise"   # numéro AVS inventé -> refusé deux fois -> demande modèle
at.button(key="choisir_0_1").click().run()
m = at.session_state.messages[-1]
assert m["par"] == "modele" and "756" not in m["texte"] and m["choix"]["caisse"].upper().startswith("GALENOS")
MODE["affiliation"] = None
at.chat_input[0].set_value("Ai-je droit à un subside ?").run()
assert "Office vaudois" in at.session_state.messages[-1]["contenu"]
assert not at.exception, [e.value for e in at.exception]
# « ← Modifier mes réponses » : retour au formulaire, déjà rempli ; un nouvel envoi recalcule tout
at.button(key="retour_formulaire").click().run()
s = at.session_state
assert not s.get("formulaire_valide") and not s.get("resultats"), "pas revenu au formulaire"
assert at.number_input(key="f_naissance").value == 1991 and at.text_input(key="f_npa").value == "1004"
assert at.radio(key="f_situation").value == "sans_emploi" and not at.warning
at.radio(key="f_situation").set_value("salarie_8h").run()
at.button(key="f_valider").click().run()
assert at.session_state.formulaire_valide and at.session_state.profil["contract"].accident() is False
assert len(at.session_state.resultats) == 1 and "ouverture" in at.session_state
# Changer de langue avant d'envoyer le formulaire : les modèles acceptés restent tous cochés
at8 = AppTest.from_file(os.path.abspath("src/app.py"), default_timeout=120).run()
at8.selectbox(key="langue").set_value("de").run()
assert at8.multiselect(key="f_modeles").value == list(chatbot.CARE_TYPES), at8.multiselect(key="f_modeles").value
at8.number_input(key="f_naissance").set_value(1991).run()
at8.text_input(key="f_npa").set_value("8004").run()
at8.radio(key="f_situation").set_value("independant").run()
at8.selectbox(key="langue").set_value("it").run()
assert not at8.button(key="f_valider").disabled
at8.button(key="f_valider").click().run()
assert at8.session_state.resultats and not at8.exception
# Ouverture avec un montant inventé : refusée deux fois par Python, texte de secours fixe
MODE["ouverture"] = "inventee"
at6 = AppTest.from_file(os.path.abspath("src/app.py"), default_timeout=120).run()
at6.number_input(key="f_naissance").set_value(1991).run()
at6.text_input(key="f_npa").set_value("1004").run()
at6.radio(key="f_situation").set_value("salarie_8h").run()
at6.button(key="f_valider").click().run()
assert at6.session_state.ouverture["texte"].startswith("Merci d'avoir rempli le formulaire ! 👋 Je suis votre conseiller")
assert "exclue" in OUVERTURES[-1], OUVERTURES[-1]                 # salarié 8 h : accidents exclus
assert "Que se passe-t-il pour les accidents si je quitte mon emploi ?" in at6.session_state.ouverture["suggestions"]
at6.button(key="suggestion_0").click().run()                       # question proposée -> réponse dans le chat
assert at6.session_state.messages[-2]["contenu"] == "Quelle franchise est la plus avantageuse pour moi ?", at6.session_state.messages[-2]
# « Je ne sais pas » : une précision d'abord, puis l'ouverture quand les offres sont calculées
MODE["ouverture"] = None
at7 = AppTest.from_file(os.path.abspath("src/app.py"), default_timeout=120).run()
at7.number_input(key="f_naissance").set_value(1991).run()
at7.text_input(key="f_npa").set_value("1004").run()
at7.radio(key="f_situation").set_value("ne_sait_pas").run()
at7.button(key="f_valider").click().run()
assert at7.session_state.messages[0]["contenu"].startswith("Merci d'avoir rempli le formulaire") and not at7.session_state.resultats
assert not at6.exception and not at7.exception
print("1 parcours avec le formulaire réussi")
