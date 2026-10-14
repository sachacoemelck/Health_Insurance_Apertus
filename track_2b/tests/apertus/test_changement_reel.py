"""Test avec le vrai Apertus : caisse actuelle, économie et lettre de résiliation.

1. Lecture de la caisse : 16 réponses libres (FR, DE, IT, EN), écrites avant le test, avec la caisse,
   le modèle et la prime attendus. Apertus 8B lit, Python vérifie.
2. Paragraphe d'économie : Apertus 70B l'écrit à partir des chiffres de Python ; on note s'il passe
   les contrôles (chiffres, langue, vouvoiement) ou si le texte de secours est utilisé.
3. Lettres de résiliation : 9 lettres (3 en français, 3 en allemand, 3 en italien) ; on note si la
   lettre d'Apertus passe les contrôles du premier coup, au 2e essai, ou si la lettre modèle est utilisée.

    docker run --rm --env-file .env -v "$HOME\\Downloads:/dl" hia-nouveau python tests/apertus/test_changement_reel.py
    -> crée Downloads\\resultats_changement.txt   (environ 5 minutes)
"""
import os as _os
import sys as _sys

# Lancement depuis track_2b/ (ou /app dans le conteneur). Résultats : /dl s'il est monté (Docker,
# -v "$HOME\\Downloads:/dl"), sinon tests/apertus/resultats/.
_ICI = _os.path.dirname(_os.path.abspath(__file__))
_RACINE = _os.path.dirname(_os.path.dirname(_ICI))
_os.chdir(_RACINE)
_sys.path[:0] = [_ICI, _os.path.join(_RACINE, "src")]
RESULTATS = "/dl" if _os.path.isdir("/dl") else _os.path.join(_ICI, "resultats")
_os.makedirs(RESULTATS, exist_ok=True)
import os
import sys
import time

import app  # noqa: E402
import changement as c  # noqa: E402
import chatbot  # noqa: E402
import conversation  # noqa: E402
import langues  # noqa: E402

# (langue, réponse de la personne, caisse attendue (nom officiel ou None), modèle attendu, prime attendue)
REPONSES = [
    ("fr", "Je suis chez Helsana, en modèle médecin de famille", "Helsana", "PRAXIS", None),
    ("fr", "CSS je crois", "CSS", None, None),
    ("fr", "Assura, libre choix, je paie 389.50 par mois", "Assura-Basis SA", "BASE", 389.5),
    ("fr", "je sais plus, une caisse en S", None, None, None),
    ("fr", "Chez Groupe Mutuel", "groupe", None, None),
    ("fr", "Visana avec la télémédecine", "Visana", "TEL_DIG", None),
    ("de", "Ich bin bei der Sanitas, Hausarztmodell", "Sanitas", "PRAXIS", None),
    ("de", "bei der ÖKK, Telmed", "ÖKK", "TEL_DIG", None),
    ("de", "Swica, ich zahle 455 Franken im Monat", "SWICA", None, 455.0),
    ("de", "Ich weiss es nicht mehr", None, None, None),
    ("it", "Sono assicurato con la Concordia, libera scelta", "CONCORDIA", "BASE", None),
    ("it", "Atupri, medico di famiglia", "Atupri Gesundheitsversicherung AG", "PRAXIS", None),
    ("it", "pago circa 420 franchi al mese ma non ricordo la cassa", None, None, 420.0),
    ("en", "I'm with KPT, standard model", "KPT", "BASE", None),
    ("en", "Sympany, family doctor model", "Vivao Sympany", "PRAXIS", None),
    ("en", "EGK I think, telemedicine", "EGK", "TEL_DIG", None),
]

LETTRES = [("fr", "Helsana"), ("fr", "CSS"), ("fr", "Assura-Basis SA"),
           ("de", "Sanitas"), ("de", "ÖKK"), ("de", "SWICA"),
           ("it", "CONCORDIA"), ("it", "Atupri Gesundheitsversicherung AG"), ("it", "Helsana")]

PROFIL = chatbot.ComparisonProfile(2027, "Lausanne", "VD", 1, 35, (1500,), True,
                                   ("BASE", "PRAXIS", "TEL_DIG", "FLEX"))


