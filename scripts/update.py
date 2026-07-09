#!/usr/bin/env python3
"""
Atualiza data/draws.json com os sorteios do Euromilhões e a repartição de
prémios de Portugal (€ por vencedor + nº de vencedores por escalão).

A API pública devolve, num único pedido, todo o histórico desde 2004 já com
os prémios (valores da tabela "PrizePT"). Este script vai buscá-los e reconstrói
o ficheiro, preservando quaisquer datas que só existam localmente. Se a fonte
falhar, sai sem alterar nada.

Schema de cada sorteio:
{
  "date": "YYYY-MM-DD",
  "nums": [5 números 1-50],
  "stars": [2 estrelas 1-12],
  "has_winner": bool,           # houve 1.º prémio (5+2)?
  "jackpot": número | null,     # valor do 1.º prémio por vencedor (€), se houve
  "prizes": {                   # por escalão, chave "Nnúmeros-Nestrelas"
      "5-2": {"prize": 17000000.0, "winners": 1},
      "5-1": {"prize": 130000.0,   "winners": 2},
      ...
  }
}
"""

import json, os, sys, urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "draws.json")
API_URL = "https://euromillions.api.pedromealha.dev/v1/draws"


def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "euromilhoes-api-updater (github actions)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_date(s):
    s = str(s or "")
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            return datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s[:10]


def norm(d):
    """Converte um sorteio da API no nosso formato (ou None se inválido)."""
    try:
        nums = sorted(int(x) for x in (d.get("numbers") or d.get("nums") or []))
        stars = sorted(int(x) for x in (d.get("stars") or []))
        date = parse_date(d.get("date"))
        if not (len(date) == 10 and len(nums) == 5 and len(set(nums)) == 5
                and all(1 <= n <= 50 for n in nums)
                and len(stars) == 2 and all(1 <= s <= 12 for s in stars)):
            return None

        prizes, jackpot = {}, None
        for p in (d.get("prizes") or []):
            mn, ms = p.get("matched_numbers"), p.get("matched_stars")
            if mn is None or ms is None:
                continue
            valor = p.get("prize")
            venc = p.get("winners")
            prizes[f"{mn}-{ms}"] = {"prize": valor, "winners": venc}
            if mn == 5 and ms == 2:
                jackpot = valor

        rec = {"date": date, "nums": nums, "stars": stars,
               "has_winner": bool(d.get("has_winner")) if d.get("has_winner") is not None
               else (jackpot is not None and (prizes.get("5-2", {}).get("winners") or 0) > 0)}
        rec["jackpot"] = jackpot
        rec["prizes"] = prizes
        return rec
    except (KeyError, ValueError, TypeError):
        return None


def main():
    with open(DATA, encoding="utf-8") as f:
        por_data = {d["date"]: d for d in json.load(f)}
    antes = len(por_data)
    com_premios_antes = sum(1 for d in por_data.values() if d.get("prizes"))

    try:
        remoto = fetch_json(API_URL)
    except Exception as e:
        print(f"Fonte indisponivel ({e}). Sem alteracoes.")
        return 0

    novos = 0
    for d in remoto:
        r = norm(d)
        if not r:
            continue
        if r["date"] not in por_data:
            novos += 1
        por_data[r["date"]] = r  # a API é a fonte de verdade (traz prémios)

    saida = sorted(por_data.values(), key=lambda x: x["date"], reverse=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)

    com_premios = sum(1 for d in saida if d.get("prizes"))
    print(f"Total {len(saida)} sorteios (+{novos} novos). "
          f"Com premios: {com_premios} (antes {com_premios_antes}). "
          f"Mais recente {saida[0]['date']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
