const THEME_PREF_KEY = "acm-tracker-theme-preference";
const THEME_LEGACY_KEY = "acm-tracker-theme";

function readThemePreference() {
  try {
    let pref = localStorage.getItem(THEME_PREF_KEY);
    if (!pref) {
      const old = localStorage.getItem(THEME_LEGACY_KEY);
      if (old === "dark") pref = "dark";
      else if (old === "light") pref = "light";
      else if (old) pref = "light";
    }
    if (pref !== "light" && pref !== "dark" && pref !== "system") pref = "light";
    return pref;
  } catch (e) {
    return "light";
  }
}

function resolveThemePreference(pref) {
  if (pref === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return pref === "dark" ? "dark" : "light";
}

const heatmapEl = document.getElementById("heatmap");
/** 当前选中的贡献格，避免每次 querySelectorAll 扫全图 */
let contribSelectedEl = null;
/** 日期键 → 格子元素，避免 selectContribDay 每次 querySelector 扫全图 */
let heatmapDayByDate = new Map();
const tagsChart = echarts.init(document.getElementById("tags-chart"));
/** 饼图在默认隐藏的「知识点」面板内初始化会得到 0 尺寸；改为首次需要显示时再 init。 */
let tagsPieChart = null;
let cachedTagsData = [];

const syncButton = document.getElementById("sync-button");
const forceSyncButton = document.getElementById("force-sync-button");
const cancelSyncButton = document.getElementById("cancel-sync-button");
const repairSyncButton = document.getElementById("repair-sync-button");
let syncAbortController = null;
const installButton = document.getElementById("install-button");
const saveConfigButton = document.getElementById("save-config-button");
const prevYearButton = document.getElementById("prev-year-button");
const nextYearButton = document.getElementById("next-year-button");
const sourceSelect = document.getElementById("source-select");
const yearInput = document.getElementById("year-input");
const syncStatus = document.getElementById("sync-status");
const configBadge = document.getElementById("config-badge");
const syncBadge = document.getElementById("sync-badge");
const selectedDate = document.getElementById("selected-date");
const problemList = document.getElementById("problem-list");
const syncRunsBody = document.getElementById("sync-runs-body");
const unsolvedSummary = document.getElementById("unsolved-summary");
const unsolvedList = document.getElementById("unsolved-list");
const navButtons = Array.from(document.querySelectorAll("[data-nav-view]"));
const viewPanels = Array.from(document.querySelectorAll("[data-view]"));

const weeklyAc = document.getElementById("weekly-ac");
const weeklyAttempt = document.getElementById("weekly-attempt");
const weeklyAccuracy = document.getElementById("weekly-accuracy");
const weeklyRange = document.getElementById("weekly-range");
const reportContent = document.getElementById("report-content");
const totalSubmissions = document.getElementById("total-submissions");
const totalAc = document.getElementById("total-ac");
const activeDays = document.getElementById("active-days");
const lastSync = document.getElementById("last-sync");
const periodButtons = Array.from(document.querySelectorAll("[data-period]"));
const tagSelected = document.getElementById("tag-selected");
const tagProblemList = document.getElementById("tag-problem-list");
const tagProblemsTitle = document.getElementById("tag-problems-title");
const knowledgeOjFilter = document.getElementById("knowledge-oj-filter");
const problemsOjFilter = document.getElementById("problems-oj-filter");

const cfHandleInput = document.getElementById("cf-handle");
const cfCookieKvInput = document.getElementById("cf-cookie-kv");
const luoguUidInput = document.getElementById("luogu-uid");
const luoguUsernameInput = document.getElementById("luogu-username");
const luoguCkClientIdInput = document.getElementById("luogu-ck-client-id");
const luoguCkUidInput = document.getElementById("luogu-ck-uid");
const luoguCookieKvInput = document.getElementById("luogu-cookie-kv");
const nowcoderUidInput = document.getElementById("nowcoder-uid");
const nowcoderCookieKvInput = document.getElementById("nowcoder-cookie-kv");
const atcoderUsernameInput = document.getElementById("atcoder-username");
const syncIntervalInput = document.getElementById("sync-interval");

let heatmapLookup = new Map();
let deferredPrompt = null;
let activePeriod = "day";
let activeView = "overview";
const BEIJING_LOCALE = "zh-CN";
const BEIJING_TIMEZONE = "Asia/Shanghai";
const DEFAULT_VIEW_RAW = document.body.dataset.defaultView || "overview";
// 热力图已并入总览；旧模板仍可能传 data-default-view="heatmap"；「同步」页已改为「设置」
const DEFAULT_VIEW =
  DEFAULT_VIEW_RAW === "heatmap"
    ? "overview"
    : DEFAULT_VIEW_RAW === "sync"
      ? "settings"
      : DEFAULT_VIEW_RAW;

function readChartTheme() {
  const s = getComputedStyle(document.documentElement);
  const dark = document.documentElement.getAttribute("data-theme") === "dark";
  const pick = (name, fallback) => {
    const v = s.getPropertyValue(name).trim();
    return v || fallback;
  };
  return {
    text: pick("--chart-text", dark ? "#a1b0c4" : "#475569"),
    /** 与 themes.css --chart-bg 一致；深色为透明以融入卡片 */
    chartBg: pick("--chart-bg", "transparent"),
    barA: pick("--chart-bar-a", "#2f6c5f"),
    barB: pick("--chart-bar-b", "#d98d57"),
    pieBorder: pick("--chart-pie-border", dark ? "#1e212c" : "#f8f4eb"),
    gridLine: pick("--chart-grid", dark ? "rgba(248, 250, 252, 0.08)" : "rgba(118, 99, 79, 0.12)"),
    calBorder: pick("--chart-cal-border", dark ? "#30363d" : "#d0d7de"),
    tooltipBg: pick("--chart-tooltip-bg", dark ? "rgba(28, 31, 42, 0.96)" : "rgba(255, 255, 255, 0.97)"),
    tooltipBorder: pick("--chart-tooltip-border", dark ? "rgba(248, 250, 252, 0.1)" : "rgba(15, 23, 42, 0.1)"),
    tooltipFg: pick("--chart-tooltip-fg", dark ? "#f1f5f9" : "#0b1220"),
    tooltipShadow: pick(
      "--chart-tooltip-shadow",
      dark ? "0 12px 32px rgba(0, 0, 0, 0.55)" : "0 8px 24px rgba(15, 23, 42, 0.1)",
    ),
  };
}

function syncThemeColorMeta() {
  const meta = document.getElementById("meta-theme-color");
  const c = getComputedStyle(document.documentElement).getPropertyValue("--meta-theme-color").trim();
  if (meta && c) {
    meta.setAttribute("content", c);
  }
}

function applyTheme(themePreference, refreshCharts = true) {
  const pref =
    themePreference === "dark" || themePreference === "light" || themePreference === "system"
      ? themePreference
      : "light";
  const resolved = resolveThemePreference(pref);
  document.documentElement.setAttribute("data-theme", resolved);
  try {
    localStorage.setItem(THEME_PREF_KEY, pref);
  } catch (e) {}
  syncThemeColorMeta();
  if (refreshCharts) {
    refreshDashboard().catch(() => {});
  }
}

function currentYear() {
  return Number(yearInput.value) || new Date().getFullYear();
}

function ensureTagsPieChart() {
  const el = document.getElementById("tags-pie-chart");
  if (!el) {
    return null;
  }
  if (!tagsPieChart) {
    tagsPieChart = echarts.init(el);
    tagsPieChart.on("click", (params) => {
      if (!params.name) return;
      loadTagProblems(params.name);
    });
  }
  return tagsPieChart;
}

function buildTagsPieOption(data) {
  const ct = readChartTheme();
  const seriesData = data.map((item, index) => ({
    value: item.count,
    name: item.tag,
    itemStyle: {
      color: index % 2 === 0 ? ct.barA : ct.barB,
    },
  }));
  return {
    tooltip: { trigger: "item" },
    legend: {
      show: seriesData.length > 0,
      type: "scroll",
      orient: "horizontal",
      bottom: 4,
      left: "center",
      width: "92%",
      height: 52,
      textStyle: { color: ct.text, fontSize: 11 },
      pageIconColor: ct.text,
      pageTextStyle: { color: ct.text },
    },
    series: [
      {
        type: "pie",
        radius: ["28%", "52%"],
        center: ["50%", "42%"],
        itemStyle: {
          borderColor: ct.pieBorder,
          borderWidth: 2,
        },
        label: {
          color: ct.text,
          formatter: "{b}",
          fontSize: 11,
        },
        labelLine: {
          length: 10,
          length2: 8,
        },
        data: seriesData,
      },
    ],
  };
}

function syncTagsPieChart() {
  const chart = ensureTagsPieChart();
  if (!chart) {
    return;
  }
  chart.setOption(buildTagsPieOption(cachedTagsData), { notMerge: true });
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      chart.resize();
    });
  });
}

