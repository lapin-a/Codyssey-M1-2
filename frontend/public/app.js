"use strict";

const API = (window.API_BASE_URL || "http://localhost:8000").replace(/\/+$/, "");
const $ = (sel) => document.querySelector(sel);

const CURRENCIES = {
  USD: { name: "달러", unit: "1달러" },
  EUR: { name: "유로", unit: "1유로" },
  JPY: { name: "엔", unit: "100엔" },
  CNY: { name: "위안", unit: "1위안" },
  GBP: { name: "파운드", unit: "1파운드" },
};
const PAGE_SIZE = 100;

const state = {
  currency: "USD",
  conversationId: null,
  data: [],
  shown: PAGE_SIZE,
  rangeYears: 0,
  editingId: null,
  sending: false,
};

// ---------- 공통 ----------
async function request(path, options = {}, timeoutMs = 70000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(API + path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      signal: controller.signal,
    });
    if (!res.ok) {
      let detail = `요청 실패 (${res.status})`;
      try {
        const body = await res.json();
        if (typeof body.detail === "string") detail = body.detail;
        else if (Array.isArray(body.detail)) detail = body.detail.map((d) => d.msg).join(", ");
      } catch (_) {}
      throw new Error(detail);
    }
    return res.status === 204 ? null : res.json();
  } catch (err) {
    if (err.name === "AbortError") throw new Error("서버 응답이 너무 늦습니다. 잠시 후 다시 시도해 주세요.");
    if (err instanceof TypeError) throw new Error("서버에 연결할 수 없습니다. (API 주소/CORS 설정 확인)");
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

let toastTimer;
function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2600);
}

function banner(message, isError = false) {
  const el = $("#banner");
  if (!message) return el.classList.add("hidden");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.classList.remove("hidden");
}

const fmt = (n, digits = 2) =>
  n == null ? "-" : Number(n).toLocaleString("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// ---------- 콜드스타트 대응 ----------
// Render 무료 플랜은 15분 동안 요청이 없으면 잠들고, 첫 요청에 30~60초가 걸린다.
async function wakeServer() {
  const slowTimer = setTimeout(
    () => banner("⏳ 백엔드 서버를 깨우는 중입니다. 무료 서버라 첫 접속에 최대 1분 정도 걸릴 수 있어요."),
    2500
  );
  const started = Date.now();
  while (Date.now() - started < 120000) {
    try {
      await request("/health", {}, 15000);
      clearTimeout(slowTimer);
      banner(null);
      return true;
    } catch (_) {
      await new Promise((r) => setTimeout(r, 3000));
    }
  }
  clearTimeout(slowTimer);
  banner("⚠️ 서버에 연결하지 못했습니다. 새로고침하거나 잠시 후 다시 시도해 주세요.", true);
  return false;
}

// ---------- 요약 ----------
function renderSummary(s) {
  $("#sPeriod").textContent = s.count ? `${s.period_start} ~ ${s.period_end}` : "-";
  $("#sCount").textContent = `${s.count}개`;
  $("#sMean").textContent = s.count ? `${fmt(s.mean)}원` : "-";
  $("#sMaxMin").textContent = s.count ? `${fmt(s.max)} / ${fmt(s.min)}` : "-";
  const sign = (n) => (n > 0 ? "+" : "") + n;
  $("#sLatestLabel").textContent = `최신값 (${s.unit}, 1년 변화)`;
  $("#sLatest").textContent = s.count
    ? `${fmt(s.latest_value)}원` + (s.change_1y_pct != null ? ` (${sign(s.change_1y_pct)}%)` : "")
    : "-";
  const trend = $("#sTrend");
  const icon = { 증가: "▲", 감소: "▼", 유지: "■" }[s.trend] || "";
  trend.textContent = `${icon} ${s.trend}`;
  trend.title = s.trend_detail || "";
  trend.className = { 증가: "trend-up", 감소: "trend-down" }[s.trend] || "trend-flat";
}

async function loadSummary() {
  try {
    renderSummary(await request(`/api/data/summary?currency=${state.currency}`));
  } catch (err) {
    toast(`요약을 불러오지 못했습니다: ${err.message}`, true);
  }
}

// ---------- 채팅 ----------
function clearMessages() {
  $("#messages").querySelectorAll(".msg, .tools").forEach((el) => el.remove());
  $("#chatEmpty").classList.remove("hidden");
}

function addMessage(role, content) {
  $("#chatEmpty").classList.add("hidden");
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = content;
  $("#messages").appendChild(el);
  el.scrollIntoView({ block: "end" });
  return el;
}

function addToolInfo(calls) {
  if (!calls || !calls.length) return;
  const el = document.createElement("div");
  el.className = "tools";
  el.append("🔧 사용한 도구: ");
  calls.forEach((c, i) => {
    const code = document.createElement("code");
    code.textContent = c.name;
    code.title = c.reason || JSON.stringify(c.arguments);
    if (i) el.append(" ");
    el.append(code);
  });
  $("#messages").appendChild(el);
}

function addTyping() {
  const el = addMessage("assistant", "");
  el.innerHTML = '<span class="typing"><span></span><span></span><span></span><em>데이터를 확인하고 답변을 작성하는 중…</em></span>';
  return el;
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message || state.sending) return;
  state.sending = true;
  $("#sendBtn").disabled = true;
  $("#chatInput").value = "";
  autoResize();

  addMessage("user", message);
  const typing = addTyping();
  try {
    const res = await request("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, conversation_id: state.conversationId }),
    });
    typing.remove();
    addMessage("assistant", res.reply);
    addToolInfo(res.tool_calls);
    const current = res.summaries.find((s) => s.currency === state.currency);
    if (current) renderSummary(current);
    state.conversationId = res.conversation_id;
    loadConversations();
  } catch (err) {
    typing.remove();
    addMessage("error", `⚠️ ${err.message}`);
  } finally {
    state.sending = false;
    $("#sendBtn").disabled = false;
    $("#chatInput").focus();
  }
}

