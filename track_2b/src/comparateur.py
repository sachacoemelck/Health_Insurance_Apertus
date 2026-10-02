from pathlib import Path

import pandas as pd

ASSUREURS = {
    1560: "Agrisano", 1507: "AMB", 32: "Aquilana", 1542: "Assura",
    312: "Atupri", 343: "Avenir", 1322: "Birchmeier", 290: "Concordia",
    8: "CSS", 820: "curaulta", 881: "EGK", 134: "Einsiedler",
    1386: "Galenos", 780: "Glarner", 1562: "Helsana", 376: "KPT",
    360: "Luzerner Hinterland", 1479: "Mutuel",
    1384: "SWICA", 509: "Vivao Sympany", 1509: "Sanitas",  # à vérifier
}

# Chemin absolu vers track_2b/data/primes_CH.csv, quel que soit le dossier de lancement
CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "primes_CH.csv"
df = pd.read_csv(CSV_PATH)

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
