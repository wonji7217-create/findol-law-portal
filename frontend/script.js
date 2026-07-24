// 같은 서버(FastAPI)에서 정적 파일을 서빙하므로 상대경로로 호출 (CORS 문제 없음)
const API_BASE = "";
const $ = (id) => document.getElementById(id);

// ---------- 즐겨찾기 (localStorage) ----------
let favorites = JSON.parse(localStorage.getItem("findol-favorites") || "[]");

function isFavorite(id) {
  return favorites.some((f) => f.id === id);
}

function toggleFavorite(item) {
  if (isFavorite(item.id)) {
    favorites = favorites.filter((f) => f.id !== item.id);
    showToast(`${item.name} 즐겨찾기를 해제했어요.`);
  } else {
    favorites.push(item);
    showToast(`${item.name}을(를) 즐겨찾기에 저장했어요.`);
  }
  localStorage.setItem("findol-favorites", JSON.stringify(favorites));
  updateFavoriteCount();
}

function updateFavoriteCount() {
  $("favoriteCount").textContent = favorites.length;
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("is-visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("is-visible"), 1800);
}

// ---------- 탭 전환 ----------
const navTabs = document.querySelectorAll(".nav-tab");
const panels = {
  search: document.getElementById("panel-search"),
  timeline: document.getElementById("panel-timeline"),
  calendar: document.getElementById("panel-calendar"),
};

function activateTab(tabName) {
  navTabs.forEach((b) => b.classList.toggle("is-active", b.dataset.tab === tabName));
  Object.entries(panels).forEach(([name, el]) => el.classList.toggle("is-active", name === tabName));
  $("mobileNav").classList.remove("is-open");
  $("mobileMenuButton").setAttribute("aria-expanded", "false");

  if (tabName === "timeline") loadTimeline();
  else if (tabName === "calendar") loadCalendar();

  window.scrollTo({ top: 0, behavior: "smooth" });
}

navTabs.forEach((btn) => btn.addEventListener("click", () => activateTab(btn.dataset.tab)));

document.querySelectorAll("[data-tab-link]").forEach((btn) => {
  btn.addEventListener("click", () => activateTab(btn.dataset.tabLink));
});

$("logoHome").addEventListener("click", (e) => {
  e.preventDefault();
  activateTab("search");
});

$("mobileMenuButton").addEventListener("click", () => {
  const isOpen = $("mobileNav").classList.toggle("is-open");
  $("mobileMenuButton").setAttribute("aria-expanded", String(isOpen));
});

// ---------- 검색 ----------
const searchForm = document.getElementById("search-form");
const searchInput = document.getElementById("search-input");
const searchType = document.getElementById("searchType");
const lawResultsGrid = document.getElementById("law-results");
const admrulResultsGrid = document.getElementById("admrul-results");
const lawCount = document.getElementById("law-count");
const admrulCount = document.getElementById("admrul-count");
const searchResults = document.getElementById("searchResults");
const searchResultTitle = document.getElementById("searchResultTitle");
const searchResultCount = document.getElementById("searchResultCount");

document.querySelectorAll(".quick-tag").forEach((tag) => {
  tag.addEventListener("click", () => {
    searchInput.value = tag.dataset.query;
    searchForm.requestSubmit();
  });
});

searchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = searchInput.value.trim();
  if (!q) return;

  searchResultTitle.textContent = `"${q}" 검색 중...`;
  searchResultCount.textContent = "";
  searchResults.classList.add("is-visible");

  const scope = searchType.value; // all | law | admin
  const includeAdmrul = scope !== "law";

  try {
    const url = `${API_BASE}/api/search?q=${encodeURIComponent(q)}&include_admrul=${includeAdmrul}&chem_only=true`;
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `서버 오류 (${res.status})`);
    }
    const data = await res.json();

    const laws = scope === "admin" ? [] : data.laws;
    const admrules = scope === "law" ? [] : data.admin_rules;

    lawCount.textContent = laws.length;
    admrulCount.textContent = admrules.length;

    renderResults(lawResultsGrid, laws, "law");
    renderResults(admrulResultsGrid, admrules, "admrul");

    // 법령/고시 블록 자체를 검색 범위에 따라 보이기/숨기기
    lawResultsGrid.closest(".result-block").style.display = scope === "admin" ? "none" : "";
    admrulResultsGrid.closest(".result-block").style.display = scope === "law" ? "none" : "";

    searchResultTitle.textContent = `"${data.query}" 검색 결과`;
    searchResultCount.textContent = `${laws.length + admrules.length}건 · 신규 저장 ${data.newly_saved}건`;

    searchResults.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (err) {
    searchResultTitle.textContent = "검색 중 오류가 발생했어요";
    searchResultCount.textContent = "";
    lawResultsGrid.innerHTML = `<div class="empty-state"><strong>${escapeHtml(err.message)}</strong></div>`;
    admrulResultsGrid.innerHTML = "";
  }
});

