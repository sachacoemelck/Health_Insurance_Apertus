"""Recherche dans les vrais textes de loi (RAG : recherche, puis rédaction par Apertus).

1. La base `data/lois.json` contient les articles officiels de la LAMal, de l'OAMal, de l'OPAS et de
   la LAA en français, allemand et italien (créée par telecharger_lois.py depuis fedlex.admin.ch).
2. Chaque article est découpé en alinéas : on cherche l'alinéa précis qui répond, pas tout l'article.
3. La recherche est une recherche par mots (BM25, la méthode classique des moteurs de recherche) :
   rapide, sans modèle supplémentaire, et explicable. Apertus 8B peut l'aider en traduisant la question
   en mots-clés juridiques français (« ambulance » -> « transport, sauvetage »).
4. Les alinéas trouvés sont donnés à Apertus 70B avec un numéro [L1], [L2]… ; Python vérifie ensuite
   que chaque numéro cité existe et le remplace par la référence officielle (loi, article, alinéa, lien).
"""
import json
import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

CHEMIN = Path(__file__).resolve().parent.parent / "data" / "lois.json"

NOMS = {  # nom de chaque loi dans chaque langue
    "LAMal": {"fr": "LAMal", "de": "KVG", "it": "LAMal", "en": "LAMal"},
    "OAMal": {"fr": "OAMal", "de": "KVV", "it": "OAMal", "en": "OAMal"},
    "OPAS": {"fr": "OPAS", "de": "KLV", "it": "OPre", "en": "OPAS"},
    "LAA": {"fr": "LAA", "de": "UVG", "it": "LAINF", "en": "LAA"},
}
MOTS = {"fr": ("art.", "al."), "de": ("Art.", "Abs."), "it": ("art.", "cpv."), "en": ("art.", "para.")}

# Articles utiles à une personne assurée. Le reste (tarifs, commissions, procédures entre assureurs,
# prix des médicaments…) est écarté : il noierait la recherche sans répondre aux questions des gens.
ARTICLES_UTILES = {
    "LAMal": "1a 3 4 5 7 8 10 24 25 25a 26 27 28 29 30 31 32 34 41 42 42a 52a 56a 61 61a 62 64 64a 65",
    "OAMal": "1 2 3 4 7 8 9 11 33 35a 36 89 90 91 93 94 95 96 97 99 100 101 103 104 104a 105 105b 105l 106",
    "OPAS": "4a 5 6 7 9b 9c 10 11 11a 11b 11c 12 12a 12b 12c 12d 12e 13 14 15 16 17 18 19 20 20a 25 26 27 38a",
    "LAA": "1a 3 4 8 10 13",
}
ARTICLES_UTILES = {loi: set(liste.split()) for loi, liste in ARTICLES_UTILES.items()}

# Fedlex place le titre de certains articles hors de l'article : on le complète (fr, de, it).
TITRES_AJOUTES = {
    ("LAMal", "64"): ("Participation aux coûts", "Kostenbeteiligung", "Partecipazione ai costi"),
    ("LAMal", "64a"): ("Non-paiement des primes et des participations aux coûts",
                       "Nichtbezahlung von Prämien und Kostenbeteiligungen",
                       "Mancato pagamento dei premi e delle partecipazioni ai costi"),
    ("OPAS", "4a"): ("Prestations des pharmaciens", "Leistungen der Apotheker", "Prestazioni dei farmacisti"),
    ("OPAS", "5"): ("Physiothérapie", "Physiotherapie", "Fisioterapia"),
    ("OPAS", "6"): ("Ergothérapie", "Ergotherapie", "Ergoterapia"),
    ("OPAS", "9b"): ("Conseils nutritionnels", "Ernährungsberatung", "Consulenza nutrizionale"),
    ("OPAS", "9c"): ("Conseils aux diabétiques", "Diabetesberatung", "Consulenza ai diabetici"),
    ("OPAS", "11a"): ("Neuropsychologie", "Neuropsychologie", "Neuropsicologia"),
    ("OPAS", "11b"): ("Psychothérapie pratiquée par des psychologues", "Psychologische Psychotherapie",
                      "Psicoterapia psicologica"),
    ("OPAS", "11c"): ("Podologie", "Podologie", "Podologia"),
    ("OPAS", "38a"): ("Quote-part des médicaments (originaux et génériques)",
                      "Selbstbehalt bei Arzneimitteln (Originale und Generika)",
                      "Aliquota percentuale dei medicamenti (originali e generici)"),
}
_LANGUES_TITRES = ("fr", "de", "it")

