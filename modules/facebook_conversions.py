# facebook_conversions.py - VERSÃO COMPLETA COM IP E USER-AGENT

import hashlib
import requests
import json
from datetime import datetime
import time

print("✅ Módulo facebook_conversions carregado com suporte a IP/User-Agent!")

def hash_data(data):
    """Hasheia dados pessoais conforme exigido pelo Facebook"""
    if not data:
        return None
    return hashlib.sha256(data.lower().strip().encode('utf-8')).hexdigest()

async def send_event_to_facebook(event_name, event_data, bot_id):
    """Envia evento para a Conversions API do Facebook"""
    
    # Pega config do banco
    import modules.manager as manager
    facebook_config = manager.get_facebook_config(bot_id)
    
    if not facebook_config or not facebook_config.get('enabled'):
        print(f"[CAPI] Facebook Pixel não configurado ou desativado para bot {bot_id}")
        return False
    
    pixel_id = facebook_config.get('pixel_id')
    access_token = facebook_config.get('access_token')
    
    if not pixel_id or not access_token:
        print("[CAPI] Credenciais incompletas!")
        return False
    
    # URL da API
    url = f"https://graph.facebook.com/v18.0/{pixel_id}/events"
    
    # Prepara o payload
    payload = {
        "data": [event_data],
        "access_token": access_token
    }
    
    # Adiciona test_event_code se estiver em modo de teste
    # payload["test_event_code"] = "TEST12345"  # Descomente para testar
    
    try:
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            print(f"[CAPI] Evento {event_name} enviado com sucesso!")
            print(f"[CAPI] Eventos recebidos: {result.get('events_received', 0)}")
            print(f"[CAPI] Event ID: {event_data.get('event_id')}")
            return True
        else:
            print(f"[CAPI] Erro ao enviar evento: {response.status_code}")
            print(f"[CAPI] Resposta: {response.text}")
            return False
            
    except Exception as e:
        print(f"[CAPI] Erro na requisição: {e}")
        return False

def generate_event_id(user_id, event_name):
    """Gera event_id único para evitar duplicação"""
    timestamp = int(time.time())
    return f"{user_id}_{timestamp}_{event_name.lower()}"

async def send_purchase_event(user_id, bot_id, value, plan_name, fbclid=None, event_id=None):
    """Envia evento de Purchase para o Facebook com IP e User-Agent"""
    
    # Pega config do banco
    import modules.manager as manager
    facebook_config = manager.get_facebook_config(bot_id)
    
    if not facebook_config or not facebook_config.get('enabled'):
        print(f"[CAPI] Facebook Pixel não configurado para bot {bot_id}")
        return False
    
    # Pega a URL do config.json
    with open('config.json', 'r') as f:
        config = json.loads(f.read())
    
    # Pega tracking completo (agora inclui IP e User-Agent)
    tracking_data = manager.get_utm_tracking(user_id, bot_id) or {}
    
    # Monta os dados do usuário
    user_data = {
        "external_id": hash_data(str(user_id))
    }
    
    # Adiciona fbp se existir
    if tracking_data.get('fbp'):
        user_data["fbp"] = tracking_data['fbp']
    
    # Adiciona fbc se existir (ou constrói do fbclid)
    if tracking_data.get('fbc'):
        user_data["fbc"] = tracking_data['fbc']
    elif fbclid:
        user_data["fbc"] = f"fb.1.{int(time.time() * 1000)}.{fbclid}"
    
    # NOVO: Adiciona IP e User-Agent reais do usuário
    if tracking_data.get('client_ip'):
        user_data["client_ip_address"] = tracking_data['client_ip']
    
    if tracking_data.get('user_agent'):
        user_data["client_user_agent"] = tracking_data['user_agent']
    else:
        user_data["client_user_agent"] = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"
    
    # Gera event_id único
    if not event_id:
        event_id = generate_event_id(user_id, "Purchase")
    
    # Calcula predicted_ltv
    predicted_ltv = float(value) * 12 if "mens" in plan_name.lower() else float(value)
    
    # Monta o evento
    event_data = {
        "event_name": "Purchase",
        "event_time": int(time.time()),
        "event_id": event_id,
        "event_source_url": config.get('url', 'https://example.com'),
        "action_source": "other",
        "user_data": user_data,
        "custom_data": {
            "value": float(value),
            "currency": "BRL",
            "content_name": plan_name,
            "content_type": "product",
            "content_ids": [f"plan_{bot_id}"],
            "contents": [{
                "id": f"plan_{bot_id}",
                "quantity": 1,
                "item_price": float(value)
            }],
            "predicted_ltv": predicted_ltv
        }
    }
    
    # Log para debug
    print(f"[CAPI] Enviando Purchase:")
    print(f"  - User ID: {user_id}")
    print(f"  - External ID: {user_data['external_id']}")
    print(f"  - Valor: R$ {value}")
    print(f"  - Plano: {plan_name}")
    print(f"  - Event ID: {event_id}")
    print(f"  - IP: {user_data.get('client_ip_address', 'N/A')}")
    
    return await send_event_to_facebook("Purchase", event_data, bot_id)

