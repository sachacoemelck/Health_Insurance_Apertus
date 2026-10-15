"""Demande d'affiliation à la nouvelle caisse : tout est préparé, la personne n'a plus qu'à l'envoyer.

Apertus 70B rédige la demande (e-mail ou lettre) à partir de l'offre choisie ; Python vérifie qu'elle
contient tout ce qu'il faut (caisse, produit, modèle, franchise, couverture accidents, date de début,
assurance de base, champs personnels à compléter) et qu'aucun numéro ni montant n'est inventé. Sinon,
une demande modèle écrite à l'avance est utilisée. Les contacts viennent de la liste officielle OFSP
(caisses.py). L'application n'envoie rien elle-même : le bouton ouvre la messagerie de la personne avec
la demande prête, et rien n'est enregistré.

Pourquoi s'affilier d'abord : l'assurance actuelle ne prend fin que lorsque la nouvelle caisse a
confirmé la couverture (LAMal art. 7 al. 5).
"""
import datetime
import re
from urllib.parse import quote

import changement
from chatbot import nombres
from langues import tr

# Champs que la personne remplit elle-même : Apertus n'invente aucune donnée personnelle
CHAMPS = {
    "fr": ["[Prénom Nom]", "[Adresse]", "[NPA Localité]", "[Date de naissance]", "[Numéro AVS]",
           "[Lieu, date]", "[Signature]"],
    "de": ["[Vorname Name]", "[Adresse]", "[PLZ Ort]", "[Geburtsdatum]", "[AHV-Nummer]", "[Ort, Datum]",
           "[Unterschrift]"],
    "it": ["[Nome Cognome]", "[Indirizzo]", "[NPA Località]", "[Data di nascita]", "[Numero AVS]",
           "[Luogo, data]", "[Firma]"],
}
_ACCIDENT = {"fr": r"accident", "de": r"unfall", "it": r"infortun"}
_INCLUS = {"fr": r"\b(?:avec|inclu|compris)", "de": r"\b(?:mit\b|inklusive|eingeschlossen|einschliess)",
           "it": r"\b(?:con\b|inclus|compres)"}
_EXCLU = {"fr": r"\b(?:sans|exclu|suspen)", "de": r"\b(?:ohne|ausgeschlossen|sistier|ausschliess)",
          "it": r"\b(?:senza|esclus|sospes)"}
_BASE = {
    "fr": r"assurance (?:obligatoire des soins|de base|maladie de base)|\bLAMal\b",
    "de": r"Grundversicherung|obligatorische[n]? Krankenpflegeversicherung|\bKVG\b",
    "it": r"assicurazione (?:obbligatoria delle cure|di base|malattie di base)|\bLAMal\b",
}
_NOMS_LANGUE = {"fr": "français", "de": "allemand (Hochdeutsch, forme « Sie »)", "it": "italien (forme « Lei »)"}


def debut_couverture(annee_primes):
    """Premier jour de la nouvelle assurance : le lendemain de la fin de l'assurance actuelle (même
    règle de délai que la lettre de résiliation)."""
    return changement.dates(annee_primes)[0] + datetime.timedelta(days=1)


def _date(d, langue):
    if langue == "fr" and d.day == 1:
        return f"1er {changement._MOIS_NOMS['fr'][d.month - 1]} {d.year}"
    return changement.date_texte(d, langue)


def _date_cherchee(d, langue):
    mois = changement._MOIS_NOMS[langue][d.month - 1]
    return (rf"(?:\b0?{d.day}(?:er|°|\.)?\s*{mois}\s*{d.year}|\b0?{d.day}\.\s*0?{d.month}\.\s*{d.year})")


def objet(choix, langue):
    """Objet de l'e-mail (texte fixe traduit ; caisse et produit tels quels)."""
    debut = debut_couverture(choix["annee"])
    return tr("Demande d'affiliation à l'assurance de base dès le {debut} – {produit}", langue,
              debut=f"{debut.day}.{debut.month}.{debut.year}", produit=choix["produit"])


