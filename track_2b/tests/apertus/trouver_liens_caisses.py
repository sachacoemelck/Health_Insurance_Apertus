"""Cherche, pour chaque caisse qui a des primes 2027, la page de son site où l'on calcule sa prime et
demande une offre ou s'inscrit en ligne (assurance de base). Lancé une fois, sur une machine qui a accès
à internet ; le résultat sert à remplir LIENS_INSCRIPTION dans src/caisses.py, puis l'application
n'appelle plus aucun site.

Méthode : on ouvre la page d'accueil officielle de la caisse (liste OFSP), on garde les liens dont
l'adresse ou le texte parle de calcul de prime, d'offre ou d'inscription, on ouvre chacun pour vérifier
qu'il répond (code 200), et on note l'adresse finale et le titre de la page.

    docker run --rm -v "$HOME\\Downloads:/dl" hia-nouveau python tests/apertus/trouver_liens_caisses.py
    -> crée Downloads\\liens_caisses.txt   (1 à 3 minutes ; aucune clé API nécessaire)
"""
import os as _os
import sys as _sys

_ICI = _os.path.dirname(_os.path.abspath(__file__))
_RACINE = _os.path.dirname(_os.path.dirname(_ICI))
_os.chdir(_RACINE)
_sys.path[:0] = [_ICI, _os.path.join(_RACINE, "src")]
RESULTATS = "/dl" if _os.path.isdir("/dl") else _os.path.join(_ICI, "resultats")
_os.makedirs(RESULTATS, exist_ok=True)
import html
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

import caisses  # noqa: E402
import comparateur  # noqa: E402

MOTS = re.compile(r"pr(?:ä|ae|a)mien-?rechner|pr(?:ä|ae)mie(?:n)?\s*berechnen|calculat(?:eur|rice)|calcul(?:er)?[- ]"
                  r"(?:de[- ]|votre[- ]|sa[- ]|ma[- ])?prime|calcolat|calcol(?:are|a)[- ]?(?:il[- ])?premi|"
                  r"premium[- ]calculator|calculate[- ]premium|offert|offre|offerta|quote|antrag|inscri|"
                  r"abschliessen|abschluss|beitreten|s[’']?affilier|anmeld|online-?abschluss|grundversicherung|"
                  r"assurance[- ]de[- ]base|assicurazione[- ]di[- ]base|basic[- ]insurance", re.IGNORECASE)
ENTETES = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) LAMal-Navigator-link-check",
           "Accept-Language": "fr-CH,fr;q=0.9,de-CH;q=0.8,de;q=0.7,it;q=0.6,en;q=0.5"}


class Liens(HTMLParser):
    def __init__(self):
        super().__init__()
        self.liens, self._href, self._texte, self.titre, self._dans_titre = [], None, [], "", False

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._texte = dict(attrs).get("href"), []
        elif tag == "title":
            self._dans_titre = True

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.liens.append((self._href, " ".join(self._texte).strip()))
            self._href = None
        elif tag == "title":
            self._dans_titre = False

    def handle_data(self, data):
        if self._href is not None:
            self._texte.append(data.strip())
        if self._dans_titre:
            self.titre += data.strip()


def ouvrir(url):
    requete = urllib.request.Request(url, headers=ENTETES)
    with urllib.request.urlopen(requete, timeout=20) as r:
        return r.status, r.geturl(), r.read(600_000).decode("utf-8", "replace")


def candidats(site):
    try:
        _, finale, page = ouvrir(site)
    except Exception as e:
        return None, f"accueil inaccessible ({e.__class__.__name__}: {str(e)[:80]})", []
    p = Liens()
    p.feed(page)
    vus, trouves = set(), []
    hote = urllib.parse.urlparse(finale).netloc.split(":")[0].removeprefix("www.")
    for href, texte in p.liens:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolu = urllib.parse.urljoin(finale, html.unescape(href)).split("#")[0]
        if absolu in vus or not MOTS.search(absolu + " " + texte):
            continue
        if hote not in urllib.parse.urlparse(absolu).netloc:  # liens vers d'autres sites (comparateurs…) ignorés
            continue
        vus.add(absolu)
        trouves.append((absolu, texte[:60]))
    return finale, None, trouves[:12]


def main():
    numeros = sorted(set(comparateur.df["Versicherer"].unique()))
    resultat, lignes = {}, []
    for n in numeros:
        c = caisses.contact(n)
        site = c["site"] if c else None
        lignes.append(f"\n=== {n} {comparateur.ASSUREURS.get(n)} — {site}")
        if not site:
            lignes.append("   pas de site dans la liste OFSP")
            continue
        finale, erreur, liste = candidats(site)
        if erreur:
            lignes.append("   " + erreur)
            print("\n".join(lignes[-2:]), flush=True)
            continue
        verifies = []
        for url, texte in liste:
            try:
                code, arrivee, page = ouvrir(url)
                p = Liens()
                p.feed(page)
                verifies.append({"url": arrivee, "code": code, "texte": texte, "titre": p.titre[:90]})
                lignes.append(f"   [{code}] {arrivee}   « {texte} »   titre : {p.titre[:90]}")
            except Exception as e:
                lignes.append(f"   [échec {e.__class__.__name__}] {url}   « {texte} »")
        if not liste:
            lignes.append(f"   aucun lien trouvé sur {finale} (site probablement en JavaScript)")
        resultat[int(n)] = {"site": finale, "liens": verifies}
        print("\n".join(lignes[-(len(liste) + 1):]), flush=True)
    with open(_os.path.join(RESULTATS, "liens_caisses.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lignes) + "\n\nJSON\n" + json.dumps(resultat, ensure_ascii=False, indent=1))
    print("\n-> liens_caisses.txt écrit")


if __name__ == "__main__":
    main()
