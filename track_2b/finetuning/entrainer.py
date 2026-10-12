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
"""QLoRA 4 bits d'Apertus 8B Instruct sur l'extraction de profil (expérience à part).

Lancé sur Hugging Face Jobs avec `hf jobs uv run` (voir finetuning/README.md) :
  - mini-essai : --mini (100 exemples, test sur 5 phrases, rien n'est sauvegardé)
  - entraînement complet : --epochs 2 --depot-sortie coemelcksacha/<nom> (adaptateur privé)
Le jeton Hugging Face est transmis par le job (secret HF_TOKEN), jamais écrit dans un fichier.
On essaie d'abord Unsloth ; s'il ne prend pas en charge Apertus, on passe à TRL + PEFT.
"""
import argparse
import json
import os
import re
import time

DATASET = "coemelcksacha/apertus-extraction-profil"
MODELE = "swiss-ai/Apertus-8B-Instruct-2509"
PHRASES_TEST = [
    "J'ai 30 ans, j'habite à Nyon 1260, franchise 2500, je travaille à plein temps",
    "Mon fils a 8 ans, on habite à 1260, franchise 0",
    "Ich bin 45 Jahre alt, wohne in 3011 Bern, Franchise 2500, arbeite Vollzeit",
    "je vais chez l'ostéo et je porte des lunettes, 27 ans, 1004, franchise 300",
    "Bonjour",
]


def en_prompt_completion(exemple):
    """Format conversationnel prompt / complétion : la perte ne porte que sur la réponse JSON."""
    messages = exemple["messages"]
    return {"prompt": messages[:2], "completion": messages[2:]}


def charger_donnees(nb_exemples=None):
    from datasets import load_dataset
    fichiers = {"train": f"hf://datasets/{DATASET}/entrainement.jsonl.gz",
                "validation": f"hf://datasets/{DATASET}/validation.jsonl.gz"}
    donnees = load_dataset("json", data_files=fichiers)
    if nb_exemples:
        donnees["train"] = donnees["train"].shuffle(seed=0).select(range(nb_exemples))
        donnees["validation"] = donnees["validation"].select(range(min(20, len(donnees["validation"]))))
    return donnees.map(en_prompt_completion, remove_columns=["messages", "tache"])


def charger_modele(max_len):
    """Unsloth d'abord, sinon transformers + bitsandbytes (4 bits NF4) + PEFT."""
    lora = dict(r=16, lora_alpha=32, lora_dropout=0.05,
                target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "up_proj", "down_proj"])
    try:
        from unsloth import FastLanguageModel
        modele, tok = FastLanguageModel.from_pretrained(MODELE, max_seq_length=max_len, load_in_4bit=True)
        modele = FastLanguageModel.get_peft_model(modele, **lora, bias="none")
        return modele, tok, "unsloth", None
    except Exception as erreur:  # architecture non prise en charge, version, etc.
        print(f"[moteur] Unsloth indisponible pour Apertus : {type(erreur).__name__}: {str(erreur)[:300]}")
    import torch
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                               bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    tok = AutoTokenizer.from_pretrained(MODELE)
    modele = AutoModelForCausalLM.from_pretrained(MODELE, quantization_config=quant,
                                                  torch_dtype=torch.bfloat16, device_map="auto")
    return modele, tok, "trl+peft", LoraConfig(**lora, bias="none", task_type="CAUSAL_LM")


def tester(modele, tok, consigne):
    """Génère la réponse pour quelques phrases et vérifie qu'elle est un JSON lisible."""
    import torch
    modele.eval()
    for phrase in PHRASES_TEST:
        messages = [{"role": "system", "content": consigne}, {"role": "user", "content": phrase}]
        entree = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(modele.device)
        with torch.no_grad():
            sortie = modele.generate(entree, max_new_tokens=120, do_sample=False)
        texte = tok.decode(sortie[0][entree.shape[1]:], skip_special_tokens=True).strip()
        trouve = re.search(r"\{.*\}", texte, re.DOTALL)
        try:
            json.loads(trouve.group()) if trouve else None
            lisible = bool(trouve)
        except json.JSONDecodeError:
            lisible = False
        print(f"[test] « {phrase} »\n       -> {texte[:200]}  (JSON lisible : {lisible})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mini", action="store_true", help="100 exemples, test, rien n'est sauvegardé")
    parser.add_argument("--epochs", type=float, default=1)
    parser.add_argument("--depot-sortie", help="dépôt de modèle PRIVÉ pour l'adaptateur (ex. coemelcksacha/...)")
    parser.add_argument("--max-len", type=int, default=1024)
    args = parser.parse_args()
    debut = time.time()

    donnees = charger_donnees(100 if args.mini else None)
    print(f"[données] {len(donnees['train'])} exemples d'entraînement, {len(donnees['validation'])} de validation")
    consigne_profil = donnees["train"][0]["prompt"][0]["content"]

    modele, tok, moteur, config_lora = charger_modele(args.max_len)
    print(f"[moteur] {moteur} | chargé en {time.time() - debut:.0f} s")

    from trl import SFTConfig, SFTTrainer
    config = SFTConfig(
        output_dir="sortie", num_train_epochs=args.epochs, max_steps=25 if args.mini else -1,
        per_device_train_batch_size=4, gradient_accumulation_steps=4, learning_rate=2e-4,
        lr_scheduler_type="cosine", warmup_ratio=0.03, logging_steps=5, eval_strategy="epoch",
        save_strategy="no", bf16=True, max_length=args.max_len, report_to="none", seed=0,
        completion_only_loss=True,
    )
    entraineur = SFTTrainer(model=modele, args=config, train_dataset=donnees["train"],
                            eval_dataset=donnees["validation"], processing_class=tok, peft_config=config_lora)
    resultat = entraineur.train()
    print(f"[entraînement] perte finale {resultat.training_loss:.4f} | {time.time() - debut:.0f} s au total")
    print(f"[évaluation] {entraineur.evaluate()}")

    tester(entraineur.model, tok, consigne_profil)

    if args.depot_sortie and not args.mini:
        from huggingface_hub import create_repo
        create_repo(args.depot_sortie, private=True, exist_ok=True)
        entraineur.model.push_to_hub(args.depot_sortie, private=True)
        tok.push_to_hub(args.depot_sortie, private=True)
        print(f"[sauvegarde] adaptateur envoyé dans le dépôt PRIVÉ {args.depot_sortie}")
    print(f"[fin] durée totale {time.time() - debut:.0f} s")


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()
