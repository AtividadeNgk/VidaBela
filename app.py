from flask import Flask, jsonify, request, send_file, session, redirect, url_for
import modules.manager as manager
from datetime import datetime
from modules.utmify import utmify_api
import asyncio, json, requests, datetime, time
import mercadopago, os
import sqlite3  
import modules.facebook_conversions as fb_conv  # ADICIONAR este import
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from multiprocessing import Process
from bot import run_bot_sync
from comandos.suporte import conv_handler_suporte
from flask_cors import CORS
import string
import random
import hashlib

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
CACHE_LOCK = threading.Lock()
GROUPS_CACHE = {}              # Adiciona logo abaixo
def clear_cache_entry(key):    # Adiciona depois
    """Remove entrada do cache de forma segura"""
    with CACHE_LOCK:
        GROUPS_CACHE.pop(key, None)

# Configuração do banco com DEBUG completo
print("=" * 50)
print("🔍 DEBUG DO VOLUME")
print("=" * 50)

# Verifica diretórios
print(f"📁 /app/storage existe? {os.path.exists('/app/storage')}")
print(f"📁 /app existe? {os.path.exists('/app')}")
print(f"📁 Diretório atual: {os.getcwd()}")

# Lista conteúdo de /app/storage
if os.path.exists('/app/storage'):
    print("📂 Conteúdo de /app/storage:")
    try:
        files = os.listdir('/app/storage')
        if files:
            for f in files:
                filepath = os.path.join('/app/storage', f)
                size = os.path.getsize(filepath)
                print(f"  - {f} ({size} bytes)")
        else:
            print("  [VAZIO]")
    except Exception as e:
        print(f"  Erro ao listar: {e}")
        
    # Verifica permissões
    print(f"📝 Permissões de /app/storage:")
    print(f"  - Pode ler? {os.access('/app/storage', os.R_OK)}")
    print(f"  - Pode escrever? {os.access('/app/storage', os.W_OK)}")
    print(f"  - Pode executar? {os.access('/app/storage', os.X_OK)}")

# Define DB_PATH
if os.path.exists('/app/storage'):
    DB_PATH = '/app/storage/data.db'
    print(f"✅ Usando volume: {DB_PATH}")
else:
    DB_PATH = 'data.db'
    print(f"📁 Usando local: {DB_PATH}")

# Verifica se o arquivo do banco existe
print(f"🗄️ Arquivo {DB_PATH} existe? {os.path.exists(DB_PATH)}")

# Tenta criar/abrir o banco
try:
    print(f"🔧 Tentando conectar em: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cur = conn.cursor()
    
    # Lista tabelas
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cur.fetchall()
    print(f"📊 Tabelas encontradas: {tables}")
    
    # Conta bots
    try:
        cur.execute("SELECT COUNT(*) FROM BOTS")
        count = cur.fetchone()[0]
        print(f"🤖 Total de bots na tabela: {count}")
    except:
        print("❌ Tabela BOTS não existe ou está vazia")
    
    conn.close()
except Exception as e:
    print(f"❌ Erro ao conectar no banco: {e}")

print("=" * 50)

# Debug
print(f"DEBUG - DB_PATH definido como: {DB_PATH}")
print(f"DEBUG - /data existe? {os.path.exists('/data')}")

# Configurações do Mercado Pago
CLIENT_ID = os.environ.get("CLIENT_ID", "4714763730515747")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET", "i33hQ8VZ11pYH1I3xMEMECphRJjT0CiP")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", 'kekel')

# ⬇️ ADICIONE ESTAS LINHAS LOGO ABAIXO ⬇️

