from pathlib import Path

import pandas as pd

# Chemin absolu vers track_2b/data/, quel que soit le dossier de lancement
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

df = pd.read_csv(DATA_DIR / "primes_CH.csv")

# Liste officielle des assureurs admis (OFSP) : numéro (colonne Versicherer) -> nom
_assureurs = pd.read_excel(DATA_DIR / "assureurs-admis-2026-10.xlsx",
                           sheet_name="Index ", header=2).dropna(subset=["Nummer"])
ASSUREURS = dict(zip(_assureurs["Nummer"].astype(int), _assureurs["Name"].str.strip()))

# Régions de primes 2027 par NPA (OFSP). C'est la commune (n° OFS) qui fait foi, pas le NPA.
regions = pd.read_excel(DATA_DIR / "praemienregionen-2027.xlsx",
                        sheet_name="B_NPA", header=6).rename(columns={
    "PLZ\nNPA": "npa", "Kanton\nCanton": "canton", "Region\nRégion": "region",
    "BFS-Nr.\nNo OFS": "no_ofs", "Gemeinde\nCommune": "commune",
})
regions = (regions[["npa", "canton", "region", "no_ofs", "commune"]]
           .dropna().astype({"npa": int, "region": int, "no_ofs": int}))

# Modèles d'assurance (colonne Tariftyp) : nom affiché et définition factuelle
MODELES = {
    "BASE": {"nom": "Libre choix",
             "description": "modèle standard sans restriction de choix propre à un réseau ; "
                            "les règles de prise en charge de la LAMal restent applicables"},
    "PRAXIS": {"nom": "Médecin de famille / HMO",
               "description": "premier contact auprès du médecin ou du réseau désigné ; "
                              "vérifier le réseau et les exceptions du produit"},
    "TEL_DIG": {"nom": "Télémédecine / numérique",
                "description": "premier contact par téléphone ou service numérique selon le produit ; "
                               "vérifier les obligations et exceptions"},
    "PHARM": {"nom": "Pharmacie",
              "description": "premier contact en pharmacie selon les conditions du produit"},
    "FLEX": {"nom": "Modèle alternatif",
             "description": "règles propres à chaque assureur : vérifier les conditions "
                            "exactes chez l'assureur"},
}

# Quote-part annuelle maximale (10 % des frais après franchise), plafonnée par la LAMal
QUOTE_PART_MAX = {"AKA_01_KIN": 350, "AKA_02_JUG": 700, "AKA_03_ERW": 700}

def communes_du_npa(npa):
    """Communes couvertes par un NPA (une ligne par n° OFS), avec canton et région."""
    return regions[regions["npa"] == npa].drop_duplicates("no_ofs").reset_index(drop=True)

def classe_age(age):
    if age <= 18:
        return "AKA_01_KIN"
    if age <= 25:
        return "AKA_02_JUG"
    return "AKA_03_ERW"

COLONNES = ["Assureur", "Modèle", "Produit", "Prime/mois", "Prime/an", "Écart/an", "Coût max/an"]

# Sous-groupe d'âge de base (fichier Tarife 2027 de l'OFSP) : K1 = « prime enfant sans réduction
# supplémentaire ». K3, K4 et K5 sont des rabais réservés aux familles à partir du 2e ou 3e enfant :
# les prendre pour un enfant seul sous-estimait sa prime (médiane 52 CHF/mois, mesuré le 9.10.2026).
SOUS_GROUPE_DE_BASE = {"AKA_01_KIN": "K1", "AKA_02_JUG": "J1", "AKA_03_ERW": "E1"}

# Circonscriptions 2027 (OFSP) : certains modèles ne sont proposés que dans une liste de communes.
_einzug = pd.read_csv(DATA_DIR / "einzugsgebiete_2027.csv", dtype={"Gemeinden-BFS": str})
_restreints = _einzug[_einzug["Eingeschränkt"] == "Y"]
CIRCONSCRIPTIONS = {
    (int(v), k, r, t): {int(n) for n in str(bfs).split(",") if n.strip().isdigit()}
    for v, k, r, t, bfs in zip(_restreints["Versicherer"], _restreints["Kanton"], _restreints["Region"],
                               _restreints["Tarif"], _restreints["Gemeinden-BFS"])
}


def disponible(versicherer, canton, region_code, tarif, no_ofs):
    """Vrai si l'offre peut être souscrite dans la commune. Pour un modèle réservé à certaines
    communes, il faut connaître la commune (n° OFS) et qu'elle figure dans la liste ; sinon,
    l'offre n'est pas affichée : mieux vaut une offre en moins qu'une offre impossible à souscrire."""
    communes = CIRCONSCRIPTIONS.get((int(versicherer), canton, region_code, tarif))
    return communes is None or (no_ofs is not None and int(no_ofs) in communes)


def _filtrer(canton, region, age, franchise, avec_accident, accepted_tariff_types=None, premium_year=2027,
             no_ofs=None):
    """Lignes du CSV qui correspondent au profil et que la personne peut souscrire dans sa commune."""
    lettre = {"AKA_01_KIN": "K", "AKA_02_JUG": "J", "AKA_03_ERW": "E"}[classe_age(age)]
    res = df[
        (df["Geschäftsjahr"] == premium_year)
        & (df["Tariftyp"].isin(accepted_tariff_types if accepted_tariff_types is not None else MODELES))
        & (df["Kanton"] == canton)
        & (df["Region"] == f"PR_REG_{region}")
        & (df["Altersklasse"] == classe_age(age))
        & (df["Altersuntergruppe"] == SOUS_GROUPE_DE_BASE[classe_age(age)])
        & (df["Unfalleinschluss"] == ("MIT_UNF" if avec_accident else "OHN_UNF"))
        & (df["Franchise"].str.endswith(f"_{lettre}_{franchise:04d}"))
    ]
    if CIRCONSCRIPTIONS and not res.empty:
        res = res[[disponible(v, canton, f"PR_REG_{region}", t, no_ofs)
                   for v, t in zip(res["Versicherer"], res["Tarif"])]]
    return res

