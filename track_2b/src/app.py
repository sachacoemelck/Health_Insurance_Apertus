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
import html
import re
import json
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import streamlit as st
from openai import OpenAI

import chatbot
import complementaires as compl
import sante
import affiliation
import caisses
import hors_lamal
import changement
import conversation
import langues
import lois
from langues import tr
import regles
import soins
import style
import subsides
from chatbot import (Profile, State, CARE_TYPES, CARE_LABELS, QUESTIONS,
                     FRANCHISES, NOMS_PRIORITE, PROMPT_INTRO, extraire_json,
                     faits_propositions, lire_config, localiser, nom_simple)
from comparateur import ASSUREURS, classe_age, communes_du_npa, propositions

def L():
    """Langue de la conversation : détectée dans les messages, ou choisie dans la barre latérale."""
    s = st.session_state
    return s.get("langue_detectee") or s.get("langue", "fr")


def nom_langue():
    return langues.NOMS_POUR_APERTUS[L()]

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
    # Pas de nouvel essai automatique de la bibliothèque (il doublait l'attente quand le serveur est lent) :
    # chaque appel a son propre délai (DELAI_8B, DELAI_70B) et l'application sait continuer sans réponse.
    return OpenAI(base_url=base_url, api_key=api_key, timeout=60, max_retries=0)


# Délais : lecture d'un message par Apertus 8B, rédaction par Apertus 70B, et durée maximale d'un tour.
# Au-delà de LIMITE_TOUR, Apertus 70B n'est plus appelé : la personne reçoit la question sans attendre.
DELAI_8B, DELAI_70B, LIMITE_TOUR = 20, 25, 45

# Assurances complémentaires et analyse de santé : modules d'une première version, dont les données
# (produits de 6 caisses, textes de santé) n'ont pas été vérifiées et mesurées comme le reste.
# Désactivés pour la version remise ; le code reste dans le dépôt (complementaires.py, sante.py).
MODULES_COMPLEMENTAIRES = False


def appel(fonction, modele, delai):
    """Fonction (systeme, message) -> texte, pour un modèle et un délai donnés. Préparée dans le fil
    principal : elle peut ensuite être utilisée en parallèle (sans accès à l'état Streamlit)."""
    c = client().with_options(timeout=delai)

    def appeler(systeme, message):
        try:
            return getattr(chatbot, fonction)(c, modele, systeme, message)
        except Exception as erreur:
            raise ErreurLLM(str(erreur)) from erreur
    return appeler


def en_parallele(**taches):
    """Lance les lectures d'Apertus en même temps ; une lecture en échec ou trop lente vaut None."""
    with ThreadPoolExecutor(max_workers=max(1, len(taches))) as pool:
        futurs = {nom: pool.submit(f) for nom, f in taches.items()}
        resultats = {}
        for nom, futur in futurs.items():
            try:
                resultats[nom] = futur.result()
            except Exception:
                resultats[nom] = None
        return resultats


def config():
    try:
        return lire_config()
    except SystemExit as erreur:  # lire_config() s'arrête si une variable LLM_* manque
        st.error(f"Configuration manquante : {erreur}")
        st.stop()


def client():
    cfg = config()
    return client_llm(cfg["LLM_BASE_URL"], cfg["LLM_API_KEY"])


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
        s.messages.append({"role": "assistant", "type": "accueil"})
        s.sante = []             # éléments de santé classés (en mémoire seulement)
    return s


AUTRES_LANGUES = "Sie können auch Deutsch schreiben · Può scrivere anche in italiano · You can also write in English."
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
    # Toutes les lectures d'Apertus 8B partent en même temps (profil, soins, besoins, santé) : la personne
    # attend la plus lente, pas la somme. Une lecture qui échoue ou dépasse son délai est simplement
    # ignorée : les règles Python lisent alors les formulations explicites, sans message d'erreur.
    lire = appel("demander_llm", cfg["LLM_NAME"], DELAI_8B)
    lire_json = appel("demander_llm_json", cfg["LLM_NAME"], DELAI_8B)
    taches = {"profil": lambda: chatbot.extraire_mises_a_jour(lire, message)}
    if not question and (champ == "care_access" or soins.parle_de_soins(texte)):
        taches["soins"] = lambda: soins.extraire_soins(lire_json, texte)
    # besoins et santé : seulement dans les descriptions libres, et si les modules sont activés
    libre = champ is None and not question and MODULES_COMPLEMENTAIRES
    if libre:
        taches["besoins"] = lambda: compl.categories_finales(
            extraire_json(lire(compl.PROMPT_BESOINS, texte)).get("categories"), texte)
        taches["sante"] = lambda: sante.classer(texte, lire)
    if question or suivi:  # question : Apertus 8B traduit en mots-clés juridiques, en même temps (lois.py)
        taches["mots_cles"] = lambda: lois.mots_cles(lire, texte)
    lu = en_parallele(**taches)
    s.mots_cles = lu.get("mots_cles") or ""
    updates = lu["profil"] or {}
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
    positions = lu.get("soins") or {}
    if champ in (None, "care_access") and not question and not positions and soins.accepte_tout(texte):
        # « tous les modèles », « alle Modelle », « all models » : lu par Python si Apertus l'a manqué
        positions = {m: {"stance": "accepted", "condition": None, "evidence": None} for m in soins.NOMS_MODES}
    # Formulations explicites que Python lit lui-même si Apertus les a manquées (module regles)
    updates = regles.completer_par_regles(updates, texte, champ, suivi=suivi, question=question and not suivi)
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

    if libre:
        besoins = lu.get("besoins") or []
        nouveaux = [b for b in besoins if b not in p["besoins"]]
        if nouveaux:
            p["besoins"] += nouveaux
            s.textes_besoins.append(texte)
            change = True
        # Santé : Apertus classe seulement ; les réponses sont des textes fixes et des calculs
        for element in lu.get("sante") or []:
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
    explique = False  # la raison du refus est déjà dite : pas de « je n'ai pas compris »
    if champ == "commune":
        question = tr("Quelle commune faut-il retenir : {liste} ?", L(),
                      liste=", ".join(libelle_commune(c) for c in s.choix_communes))
    elif champ == "budget":
        question = tr(conversation.QUESTION_BUDGET, L())
    else:
        question = tr(QUESTIONS[champ], L())
        fact = p["contract"].facts[champ]
        if fact.state == State.CONFLICT:
            question = tr("Deux réponses diffèrent : {a} et {b}. ", L(), a=fact.previous, b=fact.value) + question
        elif fact.state == State.INVALID:
            question = tr("Cette valeur n'est pas valide. ", L()) + question
        elif fact.state == State.AMBIGUOUS:
            question = tr("Cette information reste incertaine. ", L()) + question
        elif (champ == "deductible" and fact.state == State.KNOWN and isinstance(fact.value, int)
              and p["contract"].rating_age() is not None):
            # Montant légal en soi, mais pas pour cet âge (ex. 0 CHF pour un adulte) : on dit pourquoi
            permises = FRANCHISES[classe_age(p["contract"].rating_age())]
            explique = True
            question = tr("Une franchise de {v} CHF n'existe pas pour votre âge : les franchises possibles sont "
                          "{liste} CHF. ", L(), v=fact.value, liste=", ".join(map(str, permises))) + question
    if s.lieu_inconnu and champ in ("postal_code", "municipality"):
        question = tr("Le lieu est inconnu ou le code postal et la commune ne correspondent pas. ", L()) + question
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
        dire(tr("Je n'ai pas compris quels modèles vous acceptez : je compare le modèle standard (libre choix) et je "
                "vous montre ensuite ce que coûteraient les autres. Vous pourrez préciser après.", L()))
        s.repetitions = {}
        return None
    if (repetitions[champ] >= 2 and champ in EXEMPLES_REPONSE and not question_posee
            and not explique):
        question = (tr("Je n'ai pas compris votre réponse. ", L()) + question
                    + tr(" Par exemple : « {ex} ».", L(), ex=tr(EXEMPLES_REPONSE[champ], L())))
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
    """Rédaction par Apertus 70B, seulement s'il reste du temps dans ce tour (sinon : question seule)."""
    if time.time() > st.session_state.get("echeance", float("inf")):
        raise ErreurLLM("délai du tour dépassé")
    return appel("demander_llm", config()["LLM_NAME_RESTITUTION"], DELAI_70B)(systeme, message)


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
        # Chiffres de franchise et de budget dès que la personne en parle ou pose une question
        parle_franchise = (champ == "deductible" or question_posee
                           or re.search(r"franchise|budget|prime|co[uû]t|cher|payer|possible", tour["texte"], re.I))
        dire(conversation.repondre_tour(
            appeler_70b, tour["texte"], notes, question_posee, question,
            chiffres=chiffres_franchise() if parle_franchise else "",
            contexte="; ".join(f"{k} : {v}" for k, v in apres.items()),
            passe=conversation.historique(s.messages[:-1]), langue=nom_langue(), code=L(),
            passages=articles_de_loi(tour["texte"]) if question_posee else ()))
    if not champ:
        if s.get("profil_formulaire"):
            # Profil venu du formulaire : pas de résumé « Est-ce correct ? », on recalcule directement
            calculer()
        else:
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
    s.echeance = time.time() + LIMITE_TOUR
    s.messages.append({"role": "user", "type": "texte", "contenu": texte})
    detectee = langues.detecter(texte)
    if detectee:
        # La personne écrit dans une autre langue : on lui répond dans celle-ci. Le menu « Langue » est déjà
        # affiché quand le message est traité (en bas de la page) : il prend la langue au tour suivant.
        s.langue_detectee = detectee
    question = conversation.est_question(texte)
    tour = {"texte": texte, "question": question, "avant": faits_connus()}
    if s.attente == "commune" and choisir_commune_texte(texte):
        avancer()
    elif s.etape == "resultats" and not question and (
            s.attente in ("caisse", "caisse_choix") or changement.trouver_caisses(texte)) and traiter_caisse(texte):
        pass
    elif s.etape == "resultats" and s.attente == "lettre" and (_OUI.search(texte) or _NON.search(texte)):
        repondre_lettre_texte(bool(_OUI.search(texte)))
    elif s.etape == "resultats" and (s.get("economie") or {}).get("caisse") and demande_lettre(texte):
        ecrire_lettre()
    elif s.etape == "resultats":
        if s.attente in ("caisse", "caisse_choix", "lettre"):
            s.attente = None  # la personne passe à autre chose : on ne réinsiste pas
        avant = s.profil["contract"].context(), s.profil["budget"]
        integrer(texte, question=question, suivi=True)
        if (s.profil["contract"].context(), s.profil["budget"]) != avant:
            avancer(tour)  # une information change : nouveau résumé à confirmer, puis nouveau calcul
        else:
            repondre_apres_resultats(texte)
            ligne = subsides.office(s.profil["canton"], L()) if subsides.PARLE_DE_SUBSIDE.search(texte) else None
            if ligne:  # question sur les subsides : l'office de son canton, lien officiel (liste OFSP)
                dire(ligne)
    else:
        integrer(texte, champ=s.attente if s.attente not in (None, "confirmation") else None,
                 question=question)
        avancer(tour)