const EMPTY_MASCOT_SVG = `
  <svg class="empty-stone" viewBox="0 0 110 84" aria-hidden="true">
    <defs>
      <radialGradient id="emptyStoneBody" cx="35%" cy="25%" r="80%">
        <stop offset="0%" stop-color="#ECEDE8"/>
        <stop offset="60%" stop-color="#D7D8D3"/>
        <stop offset="100%" stop-color="#BFC3BE"/>
      </radialGradient>
    </defs>
    <ellipse cx="55" cy="75" rx="37" ry="6" fill="#78827E" opacity=".11"/>
    <path d="M19 50C18 27 35 11 57 10c24 0 39 15 39 35 11 8 10 24-1 29-10 5-70 5-80 0-10-5-8-18 4-24Z" fill="url(#emptyStoneBody)" stroke="#8E9591" stroke-width="2"/>
    <circle cx="43" cy="43" r="3.2" fill="#3F4745"/>
    <circle cx="68" cy="43" r="3.2" fill="#3F4745"/>
    <path d="M50 56c4 3 8 3 12 0" stroke="#3F4745" stroke-width="2" fill="none" stroke-linecap="round"/>
    <circle cx="30" cy="55" r="6" fill="#EBC2AC" opacity=".45"/>
    <circle cx="80" cy="55" r="6" fill="#EBC2AC" opacity=".45"/>
  </svg>`;

function renderResults(gridEl, items, kind) {
  if (!items || items.length === 0) {
    gridEl.innerHTML = `<div class="empty-state">${EMPTY_MASCOT_SVG}<strong>결과가 없어요</strong><span>다른 키워드로 다시 검색해 보세요.</span></div>`;
    return;
  }

  gridEl.innerHTML = items
    .map((item) => {
      const favId = `${kind}:${item.id}`;
      const fav = isFavorite(favId);
      const metaBits = [];
      if (item.department) metaBits.push(escapeHtml(item.department));
      if (item.type) metaBits.push(escapeHtml(item.type));
      if (item.promulgation_date) metaBits.push(`공포 ${formatDate(item.promulgation_date)}`);
      if (item.enforcement_date) metaBits.push(`시행 ${formatDate(item.enforcement_date)}`);
      const href = item.detail_link ? `https://www.law.go.kr${item.detail_link}` : "#";
      const typeLabel = kind === "law" ? "법령" : (item.type || "고시·훈령");

      return `
        <div class="result-card-wrap">
          <button class="fav-star ${fav ? "is-fav" : ""}" type="button"
            data-fav-id="${favId}" data-fav-name="${escapeHtml(item.name || "")}"
            aria-label="즐겨찾기">${fav ? "★" : "☆"}</button>
          <a class="result-card" href="${href}" target="_blank" rel="noopener">
            <small>${escapeHtml(typeLabel)}</small>
            <strong>${escapeHtml(item.name || "(이름 없음)")}</strong>
            <span class="r-meta">${metaBits.join(" · ")}</span>
          </a>
        </div>`;
    })
    .join("");

  gridEl.querySelectorAll(".fav-star").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.favId;
      const name = btn.dataset.favName;
      toggleFavorite({ id, name });
      btn.classList.toggle("is-fav");
      btn.textContent = btn.classList.contains("is-fav") ? "★" : "☆";
    });
  });
}

