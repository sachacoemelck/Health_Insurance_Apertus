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


# Page d'inscription / de demande d'offre en ligne de chaque caisse (assurance de base), trouvée par
# tests/apertus/trouver_liens_caisses.py et vérifiée (la page répond) le JJ.MM.2026. Sans lien vérifié,
# l'application donne le site officiel de la liste OFSP.
LIENS_INSCRIPTION = {}


def lien_inscription(numero):
    """(adresse, True) si une page d'inscription vérifiée existe, sinon (site officiel, False)."""
    if numero in LIENS_INSCRIPTION:
        return LIENS_INSCRIPTION[numero], True
    c = contact(numero)
    return (c["site"] if c else None), False