const VIEW_PATH = {
  overview: "/",
  knowledge: "/knowledge",
  problems: "/problems",
  settings: "/settings",
};

function switchView(view, updateHistory = true) {
  activeView = view;
  navButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.navView === view);
  });
  viewPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.view === view);
  });
  if (updateHistory) {
    const path = VIEW_PATH[view];
    if (path) {
      history.pushState({ view }, "", path);
    }
  }
  requestAnimationFrame(() => {
    if (view === "knowledge") {
      tagsChart.resize();
      syncTagsPieChart();
      setTimeout(() => {
        if (tagsPieChart) {
          tagsPieChart.resize();
        }
      }, 80);
    }
  });
}

/** @param {HTMLSelectElement | null} el */
function ojQueryFromSelect(el) {
  const v = el && el.value ? String(el.value).trim() : "";
  return v ? `?oj=${encodeURIComponent(v)}` : "";
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function formatDateTime(value) {
  if (!value) return "时间未知";
  return new Date(value).toLocaleString(BEIJING_LOCALE, {
    timeZone: BEIJING_TIMEZONE,
    hour12: false,
  });
}

function formatDate(value) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString(BEIJING_LOCALE, { timeZone: BEIJING_TIMEZONE });
}

function problemUrl(problem) {
  if (problem.oj_source === "luogu") {
    return `https://www.luogu.com.cn/problem/${problem.problem_id}`;
  }
  if (problem.oj_source === "codeforces") {
    const match = String(problem.problem_id).match(/^(\d+)([A-Za-z0-9]+)$/);
    if (match) {
      return `https://codeforces.com/problemset/problem/${match[1]}/${match[2]}`;
    }
  }
  if (problem.oj_source === "nowcoder") {
    return `https://ac.nowcoder.com/acm/problem/${problem.problem_id}`;
  }
  if (problem.oj_source === "qoj") {
    return `https://qoj.ac/problem/${problem.problem_id}`;
  }
  if (problem.oj_source === "atcoder") {
    const pid = String(problem.problem_id || "");
    const contest = pid.includes("_") ? pid.slice(0, pid.indexOf("_")) : "";
    if (contest && pid) {
      return `https://atcoder.jp/contests/${contest}/tasks/${pid}`;
    }
    return `https://atcoder.jp/home`;
  }
  return "#";
}

