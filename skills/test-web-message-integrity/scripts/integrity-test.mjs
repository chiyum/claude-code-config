#!/usr/bin/env node
/**
 * Web 訊息完整性測試腳本
 *
 * 模擬「客服頻繁切換多個 Web 聊天室 + 多訪客持續發訊息」，
 * 驗證訊息不遺漏、不重複、Messages API 單調遞增。
 *
 * Web 跟 LINE 差別：
 *   - 訪客端走 WebSocket `/ws/guest/<room_id>` 發訊息（不是 webhook）
 *   - 建室走 POST `/api/v1/chat-rooms`（不需簽名）
 *
 * Usage:
 *   node integrity-test.mjs \
 *     --api=https://your-api-url.com \
 *     --site-code=your-site \
 *     --username=test-user --password=test-pass \
 *     --duration=60 \
 *     --guests=3 \
 *     --guest-interval=500 \
 *     --switch-interval=300
 *
 * 輸出：/tmp/web-integrity-report.json + console summary
 */

// Node 22+ 原生 WebSocket（不依賴 npm ws 套件）
const WebSocket = globalThis.WebSocket;

const args = Object.fromEntries(
  process.argv.slice(2).flatMap((a) => {
    const m = a.match(/^--([^=]+)=(.*)$/);
    return m ? [[m[1], m[2]]] : [];
  })
);

const API = (args.api || 'https://your-api-url.com').replace(/\/$/, '');
const WS_BASE = API.replace(/^http/, 'ws');
const SITE_CODE = args['site-code'] || 'your-site';
const USERNAME = args.username || 'test-user';
const PASSWORD = args.password || 'test-pass';
const DURATION = parseInt(args.duration || '60', 10);
const NUM_GUESTS = parseInt(args.guests || '3', 10);
const GUEST_INTERVAL_MS = parseInt(args['guest-interval'] || '500', 10);
const SWITCH_INTERVAL_MS = parseInt(args['switch-interval'] || '300', 10);
const REPORT_PATH = args.report || '/tmp/web-integrity-report.json';

const now = () => Date.now();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const logTs = () => new Date().toISOString().slice(11, 23);

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, options);
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { raw: text }; }
  return { status: res.status, data };
}

async function login() {
  console.log(`[${logTs()}] 登入 ${USERNAME}...`);
  const { status, data } = await fetchJSON(`${API}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD }),
  });
  if (status !== 200 || !data?.data?.access_token) {
    throw new Error(`登入失敗 status=${status} data=${JSON.stringify(data)}`);
  }
  return data.data.access_token;
}

// ─────────────────────────────────────────────────
// Web 訪客：POST 建室 + WS 發訊息
// ─────────────────────────────────────────────────
class WebGuest {
  constructor(idx) {
    this.idx = idx;
    this.guestName = `WebIntegrity_${idx}_${Date.now()}`;
    this.guestId = null;       // 後端建室時生成
    this.roomId = null;
    this.ws = null;
    this.sentMessages = [];
    this.errors = [];
  }

  async createRoom() {
    const { status, data } = await fetchJSON(`${API}/api/v1/chat-rooms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        guest_name: this.guestName,
        site: SITE_CODE,
      }),
    });
    if (status !== 200 || !data?.data?.id) {
      throw new Error(`建室失敗 guest=${this.idx} status=${status} data=${JSON.stringify(data)}`);
    }
    this.roomId = data.data.id;
    this.guestId = data.data.guest_id;
    return this.roomId;
  }

  async connect() {
    return new Promise((resolve, reject) => {
      const url = `${WS_BASE}/api/v1/ws/guest/${this.roomId}?guest_id=${encodeURIComponent(this.guestId)}&guest_name=${encodeURIComponent(this.guestName)}`;
      this.ws = new WebSocket(url);
      let opened = false;
      this.ws.addEventListener('open', () => { opened = true; resolve(); });
      this.ws.addEventListener('error', (e) => {
        this.errors.push({ time: now(), kind: 'ws-error', err: String(e?.message || e) });
        if (!opened) reject(e);
      });
      this.ws.addEventListener('close', () => {
        if (!this.intentionalDisconnect) {
          // 連線斷掉，自動 reconnect（簡單版：3 秒後重連）
          setTimeout(() => this.connect().catch(() => {}), 3000);
        }
      });
      // 訪客視角：echo 回來的訊息忽略，我們追蹤 server-side 為主
      this.ws.addEventListener('message', () => {});
    });
  }

  send(content) {
    if (!this.ws || this.ws.readyState !== 1 /* OPEN */) {
      this.errors.push({ time: now(), kind: 'send-not-open', content });
      return false;
    }
    try {
      this.ws.send(JSON.stringify({ type: 'text', content }));
      this.sentMessages.push({ content, sentAt: now() });
      return true;
    } catch (e) {
      this.errors.push({ time: now(), kind: 'send-exception', err: String(e) });
      return false;
    }
  }

  disconnect() {
    if (this.ws) {
      this.intentionalDisconnect = true;
      this.ws.close();
    }
  }
}

