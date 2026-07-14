// Envia a notificação (push-msg.json) para todos os dispositivos subscritos.
// Corre no GitHub Actions só quando houve sorteio novo. Segredos vêm do ambiente.
const webpush = require("web-push");
const fs = require("fs");
const path = require("path");

const PUB = process.env.VAPID_PUBLIC;
const PRIV = process.env.VAPID_PRIVATE;
const SUBJECT = process.env.VAPID_SUBJECT || "mailto:luisfmdinis@gmail.com";
const SECRET = process.env.PUSH_SECRET;
const WORKER = process.env.WORKER_URL || "https://euromilhoes-conta.luisfmdinis.workers.dev";

(async () => {
  const msgPath = path.join(__dirname, "..", "push-msg.json");
  if (!fs.existsSync(msgPath)) { console.log("Sem mensagem — nada a enviar."); return; }
  if (!PUB || !PRIV || !SECRET) { console.log("Faltam segredos VAPID/PUSH — nao envio."); return; }

  webpush.setVapidDetails(SUBJECT, PUB, PRIV);
  const payload = fs.readFileSync(msgPath, "utf8");

  const res = await fetch(`${WORKER}/push/list?key=${encodeURIComponent(SECRET)}`);
  if (!res.ok) { console.log("Nao consegui listar subscricoes:", res.status); return; }
  const subs = await res.json();
  console.log(`A enviar para ${subs.length} dispositivo(s)...`);

  let ok = 0, removidas = 0;
  for (const s of subs) {
    try {
      await webpush.sendNotification(s.sub, payload);
      ok++;
    } catch (e) {
      const code = e.statusCode || 0;
      if (code === 404 || code === 410) {
        await fetch(`${WORKER}/push/remove`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: SECRET, name: s.name }),
        });
        removidas++;
      } else {
        console.log("Falha num envio:", code, String(e.body || "").slice(0, 80));
      }
    }
  }
  console.log(`Enviados: ${ok}. Subscricoes expiradas removidas: ${removidas}.`);
})();
