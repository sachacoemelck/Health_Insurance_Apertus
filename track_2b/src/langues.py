"""Langues de l'interface : français, allemand, italien, anglais.

La langue est détectée par Python dans les messages de la personne (mots courants de chaque langue),
sans appel au modèle. Tous les textes fixes de l'application (questions, boutons, résumé, résultats)
viennent de la table TRAD ci-dessous ; Apertus, lui, reçoit simplement la langue de réponse.
Un texte absent de la table s'affiche en français (jamais d'erreur).
"""
import re

CODES = ("fr", "de", "it", "en")
# Nom de la langue tel qu'écrit dans les consignes (en français) données à Apertus
NOMS_POUR_APERTUS = {"fr": "français", "de": "allemand (Hochdeutsch, vouvoiement « Sie »)",
                     "it": "italien (vouvoiement « Lei »)", "en": "anglais"}

_MOTS = {
    "fr": "je j' suis ai habite vis ans franchise avec sans le la les des une un est et pour mon ma mes "
          "quoi quel quelle c'est pas oui non bonjour salut merci comment combien pourquoi assurance",
    "de": "ich bin habe wohne jahre jahr alt mit ohne der die das und ist nicht ja nein ein eine mein "
          "meine was wie warum wieviel welche franchise versicherung grüezi hallo danke unfall bitte",
    "it": "sono ho abito vivo anni anno con senza il lo la gli le è e non sì si no un una mio mia "
          "cosa come perché quanto quale franchigia assicurazione buongiorno ciao grazie infortuni",
    "en": "i i'm am have live years year old with without the and is not yes no a an my what how why "
          "which much insurance deductible hello hi thanks please accident cover",
}
_ENS = {k: set(v.split()) for k, v in _MOTS.items()}


def detecter(texte):
    """Code de langue du message, ou None s'il est trop court ou ambigu (« 2500 », « Lausanne »)."""
    mots = re.findall(r"[a-zà-ÿ']+", (texte or "").lower())
    if len(mots) < 2:
        return None
    scores = {code: sum(m in _ENS[code] for m in mots) for code in CODES}
    meilleur = max(scores, key=scores.get)
    second = sorted(scores.values())[-2]
    return meilleur if scores[meilleur] >= 2 and scores[meilleur] > second else None


_TUTOIEMENT = {
    "fr": r"\b(?:tu|te|toi|ton|ta|tes)\b|\bt['’]",
    "de": r"\b(?:du|dich|dir|dein|deine|deinen|deinem|deiner)\b",
    "it": r"\b(?:tu|ti|te|tuo|tua|tuoi|tue)\b",
    "en": r"(?!)",
}


def tutoie(texte, langue="fr"):
    return bool(re.search(_TUTOIEMENT.get(langue, _TUTOIEMENT["fr"]), texte or "", re.IGNORECASE))


def tr(texte, langue="fr", **valeurs):
    """Traduction d'un texte fixe français (avec ses {valeurs})."""
    traduit = TRAD.get(texte, {}).get(langue, texte) if langue != "fr" else texte
    return traduit.format(**valeurs) if valeurs else traduit


# Placeholder fixe et multilingue : s'il changeait, Streamlit perdrait le premier message suivant
PLACEHOLDER = "Écrivez ici · Hier schreiben · Scriva qui · Write here…"

T = {}  # (fr) -> (de, it, en), rempli ci-dessous puis converti en TRAD


def _(fr, de, it, en):
    T[fr] = (de, it, en)


# --- Accueil, en-tête, erreurs ------------------------------------------------------------------
_("Bonjour ! Je suis votre conseiller pour l'assurance maladie de base (LAMal), avec Apertus. "
  "Parlez-moi de vous : votre âge, votre commune, et ce qui compte pour vous (budget, choix du "
  "médecin…). Vous pouvez aussi me poser vos questions sur la LAMal à tout moment.",
  "Grüezi! Ich bin Ihr Berater für die Grundversicherung (KVG), mit Apertus. Erzählen Sie mir von "
  "sich: Ihr Alter, Ihre Gemeinde und was Ihnen wichtig ist (Budget, Arztwahl…). Sie können mir "
  "jederzeit auch Fragen zur Grundversicherung stellen.",
  "Buongiorno! Sono il suo consulente per l'assicurazione malattie di base (LAMal), con Apertus. "
  "Mi parli di lei: età, comune e ciò che conta per lei (budget, scelta del medico…). Può anche "
  "farmi domande sulla LAMal in qualsiasi momento.",
  "Hello! I'm your advisor for Swiss basic health insurance (LAMal/KVG), powered by Apertus. Tell me "
  "about yourself: your age, your municipality and what matters to you (budget, choice of doctor…). "
  "You can also ask me questions about basic insurance at any time.")
