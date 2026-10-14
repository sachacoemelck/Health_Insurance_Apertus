"""Après les résultats : caisse actuelle, économie possible et lettre de résiliation.

Répartition du travail, comme dans le reste de l'application :
- Apertus 8B lit la réponse libre de la personne (« chez Helsana, modèle médecin de famille ») ;
- Python reconnaît la caisse dans la liste officielle de l'OFSP et calcule, avec les primes officielles
  2027, ce que la personne paiera si elle ne change rien, et ce qu'elle économiserait ;
- Apertus 70B explique cette économie en quelques phrases, puis rédige la lettre de résiliation ;
- Python vérifie chaque chiffre et chaque élément obligatoire de la lettre, sinon il utilise un modèle
  de lettre sûr écrit à l'avance.
"""
import datetime
import re
import unicodedata

import comparateur
from chatbot import extraire_json, nombres
from langues import tr

# ---------------------------------------------------------------------------------------------------
# 1. Reconnaître la caisse et le modèle
# ---------------------------------------------------------------------------------------------------
_SUFFIXES = r"\b(?:ag|sa|krankenversicherung|krankenkasse|gesundheitsversicherung|assurances?|basis)\b"


def _simple(texte):
    texte = unicodedata.normalize("NFD", (texte or "").lower().replace("’", "'"))
    return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in texte if unicodedata.category(c) != "Mn")))


# Caisses qui ont des primes 2027 dans les données de l'OFSP : numéro -> nom officiel
CAISSES = {n: nom for n, nom in comparateur.ASSUREURS.items() if n in set(comparateur.df["Versicherer"].unique())}

# Nom court de chaque caisse, tel que les gens le disent (calculé depuis le nom officiel)
NOMS_COURTS = {n: re.sub(r"\s+", " ", re.sub(_SUFFIXES, " ", _simple(nom))).strip() for n, nom in CAISSES.items()}
NOMS_COURTS[1542] = "assura"            # « Assura-Basis SA »
NOMS_COURTS[509] = "sympany"            # « Vivao Sympany »
NOMS_COURTS[455] = "okk"                # « ÖKK »

# Noms de groupe : plusieurs caisses possibles, la personne choisit celle de sa police
GROUPES = {"groupe mutuel": [343, 1479, 1535], "group mutual": [343, 1479, 1535], "mutual": [1479]}
AUTRES_NOMS = {"oekk": [455], "vivao": [509], "concordia": [290], "einsiedler": [134], "galenos": [1386]}


def trouver_caisses(texte):
    """Caisses citées dans le texte : [numéro, …] (plusieurs si c'est un nom de groupe)."""
    t = f" {_simple(texte)} "
    for groupe, numeros in GROUPES.items():
        if f" {groupe} " in t:
            return list(numeros)
    trouvees = [n for n, court in NOMS_COURTS.items() if court and f" {court} " in t]
    trouvees += [n for alias, ns in AUTRES_NOMS.items() if f" {alias} " in t for n in ns if n not in trouvees]
    return trouvees


# Modèle d'assurance dit par la personne -> type de tarif OFSP
_MODELES = [
    ("PRAXIS", r"m[eé]decin de famille|\bhmo\b|r[eé]seau|hausarzt|medico di famiglia|family doctor|\bgp\b|praxis"),
    ("TEL_DIG", r"t[eé]l[eé]m[eé]decine|telmed|t[eé]l[eé]phone|telefon|\bapp\b|num[eé]rique|digital|telemedicin"),
    ("BASE", r"libre choix|standard|classique|freie? (?:arzt)?wahl|libera scelta|free choice|ordinaire|normal"),
]


def lire_modele(texte):
    for code, motif in _MODELES:
        if re.search(motif, texte or "", re.IGNORECASE):
            return code
    return None


PROMPT_CAISSE = """Tu lis la réponse d'une personne à la question « Chez quelle caisse maladie êtes-vous
assuré(e) aujourd'hui, et avec quel modèle ? ». Réponds UNIQUEMENT par un objet JSON :
{"caisse": "<nom de la caisse tel qu'écrit, ou null>",
 "modele": "<libre choix | médecin de famille | télémédecine | null>",
 "prime_mois": <prime mensuelle actuelle en CHF si la personne la donne, sinon null>}
N'invente rien : null si l'information n'est pas dans le message."""


