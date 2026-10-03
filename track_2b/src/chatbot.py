"""Chatbot LAMal : Apertus comprend la situation, pandas calcule les primes.

1. L'utilisateur décrit sa situation en langage libre.
2. Apertus extrait un profil JSON (npa, commune, age, franchise, travaille_8h).
3. Python déduit canton et région du NPA (fichier OFSP), vérifie le profil
   et appelle comparer() sur les données OFSP.
4. Python résume les faits ; Apertus les explique en français, sans calculer.
   Python vérifie que chaque montant cité figure dans les faits.
"""
import json
import os
import re
import sys

from dotenv import load_dotenv
from openai import OpenAI

from comparateur import (MODELES, QUOTE_PART_MAX, classe_age, communes_du_npa,
                         comparer, regions)

load_dotenv()

FRANCHISES = {
    "AKA_01_KIN": [0, 100, 200, 300, 400, 500, 600],
    "AKA_02_JUG": [300, 500, 1000, 1500, 2000, 2500],
    "AKA_03_ERW": [300, 500, 1000, 1500, 2000, 2500],
}

PROMPT_EXTRACTION = """Tu extrais le profil d'assurance maladie (LAMal) d'une personne vivant en Suisse.
Réponds UNIQUEMENT avec un objet JSON, sans texte autour, avec ces clés :
- "npa" : code postal suisse à 4 chiffres (entier), ou null si non mentionné
- "commune" : nom de la commune de domicile si la personne le cite, sinon null
- "age" : âge en années (entier)
- "franchise" : franchise annuelle en CHF (entier), ou null si non mentionnée
- "travaille_8h" : true si la personne travaille au moins 8 heures par semaine chez le même employeur, false sinon, null si inconnu
Mets null pour toute information absente. N'invente rien."""

PROMPT_EXPLICATION = """Tu aides une personne vivant en Suisse à choisir son assurance maladie de base (LAMal).
Règles strictes :
- Utilise UNIQUEMENT les faits fournis. N'ajoute aucune information extérieure.
- Ne fais AUCUN calcul et ne cite AUCUN montant qui n'apparaît pas tel quel dans les faits.
- Ne définis aucun terme qui n'est pas défini dans les faits. Pour décrire un modèle,
  reprends uniquement sa définition fournie.
- N'attribue à un modèle aucun avantage ni inconvénient qui n'est pas dans sa définition.
- Pour le Modèle alternatif, dis SEULEMENT de vérifier les conditions exactes chez
  l'assureur. N'ajoute rien d'autre sur ce modèle : ni avantage, ni liberté, ni contrainte.
- Ne tire aucune conclusion du nom d'un modèle ou d'un produit (par exemple « flex »,
  « smart », « care ») : seule la définition fournie compte.
- Tutoie l'utilisateur. Écris en français simple.
- Écris 5 à 6 phrases au total, en un seul paragraphe, sans liste ni tableau.
Explique les compromis : le prix face aux contraintes de chaque modèle, et le risque
d'une franchise élevée (le coût maximal annuel si tu as beaucoup de frais médicaux)."""


def lire_config():
    config = {k: os.getenv(k) for k in ("LLM_NAME", "LLM_BASE_URL", "LLM_API_KEY")}
    manquantes = [k for k, v in config.items() if not v]
    if manquantes:
        sys.exit(f"Variables manquantes : {', '.join(manquantes)}. "
                 "Copie .env.example vers .env et remplis-le.")
    # Modèle facultatif pour l'explication (ex. 70B, qui suit mieux les consignes)
    config["LLM_NAME_RESTITUTION"] = os.getenv("LLM_NAME_RESTITUTION") or config["LLM_NAME"]
    return config


def demander_llm(client, modele, systeme, message):
    reponse = client.chat.completions.create(
        model=modele,
        messages=[{"role": "system", "content": systeme},
                  {"role": "user", "content": message}],
        temperature=0,
    )
    return reponse.choices[0].message.content


def extraire_json(texte):
    """Récupère le premier objet JSON de la réponse du LLM (vide si illisible)."""
    trouve = re.search(r"\{.*\}", texte or "", re.DOTALL)
    if not trouve:
        return {}
    try:
        return json.loads(trouve.group())
    except json.JSONDecodeError:
        return {}


