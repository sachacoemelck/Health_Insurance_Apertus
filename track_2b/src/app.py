"""Interface web du comparateur LAMal (Streamlit), en français.

Lancer depuis le dossier track_2b :   streamlit run src/app.py

Configuration : uniquement les variables LLM_NAME, LLM_BASE_URL, LLM_API_KEY
(et LLM_NAME_RESTITUTION, facultative), lues par lire_config().
Aucune donnée personnelle n'est écrite sur disque : la conversation vit seulement
dans la mémoire de la session du navigateur (st.session_state).

Le parcours réutilise le code existant :
- extraction (PROMPT_EXTRACTION, Apertus 8B) et contrôles Python (nettoyer_profil, localiser) ;
- calcul des primes (comparer) et explication vérifiée (expliquer, Apertus 70B) ;
- module complémentaires (faits agrégés, résumé vérifié, produits à vérifier).
"""
import re

import streamlit as st
from openai import OpenAI

import chatbot
import complementaires as compl
from chatbot import (FRANCHISES, PROMPT_EXTRACTION, en_langue, extraire_json, lire_config,
                     localiser, montants_intrus, nettoyer_profil, nom_simple, regles_age,
                     resumer_faits)
from comparateur import QUOTE_PART_MAX, classe_age, comparer

# Langue des explications d'Apertus (paramètre conservé pour ajouter d'autres langues plus tard)
LANGUE = "français"

AVERTISSEMENT = ("Outil d'orientation, pas un conseil personnalisé ; vérifie sur "
                 "priminfo.admin.ch avant de décider.")
QUESTIONS_DE_SECOURS = {
    "lieu": "Quel est ton code postal (NPA) ou ta commune de domicile ?",
    "commune": "Plusieurs communes correspondent. Laquelle est ta commune de domicile ?",
    "age": "Quel âge a la personne à assurer ?",
    "franchise": "Quelle franchise annuelle veux-tu ? Si tu hésites, dis-moi si tu vas souvent "
                 "ou rarement chez le médecin.",
    "travaille_8h": "Travailles-tu au moins 8 heures par semaine chez le même employeur ?",
}
COMPROMIS_DE_SECOURS = ("Plus la franchise est élevée, plus la prime est basse, mais tu paies "
                        "toi-même tes frais jusqu'au montant de la franchise. Choisis une "
                        "franchise ci-dessous.")
RAPPEL_LAMAL = ("Primes officielles OFSP 2027. Vérifie sur priminfo.admin.ch avant de changer "
                "d'assurance.")

# --------------------------------------------------------------------------------------
# Prompts propres à l'interface (questions, franchise floue)
# --------------------------------------------------------------------------------------
PROMPT_QUESTION = """Tu aides une personne vivant en Suisse à comparer son assurance maladie de base.
Il manque une information. Pose UNE seule question courte et naturelle pour l'obtenir.
Règles : écris en {langue} ; tutoie ; réponds uniquement par la question, sans salutation
ni explication ; ne cite aucun nombre qui n'apparaît pas dans le message."""

DESCRIPTIONS = {
    "lieu": "le code postal (NPA) ou la commune de domicile en Suisse",
    "commune": "laquelle de ces communes est sa commune de domicile : {liste}",
    "age": "l'âge de la personne à assurer",
    "age_plusieurs": "la personne a parlé de plusieurs personnes : demande pour quelle personne "
                     "faire la comparaison (une seule à la fois) et son âge",
    "franchise": "la franchise annuelle souhaitée, parmi {valeurs} CHF ; ajoute que si elle "
                 "hésite, elle peut dire si elle va souvent ou rarement chez le médecin",
    "travaille_8h": "si la personne travaille au moins 8 heures par semaine chez le même "
                    "employeur (dans ce cas, l'employeur l'assure contre les accidents)",
}

