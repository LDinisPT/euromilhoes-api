#!/usr/bin/env python3
"""
Recolhe os resultados do M1lhão (jogo exclusivo de Portugal): o código vencedor
de cada sorteio e, quando disponível, a localidade onde foi validado.

Fontes (euro-millions.com, sem rate limit):
  1. /pt/m1lhao — lista os sorteios do ano corrente com CÓDIGO + LOCALIDADE.
  2. /pt/resultados/DD-MM-YYYY — página por sorteio; o código do M1lhão é o que
     surge a seguir ao cabeçalho "Resultados do M1lhão" (sem localidade).

O M1lhão sai na última sexta-feira de cada mês (antes de ~2023 era a todas as
sextas). Para o histórico, testamos as sextas-feiras conhecidas (de draws.json).

Guarda em data/milhao.json: [{"date","code","location"}] (mais recente primeiro).

Env: M1LHAO_BACKFILL_LIMIT (default 40), M1LHAO_DELAY (default 0.7)
"""

import json, os, re, sys, time, html as ihtml, urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "milhao.json")
DRAWS = os.path.join(BASE, "data", "draws.json")
MAIN = "https://www.euro-millions.com/pt/m1lhao"
DRAW = "https://www.euro-millions.com/pt/resultados/{}"  # DD-MM-YYYY
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
LIMIT = int(os.getenv("M1LHAO_BACKFILL_LIMIT", "40"))
DELAY = float(os.getenv("M1LHAO_DELAY", "0.7"))
CODE = r"[A-Z]{3}\s?\d{5}"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def clean_code(c):
    c = c.strip()
    return c if " " in c else c[:3] + " " + c[3:]


def scrape_main():
    """Sorteios do ano corrente com localidade."""
    h = fetch(MAIN)
    recs = {}
    for seg in h.split("/pt/resultados/")[1:]:
        md = re.match(r"(\d{2})-(\d{2})-(\d{4})", seg)
        if not md:
            continue
        date = f"{md.group(3)}-{md.group(2)}-{md.group(1)}"
        cm = re.search(r"raffleBox[^>]*>\s*(" + CODE + r")", seg)
        if not cm:
            continue
        lm = re.search(r"Ganhou em\s*<?/?[a-z]*>?\s*([^<]+?)\s*<", seg)
        recs[date] = {"date": date, "code": clean_code(cm.group(1)),
                      "location": ihtml.unescape(lm.group(1).strip()) if lm else ""}
    return recs


def scrape_draw_code(date_iso):
    """Código do M1lhão de uma data (sem localidade), ou None."""
    dd = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d-%m-%Y")
    h = fetch(DRAW.format(dd))
    m = re.search(r"Resultados do M1lh[aã]o.*?raffleBox[^>]*>\s*(" + CODE + r")", h, re.S)
    return clean_code(m.group(1)) if m else None


def main():
    existing = {}
    if os.path.exists(OUT):
        for r in json.load(open(OUT, encoding="utf-8")):
            existing[r["date"]] = r

    # 1) Página principal (código + localidade) — fonte de verdade p/ o ano atual
    try:
        for date, rec in scrape_main().items():
            old = existing.get(date)
            # não perder localidade já conhecida se a nova vier vazia
            if old and old.get("location") and not rec.get("location"):
                rec["location"] = old["location"]
            existing[date] = rec
        print("Pagina principal: OK.")
    except Exception as e:
        print(f"Pagina principal indisponivel ({e}).")

    # 2) Backfill de sextas-feiras em falta (código, sem localidade)
    sextas = []
    if os.path.exists(DRAWS):
        for d in json.load(open(DRAWS, encoding="utf-8")):
            dt = d["date"]
            if datetime.strptime(dt, "%Y-%m-%d").weekday() == 4 and dt >= "2016-09-01":
                sextas.append(dt)
    sextas = sorted(set(sextas), reverse=True)
    faltam = [dt for dt in sextas if dt not in existing]
    raspados = 0
    for dt in faltam[:LIMIT]:
        try:
            code = scrape_draw_code(dt)
        except Exception as e:
            print(f"  {dt}: falhou ({e})")
            code = None
        if code:
            existing[dt] = {"date": dt, "code": code, "location": ""}
            raspados += 1
        time.sleep(DELAY)

    saida = sorted(existing.values(), key=lambda x: x["date"], reverse=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    com_local = sum(1 for r in saida if r.get("location"))
    print(f"Total {len(saida)} sorteios do M1lhao (+{raspados} novos). "
          f"Com localidade: {com_local}. Mais recente {saida[0]['date'] if saida else '—'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
