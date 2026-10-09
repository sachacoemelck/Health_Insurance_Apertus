"""Interface web du comparateur LAMal (Streamlit), en français.

Lancer depuis le dossier track_2b :   streamlit run src/app.py

Configuration : uniquement les variables LLM_NAME, LLM_BASE_URL, LLM_API_KEY
(et LLM_NAME_RESTITUTION, facultative), lues par lire_config().
Aucune donnée personnelle n'est écrite sur disque : la conversation vit seulement
dans la mémoire de la session du navigateur (st.session_state).

Le parcours partage le contrat de profil de chatbot.py avec la CLI :
- mises à jour structurées Apertus, validation et clarification déterministes ;
- filtrage des catégories acceptées avant classement, puis explication vérifiée ;
- module complémentaires (faits agrégés, résumé vérifié, produits à vérifier).
"""
import re
import json
from copy import deepcopy

import streamlit as st
from openai import OpenAI

import chatbot
import complementaires as compl
import sante
import conversation
import regles
import soins
from chatbot import (Profile, State, CARE_TYPES, CARE_LABELS, QUESTIONS,
                     FRANCHISES, NOMS_PRIORITE, PROMPT_INTRO, extraire_json,
                     faits_propositions, lire_config, localiser, nom_simple)
from comparateur import classe_age, propositions

# Langue des explications d'Apertus (paramètre conservé pour ajouter d'autres langues plus tard)
LANGUE = "français"

AVERTISSEMENT = ("Outil d'orientation, pas un conseil personnalisé ; vérifiez sur "
                 "priminfo.admin.ch avant de décider.")
RAPPEL_LAMAL = ("Primes officielles OFSP 2027. Vérifiez sur priminfo.admin.ch avant de changer "
                "d'assurance.")

class ErreurLLM(Exception):
    pass


# --------------------------------------------------------------------------------------
# Configuration et appels au LLM (configuration lue uniquement dans les variables LLM_*)
# --------------------------------------------------------------------------------------
@st.cache_resource
def client_llm(base_url, api_key):
    # Délai maximal par appel : si Apertus ne répond pas, la personne voit un message au lieu
    # d'attendre indéfiniment (par défaut, la bibliothèque attend 10 minutes et réessaie 2 fois).
    return OpenAI(base_url=base_url, api_key=api_key, timeout=60, max_retries=1)


def config():
    try:
        return lire_config()
    except SystemExit as erreur:  # lire_config() s'arrête si une variable LLM_* manque
        st.error(f"Configuration manquante : {erreur}")
        st.stop()


def client():
    cfg = config()
    return client_llm(cfg["LLM_BASE_URL"], cfg["LLM_API_KEY"])


def llm(modele, systeme, message):
    try:
        return chatbot.demander_llm(client(), modele, systeme, message)
    except Exception as erreur:
        raise ErreurLLM(str(erreur)) from erreur


def llm_json(modele, systeme, message):
    try:
        return chatbot.demander_llm_json(client(), modele, systeme, message)
    except Exception as erreur:
        raise ErreurLLM(str(erreur)) from erreur


# --------------------------------------------------------------------------------------
# État de la session (en mémoire seulement)
# --------------------------------------------------------------------------------------
def profil_vide():
    return {"contract": Profile(), "comparison": None, "npa": None, "commune_citee": None, "commune": None, "canton": None,
            "region": None, "age": None, "franchise": None, "travaille_8h": None,
            "plusieurs_personnes": False, "priorite": None, "besoins": [], "soins": {},
            "budget": None}  # budget : ("montant", n), ("petit", None) ou ("aucun", None)


def etat():
    s = st.session_state
    if "profil" not in s:
        s.profil = profil_vide()
        s.messages = []          # historique affiché
        s.resultats = []         # calculs déjà faits (réaffichés sans recalculer)
        s.etape = "collecte"     # collecte -> confirmation -> resultats
        s.attente = None         # champ demandé à l'utilisateur
        s.question = None        # dernière question posée
        s.choix_communes = None  # communes entre lesquelles choisir
        s.lieu_inconnu = False
        s.textes_besoins = []    # phrases où des besoins ont été exprimés
        dire(ACCUEIL)
        s.sante = []             # éléments de santé classés (en mémoire seulement)
    return s


ACCUEIL = ("Bonjour ! Je suis votre conseiller pour l'assurance maladie de base (LAMal), avec Apertus. "
           "Parlez-moi de vous : votre âge, votre commune, et ce qui compte pour vous (budget, choix du "
           "médecin…). Vous pouvez aussi me poser vos questions sur la LAMal à tout moment.")


def dire(texte):
    st.session_state.messages.append({"role": "assistant", "type": "texte", "contenu": texte})


