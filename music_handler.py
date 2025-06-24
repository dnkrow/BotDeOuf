# music_handler.py

import discord
import asyncio
import os  # Pour os.path.basename


# Les variables comme audio_queue, bot_loop, et download_path (depuis config)
# seront passées en argument par main.py aux fonctions qui en ont besoin.

async def play_audio_source_wrapper(vc: discord.VoiceClient,
                                    source: discord.PCMVolumeTransformer,  # ou FFmpegPCMAudio
                                    message_ctx: discord.Message,
                                    item_name: str,
                                    after_play_callback,  # Le callback à appeler après la lecture
                                    audio_queue_ref: asyncio.Queue,  # Référence à la file d'attente
                                    bot_loop_ref: asyncio.AbstractEventLoop,  # Référence à la boucle d'événements
                                    config_module):  # Pour accéder à DOWNLOAD_PATH si besoin
    """Joue une source audio et gère la suite ou les erreurs."""
    try:
        if not vc or not vc.is_connected():
            await message_ctx.channel.send("Je ne suis pas connecté à un salon vocal.")
            if not audio_queue_ref.empty(): audio_queue_ref._queue.clear()  # Vide la deque
            return

        # Attendre que la lecture précédente soit finie (si le bot était déjà en train de jouer)
        while vc.is_playing() or vc.is_paused():
            await asyncio.sleep(0.1)

        vc.play(source, after=after_play_callback)
        await message_ctx.channel.send(f"🎶 En lecture : `{item_name}`")

    except Exception as e_play_wrapper:
        await message_ctx.channel.send(f"⚠️ Erreur de lecture pour `{item_name}`: {e_play_wrapper}")
        print(f"❌ Erreur dans play_audio_source_wrapper pour {item_name}: {e_play_wrapper}")
        # Essayer de passer au suivant en cas d'erreur critique sur un item
        if not audio_queue_ref.empty():
            next_item = audio_queue_ref._queue[0]  # Regarde le prochain item sans le retirer
            if next_item.startswith("http"):
                await start_next_youtube_audio(vc, message_ctx, audio_queue_ref, bot_loop_ref, config_module)
            else:
                await start_next_local_audio(vc, message_ctx, audio_queue_ref, bot_loop_ref, config_module)


async def start_next_youtube_audio(vc: discord.VoiceClient, message_ctx: discord.Message,
                                   audio_queue_ref: asyncio.Queue, bot_loop_ref: asyncio.AbstractEventLoop,
                                   config_module):  # Ajout de config_module
    """Prépare et joue le prochain morceau YouTube de la file d'attente."""
    if audio_queue_ref.empty():
        # await message_ctx.channel.send("📭 File YouTube vide.") # Optionnel
        return

    url_to_play = await audio_queue_ref.get()  # Récupère de la file asyncio.Queue
    item_display_name = url_to_play.split('&list=')[0]

    await message_ctx.channel.send(f"💿 Recherche du lien pour : `{item_display_name}`...")

    try:
        yt_dlp_command = f'yt-dlp -g -f bestaudio[ext=m4a]/bestaudio --no-playlist "{url_to_play}"'
        process = await asyncio.create_subprocess_shell(
            yt_dlp_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout_data, stderr_data = await process.communicate()

        if process.returncode != 0:
            error_message_yt = stderr_data.decode(errors='replace').strip()
            await message_ctx.channel.send(
                f"⚠️ Erreur yt-dlp pour `{item_display_name}`: ```{error_message_yt[:500]}...```")
            if not audio_queue_ref.empty(): await start_next_youtube_audio(vc, message_ctx, audio_queue_ref,
                                                                           bot_loop_ref, config_module)
            return

        stream_url = stdout_data.decode().strip().split('\n')[0]
        if not stream_url or not stream_url.startswith("http"):
            await message_ctx.channel.send(
                f"⚠️ Impossible d'obtenir une URL de streaming valide pour `{item_display_name}`.")
            if not audio_queue_ref.empty(): await start_next_youtube_audio(vc, message_ctx, audio_queue_ref,
                                                                           bot_loop_ref, config_module)
            return

        ffmpeg_audio_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                                'options': '-vn'}
        audio_source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_audio_options)

        # Définition du callback pour après la lecture
        def after_yt_play_callback_handled(error_yt):
            if error_yt: print(f"Erreur pendant la lecture YT de {item_display_name}: {error_yt}")
            # Utiliser bot_loop_ref pour run_coroutine_threadsafe
            if bot_loop_ref and not bot_loop_ref.is_closed():
                asyncio.run_coroutine_threadsafe(
                    start_next_youtube_audio(vc, message_ctx, audio_queue_ref, bot_loop_ref, config_module),
                    bot_loop_ref)

        await play_audio_source_wrapper(vc, audio_source, message_ctx, item_display_name,
                                        after_yt_play_callback_handled, audio_queue_ref, bot_loop_ref, config_module)

    except Exception as e_start_yt:
        await message_ctx.channel.send(
            f"⚠️ Erreur critique (start_next_youtube_audio) pour `{item_display_name}`: {e_start_yt}")
        if not audio_queue_ref.empty(): await start_next_youtube_audio(vc, message_ctx, audio_queue_ref, bot_loop_ref,
                                                                       config_module)


