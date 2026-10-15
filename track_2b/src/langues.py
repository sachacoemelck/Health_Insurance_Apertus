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

# Mots propres à chaque langue (les mots partagés comme « a », « e », « i », « no », « con » sont exclus)
_MOTS = {
    "fr": "je j' suis ai habite vis ans avec sans les des une est et pour mon ma mes quoi quel quelle c' "
          "maintenant pardon d' qu' "
          "pas oui bonjour salut merci comment combien pourquoi assurance travaille vous votre vos avez êtes "
          "être nous dans sur aussi couverture souhaitez choisi prime primes",
    "de": "ich bin habe wohne jahre jahr alt mit ohne der die das und ist nicht ja nein ein eine mein meine "
          "was wie warum wieviel welche versicherung grüezi hallo danke unfall bitte arbeite geboren sie ihr "
          "ihre ihnen sind wir auch für prämie",
    "it": "sono ho abito vivo anni anno senza il lo gli è sì una mio mia cosa come perché quanto "
          "quale franchigia assicurazione buongiorno ciao grazie infortuni lavoro nato nata lei suo sua "
          "della delle anche premio",
    "en": "i' i'm am have live living years year old with without the and is not yes my what how why which "
          "much insurance deductible hello hi thanks please accident cover born work you your are "
          "we also premium",
}
_ENS = {k: set(v.split()) for k, v in _MOTS.items()}


def detecter(texte):
    """Code de langue du message, ou None s'il est ambigu ou sans mot reconnaissable (« 2500 », « Lausanne »)."""
    mots = re.findall(r"[a-zà-ÿ]+'|[a-zà-ÿ]+", (texte or "").lower().replace("’", "'"))
    scores = {code: sum(m in _ENS[code] for m in mots) for code in CODES}
    meilleur = max(scores, key=scores.get)
    second = sorted(scores.values())[-2]
    if scores[meilleur] >= 2 and scores[meilleur] > second:
        return meilleur
    # Un seul mot reconnu suffit pour un message court (« 48 anni, Lugano ») mais pas pour une phrase
    return meilleur if scores[meilleur] == 1 and second == 0 and len(mots) <= 4 else None


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

# Caisse actuelle, économie et lettre de résiliation (app.py, changement.py)
_("Chez quelle caisse maladie êtes-vous assuré(e) aujourd'hui, et avec quel modèle (libre choix, médecin de "
  "famille, télémédecine…) ? Je calcule ce que vous économiseriez en changeant. C'est facultatif.",
  "Bei welcher Krankenkasse sind Sie heute versichert, und mit welchem Modell (freie Arztwahl, Hausarzt, "
  "Telmed…)? Ich berechne, wie viel Sie mit einem Wechsel sparen würden. Diese Angabe ist freiwillig.",
  "Presso quale cassa malati è assicurato/a oggi, e con quale modello (libera scelta, medico di famiglia, "
  "telemedicina…)? Calcolo quanto risparmierebbe cambiando. È facoltativo.",
  "Which health insurer are you with today, and with which model (free choice, family doctor, "
  "telemedicine…)? I will calculate how much you would save by switching. This is optional.")
_("Plusieurs caisses portent ce nom. Laquelle figure sur votre police d'assurance ?",
  "Mehrere Kassen tragen diesen Namen. Welche steht auf Ihrer Versicherungspolice?",
  "Diverse casse portano questo nome. Quale figura sulla sua polizza?",
  "Several insurers carry this name. Which one is on your policy?")
_("{caisse} ne propose pas d'assurance de base pour votre profil dans votre région en 2027 : vous devrez de "
  "toute façon choisir une autre caisse.",
  "{caisse} bietet 2027 für Ihr Profil in Ihrer Region keine Grundversicherung an: Sie müssen ohnehin eine "
  "andere Kasse wählen.",
  "{caisse} non offre l'assicurazione di base per il suo profilo nella sua regione nel 2027: dovrà comunque "
  "scegliere un'altra cassa.",
  "{caisse} does not offer basic insurance for your profile in your region in 2027: you will have to choose "
  "another insurer anyway.")
_("Souhaitez-vous que je rédige votre lettre de résiliation pour {caisse} ?",
  "Möchten Sie, dass ich Ihr Kündigungsschreiben an {caisse} verfasse?",
  "Desidera che le scriva la lettera di disdetta per {caisse}?",
  "Would you like me to write your cancellation letter to {caisse}?")
_("Oui, rédigez ma lettre", "Ja, Schreiben verfassen", "Sì, scriva la lettera", "Yes, write my letter")
_("Non merci", "Nein danke", "No grazie", "No thanks")
_("Passer", "Überspringen", "Salta", "Skip")
_("D'accord. Vous pouvez me la demander plus tard en écrivant « lettre de résiliation ».",
  "In Ordnung. Sie können es später verlangen, indem Sie « Kündigungsschreiben » eingeben.",
  "D'accordo. Può chiedermela più tardi scrivendo « lettera di disdetta ».",
  "All right. You can ask for it later by writing « cancellation letter ».")
_("Votre lettre de résiliation", "Ihr Kündigungsschreiben", "La sua lettera di disdetta", "Your cancellation letter")
_("Rédigée par Apertus ; les éléments obligatoires ont été vérifiés par l'application.",
  "Von Apertus verfasst; die Pflichtangaben wurden von der Anwendung geprüft.",
  "Redatta da Apertus; gli elementi obbligatori sono stati verificati dall'applicazione.",
  "Written by Apertus; the required elements were checked by the application.")
_("Lettre modèle de l'application (la lettre d'Apertus n'était pas complète).",
  "Musterschreiben der Anwendung (das Schreiben von Apertus war nicht vollständig).",
  "Lettera modello dell'applicazione (la lettera di Apertus non era completa).",
  "The application's template letter (Apertus's letter was not complete).")