_("Apertus ne répond pas pour le moment. Réessayez dans un instant.",
  "Apertus antwortet im Moment nicht. Bitte versuchen Sie es gleich nochmals.",
  "Apertus non risponde al momento. Riprovi tra un istante.",
  "Apertus is not responding right now. Please try again in a moment.")
_("Apertus réfléchit…", "Apertus denkt nach…", "Apertus sta riflettendo…", "Apertus is thinking…")
_("Comparateur d'assurance maladie", "Krankenkassen-Vergleich", "Confronto casse malati",
  "Health insurance comparison")
_("Décrivez votre situation en quelques mots : je compare les primes officielles de l'assurance de "
  "base (LAMal) 2027 et je vous explique les différences.",
  "Beschreiben Sie Ihre Situation in wenigen Worten: Ich vergleiche die offiziellen Prämien der "
  "Grundversicherung (KVG) 2027 und erkläre Ihnen die Unterschiede.",
  "Descriva la sua situazione in poche parole: confronto i premi ufficiali dell'assicurazione di "
  "base (LAMal) 2027 e le spiego le differenze.",
  "Describe your situation in a few words: I compare the official 2027 basic insurance premiums "
  "and explain the differences.")
_("Outil d'orientation, pas un conseil personnalisé ; vérifiez sur priminfo.admin.ch avant de décider.",
  "Orientierungshilfe, keine persönliche Beratung; prüfen Sie vor dem Entscheid auf priminfo.admin.ch.",
  "Strumento di orientamento, non una consulenza personalizzata; verifichi su priminfo.admin.ch "
  "prima di decidere.",
  "Guidance tool, not personal advice; check priminfo.admin.ch before deciding.")
_("Les informations de santé ne sont pas enregistrées.", "Gesundheitsangaben werden nicht gespeichert.",
  "Le informazioni sulla salute non vengono salvate.", "Health information is not stored.")
_("Nouvelle comparaison", "Neuer Vergleich", "Nuovo confronto", "New comparison")
_("Langue", "Sprache", "Lingua", "Language")

# --- Questions de l'entretien (mêmes textes que chatbot.QUESTIONS) ------------------------------
_("Quel est votre code postal ou votre commune de domicile ?",
  "Wie lautet Ihre Postleitzahl oder Ihre Wohngemeinde?",
  "Qual è il suo numero postale o il suo comune di domicilio?",
  "What is your postcode or municipality of residence?")
_("Quelle commune de domicile faut-il retenir ?", "Welche Wohngemeinde soll ich verwenden?",
  "Quale comune di domicilio devo considerare?", "Which municipality of residence should I use?")
_("Quelle est votre année de naissance ? Elle permet de vérifier votre catégorie pour les primes 2027.",
  "In welchem Jahr sind Sie geboren? Damit prüfe ich Ihre Prämienkategorie für 2027.",
  "In che anno è nato/a? Mi serve per verificare la sua categoria di premio 2027.",
  "What is your year of birth? It lets me check your premium category for 2027.")
_("Quel est votre âge actuel, ou votre année de naissance ?",
  "Wie alt sind Sie, oder in welchem Jahr sind Sie geboren?",
  "Quanti anni ha, o in che anno è nato/a?",
  "How old are you, or what is your year of birth?")
_("Avez-vous actuellement un emploi salarié ? Merci de clarifier les informations contradictoires.",
  "Sind Sie zurzeit angestellt? Bitte klären Sie die widersprüchlichen Angaben.",
  "Ha attualmente un impiego salariato? Per favore chiarisca le informazioni contraddittorie.",
  "Are you currently employed? Please clarify the conflicting information.")
_("Combien d'heures travaillez-vous par semaine chez un même employeur ?",
  "Wie viele Stunden pro Woche arbeiten Sie beim gleichen Arbeitgeber?",
  "Quante ore alla settimana lavora presso lo stesso datore di lavoro?",
  "How many hours per week do you work for the same employer?")
_("Votre couverture des accidents non professionnels est-elle confirmée ? Vous pouvez aussi retirer "
  "cette information incertaine et demander une comparaison avec accidents inclus.",
  "Ist Ihre Nichtberufsunfallversicherung bestätigt? Sie können diese unsichere Angabe auch "
  "zurückziehen und einen Vergleich mit Unfalldeckung verlangen.",
  "La sua copertura per gli infortuni non professionali è confermata? Può anche ritirare questa "
  "informazione incerta e chiedere un confronto con gli infortuni inclusi.",
  "Is your non-occupational accident cover confirmed? You can also withdraw this uncertain "
  "information and ask for a comparison with accidents included.")
