#!/usr/bin/env python3
"""
Atualiza data/draws.json com os sorteios do Euromilhões e a repartição de
prémios de Portugal (€ por vencedor + nº de vencedores por escalão).

Duas fontes:
  1. API pedromealha (/v1/draws) — devolve todo o histórico com prémios num
     único pedido. É a fonte primária, mas tem rate limit agressivo (429).
  2. euro-millions.com (/results/DD-MM-YYYY) — página por sorteio com a tabela
     "PrizePT". Usada como recurso para preencher prémios em falta, por lotes.

Configurável por variáveis de ambiente:
  EM_BACKFILL_LIMIT  nº máx. de sorteios a raspar por execução (default 50)
  EM_DELAY           pausa entre pedidos ao euro-millions.com, em s (default 0.8)

Schema de cada sorteio:
{
  "date": "YYYY-MM-DD",
  "nums": [5 números 1-50],
  "stars": [2 estrelas 1-12],
  "has_winner": bool,           # houve 1.º prémio (5+2)?
  "jackpot": número | null,     # valor do 1.º prémio por vencedor (€)
  "prizes": {                   # por escalão, chave "Nnúmeros-Nestrelas"
      "5-2": {"prize": 17000000.0, "winners": 0},
      "4-2": {"prize": 1217.40,    "winners": 4}, ...
  }
}
"""

import json, os, re, sys, time, html as ihtml, urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "draws.json")
API_URL = "https://euromillions.api.pedromealha.dev/v1/draws"
EM_DRAW = "https://www.euro-millions.com/results/{}"  # {} = DD-MM-YYYY
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
BACKFILL_LIMIT = int(os.getenv("EM_BACKFILL_LIMIT", "50"))
DELAY = float(os.getenv("EM_DELAY", "0.8"))


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


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


# ── Fonte 1: API pedromealha ────────────────────────────────────────────────
def norm_api(d):
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
            prizes[f"{mn}-{ms}"] = {"prize": p.get("prize"), "winners": p.get("winners")}
            if mn == 5 and ms == 2:
                jackpot = p.get("prize")
        return {"date": date, "nums": nums, "stars": stars, "jackpot": jackpot,
                "has_winner": bool(d.get("has_winner")), "prizes": prizes}
    except (KeyError, ValueError, TypeError):
        return None


# ── Fonte 2: euro-millions.com (tabela PrizePT) ─────────────────────────────
def _num(x):
    x = ihtml.unescape(x).replace("€", "").replace(",", "").replace("\xa0", " ").strip()
    try:
        return float(x)
    except ValueError:
        return None


def scrape_draw_full(date_iso):
    """Sorteio completo (números + estrelas + prémios PT) do euro-millions.com,
    ou None se a página não tiver resultado. Usado quando a API principal falha."""
    dd = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d-%m-%Y")
    try:
        page = fetch_text(EM_DRAW.format(dd))
    except Exception:
        return None
    m = re.search(r'id="ballsAscending">(.*?)</ul>', page, re.S)
    if not m:
        return None
    bloco = m.group(1)
    nums = [int(x) for x in re.findall(r'class="resultBall ball">\s*(\d+)', bloco)]
    stars = [int(x) for x in re.findall(r'class="resultBall lucky-star">\s*(\d+)', bloco)]
    if not (len(nums) == 5 and len(set(nums)) == 5 and all(1 <= n <= 50 for n in nums)
            and len(stars) == 2 and all(1 <= s <= 12 for s in stars)):
        return None
    prizes = _parse_prizes_pt(page)
    jackpot = prizes.get("5-2", {}).get("prize")
    return {"date": date_iso, "nums": sorted(nums), "stars": sorted(stars),
            "has_winner": (prizes.get("5-2", {}).get("winners") or 0) > 0,
            "jackpot": jackpot, "prizes": prizes}