def articles_de_loi(texte):
    """Alinéas des vrais textes de loi les plus proches de la question (recherche Python, lois.py)."""
    try:
        return lois.chercher(texte, L(), st.session_state.get("mots_cles", ""))
    except Exception:
        return []


def demande_lettre(texte):
    """« Rédigez-moi la lettre de résiliation » (une demande), mais pas « comment l'envoyer ? »."""
    if not re.search(r"lettre|r[ée]siliation|k[üu]ndigung|disdetta|lettera|cancellation|letter", texte, re.IGNORECASE):
        return False
    return bool(len(texte.split()) <= 4 or re.search(
        r"r[ée]dig|[ée]cri[sv]|refai|fai[st]es|donne|veux|voudrais|schreib|verfass|scriv|redig|write|draft|redo|"
        r"again|nouvelle|neue|nuova|another", texte, re.IGNORECASE))


def repondre_lettre_texte(oui):
    s = st.session_state
    if oui:
        ecrire_lettre()
    else:
        s.attente = None
        dire(tr("D'accord. Vous pouvez me la demander plus tard en écrivant « lettre de résiliation ».", L()))


def repondre_apres_resultats(texte):
    """Conversation libre après les résultats : Apertus répond avec les chiffres affichés et la fiche LAMal."""
    s = st.session_state
    bloc = s.resultats[-1] if s.resultats else None
    reponse = None
    if bloc is not None:
        reponse = conversation.repondre_libre(
            appeler_70b, texte, bloc.get("faits", ""), bloc.get("chiffres_franchise", ""),
            passe=conversation.historique(s.messages[:-1]), langue=nom_langue(), code=L(),
            passages=articles_de_loi(texte))
    dire(reponse or tr("Je ne peux pas répondre de façon fiable à cette question ici ; vous pouvez vérifier sur "
                       "priminfo.admin.ch. Pour changer une information, écrivez par exemple « et avec une "
                       "franchise de 300 ? » ou « j'habite à 1003 ».", L()))


# --------------------------------------------------------------------------------------
# Calcul : comparateur + explications vérifiées (code existant)
# --------------------------------------------------------------------------------------
INTRO_DE_SECOURS = "Voici les offres retenues selon vos catégories acceptées. Comparez les primes, franchises et conditions."

PROMPT_OUVERTURE = """Tu ouvres la conversation : la personne vient de remplir le formulaire de l'application, et tu es
son conseiller en assurance maladie de base (LAMal), propulsé par Apertus, le modèle de langue suisse. Ses offres
sont affichées juste en dessous de ton texte.
Écris un seul paragraphe de 4 à 6 phrases, dans cet ordre :
1. Remercie-la d'avoir rempli le formulaire et présente-toi en une phrase.
2. Reprends ce qu'elle a indiqué dans le formulaire (âge en 2027, commune, situation professionnelle, modèles
   acceptés) et dis ce que cela change pour elle, d'après les faits (catégorie d'âge, couverture accidents).
3. Présente l'offre la moins chère et le compromis entre le prix et les contraintes, d'après les faits.
4. Dis que toutes les franchises ont été comparées et donne le seuil de frais indiqué dans les faits, s'il y en a un.
5. Si les faits contiennent des besoins hors assurance de base, dis en une phrase ce que l'assurance de base ne
   paie pas pour eux et qu'il faut une assurance complémentaire pour cela.
6. Termine en l'invitant à te poser ses questions, par exemple sur la franchise ou sur un modèle.
Règles strictes :
- Utilise UNIQUEMENT les faits fournis. N'ajoute aucune information extérieure.
- Ne fais AUCUN calcul. Recopie les montants exactement (avec les centimes) ou n'en cite pas.
- Ne recommande aucune offre : présente les compromis, la décision reste à la personne.
- Vouvoie la personne. Écris en {langue} simple et chaleureux, sans liste ni titre."""

_CATEGORIES_AGE = {"AKA_01_KIN": "enfant (jusqu'à 18 ans)", "AKA_02_JUG": "jeune adulte (19 à 25 ans)",
                   "AKA_03_ERW": "adulte (26 ans et plus)"}


def recapitulatif_formulaire(l):
    """Les réponses du formulaire en étiquettes courtes, affichées dans la carte d'ouverture."""
    p = st.session_state.profil
    c = p["contract"]
    modeles = c.known("care_access") or []
    etiquettes = [("🎂", tr("{age} ans en {annee}", l, age=p["age"], annee=c.premium_year)),
                  ("📍", f"{p['commune']} ({p['canton']})")]
    if c.accident() is not None:
        etiquettes.append(("🩹", tr("Accidents inclus", l) if c.accident() else tr("Accidents exclus (employeur)", l)))
    etiquettes.append(("🩺", tr("Tous les modèles", l) if set(modeles) == set(CARE_TYPES)
                       else ", ".join(tr(CARE_LABELS[k], l) for k in modeles)))
    etiquettes.append(("💰", tr("Toutes les franchises comparées", l)))
    besoins = st.session_state.get("hors_lamal") or []
    if besoins:
        etiquettes.append(("➕", tr("Hors assurance de base : {x}", l,
                                    x=", ".join(hors_lamal.libelle(c, l).lower() for c in besoins))))
    return etiquettes


def suggestions_formulaire(props):
    """Questions proposées d'après le formulaire et les offres (textes français, traduits à l'affichage)."""
    p = st.session_state.profil
    c = p["contract"]
    questions = ["Quelle franchise est la plus avantageuse pour moi ?"]
    modele = props[0]["modele"] if props else ""
    if modele.startswith("Médecin de famille"):
        questions.append("Comment fonctionne le modèle médecin de famille ?")
    elif modele.startswith("Télémédecine"):
        questions.append("Comment fonctionne la télémédecine ?")
    elif modele.startswith("Pharmacie"):
        questions.append("Comment fonctionne le modèle pharmacie ?")
    if st.session_state.get("f_situation") in ("sans_emploi", "salarie_moins") or (p["age"] or 99) <= 25:
        questions.append("Ai-je droit à un subside pour payer ma prime ?")
    elif c.accident() is False:
        questions.append("Que se passe-t-il pour les accidents si je quitte mon emploi ?")
    questions.append("Jusqu'à quand puis-je changer de caisse ?")
    return questions[:4]


