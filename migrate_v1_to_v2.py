#!/usr/bin/env python3
"""
migrate_v1_to_v2.py - Script de migração do banco V1 para V2
Execução: python3 migrate_v1_to_v2.py
"""

import sqlite3
import json
import os
from datetime import datetime

# Define o caminho do banco
DB_PATH = '/app/storage/data.db' if os.path.exists('/app/storage') else 'data.db'

def migrate():
    """Executa todas as migrações necessárias"""
    print(f"🔄 Iniciando migração do banco: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Banco não encontrado em {DB_PATH}")
        return False
    
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    
    try:
        # 1. ADICIONAR COLUNAS FALTANTES
        print("\n📝 Adicionando colunas novas...")
        
        # TRACKING_MAPPING - adicionar fbp e fbc
        add_column(cursor, 'TRACKING_MAPPING', 'fbp', 'TEXT')
        add_column(cursor, 'TRACKING_MAPPING', 'fbc', 'TEXT')
        
        # UTM_TRACKING - adicionar fbp e fbc
        add_column(cursor, 'UTM_TRACKING', 'fbp', 'TEXT')
        add_column(cursor, 'UTM_TRACKING', 'fbc', 'TEXT')
        
        # BOTS - adicionar last_activity
        add_column(cursor, 'BOTS', 'last_activity', 'TEXT')
        
        # PAYMENTS - adicionar created_at e is_from_new_user
        add_column(cursor, 'PAYMENTS', 'created_at', 'TEXT')
        add_column(cursor, 'PAYMENTS', 'is_from_new_user', 'INTEGER DEFAULT 0')
        
        # 2. CRIAR TABELAS NOVAS
        print("\n📊 Criando tabelas novas...")
        
        # USER_TRACKING
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS USER_TRACKING (
                user_id TEXT,
                bot_id TEXT,
                first_start TEXT,
                last_activity TEXT,
                PRIMARY KEY (user_id, bot_id)
            )
        """)
        print("✅ Tabela USER_TRACKING criada/verificada")
        
        # RECOVERY_TRACKING
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
        print("✅ Tabela RECOVERY_TRACKING criada/verificada")
        
        # 3. CONVERTER ORDERBUMP DE DICT PARA LISTA
        print("\n🔄 Convertendo formato do OrderBump...")
        convert_orderbump(cursor)
        
        # 4. PREENCHER VALORES DEFAULT
        print("\n🔧 Preenchendo valores padrão...")
        
        # Preenche last_activity para bots existentes
        now = datetime.now().isoformat()
        cursor.execute("""
            UPDATE BOTS 
            SET last_activity = ? 
            WHERE last_activity IS NULL OR last_activity = ''
        """, (now,))
        
        # Preenche created_at para pagamentos existentes
        cursor.execute("""
            UPDATE PAYMENTS 
            SET created_at = datetime('now', 'localtime')
            WHERE created_at IS NULL OR created_at = ''
        """)
        
        # Commit todas as mudanças
        conn.commit()
        print("\n✅ Migração concluída com sucesso!")
        
        # Mostra estatísticas
        show_stats(cursor)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Erro durante migração: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()

def add_column(cursor, table, column, col_type):
    """Adiciona coluna se não existir"""
    try:
        # Verifica se coluna existe
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cursor.fetchall()]
        
        if column not in columns:
            default = " DEFAULT ''" if col_type == 'TEXT' else " DEFAULT 0"
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default}")
            print(f"  ✅ {table}.{column} adicionada")
        else:
            print(f"  ⏭️  {table}.{column} já existe")
            
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
            print(f"  ⚠️  Tabela {table} não existe (será criada depois)")
        else:
            raise

def convert_orderbump(cursor):
    """Converte orderbump de dict para lista"""
    try:
        # Verifica se coluna orderbump existe
        cursor.execute("PRAGMA table_info(BOTS)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'orderbump' not in columns:
            cursor.execute("ALTER TABLE BOTS ADD COLUMN orderbump TEXT DEFAULT '[]'")
            print("  ✅ Coluna orderbump criada")
            return
        
        # Busca todos os bots com orderbump
        cursor.execute("SELECT id, orderbump FROM BOTS WHERE orderbump IS NOT NULL")
        bots = cursor.fetchall()
        
        converted = 0
        for bot_id, orderbump_json in bots:
            if not orderbump_json or orderbump_json in ['[]', '{}', None]:
                continue
                
            try:
                data = json.loads(orderbump_json)
                
                # Se já é lista, pula
                if isinstance(data, list):
                    continue
                
                # Se é dict, converte para lista
                if isinstance(data, dict):
                    new_list = []
                    for key, value in data.items():
                        if value and isinstance(value, dict):
                            value['plano_id'] = int(key)
                            new_list.append(value)
                    
                    # Atualiza no banco
                    cursor.execute(
                        "UPDATE BOTS SET orderbump = ? WHERE id = ?",
                        (json.dumps(new_list), bot_id)
                    )
                    converted += 1
                    
            except json.JSONDecodeError:
                print(f"  ⚠️  Erro ao processar orderbump do bot {bot_id}")
                continue
        
        if converted > 0:
            print(f"  ✅ {converted} orderbumps convertidos de dict para lista")
        else:
            print(f"  ⏭️  Nenhum orderbump para converter")
            
    except Exception as e:
        print(f"  ⚠️  Erro ao converter orderbump: {e}")

def show_stats(cursor):
    """Mostra estatísticas do banco"""
    print("\n📊 Estatísticas do banco:")
    
    try:
        cursor.execute("SELECT COUNT(*) FROM BOTS")
        print(f"  • Bots: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM PAYMENTS")
        print(f"  • Pagamentos: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM USERS")
        print(f"  • Usuários: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM USER_TRACKING")
        print(f"  • User Tracking: {cursor.fetchone()[0]}")
        
    except:
        pass

if __name__ == "__main__":
    print("=" * 50)
    print("MIGRAÇÃO V1 → V2 - NGK PAY BOT")
    print("=" * 50)
    
    success = migrate()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ MIGRAÇÃO COMPLETA! Pode fazer deploy da V2.")
    else:
        print("❌ MIGRAÇÃO FALHOU! Verifique os erros acima.")
    print("=" * 50)