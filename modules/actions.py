
import modules.manager as manager
import modules.payment as payment
import modules.utils as utils
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters, Updater, CallbackContext, ChatJoinRequestHandler
from telegram.error import BadRequest, Conflict
import asyncio, json

from modules.utils import escape_markdown_v2

async def send_disparo(context, user_id, config):
    
    try:
        print(user_id)
        keyboard = []
        if config['tipo'] == "plano":
            payment_id = manager.create_payment(user_id, config['plano'], config['plano'], context.bot_data['id'])
            valor = config['plano']['value']
            keyboard = [
                [InlineKeyboardButton('💠 Pagar via PIX 💠', callback_data=f'exibir_{payment_id}')]
            ]
        elif config['tipo'] == "livre":
            # MUDANÇA: Usa o texto personalizado do botão ou o padrão
            texto_botao = config.get('botao_texto', 'Acessar Conteúdo')
            keyboard = [[InlineKeyboardButton(texto_botao, url=config['link'])]]
            
        reply_markup=InlineKeyboardMarkup(keyboard)
        
        if config['mensagem'].get('media', False):
            if config['mensagem'].get('text', False):
                print(config['mensagem'].get('media', False))
                if config['mensagem']['media'].get('type', False) == 'photo':
                    await context.bot.send_photo(chat_id=user_id, photo=config['mensagem']['media']['file'], caption=config['mensagem'].get('text', False), reply_markup=reply_markup)
                else:
                    await context.bot.send_video(chat_id=user_id, video=config['mensagem']['media']['file'], caption=config['mensagem'].get('text', False), reply_markup=reply_markup)
            else:
                print('sem texto')
                if config['mensagem']['media'].get('type') == 'photo':
                    await context.bot.send_photo(chat_id=user_id, photo=config['mensagem']['media']['file'], reply_markup=reply_markup)
                else:
                    await context.bot.send_video(chat_id=user_id, video=config['mensagem']['media']['file'], reply_markup=reply_markup)
        else:
            print('texto')
            await context.bot.send_message(chat_id=user_id, text=config['mensagem']['text'], reply_markup=reply_markup)
    except Exception as e:
        print(e)
        return False
    return True
def send_payment():
    pass
#{"media": {"file": "AgACAgEAAxkBAAIDbWehTomUmGO9g5rzT8InVQwfQnQAA2mvMRtsPghFk70HYXbW_0wBAAMCAAN5AAM2BA", "type": "photo"}, "text": "Xibiu", "link": false, "value": 9.99}
async def recovery_thread(context, user_id, config, id):
    await asyncio.sleep(config['tempo']*60)
    print(config)
    payment_data = manager.get_payment_by_id(id)
    state = payment_data[5]
    plano = json.loads(payment_data[3])
    plano['recovery'] = False
    valor = config.get('value', plano['value'])
    plano['value'] = valor
    payment_id = manager.create_payment(user_id, plano, plano['name'], context.bot_data['id'])
    
    keyboard = [
        [InlineKeyboardButton('💠 Pagar via PIX 💠', callback_data=f'exibir_{payment_id}')]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if not state in ['finished', 'paid']:
        if config.get('media', False):
            if config.get('text', False):
                if config['media'].get('type') == 'photo':
                    await context.bot.send_photo(chat_id=user_id, photo=config['media']['file'], caption=config['text'], reply_markup=markup)
                else:
                    await context.bot.send_video(chat_id=user_id, video=config['media']['file'], caption=config['text'], reply_markup=markup)
            else:
                if config['media'].get('type') == 'photo':
                    await context.bot.send_photo(chat_id=user_id, photo=config['media']['file'], reply_markup=markup)
                else:
                    await context.bot.send_video(chat_id=user_id, video=config['media']['file'], reply_markup=markup)
        else:
            await context.bot.send_message(chat_id=user_id, text=config['text'], reply_markup=markup)


# SUBSTITUIR A FUNÇÃO send_upsell NO ARQUIVO actions.py

async def send_upsell(context, user_id):
    """Envia o upsell como oferta de PIX direto"""
    # Marca que está no fluxo de upsell
    context.user_data['in_upsell_flow'] = True
    
    config = manager.get_bot_upsell(context.bot_data['id'])
    
    if not config or not config.get('value') or not config.get('group_id'):
        # Se não tem upsell configurado, limpa a flag e retorna
        context.user_data['in_upsell_flow'] = False
        return
    
    # Cria um pagamento para o upsell
    upsell_plan = {
        'name': 'Upsell - Grupo VIP Extra',
        'value': config['value'],
        'time_type': 'eterno',
        'time': 'eterno',
        'is_upsell': True,
        'upsell_group': config['group_id']
    }
    
    payment_id = manager.create_payment(str(user_id), upsell_plan, 'Upsell', context.bot_data['id'])
    
    keyboard = [
        [
            InlineKeyboardButton('✅ 𝗔𝗰𝗲𝗶𝘁𝗮𝗿', callback_data=f'upsell_aceitar_{payment_id}'),
            InlineKeyboardButton('❌ Recusar', callback_data=f'upsell_recusar_{payment_id}')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Envia a mensagem do upsell
    if config.get('media') and config['media']:
        if config.get('text'):
            if config['media']['type'] == 'photo':
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=config['media']['file'],
                    caption=config['text'],
                    reply_markup=reply_markup
                )
            else:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=config['media']['file'],
                    caption=config['text'],
                    reply_markup=reply_markup
                )
        else:
            if config['media']['type'] == 'photo':
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=config['media']['file'],
                    reply_markup=reply_markup
                )
            else:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=config['media']['file'],
                    reply_markup=reply_markup
                )
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text=config.get('text', f'Por apenas R$ {config["value"]} tenha acesso ao nosso grupo VIP exclusivo!'),
            reply_markup=reply_markup
        )
    
    # NOVO: Envia ViewContent para upsell
    try:
        import modules.facebook_conversions as fb_conv
        await fb_conv.send_viewcontent_event(str(user_id), context.bot_data['id'])
    except Exception as e:
        print(f"[ViewContent Upsell] Erro ao enviar evento: {e}")
        
