const API_BASE = "";
const $ = (id) => document.getElementById(id);

// -----------------------------------------------------------------------------
// 공통 상태와 유틸
// -----------------------------------------------------------------------------
let favorites = JSON.parse(localStorage.getItem("findol-favorites") || "[]");
let archiveOffset = 0;
const ARCHIVE_LIMIT = 20;
let archiveTotal = 0;
let calendarEvents = [];
let selectedCalendarDate = null;

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

function formatDate(value) {
  if (!value) return "";
  const digits = String(value).replace(/\D/g, "");
  if (digits.length < 8) return value;
  return `${digits.slice(0, 4)}.${digits.slice(4, 6)}.${digits.slice(6, 8)}`;
}

function dateToIso(value) {
  if (!value) return "";
  const digits = String(value).replace(/\D/g, "");
  if (digits.length < 8) return "";
  return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6, 8)}`;
}

function daysUntil(value) {
  const iso = dateToIso(value);
  if (!iso) return null;
  const target = new Date(`${iso}T00:00:00`);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.ceil((target - today) / 86400000);
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("is-visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("is-visible"), 1900);
}

function emptyState(title, description = "") {
  return `<div class="empty-state">
    <svg class="empty-stone" viewBox="0 0 110 84" aria-hidden="true">
      <defs><radialGradient id="emptyStoneBody" cx="35%" cy="25%" r="80%"><stop offset="0%" stop-color="#ECEDE8"/><stop offset="60%" stop-color="#D7D8D3"/><stop offset="100%" stop-color="#BFC3BE"/></radialGradient></defs>
      <ellipse cx="55" cy="75" rx="37" ry="6" fill="#78827E" opacity=".11"/>
      <path d="M19 50C18 27 35 11 57 10c24 0 39 15 39 35 11 8 10 24-1 29-10 5-70 5-80 0-10-5-8-18 4-24Z" fill="url(#emptyStoneBody)" stroke="#8E9591" stroke-width="2"/>
      <circle cx="43" cy="43" r="3.2" fill="#3F4745"/><circle cx="68" cy="43" r="3.2" fill="#3F4745"/>
      <path d="M50 56c4 3 8 3 12 0" stroke="#3F4745" stroke-width="2" fill="none" stroke-linecap="round"/>
    </svg>
    <strong>${escapeHtml(title)}</strong><span>${escapeHtml(description)}</span>
  </div>`;
}

// -----------------------------------------------------------------------------
// 탭과 모바일 메뉴
// -----------------------------------------------------------------------------
const navTabs = document.querySelectorAll(".nav-tab");
const panels = {
  search: $("panel-search"),
  archive: $("panel-archive"),
  calendar: $("panel-calendar"),
};

function activateTab(tabName) {
  navTabs.forEach((button) => button.classList.toggle("is-active", button.dataset.tab === tabName));
  Object.entries(panels).forEach(([name, panel]) => panel.classList.toggle("is-active", name === tabName));
  $("mobileNav").classList.remove("is-open");
  $("mobileMenuButton").setAttribute("aria-expanded", "false");

  if (tabName === "archive") loadArchive(true);
  if (tabName === "calendar") loadCalendar();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

navTabs.forEach((button) => button.addEventListener("click", () => activateTab(button.dataset.tab)));
document.querySelectorAll("[data-tab-link]").forEach((button) => button.addEventListener("click", () => activateTab(button.dataset.tabLink)));
$("logoHome").addEventListener("click", (event) => { event.preventDefault(); activateTab("search"); });
$("mobileMenuButton").addEventListener("click", () => {
  const open = $("mobileNav").classList.toggle("is-open");
  $("mobileMenuButton").setAttribute("aria-expanded", String(open));
});
const officialLawButton = $("officialLawButton");
if (officialLawButton) officialLawButton.addEventListener("click", () => window.open("https://www.law.go.kr", "_blank", "noopener"));


// -----------------------------------------------------------------------------
// 유관기관 · 지방환경청 선택 팝업
// -----------------------------------------------------------------------------
let institutionModalReturnFocus = null;

function openInstitutionModal() {
  institutionModalReturnFocus = document.activeElement;
  $("institutionModal").hidden = false;
  document.body.classList.add("modal-open");
  $("regionalOfficeButton").setAttribute("aria-expanded", "true");
  requestAnimationFrame(() => $("institutionModalClose").focus());
}

function closeInstitutionModal() {
  $("institutionModal").hidden = true;
  document.body.classList.remove("modal-open");
  $("regionalOfficeButton").setAttribute("aria-expanded", "false");
  if (institutionModalReturnFocus && typeof institutionModalReturnFocus.focus === "function") {
    institutionModalReturnFocus.focus();
  }
}

$("regionalOfficeButton").setAttribute("aria-expanded", "false");
$("regionalOfficeButton").addEventListener("click", openInstitutionModal);
$("institutionModalClose").addEventListener("click", closeInstitutionModal);
$("institutionModal").addEventListener("click", (event) => {
  if (event.target === $("institutionModal")) closeInstitutionModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("institutionModal").hidden) closeInstitutionModal();
});

// -----------------------------------------------------------------------------
// 즐겨찾기
// -----------------------------------------------------------------------------
function isFavorite(id) {
  return favorites.some((item) => item.id === id);
}

function toggleFavorite(item) {
  if (isFavorite(item.id)) {
    favorites = favorites.filter((favorite) => favorite.id !== item.id);
    showToast(`${item.name} 즐겨찾기를 해제했어요.`);
  } else {
    favorites.push(item);
    showToast(`${item.name}을(를) 즐겨찾기에 저장했어요.`);
  }
  localStorage.setItem("findol-favorites", JSON.stringify(favorites));
  $("favoriteCount").textContent = favorites.length;
}

$("favoriteHeaderButton").addEventListener("click", () => {
  activateTab("search");
  $("searchResults").classList.add("is-visible");
  $("searchPlan").hidden = true;
  $("searchResultTitle").textContent = "즐겨찾기한 법령";
  $("searchResultCount").textContent = `${favorites.length}건`;
  $("admrul-results").closest(".result-block").style.display = "none";
  $("law-results").closest(".result-block").style.display = "";
  $("law-count").textContent = favorites.length;
  $("law-results").innerHTML = favorites.length
    ? favorites.map((item) => `<div class="result-card-wrap"><button class="fav-star is-fav" data-remove-favorite="${escapeHtml(item.id)}" type="button">★</button><div class="result-card"><strong>${escapeHtml(item.name)}</strong></div></div>`).join("")
    : emptyState("아직 저장한 법령이 없어요.", "검색 결과 카드의 ☆를 눌러 저장해 보세요.");

  document.querySelectorAll("[data-remove-favorite]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = favorites.find((item) => item.id === button.dataset.removeFavorite);
      if (target) toggleFavorite(target);
      button.closest(".result-card-wrap")?.remove();
      $("searchResultCount").textContent = `${favorites.length}건`;
    });
  });
});

// -----------------------------------------------------------------------------
// 실무어 + 법령지도 검색
// -----------------------------------------------------------------------------
const searchForm = $("search-form");
const searchInput = $("search-input");
const searchType = $("searchType");

function setSearchLoading(q) {
  $("searchResults").classList.add("is-visible");
  $("searchResultTitle").textContent = `“${q}” 검색 중...`;
  $("searchResultCount").textContent = "";
  $("searchPlan").hidden = true;
  ["core-rule-results", "upper-law-results", "related-rule-results", "law-results", "admrul-results"].forEach((id) => {
    $(id).innerHTML = `<div class="loading-row">관련 규정을 찾고 있어요...</div>`;
  });
}

function itemKind(item, fallback) {
  return item.kind || (fallback === "law" ? "law" : "admin_rule");
}

function filterByScope(items, scope) {
  if (scope === "all") return items;
  return items.filter((item) => itemKind(item) === (scope === "law" ? "law" : "admin_rule"));
}

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const q = searchInput.value.trim();
  if (!q) return;

  setSearchLoading(q);
  const scope = searchType.value;
  const includeAdmrul = scope !== "law";

  try {
    const response = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(q)}&include_admrul=${includeAdmrul}&chem_only=true&smart=true`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `서버 오류 (${response.status})`);

    const coreRules = filterByScope(data.core_rules || [], scope);
    const upperLaws = filterByScope(data.upper_laws || [], scope);
    const relatedRules = filterByScope(data.related_rules || [], scope);
    const laws = scope === "admin" ? [] : data.laws || [];
    const adminRules = scope === "law" ? [] : data.admin_rules || [];

    renderSearchResults($("core-rule-results"), coreRules, "admin_rule", { priority: true });
    renderSearchResults($("upper-law-results"), upperLaws, "law", { mapped: true });
    renderSearchResults($("related-rule-results"), relatedRules, "admin_rule", { mapped: true });
    renderSearchResults($("law-results"), laws, "law");
    renderSearchResults($("admrul-results"), adminRules, "admin_rule");

    $("core-count").textContent = coreRules.length;
    $("upper-count").textContent = upperLaws.length;
    $("related-count").textContent = relatedRules.length;
    $("law-count").textContent = laws.length;
    $("admrul-count").textContent = adminRules.length;
    $("additional-count").textContent = laws.length + adminRules.length;

    $("coreResultBlock").hidden = coreRules.length === 0;
    $("upperResultBlock").hidden = upperLaws.length === 0;
    $("relatedResultBlock").hidden = relatedRules.length === 0;
    $("law-results").closest(".result-block").style.display = scope === "admin" ? "none" : "";
    $("admrul-results").closest(".result-block").style.display = scope === "law" ? "none" : "";

    const displayedTotal = coreRules.length + upperLaws.length + relatedRules.length + laws.length + adminRules.length;
    $("searchResultTitle").textContent = `“${data.query}” 검색 결과`;
    $("searchResultCount").textContent = `${displayedTotal}건 · 아카이브 신규 ${data.newly_saved || 0}건`;

    $("searchIntentSummary").textContent = data.intent_summary || data.intent || "관련 법령·행정규칙 확인";
    $("topicChips").innerHTML = (data.topics || []).map((topic) => `<span class="topic-chip"><b>${escapeHtml(topic.label)}</b><small>${escapeHtml((topic.matched_terms || []).slice(0, 3).join(" · "))}</small></span>`).join("") || `<span class="topic-chip neutral"><b>통합검색</b><small>명확한 시설·업무 주제가 감지되지 않았어요.</small></span>`;

    $("checklistItems").innerHTML = (data.checklist || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("") || `<li>공식 법령명과 최신 시행일을 확인해 주세요.</li>`;
    $("expandedTerms").innerHTML = (data.expanded_terms || []).map((term) => `<button type="button" class="term-chip" data-expanded-query="${escapeHtml(term)}">${escapeHtml(term)}</button>`).join("");

    $("searchCorrection").hidden = !data.correction;
    $("searchCorrection").textContent = data.correction || "";
    $("mapVerified").textContent = data.map_verified_on ? data.map_verified_on.replaceAll("-", ".") : "확인 필요";
    $("mapNotice").textContent = data.map_notice || "법령지도는 탐색 순서를 안내하며 공식 법률 해석을 대신하지 않습니다.";
    $("apiWarning").hidden = !data.api_warning;
    $("apiWarning").textContent = data.api_warning ? `외부 API 일부 응답 지연: ${data.api_warning} — 법령지도 결과는 계속 표시됩니다.` : "";

    renderAmbiguities(data.ambiguities || []);
    $("searchPlan").hidden = false;

    document.querySelectorAll("[data-expanded-query]").forEach((button) => {
      button.addEventListener("click", () => {
        searchInput.value = button.dataset.expandedQuery;
        searchForm.requestSubmit();
      });
    });

    $("searchResults").scrollIntoView({ behavior: "smooth", block: "start" });
    loadHomeDashboard();
  } catch (error) {
    $("searchResultTitle").textContent = "검색 중 오류가 발생했어요";
    $("searchPlan").hidden = true;
    $("core-rule-results").innerHTML = emptyState(error.message, "법제처 API 인증·서버 로그를 확인해 주세요.");
    ["upper-law-results", "related-rule-results", "law-results", "admrul-results"].forEach((id) => { $(id).innerHTML = ""; });
  }
});

