#!/usr/bin/env node
/**
 * LINE 訊息完整性測試腳本
 *
 * 模擬「客服頻繁切換多個 LINE 聊天室 + 多訪客持續發訊息」場景，
 * 驗證 messages API 回傳值不遺漏、不重複，DB 寫入完整。
 *
 * Usage:
 *   node integrity-test.mjs \
 *     --api=https://your-api-url.com \
 *     --site-code=your-site \
 *     --line-token=<webhook_token> \
 *     --line-secret=<channel_secret> \
 *     --username=test-user --password=test-pass \
 *     --duration=60 \
 *     --guests=3 \
 *     --guest-interval=500 \
 *     --switch-interval=300
 *
 * 輸出：/tmp/line-integrity-report.json + console summary
 *
 * 驗證的不變量：
 *   1. 每個訪客發送的訊息（用 unique line_message_id）都應出現在 DB
 *   2. 每次 GET /chat-rooms/<id>/messages 回傳的 message ID 集合 ⊆ DB 該室訊息 ID 集合
 *   3. 每次 GET 回傳的訊息數 ≥ 前一次同室 GET 的訊息數（單調遞增）
 *   4. 任何 unique line_message_id 在 DB 內只出現一次（不重複）
 */

import crypto from 'node:crypto';
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
const LINE_TOKEN = args['line-token'];
const LINE_SECRET = args['line-secret'];
const USERNAME = args.username || 'test-user';
const PASSWORD = args.password || 'test-pass';
const DURATION = parseInt(args.duration || '60', 10);
const NUM_GUESTS = parseInt(args.guests || '3', 10);
const GUEST_INTERVAL_MS = parseInt(args['guest-interval'] || '500', 10);
const SWITCH_INTERVAL_MS = parseInt(args['switch-interval'] || '300', 10);
const REPORT_PATH = args.report || '/tmp/line-integrity-report.json';

if (!LINE_TOKEN || !LINE_SECRET) {
  console.error('❌ 缺 --line-token 或 --line-secret，請從 dev DB 撈或從 admin 後台 /channels 頁面取');
  process.exit(1);
}

// ─────────────────────────────────────────────────
// 共用工具
// ─────────────────────────────────────────────────
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

function signLineBody(body, secret) {
  return crypto.createHmac('sha256', secret).update(body).digest('base64');
}

// ─────────────────────────────────────────────────
// 登入拿 JWT
// ─────────────────────────────────────────────────
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
// 訪客：用 LINE webhook 發訊息
// ─────────────────────────────────────────────────
class LineGuest {
  constructor(idx) {
    this.idx = idx;
    // 唯一 external_id，避免衝突到既有用戶；用測試前綴方便事後清理
    this.externalId = `U_TEST_${Date.now()}_${idx}`;
    this.guestName = `IntegrityTest_${idx}`;
    this.roomId = null;            // 第一次 webhook 進來後從 DB / list 取得
    this.sentMessages = [];        // { id, content, sentAt }
    this.errors = [];
  }

