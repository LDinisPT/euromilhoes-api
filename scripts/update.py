#!/usr/bin/env python3
"""
Atualiza data/draws.json com os sorteios mais recentes do Euromilhões.

Corre no GitHub Actions 2x/semana. Vai buscar os sorteios à API pública,
junta ao histórico existente (sem duplicar) e grava ordenado do mais recente
para o mais antigo. Se a fonte falhar, sai sem alterar nada (o workflow
não faz commit e tenta de novo no próximo agendamento).

Schema de cada sorteio: {"date": "YYYY-MM-DD", "nums": [5], "stars": [2], "jackpot": null}
"""

import json, os, sys, urllib.request, urllib.error

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "draws.json")
API_URL = "https://euromillions.api.pedromealha.dev/v1/draws"


def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "euromilhoes-api-updater (github actions)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def normalizar(d):
    """Aceita os vários formatos que a API pode devolver."""
    try:
        if d.get("numbers"):
            nums = [int(x) for x in d["numbers"][:5]]
        else:
            nums = [int(d["ball_" + str(i)]) for i in range(1, 6)]
        if d.get("stars"):
            stars = [int(x) for x in d["stars"][:2]]
        else:
            stars = [int(d["lucky_star_" + str(i)]) for i in range(1, 3)]
        date = str(d.get("date", ""))[:10]
        if not (len(date) == 10 and len(set(nums)) == 5
                and all(1 <= n <= 50 for n in nums)
                and all(1 <= s <= 12 for s in stars)):
            return None
        return {"date": date, "nums": sorted(nums), "stars": sorted(stars),
                "jackpot": d.get("jackpot") or None}
    except (KeyError, ValueError, TypeError):
        return None


def main():
    with open(DATA, encoding="utf-8") as f:
        existentes = json.load(f)
    por_data = {d["date"]: d for d in existentes}
    antes = len(por_data)

    try:
        remoto = fetch_json(API_URL)
    except Exception as e:
        print(f"Fonte indisponivel ({e}). Sem alteracoes.")
        return 0  # sai limpo, workflow nao faz commit

    novos = 0
    for d in remoto:
        n = normalizar(d)
        if n and n["date"] not in por_data:
            por_data[n["date"]] = n
            novos += 1

    if novos == 0:
        print(f"Ja atualizado — {antes} sorteios.")
        return 0

    saida = sorted(por_data.values(), key=lambda x: x["date"], reverse=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    print(f"+{novos} sorteios (total {len(saida)}, mais recente {saida[0]['date']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
