"""Garde-fous déterministes : ce que Python lit directement dans le message.

Apertus 8B rate parfois une information pourtant écrite noir sur blanc (un code postal,
« la franchise la plus haute », « 42 heures par semaine chez le même employeur »). Ces règles
lisent ces formulations explicites et complètent la réponse d'Apertus, sans jamais deviner :
une règle ne s'applique que si la formulation est sans ambiguïté, sinon la question est posée.

Mesuré le 9 octobre 2026 sur le test de parcours en français (17 conversations) : avant ces
règles, 2/17 conversations aboutissaient au bon profil.
"""
import re
import unicodedata

from chatbot import FIELDS, MOTIF_MONTANT, communes_du_npa, communes_par_nom, nom_simple, regions

_CORRECTION = re.compile(r"\ben fait\b|\bfinalement\b|\bplut[ôo]t\b|\bcorrect|\bje me suis tromp|\bpas\s+\d", re.I)
_FRANCHISE_HAUTE = re.compile(r"(?:franchise|d[ée]ductible)\D{0,25}(?:plus\s+(?:haute|[ée]lev[ée]e)|\bmax)"
                              r"|(?:plus\s+(?:haute|[ée]lev[ée]e)|\bmax\w*)\D{0,12}franchise", re.I)
_FRANCHISE_BASSE = re.compile(r"(?:franchise|d[ée]ductible)\D{0,25}(?:plus\s+basse|\bmin)"
                              r"|(?:plus\s+basse|\bmin\w*)\D{0,12}franchise", re.I)
_FRANCHISE_TOUTES = re.compile(r"toutes\s+les\s+franchises|comparer\s+toutes", re.I)
_FRANCHISE_MONTANT = re.compile(r"franchise\D{0,15}?(\d{1,4})(?!\d)", re.I)
_HESITATION = re.compile(r"h[ée]sit|\bentre\b.{0,30}\bet\b|\bou\s+(?:bien\s+)?(?:une\s+)?(?:franchise\s+)?(?:de\s+)?\d", re.I)
_MONTANTS_LEGAUX = (0, 100, 200, 300, 400, 500, 600, 1000, 1500, 2000, 2500)
_AVEC_ACCIDENT = re.compile(r"\bavec\s+(?:la\s+|les\s+)?(?:couverture\s+)?accidents?\b", re.I)
_SANS_ACCIDENT = re.compile(r"\bsans\s+(?:la\s+|les\s+)?(?:couverture\s+)?accidents?\b", re.I)
# « je ne suis couvert par aucun employeur pour les accidents » : jamais une raison d'exclure les accidents
_PAS_COUVERT = re.compile(r"\b(?:pas|aucun\w*|ni|plus)\b[^.?!]{0,40}\bcouverte?s?\b[^.?!]{0,40}\baccident"
                          r"|\bcouverte?s?\b[^.?!]{0,20}\b(?:aucun\w*|personne)\b[^.?!]{0,40}\baccident"
                          r"|\baccident\w*[^.?!]{0,40}\b(?:pas|aucun\w*)\b[^.?!]{0,15}\bcouvert", re.I)
_HEURES = re.compile(r"(\d{1,2})\s*(?:h\b|heures?)\s*(?:par|/|a\s+la|à\s+la)\s*semaine", re.I)
_MEME_EMPLOYEUR = re.compile(r"m[êe]me\s+employeur|un\s+seul\s+employeur", re.I)
_AGE = re.compile(r"(?<![\d.,])(\d{1,3})\s*ans\b", re.I)
_PLUSIEURS_AGES = re.compile(r"\d{1,3}\s*(?:et|,)\s*\d{1,3}\s*ans", re.I)
_NAISSANCE = re.compile(r"\bn[ée]e?s?\s+(?:en\s+)?((?:19|20)\d\d)\b|\bann[ée]e\s+de\s+naissance\D{0,5}((?:19|20)\d\d)", re.I)

# « à Sion », « in Bern » : une préposition suivie d'un nom propre (majuscule) annonce souvent le lieu
_PARLE_DU_LIEU = re.compile(r"\bhabit|\bvi[st]\s+[àa]\b|r[ée]sid|\bcommune\b|domicil|\bwohne|\babito"
                            r"|(?:\bà|\bin|\ba)\s+(?-i:[A-ZÀ-Ü])", re.I)

# Noms de communes officiels (sans canton ajouté, sans accents), du plus long au plus court
_COMMUNES = sorted({nom_simple(c) for c in regions["commune"]}, key=len, reverse=True)


def _connu(updates, champ):
    u = updates.get(champ)
    return bool(u) and u.get("status") == "known" and u.get("value") is not None


def _mettre(updates, champ, valeur, texte, cible):
    updates[champ] = {"value": valeur, "status": "known",
                      "correction": cible == champ or bool(_CORRECTION.search(texte))}