function renderAmbiguities(items) {
  if (!items.length) {
    $("ambiguityPanel").hidden = true;
    return;
  }
  const first = items[0];
  $("ambiguityMessage").textContent = first.message || "검색 의미를 선택하면 결과가 더 정확해집니다.";
  $("ambiguityOptions").innerHTML = (first.options || []).map((option) => `<button type="button" data-ambiguity-query="${escapeHtml(option.query)}">${escapeHtml(option.label)}</button>`).join("");
  $("ambiguityPanel").hidden = false;
  $("ambiguityOptions").querySelectorAll("[data-ambiguity-query]").forEach((button) => {
    button.addEventListener("click", () => {
      searchInput.value = button.dataset.ambiguityQuery;
      searchForm.requestSubmit();
    });
  });
}

function renderSearchResults(container, items, fallbackKind, options = {}) {
  if (!items.length) {
    container.innerHTML = emptyState("표시할 결과가 없어요.", "검색 범위나 표현을 바꿔 다시 확인해 보세요.");
    return;
  }

  container.innerHTML = items.map((item) => {
    const kind = itemKind(item, fallbackKind);
    const favoriteId = `${kind}:${item.id}`;
    const favorite = isFavorite(favoriteId);
    const officialUrl = item.official_url || item.detail_link
      ? ((item.official_url || item.detail_link).startsWith("http") ? (item.official_url || item.detail_link) : `https://www.law.go.kr${item.official_url || item.detail_link}`)
      : "https://www.law.go.kr";
    const meta = [item.department, item.type, item.promulgation_date ? `공포 ${formatDate(item.promulgation_date)}` : "", item.enforcement_date ? `시행 ${formatDate(item.enforcement_date)}` : ""].filter(Boolean).join(" · ");
    const scoreLabel = item.is_mapped ? (item.rule_role || "법령지도 연결") : `관련도 ${item.relevance_score || 0}`;
    const mappedBadge = item.is_mapped ? `<span class="map-badge">법령지도</span>` : "";
    const topicBadge = item.topic_label ? `<span class="topic-result-badge">${escapeHtml(item.topic_label)}</span>` : "";
    const note = item.rule_note ? `<p class="rule-note">${escapeHtml(item.rule_note)}</p>` : "";
    return `<div class="result-card-wrap ${options.priority ? "is-priority" : ""}">
      <button class="fav-star ${favorite ? "is-fav" : ""}" type="button" data-favorite-id="${favoriteId}" data-favorite-name="${escapeHtml(item.name)}">${favorite ? "★" : "☆"}</button>
      <a class="result-card ${item.is_mapped ? "mapped-card" : ""}" href="${escapeHtml(officialUrl)}" target="_blank" rel="noopener">
        <div class="result-topline"><span><small>${kind === "law" ? "법령" : escapeHtml(item.type || "고시·행정규칙")}</small>${mappedBadge}${topicBadge}</span><span class="relevance-score ${item.is_mapped ? "mapped-score" : ""}">${escapeHtml(scoreLabel)}</span></div>
        <strong>${escapeHtml(item.name || "(이름 없음)")}</strong>
        <span class="r-meta">${escapeHtml(meta || "공식 원문에서 최신 정보 확인")}</span>
        <span class="match-reason">${escapeHtml(item.match_reason || "관련 법령 후보")}</span>
        ${note}
        <span class="official-open">공식 원문 보기 ↗</span>
      </a>
    </div>`;
  }).join("");

  container.querySelectorAll("[data-favorite-id]").forEach((button) => {
    button.addEventListener("click", () => {
      toggleFavorite({ id: button.dataset.favoriteId, name: button.dataset.favoriteName });
      const active = isFavorite(button.dataset.favoriteId);
      button.classList.toggle("is-fav", active);
      button.textContent = active ? "★" : "☆";
    });
  });
}