async def start_next_local_audio(vc: discord.VoiceClient, message_ctx: discord.Message,
                                 audio_queue_ref: asyncio.Queue, bot_loop_ref: asyncio.AbstractEventLoop,
                                 config_module):  # Ajout de config_module
    """Prépare et joue le prochain fichier local de la file d'attente."""
    if audio_queue_ref.empty():
        # await message_ctx.channel.send("📭 File locale vide.") # Optionnel
        return

    file_path = await audio_queue_ref.get()  # Récupère de la file asyncio.Queue
    item_display_name = os.path.basename(file_path)

    if not os.path.exists(file_path):
        await message_ctx.channel.send(f"⚠️ Fichier local introuvable: `{item_display_name}`")
        if not audio_queue_ref.empty(): await start_next_local_audio(vc, message_ctx, audio_queue_ref, bot_loop_ref,
                                                                     config_module)
        return

    audio_source = discord.FFmpegPCMAudio(file_path)

    def after_local_play_callback_handled(error_local):
        if error_local: print(f"Erreur pendant la lecture locale de {item_display_name}: {error_local}")
        if bot_loop_ref and not bot_loop_ref.is_closed():
            asyncio.run_coroutine_threadsafe(
                start_next_local_audio(vc, message_ctx, audio_queue_ref, bot_loop_ref, config_module), bot_loop_ref)

    await play_audio_source_wrapper(vc, audio_source, message_ctx, item_display_name, after_local_play_callback_handled,
                                    audio_queue_ref, bot_loop_ref, config_module)


# --- Fonctions de gestion des commandes musicales ---

async def handle_playyt_command(message: discord.Message, vc: discord.VoiceClient,
                                audio_queue_ref: asyncio.Queue, bot_loop_ref: asyncio.AbstractEventLoop,
                                config_module):  # Ajout de config_module
    if not vc or not vc.is_connected():
        await message.channel.send("Je ne suis pas dans un salon vocal. Utilise `!join` d'abord.");
        return

    query_url = message.content[len('!playyt'):].strip()
    if not query_url:
        await message.channel.send("Merci de me donner une URL YouTube après `!playyt `.");
        return

    # Pour l'instant, on n'implémente pas la recherche par mots-clés ici, uniquement URL directe
    if not (query_url.startswith("http://") or query_url.startswith("https://")):
        await message.channel.send("Pour l'instant, je ne prends en charge que les URLs YouTube directes.");
        return

    await audio_queue_ref.put(query_url)  # Ajoute à la file asyncio.Queue
    await message.channel.send(f"✅ Ajouté à la file (YT): `{query_url.split('&list=')[0]}`")

    if not vc.is_playing() and not vc.is_paused():
        await start_next_youtube_audio(vc, message, audio_queue_ref, bot_loop_ref, config_module)