// ---------- 즐겨찾기 보기 ----------
$("favoriteHeaderButton").addEventListener("click", () => {
  activateTab("search");
  searchResultTitle.textContent = "즐겨찾기한 법령";
  searchResultCount.textContent = `${favorites.length}건`;
  searchResults.classList.add("is-visible");

  lawResultsGrid.closest(".result-block").style.display = "";
  admrulResultsGrid.closest(".result-block").style.display = "none";
  lawCount.textContent = favorites.length;

  if (!favorites.length) {
    lawResultsGrid.innerHTML = `<div class="empty-state">${EMPTY_MASCOT_SVG}<strong>아직 저장한 법령이 없어요.</strong><span>검색 결과 카드의 ☆를 눌러 저장해 보세요.</span></div>`;
  } else {
    lawResultsGrid.innerHTML = favorites
      .map((f) => `
        <div class="result-card-wrap">
          <button class="fav-star is-fav" type="button" data-fav-id="${f.id}" data-fav-name="${escapeHtml(f.name)}" aria-label="즐겨찾기 해제">★</button>
          <div class="result-card"><strong>${escapeHtml(f.name)}</strong></div>
        </div>`)
      .join("");
    lawResultsGrid.querySelectorAll(".fav-star").forEach((btn) => {
      btn.addEventListener("click", () => {
        toggleFavorite({ id: btn.dataset.favId, name: btn.dataset.favName });
        btn.closest(".result-card-wrap").remove();
        searchResultCount.textContent = `${favorites.length}건`;
      });
    });
  }
  searchResults.scrollIntoView({ behavior: "smooth", block: "nearest" });
});

// ---------- 자주 찾는 법령 (실제 검색 실행) ----------
const SHORTCUTS = [
  { title: "화학물질관리법", type: "법률", query: "화학물질관리법", icon: "book" },
  { title: "화학물질관리법 시행령", type: "대통령령", query: "화학물질관리법 시행령", icon: "box" },
  { title: "화학물질관리법 시행규칙", type: "환경부령", query: "화학물질관리법 시행규칙", icon: "doc" },
  { title: "유해화학물질 취급시설 설치·관리", type: "고시", query: "취급시설 설치", icon: "flask" },
  { title: "화학사고예방관리계획서", type: "고시·지침", query: "화학사고예방관리계획서", icon: "shield" },
  { title: "검사 및 안전진단", type: "고시·지침", query: "안전진단", icon: "search" },
];

const ICONS = {
  book: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M5 4.5h10.5A2.5 2.5 0 0 1 18 7v12H7.5A2.5 2.5 0 0 1 5 16.5v-12Z" stroke="currentColor" stroke-width="1.6"/><path d="M8 4.5v12c0 1.4 1.1 2.5 2.5 2.5" stroke="currentColor" stroke-width="1.6"/></svg>',
  box: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" stroke="currentColor" stroke-width="1.6"/><path d="m4.5 7.8 7.5 4.3 7.5-4.3M12 12.1V21" stroke="currentColor" stroke-width="1.6"/></svg>',
  doc: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M6 3.5h8l4 4V20H6V3.5Z" stroke="currentColor" stroke-width="1.6"/><path d="M14 3.5v4h4M9 12h6M9 15h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  flask: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M9 3.5h6M10 3.5v6L5.5 18a1.7 1.7 0 0 0 1.5 2.5h10a1.7 1.7 0 0 0 1.5-2.5L14 9.5v-6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M8 15h8" stroke="currentColor" stroke-width="1.6"/></svg>',
  shield: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 3.5 19 6v5.5c0 4.5-2.8 7.7-7 9-4.2-1.3-7-4.5-7-9V6l7-2.5Z" stroke="currentColor" stroke-width="1.6"/><path d="m9 12 2 2 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  search: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="10.5" cy="10.5" r="6" stroke="currentColor" stroke-width="1.6"/><path d="m15 15 4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
};