def _sans_accents(texte):
    return unicodedata.normalize("NFD", texte or "").encode("ascii", "ignore").decode().casefold()


def _mots(texte):
    return " " + re.sub(r"[^a-z0-9]+", " ", _sans_accents(texte)) + " "


_MARQUEUR_LIEU = re.compile(r" (?:habite|habitons|habitent|vis|vit|vivons|domicilie|domiciliee|reside|residons|"
                            r"commune|wohne|abito) (?:(?:a|au|aux|en|dans|de|la|le|commune|maintenant) )*")


def commune_dans_phrase(texte):
    """Nom de commune officiel cité dans la phrase (mot entier, 4 lettres au moins). S'il y en a
    plusieurs (« Premier » est aussi une commune), on garde celui qui suit « j'habite à »,
    « domicilié à »… ; s'il reste un doute, None : la question sera posée."""
    t = _mots(texte)
    trouvees = [c for c in _COMMUNES if len(c) >= 4 and f" {re.sub(r'[^a-z0-9]+', ' ', c).strip()} " in t]
    # « Yverdon-les-Bains » contient « Bains » : on garde les noms qui ne sont pas inclus dans un autre
    gardees = list(dict.fromkeys(c for c in trouvees if not any(c != d and c in d for d in trouvees)))
    if len(gardees) == 1:
        return gardees[0]
    apres_marqueur = [c for c in gardees
                      if any(t[m.end():].startswith(re.sub(r"[^a-z0-9]+", " ", c).strip() + " ")
                             for m in _MARQUEUR_LIEU.finditer(t))]
    return apres_marqueur[0] if len(apres_marqueur) == 1 else None


def npa_presente(texte, cible=None):
    """Code postal suisse existant, écrit en chiffres et présenté comme un lieu : à côté du nom
    d'une de ses communes, après « code postal » ou « NPA », ou en réponse à la question du lieu.
    « retraité depuis 2015 » ou une franchise de 2000 ne sont donc jamais lus comme un code postal."""
    propre = MOTIF_MONTANT.sub(" ", texte or "")
    candidats = []
    for m in re.finditer(r"(?<![\d'’.,])(\d{4})(?![\d'’])", propre):
        npa = int(m.group(1))
        communes = communes_du_npa(npa)
        if communes.empty:
            continue
        autour = _mots(propre[max(0, m.start() - 45): m.end() + 45])
        noms = {re.sub(r"[^a-z0-9]+", " ", nom_simple(c)).strip() for c in communes["commune"]}
        presente = (cible in ("postal_code", "municipality")
                    or re.search(r"(?:code\s+postal|\bnpa\b|\bcp\b|\bplz\b)\W{0,3}$", propre[:m.start()], re.I)
                    or any(f" {n} " in autour for n in noms if n))
        if presente:
            candidats.append(npa)
    return candidats[0] if len(set(candidats)) == 1 else None


