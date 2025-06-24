# llm_handler.py

import asyncio
import aiohttp
import tiktoken
from datetime import datetime
import discord

# Les modules config, web_utils, et speech_handler (pour ses fonctions)
# seront importés dans main.py et les fonctions/valeurs nécessaires
# seront passées en arguments aux fonctions de ce handler.

async def generate_mistral_response(messages: list, api_url: str, model_name: str,
                                    max_tokens=1024, temperature=0.6, top_p=0.9):
    """Envoie une requête à l'API LM Studio et retourne la réponse du LLM."""
    headers = {'Content-Type': 'application/json'}
    data = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=data) as response:
                if response.status == 200:
                    response_data = await response.json()
                    if response_data and response_data.get('choices') and \
                            len(response_data['choices']) > 0 and \
                            response_data['choices'][0].get('message'):
                        return response_data['choices'][0]['message']['content'].strip()
                    else:
                        print(f"Réponse API LM Studio invalide (structure): {response_data}")
                        return "⚠️ Erreur : Réponse API LM Studio (structure incorrecte)."
                else:
                    error_text = await response.text()
                    print(f"Erreur API LM Studio (Status: {response.status}): {error_text}")
                    return f"⚠️ Erreur API LM Studio (Status: {response.status}) - {error_text[:200]}"
    except aiohttp.ClientConnectorError:
        print(f"Erreur de connexion à LM Studio ({api_url}). Est-il lancé et le serveur démarré ?")
        return "⚠️ Erreur de connexion à LM Studio. Vérifiez qu'il est bien lancé."
    except Exception as e:
        print(f"Erreur inattendue avec l'API LM Studio: {e}")
        return "⚠️ Erreur inattendue avec l'API LM Studio."


async def handle_mistral_command(message, vc, conversation_history_ref, app_config,
                                 speak_text_func, clean_text_for_speech_func):
    """Gère la commande !mistral."""
    user_id_str = str(message.author.id)
    question = message.content[len('!mistral'):].strip()

    if not question:
        await message.channel.send("Quelle est ta question pour Mistral ? Utilisation : `!mistral <ta question>`")
        return

    print(f"❓ Demande Mistral de {message.author.display_name}: {question}")
    thinking_msg = await message.channel.send("🤔 Mistral réfléchit...")

    if user_id_str not in conversation_history_ref:
        conversation_history_ref[user_id_str] = []

    dated_question = f"Date actuelle: {datetime.now().strftime('%d %B %Y, %H:%M')}. Question de l'utilisateur: {question}"

    current_conversation = conversation_history_ref[user_id_str].copy()
    current_conversation.append({"role": "user", "content": dated_question})

    # Gestion du contexte (simplifié, tiktoken pour compter)
    max_context_tokens = 1800  # Tu peux ajuster cette valeur
    try:
        encoding = tiktoken.get_encoding("cl100k_base")

        def count_tokens(text_to_count):
            return len(encoding.encode(text_to_count))
    except:  # Fallback si tiktoken a un souci
        def count_tokens(text_to_count):
            return len(text_to_count) // 4  # Approximation grossière

    total_tokens_in_conversation = sum(count_tokens(msg["content"]) for msg in current_conversation)
    while total_tokens_in_conversation > max_context_tokens and len(current_conversation) > 1:
        removed_message = current_conversation.pop(0)  # Retire le plus ancien
        total_tokens_in_conversation -= count_tokens(removed_message["content"])
        # S'assurer qu'on ne retire pas le dernier message utilisateur si c'est le seul qui reste
        if not current_conversation or (len(current_conversation) == 1 and current_conversation[0]["role"] == "user"):
            break

    try:
        await thinking_msg.edit(content="🧠 Mistral génère une réponse...")
        llm_response = await generate_mistral_response(
            current_conversation,
            app_config.LM_STUDIO_API_URL,
            app_config.LM_STUDIO_MODEL_NAME
        )

        try:
            await thinking_msg.delete()
        except discord.errors.NotFound:
            pass  # Le message a peut-être déjà été supprimé

        if not llm_response.startswith("⚠️ Erreur"):
            # Sauvegarder le contexte utilisé et la réponse de l'assistant
            conversation_history_ref[user_id_str] = current_conversation
            conversation_history_ref[user_id_str].append({"role": "assistant", "content": llm_response})

            # Optionnel : Élague l'historique stocké si conversation_history_ref[user_id_str] devient trop long
            # (similaire à la boucle de comptage de tokens ci-dessus, mais sur l'historique complet stocké)

            for part in [llm_response[i:i + 1950] for i in range(0, len(llm_response), 1950)]:
                await message.channel.send(part)
            print(f"🤖 Réponse Mistral (pour {message.author.display_name}): {llm_response[:70]}...")

            if vc and vc.is_connected():
                cleaned_response_for_speech = clean_text_for_speech_func(llm_response)
                await speak_text_func(vc, cleaned_response_for_speech, message.channel, app_config.DOWNLOAD_PATH)
            else:
                await message.channel.send("(Astuce: `!join` pour que je te donne la réponse vocalement !)")
        else:
            await message.channel.send(llm_response)  # Affiche le message d'erreur de generate_mistral_response
    except Exception as e_mistral_cmd:
        try:
            await thinking_msg.delete()
        except:
            pass
        await message.channel.send(f"⚠️ Une erreur majeure s'est produite avec Mistral: {e_mistral_cmd}")
        print(f"❌ Erreur critique dans la commande !mistral: {e_mistral_cmd}")


