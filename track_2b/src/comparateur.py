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
    return res[["Assureur", "Tariftyp", "Tarifbezeichnung", "Prämie"]]

if __name__ == "__main__":
    print(comparer("VD", 1, 30, 2500, avec_accident=False))
