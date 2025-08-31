import modules.manager as manager
import json
import requests
import time
import hashlib
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from modules.utils import process_command, is_admin, cancel, error_callback, escape_markdown_v2

FACEBOOK_ESCOLHA, FACEBOOK_PIXEL_ID, FACEBOOK_ACCESS_TOKEN = range(3)

keyboardc = [
    [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
]
cancel_markup = InlineKeyboardMarkup(keyboardc)

async def facebook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command_check = await process_command(update, context)
    if not command_check:
        return ConversationHandler.END
    
    if not await is_admin(context, update.message.from_user.id):
        return ConversationHandler.END
    
    context.user_data['conv_state'] = "facebook"
    
    # Verifica se já tem configuração
    facebook_config = manager.get_facebook_config(context.bot_data['id'])
    
    keyboard = []
    
    if facebook_config and facebook_config.get('pixel_id'):
        pixel_id = facebook_config.get('pixel_id', 'Não configurado')
        status = "✅ Ativo" if facebook_config.get('enabled', True) else "❌ Desativado"
        
        keyboard.append([InlineKeyboardButton(f"Pixel: {pixel_id}", callback_data="none")])
        keyboard.append([InlineKeyboardButton(f"Status: {status}", callback_data="none")])
        keyboard.append([
            InlineKeyboardButton("♻️ Alterar", callback_data="alterar"),
            InlineKeyboardButton("🧹 Remover", callback_data="remover")
        ])
    else:
        keyboard.append([InlineKeyboardButton("➕ Configurar", callback_data="adicionar")])
    
    keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📊 𝗖𝗼𝗻𝗳𝗶𝗴𝘂𝗿𝗮𝗰̧𝗮̃𝗼 𝗙𝗮𝗰𝗲𝗯𝗼𝗼𝗸 𝗣𝗶𝘅𝗲𝗹\n\n"
        "Como funciona? O Facebook Pixel rastreia todas as conversões do seu bot, "
        "permitindo otimizar suas campanhas com dados reais.\n\n"
        "📌 Para obter as credenciais:\n"
        "1. Acesse o Gerenciador de Eventos do Facebook\n"
        "2. Selecione seu Pixel\n"
        "3. Vá em Configurações → Conversions API\n"
        "4. Clique em 'Gerar token de acesso'\n\n"
        "O que deseja fazer?",
        reply_markup=reply_markup
    )
    return FACEBOOK_ESCOLHA