function autoResize() {
  const ta = $("#chatInput");
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
}

// ---------- 대화 기록 ----------
async function loadConversations() {
  const list = $("#convList");
  try {
    const convs = await request("/api/conversations");
    list.replaceChildren();
    if (!convs.length) {
      const li = document.createElement("li");
      li.className = "conv-empty";
      li.textContent = "아직 저장된 대화가 없습니다.";
      list.appendChild(li);
      return;
    }
    for (const c of convs) {
      const li = document.createElement("li");
      li.className = "conv-item" + (c.id === state.conversationId ? " active" : "");
      li.innerHTML = '<div class="meta"><div class="title"></div><div class="sub"></div></div><button class="del" title="삭제">✕</button>';
      li.querySelector(".title").textContent = c.title;
      li.querySelector(".sub").textContent = `${formatTime(c.updated_at)} · ${c.message_count}개 메시지`;
      li.addEventListener("click", () => openConversation(c.id));
      li.querySelector(".del").addEventListener("click", (e) => {
        e.stopPropagation();
        deleteConversation(c.id, c.title);
      });
      list.appendChild(li);
    }
  } catch (err) {
    toast(`대화 목록을 불러오지 못했습니다: ${err.message}`, true);
  }
}

async function openConversation(id) {
  try {
    const conv = await request(`/api/conversations/${encodeURIComponent(id)}`);
    state.conversationId = conv.id;
    clearMessages();
    conv.messages.forEach((m) => addMessage(m.role, m.content));
    loadConversations();
    switchTab("chat");
  } catch (err) {
    toast(`대화를 불러오지 못했습니다: ${err.message}`, true);
  }
}