# Langue des textes montrés à Apertus : celle de la personne si fedlex l'a, sinon le français.
LANGUE_TEXTE = {"fr": "fr", "de": "de", "it": "it"}

_VIDES = set("""
le la les un une des du de d l et ou en au aux a à est sont pour par sur dans avec sans ce cet cette ces
qui que quoi dont mon ma mes ton ta tes son sa ses notre nos votre vos leur leurs je tu il elle on nous
vous ils elles me te se lui y ne pas plus est-ce suis es sommes etes être avoir ai as avons avez ont
si mais donc car comme quand combien comment quel quelle quels quelles est-il faut peut peux
der die das ein eine einer eines einem den dem des und oder in im an am auf aus bei mit nach von vor zu
zum zur für über unter ist sind bin bist war wird werden kann ich du er sie es wir ihr mein meine
nicht kein keine was wie wann wer wo auch noch nur schon wenn dass ob
il lo la i gli le un una uno di da del della dei delle in nel nella con su per tra fra e o è sono
sono io tu lui lei noi voi loro mio mia non che chi come quando quanto se ma anche
the a an of to in on at for by with without and or is are am be been do does did i you he she it we
they my your his her our their not what how when who which can could if my me
""".split())


def _sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


def mots(texte):
    """Mots utiles, sans accents, raccourcis à leur racine (« franchises » et « franchise » -> « franch »)."""
    resultat = []
    for mot in re.findall(r"[a-zà-ÿß]+", (texte or "").lower()):
        if mot in _VIDES or len(mot) < 3:
            continue
        resultat.append(_sans_accents(mot)[:6])
    return resultat


_ALINEA = re.compile(r"^(\d+(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies)?)\s+(\S.*)$")


def alineas(texte):
    """« 1 … \\n 2 … \\n a. … » -> [("1", "…"), ("2", "… a. …")] ; un article sans numéro -> [("", texte)]."""
    blocs = []
    for ligne in texte.split("\n"):
        m = _ALINEA.match(ligne.strip())
        if m:
            blocs.append([m.group(1), m.group(2)])
        elif blocs:
            blocs[-1][1] += " " + ligne.strip()
        else:
            blocs.append(["", ligne.strip()])
    return [(numero, re.sub(r"\s+", " ", t).strip()) for numero, t in blocs if t.strip()]


class Index:
    """BM25 sur les alinéas d'une langue (le titre de l'article compte pour chacun de ses alinéas)."""

    def __init__(self, passages, k1=1.4, b=0.75):
        self.passages = passages
        self.docs = [Counter(mots(p["titre"]) * 2 + mots(p["texte"])) for p in passages]
        self.longueurs = [sum(d.values()) for d in self.docs]
        self.moyenne = sum(self.longueurs) / max(len(self.docs), 1)
        frequences = Counter(m for d in self.docs for m in d)
        n = len(self.docs)
        self.idf = {m: math.log(1 + (n - f + 0.5) / (f + 0.5)) for m, f in frequences.items()}
        self.k1, self.b = k1, b

    def scores(self, requete):
        termes = set(mots(requete))
        resultat = {}
        for i, (doc, longueur) in enumerate(zip(self.docs, self.longueurs)):
            s = 0.0
            for t in termes & doc.keys():
                tf = doc[t]
                s += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * longueur / self.moyenne))
            if s:
                resultat[(self.passages[i]["loi"], self.passages[i]["article"], self.passages[i]["alinea"])] = s
        return resultat


@lru_cache(maxsize=1)
def base(chemin=None):
    """{langue: Index} et {(loi, article, alinéa, langue): passage}. Vide si la base n'existe pas."""
    chemin = Path(chemin or CHEMIN)
    if not chemin.exists():
        return {}, {}
    par_langue, tous = {}, {}
    for art in json.loads(chemin.read_text(encoding="utf-8")):
        if art["loi"] in ARTICLES_UTILES and art["article"] not in ARTICLES_UTILES[art["loi"]]:
            continue
        titre = art["titre"]
        ajout = TITRES_AJOUTES.get((art["loi"], art["article"]))
        if not titre and ajout and art["langue"] in _LANGUES_TITRES:
            titre = ajout[_LANGUES_TITRES.index(art["langue"])]
        for numero, texte in alineas(art["texte"]):
            p = {"loi": art["loi"], "article": art["article"], "alinea": numero, "titre": titre,
                 "texte": texte, "url": art["url"], "langue": art["langue"]}
            par_langue.setdefault(art["langue"], []).append(p)
            tous[(art["loi"], art["article"], numero, art["langue"])] = p
    return {langue: Index(ps) for langue, ps in par_langue.items()}, tous


