import modules.manager as manager
import json
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from modules.utils import process_command, cancel, error_callback

SUPORTE_RECEBER = 0

async def suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Pega quem está usando o comando
    user_id = str(update.message.from_user.id)
    
    # Verifica se já tem um owner definido
    owner_id = manager.get_registro_owner()
    
    if owner_id:
        # Se já tem owner, verifica se é ele
        if user_id != owner_id:
            await update.message.reply_text("⛔ Apenas o owner pode configurar o suporte.")
            return ConversationHandler.END
    else:
        # Se não tem owner ainda, define o primeiro que usar como owner
        manager.set_registro_owner(user_id)
        owner_id = user_id
    
    context.user_data['conv_state'] = "suporte"
    
    keyboard = [[InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Verifica se já existe suporte configurado
    current_support = manager.get_registro_support()
    if current_support:
        await update.message.reply_text(
            f"📞 <b>Suporte Atual:</b> @{current_support}\n\n"
            "Envie o novo @ do suporte (sem o @):",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "📞 Envie o @ do suporte (sem o @):",
            reply_markup=reply_markup
        )
    
    return SUPORTE_RECEBER

async def recebe_suporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        await update.message.reply_text("⛔ Por favor, envie apenas o username do suporte")
        return SUPORTE_RECEBER
    
    username = update.message.text.strip().replace('@', '')
    
    # Salva o username do suporte
    manager.set_registro_support(username)
    
    await update.message.reply_text(
        f"✅ <b>Suporte configurado com sucesso!</b>\n\n"
        f"📞 Novo suporte: @{username}",
        parse_mode='HTML'
    )
    
    context.user_data['conv_state'] = False
    return ConversationHandler.END

conv_handler_suporte = ConversationHandler(
    entry_points=[CommandHandler("suporte", suporte)],
    states={
        SUPORTE_RECEBER: [MessageHandler(~filters.COMMAND, recebe_suporte), CallbackQueryHandler(cancel)]
    },
    fallbacks=[CallbackQueryHandler(error_callback)]
)