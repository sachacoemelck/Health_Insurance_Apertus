"""Contacts officiels des caisses maladie : adresse postale, téléphone, e-mail et site web.

Source : liste officielle des assureurs-maladie admis de l'Office fédéral de la santé publique (OFSP),
feuille « Zugelassene Krankenversicherer » de data/assureurs-admis-2026-10.xlsx (déjà utilisée pour les
noms des caisses). Rien n'est inventé : un contact absent de la liste (par exemple un e-mail remplacé par
un formulaire de contact) reste absent, et l'application propose alors le courrier ou le site.
"""
import re
from pathlib import Path

import pandas as pd

FICHIER = Path(__file__).resolve().parent.parent / "data" / "assureurs-admis-2026-10.xlsx"
FEUILLE = "Zugelassene Krankenversicherer"


def _joindre_nom(morceaux):
    """« Avenir Krankenver- » + « sicherung AG » -> « Avenir Krankenversicherung AG » ;
    « CSS Kranken- » + « Versicherung AG » -> « CSS Kranken-Versicherung AG »."""
    nom = ""
    for m in (x.strip() for x in morceaux if x and x.strip()):
        if nom.endswith("-"):
            nom = (nom[:-1] if m[:1].islower() else nom) + m
        else:
            nom = f"{nom} {m}".strip()
    nom = re.sub(r"(?<=[a-zäöü])-(?=[a-zäöü])", "", nom)  # « Unfallver-sicherung » coupé dans une cellule
    return re.sub(r"\s+", " ", nom)


