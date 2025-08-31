import modules.manager as manager
import json, re, requests

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters, Updater, CallbackContext, ChatJoinRequestHandler
from telegram.error import BadRequest, Conflict

from modules.utils import process_command, is_admin, error_callback, error_message, cancel

EXPIRACAO_RECEBER, EXPIRACAO_ESCOLHA, EXPIRACAO_CONFIRMAR = range(3)

#comando adeus
async def adeus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command_check = await process_command(update, context)
    planos = manager.get_bot_plans(context.bot_data['id'])
    if not command_check:
        return ConversationHandler.END
    if not await is_admin(context, update.message.from_user.id):
        return ConversationHandler.END
    context.user_data['conv_state'] = "adeus"

    keyboard = [
            [InlineKeyboardButton("🟢 Adicionar", callback_data="adicionar"), InlineKeyboardButton("🧹 Remover", callback_data="remover")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⏳ O que deseja fazer com a mensagem de expiração?\n\n"
        ">𝗖𝗼𝗺𝗼 𝗳𝘂𝗻𝗰𝗶𝗼𝗻𝗮\\? Defina a mensagem que o cliente vai receber após o plano dele vencer\\. Abaixo da mensagem definida, aparecerá um botão para renovar a assinatura\\.",
        reply_markup=reply_markup,
        parse_mode='MarkdownV2'
    )
    return EXPIRACAO_ESCOLHA

async def adeus_escolha(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END
    elif query.data == 'adicionar':
        keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            "💬 Envie a mensagem de expiração, pode conter mídia.",
            reply_markup=reply_markup
        )
        return EXPIRACAO_RECEBER
    elif query.data == 'remover':
        manager.update_bot_expiration(context.bot_data['id'], {}) 
        await query.message.edit_text("✅ Expiração deletada com sucesso")
        context.user_data['conv_state'] = False
        return ConversationHandler.END

async def adeus_receber_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        save = {
            'media':False,
            'text':False
        }
        
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            save['media'] = {
                'file':photo_file.file_id,
                'type':'photo'
            }
        elif update.message.video:
            video_file = await update.message.video.get_file()
            save['media'] = {
                'file':video_file.file_id,
                'type':'video'
            }
        elif update.message.text:
            save['text'] = update.message.text
        else: 
            await update.message.reply_text("⛔ Somente texto ou midia:")
            return EXPIRACAO_RECEBER
            
        if update.message.caption:
            save['text'] = update.message.caption

        # Salva temporariamente no contexto
        context.user_data['expiracao_temp'] = save
        
        # Envia prévia da mensagem
        await update.message.reply_text("👁 𝗣𝗿𝗲́𝘃𝗶𝗮 𝗱𝗮 𝗺𝗲𝗻𝘀𝗮𝗴𝗲𝗺 𝗱𝗲 𝗲𝘅𝗽𝗶𝗿𝗮𝗰̧𝗮̃𝗼:")
        
        # Cria o botão de renovação
        keyboard_preview = [[InlineKeyboardButton("♻️ 𝗥𝗲𝗻𝗼𝘃𝗮𝗿 𝗔𝘀𝘀𝗶𝗻𝗮𝘁𝘂𝗿𝗮", callback_data="renovar_exemplo")]]
        reply_markup_preview = InlineKeyboardMarkup(keyboard_preview)
        
        # Envia a prévia baseado no tipo de conteúdo
        if save['media']:
            if save['media']['type'] == 'photo':
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=save['media']['file'],
                    caption=save['text'] if save['text'] else None,
                    reply_markup=reply_markup_preview
                )
            else:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=save['media']['file'],
                    caption=save['text'] if save['text'] else None,
                    reply_markup=reply_markup_preview
                )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=save['text'],
                reply_markup=reply_markup_preview
            )
        
        # Pergunta se confirma
        keyboard = [
            [InlineKeyboardButton("✅ CONFIRMAR", callback_data="confirmar_exp")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Deseja salvar esta mensagem de expiração?",
            reply_markup=reply_markup
        )
        
        return EXPIRACAO_CONFIRMAR
        
    except Exception as e:
        await update.message.reply_text(text=f"⛔ Erro ao processar mensagem: {str(e)}")
        context.user_data['conv_state'] = False
        return ConversationHandler.END

async def adeus_confirmar(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END
    
    elif query.data == 'confirmar_exp':
        try:
            # Recupera a mensagem salva temporariamente
            save = context.user_data.get('expiracao_temp', {})
            
            # Salva no banco de dados
            manager.update_bot_expiration(context.bot_data['id'], save)
            
            await query.message.edit_text("✅ Expiração salva com sucesso!")
            
            # Limpa o estado e dados temporários
            context.user_data.pop('expiracao_temp', None)
            context.user_data['conv_state'] = False
            
            return ConversationHandler.END
            
        except Exception as e:
            await query.message.edit_text(f"⛔ Erro ao salvar expiração: {str(e)}")
            context.user_data['conv_state'] = False
            return ConversationHandler.END

conv_handler_adeus = ConversationHandler(
    entry_points=[CommandHandler("adeus", adeus)],
    states={
        EXPIRACAO_ESCOLHA: [CallbackQueryHandler(adeus_escolha)],
        EXPIRACAO_RECEBER: [MessageHandler(~filters.COMMAND, adeus_receber_mensagem), CallbackQueryHandler(cancel)],
        EXPIRACAO_CONFIRMAR: [CallbackQueryHandler(adeus_confirmar)]
    },
    fallbacks=[CallbackQueryHandler(error_callback)]
)
