"""Évaluation de l'extraction d'Apertus sur data/eval_extraction.csv.

Chaque phrase passe dans les deux extractions du projet :
- profil LAMal (PROMPT_EXTRACTION de chatbot.py) : age, npa, franchise, travaille_8h, plusieurs_personnes
- besoins complémentaires (PROMPT_BESOINS de complementaires.py) : categories

Deux scores :
- extraction : réponse brute du LLM. Les nombres doivent être recopiés fidèlement (750, 150, 9999).
- final : ce que Python garde sans poser de question, après ses contrôles. Les champs de la
  colonne vide_apres_controles doivent alors être vides (le bot les redemande).
Une case attendue vide n'est réussie que si rien n'a été inventé.

Usage :
  python src/evaluation.py                          # LLM_NAME, 3 passages
  python src/evaluation.py --modele apertus-v1.5-70b --passages 1 --sortie eval_resultats_70b.csv
  python src/evaluation.py --depuis ancien.csv --controles anciens   # re-note sans appeler le LLM
"""
import argparse
import sys
import time

import pandas as pd
from openai import OpenAI

from chatbot import (FRANCHISES, PROMPT_EXTRACTION, classe_age, demander_llm, entier,
                     extraire_json, lire_config, nettoyer_profil)
from comparateur import DATA_DIR, regions
from complementaires import CATEGORIES, PROMPT_BESOINS, filtrer_categories

CHAMPS = ["age", "npa", "franchise", "travaille_8h", "plusieurs_personnes", "categories"]


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


def attendus(ligne, final):
    """Valeurs attendues normalisées (None = case vide)."""
    def lire(champ, conv):
        return conv(ligne[champ]) if pd.notna(ligne[champ]) else None
    valeurs = {"age": lire("age", entier), "npa": lire("npa", entier),
               "franchise": lire("franchise", entier),
               "travaille_8h": lire("travaille_8h", booleen),
               "plusieurs_personnes": lire("plusieurs_personnes", booleen) is True,
               "categories": lire("categories", categories) or frozenset()}
    if final and pd.notna(ligne["vide_apres_controles"]):
        valeurs[ligne["vide_apres_controles"]] = None
    return valeurs


def bruts_normalises(profil, besoins):
    """Réponse brute du LLM, seulement normalisée (\"30\" -> 30, \"true\" -> True)."""
    return {"age": entier(profil.get("age")), "npa": entier(profil.get("npa")),
            "franchise": entier(profil.get("franchise")),
            "travaille_8h": booleen(profil.get("travaille_8h")),
            "plusieurs_personnes": booleen(profil.get("plusieurs_personnes")) is True,
            "categories": categories(besoins.get("categories"))}


def controles_actuels(profil, besoins, phrase):
    """Ce que le projet garde aujourd'hui sans poser de question."""
    profil = {**profil, "travaille_8h": booleen(profil.get("travaille_8h")),
              "plusieurs_personnes": booleen(profil.get("plusieurs_personnes"))}
    p = nettoyer_profil(profil, phrase)
    return {"age": p["age"], "npa": p["npa"], "franchise": p["franchise"],
            "travaille_8h": p["travaille_8h"], "plusieurs_personnes": p["plusieurs_personnes"],
            "categories": frozenset(filtrer_categories(besoins.get("categories"), phrase))}


def controles_anciens(profil, besoins, phrase):
    """Référence « avant » : seulement le refus des valeurs invalides, sans aucune correction."""
    b = bruts_normalises(profil, besoins)
    age = b["age"] if b["age"] in range(0, 121) else None
    valides = FRANCHISES[classe_age(age)] if age is not None else set().union(*FRANCHISES.values())
    return {**b, "age": age,
            "npa": b["npa"] if b["npa"] in set(regions["npa"]) else None,
            "franchise": b["franchise"] if b["franchise"] in valides else None,
            "categories": frozenset(c for c in b["categories"] if c in CATEGORIES)}


def texte(valeur):
    if isinstance(valeur, frozenset):
        return ";".join(sorted(valeur)) or "(vide)"
    return "(vide)" if valeur is None else str(valeur).lower()


def taux(serie):
    return f"{100 * serie.mean():.0f}% ({int(serie.sum())}/{len(serie)})"


