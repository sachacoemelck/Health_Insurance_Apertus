"""Orientation assurances complémentaires : Apertus comprend le besoin, Python fournit les faits.

1. L'utilisateur décrit ses besoins en langage libre.
2. Apertus (LLM_NAME, ex. 8B) en déduit les catégories concernées (JSON).
3. Python récupère les produits de data/complementaires.csv et les affiche par catégorie et caisse.
4. Apertus (LLM_NAME_RESTITUTION, ex. 70B) résume en 5-6 phrases, sans prime ni recommandation.
   Python vérifie que chaque montant cité figure dans les faits.
"""
import re
from datetime import date

import pandas as pd
from openai import OpenAI

from chatbot import demander_llm, extraire_json, lire_config, montants_intrus
from comparateur import DATA_DIR

produits = pd.read_csv(DATA_DIR / "complementaires.csv", dtype=str)

CATEGORIES = {
    "lunettes": "Lunettes et lentilles",
    "dentaire": "Soins dentaires",
    "medecines_alternatives": "Médecines alternatives",
    "hospitalisation": "Hospitalisation",
}

# Ce que la LAMal couvre déjà, par catégorie. Texte rédigé à la main : tant qu'il vaut
# A_REMPLIR, rien n'est transmis au LLM sur la LAMal pour cette catégorie.
LAMAL_COUVRE = {
    "lunettes": "A_REMPLIR",
    "dentaire": "A_REMPLIR",
    "medecines_alternatives": "A_REMPLIR",
    "hospitalisation": "A_REMPLIR",
}

RAPPEL = ("Les assurances complémentaires ne sont pas obligatoires : un questionnaire de santé "
          "est demandé, et la caisse peut refuser ta demande ou exclure des problèmes de santé "
          "existants. Vérifie les délais de carence et les conditions générales sur le site de "
          "la caisse avant de signer. Données vérifiées le {date} : aucun prix de prime n'est indiqué.")

PROMPT_BESOINS = """Tu identifies les besoins d'assurance complémentaire d'une personne vivant en Suisse.
Réponds UNIQUEMENT avec un objet JSON de la forme {"categories": [...]}, sans texte autour.
Catégories possibles :
- "lunettes" : lunettes, lentilles, chirurgie de la vue
- "dentaire" : dentiste, contrôles, hygiéniste, orthodontie, couronnes
- "medecines_alternatives" : ostéopathie, acupuncture, naturopathie, homéopathie, massages, thérapeutes
- "hospitalisation" : hôpital, opération, chambre privée ou demi-privée, libre choix du médecin à l'hôpital
Mets seulement les catégories clairement mentionnées. Liste vide si aucune."""

PROMPT_EXPLICATION = """Tu aides une personne vivant en Suisse à comprendre les assurances complémentaires.
Règles strictes :
- Utilise UNIQUEMENT les faits fournis. N'ajoute aucune information extérieure.
- Ne fais AUCUN calcul et ne cite AUCUN montant qui n'apparaît pas tel quel dans les faits.
- Ne cite aucun prix de prime. Ne recommande aucune caisse ni aucun produit en particulier.
- Si ce que couvre la LAMal est « non disponible », ne dis rien sur la LAMal pour cette catégorie.
- Ne tire aucune conclusion du nom d'un produit : seule sa description compte.
- Tutoie l'utilisateur. Écris en français simple.
- Écris 5 à 6 phrases au total, en un seul paragraphe, sans liste ni tableau.
  Ne recopie pas la liste des produits : l'utilisateur la voit déjà.
Contenu : ce que la LAMal couvre déjà (si fourni), les grandes différences entre les offres
(plafonds, taux, périodes), et les pièges importants : délais de carence, exclusions,
garanties préalables, et produits marqués « à vérifier »."""

# Signalement : source secondaire, mention « à vérifier / non vérifié » ou chiffre d'un comparateur
MOTIF_A_VERIFIER = re.compile(r"v[ée]rifi|moneyland|comparis", re.IGNORECASE)
AGE_MAX_CONDITIONS = 5  # ans


def avertissements(p):
    """Avertissements d'une ligne du CSV : à vérifier, conditions anciennes."""
    alertes = []
    texte = " ".join(str(p[c]) for c in ("prestation", "plafond_chf", "periode", "conditions")
                     if pd.notna(p[c]))
    if p["type_source"] == "secondaire" or MOTIF_A_VERIFIER.search(texte):
        alertes.append("à vérifier")
    # Édition des conditions : « Conditions édition 07.2015 » ou « ..._2015.07_... » dans l'URL
    edition = (re.search(r"(?i)conditions[^.]*?\d{2}\.(\d{4})", str(p["conditions"]))
               or re.search(r"[_-](20\d{2})\.\d{2}_", str(p["source_url"])))
    if edition and date.today().year - int(edition.group(1)) > AGE_MAX_CONDITIONS:
        alertes.append(f"conditions de {edition.group(1)}, peut-être plus à jour")
    return alertes