function renderShortcuts() {
  $("lawShortcuts").innerHTML = SHORTCUTS.map((item, i) => `
    <button class="law-shortcut" type="button" data-shortcut-index="${i}">
      <span class="law-icon">${ICONS[item.icon]}</span>
      <strong>${item.title}</strong>
      <span>${item.type}</span>
    </button>
  `).join("");

  document.querySelectorAll("[data-shortcut-index]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const item = SHORTCUTS[Number(btn.dataset.shortcutIndex)];
      searchInput.value = item.query;
      searchForm.requestSubmit();
    });
  });
}

// ---------- 최근 개정 법령 (실제 타임라인 데이터) ----------
async function loadRecentUpdates() {
  const list = $("updateList");
  try {
    const res = await fetch(`${API_BASE}/api/timeline?limit=4`);
    if (!res.ok) throw new Error("불러오기 실패");
    const data = await res.json();

    if (!data.items || data.items.length === 0) {
      list.innerHTML = `<div class="update-empty">아직 수집된 데이터가 없어요. 법령 검색을 한 번 실행해 보세요.</div>`;
      return;
    }

    list.innerHTML = data.items.slice(0, 4).map((item) => {
      const chipClass = item.kind === "law" ? "type-law" : "type-notice";
      const chipLabel = item.kind === "law" ? "법령" : "고시";
      return `
        <div class="update-item">
          <span class="type-chip ${chipClass}">${chipLabel}</span>
          <div>
            <strong>${escapeHtml(item.name || "")}</strong>
            <small>${escapeHtml(item.department || "")}</small>
          </div>
          <time>${formatDate(item.promulgation_date || item.enforcement_date)}</time>
        </div>`;
    }).join("");
  } catch (err) {
    list.innerHTML = `<div class="update-empty">불러오지 못했어요.</div>`;
  }
}

// ---------- 캘린더 ----------
const calGrid = document.getElementById("calendar-grid");
const calLabel = document.getElementById("cal-label");
const calEventList = document.getElementById("calendar-event-list");
const calPrevBtn = document.getElementById("cal-prev");
const calNextBtn = document.getElementById("cal-next");

const today = new Date();
let calYear = today.getFullYear();
let calMonth = today.getMonth() + 1;

calPrevBtn.addEventListener("click", () => {
  calMonth -= 1;
  if (calMonth < 1) { calMonth = 12; calYear -= 1; }
  loadCalendar();
});
calNextBtn.addEventListener("click", () => {
  calMonth += 1;
  if (calMonth > 12) { calMonth = 1; calYear += 1; }
  loadCalendar();
});

async function loadCalendar() {
  calLabel.textContent = `${calYear}년 ${calMonth}월`;
  calEventList.innerHTML = `<li class="empty-state">불러오는 중...</li>`;
  try {
    const res = await fetch(`${API_BASE}/api/calendar?year=${calYear}&month=${calMonth}`);
    if (!res.ok) throw new Error(`서버 오류 (${res.status})`);
    const data = await res.json();
    renderCalendarGrid(data.events);
    renderCalendarEventList(data.events);
  } catch (err) {
    calEventList.innerHTML = `<li class="empty-state">${EMPTY_MASCOT_SVG}<p>캘린더를 불러오지 못했어요: ${escapeHtml(err.message)}</p></li>`;
  }
}

function renderCalendarGrid(events) {
  const byDay = {};
  events.forEach((ev) => {
    const day = parseInt(ev.date.slice(6, 8), 10);
    if (!byDay[day]) byDay[day] = [];
    byDay[day].push(ev);
  });

  const firstOfMonth = new Date(calYear, calMonth - 1, 1);
  const startWeekday = firstOfMonth.getDay();
  const daysInMonth = new Date(calYear, calMonth, 0).getDate();
  const isCurrentMonth = today.getFullYear() === calYear && today.getMonth() + 1 === calMonth;

  let cells = "";
  for (let i = 0; i < startWeekday; i++) cells += `<div class="cal-day is-empty"></div>`;

  for (let d = 1; d <= daysInMonth; d++) {
    const dots = (byDay[d] || [])
      .map((ev) => {
        const cls = `dot ${ev.event_type === "공포" ? "dot-promulgate" : "dot-enforce"}`;
        const title = `${ev.name} (${ev.event_type})`;
        if (ev.detail_link) {
          return `<a class="dot-link" href="https://www.law.go.kr${ev.detail_link}" target="_blank" rel="noopener" title="${escapeHtml(title)}"><span class="${cls}"></span></a>`;
        }
        return `<span class="${cls}" title="${escapeHtml(title)}"></span>`;
      })
      .join("");
    const isToday = isCurrentMonth && today.getDate() === d;
    cells += `
      <div class="cal-day${isToday ? " is-today" : ""}">
        <span class="cal-day-num">${d}</span>
        <div class="cal-day-dots">${dots}</div>
      </div>`;
  }
  calGrid.innerHTML = cells;
}

