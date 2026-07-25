<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>findol 관리자 | 환경지식 DB</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.css" />
  <link rel="stylesheet" href="admin.css" />
</head>
<body>
  <div class="admin-shell">
    <aside class="sidebar">
      <a class="admin-brand" href="/"><span>f</span><div><strong>findol</strong><small>관리자</small></div></a>
      <nav>
        <button class="side-link active" type="button">환경지식 DB</button>
        <a class="side-link" href="/">사이트 보기</a>
      </nav>
      <div class="sidebar-note">코드를 수정하지 않고 검색 주제·핵심 고시·체크리스트를 관리합니다.</div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">FINDOL KNOWLEDGE STUDIO</p>
          <h1>환경지식 관리자</h1>
          <p>실무 검색의 핵심 데이터인 주제, 검색어, 고시, 확인사항을 한곳에서 편집합니다.</p>
        </div>
        <div class="top-actions">
          <button id="logoutBtn" class="ghost" type="button">관리자 로그아웃</button>
          <button id="newBtn" class="primary" type="button">+ 새 주제</button>
        </div>
      </header>

      <section class="stats" id="stats">
        <article><span>전체 주제</span><strong id="topicCount">-</strong></article>
        <article><span>사용 중</span><strong id="activeCount">-</strong></article>
        <article><span>개정 아카이브</span><strong id="archiveCount">-</strong></article>
      </section>

      <section class="manager-grid">
        <div class="list-panel">
          <div class="panel-head">
            <div><h2>지식 주제</h2><p>저장시설, 보관시설, 설치검사처럼 검색의 기준이 되는 단위입니다.</p></div>
            <input id="filterInput" type="search" placeholder="주제 또는 검색어 찾기" />
          </div>
          <div id="topicList" class="topic-list"></div>
        </div>

        <div class="editor-panel">
          <div class="panel-head editor-head">
            <div><h2 id="editorTitle">새 지식 주제</h2><p id="editorSubtitle">검색과 법령 연결에 필요한 내용을 입력하세요.</p></div>
            <label class="switch"><input id="activeInput" type="checkbox" checked /><span></span>사용</label>
          </div>

          <form id="topicForm">
            <input id="topicId" type="hidden" />
            <div class="two-col">
              <label>주제 ID <small>영문·숫자·밑줄</small><input id="topicKey" required placeholder="storage_facility" /></label>
              <label>화면 표시명<input id="labelInput" required placeholder="저장시설" /></label>
            </div>
            <label>한 줄 설명<textarea id="descriptionInput" rows="2" placeholder="이 주제가 어떤 시설·업무를 다루는지 설명"></textarea></label>
            <label>검색 의도 안내문<textarea id="intentInput" rows="2" placeholder="저장시설의 설치·관리·검사 기준 확인"></textarea></label>

            <div class="two-col">
              <label>대표 검색어 <small>한 줄에 하나</small><textarea id="triggersInput" rows="7" placeholder="저장시설&#10;저장탱크&#10;약품탱크"></textarea></label>
              <label>확장 검색어 <small>한 줄에 하나</small><textarea id="searchTermsInput" rows="7" placeholder="방유제&#10;액위계&#10;과충전방지"></textarea></label>
            </div>

            <section class="form-section">
              <div class="section-title"><div><h3>핵심 적용 규정</h3><p>검색 결과 가장 위에 고정할 고시·법령입니다.</p></div><button type="button" class="mini" data-add-rule="primary">+ 규정 추가</button></div>
              <div id="primaryRules" class="rule-list"></div>
            </section>

            <section class="form-section">
              <div class="section-title"><div><h3>상위 법령</h3><p>화학물질관리법, 시행령, 시행규칙 등 상위 근거입니다.</p></div><button type="button" class="mini" data-add-rule="upper">+ 법령 추가</button></div>
              <div id="upperLaws" class="rule-list"></div>
            </section>

            <section class="form-section">
              <div class="section-title"><div><h3>함께 확인할 규정</h3><p>검사·안전진단 등 같이 봐야 할 규정입니다.</p></div><button type="button" class="mini" data-add-rule="related">+ 규정 추가</button></div>
              <div id="relatedRules" class="rule-list"></div>
            </section>

            <div class="two-col">
              <label>먼저 확인할 사항 <small>한 줄에 하나</small><textarea id="checklistInput" rows="7" placeholder="저장 용량&#10;취급물질 함량&#10;설치 위치"></textarea></label>
              <label>관련 업무 <small>한 줄에 하나</small><textarea id="tasksInput" rows="7" placeholder="설치검사&#10;정기검사&#10;변경신고"></textarea></label>
            </div>
            <div class="two-col compact-row">
              <label>우선순위<input id="priorityInput" type="number" min="0" max="500" value="50" /></label>
              <label>관리자 메모<input id="notesInput" placeholder="내부 관리용 메모" /></label>
            </div>

            <div class="form-actions">
              <button id="deleteBtn" class="danger" type="button" hidden>삭제</button>
              <div></div>
              <button class="ghost" id="resetBtn" type="button">초기화</button>
              <button class="primary" type="submit">저장하기</button>
            </div>
          </form>
        </div>
      </section>
    </main>
  </div>

  <dialog id="loginDialog">
    <form method="dialog" id="loginForm">
      <div class="login-mark">f</div>
      <h2>관리자 인증</h2>
      <p>Render에 등록한 <code>ADMIN_TOKEN</code> 값을 입력하세요.</p>
      <input id="tokenInput" type="password" autocomplete="current-password" placeholder="관리자 토큰" required />
      <p id="loginError" class="error"></p>
      <button class="primary" type="submit">관리자 화면 열기</button>
    </form>
  </dialog>

  <template id="ruleTemplate">
    <div class="rule-row">
      <select class="rule-kind"><option value="admin_rule">고시·행정규칙</option><option value="law">법령</option></select>
      <input class="rule-title" placeholder="규정명" />
      <input class="rule-url" placeholder="공식 원문 URL" />
      <button type="button" class="remove-rule" aria-label="삭제">×</button>
    </div>
  </template>
  <div id="toast" class="toast"></div>
  <script src="admin.js"></script>
</body>
</html>