def afficher_ouverture():
    """Carte d'ouverture : le conseiller reprend le formulaire (étiquettes), puis le message d'Apertus.
    Les questions proposées sont en bas de la conversation (afficher_questions)."""
    s, l = st.session_state, L()
    with st.container(key="ouverture"):
        style.ouverture(tr("Votre conseiller LAMal", l), tr("Apertus · en ligne", l),
                        tr("D'après votre formulaire", l), recapitulatif_formulaire(l), s.ouverture["texte"])


def poser(question):
    """Clic sur une question proposée : elle est traitée en bas de la page, comme un message écrit."""
    st.session_state.question_en_attente = question


def afficher_questions():
    """En bas de la conversation, juste au-dessus de la zone de saisie : « Posez-moi vos questions », avec les
    questions proposées d'après le formulaire (sans celles déjà posées). La réponse arrive juste en dessous."""
    s, l = st.session_state, L()
    if not s.get("resultats"):
        return
    posees = {m.get("contenu") for m in s.messages if m["role"] == "user"}
    proposees = [(i, tr(q, l)) for i, q in enumerate((s.get("ouverture") or {}).get("suggestions", []))
                 if tr(q, l) not in posees]
    with st.container(key="questions"):
        st.markdown(f"**{tr('Posez-moi vos questions', l)}**")
        if proposees:
            with st.container(horizontal=True, key="suggestions"):
                for i, q in proposees:
                    st.button(q, key=f"suggestion_{i}", on_click=poser, args=(q,))
        st.caption(tr("Ou écrivez la vôtre ci-dessous, par exemple « que couvre la LAMal ? » ou « et avec une "
                      "franchise de 300 ? ». La réponse s'affiche juste ici.", l))


def faits_formulaire(props):
    """Ce que la personne a rempli dans le formulaire et ce que cela change, puis ses offres : la base de
    l'ouverture rédigée par Apertus. Tout vient du formulaire et des calculs Python."""
    s = st.session_state
    p = s.profil
    c = p["contract"]
    lignes = ["Ce que la personne a rempli dans le formulaire, et ce que cela change :",
              f"- Année de naissance {c.known('birth_year')} : {p['age']} ans en {c.premium_year}, catégorie de "
              f"primes {_CATEGORIES_AGE[classe_age(p['age'])]}.",
              f"- Domicile : {p['commune']} ({p['canton']}), code postal {p['npa']}, région de primes {p['region']}."]
    if s.get("f_situation") in SITUATIONS:
        lignes.append(f"- Situation professionnelle : {SITUATIONS[s.f_situation]}.")
    if c.accident() is True:
        lignes.append("- Couverture accidents : incluse dans l'assurance de base, car aucun employeur ne l'assure "
                      "contre les accidents non professionnels (il faut au moins 8 h par semaine chez un même "
                      "employeur pour cela).")
    elif c.accident() is False:
        lignes.append("- Couverture accidents : exclue de l'assurance de base, car son employeur l'assure déjà contre "
                      "les accidents non professionnels (au moins 8 h par semaine chez lui) ; la prime est plus basse.")
    modeles = c.known("care_access") or []
    lignes.append("- Modèles acceptés : " + ("tous (" if set(modeles) == set(CARE_TYPES) else "")
                  + ", ".join(CARE_LABELS[k] for k in modeles) + (")" if set(modeles) == set(CARE_TYPES) else "") + ".")
    lignes.append("- Franchise : le formulaire ne la demande pas ; toutes les franchises sont comparées.")
    besoins = hors_lamal.faits(s.get("hors_lamal") or [])
    if besoins:
        lignes += ["Besoins cochés dans le formulaire, hors assurance de base (l'application les détaille après "
                   "le choix d'une offre) :"] + besoins
    lignes += ["Offres affichées sous ton texte :", faits_propositions(props, p["priorite"])]
    retenir = [l.replace("À RETENIR : ", "- ") for l in chiffres_franchise().splitlines() if l.startswith("À RETENIR")]
    if retenir:
        lignes += ["Franchise (calculs de l'application) :"] + retenir
    return "\n".join(lignes)


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
    ouverture = bool(props and s.get("profil_formulaire") and not s.resultats)
    if ouverture:
        # Juste après le formulaire : Apertus ouvre la conversation en reprenant ce qui a été rempli
        s.ouverture = {"texte": chatbot.expliquer(
                           client().with_options(timeout=DELAI_70B), cfg["LLM_NAME_RESTITUTION"],
                           faits_formulaire(props), nom_langue(), prompt=PROMPT_OUVERTURE,
                           secours=tr(APRES_FORMULAIRE, L())),
                       "suggestions": suggestions_formulaire(props)}
    elif props:
        bloc["intro"] = chatbot.expliquer(client().with_options(timeout=DELAI_70B), cfg["LLM_NAME_RESTITUTION"],
                                          faits_propositions(props, p["priorite"]), nom_langue(),
                                          prompt=PROMPT_INTRO, secours=tr(INTRO_DE_SECOURS, L()))
    if s.sante and p["franchise"] is not None:
        reference = (props[0]["assureur"], props[0]["produit"]) if props else None
        bloc["sante"] = sante.analyser(p, s.sante, reference)
    if p["besoins"]:
        choix = compl.produits_pour(p["besoins"])
        bloc["compl"] = {
            "categories": list(p["besoins"]), "choix": choix,
            "meilleurs": {c: compl.meilleurs_produits(choix, c, p["age"]) for c in p["besoins"]}}
    bloc["budget"] = p["budget"]
    bloc["canton"] = p["canton"]
    bloc["faits"] = faits_resultats(bloc)
    bloc["chiffres_franchise"] = chiffres_franchise()
    s.resultats.append(bloc)
    if ouverture:
        s.messages.append({"role": "assistant", "type": "ouverture"})
    s.messages.append({"role": "assistant", "type": "resultats", "index": len(s.resultats) - 1})
    s.etape, s.attente = "resultats", None
    if props and s.get("caisse_lue") is None and not s.get("caisse_demandee"):
        s.caisse_demandee = True
        dire(tr(QUESTION_CAISSE, L()))
        s.attente = "caisse"
    elif props and s.get("caisse_lue"):  # nouvelle comparaison : l'économie est recalculée (Python seul)
        montrer_economie(**s.caisse_lue, rediger=False)


# --------------------------------------------------------------------------------------
# Caisse actuelle, économie et lettre de résiliation (module changement)
# --------------------------------------------------------------------------------------
QUESTION_CAISSE = ("Chez quelle caisse maladie êtes-vous assuré(e) aujourd'hui, et avec quel modèle (libre choix, "
                   "médecin de famille, télémédecine…) ? Je calcule ce que vous économiseriez en changeant. "
                   "C'est facultatif.")
_OUI = re.compile(r"^\s*(?:oui|ouais|volontiers|avec plaisir|d'accord|ok|okay|yes|yep|sure|please|ja|gerne|bitte|"
                  r"s[iì]|certo|volentieri|va bene)\b", re.IGNORECASE)
_NON = re.compile(r"^\s*(?:non|nein|no|nope|pas besoin|pas maintenant|nicht nötig|niente|no grazie)\b", re.IGNORECASE)


def traiter_caisse(texte):
    """Réponse à la question sur la caisse actuelle. True si le message a été traité ici."""
    s, cfg = st.session_state, config()
    lu = changement.lire_caisse(appel("demander_llm_json", cfg["LLM_NAME"], DELAI_8B), texte)
    if len(lu["caisses"]) > 1:
        s.choix_caisses, s.caisse_partielle = lu["caisses"], lu
        dire(tr("Plusieurs caisses portent ce nom. Laquelle figure sur votre police d'assurance ?", L()))
        s.attente = "caisse_choix"
        return True
    if not lu["caisses"] and lu["prime_mois"] is None:
        return False
    return montrer_economie(lu["caisses"][0] if lu["caisses"] else None, lu["modele"], lu["prime_mois"])


