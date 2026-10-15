"""Apparence de l'app : sobre, beaucoup d'espace, police système, un seul bleu d'accent.

Les couleurs de base sont dans .streamlit/config.toml ([theme]) ; ce fichier ajoute le reste
(arrondis, boutons en pilule, onglets, bulles de chat), en mode clair et en mode sombre.
Sélecteurs vérifiés avec Streamlit 1.65.0.
"""
import html
import re

import streamlit as st

CSS = """
<style>
/* Couleurs : une variable par rôle, en clair et en sombre. light-dark() suit le thème choisi dans
   Streamlit (menu ⋮ > Settings, ou le réglage du système) : Streamlit pose color-scheme sur .stApp. */
.stApp, [data-testid="stDialog"], div[role="dialog"] {
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
html, body, .stApp, .stApp *:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded),
div[role="dialog"] *:not([data-testid="stIconMaterial"]):not(.material-symbols-rounded) {
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
.carte .aussi { font-size: 0.75rem; color: var(--texte-3); margin: -0.4rem 0 0.6rem; line-height: 1.3; }
.carte .titre { font-size: 0.8rem; font-weight: 600; color: var(--orange); margin: 0 0 0.6rem; line-height: 1.3; }
.carte .prix { font-size: 2rem; font-weight: 700; letter-spacing: -0.03em; color: var(--texte); margin: 0; line-height: 1.1; }
.carte .prix span { display: block; font-size: 0.85rem; font-weight: 500; color: var(--texte-3); letter-spacing: 0; }
.carte .assureur { font-size: 0.95rem; font-weight: 600; color: var(--texte); margin: 1rem 0 0.15rem;
                  word-break: normal; overflow-wrap: normal; hyphens: auto; -webkit-hyphens: auto; }
.carte .produit { font-size: 0.85rem; color: var(--texte-2); margin: 0; }
.carte .ecart { font-size: 0.85rem; color: var(--texte); margin: 0.9rem 0 0; }
.carte .meilleure-ecart { color: var(--accent); font-weight: 600; }
.carte .note { font-size: 0.78rem; color: var(--texte-3); margin: 0.6rem 0 0; line-height: 1.4; }
/* Carte d'ouverture après le formulaire : le conseiller reprend les réponses, puis Apertus parle */
.st-key-ouverture {
    position: relative; overflow: hidden; background: var(--surface); border: 1px solid var(--filet);
    border-radius: 24px; padding: 1.4rem 1.5rem 1.2rem; margin: 0.5rem 0 1rem;
    box-shadow: 0 24px 48px -32px var(--ombre);
}
.st-key-ouverture::before {
    content: ""; position: absolute; inset: 0 0 auto 0; height: 3px;
    background: linear-gradient(90deg, var(--accent), #5e5ce6, var(--orange));
}
.conseiller-tete { display: flex; align-items: center; gap: 0.8rem; margin-bottom: 1rem; }
.conseiller-avatar {
    flex: none; width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center;
    background: linear-gradient(135deg, var(--accent), #5e5ce6); color: #ffffff; font-weight: 700;
    font-size: 1.2rem; box-shadow: 0 4px 14px rgba(41, 151, 255, 0.35);
}
.conseiller-nom { margin: 0; font-weight: 600; font-size: 1rem; line-height: 1.25; color: var(--texte); }
.conseiller-statut { margin: 0.1rem 0 0; display: flex; align-items: center; gap: 0.45rem;
                     font-size: 0.8rem; color: var(--texte-3); }
.conseiller-statut .point { width: 8px; height: 8px; border-radius: 50%; background: #30d158;
                            animation: pouls 2.2s ease-out infinite; }
@keyframes pouls {
    0% { box-shadow: 0 0 0 0 rgba(48, 209, 88, 0.55); }
    70%, 100% { box-shadow: 0 0 0 8px rgba(48, 209, 88, 0); }
}
.recap-titre { margin: 0 0 0.45rem; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.02em;
               text-transform: uppercase; color: var(--texte-3); }
.recap { display: flex; flex-wrap: wrap; gap: 0.45rem; margin: 0 0 1rem; }
.recap span {
    display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.3rem 0.75rem; border-radius: 980px;
    background: var(--fond); border: 1px solid var(--bord); font-size: 0.86rem; color: var(--texte);
    opacity: 0; animation: apparait 0.35s ease forwards;
}
.recap span:nth-child(2) { animation-delay: 0.08s; } .recap span:nth-child(3) { animation-delay: 0.16s; }
.recap span:nth-child(4) { animation-delay: 0.24s; } .recap span:nth-child(5) { animation-delay: 0.32s; }
.conseiller-bulle {
    position: relative; margin: 0 0 1rem; padding: 0.9rem 1.05rem; min-height: 3rem;
    background: var(--fond); border-radius: 6px 18px 18px 18px; color: var(--texte);
    font-size: 1rem; line-height: 1.6;
}
/* Apertus « écrit » un instant, puis son message apparaît (une seule fois) */
.conseiller-bulle .points { position: absolute; top: 1.15rem; left: 1.05rem; display: flex; gap: 5px;
                            animation: efface 0.2s ease 1.1s forwards; }
.conseiller-bulle .points span { width: 7px; height: 7px; border-radius: 50%; background: var(--texte-3);
                                 animation: saut 1s ease-in-out infinite; }
.conseiller-bulle .points span:nth-child(2) { animation-delay: 0.15s; }
.conseiller-bulle .points span:nth-child(3) { animation-delay: 0.3s; }
.conseiller-bulle .message { opacity: 0; animation: apparait 0.5s ease 1.2s forwards; }
@keyframes saut { 0%, 60%, 100% { transform: translateY(0); opacity: 0.5; } 30% { transform: translateY(-4px); opacity: 1; } }
@keyframes efface { to { opacity: 0; visibility: hidden; } }
@keyframes apparait { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
    .conseiller-bulle .points { display: none; }
    .conseiller-bulle .message, .recap span { opacity: 1; animation: none; }
}
.st-key-suggestions .stButton > button {
    padding: 0.38rem 0.95rem; font-size: 0.86rem; font-weight: 400; text-align: left;
    background: var(--fond); color: var(--texte-2); border-color: var(--bord);
}
.st-key-suggestions .stButton > button:hover { color: var(--accent); border-color: var(--accent); background: var(--accent-doux); }
/* « Check-out » après le choix d'une offre */
[class*="st-key-checkout_"] {
    background: var(--surface); border: 1px solid var(--filet); border-radius: 24px;
    padding: 1.3rem 1.4rem 1.1rem; box-shadow: 0 24px 48px -32px var(--ombre);
}
.choix { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 0.6rem; }
.choix .titre { margin: 0 0 0.3rem; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.02em;
                text-transform: uppercase; color: var(--orange); }
.choix .caisse { margin: 0; font-size: 1.25rem; font-weight: 700; letter-spacing: -0.02em; color: var(--texte); }
.choix .produit { margin: 0.1rem 0 0.6rem; font-size: 0.9rem; color: var(--texte-2); }
.choix .prix { margin: 0; font-size: 1.8rem; font-weight: 700; letter-spacing: -0.03em; color: var(--texte);
               text-align: right; line-height: 1.1; white-space: nowrap; }
.choix .prix span { display: block; font-size: 0.8rem; font-weight: 500; color: var(--texte-3); letter-spacing: 0; }
.choix .etiquettes { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.choix .etiquettes span { padding: 0.22rem 0.7rem; border-radius: 980px; background: var(--fond);
                          border: 1px solid var(--bord); font-size: 0.82rem; color: var(--texte); }
[class*="st-key-checkout_"] .stLinkButton a { border-radius: 980px; font-weight: 600; }
/* Les liens sont bleus (.stApp a), sauf le texte des boutons-liens pleins, en blanc sur le bleu */
.stApp a[data-testid="stBaseLinkButton-primary"], .stApp a[data-testid="stBaseLinkButton-primary"] * {
    color: #ffffff !important;
}
.stApp a[data-testid="stBaseLinkButton-primary"] { background: var(--accent) !important; border-color: var(--accent) !important; }
.stApp a[data-testid="stBaseLinkButton-primary"]:hover { background: var(--accent-survol) !important; }
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


def carte(titre, prix, unite, assureur, produit, ecart, note, meilleure=False, aussi=""):
    e = html.escape
    st.markdown(
        f'<div class="carte{" meilleure" if meilleure else ""}">'
        f'<p class="titre">{e(titre)}</p>'
        + (f'<p class="aussi">{e(aussi)}</p>' if aussi else "")
        + f'<p class="prix">{e(prix)}<span>{e(unite)}</span></p>'
        f'<p class="assureur" lang="de">{e(assureur)}</p><p class="produit">{e(produit)}</p>'
        f'<p class="ecart{" meilleure-ecart" if meilleure else ""}">{e(ecart)}</p>'
        f'<p class="note">{e(note)}</p></div>',
        unsafe_allow_html=True)


def ouverture(nom, statut, titre_recap, etiquettes, message):
    """Haut de la carte d'ouverture : avatar et statut, réponses du formulaire en étiquettes, puis le message
    d'Apertus (Markdown simple : gras et italique gardés, tout le reste échappé)."""
    e = html.escape
    recap = "".join(f"<span>{e(icone)} {e(texte)}</span>" for icone, texte in etiquettes)
    corps = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", e(message))
    corps = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", corps).replace("\n", "<br>")
    st.markdown(
        f'<div class="conseiller-tete"><div class="conseiller-avatar">A</div><div>'
        f'<p class="conseiller-nom">{e(nom)}</p>'
        f'<p class="conseiller-statut"><span class="point"></span>{e(statut)}</p></div></div>'
        f'<p class="recap-titre">{e(titre_recap)}</p><div class="recap">{recap}</div>'
        f'<div class="conseiller-bulle"><div class="points"><span></span><span></span><span></span></div>'
        f'<div class="message">{corps}</div></div>',
        unsafe_allow_html=True)


def recapitulatif_choix(titre, caisse, produit, etiquettes, prix, unite):
    """En-tête du « check-out » : l'offre choisie (textes échappés)."""
    e = html.escape
    st.markdown(
        f'<div class="choix"><div><p class="titre">{e(titre)}</p><p class="caisse">{e(caisse)}</p>'
        f'<p class="produit">{e(produit)}</p><div class="etiquettes">'
        + "".join(f"<span>{e(x)}</span>" for x in etiquettes)
        + f'</div></div><p class="prix">{e(prix)}<span>{e(unite)}</span></p></div>',
        unsafe_allow_html=True)
