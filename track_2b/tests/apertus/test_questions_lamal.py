"""Test des connaissances LAMal d'Apertus : 30 questions réalistes (série A) + 2 × 15 de contrôle (séries B et C), posées après les résultats.

Les questions ont été écrites AVANT de construire la recherche dans les textes de loi, sans les
adapter à la fiche actuelle. Le même fichier servira de mesure « avant » (fiche de 17 phrases) et
« après » (vrais articles de loi).

Pour chaque question, le script note :
  - la réponse affichée (avec sa ligne « Source » s'il y en a une) ;
  - le temps d'attente ;
  - REPONDU / NE SAIT PAS / SECOURS (aucune réponse fiable d'Apertus) ;
  - la réponse attendue (pour la correction à la main, qui se fait ensuite).

    docker run --rm --env-file .env -v "$HOME\\Downloads:/dl" hia-nouveau python tests/apertus/test_questions_lamal.py
    -> crée Downloads\\resultats_questions_lamal.txt   (environ 15 à 20 minutes)
"""
import os as _os
import sys as _sys

# Lancement depuis track_2b/ (ou /app dans le conteneur). Résultats : /dl s'il est monté (Docker,
# -v "$HOME\\Downloads:/dl"), sinon tests/apertus/resultats/.
_ICI = _os.path.dirname(_os.path.abspath(__file__))
_RACINE = _os.path.dirname(_os.path.dirname(_ICI))
_os.chdir(_RACINE)
_sys.path[:0] = [_ICI, _os.path.join(_RACINE, "src")]
RESULTATS = "/dl" if _os.path.isdir("/dl") else _os.path.join(_ICI, "resultats")
_os.makedirs(RESULTATS, exist_ok=True)
import os
import re
import sys
import time

import app  # noqa: E402  (même client et mêmes délais que l'application)
import conversation  # noqa: E402

try:  # recherche dans les textes de loi (absente de la version « avant »)
    import lois  # noqa: E402
    AVEC_LOIS = bool(lois.base()[0])
except ImportError:
    lois, AVEC_LOIS = None, False

PROFIL = ("Profil : 35 ans, Lausanne 1004 (VD), franchise 1500 CHF, couverture accidents incluse, "
          "tous les modèles acceptés.\nLes offres affichées ne sont pas utiles pour cette question.")

LANGUE = {"fr": "français", "de": "allemand", "it": "italien", "en": "anglais"}