def montrer_economie(numero=None, modele=None, prime_mois=None, rediger=True):
    """Paragraphe d'économie : chiffres calculés par Python, texte rédigé par Apertus 70B et vérifié."""
    s = st.session_state
    bloc, profil = s.resultats[-1], s.profil["comparison"]
    e = changement.calculer_economie(profil, bloc["offres"], numero, modele, prime_mois,
                                     chatbot.no_ofs_de(profil.municipality, profil.canton))
    if e is None:
        return False
    s.caisse_lue = {"numero": numero, "modele": modele, "prime_mois": prime_mois}
    s.attente = None
    if e.get("absente"):
        dire(tr("{caisse} ne propose pas d'assurance de base pour votre profil dans votre région en 2027 : vous "
                "devrez de toute façon choisir une autre caisse.", L(), caisse=e["caisse"]))
        s.economie = dict(e, autre_caisse={"caisse": bloc["offres"].iloc[0]["Assureur"]})
    else:
        texte = None
        if rediger:
            try:
                brut = conversation.demander_verifie(
                    appeler_70b, changement.PROMPT_ECONOMIE.replace("{langue}", nom_langue()),
                    changement.faits_economie(e), doit_questionner=False, code=L())
                texte = conversation.raccourcir(conversation.nettoyer(brut), 4) if brut else None
            except ErreurLLM:
                texte = None
        dire(texte or changement.texte_economie_secours(e, L()))
        s.economie = e
    if rediger and e["caisse"] and s.economie.get("autre_caisse"):
        dire(tr("Souhaitez-vous que je rédige votre lettre de résiliation pour {caisse} ?", L(), caisse=e["caisse"]))
        s.attente = "lettre"
    return True


def choisir_caisse(numero):
    s = st.session_state
    s.messages.append({"role": "user", "type": "texte", "contenu": changement.CAISSES[numero]})
    lu = s.get("caisse_partielle") or {}
    montrer_economie(numero, lu.get("modele"), lu.get("prime_mois"))


def ecrire_lettre():
    """Lettre de résiliation rédigée par Apertus 70B ; Python vérifie les éléments obligatoires."""
    s, cfg = st.session_state, config()
    e, profil = s.economie, s.profil["comparison"]
    langue = changement.langue_lettre(L(), profil.canton)
    # La lettre est la tâche principale de ce tour : un délai à elle (deux essais au plus)
    rediger = appel("demander_llm", cfg["LLM_NAME_RESTITUTION"], 40)
    lettre, par = changement.rediger_lettre(rediger, e["caisse"], langue, profil.premium_year)
    adresse = caisses.adresse_postale(e.get("numero"))
    if adresse:  # adresse officielle de la caisse (liste OFSP) à la place du champ à compléter
        lettre = lettre.replace(changement.CHAMP_ADRESSE_CAISSE[langue], "\n".join(adresse[1:]))
    s.messages.append({"role": "assistant", "type": "lettre", "texte": lettre, "langue": langue, "par": par,
                       "annee": profil.premium_year})
    s.attente = None


NUMEROS_CAISSES = {nom: numero for numero, nom in ASSUREURS.items()}


def lancer(action, *args):
    """Rappel de bouton : l'action s'exécute avant l'affichage suivant (Apertus peut ne pas répondre)."""
    try:
        action(*args)
    except ErreurLLM:
        dire(tr("Apertus ne répond pas pour le moment. Réessayez dans un instant.", L()))


def choisir_offre(index, j):
    """« Choisir cette offre » : Apertus rédige la demande d'affiliation, Python la vérifie ; l'écran
    suivant donne tout ce qu'il faut pour l'envoyer (e-mail prêt, contacts officiels, étapes)."""
    s, cfg = st.session_state, config()
    p = s.resultats[index]["propositions"][j]
    profil = s.profil["comparison"]
    numero = NUMEROS_CAISSES.get(p["assureur"])
    ancienne = (s.get("economie") or {}).get("caisse")
    choix = {"caisse": p["assureur"], "numero": numero, "produit": p["produit"], "modele": p["modele"],
             "franchise": int(p["franchise"]), "prime_mois": float(p["prime_mois"]),
             "accident": bool(profil.include_accident), "annee": profil.premium_year,
             "ancienne": ancienne if ancienne and ancienne != p["assureur"] else None,
             "meme_caisse": bool(ancienne and ancienne == p["assureur"]),
             "numero_ancienne": (s.get("economie") or {}).get("numero")}
    l = L()
    # Pas de faux message « Je choisis … » au nom de la personne : elle ne l'a pas écrit (retour de Damian).
    langue = changement.langue_lettre(l, profil.canton)
    rediger = appel("demander_llm", cfg["LLM_NAME_RESTITUTION"], 40)
    texte, par = affiliation.rediger(rediger, choix, langue)
    s.choix = choix
    # Un seul choix à la fois : la nouvelle offre remplace l'ancienne fiche dans la conversation (sinon
    # l'ancienne restait affichée plus haut et on croyait que le choix n'avait pas changé).
    s.messages = [m for m in s.messages if m["type"] != "affiliation"]
    s.messages.append({"role": "assistant", "type": "affiliation", "choix": choix, "texte": texte, "par": par,
                       "langue": langue, "objet": affiliation.objet(choix, langue)})
    s.attente = None


def demander_choix(index, j):
    """Clic sur « Choisir cette offre » : la fenêtre du choix s'ouvre à l'affichage suivant."""
    st.session_state.choix_demande = (index, j)


def ouvrir_fenetre_choix(index, j):
    """Fenêtre qui s'ouvre par-dessus la page : Apertus prépare la demande, puis les étapes jusqu'à
    l'inscription. Le choix reste aussi dans la conversation (on peut fermer la fenêtre et y revenir)."""
    s, l = st.session_state, L()
    p = s.resultats[index]["propositions"][j]

    @st.dialog(tr("Votre choix : {caisse}", l, caisse=p["assureur"]), width="large", on_dismiss="rerun")
    def fenetre():
        if s.get("choix_affiche") != (index, j):  # rédigée une seule fois, même si la fenêtre se réaffiche
            try:
                with st.spinner(tr("Apertus prépare votre demande d'affiliation…", l)):
                    choisir_offre(index, j)
            except ErreurLLM:
                st.error(tr("Apertus ne répond pas pour le moment. Réessayez dans un instant.", l))
                return
            s.choix_affiche = (index, j)
        i = max(k for k, m in enumerate(s.messages) if m["type"] == "affiliation")
        afficher_affiliation(s.messages[i], i, suffixe="_fenetre")

    fenetre()


