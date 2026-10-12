"""Tests de la caisse actuelle, de l'économie et de la lettre de résiliation (sans vrai Apertus).
Lancer : python tests/test_changement.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import changement as c  # noqa: E402
import chatbot  # noqa: E402

PROFIL = chatbot.ComparisonProfile(2027, "Lausanne", "VD", 1, 35, (1500,), True, ("BASE", "PRAXIS", "TEL_DIG", "FLEX"))
OFS = chatbot.no_ofs_de("Lausanne", "VD")


def test_caisses_reconnues():
    nom = lambda t: [c.CAISSES[n] for n in c.trouver_caisses(t)]
    assert nom("Je suis chez Helsana, modèle médecin de famille") == ["Helsana"]
    assert nom("bei der ÖKK") == ["ÖKK"] and nom("sono con la Swica") == ["SWICA"] and nom("Assura") == ["Assura-Basis SA"]
    assert len(c.trouver_caisses("Groupe Mutuel")) == 3            # nom de groupe : la personne choisit
    assert c.trouver_caisses("je sais plus, une caisse en S") == []
    assert c.lire_modele("Visana telmed") == "TEL_DIG" and c.lire_modele("KPT, Hausarztmodell") == "PRAXIS"


def test_apertus_ne_peut_pas_inventer_une_caisse_ni_une_prime():
    invente = lambda s, m: json.dumps({"caisse": "Sanitas", "modele": None, "prime_mois": 412.5})
    lu = c.lire_caisse(invente, "je ne sais plus trop")
    assert lu["caisses"] == [] and lu["prime_mois"] is None      # rien de cela n'est dans le message
    lu = c.lire_caisse(lambda s, m: json.dumps({"caisse": "CSS", "prime_mois": 412.5}), "CSS, je paie 412.50 par mois")
    assert lu["caisses"] == [8] and lu["prime_mois"] == 412.5
    assert c.lire_caisse(lambda s, m: 1 / 0, "Helsana")["caisses"] == [1562]   # 8B en panne : Python lit seul
    # Test réel du 13.10 : Apertus 8B ajoutait « médecin de famille » sans que la personne le dise
    invente_modele = lambda s, m: json.dumps({"caisse": "CSS", "modele": "médecin de famille", "prime_mois": None})
    assert c.lire_caisse(invente_modele, "CSS je crois")["modele"] is None


def test_economie_calculee_par_python():
    offres = chatbot.offres_du_profil(PROFIL)
    e = c.calculer_economie(PROFIL, offres, 1562, "PRAXIS", None, OFS)
    o = e["options"][0][1]
    assert o["economie_an"] == round((e["prime_actuelle"] - o["prime"]) * 12, 2) > 0
    assert e["autre_caisse"] is not None
    sans_modele = c.calculer_economie(PROFIL, offres, 1562, None, None, OFS)
    assert sans_modele["modele_suppose"] and sans_modele["modele"] == "BASE"
    assert "suppose le libre choix" in c.faits_economie(sans_modele)
    moins_chere = offres.iloc[0]["Assureur"]
    numero = next(n for n, nom in c.CAISSES.items() if nom == moins_chere)
    deja = c.calculer_economie(PROFIL, offres, numero, offres.iloc[0]["Tariftyp"], None, OFS)
    assert deja["deja_meilleure"] and deja["autre_caisse"] is None   # pas de lettre à proposer


def test_lettre_verifiee():
    for langue in ("fr", "de", "it"):
        assert c.problemes_lettre(c.lettre_modele("Helsana", langue, 2027), "Helsana", langue, 2027) == []
    mauvaise = c.lettre_modele("Helsana", "fr", 2027).replace(
        "ne sont pas résiliées et restent en vigueur", "sont également résiliées").replace(
        "[Numéro d'assuré]", "756.1234.5678.90")
    p = c.problemes_lettre(mauvaise, "Helsana", "fr", 2027)
    assert any("complémentaires" in x for x in p) and any("invente" in x for x in p)
    # Apertus se trompe deux fois : la lettre modèle sûre est utilisée
    lettre, par = c.rediger_lettre(lambda s, m: "Je résilie tout.", "Helsana", "fr", 2027)
    assert par == "modele" and c.problemes_lettre(lettre, "Helsana", "fr", 2027) == []
    bonne = c.lettre_modele("CSS", "de", 2027)
    assert c.rediger_lettre(lambda s, m: bonne, "CSS", "de", 2027) == (bonne, "apertus")
    assert c.langue_lettre("en", "ZH") == "de" and c.langue_lettre("en", "GE") == "fr" and c.langue_lettre("it", "ZH") == "it"
    assert c.dates(2027)[1].isoformat() == "2026-11-30"          # lundi 30 novembre 2026
    assert "30.11.2026" in c.conseils_envoi("fr", 2027)


def test_office_des_subsides_par_canton():
    import subsides
    assert len(subsides.OFFICES) == 26                      # les 26 cantons de la liste OFSP
    assert all(url.startswith("https://") for _, url in subsides.OFFICES.values())
    assert "[SVA Zürich](https://svazurich.ch)" in subsides.office("ZH", "de")
    assert "Office vaudois" in subsides.office("VD") and subsides.office(None) is None
    assert subsides.PARLE_DE_SUBSIDE.search("Ai-je droit à un subside ?")
    assert subsides.PARLE_DE_SUBSIDE.search("Habe ich Anspruch auf Prämienverbilligung?")


if __name__ == "__main__":
    tests = [f for nom, f in dict(globals()).items() if nom.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests réussis")
