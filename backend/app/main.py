from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

load_dotenv()

from . import law_api, lawmaking_api, storage, substance_service
from .db import init_db, get_db, SessionLocal
from .search_engine import (
    build_search_plan,
    rank_results,
    inject_mapped_results,
    public_plan,
    LAW_MAP_PATH,
)


app = FastAPI(title="findol 환경지식·화학법령 플랫폼 API", version="5.9.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    db = SessionLocal()
    try:
        storage.backfill_archive_from_snapshots(db)
        storage.seed_knowledge_topics(db, LAW_MAP_PATH)
    finally:
        db.close()


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    stats = storage.get_archive_stats(db, recent_limit=0, upcoming_limit=0)
    return {
        "status": "ok",
        "service": "findol 화학법령 검색·개정 아카이브",
        "version": "5.9.0",
        "archive_count": stats["total"],
        "lawmaking_api_configured": lawmaking_api.configured(),
    }


async def _search_terms(
    terms: list[str],
    *,
    target: str,
    display: int,
    page: int,
) -> list[dict]:
    """확장 검색어를 병렬 호출하고 external_id 기준으로 합침."""
    search_fn = law_api.search_law if target == "law" else law_api.search_admrul
    normalize_fn = law_api.normalize_law_results if target == "law" else law_api.normalize_admrul_results

    responses = await asyncio.gather(
        *(search_fn(term, display=display, page=page) for term in terms),
        return_exceptions=True,
    )

    merged: dict[str, dict] = {}
    errors: list[Exception] = []
    for term, response in zip(terms, responses):
        if isinstance(response, Exception):
            errors.append(response)
            continue
        for item in normalize_fn(response):
            external_id = item.get("id")
            if not external_id:
                continue
            if external_id not in merged:
                merged[external_id] = {**item, "_source_terms": [term]}
            elif term not in merged[external_id]["_source_terms"]:
                merged[external_id]["_source_terms"].append(term)

    if not merged and errors:
        first = errors[0]
        if isinstance(first, law_api.LawApiError):
            raise first
        raise law_api.LawApiError(str(first))

    return list(merged.values())


@app.get("/api/search")
async def search(
    q: str = Query(..., min_length=1, description="법령명 또는 실무 표현"),
    include_admrul: bool = Query(True),
    chem_only: bool = Query(True),
    smart: bool = Query(True, description="검색어 사전·법령지도 확장 검색"),
    page: int = Query(1, ge=1),
    display: int = Query(20, ge=1, le=50),
    x_findol_session: str | None = Header(None, alias="X-Findol-Session"),
    db: Session = Depends(get_db),
):
    """실무 표현을 시설·업무 주제로 분류하고 핵심 적용 규정을 우선 제시한다."""
    plan = build_search_plan(q, max_terms=14)

    # 관리자 페이지에서 편집한 환경지식 주제를 정적 법령지도 위에 합친다.
    dynamic_topics = storage.dynamic_knowledge_matches(db, q, limit=3)
    if dynamic_topics:
        existing_topic_ids = {item.get("id") for item in plan.topics}
        for topic in dynamic_topics:
            if topic["topic_key"] not in existing_topic_ids:
                plan.topics.append({
                    "id": topic["topic_key"],
                    "label": topic["label"],
                    "score": topic["score"],
                    "matched_terms": topic["matched_terms"],
                    "intent_summary": topic["intent_summary"],
                    "source": "admin_db",
                })
            plan.expanded_terms.extend(topic["search_terms"][:6])
            plan.checklist.extend(topic["checklist"][:7])
            for field_name, target in (("primary_rules", plan.primary_rules), ("upper_laws", plan.upper_laws), ("related_rules", plan.related_rules)):
                for rule in topic[field_name]:
                    target.append({**rule, "topic_id": topic["topic_key"], "topic_label": topic["label"]})
        plan.expanded_terms = list(dict.fromkeys(plan.expanded_terms))[:10]
        plan.checklist = list(dict.fromkeys(plan.checklist))[:7]
        if dynamic_topics[0].get("intent_summary"):
            plan.intent_summary = dynamic_topics[0]["intent_summary"]

    # 실제 이용자가 검색한 표현을 개인정보 없이 집계한다.
    storage.record_search_event(
        db,
        raw_query=q,
        normalized_query=plan.normalized_query,
        topic_label=plan.topics[0].get("label") if plan.topics else None,
        session_id=x_findol_session,
    )

    def unique_terms(values: list[str], limit: int) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            value = (value or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
            if len(result) >= limit:
                break
        return result

    if smart:
        # 일반 실무어와 핵심 규정명을 함께 검색한다. 법령/행정규칙 API 호출 수는
        # 각각 최대 10회로 제한해 응답 지연과 외부 API 부하를 줄인다.
        law_terms = unique_terms(plan.expanded_terms[:6] + plan.law_search_terms, 10)
        admin_terms = unique_terms(plan.expanded_terms[:6] + plan.rule_search_terms, 10)
    else:
        law_terms = [plan.normalized_query]
        admin_terms = [plan.normalized_query]

    law_results: list[dict] = []
    admrul_results: list[dict] = []
    warnings: list[str] = []

    try:
        law_results = await _search_terms(law_terms, target="law", display=display, page=page)
    except law_api.LawApiError as exc:
        warnings.append(f"법령 API: {exc}")

    if include_admrul:
        try:
            admrul_results = await _search_terms(admin_terms, target="admrul", display=display, page=page)
        except law_api.LawApiError as exc:
            warnings.append(f"행정규칙 API: {exc}")

    if chem_only:
        law_results = law_api.filter_chem_related(law_results)
        admrul_results = law_api.filter_chem_related(admrul_results)

    law_results = rank_results(law_results, plan)
    admrul_results = rank_results(admrul_results, plan)

    # API 결과와 별개로 법령지도에 등록된 핵심 규정은 결과 상단에 보장한다.
    mapped = inject_mapped_results(law_results, admrul_results, plan)
    all_laws = rank_results(mapped["all_laws"], plan)
    all_admin_rules = rank_results(mapped["all_admin_rules"], plan)

    core_rules = [item for item in all_laws + all_admin_rules if item.get("map_group") == "core"]
    upper_laws = [item for item in all_laws + all_admin_rules if item.get("map_group") == "upper"]
    related_rules = [item for item in all_laws + all_admin_rules if item.get("map_group") == "related"]
    general_laws = [item for item in all_laws if not item.get("map_group")]
    general_admin_rules = [item for item in all_admin_rules if not item.get("map_group")]

    # 법제처에서 실제로 받은 결과만 변경 스냅샷으로 저장한다.
    api_laws = [item for item in all_laws if item.get("source") != "law_map" and not str(item.get("id", "")).startswith("map-")]
    api_admin_rules = [item for item in all_admin_rules if item.get("source") != "law_map" and not str(item.get("id", "")).startswith("map-")]
    new_law_snapshots = storage.save_law_results(db, api_laws, q)
    new_admrul_snapshots = storage.save_admrul_results(db, api_admin_rules, q)

    for item in all_laws + all_admin_rules:
        item.pop("_source_terms", None)

    total = len(core_rules) + len(upper_laws) + len(related_rules) + len(general_laws) + len(general_admin_rules)
    if warnings and total == 0:
        raise HTTPException(status_code=502, detail=" / ".join(warnings))

    return {
        **public_plan(plan),
        "core_rules": core_rules,
        "upper_laws": upper_laws,
        "related_rules": related_rules,
        "laws": general_laws,
        "admin_rules": general_admin_rules,
        "total": total,
        "newly_saved": new_law_snapshots + new_admrul_snapshots,
        "api_warning": " / ".join(warnings) if warnings else None,
        "search_terms_used": {"law": law_terms, "admin_rule": admin_terms if include_admrul else []},
    }


@app.get("/api/substances/meta")
def substance_meta():
    """업로드된 화학물질정보처리시스템 자료의 검색 범위와 기준일을 반환한다."""
    return {
        **substance_service.get_meta(),
        "notice_verified_on": substance_service.get_notice_data().get("verified_on"),
        "notice_warning": substance_service.get_notice_data().get("notice"),
    }


@app.get("/api/substances/search")
def substance_search(
    q: str = Query(..., min_length=1, description="물질명, CAS 번호 또는 함량 포함 표현"),
    limit: int = Query(10, ge=1, le=30),
):
    """공식 다운로드 엑셀 기반 물질정보와 별도 개정·행정예고 이벤트를 함께 검색한다."""
    try:
        return substance_service.search_substances(q, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/api/substances/{cas_no}")
def substance_detail(
    cas_no: str,
    concentration: float | None = Query(None, ge=0, le=100),
):
    result = substance_service.get_substance_by_cas(cas_no, concentration=concentration)
    if not result:
        raise HTTPException(status_code=404, detail="해당 CAS 번호의 물질을 찾지 못했습니다.")
    return result


@app.get("/api/search/popular")
def popular_searches(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """findol 사이트 안에서 실제로 많이 검색된 표현을 익명 집계한다."""
    return storage.get_popular_searches(db, days=days, limit=limit)


@app.get("/api/archive/stats")
def archive_stats(
    recent_limit: int = Query(5, ge=0, le=20),
    upcoming_limit: int = Query(5, ge=0, le=20),
    db: Session = Depends(get_db),
):
    return storage.get_archive_stats(db, recent_limit, upcoming_limit)


@app.get("/api/archive")
def archive_list(
    keyword: str | None = Query(None),
    kind: str | None = Query(None),
    status: str | None = Query(None),
    year: int | None = Query(None, ge=2000, le=2100),
    department: str | None = Query(None),
    task: str | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return storage.get_archive(
        db,
        keyword=keyword,
        kind=kind,
        status=status,
        year=year,
        department=department,
        task=task,
        limit=limit,
        offset=offset,
    )


class ArchiveImportPayload(BaseModel):
    source_key: str | None = Field(None, description="원문 URL 또는 수집기 고유키")
    kind: str = "material"
    external_id: str | None = None
    title: str
    material_type: str = "공고·자료"
    department: str | None = None
    source_name: str | None = None
    official_url: str | None = None
    source_query: str | None = None
    published_date: str | None = None
    promulgation_date: str | None = None
    enforcement_date: str | None = None
    deadline_date: str | None = None
    summary: str | None = None
    findol_note: str | None = None
    tags: list[str] = Field(default_factory=list)
    related_laws: list[str] = Field(default_factory=list)
    related_tasks: list[str] = Field(default_factory=list)
    attachments: list[dict | str] = Field(default_factory=list)


@app.post("/api/archive/import")
def archive_import(
    payload: ArchiveImportPayload,
    x_admin_token: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """기존 뉴스레터/크롤러용 등록 API. ARCHIVE_ADMIN_TOKEN 설정 시에만 동작."""
    expected = os.getenv("ARCHIVE_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="ARCHIVE_ADMIN_TOKEN 환경변수가 설정되지 않았습니다.")
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="아카이브 등록 권한이 없습니다.")

    payload_dict = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    item, created = storage.import_archive_entry(db, payload_dict)
    return {"created": created, "item": item}




@app.get("/api/archive/{entry_id}")
def archive_detail(entry_id: int, db: Session = Depends(get_db)):
    item = storage.get_archive_item(db, entry_id)
    if not item:
        raise HTTPException(status_code=404, detail="해당 아카이브 게시글을 찾을 수 없습니다.")
    return item


@app.get("/api/calendar")
def calendar(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    event_types: str = Query("published,promulgated,effective,deadline"),
    kind: str | None = Query(None),
    task: str | None = Query(None),
    db: Session = Depends(get_db),
):
    selected = [value.strip() for value in event_types.split(",") if value.strip()]
    return {
        "year": year,
        "month": month,
        "events": storage.get_calendar_events(db, year, month, selected, kind=kind, task=task),
    }


@app.get("/api/timeline")
def timeline(
    keyword: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return {"items": storage.get_timeline(db, keyword=keyword, limit=limit)}


@app.get("/api/history/{kind}/{external_id}")
def history(kind: str, external_id: str, db: Session = Depends(get_db)):
    if kind not in ("law", "admin_rule"):
        raise HTTPException(status_code=400, detail="kind는 'law' 또는 'admin_rule'이어야 합니다.")
    items = storage.get_history_for_id(db, kind, external_id)
    if not items:
        raise HTTPException(status_code=404, detail="해당 항목의 이력이 없습니다.")
    return {"kind": kind, "external_id": external_id, "history": items}


def _require_admin(x_admin_token: str | None = Header(None)):
    expected = os.getenv("ADMIN_TOKEN") or os.getenv("ARCHIVE_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN 환경변수가 설정되지 않았습니다.")
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="관리자 권한이 없습니다.")
    return True


class KnowledgeRule(BaseModel):
    title: str
    kind: str = "admin_rule"
    role: str | None = None
    department: str | None = None
    official_url: str | None = None
    note: str | None = None


class KnowledgeTopicPayload(BaseModel):
    topic_key: str = Field(..., min_length=2, max_length=80)
    label: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    intent_summary: str | None = None
    triggers: list[str] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    primary_rules: list[KnowledgeRule] = Field(default_factory=list)
    upper_laws: list[KnowledgeRule] = Field(default_factory=list)
    related_rules: list[KnowledgeRule] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    related_tasks: list[str] = Field(default_factory=list)
    notes: str | None = None
    is_active: bool = True
    priority: int = Field(50, ge=0, le=500)


@app.get("/api/admin/summary")
def admin_summary(_: bool = Depends(_require_admin), db: Session = Depends(get_db)):
    topics = storage.list_knowledge_topics(db)
    return {
        "topic_count": len(topics),
        "active_count": sum(1 for item in topics if item["is_active"]),
        "archive_count": storage.get_archive_stats(db, 0, 0)["total"],
        "lawmaking_api_configured": lawmaking_api.configured(),
    }


class LawmakingSyncPayload(BaseModel):
    include_administrative: bool = True
    include_legislative: bool = True
    max_items: int = Field(60, ge=1, le=200)


@app.post("/api/admin/lawmaking/sync")
async def lawmaking_sync(
    payload: LawmakingSyncPayload,
    _: bool = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    """국민참여입법센터의 행정예고·입법예고를 수집해 개정 아카이브에 반영한다."""
    if not lawmaking_api.configured():
        raise HTTPException(status_code=503, detail="LAWMAKING_API_OC 환경변수가 설정되지 않았습니다.")
    try:
        items = await lawmaking_api.collect_candidates(
            include_administrative=payload.include_administrative,
            include_legislative=payload.include_legislative,
            max_items=payload.max_items,
        )
    except lawmaking_api.LawmakingApiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    created = 0
    unchanged = 0
    imported_items = []
    for item in items:
        archived, was_created = storage.import_archive_entry(db, lawmaking_api.to_archive_payload(item))
        imported_items.append({
            "title": archived["title"],
            "material_type": archived["material_type"],
            "department": archived["department"],
            "created": was_created,
        })
        if was_created:
            created += 1
        else:
            unchanged += 1

    return {
        "fetched": len(items),
        "created_or_changed": created,
        "unchanged": unchanged,
        "items": imported_items[:30],
    }


@app.get("/api/admin/knowledge")
def admin_knowledge_list(
    keyword: str | None = Query(None),
    _: bool = Depends(_require_admin),
    db: Session = Depends(get_db),
):
    return {"items": storage.list_knowledge_topics(db, keyword)}


@app.get("/api/admin/knowledge/{topic_id}")
def admin_knowledge_detail(topic_id: int, _: bool = Depends(_require_admin), db: Session = Depends(get_db)):
    item = storage.get_knowledge_topic(db, topic_id)
    if not item:
        raise HTTPException(status_code=404, detail="환경지식 주제를 찾을 수 없습니다.")
    return item


@app.post("/api/admin/knowledge")
def admin_knowledge_create(payload: KnowledgeTopicPayload, _: bool = Depends(_require_admin), db: Session = Depends(get_db)):
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    try:
        return storage.save_knowledge_topic(db, data)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"저장하지 못했습니다: {exc}")


@app.put("/api/admin/knowledge/{topic_id}")
def admin_knowledge_update(topic_id: int, payload: KnowledgeTopicPayload, _: bool = Depends(_require_admin), db: Session = Depends(get_db)):
    if not storage.get_knowledge_topic(db, topic_id):
        raise HTTPException(status_code=404, detail="환경지식 주제를 찾을 수 없습니다.")
    data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    try:
        return storage.save_knowledge_topic(db, data, topic_id=topic_id)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"수정하지 못했습니다: {exc}")


@app.delete("/api/admin/knowledge/{topic_id}")
def admin_knowledge_delete(topic_id: int, _: bool = Depends(_require_admin), db: Session = Depends(get_db)):
    if not storage.delete_knowledge_topic(db, topic_id):
        raise HTTPException(status_code=404, detail="환경지식 주제를 찾을 수 없습니다.")
    return {"deleted": True}


FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