# (code langue, question, réponse attendue pour la correction)
# (code langue, question, réponse attendue pour la correction, article qui contient la réponse)
# Série A : 30 questions écrites avant la recherche dans les lois. ATTENTION : la recherche a ensuite été
# réglée en regardant ces questions ; ce n'est donc plus une mesure propre pour la recherche (seulement pour
# la rédaction d'Apertus).
QUESTIONS = [
    ('fr', 'Ma fille va avoir 19 ans, est-ce que sa prime va changer ?',
     'Oui : elle passe de la catégorie enfants à jeunes adultes (19-25 ans), prime plus élevée.', 'LAMal art. 61'),
    ('fr', "Est-ce qu'un accouchement me coûte la franchise ou la quote-part ?",
     'Non : prestations de maternité sans franchise ni quote-part (LAMal art. 64 al. 7).', 'LAMal art. 64 al. 7'),
    ('fr', "Je pars en vacances en Espagne, suis-je couvert en cas d'urgence ?",
     'Oui pour les urgences, au maximum le double de ce que coûterait le traitement en Suisse.', 'OAMal art. 36'),
    ('fr', "La psychothérapie est-elle remboursée par l'assurance de base ?",
     'Oui, sur prescription médicale, par un psychothérapeute reconnu (OPAS).', 'OPAS art. 11b'),
    ('fr', 'Est-ce que la physiothérapie est remboursée ?',
     'Oui, sur prescription médicale (séries de séances prescrites).', 'OPAS art. 5'),
    ('fr', "Les frais d'ambulance sont-ils couverts ?",
     'En partie : 50 %, au maximum 500 CHF par an pour le transport (5000 CHF pour un sauvetage).', 'OPAS art. 26'),
    ('fr', 'Que se passe-t-il si je ne paie pas mes primes ?',
     "Rappels puis poursuites ; on ne peut pas changer d'assureur tant que les dettes ne sont pas payées.", 'LAMal art. 64a'),
    ('fr', "Est-ce que je peux changer de franchise en cours d'année ?",
     "Non, en principe pour le 1er janvier ; la franchise est choisie pour l'année civile.", 'OAMal art. 94'),
    ('fr', 'Quel est le délai pour résilier mon assurance de base ?',
     'Lettre reçue au plus tard le dernier jour ouvrable de novembre (changement au 1er janvier).', 'LAMal art. 7 al. 1'),
    ('fr', 'Les vaccins sont-ils remboursés ?',
     "Oui pour les vaccins de la liste de l'OPAS (selon les recommandations), pas les vaccins de voyage.", 'OPAS art. 12a'),
    ('fr', 'Une visite chez le dentiste est-elle prise en charge ?',
     "Non en général ; seulement maladies graves du système de mastication ou suites d'une maladie grave.", 'LAMal art. 31'),
    ('fr', 'Les lunettes de mon fils de 10 ans sont-elles remboursées ?',
     "Oui pour les enfants jusqu'à 18 ans, avec un montant maximal par année (180 CHF).", 'OPAS art. 20a'),
    ('fr', "Je suis frontalier et j'habite en France, dois-je prendre la LAMal ?",
     "Droit d'option : LAMal ou système français, choix à faire dans les 3 mois.", 'OAMal art. 3'),
    ('fr', 'Les médicaments génériques me coûtent-ils moins cher ?',
     "Oui : si l'original est choisi alors qu'un générique existe, la quote-part peut monter à 40 %.", 'OPAS art. 38a'),
    ('fr', "Suis-je obligé d'avoir un médecin de famille ?",
     'Non, seulement si on choisit le modèle médecin de famille.', 'OAMal art. 99'),
    ('fr', "Puis-je me faire soigner dans n'importe quel hôpital de Suisse ?",
     'Libre choix parmi les hôpitaux de la liste ; hors canton, remboursé au tarif du canton de domicile.', 'LAMal art. 41'),
    ('fr', "L'assurance de base paie-t-elle un séjour en EMS ?",
     "Elle paie une partie des soins, pas l'hébergement ni la pension.", 'LAMal art. 25a'),
    ('fr', 'Si je suis hospitalisé, combien je paie au maximum ?',
     "Franchise + quote-part (max 700 CHF) + contribution de 15 CHF par jour d'hôpital.", 'OAMal art. 104'),
    ('fr', "Un assureur peut-il refuser de m'assurer à cause de mon âge ou de ma santé ?",
     "Non : pour l'assurance de base, tout assureur doit accepter toute personne (LAMal art. 4).", 'LAMal art. 4'),
    ('fr', 'Une mammographie de dépistage est-elle remboursée ?',
     'Oui dans le cadre des programmes cantonaux de dépistage (parfois sans franchise).', 'OPAS art. 12e'),
    ('de', 'Bezahlt die Grundversicherung eine Brille für Erwachsene?',
     'Nein, grundsätzlich nicht (nur bei bestimmten Krankheiten).', 'KLV Art. 20a'),
    ('de', 'Bis wann muss ich kündigen, um die Krankenkasse auf Januar zu wechseln?',
     'Kündigung muss bis zum letzten Arbeitstag im November eingetroffen sein.', 'KVG Art. 7'),
    ('de', 'Werden bei einer Geburt Franchise und Selbstbehalt verrechnet?',
     'Nein, Mutterschaftsleistungen sind von Franchise und Selbstbehalt befreit.', 'KVG Art. 64 Abs. 7'),
    ('de', 'Ich ziehe in einen anderen Kanton. Was passiert mit meiner Prämie?',
     'Die Prämie richtet sich nach dem neuen Wohnort (Kanton/Region).', 'KVG Art. 61'),
    ('it', "La fisioterapia è rimborsata dall'assicurazione di base?",
     'Sì, su prescrizione medica.', 'OPre art. 5'),
    ('it', 'Quanto è la quota parte massima per i bambini?',
     "10 %, al massimo 350 CHF all'anno.", 'LAMal art. 64 cpv. 4'),
    ('it', 'Posso scegliere una franchigia di 2500 franchi per mio figlio?',
     'No: per i bambini la franchigia massima è 600 CHF.', 'OAMal art. 93'),
    ('en', 'Is a dental cleaning covered by basic insurance?',
     'No.', 'LAMal art. 31'),
    ('en', "I'm unemployed. Am I covered if I have an accident?",
     'Yes: if receiving unemployment benefits, through the unemployment accident insurance (Suva); otherwise through the accident cover of the basic insurance.', 'LAMal art. 8'),
    ('en', 'Can my insurer cancel my basic insurance because I got sick?',
     'No: basic insurance cannot be refused or cancelled for health reasons.', 'LAMal art. 4'),
]

