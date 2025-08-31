import modules.manager as manager
import json, re, requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters, Updater, CallbackContext, ChatJoinRequestHandler
from telegram.error import BadRequest, Conflict
from modules.utils import process_command, is_admin, error_callback, escape_markdown_v2, cancel

GRUPO_ESCOLHA, GRUPO_RECEBER = range(2)

# Comando para receber id do grupo
# /vip função
async def grupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command_check = await process_command(update, context)
    if not command_check:
        return ConversationHandler.END
    
    if not await is_admin(context, update.message.from_user.id):
        return ConversationHandler.END
    
    context.user_data['conv_state'] = "grupo"
    
    # Verifica se já tem grupo configurado
    grupo_atual = manager.get_bot_group(context.bot_data['id'])
    
    if grupo_atual:
        keyboard = [
            [InlineKeyboardButton("♻️ Trocar ID", callback_data="trocar")],
            [InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("🟢 Adicionar", callback_data="adicionar")],
            [InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🌟 O que você desejar fazer com o Grupo VIP?\n\n"
        ">𝗖𝗼𝗺𝗼 𝗳𝘂𝗻𝗰𝗶𝗼𝗻𝗮\\? Esse comando é usado para definir o ID do seu Grupo VIP\\. Quando os clientes comprarem, receberá o link de acesso do Grupo VIP definido\\.",
        reply_markup=reply_markup,
        parse_mode='MarkdownV2'
    )
    return GRUPO_ESCOLHA

async def grupo_escolha(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END
    
    elif query.data in ['adicionar', 'trocar']:
        keyboard = [[InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(
            "🔗 Envie o ID do Grupo VIP.",
            reply_markup=reply_markup
        )
        return GRUPO_RECEBER

async def recebe_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    id_recebido = update.message.text.strip()
    keyboard = [[InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    id_grupo = ''
    
    if not id_recebido.lstrip('-').isdigit():
        await update.message.reply_text("❌ Insira um ID valido:", reply_markup=reply_markup)
        return GRUPO_RECEBER
    
    invite_link = ''
    chat_info = None
    try:
        chat_info = await context.bot.get_chat(id_recebido)
        invite_link = await context.bot.create_chat_invite_link(chat_id=id_recebido, member_limit=1, creates_join_request=False)
        id_grupo = id_recebido
    except:
        try:
            id_grupo = id_recebido.replace('-', '-100')
            chat_info = await context.bot.get_chat(id_grupo)
            invite_link = await context.bot.create_chat_invite_link(chat_id=id_grupo, member_limit=1, creates_join_request=False)
        except:
            await update.message.reply_text(
                "⛔️ ID inválido ou Bot sem permissões\\.\n\n"
                ">⚠️ 𝗔𝗟𝗘𝗥𝗧𝗔\\: O bot precisa estar adicionado no grupo VIP com todas as permissões habilitadas\\.",
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
            return GRUPO_RECEBER
    
    manager.update_bot_group(context.bot_data['id'], id_grupo)
    
    # Pega o nome do grupo
    nome_grupo = chat_info.title if chat_info else "Grupo VIP"
    
    await update.message.reply_text(
        f"✅ 𝗚𝗥𝗨𝗣𝗢 𝗩𝗜𝗣 𝗗𝗘𝗙𝗜𝗡𝗜𝗗𝗢\\.\n\n"
        f"― *Nome*: {escape_markdown_v2(nome_grupo)}\n"
        f"― *ID*: {escape_markdown_v2(id_grupo)}\n"
        f"― *LINK*: {escape_markdown_v2(invite_link.invite_link)}\n\n"
        f">Agora, todos os usuários que comprarem no seu bot, receberá esse Grupo VIP\\.",
        parse_mode='MarkdownV2'
    )
    
    context.user_data['conv_state'] = False
    return ConversationHandler.END

conv_handler_grupo = ConversationHandler(
    entry_points=[CommandHandler("vip", grupo)],
    states={
        GRUPO_ESCOLHA: [CallbackQueryHandler(grupo_escolha)],
        GRUPO_RECEBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, recebe_grupo), CallbackQueryHandler(cancel)]
    },
    fallbacks=[CallbackQueryHandler(error_callback)]
)
