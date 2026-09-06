import streamlit as st
import fitz  # PyMuPDF
import io
import re
import time
import base64
import google.generativeai as genai

# ==============================================================================
# CONFIGURATION DE LA PAGE & DES VOIX GEMINI TTS
# ==============================================================================
st.set_page_config(
    page_title="Gemini Studio - Traduction & Voix 100% IA",
    page_icon="✨",
    layout="wide"
)

# Inspiré des templates du Playground Google AI Studio
VOIX_GEMINI_TTS = {
    "Le Maître Conteur (The Master Storyteller)": "The Master Storyteller",
    "L'Enseignant Patient (The Patient Teacher)": "The Patient Teacher",
    "L'Assistant Quotidien (The Everyday Assistant)": "The Everyday Assistant",
    "Voix Off Premium (The Ad Voiceover)": "The Ad Voiceover"
}

# ==============================================================================
# GESTION DE LA MÉMOIRE (SESSION STATE)
# ==============================================================================
def reinitialiser_memoire():
    st.session_state.texte_pret_pour_audio = None

if "texte_pret_pour_audio" not in st.session_state:
    st.session_state.texte_pret_pour_audio = None

# ==============================================================================
# FONCTIONS DE STRUCTURE ET DE NETTOYAGE
# ==============================================================================
def extraire_texte(fichier_telecharge) -> str:
    nom_fichier = fichier_telecharge.name.lower()
    texte_extrait = ""
    if nom_fichier.endswith(".txt"):
        bytes_data = fichier_telecharge.read()
        texte_extrait = bytes_data.decode("utf-8", errors="ignore")
    elif nom_fichier.endswith(".pdf"):
        doc = fitz.open(stream=fichier_telecharge.read(), filetype="pdf")
        for page in doc:
            texte_extrait += page.get_text() + "\n\n"
    return texte_extrait.strip()

def nettoyer_texte_source(texte: str) -> str:
    texte = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', texte)
    texte = re.sub(r'(?<!\n)\n(?!\n)', ' ', texte)
    corrections = {
        "c h a p i t r e": "chapitre",
        "ber ger": "berger",
        "V oyant": "Voyant",
        "br ebis": "brebis",
        "dif ficile": "difficile"
    }
    for erreur, correction in corrections.items():
        texte = texte.replace(erreur, correction)
        texte = texte.replace(erreur.capitalize(), correction.capitalize())
    texte = re.sub(r'[ \t]+', ' ', texte)
    texte = re.sub(r'\n{3,}', '\n\n', texte)
    return texte.strip()

def nettoyer_texte_pour_audio(texte: str) -> str:
    if not texte: return ""
    texte = re.sub(r'(\d+):(\d+)', r'\1, \2', texte)
    texte = texte.replace("*", "")
    texte = re.sub(r'^#+\s*', '', texte, flags=re.MULTILINE)
    texte = re.sub(r'(?<=\s)_(?=\S)|(?<=\S)_(?=\s)', '', texte)
    texte = texte.replace("_", "")
    texte = re.sub(r'^\s*I\s*\n+', '', texte)
    texte = re.sub(r'\s*[—–]\s*', ', ', texte)
    texte = re.sub(r'^\s*[—–]\s*', '', texte, flags=re.MULTILINE)
    texte = texte.replace("«", '"').replace("»", '"').replace("“", '"').replace("”", '"')
    texte = re.sub(r'[ \t]+', ' ', texte)            
    texte = re.sub(r' +(?=\n)', '', texte)           
    texte = re.sub(r'\n\s*\n', '\n\n', texte)       
    texte = re.sub(r'\n{3,}', '\n\n', texte)         
    return texte.strip()

def decouper_texte_en_chunks(texte: str, taille_chunk: int) -> list:
    if not texte: return []
    paragraphes = texte.split("\n\n")
    chunks = []
    chunk_actuel = ""
    for paragraphe in paragraphes:
        paragraphe_propre = paragraphe.strip()
        if not paragraphe_propre: continue
        if len(chunk_actuel) + len(paragraphe_propre) + 2 > taille_chunk and len(chunk_actuel) > 0:
            chunks.append(chunk_actuel.strip())
            chunk_actuel = paragraphe_propre + "\n\n"
        else:
            chunk_actuel += paragraphe_propre + "\n\n"
    if chunk_actuel.strip():
        chunks.append(chunk_actuel.strip())
    return chunks

def assainir_cle(cle_brute: str) -> str:
    return cle_brute.replace(r'\_', '_').replace('\\', '').strip().strip('"').strip("'")

