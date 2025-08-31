#!/usr/bin/env python3
"""
start_with_migration.py - Inicia a V2 com migração automática
"""
import os
import subprocess
import time

print("=" * 50)
print("🚀 INICIANDO NGK PAY V2")
print("=" * 50)

# Executa migração
print("\n📦 Executando migração do banco...")
try:
    subprocess.run(["python", "migrate_v1_to_v2.py"], check=True)
    print("✅ Migração concluída!")
except:
    print("⚠️ Erro na migração, continuando...")

# Aguarda 2 segundos
time.sleep(2)

# Inicia a aplicação
print("\n🎯 Iniciando aplicação...")
subprocess.run(["python", "app.py"])