"""Génère un jeu d'évaluation synthétique de 300 phrases dont la bonne réponse est connue.

Chaque cas part d'un profil aléatoire (âge, NPA réel, franchise légale, statut, besoins),
puis est transformé en phrase avec des tournures variées : ordre mélangé, style formel ou
familier, nombres en lettres, fautes de frappe, quelques phrases en allemand et en italien.
Certains cas omettent volontairement une information : la réponse attendue est alors vide.

Graine fixe : le même fichier est produit à chaque exécution.
Usage (depuis track_2b) : python src/generer_eval.py
"""
import csv
import random
import re

from chatbot import FRANCHISES
from comparateur import DATA_DIR, classe_age, regions

GRAINE = 2026
NB_CAS = 300
SORTIE = DATA_DIR / "eval_synthetique.csv"
COLONNES = ["id", "phrase", "age", "npa", "franchise", "travaille_8h", "categories",
            "type_test", "note", "plusieurs_personnes", "vide_apres_controles"]

# --- Nombres en lettres (âges de 0 à 90, franchises légales) ------------------------------
UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
          "onze", "douze", "treize", "quatorze", "quinze", "seize"]
DIZAINES = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}


def en_lettres(n):
    if n <= 16:
        return UNITES[n]
    if n < 20:
        return "dix-" + UNITES[n - 10]
    if n < 70:
        d, u = n // 10 * 10, n % 10
        return DIZAINES[d] + ("" if u == 0 else " et un" if u == 1 else "-" + UNITES[u])
    if n < 80:
        return "soixante" + (" et onze" if n == 71 else "-" + en_lettres(n - 60))
    if n < 100:
        return "quatre-vingts" if n == 80 else "quatre-vingt-" + en_lettres(n - 80)
    if n < 1000:
        c, reste = n // 100, n % 100
        tete = "cent" if c == 1 else UNITES[c] + (" cents" if reste == 0 else " cent")
        return tete + ("" if reste == 0 else " " + en_lettres(reste))
    m, reste = n // 1000, n % 1000
    return ("mille" if m == 1 else UNITES[m] + " mille") + ("" if reste == 0 else " " + en_lettres(reste))


# --- Morceaux de phrase -------------------------------------------------------------------
STATUTS = {  # statut -> (travaille_8h attendu, formulations FR)
    "plein_temps": (True, ["je travaille à plein temps", "je bosse à 100%", "salarié à plein temps",
                           "j'exerce une activité salariée à temps complet", "je taffe à plein temps"]),
    "apprenti": (True, ["je suis apprenti", "je suis en apprentissage", "je fais un CFC en entreprise"]),
    "etudiant": (False, ["je suis étudiant", "je fais mes études à l'uni", "étudiante à plein temps"]),
    "eleve": (False, ["je suis au gymnase", "je suis encore à l'école"]),
    "chomeur": (False, ["je suis au chômage", "sans emploi en ce moment", "j'suis au chômage"]),
    "independant": (False, ["je suis indépendant", "je travaille à mon compte", "j'ai ma propre entreprise"]),
    "retraite": (False, ["je suis à la retraite", "retraité", "je suis pensionné"]),
}
BESOINS = {
    "lunettes": ["je porte des lunettes", "j'ai des lentilles", "je suis myope"],
    "dentaire": ["je vais souvent chez le dentiste", "j'ai besoin de soins dentaires",
                 "je dois faire un détartrage chaque année"],
    "medecines_alternatives": ["je vais chez l'ostéo", "je fais de l'acupuncture", "je consulte un naturopathe"],
    "hospitalisation": ["je veux une chambre privée à l'hôpital",
                        "j'aimerais être en demi-privé si je suis hospitalisé",
                        "je voudrais une bonne couverture en cas d'hospitalisation"],
}
DE = {"plein_temps": "ich arbeite Vollzeit", "apprenti": "ich mache eine Lehre", "etudiant": "ich studiere",
      "eleve": "ich gehe noch zur Schule", "chomeur": "ich bin arbeitslos",
      "independant": "ich bin selbständig", "retraite": "ich bin pensioniert",
      "lunettes": "ich trage eine Brille", "dentaire": "ich gehe oft zum Zahnarzt",
      "medecines_alternatives": "ich gehe zum Osteopathen",
      "hospitalisation": "ich möchte ein Privatzimmer im Spital"}