async def handle_playlocal_command(message: discord.Message, vc: discord.VoiceClient,
                                   audio_queue_ref: asyncio.Queue, bot_loop_ref: asyncio.AbstractEventLoop,
                                   config_module):  # Contient DOWNLOAD_PATH
    if not vc or not vc.is_connected():
        await message.channel.send("Pas en vocal. `!join` d'abord.");
        return

    filename_query = message.content[len('!playlocal'):].strip()
    if not filename_query:
        await message.channel.send("Quel fichier local veux-tu jouer ? (doit être dans le dossier audio_cache)");
        return

    # Construit le chemin complet en utilisant DOWNLOAD_PATH de config_module
    file_path_to_play = os.path.join(config_module.DOWNLOAD_PATH, filename_query)

    if not os.path.exists(file_path_to_play):
        await message.channel.send(f"Fichier `{filename_query}` introuvable dans `{config_module.DOWNLOAD_PATH}`.");
        return

    await audio_queue_ref.put(file_path_to_play)  # Ajoute à la file asyncio.Queue
    await message.channel.send(f"✅ Ajouté à la file (Local): `{filename_query}`")

    if not vc.is_playing() and not vc.is_paused():
        await start_next_local_audio(vc, message, audio_queue_ref, bot_loop_ref, config_module)


async def handle_next_command(message: discord.Message, vc: discord.VoiceClient,
                              audio_queue_ref: asyncio.Queue, bot_loop_ref: asyncio.AbstractEventLoop,
                              config_module):  # Ajout de config_module
    if not vc or not vc.is_connected():
        await message.channel.send("Je ne suis pas connecté à un salon vocal.");
        return

    if vc.is_playing() or vc.is_paused():
        vc.stop()  # Arrêter la lecture en cours, le callback "after" devrait lancer la suivante
        await message.channel.send("⏭️ Passage au morceau suivant...")
    elif not audio_queue_ref.empty():
        await message.channel.send("▶️ La file n'est pas vide, démarrage du prochain morceau...")
        # Détermine si le prochain est local ou youtube
        next_item = audio_queue_ref._queue[0]  # Regarde sans retirer pour l'instant
        if next_item.startswith("http"):
            await start_next_youtube_audio(vc, message, audio_queue_ref, bot_loop_ref, config_module)
        else:
            await start_next_local_audio(vc, message, audio_queue_ref, bot_loop_ref, config_module)
    else:
        await message.channel.send("🤔 La file d'attente est vide, rien à passer.")


async def handle_stop_command(message: discord.Message, vc: discord.VoiceClient, audio_queue_ref: asyncio.Queue):
    if vc and vc.is_connected():
        # Vider la file d'attente (pour asyncio.Queue)
        while not audio_queue_ref.empty():
            try:
                audio_queue_ref.get_nowait()
            except asyncio.QueueEmpty:
                break
        vc.stop()
        await message.channel.send("⏹️ Lecture stoppée et file d'attente vidée.")
    else:
        await message.channel.send("Je ne suis pas en train de jouer de musique.")


async def handle_queue_command(message: discord.Message, audio_queue_ref: asyncio.Queue):
    if audio_queue_ref.empty():
        await message.channel.send("🌀 La file d'attente est vide.");
        return

    # Pour afficher le contenu d'une asyncio.Queue, on accède à sa deque interne _queue
    # C'est un détail d'implémentation, mais c'est la manière la plus simple de lister sans consommer.
    queue_list_display = list(audio_queue_ref._queue)

    if not queue_list_display:  # Double vérification après la conversion en liste
        await message.channel.send("🌀 La file d'attente est vide (après vérification).");
        return

    queue_message = "📄 **File d'attente actuelle**:\n"
    for i, item_path_or_url in enumerate(queue_list_display):
        item_name = os.path.basename(item_path_or_url) if not item_path_or_url.startswith("http") else \
        item_path_or_url.split('&list=')[0]
        queue_message += f"`{i + 1}.` {item_name}\n"
    await message.channel.send(queue_message)