# Configurar CORS para aceitar requisições do GitHub Pages
CORS(app, resources={
    r"/api/*": {
        "origins": ["*"],  # Aceita de qualquer origem
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

fbclid_storage = {}
# Carrega configurações
try:
    config = json.loads(open('./config.json', 'r').read())
except:
    config = {}

# Usa variáveis de ambiente com fallback para config.json
IP_DA_VPS = os.environ.get("URL", config.get("url", "https://localhost:4040"))
REGISTRO_TOKEN = os.environ.get("REGISTRO_TOKEN", config.get("registro", ""))
ADMIN_PASSWORD = os.environ.get("PASSWORD", config.get("password", "adminadmin"))

# Porta do Railway ou padrão
port = int(os.environ.get("PORT", 4040))

dashboard_data = {
    "botsActive": 0,
    "usersCount": 0,
    "salesCount": 0
}

bots_data = {}
processes = {}
tokens = []
bot_status_cache = {}
CACHE_TTL = 300  # Cache por 5 minutos
event_loop = asyncio.new_event_loop()

def get_bot_info_cached(bot_token):
    """
    Verifica informações do bot com cache de 5 minutos.
    Usa o bot_status_cache existente.
    """
    cache_key = bot_token[:20]  # Usa os primeiros 20 chars como já está no código
    now = time.time()
    
    # Usa o bot_status_cache existente
    if cache_key in bot_status_cache:
        cached_data, timestamp = bot_status_cache[cache_key]
        if now - timestamp < CACHE_TTL:
            print(f"[CACHE HIT] Bot info do cache")
            return cached_data
    
    # Se não tem cache válido, busca do Telegram
    print(f"[CACHE MISS] Buscando bot info do Telegram")
    try:
        data = manager.check_bot_token(bot_token)
    except Exception as e:
        print(f"[CACHE ERROR] Erro ao verificar token: {e}")
        data = None
    
    # Armazena no cache existente
    bot_status_cache[cache_key] = (data, now)
    
    return data

def clear_old_cache():
    """
    Remove entradas antigas do cache existente.
    """
    global bot_status_cache
    now = time.time()
    
    keys_to_remove = []
    for key, (data, timestamp) in list(bot_status_cache.items()):
        if now - timestamp > CACHE_TTL:
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        del bot_status_cache[key]
    
    if keys_to_remove:
        print(f"[CACHE CLEANER] Removidas {len(keys_to_remove)} entradas antigas")
    
    # Reagenda para rodar novamente em 5 minutos
    timer = threading.Timer(300, clear_old_cache)
    timer.daemon = True
    timer.start()

# Estados para o bot de registro
REGISTRO_MENU, REGISTRO_AGUARDANDO_TOKEN, REGISTRO_SELECIONAR_BOT, REGISTRO_AGUARDANDO_NOVO_TOKEN, REGISTRO_DELETAR_BOT = range(5)

def initialize_all_registered_bots():
    """Inicializa todos os bots registrados e ativos com carregamento gradual."""
    print('Inicializando bots registrados...')
    
    # Marca todos os bots como ativos para não deletar bots existentes
    manager.mark_all_bots_active()
    
    global bots_data, processes
    bots = manager.get_all_bots()
    total_bots = len(bots)
    print(f'Encontrados {total_bots} bots')
    
    # Define tamanho do lote e delay
    BATCH_SIZE = 10
    BATCH_DELAY = 5  # segundos entre lotes
    
    # Processa bots em lotes
    for i in range(0, total_bots, BATCH_SIZE):
        batch = bots[i:i + BATCH_SIZE]
        batch_number = (i // BATCH_SIZE) + 1
        total_batches = (total_bots + BATCH_SIZE - 1) // BATCH_SIZE
        
        print(f'\n📦 Iniciando lote {batch_number}/{total_batches} ({len(batch)} bots)...')
        
        for bot in batch:
            bot_id = bot[0]

            # Verifica se já existe um processo rodando para este bot
            if str(bot_id) in processes and processes[str(bot_id)].is_alive():
                print(f"Bot {bot_id} já está em execução. Ignorando nova inicialização.")
                continue

            try:
                start_bot(bot[1], bot_id)
                print(f"✅ Bot {bot_id} iniciado com sucesso.")
                
                # CORREÇÃO: Garante que o bot_id seja string no dicionário processes
                if str(bot_id) not in processes and bot_id in processes:
                    processes[str(bot_id)] = processes[bot_id]
                    processes.pop(bot_id)
                
            except Exception as e:
                print(f"❌ Erro ao iniciar o bot {bot_id}: {e}")
        
        # Aguarda antes do próximo lote (exceto no último)
        if i + BATCH_SIZE < total_bots:
            print(f'⏳ Aguardando {BATCH_DELAY} segundos antes do próximo lote...')
            time.sleep(BATCH_DELAY)
    
    # Aguarda um pouco para garantir que todos os bots iniciaram
    print('\n✅ Todos os bots foram iniciados!')
    time.sleep(2)
    
    # Inicia disparos programados para todos os bots
    print('\nInicializando disparos programados...')
    bots_with_broadcasts = manager.get_all_bots_with_scheduled_broadcasts()
    print(f'Encontrados {len(bots_with_broadcasts)} bots com disparos programados')
    
    # Os disparos serão iniciados individualmente por cada bot quando ele iniciar

@app.route('/callback', methods=['GET'])
def callback():
    """
    Endpoint para receber o webhook de redirecionamento do Mercado Pago.
    """
    TOKEN_URL = "https://api.mercadopago.com/oauth/token"

    authorization_code = request.args.get('code')
    bot_id = request.args.get('state')

    if not authorization_code:
        return jsonify({"error": "Authorization code not provided"}), 400

    try:
        payload = {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": authorization_code,
            "redirect_uri": IP_DA_VPS+'/callback',
            "state":bot_id,
        }
        
        response = requests.post(TOKEN_URL, data=payload)
        response_data = response.json()

        if response.status_code == 200:
            access_token = response_data.get("access_token")
            print(f"Token MP recebido para bot {bot_id}")
            manager.update_bot_gateway(bot_id, {'type':"MP", 'token':access_token})
            return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Token Cadastrado</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f4f4f9;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            color: #333;
        }
        .container {
            background-color: #fff;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
            border-radius: 8px;
            padding: 20px 30px;
            text-align: center;
            max-width: 400px;
        }
        .container h1 {
            color: #4caf50;
            font-size: 24px;
            margin-bottom: 10px;
        }
        .container p {
            font-size: 16px;
            margin-bottom: 20px;
        }
        .btn {
            display: inline-block;
            padding: 10px 20px;
            font-size: 14px;
            color: #fff;
            background-color: #4caf50;
            text-decoration: none;
            border-radius: 4px;
            transition: background-color 0.3s ease;
        }
        .btn:hover {
            background-color: #45a049;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Token Cadastrado com Sucesso!</h1>
        <p>O seu token Mercado Pago está pronto para uso.</p>
    </div>
</body>
</html>
"""
        else:
            return jsonify({"error": response_data}), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
# ADICIONAR ESTAS ROTAS ANTES DE: @app.route('/webhook/mp', methods=['POST'])

def generate_short_id(length=8):
    """Gera um ID curto aleatório"""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def save_fbclid_to_db(short_id, fbclid):
    """Salva o mapeamento no banco de dados"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        # Cria a tabela se não existir
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS FBCLID_MAPPING (
                short_id TEXT PRIMARY KEY,
                fbclid TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        # Remove mapeamentos antigos (mais de 7 dias)
        seven_days_ago = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
        cursor.execute("""
            DELETE FROM FBCLID_MAPPING 
            WHERE created_at < ?
        """, (seven_days_ago,))
        
        # Insere o novo mapeamento
        cursor.execute("""
            INSERT INTO FBCLID_MAPPING (short_id, fbclid, created_at)
            VALUES (?, ?, ?)
        """, (short_id, fbclid, datetime.datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        print(f"[FBCLID DB] Salvo no banco: {short_id}")
        
    except Exception as e:
        print(f"[FBCLID DB] Erro ao salvar: {e}")

def save_tracking_internal(tracking_data):
    """Salva tracking diretamente sem requisição HTTP"""
    try:
        # Gera ID único
        short_id = 'tk_' + generate_short_id()
        while short_id in fbclid_storage:
            short_id = 'tk_' + generate_short_id()
        
        # SEMPRE salva no storage temporário (memória)
        fbclid_storage[short_id] = {
            'tracking': tracking_data,
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        print(f"[TRACKING INTERNO] Salvo na memória: {short_id}")
        
        # Tenta salvar no banco mas não falha se der erro
        save_tracking_to_db(short_id, tracking_data)
        
        return short_id
        
    except Exception as e:
        print(f"[TRACKING INTERNO] Erro: {e}")
        # Mesmo com erro, retorna o ID pois está na memória
        return short_id if 'short_id' in locals() else None
        
def get_bot_status_cached(bot_token):
    """Verifica status do bot com cache"""
    cache_key = bot_token[:20]  # Usa primeiros 20 chars como chave
    now = time.time()
    
    # Verifica se tem no cache e ainda é válido
    if cache_key in bot_status_cache:
        cached_data, timestamp = bot_status_cache[cache_key]
        if now - timestamp < CACHE_TTL:
            print(f"[CACHE HIT] Bot status do cache")
            return cached_data
    
    # Busca status real
    print(f"[CACHE MISS] Verificando bot no Telegram...")
    bot_details = manager.check_bot_token(bot_token)
    
    # Salva no cache
    bot_status_cache[cache_key] = (bot_details, now)
    
    return bot_details

def save_tracking_to_db(short_id, tracking_data):
    """Salva o mapeamento completo de tracking no banco de dados - OTIMIZADO"""
    max_retries = 3
    retry_delay = 0.1
    
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            cursor = conn.cursor()
            
            # ADICIONA COLUNAS SE NÃO EXISTIREM
            try:
                cursor.execute("ALTER TABLE TRACKING_MAPPING ADD COLUMN client_ip TEXT")
                print("[TRACKING DB] Coluna client_ip adicionada")
            except:
                pass  # Coluna já existe
            
            try:
                cursor.execute("ALTER TABLE TRACKING_MAPPING ADD COLUMN user_agent TEXT")
                print("[TRACKING DB] Coluna user_agent adicionada")
            except:
                pass  # Coluna já existe
            
            # Remove mapeamentos antigos (não crítico)
            try:
                seven_days_ago = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
                cursor.execute("""
                    DELETE FROM TRACKING_MAPPING 
                    WHERE created_at < ?
                """, (seven_days_ago,))
            except:
                pass
            
            # Insere o novo mapeamento
            cursor.execute("""
                INSERT OR REPLACE INTO TRACKING_MAPPING 
                (short_id, fbclid, utm_source, utm_campaign, utm_medium, utm_content, utm_term, 
                 src, sck, fbp, fbc, client_ip, user_agent, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                short_id,
                tracking_data.get('fbclid'),
                tracking_data.get('utm_source'),
                tracking_data.get('utm_campaign'),
                tracking_data.get('utm_medium'),
                tracking_data.get('utm_content'),
                tracking_data.get('utm_term'),
                tracking_data.get('src'),
                tracking_data.get('sck'),
                tracking_data.get('fbp'),
                tracking_data.get('fbc'),
                tracking_data.get('client_ip'),
                tracking_data.get('user_agent'),
                datetime.datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            print(f"[TRACKING DB] Salvo no banco: {short_id}")
            return True
            
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < max_retries - 1:
                print(f"[TRACKING DB] Database locked, tentativa {attempt + 1}/{max_retries}")
                time.sleep(retry_delay * (attempt + 1))
                continue
            else:
                print(f"[TRACKING DB] Erro ao salvar: {e}")
                return False
        except Exception as e:
            print(f"[TRACKING DB] Erro inesperado: {e}")
            return False
    
    return False

def get_tracking_from_db(short_id):
    """Recupera tracking completo do banco de dados"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT fbclid, utm_source, utm_campaign, utm_medium, 
                   utm_content, utm_term, src, sck, fbp, fbc, client_ip, user_agent
            FROM TRACKING_MAPPING 
            WHERE short_id = ?
        """, (short_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            print(f"[TRACKING DB] Recuperado do banco: {short_id}")
            return {
                'fbclid': result[0],
                'utm_source': result[1],
                'utm_campaign': result[2],
                'utm_medium': result[3],
                'utm_content': result[4],
                'utm_term': result[5],
                'src': result[6],
                'sck': result[7],
                'fbp': result[8],
                'fbc': result[9],
                'client_ip': result[10],    # NOVO
                'user_agent': result[11]     # NOVO
            }
        return None
        
    except Exception as e:
        print(f"[TRACKING DB] Erro ao recuperar: {e}")
        return None

def get_fbclid_from_db(short_id):
    """Recupera o fbclid do banco de dados"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT fbclid FROM FBCLID_MAPPING 
            WHERE short_id = ?
        """, (short_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            print(f"[FBCLID DB] Recuperado do banco: {short_id}")
            return result[0]
        return None
        
    except Exception as e:
        print(f"[FBCLID DB] Erro ao recuperar: {e}")
        return None

def render_html_redirect(bot_username, short_id, client_ip, tracking_id=None):
    """
    Gera HTML com JavaScript para capturar cookies e redirecionar.
    Design minimalista igual ao fornecido.
    """
    
    # Define o destino final
    if tracking_id:
        telegram_url = "https://t.me/" + bot_username + "?start=" + tracking_id
    else:
        telegram_url = "https://t.me/" + bot_username
    
    html = '''<!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Redirecionando...</title>
        <meta http-equiv="refresh" content="2;url=''' + telegram_url + '''">
        <style>
            body {
                margin: 0;
                height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                background: #fff;
                font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            }
            .container {
                text-align: center;
            }
            .loader {
                width: 60px;
                height: 60px;
                margin: 0 auto 30px;
                border: 4px solid #f3f3f3;
                border-top: 4px solid #6366f1;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
            }
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
            h1 {
                color: #111;
                font-size: 32px;
                font-weight: 600;
                margin: 0 0 12px;
            }
            p {
                color: #666;
                font-size: 18px;
                margin: 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="loader"></div>
            <h1>Acessando</h1>
            <p>Aguarde um momento...</p>
        </div>
        
        <script>
            // Função para ler cookie
            function getCookie(name) {
                const value = '; ' + document.cookie;
                const parts = value.split('; ' + name + '=');
                if (parts.length === 2) return parts.pop().split(';').shift();
                return null;
            }
            
            // Função para pegar parâmetros da URL
            function getURLParam(name) {
                const urlParams = new URLSearchParams(window.location.search);
                return urlParams.get(name);
            }
            
            // Executa imediatamente
            (async function() {
                try {
                    // Aguarda 300ms para dar tempo do cookie _fbp ser criado
                    await new Promise(resolve => setTimeout(resolve, 300));
                    
                    // Captura todos os dados
                    const trackingData = {
                        // Parâmetros da URL
                        fbclid: getURLParam('fbclid'),
                        utm_source: getURLParam('utm_source'),
                        utm_campaign: getURLParam('utm_campaign'),
                        utm_medium: getURLParam('utm_medium'),
                        utm_content: getURLParam('utm_content'),
                        utm_term: getURLParam('utm_term'),
                        src: getURLParam('src'),
                        sck: getURLParam('sck'),
                        
                        // Cookies do Facebook
                        fbp: getCookie('_fbp'),
                        fbc: getCookie('_fbc'),
                        
                        // Dados do navegador
                        user_agent: navigator.userAgent,
                        client_ip: "''' + client_ip + '''"
                    };
                    
                    // Se não tem _fbc mas tem fbclid, gera o _fbc
                    if (!trackingData.fbc && trackingData.fbclid) {
                        trackingData.fbc = 'fb.1.' + Date.now() + '.' + trackingData.fbclid;
                    }
                    
                    // Verifica se tem algum dado para enviar
                    const hasTracking = trackingData.fbclid || trackingData.utm_source || 
                                       trackingData.utm_campaign || trackingData.fbp;
                    
                    if (hasTracking) {
                        // Envia para o servidor
                        const response = await fetch('/api/save-tracking', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify(trackingData)
                        });
                        
                        if (response.ok) {
                            const result = await response.json();
                            // Redireciona com o short_id
                            window.location.replace('https://t.me/''' + bot_username + '''?start=' + result.short_id);
                        } else {
                            // Erro - redireciona sem tracking
                            window.location.replace("''' + telegram_url + '''");
                        }
                    } else {
                        // Sem tracking - redirect direto
                        window.location.replace("''' + telegram_url + '''");
                    }
                    
                } catch (error) {
                    // Qualquer erro - redireciona direto
                    window.location.replace("''' + telegram_url + '''");
                }
            })();
            
            // FALLBACK: Se não redirecionou em 2 segundos, força
            setTimeout(function() {
                window.location.replace("''' + telegram_url + '''");
            }, 2000);
        </script>
    </body>
    </html>'''
    
    return html

@app.route('/api/save-fbclid', methods=['POST', 'OPTIONS'])
def save_fbclid():
    """Salva o fbclid e retorna um ID curto"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        data = request.get_json()
        fbclid = data.get('fbclid')
        
        if not fbclid:
            return jsonify({"error": "fbclid não fornecido"}), 400
        
        # Gera um ID curto único
        short_id = generate_short_id()
        while short_id in fbclid_storage:
            short_id = generate_short_id()
        
        # Salva no storage temporário
        fbclid_storage[short_id] = {
            'fbclid': fbclid,
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        # Salva no banco de dados
        save_fbclid_to_db(short_id, fbclid)
        
        print(f"[FBCLID] Salvo: {short_id} -> {fbclid[:30]}...")
        
        response = jsonify({"short_id": short_id})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 200
        
    except Exception as e:
        print(f"[FBCLID] Erro ao salvar: {e}")
        response = jsonify({"error": str(e)})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

@app.route('/api/get-fbclid/<short_id>', methods=['GET'])
def get_fbclid(short_id):
    """Recupera o fbclid original pelo ID curto"""
    try:
        # Tenta no storage temporário primeiro
        if short_id in fbclid_storage:
            return jsonify({"fbclid": fbclid_storage[short_id]['fbclid']}), 200
        
        # Tenta no banco de dados
        fbclid = get_fbclid_from_db(short_id)
        if fbclid:
            return jsonify({"fbclid": fbclid}), 200
        
        return jsonify({"error": "ID não encontrado"}), 404
        
    except Exception as e:
        print(f"[FBCLID] Erro ao recuperar: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/save-tracking', methods=['POST', 'OPTIONS'])
def save_tracking():
    """Salva tracking completo com UTMs e retorna um ID curto"""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
        response.headers.add('Access-Control-Allow-Methods', 'POST')
        return response
    
    try:
        data = request.get_json()
        
        # NOVO: Log detalhado dos dados recebidos
        print(f"[SAVE-TRACKING] ===== DADOS RECEBIDOS =====")
        print(f"[SAVE-TRACKING] IP do Cliente: {data.get('client_ip', 'NÃO CAPTURADO')}")
        print(f"[SAVE-TRACKING] User-Agent: {data.get('user_agent', 'NÃO CAPTURADO')[:100]}...")
        print(f"[SAVE-TRACKING] Cookie FBP: {data.get('fbp', 'NÃO CAPTURADO')}")
        print(f"[SAVE-TRACKING] Cookie FBC: {data.get('fbc', 'NÃO CAPTURADO')}")
        print(f"[SAVE-TRACKING] FBCLID: {data.get('fbclid', 'NÃO CAPTURADO')[:30] if data.get('fbclid') else 'NÃO CAPTURADO'}...")
        print(f"[SAVE-TRACKING] UTM Campaign: {data.get('utm_campaign', 'NÃO CAPTURADO')}")
        print(f"[SAVE-TRACKING] UTM Source: {data.get('utm_source', 'NÃO CAPTURADO')}")
        print(f"[SAVE-TRACKING] UTM Medium: {data.get('utm_medium', 'NÃO CAPTURADO')}")
        print(f"[SAVE-TRACKING] UTM Content: {data.get('utm_content', 'NÃO CAPTURADO')}")
        print(f"[SAVE-TRACKING] UTM Term: {data.get('utm_term', 'NÃO CAPTURADO')}")
        print(f"[SAVE-TRACKING] ==============================")
        
        # Extrai todos os dados de tracking
        tracking_data = {
            'fbclid': data.get('fbclid'),
            'utm_source': data.get('utm_source'),
            'utm_campaign': data.get('utm_campaign'),
            'utm_medium': data.get('utm_medium'),
            'utm_content': data.get('utm_content'),
            'utm_term': data.get('utm_term'),
            'src': data.get('src'),
            'sck': data.get('sck'),
            'fbp': data.get('fbp'),
            'fbc': data.get('fbc'),
            # NOVO: Adiciona IP e User-Agent
            'client_ip': data.get('client_ip'),
            'user_agent': data.get('user_agent')
        }
        
        # Gera um ID curto único com prefixo tk_
        short_id = 'tk_' + generate_short_id()
        while short_id in fbclid_storage:
            short_id = 'tk_' + generate_short_id()
        
        # Salva no storage temporário
        fbclid_storage[short_id] = {
            'tracking': tracking_data,
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        # Salva no banco de dados
        save_tracking_to_db(short_id, tracking_data)
        
        print(f"[TRACKING] Salvo com sucesso: {short_id}")
        print(f"  fbclid: {tracking_data.get('fbclid', 'N/A')[:30] if tracking_data.get('fbclid') else 'N/A'}...")
        print(f"  utm_campaign: {tracking_data.get('utm_campaign', 'N/A')}")
        print(f"  utm_content: {tracking_data.get('utm_content', 'N/A')}")
        print(f"  utm_term: {tracking_data.get('utm_term', 'N/A')}")
        print(f"  fbp: {'✓' if tracking_data.get('fbp') else '✗'}")
        print(f"  fbc: {'✓' if tracking_data.get('fbc') else '✗'}")
        print(f"  IP: {tracking_data.get('client_ip', 'N/A')}")
        
        response = jsonify({"short_id": short_id})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 200
        
    except Exception as e:
        print(f"[TRACKING] Erro ao salvar: {e}")
        response = jsonify({"error": str(e)})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

@app.route('/api/get-tracking/<short_id>', methods=['GET'])
def get_tracking(short_id):
    """Recupera tracking completo pelo ID curto"""
    try:
        # Tenta no storage temporário primeiro
        if short_id in fbclid_storage:
            return jsonify(fbclid_storage[short_id]['tracking']), 200
        
        # Tenta no banco de dados
        tracking_data = get_tracking_from_db(short_id)
        if tracking_data:
            return jsonify(tracking_data), 200
        
        # Se não encontrou, mas é um ID antigo fb_, tenta recuperar só o fbclid
        if short_id.startswith('fb_'):
            # Remove o prefixo para compatibilidade
            old_id = short_id[3:]
            fbclid = get_fbclid_from_db(old_id)
            if fbclid:
                return jsonify({'fbclid': fbclid}), 200
        
        return jsonify({"error": "ID não encontrado"}), 404
        
    except Exception as e:
        print(f"[TRACKING] Erro ao recuperar: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/r/<code>', methods=['GET'])
def redirect_contingency(code):
    """Endpoint de redirecionamento otimizado com distribuição funcionando"""
    try:
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if client_ip and ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()
        
        user_agent = request.headers.get('User-Agent', 'Unknown')
        print(f"[REDIRECT] Código: {code}, IP: {client_ip}")
        
        cache_key = f"group_{code}"
        group_data = None
        
        with CACHE_LOCK:
            if cache_key in GROUPS_CACHE:
                group_data = GROUPS_CACHE[cache_key]
                print(f"[CACHE HIT] Grupo {code} do cache")
        
        if not group_data:
            print(f"[CACHE MISS] Buscando grupo {code} do banco")
            
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.execute("PRAGMA journal_mode=WAL")
            cursor = conn.cursor()
            
            # Busca APENAS informações do grupo (sem bot ainda)
            cursor.execute("""
                SELECT id, distribution_enabled, emergency_link
                FROM CONTINGENCY_GROUPS 
                WHERE unique_code = ? AND is_active = 1
            """, (code,))
            
            group_result = cursor.fetchone()
            
            if not group_result:
                conn.close()
                return "Grupo não encontrado", 404
            
            group_id, distribution_enabled, emergency_link = group_result
            
            # Se distribuição está ativada, usa a função de distribuição
            if distribution_enabled == 1:
                conn.close()  # Fecha antes de chamar outra função
                bot_info = manager.get_next_distribution_bot(group_id)
                if bot_info:
                    group_data = {
                        'id': group_id,
                        'distribution': 1,
                        'emergency_link': emergency_link,
                        'bot_id': bot_info['bot_id'],
                        'bot_token': bot_info['bot_token']
                    }
                else:
                    # Sem bots online
                    group_data = {
                        'id': group_id,
                        'distribution': 1,
                        'emergency_link': emergency_link,
                        'bot_id': None,
                        'bot_token': None
                    }
            else:
                # Distribuição desativada - pega primeiro bot online
                cursor.execute("""
                    SELECT bot_id, bot_token
                    FROM CONTINGENCY_BOTS
                    WHERE group_id = ? AND is_online = 1
                    ORDER BY position
                    LIMIT 1
                """, (group_id,))
                
                bot_result = cursor.fetchone()
                conn.close()
                
                if bot_result:
                    group_data = {
                        'id': group_id,
                        'distribution': 0,
                        'emergency_link': emergency_link,
                        'bot_id': bot_result[0],
                        'bot_token': bot_result[1]
                    }
                else:
                    group_data = {
                        'id': group_id,
                        'distribution': 0,
                        'emergency_link': emergency_link,
                        'bot_id': None,
                        'bot_token': None
                    }
            
            # NÃO SALVA NO CACHE SE DISTRIBUIÇÃO ESTÁ ATIVADA
            # Porque cada request precisa pegar um bot diferente
            if distribution_enabled == 0:
                with CACHE_LOCK:
                    GROUPS_CACHE[cache_key] = group_data
                
                timer = threading.Timer(30, clear_cache_entry, args=[cache_key])
                timer.daemon = True
                timer.start()
        
        # Se o cache tem distribuição ativada, busca novo bot
        elif group_data.get('distribution') == 1:
            print(f"[DISTRIBUTION] Grupo com distribuição, buscando próximo bot")
            bot_info = manager.get_next_distribution_bot(group_data['id'])
            if bot_info:
                group_data['bot_id'] = bot_info['bot_id']
                group_data['bot_token'] = bot_info['bot_token']
        
        # Resto do código continua igual...
        if not group_data.get('bot_token'):
            if group_data.get('emergency_link'):
                params = request.args.to_dict()
                query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
                separator = '&' if '?' in group_data['emergency_link'] else '?'
                final_link = f"{group_data['emergency_link']}{separator}{query_string}" if query_string else group_data['emergency_link']
                
                html_page = '''
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Redirecionando...</title>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body {
                            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            height: 100vh;
                            margin: 0;
                        }
                        .container {
                            background: white;
                            border-radius: 20px;
                            padding: 40px;
                            text-align: center;
                            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                            max-width: 400px;
                            width: 90%;
                        }
                        h1 {
                            color: #333;
                            font-size: 24px;
                            margin-bottom: 10px;
                        }
                        p {
                            color: #666;
                            margin-bottom: 30px;
                            line-height: 1.6;
                        }
                        .btn {
                            display: inline-block;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            padding: 15px 40px;
                            border-radius: 30px;
                            text-decoration: none;
                            font-size: 18px;
                            font-weight: bold;
                            transition: transform 0.3s, box-shadow 0.3s;
                            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                        }
                        .btn:hover {
                            transform: translateY(-2px);
                            box-shadow: 0 6px 25px rgba(102, 126, 234, 0.6);
                        }
                        .warning {
                            background: #fff3cd;
                            border-left: 4px solid #ffc107;
                            padding: 10px;
                            margin-top: 20px;
                            border-radius: 5px;
                            text-align: left;
                            font-size: 14px;
                            color: #856404;
                        }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>🚀 Quase lá!</h1>
                        <p>Detectamos alta demanda no momento. Clique no botão abaixo para continuar:</p>
                        <a href="''' + final_link + '''" class="btn">ACESSAR AGORA</a>
                        <div class="warning">
                            ⚡ <strong>Atenção:</strong> Vagas limitadas! Garanta seu acesso agora.
                        </div>
                    </div>
                </body>
                </html>
                '''
                return html_page, 200
            else:
                return """
                <html>
                <body style="font-family: Arial; text-align: center; margin-top: 50px;">
                    <h2>⚠️ Sistema em Manutenção</h2>
                    <p>Todos os bots estão temporariamente offline.</p>
                    <p>Por favor, tente novamente em alguns minutos.</p>
                </body>
                </html>
                """, 503
        
        bot_token = group_data['bot_token']
        
        bot_cache_key = bot_token[:20]
        bot_details = None
        
        if bot_cache_key in bot_status_cache:
            cached_data, timestamp = bot_status_cache[bot_cache_key]
            if time.time() - timestamp < CACHE_TTL:
                bot_details = cached_data
                print(f"[CACHE HIT] Bot status do cache")
        
        if not bot_details:
            print(f"[CACHE MISS] Verificando bot no Telegram")
            bot_details = manager.check_bot_token(bot_token)
            bot_status_cache[bot_cache_key] = (bot_details, time.time())
        
        if not bot_details or not bot_details.get('result'):
            with CACHE_LOCK:
                GROUPS_CACHE.pop(cache_key, None)
            return "Bot indisponível", 503
        
        bot_username = bot_details['result'].get('username')
        
        params = request.args.to_dict()
        
        if any(k in params for k in ['fbclid', 'utm_source', 'utm_campaign', 'utm_medium']):
            return render_html_redirect(bot_username, None, client_ip), 200
        else:
            return redirect(f"https://t.me/{bot_username}", code=302)
        
    except Exception as e:
        print(f"[REDIRECT ERROR] {e}")
        cache_key = f"group_{code}"
        with CACHE_LOCK:
            GROUPS_CACHE.pop(cache_key, None)
        return "Erro temporário. Tente novamente.", 500

@app.route('/api/contingency/check-status', methods=['POST'])
def check_contingency_status():
    """Endpoint interno para verificar status dos bots - OTIMIZADO"""
    try:
        import datetime
        
        # Usa conexão com WAL mode e timeout maior
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")  # Espera até 10 segundos
        cursor = conn.cursor()
        
        # Busca todos os bots em uma query só (mais eficiente)
        cursor.execute("""
            SELECT cb.bot_id, cb.bot_token, cb.group_id, cb.position, cb.is_online,
                   cg.name, cg.owner_id
            FROM CONTINGENCY_BOTS cb
            JOIN CONTINGENCY_GROUPS cg ON cb.group_id = cg.id
            WHERE cg.is_active = 1
        """)
        
        bots_to_check = cursor.fetchall()
        conn.close()  # Fecha logo após ler
        
        notifications = []
        bots_checked = 0
        updates_needed = []
        
        # Verifica bots SEM manter conexão aberta
        for bot_id, bot_token, group_id, position, current_status, group_name, owner_id in bots_to_check:
            time.sleep(0.05)  # 50ms entre verificações (evita burst)
            
            # Verifica se o bot está online
            is_online = False
            try:
                response = requests.get(
                    f"https://api.telegram.org/bot{bot_token}/getMe",
                    timeout=2
                )
                is_online = response.status_code == 200
            except:
                is_online = False
            
            bots_checked += 1
            
            # Se mudou o status, adiciona na lista de updates
            if current_status == 1 and not is_online:
                # Bot ficou offline
                updates_needed.append({
                    'bot_id': bot_id,
                    'group_id': group_id,
                    'is_online': 0,
                    'timestamp': datetime.datetime.now().isoformat()
                })
                
                notifications.append({
                    'owner_id': owner_id,
                    'group_name': group_name,
                    'bot_id': bot_id
                })
                
                print(f"[CHECK STATUS] Bot {bot_id} do grupo '{group_name}' está OFFLINE")
                
                # IMPORTANTE: Limpa cache do grupo
                cache_key = f"group_{group_id}"
                with CACHE_LOCK:
                    GROUPS_CACHE.pop(cache_key, None)
                
            elif current_status == 0 and is_online:
                # Bot voltou online (só atualiza, não notifica)
                updates_needed.append({
                    'bot_id': bot_id,
                    'group_id': group_id,
                    'is_online': 1,
                    'timestamp': datetime.datetime.now().isoformat()
                })
                
                # Limpa cache do grupo
                cache_key = f"group_{group_id}"
                with CACHE_LOCK:
                    GROUPS_CACHE.pop(cache_key, None)
        
        # Faz TODOS os updates de uma vez só
        if updates_needed:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=10000")
            
            # Usa transação única para todos os updates
            conn.execute("BEGIN IMMEDIATE")
            try:
                for update in updates_needed:
                    if update['is_online'] == 0:
                        conn.execute("""
                            UPDATE CONTINGENCY_BOTS 
                            SET is_online = 0, marked_offline_at = ?, last_check = ?
                            WHERE bot_id = ? AND group_id = ?
                        """, (update['timestamp'], update['timestamp'], 
                              update['bot_id'], update['group_id']))
                    else:
                        conn.execute("""
                            UPDATE CONTINGENCY_BOTS 
                            SET is_online = 1, marked_offline_at = NULL, last_check = ?
                            WHERE bot_id = ? AND group_id = ?
                        """, (update['timestamp'], update['bot_id'], update['group_id']))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f"[CHECK STATUS] Erro ao atualizar: {e}")
            finally:
                conn.close()
        
        # Envia notificações (fora da transação do banco)
        for notif in notifications:
            try:
                registro_token = os.environ.get('REGISTRO_TOKEN', '')
                if registro_token:
                    message = (
                        f"⚠️ <b>Bot Offline Detectado!</b>\n\n"
                        f"📊 Grupo: {notif['group_name']}\n"
                        f"🤖 Bot ID: {notif['bot_id']}\n\n"
                        f"O sistema continuará funcionando com os outros bots do grupo.\n"
                        f"Verifique o status do bot no @BotFather."
                    )
                    
                    requests.post(
                        f"https://api.telegram.org/bot{registro_token}/sendMessage",
                        json={
                            'chat_id': notif['owner_id'],
                            'text': message,
                            'parse_mode': 'HTML'
                        },
                        timeout=5
                    )
            except:
                pass  # Ignora erros de notificação
        
        return jsonify({
            'checked': bots_checked, 
            'notifications': len(notifications),
            'timestamp': datetime.datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"[CHECK STATUS] Erro: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check endpoint para testar CORS"""
    response = jsonify({"status": "ok", "cors": "enabled"})
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

@app.route('/webhook/mp', methods=['POST'])
def handle_webhook():
    data = request.get_json(silent=True)
    print(f"Webhook MP recebido: {data}")
    
    if data and data.get('type') == 'payment':
        transaction_id = (data.get('data').get('id'))
        print(f'Pagamento {transaction_id} recebido - Mercado Pago')
        payment = manager.get_payment_by_trans_id(transaction_id)
        
        if payment:
            print(payment)
            bot_id = json.loads(payment[4])
            token = manager.get_bot_gateway(bot_id)
            sdk = mercadopago.SDK(token['token'])
            pagamento = sdk.payment().get(transaction_id)
            pagamento_status = pagamento["response"]["status"]

            if pagamento_status == "approved":
                print(f'Pagamento {transaction_id} aprovado - Mercado Pago')
                manager.update_payment_status(transaction_id, 'paid')
                
                # Pega o fbclid do usuário
                user_id = payment[2]
                fbclid = manager.get_user_fbclid(user_id, bot_id)
                
                # Pega detalhes do plano
                plan_data = json.loads(payment[3])
                
                # NOVO: Pega tracking completo com UTMs
                tracking_data = manager.get_utm_tracking(user_id, bot_id) or {}
                
                # NOVO: Envia para Utmify se configurado
                try:
                    utmify_config = manager.get_utmify_config(bot_id)
                    if utmify_config and utmify_config['enabled']:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                        tax_rate = manager.get_bot_tax(bot_id)
                        
                        # Prepara dados do pedido
                        order_data = {
                            'transaction_id': str(transaction_id),
                            'user_id': user_id,
                            'bot_id': bot_id,
                            'value': plan_data['value'],
                            'plan_name': plan_data['name']
                        }
                        
                        # Envia para Utmify
                        loop.run_until_complete(utmify_api.send_purchase_completed(
                            api_token=utmify_config['api_token'],
                            order_data=order_data,
                            tracking_data=tracking_data
                        ))
                        
                        print(f"[WEBHOOK MP] Conversão enviada para Utmify - User: {user_id}")
                        
                except Exception as e:
                    print(f"[WEBHOOK MP] Erro ao enviar para Utmify: {e}")
                
                # Envia evento Purchase para Facebook (já existente)
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(fb_conv.send_purchase_event(
                        user_id=user_id,
                        bot_id=bot_id,
                        value=plan_data['value'],
                        plan_name=plan_data['name'],
                        fbclid=fbclid
                    ))
                    
                    print(f"[WEBHOOK MP] Conversão enviada para Facebook - User: {user_id}, Valor: R$ {plan_data['value']}")
                    
                except Exception as e:
                    print(f"[WEBHOOK MP] Erro ao enviar conversão: {e}")
                
                return jsonify({"message": "Webhook recebido com sucesso."}), 200
    
    return jsonify({"message": "Evento ignorado."}), 400

@app.route('/webhook/pp', methods=['POST'])
def webhook():
    if request.content_type == 'application/json':
        data = request.get_json()
    elif request.content_type == 'application/x-www-form-urlencoded':
        data = request.form.to_dict()
    else:
        print("[ERRO] Tipo de conteúdo não suportado")
        return jsonify({"error": "Unsupported Media Type"}), 415

    if not data:
        print("[ERRO] Dados JSON ou Form Data inválidos")
        return jsonify({"error": "Invalid JSON or Form Data"}), 400
    
    print(f"[DEBUG] Webhook PP recebido: {data}")
    transaction_id = data.get("id", "").lower()
    
    if data.get('status', '').lower() == 'paid':
        print(f'Pagamento {transaction_id} pago - PushinPay')
        
        # Pega informações do pagamento
        payment = manager.get_payment_by_trans_id(transaction_id)
        if payment:
            user_id = payment[2]
            bot_id = payment[4]
            plan_data = json.loads(payment[3])
            
            # Atualiza status do pagamento
            manager.update_payment_status(transaction_id, 'paid')
            
            print(f'[PP] Pagamento aprovado: {transaction_id}')
            print(f'     Valor: R$ {plan_data.get("value", 0)}')
            
            # Pega o fbclid do usuário
            fbclid = manager.get_user_fbclid(user_id, bot_id)
            
            # Pega tracking completo com UTMs
            tracking_data = manager.get_utm_tracking(user_id, bot_id) or {}
            
            # Envia para Utmify se configurado
            try:
                utmify_config = manager.get_utmify_config(bot_id)
                if utmify_config and utmify_config['enabled']:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Pega a taxa atual para enviar pro Utmify
                    bot_tax_rate = manager.get_bot_tax(bot_id)
                    value = float(plan_data.get('value', 0))
                    tax_amount = value * (bot_tax_rate / 100)
                    
                    # Prepara dados do pedido
                    order_data = {
                        'transaction_id': str(transaction_id),
                        'user_id': user_id,
                        'bot_id': bot_id,
                        'value': value,
                        'plan_name': plan_data.get('name', 'Plano VIP')
                    }
                    
                    # Envia para Utmify
                    loop.run_until_complete(utmify_api.send_purchase_completed(
                        api_token=utmify_config['api_token'],
                        order_data=order_data,
                        tracking_data=tracking_data
                    ))
                    
                    print(f"[WEBHOOK PP] Conversão enviada para Utmify - User: {user_id}, Valor: R$ {value}")
                    
            except Exception as e:
                print(f"[WEBHOOK PP] Erro ao enviar para Utmify: {e}")
                import traceback
                traceback.print_exc()
            
            # Envia evento Purchase para Facebook
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(fb_conv.send_purchase_event(
                    user_id=user_id,
                    bot_id=bot_id,
                    value=float(plan_data.get('value', 0)),
                    plan_name=plan_data.get('name', 'Plano VIP'),
                    fbclid=fbclid
                ))
                
                print(f"[WEBHOOK PP] Conversão Purchase enviada - User: {user_id}")
                
            except Exception as e:
                print(f"[WEBHOOK PP] Erro ao enviar conversão: {e}")
                import traceback
                traceback.print_exc()
            
            # Notifica o usuário
            try:
                bot_token = manager.get_bot_token(bot_id)
                if bot_token:
                    import requests
                    
                    message_text = "✅ *Pagamento Aprovado!*\n\nSeu pagamento foi confirmado com sucesso.\nAcesso liberado!"
                    
                    telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    telegram_data = {
                        'chat_id': user_id,
                        'text': message_text,
                        'parse_mode': 'Markdown'
                    }
                    
                    response = requests.post(telegram_url, json=telegram_data)
                    if response.status_code == 200:
                        print(f"[WEBHOOK PP] Notificação enviada ao usuário {user_id}")
                    else:
                        print(f"[WEBHOOK PP] Erro ao enviar notificação: {response.text}")
                        
            except Exception as e:
                print(f"[WEBHOOK PP] Erro ao enviar notificação Telegram: {e}")
                
    else:
        print(f"[ERRO] Status do pagamento não é 'paid': {data.get('status')}")

    return jsonify({"status": "success"})

@app.route('/webhook/oasyfy', methods=['POST'])
def webhook_oasyfy():
    """Webhook para processar notificações da Oasyfy"""
    
    try:
        # Pega os dados do webhook
        data = request.get_json()
        
        if not data:
            print("[OASYFY WEBHOOK] Dados JSON inválidos")
            return jsonify({"error": "Invalid JSON"}), 400
        
        print(f"[OASYFY WEBHOOK] Recebido: {json.dumps(data, indent=2)}")
        
        # Extrai informações do webhook
        event = data.get('event')
        transaction = data.get('transaction', {})
        transaction_id = transaction.get('id')
        status = transaction.get('status')
        client = data.get('client', {})
        order_items = data.get('orderItems', [])
        track_props = data.get('trackProps', {})
        
        print(f"[OASYFY WEBHOOK] Evento: {event}, Status: {status}, ID: {transaction_id}")
        
        # Processa apenas eventos de pagamento confirmado
        if event == 'TRANSACTION_PAID' and status == 'COMPLETED':
            print(f'[OASYFY] Pagamento {transaction_id} confirmado')
            
            # Busca o pagamento pelo ID da transação
            payment = manager.get_payment_by_trans_id(transaction_id)
            
            if payment:
                print(f"[OASYFY] Pagamento encontrado no banco: {payment}")
                
                # Atualiza status para pago
                manager.update_payment_status(transaction_id, 'paid')
                
                # Extrai informações para tracking
                user_id = payment[2]
                bot_id = payment[4]
                plan_data = json.loads(payment[3])
                
                # TRACKING: Salva UTMs se vieram no trackProps
                if track_props:
                    tracking_data = {
                        'fbclid': track_props.get('fbc'),
                        'utm_source': track_props.get('utm_source'),
                        'utm_campaign': track_props.get('utm_campaign'),
                        'utm_medium': track_props.get('utm_medium'),
                        'utm_content': track_props.get('utm_content'),
                        'utm_term': track_props.get('utm_term'),
                        'src': track_props.get('src'),
                        'sck': track_props.get('sck')
                    }
                    
                    # Salva tracking se tiver dados
                    if any(tracking_data.values()):
                        manager.save_utm_tracking(user_id, bot_id, tracking_data)
                        print(f"[OASYFY] Tracking salvo: {tracking_data}")
                
                # UTMIFY: Envia para Utmify se configurado
                try:
                    utmify_config = manager.get_utmify_config(bot_id)
                    if utmify_config and utmify_config['enabled']:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        # Pega tracking completo
                        tracking_data = manager.get_utm_tracking(user_id, bot_id) or {}

                        tax_rate = manager.get_bot_tax(bot_id)
                        
                        # Prepara dados do pedido
                        order_data = {
                            'transaction_id': str(transaction_id),
                            'user_id': user_id,
                            'bot_id': bot_id,
                            'value': plan_data['value'],
                            'plan_name': plan_data['name']
                        }
                        
                        # Envia para Utmify
                        from modules.utmify import utmify_api
                        loop.run_until_complete(utmify_api.send_purchase_completed(
                            api_token=utmify_config['api_token'],
                            order_data=order_data,
                            tracking_data=tracking_data
                        ))
                        
                        print(f"[OASYFY] Conversão enviada para Utmify - User: {user_id}")
                        
                except Exception as e:
                    print(f"[OASYFY] Erro ao enviar para Utmify: {e}")
                    import traceback
                    traceback.print_exc()
                
                # FACEBOOK: Envia evento Purchase
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Pega o fbclid
                    fbclid = None
                    if track_props and track_props.get('fbc'):
                        # Extrai o fbclid do formato fb.1.timestamp.fbclid
                        fbc_parts = track_props['fbc'].split('.')
                        if len(fbc_parts) >= 4:
                            fbclid = fbc_parts[3]
                    
                    if not fbclid:
                        fbclid = manager.get_user_fbclid(user_id, bot_id)
                    
                    # Envia evento Purchase
                    import modules.facebook_conversions as fb_conv
                    loop.run_until_complete(fb_conv.send_purchase_event(
                        user_id=user_id,
                        bot_id=bot_id,
                        value=plan_data['value'],
                        plan_name=plan_data['name'],
                        fbclid=fbclid
                    ))
                    
                    print(f"[OASYFY] Conversão Purchase enviada para Facebook - User: {user_id}, Valor: R$ {plan_data['value']}")
                    
                except Exception as e:
                    print(f"[OASYFY] Erro ao enviar conversão Facebook: {e}")
                    import traceback
                    traceback.print_exc()
                
                return jsonify({"status": "success", "message": "Payment processed"}), 200
            else:
                print(f"[OASYFY] Pagamento não encontrado para transaction_id: {transaction_id}")
                return jsonify({"status": "warning", "message": "Payment not found"}), 200
        
        elif event == 'TRANSACTION_CREATED':
            print(f"[OASYFY] Transação {transaction_id} criada")
            return jsonify({"status": "success", "message": "Transaction created"}), 200
            
        elif event == 'TRANSACTION_CANCELED':
            print(f"[OASYFY] Transação {transaction_id} cancelada")
            if transaction_id:
                manager.update_payment_status(transaction_id, 'failed')
            return jsonify({"status": "success", "message": "Transaction canceled"}), 200
            
        elif event == 'TRANSACTION_REFUNDED':
            print(f"[OASYFY] Transação {transaction_id} estornada")
            if transaction_id:
                manager.update_payment_status(transaction_id, 'refunded')
            return jsonify({"status": "success", "message": "Transaction refunded"}), 200
        
        else:
            print(f"[OASYFY] Evento não processado: {event} - Status: {status}")
            return jsonify({"status": "success", "message": "Event received"}), 200
            
    except Exception as e:
        print(f"[OASYFY WEBHOOK] Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    
@app.route('/webhook/syncpay', methods=['POST'])
def webhook_syncpay():
    """Webhook para processar notificações da SyncPay"""
    
    try:
        # Pega os dados do webhook
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400
        
        # IMPORTANTE: SyncPay envia o evento no HEADER
        event_type = request.headers.get('event', '')
        
        # CORREÇÃO: Ignora eventos de CASHOUT (saques)
        if 'cashout' in event_type.lower():
            # Cashout = saque/transferência, não é pagamento recebido
            # Silencioso - não precisa logar
            return jsonify({"status": "success", "message": "Cashout event ignored"}), 200
        
        # Pega os dados da transação
        webhook_data = data.get('data', {})
        
        # Tenta pegar o ID de várias formas
        transaction_id = (
            webhook_data.get('id') or 
            webhook_data.get('identifier') or 
            webhook_data.get('idtransaction') or
            webhook_data.get('reference_id')
        )
        
        status = webhook_data.get('status', '').lower()
        
        # Log resumido apenas para CASHIN
        print(f"[SYNCPAY] Evento: {event_type}, Status: {status}, ID: {transaction_id}")
        
        # Processa apenas CASHIN (pagamentos recebidos)
        if event_type == 'cashin.update' and status in ['completed', 'approved', 'paid', 'success']:
            print(f'[SYNCPAY] ✅ Pagamento aprovado: {transaction_id}')
            
            # Busca o pagamento
            payment = manager.get_payment_by_trans_id(transaction_id)
            
            if payment:
                # Atualiza status para pago
                manager.update_payment_status(transaction_id, 'paid')
                
                # Extrai informações
                user_id = payment[2]
                bot_id = payment[4]
                plan_data = json.loads(payment[3])
                
                print(f"[SYNCPAY] User: {user_id}, Bot: {bot_id}, Valor: R$ {plan_data['value']}")
                
                # REMOVIDO: Notificação do usuário via Telegram
                # A notificação já é feita pelo payment_task em bot.py
                
                # UTMIFY
                try:
                    utmify_config = manager.get_utmify_config(bot_id)
                    if utmify_config and utmify_config['enabled']:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        tracking_data = manager.get_utm_tracking(user_id, bot_id) or {}
                        tax_rate = manager.get_bot_tax(bot_id)
                        
                        order_data = {
                            'transaction_id': str(transaction_id),
                            'user_id': user_id,
                            'bot_id': bot_id,
                            'value': plan_data['value'],
                            'plan_name': plan_data['name']
                        }
                        
                        from modules.utmify import utmify_api
                        loop.run_until_complete(utmify_api.send_purchase_completed(
                            api_token=utmify_config['api_token'],
                            order_data=order_data,
                            tracking_data=tracking_data
                        ))
                        
                        print(f"[SYNCPAY] ✅ Conversão enviada para Utmify")
                        
                except Exception as e:
                    print(f"[SYNCPAY] Erro Utmify: {e}")
                
                # FACEBOOK
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    fbclid = manager.get_user_fbclid(user_id, bot_id)
                    
                    import modules.facebook_conversions as fb_conv
                    loop.run_until_complete(fb_conv.send_purchase_event(
                        user_id=user_id,
                        bot_id=bot_id,
                        value=plan_data['value'],
                        plan_name=plan_data['name'],
                        fbclid=fbclid
                    ))
                    
                    print(f"[SYNCPAY] ✅ Conversão enviada para Facebook")
                    
                except Exception as e:
                    print(f"[SYNCPAY] Erro Facebook: {e}")
                
                print("[SYNCPAY] ✅ Pagamento processado com sucesso!")
                return jsonify({"status": "success", "message": "Payment processed"}), 200
                
            else:
                print(f"[SYNCPAY] ⚠️ Pagamento não encontrado: {transaction_id}")
                return jsonify({"status": "warning", "message": "Payment not found"}), 200
        
        elif event_type == 'cashin.create':
            # PIX criado, aguardando pagamento - silencioso
            return jsonify({"status": "success", "message": "Transaction created"}), 200
        
        elif event_type == 'cashin.canceled':
            # PIX cancelado
            if transaction_id:
                manager.update_payment_status(transaction_id, 'failed')
            return jsonify({"status": "success", "message": "Transaction canceled"}), 200
            
        else:
            # Outros eventos ignorados - sem log
            return jsonify({"status": "success", "message": "Event received"}), 200
            
    except Exception as e:
        print(f"[SYNCPAY] ❌ Erro: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['GET'])
def home():
    if session.get("auth", False):
        dashboard_data['botsActive'] = manager.count_bots()
        dashboard_data['usersCount'] = '?'
        dashboard_data['salesCount'] = len(manager.get_all_payments_by_status('finished'))
        return send_file('./templates/terminal.html')
    return redirect(url_for('login'))

@app.route('/visualizar', methods=['GET'])
def view():
    if session.get("auth", False):
        return send_file('./templates/bots.html')
    return redirect(url_for('login'))

@app.route('/delete/<id>', methods=['DELETE'])
async def delete(id):
    if session.get("auth", False):
        # Remove apenas o processo e dados em memória
        if id in processes.keys():
            processes.pop(id)
        if id in bots_data:
            bots_data.pop(id)
        
        # Remove completamente do banco
        manager.delete_bot(id)
        return 'true'
    else:
        return 'Unauthorized', 403

@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        password = request.form['password']
        if password == ADMIN_PASSWORD:
            session['auth'] = True
            return redirect('/')
    return '''
        <form method="post">
            <p><input type="text" name="password" placeholder="Digite a senha"></p>
            <p><input type="submit" value="Entrar"></p>
        </form>
    '''

def start_bot(new_token, bot_id):
    """Inicia um novo bot em um processo separado."""
    bot_id = str(bot_id)
    
    # NOVA VERIFICAÇÃO: Procura por processos com o mesmo token
    global processes, bots_data
    
    # Verifica se já existe um processo com este token
    for pid, process in list(processes.items()):
        if pid in bots_data and bots_data[pid].get('token') == new_token:
            print(f"Token {new_token[:20]}... já está em uso pelo bot {pid}")
            
            # Para o processo antigo
            try:
                if process and process.is_alive():
                    print(f"Parando processo antigo do bot {pid}")
                    process.terminate()
                    time.sleep(0.5)
                    if process.is_alive():
                        process.kill()
                    process.join(timeout=2)
            except Exception as e:
                print(f"Erro ao parar processo antigo: {e}")
            
            # Remove dos dicionários
            processes.pop(pid, None)
            bots_data.pop(pid, None)
    
    # Verifica se o bot_id já tem processo
    if bot_id in processes:
        process = processes[bot_id]
        if process and process.is_alive():
            print(f"Bot {bot_id} já tem processo ativo. Parando...")
            try:
                process.terminate()
                time.sleep(0.5)
                if process.is_alive():
                    process.kill()
                process.join(timeout=2)
            except:
                pass
        processes.pop(bot_id, None)
    
    # Agora inicia o novo processo
    process = Process(target=run_bot_sync, args=(new_token, bot_id))
    process.start()
    tokens.append(new_token)
    
    bot = manager.get_bot_by_id(bot_id)
    bot_details = manager.check_bot_token(new_token)
    bot_obj = {
        'id': bot_id,
        'url':f'https://t.me/{bot_details["result"].get("username", "INDEFINIDO")}' if bot_details else 'Token Inválido',
        'token': new_token,  # IMPORTANTE: Salvar o token aqui
        'owner': bot[2],
        'data': json.loads(bot[4])
    }
    bots_data[bot_id] = bot_obj
    processes[bot_id] = process
    print(f"Bot {bot_id} processo iniciado - PID: {process.pid}")
    return True
def check_and_remove_inactive_bots():
    """Remove bots inativos do sistema"""
    global processes, bots_data
    
    try:
        # Pega bots inativos há mais de 5 minutos (para teste)
        inactive_bots = manager.get_inactive_bots(minutes=21600)
        
        for bot_data in inactive_bots:
            bot_id = str(bot_data[0])
            bot_token = bot_data[1]
            owner_id = bot_data[2]
            
            print(f"Removendo bot inativo {bot_id} do sistema")
            
            # Para o processo se estiver rodando
            if bot_id in processes:
                try:
                    process = processes[bot_id]
                    if process and process.is_alive():
                        process.terminate()
                        time.sleep(0.5)
                        if process.is_alive():
                            process.kill()
                        process.join(timeout=2)
                    processes.pop(bot_id)
                except Exception as e:
                    print(f"Erro ao parar processo: {e}")
            
            # Remove dos dados em memória
            if bot_id in bots_data:
                bots_data.pop(bot_id)
                
    except Exception as e:
        print(f"Erro ao verificar bots inativos: {e}")
        
def inactivity_checker_thread():
    """Thread para verificar bots inativos periodicamente"""
    while True:
        time.sleep(18000)  # Verifica a cada 5 horas
        check_and_remove_inactive_bots()

def contingency_monitor_thread():
    """Thread para monitorar status dos bots de contingência a cada 2 minutos"""
    print("✅ Monitor de contingência iniciado (intervalo: 2 minutos)")
    
    # Aguarda 30 segundos antes da primeira verificação
    time.sleep(30)
    
    while True:
        try:
            print(f"[CONTINGENCY MONITOR] Iniciando verificação às {time.strftime('%H:%M:%S')}")
            response = requests.post(f"http://localhost:{port}/api/contingency/check-status")
            
            if response.status_code == 200:
                data = response.json()
                if data.get('checked', 0) > 0:
                    print(f"[CONTINGENCY MONITOR] Verificados {data['checked']} bots")
                if data.get('notifications', 0) > 0:
                    print(f"[CONTINGENCY MONITOR] {data['notifications']} trocas realizadas")
        except Exception as e:
            print(f"[CONTINGENCY MONITOR] Erro: {e}")
        
        # Aguarda 2 minutos até próxima verificação
        time.sleep(120)  # 2 minutos

async def receive_token_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Verifica se é callback de cancelar
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        if query.data == "registro_cancelar_silencioso":
            # Volta para o menu principal sem mensagem
            return await mostrar_menu_principal(query.message, query.from_user)
    
    # Processa o token enviado
    if update.message and update.message.text:
        new_token = update.message.text.strip()
        admin_id = update.effective_user.id
        
        # Verifica se já existe
        if manager.bot_exists(new_token):
            await update.message.reply_text(
                '⚠️ <b>Token já registrado!</b>\n\n'
                'Este bot já está cadastrado no sistema.',
                parse_mode='HTML'
            )
            return ConversationHandler.END
            
        # Verifica se o token é válido
        telegram_bot = manager.check_bot_token(new_token)
        if telegram_bot and telegram_bot.get('result'):
            bot_info = telegram_bot['result']
            bot_id = bot_info.get('id')
            bot_username = bot_info.get('username', 'sem_username')
            bot_name = bot_info.get('first_name', 'Sem nome')
            
            if bot_id:
                # Cria o bot no banco
                manager.create_bot(str(bot_id), new_token, admin_id)
                
                # Inicia o bot
                start_bot(new_token, bot_id)
                
                # Cria o botão de acessar o bot
                keyboard = [[InlineKeyboardButton("𝗔𝗰𝗲𝘀𝘀𝗮𝗿 𝗕𝗼𝘁", url=f"https://t.me/{bot_username}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f'✅ <b>Bot cadastrado com sucesso!</b> Sua máquina de dinheiro já está online 🥂\n\n'
                    f'📝 Nome: {bot_name}\n'
                    f'👤 Username: @{bot_username}\n'
                    f'📦 ID: {bot_id}',
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    '❌ <b>Erro ao obter ID do bot!</b>\n\n'
                    'Tente novamente mais tarde.',
                    parse_mode='HTML'
                )
        else:
            await update.message.reply_text(
                '❌ <b>Token inválido!</b>\n\n'
                'Verifique se o token está correto e tente novamente.\n\n'
                '💡 <i>Dica: O token deve ter o formato:</i>\n'
                '<code>123456789:ABCdefGHIjklMNOpqrsTUVwxyz</code>',
                parse_mode='HTML'
            )
    
    return ConversationHandler.END

async def start_func(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    # Texto de apresentação
    welcome_text = (
        f"<b>Bem-vindo</b> {user_name} 🥂\n\n"
        f"🥷 Hora de colocar a caixa pra movimentar com o melhor <b>Bot de Pagamento do Telegram!</b>\n\n"
        "⚙️ <b>Sistema completo,</b> desde funcionalidades para uma maior conversão a taxas justas.\n\n"
        "O que você deseja fazer?"
    )
    
    # Pega o username do suporte
    support_username = manager.get_registro_support()
    
    # Botões do menu
    keyboard = [
        [InlineKeyboardButton("📦 𝗖𝗮𝗱𝗮𝘀𝘁𝗿𝗮𝗿 𝗕𝗼𝘁", callback_data="registro_cadastrar")],
        [
            InlineKeyboardButton("👤 𝗠𝗲𝘂𝘀 𝗕𝗼𝘁𝘀", callback_data="registro_ver_bots"),
            InlineKeyboardButton("♻️ 𝗧𝗿𝗼𝗰𝗮𝗿 𝗧𝗼𝗸𝗲𝗻", callback_data="registro_substituir")
        ],
        [InlineKeyboardButton("🔄 𝗖𝗼𝗻𝘁𝗶𝗻𝗴ê𝗻𝗰𝗶𝗮", callback_data="contingencia_menu_inicial")],
        [
            InlineKeyboardButton("💰 𝗧𝗮𝘅𝗮𝘀", callback_data="registro_taxas"),
            InlineKeyboardButton("🙋‍♂ 𝗔𝗷𝘂𝗱𝗮", url=f"https://t.me/{support_username or 'suporte'}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    return REGISTRO_MENU

async def registro_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # IMPORTANTE: Tratar registro_voltar_menu PRIMEIRO
    if query.data == "registro_voltar_menu":
        return await mostrar_menu_principal(query.message, query.from_user)
    
    if query.data == "registro_cadastrar":
        # Inicia processo de cadastro
        keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data="registro_cancelar_silencioso")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🚀 <b>Como cadastrar na NGK Pay?</b> É simples! Basta seguir o tutorial:\n\n"
            "<b>1.</b> Crie um novo Bot no @Botfather\n"
            "<b>2.</b> Copie o Token do Bot\n"
            "<b>3.</b> Cole o Token aqui abaixo",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return REGISTRO_AGUARDANDO_TOKEN
    
    elif query.data == "contingencia_menu_inicial":
        await contingencia_menu(update, context)
        return ConversationHandler.END  # Encerra o handler atual para iniciar o de contingência
        
    elif query.data == "registro_ver_bots":
        # Mostra lista de bots do usuário com opção de gerenciar
        user_id = query.from_user.id
        bots = manager.get_bots_by_owner(str(user_id))
        
        if not bots:
            keyboard = [[InlineKeyboardButton("🏠 Voltar", callback_data="registro_voltar_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ <b>Nenhum bot cadastrado</b>\n\n"
                "Você ainda não possui bots cadastrados no sistema. "
                "Use o botão <b>Cadastrar Bot</b> para adicionar seu primeiro bot na NGK Pay.",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        else:
            bot_list = "🥷 <b>Meus bots cadastrados</b>\n\n"
            for bot in bots:
                bot_id = bot[0]
                bot_token = bot[1]
                
                # Verifica se o bot está ativo
                bot_details = manager.check_bot_token(bot_token)
                if bot_details and bot_details.get('result'):
                    bot_username = bot_details['result'].get('username', 'INDEFINIDO')
                    bot_name = bot_details['result'].get('first_name', 'Sem nome')
                    bot_list += f"📦 {bot_name} - @{bot_username}\n"
                else:
                    bot_list += f"📦 Bot ID: {bot_id} (Token inválido)\n"
            
            bot_list += f"\n📊 <b>Total:</b> {len(bots)} bot(s)"
            
            # Adicionar botão de deletar
            keyboard = [
                [InlineKeyboardButton("🗑 Deletar Bot", callback_data="registro_deletar_bot")],
                [InlineKeyboardButton("🏠 Voltar", callback_data="registro_voltar_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                bot_list, 
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        
        return REGISTRO_MENU
        
    elif query.data == "registro_deletar_bot":
        # Listar bots para deletar
        user_id = query.from_user.id
        bots = manager.get_bots_by_owner(str(user_id))
        
        if not bots:
            keyboard = [[InlineKeyboardButton("🏠 Voltar", callback_data="registro_voltar_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ Você não possui bots para deletar.",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return REGISTRO_MENU
        
        keyboard = []
        for bot in bots:
            bot_id = bot[0]
            bot_token = bot[1]
            
            bot_details = manager.check_bot_token(bot_token)
            if bot_details and bot_details.get('result'):
                bot_username = bot_details['result'].get('username', 'INDEFINIDO')
                bot_name = bot_details['result'].get('first_name', 'Sem nome')
                button_text = f"🗑 {bot_name} (@{bot_username})"
            else:
                button_text = f"🗑 Bot ID: {bot_id}"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"confirmar_deletar_{bot_id}")])
        
        keyboard.append([InlineKeyboardButton("❌ CANCELAR", callback_data="registro_voltar_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🗑 <b>Deletar Bot</b>\n\n"
            "⚠️ <b>ATENÇÃO:</b> Esta ação é PERMANENTE!\n\n"
            "Ao deletar, você perderá:\n"
            "• Todas as configurações\n"
            "• Histórico de vendas\n"
            "• Dados de usuários\n\n"
            "Selecione o bot que deseja deletar:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        return REGISTRO_DELETAR_BOT
        
    elif query.data == "registro_substituir":
        # Busca bots do usuário
        user_id = query.from_user.id
        bots = manager.get_bots_by_owner(str(user_id))
        
        if not bots:
            keyboard = [[InlineKeyboardButton("🏠 Voltar", callback_data="registro_voltar_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ <b>Nenhum bot para substituir</b>\n\n"
                "Você precisa ter pelo menos um bot cadastrado para usar esta função.",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return REGISTRO_MENU
        
        # Monta lista de bots para escolher
        keyboard = []
        for bot in bots:
            bot_id = bot[0]
            bot_token = bot[1]
            
            # Pega info do bot
            bot_details = manager.check_bot_token(bot_token)
            if bot_details and bot_details.get('result'):
                bot_username = bot_details['result'].get('username', 'INDEFINIDO')
                bot_name = bot_details['result'].get('first_name', 'Sem nome')
                button_text = f"{bot_name} (@{bot_username})"
            else:
                button_text = f"Bot ID: {bot_id} (Offline)"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"substituir_bot_{bot_id}")])
        
        keyboard.append([InlineKeyboardButton("❌ CANCELAR", callback_data="registro_voltar_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "♻️ <b>Substituir Bot</b>\n\n"
            "⚠️ O bot selecionado será desativado e suas configurações "
            "serão transferidas para o novo bot.\n\n"
            "<b>Qual bot deseja substituir?</b>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        return REGISTRO_SELECIONAR_BOT
        
    elif query.data == "registro_taxas":
        user_id = query.from_user.id
        tax_config = manager.get_owner_tax_type(str(user_id))
        
        if tax_config['type'] == 'fixed':
            taxa_atual = f"<b>R$ {tax_config['fixed_value']:.2f}</b> por venda (Taxa Fixa)"
            exemplo = f"Em uma venda de R$ 100,00 → Taxa de R$ {tax_config['fixed_value']:.2f}"
        else:
            taxa_atual = f"<b>{tax_config['percentage_value']}%</b> do valor da venda (Taxa Percentual)"
            exemplo = f"Em uma venda de R$ 100,00 → Taxa de R$ {tax_config['percentage_value']:.2f}"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Alterar Taxa", callback_data="registro_alterar_taxa")],
            [InlineKeyboardButton("🏠 Voltar", callback_data="registro_voltar_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"💰 <b>Configuração de Taxa</b>\n\n"
            f"📍 <b>Taxa Atual:</b> {taxa_atual}\n\n"
            f"📊 <b>Como funciona:</b>\n"
            f"• {exemplo}\n"
            f"• Sem mensalidades ou taxas ocultas\n"
            f"• Processamento instantâneo\n\n"
            f"💡 <b>Escolha o que faz mais sentido para você:</b>\n"
            f"• <b>Taxa Fixa:</b> Ideal para produtos de maior valor\n"
            f"• <b>Taxa Percentual:</b> Ideal para produtos de menor valor\n\n"
            f"✅ <b>Vantagens NGK Pay:</b>\n"
            f"• Suporte 24/7\n"
            f"• Pagamentos via PIX instantâneo\n"
            f"• Sistema 100% automatizado\n"
            f"• Sem limites de vendas",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return REGISTRO_MENU
        
    elif query.data == "registro_alterar_taxa":
        keyboard = [
            [InlineKeyboardButton("💵 Taxa Fixa (R$ 0,75)", callback_data="registro_taxa_fixa")],
            [InlineKeyboardButton("📊 Taxa Percentual (3,5%)", callback_data="registro_taxa_percentual")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="registro_taxas")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🔄 <b>Alterar Tipo de Taxa</b>\n\n"
            "Escolha o modelo de taxa que prefere:\n\n"
            "💵 <b>Taxa Fixa - R$ 0,75</b>\n"
            "• Você paga R$ 0,75 por venda\n"
            "• Independente do valor do produto\n"
            "• Ideal para produtos acima de R$ 25\n\n"
            "📊 <b>Taxa Percentual - 3,5%</b>\n"
            "• Você paga 3,5% do valor da venda\n"
            "• Proporcional ao valor do produto\n"
            "• Ideal para produtos abaixo de R$ 25\n\n"
            "⚠️ <b>Importante:</b> A mudança afetará todos os seus bots e vale apenas para vendas futuras.",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return REGISTRO_MENU
        
    elif query.data == "registro_taxa_fixa":
        user_id = query.from_user.id
        manager.set_owner_tax_type(str(user_id), 'fixed')
        
        keyboard = [[InlineKeyboardButton("✅ Entendido", callback_data="registro_taxas")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✅ <b>Taxa Alterada com Sucesso!</b>\n\n"
            "Sua taxa foi alterada para:\n"
            "💵 <b>Taxa Fixa - R$ 0,75 por venda</b>\n\n"
            "Esta configuração já está valendo para:\n"
            "• Todas as novas vendas\n"
            "• Todos os seus bots\n\n"
            "💡 Você pode alterar novamente quando quiser.",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return REGISTRO_MENU
        
    elif query.data == "registro_taxa_percentual":
        user_id = query.from_user.id
        manager.set_owner_tax_type(str(user_id), 'percentage')
        
        keyboard = [[InlineKeyboardButton("✅ Entendido", callback_data="registro_taxas")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✅ <b>Taxa Alterada com Sucesso!</b>\n\n"
            "Sua taxa foi alterada para:\n"
            "📊 <b>Taxa Percentual - 3,5% do valor</b>\n\n"
            "Esta configuração já está valendo para:\n"
            "• Todas as novas vendas\n"
            "• Todos os seus bots\n\n"
            "💡 Você pode alterar novamente quando quiser.",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return REGISTRO_MENU

async def registro_processar_deletar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "registro_voltar_menu":
        return await mostrar_menu_principal(query.message, query.from_user)
    
    if query.data.startswith("confirmar_deletar_"):
        bot_id = query.data.replace("confirmar_deletar_", "")
        user_id = query.from_user.id
        
        # Busca informações do bot ANTES de verificar contingência
        bot = manager.get_bot_by_id(bot_id)
        if bot:
            bot_details = manager.check_bot_token(bot[1])
            bot_username = bot_details['result'].get('username', 'Bot') if bot_details else 'Bot'
        else:
            bot_username = 'Bot'
        
        # NOVO: Verificar se bot está em grupos de contingência
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        # Busca grupos que contêm este bot
        cursor.execute("""
            SELECT cg.id, cg.name, COUNT(cb2.bot_id) as total_bots
            FROM CONTINGENCY_GROUPS cg
            JOIN CONTINGENCY_BOTS cb ON cg.id = cb.group_id
            LEFT JOIN CONTINGENCY_BOTS cb2 ON cg.id = cb2.group_id
            WHERE cb.bot_id = ? AND cg.is_active = 1 AND cg.owner_id = ?
            GROUP BY cg.id
        """, (bot_id, str(user_id)))
        
        groups_affected = cursor.fetchall()
        conn.close()
        
        if groups_affected:
            # Bot está em grupos de contingência
            groups_to_delete = []
            groups_safe = []
            
            for group_id, group_name, total_bots in groups_affected:
                remaining_bots = total_bots - 1
                if remaining_bots < 2:
                    groups_to_delete.append(group_name)
                else:
                    groups_safe.append((group_name, remaining_bots))
            
            # Monta mensagem de aviso
            warning_text = f"⚠️ <b>ATENÇÃO - Bot em Contingência!</b>\n\n"
            warning_text += f"O bot @{bot_username} está em {len(groups_affected)} grupo(s) de contingência.\n\n"
            
            if groups_to_delete:
                warning_text += "🚨 <b>GRUPOS QUE SERÃO DELETADOS:</b>\n"
                for group_name in groups_to_delete:
                    warning_text += f"❌ {group_name} (ficará com menos de 2 bots)\n"
                warning_text += "\n⚠️ <b>Os links desses grupos serão perdidos!</b>\n\n"
                warning_text += "💡 <b>DICA:</b> Antes de deletar este bot, adicione\n"
                warning_text += "outro bot nesses grupos para mantê-los ativos.\n\n"
            
            if groups_safe:
                warning_text += "✅ <b>Grupos que continuarão funcionando:</b>\n"
                for group_name, remaining in groups_safe:
                    warning_text += f"• {group_name} (ficará com {remaining} bots)\n"
                warning_text += "\n"
            
            warning_text += "<b>Tem certeza que deseja continuar?</b>"
            
            keyboard = [
                [
                    InlineKeyboardButton("🗑 SIM, DELETAR TUDO", callback_data=f"deletar_final_{bot_id}"),
                    InlineKeyboardButton("❌ CANCELAR", callback_data="registro_voltar_menu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                warning_text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            
        else:
            # Bot não está em nenhum grupo, proceder normal
            keyboard = [
                [
                    InlineKeyboardButton("✅ SIM, DELETAR", callback_data=f"deletar_final_{bot_id}"),
                    InlineKeyboardButton("❌ CANCELAR", callback_data="registro_voltar_menu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🚨 <b>CONFIRMAÇÃO FINAL</b> 🚨\n\n"
                f"Você está prestes a deletar @{bot_username}\n\n"
                f"Esta ação é <b>IRREVERSÍVEL</b>!\n\n"
                f"Tem certeza absoluta?",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        
        return REGISTRO_DELETAR_BOT
    
    elif query.data.startswith("deletar_final_"):
        bot_id = query.data.replace("deletar_final_", "")
        user_id = query.from_user.id
        
        # Processar deleção (já inclui remoção dos grupos)
        result = manager.delete_bot_by_owner(bot_id, str(user_id))
        
        if result['success']:
            await query.edit_message_text(
                "✅ <b>Bot deletado com sucesso!</b>\n\n"
                "O bot foi completamente removido do sistema.\n\n"
                "Você será redirecionado ao menu...",
                parse_mode='HTML'
            )
            
            import asyncio
            await asyncio.sleep(2)
            return await mostrar_menu_principal(query.message, query.from_user)
        else:
            await query.edit_message_text(
                f"❌ <b>Erro ao deletar bot</b>\n\n"
                f"{result['message']}",
                parse_mode='HTML'
            )
            
            import asyncio
            await asyncio.sleep(2)
            return await mostrar_menu_principal(query.message, query.from_user)
    
    return REGISTRO_DELETAR_BOT

async def mostrar_menu_principal(message, user):
    """Função auxiliar para mostrar o menu principal"""
    user_name = user.first_name
    
    welcome_text = (
        f"<b>Bem-vindo</b> {user_name} 🥂\n\n"
        f"🥷 Hora de colocar a caixa pra movimentar com o melhor <b>Bot de Pagamento do Telegram!</b>\n\n"
        "⚙️ <b>Sistema completo,</b> desde funcionalidades para uma maior conversão a taxas justas.\n\n"
        "O que você deseja fazer?"
    )
    
    support_username = manager.get_registro_support()
    
    keyboard = [
        [InlineKeyboardButton("📦 𝗖𝗮𝗱𝗮𝘀𝘁𝗿𝗮𝗿 𝗕𝗼𝘁", callback_data="registro_cadastrar")],
        [
            InlineKeyboardButton("👤 𝗠𝗲𝘂𝘀 𝗕𝗼𝘁𝘀", callback_data="registro_ver_bots"),
            InlineKeyboardButton("♻️ 𝗧𝗿𝗼𝗰𝗮𝗿 𝗧𝗼𝗸𝗲𝗻", callback_data="registro_substituir")
        ],
        [InlineKeyboardButton("🔄 𝗖𝗼𝗻𝘁𝗶𝗻𝗴ê𝗻𝗰𝗶𝗮", callback_data="contingencia_menu_inicial")],  # ADICIONAR ESTA LINHA
        [
            InlineKeyboardButton("💰 𝗧𝗮𝘅𝗮𝘀", callback_data="registro_taxas"),
            InlineKeyboardButton("🙋‍♂ 𝗔𝗷𝘂𝗱𝗮", url=f"https://t.me/{support_username or 'suporte'}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.edit_text(
        welcome_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
    return REGISTRO_MENU

async def registro_selecionar_bot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "registro_voltar_menu":
        return await mostrar_menu_principal(query.message, query.from_user)
    
    if query.data.startswith("substituir_bot_"):
        # Extrai o ID do bot selecionado
        bot_id = query.data.replace("substituir_bot_", "")
        
        # Salva o bot selecionado no contexto
        context.user_data['bot_para_substituir'] = bot_id
        
        # Pede o novo token
        keyboard = [[InlineKeyboardButton("❌ CANCELAR", callback_data="registro_cancelar_substituir")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📝 <b>Novo Token</b>\n\n"
            "Agora envie o token do NOVO bot que substituirá o anterior.\n\n"
            "💡 <i>Crie um novo bot no @BotFather e envie o token aqui.</i>\n\n"
            "⚠️ <b>Atenção:</b> Todas as configurações serão copiadas automaticamente.",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        return REGISTRO_AGUARDANDO_NOVO_TOKEN
    
async def registro_processar_novo_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
   # Verifica se é cancelamento
   if update.callback_query:
       query = update.callback_query
       await query.answer()
       
       if query.data == "registro_cancelar_substituir":
           await query.edit_message_text(
               "❌ <b>Substituição cancelada!</b>",
               parse_mode='HTML'
           )
           return ConversationHandler.END
   
   # Processa o novo token
   if update.message and update.message.text:
       new_token = update.message.text.strip()
       bot_id_antigo = context.user_data.get('bot_para_substituir')
       user_id = update.effective_user.id
       
       # ✅ CARREGA O CONFIG.JSON
       with open('./config.json', 'r') as f:
           config = json.loads(f.read())
       
       # Verifica se o token já existe
       if manager.bot_exists(new_token):
           await update.message.reply_text(
               '⚠️ <b>Este token já está cadastrado!</b>\n\n'
               'Use um token de um bot novo.',
               parse_mode='HTML'
           )
           return REGISTRO_AGUARDANDO_NOVO_TOKEN
       
       # Valida o novo token
       telegram_bot = manager.check_bot_token(new_token)
       if not telegram_bot or not telegram_bot.get('result'):
           await update.message.reply_text(
               '❌ <b>Token inválido!</b>\n\n'
               'Verifique se o token está correto.',
               parse_mode='HTML'
           )
           return REGISTRO_AGUARDANDO_NOVO_TOKEN
       
       # Pega informações do novo bot
       new_bot_info = telegram_bot['result']
       new_bot_id = str(new_bot_info.get('id'))
       new_bot_username = new_bot_info.get('username', 'sem_username')
       new_bot_name = new_bot_info.get('first_name', 'Sem nome')
       
       # Mensagem de processamento
       processing_msg = await update.message.reply_text(
           "⏳ <b>Substituindo bot...</b>\n\n"
           "Por favor, aguarde enquanto transferimos as configurações.",
           parse_mode='HTML'
       )
       
       try:
           # 1. Para o bot antigo se estiver rodando
           if bot_id_antigo in processes:
               try:
                   process = processes[bot_id_antigo]
                   if process:
                       process.terminate()
                       time.sleep(0.5)
                       if process.is_alive():
                           process.kill()
                       process.join(timeout=2)
                   processes.pop(bot_id_antigo)
               except:
                   pass
           
           # 2. Remove dos dados em memória
           if bot_id_antigo in bots_data:
               bots_data.pop(bot_id_antigo)
           
           # 3. Copia APENAS configurações SEM MÍDIA
           bot_antigo = manager.get_bot_by_id(bot_id_antigo)
           if bot_antigo:
               # CONFIG - copia apenas textos e botão (sem mídias)
               config_data = json.loads(bot_antigo[3])
               config_limpa = {
                    'texto1': config_data.get('texto1', False),  # ✅ AGORA COPIA O TEXTO1!
                    'texto2': config_data.get('texto2', "Configure o bot usando /inicio\n\nUtilize /comandos para verificar os comandos existentes"),
                    'button': config_data.get('button', 'CLIQUE AQUI PARA VER OFERTAS'),
                    'redirect_button': config_data.get('redirect_button', None)
               }
               
               # ADMIN - OK, sem mídia
               admin_data = json.loads(bot_antigo[4])
               
               # PLANS - OK, sem mídia
               plans_data = json.loads(bot_antigo[5])
               
               # GATEWAY - OK, sem mídia
               gateway_data = json.loads(bot_antigo[6])
               
               # GROUP - OK, sem mídia
               group_data = bot_antigo[9]
               
               # Cria o novo bot com configurações básicas
               manager.create_bot(
                   id=new_bot_id,
                   token=new_token,
                   owner=str(user_id),
                   config=config_limpa,
                   admin=admin_data,
                   plans=plans_data,
                   gateway=gateway_data,
                   users=[],
                   upsell={},      # Vazio - tem mídia
                   group=group_data,
                   expiration={}   # Vazio - tem mídia
               )
               
               # 4. COPIA APENAS CONFIGURAÇÕES SEM MÍDIA
               
               # Facebook Pixel
               facebook_config = manager.get_facebook_config(bot_id_antigo)
               if facebook_config:
                   manager.save_facebook_config(new_bot_id, facebook_config)
                   print(f"✅ Facebook Pixel copiado")
               
               # Utmify
               utmify_config = manager.get_utmify_config(bot_id_antigo)
               if utmify_config:
                   manager.save_utmify_config(new_bot_id, utmify_config['api_token'])
                   print(f"✅ Utmify copiado")
               
               # Taxa personalizada
               tax_rate = manager.get_bot_tax(bot_id_antigo)
               if tax_rate != float(config.get('tax', 1)):
                   manager.set_bot_tax(new_bot_id, tax_rate)
                   print(f"✅ Taxa personalizada copiada: {tax_rate}%")
               
               # 5. Deleta o bot antigo
               manager.delete_bot(bot_id_antigo)
               
               # 6. Inicia o novo bot
               start_bot(new_token, new_bot_id)
               
               # Monta lista do que foi copiado
               configs_copiadas = []
               
               # Verifica o que foi copiado
               if admin_data: 
                   configs_copiadas.append("👤 𝗔𝗱𝗺𝗶𝗻𝗶𝘀𝘁𝗿𝗮𝗱𝗼𝗿𝗲𝘀")
               if plans_data: 
                   configs_copiadas.append("💰 𝗣𝗹𝗮𝗻𝗼𝘀 𝗱𝗲 𝗔𝘀𝘀𝗶𝗻𝗮𝘁𝘂𝗿𝗮")
               if gateway_data.get('type'):
                   gateway_name = {
                       'pp': 'PushinPay',
                       'MP': 'Mercado Pago',
                       'oasyfy': 'Oasyfy',
                       'syncpay': 'SyncPay'
                   }.get(gateway_data.get('type'), 'Gateway')
                   configs_copiadas.append(f"🔐 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ({gateway_name})")
               if group_data: 
                   configs_copiadas.append("⭐ 𝗚𝗿𝘂𝗽𝗼 𝗩𝗜𝗣")
               if config_limpa.get('redirect_button'): 
                   configs_copiadas.append("🔗 𝗕𝗼𝘁𝗮̃𝗼 𝗱𝗲 𝗥𝗲𝗱𝗶𝗿𝗲𝗰𝗶𝗼𝗻𝗮𝗺𝗲𝗻𝘁𝗼")
               if facebook_config: 
                   configs_copiadas.append("📊 𝗙𝗮𝗰𝗲𝗯𝗼𝗼𝗸 𝗣𝗶𝘅𝗲𝗹")
               if utmify_config: 
                   configs_copiadas.append("📈 𝗨𝘁𝗺𝗶𝗳𝘆")
               if tax_rate != float(config.get('tax', 1)): 
                   configs_copiadas.append(f"💸 𝗧𝗮𝘅𝗮 𝗣𝗲𝗿𝘀𝗼𝗻𝗮𝗹𝗶𝘇𝗮𝗱𝗮 ({tax_rate}%)")
               
               # Mensagem de sucesso super estilizada
               mensagem = (
                   f"✅ <b>𝗕𝗼𝘁 𝘀𝘂𝗯𝘀𝘁𝗶𝘁𝘂𝗶́𝗱𝗼 𝗰𝗼𝗺 𝘀𝘂𝗰𝗲𝘀𝘀𝗼!</b> 🎉\n"
                   f"━━━━━━━━━━━━━━━━━━━\n\n"
                   f"🤖 <b>𝗡𝗼𝘃𝗼 𝗕𝗼𝘁</b>\n"
                   f"├ 📝 <b>Nome:</b> {new_bot_name}\n"
                   f"├ 🆔 <b>Username:</b> @{new_bot_username}\n"
                   f"└ 🔗 <b>Link:</b> t.me/{new_bot_username}\n\n"
               )
               
               if configs_copiadas:
                   mensagem += (
                       "✨ <b>𝗖𝗼𝗻𝗳𝗶𝗴𝘂𝗿𝗮𝗰̧𝗼̃𝗲𝘀 𝗧𝗿𝗮𝗻𝘀𝗳𝗲𝗿𝗶𝗱𝗮𝘀</b>\n"
                       "┌─────────────────────\n"
                   )
                   for i, config in enumerate(configs_copiadas):
                       if i == len(configs_copiadas) - 1:
                           mensagem += f"└ {config}\n"
                       else:
                           mensagem += f"├ {config}\n"
                   mensagem += "\n"
               
               mensagem += (
                   "⚠️ <b>𝗔𝗰̧𝗼̃𝗲𝘀 𝗡𝗲𝗰𝗲𝘀𝘀𝗮́𝗿𝗶𝗮𝘀</b>\n"
                   "┌─────────────────────\n"
               )
               
               if group_data:
                   mensagem += f"├ 1️⃣ Adicione @{new_bot_username} como\n│   administrador no grupo VIP\n"
               else:
                   mensagem += "├ 1️⃣ Configure o grupo VIP com /vip\n"
               
               mensagem += (
                   "│\n"
                   "├ 2️⃣ <b>𝗥𝗲𝗰𝗼𝗻𝗳𝗶𝗴𝘂𝗿𝗲 𝗮𝘀 𝗳𝘂𝗻𝗰̧𝗼̃𝗲𝘀:</b>\n"
                   "│   <i>(Funções com mídia não podem ser copiadas)</i>\n"
                   "│\n"
                   "├ 🎬 <code>/inicio</code> - Mensagem inicial\n"
                   "├ 📈 <code>/upsell</code> - Oferta pós-compra\n"
                   "├ ✅ <code>/downsell</code> - Última chance\n"
                   "├ 💸 <code>/orderbump</code> - Ofertas adicionais\n"
                   "├ 🔄 <code>/recuperacao</code> - Sistema de recuperação\n"
                   "├ 🚀 <code>/disparo</code> - Disparos programados\n"
                   "└ 👋 <code>/adeus</code> - Mensagem de expiração\n\n"
                   "━━━━━━━━━━━━━━━━━━━\n"
                   "💡 <b>𝗗𝗶𝗰𝗮:</b> <i>As configurações essenciais já "
                   "estão prontas! Configure as funções com mídia "
                   "quando quiser, sem pressa.</i>\n\n"
                   "🟢 <b>𝗦𝘁𝗮𝘁𝘂𝘀:</b> Bot online e operacional!"
               )
               
               await processing_msg.edit_text(mensagem, parse_mode='HTML')
               
           else:
               await processing_msg.edit_text(
                   "❌ <b>Erro ao encontrar bot antigo!</b>",
                   parse_mode='HTML'
               )
               
       except Exception as e:
           import traceback
           print(f"Erro detalhado: {traceback.format_exc()}")
           await processing_msg.edit_text(
               f"❌ <b>Erro ao substituir bot!</b>\n\n"
               f"Detalhes: {str(e)}",
               parse_mode='HTML'
           )
   
   return ConversationHandler.END

# Estados para contingência
CONTINGENCIA_MENU, CONTINGENCIA_CRIAR_NOME, CONTINGENCIA_SELECIONAR_BOTS, CONTINGENCIA_GERENCIAR, CONTINGENCIA_DELETAR, CONTINGENCIA_CONFIGURAR_EMERGENCIA, CONTINGENCIA_TUTORIAL = range(5, 12)


async def contingencia_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu principal de contingência"""
    user_id = update.effective_user.id
    
    # Busca grupos do usuário
    groups = manager.get_user_contingency_groups(str(user_id))
    
    keyboard = []
    
    # Botão para criar novo grupo
    keyboard.append([InlineKeyboardButton("➕ Criar Novo Grupo", callback_data="contingencia_criar")])
    
    # Lista grupos existentes
    if groups:
        keyboard.append([InlineKeyboardButton("📊 Meus Grupos", callback_data="contingencia_listar")])
    
    keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="registro_voltar_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "🔄 <b>SISTEMA DE CONTINGÊNCIA</b>\n\n"
        "Este sistema permite criar grupos de bots para failover automático.\n\n"
        "✅ <b>Vantagens:</b>\n"
        "• Link único que nunca muda\n"
        "• Troca automática quando bot cai\n"
        "• Sem perda de tráfego pago\n"
        "• Notificações em tempo real\n\n"
        f"📊 <b>Seus grupos:</b> {len(groups)}"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)
    
    return CONTINGENCIA_MENU

async def contingencia_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
   """Processa callbacks do menu contingência"""
   query = update.callback_query
   await query.answer()
   
   if query.data == "contingencia_criar":
       # Verifica se tem bots suficientes
       user_id = query.from_user.id
       bots = manager.get_bots_by_owner(str(user_id))
       
       if len(bots) < 2:
           await query.edit_message_text(
               "❌ <b>Bots insuficientes!</b>\n\n"
               "Você precisa ter pelo menos 2 bots cadastrados para criar um grupo de contingência.",
               parse_mode='HTML'
           )
           return ConversationHandler.END
       
       # Mensagem simples e profissional
       keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data="registro_voltar_menu")]]
       reply_markup = InlineKeyboardMarkup(keyboard)
       
       await query.edit_message_text(
           "📝 <b>CRIAR GRUPO DE CONTINGÊNCIA</b>\n\n"
           "Digite um nome para identificar este grupo:\n\n"
           "<i>(Entre 3 e 50 caracteres)</i>",
           parse_mode='HTML',
           reply_markup=reply_markup
       )
       return CONTINGENCIA_CRIAR_NOME
   
   elif query.data == "contingencia_listar":
       user_id = query.from_user.id
       groups = manager.get_user_contingency_groups(str(user_id))
       
       if not groups:
           keyboard = [[InlineKeyboardButton("🔙 Voltar", callback_data="contingencia_menu_inicial")]]
           reply_markup = InlineKeyboardMarkup(keyboard)
           
           await query.edit_message_text(
               "❌ Você não possui grupos de contingência.",
               parse_mode='HTML',
               reply_markup=reply_markup
           )
           return CONTINGENCIA_MENU
       
       keyboard = []
       for group in groups:
           status = f"{group['bots_online']}/{group['total_bots']} online"
           button_text = f"📊 {group['name']} ({status})"
           keyboard.append([InlineKeyboardButton(button_text, callback_data=f"contingencia_ver_{group['id']}")])
       
       keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="contingencia_menu_inicial")])
       reply_markup = InlineKeyboardMarkup(keyboard)
       
       await query.edit_message_text(
           "📊 <b>Seus Grupos de Contingência</b>\n\n"
           "Selecione um grupo para ver detalhes:",
           parse_mode='HTML',
           reply_markup=reply_markup
       )
       return CONTINGENCIA_GERENCIAR
   
   elif query.data == "contingencia_menu_inicial":
       # Volta para o menu de contingência
       await contingencia_menu(update, context)
       return CONTINGENCIA_MENU
   
   elif query.data == "registro_voltar_menu":
       await mostrar_menu_principal(query.message, query.from_user)
       return REGISTRO_MENU
   
   return CONTINGENCIA_MENU

async def contingencia_criar_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o nome do grupo"""
    if update.message:
        nome = update.message.text.strip()
        
        if len(nome) < 3 or len(nome) > 50:
            await update.message.reply_text(
                "❌ Nome deve ter entre 3 e 50 caracteres. Tente novamente:",
                parse_mode='HTML'
            )
            return CONTINGENCIA_CRIAR_NOME
        
        # Salva o nome e INICIALIZA a lista vazia
        context.user_data['contingencia_nome'] = nome
        context.user_data['contingencia_bots_selecionados'] = []
        
        # Busca bots do usuário
        user_id = update.effective_user.id
        all_bots = manager.get_bots_by_owner(str(user_id))
        
        # Busca bots já em uso em outros grupos
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT cb.bot_id 
            FROM CONTINGENCY_BOTS cb
            JOIN CONTINGENCY_GROUPS cg ON cb.group_id = cg.id
            WHERE cg.owner_id = ? AND cg.is_active = 1
        """, (str(user_id),))
        
        bots_em_uso = [str(row[0]) for row in cursor.fetchall()]
        conn.close()
        
        # Filtra apenas bots disponíveis
        bots_disponiveis = [bot for bot in all_bots if str(bot[0]) not in bots_em_uso]
        
        if len(bots_disponiveis) < 2:
            await update.message.reply_text(
                "❌ <b>Bots insuficientes!</b>\n\n"
                f"Você tem {len(all_bots)} bot(s) cadastrado(s), mas {len(bots_em_uso)} já está(ão) em uso em outros grupos.\n\n"
                f"📊 <b>Disponíveis:</b> {len(bots_disponiveis)}\n"
                f"📊 <b>Mínimo necessário:</b> 2\n\n"
                "💡 <b>Opções:</b>\n"
                "• Cadastre mais bots\n"
                "• Remova bots de outros grupos\n"
                "• Delete grupos que não usa mais",
                parse_mode='HTML'
            )
            return ConversationHandler.END
        
        keyboard = []
        for bot in bots_disponiveis:
            bot_id = str(bot[0])
            bot_token = bot[1]
            
            bot_details = manager.check_bot_token(bot_token)
            if bot_details and bot_details.get('result'):
                bot_username = bot_details['result'].get('username', 'INDEFINIDO')
                bot_name = bot_details['result'].get('first_name', 'Sem nome')
                
                # Todos começam desmarcados
                prefix = "⬜"
                
                button_text = f"{prefix} {bot_name} (@{bot_username})"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"contbot_{bot_id}")])
        
        keyboard.append([InlineKeyboardButton("✔️ Confirmar Seleção", callback_data="contingencia_confirmar")])
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="registro_voltar_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📋 <b>Grupo:</b> {nome}\n"
            f"🤖 <b>Bots disponíveis:</b> {len(bots_disponiveis)}\n\n"
            "Selecione os bots para este grupo (mínimo 2, máximo 20):\n\n"
            "💡 <i>Nota: Bots já em uso em outros grupos não aparecem aqui</i>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        return CONTINGENCIA_SELECIONAR_BOTS

async def contingencia_selecionar_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa seleção de bots"""
    query = update.callback_query
    
    # Inicializa contexto se não existir
    if 'contingencia_bots_selecionados' not in context.user_data:
        context.user_data['contingencia_bots_selecionados'] = []
    
    if 'contingencia_nome' not in context.user_data:
        await query.answer("Sessão expirada. Voltando ao menu.", show_alert=True)
        return await contingencia_menu(update, context)
    
    await query.answer()
    
    if query.data.startswith("contbot_"):
        bot_id = query.data.replace("contbot_", "")
        
        # Toggle seleção do bot
        if bot_id in context.user_data['contingencia_bots_selecionados']:
            context.user_data['contingencia_bots_selecionados'].remove(bot_id)
        else:
            if len(context.user_data['contingencia_bots_selecionados']) >= 20:
                await query.answer("Máximo de 20 bots por grupo!", show_alert=True)
                return CONTINGENCIA_SELECIONAR_BOTS
            context.user_data['contingencia_bots_selecionados'].append(bot_id)
        
        # IMPORTANTE: Refaz a mesma filtragem da função anterior
        user_id = query.from_user.id
        all_bots = manager.get_bots_by_owner(str(user_id))
        
        # Busca bots já em uso em outros grupos
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT cb.bot_id 
            FROM CONTINGENCY_BOTS cb
            JOIN CONTINGENCY_GROUPS cg ON cb.group_id = cg.id
            WHERE cg.owner_id = ? AND cg.is_active = 1
        """, (str(user_id),))
        
        bots_em_uso = [str(row[0]) for row in cursor.fetchall()]
        conn.close()
        
        # Lista para armazenar apenas bots válidos (online e não em uso)
        bots_disponiveis = []
        
        for bot in all_bots:
            bot_id_check = str(bot[0])
            bot_token = bot[1]
            
            # Pula se bot já está em outro grupo
            if bot_id_check in bots_em_uso:
                continue
            
            # Verifica se o bot está online
            try:
                bot_details = manager.check_bot_token(bot_token)
                if bot_details and bot_details.get('result'):
                    bot_username = bot_details['result'].get('username', None)
                    bot_name = bot_details['result'].get('first_name', 'Sem nome')
                    
                    # Só adiciona na lista se tem username (bot válido)
                    if bot_username:
                        bots_disponiveis.append({
                            'id': bot_id_check,
                            'username': bot_username,
                            'name': bot_name
                        })
                # Se não tem result, o bot está banido/inválido - não adiciona
            except:
                # Bot com problema - não adiciona na lista
                pass
        
        keyboard = []
        for bot_info in bots_disponiveis:
            bot_id_item = bot_info['id']
            
            # Verifica se está selecionado
            is_selected = bot_id_item in context.user_data['contingencia_bots_selecionados']
            prefix = "✅" if is_selected else "⬜"
            
            button_text = f"{prefix} {bot_info['name']} (@{bot_info['username']})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"contbot_{bot_id_item}")])
        
        keyboard.append([InlineKeyboardButton("✔️ Confirmar Seleção", callback_data="contingencia_confirmar")])
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="registro_voltar_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        count = len(context.user_data['contingencia_bots_selecionados'])
        status_msg = "✅ Pronto para criar!" if count >= 2 else f"⚠️ Selecione pelo menos {2 - count} bot(s) mais"
        
        await query.edit_message_text(
            f"📋 <b>Grupo:</b> {context.user_data['contingencia_nome']}\n"
            f"🤖 <b>Bots selecionados:</b> {count}/{len(bots_disponiveis)} disponíveis\n"
            f"📊 <b>Status:</b> {status_msg}\n\n"
            "Selecione os bots para este grupo (mínimo 2, máximo 20):",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        return CONTINGENCIA_SELECIONAR_BOTS
    
    elif query.data == "contingencia_confirmar":
        # Verifica se tem pelo menos 2 bots selecionados
        if len(context.user_data.get('contingencia_bots_selecionados', [])) < 2:
            await query.answer("Selecione pelo menos 2 bots!", show_alert=True)
            return CONTINGENCIA_SELECIONAR_BOTS
        
        # Mostra mensagem de processamento
        await query.edit_message_text(
            "⏳ <b>Criando grupo de contingência...</b>\n\n"
            "Por favor, aguarde...",
            parse_mode='HTML'
        )
        
        # Cria o grupo
        user_id = query.from_user.id
        result = manager.create_contingency_group(
            str(user_id),
            context.user_data['contingencia_nome'],
            context.user_data['contingencia_bots_selecionados']
        )
        
        if result['success']:
            # Pega o domínio configurado
            with open('./config.json', 'r') as f:
                config = json.loads(f.read())
            CONTINGENCY_DOMAIN = config.get('url', 'localhost').replace('https://', '').replace('http://', '').rstrip('/')
            
            link = f"https://{CONTINGENCY_DOMAIN}/r/{result['unique_code']}"
            
            # BUG 2 CORRIGIDO: Botão Menu Principal agora funciona
            keyboard = [[InlineKeyboardButton("🏠 Menu Principal", callback_data="registro_voltar_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ <b>Grupo criado com sucesso!</b>\n\n"
                f"📋 <b>Nome:</b> {context.user_data['contingencia_nome']}\n"
                f"🤖 <b>Bots:</b> {len(context.user_data['contingencia_bots_selecionados'])}\n"
                f"🔗 <b>Link único:</b>\n<code>{link}</code>\n\n"
                f"💡 <b>Como funciona:</b>\n"
                f"• Use este link em suas campanhas\n"
                f"• Se um bot cair, o próximo assume automaticamente\n"
                f"• O link nunca muda, sempre funcionará\n"
                f"• Você receberá notificações de mudanças\n\n"
                f"✨ <b>Dica:</b> Adicione este link no seu Facebook Ads, Google Ads ou qualquer campanha de tráfego pago!",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        else:
            keyboard = [[InlineKeyboardButton("🔄 Tentar Novamente", callback_data="contingencia_menu_inicial")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"❌ <b>Erro ao criar grupo!</b>\n\n"
                f"Detalhes: {result.get('error', 'Erro desconhecido')}\n\n"
                f"Por favor, tente novamente.",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        
        # Limpa contexto após criar
        context.user_data.pop('contingencia_nome', None)
        context.user_data.pop('contingencia_bots_selecionados', None)
        
        # CORREÇÃO: Retorna ao REGISTRO_MENU ao invés de END
        return REGISTRO_MENU  # Mudança aqui para o botão funcionar
    
    elif query.data == "registro_voltar_menu":
        # Limpa contexto antes de voltar
        context.user_data.pop('contingencia_nome', None)
        context.user_data.pop('contingencia_bots_selecionados', None)
        
        await mostrar_menu_principal(query.message, query.from_user)
        return REGISTRO_MENU
    
    return CONTINGENCIA_SELECIONAR_BOTS

async def contingencia_gerenciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gerencia um grupo específico"""
    query = update.callback_query
    
    # Função auxiliar para mostrar a tela do grupo
    async def mostrar_grupo(group_id, message):
        group = manager.get_contingency_group_details(group_id)
        
        if not group:
            await message.edit_text("❌ Grupo não encontrado.", parse_mode='HTML')
            return False
        
        with open('./config.json', 'r') as f:
            config = json.loads(f.read())
        CONTINGENCY_DOMAIN = config.get('url', 'localhost').replace('https://', '').replace('http://', '').rstrip('/')
        
        link = f"https://{CONTINGENCY_DOMAIN}/r/{group['unique_code']}"
        
        text = f"📊 <b>{group['name']}</b>\n\n"
        text += f"🔗 <b>Link único:</b>\n<code>{link}</code>\n\n"
        text += f"📈 <b>Total de cliques:</b> {group['total_clicks']}\n"
        text += f"🤖 <b>Total de bots:</b> {len(group['bots'])}\n"
        
        bots_online = sum(1 for bot in group['bots'] if bot['is_online'])
        text += f"✅ <b>Bots online:</b> {bots_online}/{len(group['bots'])}\n"
        
        distribution_status = group.get('distribution_enabled', False)
        if distribution_status:
            text += f"⚙️ <b>Distribuição:</b> ✅ ATIVADA\n"
        else:
            text += f"⚙️ <b>Distribuição:</b> ❌ DESATIVADA\n"
        
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT emergency_link FROM CONTINGENCY_GROUPS 
            WHERE id = ?
        """, (group_id,))
        result = cursor.fetchone()
        conn.close()
        
        emergency_link = result[0] if result and result[0] else None
        
        if emergency_link:
            text += f"🚨 <b>Link Emergencial:</b> ✅ Configurado\n\n"
        else:
            text += f"🚨 <b>Link Emergencial:</b> ❌ Não configurado\n\n"
        
        text += "<b>Status dos bots:</b>\n"
        for i, bot in enumerate(group['bots']):
            status = "✅" if bot['is_online'] else "❌"
            
            if not distribution_status:
                current = "👉" if i == group['current_bot_index'] and bot['is_online'] else "  "
            else:
                current = "  "
            
            text += f"{current} {status} @{bot['username']}"
            if not bot['is_online'] and bot['marked_offline_at']:
                text += f" (offline desde {bot['marked_offline_at'][:10]})"
            text += "\n"
        
        if bots_online <= 2 and bots_online > 0:
            text += f"\n⚠️ <b>ATENÇÃO:</b> Apenas {bots_online} bot(s) online!"
        elif bots_online == 0:
            text += "\n🚨 <b>CRÍTICO:</b> Nenhum bot online! "
            if emergency_link:
                text += "Link emergencial está ativo!"
            else:
                text += "Configure um link emergencial!"
        
        dist_button_text = "🔴 Desativar Distribuição" if distribution_status else "🟢 Ativar Distribuição"
        dist_callback = f"cont_dist_off_{group_id}" if distribution_status else f"cont_dist_on_{group_id}"
        
        emergency_button_text = "🚨 Config. Emergência" if not emergency_link else "🚨 Editar Emergência"
        emergency_callback = f"cont_emergency_{group_id}"
        
        keyboard = [
            [InlineKeyboardButton(dist_button_text, callback_data=dist_callback)],
            [InlineKeyboardButton(emergency_button_text, callback_data=emergency_callback)],
            [InlineKeyboardButton("📚 Tutorial Rastreamento", callback_data=f"cont_tutorial_{group_id}")],
            [
                InlineKeyboardButton("➕ Add Bot", callback_data=f"cont_add_{group_id}"),
                InlineKeyboardButton("➖ Remover Bot", callback_data=f"cont_remove_{group_id}")
            ],
            [
                InlineKeyboardButton("🗑 Deletar Grupo", callback_data=f"cont_delete_{group_id}")
            ],
            [InlineKeyboardButton("🔙 Voltar", callback_data="contingencia_listar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.edit_text(text, parse_mode='HTML', reply_markup=reply_markup)
        return True
    
    if query.data.startswith("contingencia_ver_"):
        await query.answer()
        group_id = query.data.replace("contingencia_ver_", "")
        context.user_data['contingencia_group_id'] = group_id
        
        await mostrar_grupo(group_id, query.message)
        return CONTINGENCIA_GERENCIAR
    
    elif query.data.startswith("cont_tutorial_"):
        group_id = query.data.replace("cont_tutorial_", "")
        context.user_data['contingencia_group_id'] = group_id
        
        # Pega o link do grupo
        with open('./config.json', 'r') as f:
            config = json.loads(f.read())
        CONTINGENCY_DOMAIN = config.get('url', 'localhost').replace('https://', '').replace('http://', '').rstrip('/')
        
        # Busca o código único do grupo
        group = manager.get_contingency_group_details(group_id)
        if group:
            link = f"https://{CONTINGENCY_DOMAIN}/r/{group['unique_code']}"
        else:
            link = "[Link não disponível]"
        
        tutorial_text = f"""🥷 <b>TUTORIAL NGK - RASTREAMENTO UTMIFY</b>

━━━━━━━━━━━━━━━━━━

🎯 <b>COMO RASTREAR SUAS CAMPANHAS?</b>

<b>1️⃣ Configure o Link de Destino</b>

— Use este link único do seu grupo de contingência no campo "Link de Destino" do seu anúncio.

<pre>{link}</pre>

<b>2️⃣ Configure os Parâmetros de URL do anúncio</b>

— No seu anúncio, adicione o seguinte código no campo "Parâmetros de URL":

<pre>utm_source=FB&utm_campaign={{{{campaign.name}}}}|{{{{campaign.id}}}}&utm_medium={{{{adset.name}}}}|{{{{adset.id}}}}&utm_content={{{{ad.name}}}}|{{{{ad.id}}}}&utm_term={{{{placement}}}}</pre>

<b>3️⃣ Configure o Facebook Pixel</b>

— Dentro do seu bot de vendas, use o comando <code>/facebook</code> e configure seu Pixel.

<b>4️⃣ Configure a Utmify</b>

— Ainda no bot de vendas, use o comando <code>/utmify</code> e configure sua API da Utmify.

<b>5️⃣ Permissão de domínio</b>

— Para a NGK Pay enviar eventos ao Facebook e otimizar o seu Pixel com máxima performance, permita o domínio na lista de permissões dentro do gerenciador de eventos.

━━━━━━━━━━━━━━━━━━

💬 <b>PRINCIPAIS DÚVIDAS</b>

<b>1️⃣ Para que serve o Link Emergencial?</b>

— É um link de backup que será ativado automaticamente quando TODOS os bots do grupo de contingência estiverem offline. Garante que você nunca perca tráfego, mesmo em situações críticas.

<b>2️⃣ Para que serve o Distribuir Tráfego?</b>

— Quando ativado, distribui o tráfego igualmente entre todos os bots online do grupo de contingência, ao invés de usar apenas um por vez. Ideal para balancear a carga quando você tem alto volume de cliques.

<b>3️⃣ Anúncio direto pro grupo do telegram vai trackear?</b>

— NÃO! As vendas só serão trackeadas na Utmify subindo anúncio direto pro bot. É impossível trackear vendas subindo anúncio direto pro grupo/canal de prévias.

💡 <b>Dica:</b> Use o comando <code>/redirect</code> e configure seu grupo/canal de prévias no bot. Assim, você retém os usuários no grupo de prévias e ainda trackeia suas vendas na Utmify.

━━━━━━━━━━━━━━━━━━

⁉️ <b>NÃO TEM UTMIFY?</b> <a href="https://app.utmify.com.br/?code=DIARZBQBII">Clique aqui e cadastre-se com desconto especial</a>.

👨‍💻 <b>Ficou alguma dúvida?</b>
Entre em contato com nosso suporte."""
        
        keyboard = [[InlineKeyboardButton("🔙 Voltar", callback_data=f"contingencia_ver_{group_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.answer()
        await query.edit_message_text(
            tutorial_text,
            parse_mode='HTML',
            reply_markup=reply_markup,
            disable_web_page_preview=False
        )
        
        return CONTINGENCIA_TUTORIAL
    
    elif query.data.startswith("cont_dist_on_"):
        group_id = query.data.replace("cont_dist_on_", "")
        
        if manager.toggle_distribution(group_id, True):
            await query.answer("✅ Distribuição de tráfego ATIVADA!")
        else:
            await query.answer("❌ Erro ao ativar distribuição", show_alert=True)
        
        await mostrar_grupo(group_id, query.message)
        return CONTINGENCIA_GERENCIAR
    
    elif query.data.startswith("cont_dist_off_"):
        group_id = query.data.replace("cont_dist_off_", "")
        
        if manager.toggle_distribution(group_id, False):
            await query.answer("✅ Distribuição de tráfego DESATIVADA!")
        else:
            await query.answer("❌ Erro ao desativar distribuição", show_alert=True)
        
        await mostrar_grupo(group_id, query.message)
        return CONTINGENCIA_GERENCIAR
    
    elif query.data.startswith("cont_emergency_"):
        group_id = query.data.replace("cont_emergency_", "")
        context.user_data['contingencia_group_id'] = group_id
        
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT emergency_link FROM CONTINGENCY_GROUPS 
            WHERE id = ?
        """, (group_id,))
        result = cursor.fetchone()
        conn.close()
        
        current_link = result[0] if result and result[0] else None
        
        text = "🚨 <b>Configurar Link Emergencial</b>\n\n"
        
        if current_link:
            text += f"📌 <b>Link atual:</b>\n<code>{current_link}</code>\n\n"
            text += "Para alterar, envie o novo link.\n\n"
            
            keyboard = [
                [InlineKeyboardButton("🗑 Remover Link", callback_data="cont_remove_emergency")],
                [InlineKeyboardButton("❌ Cancelar", callback_data=f"contingencia_ver_{group_id}")]
            ]
        else:
            text += "💡 <b>O que é o Link Emergencial?</b>\n"
            text += "É um link de backup que será usado quando TODOS os bots do grupo estiverem offline.\n\n"
            text += "🎯 <b>Como funciona:</b>\n"
            text += "• Se todos os bots caírem, aparece uma página especial\n"
            text += "• A página tem um botão que leva para este link\n"
            text += "• Você NUNCA perde tráfego, mesmo em emergências\n\n"
            text += "📝 <b>Pode ser qualquer link:</b>\n"
            text += "• Outro grupo Telegram\n"
            text += "• WhatsApp\n"
            text += "• Seu site\n"
            text += "• Landing page\n\n"
            text += "Envie o link desejado:"
            
            keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data=f"contingencia_ver_{group_id}")]]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.answer()
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=reply_markup)
        
        return CONTINGENCIA_CONFIGURAR_EMERGENCIA
    
    elif query.data.startswith("cont_add_"):
        group_id = query.data.replace("cont_add_", "")
        context.user_data['contingencia_group_id'] = group_id
        user_id = query.from_user.id
        
        group = manager.get_contingency_group_details(group_id)
        if len(group['bots']) >= 20:
            await query.answer(
                "⚠️ Limite máximo atingido!\n\nO grupo já possui 20 bots (máximo permitido).", 
                show_alert=True
            )
            return CONTINGENCIA_GERENCIAR
        
        all_bots = manager.get_bots_by_owner(str(user_id))
        
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT cb.bot_id 
            FROM CONTINGENCY_BOTS cb
            JOIN CONTINGENCY_GROUPS cg ON cb.group_id = cg.id
            WHERE cg.owner_id = ? AND cg.is_active = 1
        """, (str(user_id),))
        
        bots_em_qualquer_grupo = [str(row[0]) for row in cursor.fetchall()]
        conn.close()
        
        available_bots = []
        bots_offline = 0
        
        for bot in all_bots:
            bot_id_str = str(bot[0])
            bot_token = bot[1]
            
            if bot_id_str in bots_em_qualquer_grupo:
                continue
            
            try:
                bot_details = manager.check_bot_token(bot_token)
                if bot_details and bot_details.get('result'):
                    bot_username = bot_details['result'].get('username')
                    bot_name = bot_details['result'].get('first_name', 'Sem nome')
                    
                    if bot_username:
                        available_bots.append({
                            'id': bot_id_str,
                            'token': bot_token,
                            'username': bot_username,
                            'name': bot_name
                        })
                    else:
                        bots_offline += 1
                else:
                    bots_offline += 1
            except:
                bots_offline += 1
        
        if len(available_bots) == 0:
            short_message = "⚠️ Nenhum bot disponível!\n\nRemova bots de outros grupos ou cadastre novos."
            
            await query.answer(short_message, show_alert=True)
            return CONTINGENCIA_GERENCIAR
        
        await query.answer()
        
        keyboard = []
        for bot_info in available_bots:
            button_text = f"➕ {bot_info['name']} (@{bot_info['username']})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"cont_confirmadd|{bot_info['id']}")])
        
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data=f"contingencia_ver_{group_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = f"➕ <b>Adicionar Bot ao Grupo</b>\n\n"
        text += f"📊 Bots disponíveis: {len(available_bots)}\n\n"
        text += "💡 <i>Apenas bots online e livres aparecem aqui</i>\n\n"
        text += "Selecione o bot que deseja adicionar:"
        
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return CONTINGENCIA_GERENCIAR
    
    elif query.data.startswith("cont_confirmadd|"):
        bot_id = query.data.replace("cont_confirmadd|", "")
        group_id = context.user_data.get('contingencia_group_id')
        
        if not group_id:
            await query.answer("❌ Sessão expirada. Volte e tente novamente.", show_alert=True)
            return CONTINGENCIA_GERENCIAR
        
        success = manager.add_bot_to_contingency_group(group_id, bot_id)
        
        if success:
            await query.answer("✅ Bot adicionado com sucesso!")
            await mostrar_grupo(group_id, query.message)
        else:
            await query.answer("❌ Bot já está no grupo ou erro ao adicionar", show_alert=True)
        
        return CONTINGENCIA_GERENCIAR
    
    elif query.data.startswith("cont_remove_"):
        group_id = query.data.replace("cont_remove_", "")
        context.user_data['contingencia_group_id'] = group_id
        group = manager.get_contingency_group_details(group_id)
        
        if len(group['bots']) <= 2:
            await query.answer(
                "⚠️ Mínimo de 2 bots no grupo!\n\n"
                "Você não pode remover bots pois o grupo precisa ter pelo menos 2 bots para funcionar.\n\n"
                "💡 Se quiser trocar os bots, adicione novos primeiro e depois remova os antigos.", 
                show_alert=True
            )
            return CONTINGENCIA_GERENCIAR
        
        await query.answer()
        
        keyboard = []
        for bot in group['bots']:
            if bot['is_online']:
                status_icon = "🟢"
            else:
                status_icon = "🔴"
            
            button_text = f"➖ {status_icon} @{bot['username']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"cont_confirmremove|{bot['bot_id']}")])
        
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data=f"contingencia_ver_{group_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bots_online = sum(1 for bot in group['bots'] if bot['is_online'])
        
        text = f"➖ <b>Remover Bot do Grupo</b>\n\n"
        text += f"📊 Total de bots: {len(group['bots'])}\n"
        text += f"✅ Online: {bots_online}\n"
        text += f"❌ Offline: {len(group['bots']) - bots_online}\n"
        text += f"⚠️ Mínimo permitido: 2 bots\n\n"
        
        if bots_online <= 2 and bots_online > 0:
            text += "⚠️ <b>ATENÇÃO:</b> Poucos bots online!\n\n"
        
        text += "Selecione o bot que deseja remover:\n"
        text += "<i>🟢 = Online | 🔴 = Offline</i>"
        
        await query.edit_message_text(
            text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return CONTINGENCIA_GERENCIAR
    
    elif query.data.startswith("cont_confirmremove|"):
        bot_id = query.data.replace("cont_confirmremove|", "")
        group_id = context.user_data.get('contingencia_group_id')
        
        if not group_id:
            await query.answer("❌ Sessão expirada. Volte e tente novamente.", show_alert=True)
            return CONTINGENCIA_GERENCIAR
        
        success = manager.remove_bot_from_contingency_group(group_id, bot_id)
        
        if success:
            await query.answer("✅ Bot removido com sucesso!")
            await mostrar_grupo(group_id, query.message)
        else:
            await query.answer("❌ Erro ao remover bot", show_alert=True)
        
        return CONTINGENCIA_GERENCIAR
    
    elif query.data.startswith("cont_delete_"):
        await query.answer()
        group_id = query.data.replace("cont_delete_", "")
        
        keyboard = [
            [
                InlineKeyboardButton("✅ SIM, DELETAR", callback_data=f"cont_confirmdelete_{group_id}"),
                InlineKeyboardButton("❌ CANCELAR", callback_data=f"contingencia_ver_{group_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🗑 <b>CONFIRMAR EXCLUSÃO</b>\n\n"
            "⚠️ Esta ação é permanente!\n"
            "O link de contingência parará de funcionar.\n\n"
            "Tem certeza que deseja deletar este grupo?",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return CONTINGENCIA_GERENCIAR
    
    elif query.data.startswith("cont_confirmdelete_"):
        group_id = query.data.replace("cont_confirmdelete_", "")
        user_id = str(query.from_user.id)
        
        if manager.delete_contingency_group(group_id, user_id):
            await query.answer("✅ Grupo deletado!")
            await query.edit_message_text(
                "✅ <b>Grupo deletado com sucesso!</b>",
                parse_mode='HTML'
            )
            return ConversationHandler.END
        else:
            await query.answer("❌ Erro ao deletar grupo", show_alert=True)
            return CONTINGENCIA_GERENCIAR
    
    elif query.data == "contingencia_listar":
        await query.answer()
        return await contingencia_callback(update, context)
    
    elif query.data == "registro_voltar_menu":
        await query.answer()
        await mostrar_menu_principal(query.message, query.from_user)
        return REGISTRO_MENU
    
    await query.answer()
    return CONTINGENCIA_GERENCIAR
    
async def contingencia_configurar_emergencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa a configuração do link emergencial com validação"""
    
    # Se for callback
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("contingencia_ver_"):
            group_id = query.data.replace("contingencia_ver_", "")
            context.user_data['contingencia_group_id'] = group_id
            
            update.callback_query.data = f"contingencia_ver_{group_id}"
            return await contingencia_gerenciar(update, context)
        
        elif query.data == "cont_remove_emergency":
            group_id = context.user_data.get('contingencia_group_id')
            
            if not group_id:
                await query.edit_message_text("❌ Sessão expirada.")
                return ConversationHandler.END
            
            if manager.set_emergency_link(group_id, None):
                keyboard = [[InlineKeyboardButton("🔙 Voltar ao Grupo", callback_data=f"contingencia_ver_{group_id}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "✅ <b>Link emergencial removido!</b>\n\n"
                    "O grupo agora não tem link de backup.",
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            else:
                await query.edit_message_text("❌ Erro ao remover link.")
            
            return CONTINGENCIA_GERENCIAR
        
        return CONTINGENCIA_GERENCIAR
    
    # Se for mensagem de texto
    if update.message:
        text = update.message.text.strip()
        group_id = context.user_data.get('contingencia_group_id')
        
        if not group_id:
            await update.message.reply_text("❌ Sessão expirada. Use /inicio")
            return ConversationHandler.END
        
        # VALIDAÇÃO DE LINK
        import re
        
        valid_patterns = [
            r'^https?://',
            r'^t\.me/',
            r'^wa\.me/',
        ]
        
        is_valid_link = any(re.match(pattern, text.lower()) for pattern in valid_patterns)
        
        if not is_valid_link:
            await update.message.reply_text(
                "⛔️ <b>Link inválido!</b>\n\n"
                "📌 <b>Exemplos de links válidos:</b>\n"
                "• https://exemplo.com\n"
                "• http://site.com.br\n"
                "• t.me/seucanal\n"
                "• https://t.me/seugrupo\n"
                "• wa.me/5511999999999\n\n"
                "⚠️ O link deve começar com:\n"
                "• http://\n"
                "• https://\n"
                "• t.me/\n"
                "• wa.me/\n\n"
                "Por favor, envie um link válido:",
                parse_mode='HTML'
            )
            return CONTINGENCIA_CONFIGURAR_EMERGENCIA
        
        # Se passou na validação, salva o link
        if manager.set_emergency_link(group_id, text):
            keyboard = [[InlineKeyboardButton("🔙 Voltar ao Grupo", callback_data=f"contingencia_ver_{group_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ <b>Link emergencial configurado!</b>\n\n"
                f"📌 <b>Link salvo:</b>\n<code>{text}</code>\n\n"
                f"Este link será usado quando todos os bots estiverem offline.\n\n"
                f"💡 <b>Importante:</b> Certifique-se que o link está funcionando!",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("❌ Erro ao salvar link. Tente novamente.")
        
        return CONTINGENCIA_GERENCIAR
    
    return CONTINGENCIA_CONFIGURAR_EMERGENCIA
    
def main():
    """Função principal para rodar o bot de registro"""
    if not REGISTRO_TOKEN:
        print("Token de registro não configurado!")
        return
        
    registro_token = REGISTRO_TOKEN
    application = Application.builder().token(registro_token).build()
    
    # Função auxiliar para cancelar contingência
    async def cancelar_contingencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancela operação de contingência e volta ao menu"""
        query = update.callback_query
        await query.answer()
        
        # Limpa dados do contexto
        context.user_data.pop('contingencia_nome', None)
        context.user_data.pop('contingencia_bots_selecionados', None)
        context.user_data.pop('contingencia_group_id', None)
        
        await mostrar_menu_principal(query.message, query.from_user)
        return ConversationHandler.END
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_func),
            CallbackQueryHandler(contingencia_menu, pattern="^contingencia_menu_inicial$"),
        ],
        states={
            REGISTRO_MENU: [
                CallbackQueryHandler(registro_menu_callback),
                CallbackQueryHandler(contingencia_menu, pattern="^contingencia_menu_inicial$"),
            ],
            REGISTRO_AGUARDANDO_TOKEN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_token_register),
                CallbackQueryHandler(receive_token_register, pattern="^registro_cancelar_silencioso$"),
            ],
            REGISTRO_SELECIONAR_BOT: [
                CallbackQueryHandler(registro_selecionar_bot_callback),
            ],
            REGISTRO_AGUARDANDO_NOVO_TOKEN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registro_processar_novo_token),
                CallbackQueryHandler(registro_processar_novo_token, pattern="^registro_cancelar_substituir$"),
            ],
            REGISTRO_DELETAR_BOT: [
                CallbackQueryHandler(registro_processar_deletar),
            ],
            # Estados de CONTINGÊNCIA
            CONTINGENCIA_MENU: [
                CallbackQueryHandler(contingencia_callback),
                CallbackQueryHandler(mostrar_menu_principal, pattern="^registro_voltar_menu$"),
            ],
            CONTINGENCIA_CRIAR_NOME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, contingencia_criar_nome),
                CallbackQueryHandler(cancelar_contingencia, pattern="^registro_voltar_menu$"),
            ],
            CONTINGENCIA_SELECIONAR_BOTS: [
                CallbackQueryHandler(contingencia_selecionar_bots, pattern="^contbot_"),
                CallbackQueryHandler(contingencia_selecionar_bots, pattern="^contingencia_confirmar$"),
                CallbackQueryHandler(cancelar_contingencia, pattern="^registro_voltar_menu$"),
            ],
            CONTINGENCIA_GERENCIAR: [
                CallbackQueryHandler(contingencia_gerenciar),
            ],
            CONTINGENCIA_CONFIGURAR_EMERGENCIA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, contingencia_configurar_emergencia),
                CallbackQueryHandler(contingencia_gerenciar, pattern="^contingencia_ver_"),
                CallbackQueryHandler(contingencia_configurar_emergencia, pattern="^cont_remove_emergency$"),
            ],
            CONTINGENCIA_TUTORIAL: [
                CallbackQueryHandler(contingencia_gerenciar, pattern="^contingencia_ver_"),
            ],
        },
        fallbacks=[
            CommandHandler('start', start_func),
            CallbackQueryHandler(mostrar_menu_principal, pattern="^registro_voltar_menu$"),
            CallbackQueryHandler(start_func, pattern="^start$"),
        ],
        per_message=False,
        allow_reentry=True
    )
    
    application.add_handler(conv_handler_suporte)
    application.add_handler(conv_handler)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print('Iniciando BOT de Registro')
    application.run_polling()

def start_register():
    register = Process(target=main)
    register.start()

@app.route('/dashboard-data', methods=['GET'])
def get_dashboard_data():
    if session.get("auth", False):
        dashboard_data['botsActive'] = len(processes)
        dashboard_data['usersCount'] = '?'
        dashboard_data['salesCount'] = len(manager.get_all_payments_by_status('finished'))
        return jsonify(dashboard_data)
    return jsonify({"error": "Unauthorized"}), 403

@app.route('/bots', methods=['GET'])
def bots():
    if session.get("auth", False):
        bot_list = manager.get_all_bots()
        bots = []

        for bot in bot_list:
            bot_details = manager.check_bot_token(bot[1])
            bot_structure = {
                'id': bot[0],
                'token': bot[1],
                'url': "Token Inválido",
                'owner': bot[2],
                'data': json.loads(bot[3])
            }
            if bot_details:
                bot_structure['url'] = f'https://t.me/{bot_details['result'].get('username', "INDEFINIDO")}'
            
            bots_data[str(bot[0])] = bot_structure
            bots.append(bot_structure)
        return jsonify(bots)
    return jsonify({"error": "Unauthorized"}), 403

@app.route('/terminal', methods=['POST'])
def terminal():
    if session.get("auth", False):
        data = request.get_json()
        command = data.get('command', '').strip()
        if not command:
            return jsonify({"response": "Comando vazio. Digite algo para enviar."}), 400
        
        response = f"Comando '{command}' recebido com sucesso. Processado às {time.strftime('%H:%M:%S')}."
        return jsonify({"response": response})
    return jsonify({"error": "Unauthorized"}), 403

@app.route('/health', methods=['GET'])
def health():
    """Endpoint de health check para o Railway"""
    return jsonify({
        "status": "healthy",
        "bots_active": len(processes),
        "timestamp": datetime.datetime.now().isoformat()
    })
    
@app.route('/admin/bots', methods=['GET'])
def admin_bots():
    if session.get("auth", False):
        return send_file('./templates/admin_bots.html')
    return redirect(url_for('login'))

@app.route('/api/bots/active', methods=['GET'])
def get_active_bots():
    if session.get("auth", False):
        # Retorna bots ativos com status dos processos
        active_bots = []
        all_bots = manager.get_all_bots()
        
        for bot in all_bots:
            bot_id = str(bot[0])
            bot_token = bot[1]
            
            bot_info = {
                'id': bot_id,
                'token': bot_token,
                'owner': bot[2],
                'status': 'inactive',  # Default
                'username': 'Carregando...',
                'name': 'Sem nome'  # Default
            }
            
            # Verifica se o processo está ativo
            if bot_id in processes:
                if processes[bot_id] and processes[bot_id].is_alive():
                    bot_info['status'] = 'active'
                else:
                    bot_info['status'] = 'inactive'
            
            # Tenta pegar username e nome do bot
            try:
                bot_details = manager.check_bot_token(bot_token)
                if bot_details and bot_details.get('result'):
                    bot_info['username'] = bot_details['result'].get('username', 'INDEFINIDO')
                    bot_info['name'] = bot_details['result'].get('first_name', 'Sem nome')
            except:
                bot_info['username'] = 'Token Inválido'
                bot_info['name'] = 'Erro'
            
            active_bots.append(bot_info)
        
        return jsonify(active_bots)
    return jsonify({"error": "Unauthorized"}), 403

# ========== ADICIONAR ESTE ENDPOINT COMPLETO ==========
@app.route('/api/bots/active/optimized', methods=['GET'])
def get_active_bots_optimized():
    """
    Versão otimizada do endpoint de listagem de bots.
    Usa processamento paralelo e cache para melhor performance.
    """
    if not session.get("auth", False):
        return jsonify({"error": "Unauthorized"}), 403
    
    print(f"[OPTIMIZED] ========== INICIANDO CARREGAMENTO ==========")
    start_time = time.time()
    
    # Busca todos os bots do banco
    all_bots = manager.get_all_bots()
    processed_bots = []
    
    # Cache de taxas por owner para evitar consultas repetidas
    owner_tax_cache = {}
    
    # print(f"[OPTIMIZED] Total de bots para processar: {len(all_bots)}")
    
    # Processa bots em paralelo usando ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        
        # Submete todas as verificações para o pool de threads
        for bot in all_bots:
            bot_id = str(bot[0])
            bot_token = bot[1]
            owner_id = str(bot[2])
            
            # Busca taxa do owner uma vez só (com cache)
            if owner_id not in owner_tax_cache:
                try:
                    owner_tax_cache[owner_id] = manager.get_owner_tax_type(owner_id)
                except Exception as e:
                    print(f"[OPTIMIZED] Erro ao buscar taxa do owner {owner_id}: {e}")
                    owner_tax_cache[owner_id] = {
                        'type': 'percentage',
                        'fixed_value': 0.75,
                        'percentage_value': 3.5
                    }
            
            # Submete verificação do bot para execução paralela
            future = executor.submit(get_bot_info_cached, bot_token)
            futures[future] = {
                'id': bot_id,
                'token': bot_token[:20] + '...',  # Segurança: não expor token completo
                'owner': owner_id,
                'tax_type': owner_tax_cache[owner_id]['type'],
                'fixed_value': owner_tax_cache[owner_id].get('fixed_value', 0.75),
                'percentage_value': owner_tax_cache[owner_id].get('percentage_value', 3.5)
            }
        
        # Processa resultados conforme as threads terminam
        completed = 0
        failed = 0
        
        for future in as_completed(futures, timeout=30):
            bot_info = futures[future]
            completed += 1
            
            try:
                # Pega resultado com timeout de 2 segundos por bot
                bot_details = future.result(timeout=2)
                
                if bot_details and bot_details.get('result'):
                    bot_info['username'] = bot_details['result'].get('username', 'INDEFINIDO')
                    bot_info['name'] = bot_details['result'].get('first_name', 'Sem nome')
                    bot_info['status'] = 'active'
                else:
                    bot_info['username'] = 'Token_Invalido'
                    bot_info['name'] = 'Erro'
                    bot_info['status'] = 'inactive'
                    failed += 1
                    
            except Exception as e:
                print(f"[OPTIMIZED] Erro ao verificar bot {bot_info['id']}: {str(e)[:50]}")
                bot_info['username'] = 'Erro'
                bot_info['name'] = 'Timeout'
                bot_info['status'] = 'inactive'
                failed += 1
            
            # Verifica se o processo do bot está rodando
            bot_id_str = str(bot_info['id'])
            if bot_id_str in processes:
                process = processes.get(bot_id_str)
                try:
                    if process and hasattr(process, 'is_alive') and process.is_alive():
                        bot_info['status'] = 'active'
                    else:
                        bot_info['status'] = 'inactive'
                except:
                    bot_info['status'] = 'inactive'
            else:
                # Se não tem processo, marca como inativo
                if bot_info['status'] == 'active' and bot_info['username'] != 'Token_Invalido':
                    bot_info['status'] = 'inactive'
            
            processed_bots.append(bot_info)
            
            # Log de progresso a cada 10 bots
            if completed % 10 == 0:
                print(f"[OPTIMIZED] Processados {completed}/{len(all_bots)} bots...")
    
    elapsed = time.time() - start_time
    print(f"[OPTIMIZED] ========== CARREGAMENTO COMPLETO ==========")
    print(f"[OPTIMIZED] Total: {len(processed_bots)} bots")
    print(f"[OPTIMIZED] Sucesso: {completed - failed}")
    print(f"[OPTIMIZED] Falhas: {failed}")
    print(f"[OPTIMIZED] Tempo: {elapsed:.2f} segundos")
    print(f"[OPTIMIZED] ==========================================")
    
    return jsonify(processed_bots)
# ========== FIM DO NOVO ENDPOINT ==========

@app.route('/api/bot/ban/<bot_id>', methods=['POST'])
def ban_bot(bot_id):
    if session.get("auth", False):
        bot = manager.get_bot_by_id(bot_id)
        if bot:
            bot_token = bot[1]
            owner_id = bot[2]
            
            # 1. PRIMEIRO envia a notificação através do PRÓPRIO BOT do cliente
            try:
                # Pega detalhes do bot
                bot_details = manager.check_bot_token(bot_token)
                bot_username = bot_details['result'].get('username', 'Bot') if bot_details else 'Bot'
                
                message = (
                    "🚫 <b>ATENÇÃO: ESTE BOT FOI BANIDO</b> 🚫\n\n"
                    f"<b>Bot:</b> @{bot_username}\n"
                    f"<b>ID:</b> {bot_id}\n\n"
                    "❌ Este bot será desligado em instantes.\n"
                    "❌ Todos os dados serão apagados.\n"
                    "❌ Esta ação é permanente e irreversível.\n\n"
                    "⚠️ <b>O bot parará de funcionar agora.</b>\n\n"
                    "Para mais informações, entre em contato com o suporte."
                )
                
                # Envia usando o TOKEN DO PRÓPRIO BOT
                response = requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": owner_id,
                        "text": message,
                        "parse_mode": "HTML"
                    }
                )
                print(f"Notificação enviada através do bot {bot_username}: {response.status_code}")
                
                # Aguarda 2 segundos para garantir que a mensagem foi enviada
                time.sleep(2)
                
            except Exception as e:
                print(f"Erro ao enviar notificação através do bot do cliente: {e}")
            
            # 2. Para TODOS os processos que usam este token
            # IMPORTANTE: Procura por token, não só por ID
            for pid, process in list(processes.items()):
                if pid == str(bot_id) or (pid in bots_data and bots_data[pid].get('token') == bot_token):
                    try:
                        if process:
                            # Envia SIGTERM
                            process.terminate()
                            time.sleep(0.5)
                            
                            # Se ainda estiver vivo, SIGKILL
                            if process.is_alive():
                                process.kill()
                                time.sleep(0.5)
                            
                            # Aguarda o processo realmente terminar
                            process.join(timeout=2)
                        
                        # Remove do dicionário de processos
                        processes.pop(pid, None)
                        print(f"Processo {pid} parado com sucesso")
                    except Exception as e:
                        print(f"Erro ao parar processo {pid}: {e}")
                    
                    # Remove dos dados em memória
                    if pid in bots_data:
                        bots_data.pop(pid)
            
            # 3. Remove o token da lista global
            if bot_token in tokens:
                tokens.remove(bot_token)
            
            # 4. Deleta do banco de dados
            success = manager.delete_bot(bot_id)
            
            if success:
                return jsonify({
                    "success": True, 
                    "message": f"Bot {bot_id} banido e removido com sucesso!"
                })
            else:
                return jsonify({
                    "success": False,
                    "message": "Erro ao remover bot do banco de dados"
                }), 500
        
        return jsonify({"error": "Bot não encontrado"}), 404
    return jsonify({"error": "Unauthorized"}), 403

@app.route('/api/bot/send-message/<bot_id>', methods=['POST'])
def send_message_to_bot_owner(bot_id):
    """Envia mensagem através do bot para o dono"""
    if not session.get("auth", False):
        return jsonify({"error": "Unauthorized"}), 403
    
    try:
        # Pega os dados da requisição
        data = request.get_json()
        message_text = data.get('message', '')
        use_template = data.get('use_template', False)
        template_id = data.get('template_id', '')
        
        if not message_text and not use_template:
            return jsonify({"error": "Mensagem vazia"}), 400
        
        # Pega informações do bot
        bot = manager.get_bot_by_id(bot_id)
        if not bot:
            return jsonify({"error": "Bot não encontrado"}), 404
        
        bot_token = bot[1]
        owner_id = bot[2]
        
        # Se usar template, pega o texto do template
        if use_template and template_id:
            templates = get_message_templates()
            template = templates.get(template_id)
            if template:
                message_text = template['text']
        
        # Pega detalhes do bot para personalizar mensagem
        bot_details = manager.check_bot_token(bot_token)
        bot_username = bot_details['result'].get('username', 'Bot') if bot_details else 'Bot'
        
        # ESCOLHA UMA DAS OPÇÕES ABAIXO (descomente a que preferir):
        
        # Opção 1 - Profissional com assinatura
        #formatted_message = f"<b>📢 NGK PAY | COMUNICADO OFICIAL</b>\n\n{message_text}\n\n<i>— Equipe NGK Pay</i>"
        
        # Opção 2 - Com linha decorativa
        #formatted_message = f"<b>⚡ AVISO IMPORTANTE - NGK PAY</b>\n━━━━━━━━━━━━━\n\n{message_text}"
        
        # Opção 3 - Minimalista
        #formatted_message = f"<b>NGK PAY INFORMA</b>\n\n{message_text}"
        
        # Opção 4 - Com emoji destacado
        #formatted_message = f"<b>🔴 ATENÇÃO - NGK PAY</b>\n\n{message_text}"
        
        # Opção 5 - Ultra clean
        # formatted_message = f"<b>NGK PAY</b>\n\n{message_text}"
        
        # Opção 6 - Com moldura
        #formatted_message = f"╭─────────────────╮\n│ <b>NGK PAY - AVISO</b> │\n╰─────────────────╯\n\n{message_text}"
        
        # Opção 7 - Estilo notificação
        # formatted_message = f"<b>⚠️ NGK PAY</b>\n\n{message_text}\n\n<i>Mensagem automática do sistema</i>"
        
        # Opção 8 - Com diamante
        # formatted_message = f"<b>NGK PAY 💎</b>\n\n{message_text}"

        # Opção 9 - Título estilizado com fonte especial
        formatted_message = f"<b>⚠️ 𝗡𝗚𝗞 𝗣𝗮𝘆 | Administração</b>\n\n{message_text}"
        
        # Envia a mensagem usando o token do bot DO CLIENTE
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': owner_id,
            'text': formatted_message,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            # Salva no log
            manager.save_admin_message_log(
                bot_id=bot_id,
                bot_token=bot_token,
                owner_id=owner_id,
                message=message_text,
                status='sent'
            )
            
            print(f"[ADMIN MSG] Mensagem enviada para owner {owner_id} através do bot {bot_id}")
            
            # Pega timestamp para resposta (apenas para log interno)
            from datetime import datetime
            import pytz
            brasilia_tz = pytz.timezone('America/Sao_Paulo')
            agora = datetime.now(brasilia_tz)
            
            return jsonify({
                "success": True,
                "message": "Mensagem enviada com sucesso!",
                "details": {
                    "bot_username": bot_username,
                    "owner_id": owner_id,
                    "timestamp": agora.strftime('%d/%m/%Y %H:%M')
                }
            })
        else:
            error_msg = response.json().get('description', 'Erro desconhecido')
            
            # Salva log de erro
            manager.save_admin_message_log(
                bot_id=bot_id,
                bot_token=bot_token,
                owner_id=owner_id,
                message=message_text,
                status=f'failed: {error_msg}'
            )
            
            return jsonify({
                "success": False,
                "error": error_msg
            }), 400
            
    except Exception as e:
        print(f"[ADMIN MSG] Erro: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/bot/groups/<bot_id>', methods=['GET'])
def get_bot_groups(bot_id):
    """Retorna todos os grupos configurados de um bot"""
    if not session.get("auth", False):
        return jsonify({"error": "Unauthorized"}), 403
    
    try:
        # Pega informações do bot
        bot = manager.get_bot_by_id(bot_id)
        if not bot:
            return jsonify({"error": "Bot não encontrado"}), 404
        
        groups = {
            "bot_username": "@indefinido",
            "groups": []
        }
        
        # Pega username do bot
        bot_token = bot[1]
        bot_details = manager.check_bot_token(bot_token)
        if bot_details and bot_details.get('result'):
            groups["bot_username"] = f"@{bot_details['result'].get('username', 'indefinido')}"
        
        # 1. GRUPO PRINCIPAL VIP
        main_group = manager.get_bot_group(bot_id)
        print(f"[GROUPS DEBUG] Grupo principal: {main_group}")
        
        if main_group:
            groups["groups"].append({
                "type": "main",
                "name": "Grupo Principal VIP",
                "id": main_group,
                "configured": True,
                "icon": "✅"
            })
        
        # 2. GRUPO UPSELL
        upsell_config = manager.get_bot_upsell(bot_id)
        print(f"[GROUPS DEBUG] Upsell config: {upsell_config}")
        
        if upsell_config and upsell_config.get('group_id'):
            groups["groups"].append({
                "type": "upsell",
                "name": "Grupo Upsell VIP",
                "id": upsell_config['group_id'],
                "configured": True,
                "icon": "🚀"
            })
        
        # 3. GRUPOS ORDERBUMP - CORRIGIDO PARA LISTA E DICIONÁRIO
        try:
            import sqlite3
            import json
            
            # Ajuste o caminho do banco se necessário
            if os.path.exists('/app/storage'):
                db_path = '/app/storage/data.db'
            else:
                db_path = 'data.db'
            
            conn = sqlite3.connect(db_path, timeout=10)
            cursor = conn.cursor()
            
            # Busca o campo orderbump direto
            cursor.execute("SELECT orderbump FROM BOTS WHERE id = ?", (bot_id,))
            result = cursor.fetchone()
            
            print(f"[GROUPS DEBUG] Orderbump raw do banco: {result}")
            
            if result and result[0] and result[0] not in ['{}', '[]', None]:
                orderbumps_data = json.loads(result[0])
                print(f"[GROUPS DEBUG] Orderbumps parseado: {orderbumps_data}")
                print(f"[GROUPS DEBUG] Tipo do orderbumps_data: {type(orderbumps_data)}")
                
                # CORREÇÃO: Verifica se é LISTA ou DICIONÁRIO
                if isinstance(orderbumps_data, list):
                    # Se for LISTA (formato novo)
                    for idx, orderbump in enumerate(orderbumps_data):
                        if orderbump and isinstance(orderbump, dict):
                            print(f"[GROUPS DEBUG] Processando orderbump {idx}: {orderbump}")
                            
                            # Verifica se tem group_id
                            if orderbump.get('group_id'):
                                group_name = orderbump.get('group_name', f'OrderBump {idx + 1}')
                                
                                # Remove prefixos desnecessários do nome se existir
                                if group_name.startswith('Canal: '):
                                    group_name = group_name.replace('Canal: ', '')
                                elif group_name.startswith('Grupo: '):
                                    group_name = group_name.replace('Grupo: ', '')
                                
                                groups["groups"].append({
                                    "type": "orderbump",
                                    "name": f"🎁 {group_name}",
                                    "id": orderbump['group_id'],
                                    "configured": True,
                                    "icon": "🎁",
                                    "plan_index": orderbump.get('plano_id', idx)
                                })
                                print(f"[GROUPS DEBUG] OrderBump adicionado: {group_name} - {orderbump['group_id']}")
                
                elif isinstance(orderbumps_data, dict):
                    # Se for DICIONÁRIO (formato antigo)
                    for plan_index, orderbump in orderbumps_data.items():
                        if orderbump and isinstance(orderbump, dict):
                            print(f"[GROUPS DEBUG] Processando orderbump do plano {plan_index}: {orderbump}")
                            
                            # Verifica se tem group_id
                            if orderbump.get('group_id'):
                                group_name = orderbump.get('group_name', f'OrderBump Plano {int(plan_index) + 1}')
                                
                                groups["groups"].append({
                                    "type": "orderbump",
                                    "name": f"🎁 {group_name}",
                                    "id": orderbump['group_id'],
                                    "configured": True,
                                    "icon": "🎁",
                                    "plan_index": plan_index
                                })
                                print(f"[GROUPS DEBUG] OrderBump adicionado: {group_name} - {orderbump['group_id']}")
            
            conn.close()
            
        except Exception as e:
            print(f"[GROUPS DEBUG] Erro ao buscar orderbumps: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"[GROUPS DEBUG] Total de grupos encontrados: {len(groups['groups'])}")
        print(f"[GROUPS DEBUG] Grupos finais: {groups}")
        
        return jsonify(groups)
        
    except Exception as e:
        print(f"[GROUPS] Erro ao buscar grupos: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/bot/generate-link/<bot_id>', methods=['POST'])
def generate_group_link(bot_id):
    """Gera link de acesso direto para um grupo"""
    if not session.get("auth", False):
        return jsonify({"error": "Unauthorized"}), 403
    
    try:
        data = request.get_json()
        group_id = data.get('group_id')
        group_type = data.get('group_type', 'main')
        
        if not group_id:
            return jsonify({"error": "ID do grupo não fornecido"}), 400
        
        # Pega o token do bot
        bot = manager.get_bot_by_id(bot_id)
        if not bot:
            return jsonify({"error": "Bot não encontrado"}), 404
        
        bot_token = bot[1]
        
        # Calcula tempo de expiração (1 hora)
        import time
        expire_time = int(time.time()) + 3600  # 1 hora
        
        # Cria o link via API do Telegram
        url = f"https://api.telegram.org/bot{bot_token}/createChatInviteLink"
        payload = {
            'chat_id': group_id,
            'name': f'Auditoria Admin - {group_type.upper()}',
            'expire_date': expire_time,
            'member_limit': 1,  # Apenas 1 uso
            'creates_join_request': False  # Acesso direto
        }
        
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                invite_link = result['result']['invite_link']
                
                # Formata resposta
                from datetime import datetime
                expire_datetime = datetime.fromtimestamp(expire_time)
                
                return jsonify({
                    "success": True,
                    "link": invite_link,
                    "expires_at": expire_datetime.strftime('%H:%M'),
                    "group_id": group_id,
                    "group_type": group_type
                })
            else:
                error_msg = result.get('description', 'Erro desconhecido')
                
                # Tratamento de erros comuns
                if 'chat not found' in error_msg.lower():
                    return jsonify({"error": "Grupo não encontrado. Verifique se o bot está no grupo."}), 400
                elif 'not enough rights' in error_msg.lower():
                    return jsonify({"error": "Bot não tem permissão de admin no grupo."}), 400
                else:
                    return jsonify({"error": error_msg}), 400
        else:
            return jsonify({"error": "Erro ao comunicar com API do Telegram"}), 500
            
    except Exception as e:
        print(f"[GENERATE LINK] Erro: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/bot/preview-text/<bot_id>', methods=['GET'])
def get_bot_preview_text(bot_id):
    """
    Retorna todos os textos do bot para preview rápido.
    Usado para identificar copy agressiva sem abrir o bot.
    """
    if not session.get("auth", False):
        return jsonify({"error": "Unauthorized"}), 403
    
    try:
        # Busca o bot no banco
        bot = manager.get_bot_by_id(bot_id)
        if not bot:
            return jsonify({"error": "Bot não encontrado"}), 404
        
        # Parse dos campos JSON
        config = json.loads(bot[3]) if bot[3] else {}
        plans = json.loads(bot[5]) if bot[5] else []
        upsell = json.loads(bot[8]) if bot[8] else {}
        expiration = json.loads(bot[10]) if bot[10] else {}
        
        # Busca dados adicionais usando as funções do manager
        downsell = manager.get_bot_downsell(bot_id)
        orderbump = manager.get_bot_orderbump(bot_id)
        recovery = manager.get_bot_recovery(bot_id)
        scheduled_broadcasts = manager.get_bot_scheduled_broadcasts(bot_id)
        
        # Monta objeto de resposta com todos os textos
        preview_data = {
            'inicio': {
                'texto1': config.get('texto1', ''),
                'texto2': config.get('texto2', 'Não configurado'),
                'button': config.get('button', 'CLIQUE AQUI PARA VER OFERTAS')  # ADICIONAR ESTA LINHA
            },
            'planos': [],
            'upsell': upsell.get('text', 'Não configurado'),
            'downsell': downsell.get('text', 'Não configurado'),
            'orderbumps': [],
            'recuperacao': [],
            'disparos': [],
            'adeus': expiration.get('text', 'Não configurado')
        }
        
        # Processa planos
        for plan in plans:
            if isinstance(plan, dict):
                preview_data['planos'].append({
                    'nome': plan.get('name', 'Sem nome'),
                    'valor': f"R$ {plan.get('value', 0)}",
                    'descricao': plan.get('description', '')
                })
        
        # Processa orderbumps (pode ser lista ou dict)
        if isinstance(orderbump, list):
            for ob in orderbump:
                if ob and isinstance(ob, dict):
                    preview_data['orderbumps'].append(ob.get('text', ''))
        elif isinstance(orderbump, dict):
            for key, ob in orderbump.items():
                if ob and isinstance(ob, dict):
                    preview_data['orderbumps'].append(ob.get('text', ''))
        
        # Processa recuperações
        if isinstance(recovery, list):
            for idx, rec in enumerate(recovery):
                if rec and isinstance(rec, dict):
                    preview_data['recuperacao'].append({
                        'ordem': idx + 1,
                        'delay': rec.get('delay', f'{idx+1}h'),
                        'texto': rec.get('text', '')
                    })
        
        # Processa disparos programados
        for broadcast in scheduled_broadcasts:
            if isinstance(broadcast, dict):
                preview_data['disparos'].append({
                    'horario': broadcast.get('time', 'Não definido'),
                    'texto': broadcast.get('text', '')
                })
        
        return jsonify(preview_data)
        
    except Exception as e:
        print(f"[PREVIEW ERROR] Erro ao buscar preview do bot {bot_id}: {e}")
        return jsonify({"error": str(e)}), 500
        
def get_message_templates():
    """Retorna templates de mensagens prontos"""
    return {
        'copy_agressiva': {
            'name': '⚠️ Copy Agressiva',
            'text': """⚠️ <b>AVISO - Conteúdo Inadequado</b>

Identificamos que seu bot está utilizando copy muito agressiva ou enganosa nas mensagens de venda.

<b>Problema identificado:</b>
- Promessas exageradas ou falsas
- Linguagem inadequada ou ofensiva
- Possível violação de diretrizes

<b>Ação necessária:</b>
Você tem 24 HORAS para adequar o conteúdo do seu bot.

Caso não seja feito, seu bot será PERMANENTEMENTE BANIDO da plataforma.

Se precisar de ajuda, entre em contato com o suporte."""
        },
        'sem_gateway': {
            'name': '🔴 Sem Gateway',
            'text': """🔴 <b>ATENÇÃO - Gateway não configurado</b>

Seu bot ainda não possui um gateway de pagamento configurado.

Sem isso, você NÃO conseguirá receber pagamentos.

<b>Como resolver:</b>
1. Acesse seu bot
2. Use o comando /gateway
3. Configure sua forma de pagamento

Precisa de ajuda? Entre em contato com o suporte."""
        },
        'manutencao': {
            'name': '🔧 Manutenção',
            'text': """🔧 <b>MANUTENÇÃO PROGRAMADA</b>

Informamos que realizaremos uma manutenção no sistema.

<b>Quando:</b> Hoje, das 02:00 às 04:00 (Horário de Brasília)

<b>O que pode acontecer:</b>
- Seu bot pode ficar temporariamente offline
- Pagamentos podem demorar para processar
- Mensagens podem ter atraso

Não é necessária nenhuma ação de sua parte. Pedimos desculpas pelo transtorno."""
        },
        'aviso_banimento': {
            'name': '🚫 Pré-Banimento',
            'text': """🚫 <b>ÚLTIMO AVISO - BANIMENTO IMINENTE</b>

Este é seu ÚLTIMO AVISO antes do banimento permanente.

Você tem 2 HORAS para:
1. Corrigir o conteúdo do seu bot
2. Entrar em contato com o suporte
3. Explicar as mudanças realizadas

Após este prazo, sem resposta, seu bot será BANIDO PERMANENTEMENTE.

Todos os seus dados serão apagados e não poderão ser recuperados."""
        },
        'taxa_ajustada': {
            'name': '💰 Taxa Ajustada',
            'text': """💰 <b>AJUSTE DE TAXA</b>

Informamos que sua taxa foi ajustada.

<b>Nova taxa:</b> X%
<b>Válida a partir de:</b> Agora

Este ajuste foi realizado devido a:
- [Motivo do ajuste]

Se tiver dúvidas, entre em contato com o suporte."""
        }
    }

@app.route('/api/bot/templates', methods=['GET'])
def get_templates():
    """Retorna os templates disponíveis"""
    if not session.get("auth", False):
        return jsonify({"error": "Unauthorized"}), 403
    
    templates = get_message_templates()
    return jsonify(templates)

@app.route('/api/bot/revenue/<bot_id>', methods=['GET'])
def get_bot_revenue(bot_id):
    """Endpoint para buscar estatísticas de faturamento de um bot"""
    if session.get("auth", False):
        # Pega o período da query string
        period = request.args.get('period', 'today')
        
        # Valida períodos permitidos
        valid_periods = ['today', 'yesterday', 'this_week', 'last_week', 
                        'this_month', 'last_month', 'total']
        
        if period not in valid_periods:
            period = 'today'
        
        # Busca as estatísticas
        stats = manager.get_bot_revenue_stats(bot_id, period)
        
        # Pega informações do bot
        bot = manager.get_bot_by_id(bot_id)
        if bot:
            bot_details = manager.check_bot_token(bot[1])
            if bot_details and bot_details.get('result'):
                stats['bot_username'] = bot_details['result'].get('username', 'INDEFINIDO')
                stats['bot_name'] = bot_details['result'].get('first_name', 'Sem nome')
            else:
                stats['bot_username'] = 'INDEFINIDO'
                stats['bot_name'] = 'Sem nome'
        
        return jsonify(stats)
    
    return jsonify({"error": "Unauthorized"}), 403

@app.route('/api/bot/tax/<bot_id>', methods=['GET'])
def get_bot_tax_endpoint(bot_id):
    """Retorna a taxa configurada para um bot"""
    if session.get("auth", False):
        tax = manager.get_bot_tax(bot_id)
        return jsonify({"tax": tax})
    return jsonify({"error": "Unauthorized"}), 403

@app.route('/api/bot/tax/<bot_id>', methods=['POST'])
def set_bot_tax_endpoint(bot_id):
    """Define a taxa para um bot"""
    if session.get("auth", False):
        try:
            data = request.get_json()
            tax = float(data.get('tax', 1))
            
            # Valida o range (0 a 10)
            if tax < 0 or tax > 10:
                return jsonify({"error": "Taxa deve estar entre 0% e 10%"}), 400
            
            # Salva a taxa
            manager.set_bot_tax(bot_id, tax)
            
            return jsonify({
                "success": True, 
                "message": f"Taxa atualizada para {tax}%",
                "tax": tax
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return jsonify({"error": "Unauthorized"}), 403

@app.route('/api/bot/owner-tax-type/<owner_id>', methods=['GET'])
def get_owner_tax_type_endpoint(owner_id):
    """Retorna o tipo de taxa configurado para um owner"""
    if session.get("auth", False):
        tax_config = manager.get_owner_tax_type(owner_id)
        return jsonify(tax_config)
    return jsonify({"error": "Unauthorized"}), 403

@app.route('/api/bot/owner-tax-value/<owner_id>', methods=['POST'])
def set_owner_tax_value(owner_id):
    """Ajusta o valor da taxa (fixa ou percentual) para um owner específico"""
    if session.get("auth", False):
        try:
            data = request.get_json()
            
            # Pega a configuração atual para saber o tipo
            tax_config = manager.get_owner_tax_type(owner_id)
            tax_type = tax_config['type']
            
            if tax_type == 'fixed':
                # Ajusta valor da taxa fixa
                new_value = float(data.get('value', 0.75))
                
                # Valida o range (0 a 10 reais)
                if new_value < 0 or new_value > 10:
                    return jsonify({"error": "Taxa fixa deve estar entre R$ 0,00 e R$ 10,00"}), 400
                
                manager.set_owner_tax_type(owner_id, 'fixed', new_value)
                
                return jsonify({
                    "success": True,
                    "message": f"Taxa fixa ajustada para R$ {new_value:.2f}",
                    "type": "fixed",
                    "value": new_value
                })
            else:
                # Ajusta valor da taxa percentual
                new_value = float(data.get('value', 3.5))
                
                # Valida o range (0 a 10%)
                if new_value < 0 or new_value > 10:
                    return jsonify({"error": "Taxa percentual deve estar entre 0% e 10%"}), 400
                
                manager.set_owner_tax_type(owner_id, 'percentage', new_value)
                
                return jsonify({
                    "success": True,
                    "message": f"Taxa percentual ajustada para {new_value:.1f}%",
                    "type": "percentage",
                    "value": new_value
                })
                
        except Exception as e:
            print(f"[ERRO set_owner_tax_value] {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500
    
    return jsonify({"error": "Unauthorized"}), 403

@app.route('/check-inactive', methods=['GET'])
def check_inactive():
    """Endpoint interno para verificar bots inativos"""
    check_and_remove_inactive_bots()
    return jsonify({"status": "checked"})

if __name__ == '__main__':
    print(f"Iniciando aplicação na porta {port}")
    print(f"URL configurada: {IP_DA_VPS}")
    
    manager.inicialize_database()
    manager.migrate_payments_tax_info()  # ADICIONE ESTA LINHA
    manager.ensure_pix_generated_at_column()  # ADICIONAR ESTA LINHA
    manager.create_pix_generation_tracking_table()  # ADICIONAR
    
    # FORÇA CRIAÇÃO DA TABELA USER_TRACKING
    print("🔄 Verificando tabelas do banco...")
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cur = conn.cursor()
    
    # Cria USER_TRACKING
    cur.execute("""
        CREATE TABLE IF NOT EXISTS USER_TRACKING (
            user_id TEXT,
            bot_id TEXT,
            first_start TEXT,
            last_activity TEXT,
            PRIMARY KEY (user_id, bot_id)
        )
    """)
    
    # Adiciona colunas em PAYMENTS
    try:
        cur.execute("ALTER TABLE PAYMENTS ADD COLUMN created_at TEXT DEFAULT (datetime('now', 'localtime'))")
    except:
        pass
    
    try:
        cur.execute("ALTER TABLE PAYMENTS ADD COLUMN is_from_new_user INTEGER DEFAULT 0")
    except:
        pass
    
    conn.commit()
    
    # Verifica se criou
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='USER_TRACKING'")
    if cur.fetchone():
        print("✅ Tabela USER_TRACKING verificada!")
    else:
        print("❌ Erro ao criar USER_TRACKING!")
    
    conn.close()
    
    manager.create_recovery_tracking_table()
    manager.create_contingency_tables()  # JÁ ESTÁ AQUI, OK!
    initialize_all_registered_bots()
    print("=" * 50)
    print("🚀 INICIALIZANDO SISTEMA DE CACHE OTIMIZADO")
    print("=" * 50)
    clear_old_cache()  # Inicia limpeza periódica de cache
    print("✅ Sistema de cache ativo - limpeza a cada 5 minutos")
    print("✅ Cache TTL configurado para 300 segundos")
    print("=" * 50)
    start_register()
    
    # Inicia thread de verificação de inatividade
    import threading
    inactivity_thread = threading.Thread(target=inactivity_checker_thread, daemon=True)
    inactivity_thread.start()
    
    # Inicia thread de monitoramento de contingência - ADICIONE ESTAS 3 LINHAS
    contingency_thread = threading.Thread(target=contingency_monitor_thread, daemon=True)
    contingency_thread.start()
    print("✅ Monitor de contingência iniciado")
    
    app.run(debug=False, host='0.0.0.0', port=port)