_PRIME = re.compile(
    r"(\d{2,4}(?:[.,]\d{1,2})?)\s*(?:chf|fr\.?|francs?|franken|franchi|\.-)?\s*(?:par|pro|im|al|a|per|/|each|a)\s*"
    r"(?:mois|monat|mese|month)|(?:paie|paye|zahle|bezahle|pago|pay)\D{0,20}?(\d{2,4}(?:[.,]\d{1,2})?)",
    re.IGNORECASE)


def prime_dite(texte):
    """Prime mensuelle écrite explicitement (« je paie 389.50 par mois », « 455 Franken im Monat »)."""
    for m in _PRIME.finditer(texte or ""):
        valeur = float((m.group(1) or m.group(2)).replace(",", "."))
        if 30 <= valeur <= 2000:
            return valeur
    return None


def lire_caisse(lire_8b, texte):
    """Ce que la personne a dit de sa caisse actuelle : Apertus 8B lit, Python contrôle.
    Renvoie {"caisses": [numéros], "modele": code ou None, "prime_mois": nombre ou None}."""
    lu = {}
    try:
        lu = extraire_json(lire_8b(PROMPT_CAISSE, texte)) or {}
    except Exception:
        lu = {}
    # Python ne garde que ce qui est vérifiable : une caisse de la liste officielle, citée dans le
    # message (Apertus ne peut pas en inventer une), et un montant qui figure dans le message.
    caisses = trouver_caisses(f"{lu.get('caisse') or ''}") if lu.get("caisse") else []
    caisses = [n for n in caisses if n in trouver_caisses(texte)] or trouver_caisses(texte)
    # Le modèle n'est retenu que s'il est écrit dans le message : au test réel, Apertus 8B a ajouté
    # « médecin de famille » à 3 réponses qui ne parlaient d'aucun modèle (« CSS je crois »).
    modele = lire_modele(texte)
    prime = lu.get("prime_mois")
    if prime is None:  # Apertus n'a rien lu (ou ne répond pas) : Python lit les formulations explicites
        prime = prime_dite(texte)
    try:
        prime = float(prime) if prime is not None and float(prime) in nombres(texte) else None
    except (TypeError, ValueError):
        prime = None
    if prime is not None and not 30 <= prime <= 2000:  # une prime LAMal mensuelle plausible
        prime = None
    return {"caisses": caisses, "modele": modele, "prime_mois": prime}


# ---------------------------------------------------------------------------------------------------
# 2. Calculer l'économie (Python seul)
# ---------------------------------------------------------------------------------------------------
NOMS_MODELES = {"BASE": "libre choix", "PRAXIS": "médecin de famille / HMO", "TEL_DIG": "télémédecine",
                "FLEX": "modèle alternatif", "PHARM": "pharmacie"}


def _offre(ligne):
    return {"caisse": ligne["Assureur"], "modele": ligne["Modèle"], "produit": ligne["Produit"],
            "prime": round(float(ligne["Prime/mois"]), 2), "tarif": ligne["Tariftyp"]}