# Série B (contrôle) : 15 questions nouvelles, écrites APRÈS le réglage et jamais utilisées pour régler.
# Sans Apertus 8B, la recherche Python seule trouve le bon article pour 10 sur 15.
CONTROLE = [
    ("fr", "Ma mère est en EMS, qui paie les soins ?",
     "L'assurance de base paie une contribution aux soins ; le reste des soins est réglé par le canton, la pension non.", "LAMal art. 25a"),
    ("fr", "Je déménage de Genève à Zurich en cours d'année, je dois changer d'assurance ?",
     "Non, sauf si l'assureur n'est pas actif dans le nouveau canton ; la prime change selon le nouveau lieu.", "LAMal art. 7"),
    ("fr", "Le podologue est-il remboursé pour un diabétique ?",
     "Oui, sur prescription médicale, pour les diabétiques à risque (podologue admis).", "OPAS art. 11c"),
    ("fr", "Est-ce que l'avortement est remboursé ?",
     "Oui, l'interruption de grossesse non punissable est prise en charge comme une maladie.", "LAMal art. 30"),
    ("fr", "Mon bébé vient de naître, combien de temps ai-je pour l'assurer ?",
     "3 mois après la naissance ; l'assurance part alors dès la naissance.", "LAMal art. 3"),
    ("fr", "Les conseils en allaitement sont-ils payés ?",
     "Oui (par une sage-femme ou une infirmière formée, nombre de séances limité).", "OPAS art. 15"),
    ("fr", "Puis-je avoir un bonus si je ne vais jamais chez le médecin ?",
     "Oui si l'assureur propose l'assurance avec bonus : la prime baisse les années sans prestations.", "OAMal art. 96"),
    ("fr", "Combien de séances de logopédie sont remboursées ?",
     "Au plus 12 séances par prescription médicale (nouvelle prescription ensuite).", "OPAS art. 11"),
    ("de", "Zahlt die Krankenkasse die Physiotherapie nach einem Unfall?",
     "Ja, wenn keine Unfallversicherung zahlt, gleich wie bei Krankheit (mit ärztlicher Verordnung).", "KVG Art. 28"),
    ("de", "Wie hoch ist der Spitalbeitrag pro Tag?",
     "15 Franken pro Tag (nicht für Kinder, junge Erwachsene in Ausbildung, Mutterschaft).", "KVV Art. 104"),
    ("de", "Muss ich als Grenzgänger in der Schweiz versichert sein?",
     "Grundsätzlich ja, mit Optionsrecht für das Wohnland (z. B. Frankreich, Italien).", "KVV Art. 3"),
    ("it", "Le vaccinazioni per i viaggi sono coperte?",
     "No, in generale solo le vaccinazioni elencate nell'OPre (non quelle per i viaggi).", "OPre art. 12a"),
    ("it", "Cosa succede se mi assicuro in ritardo?",
     "La copertura inizia dall'affiliazione e si paga un supplemento di premio se il ritardo non è scusabile.", "LAMal art. 5"),
    ("en", "Does basic insurance pay for an abortion?",
     "Yes, a legal termination of pregnancy is covered like an illness.", "LAMal art. 30"),
    ("en", "How long do I have to get insured after moving to Switzerland?",
     "3 months; then cover applies from arrival.", "LAMal art. 3"),
]