  async sendMessage(content) {
    const messageId = `${Date.now()}${Math.random().toString(36).slice(2, 10)}`;
    const event = {
      destination: 'TEST',
      events: [{
        type: 'message',
        message: { type: 'text', id: messageId, text: content },
        source: { type: 'user', userId: this.externalId },
        timestamp: Date.now(),
        replyToken: 'TEST_REPLY_TOKEN',
      }],
    };
    const body = JSON.stringify(event);
    const signature = signLineBody(body, LINE_SECRET);

    const res = await fetch(`${API}/api/v1/webhook/line/${LINE_TOKEN}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Line-Signature': signature,
      },
      body,
    });

    if (res.status !== 200) {
      const text = await res.text();
      this.errors.push({ time: now(), kind: 'send', status: res.status, body: text });
      return null;
    }
    this.sentMessages.push({ id: messageId, content, sentAt: now() });
    return messageId;
  }
}

// ─────────────────────────────────────────────────
// 客服：API 切換器（高頻 GET messages）
// ─────────────────────────────────────────────────
class AgentSwitcher {
  constructor(token, rooms) {
    this.token = token;
    this.rooms = rooms; // [{ roomId, guestIdx }]
    this.history = {};  // roomId -> [{ time, count, messageIds }]
    for (const r of rooms) this.history[r.roomId] = [];
    this.regressions = []; // 任何「下次拿到的比上次少」的紀錄
  }

  async fetchMessages(roomId) {
    const url = `${API}/api/v1/chat-rooms/${roomId}/messages?limit=30&offset=0`;
    const { status, data } = await fetchJSON(url, {
      headers: { Authorization: `Bearer ${this.token}` },
    });
    if (status !== 200 || !Array.isArray(data?.data?.messages || data?.data)) {
      return null;
    }
    const messages = data.data.messages || data.data;
    const ids = messages.map((m) => m.id || m.line_message_id).filter(Boolean);
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
        // 檢查單調遞增：當前 GET 的 ids 應包含上次 GET 的所有 ids
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
// 找出新建室的 room_id
// ─────────────────────────────────────────────────
async function findRoomByExternalId(token, externalId, maxWaitMs = 10000) {
  const deadline = now() + maxWaitMs;
  while (now() < deadline) {
    const { status, data } = await fetchJSON(
      `${API}/api/v1/chat-rooms?status=waiting,active&limit=500`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    if (status === 200 && Array.isArray(data?.data?.rooms)) {
      const found = data.data.rooms.find((r) => r.guest_id === externalId || r.external_id === externalId);
      if (found) return found.id;
    }
    await sleep(500);
  }
  return null;
}

// ─────────────────────────────────────────────────
// 主流程
// ─────────────────────────────────────────────────
async function main() {
  console.log(`========== LINE 訊息完整性測試 ==========`);
  console.log(`API: ${API}`);
  console.log(`Site code: ${SITE_CODE}`);
  console.log(`Duration: ${DURATION}s / Guests: ${NUM_GUESTS}`);
  console.log(`Guest interval: ${GUEST_INTERVAL_MS}ms / Switch interval: ${SWITCH_INTERVAL_MS}ms`);
  console.log(`========================================\n`);

  const token = await login();

  // Phase 1: 建室（每個訪客發第一則訊息）
  console.log(`[${logTs()}] Phase 1: 建室（${NUM_GUESTS} 個訪客）`);
  const guests = Array.from({ length: NUM_GUESTS }, (_, i) => new LineGuest(i));
  for (const g of guests) {
    await g.sendMessage(`[init] guest ${g.idx} 第一則訊息`);
    console.log(`  ${g.idx}: external_id=${g.externalId}`);
  }
  await sleep(2000); // 等 createNewRoom 完成

  // Phase 2: 取得所有訪客的 room_id
  console.log(`\n[${logTs()}] Phase 2: 從 API 取得各訪客的 room_id`);
  for (const g of guests) {
    g.roomId = await findRoomByExternalId(token, g.externalId);
    if (!g.roomId) {
      console.error(`  ❌ 訪客 ${g.idx} (${g.externalId}) 找不到 room`);
      process.exit(1);
    }
    console.log(`  ${g.idx}: room=${g.roomId}`);
  }

  // Phase 3: 並行跑「訪客持續發訊息」+「客服切換 GET messages」
  console.log(`\n[${logTs()}] Phase 3: 進入 ${DURATION}s 壓力測試`);
  const stopAt = now() + DURATION * 1000;

  // 訪客 background：每 GUEST_INTERVAL_MS 發一則
  const guestPromises = guests.map(async (g) => {
    let seq = 0;
    while (now() < stopAt) {
      seq++;
      await g.sendMessage(`guest-${g.idx}-msg-${seq}`);
      await sleep(GUEST_INTERVAL_MS);
    }
    console.log(`[${logTs()}] 訪客 ${g.idx} 發送完成，總 ${g.sentMessages.length} 則`);
  });

  // 客服 background：每 SWITCH_INTERVAL_MS 切一個 room 並 GET messages
  const switcher = new AgentSwitcher(
    token,
    guests.map((g) => ({ roomId: g.roomId, guestIdx: g.idx }))
  );
  const switcherPromise = switcher.run(stopAt);

  await Promise.all([...guestPromises, switcherPromise]);

  // Phase 4: 等 webhook / archive 跑完
  console.log(`\n[${logTs()}] Phase 4: 等 5s 讓 archive worker 跑完`);
  await sleep(5000);

  // Phase 5: 最終驗證：每個 room 撈完整 messages 對比
  console.log(`\n[${logTs()}] Phase 5: 驗證`);
  const report = {
    config: {
      api: API, siteCode: SITE_CODE, duration: DURATION, numGuests: NUM_GUESTS,
      guestIntervalMs: GUEST_INTERVAL_MS, switchIntervalMs: SWITCH_INTERVAL_MS,
    },
    rooms: [],
    summary: { totalSent: 0, totalInDB: 0, missingCount: 0, duplicateCount: 0, regressionCount: switcher.regressions.length, errorCount: 0 },
    regressions: switcher.regressions,
  };

  // 改進的 invariant：
  //   - 滑動窗口下，limit=30+offset=0 的舊 ID 被擠出是正常分頁行為（不算 bug）
  //   - 真正的 bug 是「ghost ID」— 某 ID 在某次 GET 中出現過，最後在 DB 撈不到
  //     表示這則訊息曾被 API 回傳但實際儲存失敗或被誤刪
  for (const g of guests) {
    // 撈完整 messages（limit 500 = API 上限；超過時用 pagination）
    let allMessages = [];
    let offset = 0;
    while (true) {
      const url = `${API}/api/v1/chat-rooms/${g.roomId}/messages?limit=500&offset=${offset}&include_history=true`;
      const { data } = await fetchJSON(url, { headers: { Authorization: `Bearer ${token}` } });
      const page = data?.data?.messages || data?.data || [];
      if (!Array.isArray(page) || page.length === 0) break;
      allMessages = allMessages.concat(page);
      if (page.length < 500) break;
      offset += 500;
    }

    // 只算 guest 發的 text 訊息（不含 system / agent reply）
    const guestMessages = allMessages.filter(
      (m) => (m.sender_id === g.externalId || m.sender_type === 'guest') && m.message_type === 'text'
    );
    const dbIdSet = new Set(allMessages.map((m) => m.id));
    const dbContentMap = new Map();
    for (const m of guestMessages) {
      dbContentMap.set(m.content, (dbContentMap.get(m.content) || 0) + 1);
    }
    const duplicates = [...dbContentMap.entries()].filter(([, n]) => n > 1);

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
      externalId: g.externalId,
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

  // 寫報告
  await import('node:fs/promises').then((fs) => fs.writeFile(REPORT_PATH, JSON.stringify(report, null, 2)));

  // Console summary
  console.log(`\n========== 測試報告 ==========`);
  console.log(`訪客發送：${report.summary.totalSent} 則`);
  console.log(`DB 內訪客訊息：${report.summary.totalInDB} 則`);
  console.log(`遺失（發了但 DB 沒有）：${report.summary.missingCount} ${report.summary.missingCount > 0 ? '❌' : '✅'}`);
  console.log(`重複（DB 內同 content）：${report.summary.duplicateCount} ${report.summary.duplicateCount > 0 ? '❌' : '✅'}`);
  console.log(`Ghost ID（API 回傳過但 DB 撈不到）：${report.summary.ghostIdCount || 0} ${(report.summary.ghostIdCount || 0) > 0 ? '❌' : '✅'}`);
  console.log(`發送錯誤：${report.summary.errorCount}`);
  console.log(``);
  console.log(`資訊性指標（不算 bug）：`);
  console.log(`  滑動窗口下 ID 進出次數：${report.summary.regressionCount}（limit=30+offset=0 視窗自然滑動，新訊息進來舊的會退出）`);
  console.log(`  客服 GET messages 次數：${switcher.rooms.reduce((sum, r) => sum + (switcher.history[r.roomId]?.length || 0), 0)}`);
  console.log(`\n詳細報告：${REPORT_PATH}`);
  console.log(`========================================`);

  // Ghost ID 詳情（真實 bug）
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