def completer_par_regles(updates, texte, cible=None, suivi=False):
    """Complète (ou corrige, pour les formulations explicites) les mises à jour d'Apertus.
    `cible` est le champ demandé par la dernière question, s'il y en a une. `suivi` : message écrit
    après les résultats (« et avec une franchise de 300 ? ») ; le montant écrit fait alors foi."""
    updates = dict(updates)
    texte = texte or ""

    # Lieu : un code postal suisse existant, écrit en chiffres, hors montants de franchise
    npa = npa_presente(texte, cible)
    if npa is not None and not _connu(updates, "postal_code"):
        _mettre(updates, "postal_code", npa, texte, cible)
    lieu_demande = cible in ("postal_code", "municipality")
    if lieu_demande or (_PARLE_DU_LIEU.search(texte) and not _connu(updates, "postal_code")):
        actuelle = updates.get("municipality", {}).get("value") if _connu(updates, "municipality") else None
        officielle = actuelle is not None and not communes_par_nom(str(actuelle)).empty
        commune = commune_dans_phrase(texte)
        if commune and not officielle and not communes_par_nom(commune).empty:
            _mettre(updates, "municipality", communes_par_nom(commune).iloc[0]["commune"], texte, cible)
    if lieu_demande:
        # Répondre à la question du lieu corrige le lieu donné avant (code postal et commune ensemble).
        # Une réponse avec seulement une commune (ou seulement un code postal) efface l'autre moitié
        # de l'ancien lieu : sinon « Lausanne » resterait en conflit avec l'ancien NPA 1700 sans fin.
        for champ in ("postal_code", "municipality"):
            if champ in updates:
                updates[champ] = {**updates[champ], "correction": True}
        commune_donnee, npa_donne = _connu(updates, "municipality"), _connu(updates, "postal_code")
        if commune_donnee and not npa_donne:
            updates["postal_code"] = {"value": None, "status": "missing", "correction": True}
        elif npa_donne and not commune_donnee:
            updates["municipality"] = {"value": None, "status": "missing", "correction": True}

    # Franchise : les formulations explicites l'emportent sur la lecture d'Apertus
    if _FRANCHISE_TOUTES.search(texte):
        _mettre(updates, "deductible", "all", texte, cible)
    elif _FRANCHISE_HAUTE.search(texte) or (cible == "deductible" and re.search(r"plus\s+haute|\bmax", texte, re.I)):
        _mettre(updates, "deductible", "highest", texte, cible)
    elif _FRANCHISE_BASSE.search(texte) or (cible == "deductible" and re.search(r"plus\s+basse|\bmin", texte, re.I)):
        _mettre(updates, "deductible", "lowest", texte, cible)
    else:
        # « 1'500 », « 2 500 » ou « 2’500 » : séparateurs de milliers suisses retirés avant de lire
        chiffres = re.sub(r"(?<=\d)[ '’\u00a0\u202f](?=\d{3}\b)", "", texte)
        montants = {int(m) for m in _FRANCHISE_MONTANT.findall(chiffres)} & set(_MONTANTS_LEGAUX)
        if not montants and cible == "deductible":
            montants = {int(m) for m in re.findall(r"(?<!\d)(\d{1,4})(?!\d)", chiffres)} & set(_MONTANTS_LEGAUX)
        # Plusieurs montants (« j'hésite entre 300 et 2500 ») : la personne n'a pas choisi, on demande
        if len(montants) == 1 and not _HESITATION.search(texte):
            if (not _connu(updates, "deductible") or _CORRECTION.search(texte) or cible == "deductible"
                    or suivi):
                _mettre(updates, "deductible", montants.pop(), texte, cible)

    # Accidents : choix explicite de comparaison
    if _AVEC_ACCIDENT.search(texte) and not _SANS_ACCIDENT.search(texte):
        _mettre(updates, "include_accident", True, texte, cible)
    elif _SANS_ACCIDENT.search(texte) and not _AVEC_ACCIDENT.search(texte):
        _mettre(updates, "include_accident", False, texte, cible)

    # Pas de couverture accidents déclarée : les accidents restent inclus, quoi qu'ait lu Apertus
    if _PAS_COUVERT.search(texte) and not _SANS_ACCIDENT.search(texte):
        updates["nonoccupational_covered"] = {"value": False, "status": "known",
                                              "correction": cible == "nonoccupational_covered" or bool(_CORRECTION.search(texte))}
        if updates.get("include_accident", {}).get("value") is False:
            updates.pop("include_accident")

    # Heures chez un même employeur : seulement si « même employeur » est écrit
    heures = _HEURES.search(texte)
    if heures and _MEME_EMPLOYEUR.search(texte) and not _connu(updates, "hours_per_week_one_employer"):
        _mettre(updates, "hours_per_week_one_employer", int(heures.group(1)), texte, cible)
        if not _connu(updates, "employed"):
            _mettre(updates, "employed", True, texte, cible)

    # Un âge lu comme une année de naissance (« 50 ans » -> 50) n'est pas une année : on l'écarte
    an = updates.get("birth_year", {}).get("value")
    if isinstance(an, int) and an < 1900:
        updates.pop("birth_year")

    # Âge et année de naissance : un seul nombre explicite, jamais quand plusieurs âges sont donnés
    naissance = _NAISSANCE.search(texte)
    if naissance and not _connu(updates, "birth_year"):
        _mettre(updates, "birth_year", int(naissance.group(1) or naissance.group(2)), texte, cible)
    # Réponse directe à la question posée : « 2026 » pour l'année de naissance, « 35 » pour l'âge
    if cible == "birth_year" and not _connu(updates, "birth_year"):
        annees = set(re.findall(r"(?<!\d)((?:19|20)\d\d)(?!\d)", texte))
        if len(annees) == 1:
            _mettre(updates, "birth_year", int(annees.pop()), texte, cible)
    if cible == "age" and not _connu(updates, "age") and not _connu(updates, "birth_year"):
        nombres = set(re.findall(r"(?<![\d.,])(\d{1,3})(?![\d.,])", texte))
        if len(nombres) == 1 and int(next(iter(nombres))) <= 120:
            _mettre(updates, "age", int(nombres.pop()), texte, cible)
    ages = _AGE.findall(texte)
    if (len(set(ages)) == 1 and not _PLUSIEURS_AGES.search(texte)
            and not _connu(updates, "age") and not _connu(updates, "birth_year")):
        _mettre(updates, "age", int(ages[0]), texte, cible)

    # Répondre à « pour qui faisons-nous la comparaison ? » désigne une seule personne
    if cible == "multiple_people":
        updates["multiple_people"] = {"value": False, "status": "known", "correction": True}

    return {k: v for k, v in updates.items() if k in FIELDS}