_("La lettre est écrite dans une langue officielle de votre canton, celle que votre caisse utilise.",
  "Das Schreiben ist in einer Amtssprache Ihres Kantons verfasst, die Ihre Kasse verwendet.",
  "La lettera è scritta in una lingua ufficiale del suo cantone, quella usata dalla sua cassa.",
  "The letter is written in an official language of your canton, the one your insurer uses.")
_("Télécharger la lettre (.txt)", "Schreiben herunterladen (.txt)", "Scarica la lettera (.txt)",
  "Download the letter (.txt)")
_("Vous payez aujourd'hui {actuelle} CHF par mois (les offres affichées sont les primes 2027).",
  "Sie bezahlen heute {actuelle} CHF pro Monat (die angezeigten Angebote sind die Prämien 2027).",
  "Oggi paga {actuelle} CHF al mese (le offerte mostrate sono i premi 2027).",
  "You pay {actuelle} CHF per month today (the offers shown are 2027 premiums).")
_("En restant chez {caisse}, vous payeriez {actuelle} CHF par mois en 2027 (franchise {franchise} CHF).",
  "Wenn Sie bei {caisse} bleiben, bezahlen Sie 2027 {actuelle} CHF pro Monat (Franchise {franchise} CHF).",
  "Restando presso {caisse}, pagherebbe {actuelle} CHF al mese nel 2027 (franchigia {franchise} CHF).",
  "If you stay with {caisse}, you would pay {actuelle} CHF per month in 2027 (deductible {franchise} CHF).")
_("(Modèle non précisé : j'ai supposé le libre choix.)",
  "(Modell nicht angegeben: ich habe die freie Arztwahl angenommen.)",
  "(Modello non indicato: ho supposto la libera scelta.)",
  "(Model not specified: I assumed free choice.)")
_("Aucune offre de vos résultats n'est moins chère : changer ne vous ferait rien économiser.",
  "Kein Angebot in Ihren Resultaten ist günstiger: ein Wechsel würde Ihnen nichts sparen.",
  "Nessuna offerta dei suoi risultati è più conveniente: cambiare non le farebbe risparmiare nulla.",
  "None of your results is cheaper: switching would not save you anything.")
_("Avec {caisse} ({modele}), vous payeriez {prime} CHF par mois, soit {an} CHF de moins par an.",
  "Mit {caisse} ({modele}) würden Sie {prime} CHF pro Monat bezahlen, also {an} CHF weniger pro Jahr.",
  "Con {caisse} ({modele}) pagherebbe {prime} CHF al mese, cioè {an} CHF in meno all'anno.",
  "With {caisse} ({modele}), you would pay {prime} CHF per month, i.e. {an} CHF less per year.")
_("Avant d'envoyer : 1) inscrivez-vous d'abord auprès de la nouvelle caisse (votre assurance actuelle ne prend "
  "fin que lorsque la nouvelle caisse confirme votre couverture, LAMal art. 7 al. 5) ; 2) envoyez la lettre en "
  "recommandé : elle doit ARRIVER chez votre caisse au plus tard le {limite} ; 3) complétez les champs entre "
  "crochets et signez.",
  "Vor dem Versand: 1) melden Sie sich zuerst bei der neuen Kasse an (Ihre bisherige Versicherung endet erst, "
  "wenn die neue Kasse Ihre Deckung bestätigt, KVG Art. 7 Abs. 5); 2) senden Sie das Schreiben eingeschrieben: "
  "es muss spätestens am {limite} bei Ihrer Kasse EINTREFFEN; 3) füllen Sie die Felder in eckigen Klammern aus "
  "und unterschreiben Sie.",
  "Prima dell'invio: 1) si iscriva prima presso la nuova cassa (l'assicurazione attuale termina solo quando la "
  "nuova cassa conferma la copertura, LAMal art. 7 cpv. 5); 2) invii la lettera per raccomandata: deve "
  "ARRIVARE alla sua cassa al più tardi il {limite}; 3) completi i campi tra parentesi quadre e firmi.",
  "Before sending: 1) first sign up with the new insurer (your current insurance only ends once the new "
  "insurer confirms your cover, KVG/LAMal art. 7 para. 5); 2) send the letter by registered mail: it must "
  "ARRIVE at your insurer by {limite} at the latest; 3) fill in the fields in square brackets and sign.")

_("Dans votre canton ({canton}), la demande se fait auprès de : [{office}]({url}). Liste officielle de tous les "
  "cantons : [OFSP]({source}).",
  "In Ihrem Kanton ({canton}) stellen Sie den Antrag bei: [{office}]({url}). Offizielle Liste aller Kantone: "
  "[BAG]({source}).",
  "Nel suo cantone ({canton}) la domanda si presenta a: [{office}]({url}). Lista ufficiale di tutti i cantoni: "
  "[UFSP]({source}).",
  "In your canton ({canton}), you apply to: [{office}]({url}). Official list for all cantons: [FOPH]({source}).")

_("Sources : primes LAMal 2027, régions de primes et liste des assureurs admis : Office fédéral de la santé "
  "publique (OFSP), via opendata.swiss et priminfo.admin.ch. Textes de loi : fedlex.admin.ch (LAMal, OAMal, OPAS, "
  "LAA). Offices des subsides : liste de l'OFSP.",
  "Quellen: KVG-Prämien 2027, Prämienregionen und Liste der zugelassenen Versicherer: Bundesamt für Gesundheit "
  "(BAG), via opendata.swiss und priminfo.admin.ch. Gesetzestexte: fedlex.admin.ch (KVG, KVV, KLV, UVG). Stellen "
  "für die Prämienverbilligung: Liste des BAG.",
  "Fonti: premi LAMal 2027, regioni di premio e lista degli assicuratori ammessi: Ufficio federale della sanità "
  "pubblica (UFSP), via opendata.swiss e priminfo.admin.ch. Testi di legge: fedlex.admin.ch (LAMal, OAMal, OPre, "
  "LAINF). Uffici dei sussidi: lista dell'UFSP.",
  "Sources: 2027 basic insurance premiums, premium regions and list of approved insurers: Federal Office of Public "
  "Health (FOPH), via opendata.swiss and priminfo.admin.ch. Law texts: fedlex.admin.ch (KVG/LAMal, KVV/OAMal, "
  "KLV/OPAS, UVG/LAA). Premium subsidy offices: FOPH list.")

