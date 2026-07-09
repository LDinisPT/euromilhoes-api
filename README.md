# Euromilhões API

Histórico de sorteios do Euromilhões desde 13/02/2004, servido como JSON estático
e atualizado automaticamente pelo GitHub Actions (2×/semana, após cada sorteio).

## Endpoint

```
https://raw.githubusercontent.com/<UTILIZADOR>/<REPO>/main/data/draws.json
```

Tem CORS (`Access-Control-Allow-Origin: *`), pelo que pode ser lido diretamente
por JavaScript no browser, sem rate limit para uso pessoal.

## Formato

Lista ordenada do mais recente para o mais antigo:

```json
[
  { "date": "2026-07-07", "nums": [5, 29, 33, 45, 47], "stars": [5, 8], "jackpot": null }
]
```

| Campo     | Descrição                                  |
|-----------|--------------------------------------------|
| `date`    | Data do sorteio (`YYYY-MM-DD`)             |
| `nums`    | Os 5 números (1–50), ordenados             |
| `stars`   | As 2 estrelas (1–12), ordenadas            |
| `jackpot` | Valor do 1.º prémio, ou `null` (por obter) |

## Como funciona

- `data/draws.json` — os dados (fonte de verdade).
- `scripts/update.py` — vai buscar os sorteios novos e junta-os ao ficheiro.
- `.github/workflows/update.yml` — corre o script à terça/sexta à noite e ao
  sábado/quarta de manhã (UTC) e faz commit se houver sorteios novos.

Também se pode correr manualmente no separador **Actions → Atualizar sorteios → Run workflow**.

Fonte dos dados: [euromillions.api.pedromealha.dev](https://euromillions.api.pedromealha.dev).
