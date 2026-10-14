"""Tests de la recherche dans les textes de loi (sans appel au vrai Apertus). Lancer : python tests/test_lois.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import conversation  # noqa: E402
import lois  # noqa: E402

URL = "https://www.fedlex.admin.ch/eli/cc/1995/1328_1328_1328/{l}#art_{a}"
ARTICLES = [  # extraits réels de la LAMal (fedlex, version du 1.7.2026)
    ("fr", "29", "Maternité", "1 L’assurance obligatoire des soins prend en charge, en plus des coûts des mêmes "
     "prestations que pour la maladie, ceux des prestations spécifiques de maternité.\n2 Ces prestations "
     "comprennent:\na. les examens de contrôle pendant et après la grossesse;\nb. l’accouchement à domicile, "
     "dans un hôpital ou dans une maison de naissance;"),
    ("fr", "31", "Soins dentaires", "1 L’assurance obligatoire des soins prend en charge les coûts des soins "
     "dentaires:\na. s’ils sont occasionnés par une maladie grave et non évitable du système de la mastication"),
    ("fr", "64", "Participation aux coûts", "1 Les assurés participent aux coûts des prestations dont ils "
     "bénéficient.\n2 Leur participation comprend:\na. un montant fixe par année (franchise); et\nb. 10 % des "
     "coûts qui dépassent la franchise (quote-part).\n7 L’assureur ne peut prélever aucune participation aux "
     "coûts des prestations suivantes:\na. prestations visées à l’art. 29, al. 2;\nb. prestations fournies à "
     "partir de la 13e semaine de grossesse, pendant l’accouchement, et jusqu’à huit semaines après."),
    ("fr", "64a", "Non-paiement des primes", "1 Lorsque l’assuré n’a pas payé des primes échues, l’assureur lui "
     "envoie une sommation.\n6 L’assuré en retard de paiement ne peut pas changer d’assureur tant que ses "
     "arriérés de primes ne sont pas payés intégralement."),
    ("de", "64", "Kostenbeteiligung", "1 Die Versicherten beteiligen sich an den Kosten.\n7 Der Versicherer darf "
     "auf folgenden Leistungen keine Kostenbeteiligung erheben:\nb. Leistungen ab der 13. Schwangerschaftswoche, "
     "während der Niederkunft und bis acht Wochen nach der Niederkunft."),
]


def base_test():
    donnees = [{"loi": "LAMal", "rs": "832.10", "langue": l, "article": a, "titre": t, "texte": x,
                "version": "20260701", "url": URL.format(l=l, a=a)} for l, a, t, x in ARTICLES]
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(donnees, f, ensure_ascii=False)
    f.close()
    return f.name


def test_alineas():
    assert lois.alineas("1 Premier.\n2 Comprend:\na. ceci;\nb. cela.\n2bis Ajout.") == [
        ("1", "Premier."), ("2", "Comprend: a. ceci; b. cela."), ("2bis", "Ajout.")]
    assert lois.alineas("Texte sans numéro.") == [("", "Texte sans numéro.")]


def test_recherche_trouve_le_bon_alinea():
    chemin = base_test()
    trouve = lambda q, code="fr", cles="": [lois.reference(p, code) for p in lois.chercher(q, code, cles, 3, chemin)]
    assert "LAMal art. 64 al. 7" in trouve("Est-ce qu'un accouchement me coûte la franchise ?")
    assert trouve("Que se passe-t-il si je ne paie pas mes primes ?")[0].startswith("LAMal art. 64a")
    assert "KVG Art. 64 Abs. 7" in trouve("Wird bei einer Geburt ein Selbstbehalt verrechnet?", "de",
                                          "maternité accouchement participation aux coûts")
    assert trouve("Is dental cleaning covered?", "en", "soins dentaires")[0] == "LAMal art. 31 para. 1"


def test_citations_de_loi_verifiees():
    passages = lois.chercher("accouchement franchise", "fr", "", 2, base_test())
    faits = lois.texte_passages(passages)
    assert faits.startswith("[L1] LAMal art.")
    assert conversation.numeros_inconnus("Rien à payer [L1].", faits) == []
    assert conversation.numeros_inconnus("Rien à payer [L7].", faits) == ["L7"]  # article jamais fourni
    texte = conversation.citer("Pendant l'accouchement, vous ne payez ni franchise ni quote-part [L1].", "fr", passages)
    assert "[L1]" not in texte and "fedlex.admin.ch" in texte and "Source :" in texte
    assert lois.mots_cles(lambda s, m: "maternité, grossesse, participation aux coûts", "Geburt?") \
        == "maternité grossesse participation aux coûts"
    assert lois.mots_cles(lambda s, m: 1 / 0, "Geburt?") == ""  # Apertus 8B en panne : recherche sans lui


def test_reponse_avec_un_article_inexistant_refusee():
    passages = lois.chercher("accouchement franchise", "fr", "", 2, base_test())
    invente = lambda s, m: "Vous ne payez rien [L9]."
    assert conversation.repondre_libre(invente, "Accouchement ?", "rien", passages=passages) is None
    juste = lambda s, m: "Pour l'accouchement, aucune participation aux coûts n'est demandée [L1]."
    assert "fedlex" in conversation.repondre_libre(juste, "Accouchement ?", "rien", passages=passages)


def test_numeros_groupes_et_dans_la_phrase():
    """Formes vues au test réel du 12.10 : « [F6, L2] », « (L1, L3) », « selon [L2], … »."""
    passages = lois.chercher("accouchement franchise", "fr", "", 2, base_test())
    a = conversation.citer("Remboursée [F6, L2]. Selon [L1], rien à payer.", "fr", passages)
    assert "[" not in a.split("\n")[0] and "Selon LAMal art." in a and ", rien à payer" in a, a
    b = conversation.citer("According to (L1, L2), nothing is due.", "en", passages)
    assert b.startswith("According to LAMal art.") and " and LAMal art." in b, b
    c = conversation.citer("Gemäss [L1] und [L2] erhebt der Versicherer nichts.", "de", passages)
    assert "erhebt" in c and "[L" not in c.split("\n")[0], c
    assert conversation.numeros_inconnus("ok [L1, L9]", "[L1] x") == ["L9"]
    assert conversation.raccourcir("Un. Deux. Trois. Quatre. Cinq. Six. Sept.", 5) == "Un. Deux. Trois. Quatre. Cinq."
    assert conversation.raccourcir("Das Modell (z. B. Hausarzt) hat Regeln. Zwei.", 1) == "Das Modell (z. B. Hausarzt) hat Regeln."
    # 2e test réel (60 questions) : numéros au milieu d'une phrase, plages, formules de lettre
    d = conversation.citer("Les articles [L1] et [L2] précisent que rien n'est dû.", "fr", passages)
    assert d.startswith("Les articles LAMal art.") and "précisent" in d, d
    e = conversation.citer("Rien à payer [L1] mais la franchise reste [L2].", "fr", passages)
    assert e.startswith("Rien à payer mais la franchise reste."), e
    assert "[L" not in conversation.citer("Die Prämie hängt vom Kanton ab [L1–L2].", "de", passages)
    assert conversation.nettoyer("Ma chère personne,  La LAMal paie.", True) == "La LAMal paie."
    assert conversation.nettoyer("Sehr geehrte Person, gemäss KVG.", True) == "Gemäss KVG."
    # Test réel multilingue (14.10) : numéros sans crochets, « St. Gallen » coupé après « St. »
    f = conversation.citer("Coperto solo nei casi gravi (articoli L1, L2). Per il resto paga Lei.", "it", passages)
    assert "L1" not in f and "articoli" not in f and f.startswith("Coperto solo nei casi gravi. Per il resto"), f
    assert conversation.numeros_inconnus("casi gravi (articoli L1, L9)", "[L1] x") == ["L9"]
    g = conversation.citer("Selon L1, rien n'est dû.", "fr", passages)
    assert g.startswith("Selon LAMal art."), g
    assert conversation.decouper_phrases("Als Student in St. Gallen zahlen Sie wenig. Zweitens.") == [
        "Als Student in St. Gallen zahlen Sie wenig.", "Zweitens."]
    assert conversation.nettoyer("In St. Gallen ist es so. Welche Franchise?") == "In St. Gallen ist es so."


if __name__ == "__main__":
    tests = [f for nom, f in dict(globals()).items() if nom.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests réussis")
