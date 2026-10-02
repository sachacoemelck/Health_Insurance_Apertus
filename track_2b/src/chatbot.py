"""Chatbot LAMal : Apertus comprend la situation, pandas calcule les primes.

1. L'utilisateur décrit sa situation en langage libre.
2. Apertus extrait un profil JSON (canton, region, age, franchise, travaille_8h).
3. Python vérifie le profil et appelle comparer() sur les données OFSP.
4. Apertus explique les offres en français, sans calculer ni inventer de chiffre.
"""
import json
import os
import re
import sys

from dotenv import load_dotenv
from openai import OpenAI

from comparateur import classe_age, comparer, df

load_dotenv()

FRANCHISES = {
    "AKA_01_KIN": [0, 100, 200, 300, 400, 500, 600],
    "AKA_02_JUG": [300, 500, 1000, 1500, 2000, 2500],
    "AKA_03_ERW": [300, 500, 1000, 1500, 2000, 2500],
}

PROMPT_EXTRACTION = """Tu extrais le profil d'assurance maladie (LAMal) d'une personne vivant en Suisse.
Réponds UNIQUEMENT avec un objet JSON, sans texte autour, avec ces clés :
- "canton" : abréviation officielle en 2 lettres majuscules (ex. "VD", "GE", "ZH")
- "region" : région de primes (0, 1, 2 ou 3), ou null si inconnue
- "age" : âge en années (entier)
- "franchise" : franchise annuelle en CHF (entier), ou null si non mentionnée
- "travaille_8h" : true si la personne travaille au moins 8 heures par semaine chez le même employeur, false sinon, null si inconnu
Mets null pour toute information absente. N'invente rien."""

PROMPT_EXPLICATION = """Tu aides une personne vivant en Suisse à choisir son assurance maladie de base (LAMal).
Explique en français, simplement, les offres du tableau fourni : qui est le moins cher,
les écarts de prix et ce que signifient les types de modèle (TEL = télémédecine,
HAM = médecin de famille, HMO/PRAXIS = cabinet de groupe, BASE = libre choix du médecin, etc.).
Utilise UNIQUEMENT les chiffres du tableau : ne calcule et n'invente aucune prime ni aucun assureur.
Les primes sont mensuelles, en CHF, issues des données officielles de l'OFSP.
Rappelle de vérifier sur priminfo.admin.ch avant de changer d'assurance."""


def lire_config():
    config = {k: os.getenv(k) for k in ("LLM_NAME", "LLM_BASE_URL", "LLM_API_KEY")}
    manquantes = [k for k, v in config.items() if not v]
    if manquantes:
        sys.exit(f"Variables manquantes : {', '.join(manquantes)}. "
                 "Copie .env.example vers .env et remplis-le.")
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


def demander(question, valides, convertir=str):
    while True:
        reponse = input(f"{question} ").strip()
        try:
            valeur = convertir(reponse)
        except ValueError:
            valeur = None
        if valeur in valides:
            return valeur
        print(f"  Choix possibles : {', '.join(str(v) for v in valides)}")


def entier(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def valider_profil(profil, demander=demander):
    """Vérifie chaque champ extrait par le LLM ; redemande ceux qui manquent ou sont faux."""
    cantons = sorted(df["Kanton"].unique())
    canton = str(profil.get("canton") or "").upper()
    if canton not in cantons:
        canton = demander("Dans quel canton habites-tu (ex. VD, GE, ZH) ?",
                          cantons, lambda s: s.upper())

    regions = sorted(int(r.removeprefix("PR_REG_"))
                     for r in df.loc[df["Kanton"] == canton, "Region"].unique())
    region = entier(profil.get("region"))
    if region not in regions:
        region = regions[0] if len(regions) == 1 else demander(
            f"Région de primes de ta commune ({', '.join(map(str, regions))}) ? "
            "(voir priminfo.admin.ch)", regions, int)

    age = entier(profil.get("age"))
    if age not in range(0, 121):
        age = demander("Quel âge as-tu ?", range(0, 121), int)

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

    return {"canton": canton, "region": region, "age": age,
            "franchise": franchise, "travaille_8h": travaille_8h}


def main():
    config = lire_config()
    client = OpenAI(base_url=config["LLM_BASE_URL"], api_key=config["LLM_API_KEY"])
    modele = config["LLM_NAME"]

    print("=== Comparateur de primes LAMal (données OFSP) ===\n")
    situation = input("Décris ta situation (âge, lieu, travail, franchise souhaitée) :\n> ")

    brut = demander_llm(client, modele, PROMPT_EXTRACTION, situation)
    profil = valider_profil(extraire_json(brut))
    print(f"\nProfil retenu : {profil}")

    # Qui travaille >= 8 h/semaine est assuré contre les accidents par l'employeur (LAA)
    resultats = comparer(profil["canton"], profil["region"], profil["age"],
                         profil["franchise"], avec_accident=not profil["travaille_8h"])
    if resultats.empty:
        print("\nAucune prime trouvée pour ce profil.")
        return

    tableau = resultats.to_string(index=False)
    print(f"\nLes {len(resultats)} primes mensuelles les moins chères (CHF) :\n{tableau}\n")

    explication = demander_llm(client, modele, PROMPT_EXPLICATION, (
        f"Profil : {json.dumps(profil, ensure_ascii=False)}\n"
        f"Couverture accident : {'exclue' if profil['travaille_8h'] else 'incluse'}\n\n"
        f"Tableau des primes (OFSP) :\n{tableau}"))
    print(f"Apertus :\n{explication}")


if __name__ == "__main__":
    main()