async def facebook_escolha(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END
    
    elif query.data == 'none':
        return FACEBOOK_ESCOLHA
    
    elif query.data in ['adicionar', 'alterar']:
        context.user_data['facebook_config'] = {}
        
        await query.message.edit_text(
            "🆔 𝗣𝗮𝘀𝘀𝗼 𝟭 𝗱𝗲 𝟮\n\n"
            "Envie o ID do seu Pixel do Facebook\\.\n\n"
            "Exemplo\\: `1024404363116287`\n\n"
            "💡 Encontre no Gerenciador de Eventos do Facebook",
            reply_markup=cancel_markup,
            parse_mode='MarkdownV2'
        )
        return FACEBOOK_PIXEL_ID
    
    elif query.data == 'remover':
        manager.remove_facebook_config(context.bot_data['id'])
        await query.message.edit_text(
            "✅ Configuração do Facebook Pixel removida com sucesso!\n\n"
            "⚠️ As conversões não serão mais enviadas para o Facebook."
        )
        context.user_data['conv_state'] = False
        return ConversationHandler.END

async def facebook_pixel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        await update.message.reply_text("❌ Por favor, envie apenas o ID do Pixel:", reply_markup=cancel_markup)
        return FACEBOOK_PIXEL_ID
    
    pixel_id = update.message.text.strip()
    
    # Validação básica - Pixel IDs geralmente têm 15-16 dígitos
    if not pixel_id.isdigit() or len(pixel_id) < 10 or len(pixel_id) > 20:
        await update.message.reply_text(
            "❌ ID do Pixel inválido!\n\n"
            "O ID deve conter apenas números.\n"
            "Exemplo: 1024404363116287",
            reply_markup=cancel_markup
        )
        return FACEBOOK_PIXEL_ID
    
    context.user_data['facebook_config']['pixel_id'] = pixel_id
    
    await update.message.reply_text(
        "🔑 𝗣𝗮𝘀𝘀𝗼 𝟮 𝗱𝗲 𝟮\n\n"
        "Agora envie o Token de Acesso \\(Access Token\\)\\.\n\n"
        "⚠️ **Importante\\:**\n"
        "• Use o token gerado em\\: Configurações do Pixel \\> Conversions API\n"
        "• Este token já vem com as permissões corretas\n\n"
        "💡 O token geralmente começa com 'EAA' e tem mais de 100 caracteres",
        reply_markup=cancel_markup,
        parse_mode='MarkdownV2'
    )
    return FACEBOOK_ACCESS_TOKEN

def hash_data(data):
    """Hasheia dados para o Facebook"""
    if not data:
        return None
    return hashlib.sha256(data.lower().strip().encode('utf-8')).hexdigest()

async def test_facebook_token(pixel_id, access_token):
    """Testa o token enviando um evento de teste real"""
    
    # URL da Conversions API
    url = f"https://graph.facebook.com/v18.0/{pixel_id}/events"
    
    # Pega URL do config
    with open('config.json', 'r') as f:
        config = json.loads(f.read())
    
    # Evento de teste
    test_event = {
        "data": [{
            "event_name": "PageView",
            "event_time": int(time.time()),
            "event_id": f"test_{int(time.time())}",
            "event_source_url": config.get('url', 'https://example.com'),
            "action_source": "website",
            "user_data": {
                "em": hash_data("test@example.com"),
                "client_user_agent": "Mozilla/5.0 (Test)"
            },
            "custom_data": {
                "test_event": True
            }
        }],
        "test_event_code": "TEST12345"  # Isso marca como evento de teste
    }
    
    # Adiciona o token
    test_event["access_token"] = access_token
    
    try:
        response = requests.post(url, json=test_event)
        
        if response.status_code == 200:
            result = response.json()
            return True, result
        else:
            return False, response.json()
    except Exception as e:
        return False, {"error": {"message": str(e)}}

async def facebook_access_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        await update.message.reply_text("❌ Por favor, envie apenas o token:", reply_markup=cancel_markup)
        return FACEBOOK_ACCESS_TOKEN
    
    access_token = update.message.text.strip()
    
    # Validação básica do token
    if len(access_token) < 50:
        await update.message.reply_text(
            "❌ Token muito curto! Verifique se copiou corretamente.\n\n"
            "O token da Conversions API geralmente tem mais de 100 caracteres.",
            reply_markup=cancel_markup
        )
        return FACEBOOK_ACCESS_TOKEN
    
    # Mensagem de status
    status_msg = await update.message.reply_text("🔄 Testando configuração...")
    
    # Testa o token enviando um evento de teste
    pixel_id = context.user_data['facebook_config']['pixel_id']
    success, result = await test_facebook_token(pixel_id, access_token)
    
    if success:
        # Token válido! Salva a configuração
        facebook_config = {
            'pixel_id': pixel_id,
            'access_token': access_token,
            'enabled': True
        }
        
        manager.save_facebook_config(context.bot_data['id'], facebook_config)
        
        # Pega estatísticas de tracking
        stats = manager.get_facebook_tracking_stats(context.bot_data['id'])
        
        # Deleta mensagem de status
        try:
            await status_msg.delete()
        except:
            pass
        
        await update.message.reply_text(
            f"✅ **Facebook Pixel configurado com sucesso!**\n\n"
            f"🆔 **Pixel ID:** {pixel_id}\n"
            f"✅ **Status:** Token validado e funcionando\n"
            f"📊 **Eventos recebidos:** {result.get('events_received', 0)}\n\n"
            f"📈 **Estatísticas atuais:**\n"
            f"• Usuários com fbclid: {stats['users_with_fbclid']}\n"
            f"• Taxa de cobertura: {stats['coverage_rate']:.1f}%\n\n"
            f"🎯 **Eventos que serão enviados:**\n"
            f"• Lead - quando alguém dá /start\n"
            f"• InitiateCheckout - quando gera PIX\n"
            f"• Purchase - quando paga\n\n"
            f"💡 **Dica:** Verifique os eventos no Gerenciador de Eventos\n"
            f"Os eventos de teste aparecerão na aba 'Test Events'",
            parse_mode='Markdown'
        )
        
    else:
        # Token inválido ou erro
        error_msg = result.get('error', {}).get('message', 'Erro desconhecido')
        error_code = result.get('error', {}).get('code', '')
        
        # Deleta mensagem de status
        try:
            await status_msg.delete()
        except:
            pass
        
        error_text = f"❌ **Erro ao validar token!**\n\n"
        
        if "Invalid OAuth" in error_msg or "Error validating access token" in error_msg:
            error_text += "**Problema:** Token inválido ou expirado\n\n"
            error_text += "**Solução:**\n"
            error_text += "1. Vá no Gerenciador de Eventos\n"
            error_text += "2. Selecione seu Pixel\n"
            error_text += "3. Configurações → Conversions API\n"
            error_text += "4. Gere um novo token de acesso\n"
            error_text += "5. Copie o token COMPLETO\n"
        elif "Invalid parameter" in error_msg:
            error_text += "**Problema:** Pixel ID incorreto\n\n"
            error_text += "Verifique se o Pixel ID está correto"
        else:
            error_text += f"**Erro:** {error_msg}\n\n"
            error_text += "**Tente:**\n"
            error_text += "1. Gerar um novo token\n"
            error_text += "2. Verificar o Pixel ID\n"
            error_text += "3. Certificar que copiou o token completo"
        
        await update.message.reply_text(
            error_text,
            reply_markup=cancel_markup,
            parse_mode='Markdown'
        )
        return FACEBOOK_ACCESS_TOKEN
    
    context.user_data['conv_state'] = False
    return ConversationHandler.END

conv_handler_facebook = ConversationHandler(
    entry_points=[CommandHandler("facebook", facebook)],
    states={
        FACEBOOK_ESCOLHA: [CallbackQueryHandler(facebook_escolha)],
        FACEBOOK_PIXEL_ID: [MessageHandler(~filters.COMMAND, facebook_pixel_id), CallbackQueryHandler(cancel)],
        FACEBOOK_ACCESS_TOKEN: [MessageHandler(~filters.COMMAND, facebook_access_token), CallbackQueryHandler(cancel)]
    },
    fallbacks=[CallbackQueryHandler(error_callback)]
)