async def send_lead_event(user_id, bot_id, fbclid=None):
    """Envia evento de Lead quando usuário dá /start"""
    
    import modules.manager as manager
    facebook_config = manager.get_facebook_config(bot_id)
    
    if not facebook_config or not facebook_config.get('enabled'):
        return False
    
    with open('config.json', 'r') as f:
        config = json.loads(f.read())
    
    # Pega tracking completo com IP e User-Agent
    tracking_data = manager.get_utm_tracking(user_id, bot_id) or {}
    
    user_data = {
        "external_id": hash_data(str(user_id))
    }
    
    if tracking_data.get('fbp'):
        user_data["fbp"] = tracking_data['fbp']
    
    if tracking_data.get('fbc'):
        user_data["fbc"] = tracking_data['fbc']
    elif fbclid:
        user_data["fbc"] = f"fb.1.{int(time.time() * 1000)}.{fbclid}"
    
    # NOVO: Adiciona IP e User-Agent reais
    if tracking_data.get('client_ip'):
        user_data["client_ip_address"] = tracking_data['client_ip']
    
    if tracking_data.get('user_agent'):
        user_data["client_user_agent"] = tracking_data['user_agent']
    else:
        user_data["client_user_agent"] = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"
    
    event_id = generate_event_id(user_id, "Lead")
    
    event_data = {
        "event_name": "Lead",
        "event_time": int(time.time()),
        "event_id": event_id,
        "event_source_url": config.get('url', 'https://example.com'),
        "action_source": "other",
        "user_data": user_data
    }
    
    print(f"[CAPI] Enviando Lead para user {user_id} com IP: {user_data.get('client_ip_address', 'N/A')}")
    return await send_event_to_facebook("Lead", event_data, bot_id)

async def send_initiate_checkout_event(user_id, bot_id, value, plan_name, fbclid=None):
    """Envia evento quando gera o PIX"""
    
    import modules.manager as manager
    facebook_config = manager.get_facebook_config(bot_id)
    
    if not facebook_config or not facebook_config.get('enabled'):
        return False
    
    with open('config.json', 'r') as f:
        config = json.loads(f.read())
    
    # Pega tracking completo com IP e User-Agent
    tracking_data = manager.get_utm_tracking(user_id, bot_id) or {}
    
    user_data = {
        "external_id": hash_data(str(user_id))
    }
    
    if tracking_data.get('fbp'):
        user_data["fbp"] = tracking_data['fbp']
    
    if tracking_data.get('fbc'):
        user_data["fbc"] = tracking_data['fbc']
    elif fbclid:
        user_data["fbc"] = f"fb.1.{int(time.time() * 1000)}.{fbclid}"
    
    # NOVO: Adiciona IP e User-Agent reais
    if tracking_data.get('client_ip'):
        user_data["client_ip_address"] = tracking_data['client_ip']
    
    if tracking_data.get('user_agent'):
        user_data["client_user_agent"] = tracking_data['user_agent']
    else:
        user_data["client_user_agent"] = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"
    
    event_id = generate_event_id(user_id, "InitiateCheckout")
    
    event_data = {
        "event_name": "InitiateCheckout",
        "event_time": int(time.time()),
        "event_id": event_id,
        "event_source_url": config.get('url', 'https://example.com'),
        "action_source": "other",
        "user_data": user_data,
        "custom_data": {
            "value": float(value),
            "currency": "BRL",
            "content_name": plan_name,
            "content_type": "product",
            "content_ids": [f"plan_{bot_id}"],
            "num_items": 1
        }
    }
    
    print(f"[CAPI] Enviando InitiateCheckout para user {user_id}")
    return await send_event_to_facebook("InitiateCheckout", event_data, bot_id)