def _parse_prizes_pt(page):
    m = re.search(r'<div id="PrizePT">(.*?)</table>', page, re.S)
    if not m:
        return {}
    block = m.group(1)
    prizes = {}
    for row in re.findall(r"<tr>(.*?)</tr>", block, re.S):
        if "prizeName" not in row:
            continue
        ball = re.search(r'class="ball">\s*(\d+)', row)
        if not ball:
            continue
        star = re.search(r'class="star">\s*(\d+)', row)
        mn, ms = int(ball.group(1)), (int(star.group(1)) if star else 0)
        cells = re.findall(r'data-title="([^"]+)"[^>]*>(.*?)</td>', row, re.S)
        d = {t.strip(): re.sub(r"<[^>]+>", "", v).strip() for t, v in cells}
        prize = _num(d.get("Prize Per Winner", ""))
        win = None
        for k, v in d.items():
            if "Winner" in k and "Total" not in k and "Prize" not in k:
                w = _num(v)
                win = int(w) if w is not None else None
                break
        prizes[f"{mn}-{ms}"] = {"prize": prize, "winners": win}
    return prizes


def scrape_prizes_pt(date_iso):
    """Devolve {'5-2': {'prize':..,'winners':..}, ...} ou {} se não encontrar."""
    dd = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d-%m-%Y")
    return _parse_prizes_pt(fetch_text(EM_DRAW.format(dd)))


def datas_de_sorteio(desde_iso, ate):
    """Terças e sextas depois de `desde_iso` até à data `ate` (inclusive)."""
    from datetime import date as _date, timedelta
    d = datetime.strptime(desde_iso, "%Y-%m-%d").date() + timedelta(days=1)
    out = []
    while d <= ate:
        if d.weekday() in (1, 4):  # ter=1, sex=4
            out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


SC_URL = "https://www.jogossantacasa.pt/web/SCCartazResult/euroMilhoes"

def scrape_santacasa_latest():
    """Último sorteio publicado pela Santa Casa (oficial): números + estrelas.
    Sem prémios (esses vêm do backfill euro-millions). Devolve dict ou None."""
    try:
        h = fetch_text(SC_URL)
    except Exception:
        return None
    md = re.search(r"Data do Sorteio\s*[-–]\s*(\d{2})/(\d{2})/(\d{4})", h)
    mk = re.search(r"Chave[\s\S]{0,300}?(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*\+\s*(\d+)\s+(\d+)", h)
    if not (md and mk):
        return None
    date = f"{md.group(3)}-{md.group(2)}-{md.group(1)}"
    g = [int(x) for x in mk.groups()]
    nums, stars = sorted(g[:5]), sorted(g[5:])
    if not (len(set(nums)) == 5 and all(1 <= n <= 50 for n in nums) and all(1 <= s <= 12 for s in stars)):
        return None
    return {"date": date, "nums": nums, "stars": stars,
            "has_winner": False, "jackpot": None, "prizes": {}}


# ── Chave do Turno A (para a mensagem de notificação) ──
TA_NUMS = {7, 21, 35, 37, 45}
TA_STARS = [2, 4, 5, 6]
TA_PAIRS = [(TA_STARS[i], TA_STARS[j]) for i in range(4) for j in range(i + 1, 4)]
PRIZE_TIERS = {"5-2", "5-1", "5-0", "4-2", "4-1", "3-2", "4-0", "2-2", "3-1", "3-0", "1-2", "2-1", "2-0"}


def turno_a_result(rec):
    nums, stars = set(rec["nums"]), set(rec["stars"])
    mn = len(TA_NUMS & nums)
    mstars = len(set(TA_STARS) & stars)
    ganho, prizes = 0.0, (rec.get("prizes") or {})
    for pa, pb in TA_PAIRS:
        pk = f"{mn}-{len({pa, pb} & stars)}"
        if pk in PRIZE_TIERS:
            info = prizes.get(pk)
            if info and info.get("prize") is not None:
                ganho += info["prize"]
    return mn, mstars, round(ganho, 2)


def escrever_push_msg(rec, path):
    dd = datetime.strptime(rec["date"], "%Y-%m-%d").strftime("%d/%m")
    nums = "·".join(str(n) for n in rec["nums"])
    stars = "·".join(str(s) for s in rec["stars"])
    mn, mstars, ganho = turno_a_result(rec)
    if ganho > 0:
        s1 = "s" if mn != 1 else ""
        s2 = "s" if mstars != 1 else ""
        linha = f"Turno A: GANHOU €{ganho:.2f} ({mn} numero{s1} e {mstars} estrela{s2})"
    else:
        linha = "Turno A: sem premio"
    msg = {"title": f"Euromilhoes · {dd}",
           "body": f"{nums} * {stars}\n{linha}",
           "url": "https://ldinispt.github.io/euromilhoes-api/"}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(msg, f, ensure_ascii=False)
    print(f"push-msg.json escrito: {msg['title']} | {linha}")


