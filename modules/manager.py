import json, sqlite3, datetime, requests
from datetime import datetime, timedelta
import pytz
import os

if os.path.exists('/app/storage'):
    DB_PATH = '/app/storage/data.db'
    print("✅ Usando volume persistente: /app/storage/data.db")
else:
    DB_PATH = 'data.db'
    print("📁 Usando banco local: data.db")

# Debug
print(f"DEBUG - DB_PATH definido como: {DB_PATH}")
print(f"DEBUG - /data existe? {os.path.exists('/data')}")

def inicialize_database():
    # IMPORTANTE: Garante que DB_PATH existe
    import os
    
    # Define DB_PATH localmente se não existir globalmente
    if 'DB_PATH' not in globals():
        if os.path.exists('/app/storage'):
            global DB_PATH
            DB_PATH = '/app/storage/data.db'
            print(f"[INIT DB] Definindo DB_PATH: {DB_PATH}")
        else:
            DB_PATH = 'data.db'
            print(f"[INIT DB] Usando local: {DB_PATH}")
    
    print(f"[INIT DB] Criando/abrindo banco em: {DB_PATH}")
    
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS BOTS (
            id TEXT PRIMARY KEY,
            token TEXT UNIQUE,
            owner TEXT,
            config TEXT,
            admin TEXT,
            plans TEXT,
            gateway TEXT,
            users TEXT,
            upsell TEXT,
            "group" TEXT,
            expiration TEXT
        )
    """)
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS USERS (
            id_user TEXT,
            data_entrada TEXT,
            data_expiracao TEXT,
            plano TEXT,
            grupo TEXT
        )
    ''')
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS PAYMENTS (
            id TEXT,
            trans_id TEXT,
            chat TEXT,
            plano TEXT,
            bot TEXT,
            status TEXT
        )
    """)
    
    # NOVO: Cria tabela de tracking do Facebook
    cur.execute("""
        CREATE TABLE IF NOT EXISTS FACEBOOK_TRACKING (
            user_id TEXT,
            bot_id TEXT,
            fbclid TEXT,
            first_click_time TEXT,
            last_updated TEXT,
            PRIMARY KEY (user_id, bot_id)
        )
    """)
    
    # NOVA TABELA: Tracking completo com UTMs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS UTM_TRACKING (
            user_id TEXT,
            bot_id TEXT,
            fbclid TEXT,
            utm_source TEXT,
            utm_campaign TEXT,
            utm_medium TEXT,
            utm_content TEXT,
            utm_term TEXT,
            src TEXT,
            sck TEXT,
            fbp TEXT,
            fbc TEXT,
            first_click_time TEXT,
            last_updated TEXT,
            PRIMARY KEY (user_id, bot_id)
        )
    """)

    # NOVA TABELA: Tracking Mapping para salvar cookies do redirect
    cur.execute("""
        CREATE TABLE IF NOT EXISTS TRACKING_MAPPING (
            short_id TEXT PRIMARY KEY,
            fbclid TEXT,
            utm_source TEXT,
            utm_campaign TEXT,
            utm_medium TEXT,
            utm_content TEXT,
            utm_term TEXT,
            src TEXT,
            sck TEXT,
            fbp TEXT,
            fbc TEXT,
            created_at TEXT NOT NULL
        )
    """)
    print("✅ Tabela TRACKING_MAPPING criada/verificada")
    
    # NOVA TABELA: Configuração Utmify por bot
    cur.execute("""
        CREATE TABLE IF NOT EXISTS UTMIFY_CONFIG (
            bot_id TEXT PRIMARY KEY,
            api_token TEXT,
            enabled INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    
    # ========== NOVO CÓDIGO COMEÇA AQUI ==========
    # ADICIONAR ÍNDICES PARA PERFORMANCE
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bots_owner 
        ON BOTS(owner)
    """)
    
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_bots_token 
        ON BOTS(token)
    """)
    
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_payments_bot 
        ON PAYMENTS(bot)
    """)
    
    # Criar tabela para cache de status dos bots
    cur.execute("""
        CREATE TABLE IF NOT EXISTS BOT_STATUS_CACHE_TABLE (
            bot_token_hash TEXT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            is_valid INTEGER,
            cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    print("✅ Índices de performance criados/verificados")
    print("✅ Tabela de cache de status criada/verificada")
    # ========== NOVO CÓDIGO TERMINA AQUI ==========
    
    conn.commit()
    conn.close()
    
    # Verifica se foi criado no lugar certo
    print(f"[INIT DB] ✅ Banco inicializado!")
    print(f"[INIT DB] 📁 Arquivo existe em {DB_PATH}? {os.path.exists(DB_PATH)}")

def count_bots():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM BOTS")
        count = cursor.fetchone()[0]
        
        return count
    except sqlite3.Error as e:
        print(f"Erro ao acessar o banco de dados: {e}")
        return None
    finally:
        if conn:
            conn.close()
def get_bot_by_id(bot_id):

    print(bot_id)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM BOTS WHERE id = ?", (bot_id,))
    result = cursor.fetchone()
    if result:
        conn.close()
        return result

config_default = {
    'texto1':False,
    'texto2':"Configure o bot usando /inicio\n\nUtilize /comandos para verificar os comandos existentes",
    'button':'CLIQUE AQUI PARA VER OFERTAS'
}

# Adicione esta função no arquivo manager.py

def get_bot_token(bot_id):
    """Retorna o token do bot pelo ID"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT token FROM BOTS WHERE id = ?", (bot_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return result[0]
    return None

def get_bots_by_owner(owner_id):
    """Retorna todos os bots de um owner específico"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM BOTS WHERE owner = ?", (str(owner_id),))
    result = cursor.fetchall()
    conn.close()
    return result if result else []

