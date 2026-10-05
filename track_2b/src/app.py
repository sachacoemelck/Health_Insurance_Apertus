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
import sante
from chatbot import (FRANCHISES, NOMS_PRIORITE, PROMPT_EXTRACTION, PROMPT_INTRO, PROMPT_PRIORITE,
                     en_langue, extraire_json, faits_propositions, filtrer_priorite, lire_config,
                     localiser, montants_intrus, nettoyer_profil, nom_simple, regles_age,
                     tutoie)
from comparateur import QUOTE_PART_MAX, classe_age, propositions, toutes_les_offres

# Langue des explications d'Apertus (paramètre conservé pour ajouter d'autres langues plus tard)
LANGUE = "français"

AVERTISSEMENT = ("Outil d'orientation, pas un conseil personnalisé ; vérifiez sur "
                 "priminfo.admin.ch avant de décider.")
QUESTIONS_DE_SECOURS = {
    "lieu": "Quel est votre code postal (NPA) ou votre commune de domicile ?",
    "commune": "Plusieurs communes correspondent. Laquelle est votre commune de domicile ?",
    "age": "Quel âge a la personne à assurer ?",
    "franchise": "Quelle franchise annuelle souhaitez-vous ? Si vous hésitez, dites-moi si vous allez souvent "
                 "ou rarement chez le médecin.",
    "travaille_8h": "Travaillez-vous au moins 8 heures par semaine chez le même employeur ?",
}
COMPROMIS_DE_SECOURS = ("Plus la franchise est élevée, plus la prime est basse, mais vous payez "
                        "vous-même vos frais jusqu'au montant de la franchise. Choisissez une "
                        "franchise ci-dessous.")
RAPPEL_LAMAL = ("Primes officielles OFSP 2027. Vérifiez sur priminfo.admin.ch avant de changer "
                "d'assurance.")

# --------------------------------------------------------------------------------------
# Prompts propres à l'interface (questions, franchise floue)
# --------------------------------------------------------------------------------------
PROMPT_QUESTION = """Tu aides une personne vivant en Suisse à comparer son assurance maladie de base.
Il manque une information. Pose UNE seule question courte et naturelle pour l'obtenir.
Règles : écris en {langue} ; vouvoie la personne ; réponds uniquement par la question, sans salutation
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
Tu peux lui conseiller une franchise selon les frais médicaux qu'elle annonce, en t'appuyant
uniquement sur les faits fournis.
Règles strictes : utilise UNIQUEMENT les faits fournis ; ne fais aucun calcul ; ne cite aucun
nombre absent des faits ; vouvoie la personne ; écris en {langue} ; 2 à 3 phrases ;
termine en l'invitant à choisir une franchise parmi les boutons affichés."""


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
            "plusieurs_personnes": False, "priorite": None, "besoins": []}


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
        s.sante = []             # éléments de santé classés (en mémoire seulement)
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

    if champ is None:  # besoins et priorité : seulement dans les messages libres
        besoins = compl.categories_finales(
            extraire_json(llm(cfg["LLM_NAME"], compl.PROMPT_BESOINS, texte)).get("categories"), texte)
        nouveaux = [b for b in besoins if b not in p["besoins"]]
        if nouveaux:
            p["besoins"] += nouveaux
            s.textes_besoins.append(texte)
            change = True
        priorite = filtrer_priorite(
            extraire_json(llm(cfg["LLM_NAME"], PROMPT_PRIORITE, texte)).get("priorite"), texte)
        if priorite and priorite != p["priorite"]:
            p["priorite"], change = priorite, True
        # Santé : Apertus classe seulement ; les réponses sont des textes fixes et des calculs
        for element in sante.classer(texte, lambda systeme, message: llm(cfg["LLM_NAME"], systeme, message)):
            if element not in s.sante:
                s.sante.append(element)
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
    if ("?" not in question or montants_intrus(question, description) or len(question) > 300
            or tutoie(question)):
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
    valide = texte and not montants_intrus(texte, faits) and not tutoie(texte)
    dire(texte if valide else COMPROMIS_DE_SECOURS)


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
        s.messages.append({"role": "assistant", "type": "profil", "profil": dict(s.profil),
                           "sante": len(s.sante)})


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
INTRO_DE_SECOURS = ("Voici trois propositions : la moins chère, la moins chère avec médecin de "
                    "famille, et la moins chère avec libre choix du médecin. Comparez le prix et "
                    "les contreparties ci-dessous.")


def calculer():
    """3 propositions LAMal (Python), introduction vérifiée (70B), meilleurs produits complémentaires."""
    s, cfg = st.session_state, config()
    p = s.profil
    offres = toutes_les_offres(p["canton"], p["region"], p["age"], p["franchise"],
                               avec_accident=not p["travaille_8h"])
    props = propositions(offres, p["priorite"])
    bloc = {"offres": offres, "propositions": props, "intro": None, "compl": None}
    if props:
        bloc["intro"] = chatbot.expliquer(client(), cfg["LLM_NAME_RESTITUTION"],
                                          faits_propositions(props, p["priorite"]), LANGUE,
                                          prompt=PROMPT_INTRO, secours=INTRO_DE_SECOURS)
    if s.sante:
        reference = (props[0]["assureur"], props[0]["produit"]) if props else None
        bloc["sante"] = sante.analyser(p, s.sante, reference)
    if p["besoins"]:
        choix = compl.produits_pour(p["besoins"])
        bloc["compl"] = {
            "categories": list(p["besoins"]), "choix": choix,
            "meilleurs": {c: compl.meilleurs_produits(choix, c, p["age"]) for c in p["besoins"]}}
    s.resultats.append(bloc)
    s.messages.append({"role": "assistant", "type": "resultats", "index": len(s.resultats) - 1})
    s.etape, s.attente = "resultats", None


# --------------------------------------------------------------------------------------
# Affichage
# --------------------------------------------------------------------------------------
def afficher_profil(p, nb_sante=0):
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
        f"- **Priorité** : {NOMS_PRIORITE.get(p['priorite'], 'aucune indiquée')}",
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
            st.caption(f"Contrepartie : {p['contrepartie']}")
    st.caption(RAPPEL_LAMAL)


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


def afficher_resultats(bloc):
    afficher_propositions(bloc)
    if bloc.get("sante"):
        afficher_sante(bloc["sante"])
    if bloc["compl"]:
        afficher_meilleurs_complementaires(bloc["compl"])
    afficher_toutes_les_offres(bloc)
    st.caption("Vous pouvez poser une question de suivi, par exemple « et avec une franchise de 300 ? » "
               "ou « je veux garder le libre choix du médecin ».")


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
        st.caption("Sinon, écrivez votre correction dans le chat (ex. « j'ai 31 ans »).")


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


main()
