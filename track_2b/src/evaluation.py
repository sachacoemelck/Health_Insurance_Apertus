"""Évaluation de l'extraction d'Apertus sur data/eval_extraction.csv.

Chaque phrase passe dans les deux extractions actuelles (sans les modifier) :
- profil LAMal (PROMPT_EXTRACTION de chatbot.py) : age, npa, franchise, travaille_8h
- besoins complémentaires (PROMPT_BESOINS de complementaires.py) : categories
On compare la réponse brute du LLM (avant toute validation Python) au résultat attendu.
Une case attendue vide n'est réussie que si le LLM n'a rien inventé (valeur nulle).
"""
import sys
import time

import pandas as pd
from openai import OpenAI

from chatbot import PROMPT_EXTRACTION, demander_llm, entier, extraire_json, lire_config
from comparateur import DATA_DIR
from complementaires import PROMPT_BESOINS

NB_PASSAGES = 3
CHAMPS = ["age", "npa", "franchise", "travaille_8h", "categories"]


def booleen(valeur):
    if isinstance(valeur, bool):
        return valeur
    if str(valeur).strip().lower() in ("true", "vrai", "oui"):
        return True
    if str(valeur).strip().lower() in ("false", "faux", "non"):
        return False
    return None


def categories(valeur):
    if isinstance(valeur, str):
        valeur = valeur.split(";")
    if not isinstance(valeur, list):
        return frozenset()
    return frozenset(str(c).strip() for c in valeur if str(c).strip())


def attendus(ligne):
    """Valeurs attendues normalisées (None = case vide)."""
    return {
        "age": entier(ligne["age"]) if pd.notna(ligne["age"]) else None,
        "npa": entier(ligne["npa"]) if pd.notna(ligne["npa"]) else None,
        "franchise": entier(ligne["franchise"]) if pd.notna(ligne["franchise"]) else None,
        "travaille_8h": booleen(ligne["travaille_8h"]) if pd.notna(ligne["travaille_8h"]) else None,
        "categories": categories(ligne["categories"]) if pd.notna(ligne["categories"]) else frozenset(),
    }


def obtenus(profil, besoins):
    """Valeurs extraites par le LLM, normalisées de la même façon."""
    return {
        "age": entier(profil.get("age")),
        "npa": entier(profil.get("npa")),
        "franchise": entier(profil.get("franchise")),
        "travaille_8h": booleen(profil.get("travaille_8h")),
        "categories": categories(besoins.get("categories")),
    }


def appeler(client, modele, prompt, phrase):
    try:
        return demander_llm(client, modele, prompt, phrase)
    except Exception as erreur:  # une erreur réseau ne doit pas arrêter toute l'évaluation
        return f"ERREUR : {erreur}"


def texte(valeur):
    if isinstance(valeur, frozenset):
        return ";".join(sorted(valeur)) or "(vide)"
    return "(vide)" if valeur is None else str(valeur).lower()


def taux(serie):
    return f"{100 * serie.mean():.0f}% ({int(serie.sum())}/{len(serie)})"


def main():
    config = lire_config()
    client = OpenAI(base_url=config["LLM_BASE_URL"], api_key=config["LLM_API_KEY"])
    modele = config["LLM_NAME"]
    tests = pd.read_csv(DATA_DIR / "eval_extraction.csv", dtype=str)
    print(f"Modèle d'extraction : {modele} | {len(tests)} phrases x {NB_PASSAGES} passages\n")

    resultats, comparaisons = [], []
    debut = time.time()
    for passage in range(1, NB_PASSAGES + 1):
        for _, ligne in tests.iterrows():
            brut_profil = appeler(client, modele, PROMPT_EXTRACTION, ligne["phrase"])
            brut_besoins = appeler(client, modele, PROMPT_BESOINS, ligne["phrase"])
            attendu = attendus(ligne)
            obtenu = obtenus(extraire_json(brut_profil), extraire_json(brut_besoins))
            ligne_res = {"passage": passage, "id": ligne["id"], "type_test": ligne["type_test"],
                         "phrase": ligne["phrase"], "reponse_brute_profil": brut_profil,
                         "reponse_brute_categories": brut_besoins}
            for champ in CHAMPS:
                ok = obtenu[champ] == attendu[champ]
                ligne_res[f"{champ}_obtenu"] = texte(obtenu[champ])
                ligne_res[f"{champ}_ok"] = ok
                comparaisons.append({"passage": passage, "id": ligne["id"], "type_test": ligne["type_test"],
                                     "phrase": ligne["phrase"], "champ": champ, "ok": ok,
                                     "attendu": texte(attendu[champ]), "obtenu": texte(obtenu[champ])})
            resultats.append(ligne_res)
            print(f"\r  passage {passage}/{NB_PASSAGES}, phrase {ligne['id']}/{len(tests)}",
                  end="", file=sys.stderr)
    print(f"\r  terminé en {time.time() - debut:.0f} s{' ' * 20}\n", file=sys.stderr)

    pd.DataFrame(resultats).to_csv(DATA_DIR / "eval_resultats.csv", index=False)
    comp = pd.DataFrame(comparaisons)

    print(f"=== Taux de réussite global : {taux(comp['ok'])}")
    print("    par passage : " + " | ".join(
        f"{p}: {100 * g['ok'].mean():.0f}%" for p, g in comp.groupby("passage")))

    print("\n=== Par champ")
    for champ in CHAMPS:
        print(f"  {champ:<13} {taux(comp.loc[comp['champ'] == champ, 'ok'])}")

    # Stabilité : même valeur obtenue aux 3 passages, pour une phrase et un champ donnés
    stable = comp.groupby(["id", "champ"])["obtenu"].nunique() == 1
    print(f"\n=== Stabilité (même réponse aux {NB_PASSAGES} passages) : {taux(stable)}")
    instables = stable[~stable].reset_index()[["id", "champ"]]
    for _, r in instables.iterrows():
        valeurs = comp[(comp["id"] == r["id"]) & (comp["champ"] == r["champ"])]["obtenu"].tolist()
        print(f"  phrase {r['id']}, {r['champ']} : {' / '.join(valeurs)}")

    print("\n=== Par type de test (tous champs confondus)")
    par_type = comp.groupby("type_test", sort=False)["ok"].agg(["mean", "sum", "count"])
    for type_test, r in par_type.sort_values("mean").iterrows():
        print(f"  {type_test:<24} {100 * r['mean']:.0f}% ({int(r['sum'])}/{int(r['count'])})")

    print("\n=== Erreurs (phrase, champ, attendu, obtenu à chaque passage)")
    erreurs = comp[~comp["ok"]]
    for (id_, champ), groupe in erreurs.groupby(["id", "champ"], sort=False):
        toutes = comp[(comp["id"] == id_) & (comp["champ"] == champ)]
        print(f"\n  [{id_}] {groupe['phrase'].iloc[0]}")
        print(f"      {champ} : attendu {groupe['attendu'].iloc[0]} | obtenu "
              f"{' / '.join(toutes['obtenu'])} ({len(groupe)}/{NB_PASSAGES} erreurs)")
    print(f"\nRéponses brutes sauvegardées dans data/eval_resultats.csv")


if __name__ == "__main__":
    main()
