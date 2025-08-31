import modules.manager as manager
import modules.payment as payment
import json, re, requests

config = json.loads(open('./config.json', 'r').read())

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters, Updater, CallbackContext, ChatJoinRequestHandler
from telegram.error import BadRequest, Conflict

from modules.utils import process_command, is_admin, error_callback, error_message, cancel, escape_markdown_v2

# REMOVIDO GATEWAY_SENHA - Agora só tem 3 estados
GATEWAY_RECEBER, GATEWAY_ESCOLHA, GATEWAY_RECEBER_PRIVATE = range(3)

keyboardc = [
    [InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]
]
cancel_markup = InlineKeyboardMarkup(keyboardc)

#comando gateway
async def gateway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command_check = await process_command(update, context)
    planos = manager.get_bot_plans(context.bot_data['id'])
    if not command_check:
        return ConversationHandler.END
    if not await is_admin(context, update.message.from_user.id):
        
        return ConversationHandler.END
    context.user_data['conv_state'] = "gateway"

    keyboard = [
            [InlineKeyboardButton("Mercado Pago", callback_data="mp"), InlineKeyboardButton("Pushinpay", callback_data="push")],
            [InlineKeyboardButton("Oasyfy", callback_data="oasyfy"), InlineKeyboardButton("SyncPay", callback_data="syncpay")],
            [InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔐 Qual gateway deseja adicionar?\n\n"
        ">𝗖𝗼𝗺𝗼 𝗳𝘂𝗻𝗰𝗶𝗼𝗻𝗮\\? Conecte seu bot com Mercado Pago, PushinPay, Oasyfy ou SyncPay para processar pagamentos\\.",
        reply_markup=reply_markup,
        parse_mode='MarkdownV2'
    )
    return GATEWAY_ESCOLHA

async def gateway_escolha(update: Update, context: CallbackContext):
   query = update.callback_query
   await query.answer()
   if query.data == 'cancelar':
       await cancel(update, context)
       return ConversationHandler.END
   elif query.data == 'mp':
       # MERCADO PAGO TEMPORARIAMENTE DESABILITADO
       await query.message.edit_text(
           "Gateway temporariamente indisponível.\n\n"
           "Utilize uma das opções disponíveis:\n"
           "• PushinPay\n"
           "• Oasyfy\n"
           "• SyncPay"
       )
       
       context.user_data['conv_state'] = False
       return ConversationHandler.END
   elif query.data == 'push':
       keyboard = [[InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]]
       reply_markup = InlineKeyboardMarkup(keyboard)        
       await query.message.edit_text("🔑 Envie o token da PushinPay.", reply_markup=reply_markup)
       context.user_data['gateway_type'] = 'push'
       return GATEWAY_RECEBER
   elif query.data == 'oasyfy':
       keyboard = [[InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]]
       reply_markup = InlineKeyboardMarkup(keyboard)
       
       await query.message.edit_text(
           "🔑 𝗢𝗮𝘀𝘆𝗳𝘆 \\- 𝗣𝗮𝘀𝘀𝗼 𝟭 𝗱𝗲 𝟮\n\n"
           "Envie a sua 𝗖𝗵𝗮𝘃𝗲 𝗣𝘂́𝗯𝗹𝗶𝗰𝗮 \\(x\\-public\\-key\\)\\:\n\n"
           "📌 Para obter suas chaves\\:\n"
           "1\\. Acesse o painel Oasyfy\n"
           "2\\. Vá em Integrações → API\n"
           "3\\. Gere suas credenciais\n"
           "4\\. Copie a chave pública",
           reply_markup=reply_markup,
           parse_mode='MarkdownV2'
       )
       context.user_data['gateway_type'] = 'oasyfy'
       return GATEWAY_RECEBER
   elif query.data == 'syncpay':
       keyboard = [[InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]]
       reply_markup = InlineKeyboardMarkup(keyboard)
       
       await query.message.edit_text(
           "🔑 𝗦𝘆𝗻𝗰𝗣𝗮𝘆 \\- 𝗣𝗮𝘀𝘀𝗼 𝟭 𝗱𝗲 𝟮\n\n"
           "Envie o seu 𝗖𝗹𝗶𝗲𝗻𝘁 𝗜𝗗\\:\n\n"
           "📌 Para obter suas credenciais\\:\n"
           "1\\. Acesse o painel SyncPay\n"
           "2\\. Vá em API Keys\n"
           "3\\. Copie o Client ID \\(chave pública\\)",
           reply_markup=reply_markup,
           parse_mode='MarkdownV2'
       )
       context.user_data['gateway_type'] = 'syncpay'
       return GATEWAY_RECEBER

async def recebe_gateway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token_recebido = update.message.text.strip()
    keyboard = [[InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if not update.message.text:
        await update.message.reply_text(text=f"⛔ Token invalido, por favor envie um valido", reply_markup=reply_markup)
        return GATEWAY_RECEBER
    
    gateway_type = context.user_data.get('gateway_type')
    
    if gateway_type == 'push':
        # Validação para PushinPay
        if not payment.verificar_push(token_recebido):
            await update.message.reply_text(
                "❌ Token inválido\\! O Token deve ser nesse formato ⬇\n\n"
                ">36498\\|kMLGkibg5Z2D1Ap8hyvabkYsf5emCcREMpRMkTPa2c802374",
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
            return GATEWAY_RECEBER
        
        manager.update_bot_gateway(context.bot_data['id'], {'type':'pp', 'token':token_recebido})
        await update.message.reply_text(text=f"✅ Gateway PushinPay configurado com sucesso!")
        context.user_data['conv_state'] = False
        return ConversationHandler.END
        
    elif gateway_type == 'oasyfy':
        # Primeira chave da Oasyfy (pública)
        context.user_data['oasyfy_public_key'] = token_recebido
        
        await update.message.reply_text(
            "🔑 𝗢𝗮𝘀𝘆𝗳𝘆 \\- 𝗣𝗮𝘀𝘀𝗼 𝟮 𝗱𝗲 𝟮\n\n"
            "Agora envie a sua 𝗖𝗵𝗮𝘃𝗲 𝗣𝗿𝗶𝘃𝗮𝗱𝗮 \\(x\\-secret\\-key\\)\\:\n\n"
            "⚠️ 𝗔𝘁𝗲𝗻𝗰̧𝗮̃𝗼\\: Mantenha esta chave segura\\!",
            reply_markup=reply_markup,
            parse_mode='MarkdownV2'
        )
        return GATEWAY_RECEBER_PRIVATE
        
    elif gateway_type == 'syncpay':
        # Primeira chave da SyncPay (client_id)
        context.user_data['syncpay_client_id'] = token_recebido
        
        await update.message.reply_text(
            "🔑 𝗦𝘆𝗻𝗰𝗣𝗮𝘆 \\- 𝗣𝗮𝘀𝘀𝗼 𝟮 𝗱𝗲 𝟮\n\n"
            "Agora envie o seu 𝗖𝗹𝗶𝗲𝗻𝘁 𝗦𝗲𝗰𝗿𝗲𝘁\\:\n\n"
            "⚠️ 𝗔𝘁𝗲𝗻𝗰̧𝗮̃𝗼\\: Esta é a chave privada, mantenha segura\\!",
            reply_markup=reply_markup,
            parse_mode='MarkdownV2'
        )
        return GATEWAY_RECEBER_PRIVATE

async def recebe_gateway_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    private_key = update.message.text.strip()
    keyboard = [[InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if not update.message.text:
        await update.message.reply_text(text=f"⛔ Chave inválida, por favor envie uma válida", reply_markup=reply_markup)
        return GATEWAY_RECEBER_PRIVATE
    
    gateway_type = context.user_data.get('gateway_type')
    
    if gateway_type == 'oasyfy':
        # Pega a chave pública salva anteriormente
        public_key = context.user_data.get('oasyfy_public_key')
        
        # Testa as credenciais fazendo uma requisição simples
        try:
            test_url = "https://app.oasyfy.com/api/v1/gateway/producer/balance"
            test_headers = {
                "x-public-key": public_key,
                "x-secret-key": private_key
            }
            
            response = requests.get(test_url, headers=test_headers)
            
            if response.status_code == 200:
                # Credenciais válidas, salva no banco
                manager.update_bot_gateway(context.bot_data['id'], {
                    'type': 'oasyfy',
                    'public_key': public_key,
                    'private_key': private_key
                })
                
                # Pega o saldo para mostrar
                balance_data = response.json()
                available = balance_data.get('available', 0)
                
                await update.message.reply_text(
                    f"✅ 𝗢𝗮𝘀𝘆𝗳𝘆 𝗰𝗼𝗻𝗳𝗶𝗴𝘂𝗿𝗮𝗱𝗮 𝗰𝗼𝗺 𝘀𝘂𝗰𝗲𝘀𝘀𝗼\\!\n\n"
                    f"💰 Saldo disponível\\: R\\$ {escape_markdown_v2(str(available))}",
                    parse_mode='MarkdownV2'
                )
                
                # Limpa os dados temporários
                context.user_data.pop('oasyfy_public_key', None)
                context.user_data.pop('gateway_type', None)
                context.user_data['conv_state'] = False
                return ConversationHandler.END
            else:
                await update.message.reply_text(
                    "❌ Credenciais inválidas\\!\n\n"
                    "Verifique se as chaves estão corretas e tente novamente\\.",
                    reply_markup=reply_markup,
                    parse_mode='MarkdownV2'
                )
                # Volta para o início do processo Oasyfy
                context.user_data.pop('oasyfy_public_key', None)
                return GATEWAY_RECEBER
                
        except Exception as e:
            print(f"[OASYFY] Erro ao testar credenciais: {e}")
            await update.message.reply_text(
                "❌ Erro ao validar credenciais.\n\n"
                "Verifique se as chaves estão corretas.",
                reply_markup=reply_markup
            )
            return GATEWAY_RECEBER_PRIVATE
            
    elif gateway_type == 'syncpay':
        # Pega o client_id salvo anteriormente
        client_id = context.user_data.get('syncpay_client_id')
        client_secret = private_key
        
        # Testa as credenciais gerando um token
        try:
            # Tenta gerar token
            token = payment.get_syncpay_token(client_id, client_secret)
            
            if token:
                # Token gerado com sucesso, agora testa o saldo
                test_url = "https://api.syncpayments.com.br/api/partner/v1/balance"
                test_headers = {
                    "Authorization": f"Bearer {token}"
                }
                
                response = requests.get(test_url, headers=test_headers)
                
                if response.status_code == 200:
                    # Credenciais válidas, salva no banco
                    manager.update_bot_gateway(context.bot_data['id'], {
                        'type': 'syncpay',
                        'client_id': client_id,
                        'client_secret': client_secret
                    })
                    
                    # Pega o saldo para mostrar
                    balance_data = response.json()
                    balance = balance_data.get('balance', '0.00')
                    
                    # ========================================
                    # CONFIGURA WEBHOOK AUTOMATICAMENTE
                    # ========================================
                    await update.message.reply_text(
                        "⏳ Configurando webhook automático..."
                    )
                    
                    webhook_configurado = False
                    webhook_msg = ""
                    
                    try:
                        # Lista webhooks existentes primeiro
                        list_url = "https://api.syncpayments.com.br/api/partner/v1/webhooks"
                        list_headers = {"Authorization": f"Bearer {token}"}
                        
                        list_response = requests.get(list_url, headers=list_headers)
                        
                        if list_response.status_code == 200:
                            webhooks = list_response.json().get('data', [])
                            
                            # Verifica se já existe nosso webhook
                            for webhook in webhooks:
                                if 'railway.app/webhook/syncpay' in webhook.get('url', ''):
                                    webhook_configurado = True
                                    webhook_msg = f"✅ Webhook já estava configurado!\nID: {webhook.get('id')}"
                                    print(f"[SYNCPAY] Webhook existente encontrado: {webhook.get('id')}")
                                    break
                        
                        # Se não existe, cria um novo
                        if not webhook_configurado:
                            create_url = "https://api.syncpayments.com.br/api/partner/v1/webhooks"
                            
                            webhook_payload = {
                                "title": "NGK Pay - Railway",
                                "url": f"{config['url']}webhook/syncpay",
                                "event": "cashin",
                                "trigger_all_products": True
                            }
                            
                            create_headers = {
                                "Authorization": f"Bearer {token}",
                                "Content-Type": "application/json"
                            }
                            
                            create_response = requests.post(create_url, json=webhook_payload, headers=create_headers)
                            
                            # CORREÇÃO: Aceita tanto 200 quanto 201 (Created)
                            if create_response.status_code in [200, 201]:
                                webhook_data = create_response.json()
                                webhook_configurado = True
                                webhook_id = webhook_data.get('id', 'N/A')
                                webhook_token = str(webhook_data.get('token', 'N/A'))[:10]
                                webhook_msg = (
                                    f"✅ Webhook configurado com sucesso!\n"
                                    f"ID: {webhook_id}\n"
                                    f"Token: {webhook_token}..."
                                )
                                print(f"[SYNCPAY] Novo webhook criado: {webhook_id}")
                            else:
                                error_text = str(create_response.text)[:100]
                                webhook_msg = f"⚠️ Não foi possível criar webhook: {error_text}"
                                print(f"[SYNCPAY] Erro ao criar webhook: {create_response.text}")
                    
                    except Exception as webhook_error:
                        error_msg = str(webhook_error)[:100]
                        webhook_msg = f"⚠️ Erro ao configurar webhook: {error_msg}"
                        print(f"[SYNCPAY] Erro ao configurar webhook: {webhook_error}")
                    
                    # ========================================
                    # FIM DA CONFIGURAÇÃO DO WEBHOOK
                    # ========================================
                    
                    # Mensagem final com todas as informações (SEM MARKDOWN)
                    final_message = (
                        f"✅ 𝗦𝘆𝗻𝗰𝗣𝗮𝘆 𝗰𝗼𝗻𝗳𝗶𝗴𝘂𝗿𝗮𝗱𝗮 𝗰𝗼𝗺 𝘀𝘂𝗰𝗲𝘀𝘀𝗼!\n\n"
                        f"💰 Saldo disponível: R$ {balance}\n"
                        f"🔑 Token gerado e em cache por 1 hora\n\n"
                        f"🔔 Status do Webhook:\n{webhook_msg}"
                    )
                    
                    await update.message.reply_text(final_message)
                    
                    # Limpa os dados temporários
                    context.user_data.pop('syncpay_client_id', None)
                    context.user_data.pop('gateway_type', None)
                    context.user_data['conv_state'] = False
                    return ConversationHandler.END
                else:
                    await update.message.reply_text(
                        "❌ Token válido mas erro ao verificar saldo.\n\n"
                        "Verifique suas permissões na SyncPay.",
                        reply_markup=reply_markup
                    )
                    return GATEWAY_RECEBER_PRIVATE
            else:
                await update.message.reply_text(
                    "❌ Credenciais inválidas!\n\n"
                    "Não foi possível gerar o token.\n"
                    "Verifique se as chaves estão corretas.",
                    reply_markup=reply_markup
                )
                # Volta para o início
                context.user_data.pop('syncpay_client_id', None)
                context.user_data['gateway_type'] = 'syncpay'
                return GATEWAY_RECEBER
                
        except Exception as e:
            print(f"[SYNCPAY] Erro ao testar credenciais: {e}")
            error_details = str(e)[:100].replace('.', '').replace('_', '').replace('-', '')
            await update.message.reply_text(
                f"❌ Erro ao validar credenciais.\n\n"
                f"Detalhes: {error_details}",
                reply_markup=reply_markup
            )
            return GATEWAY_RECEBER_PRIVATE

# ConversationHandler SEM estado de senha
conv_handler_gateway = ConversationHandler(
    entry_points=[CommandHandler("gateway", gateway)],
    states={
        GATEWAY_ESCOLHA: [CallbackQueryHandler(gateway_escolha)],
        GATEWAY_RECEBER: [MessageHandler(~filters.COMMAND, recebe_gateway), CallbackQueryHandler(cancel)],
        GATEWAY_RECEBER_PRIVATE: [MessageHandler(~filters.COMMAND, recebe_gateway_private), CallbackQueryHandler(cancel)]
    },
    fallbacks=[CallbackQueryHandler(error_callback)]
)