_("Souhaitez-vous comparer avec les accidents inclus ? Pour les exclure, vérifiez que vous disposez "
  "d'une couverture des accidents non professionnels applicable.",
  "Möchten Sie mit Unfalldeckung vergleichen? Ausschliessen können Sie sie nur, wenn Sie über Ihren "
  "Arbeitgeber gegen Nichtberufsunfälle versichert sind.",
  "Desidera confrontare con gli infortuni inclusi? Può escluderli solo se dispone di una copertura "
  "per gli infortuni non professionali.",
  "Would you like to compare with accident cover included? You can only exclude it if you have "
  "non-occupational accident cover (e.g. through your employer).")
_("Quelle franchise souhaitez-vous : un montant précis, la plus basse, la plus haute, ou comparer "
  "toutes les franchises ?",
  "Welche Franchise möchten Sie: einen bestimmten Betrag, die tiefste, die höchste, oder alle "
  "Franchisen vergleichen?",
  "Quale franchigia desidera: un importo preciso, la più bassa, la più alta, o confrontare tutte "
  "le franchigie?",
  "Which deductible would you like: a specific amount, the lowest, the highest, or compare all "
  "deductibles?")
_("Quels modèles acceptez-vous : libre choix, médecin de famille / HMO, téléphone ou service "
  "numérique, pharmacie, modèle flexible, ou tous ?",
  "Welche Modelle kommen für Sie in Frage: freie Arztwahl, Hausarzt / HMO, Telefon oder digitaler "
  "Dienst, Apotheke, flexibles Modell, oder alle?",
  "Quali modelli accetta: libera scelta, medico di famiglia / HMO, telefono o servizio digitale, "
  "farmacia, modello flessibile, o tutti?",
  "Which models do you accept: free choice of doctor, family doctor / HMO, phone or digital "
  "service, pharmacy, flexible model, or all?")
_("Vos conditions précises ne sont pas vérifiables avec les seules données de primes. Souhaitez-vous "
  "les conserver (comparaison suspendue), ou les retirer explicitement pour comparer uniquement les "
  "catégories de modèles ?",
  "Ihre genauen Bedingungen lassen sich mit den Prämiendaten allein nicht prüfen. Möchten Sie sie "
  "behalten (Vergleich pausiert) oder ausdrücklich weglassen und nur die Modellkategorien vergleichen?",
  "Le sue condizioni precise non sono verificabili con i soli dati dei premi. Desidera mantenerle "
  "(confronto sospeso) o rinunciarvi esplicitamente per confrontare solo le categorie di modelli?",
  "Your specific conditions cannot be checked with premium data alone. Keep them (comparison "
  "paused), or explicitly drop them to compare model categories only?")
_("Je compare une personne à la fois. Pour qui faisons-nous la comparaison ? Merci de redonner ses "
  "informations.",
  "Ich vergleiche jeweils eine Person. Für wen machen wir den Vergleich? Bitte geben Sie die Angaben "
  "dieser Person nochmals an.",
  "Confronto una persona alla volta. Per chi facciamo il confronto? Per favore ripeta le sue "
  "informazioni.",
  "I compare one person at a time. Who is the comparison for? Please give that person's details "
  "again.")
_("Avez-vous un budget maximum par mois pour la prime ? Indiquez un montant, ou « pas de limite ».",
  "Haben Sie ein maximales Monatsbudget für die Prämie? Nennen Sie einen Betrag oder « kein Limit ».",
  "Ha un budget massimo mensile per il premio? Indichi un importo, oppure « nessun limite ».",
  "Do you have a maximum monthly budget for the premium? Give an amount, or « no limit ».")

# --- Précisions ajoutées aux questions ------------------------------------------------------------
_("Quelle commune faut-il retenir : {liste} ?", "Welche Gemeinde ist es: {liste}?",
  "Quale comune devo considerare: {liste}?", "Which municipality is it: {liste}?")
_("Deux réponses diffèrent : {a} et {b}. ", "Zwei Angaben widersprechen sich: {a} und {b}. ",
  "Due risposte non coincidono: {a} e {b}. ", "Two answers differ: {a} and {b}. ")
_("Cette valeur n'est pas valide. ", "Dieser Wert ist ungültig. ", "Questo valore non è valido. ",
  "This value is not valid. ")
_("Cette information reste incertaine. ", "Diese Angabe ist noch unsicher. ",
  "Questa informazione resta incerta. ", "This information is still uncertain. ")
_("Une franchise de {v} CHF n'existe pas pour votre âge : les franchises possibles sont {liste} CHF. ",
  "Eine Franchise von {v} CHF gibt es für Ihr Alter nicht: möglich sind {liste} CHF. ",
  "Una franchigia di {v} CHF non esiste per la sua età: le franchigie possibili sono {liste} CHF. ",
  "A {v} CHF deductible does not exist for your age: the possible deductibles are {liste} CHF. ")