def afficher_affiliation(m, i, suffixe=""):
    """« Check-out » : récapitulatif du choix, puis les étapes, chacune avec ce qu'il faut pour la faire."""
    l, ch = L(), m["choix"]
    contact = caisses.contact(ch["numero"])
    debut = affiliation.debut_couverture(ch["annee"])
    fin, limite = changement.dates(ch["annee"])
    with st.container(key=f"checkout_{i}{suffixe}"):
        style.recapitulatif_choix(
            tr("Votre choix : assurance de base (LAMal)", l), ch["caisse"], f"{ch['produit']} — {tr(ch['modele'], l)}",
            [tr("Assurance de base (LAMal) uniquement", l), tr("Franchise {f} CHF", l, f=ch["franchise"]),
             tr("Accidents inclus", l) if ch["accident"] else tr("Accidents exclus (employeur)", l),
             tr("Dès le {debut}", l, debut=f"{debut.day:02d}.{debut.month:02d}.{debut.year}")],
            f"{ch['prime_mois']:.2f}", tr("CHF / mois", l))
        st.caption(tr("Vous avez cliqué sur « Choisir cette offre ». Rien n'est envoyé ni signé : c'est vous qui "
                      "décidez d'envoyer la demande. Vous pouvez choisir une autre offre plus haut.", l))

        # Étape 1 : demande d'affiliation
        st.markdown(f"**1. {tr('Demander l’assurance de base (LAMal) à {caisse}', l, caisse=ch['caisse'])}**")
        if m["par"] == "apertus":
            st.caption(tr("Demande rédigée par Apertus ; les éléments obligatoires ont été vérifiés par l'application.", l))
        else:
            st.caption(tr("Demande modèle de l'application (celle d'Apertus n'était pas complète).", l))
        texte = m["texte"]
        if contact and contact["email"]:
            st.link_button("✉️ " + tr("Envoyer ma demande à {caisse}", l, caisse=ch["caisse"]),
                           affiliation.lien_mailto(contact["email"], m["objet"], texte), type="primary",
                           width="stretch")
            st.caption(tr("Votre messagerie s'ouvre avec la demande prête, adressée à {email} (adresse officielle, "
                          "liste OFSP). Complétez les champs entre crochets, puis envoyez.", l, email=contact["email"])
                       + " " + tr("Cette demande concerne uniquement l'assurance de base (LAMal).", l))
        elif contact:
            st.caption(tr("{caisse} ne publie pas d'adresse e-mail dans la liste officielle de l'OFSP : envoyez la "
                          "demande par la poste (adresse déjà dans la lettre) ou via son site.", l, caisse=ch["caisse"]))
        lien, genre = caisses.lien_inscription(ch["numero"])
        if lien:
            libelle = {"offre": tr("Calculer et demander mon offre chez {caisse}", l, caisse=ch["caisse"]),
                       "page": tr("Assurance de base de {caisse} (site officiel)", l, caisse=ch["caisse"]),
                       "site": tr("Site officiel de {caisse}", l, caisse=ch["caisse"])}[genre]
            st.link_button("🌐 " + libelle, lien, width="stretch")
            st.caption(tr("Sur le site, choisissez l'assurance de base (LAMal) : {produit} ({modele}), franchise {f} "
                          "CHF, {accidents}, début le {debut}.", l, produit=ch["produit"], modele=tr(ch["modele"], l), f=ch["franchise"],
                          accidents=tr("accidents inclus", l) if ch["accident"] else tr("accidents exclus", l),
                          debut=f"{debut.day:02d}.{debut.month:02d}.{debut.year}"))
        if m["langue"] != l:
            st.caption(tr("La demande est écrite dans une langue officielle de votre canton.", l))
        lettre = affiliation.avec_adresse(texte, ch["numero"], ch["caisse"])
        with st.expander(tr("Voir et copier la demande", l)):
            st.code(lettre, language=None, wrap_lines=True)
            st.download_button(tr("Télécharger la demande (.txt)", l), data=lettre.encode("utf-8"),
                               file_name="demande_affiliation.txt", mime="text/plain", key=f"affiliation_{i}{suffixe}")
        if contact:
            liens = []
            if contact["telephone"]:
                liens.append(f"📞 {contact['telephone']}")
            adresse = caisses.adresse_postale(ch["numero"], ch["caisse"])
            if adresse:
                liens.append("📮 " + ", ".join(adresse[1:]))
            st.markdown(" · ".join(liens))
        if ch["modele"].startswith("Médecin de famille"):
            st.caption(tr("Modèle médecin de famille : choisissez votre médecin dans la liste de {caisse} (sur son "
                          "site) et indiquez-le dans la demande ou à la réception des documents.", l, caisse=ch["caisse"]))

        # Étape 2 : confirmation de la nouvelle caisse
        st.markdown(f"**2. {tr('Attendre la confirmation écrite de {caisse}', l, caisse=ch['caisse'])}**")
        st.caption(tr("Votre assurance actuelle ne prend fin que lorsque la nouvelle caisse a confirmé votre "
                      "couverture (LAMal art. 7 al. 5). Toute caisse doit accepter chaque personne pour "
                      "l'assurance de base, sans questionnaire de santé.", l))

        # Étape 3 : résiliation
        st.markdown(f"**3. {tr('Résilier l’assurance de base (LAMal) chez votre caisse actuelle avant le {limite}', l, limite=f'{limite.day}.{limite.month:02d}.{limite.year}')}**")
        st.caption(tr("La lettre résilie uniquement l'assurance de base (LAMal). Vos assurances complémentaires "
                      "continuent chez votre caisse actuelle.", l))
        deja = any(x["type"] == "lettre" for x in st.session_state.messages)
        if ch.get("meme_caisse"):
            st.caption("✅ " + tr("Vous restez chez {caisse} : rien à résilier, la demande ci-dessus suffit pour changer "
                                 "de produit ou de franchise (même délai).", l, caisse=ch["caisse"]))
        elif deja:
            st.caption("✅ " + tr("Votre lettre de résiliation est prête plus haut dans la conversation.", l))
        elif ch.get("ancienne"):
            bouton(tr("Rédiger ma lettre de résiliation pour {caisse}", l, caisse=ch["ancienne"]), ecrire_lettre,
                   cle=f"resiliation_{i}{suffixe}")
        else:
            st.caption(tr("Dites-moi chez quelle caisse vous êtes aujourd'hui : je rédige la lettre de résiliation. "
                          "Si vous arrivez en Suisse, il n'y a rien à résilier.", l))
        st.download_button("📅 " + tr("Ajouter un rappel à mon agenda", l),
                           data=affiliation.rappel_ics(limite, ch.get("ancienne") or tr("votre caisse actuelle", l), l)
                           .encode("utf-8"), file_name="rappel_resiliation.ics", mime="text/calendar",
                           key=f"rappel_{i}{suffixe}")

        # Étape 4 : ce que l'assurance de base ne couvre pas, et les complémentaires
        afficher_hors_lamal(ch, contact)


def afficher_hors_lamal(ch, contact):
    """Ce que l'assurance de base ne paie pas (besoins cochés, sinon les cas fréquents), puis un message
    clair : pour cela, il faut une complémentaire, avec les règles pour ne rien perdre."""
    l = L()
    choisis = st.session_state.get("hors_lamal") or []
    st.markdown(f"**4. {tr('Ce que l’assurance de base ne paie pas', l)}**")
    if not choisis:
        st.caption(tr("Vous n'avez rien coché dans le formulaire : voici les cas les plus fréquents.", l))
    style.tableau_hors_lamal(
        [tr("Besoin", l), tr("L'assurance de base paie", l), tr("Elle ne paie pas", l)],
        hors_lamal.lignes(choisis or list(hors_lamal.BESOINS), l), tr("Source", l), " : " if l == "fr" else ": ")
    site = contact["site"] if contact else None
    st.info("\n\n".join([
        "**" + tr("Pour ce que l'assurance de base ne paie pas, il faut une assurance complémentaire.", l) + "**",
        tr("Les complémentaires sont des assurances privées : la caisse peut poser des questions sur votre santé, "
           "émettre des réserves ou refuser. Leurs primes ne sont pas publiées : demandez une offre.", l),
        tr("Vous pouvez avoir l'assurance de base et les complémentaires dans des caisses différentes. Votre caisse "
           "actuelle ne peut ni vous obliger à résilier vos complémentaires, ni les résilier parce que vous changez "
           "d'assurance de base (LAMal art. 7 al. 7 et 8).", l),
        tr("Si vous voulez changer aussi de complémentaire : ne résiliez l'ancienne qu'après avoir reçu "
           "l'acceptation écrite de la nouvelle.", l)]
        + ([tr("Complémentaires de {caisse} : [{site}]({lien}).", l, caisse=ch["caisse"],
               site=site.replace("https://", ""), lien=site)] if site else [])), icon="➕")


def repondre_lettre(oui):
    s = st.session_state
    l = L()
    s.messages.append({"role": "user", "type": "texte",
                       "contenu": tr("Oui, rédigez ma lettre", l) if oui else tr("Non merci", l)})
    if oui:
        ecrire_lettre()
    else:
        s.attente = None
        dire(tr("D'accord. Vous pouvez me la demander plus tard en écrivant « lettre de résiliation ».", l))


def passer_caisse():
    s = st.session_state
    s.messages.append({"role": "user", "type": "texte", "contenu": tr("Passer", L())})
    s.attente = None


def faits_resultats(bloc):
    """Ce qui est affiché, en texte, pour que les réponses d'Apertus s'appuient dessus."""
    p = st.session_state.profil
    lignes = ["Profil : " + "; ".join(f"{k} : {v}" for k, v in faits_connus().items())]
    if bloc["propositions"]:
        lignes.append(faits_propositions(bloc["propositions"], p["priorite"]))
    for l in bloc.get("preferences") or []:
        lignes.append(f"Modèle non retenu {l['modele']} : dès {l['prime_mois']:.2f} CHF par mois "
                      f"({l['assureur']}), écart de {l['ecart_an']:.2f} CHF par an avec l'offre retenue.")
    if not bloc["offres"].empty:
        o = bloc["offres"].iloc[0]
        qp = int(o["Coût max/an"] - o["Prime/an"] - o["Franchise"])
        lignes.append(f"Au pire (frais médicaux élevés), l'offre la moins chère ({o['Assureur']}, franchise "
                      f"{int(o['Franchise'])} CHF) coûte au maximum {o['Coût max/an']:.2f} CHF dans l'année : "
                      f"{o['Prime/an']:.2f} CHF de primes + {int(o['Franchise'])} CHF de franchise + {qp} CHF de "
                      f"quote-part maximale (plus 15 CHF par jour d'hôpital pour un adulte).")
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
    return tr("Votre budget : {b} CHF par mois au maximum. {n} offre(s) sur {total} le respectent.", L(),
              b=b[1], n=n, total=len(bloc["offres"]))