def calculer_economie(profile, offres, numero=None, modele=None, prime_dite=None, no_ofs=None):
    """Compare la caisse actuelle avec les offres, à franchise égale (celle de la meilleure offre).

    - Prime actuelle : celle que la caisse demandera en 2027 pour le même profil (données OFSP),
      c'est-à-dire ce que la personne paiera si elle ne change rien. Sans modèle précisé, on suppose
      le libre choix et on le dit. La prime dite par la personne ne sert que si la caisse n'est pas
      reconnue (c'est alors une prime d'aujourd'hui, comparée aux primes 2027 : on le dit aussi).
    - Deux comparaisons : à modèle égal (même genre de contrat), et l'offre la moins chère des
      résultats (qui peut demander un autre modèle). Tout est calculé ici, jamais par Apertus."""
    if offres is None or offres.empty:
        return None
    franchise = int(offres.iloc[0]["Franchise"])
    toutes = comparateur.toutes_les_offres(profile.canton, profile.region, profile.rating_age, franchise,
                                           profile.include_accident, None, profile.premium_year, no_ofs)
    meilleure = _offre(offres[offres["Franchise"] == franchise].iloc[0])
    e = {"caisse": CAISSES.get(numero) if numero else None, "numero": numero, "franchise": franchise,
         "modele": modele, "modele_suppose": False, "source": "ofsp", "options": []}
    if numero:
        chez = toutes[toutes["Assureur"] == CAISSES.get(numero)]
        if chez.empty:
            e["absente"] = True  # pas d'assurance de base de cette caisse pour ce profil dans cette région
            return e
        if modele is None or chez[chez["Tariftyp"] == modele].empty:
            e["modele_suppose"] = modele is None
            modele = "BASE" if not chez[chez["Tariftyp"] == "BASE"].empty else chez.iloc[0]["Tariftyp"]
        actuelle = _offre(chez[chez["Tariftyp"] == modele].iloc[0])
        e.update(modele=modele, prime_actuelle=actuelle["prime"], produit_actuel=actuelle["produit"],
                 prime_aujourdhui=round(float(prime_dite), 2) if prime_dite is not None else None)
    elif prime_dite is not None:
        e.update(source="personne", prime_actuelle=round(float(prime_dite), 2))
    else:
        return None
    candidates = []
    if e["source"] == "ofsp":
        meme = toutes[toutes["Tariftyp"] == modele]
        if not meme.empty:
            candidates.append(("meme_modele", _offre(meme.iloc[0])))
    candidates.append(("meilleure", meilleure))
    for genre, o in candidates:
        if any(x["caisse"] == o["caisse"] and x["produit"] == o["produit"] for _, x in e["options"]):
            continue
        o = dict(o, economie_mois=round(e["prime_actuelle"] - o["prime"], 2))
        o["economie_an"] = round(o["economie_mois"] * 12, 2)
        o["meme_caisse"] = o["caisse"] == e["caisse"]
        if o["economie_mois"] > 0:
            e["options"].append((genre, o))
    e["deja_meilleure"] = not e["options"]
    # Une lettre de résiliation n'a de sens que pour aller chez une autre caisse
    e["autre_caisse"] = next((o for _, o in e["options"] if not o["meme_caisse"]), None)
    return e


def faits_economie(e):
    """Faits donnés à Apertus : tous les chiffres viennent du calcul Python ci-dessus."""
    modele = NOMS_MODELES.get(e.get("modele"), e.get("modele") or "")
    if e["source"] == "personne":
        lignes = [f"Prime actuelle indiquée par la personne : {e['prime_actuelle']:.2f} CHF par mois. Attention : "
                  "c'est la prime d'aujourd'hui, alors que les offres sont les primes 2027."]
    else:
        lignes = [f"Caisse actuelle : {e['caisse']}, modèle {modele}"
                  + (" (modèle non précisé : on suppose le libre choix, le modèle standard)" if e["modele_suppose"] else ""),
                  f"Prime 2027 de la caisse actuelle pour ce profil (données OFSP), franchise {e['franchise']} CHF : "
                  f"{e['prime_actuelle']:.2f} CHF par mois. C'est ce que la personne paiera si elle ne change rien."]
        if e.get("prime_aujourdhui"):
            lignes.append(f"La personne dit payer aujourd'hui {e['prime_aujourdhui']:.2f} CHF par mois (prime de cette "
                          "année ; les primes 2027 peuvent être différentes).")
    for genre, o in e["options"]:
        titre = "À modèle égal" if genre == "meme_modele" else "Offre la moins chère des résultats"
        ou = "chez la même caisse, en changeant seulement de modèle" if o["meme_caisse"] else f"chez {o['caisse']}"
        lignes.append(f"{titre} : {o['caisse']}, {o['modele']} ({o['produit']}), {o['prime']:.2f} CHF par mois, "
                      f"{ou} : économie de {o['economie_mois']:.2f} CHF par mois, soit {o['economie_an']:.2f} CHF par an")
    if e["deja_meilleure"]:
        lignes.append("Aucune offre des résultats n'est moins chère : aucune économie possible.")
    return "\n".join(lignes)