async def send_pageview_event(user_id, bot_id):
    """Envia evento PageView quando usuário abre o bot"""
    
    import modules.manager as manager
    facebook_config = manager.get_facebook_config(bot_id)
    
    if not facebook_config or not facebook_config.get('enabled'):
        return False
    
    with open('config.json', 'r') as f:
        config = json.loads(f.read())
    
    # Pega tracking completo com IP e User-Agent
    tracking_data = manager.get_utm_tracking(user_id, bot_id) or {}
    
    user_data = {
        "external_id": hash_data(str(user_id))
    }
    
    if tracking_data.get('fbp'):
        user_data["fbp"] = tracking_data['fbp']
    if tracking_data.get('fbc'):
        user_data["fbc"] = tracking_data['fbc']
    
    # NOVO: Adiciona IP e User-Agent reais
    if tracking_data.get('client_ip'):
        user_data["client_ip_address"] = tracking_data['client_ip']
    
    if tracking_data.get('user_agent'):
        user_data["client_user_agent"] = tracking_data['user_agent']
    else:
        user_data["client_user_agent"] = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"
    
    event_id = generate_event_id(user_id, "PageView")
    
    event_data = {
        "event_name": "PageView",
        "event_time": int(time.time()),
        "event_id": event_id,
        "event_source_url": config.get('url', 'https://example.com'),
        "action_source": "other",
        "user_data": user_data
    }
    
    print(f"[CAPI] Enviando PageView para user {user_id}")
    return await send_event_to_facebook("PageView", event_data, bot_id)

async def send_viewcontent_event(user_id, bot_id):
    """Envia evento ViewContent quando visualiza planos"""
    
    import modules.manager as manager
    facebook_config = manager.get_facebook_config(bot_id)
    
    if not facebook_config or not facebook_config.get('enabled'):
        return False
    
    with open('config.json', 'r') as f:
        config = json.loads(f.read())
    
    # Pega tracking completo com IP e User-Agent
    tracking_data = manager.get_utm_tracking(user_id, bot_id) or {}
    
    user_data = {
        "external_id": hash_data(str(user_id))
    }
    
    if tracking_data.get('fbp'):
        user_data["fbp"] = tracking_data['fbp']
    if tracking_data.get('fbc'):
        user_data["fbc"] = tracking_data['fbc']
    
    # NOVO: Adiciona IP e User-Agent reais
    if tracking_data.get('client_ip'):
        user_data["client_ip_address"] = tracking_data['client_ip']
    
    if tracking_data.get('user_agent'):
        user_data["client_user_agent"] = tracking_data['user_agent']
    else:
        user_data["client_user_agent"] = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"
    
    event_id = generate_event_id(user_id, "ViewContent")
    
    event_data = {
        "event_name": "ViewContent",
        "event_time": int(time.time()),
        "event_id": event_id,
        "event_source_url": config.get('url', 'https://example.com'),
        "action_source": "other",
        "user_data": user_data,
        "custom_data": {
            "content_type": "product_group",
            "content_name": "Lista de Planos"
        }
    }
    
    print(f"[CAPI] Enviando ViewContent para user {user_id}")
    return await send_event_to_facebook("ViewContent", event_data, bot_id)

async def send_addtocart_event(user_id, bot_id, value, plan_name):
    """Envia evento AddToCart quando seleciona um plano"""
    
    import modules.manager as manager
    facebook_config = manager.get_facebook_config(bot_id)
    
    if not facebook_config or not facebook_config.get('enabled'):
        return False
    
    with open('config.json', 'r') as f:
        config = json.loads(f.read())
    
    # Pega tracking completo com IP e User-Agent
    tracking_data = manager.get_utm_tracking(user_id, bot_id) or {}
    
    user_data = {
        "external_id": hash_data(str(user_id))
    }
    
    if tracking_data.get('fbp'):
        user_data["fbp"] = tracking_data['fbp']
    if tracking_data.get('fbc'):
        user_data["fbc"] = tracking_data['fbc']
    
    # NOVO: Adiciona IP e User-Agent reais
    if tracking_data.get('client_ip'):
        user_data["client_ip_address"] = tracking_data['client_ip']
    
    if tracking_data.get('user_agent'):
        user_data["client_user_agent"] = tracking_data['user_agent']
    else:
        user_data["client_user_agent"] = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"
    
    event_id = generate_event_id(user_id, "AddToCart")
    
    event_data = {
        "event_name": "AddToCart",
        "event_time": int(time.time()),
        "event_id": event_id,
        "event_source_url": config.get('url', 'https://example.com'),
        "action_source": "other",
        "user_data": user_data,
        "custom_data": {
            "value": float(value),
            "currency": "BRL",
            "content_name": plan_name,
            "content_type": "product",
            "content_ids": [f"plan_{bot_id}"]
        }
    }
    
    print(f"[CAPI] Enviando AddToCart para user {user_id}")
    return await send_event_to_facebook("AddToCart", event_data, bot_id)