# Série C (contrôle n° 2) : 15 questions écrites après les corrections du 12.10 au soir, jamais
# utilisées pour régler quoi que ce soit. Recherche Python seule (sans Apertus 8B) : 10/14.
CONTROLE_2 = [
    ("fr", "Les frais de transport pour aller à mes séances de chimiothérapie sont-ils remboursés ?",
     "En partie : 50 % des frais de transport médicalement nécessaires, au maximum 500 CHF par an.", "OPAS art. 26"),
    ("fr", "Est-ce que l'acupuncture est remboursée ?",
     "Oui si elle est pratiquée par un médecin avec la formation reconnue (médecine complémentaire).", "OAMal art. 35a"),
    ("fr", "Ma fille de 16 ans peut-elle avoir une franchise de 1000 francs ?",
     "Non : pour les enfants (jusqu'à 18 ans), la franchise va de 0 à 600 CHF.", "OAMal art. 93"),
    ("fr", "Je n'ai pas payé mes primes, mon assureur peut-il refuser de rembourser mes soins ?",
     "En principe non ; seulement si le canton tient une liste des mauvais payeurs (sauf urgences).", "LAMal art. 64a"),
    ("fr", "Jusqu'à quand dois-je résilier pour changer d'assureur au 30 juin ?",
     "Préavis de 3 mois (fin mars), possible seulement avec la franchise de 300 CHF et le libre choix.", "LAMal art. 7"),
    ("fr", "Les soins à domicile par une infirmière sont-ils pris en charge ?",
     "Oui, une contribution aux soins sur prescription ou mandat médical (besoin évalué).", "LAMal art. 25a"),
    ("fr", "Est-ce que la pilule contraceptive est remboursée ?",
     "Non en général. « Je ne peux pas répondre de façon fiable » est acceptable ; « oui » est faux.", "-"),
    ("fr", "Puis-je supprimer la couverture accidents si je travaille à 50 % chez un seul employeur ?",
     "Oui si c'est au moins 8 heures par semaine chez cet employeur (assuré par la LAA).", "LAMal art. 8"),
    ("de", "Übernimmt die Grundversicherung eine Ernährungsberatung?",
     "Ja, auf ärztliche Verordnung bei bestimmten Krankheiten (z. B. Diabetes, Adipositas).", "KLV Art. 9b"),
    ("de", "Ich bin schwanger. Muss ich die Kontrolluntersuchungen selber bezahlen?",
     "Nein: Kontrolluntersuchungen sind gedeckt, ohne Kostenbeteiligung (ab der 13. Woche ganz ohne).", "KVG Art. 29"),
    ("de", "Kann ich mitten im Jahr vom Hausarztmodell zur freien Arztwahl wechseln?",
     "Grundsätzlich nur auf Ende des Kalenderjahres (Frist des Versicherers beachten).", "KVV Art. 100"),
    ("it", "Il dentista mi ha tolto un dente del giudizio, paga l'assicurazione di base?",
     "No in generale; solo in caso di malattia grave del sistema masticatorio.", "LAMal art. 31"),
    ("it", "La psicoterapia con uno psicologo è rimborsata?",
     "Sì, su prescrizione medica, da uno psicologo-psicoterapeuta autorizzato (numero di sedute limitato).", "OPre art. 11b"),
    ("en", "Is a stay in a rehabilitation clinic covered?",
     "Yes, medical rehabilitation carried out or prescribed by a doctor is covered.", "LAMal art. 25"),
    ("en", "What happens if I need emergency care while visiting the US?",
     "Emergencies abroad are covered, up to at most twice what the treatment would cost in Switzerland.", "OAMal art. 36"),
]

NE_SAIT_PAS = re.compile(r"ne (?:peux|pourrai) pas répondre|je ne (?:dispose|sais) pas|pas d'information|"
                         r"nicht zuverlässig|keine (?:Information|Angabe)|non posso rispondere|non dispongo|"
                         r"(?:can't|cannot|can not) answer|(?:don't|do not) have (?:the|this|enough) information",
                         re.IGNORECASE)


