> 현재 적용본: **v5.6 독립 물질검색 + 함량기준 이상 분류 요약 + 엑셀 기반 47,520개 물질 DB**

# findol v3 — 실무 검색 · 법령지도 · 개정 아카이브 · 개정 캘린더

findol은 화학물질관리법 실무자가 정확한 법령명을 몰라도 시설·업무 표현으로 관련 규정을 찾고, 개정정보와 시행일을 놓치지 않도록 돕는 개인 업무도구입니다.

> 중요: 검색 의도와 법령지도는 **탐색 순서 안내**입니다. 법률 적용 여부를 자동 판정하지 않으며, 최신 공식 원문과 관계기관 확인이 필요합니다.

## v3에서 달라진 핵심

### 1. 검색어 사전

`backend/app/data/search_dictionary.csv`에서 다음 정보를 관리합니다.

- 오타 교정: `희선탱크 → 희석탱크`
- 현장 약어: `화관서 → 화학사고예방관리계획서`
- 시설 표현 확장: `저장탱크 → 저장시설`
- 선택이 필요한 모호어: `탱크`, `운반`, `배관`, `변경`

CSV 파일이므로 Excel에서도 편집할 수 있습니다.

### 2. 법령지도

`backend/app/data/law_map.json`에서 시설·업무 주제와 핵심 규정을 연결합니다.

예를 들어 `저장시설`을 검색하면 단순히 비슷한 단어만 검색하지 않고 다음 순서로 보여줍니다.

1. 핵심 적용 규정
   - 유해화학물질 제조·사용·저장시설 설치 및 관리에 관한 고시
2. 상위 법령
   - 화학물질관리법
   - 화학물질관리법 시행령
   - 화학물질관리법 시행규칙
3. 함께 확인할 규정
   - 검사·안전진단 규정
   - 소량취급시설 고시
4. 법제처 API 추가 검색 결과

현재 법령지도에는 다음 16개 주제가 들어 있습니다.

- 제조·사용시설
- 저장시설
- 보관시설
- 소량취급시설
- 검사·안전진단
- 배관·밸브·플랜지
- 누출·유출 방지
- 차량 운반시설
- 차량 운송시설
- 운반용기
- 사외배관 이송시설
- 영업허가·변경
- 화학사고예방관리계획서
- 유해화학물질 취급기준
- 안전거리·보호대상
- 관리자·교육

### 3. 검색 의도와 확인 목록

검색어에서 시설·업무 주제를 감지해 다음 내용을 표시합니다.

- findol이 이해한 검색 목적
- 감지한 주제와 매칭된 표현
- 먼저 확인할 사항
- 함께 검색한 표현
- 모호한 검색어의 선택지
- 법령지도 기준일과 주의문구

예시:

```text
검색어: 희석탱크 설치검사

검색 목적:
제조·사용 공정 또는 설비의 설치·관리기준과 검사 적용 여부 확인

핵심 규정:
- 유해화학물질 제조·사용·저장시설 설치 및 관리에 관한 고시
- 유해화학물질 취급시설의 설치·정기·수시검사 및 안전진단의 방법 등에 관한 규정
```

### 4. 모호어 선택 기능

다음처럼 의미가 여러 개인 단어는 임의로 하나로 확정하지 않습니다.

```text
탱크
→ 공정에서 사용하는 탱크
→ 고정식 저장탱크
→ 차량의 탱크로리
```

선택한 표현으로 다시 검색해 적용 고시를 좁힙니다.

### 5. 개정 아카이브

검색 또는 외부 뉴스레터 수집기에서 들어온 자료를 최신 게시순으로 보관합니다.

- 자료 유형·상태·연도·업무 필터
- 게시일·공포일·시행일·의견제출 마감일 구분
- 공식 자료와 findol 실무 메모 분리
- 동일 자료의 신규·변경 스냅샷 보관

### 6. 개정 캘린더

아카이브 게시글 한 건의 날짜를 월간 달력에 자동 표시합니다.

- 게시일
- 공포일
- 시행일
- 의견제출 마감일

날짜 또는 일정을 누르면 같은 아카이브 상세글로 연결됩니다.

## 폴더 구조