# --- Écran de profil (formulaire avant le conseiller) ----------------------------------------
_("Choisissez…", "Bitte wählen…", "Scelga…", "Choose…")
_("né(e) en {annee}", "Jahrgang {annee}", "nato/a nel {annee}", "born in {annee}")
_("J'ai bien noté : {faits}.", "Notiert: {faits}.", "Ho preso nota: {faits}.", "Noted: {faits}.")
_("Assurance de base LAMal 2027", "Grundversicherung KVG 2027", "Assicurazione di base LAMal 2027",
  "Basic health insurance (KVG/LAMal) 2027")
_("Votre assurance maladie.", "Ihre Krankenversicherung.", "La sua assicurazione malattie.", "Your health insurance.")
_("Comparée simplement.", "Einfach verglichen.", "Confrontata con semplicità.", "Simply compared.")
_("Les primes officielles de toutes les caisses, puis un conseiller qui répond à vos questions.",
  "Die offiziellen Prämien aller Kassen, dann ein Berater, der Ihre Fragen beantwortet.",
  "I premi ufficiali di tutte le casse, poi un consulente che risponde alle sue domande.",
  "Official premiums from every insurer, then an advisor who answers your questions.")
_("Votre profil", "Ihr Profil", "Il suo profilo", "Your profile")
_("Ces informations servent uniquement à calculer vos primes. Elles ne sont pas enregistrées.",
  "Diese Angaben dienen nur zur Berechnung Ihrer Prämien. Sie werden nicht gespeichert.",
  "Queste informazioni servono solo a calcolare i suoi premi. Non vengono salvate.",
  "This information is only used to calculate your premiums. It is not stored.")
_("Année de naissance", "Geburtsjahr", "Anno di nascita", "Year of birth")
_("Code postal (NPA)", "Postleitzahl (PLZ)", "Numero postale (NPA)", "Postcode")
_("Le code postal suisse a 4 chiffres.", "Die Schweizer Postleitzahl hat 4 Ziffern.",
  "Il numero postale svizzero ha 4 cifre.", "Swiss postcodes have 4 digits.")
_("Code postal inconnu en Suisse.", "Unbekannte Postleitzahl in der Schweiz.",
  "Numero postale sconosciuto in Svizzera.", "Unknown Swiss postcode.")
_("Commune de domicile", "Wohngemeinde", "Comune di domicilio", "Municipality of residence")
_("Situation professionnelle", "Berufliche Situation", "Situazione professionale", "Employment situation")
_("Salarié(e), au moins 8 h par semaine chez un même employeur",
  "Angestellt, mindestens 8 Std. pro Woche beim selben Arbeitgeber",
  "Dipendente, almeno 8 ore a settimana presso lo stesso datore di lavoro",
  "Employed, at least 8 hours a week with the same employer")
_("Salarié(e), moins de 8 h par semaine chez un même employeur",
  "Angestellt, weniger als 8 Std. pro Woche beim selben Arbeitgeber",
  "Dipendente, meno di 8 ore a settimana presso lo stesso datore di lavoro",
  "Employed, less than 8 hours a week with the same employer")
_("Indépendant(e)", "Selbständig", "Indipendente", "Self-employed")
_("Sans emploi, étudiant(e) ou retraité(e)", "Ohne Erwerbstätigkeit, in Ausbildung oder pensioniert",
  "Senza lavoro, studente o pensionato", "Not employed, student or retired")
_("Je ne sais pas", "Ich weiss es nicht", "Non lo so", "I don't know")
_("Elle indique si la couverture accident doit être incluse : un employeur assure contre les accidents ses "
  "salariés qui travaillent au moins 8 h par semaine chez lui.",
  "Sie zeigt, ob die Unfalldeckung eingeschlossen werden muss: Ein Arbeitgeber versichert seine Angestellten, "
  "die mindestens 8 Std. pro Woche bei ihm arbeiten, gegen Unfälle.",
  "Indica se la copertura infortuni deve essere inclusa: un datore di lavoro assicura contro gli infortuni i "
  "dipendenti che lavorano per lui almeno 8 ore a settimana.",
  "It shows whether accident cover must be included: an employer insures employees who work at least 8 hours "
  "a week for them against accidents.")
_("Modèles d'assurance acceptés", "Akzeptierte Versicherungsmodelle", "Modelli assicurativi accettati",
  "Accepted insurance models")
_("Besoins en assurances complémentaires (facultatif)", "Bedarf an Zusatzversicherungen (freiwillig)",
  "Bisogni di assicurazioni complementari (facoltativo)", "Supplementary insurance needs (optional)")
_("année de naissance", "Geburtsjahr", "anno di nascita", "year of birth")
_("code postal", "Postleitzahl", "numero postale", "postcode")
_("situation professionnelle", "berufliche Situation", "situazione professionale", "employment situation")
_("au moins un modèle", "mindestens ein Modell", "almeno un modello", "at least one model")
_("Voir mes offres", "Meine Angebote anzeigen", "Vedere le mie offerte", "See my offers")
_("À compléter : {champs}", "Noch auszufüllen: {champs}", "Da completare: {champs}", "Still to fill in: {champs}")
_("Je préfère décrire ma situation dans le chat", "Ich beschreibe meine Situation lieber im Chat",
  "Preferisco descrivere la mia situazione nella chat", "I'd rather describe my situation in the chat")
