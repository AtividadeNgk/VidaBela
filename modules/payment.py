import math, requests
import uuid, json

config = json.loads(open('./config.json', 'r').read())

#PAYMENT STATUS
#
# Idle     - pagamento gerado porem sem qrcode
# Waiting  - qrcode gerado aguardando pagamento
# Paid     - pagamento aprovado porem não processado 
# Finished - pagamento finalizado

def gerar_cpf_valido():
    """Gera um CPF válido para testes"""
    import random
    
    # Gera 9 dígitos aleatórios
    cpf = [random.randint(0, 9) for _ in range(9)]
    
    # Calcula o primeiro dígito verificador
    soma = sum((10 - i) * cpf[i] for i in range(9))
    digito1 = (soma * 10 % 11) % 10
    cpf.append(digito1)
    
    # Calcula o segundo dígito verificador
    soma = sum((11 - i) * cpf[i] for i in range(10))
    digito2 = (soma * 10 % 11) % 10
    cpf.append(digito2)
    
    # Formata o CPF
    cpf_str = ''.join(map(str, cpf))
    return f"{cpf_str[:3]}.{cpf_str[3:6]}.{cpf_str[6:9]}-{cpf_str[9:]}"

def gerar_email_aleatorio():
    """Gera um email aleatório para testes"""
    import random
    import string
    
    # Lista de domínios comuns
    dominios = ['gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'icloud.com']
    
    # Lista de nomes comuns brasileiros
    nomes = ['joao', 'maria', 'pedro', 'ana', 'paulo', 'julia', 'carlos', 'fernanda', 
             'lucas', 'mariana', 'gabriel', 'beatriz', 'rafael', 'larissa', 'bruno',
             'amanda', 'felipe', 'camila', 'diego', 'leticia', 'rodrigo', 'patricia',
             'marcelo', 'bruna', 'andre', 'carla', 'ricardo', 'daniela', 'eduardo', 'natalia']
    
    # Lista de sobrenomes comuns
    sobrenomes = ['silva', 'santos', 'oliveira', 'souza', 'lima', 'pereira', 'costa',
                  'ferreira', 'rodrigues', 'almeida', 'nascimento', 'carvalho', 'araujo',
                  'ribeiro', 'barbosa', 'vieira', 'fernandes', 'gomes', 'martins', 'rocha']
    
    # Escolhe aleatoriamente
    nome = random.choice(nomes)
    sobrenome = random.choice(sobrenomes)
    dominio = random.choice(dominios)
    
    # Adiciona um número aleatório (50% de chance)
    if random.random() > 0.5:
        numero = random.randint(1, 999)
        email = f"{nome}.{sobrenome}{numero}@{dominio}"
    else:
        email = f"{nome}.{sobrenome}@{dominio}"
    
    return email

def gerar_telefone_aleatorio():
    """Gera um telefone brasileiro aleatório"""
    import random
    
    # DDDs válidos das principais cidades
    ddds = ['11', '21', '31', '41', '51', '61', '71', '81', '85', '27', 
            '47', '48', '62', '63', '65', '67', '82', '83', '84', '86']
    
    ddd = random.choice(ddds)
    
    # Gera número de celular (9xxxx-xxxx)
    primeira_parte = random.randint(90000, 99999)
    segunda_parte = random.randint(1000, 9999)
    
    return f"({ddd}) {primeira_parte}-{segunda_parte}"

def verificar_push(token):
    url = "https://api.pushinpay.com.br/api/pix/cashIn"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "value": 100,
        "webhook_url": f'',  # Altere para seu webhook real
        "split_rules": [
            {
                "value": math.floor(100*0.05),
                "account_id": "9D60FF2D-4298-4AEF-89AB-F27AE6A9D68D"
                }
            ]
        }
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code in (200, 201):
            payment_info = response.json()
            pix_code = payment_info.get('qr_code', '')
            payment_id = payment_info.get('id', '')
            return True
        else: False
    except requests.exceptions.RequestException as e:
        print(f"Erro ao processar requisição para o PIX: {e}")
        return False, e

