import modules.manager as manager 
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from modules.utils import process_command, is_admin, cancel, error_callback

UTMIFY_ESCOLHA, UTMIFY_RECEBER_TOKEN = range(2)

keyboardc = [
    [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
]
cancel_markup = InlineKeyboardMarkup(keyboardc)

async def utmify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command_check = await process_command(update, context)
    if not command_check:
        return ConversationHandler.END
    
    if not await is_admin(context, update.message.from_user.id):
        return ConversationHandler.END
    
    context.user_data['conv_state'] = "utmify"
    
    # Verifica se já tem configuração
    utmify_config = manager.get_utmify_config(context.bot_data['id'])
    
    keyboard = []
    
    if utmify_config:
        status = "✅ Ativada" if utmify_config['enabled'] else "❌ Desativada"
        keyboard.append([InlineKeyboardButton(f"Status: {status}", callback_data="none")])
        keyboard.append([
            InlineKeyboardButton("♻️ Trocar Token", callback_data="trocar"),
            InlineKeyboardButton("🧹 Remover", callback_data="remover")
        ])
    else:
        keyboard.append([InlineKeyboardButton("➕ Adicionar", callback_data="adicionar")])
    
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📊 𝗖𝗼𝗻𝗳𝗶𝗴𝘂𝗿𝗮𝗰̧𝗮̃𝗼 𝗨𝘁𝗺𝗶𝗳𝘆\n\n"
        "Como funciona? A Utmify permite rastreamento avançado das suas campanhas. "
        "Você verá exatamente qual anúncio gerou cada venda.\n\n"
        "📌 Para obter o token:\n"
        "1. Acesse sua conta Utmify\n"
        "2. Vá em Integrações > Webhooks\n"
        "3. Crie uma credencial de API\n"
        "4. Copie o token gerado",
        reply_markup=reply_markup
    )
    return UTMIFY_ESCOLHA

async def utmify_escolha(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END
    
    elif query.data == 'none':
        return UTMIFY_ESCOLHA
    
    elif query.data in ['adicionar', 'trocar']:
        await query.message.edit_text(
            "🔑 Envie o token da API da Utmify\\:\n\n"
            "Exemplo\\: `KVRxalfMiBfm8Rm1nP5YxfwYzArNsA0VLeWC`",
            reply_markup=cancel_markup,
            parse_mode='MarkdownV2'
        )
        return UTMIFY_RECEBER_TOKEN
    
    elif query.data == 'remover':
        manager.remove_utmify_config(context.bot_data['id'])
        await query.message.edit_text("✅ Configuração Utmify removida com sucesso!")
        context.user_data['conv_state'] = False
        return ConversationHandler.END

async def utmify_receber_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        await update.message.reply_text("⛔ Por favor, envie apenas o token:", reply_markup=cancel_markup)
        return UTMIFY_RECEBER_TOKEN
    
    token = update.message.text.strip()
    
    # Validação básica do formato do token
    if len(token) < 20 or len(token) > 100:
        await update.message.reply_text(
            "⛔ Token inválido! Verifique se copiou corretamente.",
            reply_markup=cancel_markup
        )
        return UTMIFY_RECEBER_TOKEN
    
    # Salva a configuração
    manager.save_utmify_config(context.bot_data['id'], token)
    
    await update.message.reply_text(
        "✅ 𝗨𝘁𝗺𝗶𝗳𝘆 𝗰𝗼𝗻𝗳𝗶𝗴𝘂𝗿𝗮𝗱𝗮 𝗰𝗼𝗺 𝘀𝘂𝗰𝗲𝘀𝘀𝗼!\n\n"
        "📊 Agora você receberá tracking avançado de:\n"
        "• Qual campanha gerou cada venda\n"
        "• Qual conjunto de anúncios\n"
        "• Qual anúncio específico\n"
        "• ROAS real por criativo\n\n"
        "💡 Acesse seu painel Utmify para ver os resultados!"
    )
    
    context.user_data['conv_state'] = False
    return ConversationHandler.END

conv_handler_utmify = ConversationHandler(
    entry_points=[CommandHandler("utmify", utmify)],
    states={
        UTMIFY_ESCOLHA: [CallbackQueryHandler(utmify_escolha)],
        UTMIFY_RECEBER_TOKEN: [MessageHandler(~filters.COMMAND, utmify_receber_token), CallbackQueryHandler(cancel)]
    },
    fallbacks=[CallbackQueryHandler(error_callback)]

)