PROMPT_FREQUENCE = """La personne répond à une question sur la franchise de son assurance maladie.
Réponds UNIQUEMENT avec un objet JSON {"frais_medicaux": ...}, sans texte autour :
"rares" si elle dit aller rarement chez le médecin ou être en bonne santé ;
"frequents" si elle dit avoir souvent des frais médicaux, un traitement ou une maladie chronique ;
null sinon."""

PROMPT_COMPROMIS = """Tu aides une personne à choisir la franchise de son assurance maladie de base (LAMal).
Règles strictes : utilise UNIQUEMENT les faits fournis ; ne fais aucun calcul ; ne cite aucun
nombre absent des faits ; ne choisis pas à sa place ; tutoie ; écris en {langue} ;
2 à 3 phrases ; termine en l'invitant à choisir une franchise parmi les boutons affichés."""


class ErreurLLM(Exception):
    pass


# --------------------------------------------------------------------------------------
# Configuration et appels au LLM (configuration lue uniquement dans les variables LLM_*)
# --------------------------------------------------------------------------------------
@st.cache_resource
def client_llm(base_url, api_key):
    return OpenAI(base_url=base_url, api_key=api_key)


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


# --------------------------------------------------------------------------------------
# État de la session (en mémoire seulement)
# --------------------------------------------------------------------------------------
def profil_vide():
    return {"npa": None, "commune_citee": None, "commune": None, "canton": None,
            "region": None, "age": None, "franchise": None, "travaille_8h": None,
            "plusieurs_personnes": False, "besoins": []}


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
    return s


def dire(texte):
    st.session_state.messages.append({"role": "assistant", "type": "texte", "contenu": texte})


# --------------------------------------------------------------------------------------
# Compréhension des messages : extraction 8B + contrôles Python existants
# --------------------------------------------------------------------------------------
def integrer(texte, champ=None):
    """Ajoute au profil ce que l'utilisateur vient de dire. Renvoie True si le profil a changé."""
    s, cfg = st.session_state, config()
    message = f"Question posée : {s.question}\nRéponse : {texte}" if champ else texte
    brut = extraire_json(llm(cfg["LLM_NAME"], PROMPT_EXTRACTION, message))
    # Réponse à la question franchise : « la plus haute » doit être lue comme une franchise
    phrase = f"franchise {texte}" if champ == "franchise" else texte
    n = nettoyer_profil(brut, phrase)
    p, change = s.profil, False

    if n["npa"] is not None or n["commune"]:
        p.update(npa=n["npa"], commune_citee=n["commune"], commune=None, canton=None, region=None)
        s.choix_communes, change = None, True
    if n["plusieurs_personnes"]:
        p.update(plusieurs_personnes=True, age=None)
        change = True
    for cle in ("age", "franchise", "travaille_8h"):
        if n[cle] is not None and n[cle] != p[cle]:
            p[cle], change = n[cle], True
    if p["age"] is not None:
        p["plusieurs_personnes"] = False
        regles_age(p, phrase)  # franchise en mots, pas d'emploi avant 15 ans
        if p["franchise"] not in FRANCHISES[classe_age(p["age"])]:
            p["franchise"] = None

    if champ is None:  # besoins en complémentaires : seulement dans les messages libres
        besoins = compl.filtrer_categories(
            extraire_json(llm(cfg["LLM_NAME"], compl.PROMPT_BESOINS, texte)).get("categories"), texte)
        nouveaux = [b for b in besoins if b not in p["besoins"]]
        if nouveaux:
            p["besoins"] += nouveaux
            s.textes_besoins.append(texte)
            change = True
    return change


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
        p["npa"] = p["commune_citee"] = None
        s.lieu_inconnu = True
    else:
        s.choix_communes = lieu[["commune", "canton", "region"]].to_dict("records")


def champ_manquant():
    s = st.session_state
    p = s.profil
    if s.choix_communes:
        return "commune"
    if not p["canton"]:
        return "lieu"
    if p["age"] is None:
        return "age"
    if p["franchise"] is None:
        return "franchise"
    if p["travaille_8h"] is None:
        return "travaille_8h"
    return None