async def handle_askweb_command(message, vc, conversation_history_ref, app_config,
                                perform_web_search_func, speak_text_func, clean_text_for_speech_func):
    """Gère la commande !askweb."""
    user_question = message.content[len('!askweb'):].strip()
    if not user_question:
        await message.channel.send("Quelle question veux-tu poser au web et à Mistral ? `!askweb <ta question>`")
        return

    await message.channel.send(f"🔎 Recherche d'informations web pour répondre à : `{user_question}`...")
    # perform_web_search_func est web_utils.perform_sync_ddg_search, qui est synchrone
    # On l'exécute dans un thread pour ne pas bloquer la boucle asyncio
    search_results = await asyncio.to_thread(perform_web_search_func, user_question, 3)

    web_context = "Informations trouvées sur le web :\n"
    if search_results:
        for i, res_item in enumerate(search_results):
            web_context += f"Source {i + 1}: {res_item.get('title', '')} - {res_item.get('body', '')[:300]}...\n"
    else:
        web_context += "Aucune information web pertinente n'a été trouvée pour cette question."

    web_context = web_context[:3000]  # Limiter la taille du contexte web

    prompt_for_llm = (
        f"En te basant STRICTEMENT sur les informations suivantes extraites du web, réponds à la question de l'utilisateur. "
        f"Si les informations ne permettent pas de répondre, indique-le clairement.\n\n"
        f"Date actuelle: {datetime.now().strftime('%d %B %Y')}\n"
        f"--- Début des informations web ---\n{web_context}\n--- Fin des informations web ---\n\n"
        f"Question de l'utilisateur : {user_question}\n\nRéponse :"
    )

    llm_messages = [{"role": "user", "content": prompt_for_llm}]
    thinking_msg_askweb = await message.channel.send("🤔 Mistral (avec infos web) réfléchit...")

    try:
        llm_response = await generate_mistral_response(
            llm_messages,
            app_config.LM_STUDIO_API_URL,
            app_config.LM_STUDIO_MODEL_NAME
        )
        try:
            await thinking_msg_askweb.delete()
        except discord.errors.NotFound:
            pass

        if not llm_response.startswith("⚠️ Erreur"):
            for part in [llm_response[i:i + 1950] for i in range(0, len(llm_response), 1950)]:
                await message.channel.send(part)

            if vc and vc.is_connected():
                cleaned_response_for_speech_aw = clean_text_for_speech_func(llm_response)
                await speak_text_func(vc, cleaned_response_for_speech_aw, message.channel, app_config.DOWNLOAD_PATH)
        else:
            await message.channel.send(llm_response)  # Affiche l'erreur
    except Exception as e_askweb_cmd:
        try:
            await thinking_msg_askweb.delete()
        except:
            pass
        await message.channel.send(f"⚠️ Erreur majeure avec !askweb: {e_askweb_cmd}")
        print(f"❌ Erreur critique dans !askweb: {e_askweb_cmd}")


async def handle_clean_command(message, conversation_history_ref):
    """Gère la commande !clean pour effacer l'historique de conversation."""
    user_id_str_clean = str(message.author.id)
    if user_id_str_clean in conversation_history_ref:
        del conversation_history_ref[user_id_str_clean]
        await message.channel.send("🧹 L'historique de votre conversation avec Mistral a été effacé.")
    else:
        await message.channel.send("🗑️ Aucun historique de conversation à effacer pour vous.")




