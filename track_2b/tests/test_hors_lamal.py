"""Ce que l'assurance de base ne couvre pas : textes dans les 4 langues, sources fedlex qui existent.
Lancer depuis track_2b/ : python tests/test_hors_lamal.py"""
import json, os, sys
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(RACINE)
sys.path.insert(0, os.path.join(RACINE, "src"))
import hors_lamal
from langues import tr, TRAD

ok = 0
# 1. Chaque besoin a libellé, « paie », « ne paie pas » dans les 4 langues, sans texte vide
for cle, b in hors_lamal.BESOINS.items():
    for code in ("fr", "de", "it", "en"):
        assert len(b[code]) == 3 and all(x.strip() for x in b[code]), (cle, code)
ok += 1
# 2. Chaque source pointe vers fedlex, dans la langue (anglais -> texte français), vers un article existant
for cle in hors_lamal.BESOINS:
    for code, langue_loi in (("fr", "fr"), ("de", "de"), ("it", "it"), ("en", "fr")):
        for ref, lien in hors_lamal.sources(cle, code):
            assert lien.startswith("https://www.fedlex.admin.ch/") and f"/{langue_loi}" in lien, (cle, code, lien)
assert hors_lamal.sources("dentaire", "de")[0][0].endswith("Art. 31"), hors_lamal.sources("dentaire", "de")
assert "Abs." in hors_lamal.sources("hopital", "de")[0][0] and "cpv." in hors_lamal.sources("hopital", "it")[0][0]
ok += 1
# 3. Faits pour Apertus : seulement les besoins cochés, chacun finit par « il faut une complémentaire »
f = hors_lamal.faits(["lunettes", "inconnu", "etranger"])
assert len(f) == 2 and all(x.endswith("Pour cela, il faut une assurance complémentaire.") for x in f), f
assert hors_lamal.faits([]) == [] and len(hors_lamal.lignes(["dentaire"], "it")) == 1
ok += 1
# 4. Les textes clés du check-out sont traduits
for fr in ("Pour ce que l'assurance de base ne paie pas, il faut une assurance complémentaire.",
           "Assurance de base (LAMal) uniquement", "Ce que l’assurance de base ne paie pas"):
    assert fr in TRAD and all(TRAD[fr][c] for c in ("de", "it", "en")), fr
assert tr("Assurance de base (LAMal) uniquement", "de") == "Nur Grundversicherung (KVG)"
ok += 1
print(f"{ok} tests réussis")