```text
law-portal/
├─ backend/
│  ├─ app/
│  │  ├─ data/
│  │  │  ├─ search_dictionary.csv  검색어·오타·약어 사전
│  │  │  └─ law_map.json           주제별 핵심 법령 연결표
│  │  ├─ main.py                   API 라우트와 화면 서빙
│  │  ├─ law_api.py                국가법령정보 Open API 호출
│  │  ├─ search_engine.py          의도 분석·법령지도·관련도 계산
│  │  ├─ storage.py                아카이브·캘린더·스냅샷
│  │  ├─ models.py                 DB 테이블
│  │  └─ db.py                     SQLite/PostgreSQL 연결
│  ├─ tests/
│  │  └─ test_search_engine.py
│  ├─ requirements.txt
│  └─ .env.example
├─ frontend/
│  ├─ index.html
│  ├─ style.css
│  └─ script.js
├─ SEARCH_MAP_GUIDE.md
└─ UPDATE_GUIDE.md
```

## 로컬 실행

프로젝트 최상위 폴더에서 PowerShell을 엽니다.

```powershell
py -m pip install -r backend\requirements.txt
cd backend
Copy-Item .env.example .env
```

`backend/.env`를 열어 법제처 인증값을 입력합니다.

```env
LAW_API_OC=본인의_법제처_OC
ARCHIVE_ADMIN_TOKEN=본인만_아는_긴_문자열
```

실행:

```powershell
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저:

```text
http://127.0.0.1:8000
```

서버 종료:

```text
Ctrl + C
```

## Render 설정

Root Directory는 비워둡니다.

```text
Build Command
pip install -r backend/requirements.txt
```

```text
Start Command
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

환경변수:

```text
LAW_API_OC=법제처 인증값
ARCHIVE_ADMIN_TOKEN=긴 비밀 문자열
```

운영 DB를 연결할 때:

```text
DATABASE_URL=Supabase 또는 PostgreSQL 연결 문자열
```

## 테스트

검색어 사전과 법령지도 기본 동작 테스트:

```powershell
cd backend
py -m unittest discover -s tests -v
```

검증 항목:

- 저장시설 → 제조·사용·저장시설 고시
- 보관시설 → 보관시설 고시
- 희석탱크 → 제조·사용시설
- 탱크 → 선택질문
- 탱크로리 → 차량 운송시설
- 외부 API가 없어도 법령지도 핵심 규정 생성

## 뉴스레터 수집기 연동

```http
POST /api/archive/import
X-Admin-Token: ARCHIVE_ADMIN_TOKEN 값
Content-Type: application/json
```

예시:

```json
{
  "source_key": "https://기관주소/게시글/1234",
  "kind": "notice",
  "title": "유해화학물질 취급시설 관련 고시 개정",
  "material_type": "안전원고시",
  "department": "화학물질안전원",
  "official_url": "https://기관주소/게시글/1234",
  "published_date": "2026-07-25",
  "promulgation_date": "2026-07-25",
  "enforcement_date": "2026-08-01",
  "summary": "공식 게시글 설명",
  "findol_note": "운영자가 검토한 실무 메모",
  "tags": ["저장시설", "검사·안전진단"],
  "related_tasks": ["저장시설", "검사·안전진단"]
}
```

## 주의사항

1. `backend/.env`를 GitHub에 올리지 마세요.
2. 법령지도는 직접 관리하는 연결표이므로 정기적으로 최신 상태를 검토해야 합니다.
3. Render 무료 서버의 로컬 SQLite 파일은 재배포·재시작 시 사라질 수 있습니다.
4. 아카이브를 장기간 보존하려면 외부 PostgreSQL을 연결하세요.
5. 검색 결과에 표시된 공식 원문에서 시행일·연혁·개정문을 다시 확인하세요.

---

## v4 환경지식 관리자

관리자 페이지: `/admin.html`

환경변수 `ADMIN_TOKEN`으로 로그인하며, 환경지식 주제·대표 검색어·핵심 규정·상위 법령·관련 규정·체크리스트를 웹에서 편집할 수 있습니다. 관리자 DB에서 저장한 내용은 검색에 즉시 반영됩니다. 자세한 설정은 `ADMIN_GUIDE.md`를 참고하세요.