# ADICIONAR APÓS A FUNÇÃO send_upsell NO ARQUIVO actions.py

async def send_downsell(context, user_id):
    """Envia o downsell se recusar o upsell"""
    config = manager.get_bot_downsell(context.bot_data['id'])
    upsell_config = manager.get_bot_upsell(context.bot_data['id'])
    
    if not config or not config.get('value'):
        # Se não tem downsell configurado, não faz nada
        return
    
    # Cria um pagamento para o downsell (usa o mesmo grupo do upsell)
    downsell_plan = {
        'name': 'Downsell - Oferta Especial',
        'value': config['value'],
        'time_type': 'eterno',
        'time': 'eterno',
        'is_downsell': True,
        'downsell_group': upsell_config['group_id']  # Mesmo grupo do upsell
    }
    
    payment_id = manager.create_payment(str(user_id), downsell_plan, 'Downsell', context.bot_data['id'])
    
    keyboard = [
        [
            InlineKeyboardButton('✅ 𝗔𝗰𝗲𝗶𝘁𝗮𝗿 𝗢𝗳𝗲𝗿𝘁𝗮', callback_data=f'downsell_aceitar_{payment_id}'),
            InlineKeyboardButton('❌ Continuar sem', callback_data=f'downsell_recusar_{payment_id}')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Envia a mensagem do downsell
    if config.get('media') and config['media']:
        if config.get('text'):
            if config['media']['type'] == 'photo':
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=config['media']['file'],
                    caption=config['text'],
                    reply_markup=reply_markup
                )
            else:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=config['media']['file'],
                    caption=config['text'],
                    reply_markup=reply_markup
                )
        else:
            if config['media']['type'] == 'photo':
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=config['media']['file'],
                    reply_markup=reply_markup
                )
            else:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=config['media']['file'],
                    reply_markup=reply_markup
                )
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text=config.get('text', f'Última chance! Por apenas R$ {config["value"]} tenha acesso ao grupo VIP!'),
            reply_markup=reply_markup
        )
    
    # NOVO: Envia ViewContent para downsell
    try:
        import modules.facebook_conversions as fb_conv
        await fb_conv.send_viewcontent_event(str(user_id), context.bot_data['id'])
    except Exception as e:
        print(f"[ViewContent Downsell] Erro ao enviar evento: {e}")

