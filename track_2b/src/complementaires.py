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

from chatbot import demander_llm, en_langue, extraire_json, lire_config, montants_intrus, tutoie
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
    "lunettes": "Jusqu'à 18 ans révolus, la LAMal rembourse environ 180 CHF par année civile "
                "pour les lunettes et lentilles. Pour les adultes, seulement en cas de changement "
                "de la vue lié à une maladie.",
    "dentaire": "La LAMal ne rembourse les soins dentaires que s'ils sont liés à une maladie grave "
                "et inévitable de la mastication, à une maladie générale grave, ou à un accident. "
                "Les caries, le détartrage et les appareils dentaires ne sont pas couverts.",
    "medecines_alternatives": "La LAMal rembourse seulement 5 méthodes (acupuncture, médecine "
                              "anthroposophique, médecine traditionnelle chinoise, homéopathie, "
                              "phytothérapie), et uniquement si le traitement est fait par un "
                              "médecin ayant la formation reconnue. L'ostéopathie n'est pas couverte.",
    "hospitalisation": "La LAMal couvre l'hospitalisation en division commune, dans les hôpitaux "
                       "figurant sur la liste du canton de résidence, au maximum au tarif de ce canton.",
}

# Contrôles Python de la réponse du LLM (voir problemes) — en français uniquement pour l'instant
MOTIF_LAMAL = re.compile(r"LAMal|assurance de base|assurance obligatoire", re.IGNORECASE)
MOTIF_RENVOI = re.compile(r"(?:ci|au)-dessus", re.IGNORECASE)
MOTIF_INDISPENSABLE = re.compile(r"indispensable|n[ée]cessaire|obligatoire", re.IGNORECASE)
# Produit souscrit uniquement en plus d'un autre : exclu des fourchettes de taux
MOTIF_COMPLEMENT = re.compile(r"compl[ée]ment à|en combinaison avec|en plus de", re.IGNORECASE)

RAPPEL = ("Les assurances complémentaires ne sont pas obligatoires : un questionnaire de santé "
          "est demandé, et la caisse peut refuser votre demande ou exclure des problèmes de santé "
          "existants. Vérifiez les délais de carence et les conditions générales sur le site de "
          "la caisse avant de signer. Données vérifiées le {date} : aucun prix de prime n'est indiqué.")

PROMPT_BESOINS = """Tu identifies les besoins d'assurance complémentaire d'une personne vivant en Suisse.
Réponds UNIQUEMENT avec un objet JSON de la forme {"categories": [...]}, sans texte autour.
Catégories possibles :
- "lunettes" : lunettes, lentilles, chirurgie de la vue
- "dentaire" : dentiste, contrôles, hygiéniste, orthodontie, couronnes
- "medecines_alternatives" : ostéopathie, acupuncture, naturopathie, homéopathie, massages, thérapeutes
- "hospitalisation" : hôpital, opération, chambre privée ou demi-privée, libre choix du médecin à l'hôpital
Par défaut, la liste est VIDE. Ajoute une catégorie seulement si la personne exprime
explicitement un besoin qui la concerne. L'âge, le lieu, le travail ou la franchise ne sont pas des besoins.
Exemples sans aucun besoin, réponse {"categories": []} :
- « 25 ans, 2000 Neuchâtel, franchise 2500, je suis au chômage »
- « 44 ans, 1260, franchise 500, je vais souvent chez le médecin »
- « j'ai 40 ans, j'habite à Renens, je bosse »"""

# Garde-fou : une catégorie n'est gardée que si un mot lié figure dans la phrase
MOTS_BESOINS = {
    "lunettes": r"lunette|lentille|verres|\bvue\b|opticien|myop|presbyt|brille|occhiali",
    "dentaire": r"\bdent|orthodont|hygi[ée]niste|d[ée]tartrage|couronne|zahn",
    "medecines_alternatives": r"ost[ée]o|acupunct|naturo|hom[ée]o|massage|th[ée]rapeute|chiro|"
                              r"kin[ée]sio|shiatsu|phyto|m[ée]decines?\s+(?:alternative|douce|compl[ée]mentaire)",
    "hospitalisation": r"h[ôo]pita|hospitalis|clinique|chambre|op[ée]ration|spital|ospedal",
}