def _enrichir(res, age, franchise):
    """Colonnes affichées : assureur, modèle, primes mensuelle et annuelle, écart, coût maximal."""
    res = res.copy()
    res["Assureur"] = res["Versicherer"].map(ASSUREURS).fillna(
        "Assureur n°" + res["Versicherer"].astype(str))
    res["Modèle"] = res["Tariftyp"].map(lambda t: MODELES[t]["nom"])
    res["Produit"] = res["Tarifbezeichnung"]
    res["Prime/mois"] = res["Prämie"].round(2)
    res["Prime/an"] = (res["Prämie"] * 12).round(2)
    res["Écart/an"] = (res["Prime/an"] - res["Prime/an"].min()).round(2)
    res["Coût max/an"] = res["Prime/an"] + franchise + QUOTE_PART_MAX[classe_age(age)]
    return res

def comparer(canton, region, age, franchise, avec_accident, top=5):
    """Les `top` offres les moins chères, une seule par assureur."""
    res = _filtrer(canton, region, age, franchise, avec_accident)
    res = res.sort_values("Prämie").drop_duplicates("Versicherer").head(top)
    return _enrichir(res, age, franchise)[COLONNES].reset_index(drop=True)

def toutes_les_offres(canton, region, age, franchise, avec_accident, accepted_tariff_types=None, premium_year=2027,
                      no_ofs=None):
    """Toutes les offres (une ligne par produit de chaque assureur), de la moins chère à la
    plus chère. Contrairement à comparer(), un assureur peut apparaître plusieurs fois : son
    offre médecin de famille n'est pas perdue si son offre télémédecine est moins chère."""
    res = _filtrer(canton, region, age, franchise, avec_accident, accepted_tariff_types, premium_year, no_ofs)
    res = res.sort_values(["Prämie", "Versicherer", "Tarif"], kind="stable")
    res = res.drop_duplicates(["Versicherer", "Tarif"])
    enriched = _enrichir(res, age, franchise)[COLONNES + ["Tariftyp"]].reset_index(drop=True)
    enriched["Franchise"] = franchise
    return enriched

def cout_des_preferences(canton, region, age, franchise, avec_accident, accepted_tariff_types,
                         premium_year=2027, no_ofs=None):
    """Ce que coûte chaque préférence : pour chaque catégorie de modèle NON acceptée, son offre
    la moins chère et l'écart annuel avec l'offre la moins chère des catégories acceptées
    (positif = plus cher, négatif = économie). Même profil, mêmes données OFSP ; tout est
    calculé ici, jamais par le LLM. Liste vide si rien n'est comparable."""
    toutes = toutes_les_offres(canton, region, age, franchise, avec_accident, None, premium_year, no_ofs)
    acceptees = toutes[toutes["Tariftyp"].isin(list(accepted_tariff_types))]
    if acceptees.empty:
        return []
    reference = acceptees.iloc[0]
    lignes = []
    for code in MODELES:
        autres = toutes[toutes["Tariftyp"] == code]
        if code in accepted_tariff_types or autres.empty:
            continue
        o = autres.iloc[0]
        lignes.append({"tariftyp": code, "modele": o["Modèle"], "assureur": o["Assureur"],
                       "produit": o["Produit"], "prime_mois": float(o["Prime/mois"]),
                       "prime_an": float(o["Prime/an"]),
                       "ecart_an": round(float(o["Prime/an"]) - float(reference["Prime/an"]), 2)})
    return sorted(lignes, key=lambda l: l["ecart_an"])


# Les 3 propositions : clé de priorité -> (titre, modèle imposé ou None pour tous les modèles)
PROPOSITIONS = {
    "prix": ("La moins chère parmi les catégories acceptées", None),
    "medecin_famille": ("La moins chère avec médecin de famille / HMO", "PRAXIS"),
    "libre_choix": ("La moins chère avec libre choix du médecin", "BASE"),
}

def contrepartie(code_modele):
    """Contrepartie d'un modèle : première phrase de sa définition."""
    phrase = MODELES[code_modele]["description"].split(". ")[0]
    return phrase[0].upper() + phrase[1:] + "."

def propositions(offres, priorite=None):
    """Les 3 propositions, calculées sur toutes_les_offres(). La priorité de l'utilisateur
    passe en premier ; chaque carte garde le véritable minimum de sa catégorie."""
    if offres.empty:
        return []
    ordre = list(PROPOSITIONS)
    if priorite in PROPOSITIONS:
        ordre.remove(priorite)
        ordre.insert(0, priorite)
    prix_min = offres["Prime/mois"].min()
    choisies = []
    for cle in ordre:
        titre, code = PROPOSITIONS[cle]
        candidates = offres if code is None else offres[offres["Tariftyp"] == code]
        if candidates.empty:
            continue
        o = candidates.iloc[0]
        # Keep the true category minimum even when another card has the same offer.
        choisies.append({"cle": cle, "titre": titre, "assureur": o["Assureur"],
                         "modele": o["Modèle"], "produit": o["Produit"],
                         "prime_mois": o["Prime/mois"], "franchise": int(o["Franchise"]),
                         "ecart_mois": round(o["Prime/mois"] - prix_min, 2),
                         "contrepartie": contrepartie(o["Tariftyp"])})
    return choisies

if __name__ == "__main__":
    print(comparer("VD", 1, 30, 2500, avec_accident=False))