function renderProblemList(dateKey) {
  const entry = heatmapLookup.get(dateKey);
  selectedDate.textContent = entry ? `${dateKey} 共 AC ${entry.ac_count} 题` : `日期 ${dateKey} 暂无 AC 记录`;
  problemList.innerHTML = "";

  if (!entry || !entry.problems.length) {
    const empty = document.createElement("li");
    empty.textContent = "这一天还没有 AC 题目记录。";
    problemList.appendChild(empty);
    return;
  }

  entry.problems.forEach((problem) => {
    const item = document.createElement("li");
    item.innerHTML = `
      <a class="problem-link" href="${problemUrl(problem)}" target="_blank" rel="noreferrer">
        <strong>${problem.problem_id} ${problem.problem_name}</strong>
        <div class="status"><span class="oj-tag">${problem.oj_source}</span> · ${problem.status} · 难度 <span class="diff-label">${problem.difficulty || "—"}</span></div>
        <div class="meta">${formatDateTime(problem.submit_time)}</div>
      </a>
    `;
    problemList.appendChild(item);
  });
}

function nextBeijingDate(dateKey) {
  const t = Date.parse(`${dateKey}T12:00:00+08:00`) + 86400000;
  return new Intl.DateTimeFormat("en-CA", { timeZone: BEIJING_TIMEZONE }).format(new Date(t));
}

function prevBeijingDate(dateKey) {
  const t = Date.parse(`${dateKey}T12:00:00+08:00`) - 86400000;
  return new Intl.DateTimeFormat("en-CA", { timeZone: BEIJING_TIMEZONE }).format(new Date(t));
}

/** 周日=0 … 周六=6（常见贡献图行序，上海日历日） */
function beijingWeekdaySun0(dateKey) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: BEIJING_TIMEZONE,
    weekday: "short",
  }).formatToParts(new Date(`${dateKey}T12:00:00+08:00`));
  const w = parts.find((p) => p.type === "weekday").value;
  const map = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  return map[w] ?? 0;
}

function sundayOnOrBefore(dateKey) {
  let d = dateKey;
  let n = beijingWeekdaySun0(d);
  while (n > 0) {
    d = prevBeijingDate(d);
    n -= 1;
  }
  return d;
}

function saturdayOnOrAfter(dateKey) {
  let d = dateKey;
  let n = beijingWeekdaySun0(d);
  while (n < 6) {
    d = nextBeijingDate(d);
    n += 1;
  }
  return d;
}