def _contact(numero, noms, lignes):
    lignes = [l.strip() for l in lignes if l and l.strip()]
    tel = next((l for l in lignes if re.match(r"(?i)tel\.?\s", l)), None)
    email = next((l for l in lignes if re.fullmatch(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", l)), None)
    site = next((l for l in lignes if re.match(r"(?i)(?:https?://)?www\.", l)), None)
    debut_contacts = next((i for i, l in enumerate(lignes) if re.match(r"(?i)(?:tel|fax)\.?\s", l)), len(lignes))
    adresse = [l for l in lignes[:debut_contacts] if "@" not in l]
    return {"numero": numero, "nom": _joindre_nom(noms), "adresse": adresse,
            "telephone": re.sub(r"(?i)^tel\.?\s*", "", tel) if tel else None, "email": email,
            "site": ("https://" + re.sub(r"(?i)^https?://", "", site)) if site else None}


def lire_contacts(fichier=FICHIER):
    """{numéro OFSP: contact}. Une caisse s'étend parfois sur plusieurs lignes du tableur (les lignes
    suivantes n'ont pas de numéro) : elles sont réunies."""
    brut = pd.read_excel(fichier, sheet_name=FEUILLE, header=1)
    brut.columns = ["numero", "uid", "nom", "adresse", "forme", "groupe", "zone"]
    contacts, courant = {}, None
    for _, r in brut.iterrows():
        debut = re.match(r"\s*(\d+)", str(r["numero"])) if pd.notna(r["numero"]) else None
        if debut:
            if courant:
                contacts[courant[0]] = _contact(*courant)
            courant = (int(debut.group(1)), [], [])
        if courant is None:
            continue
        if pd.notna(r["nom"]):
            courant[1].extend(str(r["nom"]).split("\n"))
        if pd.notna(r["adresse"]):
            courant[2].extend(str(r["adresse"]).split("\n"))
    if courant:
        contacts[courant[0]] = _contact(*courant)
    return contacts


CONTACTS = lire_contacts()


def contact(numero):
    return CONTACTS.get(int(numero)) if numero is not None else None


def adresse_postale(numero, nom_affiche=None):
    """Adresse à mettre sur une lettre : nom de la caisse puis adresse officielle (lignes)."""
    c = contact(numero)
    if not c or not c["adresse"]:
        return None
    lignes = list(c["adresse"])
    # Lignes d'en-tête (« Groupe Mutuel », « Avenir Assurance », « Maladie ») : l'adresse commence à la
    # première ligne avec un numéro (rue, case postale, NPA) ou « Postfach / Case postale »
    debut = next((i for i, l in enumerate(lignes) if re.search(r"\d|postfach|case postale|casella", l, re.I)), 0)
    return [nom_affiche or c["nom"]] + lignes[debut:]


# Page de chaque caisse où commencer l'inscription à l'assurance de base, trouvée par
# tests/apertus/trouver_liens_caisses.py le 15.10.2026 et vérifiée ce jour-là (la page répond, code 200 ;
# résultat brut : docs/liens_caisses_2026-10-15.txt). Deux genres :
#   "offre" : calculateur de primes / demande d'offre en ligne (on y calcule la prime puis on s'inscrit) ;
#   "page"  : page « assurance de base » de la caisse (aucun calculateur trouvé sur sa page d'accueil).
# Sans lien trouvé (site en JavaScript), l'application donne le site officiel de la liste OFSP.
_GM = ("https://www.groupemutuel.ch/fr/clients-prives/vos-besoins/Vos-besoins-dans-le-domaine-de-la-sante/"
       "Trouver-la-meilleure-assurance-maladie-de-base.html", "page")
LIENS_INSCRIPTION = {
    8: ("https://www.css.ch/fr/clients-prives/bien-assure/caisse-maladie/assurance-de-base.html", "page"),
    32: ("https://calculator.aquilana.ch/", "offre"),
    134: ("https://kkeinsiedeln.ch/grundversicherung/", "page"),
    194: ("https://portal.sumiswalder.ch/portal/offerten", "offre"),
    246: ("https://www.kkst.ch/grundversicherung", "page"),
    290: ("https://www.praemienrechner.concordia.ch/ipr/home?lang=fr", "offre"),
    312: ("https://calculateur-de-primes.atupri.ch", "offre"),
    343: _GM, 1479: _GM, 1535: _GM,
    360: ("https://www.kklh.ch/versicherungen/grundversicherung/", "page"),
    376: ("https://www.kpt.ch/fr/assurances/calcul-prime-assurance-maladie", "offre"),
    455: ("https://www.oekk.ch/fr/clients-prives/assurances/assurance-de-base", "page"),
    509: ("https://www.sympany.ch/fr/contact/conseil-a-la-vente.html", "offre"),
    780: ("https://www.glkv.ch/versicherungen/grundversicherung/grundversicherung.html/48", "page"),
    881: ("https://www.egk.ch/calculer", "offre"),
    923: ("https://slkk.ch/de/grundversicherung-krankenkasse/", "page"),
    941: ("https://www.sodalis.ch/fr/pour-clients-prives/opter-pour-sodalis/offre-rapide", "offre"),
    1040: ("https://www.kkv.ch/services-2/downloads/antragsformulare/", "offre"),
    1318: ("https://www.kkwaedenswil.ch/versicherungen/grundversicherung", "page"),
    1384: ("https://www.swica.ch/fr/prive/services/calculateur-de-primes", "offre"),
    1386: ("https://www.galenos.ch/fr/personnes-privees/assurances/assurance-de-base/", "page"),
    1401: ("https://rhenusana.ch/grundversicherung/", "page"),
    1542: ("https://www.assura.ch/fr/assurances/assurances-de-base", "page"),
    1560: ("https://calculator.agrisano.ch/public/e/l/premium-calculator-home/de-CH/index", "offre"),
    1562: ("https://www.helsana.ch/fr/prives/assurances/calculateur-primes.html", "offre"),
}


def lien_inscription(numero):
    """(adresse, genre) : "offre" (calculateur / demande d'offre), "page" (page assurance de base) ou
    "site" (site officiel de la liste OFSP, quand aucune page n'a été trouvée)."""
    if numero in LIENS_INSCRIPTION:
        return LIENS_INSCRIPTION[numero]
    c = contact(numero)
    return (c["site"] if c else None), "site"