_("Merci d'avoir rempli le formulaire ! 👋 Je suis votre conseiller LAMal, propulsé par Apertus, le modèle de langue "
  "suisse. Je compare les primes officielles, je réponds à vos questions à partir de la loi, et je peux rédiger "
  "votre lettre de résiliation. Voici vos offres, avec toutes les franchises comparées. Posez-moi vos questions, par "
  "exemple « quelle franchise est la plus avantageuse pour moi ? » ou « c'est quoi le modèle médecin de famille ? ».",
  "Danke, dass Sie das Formular ausgefüllt haben! 👋 Ich bin Ihr KVG-Berater, angetrieben von Apertus, dem "
  "Schweizer Sprachmodell. Ich vergleiche die offiziellen Prämien, beantworte Ihre Fragen anhand des Gesetzes und "
  "kann Ihr Kündigungsschreiben verfassen. Hier sind Ihre Angebote, mit allen Franchisen im Vergleich. Stellen Sie "
  "mir Ihre Fragen, zum Beispiel «Welche Franchise lohnt sich für mich am meisten?» oder «Was ist das "
  "Hausarztmodell?».",
  "Grazie per aver compilato il modulo! 👋 Sono il suo consulente LAMal, basato su Apertus, il modello linguistico "
  "svizzero. Confronto i premi ufficiali, rispondo alle sue domande in base alla legge e posso redigere la sua "
  "lettera di disdetta. Ecco le sue offerte, con tutte le franchigie a confronto. Mi ponga le sue domande, ad "
  "esempio «Quale franchigia è la più vantaggiosa per me?» oppure «Che cos'è il modello del medico di famiglia?».",
  "Thank you for filling in the form! 👋 I am your basic health insurance advisor, powered by Apertus, the Swiss "
  "language model. I compare the official premiums, answer your questions based on the law, and can write your "
  "cancellation letter. Here are your offers, with all deductibles compared. Ask me your questions, for example "
  "\"Which deductible is best for me?\" or \"What is the family doctor model?\".")

_("Le délai pour changer de caisse au 1er janvier {annee} est passé (lettre reçue au plus tard fin novembre) : la "
  "lettre résilie donc pour le {fin}.",
  "Die Frist für einen Kassenwechsel auf den 1. Januar {annee} ist abgelaufen (Eingang bis Ende November): das "
  "Schreiben kündigt deshalb per {fin}.",
  "Il termine per cambiare cassa al 1° gennaio {annee} è scaduto (lettera ricevuta entro fine novembre): la "
  "lettera disdice quindi per il {fin}.",
  "The deadline to switch insurer on 1 January {annee} has passed (letter received by the end of November): the "
  "letter therefore cancels as of {fin}.")
_("Avec la franchise de 300 CHF et le modèle libre choix, vous pouvez aussi changer pour le 30 juin {annee} (lettre "
  "reçue au plus tard le {limite}) : adaptez alors la date de la lettre.",
  "Mit der Franchise von 300 CHF und freier Arztwahl können Sie auch auf den 30. Juni {annee} wechseln (Eingang "
  "spätestens am {limite}): passen Sie dann das Datum im Schreiben an.",
  "Con la franchigia di 300 CHF e la libera scelta può cambiare anche per il 30 giugno {annee} (lettera ricevuta "
  "entro il {limite}): adatti allora la data della lettera.",
  "With the 300 CHF deductible and the free-choice model, you can also switch on 30 June {annee} (letter received "
  "by {limite}): then adjust the date in the letter.")


_("Merci d'avoir rempli le formulaire ! 👋 Je suis votre conseiller LAMal, propulsé par Apertus, le modèle de langue "
  "suisse. Une précision avant de calculer vos offres :",
  "Danke, dass Sie das Formular ausgefüllt haben! 👋 Ich bin Ihr Berater für die Grundversicherung, angetrieben von "
  "Apertus, dem Schweizer Sprachmodell. Eine Präzisierung, bevor ich Ihre Angebote berechne:",
  "Grazie per aver compilato il modulo! 👋 Sono il suo consulente LAMal, basato su Apertus, il modello linguistico "
  "svizzero. Una precisazione prima di calcolare le sue offerte:",
  "Thank you for filling in the form! 👋 I'm your basic health insurance advisor, powered by Apertus, the Swiss "
  "language model. One detail before I calculate your offers:")

_("Votre conseiller LAMal", "Ihr Berater für die Grundversicherung", "Il suo consulente LAMal",
  "Your health insurance advisor")
_("Apertus · en ligne", "Apertus · online", "Apertus · online", "Apertus · online")
_("D'après votre formulaire", "Laut Ihrem Formular", "Secondo il suo modulo", "From your form")
_("{age} ans en {annee}", "{age} Jahre im Jahr {annee}", "{age} anni nel {annee}", "{age} years old in {annee}")
_("Accidents exclus (employeur)", "Ohne Unfalldeckung (Arbeitgeber)", "Infortuni esclusi (datore di lavoro)",
  "Accidents excluded (employer)")
_("Tous les modèles", "Alle Modelle", "Tutti i modelli", "All models")
_("Toutes les franchises comparées", "Alle Franchisen verglichen", "Tutte le franchigie confrontate",
  "All deductibles compared")
_("Comment fonctionne le modèle médecin de famille ?", "Wie funktioniert das Hausarztmodell?",
  "Come funziona il modello del medico di famiglia?", "How does the family doctor model work?")
_("Comment fonctionne la télémédecine ?", "Wie funktioniert das Telmed-Modell?", "Come funziona la telemedicina?",
  "How does the telemedicine model work?")
_("Comment fonctionne le modèle pharmacie ?", "Wie funktioniert das Apothekenmodell?",
  "Come funziona il modello farmacia?", "How does the pharmacy model work?")
