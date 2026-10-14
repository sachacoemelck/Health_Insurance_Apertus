"""Test avec le vrai Apertus : l'ouverture de la conversation après le formulaire.

8 formulaires (FR, DE, IT, EN ; salarié, sans emploi, indépendant, enfant, libre choix seul) sont remplis
dans l'application. Apertus 70B écrit l'ouverture à partir du formulaire et des offres calculées par
Python ; on note si elle passe les contrôles (montants, vouvoiement) ou si le texte de secours est
utilisé, sa langue, et si elle reprend bien le formulaire (âge, commune, couverture accidents).

    docker run --rm --env-file .env -v "$HOME\\Downloads:/dl" hia-nouveau python tests/apertus/test_ouverture_reel.py
    -> crée Downloads\\resultats_ouverture.txt   (environ 2 minutes)
"""
import os as _os
import sys as _sys

_ICI = _os.path.dirname(_os.path.abspath(__file__))
_RACINE = _os.path.dirname(_os.path.dirname(_ICI))
_os.chdir(_RACINE)
_sys.path[:0] = [_ICI, _os.path.join(_RACINE, "src")]
RESULTATS = "/dl" if _os.path.isdir("/dl") else _os.path.join(_ICI, "resultats")
_os.makedirs(RESULTATS, exist_ok=True)
import re
import time

from streamlit.testing.v1 import AppTest  # noqa: E402

import app  # noqa: E402
import langues  # noqa: E402

# (langue, année de naissance, NPA, situation, modèles (None = tous), commune attendue, accidents inclus ?)
FORMULAIRES = [
    ("fr", 1991, "1004", "sans_emploi", None, "Lausanne", True),
    ("fr", 2004, "1201", "salarie_moins", None, "Genève", True),
    ("fr", 2014, "1003", "sans_emploi", None, "Lausanne", True),           # enfant
    ("fr", 1960, "2000", "independant", ["unrestricted"], "Neuchâtel", True),  # libre choix seul
    ("de", 1978, "8004", "salarie_8h", None, "Zürich", False),
    ("de", 1965, "3600", "independant", None, "Thun", True),
    ("it", 1996, "6900", "sans_emploi", None, "Lugano", True),
    ("en", 1988, "3011", "salarie_8h", None, "Bern", False),
]


def remplir(langue, annee, npa, situation, modeles, commune):
    at = AppTest.from_file(_os.path.abspath("src/app.py"), default_timeout=300).run()
    at.selectbox(key="langue").set_value(langue).run()
    at.number_input(key="f_naissance").set_value(annee).run()
    at.text_input(key="f_npa").set_value(npa).run()
    choix = [w for w in at.selectbox if w.key == "f_commune"]
    if choix and commune in choix[0].options:  # NPA partagé par plusieurs communes (ex. 3600)
        choix[0].set_value(commune).run()
    at.radio(key="f_situation").set_value(situation).run()
    if modeles:
        at.multiselect(key="f_modeles").set_value(modeles).run()
    debut = time.time()
    at.button(key="f_valider").click().run()
    return at, time.time() - debut


def main():
    journal, ok, secours = [], 0, 0
    for langue, annee, npa, situation, modeles, commune, accidents in FORMULAIRES:
        at, duree = remplir(langue, annee, npa, situation, modeles, commune)
        s = at.session_state
        pb = []
        if at.exception:
            pb.append(f"erreur : {at.exception[0].value}")
        intro = s.ouverture["texte"] if "ouverture" in s else ""
        est_secours = intro == langues.tr(app.APRES_FORMULAIRE, langue)
        secours += est_secours
        vue = langues.detecter(intro)
        if vue and vue != langue:
            pb.append(f"langue « {vue} » au lieu de « {langue} »")
        age = 2027 - annee
        if not est_secours:
            if str(age) not in intro:
                pb.append(f"âge {age} non repris")
            if commune.split()[0] not in intro and commune not in intro:
                pb.append(f"commune {commune} non reprise")
        ok += not pb
        journal.append(f"\n{'=' * 90}\n[{langue}] né(e) en {annee}, {npa} {commune}, {situation}, "
                       f"modèles : {'tous' if not modeles else ', '.join(modeles)} | accidents attendus : "
                       f"{'inclus' if accidents else 'exclus'}\n{'=' * 90}")
        journal.append(f"OUVERTURE ({duree:.0f} s{', SECOURS' if est_secours else ''}) :\n{intro}\n"
                       f"QUESTIONS PROPOSÉES : {' | '.join(s.ouverture['suggestions']) if 'ouverture' in s else '-'}")
        journal.append("-> " + ("OK" if not pb else "PROBLÈMES : " + " ; ".join(pb)))
        print(journal[-3], journal[-2], journal[-1], sep="\n", flush=True)
    resume = (f"\nRÉSUMÉ : {ok}/{len(FORMULAIRES)} ouvertures sans problème détecté automatiquement, "
              f"dont {secours} textes de secours. À relire à la main : exactitude des faits repris.")
    journal.append(resume)
    print(resume)
    with open(_os.path.join(RESULTATS, "resultats_ouverture.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(journal))


if __name__ == "__main__":
    main()