function compareDateKeys(a, b) {
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

function contribLevel(n, maxAc) {
  if (n <= 0) return 0;
  if (maxAc <= 0) return 1;
  const r = n / maxAc;
  if (r <= 0.25) return 1;
  if (r <= 0.5) return 2;
  if (r <= 0.75) return 3;
  return 4;
}

function monthLabelForWeek(weekCells, year) {
  const y = `${year}`;
  for (const c of weekCells) {
    if (!c.dateKey.startsWith(`${y}-`)) continue;
    const [, mo, day] = c.dateKey.split("-");
    if (parseInt(day, 10) === 1) {
      return `${parseInt(mo, 10)}月`;
    }
  }
  return "";
}

function escapeAttr(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

function buildContribModel(year, countByDate) {
  const start = sundayOnOrBefore(`${year}-01-01`);
  const end = saturdayOnOrAfter(`${year}-12-31`);
  const cells = [];
  let d = start;
  while (compareDateKeys(d, end) <= 0) {
    const inYear = d.startsWith(`${year}-`);
    const n = inYear ? countByDate.get(d) ?? 0 : 0;
    cells.push({ dateKey: d, inYear, n });
    d = nextBeijingDate(d);
  }
  const maxAc = cells.reduce((m, c) => (c.inYear ? Math.max(m, c.n) : m), 0);
  cells.forEach((c) => {
    c.level = contribLevel(c.n, maxAc);
  });
  const weeks = [];
  for (let i = 0; i < cells.length; i += 7) {
    weeks.push(cells.slice(i, i + 7));
  }
  return { weeks, maxAc };
}

function renderHeatmap(data, year) {
  if (!heatmapEl) return;
  contribSelectedEl = null;
  heatmapLookup = new Map(data.map((item) => [item.date, item]));
  const countByDate = new Map(data.map((item) => [item.date, item.ac_count]));
  const { weeks } = buildContribModel(year, countByDate);
  const W = weeks.length;
  const dowLabels = ["", "一", "", "三", "", "五", ""];

  const parts = [];
  parts.push(`<div class="contrib-corner" style="grid-column:1;grid-row:1" aria-hidden="true"></div>`);

  for (let wi = 0; wi < W; wi++) {
    const lab = monthLabelForWeek(weeks[wi], year);
    parts.push(
      `<div class="contrib-m" style="grid-column:${wi + 2};grid-row:1">${lab ? escapeAttr(lab) : ""}</div>`,
    );
  }

  for (let di = 0; di < 7; di++) {
    parts.push(
      `<div class="contrib-wd" style="grid-column:1;grid-row:${di + 2}">${dowLabels[di] ? escapeAttr(dowLabels[di]) : ""}</div>`,
    );
    for (let wi = 0; wi < W; wi++) {
      const c = weeks[wi][di];
      const outside = !c.inYear;
      const w = beijingWeekdayShort(c.dateKey);
      const head = w ? `${c.dateKey}（${w}）` : c.dateKey;
      const title = `${head} · 当日 AC ${c.n}`;
      const gc = wi + 2;
      const gr = di + 2;
      if (outside) {
        parts.push(
          `<span class="contrib-cell contrib-day l0 is-outside" style="grid-column:${gc};grid-row:${gr}" role="presentation" aria-hidden="true"></span>`,
        );
      } else {
        // 不在每个格子上设 title：鼠标快速划过时原生 tooltip 会严重拖慢主线程；信息见 aria-label 与下方题目列表
        parts.push(
          `<button type="button" class="contrib-cell contrib-day l${c.level}" style="grid-column:${gc};grid-row:${gr}" data-date="${c.dateKey}" aria-label="${escapeAttr(
            title,
          )}"></button>`,
        );
      }
    }
  }

  heatmapEl.innerHTML = `
    <div class="contrib-graph-inner">
      <div class="contrib-scroll">
        <div
          class="contrib-canvas"
          style="grid-template-columns: 26px repeat(${W}, var(--contrib-cell)); grid-template-rows: auto repeat(7, var(--contrib-cell))"
          role="grid"
          aria-label="${year} 年 AC 贡献"
        >
          ${parts.join("")}
        </div>
      </div>
      <div class="contrib-footer">
        <span class="contrib-legend-label">少</span>
        <span class="contrib-swatch l0" aria-hidden="true"></span>
        <span class="contrib-swatch l1" aria-hidden="true"></span>
        <span class="contrib-swatch l2" aria-hidden="true"></span>
        <span class="contrib-swatch l3" aria-hidden="true"></span>
        <span class="contrib-swatch l4" aria-hidden="true"></span>
        <span class="contrib-legend-label">多</span>
      </div>
    </div>
  `;

  heatmapDayByDate = new Map();
  heatmapEl.querySelectorAll(".contrib-day[data-date]").forEach((el) => {
    const k = el.getAttribute("data-date");
    if (k && !el.classList.contains("is-outside")) heatmapDayByDate.set(k, el);
  });
}

/** 与后端日期键一致：按 Asia/Shanghai 显示星期（短） */
function beijingWeekdayShort(dateKey) {
  try {
    const inst = new Date(`${dateKey}T12:00:00+08:00`);
    return new Intl.DateTimeFormat("zh-CN", {
      weekday: "short",
      timeZone: "Asia/Shanghai",
    }).format(inst);
  } catch (e) {
    return "";
  }
}

function pickDefaultHeatmapDate(data, year) {
  const ys = `${year}`;
  const withData = data.filter((d) => d.date && d.date.startsWith(ys) && d.ac_count > 0);
  if (withData.length) {
    return withData[withData.length - 1].date;
  }
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: BEIJING_TIMEZONE }).format(new Date());
  if (today.startsWith(ys)) return today;
  return `${year}-12-31`;
}