def demander(question, valides, convertir=str, aide=None):
    while True:
        reponse = input(f"{question} ").strip()
        try:
            valeur = convertir(reponse)
        except ValueError:
            valeur = None
        if valeur in valides:
            return valeur
        print(f"  {aide or 'Choix possibles : ' + ', '.join(str(v) for v in valides)}")


def entier(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def nom_simple(commune):
    """'Cugy (VD)' -> 'cugy' : l'OFSP ajoute parfois le canton au nom de la commune."""
    return re.sub(r"\s*\([A-Z]{2}\)$", "", str(commune).strip()).casefold()


def trouver_commune(npa, commune_citee=None, demander=demander):
    """Déduit commune, canton et région d'un NPA. La commune fait foi (OFSP) :
    si le NPA couvre des communes de régions différentes, on demande laquelle."""
    communes = communes_du_npa(npa)
    if commune_citee:
        citee = communes[communes["commune"].map(nom_simple) == nom_simple(commune_citee)]
        if len(citee) == 1:
            communes = citee

    if len(communes[["canton", "region"]].drop_duplicates()) == 1:
        # Une seule région possible : inutile de demander la commune
        c = communes.iloc[0]
        return " / ".join(communes["commune"]), c["canton"], int(c["region"])

    print(f"\nLe NPA {npa} couvre des communes de régions de primes différentes.")
    print("C'est ta commune de domicile qui fait foi :")
    for i, c in enumerate(communes.itertuples(), 1):
        canton = "" if c.commune.endswith(f"({c.canton})") else f" ({c.canton})"
        print(f"  {i}. {c.commune}{canton}")
    choix = demander("Numéro de ta commune ?", range(1, len(communes) + 1), int,
                     aide=f"Tape un numéro entre 1 et {len(communes)}.")
    c = communes.iloc[choix - 1]
    return c["commune"], c["canton"], int(c["region"])


def valider_profil(profil, demander=demander):
    """Vérifie chaque champ extrait par le LLM ; redemande ceux qui manquent ou sont faux."""
    npas = set(regions["npa"])
    npa = entier(profil.get("npa"))
    if npa not in npas:
        npa = demander("Quel est ton code postal (NPA) ?", npas, int,
                       aide="NPA inconnu : tape un code postal suisse à 4 chiffres.")
    commune, canton, region = trouver_commune(npa, profil.get("commune"), demander)

    age = entier(profil.get("age"))
    if age not in range(0, 121):
        age = demander("Quel âge as-tu ?", range(0, 121), int,
                       aide="Tape un âge entre 0 et 120.")

    franchises = FRANCHISES[classe_age(age)]
    franchise = entier(profil.get("franchise"))
    if franchise not in franchises:
        franchise = demander(
            f"Quelle franchise en CHF ({', '.join(map(str, franchises))}) ?",
            franchises, int)

    travaille_8h = profil.get("travaille_8h")
    if not isinstance(travaille_8h, bool):
        travaille_8h = demander(
            "Travailles-tu au moins 8 h par semaine chez le même employeur ? (o/n)",
            ["o", "n"], lambda s: s.lower()[:1]) == "o"

    return {"npa": npa, "commune": commune, "canton": canton, "region": region,
            "age": age, "franchise": franchise, "travaille_8h": travaille_8h}


def resumer_faits(profil, resultats):
    """Résumé factuel pour le LLM : moins chère, moins chère par modèle, risque de franchise.
    Tous les montants sont calculés ici et arrondis au franc."""
    def chf(x):
        return f"{round(x)} CHF"

    moins_chere = resultats.iloc[0]
    quote_part = QUOTE_PART_MAX[classe_age(profil["age"])]
    descriptions = {m["nom"]: m["description"] for m in MODELES.values()}
    lignes = [
        f"Profil : {profil['age']} ans, {profil['commune']} ({profil['canton']}), couverture "
        f"accident {'exclue (assurée par l’employeur)' if profil['travaille_8h'] else 'incluse'}.",
        f"Offre la moins chère : {moins_chere['Assureur']}, modèle {moins_chere['Modèle']}, "
        f"{chf(moins_chere['Prime/an'])} par an.",
        "Offre la moins chère de chaque modèle :",
    ]
    for nom_modele, offres in resultats.groupby("Modèle", sort=False):
        o = offres.iloc[0]
        ecart = ("c'est l'offre la moins chère" if o["Écart/an"] == 0
                 else f"soit {chf(o['Écart/an'])} de plus par an que l'offre la moins chère")
        lignes.append(f"- {nom_modele} ({descriptions[nom_modele]}) : {o['Assureur']}, "
                      f"{chf(o['Prime/an'])} par an, {ecart}.")
    lignes += [
        f"Franchise : {profil['franchise']} CHF par an, payés par toi avant que l'assurance rembourse.",
        f"Quote-part maximale : {quote_part} CHF par an.",
        f"Si tes frais médicaux sont élevés, tu paies jusqu'à "
        f"{chf(profil['franchise'] + quote_part)} en plus de la prime (franchise + quote-part), "
        f"soit un coût maximal de {chf(moins_chere['Coût max/an'])} par an avec l'offre la moins chère.",
        "Source : primes officielles OFSP 2027.",
    ]
    return "\n".join(lignes)


def nombres(texte):
    """Nombres cités dans un texte ('5 124', "5'124" et '5124.00' donnent 5124)."""
    texte = re.sub(r"(?<=\d)[ '’  ](?=\d{3}\b)", "", texte or "")
    return {float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", texte)}


def montants_intrus(reponse, faits):
    """Nombres de la réponse du LLM absents des faits fournis (vide si tout est correct)."""
    return sorted(nombres(reponse) - nombres(faits))


def texte_standard(faits):
    """Explication de secours, sans LLM, si les montants d'Apertus restent faux."""
    return ("Je n'ai pas pu générer d'explication fiable. Voici les faits principaux :\n"
            + "\n".join(l for l in faits.splitlines() if not l.startswith("Profil")))


def expliquer(client, modele, faits):
    """Demande l'explication au LLM, la vérifie, réessaie une fois, sinon texte standard."""
    explication = demander_llm(client, modele, PROMPT_EXPLICATION, faits)
    intrus = montants_intrus(explication, faits)
    if not intrus:
        return explication
    rappel = (f"\n\nATTENTION : une réponse précédente citait des montants absents des faits "
              f"({', '.join(f'{n:g}' for n in intrus)}). N'utilise que les montants ci-dessus.")
    explication = demander_llm(client, modele, PROMPT_EXPLICATION, faits + rappel)
    return explication if not montants_intrus(explication, faits) else texte_standard(faits)


def main():
    config = lire_config()
    client = OpenAI(base_url=config["LLM_BASE_URL"], api_key=config["LLM_API_KEY"])
    modele = config["LLM_NAME"]

    print("=== Comparateur de primes LAMal (données OFSP) ===\n")
    situation = input("Décris ta situation (âge, code postal, travail, franchise souhaitée) :\n> ")

    brut = demander_llm(client, modele, PROMPT_EXTRACTION, situation)
    profil = valider_profil(extraire_json(brut))
    print(f"\nProfil retenu : {profil['commune']} ({profil['npa']}), canton "
          f"{profil['canton']}, région {profil['region']}, {profil['age']} ans, "
          f"franchise {profil['franchise']} CHF, "
          f"accident {'exclu' if profil['travaille_8h'] else 'inclus'}")

    # Qui travaille >= 8 h/semaine est assuré contre les accidents par l'employeur (LAA)
    resultats = comparer(profil["canton"], profil["region"], profil["age"],
                         profil["franchise"], avec_accident=not profil["travaille_8h"])
    if resultats.empty:
        print("\nAucune prime trouvée pour ce profil.")
        return

    tableau = resultats.to_string(index=False, float_format="%.2f")
    print(f"\nLes {len(resultats)} offres les moins chères (CHF) :\n{tableau}\n")

    # Tous les faits (définitions et montants) viennent de Python, pas du LLM
    faits = resumer_faits(profil, resultats)
    explication = expliquer(client, config["LLM_NAME_RESTITUTION"], faits)
    print(f"Apertus :\n{explication}\n")
    print("Primes officielles OFSP 2027. Vérifie sur priminfo.admin.ch avant de changer d'assurance.")


if __name__ == "__main__":
    main()
