"""Apparence de l'app : sobre, beaucoup d'espace, police système, un seul bleu d'accent.

Les couleurs de base sont dans .streamlit/config.toml ([theme]) ; ce fichier ajoute le reste
(arrondis, boutons en pilule, onglets, bulles de chat). Sélecteurs vérifiés avec Streamlit 1.40.1.
"""
import html

import streamlit as st

CSS = """
<style>
html, body, .stApp, .stApp *:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded) {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Helvetica Neue",
                 Helvetica, Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
}
.stApp { background: #ffffff; color: #1d1d1f; }
.block-container { max-width: 800px; padding-top: 3.5rem; padding-bottom: 6rem; }

/* Barre du haut translucide, menu « Deploy » masqué */
header[data-testid="stHeader"] {
    background: rgba(255, 255, 255, 0.72);
    backdrop-filter: saturate(180%) blur(20px); -webkit-backdrop-filter: saturate(180%) blur(20px);
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}
[data-testid="stAppDeployButton"], [data-testid="stDeployButton"] { display: none; }

/* Titres */
h1, h2, h3, h4 { color: #1d1d1f; font-weight: 600 !important; letter-spacing: -0.02em; }
h2 { font-size: 1.9rem !important; padding-top: 1.5rem !important; }
h3 { font-size: 1.4rem !important; }
[data-testid="stCaptionContainer"], .stCaption { color: #86868b !important; }
hr { border-color: #e8e8ed !important; }

/* En-tête centré */
.entete { text-align: center; padding: 1rem 0 2.2rem; }
.entete .surtitre { color: #bf4800; font-size: 0.95rem; font-weight: 600; margin: 0 0 0.5rem; }
.entete h1 {
    font-size: clamp(2.3rem, 6vw, 3.5rem); line-height: 1.07; font-weight: 700 !important;
    letter-spacing: -0.035em; margin: 0; padding: 0;
}
.entete h1 span { color: #86868b; }
.entete .sous-titre {
    font-size: 1.2rem; line-height: 1.45; color: #6e6e73; max-width: 34rem; margin: 1.1rem auto 0;
}
.entete .note { font-size: 0.85rem; color: #86868b; margin-top: 1.4rem; }
.entete .note b { color: #1d1d1f; font-weight: 600; }

/* Barre latérale */
section[data-testid="stSidebar"] { background: #f5f5f7; border-right: 1px solid rgba(0, 0, 0, 0.06); }

/* Boutons en pilule */
.stButton > button {
    border-radius: 980px; padding: 0.55rem 1.35rem; font-weight: 500; font-size: 0.98rem;
    border: 1px solid #d2d2d7; background: #ffffff; color: #0071e3; box-shadow: none;
    transition: background 0.2s ease, border-color 0.2s ease, transform 0.1s ease;
}
.stButton > button:hover { border-color: #0071e3; color: #0071e3; background: #f5f9ff; }
.stButton > button:active { transform: scale(0.98); }
.stButton > button[kind="primary"] { background: #0071e3; color: #ffffff; border: 1px solid #0071e3; }
.stButton > button[kind="primary"]:hover { background: #0077ed; border-color: #0077ed; color: #ffffff; }
.stButton > button:disabled { opacity: 0.35; }

/* Champs du formulaire : gris clair, arrondis, sans bordure */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {
    border-radius: 12px !important; background: #f5f5f7 !important; border-color: transparent !important;
}
[data-baseweb="input"] input, [data-baseweb="select"] input { background: transparent !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within {
    border-color: #0071e3 !important; box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.18) !important;
}
[data-baseweb="tag"] { border-radius: 980px !important; background: #e8f1fc !important; }
[data-baseweb="tag"] span { color: #0071e3 !important; }
[data-testid="stWidgetLabel"] p { font-weight: 500; color: #1d1d1f; }

/* Messages d'information : gris neutre, arrondis */
[data-testid="stAlert"] > div { border-radius: 14px; background: #f5f5f7 !important; color: #1d1d1f !important; }

/* Onglets façon contrôle segmenté */
[data-baseweb="tab-list"] { background: #f5f5f7; border-radius: 12px; padding: 4px; gap: 4px; }
[data-baseweb="tab"] { border-radius: 9px; padding: 0.4rem 1rem !important; height: auto !important; }
[data-baseweb="tab"][aria-selected="true"] { background: #ffffff; box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12); }
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none; }

/* Chat : bulles arrondies, celles de la personne en gris */
[data-testid="stChatMessage"] { background: transparent; border-radius: 18px; padding: 0.9rem 1rem; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { background: #f5f5f7; }
[data-testid="stChatInput"] { border-radius: 24px; }
[data-testid="stBottomBlockContainer"] { background: rgba(255, 255, 255, 0.85); backdrop-filter: blur(20px); }

/* Tableaux et blocs bordés */
[data-testid="stDataFrame"], [data-testid="stTable"] { border-radius: 14px; overflow: hidden; }
[data-testid="stExpander"] details { border-radius: 14px; border-color: #e8e8ed; }

/* Cartes des propositions */
.carte {
    background: #f5f5f7; border-radius: 20px; padding: 1.4rem 1.3rem 1.2rem; height: 100%;
    transition: transform 0.25s ease, box-shadow 0.25s ease;
}
.carte:hover { transform: translateY(-3px); box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08); }
.carte.meilleure { background: #ffffff; box-shadow: 0 0 0 2px #0071e3 inset; }
.carte .titre { font-size: 0.8rem; font-weight: 600; color: #bf4800; margin: 0 0 0.6rem; line-height: 1.3; }
.carte .prix { font-size: 2rem; font-weight: 700; letter-spacing: -0.03em; color: #1d1d1f; margin: 0; line-height: 1.1; }
.carte .prix span { display: block; font-size: 0.85rem; font-weight: 500; color: #86868b; letter-spacing: 0; }
.carte .assureur { font-size: 0.95rem; font-weight: 600; color: #1d1d1f; margin: 1rem 0 0.15rem;
                  word-break: normal; overflow-wrap: normal; hyphens: auto; -webkit-hyphens: auto; }
.carte .produit { font-size: 0.85rem; color: #6e6e73; margin: 0; }
.carte .ecart { font-size: 0.85rem; color: #1d1d1f; margin: 0.9rem 0 0; }
.carte .meilleure-ecart { color: #0071e3; font-weight: 600; }
.carte .note { font-size: 0.78rem; color: #86868b; margin: 0.6rem 0 0; line-height: 1.4; }
</style>
"""


def appliquer():
    st.markdown(CSS, unsafe_allow_html=True)


def entete(surtitre, titre, titre_gris, sous_titre, note=""):
    """Grand titre centré ; tous les textes sont échappés (ils viennent des traductions)."""
    e = html.escape
    st.markdown(
        f'<div class="entete"><p class="surtitre">{e(surtitre)}</p>'
        f'<h1>{e(titre)}<br><span>{e(titre_gris)}</span></h1>'
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
