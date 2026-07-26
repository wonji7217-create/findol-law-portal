from __future__ import annotations

import difflib
import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "substances.sqlite3"
META_PATH = DATA_DIR / "substance_dataset_meta.json"
NOTICES_PATH = DATA_DIR / "regulatory_notices.json"

CONCENTRATION_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?:%|퍼센트)", re.IGNORECASE)
CAS_RE = re.compile(r"\b\d{2,7}-\d{2}-\d\b")


def normalize(value: str | None) -> str:
    value = (value or "").strip().lower()
    return re.sub(r"[\s\-_/·ㆍ,().]+", "", value)


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError("물질 데이터베이스가 없습니다.")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@lru_cache(maxsize=1)
def get_meta() -> dict[str, Any]:
    if not META_PATH.exists():
        return {}
    return json.loads(META_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def get_notice_data() -> dict[str, Any]:
    if not NOTICES_PATH.exists():
        return {"events": [], "watch_sources": []}
    return json.loads(NOTICES_PATH.read_text(encoding="utf-8"))


def parse_query(query: str) -> dict[str, Any]:
    raw = re.sub(r"\s+", " ", query.strip())
    concentration = None
    match = CONCENTRATION_RE.search(raw)
    if match:
        concentration = float(match.group("value"))
    clean = CONCENTRATION_RE.sub(" ", raw)
    clean = re.sub(r"\s+", " ", clean).strip(" ,/")
    cas_match = CAS_RE.search(raw)
    return {
        "raw_query": raw,
        "lookup_text": cas_match.group(0) if cas_match else clean,
        "normalized_lookup": normalize(cas_match.group(0) if cas_match else clean),
        "cas_query": cas_match.group(0) if cas_match else None,
        "concentration": concentration,
        "concentration_label": f"{concentration:g}%" if concentration is not None else None,
    }


def _rows_to_items(rows: list[sqlite3.Row], matched_by: str, matched_text: str | None = None) -> list[dict[str, Any]]:
    return [_serialize_substance(row, matched_by=matched_by, matched_text=matched_text) for row in rows]


def _serialize_substance(row: sqlite3.Row, *, matched_by: str, matched_text: str | None = None) -> dict[str, Any]:
    raw = dict(row)
    status_fields = [
        ("hazard", "인체·생태 유해성물질", raw.get("hazard_designation")),
        ("accident", "사고대비물질", raw.get("accident_preparedness")),
        ("restricted", "제한·금지·허가물질", raw.get("restricted_prohibited_authorized")),
        ("priority", "중점관리물질", raw.get("priority_substance")),
        ("persistent", "잔류성오염물질", raw.get("persistent_pollutant")),
    ]
    current_designations = [
        {"key": key, "label": label, "value": value, "tone": "current"}
        for key, label, value in status_fields if (value or "").strip()
    ]
    if (raw.get("is_existing") or "").strip().upper() == "Y":
        current_designations.append({
            "key": "existing", "label": "기존화학물질", "value": raw.get("existing_no") or "Y", "tone": "neutral"
        })
    if raw.get("registered_existing"):
        current_designations.append({
            "key": "registered_existing", "label": "등록대상기존화학물질", "value": raw.get("registered_existing"), "tone": "neutral"
        })

    notices = events_for_cas(raw.get("cas_no"))
    current_regulatory_found = any((raw.get(key) or "").strip() for key in (
        "hazard_designation", "accident_preparedness", "restricted_prohibited_authorized", "priority_substance", "persistent_pollutant"
    ))

    display_name = raw.get("name_ko") or _preferred_alias(raw.get("id")) or raw.get("name_en") or raw.get("cas_no") or "이름 미기재 물질"
    return {
        "id": raw.get("id"),
        "source_no": raw.get("source_no"),
        "cas_no": raw.get("cas_no"),
        "name_ko": raw.get("name_ko"),
        "name_en": raw.get("name_en"),
        "display_name": display_name,
        "existing_no": raw.get("existing_no"),
        "hazard_designation": raw.get("hazard_designation"),
        "accident_preparedness": raw.get("accident_preparedness"),
        "restricted_prohibited_authorized": raw.get("restricted_prohibited_authorized"),
        "priority_substance": raw.get("priority_substance"),
        "persistent_pollutant": raw.get("persistent_pollutant"),
        "criteria_text": raw.get("criteria_text"),
        "registered_existing": raw.get("registered_existing"),
        "is_existing": raw.get("is_existing"),
        "current_designations": current_designations,
        "current_regulatory_found": current_regulatory_found,
        "current_status_label": "현행 지정정보 있음" if current_regulatory_found else "다운로드 자료에 현행 지정정보 미수록",
        "matched_by": matched_by,
        "matched_text": matched_text,
        "aliases": aliases_for_id(raw.get("id")),
        "notices": notices,
    }


@lru_cache(maxsize=256)
def aliases_for_id(substance_id: int | None) -> list[dict[str, str]]:
    if not substance_id:
        return []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT alias_text, alias_type FROM aliases WHERE substance_id=? ORDER BY alias_type, alias_text", (substance_id,)
        ).fetchall()
    return [{"text": row["alias_text"], "type": row["alias_type"]} for row in rows]


