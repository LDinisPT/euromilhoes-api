#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  REPOR A CONTA NA NUVEM a partir do último backup do GitHub.
#  Correr no PC Windows (Git Bash), a partir da pasta euromilhoes-api:
#      bash conta-worker/restaurar.sh
#  (o wrangler já tem de estar com sessão iniciada — está.)
# ─────────────────────────────────────────────────────────────
set -e
cd "$(dirname "$0")/.."   # pasta euromilhoes-api

echo "→ A obter o backup mais recente do GitHub..."
git pull --quiet || true

echo "→ A validar o backup..."
py -3 -c "import json; d=json.load(open('data/conta-backup.json',encoding='utf-8')); assert isinstance(d,dict) and 'membros' in d and d.get('cells'); print('  Backup OK:', len([m for m in d['membros'] if m.strip()]),'socios,', len(d['cells']),'pagamentos')"

echo "→ A repor na nuvem..."
( cd conta-worker && wrangler kv key put --binding CONTA conta --path ../data/conta-backup.json --remote )

echo ""
echo "✔ PRONTO. Abre a app (separador Conta) e confirma que está tudo."