_("Ai-je droit à un subside pour payer ma prime ?", "Habe ich Anspruch auf eine Prämienverbilligung?",
  "Ho diritto a un sussidio per pagare il premio?", "Am I entitled to a premium subsidy?")
_("Que se passe-t-il pour les accidents si je quitte mon emploi ?",
  "Was passiert mit der Unfalldeckung, wenn ich meine Stelle verlasse?",
  "Cosa succede per gli infortuni se lascio il mio lavoro?",
  "What happens with accident cover if I leave my job?")
_("Jusqu'à quand puis-je changer de caisse ?", "Bis wann kann ich die Krankenkasse wechseln?",
  "Entro quando posso cambiare cassa malati?", "Until when can I switch insurer?")

_("Modifier mes réponses", "Antworten ändern", "Modificare le risposte", "Edit my answers")

# --- Choix d'une offre et demande d'affiliation (« check-out ») ---------------------------------
_("Choisir cette offre", "Dieses Angebot wählen", "Scegliere questa offerta", "Choose this offer")
_("Vous avez cliqué sur « Choisir cette offre ». Rien n'est envoyé ni signé : c'est vous qui décidez d'envoyer "
  "la demande. Vous pouvez choisir une autre offre plus haut.",
  "Sie haben auf «Dieses Angebot wählen» geklickt. Nichts wird gesendet oder unterschrieben: Sie entscheiden selbst, "
  "ob Sie den Antrag senden. Sie können weiter oben ein anderes Angebot wählen.",
  "Ha cliccato su «Scegliere questa offerta». Nulla viene inviato né firmato: è lei a decidere se inviare la "
  "domanda. Può scegliere un'altra offerta più in alto.",
  "You clicked “Choose this offer”. Nothing is sent or signed: you decide whether to send the application. You "
  "can choose another offer above.")
_("Franchise {f} CHF", "Franchise {f} CHF", "Franchigia {f} CHF", "Deductible {f} CHF")
_("Dès le {debut}", "Ab {debut}", "Dal {debut}", "From {debut}")
_("Demande rédigée par Apertus ; les éléments obligatoires ont été vérifiés par l'application.",
  "Antrag von Apertus verfasst; die Pflichtangaben wurden von der Anwendung geprüft.",
  "Domanda redatta da Apertus; gli elementi obbligatori sono stati verificati dall'applicazione.",
  "Application written by Apertus; the required elements were checked by the app.")
_("Demande modèle de l'application (celle d'Apertus n'était pas complète).",
  "Musterantrag der Anwendung (der Antrag von Apertus war nicht vollständig).",
  "Domanda modello dell'applicazione (quella di Apertus non era completa).",
  "The app's template application (Apertus's version was incomplete).")
_("Envoyer ma demande à {caisse}", "Antrag an {caisse} senden", "Inviare la mia domanda a {caisse}",
  "Send my application to {caisse}")
_("Votre messagerie s'ouvre avec la demande prête, adressée à {email} (adresse officielle, liste OFSP). "
  "Complétez les champs entre crochets, puis envoyez.",
  "Ihr E-Mail-Programm öffnet sich mit dem fertigen Antrag an {email} (offizielle Adresse, Liste des BAG). "
  "Füllen Sie die Felder in Klammern aus und senden Sie ihn ab.",
  "Si apre il suo programma di posta con la domanda pronta, indirizzata a {email} (indirizzo ufficiale, "
  "elenco dell'UFSP). Completi i campi tra parentesi, poi invii.",
  "Your email opens with the application ready, addressed to {email} (official address, FOPH list). "
  "Fill in the fields in brackets, then send.")
_("{caisse} ne publie pas d'adresse e-mail dans la liste officielle de l'OFSP : envoyez la demande par la "
  "poste (adresse déjà dans la lettre) ou via son site.",
  "{caisse} veröffentlicht in der offiziellen Liste des BAG keine E-Mail-Adresse: Senden Sie den Antrag per "
  "Post (Adresse bereits im Brief) oder über die Website.",
  "{caisse} non pubblica un indirizzo e-mail nell'elenco ufficiale dell'UFSP: invii la domanda per posta "
  "(indirizzo già nella lettera) o tramite il suo sito.",
  "{caisse} does not publish an email address in the official FOPH list: send the application by post "
  "(address already in the letter) or through its website.")
_("La demande est écrite dans une langue officielle de votre canton.",
  "Der Antrag ist in einer Amtssprache Ihres Kantons verfasst.",
  "La domanda è scritta in una lingua ufficiale del suo cantone.",
  "The application is written in an official language of your canton.")
_("Voir et copier la demande", "Antrag ansehen und kopieren", "Vedere e copiare la domanda",
  "View and copy the application")
_("Télécharger la demande (.txt)", "Antrag herunterladen (.txt)", "Scaricare la domanda (.txt)",
  "Download the application (.txt)")
_("Modèle médecin de famille : choisissez votre médecin dans la liste de {caisse} (sur son site) et "
  "indiquez-le dans la demande ou à la réception des documents.",
  "Hausarztmodell: Wählen Sie Ihre Ärztin oder Ihren Arzt aus der Liste von {caisse} (auf der Website) und "
  "geben Sie sie oder ihn im Antrag oder beim Erhalt der Unterlagen an.",
  "Modello del medico di famiglia: scelga il suo medico nell'elenco di {caisse} (sul suo sito) e lo indichi "
  "nella domanda o alla ricezione dei documenti.",
  "Family doctor model: choose your doctor from {caisse}'s list (on its website) and state it in the "
  "application or when you receive the documents.")
_("Attendre la confirmation écrite de {caisse}", "Auf die schriftliche Bestätigung von {caisse} warten",
  "Attendere la conferma scritta di {caisse}", "Wait for written confirmation from {caisse}")
