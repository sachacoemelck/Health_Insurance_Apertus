# Résultats bruts des tests avec le vrai Apertus

Fichiers produits par les scripts de `tests/apertus/`, lancés dans le conteneur Docker avec
l'endpoint Apertus du hackathon (`apertus-v1.5-8b` pour la lecture, `apertus-v1.5-70b` pour la
rédaction). Ils ne sont pas modifiés. La correction à la main (juste / partiel / faux) et le
résumé sont dans le rapport technique.

| Fichier | Script | Ce qui est mesuré |
|---|---|---|
| 2026-10-09_conversations_fr_6.txt | test_conversation_fr.py | 6 conversations françaises (premier test) |
| 2026-10-09_conversations_fr_40_avant.txt / _apres.txt | test_conversation_40.py | 40 conversations, avant et après corrections |
| 2026-10-09_conversations_controle_20.txt | test_conversation_controle.py | 20 conversations nouvelles (contrôle) |
| 2026-10-10_conversations_langues_24.txt | test_conversation_langues.py | 24 conversations DE/IT/EN |
| 2026-10-10_conversations_langues_strict_34.txt | test_langues_exigeant.py | 34 conversations, profil vérifié (DE/IT/EN/suisse-allemand/romanche) |
| 2026-10-12_questions_lamal_rag_v1_45.txt | test_questions_lamal.py | 1er passage avec recherche dans les lois (45 questions) |
| 2026-10-12_questions_lamal_fiche_seule_60.txt | test_questions_lamal.py --sans-lois | 60 questions, fiche de 17 phrases seule |
| 2026-10-12_questions_lamal_rag_60.txt | test_questions_lamal.py | 60 questions, avec les articles de loi |
| 2026-10-13_caisse_economie_lettres.txt | test_changement_reel.py | lecture de la caisse, paragraphe d'économie, 9 lettres |

Attention : la colonne « NE SAIT PAS » des fichiers de questions n'est qu'un repérage automatique
(par mots) ; seule la correction à la main du rapport compte.