def criar_pix_pp(token, valor_cents, bot_id=None):
    # Endpoint da API
    url = "https://api.pushinpay.com.br/api/pix/cashIn"

    valor_cents = float(valor_cents)
    
    # MODIFICADO: Usa a nova função calculate_bot_tax
    if bot_id:
        import modules.manager as manager
        tax_value = manager.calculate_bot_tax(bot_id, valor_cents)
    else:
        # Fallback para taxa percentual padrão
        tax_value = valor_cents * (float(config['tax']) / 100)
    
    # Converte para centavos
    valor_cents_total = valor_cents * 100
    comissao = math.floor(tax_value * 100)  # Taxa já calculada, só converte para centavos

    print(f"""
    GERANDO PIX PUSHINPAY 
    TOTAL: R$ {valor_cents:.2f} ({valor_cents_total} centavos)
    TAXA: R$ {tax_value:.2f}
    COMISSAO: {comissao} centavos (R$ {comissao/100:.2f})
    VALOR ENTREGUE: {valor_cents_total - comissao} centavos
    SPLIT: {'SIM' if comissao > 0 else 'NÃO (taxa zero ou muito baixa)'}
    """)
    
    # Cabeçalhos da requisição
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Corpo da requisição BASE
    data = {
        "value": valor_cents_total,
        "webhook_url": f"{config['url']}/webhook/pp"
    }
    
    # Só adiciona split_rules se a comissão for maior que 0
    if comissao > 0:
        data["split_rules"] = [
            {
                "value": comissao,
                "account_id": "9D60FF2D-4298-4AEF-89AB-F27AE6A9D68D"
            }
        ]
        print(f"[PUSHINPAY] Split rules adicionado: {comissao} centavos")
    else:
        print(f"[PUSHINPAY] Sem split - comissão muito baixa ou taxa zero")

    try:
        # Realiza a requisição POST
        response = requests.post(url, json=data, headers=headers)
        # Verifica se a requisição foi bem-sucedida
        if response.status_code in (200, 201):
            try:
                payment_info = response.json()
                return {
                    "pix_code": payment_info.get("qr_code", False),
                    "payment_id": payment_info.get("id", False),
                    "message": "Pagamento PIX gerado com sucesso."
                }
            except ValueError:
                return {"error": "A resposta da API não está no formato esperado.", "details": response.text}
        else:
            return {
                "error": f"Erro ao criar pagamento. Status Code: {response.status_code}",
                "details": response.text
            }

    except requests.exceptions.RequestException as e:
        return {"error": "Erro ao realizar a requisição para a API.", "details": str(e)}


def criar_pix_mp(access_token: str, transaction_amount: float, bot_id=None) -> dict:
    url = "https://api.mercadopago.com/v1/payments"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": str(uuid.uuid4())
    }
    
    transaction_amount = round(float(transaction_amount), 2)
    
    # MODIFICADO: Usa a nova função calculate_bot_tax
    if bot_id:
        import modules.manager as manager
        application_fee = round(manager.calculate_bot_tax(bot_id, transaction_amount), 2)
    else:
        application_fee = round((transaction_amount * float(config['tax']) / 100), 2)
    
    # Dados do pagamento
    payment_data = {
        "transaction_amount": transaction_amount,
        "description": "Pagamento via PIX - Marketplace",
        "payment_method_id": "pix",
        "payer": {
            "email": 'ngkacesspay@empresa.com'
        },
        "application_fee": application_fee,
        "statement_descriptor": "Marketplace"
    }
    
    print(f"Taxa calculada: R$ {application_fee}")
    print(f"Transaction amount: {transaction_amount}")
    
    try:
        response = requests.post(url, headers=headers, json=payment_data)
        if response.status_code == 201:
            data = response.json()
            print(data)
            pix_code = data.get("point_of_interaction", {}).get("transaction_data", {}).get("qr_code", "")
            payment_id = data.get("id", "")
            return {
                'pix_code': pix_code,
                'payment_id': str(payment_id),
            }
        else:
            return {"error": f"Erro ao criar pagamento: {response.status_code}", "details": response.json()}
    except requests.exceptions.RequestException as e:
        print(f"Erro ao processar requisição para o PIX: {e}")
        return {"error": "Erro ao processar requisição PIX", "details": str(e)}
    