def main(sortie=_os.path.join(RESULTATS, "resultats_changement.txt")):
    cfg = app.config()
    client = app.client_llm(cfg["LLM_BASE_URL"], cfg["LLM_API_KEY"])

    def appel(fonction, modele, delai):
        c2 = client.with_options(timeout=delai)
        return lambda s, m: getattr(chatbot, fonction)(c2, modele, s, m)

    lire = appel("demander_llm_json", cfg["LLM_NAME"], app.DELAI_8B)
    ecrire = appel("demander_llm", cfg["LLM_NAME_RESTITUTION"], app.DELAI_70B)
    lettre_70b = appel("demander_llm", cfg["LLM_NAME_RESTITUTION"], 40)
    offres = chatbot.offres_du_profil(PROFIL)
    ofs = chatbot.no_ofs_de("Lausanne", "VD")
    lignes, ok_lecture, ok_texte, n_texte = [], 0, 0, 0

    lignes.append("=== 1 et 2. Caisse actuelle et paragraphe d'économie ===")
    for code, texte, caisse, modele, prime in REPONSES:
        debut = time.time()
        lu = c.lire_caisse(lire, texte)
        noms = [c.CAISSES[n] for n in lu["caisses"]]
        attendu_caisses = (len(noms) > 1) if caisse == "groupe" else (noms == ([caisse] if caisse else []))
        juste = attendu_caisses and lu["modele"] == modele and lu["prime_mois"] == prime
        ok_lecture += juste
        bloc = (f"[{code}] « {texte} »\n  Lu : caisses={noms or '-'} modèle={lu['modele']} prime={lu['prime_mois']}"
                f"  -> {'JUSTE' if juste else 'FAUX (attendu : ' + str((caisse, modele, prime)) + ')'}"
                f"  ({time.time() - debut:.1f} s)\n")
        numero = lu["caisses"][0] if len(lu["caisses"]) == 1 else None
        e = c.calculer_economie(PROFIL, offres, numero, lu["modele"], lu["prime_mois"], ofs)
        if e and not e.get("absente"):
            n_texte += 1
            debut = time.time()
            try:
                brut = conversation.demander_verifie(
                    ecrire, c.PROMPT_ECONOMIE.replace("{langue}", langues.NOMS_POUR_APERTUS[code]),
                    c.faits_economie(e), doit_questionner=False, code=code)
            except Exception as erreur:
                brut = None
                bloc += f"  Erreur Apertus : {type(erreur).__name__}\n"
            texte_final = conversation.raccourcir(conversation.nettoyer(brut), 4) if brut else None
            ok_texte += texte_final is not None
            bloc += (f"  Faits Python :\n    " + c.faits_economie(e).replace("\n", "\n    ") + "\n"
                     f"  Texte {'APERTUS (vérifié)' if texte_final else 'DE SECOURS'} ({time.time() - debut:.1f} s) : "
                     f"{texte_final or c.texte_economie_secours(e, code)}\n")
        print(bloc, flush=True)
        lignes.append(bloc)

    lignes.append("=== 3. Lettres de résiliation ===")
    resultats_lettres = {"apertus": 0, "modele": 0}
    for langue, caisse in LETTRES:
        debut = time.time()
        premiers = []

        def suivi(s, m):  # garde la trace des problèmes du premier essai
            reponse = lettre_70b(s, m)
            premiers.append(c.problemes_lettre(reponse, caisse, langue, 2027))
            return reponse
        lettre, par = c.rediger_lettre(suivi, caisse, langue, 2027)
        resultats_lettres[par] += 1
        essais = "1er essai" if par == "apertus" and len(premiers) == 1 else (
            "2e essai" if par == "apertus" else "LETTRE MODÈLE")
        bloc = (f"[{langue}] {caisse} : {par.upper()} ({essais}, {time.time() - debut:.1f} s)\n"
                f"  Problèmes vus par Python : {premiers}\n  Lettre :\n    " + lettre.replace("\n", "\n    ") + "\n")
        print(bloc, flush=True)
        lignes.append(bloc)

    resume = (f"RÉSUMÉ : lecture de la caisse {ok_lecture}/{len(REPONSES)} justes | paragraphe d'économie "
              f"d'Apertus accepté {ok_texte}/{n_texte} | lettres d'Apertus acceptées {resultats_lettres['apertus']}"
              f"/{len(LETTRES)} (lettre modèle : {resultats_lettres['modele']})")
    print(resume)
    with open(sortie, "w", encoding="utf-8") as f:
        f.write(f"Modèles : {cfg['LLM_NAME']} (lecture), {cfg['LLM_NAME_RESTITUTION']} (rédaction)\n\n"
                + "\n".join(lignes) + "\n" + resume + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