PROMPT_EXPLICATION = """Tu aides une personne vivant en Suisse à comprendre les assurances complémentaires.
Règles strictes :
- Utilise UNIQUEMENT les faits fournis. N'ajoute aucune information extérieure.
- Ne fais AUCUN calcul et ne cite AUCUN montant qui n'apparaît pas tel quel dans les faits.
- Ne cite aucun prix de prime. Ne recommande aucune caisse ni aucun produit en particulier.
- Ne cite AUCUN nom de caisse ni de produit : parle de tendances (« certaines offres »,
  « les plafonds vont de ... à ... »). L'utilisateur voit déjà la liste détaillée.
- Ne décris JAMAIS ce que couvre la LAMal. Si c'est utile, dis seulement que c'est expliqué
  ci-dessus. Si les faits indiquent que ce n'est pas affiché, ne parle pas de la LAMal.
- Ne dis jamais qu'une assurance complémentaire est indispensable, nécessaire ou obligatoire.
- Pour les taux de remboursement, utilise uniquement la fourchette fournie pour chaque
  catégorie : ne mélange jamais les catégories.
- Cite toujours un plafond avec sa période (par séance, par année, sur 3 ans).
- « Non mentionné » ne veut pas dire « non couvert » : ne transforme jamais un silence en exclusion.
- Ne tire aucune conclusion du nom d'un produit : seule sa description compte.
- Vouvoie l'utilisateur. Écris en {langue} simple.
- Écris 5 à 6 phrases au total, en un seul paragraphe, sans liste ni tableau.
Contenu : les grandes différences entre les offres (plafonds, taux, périodes), et les
pièges importants : délais de carence, exclusions, garanties préalables."""

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


def est_complement(p):
    """Vrai si le produit ne se souscrit qu'en plus d'un autre (ex. COMPLETA PLUS)."""
    return bool(MOTIF_COMPLEMENT.search(f"{p['prestation']} {p['conditions']}"))


def fourchette_taux(choix, categorie):
    """Taux minimal et maximal d'une catégorie, hors compléments (None si aucun taux connu)."""
    lignes = choix[(choix["categorie"] == categorie) & ~choix.apply(est_complement, axis=1)]
    taux = lignes["taux_rembourse"].dropna()
    taux = taux.str.rstrip("%").astype(int)
    return (taux.min(), taux.max()) if len(taux) else None


# Comptages par catégorie : élément recherché -> motif dans prestation/conditions
MOTS_CLES = {
    "lunettes": {"montures": r"monture", "lentilles": r"lentille",
                 "chirurgie de la vue": r"chirurgie|laser|correction des yeux"},
    "dentaire": {"orthodontie": r"orthodont", "contrôles et hygiène": r"contr[ôo]le|hygi[èe]n|détartrage",
                 "couronnes, ponts ou prothèses": r"couronne|pont|proth[èe]se"},
    "medecines_alternatives": {"ostéopathie (citée explicitement)": r"ost[ée]opath",
                               "massages": r"massage"},
    "hospitalisation": {"division privée": r"(?<![-\w])priv[ée]e",
                        "division demi-privée": r"(?:demi|mi|semi)-priv"},
}
MOTIF_NEGATION = re.compile(r"non couvert|exclu|pas d[e'’]|aucune prestation", re.IGNORECASE)
MOTIF_CONDITION = re.compile(r"carence|exclu|garantie préalable|accord préalable|franchise|"
                             r"attestation|souscription jusqu", re.IGNORECASE)
TOUS_LES_NOMS = sorted(set(produits["produit"]) | set(produits["assureur"]), key=len, reverse=True)


def offres_txt(nb):
    return f"{nb} offre{'s' if nb > 1 else ''}"


def type_periode(periode):
    p = str(periode).lower()
    if "séance" in p or "heure" in p:
        return "par séance ou par heure"
    if "3 an" in p:
        return "par période de 3 ans"
    if "année" in p or "par an" in p:
        return "par année"
    return "période non précisée"


def anonymiser(texte):
    for nom in TOUS_LES_NOMS:
        texte = re.sub(rf"\b{re.escape(nom)}\b", "un autre produit", texte)
    return texte


