"""Apparence de l'app : sobre, beaucoup d'espace, police système, un seul bleu d'accent.

Les couleurs de base sont dans .streamlit/config.toml ([theme]) ; ce fichier ajoute le reste
(arrondis, boutons en pilule, onglets, bulles de chat), en mode clair et en mode sombre.
Sélecteurs vérifiés avec Streamlit 1.65.0.
"""
import html

import streamlit as st

CSS = """
<style>
/* Couleurs : une variable par rôle, en clair et en sombre. light-dark() suit le thème choisi dans
   Streamlit (menu ⋮ > Settings, ou le réglage du système) : Streamlit pose color-scheme sur .stApp. */
.stApp {
    --texte: light-dark(#1d1d1f, #f5f5f7);
    --texte-2: light-dark(#6e6e73, #a1a1a6);
    --texte-3: light-dark(#86868b, #8e8e93);
    --fond: light-dark(#ffffff, #111113);
    --surface: light-dark(#f5f5f7, #1c1c1e);
    --surface-haute: light-dark(#ffffff, #2c2c2e);
    --bord: light-dark(#d2d2d7, #3a3a3c);
    --ligne: light-dark(#e8e8ed, #2c2c2e);
    --accent: light-dark(#0071e3, #2997ff);
    --accent-survol: light-dark(#0077ed, #47a6ff);
    --accent-doux: light-dark(#f5f9ff, rgba(41, 151, 255, 0.12));
    --accent-tag: light-dark(#e8f1fc, rgba(41, 151, 255, 0.18));
    --orange: light-dark(#bf4800, #ff9f0a);
    --verre: light-dark(rgba(255, 255, 255, 0.72), rgba(17, 17, 19, 0.72));
    --filet: light-dark(rgba(0, 0, 0, 0.06), rgba(255, 255, 255, 0.08));
    --ombre: light-dark(rgba(0, 0, 0, 0.08), rgba(0, 0, 0, 0.55));
}
html, body, .stApp, .stApp *:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded) {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Helvetica Neue",
                 Helvetica, Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
}
.stApp { background: var(--fond); color: var(--texte); }
.block-container { max-width: 800px; padding-top: 3.5rem; padding-bottom: 6rem; }

/* Barre du haut translucide, menu « Deploy » masqué */
header[data-testid="stHeader"] {
    background: var(--verre);
    backdrop-filter: saturate(180%) blur(20px); -webkit-backdrop-filter: saturate(180%) blur(20px);
    border-bottom: 1px solid var(--filet);
}
[data-testid="stAppDeployButton"] { display: none; }

/* Titres */
h1, h2, h3, h4 { color: var(--texte); font-weight: 600 !important; letter-spacing: -0.02em; }
h2 { font-size: 1.9rem !important; padding-top: 1.5rem !important; }
h3 { font-size: 1.4rem !important; }
[data-testid="stCaptionContainer"] { color: var(--texte-3) !important; opacity: 1 !important; }
hr { border-color: var(--ligne) !important; }
.stApp a { color: var(--accent); }
.stApp a:hover { color: var(--accent-survol); }

/* En-tête centré */
.entete { text-align: center; padding: 1rem 0 2.2rem; }
.entete .surtitre { color: var(--orange); font-size: 0.95rem; font-weight: 600; margin: 0 0 0.5rem; }
.entete h1 {
    font-size: clamp(2.3rem, 6vw, 3.5rem); line-height: 1.07; font-weight: 700 !important;
    letter-spacing: -0.035em; margin: 0; padding: 0;
}
.entete h1 .gris { color: var(--texte-3); }
.entete [data-testid="stHeaderActionElements"] { display: none; }
.entete .sous-titre {
    font-size: 1.2rem; line-height: 1.45; color: var(--texte-2); max-width: 34rem; margin: 1.1rem auto 0;
}
.entete .note { font-size: 0.85rem; color: var(--texte-3); margin-top: 1.4rem; }
.entete .note b { color: var(--texte); font-weight: 600; }

/* Barre latérale */
section[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--filet); }

/* Boutons en pilule */
.stButton > button {
    border-radius: 980px; padding: 0.55rem 1.35rem; font-weight: 500; font-size: 0.98rem;
    border: 1px solid var(--bord); background: var(--fond); color: var(--accent); box-shadow: none;
    transition: background 0.2s ease, border-color 0.2s ease, transform 0.1s ease;
}
.stButton > button:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-doux); }
.stButton > button:active { transform: scale(0.98); }
.stButton > button[kind="primary"] { background: var(--accent); color: #ffffff; border: 1px solid var(--accent); }
.stButton > button[kind="primary"]:hover { background: var(--accent-survol); border-color: var(--accent-survol); color: #ffffff; }
.stButton > button:disabled { opacity: 0.35; }

/* Champs du formulaire : les couleurs viennent du thème (secondaryBackgroundColor) ; puces des choix en bleu doux */
[data-testid="stMultiSelectTagsContainer"] [data-tag] {
    border-radius: 980px !important; background: var(--accent-tag) !important; color: var(--accent) !important;
}
[data-testid="stMultiSelectTagsContainer"] [data-tag] * { color: var(--accent) !important; }
[data-testid="stWidgetLabel"] p { font-weight: 500; color: var(--texte); }

/* Messages d'information : gris neutre, arrondis */
[data-testid="stAlert"] > div { border-radius: 14px; background: var(--surface) !important; color: var(--texte) !important; }

/* Chat : bulles arrondies, celles de la personne en gris */
[data-testid="stChatMessage"] { background: transparent; border-radius: 18px; padding: 0.9rem 1rem; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: var(--surface); }
[data-testid="stChatInput"] { border-radius: 24px; }
[data-testid="stBottom"] > div, [data-testid="stBottomBlockContainer"] {
    background: var(--verre); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
}

/* Tableaux et blocs bordés */
[data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; }
[data-testid="stExpander"] details { border-radius: 14px; border-color: var(--ligne); }

/* Cartes des propositions */
.carte {
    background: var(--surface); border-radius: 20px; padding: 1.4rem 1.3rem 1.2rem; height: 100%;
    transition: transform 0.25s ease, box-shadow 0.25s ease;
}
.carte:hover { transform: translateY(-3px); box-shadow: 0 10px 30px var(--ombre); }
.carte.meilleure { background: var(--surface-haute); box-shadow: 0 0 0 2px var(--accent) inset; }
.carte .titre { font-size: 0.8rem; font-weight: 600; color: var(--orange); margin: 0 0 0.6rem; line-height: 1.3; }
.carte .prix { font-size: 2rem; font-weight: 700; letter-spacing: -0.03em; color: var(--texte); margin: 0; line-height: 1.1; }
.carte .prix span { display: block; font-size: 0.85rem; font-weight: 500; color: var(--texte-3); letter-spacing: 0; }
.carte .assureur { font-size: 0.95rem; font-weight: 600; color: var(--texte); margin: 1rem 0 0.15rem;
                  word-break: normal; overflow-wrap: normal; hyphens: auto; -webkit-hyphens: auto; }
.carte .produit { font-size: 0.85rem; color: var(--texte-2); margin: 0; }
.carte .ecart { font-size: 0.85rem; color: var(--texte); margin: 0.9rem 0 0; }
.carte .meilleure-ecart { color: var(--accent); font-weight: 600; }
.carte .note { font-size: 0.78rem; color: var(--texte-3); margin: 0.6rem 0 0; line-height: 1.4; }
</style>
"""


