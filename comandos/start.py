# comandos/start.py - ARQUIVO COMPLETO COM SUPORTE A UTM

import modules.manager as manager
import modules.recovery_system as recovery_system
import modules.facebook_conversions as fb_conv
import requests
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import CallbackContext, ConversationHandler

async def start(update: Update, context: CallbackContext):
    """Comando /start modificado para processar fbclid curto e tracking completo"""
    
    # Marca que está processando start para evitar conflitos
    context.user_data['processing_start'] = True
    import time
    context.user_data['last_start_time'] = time.time()
    
    user_id = str(update.message.from_user.id)
    user = update.message.from_user
    
    # IMPORTANTE: Atualiza última atividade do bot
    manager.update_bot_last_activity(context.bot_data['id'])
    
    # NOVO: Registra o usuário no tracking
    is_new = manager.register_user_tracking(user_id, context.bot_data['id'])
    print(f"[START] User: {user_id}, Is New: {is_new}")
    
    # NOVO: Processa parâmetros do start (fbclid ou tracking completo)
    fbclid = None
    tracking_data = None
    
    if context.args and len(context.args) > 0:
        param = context.args[0]
        print(f"[START] Parâmetro recebido: {param}")
        
        # Carrega a URL do config.json
        with open('config.json', 'r') as f:
            config_data = json.loads(f.read())
        
        API_URL = config_data.get('url', 'https://localhost:4040')
        print(f"[START] Usando URL do config: {API_URL}")
        
        # Verifica o tipo de ID
        if param.startswith('tk_'):
            # É um tracking completo com UTMs
            short_id = param
            print(f"[START] Tracking completo detectado: {short_id}")
            
            try:
                # Faz requisição para recuperar tracking completo
                response = requests.get(f'{API_URL}/api/get-tracking/{short_id}')
                
                if response.status_code == 200:
                    tracking_data = response.json()
                    fbclid = tracking_data.get('fbclid')
                    
                    print(f"[START] Tracking recuperado:")
                    print(f"  fbclid: {fbclid[:30] if fbclid else 'N/A'}...")
                    print(f"  utm_source: {tracking_data.get('utm_source', 'N/A')}")
                    print(f"  utm_campaign: {tracking_data.get('utm_campaign', 'N/A')}")
                    print(f"  utm_content: {tracking_data.get('utm_content', 'N/A')}")
                    print(f"  utm_term: {tracking_data.get('utm_term', 'N/A')}")
                    
                    # Salva tracking completo no banco
                    manager.save_utm_tracking(user_id, context.bot_data['id'], tracking_data)
                    
                    # Também salva o fbclid na tabela antiga para compatibilidade
                    if fbclid:
                        manager.save_user_fbclid(user_id, context.bot_data['id'], fbclid)
                    
                    # Envia evento Lead para Facebook
                    await fb_conv.send_lead_event(user_id, context.bot_data['id'], fbclid)
                    
                    # NOVO: Envia evento PageView também
                    await fb_conv.send_pageview_event(user_id, context.bot_data['id'])
                else:
                    print(f"[START] Erro ao recuperar tracking: {response.status_code}")
                    
            except Exception as e:
                print(f"[START] Erro ao processar tracking: {e}")
                
        elif param.startswith('fb_'):
            # É um ID curto do fbclid antigo (compatibilidade)
            short_id = param[3:]
            print(f"[START] ID curto fbclid detectado: {short_id}")
            
            try:
                # Faz requisição para recuperar o fbclid original
                response = requests.get(f'{API_URL}/api/get-fbclid/{short_id}')
                
                if response.status_code == 200:
                    data = response.json()
                    fbclid = data.get('fbclid')
                    print(f"[START] fbclid recuperado: {fbclid[:30]}...")
                    
                    # Salva o fbclid no banco
                    manager.save_user_fbclid(user_id, context.bot_data['id'], fbclid)
                    
                    # Cria tracking_data mínimo para compatibilidade
                    tracking_data = {'fbclid': fbclid}
                    manager.save_utm_tracking(user_id, context.bot_data['id'], tracking_data)
                    
                    # Envia evento Lead para Facebook
                    await fb_conv.send_lead_event(user_id, context.bot_data['id'], fbclid)
                    
                    # NOVO: Envia evento PageView também
                    await fb_conv.send_pageview_event(user_id, context.bot_data['id'])
                else:
                    print(f"[START] Erro ao recuperar fbclid: {response.status_code}")
                    
            except Exception as e:
                print(f"[START] Erro ao processar fbclid: {e}")
        
        # Se o parâmetro for o fbclid direto (caso antigo, não deve acontecer mais)
        elif len(param) > 64:
            print("[START] fbclid direto detectado (muito longo) - ignorando")
    
    # Se não tem fbclid mas é usuário novo, envia Lead sem fbclid
    if not fbclid and is_new:
        await fb_conv.send_lead_event(user_id, context.bot_data['id'], None)
        # NOVO: Envia PageView também
        await fb_conv.send_pageview_event(user_id, context.bot_data['id'])
    
    # Adiciona o usuário aos usuários do bot
    users = manager.get_bot_users(context.bot_data['id'])
    if user_id not in users:
        users.append(user_id)
        manager.update_bot_users(context.bot_data['id'], users)
    
    # Pega a configuração do bot
    config = manager.get_bot_config(context.bot_data['id'])
    
    # Inicia o sistema de recuperação se configurado
    recoveries = manager.get_bot_recovery(context.bot_data['id'])
    if recoveries and any(r is not None for r in recoveries):
        print(f"[START] Iniciando sistema de recuperação para usuário {user_id}")
        recovery_system.start_recovery_for_user(context, user_id, context.bot_data['id'])
    
    # Prepara o teclado
    keyboard = []
    
    # Botão principal de ofertas
    if config.get('button', False):
        keyboard.append([InlineKeyboardButton(config['button'], callback_data='acessar_ofertas')])
    
    # NOVO: Botão de redirecionamento se configurado
    if config.get('redirect_button'):
        redirect_btn = config['redirect_button']
        keyboard.append([InlineKeyboardButton(redirect_btn['text'], url=redirect_btn['url'])])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    # Envia a mensagem de boas-vindas
    try:
        # Pega as configurações
        texto1 = config.get('texto1', False)
        texto2 = config.get('texto2', 'Configure o bot usando /inicio\n\nUtilize /comandos para verificar os comandos existentes')
        media = config.get('midia', False)
        
        # NOVO: Verifica se tem múltiplas mídias
        midias = config.get('midias', [])
        media_mode = config.get('media_mode', 'sequential')
        
        # CENÁRIO 1: Tem múltiplas mídias
        if midias and len(midias) > 0:
            # MODO ALBUM: Envia todas juntas
            if media_mode == 'album' and len(midias) > 1:
                # Cria lista mista de mídias
                media_group = []
                for i, midia in enumerate(midias[:10]):  # Máximo 10
                    if midia['type'] == 'photo':
                        media_group.append(InputMediaPhoto(media=midia['file']))
                    elif midia['type'] == 'video':
                        media_group.append(InputMediaVideo(media=midia['file']))
                
                # Envia o album misto
                if media_group:
                    await context.bot.send_media_group(
                        chat_id=user.id,
                        media=media_group
                    )
            
            # MODO SEQUENCIAL: Envia uma por vez
            else:
                for midia in midias[:10]:  # Máximo 10
                    if midia['type'] == 'photo':
                        await context.bot.send_photo(
                            chat_id=user.id,
                            photo=midia['file']
                        )
                    elif midia['type'] == 'video':
                        await context.bot.send_video(
                            chat_id=user.id,
                            video=midia['file']
                        )
                    # Pequeno delay entre mídias para não parecer spam
                    if len(midias) > 1:
                        await asyncio.sleep(0.3)
        
        # CENÁRIO 2: Tem mídia única (compatibilidade antiga)
        elif media and isinstance(media, dict):
            # Envia mídia única
            if media.get('type') == 'photo':
                await context.bot.send_photo(
                    chat_id=user.id, 
                    photo=media.get('file')
                )
            elif media.get('type') == 'video':
                await context.bot.send_video(
                    chat_id=user.id, 
                    video=media.get('file')
                )
        
        # SEMPRE: Envia texto1 se existir (DEPOIS das mídias)
        if texto1 and isinstance(texto1, str):
            await context.bot.send_message(
                chat_id=user.id,
                text=texto1
            )
        
        # SEMPRE: Envia texto2 com os botões (por último)
        await context.bot.send_message(
            chat_id=user.id, 
            text=texto2, 
            reply_markup=reply_markup
        )
                
    except Exception as e:
        print(f"Erro ao enviar mensagem de início: {e}")
        await update.message.reply_text("Ocorreu um erro. Por favor, tente novamente.")
    
    # Limpa a flag de processamento
    context.user_data['processing_start'] = False
    
    return ConversationHandler.END