async def send_expiration(context, user_id):
    config = manager.get_bot_expiration(context.bot_data['id'])
    if not config.get('text', False) or not config.get('media', False):
        return
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(text='♻️ 𝗥𝗲𝗻𝗼𝘃𝗮𝗿 𝗔𝘀𝘀𝗶𝗻𝗮𝘁𝘂𝗿𝗮', callback_data='acessar_ofertas')]])
    if config.get('media', False):
        if config.get('text', False):
            if config['media'].get('type') == 'photo':
                await context.bot.send_photo(chat_id=user_id, photo=config['media']['file'], caption=config['text'], reply_markup=reply_markup)
            else:
                await context.bot.send_video(chat_id=user_id, video=config['media']['file'], caption=config['text'], reply_markup=reply_markup)
        else:
            if config['media'].get('type') == 'photo':
                await context.bot.send_photo(chat_id=user_id, photo=config['media']['file'], reply_markup=reply_markup)
            else:
                await context.bot.send_video(chat_id=user_id, video=config['media']['file'], reply_markup=reply_markup)
    else:

        
        await context.bot.send_message(chat_id=user_id, text=config['text'], reply_markup=reply_markup)


async def send_invite(context, user_id):
    try:
        # Carrega as informações do grupo
        grupo_info = manager.get_bot_group(bot_id=context.bot_data['id'])
        user = await context.bot.get_chat(user_id)
        # Cria o link de convite com solicitação de entrada ativada
        
        
        group_invite_link = await context.bot.create_chat_invite_link(
            chat_id=grupo_info, 
            creates_join_request=True
        )
        nickname = user.username
        keyboard = [
            [InlineKeyboardButton("ENTRAR NO GRUPO", url=group_invite_link.invite_link)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=user_id,
            text="✅ Pagamento aprovado! Clique no botão abaixo para entrar no grupo.",
            reply_markup=reply_markup
        )
        print(f"[INFO] Link de convite criado com sucesso: {group_invite_link.invite_link}")
    except ValueError as ve:
        print(f"[ERRO] Erro no ID do grupo: {ve}")
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Não foi possível identificar o grupo. Por favor, entre em contato com o suporte."
        )
    except Exception as e:
        print(f"[ERRO] Erro ao criar link de grupo: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Ocorreu um erro ao gerar o link de convite. Por favor, tente novamente mais tarde."
        )

# LOCALIZAR E SUBSTITUIR A FUNÇÃO acessar_planos NO ARQUIVO modules/actions.py