_("Le lieu est inconnu ou le code postal et la commune ne correspondent pas. ",
  "Der Ort ist unbekannt oder Postleitzahl und Gemeinde passen nicht zusammen. ",
  "Il luogo è sconosciuto oppure numero postale e comune non corrispondono. ",
  "The place is unknown, or the postcode and municipality do not match. ")
_("Je n'ai pas compris votre réponse. ", "Ich habe Ihre Antwort nicht verstanden. ",
  "Non ho capito la sua risposta. ", "I did not understand your answer. ")
_(" Par exemple : « {ex} ».", " Zum Beispiel: « {ex} ».", " Per esempio: « {ex} ».", " For example: « {ex} ».")
_("Je n'ai pas compris quels modèles vous acceptez : je compare le modèle standard (libre choix) et je "
  "vous montre ensuite ce que coûteraient les autres. Vous pourrez préciser après.",
  "Ich habe nicht verstanden, welche Modelle Sie akzeptieren: Ich vergleiche das Standardmodell "
  "(freie Arztwahl) und zeige Ihnen danach, was die anderen kosten würden. Sie können das später präzisieren.",
  "Non ho capito quali modelli accetta: confronto il modello standard (libera scelta) e le mostro poi "
  "quanto costerebbero gli altri. Potrà precisare dopo.",
  "I didn't understand which models you accept: I'll compare the standard model (free choice) and "
  "then show you what the others would cost. You can clarify afterwards.")
_("Je ne peux pas répondre à cette question de façon fiable ici ; vous pouvez vérifier sur "
  "priminfo.admin.ch.",
  "Diese Frage kann ich hier nicht zuverlässig beantworten; Sie können auf priminfo.admin.ch nachsehen.",
  "Non posso rispondere in modo affidabile a questa domanda qui; può verificare su priminfo.admin.ch.",
  "I can't answer this question reliably here; you can check priminfo.admin.ch.")
_("Je ne peux pas répondre de façon fiable à cette question ici ; vous pouvez vérifier sur "
  "priminfo.admin.ch. Pour changer une information, écrivez par exemple « et avec une franchise de "
  "300 ? » ou « j'habite à 1003 ».",
  "Diese Frage kann ich hier nicht zuverlässig beantworten; Sie können auf priminfo.admin.ch "
  "nachsehen. Um eine Angabe zu ändern, schreiben Sie z. B. « und mit 300 Franchise? » oder « ich "
  "wohne in 3011 ».",
  "Non posso rispondere in modo affidabile qui; può verificare su priminfo.admin.ch. Per cambiare "
  "un'informazione scriva per esempio « e con una franchigia di 300? » o « abito a 6900 ».",
  "I can't answer this reliably here; you can check priminfo.admin.ch. To change something, write "
  "for example « and with a 300 deductible? » or « I live in 1003 ».")
_("Voici ce que j'ai compris :", "Das habe ich verstanden:", "Ecco cosa ho capito:", "Here is what I understood:")

# Exemples de réponse (EXEMPLES_REPONSE)
for fr, de, it, en in [
        ("1003 Lausanne", "3011 Bern", "6900 Lugano", "1202 Geneva"),
        ("Lausanne", "Bern", "Lugano", "Geneva"),
        ("je suis né en 1990", "ich bin 1990 geboren", "sono nato nel 1990", "I was born in 1990"),
        ("j'ai 35 ans", "ich bin 35 Jahre alt", "ho 35 anni", "I am 35"),
        ("2500, ou la plus haute", "2500, oder die höchste", "2500, o la più alta", "2500, or the highest"),
        ("avec accidents", "mit Unfall", "con infortuni", "with accidents"),
        ("tous les modèles me conviennent", "alle Modelle sind mir recht", "tutti i modelli mi vanno bene",
         "all models are fine"),
        ("seulement moi, 35 ans", "nur ich, 35 Jahre", "solo io, 35 anni", "just me, 35"),
        ("42 heures par semaine chez le même employeur", "42 Stunden pro Woche beim gleichen Arbeitgeber",
         "42 ore alla settimana presso lo stesso datore di lavoro", "42 hours a week for the same employer"),
        ("oui, je suis salarié", "ja, ich bin angestellt", "sì, sono dipendente", "yes, I am employed"),
        ("oui, c'est confirmé par mon employeur", "ja, mein Arbeitgeber hat es bestätigt",
         "sì, è confermato dal mio datore di lavoro", "yes, my employer confirmed it"),
        ("250 CHF par mois, ou pas de limite", "250 CHF pro Monat, oder kein Limit",
         "250 CHF al mese, o nessun limite", "250 CHF a month, or no limit")]:
    _(fr, de, it, en)

# --- Boutons ------------------------------------------------------------------------------------
_("Comparer toutes les franchises", "Alle Franchisen vergleichen", "Confrontare tutte le franchigie",
  "Compare all deductibles")
