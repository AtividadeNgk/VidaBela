import modules.manager as manager
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from modules.utils import process_command, is_admin, cancel, error_callback

UPSELL_ESCOLHA, UPSELL_RECEBER, UPSELL_VALOR, UPSELL_GRUPO = range(4)

keyboardc = [
    [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
]
cancel_markup = InlineKeyboardMarkup(keyboardc)

async def upsell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command_check = await process_command(update, context)
    if not command_check:
        return ConversationHandler.END
    
    if not await is_admin(context, update.message.from_user.id):
        return ConversationHandler.END
    
    context.user_data['conv_state'] = "upsell"

    keyboard = [
        [InlineKeyboardButton("Adicionar", callback_data="adicionar"), InlineKeyboardButton("Remover", callback_data="remover")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📈 O que deseja fazer com o Upsell?\n\n"
        ">𝗖𝗼𝗺𝗼 𝗳𝘂𝗻𝗰𝗶𝗼𝗻𝗮\\? Após o cliente finalizar a primeira compra, o bot envia automaticamente uma segunda oferta para o cliente\\.",
        reply_markup=reply_markup,
        parse_mode='MarkdownV2'
    )
    return UPSELL_ESCOLHA

async def upsell_escolha(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END
    
    elif query.data == 'adicionar':
        context.user_data['upsell_context'] = {
            'media': False,
            'text': False,
            'value': False,
            'group_id': False
        }
        await query.message.edit_text(
            "💬 Envie a mensagem para o upsell, pode conter mídia.",
            reply_markup=cancel_markup
        )
        return UPSELL_RECEBER
    
    elif query.data == 'remover':
        manager.update_bot_upsell(context.bot_data['id'], {})
        await query.message.edit_text("✅ Upsell removido com sucesso!")
        context.user_data['conv_state'] = False
        return ConversationHandler.END

async def upsell_receber_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        save = {
            'media': False,
            'text': False
        }
        
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            save['media'] = {
                'file': photo_file.file_id,
                'type': 'photo'
            }
        elif update.message.video:
            video_file = await update.message.video.get_file()
            save['media'] = {
                'file': video_file.file_id,
                'type': 'video'
            }
        elif update.message.text:
            save['text'] = update.message.text
        else:
            await update.message.reply_text("⛔ Somente texto ou mídia:", reply_markup=cancel_markup)
            return UPSELL_RECEBER

        if update.message.caption:
            save['text'] = update.message.caption

        context.user_data['upsell_context']['media'] = save['media']
        context.user_data['upsell_context']['text'] = save['text']
        
        await update.message.reply_text(
            "💰 Envie o valor do upsell.",
            reply_markup=cancel_markup
        )
        return UPSELL_VALOR
        
    except Exception as e:
        await update.message.reply_text(f"⛔ Erro ao salvar upsell: {str(e)}")
        context.user_data['conv_state'] = False
        return ConversationHandler.END

async def upsell_valor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        await update.message.reply_text("⛔️ Por favor, envie apenas números.", reply_markup=cancel_markup)
        return UPSELL_VALOR
    
    try:
        valor = float(update.message.text.replace(',', '.'))
        if valor <= 0:
            await update.message.reply_text("⛔ O valor deve ser maior que zero:", reply_markup=cancel_markup)
            return UPSELL_VALOR
        
        context.user_data['upsell_context']['value'] = valor
        
        await update.message.reply_text(
            "🌟 Envie o ID do Grupo VIP do Upsell\n\n"
            ">𝗖𝗼𝗺𝗼 𝗳𝘂𝗻𝗰𝗶𝗼𝗻𝗮\\? Envie aqui o ID do Grupo VIP que o cliente terá acesso após comprar o seu Upsell\\.",
            reply_markup=cancel_markup,
            parse_mode='MarkdownV2'
        )
        return UPSELL_GRUPO
        
    except ValueError:
        await update.message.reply_text("⛔️ Por favor, envie apenas números.", reply_markup=cancel_markup)
        return UPSELL_VALOR

async def upsell_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    id_recebido = update.message.text.strip()
    
    if not id_recebido.lstrip('-').isdigit():
        await update.message.reply_text("❌ Insira um ID válido:", reply_markup=cancel_markup)
        return UPSELL_GRUPO
    
    # Testa se o bot tem acesso ao grupo
    try:
        chat = await context.bot.get_chat(id_recebido)
        id_grupo = id_recebido
        nome_grupo = chat.title
    except:
        try:
            # Tenta com -100
            id_grupo = id_recebido.replace('-', '-100')
            chat = await context.bot.get_chat(id_grupo)
            nome_grupo = chat.title
        except:
            await update.message.reply_text(
                "⛔️ ID inválido ou incorreto\\.\n\n"
                ">𝗔𝘃𝗶𝘀𝗼\\: Certifique\\-se que o bot está como administrador no grupo do Upsell com todas as permissões habilitadas\\.",
                reply_markup=cancel_markup,
                parse_mode='MarkdownV2'
            )
            return UPSELL_GRUPO
    
    context.user_data['upsell_context']['group_id'] = id_grupo
    
    # Salva o upsell
    upsell_data = context.user_data['upsell_context']
    manager.update_bot_upsell(context.bot_data['id'], upsell_data)
    
    await update.message.reply_text(
        f"✅ 𝗨𝗽𝘀𝗲𝗹𝗹 𝗰𝗼𝗻𝗳𝗶𝗴𝘂𝗿𝗮𝗱𝗼!\n\n"
        f"💰 Valor: R$ {upsell_data['value']:.2f}\n"
        f"🫂 Grupo: {nome_grupo}"
    )
    
    context.user_data['conv_state'] = False
    return ConversationHandler.END

conv_handler_upsell = ConversationHandler(
    entry_points=[CommandHandler("upsell", upsell)],
    states={
        UPSELL_ESCOLHA: [CallbackQueryHandler(upsell_escolha)],
        UPSELL_RECEBER: [MessageHandler(~filters.COMMAND, upsell_receber_mensagem), CallbackQueryHandler(cancel)],
        UPSELL_VALOR: [MessageHandler(~filters.COMMAND, upsell_valor), CallbackQueryHandler(cancel)],
        UPSELL_GRUPO: [MessageHandler(~filters.COMMAND, upsell_grupo), CallbackQueryHandler(cancel)]
    },
    fallbacks=[CallbackQueryHandler(error_callback)]
)