def main():
    with open(DATA, encoding="utf-8") as f:
        por_data = {d["date"]: d for d in json.load(f)}
    com_premios_antes = sum(1 for d in por_data.values() if d.get("prizes"))
    novos = 0
    novas_datas = []

    # ── Sorteios NOVOS (terças/sextas desde o último registado) ──
    # Fonte 1: euro-millions.com (por data, com prémios PT)
    # Fonte 2: Santa Casa (oficial; só o último sorteio publicado)
    from datetime import date as _date
    ultimo = max(por_data)
    for dt in datas_de_sorteio(ultimo, _date.today()):
        if dt in por_data:
            continue
        r = scrape_draw_full(dt)
        fonte = "euro-millions.com"
        if not r:
            sc = scrape_santacasa_latest()
            if sc and sc["date"] == dt:
                r, fonte = sc, "Santa Casa"
        if r:
            por_data[dt] = r
            novos += 1
            novas_datas.append(dt)
            print(f"  novo sorteio {dt} via {fonte}: {r['nums']} + {r['stars']}")
        else:
            print(f"  {dt}: ainda sem resultado publicado (euro-millions e Santa Casa).")
        time.sleep(DELAY)

    # ── Prémios em falta: euro-millions.com, por lotes (mais recentes primeiro) ──
    faltam = [d for d in sorted(por_data.values(), key=lambda x: x["date"], reverse=True)
              if not d.get("prizes")]
    raspados = 0
    for d in faltam[:BACKFILL_LIMIT]:
        try:
            p = scrape_prizes_pt(d["date"])
        except Exception as e:
            print(f"  {d['date']}: falhou ({e})")
            p = {}
        if p:
            d["prizes"] = p
            d["jackpot"] = p.get("5-2", {}).get("prize")
            d["has_winner"] = (p.get("5-2", {}).get("winners") or 0) > 0
            raspados += 1
        time.sleep(DELAY)

    # ── Fonte 3 (última opção): API pedromealha — só ADICIONA o que faltar. ──
    # Nunca substitui registos existentes; útil se as outras fontes falharem
    # ou para preencher prémios antigos em falta.
    ainda_faltam_novos = bool(datas_de_sorteio(max(por_data), _date.today()))
    ainda_faltam_premios = any(not d.get("prizes") for d in por_data.values())
    if ainda_faltam_novos or ainda_faltam_premios:
        try:
            for d in fetch_json(API_URL):
                r = norm_api(d)
                if not r:
                    continue
                antigo = por_data.get(r["date"])
                if antigo is None:
                    por_data[r["date"]] = r
                    novos += 1
                elif not antigo.get("prizes") and r.get("prizes"):
                    antigo["prizes"] = r["prizes"]
                    antigo["jackpot"] = r.get("jackpot")
                    antigo["has_winner"] = r.get("has_winner")
            print("API pedromealha (3.ª opção): consultada.")
        except Exception as e:
            print(f"API pedromealha (3.ª opção) indisponivel ({e}) — sem problema.")
    else:
        print("Tudo completo sem precisar da pedromealha.")

    saida = sorted(por_data.values(), key=lambda x: x["date"], reverse=True)
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)

    # ── Mensagem de notificação (se houve sorteio novo) ──
    msg_path = os.path.join(BASE, "push-msg.json")
    if os.path.exists(msg_path):
        os.remove(msg_path)
    if novas_datas:
        dt = max(novas_datas)
        escrever_push_msg(por_data[dt], msg_path)

    com_premios = sum(1 for d in saida if d.get("prizes"))
    faltam_ainda = len(saida) - com_premios
    print(f"Total {len(saida)} sorteios (+{novos} novos). "
          f"Com premios: {com_premios} (antes {com_premios_antes}, +{raspados} raspados). "
          f"Ainda sem premios: {faltam_ainda}. Mais recente {saida[0]['date']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
