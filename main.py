# main.py

import discord
from discord.sinks import WaveSink
import asyncio
import os
import re
from datetime import datetime

import config
import speech_handler
import music_handler
import llm_handler
import web_utils
import screen_analyzer

# --- Configuration et Initialisation du Client Discord ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
client = discord.Client(intents=intents)

# --- Variables d'État Globales (gérées par main.py) ---
audio_queue = asyncio.Queue()
bot_loop = None
conversation_history = {}
whisper_model = None
vad_instance = None


# --- Fonctions Utilitaires Globales ---
async def dummy_finished_recording_callback(sink, *args):
    pass


# --- Événements Discord ---

@client.event
async def on_ready():
    global bot_loop, whisper_model, vad_instance, config
    bot_loop = asyncio.get_event_loop()

    print(f'✅ Bot connecté: {client.user.name} ({client.user.id})')
    if not os.path.exists(config.DOWNLOAD_PATH):
        try:
            os.makedirs(config.DOWNLOAD_PATH)
            print(f"Dossier '{config.DOWNLOAD_PATH}' créé.")
        except OSError as e:
            print(f"ERREUR: Création dossier '{config.DOWNLOAD_PATH}' échouée: {e}");
            exit()
    print('------')

    try:
        import whisper
        print("Chargement Whisper 'small'...")
        whisper_model = whisper.load_model("small")
        device = next(whisper_model.parameters()).device
        print(f"✅ Whisper 'small' chargé sur: {device}")
        if device.type == 'cuda':
            import torch
            print(f"   GPU: {torch.cuda.get_device_name(0)}")
    except Exception as e_wspr_load:
        print(f"⚠️ ERREUR WHISPER: {e_wspr_load}\n   !ecoute peut échouer.");
        whisper_model = None

    try:
        import webrtcvad
        vad_instance = webrtcvad.Vad(config.VAD_AGGRESSIVENESS)
        print(f"✅ VAD initialisé (agressivité: {config.VAD_AGGRESSIVENESS}).")
    except Exception as e_vad_load:
        print(f"⚠️ ERREUR VAD: {e_vad_load}\n   VAD pour !ecoute peut échouer.");
        vad_instance = None


