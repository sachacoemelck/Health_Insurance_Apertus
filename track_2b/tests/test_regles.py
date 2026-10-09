"""Tests des garde-fous déterministes (aucun appel à Apertus). Lancer : python tests/test_regles.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import regles  # noqa: E402
import soins  # noqa: E402


def valeurs(updates):
    return {k: v["value"] for k, v in updates.items()}


def test_profil_complet_lu_sans_apertus():
    u = valeurs(regles.completer_par_regles({}, "J'ai 30 ans, j'habite à Lausanne (1003), je veux une franchise de "
                                                "2500, je travaille 42 heures par semaine chez le même employeur"))
    assert u == {"postal_code": 1003, "deductible": 2500, "hours_per_week_one_employer": 42,
                 "employed": True, "age": 30}


def test_franchise_en_mots_l_emporte_sur_apertus():
    u = regles.completer_par_regles({"deductible": {"value": 300, "status": "known", "correction": False}},
                                    "La franchise la plus haute.", "deductible")
    assert u["deductible"]["value"] == "highest"
    assert valeurs(regles.completer_par_regles({}, "je prends la franchise max"))["deductible"] == "highest"


def test_lieu_corrige_quand_on_repond_a_la_question():
    u = regles.completer_par_regles({"municipality": {"value": "Lausanne, code postal 1003", "status": "known",
                                                      "correction": False}}, "Lausanne, code postal 1003", "municipality")
    assert u["municipality"]["value"] == "Lausanne" and u["municipality"]["correction"]
    assert u["postal_code"]["value"] == 1003 and u["postal_code"]["correction"]


def test_pas_de_deduction_hasardeuse():
    assert "age" not in regles.completer_par_regles({}, "Ma femme et moi, 35 et 37 ans, à Lausanne 1003")
    assert "hours_per_week_one_employer" not in regles.completer_par_regles({}, "je travaille 5 heures par semaine")
    assert regles.completer_par_regles({}, "je bois une Bière") == {}


def test_une_annee_n_est_pas_un_code_postal():
    assert "postal_code" not in regles.completer_par_regles({}, "Je suis retraité depuis 2015, j'habite à Sierre.")
    assert valeurs(regles.completer_par_regles({}, "j'habite à Nyon 1260"))["postal_code"] == 1260


def test_commune_apres_j_habite():
    # « Premier » est aussi une commune vaudoise
    u = regles.completer_par_regles({}, "J'ai 48 ans, j'habite à Sion. La pharmacie en premier, pourquoi pas.")
    assert valeurs(u)["municipality"] == "Sion"


def test_reponse_pour_qui_designe_une_personne():
    u = regles.completer_par_regles({}, "Seulement ma fille, 8 ans", "multiple_people")
    assert u["multiple_people"]["value"] is False and u["age"]["value"] == 8


def test_peu_importe_le_modele():
    assert soins.parle_de_soins("je m'en fiche du modèle tant que c'est pas cher")


if __name__ == "__main__":
    tests = [f for nom, f in sorted(globals().items()) if nom.startswith("test_")]
    for test in tests:
        test()
    print(f"{len(tests)} tests réussis")