def libelle_commune(c):
    return c["commune"] if c["commune"].endswith(f"({c['canton']})") else f"{c['commune']} ({c['canton']})"


def poser_question(champ):
    """Apertus formule UNE question ; Python vérifie qu'elle n'invente aucun nombre."""
    s, cfg = st.session_state, config()
    p = s.profil
    if champ == "commune":
        description = DESCRIPTIONS["commune"].format(
            liste=", ".join(libelle_commune(c) for c in s.choix_communes))
    elif champ == "age" and p["plusieurs_personnes"]:
        description = DESCRIPTIONS["age_plusieurs"]
    elif champ == "franchise":
        description = DESCRIPTIONS["franchise"].format(
            valeurs=", ".join(map(str, FRANCHISES[classe_age(p["age"])])))
    else:
        description = DESCRIPTIONS[champ]
    question = llm(cfg["LLM_NAME_RESTITUTION"], en_langue(PROMPT_QUESTION, LANGUE),
                   f"Information à obtenir : {description}").strip()
    if "?" not in question or montants_intrus(question, description) or len(question) > 300:
        question = QUESTIONS_DE_SECOURS[champ]
    if s.lieu_inconnu and champ == "lieu":
        question = f"Je n'ai pas trouvé ce lieu en Suisse. {question}"
        s.lieu_inconnu = False
    s.question, s.attente = question, champ
    dire(question)


def expliquer_compromis(frais):
    """Réponse floue sur la franchise : Python fournit les faits, Apertus les explique."""
    s, cfg = st.session_state, config()
    classe = classe_age(s.profil["age"])
    faits = (f"Frais médicaux annoncés : {'rares' if frais == 'rares' else 'fréquents'}.\n"
             f"Franchises possibles : {', '.join(map(str, FRANCHISES[classe]))} CHF par an.\n"
             f"Quote-part : 10 % des frais après la franchise, au maximum "
             f"{QUOTE_PART_MAX[classe]} CHF par an.\n"
             "Plus la franchise est élevée, plus la prime est basse, mais la personne paie "
             "elle-même ses frais médicaux jusqu'au montant de la franchise.\n"
             "Avec peu de frais médicaux, une franchise élevée revient souvent moins cher au total. "
             "Avec des frais réguliers, une franchise basse limite ce que la personne paie elle-même.")
    texte = llm(cfg["LLM_NAME_RESTITUTION"], en_langue(PROMPT_COMPROMIS, LANGUE), faits)
    dire(texte if texte and not montants_intrus(texte, faits) else COMPROMIS_DE_SECOURS)


def avancer():
    """Demande le prochain champ manquant, sinon confirmation (ou nouveau calcul en suivi)."""
    s = st.session_state
    resoudre_lieu()
    champ = champ_manquant()
    if champ:
        s.etape = "collecte"
        poser_question(champ)
    elif s.resultats:
        dire("Profil mis à jour, voici le nouveau calcul.")
        calculer()
    else:
        s.etape, s.attente = "confirmation", "confirmation"
        s.messages.append({"role": "assistant", "type": "profil", "profil": dict(s.profil)})


def choisir_commune(c):
    p = st.session_state.profil
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
    if s.attente == "commune" and choisir_commune_texte(texte):
        avancer()
    elif s.attente == "franchise":
        integrer(texte, champ="franchise")
        if s.profil["franchise"] is None:
            frais = extraire_json(llm(config()["LLM_NAME"], PROMPT_FREQUENCE, texte)).get("frais_medicaux")
            if frais in ("rares", "frequents"):
                expliquer_compromis(frais)
                return
        avancer()
    elif s.etape == "resultats":
        if integrer(texte):
            avancer()
        else:
            dire("Je n'ai pas compris ce qu'il faut changer. Exemple : « et avec une franchise "
                 "de 300 ? » ou « j'habite à 1003 ».")
    else:
        integrer(texte, champ=s.attente if s.attente not in (None, "confirmation") else None)
        avancer()