$("searchReset").addEventListener("click", () => $("searchResults").classList.remove("is-visible"));
document.querySelectorAll("[data-query]").forEach((button) => button.addEventListener("click", () => {
  searchInput.value = button.dataset.query;
  searchForm.requestSubmit();
}));
// 홈 화면의 검색 바로가기
document.querySelectorAll("[data-search-focus]").forEach((button) => button.addEventListener("click", () => {
  activateTab("search");
  requestAnimationFrame(() => {
    searchInput.focus();
    searchInput.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}));


const SHORTCUTS = [
  ["제조·사용시설", "핵심 시설분류", "제조·사용시설", "⚗"],
  ["저장시설", "고정식 탱크·저장조", "저장시설", "▣"],
  ["보관시설", "드럼·IBC·용기", "보관시설", "▤"],
  ["소량취급시설", "기준수량·검사", "소량취급시설", "◇"],
  ["검사·안전진단", "설치·정기·수시검사", "설치검사 안전진단", "⌕"],
  ["화학사고예방관리계획서", "작성·검토·이행", "화학사고예방관리계획서", "♢"],
];

function renderShortcuts() {
  $("lawShortcuts").innerHTML = SHORTCUTS.map(([title, type, query, icon]) => `<button class="law-shortcut" type="button" data-shortcut-query="${escapeHtml(query)}"><span class="law-icon">${icon}</span><strong>${escapeHtml(title)}</strong><span>${escapeHtml(type)}</span></button>`).join("");
  document.querySelectorAll("[data-shortcut-query]").forEach((button) => button.addEventListener("click", () => { searchInput.value = button.dataset.shortcutQuery; searchForm.requestSubmit(); }));
}

// -----------------------------------------------------------------------------
// 홈 대시보드
// -----------------------------------------------------------------------------
async function loadHomeDashboard() {
  try {
    const response = await fetch(`${API_BASE}/api/archive/stats?recent_limit=5&upcoming_limit=5`);
    if (!response.ok) throw new Error("아카이브 통계를 불러오지 못했습니다.");
    const data = await response.json();
    $("archiveTotalBadge").textContent = `${data.total || 0}건`;
    $("upcomingBadge").textContent = `${data.upcoming_count || 0}건`;
    $("recentArchiveList").innerHTML = renderMiniPosts(data.recent || [], "published_date", "아직 쌓인 개정정보가 없어요.");
    $("upcomingList").innerHTML = renderMiniPosts(data.upcoming || [], "enforcement_date", "다가오는 시행일이 없어요.", true);
    bindArchiveOpenButtons();
  } catch (error) {
    $("recentArchiveList").innerHTML = `<div class="soft-empty">${escapeHtml(error.message)}</div>`;
    $("upcomingList").innerHTML = `<div class="soft-empty">배포 후 데이터가 쌓이면 표시됩니다.</div>`;
  }
}

function renderMiniPosts(items, dateField, emptyMessage, showDday = false) {
  if (!items.length) return `<div class="soft-empty">${escapeHtml(emptyMessage)}</div>`;
  return items.map((item) => {
    const dday = showDday ? daysUntil(item[dateField]) : null;
    const dateLabel = showDday && dday !== null ? (dday === 0 ? "D-DAY" : `D-${dday}`) : formatDate(item[dateField]);
    return `<button class="mini-post" type="button" data-archive-id="${item.id}"><span class="mini-post-date">${escapeHtml(dateLabel)}</span><span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.material_type || item.department || "")}</small></span></button>`;
  }).join("");
}

// -----------------------------------------------------------------------------
// 개정 아카이브
// -----------------------------------------------------------------------------
function initializeArchiveYears() {
  const current = new Date().getFullYear();
  const options = [];
  for (let year = current + 1; year >= current - 8; year -= 1) options.push(`<option value="${year}">${year}년</option>`);
  $("archiveYear").insertAdjacentHTML("beforeend", options.join(""));
}

function archiveQueryString() {
  const params = new URLSearchParams();
  const values = {
    keyword: $("archiveKeyword").value.trim(),
    kind: $("archiveKind").value,
    status: $("archiveStatus").value,
    year: $("archiveYear").value,
    task: $("archiveTask").value,
  };
  Object.entries(values).forEach(([key, value]) => { if (value && value !== "all") params.set(key, value); });
  params.set("limit", ARCHIVE_LIMIT);
  params.set("offset", archiveOffset);
  return params.toString();
}

async function loadArchive(reset = false) {
  if (reset) archiveOffset = 0;
  if (reset) $("archiveList").innerHTML = `<div class="loading-row">개정 아카이브를 불러오는 중...</div>`;

  try {
    const [listResponse, statsResponse] = await Promise.all([
      fetch(`${API_BASE}/api/archive?${archiveQueryString()}`),
      fetch(`${API_BASE}/api/archive/stats?recent_limit=0&upcoming_limit=0`),
    ]);
    if (!listResponse.ok) throw new Error(`아카이브 서버 오류 (${listResponse.status})`);
    const data = await listResponse.json();
    const stats = statsResponse.ok ? await statsResponse.json() : {};
    archiveTotal = data.total || 0;

    $("archiveMetricTotal").textContent = stats.total || 0;
    $("archiveMetricMonth").textContent = stats.this_month || 0;
    $("archiveMetricUpcoming").textContent = stats.upcoming_count || 0;
    $("archiveResultSummary").textContent = `조건에 맞는 개정정보 ${archiveTotal}건`;

    const cards = (data.items || []).map(renderArchiveCard).join("");
    if (reset) $("archiveList").innerHTML = cards || emptyState("아카이브 기록이 없어요.", "법령 검색을 실행하거나 뉴스레터 수집기를 연결하면 자동으로 쌓입니다.");
    else $("archiveList").insertAdjacentHTML("beforeend", cards);

    archiveOffset += (data.items || []).length;
    $("archiveLoadMore").hidden = archiveOffset >= archiveTotal;
    bindArchiveOpenButtons();
  } catch (error) {
    $("archiveList").innerHTML = emptyState("아카이브를 불러오지 못했어요.", error.message);
  }
}

function renderArchiveCard(item) {
  const tags = (item.tags || []).slice(0, 5).map((tag) => `<span>#${escapeHtml(tag)}</span>`).join("");
  return `<article class="archive-card">
    <button class="archive-card-main" type="button" data-archive-id="${item.id}">
      <div class="archive-card-top"><div class="archive-badges"><span class="material-badge">${escapeHtml(item.material_type || "자료")}</span><span class="status-badge status-${statusClass(item.status)}">${escapeHtml(item.status || "신규")}</span></div><time>${formatDate(item.published_date)}</time></div>
      <h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.summary || "개정정보가 아카이브에 저장되었습니다.")}</p>
      <div class="archive-date-row">
        ${dateItem("게시", item.published_date, "published")}
        ${dateItem("공포", item.promulgation_date, "promulgated")}
        ${dateItem("시행", item.enforcement_date, "effective")}
        ${dateItem("의견마감", item.deadline_date, "deadline")}
      </div>
      <div class="archive-card-footer"><span>${escapeHtml(item.department || item.source_name || "출처 확인 필요")}</span><div class="archive-tags">${tags}</div></div>
    </button>
    ${item.official_url ? `<a class="official-link" href="${escapeHtml(item.official_url)}" target="_blank" rel="noopener">공식 원문 ↗</a>` : ""}
  </article>`;
}

function dateItem(label, value, code) {
  if (!value) return "";
  return `<span class="archive-date ${code}"><b>${label}</b>${formatDate(value)}</span>`;
}

function statusClass(status = "") {
  if (status.includes("시행 예정") || status.includes("의견")) return "upcoming";
  if (status.includes("변경")) return "changed";
  if (status.includes("현재")) return "current";
  return "new";
}

$("archiveFilterForm").addEventListener("submit", (event) => { event.preventDefault(); loadArchive(true); });
$("archiveReset").addEventListener("click", () => {
  $("archiveFilterForm").reset();
  loadArchive(true);
});
$("archiveLoadMore").addEventListener("click", () => loadArchive(false));

function bindArchiveOpenButtons() {
  document.querySelectorAll("[data-archive-id]").forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => openArchiveDetail(Number(button.dataset.archiveId)));
  });
}