_("Toutes les franchises", "Alle Franchisen", "Tutte le franchigie", "All deductibles")
_("Laquelle est la plus avantageuse pour moi ?", "Welche ist für mich am günstigsten?",
  "Quale è la più vantaggiosa per me?", "Which one is best for me?")
_("Quelle franchise est la plus avantageuse pour moi ?", "Welche Franchise ist für mich am günstigsten?",
  "Quale franchigia è la più vantaggiosa per me?", "Which deductible is best for me?")
_("Accidents inclus", "Mit Unfalldeckung", "Infortuni inclusi", "Accidents included")
_("Comparer avec accidents inclus", "Mit Unfalldeckung vergleichen", "Confrontare con infortuni inclusi",
  "Compare with accidents included")
_("Accidents exclus (couverture vérifiée)", "Ohne Unfalldeckung (Deckung geprüft)",
  "Infortuni esclusi (copertura verificata)", "Accidents excluded (cover checked)")
_("Comparer avec accidents exclus, couverture vérifiée", "Ohne Unfalldeckung vergleichen, Deckung geprüft",
  "Confrontare senza infortuni, copertura verificata", "Compare without accidents, cover checked")
_("Libre choix uniquement", "Nur freie Arztwahl", "Solo libera scelta", "Free choice only")
_("J'accepte tous les modèles", "Alle Modelle sind mir recht", "Accetto tutti i modelli", "I accept all models")
_("Besoins en assurances complémentaires", "Bedarf an Zusatzversicherungen",
  "Bisogni di assicurazioni complementari", "Supplementary insurance needs")
_("C'est correct, lancer la comparaison", "Stimmt, Vergleich starten", "È corretto, avviare il confronto",
  "That's right, run the comparison")
_("Sinon, écrivez votre correction dans le chat (ex. « j'ai 31 ans »).",
  "Sonst schreiben Sie Ihre Korrektur in den Chat (z. B. « ich bin 31 »).",
  "Altrimenti scriva la correzione nella chat (es. « ho 31 anni »).",
  "Otherwise, type your correction in the chat (e.g. « I am 31 »).")

# --- Résumé du profil ---------------------------------------------------------------------------
_("Voici ce que j'ai compris. Est-ce correct ?", "Das habe ich verstanden. Stimmt das?",
  "Ecco cosa ho capito. È corretto?", "Here is what I understood. Is it correct?")
_("Année de naissance : {v}", "Geburtsjahr: {v}", "Anno di nascita: {v}", "Year of birth: {v}")
_("Âge déclaré : {v} ans", "Angegebenes Alter: {v} Jahre", "Età indicata: {v} anni", "Stated age: {v}")
_("catégorie tarifaire vérifiée pour {annee}", "Prämienkategorie geprüft für {annee}",
  "categoria di premio verificata per {annee}", "premium category checked for {annee}")
_("Commune", "Gemeinde", "Comune", "Municipality")
_("Canton", "Kanton", "Cantone", "Canton")
_("Région de primes", "Prämienregion", "Regione di premio", "Premium region")
_("Franchise(s)", "Franchise(n)", "Franchigia/e", "Deductible(s)")
_("Modèles acceptés", "Akzeptierte Modelle", "Modelli accettati", "Accepted models")
_("Refusé", "Abgelehnt", "Rifiutato", "Rejected")
_("Selon le prix", "Je nach Preis", "Secondo il prezzo", "Depending on price")
_("Incertain", "Unsicher", "Incerto", "Unsure")
_("Couverture accident", "Unfalldeckung", "Copertura infortuni", "Accident cover")
_("incluse", "eingeschlossen", "inclusa", "included")
_("exclue", "ausgeschlossen", "esclusa", "excluded")
_(" — selon votre choix de comparaison", " — gemäss Ihrer Wahl", " — secondo la sua scelta",
  " — as you chose")
_(" — selon la couverture non professionnelle déclarée", " — gemäss angegebener Nichtberufsunfalldeckung",
  " — secondo la copertura non professionale dichiarata", " — based on the stated non-occupational cover")
_(" — emploi salarié déclaré, {h} h/semaine chez un même employeur",
  " — angestellt, {h} Std./Woche beim gleichen Arbeitgeber",
  " — impiego dichiarato, {h} ore/settimana presso lo stesso datore di lavoro",
  " — employed, {h} h/week for the same employer")
_("Priorité", "Priorität", "Priorità", "Priority")
_("aucune indiquée", "keine angegeben", "nessuna indicata", "none given")
_("Budget", "Budget", "Budget", "Budget")
_("{v} CHF par mois au maximum", "höchstens {v} CHF pro Monat", "al massimo {v} CHF al mese",
  "at most {v} CHF a month")
