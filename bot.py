import modules.manager as manager
import modules.scheduled_broadcast as scheduled_broadcast
import json, re, requests, asyncio
from modules.utmify import utmify_api
from modules.actions import recovery_thread
import modules.recovery_system as recovery_system
from modules.utils import escape_markdown_v2
import modules.facebook_conversions as fb_conv
import modules.payment as payment
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters, Updater, CallbackContext, ChatJoinRequestHandler
from telegram.error import BadRequest, Conflict
config = json.loads(open('./config.json', 'r').read())

if os.path.exists('/app/storage'):
    DB_PATH = '/app/storage/data.db'
    print("✅ Usando volume persistente: /app/storage/data.db")
else:
    DB_PATH = 'data.db'
    print("📁 Usando banco local: data.db")

# Debug
print(f"DEBUG - DB_PATH definido como: {DB_PATH}")
print(f"DEBUG - /data existe? {os.path.exists('/data')}")

# Função de execução do bot
from modules.utils import cancel, escape_markdown_v2
from modules.actions import send_disparo, send_upsell, send_downsell, send_expiration, send_invite, send_payment, acessar_planos, confirmar_plano, notificar_admin, acessar_planos_mensagem
from comandos.grupo import conv_handler_grupo
from comandos.utmify import conv_handler_utmify
from comandos.planos import conv_handler_planos
from comandos.facebook import conv_handler_facebook
from comandos.upsell import conv_handler_upsell
from comandos.expiracao import conv_handler_adeus
from comandos.recuperacao import conv_handler_recuperacao
from comandos.inicio import conv_handler_inicio
from comandos.admins import conv_handler_admin
from comandos.gateway import conv_handler_gateway
from comandos.redirect import conv_handler_redirect
from comandos.downsell import conv_handler_downsell
from comandos.disparo import conv_handler_disparo
from comandos.orderbump import conv_handler_orderbump
from comandos.start import start
from datetime import datetime, timedelta
def add_days(date_str, type, amount, date_format="%Y-%m-%d"):
    name = {
            'dia':1,
            'semana':7,
            'mes':30,
            'ano':365
        }
    if type == 'eterno':
        return '2077-01-01'
    if not type in name.keys():
        return False
    days = name[type]*amount
    date_obj = datetime.strptime(date_str, date_format)
    new_date = date_obj + timedelta(days=days)
    return new_date.strftime(date_format)
from datetime import datetime, timedelta

def calcular_datas(dias: int):
    agora = datetime.now()  # Obtém a data e hora atual
    futura = agora + timedelta(days=dias)  # Soma os dias à data atual

    return agora.strftime("%Y-%m-%d %H:%M:%S"), futura.strftime("%Y-%m-%d %H:%M:%S")

async def check_join_request(update: Update, context: CallbackContext):
    join_request = update.chat_join_request
    user = join_request.from_user
    chat_id = str(join_request.chat.id)
    
    # Pega o grupo principal e o grupo do upsell
    main_group = manager.get_bot_group(bot_application.bot_data['id'])
    upsell_config = manager.get_bot_upsell(bot_application.bot_data['id'])
    upsell_group = upsell_config.get('group_id', '') if upsell_config else ''
    
    # Verifica se tem autorização para o grupo específico
    auth = manager.get_user_expiration(str(user.id), chat_id)
    
    if auth:
        await join_request.approve()
        print(f'user aprovado {user.username} no grupo {chat_id}')
        
        # Só envia upsell se for o grupo PRINCIPAL
        if chat_id == main_group:
            await send_upsell(context, str(user.id))
        
async def expiration_task():
    print('expiration')
    while True:
        try:
            grupo_id = manager.get_bot_group(bot_application.bot_data['id'])
            expirados = manager.verificar_expirados(grupo_id)
        
            for user_id in expirados:
                try:
                    print(f'expirado {user_id}')
                    manager.remover_usuario(user_id, grupo_id)
                    await send_expiration(bot_application, user_id)
                    await bot_application.bot.ban_chat_member(chat_id=grupo_id, user_id=user_id)
                    await bot_application.bot.unban_chat_member(chat_id=grupo_id, user_id=user_id)
                    
                    
                except Exception as e:
                    print(e)
        except Exception as e:
            print(e)
            #print(f'erro exp {bot_application.bot_data['id']}')
        await asyncio.sleep(5)

async def payment_task():
    print("PAYMENT TASK > Iniciando")
    name = {
            'dia':1,
            'semana':7,
            'mes':30,
            'ano':365
        }
    while True:
        await asyncio.sleep(2)
        try:
            payments = manager.get_payments_by_status('paid', bot_application.bot_data['id'])
            
            if len(payments) > 0:
                
                for payment in payments:
                    manager.update_payment_status(payment[1], 'finished')
                    
                    if True:
                        group = manager.get_bot_group(bot_application.bot_data['id'])
                        user = payment[2]
                        plan = json.loads(payment[3])
                        days = 3650
                        if not plan['time_type'] == 'eterno':
                            days = name[plan['time_type']]*int(plan['time'])
                        today, expiration = calcular_datas(days)

                        # ADICIONAR ESTE CÓDIGO AQUI - CANCELA RECUPERAÇÕES AO PAGAR
                        # Cancela todas as recuperações pendentes para este usuário
                        manager.stop_recovery_tracking(user, bot_application.bot_data['id'])
                        print(f"Recuperações canceladas para usuário {user} - pagamento confirmado")

                        # Verifica se é upsell ou downsell
                        if plan.get('is_upsell') or plan.get('is_downsell'):
                            # Para upsell/downsell, adiciona ao grupo extra
                            extra_group = plan.get('upsell_group') or plan.get('downsell_group')
                            manager.add_user_to_expiration(user, today, expiration, plan, extra_group)
                            
                            # Envia convite para o grupo extra
                            try:
                                group_invite_link = await bot_application.bot.create_chat_invite_link(
                                    chat_id=extra_group,
                                    creates_join_request=True
                                )
                                keyboard = [
                                    [InlineKeyboardButton("ENTRAR NO GRUPO VIP EXTRA", url=group_invite_link.invite_link)]
                                ]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                
                                await bot_application.bot.send_message(
                                    chat_id=user,
                                    text="✅ Pagamento do VIP Extra aprovado! Clique abaixo para entrar:",
                                    reply_markup=reply_markup
                                )
                            except Exception as e:
                                print(f"Erro ao criar link do grupo extra: {e}")
                        else:
                            # Pagamento normal
                            manager.add_user_to_expiration(user, today, expiration, plan, group)
                            await send_invite(bot_application, user)
                            
                            # NOVO: Se tem OrderBump com grupo, adiciona ao grupo extra
                            if plan.get('has_orderbump') and plan.get('orderbump_group_id'):
                                orderbump_group = plan.get('orderbump_group_id')
                                
                                print(f"[PAYMENT] Processando grupo OrderBump {orderbump_group} para usuário {user}")
                                
                                # Adiciona ao grupo do OrderBump também
                                manager.add_user_to_expiration(
                                    user, today, expiration, 
                                    {'name': f"OrderBump - {plan.get('orderbump_group_name', 'Extra')}"}, 
                                    orderbump_group
                                )
                                
                                # Cria convite para o grupo extra
                                try:
                                    extra_invite = await bot_application.bot.create_chat_invite_link(
                                        chat_id=orderbump_group,
                                        creates_join_request=True
                                    )
                                    
                                    keyboard = [
                                        [InlineKeyboardButton("🌟 ENTRAR NO GRUPO VIP EXTRA", url=extra_invite.invite_link)]
                                    ]
                                    reply_markup = InlineKeyboardMarkup(keyboard)
                                    
                                    await bot_application.bot.send_message(
                                        chat_id=user,
                                        text=f"🎁 Parabéns! Você também tem acesso ao {plan.get('orderbump_group_name', 'Grupo VIP Extra')}!\n\nClique abaixo para entrar:",
                                        reply_markup=reply_markup
                                    )
                                    print(f"[PAYMENT] Usuário {user} adicionado ao grupo OrderBump {orderbump_group}")
                                    
                                except Exception as e:
                                    print(f"[PAYMENT] Erro ao adicionar ao grupo OrderBump: {e}")
                        
                        # NOTIFICAÇÃO PARA TODOS OS TIPOS DE PAGAMENTO (FORA DO ELSE!)
                        admin_list = manager.get_bot_admin(bot_application.bot_data['id'])
                        owner = manager.get_bot_owner(bot_application.bot_data['id'])
                        if owner not in admin_list:
                            admin_list.append(owner)
                        
                        # Constrói a origem da venda para notificação
                        origem = ""

                        # Verifica se é recuperação
                        if plan.get('is_recovery'):
                            recovery_num = plan.get('recovery_index', 0) + 1
                            discount = plan.get('discount', 0)
                            origem = f"RECUPERAÇÃO {recovery_num} ({int(discount)}% OFF)"

                        # Verifica se tem OrderBump (pode combinar com recuperação)
                        if plan.get('has_orderbump'):
                            if origem:  # Se já tem origem (ex: recuperação)
                                origem += " + ORDERBUMP"
                            else:
                                origem = "COM ORDERBUMP"

                        # Verifica outros tipos (não combinam)
                        if plan.get('is_upsell'):
                            origem = "UPSELL - OFERTA ESPECIAL"
                        elif plan.get('is_downsell'):
                            origem = "DOWNSELL - ÚLTIMA CHANCE"
                        elif plan.get('is_scheduled_broadcast'):
                            discount = plan.get('discount', 0)
                            origem = f"DISPARO PROGRAMADO ({int(discount)}% OFF)"

                        # Adiciona origem ao plano para passar para notificação
                        plan['origem_venda'] = origem
                            
                        for admin in admin_list:
                            try:
                                await notificar_admin(user, plan, bot_application, admin)
                            except Exception as e:
                                print(f"Erro ao notificar admin {admin}: {e}")
                    
        except Exception as e:
            print(f"Erro no payment_task: {e}")
            