IT = {"plein_temps": "lavoro a tempo pieno", "apprenti": "sono apprendista", "etudiant": "sono studente",
      "eleve": "vado ancora a scuola", "chomeur": "sono disoccupato",
      "independant": "sono indipendente", "retraite": "sono in pensione",
      "lunettes": "porto gli occhiali", "dentaire": "vado spesso dal dentista",
      "medecines_alternatives": "vado dall'osteopata",
      "hospitalisation": "vorrei una camera privata in ospedale"}


def choisir_statut(rng, age):
    if age < 15:
        return "enfant"
    if age <= 19:
        options = ["eleve", "apprenti", "etudiant", "plein_temps", "partiel"]
    elif age <= 25:
        options = ["etudiant", "apprenti", "plein_temps", "partiel", "chomeur"]
    elif age < 65:
        options = ["plein_temps", "plein_temps", "partiel", "independant", "chomeur"]
    else:
        options = ["retraite", "retraite", "retraite", "partiel"]
    return rng.choice(options)


def faute_de_frappe(rng, phrase):
    """Inverse, supprime ou double une lettre dans un mot d'au moins 5 lettres (jamais un nombre)."""
    mots = phrase.split(" ")
    candidats = [i for i, m in enumerate(mots) if len(m) >= 5 and m.isalpha()]
    if not candidats:
        return phrase
    i = rng.choice(candidats)
    m, j = mots[i], rng.randrange(1, len(mots[i]) - 1)
    mots[i] = rng.choice([m[:j] + m[j + 1] + m[j] + m[j + 2:], m[:j] + m[j + 1:], m[:j] + m[j] + m[j:]])
    return " ".join(mots)