def faits(choix, langue):
    """Ce qu'Apertus doit mettre dans la demande : tout vient de l'offre choisie (données OFSP)."""
    accident = tr("incluse", langue) if choix["accident"] else tr("exclue (déjà assuré par mon employeur)", langue)
    lignes = [f"Nouvelle caisse : {choix['caisse']}",
              f"Produit : {choix['produit']}",
              f"Modèle : {tr(choix['modele'], langue)}",
              f"Franchise : {choix['franchise']} CHF par an",
              f"Couverture accidents : {accident}",
              f"Prime selon les primes officielles {choix['annee']} : {choix['prime_mois']:.2f} CHF par mois",
              f"Début de l'assurance : {_date(debut_couverture(choix['annee']), langue)}"]
    if choix.get("ancienne"):
        lignes.append(f"Caisse actuelle (à résilier) : {choix['ancienne']}")
    return "\n".join(lignes)


PROMPT = """Tu rédiges, au nom d'une personne, une demande d'affiliation à l'assurance maladie de base
(LAMal) suisse, adressée à sa nouvelle caisse. Elle sera envoyée par e-mail ou par la poste.
Écris le texte COMPLET en {langue}, poli et court. Il doit contenir :
- en haut, les champs de l'expéditeur, recopiés EXACTEMENT avec leurs crochets : {champs_haut} ;
- le lieu et la date : {lieu_date} ;
- un objet clair ;
- la demande d'affiliation à l'assurance obligatoire des soins (assurance de base) à partir de la date de
  début indiquée, avec le produit, le modèle, la franchise et la couverture accidents des FAITS ;
- la date de naissance avec le champ {naissance} et le numéro AVS avec le champ {avs} ;
- s'il y a une caisse actuelle dans les faits : dire qu'elle sera résiliée, et demander une confirmation
  écrite de la couverture, nécessaire pour que la résiliation prenne effet ;
- la demande d'envoyer la police d'assurance ou les documents à signer ;
- une formule de politesse, puis le champ {signature} et le champ {nom}.
Recopie les noms et les montants des faits exactement. N'invente aucun nom, aucune adresse, aucun numéro :
utilise les champs entre crochets. Réponds uniquement par le texte, sans explication."""


def consignes(langue):
    c = CHAMPS[langue]
    return (PROMPT.replace("{langue}", _NOMS_LANGUE[langue]).replace("{champs_haut}", ", ".join(c[:3]))
            .replace("{lieu_date}", c[5]).replace("{naissance}", c[3]).replace("{avs}", c[4])
            .replace("{signature}", c[6]).replace("{nom}", c[0]))


def problemes(texte, choix, langue):
    """Éléments obligatoires manquants ou erreurs (liste vide si la demande est correcte)."""
    t = texte or ""
    p = []
    premier_mot = changement._simple(choix["caisse"]).split()[0]
    if premier_mot not in changement._simple(t):
        p.append(f"le nom de la caisse ({choix['caisse']}) manque")
    if choix["produit"].lower() not in t.lower():
        p.append(f"le nom exact du produit ({choix['produit']}) manque")
    f = choix["franchise"]
    if not re.search(rf"\b{f}\b" + (rf"|\b{f // 1000}['’ ]{f % 1000:03d}\b" if f >= 1000 else ""), t):
        p.append(f"la franchise ({choix['franchise']} CHF) manque")
    debut = debut_couverture(choix["annee"])
    if not re.search(_date_cherchee(debut, langue), t, re.IGNORECASE):
        p.append(f"la date de début ({_date(debut, langue)}) manque")
    if not re.search(_BASE[langue], t, re.IGNORECASE):
        p.append("il faut dire qu'il s'agit de l'assurance de base (obligatoire)")
    phrases = [x for x in re.split(r"(?<=[.!?])\s+|\n", t) if re.search(_ACCIDENT[langue], x, re.IGNORECASE)]
    attendu = _INCLUS if choix["accident"] else _EXCLU
    if not any(re.search(attendu[langue], x, re.IGNORECASE) for x in phrases):
        p.append("la couverture accidents doit être " + ("incluse" if choix["accident"] else "exclue"))
    for champ in CHAMPS[langue]:
        if champ.lower() not in t.lower():
            p.append(f"le champ {champ} manque")
    if choix.get("ancienne") and changement._simple(choix["ancienne"]).split()[0] not in changement._simple(t):
        p.append(f"la caisse actuelle ({choix['ancienne']}) manque")
    autorises = ({float(choix["franchise"]), float(choix["prime_mois"]), float(round(choix["prime_mois"])),
                  float(debut.year), float(debut.year - 1), float(choix["annee"]), 1.0, 7.0, 5.0, 12.0, 31.0}
                 | {float(n) for n in range(1, 11)})
    hors_champs = re.sub(r"\[[^\]]*\]", "", t)
    for nom in (choix["produit"], choix["caisse"]):  # chiffres d'un nom de produit (« Hausarzt 24 »)
        hors_champs = re.sub(re.escape(nom), "", hors_champs, flags=re.IGNORECASE)
    inventes = sorted({n for n in nombres(hors_champs) if n not in autorises})
    if inventes:
        p.append("n'invente aucun numéro ni montant (" + ", ".join(f"{n:g}" for n in inventes) + ")")
    if len(t) > 2500:
        p.append("le texte est trop long")
    return p