async function openArchiveDetail(id) {
  $("archiveModal").hidden = false;
  document.body.classList.add("modal-open");
  $("archiveModalContent").innerHTML = `<div class="loading-row">게시글을 불러오는 중...</div>`;
  try {
    const response = await fetch(`${API_BASE}/api/archive/${id}`);
    const item = await response.json();
    if (!response.ok) throw new Error(item.detail || "게시글을 불러오지 못했습니다.");
    $("archiveModalContent").innerHTML = renderArchiveDetail(item);
  } catch (error) {
    $("archiveModalContent").innerHTML = emptyState("게시글을 열지 못했어요.", error.message);
  }
}

function renderArchiveDetail(item) {
  const tags = (item.tags || []).map((tag) => `<span class="detail-tag">#${escapeHtml(tag)}</span>`).join("");
  const tasks = (item.related_tasks || []).map((task) => `<li>${escapeHtml(task)}</li>`).join("") || "<li>연결된 실무업무가 아직 없습니다.</li>";
  const laws = (item.related_laws || []).map((law) => `<li>${escapeHtml(law)}</li>`).join("") || "<li>관련 법령 연결은 추후 보완할 수 있습니다.</li>";
  const attachments = (item.attachments || []).map((attachment) => {
    if (typeof attachment === "string") return `<li>${escapeHtml(attachment)}</li>`;
    const label = attachment.name || attachment.title || attachment.url || "첨부파일";
    return `<li>${attachment.url ? `<a href="${escapeHtml(attachment.url)}" target="_blank" rel="noopener">${escapeHtml(label)} ↗</a>` : escapeHtml(label)}</li>`;
  }).join("") || "<li>등록된 첨부파일이 없습니다.</li>";

  return `<header class="detail-header"><div class="archive-badges"><span class="material-badge">${escapeHtml(item.material_type || "자료")}</span><span class="status-badge status-${statusClass(item.status)}">${escapeHtml(item.status)}</span></div><h2 id="archiveModalTitle">${escapeHtml(item.title)}</h2><p>${escapeHtml(item.department || item.source_name || "출처 확인 필요")}</p></header>
    <div class="detail-date-grid">${detailDate("게시일", item.published_date)}${detailDate("공포일", item.promulgation_date)}${detailDate("시행일", item.enforcement_date)}${detailDate("의견마감", item.deadline_date)}${detailDate("수집일", item.collected_at ? item.collected_at.slice(0, 10).replaceAll("-", "") : "")}</div>
    <section class="detail-section official-section"><span class="detail-section-label">공식 자료 기반</span><h3>수집 내용</h3><p>${escapeHtml(item.summary || "공식 자료의 제목과 날짜 정보가 수집되었습니다.")}</p>${item.official_url ? `<a class="primary-link" href="${escapeHtml(item.official_url)}" target="_blank" rel="noopener">공식 원문 확인 ↗</a>` : ""}</section>
    <section class="detail-section findol-section"><span class="detail-section-label">findol 실무 메모</span><h3>운영자 정리</h3><p>${escapeHtml(item.findol_note || "아직 운영자가 작성한 실무 메모가 없습니다. 자동 수집 정보와 수동 해설은 구분해 표시됩니다.")}</p><div class="detail-tags">${tags}</div></section>
    <div class="detail-two-column"><section class="detail-section"><h3>관련 업무</h3><ul>${tasks}</ul></section><section class="detail-section"><h3>관련 법령</h3><ul>${laws}</ul></section></div>
    <section class="detail-section"><h3>첨부파일</h3><ul>${attachments}</ul></section>
    <p class="legal-notice">findol의 요약과 메모는 실무 참고용입니다. 법령의 정확한 문구와 적용 여부는 공식 원문 및 관계기관에서 확인하세요.</p>`;
}