function selectContribDay(dateKey) {
  if (!heatmapEl) return;
  if (contribSelectedEl) {
    contribSelectedEl.classList.remove("is-selected");
    contribSelectedEl = null;
  }
  const btn = heatmapDayByDate.get(dateKey);
  if (btn) {
    btn.classList.add("is-selected");
    contribSelectedEl = btn;
  }
}

function renderPeriodStats(data) {
  weeklyAc.textContent = data.ac_count;
  weeklyAttempt.textContent = data.attempt_count;
  weeklyAccuracy.textContent = `${data.accuracy}%`;
  weeklyRange.textContent = `统计区间：${data.start} 至 ${data.end}`;
}

function renderSummary(data) {
  totalSubmissions.textContent = data.total_submissions;
  totalAc.textContent = data.total_ac;
  activeDays.textContent = data.active_days;
  lastSync.textContent = data.last_sync_text || formatDate(data.last_sync_at);
  syncBadge.textContent = data.last_sync_status ? `最近同步：${data.last_sync_status}` : "同步未开始";
}

function renderTags(data) {
  const ct = readChartTheme();
  cachedTagsData = data;
  tagsChart.setOption({
    tooltip: { trigger: "item" },
    xAxis: {
      type: "category",
      data: data.map((item) => item.tag),
      axisLabel: {
        rotate: 28,
        color: ct.text,
      },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: ct.text },
      splitLine: { lineStyle: { color: ct.gridLine } },
    },
    grid: { top: 18, left: 34, right: 18, bottom: 74 },
    series: [
      {
        type: "bar",
        barWidth: 26,
        cursor: "pointer",
        data: data.map((item, index) => ({
          value: item.count,
          name: item.tag,
          itemStyle: {
            color: index % 2 === 0 ? ct.barA : ct.barB,
            borderRadius: [10, 10, 0, 0],
          },
        })),
      },
    ],
  });
  const knowledgePanel = document.querySelector('[data-view="knowledge"]');
  if (knowledgePanel && knowledgePanel.classList.contains("active")) {
    syncTagsPieChart();
  }
}

function renderTagProblems(tag, problems) {
  tagProblemsTitle.textContent = `${tag} 相关题目`;
  tagSelected.textContent = `${tag} 共 ${problems.length} 题，点击将在新标签页打开。`;
  tagProblemList.innerHTML = "";

  if (!problems.length) {
    const empty = document.createElement("li");
    empty.textContent = "该知识点下暂时没有题目。";
    tagProblemList.appendChild(empty);
    return;
  }

  problems.forEach((problem) => {
    const item = document.createElement("li");
    item.innerHTML = `
      <a class="problem-link" href="${problemUrl(problem)}" target="_blank" rel="noreferrer">
        <strong>${problem.problem_id} ${problem.problem_name}</strong>
        <div class="status"><span class="oj-tag">${problem.oj_source}</span> · 难度 <span class="diff-label">${problem.difficulty || "—"}</span>${problem.tags && problem.tags.length ? ` · ${problem.tags.join(" / ")}` : ""}</div>
        <div class="meta">${formatDateTime(problem.submit_time)}</div>
      </a>
    `;
    tagProblemList.appendChild(item);
  });
}