// ─────────────────────────────────────────────────
// 客服切換器（同 LINE skill）
// ─────────────────────────────────────────────────
class AgentSwitcher {
  constructor(token, rooms) {
    this.token = token;
    this.rooms = rooms;
    this.history = {};
    for (const r of rooms) this.history[r.roomId] = [];
    this.regressions = [];
  }

  async fetchMessages(roomId) {
    const url = `${API}/api/v1/chat-rooms/${roomId}/messages?limit=30&offset=0`;
    const { status, data } = await fetchJSON(url, {
      headers: { Authorization: `Bearer ${this.token}` },
    });
    if (status !== 200) return null;
    const messages = data?.data?.messages || data?.data || [];
    if (!Array.isArray(messages)) return null;
    const ids = messages.map((m) => m.id).filter(Boolean);
    return { count: messages.length, ids, raw: messages };
  }

  async run(stopAt) {
    let switchCount = 0;
    while (now() < stopAt) {
      const target = this.rooms[switchCount % this.rooms.length];
      const result = await this.fetchMessages(target.roomId);
      if (result) {
        const prev = this.history[target.roomId].at(-1);
        this.history[target.roomId].push({
          time: now(),
          count: result.count,
          messageIds: result.ids,
        });
        if (prev) {
          const prevSet = new Set(prev.messageIds);
          const currSet = new Set(result.ids);
          const lostIds = [...prevSet].filter((id) => !currSet.has(id));
          if (lostIds.length > 0) {
            this.regressions.push({
              roomId: target.roomId,
              guestIdx: target.guestIdx,
              time: now(),
              prevCount: prev.count,
              currCount: result.count,
              lostIds,
              lostCount: lostIds.length,
            });
          }
        }
      }
      switchCount++;
      await sleep(SWITCH_INTERVAL_MS);
    }
    console.log(`[${logTs()}] 客服切換完成，總 GET 次數 ${switchCount}`);
  }
}