function detailDate(label, value) {
  return `<div><span>${label}</span><strong>${value ? formatDate(value) : "-"}</strong></div>`;
}

function closeArchiveModal() {
  $("archiveModal").hidden = true;
  document.body.classList.remove("modal-open");
}
$("archiveModalClose").addEventListener("click", closeArchiveModal);
$("archiveModal").addEventListener("click", (event) => { if (event.target === $("archiveModal")) closeArchiveModal(); });
document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !$("archiveModal").hidden) closeArchiveModal(); });

// -----------------------------------------------------------------------------
// 개정 캘린더
// -----------------------------------------------------------------------------
const today = new Date();
let calYear = today.getFullYear();
let calMonth = today.getMonth() + 1;

$("cal-prev").addEventListener("click", () => { calMonth -= 1; if (calMonth < 1) { calMonth = 12; calYear -= 1; } loadCalendar(); });
$("cal-next").addEventListener("click", () => { calMonth += 1; if (calMonth > 12) { calMonth = 1; calYear += 1; } loadCalendar(); });
$("calToday").addEventListener("click", () => { calYear = today.getFullYear(); calMonth = today.getMonth() + 1; loadCalendar(); });
$("calendarTask").addEventListener("change", loadCalendar);
document.querySelectorAll("[data-event-type]").forEach((checkbox) => checkbox.addEventListener("change", loadCalendar));