_("petit budget", "kleines Budget", "budget ridotto", "small budget")
_("pas de limite indiquée", "kein Limit angegeben", "nessun limite indicato", "no limit given")
_("non indiqué", "nicht angegeben", "non indicato", "not given")
_("Besoins en complémentaires", "Bedarf an Zusatzversicherungen", "Bisogni di complementari",
  "Supplementary needs")
_("aucun", "keiner", "nessuno", "none")
_("Santé", "Gesundheit", "Salute", "Health")
_("{n} élément(s) pris en compte", "{n} Angabe(n) berücksichtigt", "{n} elemento/i considerato/i",
  "{n} item(s) taken into account")

# Modes de soins (chatbot.CARE_LABELS, soins.NOMS_MODES) et priorités
for fr, de, it, en in [
        ("libre choix", "freie Arztwahl", "libera scelta", "free choice of doctor"),
        ("médecin de famille / HMO", "Hausarzt / HMO", "medico di famiglia / HMO", "family doctor / HMO"),
        ("téléphone ou service numérique", "Telefon oder digitaler Dienst", "telefono o servizio digitale",
         "phone or digital service"),
        ("pharmacie", "Apotheke", "farmacia", "pharmacy"),
        ("modèle flexible (conditions à vérifier)", "flexibles Modell (Bedingungen prüfen)",
         "modello flessibile (condizioni da verificare)", "flexible model (check the conditions)"),
        ("libre choix du médecin", "freie Arztwahl", "libera scelta del medico", "free choice of doctor"),
        ("conseil par téléphone", "telefonische Beratung", "consulenza telefonica", "phone advice"),
        ("application", "App", "applicazione", "app"),
        ("le prix le plus bas", "der tiefste Preis", "il prezzo più basso", "the lowest price"),
        ("passer par un médecin de famille", "über einen Hausarzt gehen", "passare dal medico di famiglia",
         "going through a family doctor"),
        ("le libre choix du médecin", "die freie Arztwahl", "la libera scelta del medico",
         "free choice of doctor"),
        ("vous l'avez écarté", "Sie haben es ausgeschlossen", "l'ha escluso", "you ruled it out"),
        ("vous l'accepteriez si cela fait économiser", "Sie würden es akzeptieren, wenn es Geld spart",
         "lo accetterebbe se fa risparmiare", "you'd accept it if it saves money"),
        ("vous hésitez", "Sie sind unsicher", "è indeciso/a", "you're unsure")]:
    _(fr, de, it, en)

# --- Résultats ----------------------------------------------------------------------------------
_("Aucune prime trouvée pour ce profil.", "Für dieses Profil wurde keine Prämie gefunden.",
  "Nessun premio trovato per questo profilo.", "No premium found for this profile.")
_("CHF / mois", "CHF / Monat", "CHF / mese", "CHF / month")
_("La moins chère", "Die günstigste", "La meno cara", "The cheapest")
_("+{x} CHF / mois par rapport à la moins chère", "+{x} CHF / Monat gegenüber der günstigsten",
  "+{x} CHF / mese rispetto alla meno cara", "+{x} CHF / month compared with the cheapest")
_("Franchise : {f} CHF. Contrepartie : {c}", "Franchise: {f} CHF. Gegenleistung: {c}",
  "Franchigia: {f} CHF. Contropartita: {c}", "Deductible: {f} CHF. Trade-off: {c}")
_("Compatibilité par catégorie seulement : réseau de médecins, application et conditions du produit à "
  "vérifier. Primes officielles OFSP 2027. Vérifiez sur priminfo.admin.ch avant de changer d'assurance.",
  "Nur nach Kategorie geprüft: Ärztenetz, App und Produktbedingungen bitte prüfen. Offizielle "
  "BAG-Prämien 2027. Prüfen Sie vor einem Wechsel auf priminfo.admin.ch.",
  "Compatibilità solo per categoria: rete di medici, app e condizioni del prodotto da verificare. "
  "Premi ufficiali UFSP 2027. Verifichi su priminfo.admin.ch prima di cambiare.",
  "Compatibility by category only: check the doctor network, app and product conditions. Official "
  "FOPH 2027 premiums. Check priminfo.admin.ch before switching.")
_("Plusieurs franchises sont comparées : la prime la plus basse ne signifie pas le coût total de soins "
  "le plus bas.",
  "Mehrere Franchisen werden verglichen: Die tiefste Prämie bedeutet nicht die tiefsten Gesamtkosten.",
  "Si confrontano più franchigie: il premio più basso non significa il costo totale più basso.",
  "Several deductibles are compared: the lowest premium does not mean the lowest total cost.")
_("La moins chère parmi les catégories acceptées", "Die günstigste der akzeptierten Kategorien",
  "La meno cara tra le categorie accettate", "Cheapest among accepted categories")
_("La moins chère avec médecin de famille / HMO", "Die günstigste mit Hausarzt / HMO",
  "La meno cara con medico di famiglia / HMO", "Cheapest with family doctor / HMO")