# --------------------------------------------------------------------------------------
# Compréhension des messages : extraction 8B + contrôles Python existants
# --------------------------------------------------------------------------------------
def integrer(texte, champ=None, question=False, suivi=False):
    """Ajoute au profil ce que l'utilisateur vient de dire. Renvoie True si le profil a changé.
    Si la personne pose une question, la lecture d'Apertus du champ demandé est ignorée : seules
    les valeurs écrites explicitement (relues par les règles Python) comptent. `suivi` : message
    écrit après les résultats (« et avec une franchise de 300 ? ») ; c'est un changement voulu."""
    s, cfg = st.session_state, config()
    p = s.profil
    contract = p["contract"]
    message = json.dumps({"profile": contract.context(), "question": s.question if champ else None,
                          "target": champ, "user_message": texte}, ensure_ascii=False)
    try:
        updates = chatbot.extraire_mises_a_jour(
            lambda prompt, message: llm(cfg["LLM_NAME"], prompt, message), message)
    except ValueError as error:
        raise ErreurLLM("Réponse structurée invalide après deux essais") from error
    updates = conversation.mises_a_jour_hors_question(updates, champ, question)
    budget = conversation.lire_budget(texte, champ)
    if budget and not (budget[0] == "petit" and p["budget"] and p["budget"][0] == "montant"):
        p["budget"] = budget
    elif champ == "budget" and not question:
        p["budget"] = ("aucun", None)  # budget facultatif : on n'insiste pas
    selecting_person = (contract.known("multiple_people") is True
                        and updates.get("multiple_people", {}).get("value") is False
                        and updates.get("multiple_people", {}).get("status") == "known")
    # Préférences de soins : positions d'Apertus contrôlées par Python (module soins). Une
    # condition ou une hésitation ne suspend plus la comparaison : elle est chiffrée à part.
    positions = {}
    if not question and (champ == "care_access" or soins.parle_de_soins(texte)):
        positions = soins.extraire_soins(
            lambda systeme, message: llm_json(cfg["LLM_NAME"], systeme, message), texte)
    # Formulations explicites que Python lit lui-même si Apertus les a manquées (module regles)
    updates = regles.completer_par_regles(updates, texte, champ, suivi=suivi)
    updates.pop("care_conditions", None)
    if suivi:  # après les résultats, une nouvelle valeur remplace l'ancienne au lieu de créer un conflit
        updates = {k: {**v, "correction": True} for k, v in updates.items()}
    if positions or champ != "care_access":
        # Sans position contrôlée, seule une réponse directe à la question des modèles peut
        # encore renseigner les catégories par l'ancienne extraction.
        updates.pop("care_access", None)
    change = contract.apply(updates, resolving=champ)
    if selecting_person:
        p["besoins"], s.textes_besoins, s.sante, p["soins"] = [], [], [], {}
    if positions:
        p["soins"] = soins.fusionner_soins(p["soins"], positions)
        acceptes = soins.modeles_acceptes(p["soins"])
        if acceptes != contract.known("care_access"):
            contract.set("care_access", acceptes)
        change = True
    if change:
        synchroniser_profil()

    if champ is None and not question:  # besoins et santé : seulement dans les descriptions libres
        besoins = compl.categories_finales(
            extraire_json(llm(cfg["LLM_NAME"], compl.PROMPT_BESOINS, texte)).get("categories"), texte)
        nouveaux = [b for b in besoins if b not in p["besoins"]]
        if nouveaux:
            p["besoins"] += nouveaux
            s.textes_besoins.append(texte)
            change = True
        # Santé : Apertus classe seulement ; les réponses sont des textes fixes et des calculs
        for element in sante.classer(texte, lambda systeme, message: llm(cfg["LLM_NAME"], systeme, message)):
            if element not in s.sante:
                s.sante.append(element)
                change = True
    return change


def synchroniser_profil():
    """Compatibility projection for existing display and optional modules; contract is authoritative."""
    p = st.session_state.profil
    c = p["contract"]
    p.update(npa=c.known("postal_code"), commune_citee=c.known("municipality"),
             age=c.rating_age(), franchise=c.deductibles()[0] if len(c.deductibles()) == 1 else None,
             travaille_8h=None if c.accident() is None else not c.accident(),
             plusieurs_personnes=c.known("multiple_people") is True,
             priorite="libre_choix" if c.known("care_access") == ["unrestricted"] else None,
             commune=None, canton=None, region=None, comparison=None)
    st.session_state.choix_communes = None


def resoudre_lieu():
    s = st.session_state
    p = s.profil
    if p["canton"] or (p["npa"] is None and not p["commune_citee"]):
        return
    lieu = localiser(p["npa"], p["commune_citee"])
    if isinstance(lieu, tuple):
        p["commune"], p["canton"], p["region"] = lieu
        s.choix_communes = None
    elif lieu is None:
        # Preserve the user's facts. Never silently discard a conflicting municipality.
        s.lieu_inconnu = True
    else:
        s.choix_communes = lieu[["commune", "canton", "region"]].to_dict("records")


def champ_manquant():
    s = st.session_state
    p = s.profil
    issue = p["contract"].issue()
    if issue and issue != "deductible":
        return issue
    if s.choix_communes:
        return "commune"
    if not p["canton"]:
        return "municipality" if p["npa"] is not None else "postal_code"
    if issue == "deductible" and (p["budget"] is None or p["budget"][0] == "petit"):
        return "budget"  # facultatif, demandé avant la franchise pour pouvoir en tenir compte
    return issue


def libelle_commune(c):
    return c["commune"] if c["commune"].endswith(f"({c['canton']})") else f"{c['commune']} ({c['canton']})"