async def inactivity_check_task():
    """Verifica bots inativos e os remove após período de inatividade"""
    print('INACTIVITY CHECK > Iniciando')
    
    # Marca todos os bots como ativos na primeira execução para não deletar bots antigos
    manager.mark_all_bots_active()
    
    while True:
        await asyncio.sleep(60)  # Verifica a cada 1 minuto
        
        try:
            # Pega bots inativos há mais de 5 minutos (para teste)
            inactive_bots = manager.get_inactive_bots(minutes=21600)
            
            for bot_data in inactive_bots:
                bot_id = bot_data[0]
                bot_token = bot_data[1]
                owner_id = bot_data[2]
                last_activity = bot_data[3]
                
                print(f"Bot {bot_id} inativo detectado. Última atividade: {last_activity}")
                
                try:
                    # Pega detalhes do bot
                    bot_details = manager.check_bot_token(bot_token)
                    bot_username = bot_details['result'].get('username', 'Bot') if bot_details else 'Bot'
                    
                    # Mensagem de aviso
                    message = (
                        "🚫 <b>ATENÇÃO: BOT REMOVIDO POR INATIVIDADE</b> 🚫\n\n"
                        f"<b>Bot:</b> @{bot_username}\n"
                        f"<b>ID:</b> {bot_id}\n\n"
                        "❌ Este bot foi automaticamente removido do sistema.\n"
                        "❌ Motivo: Inatividade por mais de 5 minutos.\n"
                        "❌ Todos os dados foram apagados.\n\n"
                        "💡 Para usar novamente, cadastre um novo bot.\n\n"
                        "⚠️ <i>Sistema de limpeza automática</i>"
                    )
                    
                    # Envia notificação através do próprio bot
                    response = requests.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={
                            "chat_id": owner_id,
                            "text": message,
                            "parse_mode": "HTML"
                        }
                    )
                    print(f"Notificação de inatividade enviada: {response.status_code}")
                    
                    # Aguarda para garantir que a mensagem foi enviada
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    print(f"Erro ao enviar notificação de inatividade: {e}")
                
                # Agora vamos deletar do banco (o processo será parado no app.py)
                # Deleta do banco de dados
                manager.delete_bot(bot_id)
                print(f"Bot {bot_id} removido por inatividade")
                
        except Exception as e:
            print(f"Erro no inactivity_check_task: {e}")

from modules.utils import process_command, is_admin, cancel, error_callback, error_message, escape_markdown_v2
from modules.actions import exibir_plano

# ADICIONAR ANTES DA FUNÇÃO processar_orderbump NO ARQUIVO bot.py

async def processar_upsell(update: Update, context: CallbackContext):
    """Processa a resposta do usuário ao upsell"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split('_')
    action = data_parts[1]  # 'aceitar' ou 'recusar'
    payment_id = data_parts[2]
    
    if action == 'aceitar':
        # Marca que está processando pagamento
        context.user_data['processing_payment'] = True
        context.user_data['in_upsell_flow'] = True
        # Aceita o upsell - gera PIX
        await pagar(update, context)
    else:
        # Recusa o upsell - mostra downsell se configurado
        # Mantém a flag in_upsell_flow ativa para o downsell
        await send_downsell(context, query.from_user.id)

async def processar_downsell(update: Update, context: CallbackContext):
    """Processa a resposta do usuário ao downsell"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split('_')
    action = data_parts[1]  # 'aceitar' ou 'recusar'
    payment_id = data_parts[2]
    
    if action == 'aceitar':
        # Marca que está processando pagamento
        context.user_data['processing_payment'] = True
        context.user_data['in_upsell_flow'] = True
        # Aceita o downsell - gera PIX
        await pagar(update, context)
    else:
        # Recusa o downsell - mensagem final
        # Limpa todas as flags
        context.user_data['in_upsell_flow'] = False
        context.user_data['processing_payment'] = False
        
        try:
            await query.message.edit_text(
                "✅ Tudo certo! Você já tem acesso ao grupo principal.\n\n"
                "📱 Verifique suas mensagens anteriores para encontrar o link de acesso.\n"
                "💬 Qualquer dúvida, use /start\n\n"
                "Aproveite o conteúdo!"
            )
        except:
            # Se não conseguir editar (mensagem só tem mídia), envia nova mensagem
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text="✅ Tudo certo! Você já tem acesso ao grupo principal.\n\n"
                     "📱 Verifique suas mensagens anteriores para encontrar o link de acesso.\n"
                     "💬 Qualquer dúvida, use /start\n\n"
                     "Aproveite o conteúdo!"
            )