PROMPT_ECONOMIE = """Tu es le conseiller en assurance maladie de base (LAMal) d'une application suisse.
Explique à la personne, en 2 ou 3 phrases simples, ce qu'elle paierait en restant chez sa caisse
actuelle et ce qu'elle économiserait en changeant, avec les FAITS ci-dessous.
Règles strictes :
- Recopie les montants exactement ; n'invente aucun chiffre et ne fais aucun calcul.
- Si le modèle a été supposé, dis-le en une courte phrase.
- Si la personne est déjà chez l'offre la moins chère, dis-le simplement : pas d'économie.
- Rappelle en une phrase que les prestations de base sont les mêmes chez toutes les caisses, mais que
  le modèle (médecin de famille, télémédecine…) a ses propres règles.
- Ne pousse pas à changer : présente les chiffres, la décision reste à la personne. Pas de question.
- Vouvoie la personne. Écris en {langue} simple, sans liste ni titre, sans « Bonjour »."""


def texte_economie_secours(e, code="fr"):
    """Même information sans Apertus (s'il ne répond pas ou si ses chiffres sont faux)."""
    actuelle = f"{e['prime_actuelle']:.2f}"
    if e["source"] == "personne":
        debut = tr("Vous payez aujourd'hui {actuelle} CHF par mois (les offres affichées sont les primes 2027).",
                   code, actuelle=actuelle)
    else:
        debut = tr("En restant chez {caisse}, vous payeriez {actuelle} CHF par mois en 2027 (franchise {franchise} "
                   "CHF).", code, caisse=e["caisse"], actuelle=actuelle, franchise=e["franchise"])
        if e["modele_suppose"]:
            debut += " " + tr("(Modèle non précisé : j'ai supposé le libre choix.)", code)
    if e["deja_meilleure"]:
        return debut + " " + tr("Aucune offre de vos résultats n'est moins chère : changer ne vous ferait rien "
                                "économiser.", code)
    phrases = [debut]
    for _, o in e["options"]:
        phrases.append(tr("Avec {caisse} ({modele}), vous payeriez {prime} CHF par mois, soit {an} CHF de moins "
                          "par an.", code, caisse=o["caisse"], modele=tr(o["modele"], code),
                          prime=f"{o['prime']:.2f}", an=f"{o['economie_an']:.2f}"))
    return " ".join(phrases)


# ---------------------------------------------------------------------------------------------------
# 3. Lettre de résiliation
# ---------------------------------------------------------------------------------------------------
# Langue de la lettre : celle de la personne (langue nationale) ; en anglais, celle du canton.
LANGUE_CANTON = {"GE": "fr", "VD": "fr", "NE": "fr", "JU": "fr", "FR": "fr", "VS": "fr", "TI": "it"}

CHAMPS = {  # champs que la personne remplit elle-même : Apertus n'invente aucune donnée personnelle
    "fr": ["[Prénom Nom]", "[Adresse]", "[NPA Localité]", "[Numéro d'assuré]", "[Lieu, date]", "[Signature]"],
    "de": ["[Vorname Name]", "[Adresse]", "[PLZ Ort]", "[Versichertennummer]", "[Ort, Datum]", "[Unterschrift]"],
    "it": ["[Nome Cognome]", "[Indirizzo]", "[NPA Località]", "[Numero d'assicurato]", "[Luogo, data]", "[Firma]"],
}
CHAMP_ADRESSE_CAISSE = {"fr": "[Adresse de la caisse]", "de": "[Adresse der Krankenkasse]",
                        "it": "[Indirizzo della cassa]"}