# --------------------------------------------------------------------------------------
# Affichage
# --------------------------------------------------------------------------------------
def afficher_profil(p, nb_sante=0):
    c, l = p["contract"], L()
    sep = " :" if l == "fr" else ":"  # espace avant les deux-points seulement en français
    accident = tr("incluse" if c.accident() else "exclue", l)
    if c.known("include_accident") is not None:
        accident += tr(" — selon votre choix de comparaison", l)
    elif c.known("nonoccupational_covered") is not None:
        accident += tr(" — selon la couverture non professionnelle déclarée", l)
    else:
        accident += tr(" — emploi salarié déclaré, {h} h/semaine chez un même employeur", l,
                       h=f"{c.known('hours_per_week_one_employer'):g}")
    age_label = (tr("Année de naissance : {v}", l, v=c.known("birth_year")) if c.known("birth_year") is not None
                 else tr("Âge déclaré : {v} ans", l, v=c.known("age")))
    franchises = ", ".join(map(str, c.deductibles()))
    care = ", ".join(tr(CARE_LABELS[k], l) for k in c.known("care_access"))
    positions_soins = []
    for position, titre in (("rejected", "Refusé"), ("conditional", "Selon le prix"), ("unsure", "Incertain")):
        modes = soins.par_position(p.get("soins", {}), position)
        if modes:
            positions_soins.append(f"- **{tr(titre, l)}**{sep} " + ", ".join(
                tr(nom, l) + (f" (« {citation} »)" if citation else "") for nom, citation in modes))
    besoins = ", ".join(compl.CATEGORIES[b] for b in p["besoins"]) or tr("aucun", l)
    commune = p["commune"] + (f" ({p['npa']})" if p["npa"] else "")
    b = p.get("budget") or ("", None)
    budget = {"montant": tr("{v} CHF par mois au maximum", l, v=b[1]), "petit": tr("petit budget", l),
              "aucun": tr("pas de limite indiquée", l)}.get(b[0], tr("non indiqué", l))
    priorite = tr(NOMS_PRIORITE[p["priorite"]], l) if p["priorite"] in NOMS_PRIORITE else tr("aucune indiquée", l)
    st.markdown("**" + tr("Voici ce que j'ai compris. Est-ce correct ?", l) + "**")
    st.markdown("\n".join([
        f"- **{age_label}** ({tr('catégorie tarifaire vérifiée pour {annee}', l, annee=c.premium_year)})",
        f"- **{tr('Commune', l)}**{sep} {commune}",
        f"- **{tr('Canton', l)}**{sep} {p['canton']}",
        f"- **{tr('Région de primes', l)}**{sep} {p['region']}",
        f"- **{tr('Franchise(s)', l)}**{sep} {franchises} CHF",
        f"- **{tr('Modèles acceptés', l)}**{sep} {care}",
    ] + positions_soins + [
        f"- **{tr('Couverture accident', l)}**{sep} {accident}",
        f"- **{tr('Priorité', l)}**{sep} {priorite}",
        f"- **{tr('Budget', l)}**{sep} {budget}",
    ] + ([f"- **{tr('Besoins en complémentaires', l)}**{sep} {besoins}"] if MODULES_COMPLEMENTAIRES else []) + ([f"- **{tr('Santé', l)}**{sep} {tr('{n} élément(s) pris en compte', l, n=nb_sante)}"] if nb_sante else [])))


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


def afficher_propositions(bloc, index=None):
    props = bloc["propositions"]
    if not props:
        st.write(tr("Aucune prime trouvée pour ce profil.", L()))
        return
    if bloc["intro"]:
        st.write(bloc["intro"])
    l = L()
    for colonne, p in zip(st.columns(len(props)), props):
        with colonne:
            style.carte(tr(p["titre"], l), f"{p['prime_mois']:.2f}", tr("CHF / mois", l), p["assureur"],
                        f"{p['produit']} — {tr(p['modele'], l)}",
                        tr("La moins chère", l) if p["ecart_mois"] == 0
                        else tr("+{x} CHF / mois par rapport à la moins chère", l, x=f"{p['ecart_mois']:.2f}"),
                        tr("Franchise : {f} CHF. Contrepartie : {c}", l, f=p["franchise"], c=tr(p["contrepartie"], l)),
                        meilleure=p["ecart_mois"] == 0,
                        aussi=tr("Aussi : {x}", l, x=", ".join(tr(x, l).lower() for x in p.get("aussi", [])))
                        if p.get("aussi") else "")
            if index is not None:
                st.button(tr("Choisir cette offre", l), key=f"choisir_{index}_{props.index(p)}",
                          on_click=demander_choix, args=(index, props.index(p)), width="stretch",
                          type="primary" if p["ecart_mois"] == 0 else "secondary")
    st.caption(tr("Compatibilité par catégorie seulement : réseau de médecins, application et conditions du produit à "
                  "vérifier. " + RAPPEL_LAMAL, L()))
    if bloc["offres"]["Franchise"].nunique() > 1:
        st.caption(tr("Plusieurs franchises sont comparées : la prime la plus basse ne signifie pas le coût total de "
                      "soins le plus bas.", L()))


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
    with st.expander(tr("Voir toutes les offres", L())):
        offres = bloc["offres"].drop(columns="Tariftyp")
        if not offres.empty:
            st.markdown(f"**{tr('Assurance de base (LAMal) : {n} offres, de la moins chère à la plus chère (CHF)', L(), n=len(offres))}**")
            offres = offres.assign(Modèle=offres["Modèle"].map(lambda m: tr(m, L())))
            offres = offres.rename(columns={c: tr(c, L()) for c in offres.columns})
            montants = offres.select_dtypes("number").columns
            st.dataframe(offres.style.format({c: "{:.2f}" for c in montants}),
                         hide_index=True, width="stretch")
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
    lg = L()
    st.markdown("### " + tr("Ce que coûtent vos préférences", lg))
    st.write(tr("Pour le même profil, voici l'offre la moins chère de chaque modèle que vous n'avez pas retenu, "
                "comparée à votre offre la moins chère.", lg))
    for l in lignes:
        if l["ecart_an"] < 0:
            ecart = "**" + tr("{x} CHF de moins par an", lg, x=chf(-l["ecart_an"])) + "**"
        elif l["ecart_an"] > 0:
            ecart = "**" + tr("{x} CHF de plus par an", lg, x=chf(l["ecart_an"])) + "**"
        else:
            ecart = "**" + tr("même prime annuelle", lg) + "**"
        raison = soins.raison_non_retenu(l["tariftyp"], positions or {})
        st.markdown(f"- **{tr(l['modele'], lg)}**" + (f" ({tr(raison, lg)})" if raison else "")
                    + tr(" : dès {x} CHF / mois ({assureur}, *{produit}*), soit {ecart}.", lg,
                         x=chf(l["prime_mois"]), assureur=l["assureur"], produit=l["produit"], ecart=ecart))
    st.caption(tr("Écarts de primes uniquement, source OFSP 2027. Chaque modèle a des contraintes propres : vérifiez "
                  "les conditions du produit avant de changer.", lg))


def afficher_lettre(m, i):
    l = L()
    st.markdown(f"**{tr('Votre lettre de résiliation', l)}**")
    if m["par"] == "apertus":
        st.caption(tr("Rédigée par Apertus ; les éléments obligatoires ont été vérifiés par l'application.", l))
    else:
        st.caption(tr("Lettre modèle de l'application (la lettre d'Apertus n'était pas complète).", l))
    if m["langue"] != l:
        st.caption(tr("La lettre est écrite dans une langue officielle de votre canton, celle que votre caisse "
                      "utilise.", l))
    st.caption(tr("Cette lettre résilie uniquement l'assurance de base (LAMal). Vos assurances complémentaires "
                  "continuent.", l))
    st.code(m["texte"], language=None, wrap_lines=True)
    st.download_button(tr("Télécharger la lettre (.txt)", l), data=m["texte"].encode("utf-8"),
                       file_name="resiliation_assurance_de_base.txt", mime="text/plain", key=f"lettre_{i}")
    st.info(changement.conseils_envoi(l, m["annee"]), icon="📮")


def afficher_resultats(bloc, index=None):
    afficher_propositions(bloc, index)
    resume = resume_budget(bloc)
    if resume:
        st.markdown(f"**{resume}**")
    b = bloc.get("budget")
    hors_budget = (b and b[0] == "montant" and not bloc["offres"].empty
                   and bloc["offres"]["Prime/mois"].min() > b[1])
    if b and (b[0] == "petit" or hors_budget):
        ligne = subsides.office(bloc.get("canton") or st.session_state.profil.get("canton"), L())
        st.info(tr(conversation.TEXTE_SUBSIDES, L()) + (f"\n\n{ligne}" if ligne else ""), icon="💡")
    if bloc.get("preferences"):
        afficher_preferences(bloc["preferences"], bloc.get("soins"))
    if bloc.get("sante"):
        afficher_sante(bloc["sante"])
    if bloc["compl"]:
        afficher_meilleurs_complementaires(bloc["compl"])
    afficher_toutes_les_offres(bloc)


