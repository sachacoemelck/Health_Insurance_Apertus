"""Tests du multilingue (sans appel au vrai Apertus). Lancer : python tests/test_langues.py"""
import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import chatbot  # noqa: E402
import comparateur  # noqa: E402
import conversation  # noqa: E402
import langues  # noqa: E402
import regles  # noqa: E402
import soins  # noqa: E402


def test_detection():
    assert langues.detecter("Ich bin 35 Jahre alt und wohne in Bern") == "de"
    assert langues.detecter("Ho 40 anni e abito a Lugano") == "it"
    assert langues.detecter("I'm 32 and I live in Geneva") == "en"
    assert langues.detecter("j'ai 30 ans et j'habite à Lausanne") == "fr"
    assert langues.detecter("2500") is None and langues.detecter("Lausanne") is None


def test_tous_les_textes_fixes_sont_traduits():
    manquants = []
    for fichier in ("app.py", "conversation.py"):
        for n in ast.walk(ast.parse((SRC / fichier).read_text())):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "tr" and n.args:
                a = n.args[0]
                if isinstance(a, ast.Constant) and a.value not in langues.TRAD:
                    manquants.append(a.value[:60])
    dynamiques = (list(chatbot.QUESTIONS.values()) + list(chatbot.CARE_LABELS.values())
                  + list(chatbot.NOMS_PRIORITE.values()) + list(soins.NOMS_MODES.values())
                  + [t for t, _ in comparateur.PROPOSITIONS.values()]
                  + [m["nom"] for m in comparateur.MODELES.values()]
                  + [comparateur.contrepartie(c) for c in comparateur.MODELES]
                  + [conversation.QUESTION_BUDGET, conversation.TEXTE_SUBSIDES])
    manquants += [t[:60] for t in dynamiques if t not in langues.TRAD]
    assert not manquants, manquants
    for fr, traductions in langues.TRAD.items():  # mêmes {valeurs} dans chaque langue
        champs = sorted(set(__import__("re").findall(r"\{(\w+)\}", fr)))
        for code, texte in traductions.items():
            assert sorted(set(__import__("re").findall(r"\{(\w+)\}", texte))) == champs, (code, fr[:50])


def test_regles_dans_les_quatre_langues():
    lu = lambda t, cible=None: {k: v["value"] for k, v in regles.completer_par_regles({}, t, cible).items()}
    de = lu("Ich bin 35 Jahre alt, wohne in Bern 3011, mit Unfall, höchste Franchise")
    assert de["age"] == 35 and de["postal_code"] == 3011 and de["include_accident"] is True and de["deductible"] == "highest"
    it = lu("Ho 40 anni e abito a Lugano 6900, senza infortuni, franchigia 1500")
    assert it["age"] == 40 and it["include_accident"] is False and it["deductible"] == 1500
    en = lu("I'm 32 and I live in Geneva 1202, with accidents, lowest deductible")
    assert en["age"] == 32 and en["postal_code"] == 1202 and en["deductible"] == "lowest"
    assert lu("born in 1990")["birth_year"] == 1990 and lu("nato nel 1985")["birth_year"] == 1985
    assert lu("la più alta", "deductible")["deductible"] == "highest"
    assert chatbot.localiser(None, "Genf")[0] == "Genève"
    assert conversation.lire_budget("kein Limit") == ("aucun", None)
    assert soins.accepte_tout("alle Modelle") and not soins.accepte_tout("alle Modelle ausser Apotheke")


def test_controles_dans_les_quatre_langues():
    assert langues.tutoie("Kannst du mir helfen?", "de") and not langues.tutoie("Können Sie mir helfen?", "de")
    assert langues.tutoie("Puoi dirmi la tua età?", "it")
    assert conversation.emploi_non_fonde("Da Sie angestellt sind, können Sie Unfälle ausschliessen.", "Profil connu : âge : 31")
    assert conversation.emploi_non_fonde("Since you are employed, your employer covers you.", "Profil connu : âge : 31")
    assert chatbot.montants_intrus("CHF 1,539.60 per year", "1539.60 CHF par an") == []


if __name__ == "__main__":
    tests = [f for nom, f in dict(globals()).items() if nom.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests réussis")