function selectedEventTypes() {
  return [...document.querySelectorAll("[data-event-type]:checked")].map((input) => input.dataset.eventType);
}

async function loadCalendar() {
  $("cal-label").textContent = `${calYear}년 ${calMonth}월`;
  const params = new URLSearchParams({
    year: calYear,
    month: calMonth,
    event_types: selectedEventTypes().join(","),
  });
  if ($("calendarTask").value) params.set("task", $("calendarTask").value);

  $("calendar-grid").innerHTML = `<div class="loading-row calendar-loading">일정을 불러오는 중...</div>`;
  try {
    const response = await fetch(`${API_BASE}/api/calendar?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `서버 오류 (${response.status})`);
    calendarEvents = data.events || [];
    renderCalendarGrid();
    renderMonthEvents();
    if (selectedCalendarDate && selectedCalendarDate.startsWith(`${calYear}${String(calMonth).padStart(2, "0")}`)) renderDayPanel(selectedCalendarDate);
    else resetDayPanel();
  } catch (error) {
    $("calendar-grid").innerHTML = emptyState("캘린더를 불러오지 못했어요.", error.message);
  }
}

function renderCalendarGrid() {
  const firstWeekday = new Date(calYear, calMonth - 1, 1).getDay();
  const daysInMonth = new Date(calYear, calMonth, 0).getDate();
  const monthPrefix = `${calYear}${String(calMonth).padStart(2, "0")}`;
  const byDate = Object.groupBy ? Object.groupBy(calendarEvents, (event) => event.date) : calendarEvents.reduce((acc, event) => { (acc[event.date] ||= []).push(event); return acc; }, {});
  let html = "";
  for (let index = 0; index < firstWeekday; index += 1) html += `<div class="cal-day is-empty"></div>`;

  for (let day = 1; day <= daysInMonth; day += 1) {
    const dateValue = `${monthPrefix}${String(day).padStart(2, "0")}`;
    const events = byDate[dateValue] || [];
    const isToday = today.getFullYear() === calYear && today.getMonth() + 1 === calMonth && today.getDate() === day;
    const eventHtml = events.slice(0, 3).map((event) => `<button class="cal-event event-${event.event_code}" type="button" data-calendar-event-id="${event.archive_id}" data-date="${event.date}" title="${escapeHtml(event.title)}"><b>${event.event_type}</b><span>${escapeHtml(event.title)}</span></button>`).join("");
    html += `<div class="cal-day ${isToday ? "is-today" : ""} ${events.length ? "has-events" : ""}" data-calendar-date="${dateValue}"><button class="cal-day-number" type="button" data-select-date="${dateValue}">${day}</button><div class="cal-events">${eventHtml}${events.length > 3 ? `<button class="more-events" type="button" data-select-date="${dateValue}">+${events.length - 3}건</button>` : ""}</div></div>`;
  }
  $("calendar-grid").innerHTML = html;

  document.querySelectorAll("[data-select-date]").forEach((button) => button.addEventListener("click", () => renderDayPanel(button.dataset.selectDate)));
  document.querySelectorAll("[data-calendar-event-id]").forEach((button) => button.addEventListener("click", (event) => { event.stopPropagation(); openArchiveDetail(Number(button.dataset.calendarEventId)); }));
}

function renderDayPanel(dateValue) {
  selectedCalendarDate = dateValue;
  document.querySelectorAll(".cal-day").forEach((cell) => cell.classList.toggle("is-selected", cell.dataset.calendarDate === dateValue));
  const events = calendarEvents.filter((event) => event.date === dateValue);
  $("dayPanelTitle").textContent = `${formatDate(dateValue)} 일정`;
  $("dayPanelEvents").innerHTML = events.length ? events.map(renderDayEvent).join("") : `<div class="soft-empty">이 날짜에 표시할 일정이 없습니다.</div>`;
  bindArchiveOpenButtons();
}

function resetDayPanel() {
  selectedCalendarDate = null;
  $("dayPanelTitle").textContent = "날짜를 선택해 주세요";
  $("dayPanelEvents").innerHTML = `<div class="soft-empty">달력의 날짜를 누르면 해당 일정이 표시됩니다.</div>`;
}

function renderDayEvent(event) {
  return `<button class="day-event-card event-border-${event.event_code}" type="button" data-archive-id="${event.archive_id}"><span class="event-key key-${event.event_code}">${event.event_type}</span><strong>${escapeHtml(event.title)}</strong><small>${escapeHtml(event.material_type || "")} · ${escapeHtml(event.department || "출처 확인 필요")}</small></button>`;
}

function renderMonthEvents() {
  $("calendarEventCount").textContent = `${calendarEvents.length}건`;
  $("calendar-event-list").innerHTML = calendarEvents.length
    ? calendarEvents.map((event) => `<button class="month-event-row" type="button" data-archive-id="${event.archive_id}"><time>${formatDate(event.date)}</time><span class="event-key key-${event.event_code}">${event.event_type}</span><span class="month-event-main"><strong>${escapeHtml(event.title)}</strong><small>${escapeHtml(event.material_type || "")} · ${escapeHtml(event.department || "")}</small></span></button>`).join("")
    : emptyState("이번 달 일정이 없어요.", "표시 날짜 종류 또는 업무 필터를 변경해 보세요.");
  bindArchiveOpenButtons();
}

// -----------------------------------------------------------------------------
// 초기화
// -----------------------------------------------------------------------------
initializeArchiveYears();
renderShortcuts();
$("favoriteCount").textContent = favorites.length;
loadHomeDashboard();