EXEMPLES_REPONSE = {
    "postal_code": "1003 Lausanne", "municipality": "Lausanne", "birth_year": "je suis né en 1990",
    "age": "j'ai 35 ans", "deductible": "2500, ou la plus haute", "include_accident": "avec accidents",
    "care_access": "tous les modèles me conviennent", "multiple_people": "seulement moi, 35 ans",
    "hours_per_week_one_employer": "42 heures par semaine chez le même employeur",
    "employed": "oui, je suis salarié", "nonoccupational_covered": "oui, c'est confirmé par mon employeur",
    "budget": "250 CHF par mois, ou pas de limite",
}


def preparer_question(champ, question_posee=False):
    """Question fixe pour le champ choisi par le contrat (Python). Renvoie None si le champ a été
    réglé sans question (repli après plusieurs incompréhensions) : il faut alors passer au suivant."""
    s = st.session_state
    p = s.profil
    if champ == "commune":
        question = "Quelle commune faut-il retenir : " + ", ".join(
            libelle_commune(c) for c in s.choix_communes) + " ?"
    elif champ == "budget":
        question = conversation.QUESTION_BUDGET
    else:
        question = QUESTIONS[champ]
        fact = p["contract"].facts[champ]
        if fact.state == State.CONFLICT:
            question = (f"Deux réponses diffèrent : {fact.previous!s} et {fact.value!s}. " + question)
        elif fact.state == State.INVALID:
            question = "Cette valeur n'est pas valide. " + question
        elif fact.state == State.AMBIGUOUS:
            question = "Cette information reste incertaine. " + question
        elif (champ == "deductible" and fact.state == State.KNOWN and isinstance(fact.value, int)
              and p["contract"].rating_age() is not None):
            # Montant légal en soi, mais pas pour cet âge (ex. 0 CHF pour un adulte) : on dit pourquoi
            permises = FRANCHISES[classe_age(p["contract"].rating_age())]
            question = (f"Une franchise de {fact.value} CHF n'existe pas pour votre âge : les franchises "
                        f"possibles sont {', '.join(map(str, permises))} CHF. " + question)
    if s.lieu_inconnu and champ in ("postal_code", "municipality"):
        question = "Le lieu est inconnu ou le code postal et la commune ne correspondent pas. " + question
        s.lieu_inconnu = False
    repetitions = s.get("repetitions", {})
    # Une question de la personne n'est pas une incompréhension : on y répond, puis on redemande
    repetitions = {champ: repetitions.get(champ, 0) + (0 if question_posee else 1)}
    s.repetitions = repetitions
    if champ == "budget" and repetitions[champ] >= 2:
        p["budget"] = ("aucun", None)  # facultatif : demandé une fois, jamais imposé
        s.repetitions = {}
        return None
    if champ == "care_access" and repetitions[champ] >= 3:
        # Sans réponse comprise, jamais de restriction acceptée à la place de la personne : on compare
        # le modèle standard, et les autres modèles sont chiffrés dans « Ce que coûtent vos préférences ».
        p["contract"].set("care_access", ["unrestricted"])
        synchroniser_profil()
        dire("Je n'ai pas compris quels modèles vous acceptez : je compare le modèle standard (libre choix) "
             "et je vous montre ensuite ce que coûteraient les autres. Vous pourrez préciser après.")
        s.repetitions = {}
        return None
    if (repetitions[champ] >= 2 and champ in EXEMPLES_REPONSE and not question_posee
            and "n'existe pas pour votre âge" not in question):
        question = ("Je n'ai pas compris votre réponse. " + question
                    + f" Par exemple : « {EXEMPLES_REPONSE[champ]} ».")
    s.question, s.attente = question, champ
    return question


LIBELLES_FAITS = {"age": "âge", "birth_year": "année de naissance", "postal_code": "code postal",
                  "municipality": "commune", "deductible": "franchise", "include_accident": "accidents inclus",
                  "care_access": "modèles acceptés", "employed": "emploi salarié",
                  "hours_per_week_one_employer": "heures par semaine chez un même employeur",
                  "nonoccupational_covered": "couverture accidents non professionnels confirmée"}


def faits_connus():
    """Le profil en mots, pour qu'Apertus confirme ce qui a été noté sans rien inventer."""
    p = st.session_state.profil
    c = p["contract"]
    faits = {}
    for champ, libelle in LIBELLES_FAITS.items():
        v = c.known(champ)
        if v is None:
            continue
        if champ == "care_access":
            v = ", ".join(CARE_LABELS[k] for k in v)
        elif champ == "deductible":
            v = {"all": "comparer toutes", "lowest": "la plus basse", "highest": "la plus haute"}.get(v, f"{v} CHF")
        elif isinstance(v, bool):
            v = "oui" if v else "non"
        faits[libelle] = str(v)
    if p.get("commune"):
        faits["commune retenue"] = f"{p['commune']} ({p['canton']}, région de primes {p['region']})"
    b = p.get("budget")
    if b:
        faits["budget"] = {"montant": f"{b[1]} CHF par mois au maximum", "petit": "petit budget",
                           "aucun": "pas de limite indiquée"}[b[0]]
    return faits