function renderCalendarEventList(events) {
  if (!events || events.length === 0) {
    calEventList.innerHTML = `<li class="empty-state">${EMPTY_MASCOT_SVG}<p>이번 달에 수집된 공포·시행 일정이 없어요.</p></li>`;
    return;
  }
  calEventList.innerHTML = events.map((ev) => {
    const href = ev.detail_link ? `https://www.law.go.kr${ev.detail_link}` : null;
    const inner = `
      <div class="t-date">${formatDate(ev.date)}</div>
      <div class="t-name"><span class="t-badge">${ev.event_type}</span>${escapeHtml(ev.name || "")}</div>
      <div class="r-meta">${ev.department ? escapeHtml(ev.department) + " · " : ""}${ev.kind === "law" ? "법령" : "고시·훈령"}</div>`;
    if (href) {
      return `<li class="timeline-item${ev.event_type === "시행" ? " is-change" : ""}"><a class="cal-event-link" href="${href}" target="_blank" rel="noopener">${inner}</a></li>`;
    }
    return `<li class="timeline-item${ev.event_type === "시행" ? " is-change" : ""}">${inner}</li>`;
  }).join("");
}

// ---------- 개정 이력(타임라인) ----------
const timelineList = document.getElementById("timeline-list");
const timelineKeyword = document.getElementById("timeline-keyword");
const timelineRefresh = document.getElementById("timeline-refresh");

timelineRefresh.addEventListener("click", loadTimeline);
timelineKeyword.addEventListener("keydown", (e) => { if (e.key === "Enter") loadTimeline(); });

async function loadTimeline() {
  timelineList.innerHTML = `<li class="empty-state">불러오는 중...</li>`;
  const kw = timelineKeyword.value.trim();
  const url = `${API_BASE}/api/timeline${kw ? `?keyword=${encodeURIComponent(kw)}` : ""}`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`서버 오류 (${res.status})`);
    const data = await res.json();
    if (!data.items || data.items.length === 0) {
      timelineList.innerHTML = `<li class="empty-state">${EMPTY_MASCOT_SVG}<p>아직 쌓인 데이터가 없어요. 법령 검색 탭에서 검색을 실행해주세요.</p></li>`;
      return;
    }
    timelineList.innerHTML = data.items.map((item) => `
      <li class="timeline-item">
        <div class="t-date">${formatDateTime(item.fetched_at)}</div>
        <div class="t-name"><span class="t-badge">${item.kind === "law" ? "법령" : "고시·훈령"}</span>${escapeHtml(item.name || "")}</div>
        <div class="r-meta">
          ${item.department ? escapeHtml(item.department) + " · " : ""}
          ${item.promulgation_date ? "공포 " + formatDate(item.promulgation_date) : ""}
          ${item.source_query ? " · 검색어: " + escapeHtml(item.source_query) : ""}
        </div>
      </li>`).join("");
  } catch (err) {
    timelineList.innerHTML = `<li class="empty-state">타임라인을 불러오지 못했어요: ${escapeHtml(err.message)}</li>`;
  }
}

// ---------- 유틸 ----------
function formatDate(yyyymmdd) {
  if (!yyyymmdd || yyyymmdd.length !== 8) return yyyymmdd || "";
  return `${yyyymmdd.slice(0, 4)}.${yyyymmdd.slice(4, 6)}.${yyyymmdd.slice(6, 8)}`;
}

function formatDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

// ---------- 초기화 ----------
renderShortcuts();
loadRecentUpdates();
updateFavoriteCount();