def reponses_llm(args, tests):
    """Réponses brutes : appels au LLM, ou relecture d'un fichier de résultats (--depuis)."""
    if args.depuis:
        anciennes = pd.read_csv(args.depuis, dtype=str)
        return [(int(r["passage"]), r["id"], r["reponse_brute_profil"], r["reponse_brute_categories"])
                for _, r in anciennes.iterrows()], "(relecture)"
    config = lire_config()
    client = OpenAI(base_url=config["LLM_BASE_URL"], api_key=config["LLM_API_KEY"])
    modele = args.modele or config["LLM_NAME"]

    def appeler(prompt, phrase):
        try:
            return demander_llm(client, modele, prompt, phrase)
        except Exception as erreur:  # une erreur réseau ne doit pas arrêter l'évaluation
            return f"ERREUR : {erreur}"

    reponses, debut = [], time.time()
    for passage in range(1, args.passages + 1):
        for _, ligne in tests.iterrows():
            reponses.append((passage, ligne["id"], appeler(PROMPT_EXTRACTION, ligne["phrase"]),
                             appeler(PROMPT_BESOINS, ligne["phrase"])))
            print(f"\r  passage {passage}/{args.passages}, phrase {ligne['id']}/{len(tests)}",
                  end="", file=sys.stderr)
    print(f"\r  terminé en {time.time() - debut:.0f} s{' ' * 20}", file=sys.stderr)
    return reponses, modele


def afficher_score(nom, comp, nb_passages, details):
    print(f"\n##### Score {nom} : {taux(comp['ok'])}")
    if nb_passages > 1:
        print("    par passage : " + " | ".join(
            f"{p}: {100 * g['ok'].mean():.0f}%" for p, g in comp.groupby("passage")))
    for champ in CHAMPS:
        print(f"    {champ:<20} {taux(comp.loc[comp['champ'] == champ, 'ok'])}")
    if not details:
        return
    print("\n  Par type de test :")
    par_type = comp.groupby("type_test", sort=False)["ok"].agg(["mean", "sum", "count"])
    for type_test, r in par_type.sort_values("mean").iterrows():
        print(f"    {type_test:<24} {100 * r['mean']:.0f}% ({int(r['sum'])}/{int(r['count'])})")
    print("\n  Erreurs (attendu | obtenu à chaque passage) :")
    for (id_, champ), groupe in comp[~comp["ok"]].groupby(["id", "champ"], sort=False):
        toutes = comp[(comp["id"] == id_) & (comp["champ"] == champ)]
        print(f"    [{id_}] {groupe['phrase'].iloc[0]}\n        {champ} : attendu "
              f"{groupe['attendu'].iloc[0]} | obtenu {' / '.join(toutes['obtenu'])}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--modele", help="modèle d'extraction (défaut : LLM_NAME)")
    parser.add_argument("--passages", type=int, default=3)
    parser.add_argument("--sortie", default="eval_resultats.csv", help="fichier dans data/")
    parser.add_argument("--depuis", help="re-noter un fichier de résultats existant, sans LLM")
    parser.add_argument("--controles", choices=["actuels", "anciens"], default="actuels")
    parser.add_argument("--court", action="store_true", help="scores seulement, sans le détail")
    args = parser.parse_args()

    tests = pd.read_csv(DATA_DIR / "eval_extraction.csv", dtype=str).set_index("id", drop=False)
    reponses, modele = reponses_llm(args, tests)
    controler = controles_actuels if args.controles == "actuels" else controles_anciens
    nb_passages = len({r[0] for r in reponses})
    print(f"Modèle : {modele} | {len(tests)} phrases x {nb_passages} passage(s) | "
          f"contrôles Python : {args.controles}")

    lignes, comp = [], []
    for passage, id_, brut_profil, brut_besoins in reponses:
        ligne = tests.loc[id_]
        profil, besoins = extraire_json(brut_profil), extraire_json(brut_besoins)
        obtenu = {"extraction": bruts_normalises(profil, besoins),
                  "final": controler(profil, besoins, ligne["phrase"])}
        res = {"passage": passage, "id": id_, "type_test": ligne["type_test"],
               "phrase": ligne["phrase"], "reponse_brute_profil": brut_profil,
               "reponse_brute_categories": brut_besoins}
        for score in ("extraction", "final"):
            attendu = attendus(ligne, final=score == "final")
            for champ in CHAMPS:
                ok = obtenu[score][champ] == attendu[champ]
                res[f"{champ}_{score}"] = texte(obtenu[score][champ])
                comp.append({"score": score, "passage": passage, "id": id_, "champ": champ,
                             "type_test": ligne["type_test"], "phrase": ligne["phrase"], "ok": ok,
                             "attendu": texte(attendu[champ]), "obtenu": texte(obtenu[score][champ])})
        lignes.append(res)
    comp = pd.DataFrame(comp)

    if not args.depuis:
        pd.DataFrame(lignes).to_csv(DATA_DIR / args.sortie, index=False)
        print(f"Réponses brutes sauvegardées dans data/{args.sortie}")
    if nb_passages > 1:
        ext = comp[comp["score"] == "extraction"]
        stable = ext.groupby(["id", "champ"])["obtenu"].nunique() == 1
        print(f"Stabilité de l'extraction (même réponse à chaque passage) : {taux(stable)}")
    for score in ("extraction", "final"):
        afficher_score(score, comp[comp["score"] == score], nb_passages, not args.court)


if __name__ == "__main__":
    main()