_("Votre assurance actuelle ne prend fin que lorsque la nouvelle caisse a confirmé votre couverture (LAMal "
  "art. 7 al. 5). Toute caisse doit accepter chaque personne pour l'assurance de base, sans questionnaire de "
  "santé.",
  "Ihre bisherige Versicherung endet erst, wenn die neue Kasse Ihre Deckung bestätigt hat (KVG Art. 7 "
  "Abs. 5). Jede Kasse muss für die Grundversicherung jede Person aufnehmen, ohne Gesundheitsfragebogen.",
  "La sua assicurazione attuale termina solo quando la nuova cassa ha confermato la copertura (LAMal art. 7 "
  "cpv. 5). Ogni cassa deve accettare ogni persona per l'assicurazione di base, senza questionario sulla salute.",
  "Your current insurance only ends once the new insurer has confirmed your cover (KVG/LAMal art. 7 para. 5). "
  "Every insurer must accept everyone for basic insurance, without a health questionnaire.")
_("Votre lettre de résiliation est prête plus haut dans la conversation.",
  "Ihr Kündigungsschreiben steht weiter oben im Gespräch bereit.",
  "La sua lettera di disdetta è pronta più in alto nella conversazione.",
  "Your cancellation letter is ready further up in the conversation.")
_("Rédiger ma lettre de résiliation pour {caisse}", "Kündigungsschreiben für {caisse} verfassen",
  "Redigere la lettera di disdetta per {caisse}", "Write my cancellation letter for {caisse}")
_("Dites-moi chez quelle caisse vous êtes aujourd'hui : je rédige la lettre de résiliation. Si vous arrivez "
  "en Suisse, il n'y a rien à résilier.",
  "Sagen Sie mir, bei welcher Kasse Sie heute sind: Ich verfasse das Kündigungsschreiben. Wenn Sie neu in die "
  "Schweiz ziehen, gibt es nichts zu kündigen.",
  "Mi dica presso quale cassa è assicurato/a oggi: redigo la lettera di disdetta. Se arriva in Svizzera, non "
  "c'è nulla da disdire.",
  "Tell me which insurer you are with today: I will write the cancellation letter. If you are moving to "
  "Switzerland, there is nothing to cancel.")
_("Ajouter un rappel à mon agenda", "Erinnerung in meinen Kalender", "Aggiungere un promemoria al calendario",
  "Add a reminder to my calendar")
_("votre caisse actuelle", "Ihrer bisherigen Kasse", "la sua cassa attuale", "your current insurer")
_("Résilier l'assurance de base chez {caisse} (lettre reçue au plus tard le {limite})",
  "Grundversicherung bei {caisse} kündigen (Brief muss bis {limite} eintreffen)",
  "Disdire l'assicurazione di base presso {caisse} (lettera ricevuta entro il {limite})",
  "Cancel basic insurance with {caisse} (letter must arrive by {limite})")
_("Demande d'affiliation à l'assurance de base dès le {debut} – {produit}",
  "Antrag auf Aufnahme in die Grundversicherung ab {debut} – {produit}",
  "Domanda di affiliazione all'assicurazione di base dal {debut} – {produit}",
  "Application for basic health insurance from {debut} – {produit}")
_("incluse", "eingeschlossen", "inclusa", "included")
_("exclue (déjà assuré par mon employeur)", "ausgeschlossen (bereits über meinen Arbeitgeber versichert)",
  "esclusa (già assicurato tramite il datore di lavoro)", "excluded (already insured through my employer)")

_("Vous restez chez {caisse} : rien à résilier, la demande ci-dessus suffit pour changer de produit ou de "
  "franchise (même délai).",
  "Sie bleiben bei {caisse}: Es gibt nichts zu kündigen, der Antrag oben genügt, um Produkt oder Franchise zu "
  "wechseln (gleiche Frist).",
  "Rimane presso {caisse}: non c'è nulla da disdire, la domanda qui sopra basta per cambiare prodotto o "
  "franchigia (stesso termine).",
  "You are staying with {caisse}: nothing to cancel, the application above is enough to change product or "
  "deductible (same deadline).")

_("Calculer et demander mon offre chez {caisse}", "Prämie berechnen und Offerte bei {caisse} anfordern",
  "Calcolare e chiedere un'offerta a {caisse}", "Calculate and request my offer from {caisse}")
_("Assurance de base de {caisse} (site officiel)", "Grundversicherung von {caisse} (offizielle Website)",
  "Assicurazione di base di {caisse} (sito ufficiale)", "{caisse} basic insurance (official website)")
_("Site officiel de {caisse}", "Offizielle Website von {caisse}", "Sito ufficiale di {caisse}",
  "Official website of {caisse}")
_("accidents inclus", "mit Unfalldeckung", "infortuni inclusi", "accidents included")
_("accidents exclus", "ohne Unfalldeckung", "infortuni esclusi", "accidents excluded")

_("La moins chère d'une autre caisse", "Die günstigste einer anderen Kasse", "La più conveniente di un'altra cassa",
  "Cheapest from another insurer")
_("Aussi : {x}", "Auch: {x}", "Anche: {x}", "Also: {x}")
_("Votre choix : {caisse}", "Ihre Wahl: {caisse}", "La sua scelta: {caisse}", "Your choice: {caisse}")
_("Apertus prépare votre demande d'affiliation…", "Apertus bereitet Ihren Antrag vor…",
  "Apertus prepara la sua domanda di affiliazione…", "Apertus is preparing your application…")

# Ce que l'assurance de base ne couvre pas, et assurances complémentaires
_("Ce qui compte aussi pour moi (facultatif)", "Was mir auch wichtig ist (freiwillig)",
  "Cosa conta anche per me (facoltativo)", "What also matters to me (optional)")
_("Lunettes, dentiste, médecines complémentaires…", "Brille, Zahnarzt, Komplementärmedizin…",
  "Occhiali, dentista, medicine complementari…", "Glasses, dentist, complementary medicine…")
