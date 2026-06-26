// RunPod reaper — the single EXTERNAL authority that deletes RunPod pods.
//
// Why this exists: a pod calling the RunPod API to delete ITSELF is unreliable —
// pod->RunPod requests intermittently 403 (shared datacenter egress IP hits
// RunPod's own WAF/rate-limit). Calls from OUTSIDE RunPod are 100% reliable.
// So all termination is funnelled through this always-on Cloudflare Worker.
//
// Three jobs:
//   scheduled() (cron */15) : list pods; for any RUNNING older than MAX_AGE_HOURS,
//                             post a Discord alert with a 🗑️ Terminate button.
//   POST /terminate         : a pod asks to be killed -> DELETE it. From attempt>=2
//                             (then ~every 30s) also post a button alarm so a human
//                             can force it if the auto path is struggling.
//   POST /interactions      : a Discord button click -> verify Ed25519 -> DELETE.
//
// Secrets (wrangler secret put): RUNPOD_API_KEY, DISCORD_BOT_TOKEN,
//   DISCORD_PUBLIC_KEY, POD_PING_SECRET.  Vars: CHANNEL_ID, MAX_AGE_HOURS.

const RUNPOD = "https://rest.runpod.io/v1/pods";
const DISCORD = "https://discord.com/api/v10";
const hex2bin = (h) => Uint8Array.from(h.match(/.{1,2}/g).map((b) => parseInt(b, 16)));

async function runpodList(env) {
  const r = await fetch(RUNPOD, { headers: { Authorization: `Bearer ${env.RUNPOD_API_KEY}` } });
  if (!r.ok) throw new Error(`runpod list ${r.status}`);
  return r.json();
}
async function runpodDelete(env, podId) {
  const r = await fetch(`${RUNPOD}/${podId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${env.RUNPOD_API_KEY}`, "Content-Type": "application/json" },
  });
  return r.ok; // external call -> reliable
}
function terminateButton(podId, label) {
  return { type: 1, components: [{ type: 2, style: 4, label: label || "🗑️ Terminate", custom_id: `terminate:${podId}` }] };
}
async function postMessage(env, content, components) {
  // Must be posted by the BOT (not a webhook) so the button routes interactions back here.
  await fetch(`${DISCORD}/channels/${env.CHANNEL_ID}/messages`, {
    method: "POST",
    headers: { Authorization: `Bot ${env.DISCORD_BOT_TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ content, components: components || [], allowed_mentions: { parse: [] } }),
  });
}
function ageHours(pod) {
  // RunPod's pod-object timestamp field name varies — try a few, fail safe to null.
  const ts = pod.lastStartedAt || pod.createdAt || pod.startedAt;
  const t = ts ? Date.parse(ts) : NaN;
  return isNaN(t) ? null : (Date.now() - t) / 3.6e6;
}

export default {
  // ---- cron: stale-pod reaper (alert + button) ----
  async scheduled(event, env, ctx) {
    const maxAge = parseFloat(env.MAX_AGE_HOURS || "1");
    let pods;
    try { pods = await runpodList(env); } catch (e) { console.log("list failed", e); return; }
    const list = Array.isArray(pods) ? pods : (pods.pods || pods.data || []);
    for (const pod of list) {
      const running = (pod.desiredStatus || pod.status || "").toUpperCase() === "RUNNING";
      const age = ageHours(pod);
      if (running && age !== null && age > maxAge) {
        await postMessage(
          env,
          `🧹 오래 떠 있는 파드 — \`${pod.id}\` (${pod.name || "?"}, ${age.toFixed(1)}h, $${pod.costPerHr ?? "?"}/hr)\n임계 ${maxAge}h 초과. 종료하려면 버튼 👇`,
          [terminateButton(pod.id)],
        );
      }
    }
  },

  async fetch(req, env) {
    const url = new URL(req.url);

    // ---- pod -> auto terminate (feature 2) ----
    if (url.pathname === "/terminate" && req.method === "POST") {
      const b = await req.json().catch(() => ({}));
      if (b.secret !== env.POD_PING_SECRET) return new Response("forbidden", { status: 403 });
      if (!b.pod_id) return new Response("no pod_id", { status: 400 });
      const ok = await runpodDelete(env, b.pod_id);
      const attempt = Number(b.attempt || 1);
      // 2번째, 이후 ~30초마다(매 10시도) 버튼 알람. Worker 핑 자체는 파드가 3초마다 보냄.
      if (attempt === 2 || (attempt > 2 && attempt % 10 === 0)) {
        await postMessage(
          env,
          `⛔ 자동 종료 미완 — \`${b.pod_id}\` (시도 #${attempt}, DELETE ok=${ok})\n수동으로 끝내려면 버튼 👇`,
          [terminateButton(b.pod_id)],
        );
      }
      return Response.json({ ok });
    }

    // ---- Discord button click (shared by feature 1 & 2) ----
    if (url.pathname === "/interactions" && req.method === "POST") {
      const raw = await req.text();
      const sig = req.headers.get("X-Signature-Ed25519");
      const ts = req.headers.get("X-Signature-Timestamp");
      let valid = false;
      if (sig && ts) {
        const key = await crypto.subtle.importKey("raw", hex2bin(env.DISCORD_PUBLIC_KEY), { name: "Ed25519" }, false, ["verify"]);
        valid = await crypto.subtle.verify({ name: "Ed25519" }, key, hex2bin(sig), new TextEncoder().encode(ts + raw));
      }
      if (!valid) return new Response("bad signature", { status: 401 });
      const i = JSON.parse(raw);
      if (i.type === 1) return Response.json({ type: 1 }); // PING -> PONG (URL 검증)
      if (i.type === 3) { // MESSAGE_COMPONENT
        const [action, podId] = (i.data.custom_id || "").split(":");
        if (action === "terminate") {
          const ok = await runpodDelete(env, podId);
          const who = i.member?.user?.id || i.user?.id;
          return Response.json({
            type: 7, // UPDATE_MESSAGE
            data: {
              content: ok ? `✅ 종료됨 — \`${podId}\`${who ? ` (by <@${who}>)` : ""}` : `⚠️ 종료 실패 — \`${podId}\` (로컬 runpod_down 으로 수동 확인)`,
              components: [],
            },
          });
        }
      }
      return new Response("unhandled", { status: 400 });
    }

    return new Response("runpod-reaper up");
  },
};