def generer_cas(rng, numero, communes):
    age = rng.randint(0, 90)
    npa, commune = rng.choice(communes)
    franchise = rng.choice(FRANCHISES[classe_age(age)])
    statut = choisir_statut(rng, age)
    besoins = rng.sample(list(BESOINS), rng.choice([0, 0, 1, 1, 2]))
    attendu = {"age": age, "npa": npa, "franchise": franchise, "categories": besoins}
    notes = []

    if statut == "enfant":
        travaille = False
    elif statut == "partiel":
        heures = rng.choice([4, 5, 6, 8, 10, 12, 16, 20, 24])
        travaille = heures >= 8
    else:
        travaille = STATUTS[statut][0]

    langue = rng.choices(["fr", "de", "it"], weights=[84, 8, 8])[0]
    style = rng.choice(["neutre", "formel", "familier"]) if langue == "fr" else langue
    lettres = langue == "fr" and rng.random() < 0.2
    omission = rng.choices(["aucune", "franchise", "statut", "age", "npa"], weights=[70, 9, 9, 4, 8])[0]
    if omission in ("statut", "age") and statut == "enfant":
        omission = "aucune"  # sans l'âge, rien n'indiquerait qu'il s'agit d'un enfant

    def nombre(n):
        return en_lettres(n) if lettres else str(n)

    morceaux = []
    # Âge
    if omission != "age":
        if statut == "enfant":
            sujet = rng.choice(["Mon fils", "Ma fille"]) if langue == "fr" else None
            morceaux.append({"fr": f"{sujet} a {nombre(age)} ans",
                             "de": f"Mein Kind ist {age} Jahre alt",
                             "it": f"Mio figlio ha {age} anni"}[langue])
        else:
            morceaux.append({"fr": {"neutre": f"j'ai {nombre(age)} ans", "formel": f"je suis âgé de {nombre(age)} ans",
                                    "familier": f"{nombre(age)} ans"}[style] if langue == "fr" else "",
                             "de": f"ich bin {age} Jahre alt", "it": f"ho {age} anni"}[langue])
    else:
        attendu["age"] = None
        notes.append("âge non donné")
    # Lieu (la commune fait foi : sans NPA écrit, le NPA attendu est vide)
    if omission == "npa":
        morceaux.append({"fr": f"j'habite à {commune}", "de": f"ich wohne in {commune}",
                         "it": f"abito a {commune}"}[langue])
        attendu["npa"] = None
        notes.append("commune sans NPA")
    else:
        morceaux.append({"fr": rng.choice([f"j'habite à {commune} ({npa})", f"{npa} {commune}",
                                           f"je réside à {npa} {commune}", f"code postal {npa}",
                                           f"on habite à {npa}" if statut == "enfant" else f"je vis à {commune}, {npa}"]),
                         "de": f"wohne in {npa} {commune}", "it": f"abito a {npa} {commune}"}[langue])
    # Franchise
    if omission != "franchise":
        morceaux.append({"fr": rng.choice([f"franchise {nombre(franchise)}", f"je veux une franchise de {nombre(franchise)}",
                                           f"je souhaiterais une franchise de {nombre(franchise)} francs"]),
                         "de": f"Franchise {franchise}", "it": f"franchigia {franchise}"}[langue])
    else:
        attendu["franchise"] = None
        notes.append("franchise non donnée")
    # Statut
    if statut == "partiel":
        if omission == "statut":
            travaille = None
        else:
            morceaux.append({"fr": rng.choice([f"je travaille {heures} heures par semaine",
                                               f"temps partiel, {heures}h par semaine"]),
                             "de": f"ich arbeite {heures} Stunden pro Woche",
                             "it": f"lavoro {heures} ore alla settimana"}[langue])
            notes.append(f"{heures} h/semaine")
    elif statut != "enfant":
        if omission == "statut":
            travaille = None
            notes.append("statut non donné")
        else:
            morceaux.append({"fr": rng.choice(STATUTS[statut][1]), "de": DE[statut], "it": IT[statut]}[langue])
    attendu["travaille_8h"] = travaille
    # Besoins
    for b in besoins:
        morceaux.append({"fr": rng.choice(BESOINS[b]), "de": DE[b], "it": IT[b]}[langue])

    morceaux = [m for m in morceaux if m]
    premier = morceaux.pop(0) if statut == "enfant" and omission != "age" else None
    rng.shuffle(morceaux)  # ordre différent (le sujet « Mon fils… » reste en tête)
    if premier:
        morceaux.insert(0, premier)
    phrase = ", ".join(morceaux)
    phrase = phrase[0].upper() + phrase[1:]
    fautes = langue == "fr" and rng.random() < 0.2
    if fautes:
        for _ in range(rng.choice([1, 2])):
            phrase = faute_de_frappe(rng, phrase)
    if style == "familier" and rng.random() < 0.5:
        phrase = phrase.lower()

    type_test = langue if langue != "fr" else ("enfant" if statut == "enfant" else style)
    if lettres:
        notes.append("nombres en lettres")
    if fautes:
        notes.append("fautes de frappe")
    return {
        "id": str(numero), "phrase": phrase,
        "age": "" if attendu["age"] is None else attendu["age"],
        "npa": "" if attendu["npa"] is None else attendu["npa"],
        "franchise": "" if attendu["franchise"] is None else attendu["franchise"],
        "travaille_8h": "" if travaille is None else str(travaille).lower(),
        "categories": ";".join(besoins), "type_test": type_test,
        "note": f"statut {statut}" + (f" ; {' ; '.join(notes)}" if notes else ""),
        "plusieurs_personnes": "false", "vide_apres_controles": "",
    }


def main():
    rng = random.Random(GRAINE)
    # NPA réels avec le nom de leur commune (sans le canton ajouté par l'OFSP, ex. « Cugy (VD) »)
    communes = sorted({(int(r.npa), re.sub(r"\s*\([A-Z]{2}\)$", "", r.commune))
                       for r in regions.itertuples()})
    cas = [generer_cas(rng, i, communes) for i in range(1, NB_CAS + 1)]
    with open(SORTIE, "w", encoding="utf-8", newline="") as f:
        ecrivain = csv.DictWriter(f, fieldnames=COLONNES, lineterminator="\r\n")
        ecrivain.writeheader()
        ecrivain.writerows(cas)
    print(f"{len(cas)} cas écrits dans {SORTIE}")


if __name__ == "__main__":
    main()