function renderUnsolvedProblems(problems) {
  const ojNote = problemsOjFilter && problemsOjFilter.value ? `（${problemsOjFilter.value}）` : "";
  unsolvedSummary.textContent = `当前共有 ${problems.length} 道已尝试但尚未 AC 的题目${ojNote}。`;
  unsolvedList.innerHTML = "";

  if (!problems.length) {
    const empty = document.createElement("li");
    empty.textContent = "暂时没有未通过题目。";
    unsolvedList.appendChild(empty);
    return;
  }

  problems.forEach((problem) => {
    const item = document.createElement("li");
    item.innerHTML = `
      <a class="problem-link" href="${problemUrl(problem)}" target="_blank" rel="noreferrer">
        <strong>${problem.problem_id} ${problem.problem_name}</strong>
        <div class="status"><span class="oj-tag">${problem.oj_source}</span> · 最近 ${problem.status} · 难度 <span class="diff-label">${problem.difficulty || "—"}</span></div>
        <div class="meta">${formatDateTime(problem.submit_time)}</div>
      </a>
    `;
    unsolvedList.appendChild(item);
  });
}

function renderReport(data) {
  const lines = [
    data.summary,
    "",
    `亮点：${data.highlights.join("；")}`,
    `薄弱点：${data.weaknesses.join("；")}`,
    `建议：${data.suggestion}`,
  ];
  reportContent.textContent = lines.join("\n");
}

function renderConfig(data) {
  cfHandleInput.value = data.codeforces_handle || "";
  cfCookieKvInput.value = data.codeforces_cookie_kv || "";
  luoguUidInput.value = data.luogu_uid || "";
  luoguUsernameInput.value = data.luogu_username || "";
  luoguCkClientIdInput.value = data.luogu_ck_client_id || "";
  luoguCkUidInput.value = data.luogu_ck_uid || "";
  luoguCookieKvInput.value = data.luogu_cookie_kv || "";
  nowcoderUidInput.value = data.nowcoder_uid || "";
  nowcoderCookieKvInput.value = data.nowcoder_cookie_kv || "";
  if (atcoderUsernameInput) atcoderUsernameInput.value = data.atcoder_username || "";
  syncIntervalInput.value = data.sync_interval_minutes || 0;

  if (data.configured_sources.length) {
    configBadge.textContent = `已配置：${data.configured_sources.join(" / ")}`;
  } else {
    configBadge.textContent = "尚未配置账号";
  }
}

function renderSyncRuns(data) {
  if (!data.length) {
    syncRunsBody.innerHTML = `<tr><td colspan="5" class="meta">还没有同步记录。</td></tr>`;
    return;
  }

  syncRunsBody.innerHTML = data
    .map((run) => {
      const detail = Object.entries(run.detail || {})
        .map(([source, item]) => `${source}: 抓取 ${item.fetched ?? 0} / 新增 ${item.inserted ?? 0}${item.updated ? ` / 更新 ${item.updated}` : ""}${item.meta_enriched != null ? ` / 补全元数据 ${item.meta_enriched}` : ""}${item.editorial_filled != null ? ` / 题解推断 ${item.editorial_filled}` : ""}${item.record_count !== undefined ? ` / record=${item.record_count}` : ""}${item.matched_ac_time_count !== undefined ? ` / 命中时间=${item.matched_ac_time_count}` : ""}${item.message ? ` / ${item.message}` : ""}`)
        .join("<br/>");
      return `
        <tr>
          <td>${run.started_at_text || formatDateTime(run.started_at)}</td>
          <td>${run.source}</td>
          <td>${run.mode}</td>
          <td>${run.status}</td>
          <td>${detail || "-"}</td>
        </tr>
      `;
    })
    .join("");
}

function formatSyncSummary(data) {
  const parts = [
    `抓取 ${data.fetched} 条`,
    `新增 ${data.inserted} 条`,
    `跳过 ${data.skipped} 条`,
  ];
  if (data.updated) {
    parts.push(`更新 ${data.updated} 条`);
  }
  if (data.unknown_time_count) {
    parts.push(`时间未知 ${data.unknown_time_count} 条`);
  }
  const detailParts = Object.entries(data.sources || {}).map(([source, item]) => {
    return `${source}: 抓取 ${item.fetched ?? 0} / 入库 ${item.inserted ?? 0}${item.updated ? ` / 更新 ${item.updated}` : ""}${item.meta_enriched != null ? ` / 补全元数据 ${item.meta_enriched}` : ""}${item.editorial_filled != null ? ` / 题解推断 ${item.editorial_filled}` : ""}${item.unknown_time_count ? ` / 未知时间 ${item.unknown_time_count}` : ""}${item.message ? ` / ${item.message}` : ""}`;
  });
  return `${parts.join("，")}，失败来源 ${data.failed_sources.join(", ") || "无"}${detailParts.length ? `，详情：${detailParts.join("；")}` : ""}`;
}