def bouton(libelle, action, *args, cle):
    """Bouton de réponse rapide : l'action s'exécute avant le prochain affichage."""
    def rappel():
        try:
            action(*args)
        except ErreurLLM:
            dire(tr("Apertus ne répond pas pour le moment. Réessayez dans un instant.", L()))
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
        l = L()
        bouton(tr("Comparer toutes les franchises", l), repondre_bouton, tr("Toutes les franchises", l), "deductible",
               "all", cle="franchises_all")
        bouton(tr("Laquelle est la plus avantageuse pour moi ?", l), traiter_message,
               tr("Quelle franchise est la plus avantageuse pour moi ?", l), cle="franchise_conseil")
    elif s.attente == "include_accident":
        l = L()
        bouton(tr("Accidents inclus", l), repondre_bouton, tr("Comparer avec accidents inclus", l), "include_accident",
               True, cle="accident_yes")
        bouton(tr("Accidents exclus (couverture vérifiée)", l), repondre_bouton,
               tr("Comparer avec accidents exclus, couverture vérifiée", l), "include_accident", False, cle="accident_no")
    elif s.attente == "care_access":
        l = L()
        bouton(tr("Libre choix uniquement", l), repondre_bouton, tr("Libre choix uniquement", l), "care_access",
               ["unrestricted"], cle="care_base")
        bouton(tr("J'accepte tous les modèles", l), repondre_bouton, tr("J'accepte tous les modèles", l), "care_access",
               list(CARE_TYPES), cle="care_all")
    elif s.attente == "caisse":
        bouton(tr("Passer", L()), passer_caisse, cle="caisse_passer")
    elif s.attente == "caisse_choix" and s.get("choix_caisses"):
        colonnes = st.columns(min(len(s.choix_caisses), 3))
        for i, n in enumerate(s.choix_caisses):
            with colonnes[i % len(colonnes)]:
                bouton(changement.CAISSES[n], choisir_caisse, n, cle=f"caisse_{n}")
    elif s.attente == "lettre":
        l = L()
        bouton(tr("Oui, rédigez ma lettre", l), repondre_lettre, True, cle="lettre_oui")
        bouton(tr("Non merci", l), repondre_lettre, False, cle="lettre_non")
    elif s.attente == "confirmation":
        l = L()
        if MODULES_COMPLEMENTAIRES:
            st.multiselect(tr("Besoins en assurances complémentaires", l), options=list(compl.CATEGORIES),
                           default=p["besoins"], format_func=compl.CATEGORIES.get, key="choix_besoins",
                           placeholder=tr("Choisissez…", l))
        bouton(tr("C'est correct, lancer la comparaison", l), confirmer, cle="confirmer")
        st.caption(tr("Sinon, écrivez votre correction dans le chat (ex. « j'ai 31 ans »).", l))


# --------------------------------------------------------------------------------------
# Écran de profil : les faits de base sont saisis dans des champs (lus sans erreur par Python),
# puis le conseiller (chat) part d'un profil déjà juste et aide à choisir la franchise
# --------------------------------------------------------------------------------------
SITUATIONS = {
    "salarie_8h": "Salarié(e), au moins 8 h par semaine chez un même employeur",
    "salarie_moins": "Salarié(e), moins de 8 h par semaine chez un même employeur",
    "independant": "Indépendant(e)",
    "sans_emploi": "Sans emploi, étudiant(e) ou retraité(e)",
    "ne_sait_pas": "Je ne sais pas",
}
# Après le formulaire, Apertus ouvre la conversation en reprenant le formulaire (PROMPT_OUVERTURE) ;
# ce texte fixe n'est que le secours si sa réponse ne passe pas les contrôles.
PRECISION_FORMULAIRE = ("Merci d'avoir rempli le formulaire ! 👋 Je suis votre conseiller LAMal, propulsé par Apertus, "
                        "le modèle de langue suisse. Une précision avant de calculer vos offres :")
APRES_FORMULAIRE = ("Merci d'avoir rempli le formulaire ! 👋 Je suis votre conseiller LAMal, propulsé par Apertus, le "
                    "modèle de langue suisse. Je compare les primes officielles, je réponds à vos questions à partir "
                    "de la loi, et je peux rédiger votre lettre de résiliation. Voici vos offres, avec toutes les "
                    "franchises comparées. Posez-moi vos questions, par exemple « quelle franchise est la plus "
                    "avantageuse pour moi ? » ou « c'est quoi le modèle médecin de famille ? ».")


def enregistrer_situation(c, situation):
    """Couverture accident : un employeur assure ses salariés travaillant au moins 8 h par semaine."""
    if situation == "salarie_8h":
        c.set("employed", True)
        c.set("nonoccupational_covered", True)
    elif situation == "salarie_moins":
        c.set("employed", True)
        c.set("nonoccupational_covered", False)
    elif situation in ("independant", "sans_emploi"):
        c.set("employed", False)
        c.set("nonoccupational_covered", False)
    # « Je ne sais pas » (ou rien) : rien n'est déduit, le conseiller posera la question dans le chat


def valider_formulaire(annee, npa, commune, situation, modeles, besoins):
    """Enregistre les champs dans le contrat de profil, puis calcule les offres directement."""
    s = st.session_state
    p = s.profil
    c = p["contract"]
    c.set("birth_year", int(annee))
    c.set("postal_code", int(npa))
    c.set("municipality", commune)
    enregistrer_situation(c, situation)
    c.set("care_access", list(modeles))
    c.set("deductible", "all")  # le conseiller aide à choisir la franchise dans le chat
    p["besoins"] = list(besoins)
    synchroniser_profil()
    s.formulaire_valide = s.profil_formulaire = True
    s.messages = []
    avancer()  # résout le lieu, puis calcule les offres ; s'il manque quelque chose, le chat le demande
    if not s.resultats:  # « Je ne sais pas » (accidents) ou commune à préciser : une question d'abord
        s.messages.insert(0, {"role": "assistant", "type": "texte", "contenu": tr(PRECISION_FORMULAIRE, L())})


def passer_au_chat():
    """« Je préfère décrire ma situation dans le chat » : ce qui est déjà rempli dans le formulaire est
    gardé (le conseiller ne le redemande pas), puis le chat pose directement la question suivante."""
    s = st.session_state
    sauver_formulaire()
    s.formulaire_valide = True
    c = s.profil["contract"]
    l = L()
    notes = []
    if s.get("f_naissance"):
        c.set("birth_year", int(s.f_naissance))
        notes.append(tr("né(e) en {annee}", l, annee=int(s.f_naissance)))
    npa = npa_saisi()
    commune = commune_choisie(npa)
    if commune:
        c.set("postal_code", npa)
        c.set("municipality", commune)
        notes.append(f"{commune} ({npa})")
    situation = s.get("f_situation")
    if situation and situation != "ne_sait_pas":
        enregistrer_situation(c, situation)
        notes.append(tr(SITUATIONS[situation], l).lower())
    modeles = s.get("f_modeles")
    if modeles and set(modeles) != set(CARE_TYPES):  # seulement si la personne a changé la liste
        c.set("care_access", list(modeles))
    if not notes:
        return  # rien de rempli : accueil habituel du chat
    synchroniser_profil()
    s.messages = [{"role": "assistant", "type": "texte",
                   "contenu": tr("J'ai bien noté : {faits}.", l, faits=", ".join(notes))}]
    avancer()  # pose la question suivante (ou propose le résumé si tout est connu)


def commune_choisie(npa):
    """Commune du formulaire : la seule commune du NPA, ou celle choisie dans la liste."""
    communes = communes_du_npa(npa) if npa is not None else None
    if communes is None or communes.empty:
        return None
    if len(communes) == 1:
        return communes.iloc[0]["commune"]
    return st.session_state.get("f_commune")


def npa_saisi():
    texte = str(st.session_state.get("f_npa") or "").strip()
    return int(texte) if texte.isdigit() and len(texte) == 4 else None


CLES_FORMULAIRE = ("f_naissance", "f_npa", "f_commune", "f_situation", "f_modeles", "f_besoins", "f_hors_lamal")


def sauver_formulaire():
    """Copie des réponses du formulaire : Streamlit efface l'état d'un champ qui n'est plus affiché, et on
    veut les retrouver en revenant au formulaire."""
    s = st.session_state
    s.formulaire_sauve = {k: s[k] for k in CLES_FORMULAIRE if k in s}


def revenir_au_formulaire():
    """« ← Modifier mes réponses » : retour au formulaire, déjà rempli avec les réponses précédentes. La
    conversation et les offres sont recalculées au prochain envoi (comme « Nouvelle comparaison »)."""
    s = st.session_state
    sauve, langue = dict(s.get("formulaire_sauve") or {}), s.get("langue")
    recommencer()
    for cle, valeur in sauve.items():
        st.session_state[cle] = valeur
    if langue:
        st.session_state.langue = langue


def garder_formulaire():
    """Changement de langue : les choix traduits du formulaire (situation, modèles) sont remis tels quels.
    Sans cela, Streamlit les compare à leurs libellés dans la nouvelle langue et les perd."""
    s = st.session_state
    for cle in CLES_FORMULAIRE:
        if cle in s:
            s[cle] = s[cle]


