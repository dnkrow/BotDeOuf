# speech_handler.py

from collections import deque
import asyncio
import os
import re
import uuid
import time
import wave

import discord  # Nécessaire pour discord.FFmpegPCMAudio et discord.User
import pyttsx3
import webrtcvad  # Pour la détection d'activité vocale


# On n'importe pas 'config' directement ici pour garder le module plus indépendant.
# Les valeurs de config nécessaires (comme DOWNLOAD_PATH, VAD_SAMPLE_RATE, etc.)
# seront passées en argument aux fonctions qui en ont besoin.

def clean_text_for_speech(text_to_clean):
    """Nettoie le texte pour la synthèse vocale."""
    text = re.sub(r'http[s]?://\S+', "[source en ligne]", text_to_clean)
    text = re.sub(r'[*_`~]', '', text)
    text = re.sub(r'<@!?\d+>|<#\d+>|<:\w*:\d+>', '', text)
    return re.sub(r'\s+', ' ', text).strip()


async def speak_text(voice_client: discord.VoiceClient, text_to_speak: str,
                     message_channel: discord.TextChannel, download_path: str):
    """Génère un fichier audio à partir du texte et le joue dans le salon vocal."""

    # Utiliser un nom de variable unique pour le fichier dans cette fonction
    # pour éviter toute confusion avec d'autres variables dans d'autres scopes.
    current_tts_temp_file = None
    try:
        def blocking_tts_save_sync(text_sync, filename_sync):  # Reste synchrone
            engine = pyttsx3.init()
            engine.save_to_file(text_sync, filename_sync)
            engine.runAndWait()
            engine.stop()

        current_tts_temp_file = os.path.join(download_path, f"tts_audio_{uuid.uuid4().hex}.mp3")
        await asyncio.to_thread(blocking_tts_save_sync, text_to_speak, current_tts_temp_file)

        if os.path.exists(current_tts_temp_file) and os.path.getsize(current_tts_temp_file) > 0:
            if voice_client and voice_client.is_connected():
                while voice_client.is_playing():
                    await asyncio.sleep(0.1)

                # Définition du callback synchrone directement ici
                # Elle a accès à current_tts_temp_file grâce à la portée (closure)
                def after_tts_playback_finished_sync(error_in_playback):  # Fonction synchrone
                    if error_in_playback:
                        print(f'Erreur Player TTS (callback): {error_in_playback}')

                    # Tenter de supprimer le fichier
                    if os.path.exists(current_tts_temp_file):
                        try:
                            os.remove(current_tts_temp_file)
                            # print(f"Fichier TTS {os.path.basename(current_tts_temp_file)} supprimé via callback.")
                        except Exception as e_del_in_cb:
                            # Cette erreur peut encore arriver si le fichier est verrouillé,
                            # mais le warning sur la coroutine devrait disparaître.
                            print(
                                f"Erreur suppression fichier TTS (dans callback) {os.path.basename(current_tts_temp_file)}: {e_del_in_cb}")

                audio_source_to_play = discord.FFmpegPCMAudio(current_tts_temp_file)
                # On passe directement la fonction synchrone définie localement
                voice_client.play(audio_source_to_play, after=after_tts_playback_finished_sync)

            elif os.path.exists(current_tts_temp_file):
                # Si le bot n'est pas connecté en vocal mais que le fichier a été créé, on le supprime.
                os.remove(current_tts_temp_file)
        else:
            if message_channel:  # Vérifier si message_channel est défini
                await message_channel.send("⚠️ Erreur: Fichier audio TTS non généré ou est vide.")
            if os.path.exists(current_tts_temp_file):
                os.remove(current_tts_temp_file)
    except Exception as e_speak_main_exc:
        print(f"❌ Erreur majeure dans la fonction speak_text: {e_speak_main_exc}")
        if message_channel:
            await message_channel.send(f"⚠️ Erreur lors de la génération de la parole: {e_speak_main_exc}")
        if current_tts_temp_file and os.path.exists(current_tts_temp_file):  # Nettoyage en cas d'erreur
            try:
                os.remove(current_tts_temp_file)
            except Exception as e_del_speak_in_exc:
                print(f"Erreur suppression fichier TTS (dans exception principale de speak_text): {e_del_speak_in_exc}")