async function refreshKnowledgeTagsOnly() {
  const tagsRes = await fetchJSON(`/api/stats/tags${ojQueryFromSelect(knowledgeOjFilter)}`);
  renderTags(tagsRes.data);
  syncTagsPieChart();
  if (tagProblemList) tagProblemList.innerHTML = "";
  if (tagSelected) tagSelected.textContent = "筛选已更改，请重新点击柱状图或饼图中的知识点。";
  if (tagProblemsTitle) tagProblemsTitle.textContent = "知识点相关题目";
}

async function refreshUnsolvedOnly() {
  const res = await fetchJSON(`/api/problems/unsolved${ojQueryFromSelect(problemsOjFilter)}`);
  renderUnsolvedProblems(res.data);
}

async function refreshDashboard() {
  const year = currentYear();
  const [heatmapRes, periodRes, tagsRes, reportRes, summaryRes, configRes, runsRes, unsolvedRes] = await Promise.all([
    fetchJSON(`/api/heatmap?year=${year}`),
    fetchJSON(`/api/stats/period?period=${activePeriod}`),
    fetchJSON(`/api/stats/tags${ojQueryFromSelect(knowledgeOjFilter)}`),
    fetchJSON("/api/report/weekly"),
    fetchJSON("/api/summary"),
    fetchJSON("/api/config"),
    fetchJSON("/api/sync/runs"),
    fetchJSON(`/api/problems/unsolved${ojQueryFromSelect(problemsOjFilter)}`),
  ]);

  renderHeatmap(heatmapRes.data, year);
  renderPeriodStats(periodRes.data);
  renderTags(tagsRes.data);
  renderReport(reportRes.data);
  renderSummary(summaryRes.data);
  renderConfig(configRes.data);
  renderSyncRuns(runsRes.data);
  renderUnsolvedProblems(unsolvedRes.data);

  const defaultDay = pickDefaultHeatmapDate(heatmapRes.data, year);
  selectContribDay(defaultDay);
  requestAnimationFrame(() => renderProblemList(defaultDay));
}

async function loadTagProblems(tag) {
  switchView("knowledge");
  tagSelected.textContent = `正在加载 ${tag} 题目列表...`;
  try {
    let url = `/api/problems/by-tag?tag=${encodeURIComponent(tag)}`;
    const kv = knowledgeOjFilter && knowledgeOjFilter.value ? knowledgeOjFilter.value.trim() : "";
    if (kv) url += `&oj=${encodeURIComponent(kv)}`;
    const response = await fetchJSON(url);
    renderTagProblems(tag, response.data);
  } catch (error) {
    tagSelected.textContent = `加载失败：${error.message}`;
  }
}

async function triggerSync(forceFull = false) {
  if (syncAbortController) {
    try {
      syncAbortController.abort();
    } catch (e) {}
  }
  syncAbortController = new AbortController();
  syncButton.disabled = true;
  forceSyncButton.disabled = true;
  if (cancelSyncButton) cancelSyncButton.hidden = false;
  syncStatus.textContent = forceFull ? "正在执行全量同步，请稍候。" : "正在同步提交记录，请稍候。";
  try {
    const payload = {
      source: sourceSelect.value || null,
      force_full: forceFull,
    };
    const response = await fetchJSON("/api/sync", {
      method: "POST",
      body: JSON.stringify(payload),
      signal: syncAbortController.signal,
    });
    const data = response.data;
    syncStatus.textContent = `同步完成：${formatSyncSummary(data)}`;
    await refreshDashboard();
  } catch (error) {
    if (error.name === "AbortError") {
      syncStatus.textContent = "已取消等待。（若服务端仍在同步，可点「清除卡住状态」后再试。）";
    } else {
      syncStatus.textContent = `同步失败：${error.message}`;
    }
  } finally {
    syncButton.disabled = false;
    forceSyncButton.disabled = false;
    if (cancelSyncButton) cancelSyncButton.hidden = true;
    syncAbortController = null;
  }
}

syncButton.addEventListener("click", async () => {
  await triggerSync(false);
});

forceSyncButton.addEventListener("click", async () => {
  await triggerSync(true);
});