def soumettre_formulaire():
    """Rappel du bouton « Voir mes offres » : s'exécute avant l'affichage suivant."""
    s = st.session_state
    sauver_formulaire()
    s.hors_lamal = list(s.get("f_hors_lamal") or [])  # gardé après le formulaire (le champ, lui, disparaît)
    npa = npa_saisi()
    try:
        valider_formulaire(s["f_naissance"], npa, commune_choisie(npa), s["f_situation"],
                           s["f_modeles"], s.get("f_besoins", []))
    except ErreurLLM:
        dire(tr("Apertus ne répond pas pour le moment. Réessayez dans un instant.", L()))


def ecran_profil():
    """Formulaire de départ : année de naissance, NPA et commune, situation professionnelle,
    modèles acceptés et besoins facultatifs."""
    l = L()
    st.subheader(tr("Votre profil", l))
    st.caption(tr("Ces informations servent uniquement à calculer vos primes. Elles ne sont pas enregistrées.", l))
    annee = st.number_input(tr("Année de naissance", l) + " :red[*]", min_value=1920, max_value=2027, value=None, step=1,
                            placeholder="1994", key="f_naissance")
    npa_texte = st.text_input(tr("Code postal (NPA)", l) + " :red[*]", max_chars=4, placeholder="1260", key="f_npa").strip()
    npa = npa_saisi()
    if npa_texte and npa is None:
        st.caption(tr("Le code postal suisse a 4 chiffres.", l))
    elif npa is not None:
        communes = communes_du_npa(npa)
        if communes.empty:
            st.error(tr("Code postal inconnu en Suisse.", l))
        elif len(communes) == 1:
            st.caption(f"{communes.iloc[0]['commune']} ({communes.iloc[0]['canton']})")
        else:
            st.selectbox(tr("Commune de domicile", l), list(communes["commune"]), key="f_commune")
    commune = commune_choisie(npa)
    situation = st.radio(tr("Situation professionnelle", l) + " :red[*]", list(SITUATIONS), index=None,
                         format_func=lambda k: tr(SITUATIONS[k], l), key="f_situation")
    st.caption(tr("Elle indique si la couverture accident doit être incluse : un employeur assure contre les "
                  "accidents ses salariés qui travaillent au moins 8 h par semaine chez lui.", l))
    # Tous les modèles au premier affichage ; ensuite la valeur gardée (changement de langue, retour)
    modeles = st.multiselect(tr("Modèles d'assurance acceptés", l), list(CARE_TYPES),
                             default=None if "f_modeles" in st.session_state else list(CARE_TYPES),
                             format_func=lambda k: tr(CARE_LABELS[k], l), key="f_modeles", placeholder=tr("Choisissez…", l))
    st.multiselect(tr("Ce qui compte aussi pour moi (facultatif)", l), list(hors_lamal.BESOINS),
                   default=None if "f_hors_lamal" in st.session_state else [],
                   format_func=lambda k: hors_lamal.libelle(k, l), key="f_hors_lamal",
                   placeholder=tr("Lunettes, dentiste, médecines complémentaires…", l))
    st.caption(tr("Après votre choix, je vous montrerai ce que l'assurance de base ne paie pas pour ces besoins.", l))
    if MODULES_COMPLEMENTAIRES:
        st.multiselect(tr("Besoins en assurances complémentaires (facultatif)", l), list(compl.CATEGORIES),
                       format_func=compl.CATEGORIES.get, key="f_besoins", placeholder=tr("Choisissez…", l))
    manquants = [nom for nom, ok in ((tr("année de naissance", l), annee is not None),
                                     (tr("code postal", l), commune is not None),
                                     (tr("situation professionnelle", l), situation is not None),
                                     (tr("au moins un modèle", l), bool(modeles))) if not ok]
    st.button(tr("Voir mes offres", l), type="primary", disabled=bool(manquants), key="f_valider",
              on_click=soumettre_formulaire)
    if manquants:
        st.caption(tr("À compléter : {champs}", l, champs=", ".join(manquants)))
    st.button(tr("Je préfère décrire ma situation dans le chat", l), on_click=passer_au_chat, key="f_chat")


def recommencer():
    for cle in list(st.session_state.keys()):
        del st.session_state[cle]


def main():
    st.set_page_config(page_title="Health Insurance Apertus", page_icon="🩺", layout="centered")
    style.appliquer()
    config()  # arrête l'app avec un message clair si une variable LLM_* manque
    s = etat()
    if s.get("langue_detectee"):  # langue détectée dans le dernier message : appliquée au menu avant son affichage
        s.langue = s.pop("langue_detectee")

    if not s.get("formulaire_valide"):  # écran de profil avant le conseiller
        afficher_entete()
        ecran_profil()
        afficher_sources()
        return

    # Texte d'exemple fixe : s'il changeait d'une étape à l'autre, Streamlit recréerait la zone de
    # saisie et le premier message écrit après le changement d'étape serait perdu.
    texte = st.chat_input(langues.PLACEHOLDER)
    if texte and texte.strip():
        s.question_en_attente = texte.strip()

    afficher_entete()
    st.button("← " + tr("Modifier mes réponses", L()), on_click=revenir_au_formulaire, key="retour_formulaire",
              type="tertiary")

    for i, m in enumerate(s.messages):
        if m["type"] == "ouverture":
            afficher_ouverture()
            continue
        with st.chat_message(m["role"]):
            if m["type"] == "accueil":
                st.markdown(tr(ACCUEIL, L()))
                if L() == "fr":
                    st.caption(AUTRES_LANGUES)
            elif m["type"] == "texte":
                st.markdown(m["contenu"])
            elif m["type"] == "profil":
                afficher_profil(m["profil"], m.get("sante", 0))
            elif m["type"] == "lettre":
                afficher_lettre(m, i)
            elif m["type"] == "affiliation":
                afficher_affiliation(m, i)
            else:
                afficher_resultats(s.resultats[m["index"]], m["index"])
    # Message écrit ou question cliquée : il s'affiche tout de suite en bas, Apertus répond juste en dessous
    # (avant, la réponse se préparait en haut de la page, sans rien montrer là où la personne regardait).
    question = s.pop("question_en_attente", None)
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            try:
                with st.spinner(tr("Apertus réfléchit…", L())):
                    traiter_message(question)
            except ErreurLLM:
                dire(tr("Apertus ne répond pas pour le moment. Réessayez dans un instant.", L()))
        st.rerun()
    reponses_rapides()
    afficher_questions()
    if s.get("choix_demande"):  # « Choisir cette offre » : la fenêtre du choix s'ouvre
        ouvrir_fenetre_choix(*s.pop("choix_demande"))

    afficher_sources()


def afficher_entete():
    with st.sidebar:
        st.selectbox(tr("Langue", L()), langues.CODES, key="langue", on_change=garder_formulaire,
                     format_func={"fr": "Français", "de": "Deutsch", "it": "Italiano", "en": "English"}.get)
        if st.session_state.get("formulaire_valide"):
            st.button("← " + tr("Modifier mes réponses", L()), on_click=revenir_au_formulaire,
                      key="retour_formulaire_barre")
        st.button(tr("Nouvelle comparaison", L()), on_click=recommencer)
    l = L()
    style.entete(tr("Assurance de base LAMal 2027", l), tr("Votre assurance maladie.", l),
                 tr("Comparée simplement.", l),
                 tr("Les primes officielles de toutes les caisses, puis un conseiller qui répond à vos questions.", l),
                 note=html.escape(tr(AVERTISSEMENT, l)) + "<br>"
                 + html.escape(tr("Les informations de santé ne sont pas enregistrées.", l)))


def afficher_sources():
    st.divider()
    caisses = ", ".join(sorted(compl.produits["assureur"].unique()))
    if not MODULES_COMPLEMENTAIRES:
        st.caption(tr("Sources : primes LAMal 2027, régions de primes et liste des assureurs admis : Office fédéral de "
                      "la santé publique (OFSP), via opendata.swiss et priminfo.admin.ch. Textes de loi : fedlex.admin.ch "
                      "(LAMal, OAMal, OPAS, LAA). Offices des subsides : liste de l'OFSP.", L()))
        return
    st.caption(tr("Sources : primes LAMal 2027, régions de primes et liste des assureurs admis : Office fédéral de "
                  "la santé publique (OFSP), via opendata.swiss et priminfo.admin.ch. Assurances complémentaires : "
                  "sites des caisses ({caisses}), vérifiés le {date}.", L(), caisses=caisses,
                  date=compl.produits["date_verification"].max()))


if __name__ == "__main__":
    main()
