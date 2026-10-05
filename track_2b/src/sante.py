"""Situation de santé : Apertus classe, Python répond avec des textes fixes et des calculs.

Apertus (8B) ne rédige rien sur la santé : il classe seulement ce que la personne dit
(problème actuel ou inquiétude pour l'avenir) et le relie à une catégorie de complémentaire.
Tous les textes affichés sont fixes ou calculés par Python : aucun diagnostic, aucun
commentaire sur la maladie, aucun conseil médical. Rien n'est écrit sur disque.
"""
import re

import complementaires as compl
from chatbot import FRANCHISES, extraire_json
from comparateur import classe_age, toutes_les_offres

PROMPT_SANTE = """Tu analyses ce qu'une personne dit de sa santé, uniquement pour l'orienter dans ses assurances maladie en Suisse.
Tu ne fais aucun diagnostic et aucun commentaire.
Réponds UNIQUEMENT avec un objet JSON {"elements": [...]}, sans texte autour. Chaque élément :
- "type" : "existant" pour une maladie, un problème ou un traitement actuel (même passager, ex. une douleur en ce moment) ;
  "avenir" pour une inquiétude ou un projet futur (opération possible, grossesse, sport à risque, soins à venir).
- "categorie" : "lunettes", "dentaire", "medecines_alternatives" ou "hospitalisation" si l'élément
  concerne clairement l'une de ces assurances complémentaires (une grossesse ou une opération
  concerne "hospitalisation"), sinon null.
Liste vide si la personne ne parle pas de sa santé."""

# Garde-fou 1 : on ne demande le classement que si la phrase parle de santé
MOTIF_SANTE = re.compile(
    r"malad|traitement|chroniq|m[ée]dic|m[ée]decin|sp[ée]cialiste|pneumo|cardio|dermato|psy|"
    r"asthm|diab[èe]t|allerg|cancer|douleur|\bmal\s+(?:aux?|à)\b|op[ée]r|chirurg|h[ôo]pita|"
    r"hospitalis|enfant|b[ée]b[ée]|grossesse|enceinte|accouch|sport|\bski|moto|\bdents?\b|"
    r"dentiste|lunette|\bvue\b|sant[ée]|peur|inqui[èe]t", re.IGNORECASE)
# Garde-fou 2 : une catégorie n'est gardée que si un mot lié figure dans la phrase
MOTS_CATEGORIE = {
    "lunettes": compl.MOTS_BESOINS["lunettes"] + r"|\byeux\b|\b[œo]il\b",
    "dentaire": compl.MOTS_BESOINS["dentaire"],
    "medecines_alternatives": compl.MOTS_BESOINS["medecines_alternatives"],
    "hospitalisation": compl.MOTS_BESOINS["hospitalisation"]
                       + r"|op[ée]r|chirurg|enfant|b[ée]b[ée]|grossesse|enceinte|accouch|maternit",
}
# Thèmes qui excluent certains produits (ex. « maternité exclue » pour une grossesse)
EXCLUSIONS_THEME = {
    "grossesse": (r"enfant|b[ée]b[ée]|grossesse|enceinte|accouch|maternit", r"maternit"),
}

TEXTE_LAMAL_MALADIE = (
    "L'assurance de base (LAMal) prend en charge les traitements médicaux reconnus de la plupart "
    "des maladies, quelle que soit votre caisse, avec votre franchise et votre quote-part. En assurance de "
    "base, la caisse ne peut ni vous refuser, ni vous demander une surprime à cause de votre santé.")
AVERTISSEMENT_EXISTANT = (
    "Attention : si vous souscrivez maintenant une nouvelle assurance complémentaire, la caisse "
    "examinera votre questionnaire de santé et exclura probablement ce problème de la couverture, "
    "ou refusera votre demande.")
TEXTE_AVENIR = (
    "Une assurance complémentaire se souscrit avant que le besoin n'apparaisse : un "
    "questionnaire de santé est demandé, et des délais de carence peuvent s'appliquer.")
SANS_CATEGORIE = ("Nos données d'assurances complémentaires ne couvrent pas ce type de besoin : "
                  "renseignez-vous directement auprès des caisses.")
CARENCE_INCONNUE = "délai de carence non indiqué dans nos données : à demander à la caisse"
MOTIF_CARENCE = re.compile(r"carence|d[ée]lai", re.IGNORECASE)
# Pour ces catégories, la LAMal ne rembourse en général pas les frais : comparer les
# franchises n'aurait pas de sens (voir les textes LAMAL_COUVRE)
SANS_COMPARAISON_FRANCHISE = {"dentaire", "lunettes"}