def main(sortie=_os.path.join(RESULTATS, "resultats_questions_lamal.txt")):
    cfg = app.config()
    client = app.client_llm(cfg["LLM_BASE_URL"], cfg["LLM_API_KEY"]).with_options(timeout=app.DELAI_70B)
    modele = cfg["LLM_NAME_RESTITUTION"] or cfg["LLM_NAME"]
    appel = lambda m, delai: lambda systeme, message: client.with_options(timeout=delai).chat.completions.create(
        model=m, temperature=0,
        messages=[{"role": "system", "content": systeme}, {"role": "user", "content": message}],
    ).choices[0].message.content
    appeler, appeler_8b = appel(modele, app.DELAI_70B), appel(cfg["LLM_NAME"], app.DELAI_8B)

    lignes, compte, durees = [], {"REPONDU": 0, "NE SAIT PAS": 0, "SECOURS": 0}, []
    trouve_cle = {"A": [0, 0], "B": [0, 0], "C": [0, 0]}
    series = [("A", f"Q{i:02d}", q) for i, q in enumerate(QUESTIONS, 1)] + \
             [("B", f"C{i:02d}", q) for i, q in enumerate(CONTROLE, 1)] + \
             [("C", f"N{i:02d}", q) for i, q in enumerate(CONTROLE_2, 1)]
    for serie, nom, (code, question, attendu, cle) in series:
        debut = time.time()
        trouves = ""
        if AVEC_LOIS:  # comme dans l'application : mots-clés d'Apertus 8B, puis recherche Python
            cles = lois.mots_cles(appeler_8b, question)
            passages = lois.chercher(question, code, cles)
            refs = [lois.reference(p, code) for p in passages]
            ok = any(r.startswith(cle) for r in refs)
            if cle != "-":
                trouve_cle[serie][0] += ok
                trouve_cle[serie][1] += 1
            trouves = (f"  Mots-clés 8B : {cles or '(aucun)'}\n  Articles trouvés : {', '.join(refs)}\n"
                       f"  Article clé ({cle}) trouvé : {'OUI' if ok else 'NON'}\n")
            reponse = conversation.repondre_libre(appeler, question, PROFIL, langue=LANGUE[code], code=code,
                                                  passages=passages)
        else:
            reponse = conversation.repondre_libre(appeler, question, PROFIL, langue=LANGUE[code], code=code)
        duree = time.time() - debut
        durees.append(duree)
        etat = "SECOURS" if not reponse else ("NE SAIT PAS" if NE_SAIT_PAS.search(reponse) else "REPONDU")
        compte[etat] += 1
        source = "avec source" if reponse and re.search(r"\*(Source|Quelle|Fonte) :", reponse) else "sans source"
        bloc = (f"{nom} [{code}] {etat} | {duree:.1f} s | {source}\n  Question : {question}\n"
                f"  Attendu  : {attendu}\n{trouves}  Réponse  : {(reponse or '(aucune réponse fiable)').strip()}\n")
        print(bloc, flush=True)
        lignes.append(bloc)
    durees.sort()
    total = len(series)
    resume = (f"RÉSUMÉ : {compte['REPONDU']}/{total} répondues, {compte['NE SAIT PAS']} « ne sait pas », "
              f"{compte['SECOURS']} sans réponse fiable | temps médian {durees[len(durees) // 2]:.1f} s, "
              f"maximum {durees[-1]:.1f} s\n(La justesse de chaque réponse se vérifie ensuite à la main "
              f"avec la ligne « Attendu ».)")
    if AVEC_LOIS:
        resume += (f"\nArticle clé trouvé par la recherche : série A {trouve_cle['A'][0]}/{trouve_cle['A'][1]} "
                   f"(questions ayant servi au réglage), série B {trouve_cle['B'][0]}/{trouve_cle['B'][1]} "
                   f"(contrôle n° 1), série C {trouve_cle['C'][0]}/{trouve_cle['C'][1]} (contrôle n° 2, jamais réglé)")
    print(resume)
    with open(sortie, "w", encoding="utf-8") as f:
        f.write(f"Modèle : {modele} | recherche dans les lois : {'OUI' if AVEC_LOIS else 'non'}\n\n" + "\n".join(lignes) + "\n" + resume + "\n")


if __name__ == "__main__":
    if "--sans-lois" in sys.argv:  # mesure de comparaison : la fiche seule, comme avant la recherche
        sys.argv.remove("--sans-lois")
        AVEC_LOIS = False
        main(_os.path.join(RESULTATS, "resultats_questions_sans_lois.txt"))
    else:
        main(*sys.argv[1:])