async function deleteConversation(id, title) {
  if (!confirm(`"${title}" 대화를 삭제할까요?`)) return;
  try {
    await request(`/api/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (state.conversationId === id) newChat();
    loadConversations();
    toast("대화를 삭제했습니다.");
  } catch (err) {
    toast(err.message, true);
  }
}

function newChat() {
  state.conversationId = null;
  clearMessages();
  loadConversations();
  $("#chatInput").focus();
}

// ---------- 데이터 관리 ----------
async function loadData(flashId) {
  try {
    const res = await request(`/api/data?currency=${state.currency}`);
    state.data = res.items;
    if (!flashId) state.shown = PAGE_SIZE;
    renderTable(flashId);
    drawChart();
  } catch (err) {
    toast(`데이터를 불러오지 못했습니다: ${err.message}`, true);
  }
}

function renderTable(flashId) {
  const body = $("#dataBody");
  body.replaceChildren();
  $("#dataCount").textContent = `(${state.data.length}개)`;
  // 최신 날짜가 위로 오도록 역순 표시, 많으면 PAGE_SIZE씩 나눠 그린다
  const rows = [...state.data].reverse();
  if (flashId) {
    const idx = rows.findIndex((r) => r.id === flashId);
    if (idx >= state.shown) state.shown = idx + 1;
  }
  $("#moreBtn").classList.toggle("hidden", rows.length <= state.shown);
  $("#moreBtn").textContent = `더 보기 (${state.shown.toLocaleString()} / ${rows.length.toLocaleString()})`;
  for (const item of rows.slice(0, state.shown)) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td></td><td class="num"></td><td></td><td class="actions"><button class="btn small">수정</button> <button class="btn small danger">삭제</button></td>';
    tr.children[0].textContent = item.date;
    tr.children[1].textContent = fmt(item.value);
    tr.children[2].textContent = item.memo || "";
    const [editBtn, delBtn] = tr.querySelectorAll("button");
    editBtn.addEventListener("click", () => startEdit(item));
    delBtn.addEventListener("click", () => deleteData(item));
    if (item.id === flashId) tr.classList.add("flash");
    body.appendChild(tr);
  }
  if (flashId) body.querySelector(".flash")?.scrollIntoView({ block: "nearest" });
}

function startEdit(item) {
  state.editingId = item.id;
  $("#fDate").value = item.date;
  $("#fCurrency").value = item.currency;
  $("#fValue").value = item.value;
  $("#fMemo").value = item.memo || "";
  $("#formTitle").textContent = `데이터 수정 (${item.date})`;
  $("#fSubmit").textContent = "수정 저장";
  $("#fCancel").classList.remove("hidden");
  $("#dataForm").scrollIntoView({ behavior: "smooth", block: "center" });
}

function resetForm() {
  state.editingId = null;
  $("#dataForm").reset();
  $("#fDate").value = new Date().toISOString().slice(0, 10);
  $("#fCurrency").value = state.currency;
  $("#formTitle").textContent = "새 데이터 추가";
  $("#fSubmit").textContent = "추가";
  $("#fCancel").classList.add("hidden");
}

async function submitData(e) {
  e.preventDefault();
  const payload = {
    date: $("#fDate").value,
    currency: $("#fCurrency").value,
    value: Number($("#fValue").value),
    memo: $("#fMemo").value.trim(),
  };
  const btn = $("#fSubmit");
  btn.disabled = true;
  try {
    let saved;
    if (state.editingId) {
      saved = await request(`/api/data/${encodeURIComponent(state.editingId)}`, { method: "PUT", body: JSON.stringify(payload) });
      toast(`✅ ${saved.date} 데이터를 수정했습니다.`);
    } else {
      saved = await request("/api/data", { method: "POST", body: JSON.stringify(payload) });
      toast(`✅ ${saved.date} 데이터를 추가했습니다.`);
    }
    if (saved.currency !== state.currency) selectCurrency(saved.currency, false);
    resetForm();
    await Promise.all([loadData(saved.id), loadSummary(), loadStatistics()]);
  } catch (err) {
    toast(`저장 실패: ${err.message}`, true);
  } finally {
    btn.disabled = false;
  }
}

async function deleteData(item) {
  if (!confirm(`${item.date} (${fmt(item.value)}원) 데이터를 삭제할까요?`)) return;
  try {
    await request(`/api/data/${encodeURIComponent(item.id)}`, { method: "DELETE" });
    toast(`🗑️ ${item.date} 데이터를 삭제했습니다.`);
    if (state.editingId === item.id) resetForm();
    await Promise.all([loadData(), loadSummary(), loadStatistics()]);
  } catch (err) {
    toast(`삭제 실패: ${err.message}`, true);
  }
}

async function exportData(format) {
  try {
    const res = await fetch(`${API}/api/data/export?format=${format}&currency=${state.currency}`);
    if (!res.ok) throw new Error(`요청 실패 (${res.status})`);
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: `${state.currency.toLowerCase()}_krw.${format}` });
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    toast(`내보내기 실패: ${err.message}`, true);
  }
}

async function loadStatistics() {
  try {
    const s = await request(`/api/data/statistics?currency=${state.currency}`);
    const items = [
      ["표준편차", s.std != null ? `${fmt(s.std)}원` : "-"],
      ["중앙값", s.median != null ? `${fmt(s.median)}원` : "-"],
      ["일간 변동성", s.daily_volatility_pct != null ? `${s.daily_volatility_pct}%` : "-"],
      ["최대 낙폭(MDD)", s.max_drawdown_pct != null ? `${s.max_drawdown_pct}%` : "-"],
      ["7일 이동평균", s.ma7 != null ? `${fmt(s.ma7)}원` : "-"],
      ["30일 이동평균", s.ma30 != null ? `${fmt(s.ma30)}원` : "-"],
    ];
    const box = $("#extraStats");
    box.replaceChildren();
    for (const [label, value] of items) {
      const div = document.createElement("div");
      div.innerHTML = "<span></span><b></b>";
      div.children[0].textContent = label;
      div.children[1].textContent = value;
      box.appendChild(div);
    }
  } catch (err) {
    toast(`통계를 불러오지 못했습니다: ${err.message}`, true);
  }
}

// ---------- 차트 (canvas 직접 그리기) ----------
const chart = { points: [], area: null };

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function movingAverage(values, n) {
  return values.map((_, i) => {
    if (i < n - 1) return null;
    let sum = 0;
    for (let j = i - n + 1; j <= i; j++) sum += values[j];
    return sum / n;
  });
}

function drawChart() {
  const canvas = $("#chart");
  if (!canvas.offsetWidth) return; // 탭이 숨겨져 있으면 나중에 그린다
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.offsetWidth;
  const H = canvas.offsetHeight;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  let data = state.data;
  if (state.rangeYears && data.length) {
    const last = new Date(data[data.length - 1].date);
    last.setFullYear(last.getFullYear() - state.rangeYears);
    const cutoff = last.toISOString().slice(0, 10);
    data = data.filter((d) => d.date >= cutoff);
  }
  // 기간이 길면 7일 대신 30일 이동평균이 추세를 더 잘 보여준다
  const maN = data.length > 800 ? 30 : 7;
  $("#maLabel").textContent = `${maN}일 이동평균`;
  $("#chartTitle").textContent = `${CURRENCIES[state.currency].name} 환율 추이 (${CURRENCIES[state.currency].unit}당 원)`;
  if (data.length < 2) {
    ctx.fillStyle = cssVar("--muted");
    ctx.font = "14px sans-serif";
    ctx.fillText("그래프를 그리려면 데이터가 2개 이상 필요합니다.", 16, 30);
    return;
  }

  const pad = { l: 56, r: 12, t: 12, b: 28 };
  const area = { x: pad.l, y: pad.t, w: W - pad.l - pad.r, h: H - pad.t - pad.b };
  const values = data.map((d) => d.value);
  const ma = movingAverage(values, maN);
  let min = Math.min(...values);
  let max = Math.max(...values);
  const margin = (max - min) * 0.08 || 1;
  min -= margin;
  max += margin;
  const x = (i) => area.x + (i / (data.length - 1)) * area.w;
  const y = (v) => area.y + (1 - (v - min) / (max - min)) * area.h;

  // 격자와 y축 눈금
  ctx.strokeStyle = cssVar("--grid");
  ctx.fillStyle = cssVar("--muted");
  ctx.font = "11px sans-serif";
  ctx.lineWidth = 1;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let k = 0; k <= 4; k++) {
    const v = min + ((max - min) * k) / 4;
    const yy = Math.round(y(v)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(area.x, yy);
    ctx.lineTo(area.x + area.w, yy);
    ctx.stroke();
    ctx.fillText(Math.round(v).toLocaleString("ko-KR"), area.x - 8, yy);
  }

  // x축: 2년 넘게 보이면 연도, 아니면 월 시작 지점에 라벨
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const byYear = data.length > 520;
  let lastKey = "";
  let lastX = -Infinity;
  data.forEach((d, i) => {
    const key = byYear ? d.date.slice(0, 4) : d.date.slice(0, 7);
    if (key !== lastKey && lastKey && x(i) - lastX > 48) {
      ctx.fillText(byYear ? key : `${d.date.slice(2, 4)}.${d.date.slice(5, 7)}`, x(i), area.y + area.h + 8);
      lastX = x(i);
    }
    lastKey = key;
  });

  const line = (vals, color, width) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineJoin = "round";
    ctx.beginPath();
    let started = false;
    vals.forEach((v, i) => {
      if (v == null) return;
      if (!started) ctx.moveTo(x(i), y(v));
      else ctx.lineTo(x(i), y(v));
      started = true;
    });
    ctx.stroke();
  };
  line(values, cssVar("--line-1"), 1.5);
  line(ma, cssVar("--line-2"), 2);

  chart.area = area;
  chart.points = data.map((d, i) => ({ x: x(i), y: y(d.value), d, ma: ma[i] }));
}

function onChartHover(e) {
  const tip = $("#tooltip");
  if (!chart.points.length) return;
  const rect = e.currentTarget.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  let best = chart.points[0];
  for (const p of chart.points) if (Math.abs(p.x - mx) < Math.abs(best.x - mx)) best = p;
  tip.textContent = `${best.d.date}  ${fmt(best.d.value)}원` + (best.ma != null ? ` · 이동평균 ${fmt(best.ma)}` : "");
  tip.style.left = `${best.x}px`;
  tip.style.top = `${best.y}px`;
  tip.classList.remove("hidden");
}

// ---------- 통화 선택 ----------
function selectCurrency(code, reload = true) {
  if (!CURRENCIES[code]) return;
  state.currency = code;
  document.querySelectorAll(".cur").forEach((b) => b.classList.toggle("active", b.dataset.cur === code));
  try {
    localStorage.setItem("currency", code);
  } catch (_) {}
  if (!state.editingId) $("#fCurrency").value = code;
  if (reload) Promise.all([loadSummary(), loadData(), loadStatistics()]);
}

// ---------- 탭/테마 ----------
function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $("#tab-chat").classList.toggle("hidden", name !== "chat");
  $("#tab-data").classList.toggle("hidden", name !== "data");
  history.replaceState(null, "", name === "data" ? "#data" : location.pathname);
  if (name === "data") drawChart();
}

function currentTheme() {
  const set = document.documentElement.dataset.theme;
  if (set) return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function updateThemeIcon() {
  $("#themeToggle").textContent = currentTheme() === "dark" ? "☀️" : "🌙";
}

function toggleTheme() {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try {
    localStorage.setItem("theme", next);
  } catch (_) {}
  updateThemeIcon();
  drawChart();
}

// ---------- 초기화 ----------
function bindEvents() {
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.tab)));
  $("#themeToggle").addEventListener("click", toggleTheme);
  $("#newChat").addEventListener("click", newChat);
  $("#chatForm").addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage($("#chatInput").value);
  });
  $("#chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      sendMessage($("#chatInput").value);
    }
  });
  $("#chatInput").addEventListener("input", autoResize);
  document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => sendMessage(c.textContent)));
  $("#dataForm").addEventListener("submit", submitData);
  $("#fCancel").addEventListener("click", resetForm);
  document.querySelectorAll("[data-export]").forEach((b) => b.addEventListener("click", () => exportData(b.dataset.export)));
  document.querySelectorAll(".cur").forEach((b) => b.addEventListener("click", () => selectCurrency(b.dataset.cur)));
  document.querySelectorAll("#rangeSeg button").forEach((b) =>
    b.addEventListener("click", () => {
      state.rangeYears = Number(b.dataset.range);
      document.querySelectorAll("#rangeSeg button").forEach((x) => x.classList.toggle("active", x === b));
      drawChart();
    })
  );
  $("#moreBtn").addEventListener("click", () => {
    state.shown += PAGE_SIZE;
    renderTable();
  });
  const canvas = $("#chart");
  canvas.addEventListener("mousemove", onChartHover);
  canvas.addEventListener("mouseleave", () => $("#tooltip").classList.add("hidden"));
  window.addEventListener("resize", drawChart);
}

async function init() {
  bindEvents();
  updateThemeIcon();
  try {
    const saved = localStorage.getItem("currency");
    if (saved) selectCurrency(saved, false);
  } catch (_) {}
  resetForm();
  if (location.hash === "#data") switchTab("data");
  if (!(await wakeServer())) return;
  await Promise.all([loadSummary(), loadConversations(), loadData(), loadStatistics()]);
}

init();