# Mots de tous les jours -> termes de la loi (ajoutés à la question, dans chaque langue). La loi dit
# « participation aux coûts » là où les gens disent « franchise » ou « quote-part ».
SYNONYMES = [
    (r"franchise|quote-part|quote part", "participation aux coûts"),
    (r"franchise|selbstbehalt", "Kostenbeteiligung"),
    (r"franchigia|aliquota|quota parte", "partecipazione ai costi"),
    (r"accouch|naissance|enceinte", "maternité grossesse accouchement"),
    (r"geburt|schwanger", "Mutterschaft Niederkunft Schwangerschaft"),
    (r"parto|nascita|incinta", "maternità gravidanza parto"),
    (r"ambulance", "transport sauvetage"),
    (r"ambulanz|krankenwagen", "Transport Rettung"),
    (r"ambulanza", "trasporto salvataggio"),
    (r"résili|quitter (?:mon|ma) (?:caisse|assur)", "changement d'assureur"),
    (r"kündig", "Wechsel des Versicherers"),
    (r"disdet|disdire", "cambiamento dell'assicuratore"),
    (r"vacances|étranger", "prestations à l'étranger urgence"),
    (r"ferien|ausland", "Leistungen im Ausland Notfall"),
    (r"vacanz|estero", "prestazioni all'estero urgenza"),
    (r"médecin de famille|hmo|télémédecine|telmed", "choix limité du fournisseur de prestations"),
    (r"hausarzt|telmed|hmo", "eingeschränkte Wahl des Leistungserbringers"),
    (r"medico di famiglia|telmed|hmo", "scelta limitata del fornitore di prestazioni"),
    (r"n.importe quel hôpital|choisir (?:mon |l.|un )?hôpital", "hôpital répertorié traitement hospitalier"),
    (r"hospitalis", "contribution aux frais de séjour hospitalier"),
    (r"dentist|dents", "soins dentaires"),
    (r"zahnarzt|zähne|zahn", "Zahnärztliche Behandlungen"),
    (r"dentist|denti", "cure dentarie"),
    (r"\b(?:18|19|2[0-5]) ans|jeune adulte", "jeunes adultes enfants primes"),
    (r"délai|résili", "préavis"),
    (r"refuser de m.assurer|accepter", "choix de l'assureur"),
    (r"déménag|autre canton", "lieu de résidence primes"),
    (r"umzieh|anderen kanton", "Wohnort Prämien"),
    (r"trasloc|altro cantone", "luogo di residenza premi"),
    (r"avortement|\bivg\b|interrompre (?:ma|une) grossesse", "interruption de grossesse non punissable"),
    (r"abtreibung|schwangerschaftsabbruch", "straflosen Abbruch der Schwangerschaft"),
    (r"aborto|interruzione (?:della )?gravidanza", "interruzione non punibile della gravidanza"),
    (r"naître|nouveau-né|bébé|naissance", "naissance obligation de s'assurer trois mois"),
    (r"lunettes|lentilles", "verres de lunettes moyens et appareils"),
    (r"brille|kontaktlinsen", "Brillengläser Mittel und Gegenstände"),
    (r"occhiali|lenti", "lenti per occhiali mezzi e apparecchi"),
]


# Anglais : pas de texte de loi officiel en anglais. Apertus 8B traduit d'habitude la question en
# mots-clés français ; ces équivalents servent de filet s'il ne répond pas.
SYNONYMES_EN = [
    (r"dental|dentist|teeth", "soins dentaires"),
    (r"deductible|co-?pay|excess", "participation aux coûts franchise quote-part"),
    (r"birth|pregnan|maternity|childbirth", "maternité grossesse accouchement"),
    (r"accident", "accidents couverture des accidents"),
    (r"unemploy", "assurance-chômage suspension couverture des accidents"),
    (r"ambulance", "transport sauvetage"),
    (r"glasses|contact lens", "verres de lunettes moyens et appareils"),
    (r"cancel|switch|change (?:my )?insurer|terminate", "changement d'assureur préavis choix de l'assureur"),
    (r"abroad|holiday|vacation|travel", "prestations à l'étranger urgence"),
    (r"abortion|termination of pregnancy", "interruption de grossesse non punissable"),
    (r"newborn|baby|moving to switzerland|move to switzerland", "obligation de s'assurer trois mois naissance domicile"),
    (r"vaccin", "vaccinations prophylactiques"),
    (r"physio", "physiothérapie"),
    (r"psycho|therap", "psychothérapie"),
    (r"generic|medicine|drug", "médicaments génériques quote-part"),
    (r"hospital", "traitement hospitalier contribution aux frais de séjour hospitalier"),
    (r"premium", "primes"),
    (r"sick|illness|refuse|reject", "choix de l'assureur"),
]