@lru_cache(maxsize=256)
def _preferred_alias(substance_id: int | None) -> str | None:
    aliases = aliases_for_id(substance_id)
    for kind in ("preferred_ko", "common_ko", "normalized_ko", "official_ko"):
        for item in aliases:
            if item["type"] == kind:
                return item["text"]
    return None


def events_for_cas(cas_no: str | None) -> list[dict[str, Any]]:
    normalized = normalize(cas_no)
    if not normalized:
        return []
    return [event for event in get_notice_data().get("events", []) if normalize(event.get("cas_no")) == normalized]


def _exact_search(conn: sqlite3.Connection, lookup_norm: str, cas_query: str | None, limit: int) -> tuple[list[dict[str, Any]], str]:
    if cas_query:
        rows = conn.execute(
            "SELECT * FROM substances WHERE normalized_cas=? LIMIT ?", (normalize(cas_query), limit)
        ).fetchall()
        if rows:
            return _rows_to_items(rows, "cas", cas_query), "exact"

    rows = conn.execute(
        "SELECT * FROM substances WHERE normalized_ko=? OR normalized_en=? LIMIT ?",
        (lookup_norm, lookup_norm, limit),
    ).fetchall()
    if rows:
        return _rows_to_items(rows, "official_name"), "exact"

    alias_rows = conn.execute(
        """SELECT s.*, a.alias_text AS matched_alias
           FROM aliases a JOIN substances s ON s.id=a.substance_id
           WHERE a.alias_norm=? LIMIT ?""",
        (lookup_norm, limit),
    ).fetchall()
    if alias_rows:
        items = [_serialize_substance(row, matched_by="alias", matched_text=row["matched_alias"]) for row in alias_rows]
        return items, "exact"
    return [], "none"


def _contains_search(conn: sqlite3.Connection, lookup_norm: str, limit: int) -> list[dict[str, Any]]:
    if len(lookup_norm) < 2:
        return []
    pattern = f"%{lookup_norm}%"
    rows = conn.execute(
        """SELECT * FROM substances
           WHERE normalized_ko LIKE ? OR normalized_en LIKE ? OR normalized_cas LIKE ?
           ORDER BY CASE WHEN normalized_ko LIKE ? THEN 0 WHEN normalized_en LIKE ? THEN 1 ELSE 2 END,
                    LENGTH(COALESCE(name_ko, name_en, cas_no))
           LIMIT ?""",
        (pattern, pattern, pattern, pattern, pattern, limit),
    ).fetchall()
    return _rows_to_items(rows, "partial_name")