def demande_modele(choix, langue):
    """Demande sûre écrite à l'avance (si celle d'Apertus n'est pas complète)."""
    c = CHAMPS[langue]
    debut = _date(debut_couverture(choix["annee"]), langue)
    modele = tr(choix["modele"], langue)
    f, prod, caisse, prime = choix["franchise"], choix["produit"], choix["caisse"], f"{choix['prime_mois']:.2f}"
    anc = choix.get("ancienne")
    if langue == "de":
        acc = "mit Unfalldeckung" if choix["accident"] else "ohne Unfalldeckung (über meinen Arbeitgeber versichert)"
        corps = (f"Antrag auf Aufnahme in die obligatorische Krankenpflegeversicherung (Grundversicherung)\n\n"
                 f"Sehr geehrte Damen und Herren\n\n"
                 f"Hiermit beantrage ich die Aufnahme in Ihre Grundversicherung nach KVG ab dem {debut}: "
                 f"Produkt {prod}, Modell {modele}, Franchise {f} CHF, {acc}. Gemäss den offiziellen Prämien "
                 f"{choix['annee']} beträgt die Prämie {prime} CHF pro Monat.\n\n"
                 f"Geburtsdatum: {c[3]}\nAHV-Nummer: {c[4]}\n\n"
                 + (f"Meine Grundversicherung bei {anc} wird gekündigt. Bitte bestätigen Sie mir die Aufnahme "
                    f"schriftlich, damit die Kündigung wirksam wird.\n\n" if anc else
                    "Bitte bestätigen Sie mir die Aufnahme schriftlich.\n\n")
                 + f"Bitte senden Sie mir die Police oder die zu unterzeichnenden Unterlagen.\n\n"
                   f"Freundliche Grüsse\n\n{c[6]}\n{c[0]}")
    elif langue == "it":
        acc = "con copertura infortuni" if choix["accident"] else "senza copertura infortuni (assicurato tramite il datore di lavoro)"
        corps = (f"Domanda di affiliazione all'assicurazione obbligatoria delle cure (assicurazione di base)\n\n"
                 f"Gentili Signore e Signori,\n\n"
                 f"con la presente chiedo l'affiliazione alla vostra assicurazione di base (LAMal) a partire dal "
                 f"{debut}: prodotto {prod}, modello {modele}, franchigia {f} CHF, {acc}. Secondo i premi "
                 f"ufficiali {choix['annee']}, il premio è di {prime} CHF al mese.\n\n"
                 f"Data di nascita: {c[3]}\nNumero AVS: {c[4]}\n\n"
                 + (f"La mia assicurazione di base presso {anc} sarà disdetta. Vi prego di confermarmi "
                    f"l'affiliazione per iscritto, affinché la disdetta abbia effetto.\n\n" if anc else
                    "Vi prego di confermarmi l'affiliazione per iscritto.\n\n")
                 + f"Vi prego di inviarmi la polizza o i documenti da firmare.\n\nCordiali saluti\n\n{c[6]}\n{c[0]}")
    else:
        acc = ("avec la couverture accidents" if choix["accident"]
               else "sans la couverture accidents (je suis assuré par mon employeur)")
        corps = (f"Objet : demande d'affiliation à l'assurance obligatoire des soins (assurance de base)\n\n"
                 f"Madame, Monsieur,\n\n"
                 f"Par la présente, je demande mon affiliation à votre assurance de base (LAMal) à partir du "
                 f"{debut} : produit {prod}, modèle {modele}, franchise de {f} CHF, {acc}. Selon les primes "
                 f"officielles {choix['annee']}, la prime est de {prime} CHF par mois.\n\n"
                 f"Date de naissance : {c[3]}\nNuméro AVS : {c[4]}\n\n"
                 + (f"Mon assurance de base auprès de {anc} sera résiliée. Je vous prie de me confirmer "
                    f"l'affiliation par écrit, afin que la résiliation prenne effet.\n\n" if anc else
                    "Je vous prie de me confirmer l'affiliation par écrit.\n\n")
                 + f"Merci de m'envoyer la police d'assurance ou les documents à signer.\n\n"
                   f"Veuillez agréer, Madame, Monsieur, mes salutations distinguées.\n\n{c[6]}\n{c[0]}")
    return f"{c[0]}\n{c[1]}\n{c[2]}\n\n{caisse}\n\n{c[5]}\n\n{corps}"