MOIS = {"fr": "décembre", "de": "Dezember", "it": "dicembre"}
_ASSURANCE_DE_BASE = {
    "fr": r"assurance (?:obligatoire des soins|de base|maladie de base)|\bLAMal\b",
    "de": r"Grundversicherung|obligatorische[n]? Krankenpflegeversicherung|\bKVG\b",
    "it": r"assicurazione (?:obbligatoria delle cure|di base|malattie di base)|\bLAMal\b",
}
_COMPLEMENTAIRE = {"fr": r"compl[ée]mentaire", "de": r"Zusatzversicherung", "it": r"complementar"}
_NEGATION = {"fr": r"\b(?:ne|pas|non|reste|restent|maintenu|maintenues|conserv)", "de": r"\b(?:nicht|kein|bleib|weiterhin)",
             "it": r"\b(?:non|rimang|mantenut|restano)"}


def langue_lettre(code, canton):
    return code if code in CHAMPS else LANGUE_CANTON.get(canton, "de")


AUJOURDHUI = None  # date du jour ; les tests la fixent pour simuler décembre ou mars


def _aujourdhui():
    return AUJOURDHUI or datetime.date.today()


def _dernier_jour_ouvrable(annee, mois, jour):
    d = datetime.date(annee, mois, jour)
    while d.weekday() >= 5:  # samedi, dimanche
        d -= datetime.timedelta(days=1)
    return d


def dates(annee_primes=None):
    """(fin de l'assurance actuelle, date limite de réception de la lettre) : la prochaine échéance
    encore possible à la date du jour (LAMal art. 7). Jusqu'au dernier jour ouvrable de novembre, fin au
    31 décembre de l'année ; après, fin au 31 décembre de l'année suivante. (Le changement pour le
    30 juin, réservé à la franchise de 300 CHF et au libre choix, est signalé à part : changement_juin.)"""
    jour = _aujourdhui()
    annee = jour.year if jour <= _dernier_jour_ouvrable(jour.year, 11, 30) else jour.year + 1
    return datetime.date(annee, 12, 31), _dernier_jour_ouvrable(annee, 11, 30)


def changement_juin():
    """(30 juin, date limite) si un changement pour le 30 juin est encore possible avant l'échéance de
    décembre : lettre reçue au plus tard fin mars (préavis de 3 mois), franchise de 300 CHF et libre choix."""
    jour = _aujourdhui()
    annee = jour.year if jour <= _dernier_jour_ouvrable(jour.year, 3, 31) else jour.year + 1
    juin = datetime.date(annee, 6, 30)
    return (juin, _dernier_jour_ouvrable(annee, 3, 31)) if juin < dates()[0] else None


def delai_janvier_passe(annee_primes):
    """Vrai si on ne peut plus changer pour le 1er janvier de l'année des primes affichées."""
    return dates()[0].year >= annee_primes


_MOIS_NOMS = {"fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
                     "octobre", "novembre", "décembre"],
              "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September",
                     "Oktober", "November", "Dezember"],
              "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
                     "settembre", "ottobre", "novembre", "dicembre"]}


def date_texte(d, langue):
    nom = _MOIS_NOMS.get(langue, _MOIS_NOMS["fr"])[d.month - 1]
    return f"{d.day}. {nom} {d.year}" if langue == "de" else f"{d.day} {nom} {d.year}"


PROMPT_LETTRE = """Tu rédiges une lettre de résiliation de l'assurance maladie de base (LAMal) suisse.
Écris la lettre COMPLÈTE en {langue}, polie et courte, prête à être imprimée. Elle doit contenir :
- en haut, les champs de l'expéditeur, recopiés EXACTEMENT avec leurs crochets : {champs_haut} ;
- le destinataire : {caisse}, puis le champ {adresse_caisse} ;
- le lieu et la date : {lieu_date} ;
- un objet clair ;
- la résiliation de l'assurance obligatoire des soins (assurance de base) pour le {fin} ;
- le numéro d'assuré avec le champ {numero} ;
- une phrase qui dit que les assurances complémentaires ne sont PAS résiliées ;
- la demande d'une confirmation écrite de la résiliation ;
- une formule de politesse, puis le champ {signature}.
N'invente aucun nom, aucune adresse, aucun numéro : utilise les champs entre crochets.
Réponds uniquement par le texte de la lettre, sans explication."""