def chiffres_franchise():
    """Conseil de franchise chiffré par Python, dès que le lieu et l'âge sont connus."""
    p = st.session_state.profil
    c = p["contract"]
    if not p.get("canton") or c.rating_age() is None:
        return ""
    care = c.known("care_access")
    budget = p["budget"][1] if p.get("budget") and p["budget"][0] == "montant" else None
    try:
        return conversation.faits_franchise(
            p["canton"], p["region"], c.rating_age(), c.accident(),
            [CARE_TYPES[k] for k in care] if care else None, budget,
            chatbot.no_ofs_de(p["commune"], p["canton"]))
    except Exception:
        return ""


def appeler_70b(systeme, message):
    return llm(config()["LLM_NAME_RESTITUTION"], systeme, message)


def avancer(tour=None):
    """Demande le prochain champ non résolu, sinon le résumé à confirmer. Avec `tour` (un message
    tapé par la personne), c'est Apertus qui écrit la réponse : il réagit, répond à la question
    éventuelle, puis pose la question choisie par Python. Sans `tour` (bouton), question fixe."""
    s = st.session_state
    question_posee = bool(tour and tour["question"])
    while True:
        resoudre_lieu()
        champ = champ_manquant()
        question = preparer_question(champ, question_posee) if champ else None
        if not champ or question is not None:
            break
    if champ:
        s.etape = "collecte"
    else:
        s.etape, s.attente = "confirmation", "confirmation"
    if tour is None:
        if question:
            dire(question)
    else:
        apres = faits_connus()
        notes = [f"{k} : {v}" for k, v in apres.items() if tour["avant"].get(k) != v]
        parle_franchise = champ == "deductible" or re.search(r"franchise", tour["texte"], re.I)
        dire(conversation.repondre_tour(
            appeler_70b, tour["texte"], notes, question_posee, question,
            chiffres=chiffres_franchise() if parle_franchise else "",
            contexte="; ".join(f"{k} : {v}" for k, v in apres.items()),
            passe=conversation.historique(s.messages[:-1]), langue=LANGUE))
    if not champ:
        s.messages.append({"role": "assistant", "type": "profil", "profil": deepcopy(s.profil),
                           "sante": len(s.sante)})


def choisir_commune(c):
    p = st.session_state.profil
    p["contract"].set("municipality", c["commune"])
    synchroniser_profil()
    p["commune"], p["canton"], p["region"] = c["commune"], c["canton"], int(c["region"])
    st.session_state.choix_communes = None
    return True


def choisir_commune_texte(texte):
    """Réponse à la question commune : numéro ou nom d'une commune proposée."""
    choix = st.session_state.choix_communes or []
    numero = re.fullmatch(r"\s*(\d{1,2})\s*", texte)
    if numero and 1 <= int(numero.group(1)) <= len(choix):
        return choisir_commune(choix[int(numero.group(1)) - 1])
    trouvees = [c for c in choix if nom_simple(c["commune"]) == nom_simple(texte)]
    return choisir_commune(trouvees[0]) if len(trouvees) == 1 else False


def traiter_message(texte):
    s = st.session_state
    s.messages.append({"role": "user", "type": "texte", "contenu": texte})
    question = conversation.est_question(texte)
    tour = {"texte": texte, "question": question, "avant": faits_connus()}
    if s.attente == "commune" and choisir_commune_texte(texte):
        avancer()
    elif s.etape == "resultats":
        avant = s.profil["contract"].context(), s.profil["budget"]
        integrer(texte, question=question, suivi=True)
        if (s.profil["contract"].context(), s.profil["budget"]) != avant:
            avancer(tour)  # une information change : nouveau résumé à confirmer, puis nouveau calcul
        else:
            repondre_apres_resultats(texte)
    else:
        integrer(texte, champ=s.attente if s.attente not in (None, "confirmation") else None,
                 question=question)
        avancer(tour)


def repondre_apres_resultats(texte):
    """Conversation libre après les résultats : Apertus répond avec les chiffres affichés et la fiche LAMal."""
    s = st.session_state
    bloc = s.resultats[-1] if s.resultats else None
    reponse = None
    if bloc is not None:
        reponse = conversation.repondre_libre(
            appeler_70b, texte, bloc.get("faits", ""), bloc.get("chiffres_franchise", ""),
            passe=conversation.historique(s.messages[:-1]), langue=LANGUE)
    dire(reponse or "Je ne peux pas répondre de façon fiable à cette question ici ; vous pouvez vérifier "
                    "sur priminfo.admin.ch. Pour changer une information, écrivez par exemple « et avec "
                    "une franchise de 300 ? » ou « j'habite à 1003 ».")


# --------------------------------------------------------------------------------------
# Calcul : comparateur + explications vérifiées (code existant)
# --------------------------------------------------------------------------------------
INTRO_DE_SECOURS = "Voici les offres retenues selon vos catégories acceptées. Comparez les primes, franchises et conditions."