def appliquer():
    st.markdown(CSS, unsafe_allow_html=True)


def entete(surtitre, titre, titre_gris, sous_titre, note=""):
    """Grand titre centré ; tous les textes sont échappés (ils viennent des traductions)."""
    e = html.escape
    st.markdown(
        f'<div class="entete"><p class="surtitre">{e(surtitre)}</p>'
        f'<h1>{e(titre)}<br><span class="gris">{e(titre_gris)}</span></h1>'
        f'<p class="sous-titre">{e(sous_titre)}</p>'
        + (f'<p class="note">{note}</p>' if note else "") + "</div>",
        unsafe_allow_html=True)


def carte(titre, prix, unite, assureur, produit, ecart, note, meilleure=False):
    e = html.escape
    st.markdown(
        f'<div class="carte{" meilleure" if meilleure else ""}">'
        f'<p class="titre">{e(titre)}</p>'
        f'<p class="prix">{e(prix)}<span>{e(unite)}</span></p>'
        f'<p class="assureur" lang="de">{e(assureur)}</p><p class="produit">{e(produit)}</p>'
        f'<p class="ecart{" meilleure-ecart" if meilleure else ""}">{e(ecart)}</p>'
        f'<p class="note">{e(note)}</p></div>',
        unsafe_allow_html=True)
