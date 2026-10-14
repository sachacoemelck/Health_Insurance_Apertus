"""Où demander une réduction individuelle des primes (subside) : l'office compétent de chaque canton.

Source : liste officielle de l'Office fédéral de la santé publique (OFSP), « Services cantonaux pour la
réduction des primes », état novembre 2025 :
https://www.bag.admin.ch/dam/fr/sd-web/qWdCRIbMa780/kantonale%20Stellen%20Pr%C3%A4mienverbilligung%202025%20(f)_Nov.%202025.pdf
Noms et sites recopiés de ce document. Le 13.10.2026, chaque site a été ouvert : quand le site de
l'office a une page dédiée aux subsides, c'est elle qui est donnée (lien direct vérifié) ; sinon, la
page d'accueil indiquée par l'OFSP. Non vérifiables depuis notre outil (site bloqué ou redirigé) :
AG (redirige vers sva-aargau.ch), AI, BE, BS ; leurs adresses restent celles de la liste OFSP.
"""
import re

from langues import tr

SOURCE_OFSP = "https://www.bag.admin.ch/fr/assurance-maladie-reduction-des-primes"

OFFICES = {
    "AG": ("SVA Aargau", "https://www.sva-ag.ch/pv"),
    "AI": ("Gesundheitsamt Appenzell Innerrhoden", "https://www.ai.ch"),
    "AR": ("Sozialversicherungen Appenzell Ausserrhoden", "https://www.sovar.ch/dienstleistungen/prämienverbilligung-ipv"),
    "BE": ("Amt für Sozialversicherungen, Prämienverbilligung / Office des assurances sociales",
           "https://www.asv.dij.be.ch"),
    "BL": ("SVA Basel-Landschaft", "https://www.sva-bl.ch/de/ausgleichskasse/individuelle-praemienverbilligung-ipv"),
    "BS": ("Amt für Sozialbeiträge Basel-Stadt, Prämienverbilligung", "https://www.asb.bs.ch"),
    "FR": ("Caisse de compensation du canton de Fribourg", "https://www.ecasfr.ch/fr/Assurances/Reduction-des-primes-d-assurance-maladie/Reduction-des-primes-d-assurance-maladie.html"),
    "GE": ("Service de l'assurance maladie", "https://www.ge.ch"),
    "GL": ("Kantonale Steuerverwaltung Glarus, Fachstelle IPV", "https://www.gl.ch"),
    "GR": ("SVA Graubünden", "https://www.sva.gr.ch"),
    "JU": ("Caisse de compensation du Jura", "https://www.ecasjura.ch/fr/Assurances/Assurance-maladie/Reduction-des-primes-d-assurance-maladie-RPI-Informations-generales-2026/Reduction-des-primes-d-assurance-maladie-RPI-Informations-generales-2026.html"),
    "LU": ("WAS Wirtschaft Arbeit Soziales, Ausgleichskasse Luzern", "https://www.was-luzern.ch/praemienverbilligung"),
    "NE": ("Office de l'assurance-maladie et des bourses d'études", "https://www.ne.ch"),
    "NW": ("Ausgleichskasse Nidwalden", "https://www.aknw.ch/dienstleistungen/praemienverbilligung-ipv"),
    "OW": ("Ausgleichskasse Obwalden", "https://www.akow.ch/ipv"),
    "SG": ("SVA St. Gallen", "https://www.svasg.ch/ipv"),
    "SH": ("SVA Schaffhausen", "https://www.svash.ch"),
    "SO": ("Ausgleichskasse des Kantons Solothurn", "https://www.akso.ch/dienstleistungen/praemienverbilligung-ipv"),
    "SZ": ("SVA Schwyz", "https://www.sva-sz.ch/dienstleistungen/prämienverbilligung-ipv"),
    "TG": ("Krankenkassen-Kontrollstelle der Wohngemeinde / Amt für Gesundheit Thurgau", "https://gesundheit.tg.ch/bevoelkerung/krankenversicherung.html/5343"),
    "TI": ("Istituto delle assicurazioni sociali, Servizio sussidi assicurazione malattia", "https://www.ti.ch"),
    "UR": ("Sozialversicherungsstelle Uri", "https://www.svsuri.ch/dienstleistungen/prämienverbilligung-ipv"),
    "VD": ("Office vaudois de l'assurance-maladie", "https://www.vd.ch"),
    "VS": ("Caisse de compensation du canton du Valais", "https://www.avsvalais.ch/fr/Assurances/RIP-Reduction-individuelle-des-primes-d-assurance-maladie/Reduction-des-primes-d-assurance-maladie/Reduction-des-primes-caisse-maladie.html"),
    "ZG": ("Ausgleichskasse Zug", "https://www.akzug.ch/ipv"),
    "ZH": ("SVA Zürich", "https://svazurich.ch"),
}

# La personne parle de subside / réduction des primes (quatre langues)
PARLE_DE_SUBSIDE = re.compile(
    r"subsides?|r[ée]duction (?:individuelle )?(?:des|de) primes?|aide (?:pour|à) (?:payer|la prime)|"
    r"pr[äa]mienverbilligung|\bipv\b|verbilligung|sussidi|riduzione (?:dei|del) premi|"
    r"premium (?:reduction|subsid)|subsid", re.IGNORECASE)


def office(canton, code="fr"):
    """Phrase avec le lien vers l'office compétent du canton (Markdown), ou None si canton inconnu."""
    if canton not in OFFICES:
        return None
    nom, url = OFFICES[canton]
    return tr("Dans votre canton ({canton}), la demande se fait auprès de : [{office}]({url}). Liste officielle de "
              "tous les cantons : [OFSP]({source}).", code, canton=canton, office=nom, url=url, source=SOURCE_OFSP)