# Screen analyse -----
async def handle_screen_analysis_with_llm(
    message_ctx: discord.Message,
    vc: discord.VoiceClient,
    screen_text: str,
    user_specific_prompt: str,

    app_config,
    perform_web_search_func,
    speak_text_func,
    clean_text_for_speech_func
):
    """
    Analyse le texte extrait de l'écran, effectue une recherche web basée sur la demande de l'utilisateur,
    interroge Mistral avec toutes ces informations, et envoie la réponse.
    """
    await message_ctx.channel.send(
        f"🤖 Analyse du contenu de l'écran et recherche web pour : \"{user_specific_prompt}\" en cours...")

    # 1. Effectuer une recherche web basée sur la demande spécifique de l'utilisateur
    # On utilise asyncio.to_thread car perform_web_search_func (DDGS) est synchrone
    search_query_for_web = user_specific_prompt  # On pourrait affiner ça plus tard
    web_search_results = await asyncio.to_thread(perform_web_search_func, search_query_for_web, 3)  # 3 résultats

    web_context_for_llm = "Informations trouvées sur le web :\n"
    if web_search_results:
        for i, res_item_web_analysis in enumerate(web_search_results):
            web_context_for_llm += f"Source {i + 1}: {res_item_web_analysis.get('title', '')} - {res_item_web_analysis.get('body', '')[:250]}...\n"  # Snippet un peu plus court
    else:
        web_context_for_llm += "Aucune information pertinente trouvée sur le web pour cette demande spécifique."

    web_context_for_llm = web_context_for_llm[:2500]  # Limiter la taille du contexte web

    # 2. Construire le prompt final pour Mistral
    # On inclut une instruction claire, le texte de l'écran, la question de l'utilisateur, et les résultats web.
    final_prompt_to_llm = (
        f"Réponds uniquement en français. Tu es un assistant expert en analyse de code et résolution de problèmes.\n\n"
        f"L'utilisateur a partagé le contenu suivant de son écran :\n"
        f"--- CONTENU DE L'ÉCRAN ---\n"
        f"{screen_text[:3000]}\n"  # Limiter la taille du texte de l'écran envoyé à l'IA
        f"--- FIN DU CONTENU DE L'ÉCRAN ---\n\n"
        f"Voici sa question ou l'instruction spécifique concernant ce contenu d'écran :\n"
        f"\"{user_specific_prompt}\"\n\n"
        f"Voici des informations supplémentaires que j'ai trouvées sur internet concernant sa question/instruction :\n"
        f"--- INFORMATIONS WEB ---\n"
        f"{web_context_for_llm}\n"
        f"--- FIN DES INFORMATIONS WEB ---\n\n"
        f"Maintenant, en te basant sur TOUTES ces informations (contenu de l'écran, question de l'utilisateur, et infos web), "
        f"fournis une analyse, une explication, une suggestion de correction, ou une réponse pertinente et utile à l'utilisateur."
    )

    llm_messages_for_screen_analysis = [{"role": "user", "content": final_prompt_to_llm}]

    thinking_message_screen_analysis = await message_ctx.channel.send(
        "🤔 Mistral analyse l'écran et les informations web...")

    try:
        # Appel à la fonction generate_mistral_response (qui est déjà dans ce fichier llm_handler.py)
        llm_response_screen = await generate_mistral_response(
            llm_messages_for_screen_analysis,
            app_config.LM_STUDIO_API_URL,
            app_config.LM_STUDIO_MODEL_NAME
            # On pourrait ajuster max_tokens, temperature ici si besoin pour ce type de tâche
        )

        try:
            await thinking_message_screen_analysis.delete()
        except discord.errors.NotFound:
            pass

        if not llm_response_screen.startswith("⚠️ Erreur"):
            # Envoyer la réponse de Mistral
            for part in [llm_response_screen[i:i + 1950] for i in range(0, len(llm_response_screen), 1950)]:
                await message_ctx.channel.send(part)

            # Faire parler le bot si en vocal
            if vc and vc.is_connected():
                cleaned_llm_response_for_speech = clean_text_for_speech_func(llm_response_screen)
                await speak_text_func(vc, cleaned_llm_response_for_speech, message_ctx.channel,
                                      app_config.DOWNLOAD_PATH)
        else:
            await message_ctx.channel.send(
                llm_response_screen)  # Affiche le message d'erreur de generate_mistral_response

    except Exception as e_screen_llm_processing:
        try:
            await thinking_message_screen_analysis.delete()
        except:
            pass
        await message_ctx.channel.send(
            f"⚠️ Une erreur majeure s'est produite lors de l'analyse par Mistral : {e_screen_llm_processing}")
        print(f"❌ Erreur critique dans handle_screen_analysis_with_llm : {e_screen_llm_processing}")