_("Après votre choix, je vous montrerai ce que l'assurance de base ne paie pas pour ces besoins.",
  "Nach Ihrer Wahl zeige ich Ihnen, was die Grundversicherung dafür nicht bezahlt.",
  "Dopo la sua scelta, le mostrerò cosa l'assicurazione di base non paga per queste esigenze.",
  "After your choice, I will show you what basic insurance does not pay for these needs.")
_("Hors assurance de base : {x}", "Ausserhalb der Grundversicherung: {x}", "Fuori dall'assicurazione di base: {x}",
  "Outside basic insurance: {x}")
_("Votre choix : assurance de base (LAMal)", "Ihre Wahl: Grundversicherung (KVG)",
  "La sua scelta: assicurazione di base (LAMal)", "Your choice: basic insurance (LAMal)")
_("Assurance de base (LAMal) uniquement", "Nur Grundversicherung (KVG)", "Solo assicurazione di base (LAMal)",
  "Basic insurance (LAMal) only")
_("Demander l’assurance de base (LAMal) à {caisse}", "Grundversicherung (KVG) bei {caisse} beantragen",
  "Chiedere l’assicurazione di base (LAMal) a {caisse}", "Apply for basic insurance (LAMal) with {caisse}")
_("Cette demande concerne uniquement l'assurance de base (LAMal).",
  "Dieser Antrag betrifft nur die Grundversicherung (KVG).",
  "Questa domanda riguarda solo l'assicurazione di base (LAMal).",
  "This application concerns basic insurance (LAMal) only.")
_("Sur le site, choisissez l'assurance de base (LAMal) : {produit} ({modele}), franchise {f} CHF, {accidents}, "
  "début le {debut}.",
  "Wählen Sie auf der Website die Grundversicherung (KVG): {produit} ({modele}), Franchise {f} CHF, {accidents}, "
  "Beginn am {debut}.",
  "Sul sito, scelga l'assicurazione di base (LAMal): {produit} ({modele}), franchigia {f} CHF, {accidents}, "
  "inizio il {debut}.",
  "On the website, choose basic insurance (LAMal): {produit} ({modele}), deductible {f} CHF, {accidents}, start "
  "on {debut}.")
_("Résilier l’assurance de base (LAMal) chez votre caisse actuelle avant le {limite}",
  "Grundversicherung (KVG) bei Ihrer jetzigen Kasse vor dem {limite} kündigen",
  "Disdire l’assicurazione di base (LAMal) presso la sua cassa attuale prima del {limite}",
  "Cancel basic insurance (LAMal) with your current insurer before {limite}")
_("La lettre résilie uniquement l'assurance de base (LAMal). Vos assurances complémentaires continuent chez "
  "votre caisse actuelle.",
  "Der Brief kündigt nur die Grundversicherung (KVG). Ihre Zusatzversicherungen laufen bei Ihrer jetzigen "
  "Kasse weiter.",
  "La lettera disdice solo l'assicurazione di base (LAMal). Le sue assicurazioni complementari continuano "
  "presso la sua cassa attuale.",
  "The letter cancels basic insurance (LAMal) only. Your supplementary insurance continues with your current "
  "insurer.")
_("Cette lettre résilie uniquement l'assurance de base (LAMal). Vos assurances complémentaires continuent.",
  "Dieser Brief kündigt nur die Grundversicherung (KVG). Ihre Zusatzversicherungen laufen weiter.",
  "Questa lettera disdice solo l'assicurazione di base (LAMal). Le sue assicurazioni complementari continuano.",
  "This letter cancels basic insurance (LAMal) only. Your supplementary insurance continues.")
_("Ce que l’assurance de base ne paie pas", "Was die Grundversicherung nicht bezahlt",
  "Cosa l’assicurazione di base non paga", "What basic insurance does not pay")
_("Vous n'avez rien coché dans le formulaire : voici les cas les plus fréquents.",
  "Sie haben im Formular nichts angekreuzt: Hier die häufigsten Fälle.",
  "Non ha selezionato nulla nel modulo: ecco i casi più frequenti.",
  "You did not tick anything in the form: here are the most common cases.")
_("Besoin", "Bedarf", "Esigenza", "Need")
_("L'assurance de base paie", "Die Grundversicherung bezahlt", "L'assicurazione di base paga", "Basic insurance pays")
_("Elle ne paie pas", "Sie bezahlt nicht", "Non paga", "It does not pay")
_("Source", "Quelle", "Fonte", "Source")
_("Pour ce que l'assurance de base ne paie pas, il faut une assurance complémentaire.",
  "Für das, was die Grundversicherung nicht bezahlt, braucht es eine Zusatzversicherung.",
  "Per ciò che l'assicurazione di base non paga, serve un'assicurazione complementare.",
  "For what basic insurance does not pay, you need supplementary insurance.")
_("Les complémentaires sont des assurances privées : la caisse peut poser des questions sur votre santé, émettre "
  "des réserves ou refuser. Leurs primes ne sont pas publiées : demandez une offre.",
  "Zusatzversicherungen sind private Versicherungen: Die Kasse kann Fragen zu Ihrer Gesundheit stellen, "
  "Vorbehalte anbringen oder ablehnen. Ihre Prämien sind nicht öffentlich: Verlangen Sie eine Offerte.",
  "Le complementari sono assicurazioni private: la cassa può porre domande sulla sua salute, formulare riserve "
  "o rifiutare. I loro premi non sono pubblicati: chieda un'offerta.",
  "Supplementary insurance is private: the insurer may ask about your health, add exclusions or refuse. "
  "Premiums are not published: ask for a quote.")
