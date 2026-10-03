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
             "description": "libre choix du médecin"},
    "PRAXIS": {"nom": "Médecin de famille / HMO",
               "description": "médecin de famille ou HMO, à consulter en premier"},
    "TEL_DIG": {"nom": "Télémédecine",
                "description": "appel obligatoire à un centre de télémédecine "
                               "avant toute consultation"},
    "FLEX": {"nom": "Modèle alternatif",
             "description": "modèle alternatif propre à chaque assureur, "
                            "conditions à vérifier chez l'assureur"},
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

def comparer(canton, region, age, franchise, avec_accident, top=5):
    lettre = {"AKA_01_KIN": "K", "AKA_02_JUG": "J", "AKA_03_ERW": "E"}[classe_age(age)]
    res = df[
        (df["Kanton"] == canton)
        & (df["Region"] == f"PR_REG_{region}")
        & (df["Altersklasse"] == classe_age(age))
        & (df["Unfalleinschluss"] == ("MIT_UNF" if avec_accident else "OHN_UNF"))
        & (df["Franchise"].str.endswith(f"_{lettre}_{franchise:04d}"))
    ]
    res = res.sort_values("Prämie").drop_duplicates("Versicherer")
    res = res.head(top).copy()
    res["Assureur"] = res["Versicherer"].map(ASSUREURS).fillna(
        "Assureur n°" + res["Versicherer"].astype(str))
    res["Modèle"] = res["Tariftyp"].map(lambda t: MODELES[t]["nom"])
    res["Produit"] = res["Tarifbezeichnung"]
    res["Prime/mois"] = res["Prämie"].round(2)
    res["Prime/an"] = (res["Prämie"] * 12).round(2)
    res["Écart/an"] = (res["Prime/an"] - res["Prime/an"].min()).round(2)
    res["Coût max/an"] = res["Prime/an"] + franchise + QUOTE_PART_MAX[classe_age(age)]
    return res[["Assureur", "Modèle", "Produit", "Prime/mois", "Prime/an",
                "Écart/an", "Coût max/an"]].reset_index(drop=True)

if __name__ == "__main__":
    print(comparer("VD", 1, 30, 2500, avec_accident=False))
