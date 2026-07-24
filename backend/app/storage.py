"""
검색 결과를 DB에 누적 저장하고, 항목별 변경 이력(타임라인)을 조회하는 로직.
"""

from sqlalchemy.orm import Session
from sqlalchemy import or_
from . import models


def _has_changed(latest, new_data: dict) -> bool:
    """가장 최근 스냅샷과 비교해서 내용이 달라졌는지 확인"""
    if latest is None:
        return True
    for key in ("name", "promulgation_date", "enforcement_date", "department"):
        if getattr(latest, key, None) != new_data.get(key):
            return True
    return False


def save_law_results(db: Session, results: list[dict], query: str) -> int:
    """법령 검색 결과 저장. 새로 추가된(또는 변경된) 스냅샷 개수 반환."""
    added = 0
    for item in results:
        if not item.get("id"):
            continue
        latest = (
            db.query(models.LawSnapshot)
            .filter(models.LawSnapshot.external_id == item["id"])
            .order_by(models.LawSnapshot.fetched_at.desc())
            .first()
        )
        if _has_changed(latest, item):
            snapshot = models.LawSnapshot(
                external_id=item["id"],
                name=item.get("name"),
                promulgation_date=item.get("promulgation_date"),
                enforcement_date=item.get("enforcement_date"),
                department=item.get("department"),
                detail_link=item.get("detail_link"),
                source_query=query,
            )
            db.add(snapshot)
            added += 1
    db.commit()
    return added


def save_admrul_results(db: Session, results: list[dict], query: str) -> int:
    """행정규칙 검색 결과 저장. 새로 추가된(또는 변경된) 스냅샷 개수 반환."""
    added = 0
    for item in results:
        if not item.get("id"):
            continue
        latest = (
            db.query(models.AdminRuleSnapshot)
            .filter(models.AdminRuleSnapshot.external_id == item["id"])
            .order_by(models.AdminRuleSnapshot.fetched_at.desc())
            .first()
        )
        data = {**item, "promulgation_date": item.get("promulgation_date")}
        if _has_changed(latest, data):
            snapshot = models.AdminRuleSnapshot(
                external_id=item["id"],
                name=item.get("name"),
                rule_type=item.get("type"),
                promulgation_date=item.get("promulgation_date"),
                department=item.get("department"),
                detail_link=item.get("detail_link"),
                source_query=query,
            )
            db.add(snapshot)
            added += 1
    db.commit()
    return added


def get_timeline(db: Session, keyword: str | None = None, limit: int = 100) -> list[dict]:
    """
    누적 저장된 스냅샷을 최신순으로 반환 (법령 + 행정규칙 통합).
    keyword가 있으면 이름에 포함된 것만 필터링.
    """
    law_q = db.query(models.LawSnapshot)
    admrul_q = db.query(models.AdminRuleSnapshot)

    if keyword:
        law_q = law_q.filter(models.LawSnapshot.name.contains(keyword))
        admrul_q = admrul_q.filter(models.AdminRuleSnapshot.name.contains(keyword))

    laws = law_q.order_by(models.LawSnapshot.fetched_at.desc()).limit(limit).all()
    admrules = admrul_q.order_by(models.AdminRuleSnapshot.fetched_at.desc()).limit(limit).all()

    timeline = []
    for l in laws:
        timeline.append({
            "kind": "law",
            "id": l.external_id,
            "name": l.name,
            "promulgation_date": l.promulgation_date,
            "enforcement_date": l.enforcement_date,
            "department": l.department,
            "detail_link": l.detail_link,
            "source_query": l.source_query,
            "fetched_at": l.fetched_at.isoformat() if l.fetched_at else None,
        })
    for a in admrules:
        timeline.append({
            "kind": "admin_rule",
            "id": a.external_id,
            "name": a.name,
            "rule_type": a.rule_type,
            "promulgation_date": a.promulgation_date,
            "department": a.department,
            "detail_link": a.detail_link,
            "source_query": a.source_query,
            "fetched_at": a.fetched_at.isoformat() if a.fetched_at else None,
        })

    timeline.sort(key=lambda x: x["fetched_at"] or "", reverse=True)
    return timeline[:limit]


def _latest_snapshots(db: Session, model):
    """external_id별 가장 최근 스냅샷만 남긴 목록 반환"""
    rows = db.query(model).order_by(model.fetched_at.desc()).all()
    seen = set()
    latest = []
    for r in rows:
        if r.external_id in seen:
            continue
        seen.add(r.external_id)
        latest.append(r)
    return latest


def get_calendar_events(db: Session, year: int, month: int) -> list[dict]:
    """
    지정한 연/월에 공포되거나 시행되는 법령·고시 목록을 반환.
    (검색을 통해 수집된 데이터 기준 — 자동 전수 수집이 아님)
    """
    prefix = f"{year:04d}{month:02d}"
    events = []

    for r in _latest_snapshots(db, models.LawSnapshot):
        if r.promulgation_date and r.promulgation_date.startswith(prefix):
            events.append({
                "date": r.promulgation_date, "event_type": "공포",
                "kind": "law", "id": r.external_id,
                "name": r.name, "department": r.department,
                "detail_link": r.detail_link,
            })
        if r.enforcement_date and r.enforcement_date.startswith(prefix):
            events.append({
                "date": r.enforcement_date, "event_type": "시행",
                "kind": "law", "id": r.external_id,
                "name": r.name, "department": r.department,
                "detail_link": r.detail_link,
            })

    for r in _latest_snapshots(db, models.AdminRuleSnapshot):
        if r.promulgation_date and r.promulgation_date.startswith(prefix):
            events.append({
                "date": r.promulgation_date, "event_type": "공포",
                "kind": "admin_rule", "id": r.external_id,
                "name": r.name, "department": r.department,
                "detail_link": r.detail_link,
            })

    events.sort(key=lambda e: e["date"])
    return events


def get_history_for_id(db: Session, kind: str, external_id: str) -> list[dict]:
    """특정 법령/행정규칙 하나의 변경 이력(스냅샷 전체)을 시간순으로 반환"""
    if kind == "law":
        rows = (
            db.query(models.LawSnapshot)
            .filter(models.LawSnapshot.external_id == external_id)
            .order_by(models.LawSnapshot.fetched_at.asc())
            .all()
        )
        return [
            {
                "name": r.name,
                "promulgation_date": r.promulgation_date,
                "enforcement_date": r.enforcement_date,
                "department": r.department,
                "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
            }
            for r in rows
        ]
    else:
        rows = (
            db.query(models.AdminRuleSnapshot)
            .filter(models.AdminRuleSnapshot.external_id == external_id)
            .order_by(models.AdminRuleSnapshot.fetched_at.asc())
            .all()
        )
        return [
            {
                "name": r.name,
                "rule_type": r.rule_type,
                "promulgation_date": r.promulgation_date,
                "department": r.department,
                "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
            }
            for r in rows
        ]