def calculer():
    """3 propositions LAMal (Python), introduction vérifiée (70B), meilleurs produits complémentaires."""
    s, cfg = st.session_state, config()
    p = s.profil
    if champ_manquant():
        avancer()
        return
    c = p["contract"].comparison((p["commune"], p["canton"], p["region"]))
    p["comparison"] = c
    offres = chatbot.offres_du_profil(c)
    props = propositions(offres, p["priorite"])
    bloc = {"offres": offres, "propositions": props, "intro": None, "compl": None,
            "preferences": chatbot.couts_des_preferences(c), "soins": dict(p["soins"])}
    if props:
        bloc["intro"] = chatbot.expliquer(client(), cfg["LLM_NAME_RESTITUTION"],
                                          faits_propositions(props, p["priorite"]), LANGUE,
                                          prompt=PROMPT_INTRO, secours=INTRO_DE_SECOURS)
    if s.sante and p["franchise"] is not None:
        reference = (props[0]["assureur"], props[0]["produit"]) if props else None
        bloc["sante"] = sante.analyser(p, s.sante, reference)
    if p["besoins"]:
        choix = compl.produits_pour(p["besoins"])
        bloc["compl"] = {
            "categories": list(p["besoins"]), "choix": choix,
            "meilleurs": {c: compl.meilleurs_produits(choix, c, p["age"]) for c in p["besoins"]}}
    bloc["budget"] = p["budget"]
    bloc["faits"] = faits_resultats(bloc)
    bloc["chiffres_franchise"] = chiffres_franchise()
    s.resultats.append(bloc)
    s.messages.append({"role": "assistant", "type": "resultats", "index": len(s.resultats) - 1})
    s.etape, s.attente = "resultats", None


def faits_resultats(bloc):
    """Ce qui est affiché, en texte, pour que les réponses d'Apertus s'appuient dessus."""
    p = st.session_state.profil
    lignes = ["Profil : " + "; ".join(f"{k} : {v}" for k, v in faits_connus().items())]
    if bloc["propositions"]:
        lignes.append(faits_propositions(bloc["propositions"], p["priorite"]))
    for l in bloc.get("preferences") or []:
        lignes.append(f"Modèle non retenu {l['modele']} : dès {l['prime_mois']:.2f} CHF par mois "
                      f"({l['assureur']}), écart de {l['ecart_an']:.2f} CHF par an avec l'offre retenue.")
    resume = resume_budget(bloc)
    if resume:
        lignes.append(resume)
    lignes.append(f"Nombre d'offres comparées : {len(bloc['offres'])}.")
    return "\n".join(lignes)


def resume_budget(bloc):
    b = bloc.get("budget")
    if not b or b[0] != "montant" or bloc["offres"].empty:
        return ""
    n = int((bloc["offres"]["Prime/mois"] <= b[1]).sum())
    return (f"Votre budget : {b[1]} CHF par mois au maximum. {n} offre(s) sur {len(bloc['offres'])} "
            f"le respectent.")


# --------------------------------------------------------------------------------------
# Affichage
# --------------------------------------------------------------------------------------
def afficher_profil(p, nb_sante=0):
    c = p["contract"]
    accident = "incluse" if c.accident() else "exclue"
    if c.known("include_accident") is not None:
        accident += " — selon votre choix de comparaison"
    elif c.known("nonoccupational_covered") is not None:
        accident += " — selon la couverture non professionnelle déclarée"
    else:
        accident += f" — emploi salarié déclaré, {c.known('hours_per_week_one_employer'):g} h/semaine chez un même employeur"
    age_label = (f"Année de naissance : {c.known('birth_year')}" if c.known("birth_year") is not None
                 else f"Âge déclaré : {c.known('age')} ans")
    franchises = ", ".join(map(str, c.deductibles()))
    care = ", ".join(CARE_LABELS[k] for k in c.known("care_access"))
    positions_soins = []
    for position, titre in (("rejected", "Refusé"), ("conditional", "Selon le prix"), ("unsure", "Incertain")):
        modes = soins.par_position(p.get("soins", {}), position)
        if modes:
            positions_soins.append(f"- **{titre}** : " + ", ".join(
                nom + (f" (« {citation} »)" if citation else "") for nom, citation in modes))
    besoins = ", ".join(compl.CATEGORIES[b] for b in p["besoins"]) or "aucun"
    commune = p["commune"] + (f" ({p['npa']})" if p["npa"] else "")
    st.markdown("**Voici ce que j'ai compris. Est-ce correct ?**")
    st.markdown("\n".join([
        f"- **{age_label}** (catégorie tarifaire vérifiée pour {c.premium_year})",
        f"- **Commune** : {commune}",
        f"- **Canton** : {p['canton']}",
        f"- **Région de primes** : {p['region']}",
        f"- **Franchise(s)** : {franchises} CHF",
        f"- **Modèles acceptés** : {care}",
    ] + positions_soins + [
        f"- **Couverture accident** : {accident}",
        f"- **Priorité** : {NOMS_PRIORITE.get(p['priorite'], 'aucune indiquée')}",
        f"- **Budget** : " + ({"montant": f"{(p.get('budget') or (0, 0))[1]} CHF par mois au maximum",
                              "petit": "petit budget", "aucun": "pas de limite indiquée"}
                             .get((p.get("budget") or ("",))[0], "non indiqué")),
        f"- **Besoins en complémentaires** : {besoins}",
    ] + ([f"- **Santé** : {nb_sante} élément(s) pris en compte"] if nb_sante else [])))