# --------------------------------------------------------------------------------------
# Calcul : comparateur + explications vérifiées (code existant)
# --------------------------------------------------------------------------------------
def calculer():
    s, cfg = st.session_state, config()
    p = s.profil
    lamal = comparer(p["canton"], p["region"], p["age"], p["franchise"],
                     avec_accident=not p["travaille_8h"])
    bloc = {"lamal": lamal, "explication": None, "compl": None}
    if not lamal.empty:
        faits = resumer_faits(p, lamal)
        bloc["explication"] = chatbot.expliquer(client(), cfg["LLM_NAME_RESTITUTION"], faits, LANGUE)
    if p["besoins"]:
        choix = compl.produits_pour(p["besoins"])
        faits_c = compl.faits_pour(" ".join(s.textes_besoins), p["besoins"], choix)
        bloc["compl"] = {
            "categories": list(p["besoins"]), "choix": choix,
            "resume": compl.expliquer(client(), cfg["LLM_NAME_RESTITUTION"], faits_c, choix,
                                      p["besoins"], LANGUE),
            "a_verifier": compl.produits_a_verifier(choix)}
    s.resultats.append(bloc)
    s.messages.append({"role": "assistant", "type": "resultats", "index": len(s.resultats) - 1})
    s.etape, s.attente = "resultats", None


# --------------------------------------------------------------------------------------
# Affichage
# --------------------------------------------------------------------------------------
def afficher_profil(p):
    accident = "exclue (assurée par l'employeur)" if p["travaille_8h"] else "incluse"
    besoins = ", ".join(compl.CATEGORIES[b] for b in p["besoins"]) or "aucun"
    commune = p["commune"] + (f" ({p['npa']})" if p["npa"] else "")
    st.markdown("**Voici ce que j'ai compris. Est-ce correct ?**")
    st.markdown("\n".join([
        f"- **Âge** : {p['age']} ans",
        f"- **Commune** : {commune}",
        f"- **Canton** : {p['canton']}",
        f"- **Région de primes** : {p['region']}",
        f"- **Franchise** : {p['franchise']} CHF",
        f"- **Couverture accident** : {accident}",
        f"- **Besoins en complémentaires** : {besoins}",
    ]))


def afficher_resultats(bloc):
    lamal = bloc["lamal"]
    st.markdown("**Les offres LAMal les moins chères (CHF)**")
    if lamal.empty:
        st.write("Aucune prime trouvée pour ce profil.")
    else:
        montants = lamal.select_dtypes("number").columns
        st.dataframe(lamal.style.format({c: "{:.2f}" for c in montants}),
                     hide_index=True, use_container_width=True)
        st.markdown("**Explication d'Apertus**")
        st.write(bloc["explication"])
        st.caption(RAPPEL_LAMAL)

    c = bloc["compl"]
    if c:
        st.markdown("### Assurances complémentaires")
        choix = c["choix"]
        for categorie in c["categories"] + ["toutes"]:
            lignes = choix[choix["categorie"] == categorie]
            if lignes.empty:
                continue
            with st.expander(compl.CATEGORIES.get(categorie, "Toutes catégories")):
                if compl.LAMAL_COUVRE.get(categorie, "A_REMPLIR") != "A_REMPLIR":
                    st.info(f"**Ce que couvre déjà la LAMal** : {compl.LAMAL_COUVRE[categorie]}")
                for assureur, offres in lignes.groupby("assureur", sort=False):
                    st.markdown(f"**{assureur}**")
                    for _, prod in offres.iterrows():
                        texte = f"- *{prod['produit']}* — {prod['prestation']}"
                        if compl.details(prod):
                            texte += f"  \n  {compl.details(prod)}"
                        if isinstance(prod["conditions"], str):
                            texte += f"  \n  Conditions : {prod['conditions']}"
                        for alerte in compl.avertissements(prod):
                            texte += f"  \n  ⚠ {alerte}"
                        st.markdown(texte)
        st.markdown("**Résumé d'Apertus**")
        st.write(c["resume"])
        if c["a_verifier"]:
            st.markdown("**Produits à vérifier avant de te décider**")
            st.markdown("\n".join(f"- ⚠ {assureur} {produit} : {'; '.join(alertes)}"
                                  for (assureur, produit), alertes in c["a_verifier"].items()))
        st.warning(compl.RAPPEL.format(date=compl.produits["date_verification"].max()))
    st.caption("Tu peux poser une question de suivi, par exemple « et avec une franchise de 300 ? ».")