def create_bot(id, token, owner, config=config_default, admin=[], plans=[], gateway={}, users=[], upsell={}, group='', expiration={}):
    # Conecta ao banco de dados
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cur = conn.cursor()
    
    # Primeiro, garante que a coluna last_activity existe
    cur.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cur.fetchall()]
    
    if 'last_activity' not in columns:
        cur.execute("ALTER TABLE BOTS ADD COLUMN last_activity TEXT DEFAULT NULL")
        conn.commit()

    # Insere um novo registro na tabela BOTS
    try:
        # IMPORTANTE: Define last_activity como AGORA
        from datetime import datetime
        current_time = datetime.now().isoformat()
        
        cur.execute("""
            INSERT INTO BOTS (id, token, owner, config, admin, plans, gateway, users, upsell, "group", expiration, last_activity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (id, token, owner, json.dumps(config), json.dumps(admin), json.dumps(plans), 
              json.dumps(gateway), json.dumps(users), json.dumps(upsell), group, 
              json.dumps(expiration), current_time))
        
        # Confirma a transação
        conn.commit()
        print(f"Bot criado com sucesso! Last activity: {current_time}")
    except sqlite3.IntegrityError as e:
        print("Erro ao criar bot:", e)
    finally:
        # Fecha a conexão
        conn.close()

def check_bot_token(token):
    response = requests.get(f'https://api.telegram.org/bot{token}/getMe')
    if response.status_code == 200:
        return json.loads(response.text)
    else:
        return False
    
def bot_exists(token):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM BOTS WHERE token = ?", (token,))
    exists = cursor.fetchone() is not None
    
    conn.close()
    return exists

def get_all_bots():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM BOTS")
    exists = cursor.fetchall()
    print(exists)
    conn.close()
    return exists

def update_bot_config(bot_id, config):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE BOTS SET config = ? WHERE id = ?", (json.dumps(config), bot_id))
    conn.commit()
    conn.close()

def add_media_to_config(bot_id, media_data):
    """Adiciona uma mídia ao array de mídias do bot"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # CORREÇÃO: Usa 'id' ao invés de 'bot_id'
    cursor.execute("SELECT config FROM BOTS WHERE id = ?", (bot_id,))
    result = cursor.fetchone()
    
    if result:
        import json
        config = json.loads(result[0]) if result[0] else {}
        
        # Inicializa array de mídias se não existir
        if 'midias' not in config:
            config['midias'] = []
        
        # Adiciona a nova mídia com ordem
        media_data['order'] = len(config['midias']) + 1
        config['midias'].append(media_data)
        
        # Salva de volta
        cursor.execute("UPDATE BOTS SET config = ? WHERE id = ?", 
                      (json.dumps(config), bot_id))
        conn.commit()
        conn.close()
        
        print(f"[MANAGER] Mídia {media_data['order']} adicionada para bot {bot_id}")
        return True
    
    conn.close()
    return False

def clear_medias_config(bot_id):
    """Limpa todas as mídias do array e configurações relacionadas"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("SELECT config FROM BOTS WHERE id = ?", (bot_id,))
    result = cursor.fetchone()
    
    if result:
        import json
        config = json.loads(result[0]) if result[0] else {}
        
        # Limpa TUDO relacionado a mídias
        config['midias'] = []
        config['midia'] = False  # Remove mídia única também
        config['media_mode'] = None  # Remove modo de exibição
        
        # Salva de volta
        cursor.execute("UPDATE BOTS SET config = ? WHERE id = ?", 
                      (json.dumps(config), bot_id))
        conn.commit()
        conn.close()
        
        print(f"[MANAGER] Todas as mídias e configurações relacionadas foram limpas para bot {bot_id}")
        return True
    
    conn.close()
    return False

def get_medias_count(bot_id):
    """Retorna quantidade de mídias cadastradas"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # CORREÇÃO: Usa 'id' ao invés de 'bot_id'
    cursor.execute("SELECT config FROM BOTS WHERE id = ?", (bot_id,))
    result = cursor.fetchone()
    
    if result:
        import json
        config = json.loads(result[0]) if result[0] else {}
        midias = config.get('midias', [])
        conn.close()
        return len(midias)
    
    conn.close()
    return 0

def get_medias_info(bot_id):
    """Retorna informações detalhadas sobre as mídias cadastradas"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("SELECT config FROM BOTS WHERE id = ?", (bot_id,))
    result = cursor.fetchone()
    
    if result:
        import json
        config = json.loads(result[0]) if result[0] else {}
        midias = config.get('midias', [])
        
        # Conta tipos
        photos = len([m for m in midias if m.get('type') == 'photo'])
        videos = len([m for m in midias if m.get('type') == 'video'])
        
        conn.close()
        return {
            'total': len(midias),
            'photos': photos,
            'videos': videos
        }
    
    conn.close()
    return {'total': 0, 'photos': 0, 'videos': 0}

def set_media_display_mode(bot_id, mode):
    """Define se mídias serão enviadas como 'sequential' ou 'album'"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # CORREÇÃO: Usa 'id' ao invés de 'bot_id'
    cursor.execute("SELECT config FROM BOTS WHERE id = ?", (bot_id,))
    result = cursor.fetchone()
    
    if result:
        import json
        config = json.loads(result[0]) if result[0] else {}
        
        # Define o modo de exibição
        config['media_mode'] = mode  # 'sequential' ou 'album'
        
        # Salva de volta
        cursor.execute("UPDATE BOTS SET config = ? WHERE id = ?", 
                      (json.dumps(config), bot_id))
        conn.commit()
        conn.close()
        
        print(f"[MANAGER] Modo de mídia definido como '{mode}' para bot {bot_id}")
        return True
    
    conn.close()
    return False

def update_bot_admin(bot_id, admin):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE BOTS SET admin = ? WHERE id = ?", (json.dumps(admin), bot_id))
    conn.commit()
    conn.close()

def update_bot_token(bot_id, admin):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE BOTS SET token = ? WHERE id = ?", (json.dumps(admin), bot_id))
    conn.commit()
    conn.close()

def update_bot_plans(bot_id, plans):
    print(plans)
    print(json.dumps(plans))
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE BOTS SET plans = ? WHERE id = ?", (json.dumps(plans), bot_id))
    conn.commit()
    conn.close()

def update_bot_gateway(bot_id, gateway):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE BOTS SET gateway = ? WHERE id = ?", (json.dumps(gateway), bot_id))
    conn.commit()
    conn.close()

def update_bot_users(bot_id, users):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE BOTS SET users = ? WHERE id = ?", (json.dumps(users), bot_id))
    conn.commit()
    conn.close()

def update_bot_upsell(bot_id, upsell):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE BOTS SET upsell = ? WHERE id = ?", (json.dumps(upsell), bot_id))
    conn.commit()
    conn.close()

def update_bot_expiration(bot_id, expiration):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE BOTS SET expiration = ? WHERE id = ?", (json.dumps(expiration), bot_id))
    conn.commit()
    conn.close()

def update_bot_group(bot_id, group):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE BOTS SET 'group' = ? WHERE id = ?", (group, bot_id))
    conn.commit()
    conn.close()
    
def delete_bot(bot_id):
    """Remove completamente um bot do banco de dados"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    try:
        # Remove o bot da tabela BOTS
        cursor.execute("DELETE FROM BOTS WHERE id = ?", (bot_id,))
        
        # Remove todos os pagamentos associados ao bot
        cursor.execute("DELETE FROM PAYMENTS WHERE bot = ?", (bot_id,))
        
        # Remove grupo associado
        cursor.execute("SELECT 'group' FROM BOTS WHERE id = ?", (bot_id,))
        result = cursor.fetchone()
        if result and result[0]:
            grupo = result[0]
            cursor.execute("DELETE FROM USERS WHERE grupo = ?", (grupo,))
        
        # Remove rastreamento de recuperação associado
        cursor.execute("DELETE FROM RECOVERY_TRACKING WHERE bot_id = ?", (bot_id,))
        
        conn.commit()
        conn.close()
        
        # NOVO: Limpa bots órfãos da contingência
        clean_orphan_bots_from_contingency()
        
        print(f"Bot {bot_id} removido completamente do banco de dados")
        return True
        
    except Exception as e:
        print(f"Erro ao deletar bot {bot_id}: {e}")
        conn.rollback()
        conn.close()
        return False

def get_bot_users(bot_id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT "users" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    print(result)
    if result:
        conn.close()
        return json.loads(result[0])

def get_bot_gateway(bot_id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT "gateway" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    if result:
        conn.close()
        return json.loads(result[0])





def get_bot_config(bot_id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT "config" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    if result:
        conn.close()
        return json.loads(result[0])


def get_bot_group(bot_id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT "group" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    if result:
        conn.close()
        return result[0]

def get_bot_upsell(bot_id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT "upsell" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    if result:
        conn.close()
        return json.loads(result[0])

def get_bot_plans(bot_id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT "plans" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    if result:
        conn.close()
        return json.loads(result[0])

def get_bot_expiration(bot_id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT "expiration" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    if result:
        conn.close()
        return json.loads(result[0])

# Administração

def get_bot_owner(bot_id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT "owner" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    if result:
        conn.close()
        return str(result[0])
def get_bot_admin(bot_id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT "admin" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    if result:
        conn.close()
        return json.loads(result[0])
    



def add_user_to_expiration(id_user, data_entrada, data_expiracao, plano_dict, grupo):
    # Converter o plano (dicionário) em uma string JSON
    plano_json = json.dumps(plano_dict)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    # Inserir a nova linha na tabela
    cursor.execute('''
    INSERT INTO USERS (id_user, data_entrada, data_expiracao, plano, grupo)
    VALUES (?, ?, ?, ?, ?)
    ''', (id_user, data_entrada, data_expiracao, plano_json, grupo))
    
    # Salvar as alterações e fechar
    conn.commit()


def remover_usuario(id_user, id_group):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('''
    DELETE FROM USERS 
    WHERE id_user = ? and grupo = ?
    ''', (id_user, id_group,))
    
    # Salvar as alterações
    conn.commit()

def verificar_expirados(grupo):
    data_atual = datetime.now()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT id_user, data_expiracao FROM USERS 
    WHERE grupo = ?
    ''', (grupo,))

    expirados = []
    
    for id_user, data_expiracao in cursor.fetchall():
        # Converter a data de expiração para objeto datetime
        data_expiracao_dt = datetime.strptime(data_expiracao, '%Y-%m-%d %H:%M:%S')
        
        # Verificar se o usuário está expirado
        if data_expiracao_dt < data_atual:
            print(expirados)
            expirados.append(id_user)
    
    return expirados


def get_user_expiration(id_user, grupo):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM USERS WHERE "id_user" = ? and grupo = ?', (id_user, grupo,))
    result = cursor.fetchone()
    if result and len(result) > 0:
        conn.close()
        return result[0]
    else:
        return False
    

def count_payments():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM PAYMENTS")
        count = cursor.fetchone()[0]
        
        return count
    except sqlite3.Error as e:
        print(f"Erro ao acessar o banco de dados: {e}")
        return None
    finally:
        if conn:
            conn.close()

def create_payment(chat, plano, nome_plano, bot, status='idle', trans_id='false'):
    """Cria pagamento verificando se é usuário novo"""
    # Verifica se usuário é novo hoje
    is_new_user = is_user_new_today(chat, bot)
    print(f"[CREATE_PAYMENT] User: {chat}, Is New Today: {is_new_user}")
    
    # Usa a nova função com tracking
    return create_payment_with_tracking(chat, plano, nome_plano, bot, is_new_user, status, trans_id)



def update_payment_status(id, status):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    id = str(id)
    cursor.execute("UPDATE PAYMENTS SET status = ? WHERE trans_id = ?", (status, id))
    conn.commit()
    conn.close()

def update_payment_id(id, trans):
    """Atualiza o ID da transação e registra a geração do PIX"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Atualiza o payment
    cursor.execute("""
        UPDATE PAYMENTS 
        SET trans_id = ?
        WHERE id = ?
    """, (trans, id))
    
    conn.commit()
    conn.close()
    
    # IMPORTANTE: Registra a geração do PIX
    track_pix_generation(id, trans)

def get_payment_by_trans_id(id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM PAYMENTS WHERE trans_id = ?", (id,))
    payment = cursor.fetchone()
    conn.close()
    return payment


def get_payment_by_id(id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM PAYMENTS WHERE id = ?", (id,))
    payment = cursor.fetchone()
    conn.close()
    return payment

def get_payment_plan_by_id(id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT plano FROM PAYMENTS WHERE id = ?", (id,))
    payment = cursor.fetchone()
    conn.close()
    return payment[0]


def get_payment_by_chat(id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM PAYMENTS WHERE chat = ?", (id,))
    payment = cursor.fetchone()
    conn.close()
    return payment


def get_payment_by_chat(id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM PAYMENTS WHERE chat = ?", (id,))
    payment = cursor.fetchone()
    conn.close()
    return payment

def get_payments_by_status(status, bot_id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM PAYMENTS WHERE status = ? AND bot = ?", (status, bot_id,))
    payment = cursor.fetchall()
    conn.close()
    return payment

def get_all_payments_by_status(status):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM PAYMENTS WHERE status = ?", (status,))
    payment = cursor.fetchall()
    conn.close()
    return payment

# ADICIONAR NO FINAL DO ARQUIVO manager.py

def update_bot_orderbump(bot_id, orderbump):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    # Primeiro, verifica se a coluna orderbump existe
    cursor.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'orderbump' not in columns:
        # Adiciona a coluna se não existir
        cursor.execute("ALTER TABLE BOTS ADD COLUMN orderbump TEXT DEFAULT '{}'")
        conn.commit()
    
    cursor.execute("UPDATE BOTS SET orderbump = ? WHERE id = ?", (json.dumps(orderbump), bot_id))
    conn.commit()
    conn.close()

def get_bot_orderbump(bot_id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se a coluna existe
    cursor.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'orderbump' not in columns:
        conn.close()
        return []
    
    cursor.execute('SELECT "orderbump" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    if result and result[0]:
        conn.close()
        try:
            return json.loads(result[0])
        except:
            return []
    return []

def add_orderbump_to_plan(bot_id, plan_index, orderbump_data):
    """Adiciona order bump a um plano específico"""
    orderbumps = get_bot_orderbump(bot_id)
    
    # Remove order bump anterior do mesmo plano se existir
    orderbumps = [ob for ob in orderbumps if ob.get('plano_id') != plan_index]
    
    # Adiciona o novo order bump
    orderbump_data['plano_id'] = plan_index
    orderbumps.append(orderbump_data)
    
    update_bot_orderbump(bot_id, orderbumps)

def remove_orderbump_from_plan(bot_id, plan_index):
    """Remove order bump de um plano específico"""
    orderbumps = get_bot_orderbump(bot_id)
    orderbumps = [ob for ob in orderbumps if ob.get('plano_id') != plan_index]
    update_bot_orderbump(bot_id, orderbumps)

def get_orderbump_by_plan(bot_id, plan_index):
    """Retorna o orderbump de um plano específico"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        cursor.execute("SELECT orderbump FROM BOTS WHERE id = ?", (bot_id,))
        result = cursor.fetchone()
        
        if not result or not result[0]:
            conn.close()
            return None
        
        orderbumps_data = json.loads(result[0])
        
        print(f"[ORDERBUMP DEBUG] Tipo de dados: {type(orderbumps_data)}")
        print(f"[ORDERBUMP DEBUG] Procurando orderbump para plano {plan_index}")
        
        # CORREÇÃO: Verifica se é lista ou dicionário
        if isinstance(orderbumps_data, list):
            # Se for lista (formato novo), procura pelo plano_id
            for orderbump in orderbumps_data:
                if orderbump.get('plano_id') == plan_index:
                    print(f"[ORDERBUMP DEBUG] Encontrado na lista: {orderbump}")
                    conn.close()
                    return orderbump
        elif isinstance(orderbumps_data, dict):
            # Se for dicionário (formato antigo), usa a chave
            orderbump = orderbumps_data.get(str(plan_index))
            if orderbump:
                print(f"[ORDERBUMP DEBUG] Encontrado no dict: {orderbump}")
            conn.close()
            return orderbump
        
        print(f"[ORDERBUMP DEBUG] Nenhum orderbump encontrado para plano {plan_index}")
        conn.close()
        return None
        
    except Exception as e:
        print(f"[MANAGER] Erro ao buscar orderbump do plano {plan_index}: {e}")
        import traceback
        traceback.print_exc()
        return None

def update_payment_plan(payment_id, plan):
    """Atualiza o plano de um pagamento"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("UPDATE PAYMENTS SET plano = ? WHERE id = ?", (json.dumps(plan), payment_id))
    conn.commit()
    conn.close()
    
# ADICIONAR NO FINAL DO ARQUIVO manager.py

def update_bot_downsell(bot_id, downsell):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se a coluna downsell existe
    cursor.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'downsell' not in columns:
        # Adiciona a coluna se não existir
        cursor.execute("ALTER TABLE BOTS ADD COLUMN downsell TEXT DEFAULT '{}'")
        conn.commit()
    
    cursor.execute("UPDATE BOTS SET downsell = ? WHERE id = ?", (json.dumps(downsell), bot_id))
    conn.commit()
    conn.close()

def get_bot_downsell(bot_id):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se a coluna existe
    cursor.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'downsell' not in columns:
        conn.close()
        return {}
    
    cursor.execute('SELECT "downsell" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    if result and result[0]:
        conn.close()
        try:
            return json.loads(result[0])
        except:
            return {}
    return {}

# ADICIONAR NO FINAL DO ARQUIVO manager.py

def update_bot_recovery(bot_id, recovery):
    """Atualiza as recuperações de um bot"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se a coluna recovery existe
    cursor.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'recovery' not in columns:
        # Adiciona a coluna se não existir
        cursor.execute("ALTER TABLE BOTS ADD COLUMN recovery TEXT DEFAULT '[]'")
        conn.commit()
    
    cursor.execute("UPDATE BOTS SET recovery = ? WHERE id = ?", (json.dumps(recovery), bot_id))
    conn.commit()
    conn.close()

def get_bot_recovery(bot_id):
    """Retorna as recuperações de um bot"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se a coluna existe
    cursor.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'recovery' not in columns:
        conn.close()
        return []
    
    cursor.execute('SELECT "recovery" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    if result and result[0]:
        conn.close()
        try:
            return json.loads(result[0])
        except:
            return []
    return []

def add_recovery_to_bot(bot_id, recovery_index, recovery_data):
    """Adiciona uma recuperação específica"""
    recoveries = get_bot_recovery(bot_id)
    
    # Garante que temos uma lista de 5 elementos
    while len(recoveries) < 5:
        recoveries.append(None)
    
    # Adiciona a recuperação no índice especificado
    recoveries[recovery_index] = recovery_data
    
    update_bot_recovery(bot_id, recoveries)

def remove_recovery_from_bot(bot_id, recovery_index):
    """Remove uma recuperação específica"""
    recoveries = get_bot_recovery(bot_id)
    
    if len(recoveries) > recovery_index:
        recoveries[recovery_index] = None
        update_bot_recovery(bot_id, recoveries)

def get_recovery_by_index(bot_id, recovery_index):
    """Retorna uma recuperação específica por índice"""
    recoveries = get_bot_recovery(bot_id)
    if len(recoveries) > recovery_index:
        return recoveries[recovery_index]
    return None

# Tabela para rastrear recuperações em andamento
def create_recovery_tracking_table():
    """Cria tabela para rastrear recuperações em andamento"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS RECOVERY_TRACKING (
            user_id TEXT,
            bot_id TEXT,
            start_time TEXT,
            recovery_index INTEGER,
            status TEXT,
            PRIMARY KEY (user_id, bot_id)
        )
    """)
    
    conn.commit()
    conn.close()

def start_recovery_tracking(user_id, bot_id):
    """Inicia o rastreamento de recuperação para um usuário"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se já existe um rastreamento ativo
    cursor.execute("""
        SELECT * FROM RECOVERY_TRACKING 
        WHERE user_id = ? AND bot_id = ? AND status = 'active'
    """, (user_id, bot_id))
    
    existing = cursor.fetchone()
    
    if existing:
        # Já existe rastreamento ativo, não faz nada
        conn.close()
        return False
    
    # Remove rastreamentos antigos inativos
    cursor.execute("""
        DELETE FROM RECOVERY_TRACKING 
        WHERE user_id = ? AND bot_id = ? AND status != 'active'
    """, (user_id, bot_id))
    
    # Insere novo rastreamento
    cursor.execute("""
        INSERT INTO RECOVERY_TRACKING (user_id, bot_id, start_time, recovery_index, status)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, bot_id, datetime.now().isoformat(), -1, 'active'))
    
    conn.commit()
    conn.close()
    return True

def stop_recovery_tracking(user_id, bot_id):
    """Para o rastreamento de recuperação (quando compra ou cancela)"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("UPDATE RECOVERY_TRACKING SET status = 'completed' WHERE user_id = ? AND bot_id = ?", (user_id, bot_id))
    
    conn.commit()
    conn.close()

def get_recovery_tracking(user_id, bot_id):
    """Retorna o status de rastreamento de recuperação"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM RECOVERY_TRACKING WHERE user_id = ? AND bot_id = ? AND status = 'active'", (user_id, bot_id))
    result = cursor.fetchone()
    
    conn.close()
    return result

def update_recovery_tracking_index(user_id, bot_id, recovery_index):
    """Atualiza o índice da última recuperação enviada"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE RECOVERY_TRACKING 
        SET recovery_index = ? 
        WHERE user_id = ? AND bot_id = ? AND status = 'active'
    """, (recovery_index, user_id, bot_id))
    
    conn.commit()
    conn.close()
    
def update_bot_scheduled_broadcasts(bot_id, broadcasts):
    """Atualiza os disparos programados de um bot"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se a coluna scheduled_broadcasts existe
    cursor.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'scheduled_broadcasts' not in columns:
        # Adiciona a coluna se não existir
        cursor.execute("ALTER TABLE BOTS ADD COLUMN scheduled_broadcasts TEXT DEFAULT '[]'")
        conn.commit()
    
    cursor.execute("UPDATE BOTS SET scheduled_broadcasts = ? WHERE id = ?", (json.dumps(broadcasts), bot_id))
    conn.commit()
    conn.close()

def get_bot_scheduled_broadcasts(bot_id):
    """Retorna os disparos programados de um bot"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se a coluna existe
    cursor.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'scheduled_broadcasts' not in columns:
        conn.close()
        return []
    
    cursor.execute('SELECT "scheduled_broadcasts" FROM BOTS WHERE "id" = ?', (bot_id,))
    result = cursor.fetchone()
    if result and result[0]:
        conn.close()
        try:
            return json.loads(result[0])
        except:
            return []
    return []

def add_scheduled_broadcast(bot_id, broadcast_data):
    """Adiciona um disparo programado"""
    broadcasts = get_bot_scheduled_broadcasts(bot_id)
    
    # Limita a 3 disparos
    if len(broadcasts) >= 3:
        return False
    
    # Adiciona ID único ao broadcast
    broadcast_data['id'] = len(broadcasts)
    broadcasts.append(broadcast_data)
    
    update_bot_scheduled_broadcasts(bot_id, broadcasts)
    return True

def remove_scheduled_broadcast(bot_id, broadcast_id):
    """Remove um disparo programado específico"""
    broadcasts = get_bot_scheduled_broadcasts(bot_id)
    
    # Filtra removendo o broadcast com o ID especificado
    broadcasts = [b for b in broadcasts if b.get('id') != broadcast_id]
    
    # Reindexar IDs
    for i, broadcast in enumerate(broadcasts):
        broadcast['id'] = i
    
    update_bot_scheduled_broadcasts(bot_id, broadcasts)

def get_all_bots_with_scheduled_broadcasts():
    """Retorna todos os bots que têm disparos programados"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se a coluna existe
    cursor.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'scheduled_broadcasts' not in columns:
        conn.close()
        return []
    
    cursor.execute("""
        SELECT id, token, scheduled_broadcasts 
        FROM BOTS 
        WHERE scheduled_broadcasts != '[]' 
        AND scheduled_broadcasts IS NOT NULL
    """)
    
    results = cursor.fetchall()
    conn.close()
    
    bots_with_broadcasts = []
    for bot_id, token, broadcasts_json in results:
        try:
            broadcasts = json.loads(broadcasts_json)
            if broadcasts:  # Se tem broadcasts configurados
                bots_with_broadcasts.append({
                    'bot_id': bot_id,
                    'token': token,
                    'broadcasts': broadcasts
                })
        except:
            pass
    
    return bots_with_broadcasts

def update_bot_last_activity(bot_id):
    """Atualiza a última atividade do bot (quando recebe /start)"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se a coluna existe
    cursor.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'last_activity' not in columns:
        # Adiciona a coluna se não existir
        cursor.execute("ALTER TABLE BOTS ADD COLUMN last_activity TEXT DEFAULT NULL")
        conn.commit()
    
    # Atualiza com timestamp atual
    cursor.execute("UPDATE BOTS SET last_activity = ? WHERE id = ?", 
                   (datetime.now().isoformat(), bot_id))
    conn.commit()
    conn.close()

def get_inactive_bots(minutes=21600):
    """Retorna bots inativos há mais de X minutos"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se a coluna existe
    cursor.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'last_activity' not in columns:
        conn.close()
        return []
    
    # Calcula o tempo limite
    from datetime import datetime, timedelta
    time_limit = datetime.now() - timedelta(minutes=minutes)
    
    # IMPORTANTE: Só pega bots que TÊM last_activity E é antiga
    # Ignora completamente bots com last_activity NULL
    cursor.execute("""
        SELECT id, token, owner, last_activity 
        FROM BOTS 
        WHERE last_activity IS NOT NULL 
        AND last_activity != ''
        AND last_activity < ?
    """, (time_limit.isoformat(),))
    
    inactive_bots = cursor.fetchall()
    conn.close()
    
    print(f"[get_inactive_bots] Encontrados {len(inactive_bots)} bots inativos")
    for bot in inactive_bots:
        print(f"  - Bot {bot[0]}: last_activity = {bot[3]}")
    
    return inactive_bots

def mark_all_bots_active():
    """Marca todos os bots existentes como ativos agora (para não deletar bots antigos)"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se a coluna existe
    cursor.execute("PRAGMA table_info(BOTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'last_activity' not in columns:
        cursor.execute("ALTER TABLE BOTS ADD COLUMN last_activity TEXT DEFAULT NULL")
        conn.commit()
    
    # Atualiza todos os bots sem última atividade
    cursor.execute("""
        UPDATE BOTS 
        SET last_activity = ? 
        WHERE last_activity IS NULL
    """, (datetime.now().isoformat(),))
    
    conn.commit()
    conn.close()

def get_registro_support():
    """Retorna o username do suporte configurado"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Cria tabela se não existir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS REGISTRO_CONFIG (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    cursor.execute("SELECT value FROM REGISTRO_CONFIG WHERE key = 'support_username'")
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else None

def set_registro_support(username):
    """Define o username do suporte"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Cria tabela se não existir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS REGISTRO_CONFIG (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    cursor.execute("""
        INSERT OR REPLACE INTO REGISTRO_CONFIG (key, value) 
        VALUES ('support_username', ?)
    """, (username,))
    
    conn.commit()
    conn.close()

def get_registro_owner():
    """Retorna o owner salvo do bot de registro"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS REGISTRO_CONFIG (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    cursor.execute("SELECT value FROM REGISTRO_CONFIG WHERE key = 'owner_id'")
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else None

def set_registro_owner(owner_id):
    """Define o owner do bot de registro"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS REGISTRO_CONFIG (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    cursor.execute("""
        INSERT OR REPLACE INTO REGISTRO_CONFIG (key, value) 
        VALUES ('owner_id', ?)
    """, (owner_id,))
    
    conn.commit()
    conn.close()

# FUNÇÕES PARA O SISTEMA DE STATUS - ADICIONAR NO FINAL DO ARQUIVO

# FUNÇÕES PARA O SISTEMA DE STATUS - ADICIONAR NO FINAL DO ARQUIVO

def register_user_tracking(user_id, bot_id):
    """Registra um novo usuário ou atualiza atividade"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se usuário já existe
    cursor.execute("""
        SELECT first_start FROM USER_TRACKING 
        WHERE user_id = ? AND bot_id = ?
    """, (user_id, bot_id))
    
    result = cursor.fetchone()
    
    # USA HORÁRIO DE BRASÍLIA
    from datetime import datetime
    import pytz
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(brasilia_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    if result:
        # Usuário existe - atualiza última atividade
        cursor.execute("""
            UPDATE USER_TRACKING 
            SET last_activity = ? 
            WHERE user_id = ? AND bot_id = ?
        """, (now, user_id, bot_id))
        is_new = False
    else:
        # Novo usuário - insere registro
        cursor.execute("""
            INSERT INTO USER_TRACKING (user_id, bot_id, first_start, last_activity)
            VALUES (?, ?, ?, ?)
        """, (user_id, bot_id, now, now))
        is_new = True
    
    conn.commit()
    conn.close()
    return is_new

def is_user_new_today(user_id, bot_id):
    """Verifica se usuário é novo hoje"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # USA HORÁRIO DE BRASÍLIA
    from datetime import datetime
    import pytz
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(brasilia_tz).strftime('%Y-%m-%d')
    
    cursor.execute("""
        SELECT first_start FROM USER_TRACKING 
        WHERE user_id = ? AND bot_id = ?
    """, (user_id, bot_id))
    
    result = cursor.fetchone()
    
    if result:
        # Extrai apenas a data (ignora a hora)
        first_start_date = result[0].split(' ')[0]
        is_new = (first_start_date == hoje)
        print(f"[IS_NEW_TODAY] User: {user_id}, First: {first_start_date}, Hoje: {hoje}, Is New: {is_new}")
        return is_new
    
    # Se não encontrou o usuário, considera como novo
    print(f"[IS_NEW_TODAY] User: {user_id} não encontrado no tracking")
    return True

def get_new_users_today(bot_id):
    """Conta novos usuários de hoje"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Pega a data de hoje no horário de Brasília
    from datetime import datetime
    import pytz
    
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(brasilia_tz).strftime('%Y-%m-%d')
    
    cursor.execute("""
        SELECT COUNT(*) FROM USER_TRACKING 
        WHERE bot_id = ? 
        AND DATE(first_start) = ?
    """, (bot_id, hoje))
    
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_total_users(bot_id):
    """Conta total de usuários do bot"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) FROM USER_TRACKING 
        WHERE bot_id = ?
    """, (bot_id,))
    
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_sales_today(bot_id):
    """Retorna estatísticas de vendas de hoje contando TODOS os PIX gerados"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Garante que as tabelas existem
    create_pix_generation_tracking_table()
    
    from datetime import datetime
    import pytz
    
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(brasilia_tz).strftime('%Y-%m-%d')

    print(f"[DEBUG STATUS] Buscando dados do dia: {hoje}")
    
    # Total de vendas hoje (finalizadas)
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(CAST(json_extract(plano, '$.value') AS REAL)), 0)
        FROM PAYMENTS 
        WHERE bot = ? 
        AND status = 'finished'
        AND DATE(created_at) = ?
    """, (bot_id, hoje))
    
    total_sales, total_revenue = cursor.fetchone()
    
    # Vendas de novos usuários
    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(CAST(json_extract(plano, '$.value') AS REAL)), 0)
        FROM PAYMENTS 
        WHERE bot = ? 
        AND status = 'finished'
        AND is_from_new_user = 1
        AND DATE(created_at) = ?
    """, (bot_id, hoje))
    
    new_user_sales, new_user_revenue = cursor.fetchone()
    
    # PIX gerados hoje (CONTA TODOS DA NOVA TABELA)
    cursor.execute("""
        SELECT COUNT(*)
        FROM PIX_GENERATIONS 
        WHERE bot_id = ? 
        AND DATE(generated_at) = ?
    """, (bot_id, hoje))
    
    total_pix = cursor.fetchone()[0]
    
    # PIX gerados por novos usuários
    cursor.execute("""
        SELECT COUNT(*)
        FROM PIX_GENERATIONS 
        WHERE bot_id = ? 
        AND is_new_user = 1
        AND DATE(generated_at) = ?
    """, (bot_id, hoje))
    
    new_user_pix = cursor.fetchone()[0]
    
    # Debug adicional
    cursor.execute("""
        SELECT COUNT(DISTINCT payment_id)
        FROM PIX_GENERATIONS 
        WHERE bot_id = ? 
        AND DATE(generated_at) = ?
    """, (bot_id, hoje))
    
    unique_payments = cursor.fetchone()[0]
    
    print(f"[STATUS] Total PIX gerados: {total_pix}")
    print(f"[STATUS] Pagamentos únicos: {unique_payments}")
    print(f"[STATUS] Média PIX/pagamento: {total_pix/unique_payments if unique_payments > 0 else 0:.1f}")
    
    conn.close()
    
    return {
        'total_sales': total_sales or 0,
        'total_revenue': total_revenue or 0,
        'new_user_sales': new_user_sales or 0,
        'new_user_revenue': new_user_revenue or 0,
        'total_pix': total_pix or 0,
        'new_user_pix': new_user_pix or 0
    }
    
def create_payment_with_tracking(chat, plano, nome_plano, bot, is_new_user, status='idle', trans_id='false'):
    """Cria pagamento com tracking de novo usuário E taxa aplicada"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    import uuid
    id = str(uuid.uuid4())[:8]
    
    from datetime import datetime
    import pytz
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(brasilia_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    # NOVO: Calcula e salva a taxa que será cobrada
    valor = float(plano.get('value', 0))
    tax_amount = calculate_bot_tax(bot, valor)
    
    # Pega o tipo de taxa do owner
    cursor.execute("SELECT owner FROM BOTS WHERE id = ?", (bot,))
    owner_result = cursor.fetchone()
    tax_type = 'percentage'  # default
    if owner_result:
        owner_tax = get_owner_tax_type(owner_result[0])
        tax_type = owner_tax['type']
    
    print(f"[PAYMENT] Criando pagamento - ID: {id}, User: {chat}, Bot: {bot}")
    print(f"[PAYMENT] Valor: R$ {valor}, Taxa: R$ {tax_amount:.2f} ({tax_type})")
    
    cursor.execute("""
        INSERT INTO PAYMENTS (id, trans_id, chat, plano, bot, status, created_at, is_from_new_user, tax_type, tax_value)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (id, trans_id, chat, json.dumps(plano), bot, status, now, 1 if is_new_user else 0, tax_type, tax_amount))
    
    conn.commit()
    conn.close()
    return id

def migrate_payments_tax_info():
    """Adiciona campos de taxa na tabela PAYMENTS"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Adiciona coluna tax_type se não existir
    try:
        cursor.execute("ALTER TABLE PAYMENTS ADD COLUMN tax_type TEXT DEFAULT 'percentage'")
        print("✅ Coluna tax_type adicionada")
    except:
        pass  # Coluna já existe
    
    # Adiciona coluna tax_value se não existir
    try:
        cursor.execute("ALTER TABLE PAYMENTS ADD COLUMN tax_value REAL DEFAULT 0")
        print("✅ Coluna tax_value adicionada")
    except:
        pass  # Coluna já existe
    
    conn.commit()
    conn.close()
    print("✅ Migração de tabela PAYMENTS concluída")

# Chama a migração ao importar o módulo
migrate_payments_tax_info()

# FUNÇÃO 1: Debug do user tracking
def debug_user_tracking(bot_id):
    """Debug completo do user tracking"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Mostra todos os usuários do bot
    cursor.execute("""
        SELECT user_id, first_start, last_activity 
        FROM USER_TRACKING 
        WHERE bot_id = ?
        ORDER BY first_start DESC
        LIMIT 10
    """, (bot_id,))
    
    users = cursor.fetchall()
    
    print("\n=== DEBUG USER TRACKING ===")
    print(f"Bot ID: {bot_id}")
    
    from datetime import datetime
    import pytz
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(brasilia_tz).strftime('%Y-%m-%d')
    print(f"Data de hoje (Brasília): {hoje}")
    
    for user in users:
        print(f"User: {user[0]}, First: {user[1]}, Last: {user[2]}")
    
    # Conta quantos são de hoje
    cursor.execute("""
        SELECT COUNT(*) 
        FROM USER_TRACKING 
        WHERE bot_id = ? 
        AND DATE(first_start) = ?
    """, (bot_id, hoje))
    
    hoje_count = cursor.fetchone()[0]
    print(f"\nUsuários de hoje: {hoje_count}")
    
    conn.close()

# FUNÇÃO 2: Debug dos pagamentos
def debug_payments_today(bot_id):
    """Debug para ver o que está acontecendo com os pagamentos"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica todos os pagamentos do bot
    cursor.execute("""
        SELECT id, created_at, status, is_from_new_user,
               json_extract(plano, '$.value') as value
        FROM PAYMENTS 
        WHERE bot = ?
        ORDER BY id DESC
        LIMIT 10
    """, (bot_id,))
    
    payments = cursor.fetchall()
    
    print("\n=== DEBUG PAYMENTS ===")
    print(f"Bot ID: {bot_id}")
    
    from datetime import datetime
    import pytz
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(brasilia_tz).strftime('%Y-%m-%d')
    print(f"Data de hoje: {hoje}")
    
    for p in payments:
        print(f"ID: {p[0]}, Created: {p[1]}, Status: {p[2]}, NewUser: {p[3]}, Value: {p[4]}")
    
    # Verifica quantos são de hoje
    cursor.execute("""
        SELECT COUNT(*) 
        FROM PAYMENTS 
        WHERE bot = ? 
        AND DATE(created_at) = ?
    """, (bot_id, hoje))
    
    hoje_count = cursor.fetchone()[0]
    print(f"\nPagamentos de hoje: {hoje_count}")
    
    conn.close()

# FUNÇÃO 3: Corrigir timestamp dos registros antigos
def fix_old_timestamps(bot_id):
    """Corrige timestamps antigos que possam estar com problema"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    from datetime import datetime
    import pytz
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(brasilia_tz).strftime('%Y-%m-%d %H:%M:%S')
    
    # Corrige USER_TRACKING sem timestamp
    cursor.execute("""
        UPDATE USER_TRACKING 
        SET first_start = ?, last_activity = ?
        WHERE bot_id = ? 
        AND (first_start IS NULL OR first_start = '')
    """, (hoje, hoje, bot_id))
    
    users_fixed = cursor.rowcount
    
    # Corrige PAYMENTS sem timestamp
    cursor.execute("""
        UPDATE PAYMENTS 
        SET created_at = ?
        WHERE bot = ? 
        AND (created_at IS NULL OR created_at = '')
    """, (hoje, bot_id))
    
    payments_fixed = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    if users_fixed > 0 or payments_fixed > 0:
        print(f"✅ Corrigidos: {users_fixed} usuários, {payments_fixed} pagamentos")

# ADICIONAR NO FINAL DO ARQUIVO manager.py

def create_facebook_tracking_table():
    """Cria tabela para rastrear fbclid dos usuários"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS FACEBOOK_TRACKING (
            user_id TEXT,
            bot_id TEXT,
            fbclid TEXT,
            first_click_time TEXT,
            last_updated TEXT,
            PRIMARY KEY (user_id, bot_id)
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Tabela FACEBOOK_TRACKING criada/verificada")

def save_user_fbclid(user_id, bot_id, fbclid):
    """Salva o fbclid do usuário quando ele clica no anúncio"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Garante que a tabela existe
    create_facebook_tracking_table()
    
    from datetime import datetime
    now = datetime.now().isoformat()
    
    # Insere ou atualiza o fbclid
    cursor.execute("""
        INSERT OR REPLACE INTO FACEBOOK_TRACKING 
        (user_id, bot_id, fbclid, first_click_time, last_updated)
        VALUES (?, ?, ?, 
            COALESCE((SELECT first_click_time FROM FACEBOOK_TRACKING WHERE user_id = ? AND bot_id = ?), ?),
            ?
        )
    """, (user_id, bot_id, fbclid, user_id, bot_id, now, now))
    
    conn.commit()
    conn.close()
    
    print(f"[FACEBOOK] fbclid salvo para user {user_id}: {fbclid[:20]}...")

def get_user_fbclid(user_id, bot_id):
    """Recupera o fbclid salvo do usuário"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT fbclid FROM FACEBOOK_TRACKING 
        WHERE user_id = ? AND bot_id = ?
    """, (user_id, bot_id))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return result[0]
    return None

def get_facebook_tracking_stats(bot_id):
    """Retorna estatísticas de tracking do Facebook para um bot"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Total de usuários com fbclid
    cursor.execute("""
        SELECT COUNT(*) FROM FACEBOOK_TRACKING 
        WHERE bot_id = ? AND fbclid IS NOT NULL
    """, (bot_id,))
    
    users_with_fbclid = cursor.fetchone()[0]
    
    # Total de usuários únicos do bot
    cursor.execute("""
        SELECT COUNT(*) FROM USER_TRACKING 
        WHERE bot_id = ?
    """, (bot_id,))
    
    total_users = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'users_with_fbclid': users_with_fbclid,
        'total_users': total_users,
        'coverage_rate': (users_with_fbclid / total_users * 100) if total_users > 0 else 0
    }

# ===== FUNÇÕES PARA UTM TRACKING E UTMIFY =====

def save_utm_tracking(user_id, bot_id, tracking_data):
    """Salva tracking completo com UTMs, cookies, IP e User-Agent - VERSÃO SEGURA"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Cria tabela se não existir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS UTM_TRACKING (
            user_id TEXT,
            bot_id TEXT,
            fbclid TEXT,
            utm_source TEXT,
            utm_campaign TEXT,
            utm_medium TEXT,
            utm_content TEXT,
            utm_term TEXT,
            src TEXT,
            sck TEXT,
            fbp TEXT,
            fbc TEXT,
            client_ip TEXT,
            user_agent TEXT,
            first_click_time TEXT,
            last_updated TEXT,
            PRIMARY KEY (user_id, bot_id)
        )
    """)
    
    # Garante que as colunas novas existem
    cursor.execute("PRAGMA table_info(UTM_TRACKING)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'client_ip' not in columns:
        cursor.execute("ALTER TABLE UTM_TRACKING ADD COLUMN client_ip TEXT")
    
    if 'user_agent' not in columns:
        cursor.execute("ALTER TABLE UTM_TRACKING ADD COLUMN user_agent TEXT")
    
    from datetime import datetime
    now = datetime.now().isoformat()
    
    cursor.execute("""
        INSERT OR REPLACE INTO UTM_TRACKING 
        (user_id, bot_id, fbclid, utm_source, utm_campaign, utm_medium, 
         utm_content, utm_term, src, sck, fbp, fbc, client_ip, user_agent,
         first_click_time, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            COALESCE((SELECT first_click_time FROM UTM_TRACKING WHERE user_id = ? AND bot_id = ?), ?),
            ?
        )
    """, (
        user_id, bot_id, 
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
        user_id, bot_id, now, now
    ))
    
    conn.commit()
    conn.close()
    
    print(f"[UTM_TRACKING] Dados salvos para user {user_id}")
    if tracking_data.get('client_ip'):
        print(f"  IP: {tracking_data.get('client_ip')}")
    if tracking_data.get('user_agent'):
        print(f"  User-Agent: {tracking_data.get('user_agent')[:50]}...")

def get_utm_tracking(user_id, bot_id):
    """Recupera tracking completo do usuário - VERSÃO SEGURA"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Primeiro, garante que as colunas existem
    cursor.execute("PRAGMA table_info(UTM_TRACKING)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Adiciona colunas se não existirem
    if 'client_ip' not in columns:
        cursor.execute("ALTER TABLE UTM_TRACKING ADD COLUMN client_ip TEXT")
        conn.commit()
    
    if 'user_agent' not in columns:
        cursor.execute("ALTER TABLE UTM_TRACKING ADD COLUMN user_agent TEXT")
        conn.commit()
    
    # Agora busca com segurança
    cursor.execute("""
        SELECT fbclid, utm_source, utm_campaign, utm_medium, 
               utm_content, utm_term, src, sck, fbp, fbc, client_ip, user_agent
        FROM UTM_TRACKING 
        WHERE user_id = ? AND bot_id = ?
    """, (user_id, bot_id))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
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
            'client_ip': result[10],
            'user_agent': result[11]
        }
    return None

def save_utmify_config(bot_id, api_token):
    """Salva configuração da Utmify para um bot"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    from datetime import datetime
    now = datetime.now().isoformat()
    
    cursor.execute("""
        INSERT OR REPLACE INTO UTMIFY_CONFIG 
        (bot_id, api_token, enabled, created_at, updated_at)
        VALUES (?, ?, 1, 
            COALESCE((SELECT created_at FROM UTMIFY_CONFIG WHERE bot_id = ?), ?),
            ?
        )
    """, (bot_id, api_token, bot_id, now, now))
    
    conn.commit()
    conn.close()
    
    print(f"[UTMIFY] Config salva para bot {bot_id}")

def get_utmify_config(bot_id):
    """Recupera configuração da Utmify de um bot"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT api_token, enabled 
        FROM UTMIFY_CONFIG 
        WHERE bot_id = ?
    """, (bot_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'api_token': result[0],
            'enabled': result[1] == 1
        }
    return None

def remove_utmify_config(bot_id):
    """Remove configuração da Utmify"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM UTMIFY_CONFIG WHERE bot_id = ?", (bot_id,))
    
    conn.commit()
    conn.close()


# Adicionar no final do arquivo manager.py

def save_facebook_config(bot_id, config):
    """Salva configuração do Facebook Pixel para um bot"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Cria tabela se não existir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS FACEBOOK_CONFIG (
            bot_id TEXT PRIMARY KEY,
            pixel_id TEXT,
            access_token TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    
    from datetime import datetime
    now = datetime.now().isoformat()
    
    cursor.execute("""
        INSERT OR REPLACE INTO FACEBOOK_CONFIG 
        (bot_id, pixel_id, access_token, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, 
            COALESCE((SELECT created_at FROM FACEBOOK_CONFIG WHERE bot_id = ?), ?),
            ?
        )
    """, (bot_id, config['pixel_id'], config['access_token'], 
          1 if config.get('enabled', True) else 0,
          bot_id, now, now))
    
    conn.commit()
    conn.close()
    
    print(f"[FACEBOOK] Config salva para bot {bot_id}")

def get_facebook_config(bot_id):
    """Recupera configuração do Facebook Pixel de um bot"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # PRIMEIRO: Cria a tabela se não existir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS FACEBOOK_CONFIG (
            bot_id TEXT PRIMARY KEY,
            pixel_id TEXT,
            access_token TEXT,
            enabled INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    
    # DEPOIS: Busca a configuração
    cursor.execute("""
        SELECT pixel_id, access_token, enabled 
        FROM FACEBOOK_CONFIG 
        WHERE bot_id = ?
    """, (bot_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'pixel_id': result[0],
            'access_token': result[1],
            'enabled': result[2] == 1
        }
    return None

def remove_facebook_config(bot_id):
    """Remove configuração do Facebook Pixel"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM FACEBOOK_CONFIG WHERE bot_id = ?", (bot_id,))
    
    conn.commit()
    conn.close()

def get_bot_revenue_stats(bot_id, period='today'):
    """
    Retorna estatísticas de faturamento usando as taxas salvas em cada venda
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cur = conn.cursor()
    
    from datetime import datetime, timedelta
    import pytz
    
    brasilia_tz = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(brasilia_tz)
    
    # Define os períodos (mantém igual)
    if period == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif period == 'yesterday':
        yesterday = now - timedelta(days=1)
        start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == 'this_week':
        days_since_monday = now.weekday()
        start_date = now - timedelta(days=days_since_monday)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif period == 'last_week':
        days_since_monday = now.weekday()
        start_date = now - timedelta(days=days_since_monday + 7)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)
    elif period == 'this_month':
        start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    elif period == 'last_month':
        first_day_current = now.replace(day=1)
        last_day_previous = first_day_current - timedelta(days=1)
        start_date = last_day_previous.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = last_day_previous.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:  # total (últimos 3 meses)
        start_date = now - timedelta(days=90)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now
    
    start_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
    end_str = end_date.strftime('%Y-%m-%d %H:%M:%S')
    
    # NOVO: Query direta para pegar vendas com taxas salvas
    cur.execute("""
        SELECT plano, tax_value, created_at
        FROM PAYMENTS
        WHERE bot = ? 
        AND status = 'finished'
        AND created_at BETWEEN ? AND ?
    """, (bot_id, start_str, end_str))
    
    payments = cur.fetchall()
    
    # Calcula totais
    total_revenue = 0
    total_ngk_fee = 0
    num_sales = 0
    
    for payment in payments:
        try:
            plan_json = payment[0]
            tax_value = payment[1] if payment[1] else 0  # Taxa salva
            
            plan_data = json.loads(plan_json)
            value = float(plan_data.get('value', 0))
            
            total_revenue += value
            
            # IMPORTANTE: Usa a taxa salva, não recalcula!
            if tax_value and tax_value > 0:
                total_ngk_fee += float(tax_value)
            else:
                # Fallback para vendas antigas sem taxa salva (calcula com taxa atual)
                tax = calculate_bot_tax(bot_id, value)
                total_ngk_fee += tax
            
            num_sales += 1
            
        except Exception as e:
            print(f"Erro ao processar pagamento: {e}")
    
    conn.close()
    
    # Calcula ticket médio
    avg_ticket = total_revenue / num_sales if num_sales > 0 else 0
    
    # Pega configuração atual (só para exibição)
    owner_tax = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cur = conn.cursor()
        cur.execute("SELECT owner FROM BOTS WHERE id = ?", (bot_id,))
        owner_result = cur.fetchone()
        if owner_result:
            owner_tax = get_owner_tax_type(owner_result[0])
        conn.close()
    except:
        pass
    
    print(f"📊 Período: {period}")
    print(f"   Vendas: {num_sales}")
    print(f"   Total: R$ {total_revenue:.2f}")
    print(f"   Taxa total (real): R$ {total_ngk_fee:.2f}")
    
    return {
        'total_revenue': total_revenue,
        'ngk_fee': total_ngk_fee,
        'num_sales': num_sales,
        'avg_ticket': avg_ticket,
        'period': period,
        'tax_type': owner_tax['type'] if owner_tax else 'percentage',
        'tax_config': owner_tax if owner_tax else None
    }

def clean_old_payment_data():
    """
    Remove dados de pagamento com mais de 3 meses
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cur = conn.cursor()
    
    from datetime import datetime, timedelta
    three_months_ago = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')
    
    cur.execute("""
        DELETE FROM PAYMENTS 
        WHERE created_at < ?
    """, (three_months_ago,))
    
    conn.commit()
    conn.close()

def set_bot_tax(bot_id, tax_percentage):
    """Define taxa personalizada para um bot específico"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Cria tabela se não existir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS BOT_TAX (
            bot_id TEXT PRIMARY KEY,
            tax_percentage REAL,
            updated_at TEXT
        )
    """)
    
    from datetime import datetime
    cursor.execute("""
        INSERT OR REPLACE INTO BOT_TAX (bot_id, tax_percentage, updated_at)
        VALUES (?, ?, ?)
    """, (bot_id, tax_percentage, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    print(f"[TAX] Taxa do bot {bot_id} atualizada para {tax_percentage}%")

def get_bot_tax(bot_id):
    """Retorna a taxa do bot ou a taxa global se não houver"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Verifica se a tabela existe
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='BOT_TAX'
    """)
    
    if not cursor.fetchone():
        # Tabela não existe, retorna taxa padrão
        conn.close()
        with open('config.json', 'r') as f:
            config = json.loads(f.read())
        return float(config.get('tax', 1))
    
    # Busca taxa específica do bot
    cursor.execute("""
        SELECT tax_percentage FROM BOT_TAX 
        WHERE bot_id = ?
    """, (bot_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return float(result[0])
    
    # Retorna taxa global do config se não houver específica
    with open('config.json', 'r') as f:
        config = json.loads(f.read())
    return float(config.get('tax', 1))

def get_all_orderbumps(bot_id):
    """Retorna todos os orderbumps configurados de um bot com grupos"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        # Busca o bot
        cursor.execute("SELECT * FROM BOTS WHERE id = ?", (bot_id,))
        bot = cursor.fetchone()
        
        if not bot:
            conn.close()
            return []
        
        # Pega a coluna ORDERBUMP (deve ser índice 11 baseado na estrutura)
        orderbumps_data = bot[11]  # Ajuste este índice se necessário
        
        if not orderbumps_data or orderbumps_data == '{}':
            conn.close()
            return []
        
        # Parse do JSON
        orderbumps = json.loads(orderbumps_data)
        
        # Lista para retornar
        orderbumps_list = []
        
        # Itera sobre cada plano que tem orderbump
        for plan_index, orderbump in orderbumps.items():
            if orderbump and isinstance(orderbump, dict):
                # Verifica se tem grupo configurado
                if orderbump.get('group_id'):
                    orderbumps_list.append({
                        'plan_index': plan_index,
                        'group_id': orderbump['group_id'],
                        'group_name': orderbump.get('group_name', f'OrderBump Plano {int(plan_index) + 1}'),
                        'value': orderbump.get('value', 0),
                        'text': orderbump.get('text', ''),
                        'media': orderbump.get('media')
                    })
        
        conn.close()
        return orderbumps_list
        
    except Exception as e:
        print(f"[MANAGER] Erro ao buscar orderbumps: {e}")
        return []

def create_contingency_tables():
    """Cria tabelas para o sistema de contingência"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Tabela de grupos de contingência
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS CONTINGENCY_GROUPS (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            name TEXT NOT NULL,
            unique_code TEXT UNIQUE NOT NULL,
            total_clicks INTEGER DEFAULT 0,
            current_bot_index INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            is_active INTEGER DEFAULT 1,
            distribution_enabled INTEGER DEFAULT 0,
            last_distributed_index INTEGER DEFAULT 0,
            emergency_link TEXT DEFAULT NULL
        )
    """)
    
    # Tabela de bots em cada grupo
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS CONTINGENCY_BOTS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL,
            bot_id TEXT NOT NULL,
            bot_token TEXT NOT NULL,
            position INTEGER NOT NULL,
            is_online INTEGER DEFAULT 1,
            last_check TEXT,
            marked_offline_at TEXT,
            FOREIGN KEY (group_id) REFERENCES CONTINGENCY_GROUPS(id) ON DELETE CASCADE,
            UNIQUE(group_id, bot_id)
        )
    """)
    
    # Índices para performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_contingency_code 
        ON CONTINGENCY_GROUPS(unique_code)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_contingency_owner 
        ON CONTINGENCY_GROUPS(owner_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_contingency_bot_group 
        ON CONTINGENCY_BOTS(group_id, position)
    """)
    
    # Adiciona colunas para distribuição de tráfego (se não existirem)
    try:
        cursor.execute("""
            ALTER TABLE CONTINGENCY_GROUPS 
            ADD COLUMN distribution_enabled INTEGER DEFAULT 0
        """)
        print("✅ Coluna distribution_enabled adicionada")
    except:
        pass  # Coluna já existe
    
    try:
        cursor.execute("""
            ALTER TABLE CONTINGENCY_GROUPS 
            ADD COLUMN last_distributed_index INTEGER DEFAULT 0
        """)
        print("✅ Coluna last_distributed_index adicionada")
    except:
        pass  # Coluna já existe
    
    # Adiciona campo para link emergencial
    try:
        cursor.execute("""
            ALTER TABLE CONTINGENCY_GROUPS 
            ADD COLUMN emergency_link TEXT DEFAULT NULL
        """)
        print("✅ Coluna emergency_link adicionada")
    except:
        pass  # Coluna já existe
    
    conn.commit()
    conn.close()
    print("✅ Tabelas de contingência criadas/verificadas")

def generate_contingency_code():
    """Gera código único para grupo de contingência"""
    import random
    import string
    
    # Formato: 3 letras + 5 números (ex: ABC12345)
    letters = ''.join(random.choices(string.ascii_uppercase, k=3))
    numbers = ''.join(random.choices(string.digits, k=5))
    return f"{letters}{numbers}"

def create_contingency_group(owner_id, name, bot_ids):
    """Cria um novo grupo de contingência"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    try:
        import uuid
        from datetime import datetime
        
        group_id = str(uuid.uuid4())
        unique_code = generate_contingency_code()
        
        # Verifica se código já existe
        while True:
            cursor.execute("SELECT 1 FROM CONTINGENCY_GROUPS WHERE unique_code = ?", (unique_code,))
            if not cursor.fetchone():
                break
            unique_code = generate_contingency_code()
        
        # Cria o grupo
        cursor.execute("""
            INSERT INTO CONTINGENCY_GROUPS 
            (id, owner_id, name, unique_code, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (group_id, owner_id, name, unique_code, datetime.now().isoformat()))
        
        # Adiciona os bots ao grupo
        for position, bot_id in enumerate(bot_ids):
            # Busca o token do bot
            cursor.execute("SELECT token FROM BOTS WHERE id = ?", (bot_id,))
            result = cursor.fetchone()
            if result:
                bot_token = result[0]
                cursor.execute("""
                    INSERT INTO CONTINGENCY_BOTS 
                    (group_id, bot_id, bot_token, position)
                    VALUES (?, ?, ?, ?)
                """, (group_id, bot_id, bot_token, position))
        
        conn.commit()
        conn.close()
        
        return {
            'success': True,
            'group_id': group_id,
            'unique_code': unique_code
        }
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[CONTINGENCY] Erro ao criar grupo: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def get_user_contingency_groups(owner_id):
    """Retorna todos os grupos de contingência de um usuário"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            cg.id,
            cg.name,
            cg.unique_code,
            cg.total_clicks,
            cg.current_bot_index,
            cg.created_at,
            (SELECT COUNT(*) FROM CONTINGENCY_BOTS WHERE group_id = cg.id) as total_bots,
            (SELECT COUNT(*) FROM CONTINGENCY_BOTS cb2 WHERE cb2.group_id = cg.id AND cb2.is_online = 1) as bots_online
        FROM CONTINGENCY_GROUPS cg
        WHERE cg.owner_id = ? AND cg.is_active = 1
        ORDER BY cg.created_at DESC
    """, (owner_id,))
    
    groups = []
    for row in cursor.fetchall():
        groups.append({
            'id': row[0],
            'name': row[1],
            'unique_code': row[2],
            'total_clicks': row[3],
            'current_bot_index': row[4],
            'created_at': row[5],
            'total_bots': row[6],
            'bots_online': row[7]
        })
    
    conn.close()
    return groups

def get_contingency_group_details(group_id):
    """Retorna detalhes completos de um grupo de contingência"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM CONTINGENCY_GROUPS 
        WHERE id = ?
    """, (group_id,))
    
    group_data = cursor.fetchone()
    if not group_data:
        conn.close()
        return None
    
    cursor.execute("""
        SELECT 
            cb.bot_id,
            cb.position,
            cb.is_online,
            cb.marked_offline_at,
            b.token
        FROM CONTINGENCY_BOTS cb
        JOIN BOTS b ON cb.bot_id = b.id
        WHERE cb.group_id = ?
        ORDER BY cb.position
    """, (group_id,))
    
    bots = []
    for row in cursor.fetchall():
        bot_details = check_bot_token(row[4])
        bot_username = bot_details['result'].get('username', 'INDEFINIDO') if bot_details else 'INDEFINIDO'
        
        bots.append({
            'bot_id': row[0],
            'position': row[1],
            'is_online': row[2] == 1,
            'marked_offline_at': row[3],
            'username': bot_username
        })
    
    conn.close()
    
    # CORREÇÃO: Mapeia corretamente todos os campos
    return {
        'id': group_data[0],
        'owner_id': group_data[1],
        'name': group_data[2],
        'unique_code': group_data[3],
        'total_clicks': group_data[4],
        'current_bot_index': group_data[5],
        'created_at': group_data[6],
        'updated_at': group_data[7],
        'is_active': group_data[8] == 1,
        'distribution_enabled': group_data[9] == 1 if len(group_data) > 9 else False,
        'last_distributed_index': group_data[10] if len(group_data) > 10 else 0,
        'emergency_link': group_data[11] if len(group_data) > 11 else None,  # CORREÇÃO AQUI
        'bots': bots
    }

def delete_contingency_group(group_id, owner_id):
    """Deleta um grupo de contingência"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    try:
        # Verifica se o grupo pertence ao owner
        cursor.execute("""
            SELECT owner_id FROM CONTINGENCY_GROUPS 
            WHERE id = ? AND is_active = 1
        """, (group_id,))
        
        result = cursor.fetchone()
        if not result or result[0] != owner_id:
            conn.close()
            return False
        
        # Marca como inativo ao invés de deletar (para preservar histórico)
        cursor.execute("""
            UPDATE CONTINGENCY_GROUPS 
            SET is_active = 0, updated_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), group_id))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[CONTINGENCY] Erro ao deletar grupo: {e}")
        return False

def clean_orphan_bots_from_contingency():
    """Remove referências de bots que não existem mais no sistema"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    try:
        # Remove bots da contingência que não existem mais na tabela BOTS
        cursor.execute("""
            DELETE FROM CONTINGENCY_BOTS 
            WHERE bot_id NOT IN (SELECT id FROM BOTS)
        """)
        
        deleted_count = cursor.rowcount
        
        if deleted_count > 0:
            print(f"[CONTINGENCY] Removidas {deleted_count} referências órfãs")
            
            # Agora verifica grupos que ficaram com menos de 2 bots
            cursor.execute("""
                SELECT group_id, COUNT(*) as bot_count 
                FROM CONTINGENCY_BOTS 
                GROUP BY group_id 
                HAVING bot_count < 2
            """)
            
            groups_to_deactivate = cursor.fetchall()
            
            for group_id, bot_count in groups_to_deactivate:
                cursor.execute("""
                    UPDATE CONTINGENCY_GROUPS 
                    SET is_active = 0 
                    WHERE id = ?
                """, (group_id,))
                print(f"[CONTINGENCY] Grupo {group_id} desativado - apenas {bot_count} bot(s)")
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        print(f"[CONTINGENCY] Erro ao limpar bots órfãos: {e}")
    finally:
        conn.close()

def add_bot_to_contingency_group(group_id, bot_id):
    """Adiciona um bot a um grupo existente"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    try:
        # Primeiro verifica se o bot já está no grupo
        cursor.execute("""
            SELECT 1 FROM CONTINGENCY_BOTS 
            WHERE group_id = ? AND bot_id = ?
        """, (group_id, str(bot_id)))
        
        if cursor.fetchone():
            conn.close()
            print(f"[CONTINGENCY] Bot {bot_id} já está no grupo {group_id}")
            return False
        
        # Busca a maior posição atual
        cursor.execute("""
            SELECT MAX(position) FROM CONTINGENCY_BOTS 
            WHERE group_id = ?
        """, (group_id,))
        
        max_position = cursor.fetchone()[0]
        new_position = (max_position + 1) if max_position is not None else 0
        
        # Busca token do bot
        cursor.execute("SELECT token FROM BOTS WHERE id = ?", (str(bot_id),))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False
        
        bot_token = result[0]
        
        # Adiciona o bot
        cursor.execute("""
            INSERT INTO CONTINGENCY_BOTS 
            (group_id, bot_id, bot_token, position)
            VALUES (?, ?, ?, ?)
        """, (group_id, str(bot_id), bot_token, new_position))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[CONTINGENCY] Erro ao adicionar bot: {e}")
        return False

def remove_bot_from_contingency_group(group_id, bot_id):
    """Remove um bot de um grupo"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    try:
        # Remove o bot
        cursor.execute("""
            DELETE FROM CONTINGENCY_BOTS 
            WHERE group_id = ? AND bot_id = ?
        """, (group_id, bot_id))
        
        # Reordena as posições
        cursor.execute("""
            SELECT bot_id FROM CONTINGENCY_BOTS 
            WHERE group_id = ? 
            ORDER BY position
        """, (group_id,))
        
        bots = cursor.fetchall()
        for i, (bot,) in enumerate(bots):
            cursor.execute("""
                UPDATE CONTINGENCY_BOTS 
                SET position = ? 
                WHERE group_id = ? AND bot_id = ?
            """, (i, group_id, bot))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[CONTINGENCY] Erro ao remover bot: {e}")
        return False

def reactivate_offline_bot(group_id, bot_id):
    """Reativa um bot que estava offline"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE CONTINGENCY_BOTS 
            SET is_online = 1, marked_offline_at = NULL
            WHERE group_id = ? AND bot_id = ?
        """, (group_id, bot_id))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[CONTINGENCY] Erro ao reativar bot: {e}")
        return False

def toggle_distribution(group_id, enabled):
    """Ativa ou desativa distribuição de tráfego para um grupo"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE CONTINGENCY_GROUPS 
            SET distribution_enabled = ?
            WHERE id = ?
        """, (1 if enabled else 0, group_id))
        
        conn.commit()
        conn.close()
        print(f"[DISTRIBUTION] Grupo {group_id} - Distribuição {'ativada' if enabled else 'desativada'}")
        return True
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[DISTRIBUTION] Erro ao alterar distribuição: {e}")
        return False

def set_emergency_link(group_id, emergency_link):
    """Define ou remove o link emergencial do grupo"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    try:
        # Se o link for vazio, define como NULL
        link_to_save = emergency_link if emergency_link else None
        
        cursor.execute("""
            UPDATE CONTINGENCY_GROUPS 
            SET emergency_link = ?
            WHERE id = ?
        """, (link_to_save, group_id))
        
        conn.commit()
        conn.close()
        print(f"[EMERGENCY] Grupo {group_id} - Link emergencial: {link_to_save if link_to_save else 'removido'}")
        return True
        
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[EMERGENCY] Erro ao definir link emergencial: {e}")
        return False

def get_next_distribution_bot(group_id):
    """Retorna o próximo bot para distribuição round-robin"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    try:
        # Busca configuração do grupo
        cursor.execute("""
            SELECT distribution_enabled, last_distributed_index 
            FROM CONTINGENCY_GROUPS 
            WHERE id = ?
        """, (group_id,))
        
        result = cursor.fetchone()
        if not result or result[0] != 1:
            conn.close()
            return None  # Distribuição não ativada
        
        last_index = result[1] or 0
        
        # Busca todos os bots ONLINE do grupo
        cursor.execute("""
            SELECT bot_id, bot_token, position 
            FROM CONTINGENCY_BOTS 
            WHERE group_id = ? AND is_online = 1
            ORDER BY position
        """, (group_id,))
        
        online_bots = cursor.fetchall()
        
        if not online_bots:
            conn.close()
            return None
        
        # Calcula próximo índice
        next_index = (last_index + 1) % len(online_bots)
        
        # Atualiza último índice usado
        cursor.execute("""
            UPDATE CONTINGENCY_GROUPS 
            SET last_distributed_index = ?
            WHERE id = ?
        """, (next_index, group_id))
        
        conn.commit()
        conn.close()
        
        # Retorna o bot selecionado
        return {
            'bot_id': online_bots[next_index][0],
            'bot_token': online_bots[next_index][1],
            'position': online_bots[next_index][2]
        }
        
    except Exception as e:
        conn.close()
        print(f"[DISTRIBUTION] Erro ao obter próximo bot: {e}")
        return None

def save_admin_message_log(bot_id, bot_token, owner_id, message, status='sent'):
    """Salva log de mensagens enviadas pelo admin para bots"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Cria tabela se não existir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ADMIN_MESSAGE_LOG (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id TEXT,
            bot_token TEXT,
            owner_id TEXT,
            message TEXT,
            status TEXT,
            sent_at TEXT,
            sent_by TEXT
        )
    """)
    
    from datetime import datetime
    cursor.execute("""
        INSERT INTO ADMIN_MESSAGE_LOG 
        (bot_id, bot_token, owner_id, message, status, sent_at, sent_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (bot_id, bot_token[:20], owner_id, message, status, 
          datetime.now().isoformat(), 'admin'))
    
    conn.commit()
    conn.close()
    print(f"[ADMIN MSG] Log salvo - Bot: {bot_id}, Owner: {owner_id}")

def get_admin_message_history(bot_id=None, limit=50):
    """Recupera histórico de mensagens enviadas pelo admin"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    if bot_id:
        cursor.execute("""
            SELECT * FROM ADMIN_MESSAGE_LOG 
            WHERE bot_id = ? 
            ORDER BY id DESC 
            LIMIT ?
        """, (bot_id, limit))
    else:
        cursor.execute("""
            SELECT * FROM ADMIN_MESSAGE_LOG 
            ORDER BY id DESC 
            LIMIT ?
        """, (limit,))
    
    history = cursor.fetchall()
    conn.close()
    return history

def get_owner_tax_type(owner_id):
    """Retorna o tipo de taxa do owner (fixed ou percentage)"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Cria tabela se não existir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS OWNER_TAX_CONFIG (
            owner_id TEXT PRIMARY KEY,
            tax_type TEXT DEFAULT 'percentage',
            fixed_value REAL DEFAULT 0.75,
            percentage_value REAL DEFAULT 3.5,
            updated_at TEXT
        )
    """)
    conn.commit()
    
    # Busca configuração do owner
    cursor.execute("""
        SELECT tax_type, fixed_value, percentage_value 
        FROM OWNER_TAX_CONFIG 
        WHERE owner_id = ?
    """, (str(owner_id),))
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return {
            'type': result[0],
            'fixed_value': result[1],
            'percentage_value': result[2]
        }
    
    # Retorna padrão se não existir
    return {
        'type': 'percentage',
        'fixed_value': 0.75,
        'percentage_value': 3.5
    }

def set_owner_tax_type(owner_id, tax_type, custom_value=None):
    """Define o tipo de taxa E o valor personalizado para todos os bots do owner"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Cria tabela se não existir
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS OWNER_TAX_CONFIG (
            owner_id TEXT PRIMARY KEY,
            tax_type TEXT DEFAULT 'percentage',
            fixed_value REAL DEFAULT 0.75,
            percentage_value REAL DEFAULT 3.5,
            updated_at TEXT
        )
    """)
    
    from datetime import datetime
    
    # Se passou um valor customizado, atualiza o campo correto
    if custom_value is not None:
        if tax_type == 'fixed':
            cursor.execute("""
                INSERT OR REPLACE INTO OWNER_TAX_CONFIG 
                (owner_id, tax_type, fixed_value, updated_at)
                VALUES (?, ?, ?, ?)
            """, (str(owner_id), tax_type, custom_value, datetime.now().isoformat()))
        else:
            cursor.execute("""
                INSERT OR REPLACE INTO OWNER_TAX_CONFIG 
                (owner_id, tax_type, percentage_value, updated_at)
                VALUES (?, ?, ?, ?)
            """, (str(owner_id), tax_type, custom_value, datetime.now().isoformat()))
    else:
        # Só muda o tipo, mantém os valores atuais
        cursor.execute("""
            INSERT OR REPLACE INTO OWNER_TAX_CONFIG 
            (owner_id, tax_type, updated_at)
            VALUES (?, ?, ?)
        """, (str(owner_id), tax_type, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    print(f"[TAX CONFIG] Owner {owner_id} - Tipo: {tax_type}, Valor: {custom_value}")
    return True

# Adicionar esta função no manager.py
def delete_bot_by_owner(bot_id, owner_id):
    """Remove um bot do banco de dados, mas só se pertencer ao owner especificado"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    try:
        # Primeiro verifica se o bot pertence ao owner
        cursor.execute("SELECT owner FROM BOTS WHERE id = ?", (bot_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return {'success': False, 'message': 'Bot não encontrado'}
        
        if result[0] != str(owner_id):
            conn.close()
            return {'success': False, 'message': 'Você não é o dono deste bot'}
        
        # Remove o bot da tabela BOTS
        cursor.execute("DELETE FROM BOTS WHERE id = ?", (bot_id,))
        
        # Remove todos os pagamentos associados
        cursor.execute("DELETE FROM PAYMENTS WHERE bot = ?", (bot_id,))
        
        # Remove grupo associado
        cursor.execute("SELECT 'group' FROM BOTS WHERE id = ?", (bot_id,))
        group_result = cursor.fetchone()
        if group_result and group_result[0]:
            grupo = group_result[0]
            cursor.execute("DELETE FROM USERS WHERE grupo = ?", (grupo,))
        
        # Remove tracking de recuperação
        cursor.execute("DELETE FROM RECOVERY_TRACKING WHERE bot_id = ?", (bot_id,))
        
        conn.commit()
        conn.close()
        
        # NOVO: Limpa bots órfãos da contingência
        clean_orphan_bots_from_contingency()
        
        print(f"Bot {bot_id} deletado pelo owner {owner_id}")
        return {'success': True, 'message': 'Bot deletado com sucesso'}
        
    except Exception as e:
        print(f"Erro ao deletar bot {bot_id}: {e}")
        conn.rollback()
        conn.close()
        return {'success': False, 'message': f'Erro ao deletar: {str(e)}'}

def ensure_pix_generated_at_column():
    """Garante que a coluna pix_generated_at existe na tabela PAYMENTS"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Primeiro garante que a tabela existe
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS PAYMENTS (
            id TEXT PRIMARY KEY,
            trans_id TEXT,
            chat TEXT,
            plano TEXT,
            bot TEXT,
            status TEXT,
            created_at TEXT,
            is_from_new_user INTEGER DEFAULT 0,
            tax_type TEXT DEFAULT 'percentage',
            tax_value REAL DEFAULT 0,
            pix_generated_at TEXT DEFAULT NULL
        )
    """)
    
    # Verifica se a coluna pix_generated_at existe
    cursor.execute("PRAGMA table_info(PAYMENTS)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'pix_generated_at' not in columns:
        cursor.execute("ALTER TABLE PAYMENTS ADD COLUMN pix_generated_at TEXT DEFAULT NULL")
        print("✅ Coluna pix_generated_at adicionada à tabela PAYMENTS")
    
    conn.commit()
    conn.close()

def create_pix_generation_tracking_table():
    """Cria tabela para rastrear CADA geração de PIX individualmente"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS PIX_GENERATIONS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id TEXT,
            bot_id TEXT,
            user_id TEXT,
            trans_id TEXT,
            generated_at TEXT,
            is_new_user INTEGER DEFAULT 0,
            value REAL DEFAULT 0,
            has_orderbump INTEGER DEFAULT 0,
            FOREIGN KEY (payment_id) REFERENCES PAYMENTS(id)
        )
    """)
    
    # Cria índices para melhor performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pix_gen_bot 
        ON PIX_GENERATIONS(bot_id, generated_at)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pix_gen_date 
        ON PIX_GENERATIONS(DATE(generated_at))
    """)
    
    conn.commit()
    conn.close()
    print("✅ Tabela PIX_GENERATIONS criada/verificada com índices")

def track_pix_generation(payment_id, trans_id):
    """Registra CADA vez que um PIX é gerado (aceitar/recusar orderbump conta como novo)"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Garante que a tabela existe
    create_pix_generation_tracking_table()
    
    # Pega informações completas do pagamento
    cursor.execute("""
        SELECT chat, bot, plano 
        FROM PAYMENTS 
        WHERE id = ?
    """, (payment_id,))
    
    result = cursor.fetchone()
    
    if result:
        user_id, bot_id, plano_json = result
        plano = json.loads(plano_json)
        
        from datetime import datetime
        import pytz
        brasilia_tz = pytz.timezone('America/Sao_Paulo')
        now = datetime.now(brasilia_tz).strftime('%Y-%m-%d %H:%M:%S')
        
        # Verifica se é usuário novo
        is_new_user = is_user_new_today(user_id, bot_id)
        
        # Pega o valor atual do plano (pode ter mudado com orderbump)
        value = plano.get('value', 0)
        has_orderbump = 1 if plano.get('has_orderbump', False) else 0
        
        # Insere novo registro de geração de PIX
        cursor.execute("""
            INSERT INTO PIX_GENERATIONS 
            (payment_id, bot_id, user_id, trans_id, generated_at, is_new_user, value, has_orderbump)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (payment_id, bot_id, user_id, trans_id, now, 1 if is_new_user else 0, value, has_orderbump))
        
        print(f"[PIX_TRACK] Registrado: Payment {payment_id}, Trans {trans_id}, Valor R$ {value}, OrderBump: {'SIM' if has_orderbump else 'NÃO'}")
    else:
        print(f"[PIX_TRACK] AVISO: Payment {payment_id} não encontrado")
    
    conn.commit()
    conn.close()

def calculate_bot_tax(bot_id, valor):
    """Calcula a taxa baseada no tipo configurado para o owner do bot"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # Pega o owner do bot
    cursor.execute("SELECT owner FROM BOTS WHERE id = ?", (bot_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        # Se não encontrou o bot, usa taxa percentual padrão
        return valor * 0.035
    
    owner_id = result[0]
    conn.close()
    
    # Pega a configuração de taxa do owner
    tax_config = get_owner_tax_type(owner_id)
    
    if tax_config['type'] == 'fixed':
        # Taxa fixa
        return tax_config['fixed_value']
    else:
        # Taxa percentual
        return valor * (tax_config['percentage_value'] / 100)
