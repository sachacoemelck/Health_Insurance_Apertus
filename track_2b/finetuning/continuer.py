# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "torch",
#   "transformers>=4.56",
#   "datasets",
#   "peft",
#   "trl",
#   "bitsandbytes",
#   "accelerate",
#   "unsloth",
# ]
# ///
"""Évaluer puis continuer l'entraînement de l'adaptateur v1 (expérience à part, un seul job).

1. Test du modèle de base (adaptateur désactivé) et de la v1 sur les jeux d'évaluation
   (30 phrases écrites à la main + 300 phrases synthétiques 2027, jamais vues à l'entraînement).
2. Suite de l'entraînement de la v1 sur les données v2 (graine 4242) + les données v1.
   Arrêt automatique avant la limite de temps pour garder de quoi tester et sauvegarder.
3. Sauvegarde de la v2 (dépôt privé), puis même test.
Chaque résultat est envoyé dans le dataset privé dès qu'il est prêt (resultats/).
Le jeton Hugging Face vient du secret HF_TOKEN du job, jamais d'un fichier.
"""
import argparse
import csv
import io
import json
import math
import os
import re
import time

DEBUT = time.time()
DATASET = "coemelcksacha/apertus-extraction-profil"
ADAPTATEUR_V1 = "coemelcksacha/apertus-8b-extraction-profil"
ADAPTATEUR_V2 = "coemelcksacha/apertus-8b-extraction-profil-v2"
JEUX = {"main_30": "eval/eval_extraction.csv", "synth_2027_300": "eval/eval_synthetique_2027.csv"}
CHAMPS = ["age", "npa", "franchise", "travaille_8h", "plusieurs_personnes"]


def minutes():
    return f"{(time.time() - DEBUT) / 60:.0f} min"


# ---------- Lecture des réponses et des valeurs attendues ----------------------------------------
def entier(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(str(v).strip().replace("'", ""))
    except ValueError:
        return None
    return int(f) if f == int(f) else None


def booleen(v):
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower() if v is not None else ""
    return True if s == "true" else False if s == "false" else None


def attendus(ligne):
    return {"age": entier(ligne["age"]) if ligne["age"] else None,
            "npa": entier(ligne["npa"]) if ligne["npa"] else None,
            "franchise": entier(ligne["franchise"]) if ligne["franchise"] else None,
            "travaille_8h": booleen(ligne["travaille_8h"]),
            "plusieurs_personnes": booleen(ligne["plusieurs_personnes"]) is True}


def lire_reponse(texte):
    """JSON de la réponse -> valeurs normalisées ; None si illisible."""
    trouve = re.search(r"\{.*?\}", texte, re.DOTALL)
    if not trouve:
        return None
    try:
        d = json.loads(trouve.group())
    except json.JSONDecodeError:
        return None
    if not isinstance(d, dict):
        return None
    return {"age": entier(d.get("age")), "npa": entier(d.get("npa")), "franchise": entier(d.get("franchise")),
            "travaille_8h": booleen(d.get("travaille_8h")),
            "plusieurs_personnes": booleen(d.get("plusieurs_personnes")) is True}


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    marge = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - marge), min(1.0, centre + marge)


def resumer(lignes):
    """Score par champ et « tout juste », avec intervalle de confiance à 95 %."""
    n = len(lignes)
    res = {"n": n, "json_lisible": sum(l["lisible"] for l in lignes)}
    for champ in CHAMPS + ["tout_juste"]:
        k = sum(l[f"ok_{champ}"] for l in lignes)
        bas, haut = wilson(k, n)
        res[champ] = {"ok": k, "pct": round(100 * k / n, 1), "ic95": [round(100 * bas, 1), round(100 * haut, 1)]}
    return res


def noter(phrase, attendu, texte):
    obtenu = lire_reponse(texte)
    ligne = {"phrase": phrase, "reponse": texte, "lisible": obtenu is not None}
    for champ in CHAMPS:
        ligne[f"ok_{champ}"] = obtenu is not None and obtenu[champ] == attendu[champ]
    ligne["ok_tout_juste"] = all(ligne[f"ok_{c}"] for c in CHAMPS)
    return ligne


# ---------- Hugging Face ----------------------------------------------------------------------
def charger_jeux():
    from huggingface_hub import hf_hub_download
    jeux = {}
    for nom, chemin in JEUX.items():
        fichier = hf_hub_download(DATASET, chemin, repo_type="dataset")
        with open(fichier, encoding="utf-8", newline="") as f:
            jeux[nom] = [(l["phrase"], attendus(l)) for l in csv.DictReader(f)]
    return jeux


def envoyer(nom, contenu):
    """Envoie un fichier de résultats dans le dataset privé (ne fait jamais planter le job)."""
    try:
        from huggingface_hub import upload_file
        upload_file(path_or_fileobj=io.BytesIO(contenu.encode("utf-8")), path_in_repo=f"resultats/{nom}",
                    repo_id=DATASET, repo_type="dataset", commit_message=f"Résultats : {nom}")
        print(f"[envoi] resultats/{nom}")
    except Exception as erreur:
        print(f"[envoi] échec pour {nom} : {erreur}")