def rediger(appeler_70b, choix, langue):
    """(texte, "apertus" ou "modele") : la demande d'Apertus si elle passe les contrôles (un nouvel essai
    avec la liste des problèmes), sinon la demande modèle."""
    demande = "FAITS :\n" + faits(choix, langue) + "\n\nRédige la demande."
    texte = ""
    try:
        texte = (appeler_70b(consignes(langue), demande) or "").strip()
        p = problemes(texte, choix, langue)
        if p:
            texte = (appeler_70b(consignes(langue), demande + "\n\nATTENTION, corrige : " + " ; ".join(p)) or "").strip()
            p = problemes(texte, choix, langue)
        if not p:
            return texte, "apertus"
    except Exception:
        pass
    return demande_modele(choix, langue), "modele"


def avec_adresse(texte, numero, caisse_affichee):
    """Ajoute l'adresse postale officielle (liste OFSP) sous le nom de la caisse destinataire, pour une
    lettre prête à poster. Sans adresse connue, le texte est rendu tel quel."""
    import caisses
    adresse = caisses.adresse_postale(numero, caisse_affichee)
    if not adresse:
        return texte
    lignes = texte.split("\n")
    i = next((k for k, l in enumerate(lignes) if l.strip() == caisse_affichee.strip()), None)
    if i is None:
        return texte
    return "\n".join(lignes[:i] + adresse + lignes[i + 1:])


def lien_mailto(email, sujet, corps):
    """Lien qui ouvre la messagerie de la personne avec le destinataire, l'objet et le texte remplis."""
    return f"mailto:{email}?subject={quote(sujet)}&body={quote(corps.replace(chr(13), '').replace(chr(10), chr(13) + chr(10)))}"


def rappel_ics(limite, caisse, langue):
    """Rappel d'agenda (.ics) une semaine avant la date limite de réception de la résiliation."""
    jour = limite - datetime.timedelta(days=7)
    titre = tr("Résilier l'assurance de base chez {caisse} (lettre reçue au plus tard le {limite})", langue,
               caisse=caisse, limite=f"{limite.day}.{limite.month:02d}.{limite.year}")
    fin = jour + datetime.timedelta(days=1)
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//LAMal Navigator//FR\r\nBEGIN:VEVENT\r\n"
            f"UID:resiliation-{limite.isoformat()}@lamal-navigator\r\n"
            f"DTSTAMP:{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}\r\n"
            f"DTSTART;VALUE=DATE:{jour.strftime('%Y%m%d')}\r\nDTEND;VALUE=DATE:{fin.strftime('%Y%m%d')}\r\n"
            f"SUMMARY:{titre}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