def chf(montant):
    return f"{montant:,.2f}".replace(",", "'")


def afficher_sante(r):
    """Section santé : uniquement des textes fixes et des calculs Python (aucun texte du LLM)."""
    st.markdown("### Votre situation de santé")
    e = r["existant"]
    if e:
        st.markdown("**Pour un problème de santé actuel**")
        st.write(sante.TEXTE_LAMAL_MALADIE)
        for c in e["categories"]:
            if compl.LAMAL_COUVRE.get(c, "A_REMPLIR") != "A_REMPLIR":
                st.markdown(f"*{compl.CATEGORIES[c]}* : {compl.LAMAL_COUVRE[c]}")
        exception = e["exception"]
        texte = sante.AVERTISSEMENT_EXISTANT
        if exception is not None:
            texte += (f" Exception connue dans nos données : {exception['assureur']} indique « "
                      f"{exception['prestation']} » (source : {exception['source_url']}).")
        st.warning(texte)
        f = e["franchises"]
        if f:
            basse, haute = f
            meme = basse["produit"] == haute["produit"] and basse["assureur"] == haute["assureur"]
            st.markdown(("Avec le même produit (" + f"{basse['assureur']}, *{basse['produit']}*), "
                         if meme else "Avec l'offre la moins chère pour chaque franchise, ")
                        + "voici ce que vous paieriez par an :")
            st.markdown("\n".join(
                f"- **Franchise {x['franchise']} CHF** : {chf(x['prime_an'])} CHF de primes ; "
                f"au maximum {chf(x['cout_max'])} CHF si vos frais médicaux sont élevés "
                f"(prime + franchise + quote-part maximale)" for x in f))
            if basse["cout_max"] < haute["cout_max"]:
                st.markdown(
                    f"Avec des frais médicaux réguliers, la franchise de {basse['franchise']} CHF "
                    f"peut coûter jusqu'à {chf(haute['cout_max'] - basse['cout_max'])} CHF de moins "
                    f"par an au total. Avec très peu de frais, la franchise de {haute['franchise']} "
                    f"CHF coûte {chf(basse['prime_an'] - haute['prime_an'])} CHF de moins par an en primes.")
        elif e["categories"]:
            st.caption("Comparaison des franchises non affichée : ces frais ne sont en général pas "
                       "remboursés par la LAMal (voir ci-dessus).")
    for a in r["avenir"]:
        titre = compl.CATEGORIES.get(a["categorie"], "autre besoin")
        st.markdown(f"**Pour un projet ou une inquiétude ({titre})**")
        st.write(sante.TEXTE_AVENIR)
        if not a["categorie"]:
            st.write(sante.SANS_CATEGORIE)
            continue
        if a["theme"] == "grossesse":
            st.caption("Les produits dont les conditions excluent la maternité sont retirés de la liste.")
        for prod, carence in a["produits"]:
            st.markdown(f"- {texte_produit(prod, avec_conditions=False)}  \n  Délai de carence : "
                        f"{carence}  \n  *Prix non connu : demandez une offre à {prod['assureur']}.*")


def texte_produit(prod, avec_conditions=True):
    """Un produit complémentaire en Markdown : prestation, couverture, conditions, avertissements."""
    texte = f"**{prod['assureur']}** — *{prod['produit']}* : {prod['prestation']}"
    if compl.details(prod):
        texte += f"  \n  Couverture : {compl.details(prod)}"
    if avec_conditions and isinstance(prod["conditions"], str):
        texte += f"  \n  Conditions : {prod['conditions']}"
    for alerte in compl.avertissements(prod):
        texte += f"  \n  ⚠ {alerte}"
    return texte


def afficher_propositions(bloc):
    props = bloc["propositions"]
    if not props:
        st.write("Aucune prime trouvée pour ce profil.")
        return
    st.write(bloc["intro"])
    for colonne, p in zip(st.columns(len(props)), props):
        with colonne, st.container(border=True):
            st.markdown(f"**{p['titre']}**")
            st.markdown(f"### {p['prime_mois']:.2f} CHF / mois")
            st.markdown(f"{p['assureur']}  \n*{p['produit']}* — {p['modele']}")
            st.markdown("La moins chère" if p["ecart_mois"] == 0
                        else f"+{p['ecart_mois']:.2f} CHF / mois par rapport à la moins chère")
            st.caption(f"Franchise : {p['franchise']} CHF. Contrepartie : {p['contrepartie']}")
    st.caption("Compatibilité par catégorie seulement : réseau de médecins, application et conditions du produit à vérifier. " + RAPPEL_LAMAL)
    if bloc["offres"]["Franchise"].nunique() > 1:
        st.caption("Plusieurs franchises sont comparées : la prime la plus basse ne signifie pas le coût total de soins le plus bas.")