def evaluer(modele, tok, consigne, jeux, etiquette):
    import torch
    from unsloth import FastLanguageModel
    FastLanguageModel.for_inference(modele)
    resultats, details = {}, []
    for nom, exemples in jeux.items():
        lignes = []
        for phrase, attendu in exemples:
            messages = [{"role": "system", "content": consigne}, {"role": "user", "content": phrase}]
            entree = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(modele.device)
            with torch.no_grad():
                sortie = modele.generate(input_ids=entree, max_new_tokens=90, do_sample=False)
            texte = tok.decode(sortie[0][entree.shape[1]:], skip_special_tokens=True).strip()
            lignes.append(noter(phrase, attendu, texte))
        resultats[nom] = resumer(lignes)
        details += [{"jeu": nom, **l} for l in lignes]
        print(f"[test {etiquette}] {nom} : tout juste {resultats[nom]['tout_juste']} | {minutes()}")
    envoyer(f"{etiquette}.json", json.dumps({"modele": etiquette, "scores": resultats, "details": details},
                                            ensure_ascii=False, indent=1))
    return resultats, details


def comparer(details_a, details_b, a, b):
    """Comparaison appariée sur les mêmes phrases : combien passent de faux à juste et inversement."""
    gagnes = sum(1 for x, y in zip(details_a, details_b) if not x["ok_tout_juste"] and y["ok_tout_juste"])
    perdus = sum(1 for x, y in zip(details_a, details_b) if x["ok_tout_juste"] and not y["ok_tout_juste"])
    print(f"[comparaison] {a} -> {b} : {gagnes} phrases corrigées, {perdus} phrases cassées "
          f"(sur {len(details_a)})")
    return {"de": a, "vers": b, "corrigees": gagnes, "cassees": perdus, "n": len(details_a)}


# ---------- Entraînement ----------------------------------------------------------------------
def charger_donnees_entrainement():
    from datasets import concatenate_datasets, load_dataset
    v1 = load_dataset("json", data_files=f"hf://datasets/{DATASET}/entrainement.jsonl.gz")["train"]
    v2 = load_dataset("json", data_files=f"hf://datasets/{DATASET}/v2/entrainement.jsonl.gz")["train"]
    donnees = concatenate_datasets([v1, v2]).shuffle(seed=1)
    return donnees.map(lambda e: {"prompt": e["messages"][:2], "completion": e["messages"][2:]},
                       remove_columns=["messages", "tache"])


def continuer_entrainement(modele, tok, limite_min):
    from transformers import TrainerCallback
    from trl import SFTConfig, SFTTrainer
    from unsloth import FastLanguageModel

    class Chrono(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            if time.time() - DEBUT > limite_min * 60:
                print(f"[chrono] limite atteinte ({minutes()}), arrêt à l'étape {state.global_step}")
                control.should_training_stop = True

    FastLanguageModel.for_training(modele)
    donnees = charger_donnees_entrainement()
    print(f"[données] {len(donnees)} exemples (v1 + v2)")
    config = SFTConfig(
        output_dir="sortie", num_train_epochs=1, per_device_train_batch_size=4, gradient_accumulation_steps=4,
        learning_rate=1e-4, lr_scheduler_type="cosine", warmup_ratio=0.03, logging_steps=20,
        save_strategy="no", eval_strategy="no", bf16=True, max_length=1024, report_to="none", seed=1,
        completion_only_loss=True,
    )
    entraineur = SFTTrainer(model=modele, args=config, train_dataset=donnees, processing_class=tok,
                            callbacks=[Chrono()])
    resultat = entraineur.train()
    print(f"[entraînement] perte {resultat.training_loss:.4f} | {entraineur.state.global_step} étapes | {minutes()}")
    return entraineur.model, entraineur.state.global_step, resultat.training_loss


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limite-entrainement", type=float, default=170,
                        help="minutes depuis le début du job après lesquelles l'entraînement s'arrête")
    args = parser.parse_args()

    from datasets import load_dataset
    from unsloth import FastLanguageModel
    jeux = charger_jeux()
    consigne = next(e["messages"][0]["content"] for e in
                    load_dataset("json", data_files=f"hf://datasets/{DATASET}/validation.jsonl.gz")["train"]
                    if e["tache"] == "profil")
    modele, tok = FastLanguageModel.from_pretrained(ADAPTATEUR_V1, max_seq_length=1024, load_in_4bit=True)
    print(f"[modèle] base + adaptateur v1 chargés | {minutes()}")

    bilan = {}
    with modele.disable_adapter():
        bilan["base"], det_base = evaluer(modele, tok, consigne, jeux, "base")
    bilan["v1"], det_v1 = evaluer(modele, tok, consigne, jeux, "v1")
    bilan["base_vers_v1"] = comparer(det_base, det_v1, "base", "v1")
    envoyer("bilan.json", json.dumps(bilan, ensure_ascii=False, indent=1))

    try:
        modele, etapes, perte = continuer_entrainement(modele, tok, args.limite_entrainement)
        from huggingface_hub import create_repo
        create_repo(ADAPTATEUR_V2, private=True, exist_ok=True)
        modele.push_to_hub(ADAPTATEUR_V2, private=True)
        tok.push_to_hub(ADAPTATEUR_V2, private=True)
        print(f"[sauvegarde] v2 dans le dépôt PRIVÉ {ADAPTATEUR_V2} | {minutes()}")
        bilan["entrainement_v2"] = {"etapes": etapes, "perte": perte}
        bilan["v2"], det_v2 = evaluer(modele, tok, consigne, jeux, "v2")
        bilan["v1_vers_v2"] = comparer(det_v1, det_v2, "v1", "v2")
    except Exception as erreur:
        print(f"[erreur] suite de l'entraînement : {type(erreur).__name__}: {str(erreur)[:500]}")
        bilan["erreur_v2"] = str(erreur)[:500]
    envoyer("bilan.json", json.dumps(bilan, ensure_ascii=False, indent=1))
    print("[bilan] " + json.dumps({k: (v.get("main_30", v) if isinstance(v, dict) else v) for k, v in bilan.items()},
                                  ensure_ascii=False))
    print(f"[fin] {minutes()}")


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()