def _fuzzy_alias_search(conn: sqlite3.Connection, lookup_norm: str, limit: int) -> list[dict[str, Any]]:
    if len(lookup_norm) < 3:
        return []
    # Candidate pool is intentionally limited to aliases and Korean names of comparable length.
    rows = conn.execute(
        """SELECT a.alias_norm, a.alias_text, s.*
           FROM aliases a JOIN substances s ON s.id=a.substance_id
           WHERE LENGTH(a.alias_norm) BETWEEN ? AND ?""",
        (max(1, len(lookup_norm) - 3), len(lookup_norm) + 3),
    ).fetchall()
    scored: list[tuple[float, sqlite3.Row]] = []
    for row in rows:
        ratio = difflib.SequenceMatcher(None, lookup_norm, row["alias_norm"]).ratio()
        if ratio >= 0.70:
            scored.append((ratio, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    seen: set[int] = set()
    result: list[dict[str, Any]] = []
    for score, row in scored:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        item = _serialize_substance(row, matched_by="similar_alias", matched_text=row["alias_text"])
        item["similarity"] = round(score, 3)
        result.append(item)
        if len(result) >= limit:
            break
    return result



CRITERIA_CATEGORY_META = {
    "인체급성유해성": {"key": "human_acute", "group": "유독물질"},
    "인체만성유해성": {"key": "human_chronic", "group": "유독물질"},
    "생태유해성": {"key": "ecotoxicity", "group": "유독물질"},
    "사고대비물질": {"key": "accident_preparedness", "group": "사고대비물질"},
    "제한물질": {"key": "restricted", "group": "제한물질"},
    "금지물질": {"key": "prohibited", "group": "금지물질"},
    "허가물질": {"key": "authorized", "group": "허가물질"},
    "중점관리물질": {"key": "priority", "group": "중점관리물질"},
    "잔류성오염물질": {"key": "persistent", "group": "잔류성오염물질"},
    "혼합물 함량기준": {"key": "mixture", "group": "기타"},
}


def _threshold_label(value: float, comparator: str, *, include_operator: bool = False) -> str:
    base = f"{value:g}%"
    if not include_operator:
        return base
    return f"{base} {'초과' if comparator == 'gt' else '이상'}"


def _criterion_item(
    label: str,
    value: str | float,
    *,
    comparator: str = "gte",
    source_fragment: str | None = None,
) -> dict[str, Any]:
    numeric = float(value)
    meta = CRITERIA_CATEGORY_META.get(label, CRITERIA_CATEGORY_META["혼합물 함량기준"])
    return {
        "key": meta["key"],
        "label": label,
        "designation_group": meta["group"],
        "threshold": numeric,
        "comparator": comparator,
        "threshold_label": _threshold_label(numeric, comparator),
        "rule_label": _threshold_label(numeric, comparator, include_operator=True),
        "source_fragment": source_fragment,
    }


def parse_criteria(criteria_text: str | None) -> list[dict[str, Any]]:
    """함량기준 원문을 분류별 숫자 기준으로 구조화한다.

    유독물질의 인체급성·인체만성·생태유해성 기준뿐 아니라
    사고대비물질, 제한물질, 금지물질, 허가물질 등의
    ``몇 % 이상/초과 함유`` 문구도 해당 분류명과 함께 보존한다.
    """
    text = re.sub(r"\s+", " ", (criteria_text or "").strip())
    if not text:
        return []

    result: list[dict[str, Any]] = []
    seen: set[tuple[str, float, str]] = set()

    def add(label: str, value: str | float, comparator: str = "gte", source: str | None = None) -> None:
        numeric = float(value)
        key = (label, numeric, comparator)
        if key in seen:
            return
        seen.add(key)
        result.append(_criterion_item(label, numeric, comparator=comparator, source_fragment=source))

    # 자료는 보통 "/"로 규제 분류가 구분된다. 분류별 문맥을 보존하기 위해 먼저 나눈다.
    segments = [segment.strip() for segment in re.split(r"\s*/\s*", text) if segment.strip()]
    if not segments:
        segments = [text]

    for segment in segments:
        before_count = len(result)

        # 유독물질 세부 분류는 "인체급성유해성 : 10%"처럼 숫자 뒤에
        # '이상' 문구가 생략되는 경우가 많다.
        for match in re.finditer(
            r"(인체급성유해성|인체만성유해성|생태유해성)\s*:\s*(\d+(?:\.\d+)?)\s*%",
            segment,
        ):
            add(match.group(1), match.group(2), "gte", segment)

        # 그 밖의 지정 분류는 "이를 25% 이상 함유한 혼합물"과 같은 문장으로 적힌다.
        section_label = next(
            (
                label
                for label in (
                    "사고대비물질",
                    "제한물질",
                    "금지물질",
                    "허가물질",
                    "중점관리물질",
                    "잔류성오염물질",
                )
                if label in segment
            ),
            None,
        )
        if section_label:
            for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%\s*(이상|초과)", segment):
                comparator = "gt" if match.group(2) == "초과" else "gte"
                add(section_label, match.group(1), comparator, segment)

        # 분류명이 없는 예외 문구도 숫자 기준 자체는 보존하되,
        # 결과 화면에서는 '혼합물 함량기준'으로 명확히 구분한다.
        if len(result) == before_count:
            for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%\s*(이상|초과)", segment):
                comparator = "gt" if match.group(2) == "초과" else "gte"
                add("혼합물 함량기준", match.group(1), comparator, segment)

    return result


def compare_concentration(criteria_text: str | None, concentration: float | None) -> dict[str, Any]:
    thresholds = parse_criteria(criteria_text)
    comparisons: list[dict[str, Any]] = []

    if concentration is not None:
        for item in thresholds:
            comparator = item.get("comparator", "gte")
            met = concentration > item["threshold"] if comparator == "gt" else concentration >= item["threshold"]
            operator = ">" if comparator == "gt" else "≥"
            comparisons.append({
                **item,
                "input": concentration,
                "input_label": f"{concentration:g}%",
                "met": met,
                "result_label": "기준 초과" if met and comparator == "gt" else ("기준 이상" if met else ("기준 이하" if comparator == "gt" else "기준 미만")),
                "calculation": f"{concentration:g} {operator} {item['threshold']:g}" if met else (
                    f"{concentration:g} ≤ {item['threshold']:g}" if comparator == "gt"
                    else f"{concentration:g} < {item['threshold']:g}"
                ),
            })

    matched_statuses: list[dict[str, Any]] = []
    seen_matched: set[str] = set()
    for item in comparisons:
        if not item["met"] or item["key"] in seen_matched:
            continue
        seen_matched.add(item["key"])
        matched_statuses.append({
            "key": item["key"],
            "label": item["label"],
            "designation_group": item["designation_group"],
            "threshold": item["threshold"],
            "threshold_label": item["threshold_label"],
            "rule_label": item["rule_label"],
            "status_label": f"{item['label']} 함량기준 이상",
        })

    if concentration is None:
        summary = "함량을 함께 입력하면 자료의 숫자 기준과 단순 비교할 수 있습니다."
        state = "not_requested"
    elif not thresholds:
        summary = "현재 다운로드 자료에 자동 비교 가능한 숫자 함량기준이 없습니다."
        state = "no_threshold"
    elif matched_statuses:
        labels = "·".join(item["label"] for item in matched_statuses)
        summary = f"입력 농도는 {labels}의 자료상 함량기준 이상입니다."
        state = "threshold_met"
    else:
        summary = "입력 농도는 자동 비교 가능한 모든 숫자 함량기준보다 낮습니다. 적용 제외·다른 기준은 원문 확인이 필요합니다."
        state = "below_threshold"

    return {
        "state": state,
        "summary": summary,
        "thresholds": thresholds,
        "comparisons": comparisons,
        "matched_statuses": matched_statuses,
    }


def practical_checks(item: dict[str, Any]) -> list[dict[str, str]]:
    checks = [
        ("MSDS 성분명·CAS·실제 함량 확인", "제품 자료와 검색 물질이 같은지 먼저 확인합니다."),
        ("현행 고시 원문 확인", "다운로드 자료 기준일 이후 개정 여부와 적용 제외 문구를 확인합니다."),
        ("제조·사용·저장·보관 형태 확인", "취급 형태에 따라 시설 기준과 검사 대상이 달라질 수 있습니다."),
        ("신규 취급·원료 변경 여부 확인", "영업허가 변경, 변경신고, 설치검사 검토의 출발점입니다."),
    ]
    if item.get("notices"):
        checks.insert(1, ("행정예고·시행예정 영향 검토", "확정 전 내용과 시행일을 구분하여 준비 사항을 검토합니다."))
    if item.get("current_regulatory_found"):
        checks.append(("표시·취급기준 및 수량기준 확인", "현재 지정정보와 사업장 취급량을 함께 검토합니다."))
    return [{"title": title, "description": description, "state": "review"} for title, description in checks]


def search_substances(query: str, limit: int = 10) -> dict[str, Any]:
    parsed = parse_query(query)
    lookup_norm = parsed["normalized_lookup"]
    if not lookup_norm:
        return {"query": parsed, "match_type": "none", "items": [], "suggestions": [], "meta": get_meta()}

    with _connect() as conn:
        items, match_type = _exact_search(conn, lookup_norm, parsed["cas_query"], limit)
        suggestions: list[dict[str, Any]] = []
        if not items:
            items = _contains_search(conn, lookup_norm, limit)
            match_type = "partial" if items else "none"
        if not items:
            suggestions = _fuzzy_alias_search(conn, lookup_norm, min(limit, 5))
            if suggestions:
                match_type = "suggestion"

    for item in items:
        item["concentration_analysis"] = compare_concentration(item.get("criteria_text"), parsed["concentration"])
        item["practical_checks"] = practical_checks(item)
        item["timeline"] = build_timeline(item)

    return {
        "query": parsed,
        "match_type": match_type,
        "items": items,
        "suggestions": suggestions,
        "meta": get_meta(),
        "notice_meta": {
            "verified_on": get_notice_data().get("verified_on"),
            "notice": get_notice_data().get("notice"),
        },
    }


def build_timeline(item: dict[str, Any]) -> list[dict[str, Any]]:
    meta = get_meta()
    timeline = [{
        "date": meta.get("data_date"),
        "type": "dataset",
        "label": "다운로드 자료 기준",
        "description": item.get("current_status_label"),
        "tone": "current" if item.get("current_regulatory_found") else "neutral",
    }]
    for event in item.get("notices", []):
        timeline.append({
            "date": event.get("published_date"),
            "type": event.get("status"),
            "label": event.get("status_label"),
            "description": event.get("designation_summary") or event.get("title"),
            "tone": event.get("tone", "notice"),
            "source_url": event.get("source_url"),
        })
        if event.get("effective_date"):
            timeline.append({
                "date": event.get("effective_date"),
                "type": "effective",
                "label": "시행 예정",
                "description": "고시 시행 예정일",
                "tone": "upcoming",
                "source_url": event.get("source_url"),
            })
    return sorted(timeline, key=lambda event: event.get("date") or "")


def get_substance_by_cas(cas_no: str, concentration: float | None = None) -> dict[str, Any] | None:
    query = cas_no + (f" {concentration:g}%" if concentration is not None else "")
    result = search_substances(query, limit=10)
    for item in result["items"]:
        if normalize(item.get("cas_no")) == normalize(cas_no):
            return {"query": result["query"], "item": item, "meta": result["meta"], "notice_meta": result["notice_meta"]}
    return None
