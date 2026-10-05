"""Chatbot LAMal : Apertus comprend la situation, pandas calcule les primes.

1. L'utilisateur décrit sa situation en langage libre.
2. Apertus extrait un profil JSON (npa, commune, age, franchise, travaille_8h).
3. Python déduit canton et région du NPA (fichier OFSP), vérifie le profil
   et appelle comparer() sur les données OFSP.
4. Python résume les faits ; Apertus les explique en français, sans calculer.
   Python vérifie que chaque montant cité figure dans les faits.
"""
import json
import os
import re
import sys
import unicodedata

from dotenv import load_dotenv
from openai import OpenAI

from comparateur import (MODELES, QUOTE_PART_MAX, classe_age, communes_du_npa,
                         comparer, regions)

load_dotenv()

FRANCHISES = {
    "AKA_01_KIN": [0, 100, 200, 300, 400, 500, 600],
    "AKA_02_JUG": [300, 500, 1000, 1500, 2000, 2500],
    "AKA_03_ERW": [300, 500, 1000, 1500, 2000, 2500],
}

PROMPT_EXTRACTION = """Tu extrais le profil d'assurance maladie (LAMal) d'une personne vivant en Suisse.
Réponds UNIQUEMENT avec un objet JSON, sans texte autour, avec ces clés :
- "npa" : code postal suisse à 4 chiffres (entier), ou null si non mentionné
- "commune" : nom de la commune de domicile si la personne le cite, sinon null
- "age" : âge en années (entier)
- "franchise" : franchise annuelle en CHF (entier), ou null si non mentionnée
- "travaille_8h" : true si la personne travaille au moins 8 heures par semaine chez le même employeur, false sinon, null si rien ne permet de le déduire.
  Règles : salarié, apprenti, plein temps, temps partiel d'au moins 8 heures par semaine = true ;
  étudiant, élève, retraité, chômeur, sans emploi, indépendant, moins de 8 heures par semaine = false.
- "plusieurs_personnes" : true si la phrase décrit plusieurs personnes à assurer (ex. « ma femme et moi »), sinon false
Mets null pour toute information absente. N'invente rien.
Recopie les nombres tels qu'ils sont écrits, même s'ils te semblent impossibles."""

# Franchise demandée en mots (« la plus haute », « minimale ») -> valeur légale selon l'âge
MOTIF_FRANCHISE_MAX = re.compile(r"plus\s+(?:haute|élevée)|\bmax", re.IGNORECASE)
MOTIF_FRANCHISE_MIN = re.compile(r"plus\s+basse|\bmin", re.IGNORECASE)
# Montants à écarter avant de chercher un NPA dans la phrase (1000, 2000, 2500 sont aussi des NPA)
MOTIF_MONTANT = re.compile(r"franchise\s*(?:de\s*)?\d{3,4}|\d{3,4}\s*(?:CHF|francs|fr\.)",
                           re.IGNORECASE)
AGE_SANS_EMPLOI = 15  # en dessous, travaille_8h = false sans poser la question
# Priorité de la personne : prompt séparé (l'ajouter à PROMPT_EXTRACTION dégradait travaille_8h)
PROMPT_PRIORITE = """Tu identifies la priorité d'une personne qui choisit son assurance maladie de base en Suisse.
Réponds UNIQUEMENT avec un objet JSON {"priorite": ...}, sans texte autour :
"prix" si elle veut avant tout payer le moins possible ;
"medecin_famille" si elle veut passer par un médecin de famille ou une HMO ;
"libre_choix" si elle veut choisir librement ses médecins ou consulter directement un spécialiste ;
null si elle n'exprime aucune de ces priorités."""

# Garde-fou : une priorité n'est gardée que si un mot lié figure dans la phrase
MOTS_PRIORITE = {
    "prix": r"moins cher|le moins possible|[ée]conomi|budget|pas cher|meilleur prix",
    "medecin_famille": r"m[ée]decin de famille|m[ée]decin traitant|g[ée]n[ée]raliste|\bhmo\b",
    "libre_choix": r"libre choix|choisir (?:librement|mes|mon)|directement (?:chez |un |le )?"
                   r"sp[ée]cialiste|acc[èe]s direct",
}

