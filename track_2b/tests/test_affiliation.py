"""Tests de la demande d'affiliation et des contacts officiels des caisses (sans appel au vrai Apertus).
Lancer depuis track_2b/ : python tests/test_affiliation.py"""
import datetime
import os
import sys
from urllib.parse import unquote

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import affiliation  # noqa: E402
import caisses  # noqa: E402
import changement  # noqa: E402
import comparateur  # noqa: E402

changement.AUJOURDHUI = datetime.date(2026, 10, 15)


def choix(**autres):
    c = {"caisse": "Atupri Gesundheitsversicherung AG", "numero": 312, "produit": "Atupri HMO CareMed",
         "modele": "Médecin de famille / HMO", "franchise": 2500, "accident": True, "prime_mois": 456.0,
         "annee": 2027, "ancienne": None}
    c.update(autres)
    return c


def test_contacts_officiels():
    """Chaque caisse qui a des primes 2027 a une adresse, un téléphone et un site dans la liste OFSP."""
    numeros = set(comparateur.df["Versicherer"].unique())
    for n in numeros:
        c = caisses.contact(n)
        assert c and c["adresse"] and c["telephone"] and c["site"].startswith("https://www."), (n, c)
        assert caisses.adresse_postale(n)[-1][:4].isdigit(), caisses.adresse_postale(n)  # NPA en dernière ligne
    sans_email = {n for n in numeros if not caisses.contact(n)["email"]}
    assert sans_email == {343, 1479, 1535, 1562}, sans_email  # Groupe Mutuel (formulaire) et Helsana
    assert caisses.contact(312)["email"] == "info@atupri.ch"
    assert caisses.adresse_postale(343) == ["Avenir Krankenversicherung AG", "Rue des Cèdres 5", "1919 Martigny"]
    assert caisses.contact(290)["nom"] == "CONCORDIA Schweiz. Kranken- und Unfallversicherung AG"


def test_demande_modele_complete_dans_chaque_langue():
    for langue in ("fr", "de", "it"):
        for accident in (True, False):
            for ancienne in (None, "Helsana"):
                c = choix(accident=accident, ancienne=ancienne)
                assert affiliation.problemes(affiliation.demande_modele(c, langue), c, langue) == [], (langue, accident)


def test_demande_incomplete_ou_inventee_refusee():
    c = choix(ancienne="Helsana")
    bon = affiliation.demande_modele(c, "fr")
    assert affiliation.problemes(bon.replace("[Numéro AVS]", "756.1234.5678.97"), c, "fr")  # numéro inventé
    assert affiliation.problemes(bon.replace("2500", "300"), c, "fr")                      # mauvaise franchise
    assert affiliation.problemes(bon.replace("avec la couverture accidents", "sans la couverture accidents"), c, "fr")
    assert affiliation.problemes(bon.replace("Helsana", "mon ancienne caisse"), c, "fr")
    # Apertus mauvais deux fois -> demande modèle ; bon -> sa demande
    texte, par = affiliation.rediger(lambda s, m: "Je veux m'affilier.", c, "de")
    assert par == "modele" and "Grundversicherung" in texte
    texte, par = affiliation.rediger(lambda s, m: bon, c, "fr")
    assert par == "apertus" and texte == bon


def test_date_de_debut_apres_le_delai():
    assert affiliation.debut_couverture(2027) == datetime.date(2027, 1, 1)
    changement.AUJOURDHUI = datetime.date(2026, 12, 5)  # après fin novembre : changement au 1.1.2028
    try:
        c = choix()
        assert "1er janvier 2028" in affiliation.demande_modele(c, "fr")
    finally:
        changement.AUJOURDHUI = datetime.date(2026, 10, 15)


def test_lien_courriel_adresse_et_rappel():
    c = choix()
    texte = affiliation.demande_modele(c, "fr")
    lien = affiliation.lien_mailto("info@atupri.ch", affiliation.objet(c, "fr"), texte)
    assert lien.startswith("mailto:info@atupri.ch?subject=Demande%20d%27affiliation")
    assert unquote(lien.split("&body=")[1]).replace("\r\n", "\n") == texte
    lettre = affiliation.avec_adresse(texte, 312, c["caisse"])
    assert "Atupri Gesundheitsversicherung AG\nLaupenstrasse 18\n3008 Bern" in lettre
    assert affiliation.objet(c, "de").startswith("Antrag auf Aufnahme in die Grundversicherung ab 1.1.2027")
    ics = affiliation.rappel_ics(datetime.date(2026, 11, 30), "Helsana", "fr")
    assert "DTSTART;VALUE=DATE:20261123" in ics and "Helsana" in ics and ics.startswith("BEGIN:VCALENDAR")


if __name__ == "__main__":
    tests = [f for nom, f in dict(globals()).items() if nom.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests réussis")
