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


def test_lieu_remplace_en_entier_et_noms_bilingues():
    from chatbot import localiser
    u = regles.completer_par_regles({}, "Lausanne", "municipality")
    assert u["municipality"]["value"] == "Lausanne" and u["postal_code"]["status"] == "missing"
    assert localiser(2502, "Bienne")[0] == "Biel/Bienne"
    assert localiser(1205, "Genève 1205")[0] == "Genève"
    assert regles.completer_par_regles({}, "retraité de 70 ans à Sion", None)["municipality"]["value"] == "Sion"


def test_pas_couvert_ne_retire_jamais_les_accidents():
    lu = {"include_accident": {"value": False, "status": "known", "correction": False}}
    u = regles.completer_par_regles(lu, "je ne suis couvert par aucun employeur pour les accidents", "include_accident")
    assert "include_accident" not in u and u["nonoccupational_covered"]["value"] is False


def test_reponse_directe_annee_et_age():
    assert regles.completer_par_regles({}, "2026", "birth_year")["birth_year"]["value"] == 2026
    assert regles.completer_par_regles({}, "35", "age")["age"]["value"] == 35


def test_parent_un_seul_enfant():
    u = regles.completer_par_regles({}, "mon fils a 10 ans, on habite à Sion 1950", None)
    assert u["multiple_people"]["value"] is False and u["age"]["value"] == 10
    assert regles.completer_par_regles({}, "ma fille vient de naître, Lausanne 1005", None)["age"]["value"] == 0
    assert "multiple_people" not in regles.completer_par_regles({}, "j'ai 40 ans et mon fils a 10 ans", None)


def test_heures_chez_un_employeur():
    u = regles.completer_par_regles({}, "je travaille 6h par semaine chez un employeur", None)
    assert u["hours_per_week_one_employer"]["value"] == 6
    assert "hours_per_week_one_employer" not in regles.completer_par_regles(
        {}, "6h par semaine chez un employeur et 5h chez un autre", None)


def test_plusieurs_personnes_seulement_si_le_texte_le_montre():
    lu = {"multiple_people": {"value": True, "status": "known", "correction": False}}
    assert "multiple_people" not in regles.completer_par_regles(dict(lu), "je suis infirmière, 33 ans, Lancy 1212", None)
    assert regles.completer_par_regles(dict(lu), "ma femme et moi, 35 et 33 ans", None)["multiple_people"]["value"]


def test_question_ne_choisit_pas_la_franchise():
    q = regles.completer_par_regles({}, "que coûte la plus basse par rapport à la plus haute franchise ?", "deductible",
                                    question=True)
    assert "deductible" not in q
    q = regles.completer_par_regles({}, "combien pour une franchise de 500 ?", None, question=True)
    assert q["deductible"]["value"] == 500


def test_moitie_de_nom_bilingue():
    assert regles.completer_par_regles({}, "27 Jahre, Biel 2502", None)["postal_code"]["value"] == 2502


if __name__ == "__main__":
    tests = [f for nom, f in sorted(globals().items()) if nom.startswith("test_")]
    for test in tests:
        test()
    print(f"{len(tests)} tests réussis")