_("Vous pouvez avoir l'assurance de base et les complémentaires dans des caisses différentes. Votre caisse "
  "actuelle ne peut ni vous obliger à résilier vos complémentaires, ni les résilier parce que vous changez "
  "d'assurance de base (LAMal art. 7 al. 7 et 8).",
  "Grund- und Zusatzversicherung können bei verschiedenen Kassen sein. Ihre jetzige Kasse kann Sie weder zur "
  "Kündigung Ihrer Zusatzversicherungen zwingen noch sie kündigen, weil Sie die Grundversicherung wechseln "
  "(KVG Art. 7 Abs. 7 und 8).",
  "Può avere l'assicurazione di base e le complementari presso casse diverse. La sua cassa attuale non può né "
  "obbligarla a disdire le complementari, né disdirle perché lei cambia assicurazione di base (LAMal art. 7 "
  "cpv. 7 e 8).",
  "You can have basic and supplementary insurance with different insurers. Your current insurer can neither "
  "force you to cancel your supplementary insurance nor cancel it because you change basic insurance (LAMal "
  "art. 7 para. 7 and 8).")
_("Si vous voulez changer aussi de complémentaire : ne résiliez l'ancienne qu'après avoir reçu l'acceptation "
  "écrite de la nouvelle.",
  "Wenn Sie auch die Zusatzversicherung wechseln wollen: Kündigen Sie die alte erst, wenn die neue Sie "
  "schriftlich aufgenommen hat.",
  "Se vuole cambiare anche la complementare: disdica la vecchia solo dopo aver ricevuto l'accettazione scritta "
  "della nuova.",
  "If you also want to change supplementary insurance: cancel the old one only after the new one has accepted "
  "you in writing.")
_("Complémentaires de {caisse} : [{site}]({lien}).", "Zusatzversicherungen von {caisse}: [{site}]({lien}).",
  "Complementari di {caisse}: [{site}]({lien}).", "Supplementary insurance from {caisse}: [{site}]({lien}).")


_("Une question ? Posez-la-moi", "Eine Frage? Stellen Sie sie mir", "Una domanda? Me la faccia", "A question? Ask me")
_("Écrivez votre question ici…", "Schreiben Sie Ihre Frage hier…", "Scriva qui la sua domanda…",
  "Write your question here…")
_("Par exemple :", "Zum Beispiel:", "Per esempio:", "For example:")
_("Combien économiseriez-vous ? (facultatif)", "Wie viel würden Sie sparen? (freiwillig)",
  "Quanto risparmierebbe? (facoltativo)", "How much would you save? (optional)")
_("Votre caisse actuelle, et votre modèle si vous le connaissez",
  "Ihre jetzige Kasse, und Ihr Modell, wenn Sie es kennen",
  "La sua cassa attuale, e il suo modello se lo conosce", "Your current insurer, and your model if you know it")
_("Ex. : Helsana, médecin de famille", "Z. B.: Helsana, Hausarztmodell", "Es.: Helsana, medico di famiglia",
  "E.g. Helsana, family doctor")
_("Calculer mon économie", "Meine Ersparnis berechnen", "Calcolare il mio risparmio", "Calculate my savings")

# Ordre du parcours : offres -> économie -> choix -> inscription -> lettre ; caisse actuelle dans le formulaire
_("Pour changer, cliquez sur « Choisir cette offre » sous l'offre qui vous convient : je vous guide jusqu'à "
  "l'inscription, puis je rédige votre lettre de résiliation pour {caisse}.",
  "Zum Wechseln klicken Sie unter dem passenden Angebot auf «Dieses Angebot wählen»: Ich begleite Sie bis zur "
  "Anmeldung und verfasse danach Ihr Kündigungsschreiben für {caisse}.",
  "Per cambiare, clicchi su «Scegliere questa offerta» sotto l'offerta che le conviene: la accompagno fino "
  "all'iscrizione, poi redigo la sua lettera di disdetta per {caisse}.",
  "To switch, click “Choose this offer” under the offer that suits you: I will guide you through the application, "
  "then write your cancellation letter for {caisse}.")
_("Votre caisse actuelle", "Ihre jetzige Kasse", "La sua cassa attuale", "Your current insurer")
_("Choisissez votre caisse actuelle…", "Wählen Sie Ihre jetzige Kasse…", "Scelga la sua cassa attuale…",
  "Choose your current insurer…")
_("Rédiger ma lettre de résiliation", "Mein Kündigungsschreiben verfassen", "Redigere la mia lettera di disdetta",
  "Write my cancellation letter")
_("Si vous arrivez en Suisse, il n'y a rien à résilier.", "Wenn Sie neu in die Schweiz ziehen, gibt es nichts zu "
  "kündigen.", "Se arriva in Svizzera, non c'è nulla da disdire.", "If you are moving to Switzerland, there is "
  "nothing to cancel.")
_("Votre caisse actuelle (facultatif)", "Ihre jetzige Kasse (freiwillig)", "La sua cassa attuale (facoltativo)",
  "Your current insurer (optional)")
_("Je calcule ce que vous économiseriez en changeant. Si vous arrivez en Suisse, laissez vide.",
  "Ich berechne, wie viel Sie mit einem Wechsel sparen würden. Wenn Sie neu in die Schweiz ziehen, leer lassen.",
  "Calcolo quanto risparmierebbe cambiando. Se arriva in Svizzera, lasci vuoto.",
  "I calculate how much you would save by switching. If you are moving to Switzerland, leave it empty.")
_("Je n'ai pas reconnu la caisse « {texte} ». Indiquez-la ci-dessous (ex. : Helsana).",
  "Ich habe die Kasse «{texte}» nicht erkannt. Geben Sie sie unten an (z. B. Helsana).",
  "Non ho riconosciuto la cassa «{texte}». La indichi qui sotto (es. Helsana).",
  "I did not recognise the insurer “{texte}”. Please enter it below (e.g. Helsana).")
_("Aujourd'hui : {caisse}", "Heute: {caisse}", "Oggi: {caisse}", "Today: {caisse}")

TRAD = {fr: dict(zip(("de", "it", "en"), v)) for fr, v in T.items()}