def fragments(p):
    """Morceaux de phrase d'une ligne (prestation, période, conditions)."""
    texte = ". ".join(str(p[c]) for c in ("prestation", "periode", "conditions") if pd.notna(p[c]))
    return [f.strip() for f in re.split(r"\.\s+|,\s+(?=après)", texte) if f.strip()]


def faits_categorie(c, lignes):
    """Faits agrégés et anonymes d'une catégorie : aucun nom de caisse ni de produit."""
    vides = lignes["prestation"].str.contains("aucune prestation", case=False)
    offres = lignes[~vides]
    n = len(offres)
    affiche = LAMAL_COUVRE[c] != "A_REMPLIR"
    faits = [f"[{CATEGORIES[c]}] Ce que couvre la LAMal : {'affiché ci-dessus' if affiche else 'non affiché'}.",
             f"- {len(lignes)} offres listées, dont {int(vides.sum())} sans aucune prestation "
             f"dans cette catégorie."]
    taux = fourchette_taux(lignes, c)
    if taux:
        faits.append(f"- Taux de remboursement (hors compléments à un autre produit) : "
                     + (f"{taux[0]}%." if taux[0] == taux[1] else f"de {taux[0]}% à {taux[1]}%."))
    plafonds = offres.assign(montant=pd.to_numeric(offres["plafond_chf"], errors="coerce"),
                             type=offres["periode"].map(type_periode)).dropna(subset=["montant"])
    for type_p, groupe in plafonds.groupby("type", sort=False):
        mini, maxi = int(groupe["montant"].min()), int(groupe["montant"].max())
        etendue = f"{mini} CHF" if mini == maxi else f"de {mini} à {maxi} CHF"
        faits.append(f"- Plafonds {type_p} : {etendue} ({offres_txt(len(groupe))}).")
    for element, motif in MOTS_CLES[c].items():
        couvert = non_couvert = 0
        for _, p in offres.iterrows():
            trouves = [f for f in fragments(p) if re.search(motif, f, re.IGNORECASE)]
            if trouves:
                if all(MOTIF_NEGATION.search(f) for f in trouves):
                    non_couvert += 1
                else:
                    couvert += 1
        faits.append(f"- {element.capitalize()} : mentionné comme couvert par {offres_txt(couvert)}, "
                     f"explicitement non couvert par {non_couvert}, non mentionné pour les "
                     f"{n - couvert - non_couvert} autres (sur {n}).")
    conditions = {}
    for _, p in offres.iterrows():
        for f in dict.fromkeys(fragments(p)):
            if MOTIF_CONDITION.search(f):
                cle = anonymiser(f)
                conditions[cle] = conditions.get(cle, 0) + 1
    if conditions:
        faits.append("- Conditions relevées : " + " ; ".join(
            f"« {cond} » ({offres_txt(nb)})" for cond, nb in conditions.items()))
    return faits


def faits_pour(besoin, categories, choix):
    """Faits transmis au LLM : uniquement des agrégats calculés par Python, sans aucun nom."""
    faits = [f"Besoin exprimé : {besoin}"]
    for c in categories:
        faits += faits_categorie(c, choix[choix["categorie"] == c])
    for _, p in choix[choix["categorie"] == "toutes"].iterrows():
        faits.append(f"[Toutes catégories] 1 caisse indique : {anonymiser(p['prestation'])}.")
    return "\n".join(faits)


# --- Les 3 produits avec la couverture la plus élevée, par besoin -------------------------
CRITERE_CLASSEMENT = {
    "hospitalisation": "classement par type de chambre (privée, puis demi-privée, puis "
                       "commune), puis remboursement à 100 % indiqué, puis choix fixe de la "
                       "division (sans participation selon le séjour)",
    "autres": "classement par plafond annuel (un plafond sur 3 ans compte pour un tiers par "
              "an ; « sans plafond » en premier ; plafonds par séance ou par traitement "
              "ensuite), puis par taux de remboursement",
}
MOTIF_LIMITE_AGE = re.compile(r"(?<!\()jusqu'à (\d+) ans", re.IGNORECASE)
MOTIF_LIMITE_SOUSCRIPTION = re.compile(r"souscription jusqu'à (\d+) ans", re.IGNORECASE)
NIVEAUX_DIVISION = [(3, r"(?<![-\w])priv[ée]e|chambre individuelle|un lit"),
                    (2, r"(?:demi|mi|semi)-priv|deux lits"),
                    (1, r"commune")]