_("La moins chère avec libre choix du médecin", "Die günstigste mit freier Arztwahl",
  "La meno cara con libera scelta del medico", "Cheapest with free choice of doctor")
for fr, de, it, en in [
        ("Libre choix", "Freie Arztwahl", "Libera scelta", "Free choice"),
        ("Médecin de famille / HMO", "Hausarzt / HMO", "Medico di famiglia / HMO", "Family doctor / HMO"),
        ("Télémédecine / numérique", "Telmed / digital", "Telemedicina / digitale", "Telemedicine / digital"),
        ("Pharmacie", "Apotheke", "Farmacia", "Pharmacy"),
        ("Modèle alternatif", "Alternatives Modell", "Modello alternativo", "Alternative model"),
        ("Modèle standard sans restriction de choix propre à un réseau ; les règles de prise en charge de "
         "la LAMal restent applicables.",
         "Standardmodell ohne Einschränkung auf ein Netzwerk; die KVG-Regeln gelten weiterhin.",
         "Modello standard senza restrizione a una rete; restano valide le regole della LAMal.",
         "Standard model with no network restriction; LAMal coverage rules still apply."),
        ("Premier contact auprès du médecin ou du réseau désigné ; vérifier le réseau et les exceptions du "
         "produit.",
         "Erster Kontakt beim bezeichneten Arzt oder Netzwerk; Netzwerk und Ausnahmen prüfen.",
         "Primo contatto presso il medico o la rete designati; verificare la rete e le eccezioni.",
         "First contact with the designated doctor or network; check the network and exceptions."),
        ("Premier contact par téléphone ou service numérique selon le produit ; vérifier les obligations et "
         "exceptions.",
         "Erster Kontakt per Telefon oder digitalem Dienst; Pflichten und Ausnahmen prüfen.",
         "Primo contatto per telefono o servizio digitale; verificare obblighi ed eccezioni.",
         "First contact by phone or digital service; check obligations and exceptions."),
        ("Premier contact en pharmacie selon les conditions du produit.",
         "Erster Kontakt in der Apotheke gemäss Produktbedingungen.",
         "Primo contatto in farmacia secondo le condizioni del prodotto.",
         "First contact at a pharmacy, according to the product conditions."),
        ("Règles propres à chaque assureur : vérifier les conditions exactes chez l'assureur.",
         "Eigene Regeln jedes Versicherers: genaue Bedingungen beim Versicherer prüfen.",
         "Regole proprie di ogni assicuratore: verificare le condizioni esatte.",
         "Each insurer's own rules: check the exact conditions with the insurer.")]:
    _(fr, de, it, en)
_("Votre budget : {b} CHF par mois au maximum. {n} offre(s) sur {total} le respectent.",
  "Ihr Budget: höchstens {b} CHF pro Monat. {n} von {total} Angeboten halten es ein.",
  "Il suo budget: al massimo {b} CHF al mese. {n} offerta/e su {total} lo rispettano.",
  "Your budget: at most {b} CHF a month. {n} of {total} offers fit it.")
_("Ce que coûtent vos préférences", "Was Ihre Präferenzen kosten", "Quanto costano le sue preferenze",
  "What your preferences cost")
_("Pour le même profil, voici l'offre la moins chère de chaque modèle que vous n'avez pas retenu, "
  "comparée à votre offre la moins chère.",
  "Für dasselbe Profil: das günstigste Angebot jedes nicht gewählten Modells, verglichen mit Ihrem "
  "günstigsten Angebot.",
  "Per lo stesso profilo, ecco l'offerta meno cara di ogni modello non scelto, confrontata con la sua "
  "offerta meno cara.",
  "For the same profile, here is the cheapest offer of each model you did not choose, compared with "
  "your cheapest offer.")
_("{x} CHF de moins par an", "{x} CHF weniger pro Jahr", "{x} CHF in meno all'anno", "{x} CHF less per year")
_("{x} CHF de plus par an", "{x} CHF mehr pro Jahr", "{x} CHF in più all'anno", "{x} CHF more per year")
_("même prime annuelle", "gleiche Jahresprämie", "stesso premio annuo", "same annual premium")
_(" : dès {x} CHF / mois ({assureur}, *{produit}*), soit {ecart}.",
  ": ab {x} CHF / Monat ({assureur}, *{produit}*), also {ecart}.",
  ": da {x} CHF / mese ({assureur}, *{produit}*), cioè {ecart}.",
  ": from {x} CHF / month ({assureur}, *{produit}*), i.e. {ecart}.")