# ==============================================================================
# MOTEURS GOOGLE GEMINI (TEXTE & AUDIO)
# ==============================================================================
def traduire_chunk_gemini(chunk: str, api_key: str) -> str:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.8-flash')
    prompt = (
        "Tu es un traducteur littéraire professionnel et un éditeur méticuleux. "
        "Traduis le texte suivant de l'anglais vers un français fluide, élégant et naturel.\n\n"
        "CONSIGNES CRITIQUES DE NETTOYAGE ET DE FORMATAGE :\n"
        "- SUPPRIME INTÉGRALEMENT toutes les notes de bas de page. Ne les traduis surtout pas.\n"
        "- IGNORE ET SUPPRIME tous les appels de notes (les petits numéros isolés dans le texte).\n"
        "- Conserve STRICTEMENT la disposition aérée et les sauts de paragraphes d'origine.\n"
        "- Chaque paragraphe et chaque titre de section doit être séparé par un double saut de ligne (\\n\\n).\n"
        "- N'utilise AUCUN balisage Markdown : AUCUN astérisque (* ou **), AUCUN dièse (#), AUCUN souligné (_).\n"
        "- Ne rajoute aucune introduction, conclusion ou commentaire personnel.\n\n"
        f"Texte à traduire :\n{chunk}"
    )
    response = model.generate_content(prompt, generation_config={"temperature": 0.2})
    return response.text.strip()

def generer_audio_gemini_tts(chunk_texte: str, persona: str, api_key: str) -> bytes:
    """Utilisation du modèle expérimental TTS Preview pour générer la narration sans filtre MIME strict."""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.1-flash-tts-preview')
    
    prompt_narratif = f"Génère la narration vocale de ce texte en adoptant le style '{persona}' :\n\n{chunk_texte}"
    
    # On retire le paramètre 'response_mime_type' pour ne pas bloquer le SDK Python
    response = model.generate_content(prompt_narratif)
    
    try:
        # Cas 1 : L'audio est encapsulé sous forme de données binaires inline
        if response.parts and hasattr(response.parts[0], 'inline_data') and response.parts[0].inline_data:
            return response.parts[0].inline_data.data
        # Cas 2 : L'API retourne l'audio encodé en Base64 dans le texte
        else:
            texte_retour = response.text.strip()
            # Nettoyage si le modèle renvoie du texte autour du code Base64
            if "```" in texte_retour:
                texte_retour = texte_retour.split("```")[1].replace("json", "").replace("base64", "").strip()
            return base64.b64decode(texte_retour)
    except Exception as e:
        raise ValueError(f"Extraction audio impossible. Détails: {str(e)} | Extrait réponse: {str(response)[:200]}")

