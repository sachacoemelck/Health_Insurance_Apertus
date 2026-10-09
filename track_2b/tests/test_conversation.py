"""Tests du moteur de conversation (sans appel au vrai Apertus).
Lancer : python tests/test_conversation.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import conversation as c


def test_questions_detectees():
    for texte in ("c est quoi le mieux", "C'est quoi un modèle HMO", "Quelle franchise choisir",
                  "je sais pas", "vous me conseillez quoi", "j'hésite", "Laquelle est la moins chère ?",
                  "comment ça marche", "Was ist eine Franchise", "which one should I take"):
        assert c.est_question(texte), texte


def test_reponses_pas_prises_pour_des_questions():
    for texte in ("2500", "la plus haute", "avec accidents", "1261", "tous les modèles me vont",
                  "J'ai 30 ans et j'habite à Nyon", "pas de limite", "oui"):
        assert not c.est_question(texte), texte


def test_question_ne_remplit_pas_le_champ_demande():
    u = {"deductible": {"value": "all", "status": "known", "correction": False},
         "age": {"value": 21, "status": "known", "correction": False}}
    assert set(c.mises_a_jour_hors_question(u, "deductible", True)) == {"age"}
    assert c.mises_a_jour_hors_question(u, "deductible", False) == u


def test_budget():
    assert c.lire_budget("pas plus de 350 par mois", "budget") == ("montant", 350)
    assert c.lire_budget("300 CHF", "budget") == ("montant", 300)
    assert c.lire_budget("pas de limite", "budget") == ("aucun", None)
    assert c.lire_budget("j'ai un petit budget") == ("petit", None)
    assert c.lire_budget("mon budget est de 280 francs par mois") == ("montant", 280)
    # Un âge, une franchise ou un code postal ne sont jamais lus comme un budget
    assert c.lire_budget("j'ai 21 ans, franchise 2500, j'habite à 1261 Le Vaud") is None
    assert c.lire_budget("j'ai 45 ans", "budget") == ("aucun", None) or c.lire_budget("j'ai 45 ans", "budget") is None


def test_conseil_franchise_coherent():
    faits = c.faits_franchise("VD", 1, 22, True, None, 350)
    assert "franchise 300 CHF" in faits and "franchise 2500 CHF" in faits
    lignes = c.franchises_pour("VD", 1, 22, True)
    basse, haute = lignes[0], lignes[-1]
    s = c.seuil(basse, haute, 700)
    # Juste avant le seuil, la franchise haute coûte moins ; au seuil, plus
    assert c.cout_total(haute["prime_an"], 2500, s - 10, 700) <= c.cout_total(basse["prime_an"], 300, s - 10, 700)
    assert c.cout_total(haute["prime_an"], 2500, s, 700) > c.cout_total(basse["prime_an"], 300, s, 700)
    assert c.faits_franchise(None, None, 22, True) == ""


def test_reponse_avec_nombre_invente_refusee():
    question = "Quelle franchise souhaitez-vous ?"
    menteur = lambda s, m: "Prenez 2500, vous économiserez 1234 CHF. " + question
    assert c.repondre_tour(menteur, "c'est quoi le mieux", [], True, question).endswith(question)
    assert "1234" not in c.repondre_tour(menteur, "c'est quoi le mieux", [], True, question)


def test_reponse_correcte_acceptee():
    question = "Quelle franchise souhaitez-vous ?"
    bon = lambda s, m: "Avec peu de frais, une franchise haute coûte moins en primes. " + question
    assert c.repondre_tour(bon, "c'est quoi le mieux", [], True, question).startswith("Avec peu de frais")


def test_tutoiement_et_panne_refuses():
    question = "Quel est votre âge ?"
    assert c.repondre_tour(lambda s, m: "Quel est ton âge ?", "salut", [], False, question) == question

    def panne(s, m):
        raise RuntimeError("Apertus indisponible")
    assert c.repondre_tour(panne, "salut", [], False, question) == question


if __name__ == "__main__":
    tests = [f for nom, f in dict(globals()).items() if nom.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests réussis")