_("Écarts de primes uniquement, source OFSP 2027. Chaque modèle a des contraintes propres : vérifiez "
  "les conditions du produit avant de changer.",
  "Nur Prämienunterschiede, Quelle BAG 2027. Jedes Modell hat eigene Bedingungen: vor einem Wechsel prüfen.",
  "Solo differenze di premio, fonte UFSP 2027. Ogni modello ha vincoli propri: verificare prima di cambiare.",
  "Premium differences only, source FOPH 2027. Each model has its own constraints: check before switching.")
_("Voir toutes les offres", "Alle Angebote anzeigen", "Vedere tutte le offerte", "See all offers")
_("Assurance de base (LAMal) : {n} offres, de la moins chère à la plus chère (CHF)",
  "Grundversicherung (KVG): {n} Angebote, vom günstigsten zum teuersten (CHF)",
  "Assicurazione di base (LAMal): {n} offerte, dalla meno cara alla più cara (CHF)",
  "Basic insurance: {n} offers, from cheapest to most expensive (CHF)")
_("Posez-moi vos questions (« quelle franchise me conviendrait ? », « que couvre la LAMal ? ») ou changez "
  "une information (« et avec une franchise de 300 ? »).",
  "Stellen Sie mir Fragen (« Welche Franchise passt zu mir? », « Was deckt die Grundversicherung? ») "
  "oder ändern Sie eine Angabe (« und mit 300 Franchise? »).",
  "Mi faccia domande (« quale franchigia mi conviene? », « cosa copre la LAMal? ») o cambi "
  "un'informazione (« e con una franchigia di 300? »).",
  "Ask me questions (« which deductible suits me? », « what does basic insurance cover? ») or change "
  "something (« and with a 300 deductible? »).")
_("Avec un petit budget : selon votre revenu, vous pourriez avoir droit à une réduction individuelle des "
  "primes (subside) versée par votre canton. Renseignez-vous auprès du service cantonal compétent ; la "
  "démarche dépend du canton.",
  "Mit kleinem Budget: Je nach Einkommen haben Sie eventuell Anspruch auf eine individuelle "
  "Prämienverbilligung Ihres Kantons. Erkundigen Sie sich bei der zuständigen kantonalen Stelle.",
  "Con un budget ridotto: secondo il reddito potrebbe avere diritto a una riduzione individuale dei "
  "premi (sussidio) del suo cantone. Si informi presso il servizio cantonale competente.",
  "On a small budget: depending on your income, you may be entitled to an individual premium "
  "reduction (subsidy) from your canton. Ask the competent cantonal office.")
_("Voici les offres retenues selon vos catégories acceptées. Comparez les primes, franchises et conditions.",
  "Hier die Angebote gemäss Ihren akzeptierten Kategorien. Vergleichen Sie Prämien, Franchisen und Bedingungen.",
  "Ecco le offerte secondo le categorie accettate. Confronti premi, franchigie e condizioni.",
  "Here are the offers for your accepted categories. Compare premiums, deductibles and conditions.")
# En-têtes du tableau de toutes les offres
for fr, de, it, en in [("Assureur", "Versicherer", "Assicuratore", "Insurer"),
                       ("Modèle", "Modell", "Modello", "Model"), ("Produit", "Produkt", "Prodotto", "Product"),
                       ("Prime/mois", "Prämie/Monat", "Premio/mese", "Premium/month"),
                       ("Prime/an", "Prämie/Jahr", "Premio/anno", "Premium/year"),
                       ("Écart/an", "Differenz/Jahr", "Differenza/anno", "Difference/year"),
                       ("Coût max/an", "Max. Kosten/Jahr", "Costo max/anno", "Max cost/year"),
                       ("Franchise", "Franchise", "Franchigia", "Deductible")]:
    _(fr, de, it, en)

_("Sources : primes LAMal 2027, régions de primes et liste des assureurs admis : Office fédéral de la santé "
  "publique (OFSP), via opendata.swiss et priminfo.admin.ch. Assurances complémentaires : sites des caisses "
  "({caisses}), vérifiés le {date}.",
  "Quellen: KVG-Prämien 2027, Prämienregionen und Liste der zugelassenen Versicherer: Bundesamt für Gesundheit "
  "(BAG), via opendata.swiss und priminfo.admin.ch. Zusatzversicherungen: Websites der Kassen ({caisses}), "
  "geprüft am {date}.",
  "Fonti: premi LAMal 2027, regioni di premio e lista degli assicuratori ammessi: Ufficio federale della sanità "
  "pubblica (UFSP), via opendata.swiss e priminfo.admin.ch. Assicurazioni complementari: siti delle casse "
  "({caisses}), verificati il {date}.",
  "Sources: 2027 basic insurance premiums, premium regions and list of approved insurers: Federal Office of "
  "Public Health (FOPH), via opendata.swiss and priminfo.admin.ch. Supplementary insurance: insurers' websites "
  "({caisses}), checked on {date}.")

TRAD = {fr: dict(zip(("de", "it", "en"), v)) for fr, v in T.items()}
