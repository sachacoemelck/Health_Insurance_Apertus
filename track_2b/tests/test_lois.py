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


if __name__ == "__main__":
    tests = [f for nom, f in dict(globals()).items() if nom.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests réussis")
