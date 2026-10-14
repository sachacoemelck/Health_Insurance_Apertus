"""Test exigeant des langues avec le vrai Apertus : 34 conversations NOUVELLES (8 allemand, 8 italien,
8 anglais, 6 suisse-allemand écrit, 4 romanche), écrites avant de lancer le test.

Pour chaque conversation, le script vérifie automatiquement :
  - que la conversation arrive aux résultats ;
  - que le PROFIL COMPRIS est le bon (canton, âge, franchise, accidents) ;
  - que les réponses sont dans la langue de la personne (allemand pour le suisse-allemand ;
    pas de contrôle de langue pour le romanche, que l'application n'a pas comme langue d'interface).

    docker run --rm --env-file .env -v "$HOME\\Downloads:/dl" hia-nouveau python tests/apertus/test_langues_exigeant.py
    -> crée Downloads\\resultats_langues_exigeant.txt

Mettre test_conversation_fr.py, test_conversation_langues.py ET ce fichier dans Téléchargements.
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
import sys

import test_conversation_fr as base  # noqa: E402
from test_conversation_langues import DEFAUT  # noqa: E402

DEFAUT_RM = {"postal_code": "7000 Cuira", "municipality": "Cuira", "commune": "1", "birth_year": "1990",
             "age": "35 onns", "include_accident": "cun accidents", "care_access": "tut ils models",
             "budget": "nagin limit", "deductible": "2500", "employed": "na", "hours_per_week_one_employer": "0",
             "nonoccupational_covered": "na", "multiple_people": "mo jau"}


def c(id, langue, titre, messages, attendu, apres=(), controle_langue=True):
    defaut = DEFAUT_RM if langue == "rm" else DEFAUT["de" if langue == "gsw" else langue]
    code = {"gsw": "de", "rm": None}.get(langue, langue)
    return dict(id=id, langue=code if controle_langue else None, titre=titre, messages=list(messages),
                apres=list(apres), defaut=dict(defaut), attendu=attendu)


A = lambda canton, age, franchise, accidents: dict(canton=canton, age=age, franchise=franchise, accidents=accidents)

CONVERSATIONS = [
    # --- Allemand -------------------------------------------------------------------------------
    c("X-D1", "de", "Alles in einem Satz",
      ["Guten Tag, ich bin 36 Jahre alt, wohne in Aarau 5000, möchte die Unfalldeckung, alle Modelle sind okay, "
       "kein Budget, Franchise 1000."], A("AG", 36, 1000, True)),
    c("X-D2", "de", "Angestellt, ohne Unfall",
      ["Ich arbeite 40 Stunden pro Woche bei der gleichen Firma, bin 44 und wohne in Zug 6300.",
       "ohne Unfall bitte", "alle Modelle", "kein Limit", "die höchste Franchise"], A("ZG", 44, 2500, False)),
    c("X-D3", "de", "Geburtsjahr statt Alter",
      ["Ich bin 1975 geboren und lebe in Schaffhausen 8200. Mit Unfall, Hausarztmodell ist für mich okay, "
       "Franchise 2000, kein Budget."], A("SH", 1975, 2000, True)),
    c("X-D4", "de", "Frage mitten drin",
      ["Hallo, 27 Jahre, Biel 2502", "Was kostet mich die tiefste Franchise im Vergleich zur höchsten?",
       "mit Unfall", "alle Modelle", "kein Limit", "300"], A("BE", 27, 300, True)),
    c("X-D5", "de", "Kind",
      ["Ich suche eine Versicherung für meinen Sohn, er ist 9 Jahre alt. Wir wohnen in Olten 4600.",
       "mit Unfall", "alle Modelle", "kein Limit", "Franchise 0"], A("SO", 9, 0, True)),
    c("X-D6", "de", "Korrektur",
      ["Ich bin 50, wohne in Baden 5400", "Entschuldigung, ich wohne eigentlich in Wettingen 5430",
       "mit Unfall", "alle Modelle", "kein Limit", "2500"], A("AG", 50, 2500, True)),
    c("X-D7", "de", "Budget",
      ["33 Jahre, Frauenfeld 8500, höchstens 350 Franken pro Monat, mit Unfall, alle Modelle", "2500"],
      A("TG", 33, 2500, True)),
    c("X-D8", "de", "Nach den Resultaten",
      ["58 Jahre, Liestal 4410, mit Unfall, alle Modelle, kein Limit, Franchise 300"],
      A("BL", 58, 300, True), apres=["Was zahle ich höchstens pro Jahr?"]),
    # --- Italien --------------------------------------------------------------------------------
    c("X-I1", "it", "Tutto in una frase",
      ["Buonasera, ho 42 anni, abito a Lugano 6900, con infortuni, accetto tutti i modelli, nessun limite di "
       "budget, franchigia 1500."], A("TI", 42, 1500, True)),
    c("X-I2", "it", "Dipendente senza infortuni",
      ["Lavoro 42 ore alla settimana presso lo stesso datore di lavoro, ho 39 anni e vivo a Bellinzona 6500.",
       "senza infortuni", "tutti i modelli", "nessun limite", "la franchigia più alta"], A("TI", 39, 2500, False)),
    c("X-I3", "it", "Anno di nascita",
      ["Sono nata nel 1988, abito a Locarno 6600, con infortuni, franchigia 2000, tutti i modelli, nessun limite."],
      A("TI", 1988, 2000, True)),
    c("X-I4", "it", "Domanda in mezzo",
      ["Salve, 24 anni, Mendrisio 6850", "Cosa conviene di più a un giovane, franchigia alta o bassa?",
       "sono nato nel 2002", "con infortuni", "tutti i modelli", "nessun limite", "2500"], A("TI", 2002, 2500, True)),
    c("X-I5", "it", "Figlio",
      ["Cerco un'assicurazione per mia figlia di 12 anni, viviamo a Chiasso 6830.",
       "con infortuni", "tutti i modelli", "nessun limite", "franchigia 0"], A("TI", 12, 0, True)),
    c("X-I6", "it", "Italiano dei Grigioni",
      ["Ho 61 anni e abito a Poschiavo 7742, con infortuni, tutti i modelli, nessun limite, franchigia 300."],
      A("GR", 61, 300, True)),
    c("X-I7", "it", "Budget preciso",
      ["30 anni, Lugano 6900, al massimo 300 franchi al mese, con infortuni, tutti i modelli", "2500"],
      A("TI", 30, 2500, True)),
    c("X-I8", "it", "Dopo i risultati",
      ["47 anni, Locarno 6600, con infortuni, tutti i modelli, nessun limite, franchigia 2500"],
      A("TI", 47, 500, True), apres=["E con una franchigia di 500?"]),  # la franchise change : 500 attendu
    # --- Anglais --------------------------------------------------------------------------------
    c("X-E1", "en", "All in one sentence",
      ["Hi, I'm 31, I live in Lausanne 1004, include accidents, any model is fine, no budget limit, deductible 1000."],
      A("VD", 31, 1000, True)),
    c("X-E2", "en", "Employed, no accidents",
      ["I work full time, 42 hours a week for the same employer. I'm 40 and live in Zug 6300.",
       "without accidents", "all models", "no limit", "the highest deductible"], A("ZG", 40, 2500, False)),
    c("X-E3", "en", "Birth year",
      ["I was born in 1982 and I live in Basel 4051. With accidents, family doctor model is fine, deductible 1500, "
       "no budget limit."], A("BS", 1982, 1500, True)),
    c("X-E4", "en", "Question in the middle",
      ["Hello, 29, Geneva 1205", "Is the deductible paid per year or per illness?",
       "with accidents", "all models", "no limit", "2500"], A("GE", 29, 2500, True)),
    c("X-E5", "en", "Child",
      ["I need insurance for my son, he is 5. We live in Zurich 8001.",
       "with accidents", "all models", "no limit", "deductible 0"], A("ZH", 5, 0, True)),
    c("X-E6", "en", "Correction",
      ["I'm 35, living in Bern 3011", "sorry, I actually live in Köniz 3098",
       "with accidents", "all models", "no limit", "2500"], A("BE", 35, 2500, True)),
    c("X-E7", "en", "Budget",
      ["27 years old, Neuchâtel 2000, max 320 CHF per month, with accidents, all models", "2500"],
      A("NE", 27, 2500, True)),
    c("X-E8", "en", "After results",
      ["52, Lucerne 6003, with accidents, all models, no limit, deductible 1500"],
      A("LU", 52, 1500, True), apres=["Why is the family doctor model cheaper?"]),
    # --- Suisse-allemand écrit (orthographe non standard) -----------------------------------------
    c("X-G1", "gsw", "Bärn",
      ["Grüezi, ich bi 35i und wohn z'Bärn, 3011. Mit Unfall bitte, alli Modäll sind mir glich, kei Limit, "
       "Franchise 2500."], A("BE", 35, 2500, True)),
    c("X-G2", "gsw", "Züri, ohni Unfall",
      ["Hoi, bin 28 Jahr alt, wohne in Züri 8004, ohni Unfall – ich schaffe 42 Stund pro Wuche bim gliiche "
       "Arbetgeber. Franchise 1500.", "alli Modäll", "kei Limit"], A("ZH", 28, 1500, False)),
    c("X-G3", "gsw", "Basel",
      ["Ich bi 52gi, wohne z'Basel 4051, Unfall inklusiv, d'höchsti Franchise, alli Modäll, kei Limit."],
      A("BS", 52, 2500, True)),
    c("X-G4", "gsw", "Tochter",
      ["Mini Tochter isch 8 Johr alt, mir wohne in Luzärn 6003, Franchise 0, mit Unfall.", "alli Modäll",
       "kei Limit"], A("LU", 8, 0, True)),
    c("X-G5", "gsw", "Student",
      ["Bi Student, 22i, wohne z'St. Gallä 9000, ha wenig Gäld. Mit Unfall, Franchise 2500.", "alli Modäll",
       "kei Limit"], A("SG", 22, 2500, True)),
    c("X-G6", "gsw", "Thun",
      ["Grüessech, ich bi 67 und wohne z'Thun 3600. Dr Unfall mues drin si, Franchise 300.", "alli Modäll",
       "kei Limit"], A("BE", 67, 300, True)),
    # --- Romanche (rumantsch grischun) : pas de contrôle de langue de l'interface -----------------
    c("X-R1", "rm", "Cuira",
      ["Bun di! Jau hai 40 onns ed abitesch a Cuira 7000. Cun accidents, franchisa 2500, tut ils models, "
       "nagin limit."], A("GR", 40, 2500, True), controle_langue=False),
    c("X-R2", "rm", "Glion, senza accidents",
      ["Jau hai 33 onns, abitesch a Glion 7130, senza accidents, jau lavur 40 uras l'emna tar il medem patrun. "
       "Franchisa 1500, tut ils models, nagin limit."], A("GR", 33, 1500, False), controle_langue=False),
    c("X-R3", "rm", "Scuol",
      ["Allegra! Jau hai 58 onns, abitesch a Scuol 7550, cun accidents, la franchisa la pli auta, tut ils "
       "models, nagin limit."], A("GR", 58, 2500, True), controle_langue=False),
    c("X-R4", "rm", "Figlia",
      ["Mia figlia ha 10 onns, nus abitain a Domat/Ems 7013, cun accidents, franchisa 0, tut ils models, "
       "nagin limit."], A("GR", 10, 0, True), controle_langue=False),
]


def main():
    base.CONVERSATIONS[:] = CONVERSATIONS
    base.main(_os.path.join(RESULTATS, "resultats_langues_exigeant.txt"))


if __name__ == "__main__":
    main()
