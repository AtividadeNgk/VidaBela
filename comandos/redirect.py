import modules.manager as manager
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from modules.utils import process_command, is_admin, cancel

# Estados do conversation handler
REDIRECT_ESCOLHA, REDIRECT_TEXTO, REDIRECT_LINK = range(3)

async def redirect(update: Update, context: CallbackContext):
    # Verifica se já está no comando redirect
    if context.user_data.get('conv_state') == 'redirect':
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton('❌ Cancelar comando', callback_data='cancelar')]])
        await update.message.reply_text(
            '⚠️ O comando /redirect já está em execução!\n\n'
            'Você estava no meio da configuração.\n'
            'Cancele para recomeçar.',
            reply_markup=keyboard
        )
        return ConversationHandler.END
    
    # Verifica outros comandos
    command_check = await process_command(update, context)
    if not command_check:
        return ConversationHandler.END
    
    if not await is_admin(context, update.message.from_user.id):
        return ConversationHandler.END
    
    context.user_data['conv_state'] = 'redirect'
    
    keyboard = [
        [InlineKeyboardButton("🟢 Adicionar", callback_data="add_redirect"), 
         InlineKeyboardButton("🧹 Remover", callback_data="remove_redirect")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔗 Selecione o que deseja fazer com o botão de redirecionamento:\n\n"
        "Este botão aparecerá abaixo do botão de ofertas no /start",
        reply_markup=reply_markup
    )
    
    return REDIRECT_ESCOLHA

async def redirect_escolha(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END
    
    config = manager.get_bot_config(context.bot_data['id'])
    
    if query.data == 'remove_redirect':
        # Verifica se existe botão configurado
        if not config.get('redirect_button'):
            await query.message.edit_text("❌ Não há botão de redirecionamento configurado.")
            context.user_data.clear()
            return ConversationHandler.END
        
        # Remove o botão
        config['redirect_button'] = None
        manager.update_bot_config(context.bot_data['id'], config)
        
        await query.message.edit_text("✅ Botão de redirecionamento removido com sucesso!")
        context.user_data.clear()
        return ConversationHandler.END
    
    elif query.data == 'add_redirect':
        keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(
            "📝 Digite o texto que aparecerá no botão:\n\n"
            "Exemplo: 📱 Siga no Instagram",
            reply_markup=reply_markup
        )
        return REDIRECT_TEXTO

async def redirect_texto(update: Update, context: CallbackContext):
    # Verifica se é texto
    if not update.message.text:
        keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⛔ Por favor, envie apenas texto.",
            reply_markup=reply_markup
        )
        return REDIRECT_TEXTO
    
    # Salva o texto temporariamente
    context.user_data['redirect_text'] = update.message.text
    
    keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔗 Agora digite o link de redirecionamento:\n\n"
        "Exemplo: https://instagram.com/seuusuario",
        reply_markup=reply_markup
    )
    
    return REDIRECT_LINK

async def redirect_link(update: Update, context: CallbackContext):
    # Verifica se é texto
    if not update.message.text:
        keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⛔ Por favor, envie o link.",
            reply_markup=reply_markup
        )
        return REDIRECT_LINK
    
    # Pega o link
    link = update.message.text.strip()
    
    # Se não tem http, adiciona
    if not link.startswith(('http://', 'https://')):
        link = 'https://' + link
    
    # Salva no banco
    config = manager.get_bot_config(context.bot_data['id'])
    config['redirect_button'] = {
        'text': context.user_data['redirect_text'],
        'url': link
    }
    manager.update_bot_config(context.bot_data['id'], config)
    
    await update.message.reply_text(
        f"✅ Botão de redirecionamento configurado com sucesso!\n\n"
        f"📝 Texto: {context.user_data['redirect_text']}\n"
        f"🔗 Link: {link}\n\n"
        f"Use /start para testar!"
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# Conversation Handler
conv_handler_redirect = ConversationHandler(
    entry_points=[CommandHandler("redirect", redirect)],
    states={
        REDIRECT_ESCOLHA: [CallbackQueryHandler(redirect_escolha)],
        REDIRECT_TEXTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, redirect_texto)],
        REDIRECT_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, redirect_link)]
    },
    fallbacks=[CallbackQueryHandler(cancel)]
)