def consignes_lettre(caisse, langue, annee_primes):
    champs = CHAMPS[langue]
    fin, _ = dates(annee_primes)
    noms = {"fr": "français", "de": "allemand (Hochdeutsch, forme « Sie »)", "it": "italien (forme « Lei »)"}
    return (PROMPT_LETTRE.replace("{langue}", noms[langue]).replace("{champs_haut}", ", ".join(champs[:3]))
            .replace("{caisse}", caisse).replace("{adresse_caisse}", CHAMP_ADRESSE_CAISSE[langue])
            .replace("{lieu_date}", champs[4]).replace("{fin}", date_texte(fin, langue))
            .replace("{numero}", champs[3]).replace("{signature}", champs[5]))


def problemes_lettre(lettre, caisse, langue, annee_primes):
    """Éléments obligatoires manquants ou erreurs (liste vide si la lettre est correcte)."""
    fin, _ = dates(annee_primes)
    t = lettre or ""
    problemes = []
    if _simple(caisse).split()[0] not in _simple(t):
        problemes.append(f"le nom de la caisse ({caisse}) manque")
    if not re.search(rf"\b31\.?\s*(?:{MOIS[langue]}|12\.?)\s*{fin.year}", t, re.IGNORECASE):
        problemes.append(f"la date de fin ({date_texte(fin, langue)}) manque")
    if not re.search(_ASSURANCE_DE_BASE[langue], t, re.IGNORECASE):
        problemes.append("il faut dire que c'est l'assurance de base (obligatoire) qui est résiliée")
    for champ in CHAMPS[langue]:
        if champ.lower() not in t.lower():
            problemes.append(f"le champ {champ} manque")
    phrases = re.split(r"(?<=[.!?])\s+|\n", t)
    complementaires = [p for p in phrases if re.search(_COMPLEMENTAIRE[langue], p, re.IGNORECASE)]
    if not complementaires:
        problemes.append("il faut préciser que les assurances complémentaires ne sont pas résiliées")
    elif not all(re.search(_NEGATION[langue], p, re.IGNORECASE) for p in complementaires):
        problemes.append("les assurances complémentaires ne doivent PAS être résiliées")
    autorises = {31.0, 12.0, float(fin.year), float(fin.year + 1), 30.0} | {float(n) for n in range(1, 11)}
    inventes = sorted(n for n in nombres(re.sub(r"\[[^\]]*\]", "", t)) if n not in autorises)
    if inventes:
        problemes.append("n'invente aucun numéro ni montant (" + ", ".join(f"{n:g}" for n in inventes) + ")")
    if len(t) > 2500:
        problemes.append("la lettre est trop longue")
    return problemes


def lettre_modele(caisse, langue, annee_primes):
    """Lettre sûre écrite à l'avance (utilisée si Apertus ne donne pas une lettre complète)."""
    c = CHAMPS[langue]
    fin = date_texte(dates(annee_primes)[0], langue)
    if langue == "de":
        corps = (f"Kündigung der obligatorischen Krankenpflegeversicherung (Grundversicherung)\n\n"
                 f"Sehr geehrte Damen und Herren\n\n"
                 f"Hiermit kündige ich meine obligatorische Krankenpflegeversicherung (Grundversicherung nach KVG) "
                 f"per {fin}. Versichertennummer: {c[3]}.\n\n"
                 f"Meine Zusatzversicherungen werden nicht gekündigt und bleiben bestehen.\n\n"
                 f"Bitte bestätigen Sie mir die Kündigung schriftlich.\n\nFreundliche Grüsse\n\n{c[5]}\n{c[0]}")
    elif langue == "it":
        corps = (f"Disdetta dell'assicurazione obbligatoria delle cure medico-sanitarie (assicurazione di base)\n\n"
                 f"Gentili Signore e Signori,\n\n"
                 f"con la presente disdico la mia assicurazione di base (LAMal) per il {fin}. "
                 f"Numero d'assicurato: {c[3]}.\n\n"
                 f"Le mie assicurazioni complementari non sono disdette e rimangono in vigore.\n\n"
                 f"Vi prego di confermarmi la disdetta per iscritto.\n\nCordiali saluti\n\n{c[5]}\n{c[0]}")
    else:
        corps = (f"Objet : résiliation de l'assurance obligatoire des soins (assurance de base)\n\n"
                 f"Madame, Monsieur,\n\n"
                 f"Par la présente, je résilie mon assurance de base (LAMal) pour le {fin}. "
                 f"Numéro d'assuré : {c[3]}.\n\n"
                 f"Mes assurances complémentaires ne sont pas résiliées et restent en vigueur.\n\n"
                 f"Je vous prie de me confirmer cette résiliation par écrit.\n\n"
                 f"Veuillez agréer, Madame, Monsieur, mes salutations distinguées.\n\n{c[5]}\n{c[0]}")
    return f"{c[0]}\n{c[1]}\n{c[2]}\n\n{caisse}\n{CHAMP_ADRESSE_CAISSE[langue]}\n\n{c[4]}\n\n{corps}"