def classer(texte, appeler_llm):
    """Éléments de santé de la phrase : [{"type", "categorie", "theme"}] (vide si aucun).
    appeler_llm(systeme, message) renvoie la réponse brute du modèle (8B)."""
    if not MOTIF_SANTE.search(texte or ""):
        return []
    brut = extraire_json(appeler_llm(PROMPT_SANTE, texte)).get("elements")
    elements = []
    for e in brut if isinstance(brut, list) else []:
        if not isinstance(e, dict) or e.get("type") not in ("existant", "avenir"):
            continue
        categorie = e.get("categorie")
        if categorie not in MOTS_CATEGORIE or not re.search(MOTS_CATEGORIE[categorie], texte, re.IGNORECASE):
            categorie = None
        theme = next((t for t, (motif, _) in EXCLUSIONS_THEME.items()
                      if re.search(motif, texte, re.IGNORECASE)), None)
        element = {"type": e["type"], "categorie": categorie, "theme": theme}
        if element not in elements:
            elements.append(element)
    return elements


def exception_sanitas():
    """Ligne du CSV sur l'admission avec surprime individuelle (Sanitas), si elle existe."""
    lignes = compl.produits[(compl.produits["categorie"] == "toutes")
                            & compl.produits["produit"].str.contains("surprime", case=False)]
    return lignes.iloc[0] if not lignes.empty else None


def comparer_franchises(profil, produit_reference=None):
    """Coût annuel avec la franchise la plus basse et la plus haute, pour le même produit
    (celui de la première proposition) : primes seules, et coût maximal
    (prime + franchise + quote-part maximale) si les frais médicaux sont élevés."""
    franchises = FRANCHISES[classe_age(profil["age"])]
    lignes = []
    for franchise in (min(franchises), max(franchises)):
        offres = toutes_les_offres(profil["canton"], profil["region"], profil["age"], franchise,
                                   avec_accident=not profil["travaille_8h"])
        if offres.empty:
            return []
        meme = offres[(offres["Assureur"] == produit_reference[0])
                      & (offres["Produit"] == produit_reference[1])] if produit_reference else offres.iloc[0:0]
        o = (meme if not meme.empty else offres).iloc[0]
        lignes.append({"franchise": franchise, "assureur": o["Assureur"], "produit": o["Produit"],
                       "prime_an": o["Prime/an"], "cout_max": o["Coût max/an"]})
    return lignes


def delais_carence(p):
    morceaux = [f for f in compl.fragments(p) if MOTIF_CARENCE.search(f)]
    return "; ".join(morceaux) if morceaux else CARENCE_INCONNUE


def produits_avenir(categorie, theme, age):
    """Les 3 produits les plus adaptés pour un besoin futur : couverture la plus élevée,
    sans les produits qui excluent ce thème (ex. maternité exclue pour une grossesse)."""
    choix = compl.produits_pour([categorie])
    if theme in EXCLUSIONS_THEME:
        exclusion = EXCLUSIONS_THEME[theme][1]
        exclus = {(p["assureur"], p["produit"]) for _, p in choix.iterrows()
                  if re.search(exclusion, str(p["conditions"]), re.IGNORECASE)
                  and re.search(r"exclu", str(p["conditions"]), re.IGNORECASE)}
        choix = choix[[(a, pr) not in exclus for a, pr in zip(choix["assureur"], choix["produit"])]]
    meilleurs, _ = compl.meilleurs_produits(choix, categorie, age)
    return [(p, delais_carence(p)) for p in meilleurs]


def analyser(profil, elements, produit_reference=None):
    """Tout ce qu'il faut afficher pour la santé, calculé par Python (aucun texte du LLM)."""
    existants = [e for e in elements if e["type"] == "existant"]
    avenir = [e for e in elements if e["type"] == "avenir"]
    resultat = {"existant": None, "avenir": []}
    if existants:
        categories = [e["categorie"] for e in existants if e["categorie"]]
        comparer = not categories or any(c not in SANS_COMPARAISON_FRANCHISE for c in categories)
        resultat["existant"] = {
            "categories": categories,
            "franchises": comparer_franchises(profil, produit_reference) if comparer else [],
            "exception": exception_sanitas(),
        }
    for e in avenir:
        resultat["avenir"].append({
            "categorie": e["categorie"], "theme": e["theme"],
            "produits": produits_avenir(e["categorie"], e["theme"], profil["age"]) if e["categorie"] else []})
    return resultat