async def processar_orderbump(update: Update, context: CallbackContext):
    """Processa a resposta do usuário ao order bump"""
    query = update.callback_query
    await query.answer()
    
    # Extrai a ação e o payment_id
    data_parts = query.data.split('_')
    action = data_parts[1]  # 'aceitar' ou 'recusar'
    payment_id = data_parts[2]
    
    # Busca os dados do pagamento
    payment_data = manager.get_payment_by_id(payment_id)
    plan = json.loads(payment_data[3])
    
    if action == 'aceitar':
        # Usuário aceitou o order bump
        plano_index = context.user_data.get('plano_selecionado', 0)
        orderbump = manager.get_orderbump_by_plan(context.bot_data['id'], plano_index)
        
        if orderbump:
            # CORREÇÃO: Verifica se já não foi aceito antes
            if not plan.get('has_orderbump'):  # Só adiciona se ainda não tem
                valor_original = plan.get('valor_original', plan['value'])  # Preserva o valor original
                valor_orderbump = orderbump['value']
                novo_valor = valor_original + valor_orderbump
                
                # Atualiza o plano
                plan['value'] = novo_valor
                plan['has_orderbump'] = True
                plan['orderbump_value'] = valor_orderbump
                plan['valor_original'] = valor_original  # Guarda o valor original
                
                # NOVO: Adiciona informação do grupo extra se existir
                if orderbump.get('group_id'):
                    plan['orderbump_group_id'] = orderbump['group_id']
                    plan['orderbump_group_name'] = orderbump.get('group_name', 'Grupo VIP Extra')
                
                # Atualiza o pagamento no banco com o novo plano
                manager.update_payment_plan(payment_id, plan)
                
                print(f"Order Bump aceito: Valor original R${valor_original} + Order Bump R${valor_orderbump} = Total R${novo_valor}")
            else:
                print(f"Order Bump já foi aceito anteriormente, mantendo valor R${plan['value']}")
            
            # Envia AddToCart com valor atualizado
            try:
                await fb_conv.send_addtocart_event(
                    str(query.from_user.id),
                    context.bot_data['id'],
                    plan['value'],
                    f"{plan['name']} + Order Bump"
                )
            except Exception as e:
                print(f"[AddToCart OrderBump] Erro ao enviar evento: {e}")
    
    elif action == 'recusar':  # NOVA LÓGICA PARA RECUSA
        # Verifica se tinha orderbump aceito antes
        if plan.get('has_orderbump'):
            # Recupera o valor original antes do orderbump
            valor_original = plan.get('valor_original', plan['value'])
            
            # Reverte tudo para o estado original
            plan['value'] = valor_original
            plan['has_orderbump'] = False
            
            # Remove campos relacionados ao orderbump
            plan.pop('orderbump_value', None)
            plan.pop('orderbump_group_id', None)
            plan.pop('orderbump_group_name', None)
            plan.pop('valor_original', None)
            
            # Atualiza no banco
            manager.update_payment_plan(payment_id, plan)
            
            print(f"OrderBump recusado após aceite: Revertido para valor original R${valor_original}")
        else:
            print(f"OrderBump recusado (não havia sido aceito antes)")
    
    # Gera o PIX com o valor atualizado
    recovery = plan.get('recovery', False)
    if recovery:
        asyncio.create_task(recovery_thread(context, query.from_user.id, recovery, payment_id))

    keyboard = [
        [InlineKeyboardButton('JÁ FIZ O PAGAMENTO', callback_data=f'pinto')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        gate = manager.get_bot_gateway(context.bot_data['id'])
        if not gate.get('type', False):
            await query.message.edit_text('Nenhuma gateway cadastrada')
            return ConversationHandler.END

        # Valida se tem as credenciais necessárias para cada gateway
        if gate.get('type') == 'pp' and not gate.get('token'):
            await query.message.edit_text('Token PushinPay não configurado')
            return ConversationHandler.END
        elif gate.get('type') == 'MP' and not gate.get('token'):
            await query.message.edit_text('Token Mercado Pago não configurado')
            return ConversationHandler.END
        elif gate.get('type') == 'oasyfy' and (not gate.get('public_key') or not gate.get('private_key')):
            await query.message.edit_text('Credenciais Oasyfy não configuradas')
            return ConversationHandler.END
        elif gate.get('type') == 'syncpay' and (not gate.get('client_id') or not gate.get('client_secret')):
            await query.message.edit_text('Credenciais SyncPay não configuradas')
            return ConversationHandler.END

        qr_data = {}

        # Pega o plano atualizado do banco
        payment_data_updated = manager.get_payment_by_id(payment_id)
        plan_updated = json.loads(payment_data_updated[3])
        
        if gate.get('type') == 'pp':
            qr_data = payment.criar_pix_pp(gate['token'], plan_updated['value'], context.bot_data['id'])
            print(qr_data)
        elif gate.get('type') == 'MP':
            qr_data = payment.criar_pix_mp(gate['token'], plan_updated['value'], context.bot_data['id'])
        elif gate.get('type') == 'oasyfy':
            # Gera o webhook URL para Oasyfy
            webhook_url = f"{config['url']}/webhook/oasyfy"
            qr_data = payment.criar_pix_oasyfy(
                gate['public_key'],
                gate['private_key'],
                plan_updated['value'],
                webhook_url,
                context.bot_data['id']  # Adiciona bot_id como 5º parâmetro
            )
            print(f"[ORDERBUMP OASYFY] Resultado: {qr_data}")
        elif gate.get('type') == 'syncpay':
            # Cria PIX via SyncPay
            qr_data = payment.criar_pix_syncpay(
                gate['client_id'],
                gate['client_secret'],
                plan_updated['value'],
                context.bot_data['id']  # ADICIONE ESTA LINHA - FALTAVA O BOT_ID!
            )
            print(f"[ORDERBUMP SYNCPAY] Resultado: {qr_data}")
            
        payment_qr = qr_data.get('pix_code', False)
        trans_id = qr_data.get('payment_id', False)
        
        if not payment_qr or not trans_id:
            # Se houver erro específico, mostra
            if qr_data.get('error'):
                error_msg = f'Erro ao gerar pagamento: {qr_data["error"]}'
                await query.message.edit_text(error_msg[:200])  # Limita a 200 chars
            else:
                await query.message.edit_text('Erro ao gerar QRCODE tente novamente')
            return ConversationHandler.END

        manager.update_payment_id(payment_id, trans_id)
        manager.update_payment_status(payment_id, 'waiting')
        
        # NOVO: Envia InitiateCheckout para Facebook (CORREÇÃO DO BUG)
        try:
            print(f"[ORDERBUMP DEBUG] Iniciando envio para Facebook...")
            
            # Pega o fbclid do usuário
            fbclid = manager.get_user_fbclid(str(query.from_user.id), context.bot_data['id'])
            print(f"[ORDERBUMP DEBUG] fbclid recuperado: {fbclid}")
            
            # Envia evento InitiateCheckout
            await fb_conv.send_initiate_checkout_event(
                user_id=str(query.from_user.id),
                bot_id=context.bot_data['id'],
                value=plan_updated['value'],  # Valor já com order bump incluído
                plan_name=plan_updated.get('name', 'Plano VIP'),
                fbclid=fbclid
            )
            
            print(f"[ORDERBUMP] InitiateCheckout enviado - User: {query.from_user.id}, Valor: R$ {plan_updated['value']}")
            
        except Exception as e:
            print(f"[ORDERBUMP] Erro ao enviar InitiateCheckout: {e}")
            import traceback
            traceback.print_exc()
        
        # NOVO: Envia PIX gerado para Utmify
        try:
            print(f"[ORDERBUMP DEBUG] Verificando Utmify...")
            
            utmify_config = manager.get_utmify_config(context.bot_data['id'])
            if utmify_config and utmify_config['enabled']:
                print(f"[ORDERBUMP DEBUG] Utmify habilitada, enviando PIX gerado...")
                
                # Pega tracking completo
                user_id = str(query.from_user.id)
                tracking_data = manager.get_utm_tracking(user_id, context.bot_data['id']) or {}

                tax_rate = manager.get_bot_tax(context.bot_data['id'])
                
                # Prepara dados do pedido
                order_data = {
                    'transaction_id': str(trans_id),
                    'user_id': user_id,
                    'bot_id': context.bot_data['id'],
                    'value': plan_updated['value'],  # Valor já com order bump
                    'plan_name': plan_updated.get('name', 'Plano VIP'),
                    'created_at': utmify_api.format_datetime_utc()
                }
                
                # Envia PIX gerado
                await utmify_api.send_pix_generated(
                    api_token=utmify_config['api_token'],
                    order_data=order_data,
                    tracking_data=tracking_data
                )
                
                print(f"[ORDERBUMP] PIX gerado enviado para Utmify - User: {user_id}, Valor: R$ {plan_updated['value']}")
                
        except Exception as e:
            print(f"[ORDERBUMP] Erro ao enviar para Utmify: {e}")
            import traceback
            traceback.print_exc()
        
        await context.bot.send_message(query.from_user.id, f'*Aguarde um momento enquanto preparamos tudo :\) *', parse_mode='MarkdownV2')
        await context.bot.send_message(query.from_user.id, f'{escape_markdown_v2("Para efetuar o pagamento, utiliza a opção Pagar > PIX copia e Cola no aplicativo do seu banco.")}', parse_mode='MarkdownV2')
        await context.bot.send_message(query.from_user.id, f'<b>Copie o código abaixo:</b>', parse_mode='HTML')
        await context.bot.send_message(query.from_user.id, f'`{escape_markdown_v2(payment_qr)}`', parse_mode='MarkdownV2')
        await context.bot.send_message(query.from_user.id, f'Por favor, confirme quando realizar o pagamento.', reply_markup=reply_markup)
    
    except Exception as e:
        await query.message.edit_text(f'Ocorreu um erro ao executar tarefa de pagamentos\n{e}')

    return ConversationHandler.END
async def processar_recovery_plano(update: Update, context: CallbackContext):
    """Processa quando usuário clica em um plano na recuperação"""
    query = update.callback_query
    await query.answer()
    
    # Extrai os dados do callback
    data_parts = query.data.split('_')
    plan_index = int(data_parts[1])
    payment_id = data_parts[2]
    
    # Salva o índice do plano no contexto
    context.user_data['plano_selecionado'] = plan_index
    context.user_data['recovery_payment_id'] = payment_id
    
    # Verifica se este plano tem order bump
    orderbump = manager.get_orderbump_by_plan(context.bot_data['id'], plan_index)
    
    if orderbump:
        # Se tem order bump, mostra a oferta
        print(f"[RECOVERY] OrderBump encontrado para plano {plan_index}")
        
        # Pega os dados do pagamento para saber o valor com desconto
        payment_data = manager.get_payment_by_id(payment_id)
        plano_recovery = json.loads(payment_data[3])
        
        # Calcula o novo total (plano com desconto + orderbump sem desconto)
        valor_plano_com_desconto = plano_recovery['value']
        valor_orderbump = orderbump['value']
        valor_total = round(valor_plano_com_desconto + valor_orderbump, 2)
        
        keyboard = [
            [
                InlineKeyboardButton('✅ 𝗔𝗰𝗲𝗶𝘁𝗮𝗿', callback_data=f'recovery_ob_aceitar_{payment_id}'),
                InlineKeyboardButton('❌ Perder Oferta', callback_data=f'recovery_ob_recusar_{payment_id}')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Envia a mensagem do order bump
        if orderbump.get('media') and orderbump['media']:
            texto_final = orderbump.get('text', 'Oferta especial disponível!')
            
            if orderbump['media']['type'] == 'photo':
                await query.message.reply_photo(
                    photo=orderbump['media']['file'],
                    caption=texto_final,
                    reply_markup=reply_markup
                )
            else:
                await query.message.reply_video(
                    video=orderbump['media']['file'],
                    caption=texto_final,
                    reply_markup=reply_markup
                )
        else:
            await query.message.reply_text(
                orderbump.get('text', 'Oferta especial disponível!'),
                reply_markup=reply_markup
            )
    else:
        # Se não tem order bump, gera PIX direto
        print(f"[RECOVERY] Sem OrderBump para plano {plan_index}, gerando PIX direto")
        
        # Pega os dados do pagamento
        payment_data = manager.get_payment_by_id(payment_id)
        plan = json.loads(payment_data[3])
        
        keyboard = [
            [InlineKeyboardButton('JÁ FIZ O PAGAMENTO', callback_data=f'pinto')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            gate = manager.get_bot_gateway(context.bot_data['id'])
            if not gate.get('type', False):
                await query.message.edit_text('Nenhuma gateway cadastrada')
                return ConversationHandler.END
            
            qr_data = {}
            bot_id = context.bot_data['id']
            
            # Gera o PIX de acordo com a gateway
            if gate.get('type') == 'pp':
                qr_data = payment.criar_pix_pp(gate['token'], plan['value'], bot_id)
            elif gate.get('type') == 'MP':
                qr_data = payment.criar_pix_mp(gate['token'], plan['value'], bot_id)
            elif gate.get('type') == 'oasyfy':
                webhook_url = f"{config['url']}/webhook/oasyfy"
                qr_data = payment.criar_pix_oasyfy(
                    gate['public_key'],
                    gate['private_key'],
                    plan['value'],
                    webhook_url,
                    bot_id
                )
            elif gate.get('type') == 'syncpay':
                qr_data = payment.criar_pix_syncpay(
                    gate['client_id'],
                    gate['client_secret'],
                    plan['value'],
                    bot_id
                )
            
            payment_qr = qr_data.get('pix_code', False)
            trans_id = qr_data.get('payment_id', False)
            
            if not payment_qr or not trans_id:
                if qr_data.get('error'):
                    error_msg = f'Erro ao gerar pagamento: {qr_data["error"]}'
                    await query.message.edit_text(error_msg[:200])
                else:
                    await query.message.edit_text('Erro ao gerar QRCODE tente novamente')
                return ConversationHandler.END
            
            # Atualiza o pagamento
            manager.update_payment_id(payment_id, trans_id)
            manager.update_payment_status(payment_id, 'waiting')
            
            # Envia evento InitiateCheckout para Facebook
            try:
                fbclid = manager.get_user_fbclid(str(query.from_user.id), context.bot_data['id'])
                await fb_conv.send_initiate_checkout_event(
                    user_id=str(query.from_user.id),
                    bot_id=context.bot_data['id'],
                    value=plan['value'],
                    plan_name=plan.get('name', 'Plano VIP'),
                    fbclid=fbclid
                )
                print(f"[RECOVERY] InitiateCheckout enviado - User: {query.from_user.id}, Valor: R$ {plan['value']}")
            except Exception as e:
                print(f"[RECOVERY] Erro ao enviar InitiateCheckout: {e}")
            
            # Envia para Utmify se configurado
            try:
                utmify_config = manager.get_utmify_config(context.bot_data['id'])
                if utmify_config and utmify_config['enabled']:
                    user_id = str(query.from_user.id)
                    tracking_data = manager.get_utm_tracking(user_id, context.bot_data['id']) or {}

                    tax_rate = manager.get_bot_tax(context.bot_data['id'])
                    
                    order_data = {
                        'transaction_id': str(trans_id),
                        'user_id': user_id,
                        'bot_id': context.bot_data['id'],
                        'value': plan['value'],
                        'plan_name': plan.get('name', 'Plano VIP'),
                        'created_at': utmify_api.format_datetime_utc()
                    }
                    
                    await utmify_api.send_pix_generated(
                        api_token=utmify_config['api_token'],
                        order_data=order_data,
                        tracking_data=tracking_data
                    )
                    print(f"[RECOVERY] PIX gerado enviado para Utmify - User: {user_id}, Valor: R$ {plan['value']}")
            except Exception as e:
                print(f"[RECOVERY] Erro ao enviar para Utmify: {e}")
            
            # Envia as mensagens do PIX para o usuário
            await context.bot.send_message(
                query.from_user.id, 
                f'*Aguarde um momento enquanto preparamos tudo\ :\) *', 
                parse_mode='MarkdownV2'
            )
            await context.bot.send_message(
                query.from_user.id, 
                f'{escape_markdown_v2("Para efetuar o pagamento, utiliza a opção Pagar > PIX copia e Cola no aplicativo do seu banco.")}', 
                parse_mode='MarkdownV2'
            )
            await context.bot.send_message(
                query.from_user.id, 
                f'<b>Copie o código abaixo:</b>', 
                parse_mode='HTML'
            )
            await context.bot.send_message(
                query.from_user.id, 
                f'`{escape_markdown_v2(payment_qr)}`', 
                parse_mode='MarkdownV2'
            )
            await context.bot.send_message(
                query.from_user.id, 
                f'Por favor, confirme quando realizar o pagamento.', 
                reply_markup=reply_markup
            )
            
        except Exception as e:
            print(f"[RECOVERY ERROR] Erro geral no processamento: {e}")
            await query.message.edit_text(f'Ocorreu um erro ao executar tarefa de pagamentos\n{e}')
    
    return ConversationHandler.END

async def processar_recovery_orderbump(update: Update, context: CallbackContext):
    """Processa a resposta do usuário ao order bump na recuperação"""
    query = update.callback_query
    await query.answer()
    
    # Extrai a ação e o payment_id
    data_parts = query.data.split('_')
    action = data_parts[2]  # 'aceitar' ou 'recusar'
    payment_id = data_parts[3]
    
    print(f"[RECOVERY ORDERBUMP] Ação: {action}, Payment ID: {payment_id}")
    
    # Busca os dados do pagamento
    payment_data = manager.get_payment_by_id(payment_id)
    plan = json.loads(payment_data[3])
    
    if action == 'aceitar':
        # Usuário aceitou o order bump na recuperação
        plano_index = context.user_data.get('plano_selecionado', 0)
        orderbump = manager.get_orderbump_by_plan(context.bot_data['id'], plano_index)
        
        if orderbump:
            # CORREÇÃO: Verifica se já não foi aceito antes
            if not plan.get('has_orderbump'):  # Só adiciona se ainda não tem
                # Mantém o valor com desconto do plano
                valor_plano_com_desconto = plan.get('recovery_discount_value', plan['value'])
                valor_orderbump = orderbump['value']
                novo_valor = round(valor_plano_com_desconto + valor_orderbump, 2)
                
                # Atualiza o valor do plano
                plan['value'] = novo_valor
                plan['has_orderbump'] = True
                plan['orderbump_value'] = valor_orderbump
                plan['recovery_discount_value'] = valor_plano_com_desconto

                # NOVO: Adiciona informação do grupo extra SE EXISTIR
                if orderbump.get('group_id'):
                    plan['orderbump_group_id'] = orderbump['group_id']
                    plan['orderbump_group_name'] = orderbump.get('group_name', 'Grupo VIP Extra')
                    print(f"[RECOVERY OrderBump] Grupo extra configurado: {orderbump['group_id']}")
                
                # Atualiza o pagamento no banco com o novo plano
                manager.update_payment_plan(payment_id, plan)
                
                print(f"[RECOVERY OrderBump] Aceito: Plano R${valor_plano_com_desconto} + OrderBump R${valor_orderbump} = Total R${novo_valor}")
            else:
                print(f"[RECOVERY OrderBump] Já foi aceito anteriormente, mantendo valor R${plan['value']}")
            
            # NOVO: Envia AddToCart com valor atualizado
            print(f"[RECOVERY DEBUG] Enviando AddToCart para Facebook...")
            try:
                await fb_conv.send_addtocart_event(
                    str(query.from_user.id),
                    context.bot_data['id'],
                    plan['value'],
                    f"{plan['name']} (Recovery) + Order Bump"
                )
                print(f"[RECOVERY] AddToCart enviado com sucesso - Valor: R$ {plan['value']}")
            except Exception as e:
                print(f"[RECOVERY AddToCart] Erro ao enviar evento: {e}")
                import traceback
                traceback.print_exc()
    
    elif action == 'recusar':  # NOVA LÓGICA PARA RECUSA NA RECUPERAÇÃO
        print(f"[RECOVERY ORDERBUMP] Recusado - verificando se precisa reverter...")
        
        # Verifica se tinha orderbump aceito antes
        if plan.get('has_orderbump'):
            # Recupera o valor com desconto da recuperação (sem orderbump)
            valor_recovery_original = plan.get('recovery_discount_value', plan['value'])
            
            # Reverte para o valor com desconto mas SEM orderbump
            plan['value'] = valor_recovery_original
            plan['has_orderbump'] = False
            
            # Remove campos relacionados ao orderbump
            plan.pop('orderbump_value', None)
            plan.pop('orderbump_group_id', None)
            plan.pop('orderbump_group_name', None)
            # Mantém recovery_discount_value pois ainda é recuperação
            
            # Atualiza no banco
            manager.update_payment_plan(payment_id, plan)
            
            print(f"[RECOVERY OrderBump] Recusado após aceite: Revertido para R${valor_recovery_original} (com desconto da recuperação)")
        else:
            print(f"[RECOVERY OrderBump] Recusado (não havia sido aceito antes)")
    
    # Gera o PIX com o valor atualizado (com ou sem orderbump)
    keyboard = [
        [InlineKeyboardButton('JÁ FIZ O PAGAMENTO', callback_data=f'pinto')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        gate = manager.get_bot_gateway(context.bot_data['id'])
        if not gate.get('type', False):
            await query.message.edit_text('Nenhuma gateway cadastrada')
            return ConversationHandler.END
        
        # Validações de gateway (mantém as mesmas)
        if gate.get('type') == 'pp' and not gate.get('token'):
            await query.message.edit_text('Token PushinPay não configurado')
            return ConversationHandler.END
        elif gate.get('type') == 'MP' and not gate.get('token'):
            await query.message.edit_text('Token Mercado Pago não configurado')
            return ConversationHandler.END
        elif gate.get('type') == 'oasyfy' and (not gate.get('public_key') or not gate.get('private_key')):
            await query.message.edit_text('Credenciais Oasyfy não configuradas')
            return ConversationHandler.END
        elif gate.get('type') == 'syncpay' and (not gate.get('client_id') or not gate.get('client_secret')):
            await query.message.edit_text('Credenciais SyncPay não configuradas')
            return ConversationHandler.END
        
        # Pega o plano atualizado do banco
        payment_data_updated = manager.get_payment_by_id(payment_id)
        plan_updated = json.loads(payment_data_updated[3])
        
        print(f"[RECOVERY DEBUG] Gerando PIX - Gateway: {gate.get('type')}, Valor: R$ {plan_updated['value']}")
        
        qr_data = {}
        
        if gate.get('type') == 'pp':
            qr_data = payment.criar_pix_pp(gate['token'], plan_updated['value'], context.bot_data['id'])
            print(f"[RECOVERY PUSHINPAY] Resultado: {qr_data}")
        elif gate.get('type') == 'MP':
            qr_data = payment.criar_pix_mp(gate['token'], plan_updated['value'], context.bot_data['id'])
            print(f"[RECOVERY MP] Resultado: {qr_data}")
        elif gate.get('type') == 'oasyfy':
            webhook_url = f"{config['url']}/webhook/oasyfy"
            qr_data = payment.criar_pix_oasyfy(
                gate['public_key'],
                gate['private_key'],
                plan_updated['value'],
                webhook_url,
                context.bot_data['id']
            )
            print(f"[RECOVERY OASYFY] Resultado: {qr_data}")
        elif gate.get('type') == 'syncpay':
            qr_data = payment.criar_pix_syncpay(
                gate['client_id'],
                gate['client_secret'],
                plan_updated['value'],
                context.bot_data['id']
            )
            print(f"[RECOVERY SYNCPAY] Resultado: {qr_data}")
        
        payment_qr = qr_data.get('pix_code', False)
        trans_id = qr_data.get('payment_id', False)
        
        if not payment_qr or not trans_id:
            if qr_data.get('error'):
                error_msg = f'Erro ao gerar pagamento: {qr_data["error"]}'
                await query.message.edit_text(error_msg[:200])
            else:
                await query.message.edit_text('Erro ao gerar QRCODE tente novamente')
            return ConversationHandler.END
        
        manager.update_payment_id(payment_id, trans_id)
        manager.update_payment_status(payment_id, 'waiting')
        
        print(f"[RECOVERY DEBUG] PIX gerado com sucesso - Trans ID: {trans_id}")
        
        # Envia eventos de tracking
        print(f"[RECOVERY DEBUG] Iniciando envio de eventos de tracking...")
        
        # Facebook InitiateCheckout
        try:
            print(f"[RECOVERY DEBUG] Enviando InitiateCheckout para Facebook...")
            
            # Pega o fbclid do usuário
            fbclid = manager.get_user_fbclid(str(query.from_user.id), context.bot_data['id'])
            print(f"[RECOVERY DEBUG] fbclid recuperado: {fbclid}")
            
            await fb_conv.send_initiate_checkout_event(
                user_id=str(query.from_user.id),
                bot_id=context.bot_data['id'],
                value=plan_updated['value'],
                plan_name=plan_updated.get('name', 'Plano VIP'),
                fbclid=fbclid
            )
            
            print(f"[RECOVERY] InitiateCheckout enviado - User: {query.from_user.id}, Valor: R$ {plan_updated['value']}")
            
        except Exception as e:
            print(f"[RECOVERY] Erro ao enviar InitiateCheckout: {e}")
            import traceback
            traceback.print_exc()
        
        # Utmify
        try:
            print(f"[RECOVERY DEBUG] Verificando Utmify...")
            
            utmify_config = manager.get_utmify_config(context.bot_data['id'])
            if utmify_config and utmify_config['enabled']:
                print(f"[RECOVERY DEBUG] Utmify habilitada, enviando PIX gerado...")
                
                # Pega tracking completo
                user_id = str(query.from_user.id)
                tracking_data = manager.get_utm_tracking(user_id, context.bot_data['id']) or {}
                
                print(f"[RECOVERY DEBUG] Tracking data: {tracking_data}")

                tax_rate = manager.get_bot_tax(context.bot_data['id'])
                
                # Prepara dados do pedido
                order_data = {
                    'transaction_id': str(trans_id),
                    'user_id': user_id,
                    'bot_id': context.bot_data['id'],
                    'value': plan_updated['value'],
                    'plan_name': plan_updated.get('name', 'Plano VIP'),
                    'created_at': utmify_api.format_datetime_utc()
                }
                
                print(f"[RECOVERY DEBUG] Order data preparado: Trans {trans_id}, Valor R$ {plan_updated['value']}")
                
                await utmify_api.send_pix_generated(
                    api_token=utmify_config['api_token'],
                    order_data=order_data,
                    tracking_data=tracking_data
                )
                
                print(f"[RECOVERY] PIX gerado enviado para Utmify - User: {user_id}, Valor: R$ {plan_updated['value']}")
            else:
                print(f"[RECOVERY DEBUG] Utmify não configurada para este bot")
                
        except Exception as e:
            print(f"[RECOVERY] Erro ao enviar para Utmify: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"[RECOVERY DEBUG] Enviando mensagens do PIX para o usuário...")
        
        # Mensagem especial para recuperação
        await context.bot.send_message(query.from_user.id, f'*Aguarde um momento enquanto preparamos tudo :\) *', parse_mode='MarkdownV2')
        await context.bot.send_message(query.from_user.id, f'{escape_markdown_v2("Para efetuar o pagamento, utiliza a opção Pagar > PIX copia e Cola no aplicativo do seu banco.")}', parse_mode='MarkdownV2')
        await context.bot.send_message(query.from_user.id, f'<b>Copie o código abaixo:</b>', parse_mode='HTML')
        await context.bot.send_message(query.from_user.id, f'`{escape_markdown_v2(payment_qr)}`', parse_mode='MarkdownV2')
        await context.bot.send_message(query.from_user.id, f'Por favor, confirme quando realizar o pagamento.', reply_markup=reply_markup)
        
        print(f"[RECOVERY DEBUG] Processo finalizado com sucesso!")
        
    except Exception as e:
        print(f"[RECOVERY ERROR] Erro geral no processamento: {e}")
        import traceback
        traceback.print_exc()
        await query.message.edit_text(f'Ocorreu um erro ao executar tarefa de pagamentos\n{e}')
    
    return ConversationHandler.END

async def comandos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(context, update.message.from_user.id):
        return ConversationHandler.END
    
    commands_text = """⚙️ <b>Painel do Administrador</b>, configure seu bot com os comandos abaixo.

<b>/inicio</b> 🎬 - Configure as mensagens de início do seu bot

<b>/planos</b> 💰 - Crie planos de pagamento ou remova-os

<b>/gateway</b> 🔐 - Adicione um Gateway para pagamentos

<b>/recuperacao</b> 📤 - Defina mensagens de recuperação de compra

<b>/upsell</b> 📈 - Adicione uma nova nova oferta pós compra

<b>/downsell</b> ✅ - Adicione uma oferta ao recusar o upsell

<b>/orderbump</b> 💸 - Gerencie ofertas adicionais a planos

<b>/disparo</b> 🚀 - Envia mensagens em massa a todos do bot

<b>/facebook</b> 📊 - Configure o Facebook Pixel para tracking de conversões

<b>/utmify</b> 📊 - Configure integração com Utmify para tracking avançado

<b>/adeus</b> 👋 - Personalize a mensagem de plano expirado

<b>/status</b> 🧮 - Veja estatisticas do seu bot

<b>/admin</b> 👤 - Adicione novos administradores ao bot

<b>/redirect</b> 🔗 - Adicione um botão de redirecionamento no inicio

<b>/vip</b> ⭐ - Defina o Grupo VIP que os clientes receberão

<b>/start</b> 🏁 - Comando para iniciar o bot"""
    
    await context.bot.send_message(
        chat_id=update.message.from_user.id, 
        text=commands_text, 
        parse_mode='HTML'
    )

    return ConversationHandler.END

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /status - Mostra estatísticas do dia"""
    # Verifica se é admin
    if not await is_admin(context, update.message.from_user.id, show_plans_if_not_admin=False):
        return ConversationHandler.END
    
    bot_id = context.bot_data['id']
    
    # DEBUG E CORREÇÃO
    print(f"\n[STATUS DEBUG] Bot ID: {bot_id}")
    manager.fix_old_timestamps(bot_id)  # Corrige timestamps antigos
    manager.debug_user_tracking(bot_id)
    manager.debug_payments_today(bot_id)
    
    # Busca todas as estatísticas
    new_users_today = manager.get_new_users_today(bot_id)
    total_users = manager.get_total_users(bot_id)
    sales_data = manager.get_sales_today(bot_id)
    
    # Calcula taxas de conversão
    conversion_new = 0
    if sales_data['new_user_pix'] > 0:
        conversion_new = (sales_data['new_user_sales'] / sales_data['new_user_pix']) * 100
    
    conversion_total = 0
    if sales_data['total_pix'] > 0:
        conversion_total = (sales_data['total_sales'] / sales_data['total_pix']) * 100
    
    # Formata a mensagem
    from datetime import datetime
    import pytz
    
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(brasilia_tz)
    
    message = f"""📊 <b>ESTATÍSTICAS DE HOJE ({now.strftime('%d/%m/%Y')})</b>

━━  <b>GERAL</b>

👥 Novos usuários: {new_users_today}
💰 Total de vendas: {sales_data['total_sales']}
💸 Faturamento total: R$ {sales_data['total_revenue']:.2f}
👤 Usuários totais: {total_users}

━━  <b>CONVERSÃO HOJE</b>

💰 Vendas (novos): {sales_data['new_user_sales']}
💵 Faturamento (novos): R$ {sales_data['new_user_revenue']:.2f}
💳 PIX gerados (novos): {sales_data['new_user_pix']}
📈 Taxa conversão (novos): {conversion_new:.1f}%

━━  <b>PERFORMANCE</b>

💳 PIX gerados total: {sales_data['total_pix']}
📊 Taxa conversão geral: {conversion_total:.1f}%

🕐 Atualizado às {now.strftime('%H:%M')}"""
    
    await update.message.reply_text(message, parse_mode='HTML')
    return ConversationHandler.END


import modules.payment as payment
# SUBSTITUIR A FUNÇÃO pagar NO ARQUIVO bot.py

async def pagar(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    # Extrai o payment_id de diferentes formatos de callback
    if '_' in query.data:
        payment_id = query.data.split('_')[-1]
    else:
        payment_id = query.data.replace('pagar', '')
    
    payment_data = manager.get_payment_by_id(payment_id)
    plan = json.loads(payment_data[3])
    value = plan.get('value', False)
    
    if not value:
        await query.message.edit_text('Valor não encontrado')
        return ConversationHandler.END
        
    recovery = plan.get('recovery', False)
    if recovery:
        asyncio.create_task(recovery_thread(context, query.from_user.id, recovery, payment_id))

    keyboard = [
        [InlineKeyboardButton('JÁ FIZ O PAGAMENTO', callback_data=f'pinto')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        gate = manager.get_bot_gateway(context.bot_data['id'])
        if not gate.get('type', False):
            await query.message.edit_text('Nenhuma gateway cadastrada')
            return ConversationHandler.END

        # Valida se tem as credenciais necessárias para cada gateway
        if gate.get('type') == 'pp' and not gate.get('token'):
            await query.message.edit_text('Token PushinPay não configurado')
            return ConversationHandler.END
        elif gate.get('type') == 'MP' and not gate.get('token'):
            await query.message.edit_text('Token Mercado Pago não configurado')
            return ConversationHandler.END
        elif gate.get('type') == 'oasyfy' and (not gate.get('public_key') or not gate.get('private_key')):
            await query.message.edit_text('Credenciais Oasyfy não configuradas')
            return ConversationHandler.END
        elif gate.get('type') == 'syncpay' and (not gate.get('client_id') or not gate.get('client_secret')):
            await query.message.edit_text('Credenciais SyncPay não configuradas')
            return ConversationHandler.END

        qr_data = {}
        
        # IMPORTANTE: Pega o bot_id
        bot_id = context.bot_data['id']

        if gate.get('type') == 'pp':
            qr_data = payment.criar_pix_pp(gate['token'], plan['value'], bot_id)  # MUDANÇA: Adicionado bot_id
            print(qr_data)
        elif gate.get('type') == 'MP':
            qr_data = payment.criar_pix_mp(gate['token'], plan['value'], bot_id)  # MUDANÇA: Adicionado bot_id
        elif gate.get('type') == 'oasyfy':
            # Gera o webhook URL para Oasyfy
            webhook_url = f"{config['url']}/webhook/oasyfy"
            qr_data = payment.criar_pix_oasyfy(
                gate['public_key'],
                gate['private_key'],
                plan['value'],
                webhook_url,
                bot_id  # MUDANÇA: Adicionado bot_id
            )
            print(f"[PAGAR OASYFY] Resultado: {qr_data}")
        elif gate.get('type') == 'syncpay':
            # Cria PIX via SyncPay
            qr_data = payment.criar_pix_syncpay(
                gate['client_id'],
                gate['client_secret'],
                plan['value'],
                bot_id  # MUDANÇA: Adicionado bot_id
            )
            print(f"[PAGAR SYNCPAY] Resultado: {qr_data}")
            
        payment_qr = qr_data.get('pix_code', False)
        trans_id = qr_data.get('payment_id', False)
        
        if not payment_qr or not trans_id:
            # Se houver erro específico, mostra
            if qr_data.get('error'):
                error_msg = f'Erro ao gerar pagamento: {qr_data["error"]}'
                await query.message.edit_text(error_msg[:200])  # Limita a 200 chars
            else:
                await query.message.edit_text('Erro ao gerar QRCODE tente novamente')
            return ConversationHandler.END

        manager.update_payment_id(payment_id, trans_id)
        manager.update_payment_status(payment_id, 'waiting')
        
        # NOVO: Envia PIX gerado para Utmify
        try:
            print(f"[PAGAR DEBUG] Verificando Utmify...")
            
            utmify_config = manager.get_utmify_config(context.bot_data['id'])
            if utmify_config and utmify_config['enabled']:
                print(f"[PAGAR DEBUG] Utmify habilitada, enviando PIX gerado...")
                
                # Pega tracking completo
                user_id = str(query.from_user.id)
                tracking_data = manager.get_utm_tracking(user_id, context.bot_data['id']) or {}

                tax_rate = manager.get_bot_tax(context.bot_data['id'])
                
                # Prepara dados do pedido
                order_data = {
                    'transaction_id': str(trans_id),
                    'user_id': user_id,
                    'bot_id': context.bot_data['id'],
                    'value': plan['value'],
                    'plan_name': plan.get('name', 'Plano VIP'),
                    'created_at': utmify_api.format_datetime_utc()
                }
                
                # Envia PIX gerado
                await utmify_api.send_pix_generated(
                    api_token=utmify_config['api_token'],
                    order_data=order_data,
                    tracking_data=tracking_data
                )
                
                print(f"[PAGAR] PIX gerado enviado para Utmify - User: {user_id}, Valor: R$ {plan['value']}")
            else:
                print(f"[PAGAR DEBUG] Utmify não configurada para este bot")
                
        except Exception as e:
            print(f"[PAGAR] Erro ao enviar para Utmify: {e}")
            import traceback
            traceback.print_exc()
        
        # EXISTENTE: Envia InitiateCheckout para Facebook
        try:
            print(f"[PAGAR DEBUG] Iniciando envio para Facebook...")
            
            # Pega o fbclid do usuário
            fbclid = manager.get_user_fbclid(str(query.from_user.id), context.bot_data['id'])
            print(f"[PAGAR DEBUG] fbclid recuperado: {fbclid}")
            
            # Envia evento InitiateCheckout
            await fb_conv.send_initiate_checkout_event(
                user_id=str(query.from_user.id),
                bot_id=context.bot_data['id'],
                value=plan['value'],
                plan_name=plan.get('name', 'Plano VIP'),
                fbclid=fbclid
            )
            
            print(f"[PAGAR] InitiateCheckout enviado - User: {query.from_user.id}, Valor: R$ {plan['value']}")
            
        except Exception as e:
            print(f"[PAGAR] Erro ao enviar InitiateCheckout: {e}")
            import traceback
            traceback.print_exc()
        
        # Mensagem personalizada para upsell/downsell
        if plan.get('is_upsell'):
            await context.bot.send_message(query.from_user.id, f'🎯 *Oferta Especial Ativada\!*', parse_mode='MarkdownV2')
        elif plan.get('is_downsell'):
            await context.bot.send_message(query.from_user.id, f'💸 *Última Chance Ativada\!*', parse_mode='MarkdownV2')
        
        await context.bot.send_message(query.from_user.id, f'*Aguarde um momento enquanto preparamos tudo :\\) *', parse_mode='MarkdownV2')
        await context.bot.send_message(query.from_user.id, f'{escape_markdown_v2("Para efetuar o pagamento, utiliza a opção Pagar > PIX copia e Cola no aplicativo do seu banco.")}', parse_mode='MarkdownV2')
        await context.bot.send_message(query.from_user.id, f'<b>Copie o código abaixo:</b>', parse_mode='HTML')
        await context.bot.send_message(query.from_user.id, f'`{escape_markdown_v2(payment_qr)}`', parse_mode='MarkdownV2')
        await context.bot.send_message(query.from_user.id, f'Por favor, confirme quando realizar o pagamento.', reply_markup=reply_markup)
    
    except Exception as e:
        await query.message.edit_text(f'Ocorreu um erro ao executar tarefa de pagamentos\n{e}')

    return ConversationHandler.END

async def acessar_planos_force(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Debug log
        if update.message and update.message.text:
            print(f"[DEBUG acessar_planos_force] Mensagem recebida: '{update.message.text}'")
            print(f"[DEBUG] processing_start: {context.user_data.get('processing_start')}")
        
        # Ignora COMPLETAMENTE se for callback query
        if update.callback_query:
            return ConversationHandler.END
        
        # Ignora se não tiver mensagem
        if not update.message:
            return ConversationHandler.END
            
        # Ignora se não tiver texto (pode ser mídia, sticker, etc)
        if not update.message.text:
            return ConversationHandler.END
            
        # IMPORTANTE: Ignora se for qualquer comando
        if update.message.text.startswith('/'):
            print(f"[DEBUG] Ignorando comando: {update.message.text}")
            return ConversationHandler.END
            
        # IMPORTANTE: Ignora se estiver processando /start
        if context.user_data.get('processing_start'):
            print("[DEBUG] Ignorando - processando start")
            return ConversationHandler.END
            
        # NOVA VERIFICAÇÃO: Ignora se acabou de processar start (adiciona delay)
        if context.user_data.get('last_start_time'):
            import time
            if time.time() - context.user_data.get('last_start_time', 0) < 2:  # 2 segundos de delay
                print("[DEBUG] Ignorando - start recente")
                return ConversationHandler.END
            
        # Ignora se for admin (NÃO mostra planos)
        if await is_admin(context, update.message.from_user.id, show_plans_if_not_admin=False):
            print("[DEBUG] Ignorando - é admin")
            return ConversationHandler.END
            
        # Ignora se estiver em alguma conversa ativa
        if context.user_data.get('conv_state'):
            print(f"[DEBUG] Ignorando - em conversa: {context.user_data.get('conv_state')}")
            return ConversationHandler.END
        
        # Ignora se acabou de processar um pagamento
        if context.user_data.get('processing_payment'):
            return ConversationHandler.END
            
        # Ignora se acabou de ver upsell/downsell
        if context.user_data.get('in_upsell_flow'):
            return ConversationHandler.END
        
        print("[DEBUG] Mostrando planos via acessar_planos_force")
        # Usa a versão para mensagens ao invés da versão para callbacks
        await acessar_planos_mensagem(update, context)
    except Exception as e:
        print(f"Erro em acessar_planos_force: {e}")
        pass


async def run_bot(token, bot_id):
    global bot_application
    
    # REMOVER TODAS AS VERIFICAÇÕES DE BANIMENTO
    # O código agora começa direto com:
    disable_get_updates(token)
    bot_application = Application.builder().token(token).build()
    
    # IMPORTANTE: CommandHandlers devem vir ANTES do MessageHandler genérico
    # Handlers de comandos específicos
    bot_application.add_handler(CommandHandler('start', start))
    bot_application.add_handler(CommandHandler('comandos', comandos))
    bot_application.add_handler(CommandHandler('status', status))  # ADICIONAR ESTA LINHA
    
    # ConversationHandlers
    bot_application.add_handler(conv_handler_grupo)
    bot_application.add_handler(conv_handler_upsell)
    bot_application.add_handler(conv_handler_planos)
    bot_application.add_handler(conv_handler_adeus)
    bot_application.add_handler(conv_handler_recuperacao)
    bot_application.add_handler(conv_handler_inicio)
    bot_application.add_handler(conv_handler_admin)
    bot_application.add_handler(conv_handler_gateway)
    bot_application.add_handler(conv_handler_disparo)
    bot_application.add_handler(conv_handler_downsell)
    bot_application.add_handler(conv_handler_orderbump)
    bot_application.add_handler(conv_handler_utmify)
    bot_application.add_handler(conv_handler_facebook)
    bot_application.add_handler(conv_handler_redirect)

    
    # Handlers de chat
    bot_application.add_handler(ChatJoinRequestHandler(check_join_request))
    
    # CallbackQueryHandlers
    bot_application.add_handler(CallbackQueryHandler(pagar, pattern='^pagar_'))
    bot_application.add_handler(CallbackQueryHandler(processar_recovery_plano, pattern='^recovery_\d+_'))  # NOVA LINHA
    bot_application.add_handler(CallbackQueryHandler(processar_recovery_orderbump, pattern='^recovery_ob_'))  # NOVA LINHA
    bot_application.add_handler(CallbackQueryHandler(acessar_planos, pattern='^acessar_ofertas$'))
    bot_application.add_handler(CallbackQueryHandler(confirmar_plano, pattern='^plano_'))
    bot_application.add_handler(CallbackQueryHandler(processar_upsell, pattern='^upsell_'))
    bot_application.add_handler(CallbackQueryHandler(processar_downsell, pattern='^downsell_'))
    bot_application.add_handler(CallbackQueryHandler(exibir_plano, pattern='^exibir_'))
    bot_application.add_handler(CallbackQueryHandler(processar_orderbump, pattern='^orderbump_'))
    bot_application.add_handler(CallbackQueryHandler(cancel, pattern='cancelar'))
    
    # IMPORTANTE: MessageHandler genérico deve ser o ÚLTIMO
    # Adicionar um filtro mais específico para evitar conflitos
    bot_application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, acessar_planos_force))
    
    
    bot_application.bot_data['id'] = bot_id
    await bot_application.initialize()
    await bot_application.start()
    await bot_application.updater.start_polling()


async def main_start(token, id):
    """Executa o bot e outras tarefas simultaneamente"""
    
    # Primeiro inicializa o bot
    await run_bot(token, id)
    
    # Inicia os disparos programados após o bot estar pronto
    scheduled_broadcast.start_scheduled_broadcasts_for_bot(bot_application, id)
    
    # Depois inicia as outras tasks
    await asyncio.gather(
        payment_task(),
        expiration_task(),
        inactivity_check_task()  # NOVA TASK ADICIONADA
    )

def disable_get_updates(token):
    url = f"https://api.telegram.org/bot{token}/close"
    response = requests.post(url)

    if response.status_code == 200:
        print("✅ getUpdates desativado com sucesso!")
    else:
        print(f"❌ Erro ao desativar getUpdates: {response.text}")

def run_bot_sync(token, bot_id):
    """Executa o bot sincronamente dentro do novo processo."""
    asyncio.run(main_start(token, bot_id))

#def run_bot_sync(token,bot_id):
#    loop = asyncio.new_event_loop()
#    asyncio.set_event_loop(loop)
#    loop.create_task(payment_task())
#    loop.run_until_complete(run_bot(token, bot_id))

# Inicia o bot caso esteja no processo principal e possua argumentos validos
#if __name__ == '__main__':
#    import sys
#    if len(sys.argv) < 2:
#        print("Por favor, forneça o token do bot como argumento.")
#    else:
#        run_bot(sys.argv[1])
#        asyncio.run(main(sys.argv[0], sys.argv[1]))
#    loop = asyncio.get_event_loop()
#    loop.create_task(main())
    
# DEVELOPED BY GLOW