saveConfigButton.addEventListener("click", async () => {
  saveConfigButton.disabled = true;
  syncStatus.textContent = "正在保存配置。";
  try {
    await fetchJSON("/api/config", {
      method: "POST",
      body: JSON.stringify({
        codeforces_handle: cfHandleInput.value.trim(),
        codeforces_cookie_kv: cfCookieKvInput.value,
        luogu_uid: luoguUidInput.value.trim(),
        luogu_username: luoguUsernameInput.value.trim(),
        luogu_ck_client_id: luoguCkClientIdInput.value.trim(),
        luogu_ck_uid: luoguCkUidInput.value.trim(),
        luogu_cookie_kv: luoguCookieKvInput.value,
        nowcoder_uid: nowcoderUidInput.value.trim(),
        nowcoder_cookie_kv: nowcoderCookieKvInput.value,
        atcoder_username: atcoderUsernameInput ? atcoderUsernameInput.value.trim() : "",
        sync_interval_minutes: Number(syncIntervalInput.value || 0),
      }),
    });
    syncStatus.textContent = "配置已保存，可以立即开始同步。";
    await refreshDashboard();
  } catch (error) {
    syncStatus.textContent = `保存配置失败：${error.message}`;
  } finally {
    saveConfigButton.disabled = false;
  }
});

yearInput.addEventListener("change", () => {
  refreshDashboard().catch((error) => {
    syncStatus.textContent = `加载热力图失败：${error.message}`;
  });
});

prevYearButton.addEventListener("click", () => {
  yearInput.value = String(currentYear() - 1);
  yearInput.dispatchEvent(new Event("change"));
});

nextYearButton.addEventListener("click", () => {
  yearInput.value = String(currentYear() + 1);
  yearInput.dispatchEvent(new Event("change"));
});

knowledgeOjFilter?.addEventListener("change", () => {
  refreshKnowledgeTagsOnly().catch((error) => {
    syncStatus.textContent = `更新知识点统计失败：${error.message}`;
  });
});

problemsOjFilter?.addEventListener("change", () => {
  refreshUnsolvedOnly().catch((error) => {
    syncStatus.textContent = `更新补题列表失败：${error.message}`;
  });
});

heatmapEl?.addEventListener("click", (e) => {
  const btn = e.target.closest(".contrib-day");
  if (!btn || btn.classList.contains("is-outside")) return;
  const dateKey = btn.getAttribute("data-date");
  if (!dateKey) return;
  selectContribDay(dateKey);
  requestAnimationFrame(() => renderProblemList(dateKey));
});

tagsChart.on("click", (params) => {
  if (!params.name) return;
  loadTagProblems(params.name);
});
periodButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activePeriod = button.dataset.period;
    periodButtons.forEach((item) => item.classList.toggle("active", item === button));
    refreshDashboard().catch((error) => {
      syncStatus.textContent = `加载统计失败：${error.message}`;
    });
  });
});

window.addEventListener("resize", () => {
  tagsChart.resize();
  if (tagsPieChart) {
    tagsPieChart.resize();
  }
});

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredPrompt = event;
  installButton.hidden = false;
});

installButton.addEventListener("click", async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  await deferredPrompt.userChoice;
  deferredPrompt = null;
  installButton.hidden = true;
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/static/service-worker.js").catch(() => {});
  });
}

const themeSelect = document.getElementById("theme-select");
if (themeSelect) {
  const pref = readThemePreference();
  themeSelect.value = pref;
  applyTheme(pref, false);
  themeSelect.addEventListener("change", () => applyTheme(themeSelect.value));
}
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (readThemePreference() === "system") {
    applyTheme("system");
  }
});

cancelSyncButton?.addEventListener("click", () => {
  if (syncAbortController) {
    syncAbortController.abort();
  }
});

repairSyncButton?.addEventListener("click", async () => {
  repairSyncButton.disabled = true;
  try {
    const res = await fetchJSON("/api/sync/repair-stuck", { method: "POST" });
    syncStatus.textContent = `已清除卡住状态：修复 ${res.data.repaired} 条未结束记录。`;
    await refreshDashboard();
  } catch (error) {
    syncStatus.textContent = `清除失败：${error.message}`;
  } finally {
    repairSyncButton.disabled = false;
  }
});

const startView = viewPanels.some((panel) => panel.dataset.view === DEFAULT_VIEW)
  ? DEFAULT_VIEW
  : "overview";
switchView(startView, false);

navButtons.forEach((btn) => {
  btn.addEventListener("click", (e) => {
    const v = btn.dataset.navView;
    if (!v) return;
    e.preventDefault();
    switchView(v, true);
  });
});

window.addEventListener("popstate", () => {
  const path = location.pathname;
  const pathToView =
    path === "/knowledge"
      ? "knowledge"
      : path === "/problems"
        ? "problems"
        : path === "/settings"
          ? "settings"
          : "overview";
  switchView(pathToView, false);
});

if (location.hash === "#heatmap-section" || location.hash === "#heatmap") {
  requestAnimationFrame(() => {
    document.getElementById("heatmap-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

refreshDashboard().catch((error) => {
  syncStatus.textContent = `初始化加载失败：${error.message}`;
});