def accessible(p, age):
    """Faux si la prestation est réservée à un âge dépassé (ex. orthodontie jusqu'à 20 ans)."""
    if age is None:
        return True
    texte = f"{p['periode']} {p['conditions']}"
    limites = [int(m) for m in MOTIF_LIMITE_AGE.findall(str(p["periode"]))]
    limites += [int(m) for m in MOTIF_LIMITE_SOUSCRIPTION.findall(texte)]
    return all(age <= limite for limite in limites)


def plafond_annuel(p):
    """(groupe, valeur) pour classer : 3 = sans plafond, 2 = plafond annuel (3 ans / 3),
    1 = par séance, par heure ou pour tout le traitement, 0 = plafond inconnu."""
    periode = str(p["periode"]).lower()
    if "sans plafond" in periode:
        return 3, float("inf")
    montants = [int(m) for m in re.findall(r"\d+", str(p["plafond_chf"]))]
    if not montants:
        return 0, 0
    valeur = max(montants)  # « 600 à 5000 » : la variante la plus élevée
    if type_periode(periode) == "par période de 3 ans":
        return 2, valeur / 3
    if type_periode(periode) == "par année":
        return 2, valeur
    return 1, valeur


def taux_pourcent(p):
    return int(str(p["taux_rembourse"]).rstrip("%")) if pd.notna(p["taux_rembourse"]) else 0


def niveau_division(p):
    """Niveau de chambre le plus élevé accessible : 3 privée, 2 demi-privée, 1 commune, 0 inconnu."""
    for niveau, motif in NIVEAUX_DIVISION:
        if re.search(motif, str(p["prestation"]), re.IGNORECASE):
            return niveau
    return 2 if "choix de la division" in str(p["prestation"]).lower() else 0


def meilleurs_produits(choix, categorie, age=None, n=3):
    """Les n produits avec la couverture la plus élevée d'une catégorie (une ligne par produit),
    et le nombre d'autres produits au même niveau que le dernier retenu (ex aequo)."""
    lignes = choix[choix["categorie"] == categorie]
    complements = {(p["assureur"], p["produit"]) for _, p in lignes.iterrows() if est_complement(p)}
    candidats = []
    for _, p in lignes.iterrows():
        if ("aucune prestation" in str(p["prestation"]).lower()
                or (p["assureur"], p["produit"]) in complements or not accessible(p, age)):
            continue
        if categorie == "hospitalisation":
            flex = "choix" in str(p["prestation"]).lower()
            cle = (niveau_division(p), taux_pourcent(p) == 100, not flex, not avertissements(p))
        else:
            cle = (*plafond_annuel(p), taux_pourcent(p))
        candidats.append((cle, p))
    candidats.sort(key=lambda c: c[0], reverse=True)  # tri stable : ordre du CSV en cas d'égalité
    retenus, vus = [], set()
    for cle, p in candidats:
        if (p["assureur"], p["produit"]) not in vus:
            vus.add((p["assureur"], p["produit"]))
            retenus.append((cle, p))
    meilleurs = retenus[:n]
    ex_aequo = sum(1 for cle, _ in retenus[n:] if meilleurs and cle == meilleurs[-1][0])
    return [p for _, p in meilleurs], ex_aequo


def produits_a_verifier(choix):
    """{(caisse, produit): [avertissements]} ; un produit à plusieurs lignes n'apparaît qu'une fois."""
    a_verifier = {}
    for _, p in choix.iterrows():
        alertes = avertissements(p)
        if alertes:
            a_verifier.setdefault((p["assureur"], p["produit"]), alertes)
    return a_verifier


