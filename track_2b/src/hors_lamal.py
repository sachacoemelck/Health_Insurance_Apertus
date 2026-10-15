"""Ce que l'assurance de base (LAMal) ne couvre pas, pour les besoins cochés dans le formulaire.

Textes fixes, écrits à partir des articles de loi de data/lois.json (fedlex, version du 1.7.2026) et
relus article par article ; chaque ligne donne sa source. Aucun prix : les assurances complémentaires
relèvent du droit privé (LCA), leurs primes ne sont pas publiées et dépendent de la personne.
L'application dit seulement ce que la base ne paie pas, puis que cela relève d'une complémentaire.
"""
from conversation import LOIS

# Pour chaque besoin : libellé, ce que l'assurance de base paie, ce qu'elle ne paie pas, sources
# (loi, précision d'article, ancre fedlex ou None).
BESOINS = {
    "lunettes": {
        "fr": ("Lunettes et lentilles",
               "Enfants jusqu'à 18 ans : environ 180 CHF par année. Adultes : seulement pour certaines maladies "
               "des yeux (liste fédérale des moyens et appareils).",
               "Lunettes et lentilles d'un adulte qui voit mal sans maladie de l'œil (myopie, presbytie…)."),
        "de": ("Brille und Kontaktlinsen",
               "Kinder bis 18 Jahre: rund 180 CHF pro Jahr. Erwachsene: nur bei bestimmten Augenkrankheiten "
               "(eidgenössische Mittel- und Gegenständeliste).",
               "Brillen und Linsen von Erwachsenen ohne Augenkrankheit (Kurzsichtigkeit, Altersweitsichtigkeit…)."),
        "it": ("Occhiali e lenti a contatto",
               "Bambini fino a 18 anni: circa 180 CHF all'anno. Adulti: solo per alcune malattie degli occhi "
               "(elenco federale dei mezzi e degli apparecchi).",
               "Occhiali e lenti di un adulto senza malattia dell'occhio (miopia, presbiopia…)."),
        "en": ("Glasses and contact lenses",
               "Children up to 18: about 180 CHF per year. Adults: only for certain eye diseases (federal list "
               "of aids and appliances).",
               "Glasses and lenses for adults without an eye disease (short-sightedness, presbyopia…)."),
        "sources": [("OPAS", "annexe 2", None)],
    },
    "dentaire": {
        "fr": ("Dentiste",
               "Seulement si les soins sont causés par une maladie grave (de la mastication ou générale) ou "
               "nécessaires pour la traiter, et après un accident.",
               "Contrôles, détartrage, caries, couronnes, appareils dentaires (orthodontie)."),
        "de": ("Zahnarzt",
               "Nur wenn die Behandlung durch eine schwere Krankheit (des Kausystems oder allgemein) verursacht "
               "wird oder zu deren Behandlung nötig ist, sowie nach einem Unfall.",
               "Kontrollen, Dentalhygiene, Karies, Kronen, Zahnspangen (Kieferorthopädie)."),
        "it": ("Dentista",
               "Solo se le cure sono causate da una malattia grave (dell'apparato masticatorio o generale) o "
               "necessarie per curarla, e dopo un infortunio.",
               "Controlli, igiene dentale, carie, corone, apparecchi (ortodonzia)."),
        "en": ("Dentist",
               "Only if the treatment is caused by a serious illness (of the chewing system or general) or needed "
               "to treat it, and after an accident.",
               "Check-ups, cleaning, cavities, crowns, braces (orthodontics)."),
        "sources": [("LAMal", "art. 31", "art_31")],
    },
    "medecines": {
        "fr": ("Médecines complémentaires",
               "5 méthodes, si elles sont pratiquées par un médecin avec le titre reconnu : acupuncture, médecine "
               "anthroposophique, pharmacothérapie chinoise, homéopathie classique, phytothérapie.",
               "Thérapeutes qui ne sont pas médecins (naturopathe, ostéopathe, masseur…) et les autres méthodes."),
        "de": ("Komplementärmedizin",
               "5 Methoden, wenn eine Ärztin oder ein Arzt mit anerkanntem Titel sie ausübt: Akupunktur, "
               "anthroposophische Medizin, chinesische Arzneitherapie, klassische Homöopathie, Phytotherapie.",
               "Therapeutinnen und Therapeuten ohne Arztdiplom (Naturheilpraktiker, Osteopathie, Massage…) und "
               "andere Methoden."),
        "it": ("Medicine complementari",
               "5 metodi, se praticati da un medico con il titolo riconosciuto: agopuntura, medicina "
               "antroposofica, farmacoterapia cinese, omeopatia classica, fitoterapia.",
               "Terapisti che non sono medici (naturopata, osteopata, massaggiatore…) e gli altri metodi."),
        "en": ("Complementary medicine",
               "5 methods, if practised by a doctor with the recognised title: acupuncture, anthroposophic "
               "medicine, Chinese herbal therapy, classical homeopathy, phytotherapy.",
               "Therapists who are not doctors (naturopath, osteopath, massage…) and other methods."),
        "sources": [("OPAS", "art. 4b", "art_4_b")],
    },
    "hopital": {
        "fr": ("Hôpital : chambre privée ou demi-privée",
               "Séjour en division commune d'un hôpital de la liste de votre canton ou du canton de l'hôpital, "
               "jusqu'au tarif de votre canton.",
               "Chambre privée ou demi-privée, libre choix du médecin à l'hôpital, différence de tarif dans un "
               "hôpital d'un autre canton."),
        "de": ("Spital: Privat- oder Halbprivatabteilung",
               "Aufenthalt in der allgemeinen Abteilung eines Listenspitals Ihres Kantons oder des Standortkantons, "
               "bis zum Tarif Ihres Kantons.",
               "Privat- oder Halbprivatzimmer, freie Arztwahl im Spital, Tarifdifferenz in einem Spital eines "
               "anderen Kantons."),
        "it": ("Ospedale: reparto privato o semiprivato",
               "Degenza nel reparto comune di un ospedale dell'elenco del suo cantone o del cantone dell'ospedale, "
               "fino alla tariffa del suo cantone.",
               "Camera privata o semiprivata, libera scelta del medico in ospedale, differenza di tariffa in un "
               "ospedale di un altro cantone."),
        "en": ("Hospital: private or semi-private ward",
               "Stay in the general ward of a hospital on the list of your canton or of the hospital's canton, up "
               "to your canton's tariff.",
               "Private or semi-private room, free choice of doctor in hospital, tariff difference in a hospital "
               "in another canton."),
        "sources": [("LAMal", "art. 25 al. 2 let. e", "art_25"), ("LAMal", "art. 41 al. 1bis", "art_41")],
    },
    "etranger": {
        "fr": ("Soins à l'étranger",
               "Urgences pendant un séjour temporaire : jusqu'au double de ce que le traitement coûterait en "
               "Suisse.",
               "Soins planifiés à l'étranger, frais au-delà du double (pays chers comme les États-Unis), "
               "rapatriement en Suisse."),
        "de": ("Behandlung im Ausland",
               "Notfälle während eines vorübergehenden Aufenthalts: bis zum Doppelten der Kosten in der Schweiz.",
               "Geplante Behandlungen im Ausland, Kosten über dem Doppelten (teure Länder wie die USA), "
               "Rücktransport in die Schweiz."),
        "it": ("Cure all'estero",
               "Urgenze durante un soggiorno temporaneo: fino al doppio di quanto costerebbe la cura in Svizzera.",
               "Cure pianificate all'estero, costi oltre il doppio (paesi cari come gli Stati Uniti), rimpatrio "
               "in Svizzera."),
        "en": ("Treatment abroad",
               "Emergencies during a temporary stay: up to twice what the treatment would cost in Switzerland.",
               "Planned treatment abroad, costs above twice the Swiss amount (expensive countries such as the "
               "USA), repatriation to Switzerland."),
        "sources": [("OAMal", "art. 36 al. 2 et 4", "art_36"), ("OPAS", "art. 27", "art_27")],
    },
}