def criar_pix_oasyfy(public_key: str, private_key: str, valor: float, webhook_url: str, bot_id=None) -> dict:
    """
    Cria um pagamento PIX via Oasyfy
    """
    import uuid
    import json
    from datetime import datetime, timedelta
    
    # Carrega o config para pegar o producer ID
    with open('./config.json', 'r') as f:
        config_data = json.loads(f.read())
    
    # MODIFICADO: Usa a nova função calculate_bot_tax
    if bot_id:
        import modules.manager as manager
        tax_value = manager.calculate_bot_tax(bot_id, valor)
    else:
        tax_value = valor * (float(config_data.get('tax', 0)) / 100)
    
    oasyfy_producer_id = config_data.get('oasyfy_producer_id', '')
    
    # URL da API Oasyfy
    url = "https://app.oasyfy.com/api/v1/gateway/pix/receive"
    
    # Headers com autenticação
    headers = {
        "x-public-key": public_key,
        "x-secret-key": private_key,
        "Content-Type": "application/json"
    }
    
    # Gera um identificador único
    identifier = str(uuid.uuid4())[:12]
    
    # Data de vencimento (7 dias a partir de hoje)
    due_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    
    # Valor total
    valor_total = round(float(valor), 2)
    
    # Monta o payload
    payload = {
        "identifier": identifier,
        "amount": valor_total,
        "client": {
            "name": "Cliente NGK Pay",
            "email": gerar_email_aleatorio(),
            "phone": gerar_telefone_aleatorio(),
            "document": gerar_cpf_valido()
        },
        "products": [
            {
                "id": str(uuid.uuid4())[:8],
                "name": "Plano VIP - NGK Pay",
                "quantity": 1,
                "price": valor_total
            }
        ],
        "dueDate": due_date,
        "metadata": {
            "gateway": "NGK Pay",
            "type": "telegram_bot"
        },
        "callbackUrl": webhook_url
    }
    
    # Adiciona splits se a taxa for maior que 0 e tiver producer ID
    if tax_value > 0 and oasyfy_producer_id:
        valor_split = round(tax_value, 2)
        
        payload["splits"] = [
            {
                "producerId": oasyfy_producer_id,
                "amount": valor_split
            }
        ]
        
        print(f"[OASYFY SPLIT] Taxa: R$ {valor_split:.2f} de R$ {valor_total}")
    
    split_info = f"SIM - R$ {tax_value:.2f}" if 'splits' in payload else "NÃO"
    
    print(f"""
    GERANDO PIX OASYFY
    TOTAL: {valor}
    TAXA: R$ {tax_value:.2f}
    WEBHOOK: {webhook_url}
    IDENTIFIER: {identifier}
    CLIENT: {payload['client']['email']} - {payload['client']['document']}
    SPLIT: {split_info}
    """)
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        
        print(f"[OASYFY] Status Code: {response.status_code}")
        print(f"[OASYFY] Response: {response.text[:500]}")
        
        if response.status_code in (200, 201):
            data = response.json()
            
            if data.get('pix') and data.get('transactionId'):
                return {
                    'pix_code': data['pix'].get('code', ''),
                    'payment_id': data.get('transactionId', ''),
                    'message': 'PIX Oasyfy gerado com sucesso',
                    'qr_image': data['pix'].get('image', ''),
                    'qr_base64': data['pix'].get('base64', '')
                }
            else:
                return {
                    'error': 'Resposta incompleta da Oasyfy',
                    'details': data
                }
        else:
            try:
                error_data = response.json()
                error_message = error_data.get('message', 'Erro desconhecido')
                error_code = error_data.get('errorCode', 'UNKNOWN')
                
                return {
                    'error': f'Erro Oasyfy ({error_code}): {error_message}',
                    'details': error_data
                }
            except:
                return {
                    'error': f'Erro HTTP {response.status_code}',
                    'details': response.text
                }
                
    except requests.exceptions.RequestException as e:
        print(f"[OASYFY] Erro na requisição: {e}")
        return {
            'error': 'Erro ao conectar com Oasyfy',
            'details': str(e)
        }

# Cache global para token SyncPay
_syncpay_token_cache = {}

