"""Test avec le vrai Apertus : la demande d'affiliation à la nouvelle caisse (« check-out »).

9 demandes (3 en français, 3 en allemand, 3 en italien), avec et sans caisse actuelle, accidents inclus
ou exclus, pour des offres réelles (primes OFSP 2027). On note si la demande d'Apertus 70B passe les
contrôles de Python du premier coup, au 2e essai, ou si la demande modèle est utilisée, et on garde le
texte pour le relire à la main.

    docker run --rm --env-file .env -v "$HOME\\Downloads:/dl" hia-nouveau python tests/apertus/test_affiliation_reel.py
    -> crée Downloads\\resultats_affiliation.txt   (environ 2 minutes)
"""
import os as _os
import sys as _sys

_ICI = _os.path.dirname(_os.path.abspath(__file__))
_RACINE = _os.path.dirname(_os.path.dirname(_ICI))
_os.chdir(_RACINE)
_sys.path[:0] = [_ICI, _os.path.join(_RACINE, "src")]
RESULTATS = "/dl" if _os.path.isdir("/dl") else _os.path.join(_ICI, "resultats")
_os.makedirs(RESULTATS, exist_ok=True)
import time

import affiliation  # noqa: E402
import app  # noqa: E402
import chatbot  # noqa: E402
import comparateur  # noqa: E402

# (langue, canton, région, commune, âge, franchise, accidents inclus, caisse actuelle, rang de l'offre)
CAS = [("fr", "VD", 1, "Lausanne", 35, 2500, True, "Helsana", 0),
       ("fr", "GE", 0, "Genève", 22, 300, True, None, 1),
       ("fr", "NE", 0, "Neuchâtel", 52, 1500, False, "CSS", 2),
       ("de", "ZH", 1, "Zürich", 41, 2500, False, "CSS", 0),
       ("de", "BE", 1, "Bern", 63, 300, True, None, 3),
       ("de", "LU", 1, "Luzern", 29, 2000, True, "SWICA", 1),
       ("it", "TI", 1, "Lugano", 31, 2500, True, "Helsana", 0),
       ("it", "TI", 1, "Bellinzona", 47, 1000, False, None, 2),
       ("it", "TI", 1, "Locarno", 24, 300, True, "CONCORDIA", 1)]


def main():
    cfg = app.config()
    client = app.client_llm(cfg["LLM_BASE_URL"], cfg["LLM_API_KEY"]).with_options(timeout=40)
    essais = []

    def ecrire(systeme, message):
        essais.append(1)
        return chatbot.demander_llm(client, cfg["LLM_NAME_RESTITUTION"], systeme, message)

    journal, premier, second, modele = [], 0, 0, 0
    for langue, canton, region, commune, age, franchise, accident, ancienne, rang in CAS:
        offres = comparateur.toutes_les_offres(canton, region, age, franchise, accident)
        o = offres.iloc[min(rang, len(offres) - 1)]
        numero = app.NUMEROS_CAISSES.get(o["Assureur"])
        choix = {"caisse": o["Assureur"], "numero": numero, "produit": o["Produit"], "modele": o["Modèle"],
                 "franchise": franchise, "prime_mois": float(o["Prime/mois"]), "accident": accident,
                 "annee": 2027, "ancienne": ancienne}
        essais.clear()
        debut = time.time()
        texte, par = affiliation.rediger(ecrire, choix, langue)
        duree = time.time() - debut
        if par == "modele":
            modele += 1
            resultat = "demande modèle (Apertus refusé 2 fois)"
        elif len(essais) == 1:
            premier += 1
            resultat = "Apertus accepté du 1er coup"
        else:
            second += 1
            resultat = "Apertus accepté au 2e essai"
        journal.append(f"\n{'=' * 90}\n[{langue}] {o['Assureur']} – {o['Produit']} ({o['Modèle']}), franchise "
                       f"{franchise}, accidents {'inclus' if accident else 'exclus'}, caisse actuelle : "
                       f"{ancienne or '-'}\n{'=' * 90}\n{resultat} ({duree:.1f} s)\n\n{texte}")
        print(journal[-1], flush=True)
    resume = (f"\nRÉSUMÉ : demandes d'Apertus acceptées {premier + second}/{len(CAS)} (1er coup : {premier}, "
              f"2e essai : {second}) ; demande modèle : {modele}. À relire à la main : ton, exactitude.")
    journal.append(resume)
    print(resume)
    with open(_os.path.join(RESULTATS, "resultats_affiliation.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(journal))


if __name__ == "__main__":
    main()