@client.event
async def on_message(message: discord.Message):
    global conversation_history, audio_queue, bot_loop
    global whisper_model, vad_instance

    if message.author == client.user: return

    vc = message.guild.voice_client if message.guild else None

    if message.content.startswith('!hello'):
        await message.channel.send(f'Salut {message.author.mention} ! 👋')

    elif message.content.startswith('!join'):
        if not message.author.voice or not message.author.voice.channel:
            await message.channel.send("Tu dois être dans un salon vocal.");
            return

        target_channel = message.author.voice.channel
        action_message = ""
        connection_successful = False

        if vc and vc.is_connected():
            if vc.channel == target_channel:
                action_message = f"Je suis déjà dans {target_channel.name}."
                connection_successful = True
            else:
                try:
                    await vc.move_to(target_channel)
                    action_message = f"🔊 Déplacé vers {target_channel.name}."
                    connection_successful = True
                except Exception as e_move_vc:
                    action_message = f"⚠️ Erreur déplacement: {e_move_vc}"
        else:
            try:
                new_vc = await target_channel.connect()
                vc = new_vc
                action_message = f"🔊 Connecté à {target_channel.name}."
                connection_successful = True
            except Exception as e_join_vc:
                action_message = f"⚠️ Erreur connexion: {e_join_vc}"

        if action_message: await message.channel.send(action_message)
        if connection_successful:
            await message.channel.send("Tapez `!commande` pour voir la liste de mes fonctionnalités !")

    elif message.content.startswith('!leave'):
        if vc and vc.is_connected():
            await vc.disconnect(); await message.channel.send("👋 Déconnecté.")
        else:
            await message.channel.send("Pas en vocal.")

    elif message.content.startswith('!commande') or message.content.startswith(
            '!commandes') or message.content.startswith('!aide'):
        commands_list_text = """Salut ! Voici la liste de mes super pouvoirs :--- Général ---
!hello         : Juste pour un petit coucou !
!join          : Je te rejoins dans ton salon vocal.
!leave         : Je quitte le salon vocal.
!commande      : Affiche cette liste d'aide.

--- 🎵 Musique ---
!playyt &lt;URL>  : Joue une musique/playlist YouTube.
!playlocal &lt;fichier> : Joue un fichier audio (doit être dans audio_cache).
!next          : Musique suivante.
!stop          : Arrête la musique et vide la file.
!queue         : Affiche la file d'attente.

--- 🗣️ Vocal & IA 🧠 ---
!ecoute        : J'enregistre ta voix (durée fixe), la nettoie (VAD),
la transcris, puis tu peux interroger Mistral.
(Dis "Mistral..." ou "Ok Bot..." au début de ta phrase orale).
!screen        : Je prends une capture de ton écran. Dis-moi ensuite
ce que tu veux analyser/corriger avec Mistral & recherche web.
!mistral &lt;...> : Pose une question directement à Mistral.
!askweb &lt;...>  : Question à Mistral avec recherche web préalable.
!clean         : Efface ton historique de conversation avec Mistral."""



        try: await message.channel.send(commands_list_text)
        except discord.errors.HTTPException: await message.channel.send("La liste de mes commandes est un peu longue pour s'afficher en une fois !")

    elif message.content.startswith('!playyt'):
        await music_handler.handle_playyt_command(message, vc, audio_queue, bot_loop, config)
    elif message.content.startswith('!playlocal'):
        await music_handler.handle_playlocal_command(message, vc, audio_queue, bot_loop, config)
    elif message.content.startswith('!next'):
        await music_handler.handle_next_command(message, vc, audio_queue, bot_loop, config)
    elif message.content.startswith('!stop'):
        await music_handler.handle_stop_command(message, vc, audio_queue)
    elif message.content.startswith('!queue'):
        await music_handler.handle_queue_command(message, audio_queue)

    elif message.content.startswith('!screen'):
        print(f"DEBUG: Commande !screen entrée. ID: {message.id}, Contenu: '{message.content}'")
        await message.channel.send("📸 Capture écran & OCR, instant...")
        extracted_text_screen = None
        try:
            extracted_text_screen = await asyncio.to_thread(screen_analyzer.capture_and_ocr_primary_screen, 'fra+eng')
        except Exception as e_scr_ocr:
            await message.channel.send(f"⚠️ Erreur capture/OCR: {e_scr_ocr}"); return
        if not extracted_text_screen:
            await message.channel.send("Aucun texte extrait. Opération annulée."); return
        preview = extracted_text_screen[:500] + ("..." if len(extracted_text_screen) > 500 else "")
        await message.channel.send(f"Texte de l'écran ({len(extracted_text_screen)} chars):\n```\n{preview}\n```")
        await message.channel.send("Que veux-tu faire avec ce texte ? (Ex: 'Corrige ce code', 'Explique cette erreur')\nRéponds en 60s.")
        def check_auth_chan(m): return m.author == message.author and m.channel == message.channel
        try:
            user_prompt_msg = await client.wait_for('message', check=check_auth_chan, timeout=60.0)
            user_prompt = user_prompt_msg.content.strip()
            if not user_prompt: await message.channel.send("Instruction vide. Annulé."); return
            await message.channel.send(f"Reçu ! Analyse pour: \"{user_prompt}\"")
            await llm_handler.handle_screen_analysis_with_llm(
                message, vc, extracted_text_screen, user_prompt, config,
                web_utils.perform_sync_ddg_search,
                speech_handler.speak_text, speech_handler.clean_text_for_speech
            )
        except asyncio.TimeoutError: await message.channel.send("Temps écoulé pour `!screen`. Relance si besoin.")
        except Exception as e_scr_followup: await message.channel.send(f"⚠️ Erreur `!screen`: {e_scr_followup}")

    elif message.content.startswith('!ecoute'):
        if not whisper_model: await message.channel.send("⚠️ Whisper non chargé."); return
        if not vc or not vc.is_connected(): await message.channel.send("Pas en vocal. `!join`."); return
        if not message.author.voice or message.author.voice.channel != vc.channel: await message.channel.send("Tu dois être avec moi."); return
        if vad_instance is None: await message.channel.send("⚠️ VAD non prêt."); return

        transcribed_text = await speech_handler.handle_ecoute_command(
            message, vc, whisper_model, vad_instance, config, dummy_finished_recording_callback
        )
        if transcribed_text:
            bot_name = client.user.name or ""
            act_phrases = ["mistral", "ok bot"];
            if bot_name: act_phrases.append(bot_name.lower())
            should_chain, question_llm = False, transcribed_text
            for phrase in act_phrases:
                if transcribed_text.lower().startswith(phrase):
                    should_chain, question_llm = True, transcribed_text[len(phrase):].lstrip(', ').strip(); break
            if should_chain and question_llm:
                original_content = message.content
                web_kw = ["cherche sur internet", "recherche web", "trouve sur le web", "sur internet", "sur le net", "cherchons internet"]
                is_web = any(kw in question_llm.lower() for kw in web_kw)

                # Arguments communs pour les handlers LLM
                llm_common_args = {
                    "message": message, "vc": vc,
                    "conversation_history_ref": conversation_history, "app_config": config,
                    "speak_text_func": speech_handler.speak_text,
                    "clean_text_for_speech_func": speech_handler.clean_text_for_speech
                }
                # Mettre à jour message.content avant d'appeler les handlers spécifiques
                # car ils peuvent parser la question à partir de là.
                if is_web:
                    await message.channel.send(f"💡 `!ecoute` -> AskWeb: `{question_llm}`")
                    message.content = f"!askweb {question_llm}" # Les handlers s'attendent à parser ça
                    await llm_handler.handle_askweb_command(**llm_common_args, perform_web_search_func=web_utils.perform_sync_ddg_search)
                else:
                    await message.channel.send(f"💡 `!ecoute` -> Mistral: `{question_llm}`")
                    message.content = f"!mistral {question_llm}" # Les handlers s'attendent à parser ça
                    await llm_handler.handle_mistral_command(**llm_common_args)
                message.content = original_content # Restaurer le contenu original
            elif should_chain and not question_llm:
                 await message.channel.send(f"Mot d'activation entendu, mais pas de question.")

    elif message.content.startswith('!clean'):
        await llm_handler.handle_clean_command(message, conversation_history)
    elif message.content.startswith('!mistral'):
        await llm_handler.handle_mistral_command(message, vc, conversation_history, config, speech_handler.speak_text, speech_handler.clean_text_for_speech)
    elif message.content.startswith('!askweb'):
        await llm_handler.handle_askweb_command(message, vc, conversation_history, config, web_utils.perform_sync_ddg_search, speech_handler.speak_text, speech_handler.clean_text_for_speech)

if __name__ == "__main__":
    if not hasattr(config, 'TOKEN') or not config.TOKEN or config.TOKEN == "TON_VRAI_TOKEN_DISCORD_ICI":
        print("ERREUR: TOKEN manquant/incorrect dans config.py.")
    elif not hasattr(config, 'LM_STUDIO_MODEL_NAME') or not config.LM_STUDIO_MODEL_NAME:
        print(f"ATTENTION: LM_STUDIO_MODEL_NAME non défini dans config.py.")
    else:
        print(f"INFO: Modèle LM Studio: {config.LM_STUDIO_MODEL_NAME}")
        if not os.path.exists(config.DOWNLOAD_PATH):
            try: os.makedirs(config.DOWNLOAD_PATH); print(f"Dossier '{config.DOWNLOAD_PATH}' créé.")
            except OSError as e: print(f"ERREUR: Création dossier '{config.DOWNLOAD_PATH}' échouée: {e}"); exit()
        try: client.run(config.TOKEN)
        except discord.errors.LoginFailure: print("ERREUR LOGIN: Token invalide ou intents Discord non activés.")
        except Exception as e_run: print(f"ERREUR DÉMARRAGE BOT: {e_run}")