PROMPT_INTRO = """Tu présentes à une personne vivant en Suisse trois propositions d'assurance maladie de base (LAMal), affichées juste en dessous de ton texte.
Règles strictes :
- Utilise UNIQUEMENT les faits fournis. N'ajoute aucune information extérieure.
- Ne fais AUCUN calcul. Ne cite AUCUN montant qui n'apparaît pas tel quel dans les faits :
  recopie les montants exactement (avec les centimes) ou n'en cite pas.
- Pour un modèle, reprends uniquement sa contrepartie fournie : n'ajoute aucun avantage ni inconvénient.
- Ne recommande aucune proposition : présente les compromis entre le prix et les contraintes.
- Si une priorité est indiquée, commence par la proposition qui y correspond.
- Tutoie l'utilisateur. Écris en {langue} simple.
- Écris 2 à 3 phrases au total, en un seul paragraphe, sans liste ni tableau."""

PROMPT_EXPLICATION = """Tu aides une personne vivant en Suisse à choisir son assurance maladie de base (LAMal).
Règles strictes :
- Utilise UNIQUEMENT les faits fournis. N'ajoute aucune information extérieure.
- Ne fais AUCUN calcul et ne cite AUCUN montant qui n'apparaît pas tel quel dans les faits.
- Ne définis aucun terme qui n'est pas défini dans les faits. Pour décrire un modèle,
  reprends uniquement sa définition fournie.
- N'attribue à un modèle aucun avantage ni inconvénient qui n'est pas dans sa définition.
- Pour le Modèle alternatif, dis SEULEMENT de vérifier les conditions exactes chez
  l'assureur. N'ajoute rien d'autre sur ce modèle : ni avantage, ni liberté, ni contrainte.
- Ne tire aucune conclusion du nom d'un modèle ou d'un produit (par exemple « flex »,
  « smart », « care ») : seule la définition fournie compte.
- Tutoie l'utilisateur. Écris en {langue} simple.
- Écris 5 à 6 phrases au total, en un seul paragraphe, sans liste ni tableau.
Explique les compromis : le prix face aux contraintes de chaque modèle, et le risque
d'une franchise élevée (le coût maximal annuel si tu as beaucoup de frais médicaux)."""


def en_langue(prompt, langue):
    """Prompt avec la langue de réponse voulue (ex. « français », « allemand »)."""
    return prompt.replace("{langue}", langue)


def lire_config():
    config = {k: os.getenv(k) for k in ("LLM_NAME", "LLM_BASE_URL", "LLM_API_KEY")}
    manquantes = [k for k, v in config.items() if not v]
    if manquantes:
        sys.exit(f"Variables manquantes : {', '.join(manquantes)}. "
                 "Copie .env.example vers .env et remplis-le.")
    # Modèle facultatif pour l'explication (ex. 70B, qui suit mieux les consignes)
    config["LLM_NAME_RESTITUTION"] = os.getenv("LLM_NAME_RESTITUTION") or config["LLM_NAME"]
    return config


def demander_llm(client, modele, systeme, message):
    reponse = client.chat.completions.create(
        model=modele,
        messages=[{"role": "system", "content": systeme},
                  {"role": "user", "content": message}],
        temperature=0,
    )
    return reponse.choices[0].message.content


def extraire_json(texte):
    """Récupère le premier objet JSON de la réponse du LLM (vide si illisible)."""
    trouve = re.search(r"\{.*\}", texte or "", re.DOTALL)
    if not trouve:
        return {}
    try:
        return json.loads(trouve.group())
    except json.JSONDecodeError:
        return {}


def demander(question, valides, convertir=str, aide=None):
    while True:
        reponse = input(f"{question} ").strip()
        try:
            valeur = convertir(reponse)
        except ValueError:
            valeur = None
        if valeur in valides:
            return valeur
        print(f"  {aide or 'Choix possibles : ' + ', '.join(str(v) for v in valides)}")