def _termes_ajoutes(question):
    return [terme for motif, terme in SYNONYMES + SYNONYMES_EN if re.search(motif, question or "", re.IGNORECASE)]


def enrichir(question):
    return " ".join([question or ""] + _termes_ajoutes(question))


def _simple(texte):
    return " ".join(re.findall(r"[a-z]+", _sans_accents((texte or "").lower())))


def chercher(question, code="fr", mots_cles_fr="", n=8, chemin=None, par_article=3, budget=5000):
    """Les n alinéas les plus proches de la question, dans la langue de la personne (sinon français).
    La recherche combine la question elle-même (dans sa langue) et les mots-clés français d'Apertus 8B."""
    index, tous = base(chemin)
    if not index:
        return []
    langue = LANGUE_TEXTE.get(code, "fr")
    # Expressions exactes de la loi (« participation aux coûts ») : un alinéa qui les contient telles
    # quelles passe devant un alinéa qui n'en contient que des mots épars.
    expressions = [_simple(t) for t in _termes_ajoutes(question) if " " in t.strip()]
    question = enrichir(question)
    total = Counter()
    if langue in index:
        total.update(index[langue].scores(question))
    if "fr" in index and (mots_cles_fr or langue != "fr"):
        total.update(index["fr"].scores(f"{mots_cles_fr} {question if langue == 'fr' else ''}"))
    for cle in list(total):
        textes = [_simple(tous[(*cle, l)]["texte"]) for l in {langue, "fr"} if (*cle, l) in tous]
        if any(e in t for e in expressions for t in textes):
            total[cle] *= 1.3
    meilleurs, compte = [], Counter()
    for cle, s in total.most_common():  # au plus `par_article` alinéas du même article : plus de variété
        if s <= 0 or len(meilleurs) == n:
            break
        if compte[cle[:2]] < par_article:
            meilleurs.append(cle)
            compte[cle[:2]] += 1
    passages = []
    for loi, article, alinea in meilleurs:
        p = tous.get((loi, article, alinea, langue)) or tous.get((loi, article, alinea, "fr"))
        if p and (not passages or sum(len(x["texte"]) for x in passages) + len(p["texte"]) <= budget):
            passages.append(p)  # au plus ~5000 caractères pour Apertus : réponse plus rapide et ciblée
    return passages


def reference(p, code="fr"):
    art, al = MOTS.get(code, MOTS["fr"])
    texte = f"{NOMS[p['loi']].get(code, p['loi'])} {art} {p['article']}"
    return texte + (f" {al} {p['alinea']}" if p["alinea"] else "")


def texte_passages(passages, code="fr"):
    """Texte des alinéas pour Apertus, numérotés [L1], [L2]…"""
    return "\n".join(f"[L{i}] {reference(p, code)} ({p['titre']}) : {p['texte']}"
                     for i, p in enumerate(passages, 1))


def lien(p, code="fr"):
    return f"[{reference(p, code)}]({p['url']})"


PROMPT_MOTS_CLES = """Tu aides à chercher dans la loi suisse sur l'assurance-maladie (LAMal, OAMal, OPAS, LAA).
Donne 4 à 8 mots-clés EN FRANÇAIS, avec les termes qu'utiliserait le texte de loi, pour trouver la
réponse à la question. Exemples : « ambulance » -> transport, sauvetage ; « accouchement » ->
maternité, grossesse, participation aux coûts. Réponds uniquement par les mots, séparés par des virgules."""


def mots_cles(appeler_8b, question):
    """Mots-clés juridiques français proposés par Apertus 8B ; chaîne vide en cas d'échec."""
    try:
        brut = appeler_8b(PROMPT_MOTS_CLES, question) or ""
    except Exception:
        return ""
    return " ".join(re.findall(r"[a-zà-ÿA-ZÀ-Ÿ-]+", brut))[:300]
