import modules.manager as manager
import json, re, requests

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters, Updater, CallbackContext, ChatJoinRequestHandler
from telegram.error import BadRequest, Conflict

from modules.utils import process_command, is_admin, cancel, error_callback, error_message

keyboardc = [
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
        ]
cancel_markup = InlineKeyboardMarkup(keyboardc)

# Estados do conversation handler
INICIO_ESCOLHA, INICIO_ADICIONAR_OU_DELETAR, INICIO_RECEBER, AGUARDANDO_MIDIAS, ESCOLHER_MODO_MIDIA = range(5)

# Comando definir inicio
# /Inicio
async def inicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command_check = await process_command(update, context)
    if not command_check:
        return ConversationHandler.END

    if not await is_admin(context, update.message.from_user.id):
        return ConversationHandler.END
    
    context.user_data['inicio_context'] = manager.get_bot_config(context.bot_data['id'])
    context.user_data['conv_state'] = "inicio"

    keyboard = [
        [InlineKeyboardButton("Midia Inicial", callback_data="midia"), InlineKeyboardButton("Texto 1", callback_data="texto1")],
        [InlineKeyboardButton("Texto 2", callback_data="texto2"), InlineKeyboardButton("Botão", callback_data="botao")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📱 O que deseja modificar no início?\n\n"
        ">𝗖𝗼𝗺𝗼 𝗳𝘂𝗻𝗰𝗶𝗼𝗻𝗮\\? Esse comando serve para personalizar o início do seu bot\\. Personalize textos, midia inicial e o botão inicial\\.",
        reply_markup=reply_markup,
        parse_mode='MarkdownV2'
    )
    return INICIO_ESCOLHA

async def inicio_escolha(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END

    context.user_data['inicio_acao'] = query.data

    # Se for botão, vai direto para receber o texto
    if query.data == 'botao':
        keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            "🕹 Envie abaixo o texto que deseja para o botão inicial\n\n"
            ">𝗖𝗼𝗺𝗼 𝗳𝘂𝗻𝗰𝗶𝗼𝗻𝗮\\? Esse texto é aplicado no botão que o usuário clica para exibir a lista de planos no início do bot\\.",
            reply_markup=reply_markup,
            parse_mode='MarkdownV2'
        )
        return INICIO_RECEBER

    keyboard = [
        [InlineKeyboardButton("🟢 Adicionar", callback_data="adicionar"), InlineKeyboardButton("🧹 Remover", callback_data="deletar")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Textos específicos para cada opção
    if query.data == 'midia':
        texto = "🎬 O que deseja fazer com a mídia inicial?"
    elif query.data == 'texto1':
        texto = "📝 O que deseja fazer com o Texto 1?"
    elif query.data == 'texto2':
        texto = "📝 O que deseja fazer com o Texto 2?"
    else:
        texto = f"🛠️ Deseja adicionar ou deletar o valor para {query.data}?"
    
    await query.message.edit_text(texto, reply_markup=reply_markup)
    return INICIO_ADICIONAR_OU_DELETAR

async def inicio_adicionar_ou_deletar(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    acao = context.user_data.get('inicio_acao')
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END

    if query.data == 'deletar':
        # Verifica se o item já foi definido
        config = context.user_data['inicio_context']
        
        if acao == 'texto2' and (not config.get('texto2') or config.get('texto2') == "Configure o bot usando /inicio\n\nUtilize /comandos para verificar os comandos existentes"):
            await query.message.edit_text("❌ Não é possível deletar o Texto 2, pois o mesmo ainda não foi definido.")
            context.user_data['conv_state'] = False
            return ConversationHandler.END
            
        if acao == 'texto1' and not config.get('texto1'):
            await query.message.edit_text("❌ Não é possível deletar o Texto 1, pois o mesmo ainda não foi definido.")
            context.user_data['conv_state'] = False
            return ConversationHandler.END
            
        if acao == 'midia':
            midias_count = manager.get_medias_count(context.bot_data['id'])
            if not config.get('midia') and midias_count == 0:
                await query.message.edit_text("❌ Não é possível deletar a Mídia, pois a mesma ainda não foi definida.")
                context.user_data['conv_state'] = False
                return ConversationHandler.END

        # Processa a remoção
        if acao == 'midia':
            manager.clear_medias_config(context.bot_data['id'])
            context.user_data['inicio_context']['midia'] = False
            context.user_data['inicio_context']['midias'] = []
            context.user_data['inicio_context']['media_mode'] = None
            manager.update_bot_config(context.bot_data['id'], context.user_data['inicio_context'])
            await query.message.edit_text("✅ Todas as mídias foram removidas com sucesso.")
            
        elif acao == 'texto1':
            context.user_data['inicio_context']['texto1'] = False
            manager.update_bot_config(context.bot_data['id'], context.user_data['inicio_context'])
            await query.message.edit_text("✅ Texto 1 foi removido com sucesso.")
            
        elif acao == 'texto2':
            context.user_data['inicio_context']['texto2'] = False
            manager.update_bot_config(context.bot_data['id'], context.user_data['inicio_context'])
            await query.message.edit_text("✅ Texto 2 foi removido com sucesso.")
        
        context.user_data['conv_state'] = False
        return ConversationHandler.END

    elif query.data == 'adicionar':
        keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if acao == "midia":
            # NÃO LIMPA MAIS AQUI!
            # manager.clear_medias_config(context.bot_data['id'])
            
            # NOVO: Marca que está esperando primeira mídia
            context.user_data['aguardando_primeira_midia'] = True
            
            keyboard = [[InlineKeyboardButton("🔴 FINALIZAR CONFIGURAÇÃO", callback_data="finalizar_midias")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Verifica se já tem mídias
            count = manager.get_medias_count(context.bot_data['id'])
            
            await query.message.edit_text(
                f"📸 Envie suas mídias (até 10)\n"
                f"Quando terminar, clique em FINALIZAR\n\n"
                f"📊 Mídias atuais: {count}/10",  # Mostra quantas já tem
                reply_markup=reply_markup
            )
            return AGUARDANDO_MIDIAS
            
        elif acao == "texto1":
            await query.message.edit_text(
                "📝 Envie o Texto 1\\.\n\n"
                ">𝗖𝗼𝗺𝗼 𝗳𝘂𝗻𝗰𝗶𝗼𝗻𝗮\\? Este texto será enviado DEPOIS das mídias \\(se houver\\)\\.", 
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
        elif acao == "texto2":
            await query.message.edit_text(
                "📝 Envie o Texto 2\\.\n\n"
                ">𝗖𝗼𝗺𝗼 𝗳𝘂𝗻𝗰𝗶𝗼𝗻𝗮\\? Este texto será enviado junto com o botão de ofertas\\.", 
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
        return INICIO_RECEBER

async def inicio_receber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    acao = context.user_data.get('inicio_acao')
    mensagem = update.message.text if update.message else None
    
    try:
        if acao in ["texto1", "texto2"]:
            if not update.message.text or update.message.photo or update.message.video or update.message.sticker or update.message.document or update.message.audio or update.message.voice or update.message.video_note or update.message.animation:
                await update.message.reply_text("⛔ Por favor, envie apenas texto.", reply_markup=cancel_markup)
                return INICIO_RECEBER
            
            context.user_data['inicio_context'][acao] = mensagem
            
            if acao == "texto1":
                await update.message.reply_text("✅ Texto 1 atualizado com sucesso.")
            else:
                await update.message.reply_text("✅ Texto 2 atualizado com sucesso.")
            
            manager.update_bot_config(context.bot_data['id'], context.user_data['inicio_context'])
            
        elif acao == "botao":
            if not update.message.text or update.message.photo or update.message.video or update.message.sticker or update.message.document or update.message.audio or update.message.voice or update.message.video_note or update.message.animation:
                await update.message.reply_text("⛔ Por favor, envie apenas texto.", reply_markup=cancel_markup)
                return INICIO_RECEBER
            context.user_data['inicio_context']['button'] = mensagem
            await update.message.reply_text("✅ Texto do botão inicial atualizado com sucesso.")
            manager.update_bot_config(context.bot_data['id'], context.user_data['inicio_context'])

    except Exception as e:
        print(f'Erro ao modificar inicio: {e}')
        await update.message.reply_text(f"⛔ Erro ao modificar o inicio: {str(e)}")
        context.user_data['conv_state'] = False
        return ConversationHandler.END

    context.user_data['conv_state'] = False
    return ConversationHandler.END

# NOVO: Função para aguardar mídias
async def aguardar_midias(update: Update, context: CallbackContext):
    """Recebe mídias continuamente até o usuário finalizar"""
    
    # Verifica se é foto ou vídeo
    if not (update.message.photo or update.message.video):
        await update.message.reply_text("⛔️ Por favor, envie apenas fotos ou vídeos.")
        return AGUARDANDO_MIDIAS
    
    # NOVO: Se está aguardando primeira mídia, limpa tudo antes
    if context.user_data.get('aguardando_primeira_midia'):
        manager.clear_medias_config(context.bot_data['id'])
        context.user_data['aguardando_primeira_midia'] = False
        print("[INICIO] Mídias anteriores limpas, iniciando nova configuração")
    
    # Verifica limite
    count = manager.get_medias_count(context.bot_data['id'])
    if count >= 10:
        keyboard = [[InlineKeyboardButton("🔴 FINALIZAR CONFIGURAÇÃO", callback_data="finalizar_midias")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ Limite máximo de 10 mídias atingido!\n"
            "Clique em FINALIZAR para continuar.",
            reply_markup=reply_markup
        )
        return AGUARDANDO_MIDIAS
    
    # Adiciona a mídia
    try:
        # MUDANÇA: REMOVE O TIMEOUT COMPLETAMENTE!
        if update.message.photo:
            # Pega o file_id direto, sem baixar o arquivo
            file_id = update.message.photo[-1].file_id
            media_type = 'photo'
        else:
            # Pega o file_id direto, sem baixar o arquivo
            file_id = update.message.video.file_id
            media_type = 'video'
        
        # Adiciona no array usando o file_id direto
        manager.add_media_to_config(context.bot_data['id'], {
            'type': media_type,
            'file': file_id  # Usa o file_id direto!
        })
        
        # Se for a primeira, salva também como mídia principal (compatibilidade)
        if count == 0:
            config = manager.get_bot_config(context.bot_data['id'])
            config['midia'] = {
                'type': media_type,
                'file': file_id
            }
            manager.update_bot_config(context.bot_data['id'], config)
        
        # Pega informações atualizadas
        info = manager.get_medias_info(context.bot_data['id'])
        
        # Monta mensagem de status
        status_text = f"✅ Mídia {info['total']} adicionada\n\n"
        status_text += f"📊 Status: {info['total']}/10 mídias\n"
        if info['photos'] > 0:
            status_text += f"• {info['photos']} foto(s)\n"
        if info['videos'] > 0:
            status_text += f"• {info['videos']} vídeo(s)\n"
        status_text += "\nContinue enviando ou finalize:"
        
        keyboard = [[InlineKeyboardButton("🔴 FINALIZAR CONFIGURAÇÃO", callback_data="finalizar_midias")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(status_text, reply_markup=reply_markup)
        
    except Exception as e:
        print(f"Erro ao adicionar mídia: {e}")
        await update.message.reply_text(
            f"⛔ Erro ao adicionar mídia.\n"
            "Tente novamente ou finalize a configuração."
        )
        keyboard = [[InlineKeyboardButton("🔴 FINALIZAR CONFIGURAÇÃO", callback_data="finalizar_midias")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Opções:", reply_markup=reply_markup)
    
    return AGUARDANDO_MIDIAS

# NOVO: Função para finalizar configuração de mídias
async def finalizar_midias(update: Update, context: CallbackContext):
    """Finaliza a configuração de mídias e pergunta o modo de exibição"""
    query = update.callback_query
    await query.answer()
    
    # Pega informações das mídias
    info = manager.get_medias_info(context.bot_data['id'])
    
    # NOVO: Se ainda estava aguardando primeira mídia, não enviou nada
    if context.user_data.get('aguardando_primeira_midia'):
        await query.edit_message_text(
            f"✅ Configuração mantida!\n\n"
            f"Você tem {info['total']} mídia(s) configurada(s).\n\n"
            f"Use /start para testar"
        )
        context.user_data['conv_state'] = False
        context.user_data['aguardando_primeira_midia'] = False
        return ConversationHandler.END
    
    # Se tem 0 mídias (limpou mas não adicionou novas)
    if info['total'] == 0:
        await query.edit_message_text(
            "⚠️ Nenhuma mídia foi adicionada.\n"
            "As mídias anteriores foram removidas."
        )
        context.user_data['conv_state'] = False
        return ConversationHandler.END
    
    # Se tem só 1 mídia, finaliza direto
    if info['total'] == 1:
        await query.edit_message_text(
            f"✅ Configuração concluída!\n\n"
            f"• 1 mídia salva\n\n"
            f"Use /start para testar"
        )
        context.user_data['conv_state'] = False
        return ConversationHandler.END
    
    # Se tem múltiplas, pergunta o modo
    keyboard = [
        [InlineKeyboardButton("📷 Uma por vez (Sequencial)", callback_data="mode_sequential")],
        [InlineKeyboardButton("🎞️ Todas juntas (Album)", callback_data="mode_album")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status = f"📊 Você adicionou {info['total']} mídias"
    if info['photos'] > 0 and info['videos'] > 0:
        status += f" ({info['photos']} fotos, {info['videos']} vídeos)"
    
    await query.edit_message_text(
        f"{status}\n\n"
        "Como deseja exibir para os usuários?\n\n"
        "⚠️ Nota: Album funciona melhor com mídias do mesmo tipo",
        reply_markup=reply_markup
    )
    
    return ESCOLHER_MODO_MIDIA

# Função para escolher modo de exibição
async def escolher_modo_midia(update: Update, context: CallbackContext):
    """Processa a escolha do modo de exibição"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "mode_sequential":
        manager.set_media_display_mode(context.bot_data['id'], 'sequential')
        modo = "Sequencial (uma por vez)"
    elif query.data == "mode_album":
        manager.set_media_display_mode(context.bot_data['id'], 'album')
        modo = "Album (todas juntas)"
    
    info = manager.get_medias_info(context.bot_data['id'])
    
    await query.edit_message_text(
        f"✅ Configuração concluída!\n\n"
        f"• {info['total']} mídias salvas\n"
        f"• Modo: {modo}\n\n"
        f"Use /start para testar"
    )
    
    context.user_data['conv_state'] = False
    return ConversationHandler.END

conv_handler_inicio = ConversationHandler(
    entry_points=[CommandHandler("inicio", inicio)],
    states={
        INICIO_ESCOLHA: [CallbackQueryHandler(inicio_escolha)],
        INICIO_ADICIONAR_OU_DELETAR: [CallbackQueryHandler(inicio_adicionar_ou_deletar)],
        INICIO_RECEBER: [MessageHandler(filters.ALL, inicio_receber)],
        # NOVO ESTADO: Aguardando múltiplas mídias
        AGUARDANDO_MIDIAS: [
            MessageHandler(filters.PHOTO | filters.VIDEO, aguardar_midias),
            CallbackQueryHandler(finalizar_midias, pattern="^finalizar_midias$")
        ],
        ESCOLHER_MODO_MIDIA: [
            CallbackQueryHandler(escolher_modo_midia, pattern="^mode_(sequential|album)$")
        ]
    },
    fallbacks=[CallbackQueryHandler(cancel)],
)