def bouton(libelle, action, *args, cle):
    """Bouton de réponse rapide : l'action s'exécute avant le prochain affichage."""
    def rappel():
        try:
            action(*args)
        except ErreurLLM:
            dire("Apertus ne répond pas pour le moment. Réessaie dans un instant.")
    st.button(libelle, key=cle, on_click=rappel)


def repondre_bouton(texte_affiche, champ, valeur):
    s = st.session_state
    s.messages.append({"role": "user", "type": "texte", "contenu": texte_affiche})
    s.profil[champ] = valeur
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
    elif s.attente == "franchise" and p["age"] is not None:
        valeurs = FRANCHISES[classe_age(p["age"])]  # seulement les franchises légales pour l'âge
        for colonne, v in zip(st.columns(len(valeurs)), valeurs):
            with colonne:
                bouton(f"{v} CHF", repondre_bouton, f"{v} CHF", "franchise", v, cle=f"franchise_{v}")
    elif s.attente == "travaille_8h":
        gauche, droite, _ = st.columns([1, 1, 4])
        with gauche:
            bouton("Oui", repondre_bouton, "Oui", "travaille_8h", True, cle="travail_oui")
        with droite:
            bouton("Non", repondre_bouton, "Non", "travaille_8h", False, cle="travail_non")
    elif s.attente == "confirmation":
        st.multiselect("Besoins en assurances complémentaires", options=list(compl.CATEGORIES),
                       default=p["besoins"], format_func=compl.CATEGORIES.get, key="choix_besoins")
        bouton("C'est correct, lancer la comparaison", confirmer, cle="confirmer")
        st.caption("Sinon, écris ta correction dans le chat (ex. « j'ai 31 ans »).")


def recommencer():
    for cle in list(st.session_state.keys()):
        del st.session_state[cle]


def main():
    st.set_page_config(page_title="Health Insurance Apertus", page_icon="🩺", layout="centered")
    config()  # arrête l'app avec un message clair si une variable LLM_* manque
    s = etat()

    texte = st.chat_input("Ex. : et avec une franchise de 300 ?" if s.etape == "resultats"
                          else "Ex. : j'ai 30 ans, j'habite à Nyon, je travaille à plein temps…")
    if texte:
        try:
            with st.spinner("Apertus réfléchit…"):
                traiter_message(texte.strip())
        except ErreurLLM:
            dire("Apertus ne répond pas pour le moment. Réessaie dans un instant.")

    st.title("Comparateur d'assurance maladie")
    st.write("Décris ta situation en quelques mots : je compare les primes officielles de "
             "l'assurance de base (LAMal) 2027 et je t'explique les différences.")
    st.warning(AVERTISSEMENT, icon="⚠️")
    with st.sidebar:
        st.button("Nouvelle comparaison", on_click=recommencer)

    for m in s.messages:
        with st.chat_message(m["role"]):
            if m["type"] == "texte":
                st.markdown(m["contenu"])
            elif m["type"] == "profil":
                afficher_profil(m["profil"])
            else:
                afficher_resultats(s.resultats[m["index"]])
    reponses_rapides()

    st.divider()
    caisses = ", ".join(sorted(compl.produits["assureur"].unique()))
    st.caption("Sources : primes LAMal 2027, régions de primes et liste des assureurs admis : "
               "Office fédéral de la santé publique (OFSP), via opendata.swiss et "
               f"priminfo.admin.ch. Assurances complémentaires : sites des caisses ({caisses}), "
               f"vérifiés le {compl.produits['date_verification'].max()}.")


main()
