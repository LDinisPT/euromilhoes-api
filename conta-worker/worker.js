// API do Turno A — guarda na nuvem (Cloudflare KV):
//  • Conta (raiz):  GET devolve o JSON; POST grava (só com PIN).
//  • Notificações:  /push/subscribe (POST) guarda a subscrição de um telemóvel;
//                   /push/list (GET, com ?key=SECRET) devolve todas (só o servidor);
//                   /push/remove (POST, com key=SECRET) apaga uma expirada.
// Segredos do Worker: env.PIN (Conta) e env.PUSH_SECRET (listar/limpar subscrições).

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" },
  });
}

async function sha(s) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, "0")).join("").slice(0, 24);
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    const url = new URL(request.url);
    const path = url.pathname;

    // ── Notificações (Web Push) ──
    if (path === "/push/subscribe" && request.method === "POST") {
      let sub;
      try { sub = await request.json(); } catch { return json({ error: "json" }, 400); }
      if (!sub || !sub.endpoint) return json({ error: "sem endpoint" }, 400);
      await env.CONTA.put("push:" + (await sha(sub.endpoint)), JSON.stringify(sub));
      return json({ ok: true });
    }
    if (path === "/push/list" && request.method === "GET") {
      if (url.searchParams.get("key") !== env.PUSH_SECRET) return json({ error: "nao autorizado" }, 403);
      const out = [];
      let cursor;
      do {
        const l = await env.CONTA.list({ prefix: "push:", cursor });
        for (const k of l.keys) {
          const v = await env.CONTA.get(k.name);
          if (v) out.push({ name: k.name, sub: JSON.parse(v) });
        }
        cursor = l.cursor;
        if (l.list_complete) break;
      } while (cursor);
      return json(out);
    }
    if (path === "/push/remove" && request.method === "POST") {
      let b;
      try { b = await request.json(); } catch { return json({ error: "json" }, 400); }
      if (b.key !== env.PUSH_SECRET) return json({ error: "nao autorizado" }, 403);
      if (b.name) await env.CONTA.delete(b.name);
      return json({ ok: true });
    }

    // ── Conta (raiz) ──
    if (request.method === "GET") {
      const data = await env.CONTA.get("conta");
      return new Response(data || "null", {
        headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" },
      });
    }
    if (request.method === "POST") {
      let body;
      try { body = await request.json(); } catch { return json({ error: "json inválido" }, 400); }
      if (!env.PIN) return json({ error: "PIN não configurado no servidor" }, 500);
      if (!body || String(body.pin) !== String(env.PIN)) return json({ error: "PIN errado" }, 403);
      if (typeof body.data === "undefined") return json({ error: "sem dados" }, 400);
      await env.CONTA.put("conta", JSON.stringify(body.data));
      return json({ ok: true });
    }

    return json({ error: "método não permitido" }, 405);
  },
};