def entier(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return None


def nom_simple(commune):
    """'Cugy (VD)' -> 'cugy', 'Neuchâtel' -> 'neuchatel' : sans canton ajouté par l'OFSP,
    sans accents ni majuscules."""
    nom = re.sub(r"\s*\([A-Z]{2}\)$", "", str(commune).strip())
    nom = unicodedata.normalize("NFD", nom).encode("ascii", "ignore").decode()
    return nom.casefold()


def communes_par_nom(nom):
    """Communes (une ligne par n° OFS) dont le nom correspond à celui donné, sinon vide."""
    if not nom:
        return regions.iloc[0:0]
    trouvees = regions[regions["commune"].map(nom_simple) == nom_simple(nom)]
    return trouvees.drop_duplicates("no_ofs").reset_index(drop=True)


def choisir_commune(communes, message, demander=demander):
    """Liste numérotée des communes ; renvoie commune, canton et région choisis."""
    print(f"\n{message}")
    for i, c in enumerate(communes.itertuples(), 1):
        canton = "" if c.commune.endswith(f"({c.canton})") else f" ({c.canton})"
        print(f"  {i}. {c.commune}{canton}")
    choix = demander("Numéro de ta commune ?", range(1, len(communes) + 1), int,
                     aide=f"Tape un numéro entre 1 et {len(communes)}.")
    c = communes.iloc[choix - 1]
    return c["commune"], c["canton"], int(c["region"])


def localiser(npa=None, commune=None):
    """Lieu sans interaction. Renvoie (commune, canton, région) si le lieu est sûr, les
    communes entre lesquelles choisir (DataFrame) s'il est ambigu, ou None s'il est inconnu.
    La commune fait foi (OFSP), pas le NPA."""
    if npa is None:
        communes = communes_par_nom(commune)
    else:
        communes = communes_du_npa(npa)
        if commune:
            citee = communes[communes["commune"].map(nom_simple) == nom_simple(commune)]
            if len(citee) == 1:
                communes = citee
        if not communes.empty and len(communes[["canton", "region"]].drop_duplicates()) == 1:
            # Une seule région possible pour ce NPA : inutile de demander la commune
            c = communes.iloc[0]
            return " / ".join(communes["commune"]), c["canton"], int(c["region"])
    if communes.empty:
        return None
    if len(communes) == 1:
        c = communes.iloc[0]
        return c["commune"], c["canton"], int(c["region"])
    return communes


def trouver_commune(npa, commune_citee=None, demander=demander):
    """Déduit commune, canton et région d'un NPA ; demande la commune si le NPA est ambigu."""
    lieu = localiser(npa, commune_citee)
    if isinstance(lieu, tuple):
        return lieu
    return choisir_commune(lieu, f"Le NPA {npa} couvre des communes de régions de primes "
                                 "différentes.\nC'est ta commune de domicile qui fait foi :",
                           demander)


def npa_dans_phrase(phrase):
    """Seul nombre à 4 chiffres de la phrase qui existe comme NPA (montants écartés), sinon None."""
    texte = MOTIF_MONTANT.sub(" ", phrase or "")
    candidats = {int(n) for n in re.findall(r"(?<!\d)\d{4}(?!\d)", texte)} & set(regions["npa"])
    return candidats.pop() if len(candidats) == 1 else None


def regles_age(p, phrase):
    """Règles qui dépendent de l'âge : franchise en mots, pas d'emploi avant 15 ans."""
    if p["age"] is None:
        return
    franchises = FRANCHISES[classe_age(p["age"])]
    if "franchise" in (phrase or "").lower():
        if MOTIF_FRANCHISE_MAX.search(phrase):
            p["franchise"] = max(franchises)
        elif MOTIF_FRANCHISE_MIN.search(phrase):
            p["franchise"] = min(franchises)
    if p["age"] < AGE_SANS_EMPLOI:
        p["travaille_8h"] = False


def nettoyer_profil(profil, phrase=""):
    """Contrôles Python sans interaction : corrige ce qui peut l'être, met None ce qui est
    invalide ou douteux (le bot le redemandera)."""
    travaille = profil.get("travaille_8h")
    p = {"npa": entier(profil.get("npa")), "commune": profil.get("commune"),
         "age": entier(profil.get("age")), "franchise": entier(profil.get("franchise")),
         "travaille_8h": travaille if isinstance(travaille, bool) else None,
         "plusieurs_personnes": profil.get("plusieurs_personnes") is True}
    # Le modèle ne doit jamais deviner un NPA : il n'est gardé que s'il figure dans la phrase
    if phrase and p["npa"] is not None and not re.search(rf"(?<!\d){p['npa']}(?!\d)", phrase):
        p["npa"] = None
    if p["npa"] not in set(regions["npa"]):
        p["npa"] = npa_dans_phrase(phrase)
    if p["age"] not in range(0, 121) or p["plusieurs_personnes"]:
        p["age"] = None  # âge impossible, ou on ne sait pas de quelle personne il s'agit
    regles_age(p, phrase)
    toutes = set().union(*FRANCHISES.values())
    valides = FRANCHISES[classe_age(p["age"])] if p["age"] is not None else toutes
    if p["franchise"] not in valides:
        p["franchise"] = None
    return p


def filtrer_priorite(priorite, phrase):
    """Priorité du LLM, gardée seulement si un mot lié figure dans la phrase (sinon None)."""
    if priorite in MOTS_PRIORITE and re.search(MOTS_PRIORITE[priorite], phrase or "", re.IGNORECASE):
        return priorite
    return None


def valider_profil(profil, demander=demander, phrase=""):
    """Vérifie chaque champ extrait par le LLM ; redemande ceux qui manquent ou sont faux."""
    p = nettoyer_profil(profil, phrase)
    npa = p["npa"]
    # Commune sans NPA : cherchée dans le fichier OFSP (le modèle ne devine jamais le NPA)
    lieu = localiser(npa, p["commune"]) if npa is not None or p["commune"] else None
    if lieu is None:
        npa = demander("Quel est ton code postal (NPA) ?", set(regions["npa"]), int,
                       aide="NPA inconnu : tape un code postal suisse à 4 chiffres.")
        commune, canton, region = trouver_commune(npa, p["commune"], demander)
    elif isinstance(lieu, tuple):
        commune, canton, region = lieu
    elif npa is not None:
        commune, canton, region = trouver_commune(npa, p["commune"], demander)
    else:
        commune, canton, region = choisir_commune(
            lieu, f"Plusieurs communes s'appellent « {p['commune']} » :", demander)

    if p["plusieurs_personnes"]:
        print("Je compare une personne à la fois : réponds pour la personne à assurer.")
    if p["age"] is None:
        p["age"] = demander("Quel âge a la personne à assurer ?", range(0, 121), int,
                            aide="Tape un âge entre 0 et 120.")
        regles_age(p, phrase)
    age = p["age"]

    franchises = FRANCHISES[classe_age(age)]
    franchise = p["franchise"]
    if franchise not in franchises:
        franchise = demander(
            f"Quelle franchise en CHF ({', '.join(map(str, franchises))}) ?",
            franchises, int)

    travaille_8h = p["travaille_8h"]
    if travaille_8h is None:
        travaille_8h = demander(
            "Travailles-tu au moins 8 h par semaine chez le même employeur ? (o/n)",
            ["o", "n"], lambda s: s.lower()[:1]) == "o"

    return {"npa": npa, "commune": commune, "canton": canton, "region": region,
            "age": age, "franchise": franchise, "travaille_8h": travaille_8h}


def resumer_faits(profil, resultats):
    """Résumé factuel pour le LLM : moins chère, moins chère par modèle, risque de franchise.
    Tous les montants sont calculés ici et arrondis au franc."""
    def chf(x):
        return f"{round(x)} CHF"

    moins_chere = resultats.iloc[0]
    quote_part = QUOTE_PART_MAX[classe_age(profil["age"])]
    descriptions = {m["nom"]: m["description"] for m in MODELES.values()}
    lignes = [
        f"Profil : {profil['age']} ans, {profil['commune']} ({profil['canton']}), couverture "
        f"accident {'exclue (assurée par l’employeur)' if profil['travaille_8h'] else 'incluse'}.",
        f"Offre la moins chère : {moins_chere['Assureur']}, modèle {moins_chere['Modèle']}, "
        f"{chf(moins_chere['Prime/an'])} par an.",
        "Offre la moins chère de chaque modèle :",
    ]
    for nom_modele, offres in resultats.groupby("Modèle", sort=False):
        o = offres.iloc[0]
        ecart = ("c'est l'offre la moins chère" if o["Écart/an"] == 0
                 else f"soit {chf(o['Écart/an'])} de plus par an que l'offre la moins chère")
        lignes.append(f"- {nom_modele} ({descriptions[nom_modele]}) : {o['Assureur']}, "
                      f"{chf(o['Prime/an'])} par an, {ecart}.")
    lignes += [
        f"Franchise : {profil['franchise']} CHF par an, payés par toi avant que l'assurance rembourse.",
        f"Quote-part maximale : {quote_part} CHF par an.",
        f"Si tes frais médicaux sont élevés, tu paies jusqu'à "
        f"{chf(profil['franchise'] + quote_part)} en plus de la prime (franchise + quote-part), "
        f"soit un coût maximal de {chf(moins_chere['Coût max/an'])} par an avec l'offre la moins chère.",
        "Source : primes officielles OFSP 2027.",
    ]
    return "\n".join(lignes)


def nombres(texte):
    """Nombres cités dans un texte ('5 124', "5'124" et '5124.00' donnent 5124)."""
    texte = re.sub(r"(?<=\d)[ '’  ](?=\d{3}\b)", "", texte or "")
    return {float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", texte)}


def montants_intrus(reponse, faits):
    """Nombres de la réponse du LLM absents des faits fournis (vide si tout est correct)."""
    return sorted(nombres(reponse) - nombres(faits))


def texte_standard(faits):
    """Explication de secours, sans LLM, si les montants d'Apertus restent faux."""
    return ("Je n'ai pas pu générer d'explication fiable. Voici les faits principaux :\n"
            + "\n".join(l for l in faits.splitlines() if not l.startswith("Profil")))


def expliquer(client, modele, faits, langue="français", prompt=PROMPT_EXPLICATION, secours=None):
    """Demande l'explication au LLM, la vérifie, réessaie une fois, sinon texte de secours."""
    systeme = en_langue(prompt, langue)
    explication = demander_llm(client, modele, systeme, faits)
    intrus = montants_intrus(explication, faits)
    if not intrus:
        return explication
    rappel = (f"\n\nATTENTION : une réponse précédente citait des montants absents des faits "
              f"({', '.join(f'{n:g}' for n in intrus)}). N'utilise que les montants ci-dessus.")
    explication = demander_llm(client, modele, systeme, faits + rappel)
    if not montants_intrus(explication, faits):
        return explication
    return secours or texte_standard(faits)


NOMS_PRIORITE = {"prix": "le prix le plus bas", "medecin_famille": "passer par un médecin de famille",
                 "libre_choix": "le libre choix du médecin"}


def faits_propositions(propositions, priorite=None):
    """Faits des 3 propositions pour l'introduction du LLM (montants tels qu'affichés)."""
    lignes = [f"Priorité de la personne : {NOMS_PRIORITE.get(priorite, 'aucune indiquée')}."]
    for i, p in enumerate(propositions, 1):
        ecart = ("c'est la moins chère" if p["ecart_mois"] == 0
                 else f"{p['ecart_mois']:.2f} CHF de plus par mois que la moins chère")
        lignes.append(f"Proposition {i} — {p['titre']} : {p['assureur']}, modèle {p['modele']}, "
                      f"{p['prime_mois']:.2f} CHF par mois, {ecart}. "
                      f"Contrepartie : {p['contrepartie']}")
    lignes.append("Source : primes officielles OFSP 2027.")
    return "\n".join(lignes)


def main():
    config = lire_config()
    client = OpenAI(base_url=config["LLM_BASE_URL"], api_key=config["LLM_API_KEY"])
    modele = config["LLM_NAME"]

    print("=== Comparateur de primes LAMal (données OFSP) ===\n")
    situation = input("Décris ta situation (âge, code postal, travail, franchise souhaitée) :\n> ")

    brut = demander_llm(client, modele, PROMPT_EXTRACTION, situation)
    profil = valider_profil(extraire_json(brut), phrase=situation)
    npa = f" ({profil['npa']})" if profil["npa"] else ""
    print(f"\nProfil retenu : {profil['commune']}{npa}, canton "
          f"{profil['canton']}, région {profil['region']}, {profil['age']} ans, "
          f"franchise {profil['franchise']} CHF, "
          f"accident {'exclu' if profil['travaille_8h'] else 'inclus'}")

    # Qui travaille >= 8 h/semaine est assuré contre les accidents par l'employeur (LAA)
    resultats = comparer(profil["canton"], profil["region"], profil["age"],
                         profil["franchise"], avec_accident=not profil["travaille_8h"])
    if resultats.empty:
        print("\nAucune prime trouvée pour ce profil.")
        return

    tableau = resultats.to_string(index=False, float_format="%.2f")
    print(f"\nLes {len(resultats)} offres les moins chères (CHF) :\n{tableau}\n")

    # Tous les faits (définitions et montants) viennent de Python, pas du LLM
    faits = resumer_faits(profil, resultats)
    explication = expliquer(client, config["LLM_NAME_RESTITUTION"], faits)
    print(f"Apertus :\n{explication}\n")
    print("Primes officielles OFSP 2027. Vérifie sur priminfo.admin.ch avant de changer d'assurance.")


if __name__ == "__main__":
    main()