def afficher_meilleurs_complementaires(c):
    st.markdown("### Assurances complémentaires")
    st.info("Le prix de ces assurances n'est pas connu : demandez une offre à la caisse.", icon="ℹ️")
    for categorie in c["categories"]:
        meilleurs, ex_aequo = c["meilleurs"][categorie]
        st.markdown(f"#### {compl.CATEGORIES[categorie]}")
        if compl.LAMAL_COUVRE.get(categorie, "A_REMPLIR") != "A_REMPLIR":
            st.markdown(f"*Ce que couvre déjà la LAMal* : {compl.LAMAL_COUVRE[categorie]}")
        st.markdown("Les 3 produits avec la couverture la plus élevée :" if meilleurs
                    else "Aucun produit accessible pour votre âge dans cette catégorie.")
        for prod in meilleurs:
            st.markdown(f"- {texte_produit(prod)}  \n  *Prix non connu : demandez une offre à "
                        f"{prod['assureur']}.*")
        critere = compl.CRITERE_CLASSEMENT["hospitalisation" if categorie == "hospitalisation"
                                           else "autres"]
        egalite = (f" {ex_aequo} autre(s) produit(s) au même niveau : voir toutes les offres."
                   if ex_aequo else "")
        st.caption(f"Choix : {critere}. Produits réservés à un âge dépassé et compléments à un "
                   f"autre produit exclus.{egalite}")
    for _, prod in c["choix"][c["choix"]["categorie"] == "toutes"].iterrows():
        st.markdown(f"À savoir : {texte_produit(prod)}")
    a_verifier = compl.produits_a_verifier(
        compl.produits.loc[[p.name for cat in c["categories"] for p in c["meilleurs"][cat][0]]])
    if a_verifier:
        st.markdown("**Parmi ces produits, à vérifier avant de vous décider :**")
        st.markdown("\n".join(f"- ⚠ {assureur} {produit} : {'; '.join(alertes)}"
                              for (assureur, produit), alertes in a_verifier.items()))
    st.warning(compl.RAPPEL.format(date=compl.produits["date_verification"].max()))


def afficher_toutes_les_offres(bloc):
    with st.expander("Voir toutes les offres"):
        offres = bloc["offres"].drop(columns="Tariftyp")
        if not offres.empty:
            st.markdown(f"**Assurance de base (LAMal) : {len(offres)} offres, de la moins "
                        f"chère à la plus chère (CHF)**")
            montants = offres.select_dtypes("number").columns
            st.dataframe(offres.style.format({c: "{:.2f}" for c in montants}),
                         hide_index=True, use_container_width=True)
        c = bloc["compl"]
        if c:
            st.markdown("**Assurances complémentaires : liste complète**")
            for categorie in c["categories"]:
                st.markdown(f"*{compl.CATEGORIES[categorie]}*")
                lignes = c["choix"][c["choix"]["categorie"] == categorie]
                st.markdown("\n".join(f"- {texte_produit(prod)}" for _, prod in lignes.iterrows()))
            a_verifier = compl.produits_a_verifier(c["choix"])
            if a_verifier:
                st.markdown("*Produits à vérifier :* " + " ; ".join(
                    f"{assureur} {produit} ({', '.join(alertes)})"
                    for (assureur, produit), alertes in a_verifier.items()))


def afficher_preferences(lignes, positions=None):
    """Ce que coûtent les préférences : uniquement des montants calculés par Python."""
    st.markdown("### Ce que coûtent vos préférences")
    st.write("Pour le même profil, voici l'offre la moins chère de chaque modèle que vous "
             "n'avez pas retenu, comparée à votre offre la moins chère.")
    for l in lignes:
        if l["ecart_an"] < 0:
            ecart = f"**{chf(-l['ecart_an'])} CHF de moins par an**"
        elif l["ecart_an"] > 0:
            ecart = f"**{chf(l['ecart_an'])} CHF de plus par an**"
        else:
            ecart = "**même prime annuelle**"
        raison = soins.raison_non_retenu(l["tariftyp"], positions or {})
        st.markdown(f"- **{l['modele']}**" + (f" ({raison})" if raison else "")
                    + f" : dès {chf(l['prime_mois'])} CHF / mois "
                    f"({l['assureur']}, *{l['produit']}*), soit {ecart}.")
    st.caption("Écarts de primes uniquement, source OFSP 2027. Chaque modèle a des contraintes "
               "propres : vérifiez les conditions du produit avant de changer.")


def afficher_resultats(bloc):
    afficher_propositions(bloc)
    resume = resume_budget(bloc)
    if resume:
        st.markdown(f"**{resume}**")
    b = bloc.get("budget")
    hors_budget = (b and b[0] == "montant" and not bloc["offres"].empty
                   and bloc["offres"]["Prime/mois"].min() > b[1])
    if b and (b[0] == "petit" or hors_budget):
        st.info(conversation.TEXTE_SUBSIDES, icon="💡")
    if bloc.get("preferences"):
        afficher_preferences(bloc["preferences"], bloc.get("soins"))
    if bloc.get("sante"):
        afficher_sante(bloc["sante"])
    if bloc["compl"]:
        afficher_meilleurs_complementaires(bloc["compl"])
    afficher_toutes_les_offres(bloc)
    st.caption("Posez-moi vos questions (« quelle franchise me conviendrait ? », « que couvre la LAMal ? ») "
               "ou changez une information (« et avec une franchise de 300 ? »).")