_TEXTE_LOI = {"fr": "fr", "de": "de", "it": "it", "en": "fr"}  # pas de texte de loi officiel en anglais
_MOTS = {"de": {"art.": "Art.", "al.": "Abs.", "let.": "Bst.", "annexe": "Anhang", " et ": " und "},
         "it": {"al.": "cpv.", "let.": "lett.", "annexe": "allegato", " et ": " e "},
         "en": {"al.": "para.", "let.": "let.", "annexe": "Annex", " et ": " and "}}


def libelle(cle, code="fr"):
    return BESOINS[cle].get(code, BESOINS[cle]["fr"])[0]


def sources(cle, code="fr"):
    """[(texte, lien)] : références lisibles dans la langue, liens fedlex vers l'article."""
    resultat = []
    for loi, ref, ancre in BESOINS[cle]["sources"]:
        url, noms = LOIS[loi]
        for fr, autre in _MOTS.get(code, {}).items():
            ref = ref.replace(fr, autre)
        lien = url.format(l=_TEXTE_LOI.get(code, "fr")) + (f"#{ancre}" if ancre else "")
        resultat.append((f"{noms.get(code, loi)} {ref}", lien))
    return resultat


def lignes(cles, code="fr"):
    """Lignes du tableau : (libellé, ce que la base paie, ce qu'elle ne paie pas, sources)."""
    return [(*BESOINS[c].get(code, BESOINS[c]["fr"]), sources(c, code)) for c in cles if c in BESOINS]


def faits(cles):
    """Pour l'ouverture d'Apertus : ce que la base couvre ou non pour les besoins cochés (en français)."""
    return [f"- {BESOINS[c]['fr'][0]} : l'assurance de base paie : {BESOINS[c]['fr'][1]} Elle ne paie pas : "
            f"{BESOINS[c]['fr'][2]} Pour cela, il faut une assurance complémentaire." for c in cles if c in BESOINS]