// ─────────────────────────────────────────────────
// 主流程
// ─────────────────────────────────────────────────
async function main() {
  console.log(`========== Web 訊息完整性測試 ==========`);
  console.log(`API: ${API}`);
  console.log(`Site code: ${SITE_CODE}`);
  console.log(`Duration: ${DURATION}s / Guests: ${NUM_GUESTS}`);
  console.log(`Guest interval: ${GUEST_INTERVAL_MS}ms / Switch interval: ${SWITCH_INTERVAL_MS}ms`);
  console.log(`========================================\n`);

  const token = await login();

  // Phase 1: 建室 + WS 連線
  console.log(`[${logTs()}] Phase 1: 建室 + WS 連線（${NUM_GUESTS} 個訪客）`);
  const guests = Array.from({ length: NUM_GUESTS }, (_, i) => new WebGuest(i));
  for (const g of guests) {
    await g.createRoom();
    await g.connect();
    console.log(`  ${g.idx}: room=${g.roomId} guest_id=${g.guestId}`);
  }
  await sleep(1000);

  // Phase 2: 並行訪客發訊息 + 客服切換
  console.log(`\n[${logTs()}] Phase 2: 進入 ${DURATION}s 壓力測試`);
  const stopAt = now() + DURATION * 1000;

  const guestPromises = guests.map(async (g) => {
    let seq = 0;
    while (now() < stopAt) {
      seq++;
      g.send(`web-${g.idx}-msg-${seq}`);
      await sleep(GUEST_INTERVAL_MS);
    }
    console.log(`[${logTs()}] 訪客 ${g.idx} 發送完成，總 ${g.sentMessages.length} 則`);
  });

  const switcher = new AgentSwitcher(
    token,
    guests.map((g) => ({ roomId: g.roomId, guestIdx: g.idx }))
  );
  const switcherPromise = switcher.run(stopAt);

  await Promise.all([...guestPromises, switcherPromise]);

  // Phase 3: 等 archive worker
  console.log(`\n[${logTs()}] Phase 3: 等 5s 讓 archive worker 跑完`);
  await sleep(5000);

  // 關閉 WS
  for (const g of guests) g.disconnect();

  // Phase 4: 最終驗證
  console.log(`\n[${logTs()}] Phase 4: 驗證`);
  const report = {
    config: {
      api: API, siteCode: SITE_CODE, duration: DURATION, numGuests: NUM_GUESTS,
      guestIntervalMs: GUEST_INTERVAL_MS, switchIntervalMs: SWITCH_INTERVAL_MS,
    },
    rooms: [],
    summary: { totalSent: 0, totalInDB: 0, missingCount: 0, duplicateCount: 0, regressionCount: switcher.regressions.length, errorCount: 0 },
    regressions: switcher.regressions,
  };

  for (const g of guests) {
    // 撈完整 messages（limit 500 = API 上限；超過時用 pagination）
    let allMessages = [];
    let offset = 0;
    while (true) {
      const url = `${API}/api/v1/chat-rooms/${g.roomId}/messages?limit=500&offset=${offset}`;
      const { data } = await fetchJSON(url, { headers: { Authorization: `Bearer ${token}` } });
      const page = data?.data?.messages || data?.data || [];
      if (!Array.isArray(page) || page.length === 0) break;
      allMessages = allMessages.concat(page);
      if (page.length < 500) break;
      offset += 500;
    }

    // Web 後端 bug：訪客訊息 sender_id / sender_type 是空字串（理論上應該是 guest_id / guest）
    // 暫時改用 content prefix 過濾（content 格式 web-N-msg-X 由本腳本產生）
    const contentPrefix = `web-${g.idx}-msg-`;
    const guestMessages = allMessages.filter(
      (m) => m.message_type === 'text' && typeof m.content === 'string' && m.content.startsWith(contentPrefix)
    );
    const dbIdSet = new Set(allMessages.map((m) => m.id));

    const byContent = new Map();
    for (const m of guestMessages) {
      const c = m.content;
      byContent.set(c, (byContent.get(c) || 0) + 1);
    }
    const duplicates = [...byContent.entries()].filter(([, n]) => n > 1);

    const sentContents = new Set(g.sentMessages.map((m) => m.content));
    const dbContents = new Set(guestMessages.map((m) => m.content));
    const missing = [...sentContents].filter((c) => !dbContents.has(c));
    const extra = [...dbContents].filter((c) => !sentContents.has(c));

    // Ghost ID：客服 GET 過程中出現過的 message ID，最後在 DB 撈不到（真實 bug）
    const seenIds = new Set();
    for (const h of switcher.history[g.roomId] || []) {
      for (const id of h.messageIds) seenIds.add(id);
    }
    const ghostIds = [...seenIds].filter((id) => !dbIdSet.has(id));

    const roomReport = {
      guestIdx: g.idx,
      guestId: g.guestId,
      roomId: g.roomId,
      sent: g.sentMessages.length,
      inDB: guestMessages.length,
      inDBIncludingAgent: allMessages.length,
      missing: missing.length,
      missingExamples: missing.slice(0, 5),
      duplicate: duplicates.length,
      duplicateExamples: duplicates.slice(0, 5),
      extra: extra.length,
      extraExamples: extra.slice(0, 5),
      sendErrors: g.errors.length,
      switchHistorySize: switcher.history[g.roomId]?.length || 0,
      ghostIds: ghostIds.length,
      ghostIdSamples: ghostIds.slice(0, 5),
    };
    report.rooms.push(roomReport);
    report.summary.totalSent += roomReport.sent;
    report.summary.totalInDB += roomReport.inDB;
    report.summary.missingCount += roomReport.missing;
    report.summary.duplicateCount += roomReport.duplicate;
    report.summary.errorCount += roomReport.sendErrors;
    report.summary.ghostIdCount = (report.summary.ghostIdCount || 0) + roomReport.ghostIds;
  }

  await import('node:fs/promises').then((fs) => fs.writeFile(REPORT_PATH, JSON.stringify(report, null, 2)));

  console.log(`\n========== 測試報告 ==========`);
  console.log(`訪客發送：${report.summary.totalSent} 則`);
  console.log(`DB 內訪客訊息：${report.summary.totalInDB} 則`);
  console.log(`遺失（發了但 DB 沒有）：${report.summary.missingCount} ${report.summary.missingCount > 0 ? '❌' : '✅'}`);
  console.log(`重複（DB 內同 content）：${report.summary.duplicateCount} ${report.summary.duplicateCount > 0 ? '❌' : '✅'}`);
  console.log(`Ghost ID（API 回傳過但 DB 撈不到）：${report.summary.ghostIdCount || 0} ${(report.summary.ghostIdCount || 0) > 0 ? '❌' : '✅'}`);
  console.log(`發送錯誤：${report.summary.errorCount}`);
  console.log(``);
  console.log(`資訊性指標（不算 bug）：`);
  console.log(`  滑動窗口下 ID 進出次數：${report.summary.regressionCount}（limit=30+offset=0 視窗自然滑動）`);
  console.log(`\n詳細報告：${REPORT_PATH}`);
  console.log(`========================================`);

  if ((report.summary.ghostIdCount || 0) > 0) {
    console.log(`\n❌ Ghost ID sample（真實 bug，前 5 筆）：`);
    for (const r of report.rooms) {
      if (r.ghostIds > 0) {
        console.log(`  room=${r.roomId} ghost 數=${r.ghostIds}`);
        console.log(`    IDs: ${r.ghostIdSamples.join(',')}`);
      }
    }
  }

  process.exit(report.summary.missingCount > 0 || report.summary.duplicateCount > 0 || (report.summary.ghostIdCount || 0) > 0 ? 1 : 0);
}

main().catch((e) => {
  console.error('❌ 測試失敗:', e);
  process.exit(2);
});
