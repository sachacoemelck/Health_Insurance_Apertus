"""Tests déterministes des préférences de soins (aucun appel à Apertus).

Lancer depuis track_2b :   python tests/test_soins.py
Les réponses d'Apertus utilisées ici sont des réponses réelles relevées le 6 octobre 2026.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import soins  # noqa: E402


def positions(d):
    return {m: v["stance"] for m, v in d.items()}


def test_reponse_mal_formee_du_70b_est_lue():
    brut = ('{"care": {\n "phone_first": {"stance": "accepted", "condition": "saving", '
            '"evidence": "Appeler d\'abord, d\'accord"},\n "pharmacy_first": {"stance": '
            '"not_mentioned", "condition": null, "evidence": null"}}\n}')
    lu = soins.lire_soins(brut)
    assert positions(lu) == {"phone_first": "conditional"}  # accepté + condition = conditionnel
    assert soins.lire_soins("désolé, je ne peux pas") is None


def test_forme_abregee_du_8b_est_lue():
    assert positions(soins.lire_soins('{"care": {"pharmacy_first": "rejected", "gp_first": "not_mentioned"}}')) \
        == {"pharmacy_first": "rejected"}


def test_mode_invente_est_ecarte():
    phrase = "Pas d'application pour moi, je déteste ça."
    brut = {"free_choice": {"stance": "accepted", "condition": None, "evidence": None},
            "phone_first": {"stance": "rejected", "condition": None, "evidence": None},
            "app_first": {"stance": "rejected", "condition": None, "evidence": "Pas d'application pour moi"}}
    garde = soins.controler_soins(brut, phrase)
    assert positions(garde) == {"app_first": "rejected"}
    assert garde["app_first"]["evidence"] == "Pas d'application pour moi"


def test_citation_reformulee_est_retiree_mais_le_mode_reste():
    garde = soins.controler_soins(
        {"pharmacy_first": {"stance": "rejected", "condition": None, "evidence": "il refuse la pharmacie"}},
        "jveux pas de pharmasie")
    assert positions(garde) == {"pharmacy_first": "rejected"} and garde["pharmacy_first"]["evidence"] is None


def test_telemedecine_generale_vaut_pour_les_deux_canaux_sauf_avis_precis():
    v = {"stance": "accepted", "condition": None, "evidence": None}
    assert positions(soins.controler_soins({"telemedicine": v}, "La télémédecine, ça me va.")) \
        == {"phone_first": "accepted", "app_first": "accepted"}
    precis = soins.controler_soins({"telemedicine": v, "app_first": {**v, "stance": "rejected"}},
                                   "La télémédecine oui, mais pas d'appli.")
    assert positions(precis) == {"app_first": "rejected", "phone_first": "accepted"}


def test_tous_les_modeles():
    v = {"stance": "accepted", "condition": None, "evidence": None}
    garde = soins.controler_soins({m: v for m in soins.MODES_APERTUS}, "N'importe quel modèle, ça m'est égal.")
    assert soins.modeles_acceptes(garde) == ["unrestricted", "gp_first", "remote_first", "pharmacy_first", "flexible"]


def test_rien_sans_mot_lie():
    assert not soins.parle_de_soins("J'ai 45 ans et j'habite à Lausanne, franchise 300.")
    assert soins.parle_de_soins("Zuerst anrufen ist für mich in Ordnung.")
    v = {"stance": "accepted", "condition": None, "evidence": None}
    assert soins.controler_soins({m: v for m in soins.MODES_APERTUS}, "Je cherche l'assurance la moins chère.") == {}


def s(**modes):
    return {m: {"stance": p, "condition": None, "evidence": None} for m, p in modes.items()}


def test_categories_acceptees():
    assert soins.modeles_acceptes({}) is None
    assert soins.modeles_acceptes(s(free_choice="required", gp_first="accepted")) == ["unrestricted"]
    assert soins.modeles_acceptes(s(phone_first="accepted", app_first="rejected")) == ["remote_first", "flexible"]
    assert soins.modeles_acceptes(s(free_choice="accepted", gp_first="accepted")) \
        == ["unrestricted", "gp_first", "flexible"]
    # Refusé, conditionnel ou incertain : jamais accepté à la place de la personne
    for position in ("rejected", "conditional", "unsure"):
        assert soins.modeles_acceptes(s(pharmacy_first=position, gp_first=position)) == ["unrestricted"]


def test_dernier_message_remplace_mode_par_mode():
    fusion = soins.fusionner_soins(s(gp_first="rejected", app_first="rejected"), s(gp_first="accepted"))
    assert positions(fusion) == {"gp_first": "accepted", "app_first": "rejected"}


def test_raison_affichee():
    etat = s(app_first="rejected", phone_first="accepted", pharmacy_first="conditional", gp_first="unsure")
    assert soins.raison_non_retenu("TEL_DIG", etat) == "vous l'avez écarté"
    assert "économiser" in soins.raison_non_retenu("PHARM", etat)
    assert soins.raison_non_retenu("PRAXIS", etat) == "vous hésitez"
    assert soins.raison_non_retenu("BASE", etat) is None


if __name__ == "__main__":
    tests = [f for nom, f in sorted(globals().items()) if nom.startswith("test_")]
    for test in tests:
        test()
    print(f"{len(tests)} tests réussis")