def extract_speech_segments_from_file(input_filepath: str, vad_object: webrtcvad.Vad,
                                            sample_rate: int, frame_duration_ms: int,
                                            download_path_vad: str):
    """
    Analyse un fichier WAV, extrait les segments de parole en utilisant webrtcvad,
    et les sauvegarde dans un nouveau fichier WAV.
    Retourne le chemin du nouveau fichier si de la parole est trouvée, sinon None.
    """
    if not os.path.exists(input_filepath):
        print(f"Fichier d'entrée VAD non trouvé: {input_filepath}")
        return None

    try:
        with wave.open(input_filepath, 'rb') as wf_input:
            num_channels = wf_input.getnchannels()
            sampwidth = wf_input.getsampwidth()
            input_framerate = wf_input.getframerate()

            if input_framerate != sample_rate:
                print(f"Erreur VAD: Taux échantillonnage fichier ({input_framerate}Hz) != attendu ({sample_rate}Hz)")
                return None
            if sampwidth != 2:  # Doit être 16-bit PCM
                print(f"Erreur VAD: Largeur d'échantillon non supportée ({sampwidth} bytes)")
                return None
            if num_channels not in [1, 2]:
                print(f"Erreur VAD: Nombre de canaux non supporté ({num_channels})")
                return None

            samples_per_frame_for_vad = (sample_rate // 1000) * frame_duration_ms
            bytes_per_sample_mono = sampwidth
            bytes_per_frame_mono_for_vad = samples_per_frame_for_vad * bytes_per_sample_mono
            bytes_per_frame_original_input = samples_per_frame_for_vad * sampwidth * num_channels

            speech_audio_data_buffer = bytearray()
            padding_duration_ms = 300  # Ajouter un peu de son avant/après la détection
            padding_frames = (padding_duration_ms // frame_duration_ms)
            ring_buffer = deque(maxlen=padding_frames)
            triggered = False
            voiced_frames = []

            while True:
                frame_input_original = wf_input.readframes(samples_per_frame_for_vad)
                if not frame_input_original: break
                if len(frame_input_original) < bytes_per_frame_original_input: break

                frame_for_vad_analysis = bytearray(bytes_per_frame_mono_for_vad)
                if num_channels == 2:  # Stereo -> Mono (prendre canal gauche)
                    for i in range(samples_per_frame_for_vad):
                        frame_for_vad_analysis[i * sampwidth:(i + 1) * sampwidth] = frame_input_original[
                                                                                    i * sampwidth * 2:(
                                                                                                                  i * sampwidth * 2) + sampwidth]
                else:  # Déjà Mono
                    frame_for_vad_analysis = frame_input_original

                is_speech = vad_object.is_speech(bytes(frame_for_vad_analysis), sample_rate)

                if not triggered:
                    ring_buffer.append((frame_input_original, is_speech))
                    if is_speech:
                        triggered = True
                        # Ajouter les frames de padding du début
                        for f_data, _ in ring_buffer: speech_audio_data_buffer.extend(f_data)
                        ring_buffer.clear()
                else:
                    speech_audio_data_buffer.extend(frame_input_original)
                    ring_buffer.append((frame_input_original, is_speech))
                    num_voiced = len([f_data for f_data, spoken in ring_buffer if spoken])
                    if num_voiced < (ring_buffer.maxlen * 0.3):  # Si moins de 30% de parole dans le buffer de fin
                        triggered = False  # Fin du segment de parole, on arrête d'ajouter au buffer principal
                        # On pourrait aussi enlever les derniers frames silencieux du speech_audio_data_buffer ici

        if not speech_audio_data_buffer:
            print("VAD n'a détecté aucune parole dans le fichier.")
            return None

        trimmed_audio_filepath = os.path.join(download_path_vad, f"vad_trimmed_{uuid.uuid4().hex}.wav")
        with wave.open(trimmed_audio_filepath, 'wb') as wf_output:
            wf_output.setnchannels(num_channels);
            wf_output.setsampwidth(sampwidth)
            wf_output.setframerate(input_framerate);
            wf_output.writeframes(speech_audio_data_buffer)

        print(f"Fichier audio traité par VAD sauvegardé : {trimmed_audio_filepath}")
        return trimmed_audio_filepath
    except Exception as e_vad_file_processing:
        print(f"Erreur pendant le traitement VAD du fichier {input_filepath}: {e_vad_file_processing}")
        return None


async def handle_ecoute_command(message: discord.Message, vc: discord.VoiceClient,
                                whisper_module, vad_module_instance,
                                app_config,  # L'objet config importé
                                dummy_recording_callback):  # Le callback factice de main.py
    """Gère la commande !ecoute : enregistrement à durée fixe, VAD sur fichier, puis Whisper."""

    if not whisper_module:
        await message.channel.send("⚠️ Modèle Whisper non chargé.");
        return ""
    if not vc or not vc.is_connected():
        await message.channel.send("Pas en vocal. `!join` svp.");
        return ""
    if not message.author.voice or message.author.voice.channel != vc.channel:
        await message.channel.send("Tu dois être avec moi dans le salon.");
        return ""

    # S'assurer que vad_module_instance est bien une instance de webrtcvad.Vad
    if not isinstance(vad_module_instance, webrtcvad.Vad):
        await message.channel.send("⚠️ Instance VAD non initialisée correctement.");
        return ""

    # Utilisation des constantes de config.py
    recording_duration = app_config.FIXED_RECORDING_DURATION_SECONDS
    vad_sample_rate_config = app_config.VAD_SAMPLE_RATE
    vad_frame_duration_config = app_config.VAD_FRAME_DURATION_MS
    download_path_config = app_config.DOWNLOAD_PATH

    # discord.sinks.WaveSink est utilisé par la logique d'enregistrement
    # Il faut s'assurer que `main.py` a fait `from discord.sinks import WaveSink`
    # ou alors, il faut l'importer ici. Pour l'instant on suppose qu'elle est dispo
    # via l'import dans main.py ou si discord.py l'expose globalement.
    # Pour être sûr, on peut l'importer localement si nécessaire, mais c'est mieux en haut du module.
    try:
        from discord.sinks import WaveSink  # Import local pour être sûr
    except ImportError:
        await message.channel.send("Erreur critique: WaveSink non trouvé.");
        return ""

    current_sink = WaveSink()
    raw_audio_filepath = os.path.join(download_path_config, f"raw_ecoute_{message.author.id}_{int(time.time())}.wav")

    await message.channel.send(f"🎙️ J'écoute {message.author.mention} pendant {recording_duration}s...")
    try:
        vc.start_recording(current_sink, dummy_recording_callback)
        await asyncio.sleep(recording_duration)
    finally:
        if vc.recording: vc.stop_recording(); await asyncio.sleep(0.5)

    author_audio = current_sink.audio_data.get(message.author.id)
    if not author_audio:
        err_msg = f"Voix non isolée." if current_sink.audio_data else "❌ Aucun son capté."
        await message.channel.send(err_msg);
        return ""
    try:
        with wave.open(raw_audio_filepath, 'wb') as wf:
            wf.setnchannels(2);
            wf.setsampwidth(2);
            wf.setframerate(vad_sample_rate_config)
            wf.writeframes(author_audio.file.read())
        print(f"Audio brut sauvegardé: {raw_audio_filepath}")
    except Exception as e_write:
        await message.channel.send(f"⚠️ Erreur sauvegarde audio brut: {e_write}");
        return ""

    await message.channel.send("🎤 Enreg. terminé. Analyse VAD de l'audio...")
    trimmed_audio_filepath = await asyncio.to_thread(
        extract_speech_segments_from_file,
        raw_audio_filepath,
        vad_module_instance,  # L'instance de webrtcvad.Vad passée en argument
        vad_sample_rate_config,
        vad_frame_duration_config,
        download_path_config
    )

    file_to_transcribe = raw_audio_filepath  # Par défaut, le fichier brut
    transcription_prefix = "(brut)"
    if trimmed_audio_filepath and os.path.exists(trimmed_audio_filepath):
        file_to_transcribe = trimmed_audio_filepath
        transcription_prefix = "(nettoyé VAD)"
        await message.channel.send("Analyse VAD terminée. Transcription du son nettoyé.")
    else:
        await message.channel.send("Analyse VAD n'a pas extrait de segment clair, transcription de l'audio brut.")

    transcribed_text = ""
    try:
        if not os.path.exists(file_to_transcribe):
            await message.channel.send(
                f"Fichier {os.path.basename(file_to_transcribe)} introuvable pour transcription.");
            return ""

        use_fp16 = next(whisper_module.parameters()).device.type == 'cuda'
        result = await asyncio.to_thread(whisper_module.transcribe, file_to_transcribe, fp16=use_fp16)
        transcribed_text = result["text"].strip()

        if transcribed_text:
            await message.channel.send(
                f"{message.author.mention} a dit {transcription_prefix}: \"_{transcribed_text}_\"")
        else:
            await message.channel.send(f"Je n'ai rien compris {transcription_prefix}, {message.author.mention}. 🤔")
    except Exception as e_transcribe:
        await message.channel.send(f"⚠️ Erreur transcription: {e_transcribe}")
    finally:
        if os.path.exists(raw_audio_filepath):
            try:
                os.remove(raw_audio_filepath)
            except Exception as e:
                print(f"Err supp raw: {e}")
        if trimmed_audio_filepath and trimmed_audio_filepath != raw_audio_filepath and os.path.exists(
                trimmed_audio_filepath):
            try:
                os.remove(trimmed_audio_filepath)
            except Exception as e:
                print(f"Err supp trimmed: {e}")

    return transcribed_text  # Retourne le texte pour que main.py puisse enchaîner