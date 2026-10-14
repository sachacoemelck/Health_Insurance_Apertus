"""Télécharge les textes officiels (fedlex.admin.ch) des lois utilisées par le conseiller LAMal et
en extrait les articles, en français, allemand et italien.

    python src/telecharger_lois.py [fichier_sortie]      (défaut : data/lois.json)

Le résultat est un fichier JSON : une entrée par article et par langue, avec la loi, le numéro,
le titre, le texte (sans les notes de bas de page) et l'adresse officielle. Il suffit de relancer
ce script pour mettre à jour la base quand une loi change.

Fedlex range chaque version consolidée d'une loi sous sa date d'entrée en vigueur. Le script cherche
la version la plus récente déjà en vigueur, en essayant les dates du 1er de chaque mois, de
la plus récente à la plus ancienne.
"""
import datetime
import html
import json
import re
import sys
import urllib.error
import urllib.request

LOIS = {  # abréviation française : (ELI, numéro du recueil systématique)
    "LAMal": ("cc/1995/1328_1328_1328", "832.10"),
    "OAMal": ("cc/1995/3867_3867_3867", "832.102"),
    "OPAS": ("cc/1995/4964_4964_4964", "832.112.31"),
    "LAA": ("cc/1982/1676_1676_1676", "832.20"),
}
LANGUES = ("fr", "de", "it")
BASE = "https://www.fedlex.admin.ch"


def adresse_fichier(eli, date, langue):
    nom = "fedlex-data-admin-ch-eli-" + eli.replace("/", "-")
    return f"{BASE}/filestore/fedlex.data.admin.ch/eli/{eli}/{date}/{langue}/html/{nom}-{date}-{langue}-html-1.html"


def lire(adresse):
    requete = urllib.request.Request(adresse, headers={"User-Agent": "LAMal-Navigator (Hack Apertus)"})
    with urllib.request.urlopen(requete, timeout=30) as reponse:
        return reponse.read().decode("utf-8")


def dates_candidates(aujourdhui=None):
    jour = aujourdhui or datetime.date.today()
    annee, mois = jour.year, jour.month
    for _ in range(72):  # six ans en arrière au plus
        yield f"{annee:04d}{mois:02d}01"
        mois -= 1
        if mois == 0:
            annee, mois = annee - 1, 12


def version_en_vigueur(eli, langue):
    for date in dates_candidates():
        try:
            page = lire(adresse_fichier(eli, date, langue))
        except urllib.error.HTTPError as erreur:
            if erreur.code != 404:
                raise
            continue
        # Pour une date sans version, fedlex renvoie parfois la page d'accueil du site (sans erreur 404) :
        # on n'accepte que le vrai texte de loi, qui contient des articles.
        if re.search(r"<article[^>]*\bid=\"art_", page):
            return date, page
    raise RuntimeError(f"aucune version trouvée pour {eli} ({langue})")


def texte_brut(fragment):
    """HTML d'un article -> texte lisible : alinéas sur des lignes, notes de bas de page retirées."""
    t = re.sub(r"<div[^>]*class=\"[^\"]*footnotes[^\"]*\"[^>]*>.*?</div>", " ", fragment, flags=re.S)
    t = re.sub(r"<sup[^>]*>\s*<a[^>]*>.*?</a>\s*</sup>", "", t, flags=re.S)   # renvoi à une note
    t = re.sub(r"<sup[^>]*>(.*?)</sup>", r"\1 ", t, flags=re.S)                # numéro d'alinéa (1, 1bis…)
    t = re.sub(r"</dt>\s*", " ", t)                                            # « a. » sur la même ligne
    t = re.sub(r"</(?:p|dd|h\d|li|div)>|<br\s*/?>", "\n", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).replace("\xa0", " ")
    lignes = [re.sub(r"[ \t]+", " ", ligne).strip() for ligne in t.split("\n")]
    return "\n".join(ligne for ligne in lignes if ligne)


def articles(page):
    for m in re.finditer(r"<article[^>]*\bid=\"(art_[^\"]+)\"[^>]*>(.*?)</article>", page, flags=re.S):
        corps = m.group(2)
        entete = re.search(r"<h\d[^>]*>(.*?)</h\d>", corps, flags=re.S)  # « Art. 64 Participation… »
        titre = ""
        if entete:
            titre = texte_brut(entete.group(1)).replace("\n", " ")
            titre = re.sub(r"^(?:Art\.|Artikel|Articolo)\s*\S+\s*", "", titre).strip()
            corps = corps[:entete.start()] + corps[entete.end():]
        texte = texte_brut(corps)
        numero = m.group(1)[4:].replace("_", "")
        if not texte or re.fullmatch(r"(?:…|\.\.\.|Abrogé|Aufgehoben|Abrogato)\s*", texte):
            continue  # article abrogé
        yield m.group(1), numero, titre, texte


def main(sortie="data/lois.json"):
    print("telecharger_lois.py, version 3")
    base = []
    for loi, (eli, rs) in LOIS.items():
        for langue in LANGUES:
            date, page = version_en_vigueur(eli, langue)
            trouves = list(articles(page))
            print(f"{loi} ({langue}) : version du {date[6:]}.{date[4:6]}.{date[:4]}, {len(trouves)} articles")
            for ancre, numero, titre, texte in trouves:
                base.append({"loi": loi, "rs": rs, "langue": langue, "article": numero, "titre": titre,
                             "texte": texte, "version": date,
                             "url": f"{BASE}/eli/{eli}/{langue}#{ancre}"})
    with open(sortie, "w", encoding="utf-8") as f:
        json.dump(base, f, ensure_ascii=False, indent=0)
    print(f"{len(base)} articles enregistrés dans {sortie}")
    if not base:
        print("DIAGNOSTIC (aucun article) :", re.findall(r"<article[^>]{0,120}", page)[:3], page[:500])
    exemple = next((a for a in base if a["loi"] == "LAMal" and a["article"] == "64" and a["langue"] == "fr"), None)
    print("Contrôle, LAMal art. 64 :\n" + (exemple["texte"][:600] if exemple else "INTROUVABLE"))


if __name__ == "__main__":
    main(*sys.argv[1:])
