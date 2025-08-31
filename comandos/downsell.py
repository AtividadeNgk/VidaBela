import modules.manager as manager
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from modules.utils import process_command, is_admin, cancel, error_callback

DOWNSELL_ESCOLHA, DOWNSELL_RECEBER, DOWNSELL_VALOR = range(3)

keyboardc = [
    [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
]
cancel_markup = InlineKeyboardMarkup(keyboardc)

async def downsell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command_check = await process_command(update, context)
    if not command_check:
        return ConversationHandler.END
    
    if not await is_admin(context, update.message.from_user.id):
        return ConversationHandler.END
    
    context.user_data['conv_state'] = "downsell"
    
    # Verifica se existe upsell configurado
    upsell_config = manager.get_bot_upsell(context.bot_data['id'])
    if not upsell_config or not upsell_config.get('group_id'):
        await update.message.reply_text(
            "⛔ Configure o upsell primeiro!\n"
            "O downsell usa o mesmo grupo VIP do upsell."
        )
        context.user_data['conv_state'] = False
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("➕ ADICIONAR", callback_data="adicionar"), InlineKeyboardButton("➖ REMOVER", callback_data="remover")],
        [InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📉 O que deseja fazer com o Downsell?\n\n"
        ">𝗖𝗼𝗺𝗼 𝗳𝘂𝗻𝗰𝗶𝗼𝗻𝗮\\? Quando o cliente recusar o upsell, o bot envia automaticamente uma última oferta com desconto maior\\.",
        reply_markup=reply_markup,
        parse_mode='MarkdownV2'
    )
    return DOWNSELL_ESCOLHA

async def downsell_escolha(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END
    
    elif query.data == 'adicionar':
        context.user_data['downsell_context'] = {
            'media': False,
            'text': False,
            'value': False
        }
        await query.message.edit_text(
            "💬 Envie a mensagem para o downsell, pode conter mídia.",
            reply_markup=cancel_markup
        )
        return DOWNSELL_RECEBER
    
    elif query.data == 'remover':
        manager.update_bot_downsell(context.bot_data['id'], {})
        await query.message.edit_text("✅ Downsell removido com sucesso!")
        context.user_data['conv_state'] = False
        return ConversationHandler.END

async def downsell_receber_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            return DOWNSELL_RECEBER

        if update.message.caption:
            save['text'] = update.message.caption

        context.user_data['downsell_context']['media'] = save['media']
        context.user_data['downsell_context']['text'] = save['text']
        
        # Pega o valor do upsell para referência
        upsell_config = manager.get_bot_upsell(context.bot_data['id'])
        upsell_value = upsell_config.get('value', 0)
        
        await update.message.reply_text(
            "💰 Envie o valor do downsell\\.\n\n"
            ">𝗗𝗶𝗰𝗮\\: Use um valor menor que o upsell para incentivar o cliente aceitar a oferta\\.",
            reply_markup=cancel_markup,
            parse_mode='MarkdownV2'
        )
        return DOWNSELL_VALOR
        
    except Exception as e:
        await update.message.reply_text(f"⛔ Erro ao salvar downsell: {str(e)}")
        context.user_data['conv_state'] = False
        return ConversationHandler.END

async def downsell_valor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        await update.message.reply_text("⛔ Por favor, envie apenas o valor numérico:", reply_markup=cancel_markup)
        return DOWNSELL_VALOR
    
    try:
        valor = float(update.message.text.replace(',', '.'))
        if valor <= 0:
            await update.message.reply_text("⛔ O valor deve ser maior que zero:", reply_markup=cancel_markup)
            return DOWNSELL_VALOR
        
        context.user_data['downsell_context']['value'] = valor
        
        # Salva o downsell
        downsell_data = context.user_data['downsell_context']
        manager.update_bot_downsell(context.bot_data['id'], downsell_data)
        
        # Pega o valor do upsell para calcular desconto
        upsell_config = manager.get_bot_upsell(context.bot_data['id'])
        upsell_value = upsell_config.get('value', 0)
        
        # Monta a mensagem base
        mensagem = (
            f"✅ 𝗗𝗼𝘄𝗻𝘀𝗲𝗹𝗹 𝗰𝗼𝗻𝗳𝗶𝗴𝘂𝗿𝗮𝗱𝗼!\n\n"
            f"💰 Valor do upsell: R$ {upsell_value:.2f}\n"
            f"💸 Valor do downsell: R$ {valor:.2f}"
        )
        
        # Adiciona desconto apenas se o downsell for menor que o upsell
        if valor < upsell_value:
            desconto = int(((upsell_value - valor) / upsell_value) * 100)
            mensagem += f"\n🏷 Desconto: {desconto}%"
        
        await update.message.reply_text(mensagem)
        
        context.user_data['conv_state'] = False
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("⛔ Envie um valor numérico válido:", reply_markup=cancel_markup)
        return DOWNSELL_VALOR

conv_handler_downsell = ConversationHandler(
    entry_points=[CommandHandler("downsell", downsell)],
    states={
        DOWNSELL_ESCOLHA: [CallbackQueryHandler(downsell_escolha)],
        DOWNSELL_RECEBER: [MessageHandler(~filters.COMMAND, downsell_receber_mensagem), CallbackQueryHandler(cancel)],
        DOWNSELL_VALOR: [MessageHandler(~filters.COMMAND, downsell_valor), CallbackQueryHandler(cancel)]
    },
    fallbacks=[CallbackQueryHandler(error_callback)]
)