def afficher_a_verifier(choix):
    """Liste finale des produits à vérifier, affichée par Python (pas par le LLM)."""
    a_verifier = {cle: "; ".join(alertes) for cle, alertes in produits_a_verifier(choix).items()}
    if a_verifier:
        print("\nProduits à vérifier avant de vous décider :")
        for (assureur, produit), alertes in a_verifier.items():
            print(f"  ⚠ {assureur} {produit} : {alertes}")


def filtrer_categories(categories, phrase):
    """Catégories valides du LLM, gardées seulement si un mot lié est dans la phrase."""
    if not isinstance(categories, list):
        return []
    gardees = [c for c in categories if c in CATEGORIES
               and re.search(MOTS_BESOINS[c], phrase or "", re.IGNORECASE)]
    return list(dict.fromkeys(gardees))


def demander_categories():
    noms = list(CATEGORIES)
    print("Je n'ai pas identifié votre besoin. Choisissez une ou plusieurs catégories :")
    for i, c in enumerate(noms, 1):
        print(f"  {i}. {CATEGORIES[c]}")
    while True:
        choix = [noms[int(n) - 1] for n in re.findall(r"\d", input("Numéros (ex. 1,3) : "))
                 if 1 <= int(n) <= len(noms)]
        if choix:
            return list(dict.fromkeys(choix))
        print("  Tapez au moins un numéro entre 1 et 4.")


def problemes(explication, faits, choix, lamal_interdite):
    """Règles violées par la réponse du LLM (liste vide si elle est valide)."""
    texte = explication or ""
    trouves = []
    if montants_intrus(texte, faits):
        trouves.append("montant absent des faits")
    if tutoie(texte):
        trouves.append("tutoiement (il faut vouvoyer l'utilisateur)")
    noms = set(choix["produit"]) | set(choix["assureur"])
    caisses = set(choix["assureur"])
    if any(re.search(rf"\b{re.escape(n)}\b", texte, 0 if n not in caisses else re.IGNORECASE)
           for n in noms):
        trouves.append("nom de caisse ou de produit")
    for phrase in re.split(r"(?<=[.!?])\s+", texte):
        if MOTIF_LAMAL.search(phrase) and (lamal_interdite or not MOTIF_RENVOI.search(phrase)):
            trouves.append("description de la LAMal")
        if "complémentaire" in phrase.lower() and MOTIF_INDISPENSABLE.search(phrase):
            trouves.append("complémentaire présentée comme indispensable")
    return sorted(set(trouves))


def expliquer(client, modele, faits, choix, categories, langue="français"):
    """Résumé par le LLM, vérifié ; un nouvel essai, puis renvoi à la liste s'il reste faux."""
    lamal_interdite = all(LAMAL_COUVRE[c] == "A_REMPLIR" for c in categories)
    systeme = en_langue(PROMPT_EXPLICATION, langue)
    rappel = ""
    for _ in range(3):
        explication = demander_llm(client, modele, systeme, faits + rappel)
        erreurs = problemes(explication, faits, choix, lamal_interdite)
        if not erreurs:
            return explication
        rappel = (f"\n\nATTENTION : ta réponse précédente enfreignait ces règles : "
                  f"{', '.join(erreurs)}. Respecte strictement les règles.")
    return "Je n'ai pas pu générer de résumé fiable : référez-vous à la liste ci-dessus."


def main():
    config = lire_config()
    client = OpenAI(base_url=config["LLM_BASE_URL"], api_key=config["LLM_API_KEY"])

    print("=== Orientation assurances complémentaires ===\n")
    besoin = input("Décrivez vos besoins (lunettes, dentiste, ostéo, hôpital...) :\n> ")
    brut = demander_llm(client, config["LLM_NAME"], PROMPT_BESOINS, besoin)
    categories = (filtrer_categories(extraire_json(brut).get("categories"), besoin)
                  or demander_categories())
    print(f"\nCatégories retenues : {', '.join(CATEGORIES[c] for c in categories)}")

    choix = produits_pour(categories)
    afficher(choix)

    faits = faits_pour(besoin, categories, choix)
    explication = expliquer(client, config["LLM_NAME_RESTITUTION"], faits, choix, categories)
    print(f"\nApertus :\n{explication}\n")
    print(RAPPEL.format(date=produits["date_verification"].max()))
    afficher_a_verifier(choix)


if __name__ == "__main__":
    main()