def details(p):
    """Taux, plafond et période d'une ligne, en une phrase (vide si rien n'est connu)."""
    morceaux = []
    if pd.notna(p["taux_rembourse"]):
        morceaux.append(f"remboursé à {p['taux_rembourse']}")
    if pd.notna(p["plafond_chf"]):
        morceaux.append(f"plafond {p['plafond_chf']} CHF")
    if pd.notna(p["periode"]):
        morceaux.append(p["periode"])
    return ", ".join(morceaux)


def produits_pour(categories):
    """Lignes du CSV pour ces catégories, plus celles qui valent pour toutes."""
    choix = produits[produits["categorie"].isin(list(categories) + ["toutes"])].copy()
    choix["ordre"] = choix["categorie"].map({c: i for i, c in enumerate(categories)}).fillna(99)
    return choix.sort_values(["ordre", "assureur"], kind="stable")


def afficher(choix):
    for categorie, lignes in choix.groupby("categorie", sort=False):
        print(f"\n=== {CATEGORIES.get(categorie, 'Toutes catégories')} ===")
        if LAMAL_COUVRE.get(categorie) == "A_REMPLIR":
            print("[À compléter] Ce que couvre déjà la LAMal : texte pas encore rédigé.")
        elif categorie in LAMAL_COUVRE:
            print(f"Ce que couvre déjà la LAMal : {LAMAL_COUVRE[categorie]}")
        for assureur, offres in lignes.groupby("assureur", sort=False):
            print(f"\n{assureur}")
            for _, p in offres.iterrows():
                print(f"  • {p['produit']} — {p['prestation']}")
                if details(p):
                    print(f"      {details(p)}")
                if pd.notna(p["conditions"]):
                    print(f"      Conditions : {p['conditions']}")
                for alerte in avertissements(p):
                    print(f"      ⚠ {alerte.upper()}")


def faits_pour(besoin, categories, choix):
    """Faits transmis au LLM : besoin exprimé, couverture LAMal si rédigée, produits du CSV."""
    lignes = [f"Besoin exprimé : {besoin}"]
    for c in categories:
        texte = LAMAL_COUVRE[c]
        lignes.append(f"Ce que couvre la LAMal ({CATEGORIES[c]}) : "
                      f"{'non disponible' if texte == 'A_REMPLIR' else texte}")
    lignes.append("Produits (source : sites des caisses) :")
    for _, p in choix.iterrows():
        ligne = f"- [{CATEGORIES.get(p['categorie'], 'toutes catégories')}] {p['assureur']}, " \
                f"{p['produit']} : {p['prestation']}"
        for morceau in (details(p), p["conditions"] if pd.notna(p["conditions"]) else ""):
            if morceau:
                ligne += f". {morceau}"
        alertes = avertissements(p)
        if alertes:
            ligne += f" [{'; '.join(alertes)}]"
        lignes.append(ligne)
    return "\n".join(lignes)


def demander_categories():
    noms = list(CATEGORIES)
    print("Je n'ai pas identifié ton besoin. Choisis une ou plusieurs catégories :")
    for i, c in enumerate(noms, 1):
        print(f"  {i}. {CATEGORIES[c]}")
    while True:
        choix = [noms[int(n) - 1] for n in re.findall(r"\d", input("Numéros (ex. 1,3) : "))
                 if 1 <= int(n) <= len(noms)]
        if choix:
            return list(dict.fromkeys(choix))
        print("  Tape au moins un numéro entre 1 et 4.")


def expliquer(client, modele, faits):
    """Résumé par le LLM, vérifié ; un nouvel essai, puis renvoi au tableau si les montants restent faux."""
    for rappel in ("", "\n\nATTENTION : n'utilise QUE des montants présents ci-dessus."):
        explication = demander_llm(client, modele, PROMPT_EXPLICATION, faits + rappel)
        if not montants_intrus(explication, faits):
            return explication
    return "Je n'ai pas pu générer de résumé fiable : réfère-toi à la liste ci-dessus."


def main():
    config = lire_config()
    client = OpenAI(base_url=config["LLM_BASE_URL"], api_key=config["LLM_API_KEY"])

    print("=== Orientation assurances complémentaires ===\n")
    besoin = input("Décris tes besoins (lunettes, dentiste, ostéo, hôpital...) :\n> ")
    brut = demander_llm(client, config["LLM_NAME"], PROMPT_BESOINS, besoin)
    categories = [c for c in extraire_json(brut).get("categories", []) if c in CATEGORIES]
    categories = list(dict.fromkeys(categories)) or demander_categories()
    print(f"\nCatégories retenues : {', '.join(CATEGORIES[c] for c in categories)}")

    choix = produits_pour(categories)
    afficher(choix)

    faits = faits_pour(besoin, categories, choix)
    explication = expliquer(client, config["LLM_NAME_RESTITUTION"], faits)
    print(f"\nApertus :\n{explication}\n")
    print(RAPPEL.format(date=produits["date_verification"].max()))


if __name__ == "__main__":
    main()
