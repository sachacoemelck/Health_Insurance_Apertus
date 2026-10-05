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
             "description": "aucune contrainte, accès direct à n'importe quel médecin "
                            "ou spécialiste, prime la plus élevée"},
    "PRAXIS": {"nom": "Médecin de famille / HMO",
               "description": "on passe toujours d'abord par son médecin de famille, qui "
                              "oriente vers les spécialistes. Suivi coordonné par quelqu'un "
                              "qui connaît ton historique, prime réduite. Moins adapté si on "
                              "veut un accès rapide : il faut attendre un rendez-vous selon "
                              "ses disponibilités. Pas de passage obligatoire en cas d'urgence"},
    "TEL_DIG": {"nom": "Télémédecine",
                "description": "appel obligatoire à un centre de conseil avant toute "
                               "consultation, sauf en cas d'urgence. Prime réduite. "
                               "Contraignant si on veut voir directement son médecin"},
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

def _filtrer(canton, region, age, franchise, avec_accident):
    """Lignes du CSV qui correspondent au profil."""
    lettre = {"AKA_01_KIN": "K", "AKA_02_JUG": "J", "AKA_03_ERW": "E"}[classe_age(age)]
    return df[
        (df["Kanton"] == canton)
        & (df["Region"] == f"PR_REG_{region}")
        & (df["Altersklasse"] == classe_age(age))
        & (df["Unfalleinschluss"] == ("MIT_UNF" if avec_accident else "OHN_UNF"))
        & (df["Franchise"].str.endswith(f"_{lettre}_{franchise:04d}"))
    ]

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

def toutes_les_offres(canton, region, age, franchise, avec_accident):
    """Toutes les offres (une ligne par produit de chaque assureur), de la moins chère à la
    plus chère. Contrairement à comparer(), un assureur peut apparaître plusieurs fois : son
    offre médecin de famille n'est pas perdue si son offre télémédecine est moins chère."""
    res = _filtrer(canton, region, age, franchise, avec_accident)
    res = res.sort_values(["Prämie", "Versicherer", "Tarif"], kind="stable")
    res = res.drop_duplicates(["Versicherer", "Tarif"])
    return _enrichir(res, age, franchise)[COLONNES + ["Tariftyp"]].reset_index(drop=True)

# Les 3 propositions : clé de priorité -> (titre, modèle imposé ou None pour tous les modèles)
PROPOSITIONS = {
    "prix": ("La moins chère, tous modèles confondus", None),
    "medecin_famille": ("La moins chère avec médecin de famille / HMO", "PRAXIS"),
    "libre_choix": ("La moins chère avec libre choix du médecin", "BASE"),
}

def contrepartie(code_modele):
    """Contrepartie d'un modèle : première phrase de sa définition."""
    phrase = MODELES[code_modele]["description"].split(". ")[0]
    return phrase[0].upper() + phrase[1:] + "."

def propositions(offres, priorite=None):
    """Les 3 propositions, calculées sur toutes_les_offres(). La priorité de l'utilisateur
    passe en premier ; si deux propositions tombent sur la même offre, on prend la suivante."""
    if offres.empty:
        return []
    ordre = list(PROPOSITIONS)
    if priorite in PROPOSITIONS:
        ordre.remove(priorite)
        ordre.insert(0, priorite)
    prix_min = offres["Prime/mois"].min()
    deja_prises, choisies = set(), []
    for cle in ordre:
        titre, code = PROPOSITIONS[cle]
        candidates = offres if code is None else offres[offres["Tariftyp"] == code]
        for _, o in candidates.iterrows():
            if (o["Assureur"], o["Produit"]) not in deja_prises:
                deja_prises.add((o["Assureur"], o["Produit"]))
                choisies.append({"cle": cle, "titre": titre, "assureur": o["Assureur"],
                                 "modele": o["Modèle"], "produit": o["Produit"],
                                 "prime_mois": o["Prime/mois"],
                                 "ecart_mois": round(o["Prime/mois"] - prix_min, 2),
                                 "contrepartie": contrepartie(o["Tariftyp"])})
                break
    return choisies

if __name__ == "__main__":
    print(comparer("VD", 1, 30, 2500, avec_accident=False))