async def acessar_planos(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    # REMOVIDO O CANCELAMENTO DE RECUPERAÇÕES AQUI
    # Agora só cancela quando o pagamento for confirmado
    
    planos = manager.get_bot_plans(context.bot_data['id'])
    keyboard_plans = []
    for plan_index in range(len(planos)):
        keyboard_plans.append([InlineKeyboardButton(f'{planos[plan_index]["name"]} - R$ {planos[plan_index]["value"]}', callback_data=f"plano_{plan_index}")])
    reply_markup = InlineKeyboardMarkup(keyboard_plans)
    await query.message.edit_text('Escolha uma das oferta abaixo:　', parse_mode='HTML', reply_markup=reply_markup)
    
    # NOVO: Envia evento ViewContent para Facebook
    try:
        import modules.facebook_conversions as fb_conv
        await fb_conv.send_viewcontent_event(str(query.from_user.id), context.bot_data['id'])
    except Exception as e:
        print(f"[ViewContent] Erro ao enviar evento: {e}")
    
async def acessar_planos_mensagem(update: Update, context: CallbackContext):
    """Versão de acessar_planos para mensagens diretas (não callback)"""
    # Não tem query.answer() porque não é um callback
    
    planos = manager.get_bot_plans(context.bot_data['id'])
    keyboard_plans = []
    for plan_index in range(len(planos)):
        keyboard_plans.append([InlineKeyboardButton(f'{planos[plan_index]["name"]} - R$ {planos[plan_index]["value"]}', callback_data=f"plano_{plan_index}")])
    reply_markup = InlineKeyboardMarkup(keyboard_plans)
    
    # Envia uma nova mensagem ao invés de editar
    await context.bot.send_message(
        chat_id=update.message.from_user.id,
        text='Escolha uma das oferta abaixo:　',
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    # NOVO: Envia evento ViewContent para Facebook
    try:
        import modules.facebook_conversions as fb_conv
        await fb_conv.send_viewcontent_event(str(update.message.from_user.id), context.bot_data['id'])
    except Exception as e:
        print(f"[ViewContent] Erro ao enviar evento: {e}")


async def confirmar_plano(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    plano_index = int(query.data.split('_')[-1])
    planos = manager.get_bot_plans(context.bot_data['id'])
    
    if len(planos) > plano_index:
        # IMPORTANTE: Fazer uma CÓPIA PROFUNDA do plano
        import copy
        plano = copy.deepcopy(planos[plano_index])
        
        # GARANTE que o valor está limpo e correto
        valor_original = planos[plano_index]['value']
        plano['value'] = float(valor_original)  # Força conversão para float
        plano['plan_index'] = plano_index
        
        print(f"[CONFIRMAR_PLANO] Plano: {plano['name']}")
        print(f"[CONFIRMAR_PLANO] Valor original: R$ {valor_original}")
        print(f"[CONFIRMAR_PLANO] Valor no plano copiado: R$ {plano['value']}")
        
        # NOVO: Envia evento AddToCart para Facebook
        try:
            import modules.facebook_conversions as fb_conv
            await fb_conv.send_addtocart_event(
                str(query.from_user.id), 
                context.bot_data['id'],
                plano['value'],
                plano['name']
            )
        except Exception as e:
            print(f"[AddToCart] Erro ao enviar evento: {e}")
        
        # Salva o índice do plano selecionado no contexto
        context.user_data['plano_selecionado'] = plano_index
        
        # Verifica se este plano tem order bump
        orderbump = manager.get_orderbump_by_plan(context.bot_data['id'], plano_index)
        
        if orderbump:
            # Se tem order bump, mostra a oferta primeiro
            print(f"[CONFIRMAR_PLANO] OrderBump detectado para plano {plano_index}")
            
            # CRIA O PAYMENT COM VALOR ORIGINAL
            plano_para_payment = copy.deepcopy(plano)
            plano_para_payment['value'] = float(valor_original)  # FORÇA o valor original
            
            payment_id = manager.create_payment(
                str(query.from_user.id), 
                plano_para_payment, 
                plano['name'], 
                context.bot_data['id']
            )
            
            print(f"[CONFIRMAR_PLANO] Payment {payment_id} criado com valor: R$ {plano_para_payment['value']}")
            
            keyboard = [
                [
                    InlineKeyboardButton('✅ 𝗔𝗰𝗲𝗶𝘁𝗮𝗿', callback_data=f'orderbump_aceitar_{payment_id}'),
                    InlineKeyboardButton('❌ Perder Oferta', callback_data=f'orderbump_recusar_{payment_id}')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Envia a mensagem do order bump
            if orderbump.get('media') and orderbump['media']:
                if orderbump.get('text'):
                    if orderbump['media']['type'] == 'photo':
                        await query.message.reply_photo(
                            photo=orderbump['media']['file'],
                            caption=orderbump['text'],
                            reply_markup=reply_markup
                        )
                    else:
                        await query.message.reply_video(
                            video=orderbump['media']['file'],
                            caption=orderbump['text'],
                            reply_markup=reply_markup
                        )
                else:
                    if orderbump['media']['type'] == 'photo':
                        await query.message.reply_photo(
                            photo=orderbump['media']['file'],
                            reply_markup=reply_markup
                        )
                    else:
                        await query.message.reply_video(
                            video=orderbump['media']['file'],
                            reply_markup=reply_markup
                        )
            else:
                await query.message.reply_text(
                    orderbump.get('text', 'Oferta especial disponível!'),
                    reply_markup=reply_markup
                )
        else:
            # Se não tem order bump, segue o fluxo normal
            print(f"[CONFIRMAR_PLANO] Sem OrderBump, criando payment normal")
            
            payment_id = manager.create_payment(
                str(query.from_user.id), 
                plano, 
                plano['name'], 
                context.bot_data['id']
            )
            
            print(f"[CONFIRMAR_PLANO] Payment {payment_id} criado com valor: R$ {plano['value']}")
            
            keyboard = [
                [InlineKeyboardButton('💠 Pagar via PIX 💠', callback_data=f'pagar_{payment_id}')]
            ]
            names = {
                'dia':'dias',
                'semana':'semanas',
                'mes':'meses',
                'ano':'anos',
                'eterno':''
            }
        
            reply_markup = InlineKeyboardMarkup(keyboard)
            valor = plano['value']
        
            if plano['time'] == 1:
                names = {
                'dia':'dia',
                'semana':'semana',
                'mes':'mes',
                'ano':'ano',
                'eterno':''
            }
        
            if plano['time_type'] != 'eterno':
                await query.message.reply_text(
                    f"Plano selecionado com sucesso\.\n• Título\: {escape_markdown_v2(plano['name'])}\n• Duração\: {plano['time']} {names[plano['time_type']]}\n• Valor\: R\$ {escape_markdown_v2(str(valor))}", 
                    reply_markup=reply_markup, 
                    parse_mode='MarkdownV2'
                )
            else:
                await query.message.reply_text(
                    f"Plano selecionado com sucesso\.\n• Título\: {escape_markdown_v2(plano['name'])}\n• Duração\: Vitalicio\n• Valor\: R\$ {escape_markdown_v2(str(valor))}", 
                    reply_markup=reply_markup, 
                    parse_mode='MarkdownV2'
                )
    else:
        await query.message.reply_text(f'⛔ Erro ao encontrar oferta')

async def exibir_plano(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    payment_index = query.data.split('_')[-1]
    plano = json.loads(manager.get_payment_plan_by_id(payment_index))

    keyboard = [
        [InlineKeyboardButton('💠 Pagar via PIX 💠', callback_data=f'pagar_{payment_index}')]
    ]
    names = {
        'dia':'dias',
        'semana':'semanas',
        'mes':'meses',
        'ano':'anos',
        'eterno':''
    }
    reply_markup = InlineKeyboardMarkup(keyboard)
    valor = plano['value']
    if plano['time'] == 1:
            names = {
            'dia':'dia',
            'semana':'semana',
            'mes':'mes',
            'ano':'ano',
            'eterno':''
        }
    if plano['time_type'] != 'eterno':
        await query.message.reply_text(f"Plano selecionado com sucesso\.\n• Título\: {escape_markdown_v2(plano['name'])}\n• Duração\: {plano['time']} {names[plano['time_type']]}\n• Valor\: R\$ {escape_markdown_v2(str(valor))}", reply_markup=reply_markup, parse_mode='MarkdownV2')
    else:
        await query.message.reply_text(f"Plano selecionado com sucesso\.\n• Título\: {escape_markdown_v2(plano['name'])}\n• Duração\: Vitalicio\n• Valor\: R\$ {escape_markdown_v2(str(valor))}", reply_markup=reply_markup, parse_mode='MarkdownV2')


async def notificar_admin(chat_id, plano_escolhido, bot_application, admin):
    bot_instance = bot_application.bot
    try:
        user = await bot_instance.get_chat(int(chat_id))
        username = user.username or "Não definido"
        first_name = user.first_name or "Não definido"
        
        # Monta a mensagem base
        mensagem_venda = (
            f"✅ Venda realizada!\n\n"
            f"🆔 Clientid: {chat_id}\n"
            f"👤 User: @{username}\n"
            f"📝 Nome: {first_name}\n"
            f"💵 Valor: R$ {str(plano_escolhido['value']).replace('.', ',')}\n"
            f"🔗 Plano: {plano_escolhido['name']}"
        )
        
        # Adiciona origem se existir
        origem = plano_escolhido.get('origem_venda', '')
        if origem:
            mensagem_venda += f"\n🎯 Origem: {origem}"
        
        await bot_instance.send_message(chat_id=int(admin), text=mensagem_venda)
    except Exception as e:
        print(f'[ERROR] Erro ao notificar admin? {e}')


#{"name": "Alexo", "value": 18.9, "time_type": "eterno", "time": "eterno"}



