"""검색 스냅샷 저장, 개정 아카이브, 캘린더 조회 로직."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import hashlib
import json
import re
from typing import Iterable

from sqlalchemy import or_, and_, func
from sqlalchemy.orm import Session

from . import models


KST = ZoneInfo("Asia/Seoul")

def _now_local() -> datetime:
    return datetime.now(KST).replace(tzinfo=None)

def _today_yyyymmdd() -> str:
    return datetime.now(KST).strftime("%Y%m%d")


def _clean_search_query(value: str | None) -> str:
    value = re.sub(r"\s+", " ", (value or "").strip())
    return value[:120]


def record_search_event(
    db: Session,
    *,
    raw_query: str,
    normalized_query: str,
    topic_label: str | None = None,
    session_id: str | None = None,
    dedupe_minutes: int = 10,
) -> bool:
    """내부 검색어를 익명 집계한다.

    IP·이메일·계정은 저장하지 않는다. 브라우저 세션값은 SHA-256 해시 일부만
    저장하며, 같은 세션/검색어가 짧은 시간에 반복되면 한 번으로 집계한다.
    """
    raw = _clean_search_query(raw_query)
    normalized = _clean_search_query(normalized_query) or raw
    if not normalized:
        return False

    session_key = None
    if session_id:
        session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
        cutoff = _now_local() - timedelta(minutes=max(1, dedupe_minutes))
        duplicate = (
            db.query(models.SearchEvent)
            .filter(
                models.SearchEvent.session_key == session_key,
                models.SearchEvent.normalized_query == normalized,
                models.SearchEvent.searched_at >= cutoff,
            )
            .first()
        )
        if duplicate:
            return False

    db.add(models.SearchEvent(
        raw_query=raw,
        normalized_query=normalized,
        topic_label=_clean_search_query(topic_label) if topic_label else None,
        session_key=session_key,
        searched_at=_now_local(),
    ))
    db.commit()
    return True


def get_popular_searches(db: Session, *, days: int = 30, limit: int = 6) -> dict:
    """최근 사이트 내부 검색어 순위를 반환한다.

    동일 브라우저의 짧은 시간 내 반복 검색은 저장 단계에서 제거된다.
    정렬은 검색 횟수 우선, 동률이면 가장 최근 검색 순이다.
    """
    days = max(1, min(int(days), 365))
    limit = max(1, min(int(limit), 20))
    cutoff = _now_local() - timedelta(days=days)
    events = (
        db.query(models.SearchEvent)
        .filter(models.SearchEvent.searched_at >= cutoff)
        .order_by(models.SearchEvent.searched_at.desc())
        .all()
    )

    grouped: dict[str, dict] = {}
    for event in events:
        key = _clean_search_query(event.normalized_query)
        if not key:
            continue
        item = grouped.setdefault(key, {
            "query": key,
            "count": 0,
            "topic_label": event.topic_label,
            "last_searched_at": event.searched_at,
            "sessions": set(),
        })
        item["count"] += 1
        if event.session_key:
            item["sessions"].add(event.session_key)
        if event.searched_at and event.searched_at > item["last_searched_at"]:
            item["last_searched_at"] = event.searched_at
            if event.topic_label:
                item["topic_label"] = event.topic_label

    ranked = sorted(
        grouped.values(),
        key=lambda item: (item["count"], item["last_searched_at"]),
        reverse=True,
    )[:limit]

    return {
        "period_days": days,
        "total_events": len(events),
        "items": [
            {
                "rank": index + 1,
                "query": item["query"],
                "count": item["count"],
                "unique_sessions": len(item["sessions"]),
                "topic_label": item["topic_label"],
                "last_searched_at": item["last_searched_at"].isoformat() if item["last_searched_at"] else None,
            }
            for index, item in enumerate(ranked)
        ],
    }


def normalize_date(value: str | None) -> str | None:
    """2026-07-25, 2026.07.25, 20260725 등을 YYYYMMDD로 정규화."""
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    return digits[:8] if len(digits) >= 8 else None


def _json_dumps(value) -> str:
    return json.dumps(value or [], ensure_ascii=False)


def _json_loads(value: str | None):
    if not value:
        return []
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []


def _has_changed(latest, new_data: dict) -> bool:
    if latest is None:
        return True
    for key in ("name", "promulgation_date", "enforcement_date", "department", "detail_link"):
        if getattr(latest, key, None) != new_data.get(key):
            return True
    return False


def _official_url(detail_link: str | None) -> str | None:
    if not detail_link:
        return None
    if detail_link.startswith("http://") or detail_link.startswith("https://"):
        return detail_link
    return f"https://www.law.go.kr{detail_link}"


def _infer_tags(title: str | None, source_query: str | None = None) -> list[str]:
    text = f"{title or ''} {source_query or ''}"
    groups = {
        "제조·사용시설": ("제조·사용시설", "반응조", "혼합탱크", "희석탱크", "공정설비"),
        "저장시설": ("저장시설", "저장탱크", "방유제", "액위계", "과충전"),
        "보관시설": ("보관시설", "보관창고", "드럼 보관", "IBC 보관", "용기 보관"),
        "소량취급시설": ("소량취급시설", "소량기준", "기준수량"),
        "검사·안전진단": ("설치검사", "정기검사", "수시검사", "안전진단", "검사 및 안전진단"),
        "배관·누출": ("배관", "플랜지", "밸브", "누출", "유출", "집수조", "트렌치"),
        "영업허가·변경": ("영업허가", "변경허가", "변경신고", "영업변경"),
        "화학사고예방": ("화학사고", "화학사고예방관리계획서", "장외영향평가", "주민고지"),
        "차량 운반시설": ("차량 운반시설", "용기 적재", "운반차량"),
        "차량 운송시설": ("차량 운송시설", "탱크로리", "탱크트럭"),
        "운반용기": ("운반용기", "사용연장검사", "용기검사"),
        "사외배관": ("사외배관", "사업장 밖 배관", "매설배관"),
        "취급기준": ("구체적인 취급기준", "물질별 기준", "혼합금지"),
        "안전거리": ("안전거리", "보호대상", "이격거리"),
        "교육·관리자": ("안전교육", "종사자", "관리자 선임", "취급담당자"),
    }
    tags = [tag for tag, keywords in groups.items() if any(keyword in text for keyword in keywords)]
    return tags[:8]


def _infer_related_tasks(title: str | None, source_query: str | None = None) -> list[str]:
    return _infer_tags(title, source_query)


def _status_for(entry: models.ArchiveEntry) -> str:
    today = _today_yyyymmdd()
    if entry.deadline_date and entry.deadline_date >= today:
        return "의견제출 예정"
    if entry.enforcement_date:
        if entry.enforcement_date > today:
            return "시행 예정"
        return "현재 시행"
    if entry.event_action == "changed":
        return "내용 변경"
    return "신규"


def _archive_summary(title: str, event_action: str, material_type: str | None) -> str:
    label = material_type or "법령정보"
    if event_action == "changed":
        return f"기존에 수집한 {label} 정보와 비교해 제목·날짜·소관부처 또는 원문 링크의 변경이 확인되었습니다."
    if event_action == "imported":
        return f"외부 수집기에서 등록된 {label} 자료입니다."
    return f"findol이 새로 발견해 아카이브한 {label} 자료입니다."


def _archive_key(prefix: str, *parts) -> str:
    raw = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _create_archive_from_snapshot(
    db: Session,
    *,
    kind: str,
    external_id: str,
    event_action: str,
    title: str,
    material_type: str,
    department: str | None,
    detail_link: str | None,
    source_query: str | None,
    promulgation_date: str | None,
    enforcement_date: str | None,
    fetched_at: datetime,
) -> bool:
    key = _archive_key("snapshot", kind, external_id, fetched_at.isoformat())
    if db.query(models.ArchiveEntry).filter(models.ArchiveEntry.archive_key == key).first():
        return False

    published_date = fetched_at.strftime("%Y%m%d")
    entry = models.ArchiveEntry(
        archive_key=key,
        kind=kind,
        external_id=external_id,
        event_action=event_action,
        title=title or "(제목 없음)",
        material_type=material_type,
        department=department,
        source_name="국가법령정보센터",
        official_url=_official_url(detail_link),
        source_query=source_query,
        published_date=published_date,
        promulgation_date=normalize_date(promulgation_date),
        enforcement_date=normalize_date(enforcement_date),
        summary=_archive_summary(title, event_action, material_type),
        tags_json=_json_dumps(_infer_tags(title, source_query)),
        related_tasks_json=_json_dumps(_infer_related_tasks(title, source_query)),
        related_laws_json=_json_dumps([]),
        attachments_json=_json_dumps([]),
        collected_at=fetched_at,
    )
    db.add(entry)
    return True


def save_law_results(db: Session, results: list[dict], query: str) -> int:
    added = 0
    for item in results:
        external_id = item.get("id")
        if not external_id:
            continue
        latest = (
            db.query(models.LawSnapshot)
            .filter(models.LawSnapshot.external_id == external_id)
            .order_by(models.LawSnapshot.fetched_at.desc())
            .first()
        )
        if not _has_changed(latest, item):
            continue

        fetched_at = _now_local()
        snapshot = models.LawSnapshot(
            external_id=external_id,
            name=item.get("name"),
            promulgation_date=normalize_date(item.get("promulgation_date")),
            enforcement_date=normalize_date(item.get("enforcement_date")),
            department=item.get("department"),
            detail_link=item.get("detail_link"),
            source_query=query,
            fetched_at=fetched_at,
        )
        db.add(snapshot)
        _create_archive_from_snapshot(
            db,
            kind="law",
            external_id=external_id,
            event_action="new" if latest is None else "changed",
            title=item.get("name") or "(제목 없음)",
            material_type="법령",
            department=item.get("department"),
            detail_link=item.get("detail_link"),
            source_query=query,
            promulgation_date=item.get("promulgation_date"),
            enforcement_date=item.get("enforcement_date"),
            fetched_at=fetched_at,
        )
        added += 1
    db.commit()
    return added


def save_admrul_results(db: Session, results: list[dict], query: str) -> int:
    added = 0
    for item in results:
        external_id = item.get("id")
        if not external_id:
            continue
        latest = (
            db.query(models.AdminRuleSnapshot)
            .filter(models.AdminRuleSnapshot.external_id == external_id)
            .order_by(models.AdminRuleSnapshot.fetched_at.desc())
            .first()
        )
        data = {
            **item,
            "promulgation_date": normalize_date(item.get("promulgation_date")),
            "enforcement_date": None,
        }
        if not _has_changed(latest, data):
            continue

        fetched_at = _now_local()
        snapshot = models.AdminRuleSnapshot(
            external_id=external_id,
            name=item.get("name"),
            rule_type=item.get("type"),
            promulgation_date=normalize_date(item.get("promulgation_date")),
            department=item.get("department"),
            detail_link=item.get("detail_link"),
            source_query=query,
            fetched_at=fetched_at,
        )
        db.add(snapshot)
        _create_archive_from_snapshot(
            db,
            kind="admin_rule",
            external_id=external_id,
            event_action="new" if latest is None else "changed",
            title=item.get("name") or "(제목 없음)",
            material_type=item.get("type") or "고시·행정규칙",
            department=item.get("department"),
            detail_link=item.get("detail_link"),
            source_query=query,
            promulgation_date=item.get("promulgation_date"),
            enforcement_date=None,
            fetched_at=fetched_at,
        )
        added += 1
    db.commit()
    return added


def backfill_archive_from_snapshots(db: Session) -> int:
    """업데이트 전 DB의 기존 스냅샷을 아카이브 게시글로 변환."""
    created = 0
    law_seen: set[str] = set()
    for row in db.query(models.LawSnapshot).order_by(models.LawSnapshot.fetched_at.asc()).all():
        action = "new" if row.external_id not in law_seen else "changed"
        law_seen.add(row.external_id)
        if _create_archive_from_snapshot(
            db,
            kind="law",
            external_id=row.external_id,
            event_action=action,
            title=row.name or "(제목 없음)",
            material_type="법령",
            department=row.department,
            detail_link=row.detail_link,
            source_query=row.source_query,
            promulgation_date=row.promulgation_date,
            enforcement_date=row.enforcement_date,
            fetched_at=row.fetched_at or _now_local(),
        ):
            created += 1

    admin_seen: set[str] = set()
    for row in db.query(models.AdminRuleSnapshot).order_by(models.AdminRuleSnapshot.fetched_at.asc()).all():
        action = "new" if row.external_id not in admin_seen else "changed"
        admin_seen.add(row.external_id)
        if _create_archive_from_snapshot(
            db,
            kind="admin_rule",
            external_id=row.external_id,
            event_action=action,
            title=row.name or "(제목 없음)",
            material_type=row.rule_type or "고시·행정규칙",
            department=row.department,
            detail_link=row.detail_link,
            source_query=row.source_query,
            promulgation_date=row.promulgation_date,
            enforcement_date=None,
            fetched_at=row.fetched_at or _now_local(),
        ):
            created += 1

    db.commit()
    return created


def _serialize_archive(entry: models.ArchiveEntry) -> dict:
    return {
        "id": entry.id,
        "kind": entry.kind,
        "external_id": entry.external_id,
        "source_key": entry.source_key,
        "revision_no": entry.revision_no or 1,
        "previous_entry_id": entry.previous_entry_id,
        "event_action": entry.event_action,
        "title": entry.title,
        "material_type": entry.material_type,
        "department": entry.department,
        "source_name": entry.source_name,
        "official_url": entry.official_url,
        "source_query": entry.source_query,
        "published_date": entry.published_date,
        "promulgation_date": entry.promulgation_date,
        "enforcement_date": entry.enforcement_date,
        "deadline_date": entry.deadline_date,
        "status": _status_for(entry),
        "summary": entry.summary,
        "findol_note": entry.findol_note,
        "tags": _json_loads(entry.tags_json),
        "related_laws": _json_loads(entry.related_laws_json),
        "related_tasks": _json_loads(entry.related_tasks_json),
        "attachments": _json_loads(entry.attachments_json),
        "collected_at": entry.collected_at.isoformat() if entry.collected_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


def get_archive(
    db: Session,
    *,
    keyword: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    year: int | None = None,
    department: str | None = None,
    task: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict:
    query = db.query(models.ArchiveEntry)

    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(
            models.ArchiveEntry.title.ilike(like),
            models.ArchiveEntry.summary.ilike(like),
            models.ArchiveEntry.findol_note.ilike(like),
            models.ArchiveEntry.source_query.ilike(like),
            models.ArchiveEntry.tags_json.ilike(like),
            models.ArchiveEntry.related_tasks_json.ilike(like),
        ))
    if kind and kind != "all":
        if kind == "law":
            query = query.filter(models.ArchiveEntry.kind == "law")
        elif kind == "admin_rule":
            query = query.filter(models.ArchiveEntry.kind == "admin_rule")
        else:
            query = query.filter(models.ArchiveEntry.material_type == kind)
    if year:
        prefix = str(year)
        query = query.filter(or_(
            models.ArchiveEntry.published_date.startswith(prefix),
            models.ArchiveEntry.promulgation_date.startswith(prefix),
            models.ArchiveEntry.enforcement_date.startswith(prefix),
        ))
    if department:
        query = query.filter(models.ArchiveEntry.department.contains(department))
    if task:
        query = query.filter(models.ArchiveEntry.related_tasks_json.contains(task))

    # 상태는 오늘 날짜에 따라 달라지므로 SQL 필터를 명시적으로 구성.
    today = _today_yyyymmdd()
    if status and status != "all":
        if status == "upcoming":
            query = query.filter(models.ArchiveEntry.enforcement_date > today)
        elif status == "current":
            query = query.filter(and_(
                models.ArchiveEntry.enforcement_date.isnot(None),
                models.ArchiveEntry.enforcement_date <= today,
            ))
        elif status == "changed":
            query = query.filter(models.ArchiveEntry.event_action == "changed")
        elif status == "new":
            query = query.filter(models.ArchiveEntry.event_action.in_(["new", "imported"]))
        elif status == "deadline":
            query = query.filter(models.ArchiveEntry.deadline_date >= today)

    total = query.count()
    rows = (
        query.order_by(
            models.ArchiveEntry.published_date.desc(),
            models.ArchiveEntry.collected_at.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"total": total, "items": [_serialize_archive(row) for row in rows]}


def get_archive_item(db: Session, entry_id: int) -> dict | None:
    row = db.query(models.ArchiveEntry).filter(models.ArchiveEntry.id == entry_id).first()
    return _serialize_archive(row) if row else None


def get_archive_stats(db: Session, recent_limit: int = 5, upcoming_limit: int = 5) -> dict:
    today = _today_yyyymmdd()
    recent_rows = (
        db.query(models.ArchiveEntry)
        .order_by(models.ArchiveEntry.published_date.desc(), models.ArchiveEntry.collected_at.desc())
        .limit(recent_limit)
        .all()
    )

    # 시행일뿐 아니라 입법·행정예고의 의견제출 마감일도 홈의 다가오는 일정에 표시한다.
    upcoming_query = db.query(models.ArchiveEntry).filter(or_(
        models.ArchiveEntry.enforcement_date > today,
        models.ArchiveEntry.deadline_date >= today,
    ))
    upcoming_all = upcoming_query.all()

    def next_event(row):
        candidates = []
        if row.deadline_date and row.deadline_date >= today:
            candidates.append((row.deadline_date, "의견마감"))
        if row.enforcement_date and row.enforcement_date > today:
            candidates.append((row.enforcement_date, "시행"))
        return min(candidates, key=lambda item: item[0]) if candidates else ("99999999", "일정")

    upcoming_all.sort(key=lambda row: (next_event(row)[0], row.title or ""))
    upcoming_rows = upcoming_all[:upcoming_limit]
    serialized_upcoming = []
    for row in upcoming_rows:
        item = _serialize_archive(row)
        item["next_date"], item["next_event"] = next_event(row)
        serialized_upcoming.append(item)

    month_prefix = date.today().strftime("%Y%m")
    return {
        "total": db.query(models.ArchiveEntry).count(),
        "this_month": db.query(models.ArchiveEntry).filter(models.ArchiveEntry.published_date.startswith(month_prefix)).count(),
        "upcoming_count": len(upcoming_all),
        "recent": [_serialize_archive(row) for row in recent_rows],
        "upcoming": serialized_upcoming,
    }


def import_archive_entry(db: Session, payload: dict) -> tuple[dict, bool]:
    """기존 뉴스레터/크롤러가 개정정보를 직접 등록할 때 사용.

    같은 source_key가 다시 들어왔을 때 내용이 같으면 중복 저장하지 않습니다.
    내용이 달라졌다면 기존 게시글을 덮어쓰지 않고 새 개정 버전으로 추가합니다.
    """
    source_key = payload.get("source_key") or payload.get("official_url") or ""
    if not source_key:
        source_key = "|".join([
            payload.get("title") or "",
            payload.get("published_date") or "",
            payload.get("department") or "",
        ])

    normalized_payload = {
        "kind": payload.get("kind") or "material",
        "external_id": payload.get("external_id"),
        "title": payload.get("title") or "(제목 없음)",
        "material_type": payload.get("material_type") or "공고·자료",
        "department": payload.get("department"),
        "source_name": payload.get("source_name") or payload.get("department"),
        "official_url": payload.get("official_url"),
        "source_query": payload.get("source_query"),
        "published_date": normalize_date(payload.get("published_date")) or _today_yyyymmdd(),
        "promulgation_date": normalize_date(payload.get("promulgation_date")),
        "enforcement_date": normalize_date(payload.get("enforcement_date")),
        "deadline_date": normalize_date(payload.get("deadline_date")),
        "summary": payload.get("summary") or _archive_summary(payload.get("title") or "", "imported", payload.get("material_type")),
        "findol_note": payload.get("findol_note"),
        "tags_json": _json_dumps(payload.get("tags") or _infer_tags(payload.get("title"), payload.get("source_query"))),
        "related_laws_json": _json_dumps(payload.get("related_laws")),
        "related_tasks_json": _json_dumps(payload.get("related_tasks") or _infer_related_tasks(payload.get("title"), payload.get("source_query"))),
        "attachments_json": _json_dumps(payload.get("attachments")),
    }

    hash_source = json.dumps(normalized_payload, ensure_ascii=False, sort_keys=True)
    content_hash = hashlib.sha256(hash_source.encode("utf-8")).hexdigest()
    latest = (
        db.query(models.ArchiveEntry)
        .filter(models.ArchiveEntry.source_key == source_key)
        .order_by(models.ArchiveEntry.revision_no.desc(), models.ArchiveEntry.collected_at.desc())
        .first()
    )

    if latest and latest.content_hash == content_hash:
        return _serialize_archive(latest), False

    revision_no = (latest.revision_no or 1) + 1 if latest else 1
    action = "changed" if latest else "imported"
    key = _archive_key("import", source_key, content_hash)
    existing_by_hash = db.query(models.ArchiveEntry).filter(models.ArchiveEntry.archive_key == key).first()
    if existing_by_hash:
        return _serialize_archive(existing_by_hash), False

    entry = models.ArchiveEntry(
        archive_key=key,
        source_key=source_key,
        content_hash=content_hash,
        revision_no=revision_no,
        previous_entry_id=latest.id if latest else None,
        event_action=action,
        collected_at=_now_local(),
        updated_at=_now_local(),
        **normalized_payload,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _serialize_archive(entry), True


def get_calendar_events(
    db: Session,
    year: int,
    month: int,
    event_types: Iterable[str] | None = None,
    kind: str | None = None,
    task: str | None = None,
) -> list[dict]:
    prefix = f"{year:04d}{month:02d}"
    selected = set(event_types or ["published", "promulgated", "effective", "deadline"])

    query = db.query(models.ArchiveEntry)
    if kind and kind != "all":
        query = query.filter(models.ArchiveEntry.kind == kind)
    if task:
        query = query.filter(models.ArchiveEntry.related_tasks_json.contains(task))

    rows = query.order_by(models.ArchiveEntry.collected_at.desc()).all()
    events: list[dict] = []
    seen: set[tuple] = set()
    mapping = [
        ("published", "게시", "published_date"),
        ("promulgated", "공포", "promulgation_date"),
        ("effective", "시행", "enforcement_date"),
        ("deadline", "의견마감", "deadline_date"),
    ]

    for entry in rows:
        for event_code, event_label, field in mapping:
            if event_code not in selected:
                continue
            event_date = getattr(entry, field)
            if not event_date or not event_date.startswith(prefix):
                continue

            # 게시일은 게시글별 표시, 공포/시행/마감은 같은 문서·날짜 중복 제거.
            dedupe_id = entry.id if event_code == "published" else (entry.external_id or entry.title)
            dedupe_key = (event_code, event_date, entry.kind, dedupe_id)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            events.append({
                "archive_id": entry.id,
                "date": event_date,
                "event_code": event_code,
                "event_type": event_label,
                "kind": entry.kind,
                "title": entry.title,
                "material_type": entry.material_type,
                "department": entry.department,
                "status": _status_for(entry),
                "official_url": entry.official_url,
                "tags": _json_loads(entry.tags_json),
            })

    priority = {"deadline": 0, "effective": 1, "promulgated": 2, "published": 3}
    events.sort(key=lambda item: (item["date"], priority.get(item["event_code"], 9), item["title"]))
    return events


def get_timeline(db: Session, keyword: str | None = None, limit: int = 100) -> list[dict]:
    """기존 API 호환용: 아카이브 게시글을 최신순 타임라인으로 반환."""
    result = get_archive(db, keyword=keyword, limit=limit, offset=0)
    return [
        {
            "kind": item["kind"],
            "id": item["external_id"],
            "archive_id": item["id"],
            "name": item["title"],
            "rule_type": item["material_type"],
            "promulgation_date": item["promulgation_date"],
            "enforcement_date": item["enforcement_date"],
            "department": item["department"],
            "detail_link": item["official_url"],
            "source_query": item["source_query"],
            "fetched_at": item["collected_at"],
        }
        for item in result["items"]
    ]


def get_history_for_id(db: Session, kind: str, external_id: str) -> list[dict]:
    if kind == "law":
        rows = (
            db.query(models.LawSnapshot)
            .filter(models.LawSnapshot.external_id == external_id)
            .order_by(models.LawSnapshot.fetched_at.asc())
            .all()
        )
        return [{
            "name": row.name,
            "promulgation_date": row.promulgation_date,
            "enforcement_date": row.enforcement_date,
            "department": row.department,
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        } for row in rows]

    rows = (
        db.query(models.AdminRuleSnapshot)
        .filter(models.AdminRuleSnapshot.external_id == external_id)
        .order_by(models.AdminRuleSnapshot.fetched_at.asc())
        .all()
    )
    return [{
        "name": row.name,
        "rule_type": row.rule_type,
        "promulgation_date": row.promulgation_date,
        "department": row.department,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
    } for row in rows]

# ---------------------------------------------------------------------------
# 관리자용 환경지식 DB
# ---------------------------------------------------------------------------

def _knowledge_payload(row: models.KnowledgeTopic) -> dict:
    return {
        "id": row.id,
        "topic_key": row.topic_key,
        "label": row.label,
        "description": row.description or "",
        "intent_summary": row.intent_summary or "",
        "triggers": _json_loads(row.triggers_json),
        "search_terms": _json_loads(row.search_terms_json),
        "primary_rules": _json_loads(row.primary_rules_json),
        "upper_laws": _json_loads(row.upper_laws_json),
        "related_rules": _json_loads(row.related_rules_json),
        "checklist": _json_loads(row.checklist_json),
        "related_tasks": _json_loads(row.related_tasks_json),
        "notes": row.notes or "",
        "is_active": bool(row.is_active),
        "priority": row.priority or 0,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def seed_knowledge_topics(db: Session, law_map_path) -> int:
    """정적 law_map.json을 최초 1회 관리자 DB로 복사한다."""
    if db.query(models.KnowledgeTopic).count() > 0:
        return 0
    try:
        data = json.loads(law_map_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    count = 0
    for topic in data.get("topics", []):
        key = str(topic.get("id") or "").strip()
        label = str(topic.get("label") or "").strip()
        if not key or not label:
            continue
        row = models.KnowledgeTopic(
            topic_key=key,
            label=label,
            description=topic.get("description"),
            intent_summary=topic.get("intent_summary"),
            triggers_json=_json_dumps(topic.get("triggers")),
            search_terms_json=_json_dumps(topic.get("search_terms")),
            primary_rules_json=_json_dumps(topic.get("primary_rules")),
            upper_laws_json=_json_dumps(topic.get("upper_laws")),
            related_rules_json=_json_dumps(topic.get("related_rules")),
            checklist_json=_json_dumps(topic.get("checklist")),
            related_tasks_json=_json_dumps(topic.get("related_tasks")),
            notes=topic.get("notes"),
            is_active=1,
            priority=int(topic.get("priority") or 50),
        )
        db.add(row)
        count += 1
    db.commit()
    return count


def list_knowledge_topics(db: Session, keyword: str | None = None) -> list[dict]:
    query = db.query(models.KnowledgeTopic)
    if keyword:
        token = f"%{keyword.strip()}%"
        query = query.filter(or_(
            models.KnowledgeTopic.label.ilike(token),
            models.KnowledgeTopic.topic_key.ilike(token),
            models.KnowledgeTopic.description.ilike(token),
            models.KnowledgeTopic.triggers_json.ilike(token),
        ))
    rows = query.order_by(models.KnowledgeTopic.priority.desc(), models.KnowledgeTopic.label.asc()).all()
    return [_knowledge_payload(row) for row in rows]


def get_knowledge_topic(db: Session, topic_id: int) -> dict | None:
    row = db.query(models.KnowledgeTopic).filter(models.KnowledgeTopic.id == topic_id).first()
    return _knowledge_payload(row) if row else None


def save_knowledge_topic(db: Session, data: dict, topic_id: int | None = None) -> dict:
    row = None
    if topic_id is not None:
        row = db.query(models.KnowledgeTopic).filter(models.KnowledgeTopic.id == topic_id).first()
    if row is None:
        row = models.KnowledgeTopic(topic_key=data["topic_key"], label=data["label"])
        db.add(row)
    row.topic_key = data["topic_key"].strip()
    row.label = data["label"].strip()
    row.description = data.get("description") or ""
    row.intent_summary = data.get("intent_summary") or ""
    row.triggers_json = _json_dumps(data.get("triggers"))
    row.search_terms_json = _json_dumps(data.get("search_terms"))
    row.primary_rules_json = _json_dumps(data.get("primary_rules"))
    row.upper_laws_json = _json_dumps(data.get("upper_laws"))
    row.related_rules_json = _json_dumps(data.get("related_rules"))
    row.checklist_json = _json_dumps(data.get("checklist"))
    row.related_tasks_json = _json_dumps(data.get("related_tasks"))
    row.notes = data.get("notes") or ""
    row.is_active = 1 if data.get("is_active", True) else 0
    row.priority = int(data.get("priority") or 50)
    db.commit()
    db.refresh(row)
    return _knowledge_payload(row)


def delete_knowledge_topic(db: Session, topic_id: int) -> bool:
    row = db.query(models.KnowledgeTopic).filter(models.KnowledgeTopic.id == topic_id).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def dynamic_knowledge_matches(db: Session, query_text: str, limit: int = 3) -> list[dict]:
    """관리자 DB 주제를 검색어와 매칭하여 검색엔진에 즉시 반영한다."""
    compact = re.sub(r"[\s·ㆍ,./()\[\]{}\-]+", "", query_text or "").lower()
    results: list[dict] = []
    for row in db.query(models.KnowledgeTopic).filter(models.KnowledgeTopic.is_active == 1).all():
        item = _knowledge_payload(row)
        matched = []
        score = 0
        for trigger in item["triggers"]:
            trigger_compact = re.sub(r"[\s·ㆍ,./()\[\]{}\-]+", "", str(trigger)).lower()
            if trigger_compact and trigger_compact in compact:
                matched.append(trigger)
                score += (row.priority or 0) + min(len(trigger_compact) * 10, 100)
                if trigger_compact == compact:
                    score += 120
        if score:
            item["score"] = score
            item["matched_terms"] = matched
            results.append(item)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]
