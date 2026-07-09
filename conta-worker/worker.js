// API da Conta do Turno A — guarda o estado na nuvem (Cloudflare KV).
// GET  -> devolve o JSON guardado (leitura livre).
// POST -> grava, mas só com o PIN correto (validado aqui, no servidor).
// O PIN vive como "secret" do Worker (env.PIN), nunca vai para o browser.

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

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });

    if (request.method === "GET") {
      const data = await env.CONTA.get("conta");
      return new Response(data || "null", {
        headers: { ...CORS, "Content-Type": "application/json; charset=utf-8" },
      });
    }

    if (request.method === "POST") {
      let body;
      try { body = await request.json(); }
      catch { return json({ error: "json inválido" }, 400); }

      if (!env.PIN) return json({ error: "PIN não configurado no servidor" }, 500);
      if (!body || String(body.pin) !== String(env.PIN)) return json({ error: "PIN errado" }, 403);
      if (typeof body.data === "undefined") return json({ error: "sem dados" }, 400);

      await env.CONTA.put("conta", JSON.stringify(body.data));
      return json({ ok: true });
    }

    return json({ error: "método não permitido" }, 405);
  },
};