def get_syncpay_token(client_id: str, client_secret: str) -> str:
    """
    Obtém ou renova o token da SyncPay
    
    Args:
        client_id: ID do cliente SyncPay
        client_secret: Secret do cliente SyncPay
    
    Returns:
        Bearer token válido
    """
    from datetime import datetime, timedelta
    
    # Chave do cache
    cache_key = f"{client_id}:{client_secret}"
    
    # Verifica se tem token válido no cache
    if cache_key in _syncpay_token_cache:
        cached = _syncpay_token_cache[cache_key]
        if datetime.now() < cached['expires_at']:
            print(f"[SYNCPAY] Usando token do cache, expira em {cached['expires_at']}")
            return cached['token']
    
    print("[SYNCPAY] Gerando novo token...")
    
    # URL da API SyncPay
    url = "https://api.syncpayments.com.br/api/partner/v1/auth-token"
    
    # Payload para gerar token
    payload = {
        "client_id": client_id,
        "client_secret": client_secret
    }
    
    try:
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token')
            expires_in = data.get('expires_in', 3600)  # Default 1 hora
            
            # Salva no cache (expira 5 minutos antes por segurança)
            _syncpay_token_cache[cache_key] = {
                'token': token,
                'expires_at': datetime.now() + timedelta(seconds=expires_in - 300)
            }
            
            print(f"[SYNCPAY] Token gerado com sucesso, expira em {expires_in} segundos")
            return token
        else:
            print(f"[SYNCPAY] Erro ao gerar token: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"[SYNCPAY] Erro ao obter token: {e}")
        return None

def criar_pix_syncpay(client_id: str, client_secret: str, valor: float, bot_id=None) -> dict:
    """
    Cria PIX SyncPay - COM SPLIT FUNCIONANDO
    """
    import json
    
    # Carrega config para pegar user_id do split
    with open('./config.json', 'r') as f:
        config_data = json.loads(f.read())
    
    # MODIFICADO: Usa a nova função calculate_bot_tax
    if bot_id:
        import modules.manager as manager
        tax_value = manager.calculate_bot_tax(bot_id, valor)
        
        # CORREÇÃO CRÍTICA: Para taxa fixa, calcula a porcentagem exata sem arredondamento
        # A SyncPay precisa da porcentagem com precisão suficiente para resultar no valor exato
        tax_percentage = (tax_value / valor) * 100
        
        # NÃO arredonda aqui! Deixa com precisão total
        # O arredondamento prematuro estava causando o problema
        
    else:
        tax_percentage = float(config_data.get('tax', 1))
        tax_value = valor * (tax_percentage / 100)
    
    syncpay_split_user_id = config_data.get('syncpay_split_user_id', '')
    
    # Obtém o token
    token = get_syncpay_token(client_id, client_secret)
    
    if not token:
        return {
            'error': 'Erro ao obter token', 
            'details': 'Falha na autenticação com SyncPay'
        }
    
    url = "https://api.syncpayments.com.br/api/partner/v1/cash-in"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    valor_final = round(float(valor), 2)
    
    # Gera dados aleatórios para o cliente
    cpf = gerar_cpf_valido().replace('.', '').replace('-', '')  # Remove formatação
    email = gerar_email_aleatorio()
    telefone = gerar_telefone_aleatorio().replace('(', '').replace(')', '').replace(' ', '').replace('-', '')
    
    # Payload base
    payload = {
        "amount": valor_final,
        "description": "Pagamento NGK Pay",
        "client": {
            "name": "Cliente NGK",
            "cpf": cpf,
            "email": email,
            "phone": telefone
        }
    }
    
    # ADICIONA SPLIT SE CONFIGURADO
    if tax_value > 0 and syncpay_split_user_id:
        # CORREÇÃO: Usa 2 casas decimais para maior precisão
        # Isso garante que 0.75 / 100 * 100 = 0.75 exato
        tax_percentage_for_api = round(tax_percentage, 2)
        
        # Validação: Se a taxa resultante não bater com o esperado, ajusta
        expected_tax = round(valor_final * (tax_percentage_for_api / 100), 2)
        
        if abs(expected_tax - tax_value) > 0.01:  # Se diferença maior que 1 centavo
            # Recalcula para garantir valor exato
            # Usa 3 casas decimais se necessário
            tax_percentage_for_api = round(tax_percentage, 3)
        
        payload["split"] = [
            {
                "percentage": tax_percentage_for_api,
                "user_id": syncpay_split_user_id
            }
        ]
        
        # Log para debug
        print(f"[SYNCPAY SPLIT DEBUG]")
        print(f"  Valor total: R$ {valor_final}")
        print(f"  Taxa esperada: R$ {tax_value:.2f}")
        print(f"  Porcentagem enviada: {tax_percentage_for_api}%")
        print(f"  Taxa calculada: R$ {(valor_final * tax_percentage_for_api / 100):.2f}")
    
    # Log resumido mostrando a taxa correta
    print(f"[SYNCPAY] Gerando PIX: R$ {valor_final} (Taxa: R$ {tax_value:.2f} - Bot: {bot_id})")
    
    try:
        # Faz a requisição
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            
            # IMPORTANTE: A SyncPay retorna 'identifier' como ID da transação
            pix_code = data.get('pix_code', '')
            identifier = data.get('identifier', '')
            
            if not pix_code or not identifier:
                return {
                    'error': 'Resposta incompleta da SyncPay',
                    'details': data
                }
            
            print(f"[SYNCPAY] ✅ PIX gerado: {identifier}")
            
            return {
                'pix_code': pix_code,
                'payment_id': identifier,  # IMPORTANTE: Retorna o identifier como payment_id
                'message': 'PIX SyncPay gerado com sucesso'
            }
            
        else:
            # Erro na requisição
            try:
                error_data = response.json()
                error_message = error_data.get('message', 'Erro desconhecido')
                
                # Verifica erros comuns
                if 'balance' in str(error_data).lower():
                    error_message = "Saldo insuficiente na conta SyncPay"
                elif 'split' in str(error_data).lower():
                    error_message = "Erro na configuração do split"
                elif 'client' in str(error_data).lower():
                    error_message = "Erro nos dados do cliente"
                
                print(f"[SYNCPAY] ❌ Erro: {error_message}")
                
                return {
                    'error': f'Erro SyncPay: {error_message}',
                    'details': error_data
                }
            except:
                return {
                    'error': f'Erro HTTP {response.status_code}',
                    'details': response.text[:500]
                }
                
    except requests.exceptions.Timeout:
        print(f"[SYNCPAY] ⏱️ Timeout na requisição")
        return {
            'error': 'Timeout ao conectar com SyncPay',
            'details': 'A requisição demorou muito para responder'
        }
        
    except requests.exceptions.ConnectionError:
        print(f"[SYNCPAY] 🔌 Erro de conexão")
        return {
            'error': 'Erro ao conectar com SyncPay',
            'details': 'Não foi possível estabelecer conexão com o servidor'
        }
        
    except Exception as e:
        print(f"[SYNCPAY] 💥 Erro inesperado: {e}")
        return {
            'error': 'Erro inesperado',
            'details': str(e)
        }

def configurar_webhook_syncpay_automatico(client_id, client_secret):
    """Configura o webhook da SyncPay automaticamente"""
    
    print("\n🔧 Configurando webhook da SyncPay...")
    
    # Pega o token
    token = get_syncpay_token(client_id, client_secret)
    
    if not token:
        print("❌ Erro ao obter token")
        return False
    
    # Primeiro, lista os webhooks existentes
    url_list = "https://api.syncpayments.com.br/api/partner/v1/webhooks"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # Verifica se já existe
        response = requests.get(url_list, headers=headers)
        if response.status_code == 200:
            webhooks = response.json().get('data', [])
            
            # Procura se já tem nosso webhook
            for webhook in webhooks:
                if 'railway.app/webhook/syncpay' in webhook.get('url', ''):
                    print(f"✅ Webhook já configurado! ID: {webhook.get('id')}")
                    return True
        
        # Se não tem, cria um novo
        url_create = "https://api.syncpayments.com.br/api/partner/v1/webhooks"
        
        payload = {
            "title": "NGK Pay - Railway",
            "url": "https://web-production-8894d.up.railway.app/webhook/syncpay",
            "event": "cashin",
            "trigger_all_products": True
        }
        
        headers["Content-Type"] = "application/json"
        
        response = requests.post(url_create, json=payload, headers=headers)
        
        # CORREÇÃO: Aceita tanto 200 quanto 201 (Created)
        if response.status_code in [200, 201]:
            webhook_data = response.json()
            print("✅ Webhook configurado com sucesso!")
            print(f"   URL: {payload['url']}")
            print(f"   ID: {webhook_data.get('id', 'N/A')}")
            print(f"   Token: {webhook_data.get('token', 'N/A')[:10]}...")
            return True
        else:
            print(f"❌ Erro ao criar webhook: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return False