def bouton(libelle, action, *args, cle):
    """Bouton de réponse rapide : l'action s'exécute avant le prochain affichage."""
    def rappel():
        try:
            action(*args)
        except ErreurLLM:
            dire("Apertus ne répond pas pour le moment. Réessayez dans un instant.")
    st.button(libelle, key=cle, on_click=rappel)


def repondre_bouton(texte_affiche, champ, valeur):
    s = st.session_state
    s.messages.append({"role": "user", "type": "texte", "contenu": texte_affiche})
    s.profil["contract"].set(champ, valeur)
    if champ == "care_access":
        s.profil["soins"] = {}  # un choix par bouton remplace les positions dites en texte
    synchroniser_profil()
    avancer()


def repondre_commune(index):
    s = st.session_state
    c = s.choix_communes[index]
    s.messages.append({"role": "user", "type": "texte", "contenu": libelle_commune(c)})
    choisir_commune(c)
    avancer()


def confirmer():
    s = st.session_state
    s.profil["besoins"] = list(s.get("choix_besoins", s.profil["besoins"]))
    calculer()


def reponses_rapides():
    s = st.session_state
    p = s.profil
    if s.attente == "commune" and s.choix_communes:
        colonnes = st.columns(min(len(s.choix_communes), 4))
        for i, c in enumerate(s.choix_communes):
            with colonnes[i % len(colonnes)]:
                bouton(libelle_commune(c), repondre_commune, i, cle=f"commune_{i}")
    elif s.attente == "deductible" and p["age"] is not None:
        valeurs = FRANCHISES[classe_age(p["age"])]
        for colonne, v in zip(st.columns(len(valeurs)), valeurs):
            with colonne:
                bouton(f"{v} CHF", repondre_bouton, f"{v} CHF", "deductible", v, cle=f"franchise_{v}")
        bouton("Comparer toutes les franchises", repondre_bouton, "Toutes les franchises", "deductible", "all", cle="franchises_all")
        bouton("Laquelle est la plus avantageuse pour moi ?", traiter_message,
               "Quelle franchise est la plus avantageuse pour moi ?", cle="franchise_conseil")
    elif s.attente == "include_accident":
        bouton("Accidents inclus", repondre_bouton, "Comparer avec accidents inclus", "include_accident", True, cle="accident_yes")
        bouton("Accidents exclus (couverture vérifiée)", repondre_bouton,
               "Comparer avec accidents exclus, couverture vérifiée", "include_accident", False, cle="accident_no")
    elif s.attente == "care_access":
        bouton("Libre choix uniquement", repondre_bouton, "Libre choix uniquement", "care_access", ["unrestricted"], cle="care_base")
        bouton("J'accepte tous les modèles", repondre_bouton, "J'accepte tous les modèles", "care_access", list(CARE_TYPES), cle="care_all")
    elif s.attente == "confirmation":
        st.multiselect("Besoins en assurances complémentaires", options=list(compl.CATEGORIES),
                       default=p["besoins"], format_func=compl.CATEGORIES.get, key="choix_besoins")
        bouton("C'est correct, lancer la comparaison", confirmer, cle="confirmer")
        st.caption("Sinon, écrivez votre correction dans le chat (ex. « j'ai 31 ans »).")


def recommencer():
    for cle in list(st.session_state.keys()):
        del st.session_state[cle]


def main():
    st.set_page_config(page_title="Health Insurance Apertus", page_icon="🩺", layout="centered")
    config()  # arrête l'app avec un message clair si une variable LLM_* manque
    s = etat()

    # Texte d'exemple fixe : s'il changeait d'une étape à l'autre, Streamlit recréerait la zone de
    # saisie et le premier message écrit après le changement d'étape serait perdu.
    texte = st.chat_input("Écrivez votre réponse ou posez une question…")
    if texte:
        try:
            with st.spinner("Apertus réfléchit…"):
                traiter_message(texte.strip())
        except ErreurLLM:
            dire("Apertus ne répond pas pour le moment. Réessayez dans un instant.")

    st.title("Comparateur d'assurance maladie")
    st.write("Décrivez votre situation en quelques mots : je compare les primes officielles de "
             "l'assurance de base (LAMal) 2027 et je vous explique les différences.")
    st.warning(AVERTISSEMENT, icon="⚠️")
    st.caption("Les informations de santé ne sont pas enregistrées.")
    with st.sidebar:
        st.button("Nouvelle comparaison", on_click=recommencer)

    for m in s.messages:
        with st.chat_message(m["role"]):
            if m["type"] == "texte":
                st.markdown(m["contenu"])
            elif m["type"] == "profil":
                afficher_profil(m["profil"], m.get("sante", 0))
            else:
                afficher_resultats(s.resultats[m["index"]])
    reponses_rapides()

    st.divider()
    caisses = ", ".join(sorted(compl.produits["assureur"].unique()))
    st.caption("Sources : primes LAMal 2027, régions de primes et liste des assureurs admis : "
               "Office fédéral de la santé publique (OFSP), via opendata.swiss et "
               f"priminfo.admin.ch. Assurances complémentaires : sites des caisses ({caisses}), "
               f"vérifiés le {compl.produits['date_verification'].max()}.")


if __name__ == "__main__":
    main()