def rediger_lettre(appeler_70b, caisse, langue, annee_primes):
    """(lettre, "apertus" ou "modele") : la lettre d'Apertus si elle passe les contrôles (un nouvel
    essai avec la liste des problèmes), sinon la lettre modèle."""
    consignes = consignes_lettre(caisse, langue, annee_primes)
    demande = f"Caisse actuelle : {caisse}. Rédige la lettre."
    try:
        lettre = (appeler_70b(consignes, demande) or "").strip()
        problemes = problemes_lettre(lettre, caisse, langue, annee_primes)
        if problemes:
            lettre = (appeler_70b(consignes, demande + "\n\nATTENTION, corrige : " + " ; ".join(problemes)) or "").strip()
            problemes = problemes_lettre(lettre, caisse, langue, annee_primes)
        if not problemes:
            return lettre, "apertus"
    except Exception:
        pass
    return lettre_modele(caisse, langue, annee_primes), "modele"


def conseils_envoi(code, annee_primes):
    """Rappel affiché sous la lettre (texte fixe traduit, dates calculées par Python)."""
    fin, limite = dates(annee_primes)
    jours = {"fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi"],
             "de": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"],
             "it": ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì"],
             "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]}[code if code in ("fr", "de", "it", "en") else "fr"]
    jour = lambda d: f"{jours[d.weekday()]} {d.day}.{d.month:02d}.{d.year}"
    limite_txt = jour(limite)
    avant = ""
    if delai_janvier_passe(annee_primes):
        avant = tr("Le délai pour changer de caisse au 1er janvier {annee} est passé (lettre reçue au plus tard fin "
                   "novembre) : la lettre résilie donc pour le {fin}.", code, annee=annee_primes,
                   fin=f"{fin.day}.{fin.month:02d}.{fin.year}") + " "
    juin = changement_juin()
    if juin:
        avant += tr("Avec la franchise de 300 CHF et le modèle libre choix, vous pouvez aussi changer pour le "
                    "30 juin {annee} (lettre reçue au plus tard le {limite}) : adaptez alors la date de la lettre.",
                    code, annee=juin[0].year, limite=jour(juin[1])) + " "
    return avant + tr("Avant d'envoyer : 1) inscrivez-vous d'abord auprès de la nouvelle caisse (votre assurance actuelle ne "
              "prend fin que lorsque la nouvelle caisse confirme votre couverture, LAMal art. 7 al. 5) ; 2) envoyez "
              "la lettre en recommandé : elle doit ARRIVER chez votre caisse au plus tard le {limite} ; 3) complétez "
              "les champs entre crochets et signez.", code, limite=limite_txt)


__all__ = ["trouver_caisses", "lire_caisse", "calculer_economie", "faits_economie", "PROMPT_ECONOMIE",
           "texte_economie_secours", "langue_lettre", "rediger_lettre", "problemes_lettre", "lettre_modele",
           "conseils_envoi", "CAISSES"]
