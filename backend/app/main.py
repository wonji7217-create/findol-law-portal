from pathlib import Path

from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv()  # law_api를 불러오기 전에 반드시 먼저 실행 (환경변수 선반영)

from . import law_api, storage
from .db import init_db, get_db

app = FastAPI(title="환경·안전 법령 검색 포털 API")

# 프론트엔드를 다른 포트/도구로 따로 띄우고 싶을 때를 대비해 CORS는 열어둠
# (지금은 아래 StaticFiles로 같은 서버에서 서빙하므로 필수는 아님)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "환경·안전 법령 검색 포털"}


@app.get("/api/search")
async def search(
    q: str = Query(..., min_length=1, description="검색 키워드 (예: 안전진단)"),
    include_admrul: bool = Query(True, description="고시·훈령 포함 여부"),
    chem_only: bool = Query(True, description="화학물질관리법 관련 항목만 필터링"),
    page: int = Query(1, ge=1),
    display: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    키워드로 법령(+고시/훈령) 통합 검색.
    chem_only=True(기본값)면 소관부처·법령명 기준으로 화학물질관리법 관련
    항목만 남기고 필터링합니다.
    검색할 때마다 결과를 DB에 누적 저장 -> 이후 /api/timeline, /api/history 에서
    시간에 따른 변경 이력을 확인할 수 있습니다.
    """
    try:
        law_raw = await law_api.search_law(q, display=display, page=page)
        law_results = law_api.normalize_law_results(law_raw)

        admrul_results = []
        if include_admrul:
            admrul_raw = await law_api.search_admrul(q, display=display, page=page)
            admrul_results = law_api.normalize_admrul_results(admrul_raw)

        if chem_only:
            law_results = law_api.filter_chem_related(law_results)
            admrul_results = law_api.filter_chem_related(admrul_results)

        new_law_snapshots = storage.save_law_results(db, law_results, q)
        new_admrul_snapshots = storage.save_admrul_results(db, admrul_results, q)

        return {
            "query": q,
            "laws": law_results,
            "admin_rules": admrul_results,
            "total": len(law_results) + len(admrul_results),
            "newly_saved": new_law_snapshots + new_admrul_snapshots,
        }
    except law_api.LawApiError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/timeline")
def timeline(
    keyword: str | None = Query(None, description="이름에 포함된 키워드로 필터링"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    지금까지 검색을 통해 누적 저장된 법령/고시를 최근 수집일 순으로 반환.
    (날짜별 타임라인 화면에서 그대로 사용 가능)
    """
    return {"items": storage.get_timeline(db, keyword=keyword, limit=limit)}


@app.get("/api/calendar")
def calendar(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
):
    """
    지정한 연/월의 공포일·시행일 캘린더 이벤트 목록.
    (현재까지 검색을 통해 수집된 데이터 기준)
    """
    return {"year": year, "month": month, "events": storage.get_calendar_events(db, year, month)}


@app.get("/api/history/{kind}/{external_id}")
def history(kind: str, external_id: str, db: Session = Depends(get_db)):
    """
    법령/행정규칙 하나(external_id)의 전체 변경 이력(개정이력)을 시간순으로 반환.
    kind: 'law' 또는 'admin_rule'
    """
    if kind not in ("law", "admin_rule"):
        raise HTTPException(status_code=400, detail="kind는 'law' 또는 'admin_rule'이어야 합니다.")
    items = storage.get_history_for_id(db, kind, external_id)
    if not items:
        raise HTTPException(status_code=404, detail="해당 항목의 이력이 없습니다. 먼저 검색을 통해 수집해주세요.")
    return {"kind": kind, "external_id": external_id, "history": items}


# 프론트엔드 정적 파일 서빙. 반드시 /api/* 라우트들 아래에 위치해야
# "/" 하위 모든 경로를 가로채는 이 마운트가 API 라우트를 덮어쓰지 않음.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
