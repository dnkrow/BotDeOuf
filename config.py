# config.py

# --- Token Discord ---
TOKEN = "MTM3MjU2MzU4MjU0MTM2OTM3NA.GMTyDM.RSYDlaxGp-RrscgSLn-0q5qP-U5PFUlhXD86kE"  # REMPLACE CECI PAR TON VRAI TOKEN !

# --- Configuration LM Studio ---
LM_STUDIO_API_URL = "http://127.0.0.1:1234/v1/chat/completions"
LM_STUDIO_MODEL_NAME = "mistral-7b-instruct-v0.3.Q5_K_M.gguf"  # VÉRIFIE LE NOM EXACT DE TON MODÈLE

# --- Chemins et Dossiers ---
DOWNLOAD_PATH = 'audio_cache' # Dossier pour les fichiers audio temporaires

# --- Constantes pour la Détection d'Activité Vocale (VAD) ---
VAD_SAMPLE_RATE = 48000         # Taux d'échantillonnage (Discord utilise 48kHz)
VAD_FRAME_DURATION_MS = 20      # Durée des paquets audio de Discord (20ms)
# Mode de sensibilité du VAD pour webrtcvad (0=moins agressif, 3=plus agressif pour détecter non-parole)
VAD_AGGRESSIVENESS = 1
# Durée de silence (en secondes) après laquelle on considère que l'utilisateur a fini de parler
VAD_SILENCE_TIMEOUT_SECONDS = 2.0
# Durée maximale d'enregistrement pour la commande !ecoute VAD (sécurité)
VAD_MAX_RECORDING_SECONDS = 15.0 # Augmenté par rapport aux 10s de l'enregistrement fixe simple

# --- Constantes pour l'enregistrement fixe (utilisé si VAD sur fichier est l'étape suivante) ---
# Cette constante est pour la version de !ecoute où on enregistre X secondes puis on traite le fichier
# Si on fait du VAD en temps réel avec vc.listen, cette durée n'est pas utilisée de la même manière.
# Pour l'instant, on garde la logique d'enregistrement fixe + VAD sur fichier.
FIXED_RECORDING_DURATION_SECONDS = 12.0 # Durée de l'enregistrement initial avant VAD sur fichier