# ==============================================================================
# INTERFACE PRINCIPALE
# ==============================================================================
def main():
    st.title("✨ Gemini Studio : Traduction & Narration 100% IA")
    st.markdown("Pipeline Expérimental : Extraction PyMuPDF ➡️ Traduction Gemini 3.8 Flash ➡️ Voix Gemini 3.1 Flash TTS.")
    st.divider()

    cles_brutes = st.secrets.get("GOOGLE_API_KEYS", None)
    if cles_brutes is None:
        cle_solo = st.secrets.get("GOOGLE_API_KEY", "")
        pool_initial = [cle_solo] if cle_solo else []
    else:
        pool_initial = list(cles_brutes)

    pool_cles = [assainir_cle(k) for k in pool_initial if assainir_cle(k)]

    with st.sidebar:
        st.header("1. Type de Document")
        mode_choisi = st.radio(
            "Langue d'origine du fichier :",
            ["🇫🇷 Document en Français", "🇬🇧 Document en Anglais"],
            on_change=reinitialiser_memoire
        )

        st.header("2. Configuration")
        st.caption(f"🔑 **{len(pool_cles)} clé(s) active(s)** dans le pool global.")
        cle_manuelle = st.text_input("Remplacer temporairement par une clé :", type="password")
        if cle_manuelle.strip():
            pool_cles = [assainir_cle(cle_manuelle)]

        choix_nom_voix = st.selectbox("Style de Narration (Gemini TTS) :", options=list(VOIX_GEMINI_TTS.keys()))
        voix_technique = VOIX_GEMINI_TTS[choix_nom_voix]

        if st.button("🔄 Réinitialiser l'application", use_container_width=True):
            reinitialiser_memoire()
            st.rerun()

    st.subheader(f"Étape 1 : Charger votre fichier ({mode_choisi.split(' ')[2]})")
    fichier_upload = st.file_uploader("Fichier .txt ou .pdf", type=["txt", "pdf"])

    if fichier_upload is not None:
        texte_brut = extraire_texte(fichier_upload)
        texte_propre = nettoyer_texte_source(texte_brut)

        if not texte_propre:
            st.error("❌ Le document semble vide ou illisible.")
            return

        st.success(f"✅ Extraction réussie ! ({len(texte_propre)} caractères détectés)")

        # ======================================================================
        # BRANCHE A : TRADUCTION (POOL DE CLÉS)
        # ======================================================================
        if mode_choisi == "🇬🇧 Document en Anglais" and st.session_state.texte_pret_pour_audio is None:
            st.subheader("Étape 2 : Traduction en Français")
            if st.button("🚀 Lancer la Traduction IA", type="primary"):
                if not pool_cles:
                    st.error("🚨 Aucune clé API Google valide trouvée.")
                    return

                chunks_anglais = decouper_texte_en_chunks(texte_propre, taille_chunk=8000)
                chunks_traduits = []
                barre_progression = st.progress(0, text="Initialisation de Gemini 3.8 Flash...")
                index_cle, i = 0, 0

                while i < len(chunks_anglais):
                    pct = int(((i + 1) / len(chunks_anglais)) * 100)
                    barre_progression.progress(pct, text=f"Traduction {i + 1}/{len(chunks_anglais)} (Clé #{index_cle + 1})...")
                    
                    try:
                        traduction_brute = traduire_chunk_gemini(chunks_anglais[i], pool_cles[index_cle])
                        chunks_traduits.append(nettoyer_texte_pour_audio(traduction_brute))
                        i += 1
                        time.sleep(1)
                    except Exception as e:
                        erreur_str = str(e).lower()
                        if "429" in erreur_str or "quota" in erreur_str:
                            diagnostic = "Quota atteint (429)"
                        elif "401" in erreur_str or "403" in erreur_str:
                            diagnostic = "Clé invalide/révoquée (401/403)"
                        else:
                            diagnostic = f"Erreur de service : {str(e)}"

                        if index_cle + 1 < len(pool_cles):
                            st.warning(f"⚠️ Traduction : Bascule sur la Clé #{index_cle + 2} ({diagnostic})...")
                            index_cle += 1
                            time.sleep(1.5)
                        else:
                            if chunks_traduits:
                                st.session_state.texte_pret_pour_audio = "\n\n".join(chunks_traduits)
                            st.error("🚨 Traduction arrêtée : Toutes les clés ont été consommées.")
                            st.rerun()

                st.session_state.texte_pret_pour_audio = "\n\n".join(chunks_traduits)
                st.rerun()

        elif mode_choisi == "🇫🇷 Document en Français":
            st.session_state.texte_pret_pour_audio = nettoyer_texte_pour_audio(texte_propre)

        # ======================================================================
        # ÉTAPE FINALE : NARRATION VOCALE GEMINI TTS (POOL DE CLÉS)
        # ======================================================================
        if st.session_state.texte_pret_pour_audio is not None:
            st.divider()
            st.subheader("Étape Finale : Studio d'Enregistrement IA 🎙️")
            
            with st.expander("📖 Afficher le texte intégral à enregistrer", expanded=True):
                st.text_area("Texte Final", value=st.session_state.texte_pret_pour_audio, height=250)

            nom_base = fichier_upload.name.rsplit('.', 1)[0]
            st.download_button(
                label="📄 Télécharger le texte (.txt)",
                data=st.session_state.texte_pret_pour_audio,
                file_name=f"Texte_FR_{nom_base}.txt",
                mime="text/plain"
            )

            if st.button("🎙️ Générer l'Audio avec Gemini TTS", type="primary"):
                if not pool_cles:
                    st.error("🚨 Aucune clé API Google valide trouvée pour le TTS.")
                    return

                texte_final_audio = nettoyer_texte_pour_audio(st.session_state.texte_pret_pour_audio)
                chunks_pour_audio = decouper_texte_en_chunks(texte_final_audio, taille_chunk=3000) 
                
                audio_bytes_total = b""
                barre_progression_audio = st.progress(0, text="Chauffage du micro de Gemini 3.1 Flash TTS...")
                
                index_cle_audio, j = 0, 0

                while j < len(chunks_pour_audio):
                    pct_audio = int(((j + 1) / len(chunks_pour_audio)) * 100)
                    barre_progression_audio.progress(pct_audio, text=f"Génération vocale {j + 1}/{len(chunks_pour_audio)} (Clé #{index_cle_audio + 1})...")
                    
                    try:
                        audio_part = generer_audio_gemini_tts(chunks_pour_audio[j], voix_technique, pool_cles[index_cle_audio])
                        audio_bytes_total += audio_part
                        j += 1
                        time.sleep(1.5)
                        
                    except Exception as e_audio:
                        erreur_brute = str(e_audio)
                        erreur_str = erreur_brute.lower()
                        
                        if "429" in erreur_str or "quota" in erreur_str:
                            diagnostic = "Quota atteint (429)"
                        elif "401" in erreur_str or "403" in erreur_str:
                            diagnostic = "Clé invalide/révoquée (401/403)"
                        else:
                            diagnostic = f"Erreur technique : {erreur_brute}"

                        if index_cle_audio + 1 < len(pool_cles):
                            st.warning(f"⚠️ Audio : Bascule sur la Clé #{index_cle_audio + 2} ({diagnostic})...")
                            index_cle_audio += 1
                            time.sleep(2)
                        else:
                            st.error(f"🚨 Enregistrement arrêté. Dernière erreur : {diagnostic}")
                            break

                if audio_bytes_total:
                    st.success("🎉 Piste vocale Gemini assemblée avec succès !")
                    st.audio(audio_bytes_total, format="audio/mp3")
                    st.download_button(
                        label="⬇️ Télécharger le MP3 Narratif",
                        data=audio_bytes_total,
                        file_name=f"Gemini_TTS_{nom_base}.mp3",
                        mime="audio/mp3",
                        type="primary"
                    )

if __name__ == "__main__":
    main()
