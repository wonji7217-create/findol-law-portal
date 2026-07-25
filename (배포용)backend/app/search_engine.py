"""findol v3 실무 검색 엔진.

검색은 두 층으로 구성됩니다.

1. 검색어 사전: 오타·현장 약어를 교정하고 사용자의 표현을 표준 실무어로 확장
2. 법령지도: 시설·업무 주제를 판별한 뒤 반드시 먼저 확인할 핵심 고시,
   상위 법령, 함께 확인할 규정을 구조적으로 연결

법령지도는 법률 판단을 자동화하지 않습니다. 사용자의 검색 목적을 정리하고
공식 원문으로 이동할 탐색 순서를 만드는 용도입니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import csv
import hashlib
import json
import re
from typing import Any


DATA_DIR = Path(__file__).resolve().parent / "data"
LAW_MAP_PATH = DATA_DIR / "law_map.json"
SEARCH_DICTIONARY_PATH = DATA_DIR / "search_dictionary.csv"


def _compact(text: str | None) -> str:
    """검색 비교용: 공백·가운데점·일부 문장부호를 제거하고 소문자로 변환."""
    return re.sub(r"[\s·ㆍ,./()\[\]{}\-]+", "", text or "").lower()


def _unique(values: list[Any], key=None) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for value in values:
        marker = key(value) if key else value
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


@lru_cache(maxsize=1)
def load_law_map() -> dict:
    try:
        return json.loads(LAW_MAP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"법령지도 파일을 읽지 못했습니다: {exc}") from exc


@lru_cache(maxsize=1)
def load_search_dictionary() -> list[dict]:
    try:
        with SEARCH_DICTIONARY_PATH.open("r", encoding="utf-8-sig", newline="") as file:
            return list(csv.DictReader(file))
    except OSError as exc:
        raise RuntimeError(f"검색어 사전 파일을 읽지 못했습니다: {exc}") from exc


@lru_cache(maxsize=1)
def _topic_index() -> dict[str, dict]:
    return {topic["id"]: topic for topic in load_law_map().get("topics", [])}


@dataclass
class SearchPlan:
    original_query: str
    normalized_query: str
    expanded_terms: list[str]
    intent: str
    intent_summary: str
    correction: str | None = None
    topics: list[dict] = field(default_factory=list)
    checklist: list[str] = field(default_factory=list)
    ambiguities: list[dict] = field(default_factory=list)
    primary_rules: list[dict] = field(default_factory=list)
    upper_laws: list[dict] = field(default_factory=list)
    related_rules: list[dict] = field(default_factory=list)
    matched_dictionary: list[dict] = field(default_factory=list)
    map_verified_on: str | None = None
    map_notice: str | None = None

    @property
    def rule_search_terms(self) -> list[str]:
        titles = [item.get("title") for item in self.primary_rules + self.related_rules if item.get("title")]
        return _unique(titles)

    @property
    def law_search_terms(self) -> list[str]:
        titles = [item.get("title") for item in self.upper_laws if item.get("title")]
        return _unique(titles)


def normalize_query(query: str) -> tuple[str, str | None, list[dict]]:
    """auto_correct 항목만 치환한다. choose 항목은 화면 선택지로 남긴다."""
    cleaned = re.sub(r"\s+", " ", query.strip())
    corrected = cleaned
    changes: list[str] = []
    matched_rows: list[dict] = []

    rows = sorted(
        load_search_dictionary(),
        key=lambda row: len(row.get("user_expression") or ""),
        reverse=True,
    )
    for row in rows:
        source = (row.get("user_expression") or "").strip()
        target = (row.get("standard_expression") or "").strip()
        if not source or source not in corrected:
            continue
        matched_rows.append(row)
        if row.get("handling") != "auto_correct" or not target or source == target:
            continue
        corrected = corrected.replace(source, target)
        changes.append(f"‘{source}’ → ‘{target}’")

    correction = None
    if changes:
        correction = f"{', '.join(_unique(changes))}로 보고 검색했어요."
    return corrected, correction, _unique(matched_rows, key=lambda row: row.get("user_expression"))


def _topic_matches(query: str, dictionary_rows: list[dict]) -> list[dict]:
    compact_query = _compact(query)
    scored: list[dict] = []

    # 사전에서 잡힌 표준 주제는 약한 보조 점수로 사용한다.
    dictionary_topics = {row.get("topic") for row in dictionary_rows if row.get("topic")}

    for topic in load_law_map().get("topics", []):
        matched: list[str] = []
        score = 0
        for trigger in topic.get("triggers", []):
            compact_trigger = _compact(trigger)
            if not compact_trigger or compact_trigger not in compact_query:
                continue
            matched.append(trigger)
            # 긴 구체 표현과 완전일치를 강하게 우선한다.
            score += int(topic.get("priority", 0)) + min(len(compact_trigger) * 10, 100)
            if compact_query == compact_trigger:
                score += 120

        if topic.get("label") in dictionary_topics:
            score += 35

        # 구체적인 시설 분류는 검사·누출 같은 횡단 업무보다 먼저 보여준다.
        if score and topic.get("id") in {
            "manufacturing_use", "storage", "keeping", "small_quantity",
            "vehicle_carry", "vehicle_transport", "transport_container", "offsite_pipeline",
        }:
            score += 100

        if score:
            scored.append({
                "id": topic.get("id"),
                "label": topic.get("label"),
                "score": score,
                "matched_terms": _unique(matched),
                "intent_summary": topic.get("intent_summary"),
            })

    scored.sort(key=lambda item: (item["score"], len("".join(item["matched_terms"]))), reverse=True)

    # 상위 주제가 명시적으로 배제하는 혼동 주제는 낮은 점수일 때 제거한다.
    if scored:
        top_topic = _topic_index().get(scored[0]["id"], {})
        excluded = set(top_topic.get("exclude_topics") or [])
        scored = [
            item for index, item in enumerate(scored)
            if index == 0 or item["label"] not in excluded or item["score"] >= scored[0]["score"] * 0.9
        ]

    return scored[:3]


def _specific_trigger_exists(query: str, term: str, topics: list[dict]) -> bool:
    compact_query = _compact(query)
    compact_term = _compact(term)
    for topic_match in topics:
        topic = _topic_index().get(topic_match.get("id"), {})
        for trigger in topic.get("triggers", []):
            compact_trigger = _compact(trigger)
            if compact_term in compact_trigger and len(compact_trigger) > len(compact_term) and compact_trigger in compact_query:
                return True
    return False


def detect_ambiguities(query: str, topics: list[dict]) -> list[dict]:
    compact_query = _compact(query)
    result: list[dict] = []
    for item in load_law_map().get("ambiguities", []):
        term = item.get("term") or ""
        compact_term = _compact(term)
        if not compact_term or compact_term not in compact_query:
            continue

        # '저장탱크', '사외배관', '탱크로리'처럼 이미 구체적인 표현이 있으면
        # 일반 선택질문은 표시하지 않는다. 단, 매우 짧은 복합 검색은 선택지를 유지한다.
        if _specific_trigger_exists(query, term, topics) and compact_query != compact_term:
            continue
        result.append(item)
    return result[:2]


def _collect_topic_rules(topics: list[dict], field_name: str) -> list[dict]:
    result: list[dict] = []
    for topic_match in topics:
        topic = _topic_index().get(topic_match.get("id"), {})
        for rule in topic.get(field_name, []):
            enriched = {
                **rule,
                "topic_id": topic.get("id"),
                "topic_label": topic.get("label"),
            }
            result.append(enriched)
    return _unique(result, key=lambda item: (item.get("kind"), _compact(item.get("title"))))


def _build_intent(topics: list[dict]) -> tuple[str, str]:
    if not topics:
        return "법령·행정규칙 통합 확인", "입력한 표현과 관련된 법령·고시를 통합하여 확인"
    labels = [item["label"] for item in topics]
    intent = " · ".join(labels)
    summary = topics[0].get("intent_summary") or f"{labels[0]} 관련 기준 확인"
    if len(topics) > 1:
        summary += f" — 함께 연결된 주제: {', '.join(labels[1:])}"
    return intent, summary


def _build_checklist(topics: list[dict]) -> list[str]:
    items: list[str] = []
    for topic_match in topics[:2]:
        topic = _topic_index().get(topic_match.get("id"), {})
        items.extend(topic.get("checklist", []))
    return _unique(items)[:7]


def build_search_plan(query: str, max_terms: int = 10) -> SearchPlan:
    normalized, correction, dictionary_rows = normalize_query(query)
    topics = _topic_matches(normalized, dictionary_rows)
    ambiguities = detect_ambiguities(normalized, topics)
    intent, intent_summary = _build_intent(topics)

    terms: list[str] = [normalized]

    # 사전에 매칭된 표준 표현을 먼저 추가한다.
    for row in dictionary_rows:
        standard = (row.get("standard_expression") or "").strip()
        if standard and row.get("handling") != "choose":
            terms.append(standard)

    # 핵심 주제의 법령 검색어를 우선 추가한다.
    for topic_match in topics:
        topic = _topic_index().get(topic_match.get("id"), {})
        terms.extend(topic.get("search_terms", [])[:6])

    # 자주 입력하는 결합 표현을 표준 업무어로 보정한다.
    if "설치" in normalized and "검사" in normalized:
        terms.extend(["설치검사", "취급시설 검사"])
    if "정기" in normalized and "검사" in normalized:
        terms.extend(["정기검사", "취급시설 검사"])
    if "변경" in normalized and "신고" in normalized:
        terms.extend(["변경신고", "유해화학물질 영업허가"])
    if "변경" in normalized and "허가" in normalized:
        terms.extend(["변경허가", "유해화학물질 영업허가"])

    # 문장형 검색에서 남은 핵심 토큰도 보조 검색어로 사용한다.
    stopwords = {
        "관련", "기준", "경우", "대한", "해야", "하나요", "필요", "방법", "어떻게",
        "있을", "때", "및", "또는", "하고", "싶어", "싶은데", "되는지", "인지",
    }
    tokens = [token for token in re.split(r"[\s,./()]+", normalized) if len(token) >= 2 and token not in stopwords]
    terms.extend(tokens)

    law_map = load_law_map()
    return SearchPlan(
        original_query=query,
        normalized_query=normalized,
        expanded_terms=_unique([term for term in terms if term])[:max_terms],
        intent=intent,
        intent_summary=intent_summary,
        correction=correction,
        topics=topics,
        checklist=_build_checklist(topics),
        ambiguities=ambiguities,
        primary_rules=_collect_topic_rules(topics, "primary_rules"),
        upper_laws=_collect_topic_rules(topics, "upper_laws"),
        related_rules=_collect_topic_rules(topics, "related_rules"),
        matched_dictionary=dictionary_rows[:12],
        map_verified_on=law_map.get("verified_on"),
        map_notice=law_map.get("notice"),
    )


def _candidate_id(title: str, kind: str) -> str:
    digest = hashlib.sha1(f"{kind}|{title}".encode("utf-8")).hexdigest()[:16]
    return f"map-{digest}"


def _candidate_from_rule(rule: dict, group: str) -> dict:
    kind = rule.get("kind") or "admin_rule"
    group_scores = {"core": 1200, "upper": 1050, "related": 900}
    role_defaults = {"core": "핵심 적용 규정", "upper": "상위 법령", "related": "함께 확인할 규정"}
    return {
        "id": _candidate_id(rule.get("title") or "", kind),
        "name": rule.get("title"),
        "type": "법령" if kind == "law" else "고시·행정규칙",
        "department": rule.get("department"),
        "promulgation_date": None,
        "enforcement_date": None,
        "detail_link": rule.get("official_url"),
        "official_url": rule.get("official_url"),
        "source": "law_map",
        "is_mapped": True,
        "map_group": group,
        "rule_role": rule.get("role") or role_defaults[group],
        "topic_label": rule.get("topic_label"),
        "rule_note": rule.get("note"),
        "relevance_score": group_scores[group],
        "matched_terms": [rule.get("topic_label")] if rule.get("topic_label") else [],
        "match_reason": f"법령지도에서 {rule.get('role') or role_defaults[group]}으로 연결",
        "kind": kind,
    }


def _merge_one_candidate(items: list[dict], candidate: dict) -> dict:
    wanted = _compact(candidate.get("name"))
    group_priority = {"core": 3, "upper": 2, "related": 1}
    for item in items:
        actual = _compact(item.get("name"))
        if actual == wanted or (wanted and wanted in actual) or (actual and actual in wanted):
            # 같은 규정이 여러 주제에서 중복 연결되면 핵심(core) 역할을 하위 역할로
            # 덮어쓰지 않는다. API가 준 최신 메타데이터는 그대로 유지한다.
            existing_group = item.get("map_group")
            should_promote = group_priority.get(candidate["map_group"], 0) > group_priority.get(existing_group, 0)
            if not existing_group or should_promote:
                item.update({
                    "is_mapped": True,
                    "map_group": candidate["map_group"],
                    "rule_role": candidate["rule_role"],
                    "topic_label": candidate.get("topic_label"),
                    "rule_note": candidate.get("rule_note"),
                    "match_reason": candidate["match_reason"],
                    "kind": candidate["kind"],
                })
            item["official_url"] = item.get("detail_link") or item.get("official_url") or candidate.get("official_url")
            item["relevance_score"] = max(item.get("relevance_score", 0), candidate["relevance_score"])
            return item
    items.append(candidate)
    return candidate


def inject_mapped_results(law_items: list[dict], admin_items: list[dict], plan: SearchPlan) -> dict:
    """법령지도 규정을 결과 상단에 보장하고 섹션별 목록을 만든다."""
    groups: dict[str, list[dict]] = {"core": [], "upper": [], "related": []}
    specifications = [
        ("core", plan.primary_rules),
        ("upper", plan.upper_laws),
        ("related", plan.related_rules),
    ]

    for group, rules in specifications:
        for rule in rules:
            candidate = _candidate_from_rule(rule, group)
            target = law_items if candidate["kind"] == "law" else admin_items
            merged = _merge_one_candidate(target, candidate)
            if merged.get("map_group") == group:
                groups[group].append(merged)

    for group in groups:
        groups[group] = _unique(groups[group], key=lambda item: (item.get("kind"), _compact(item.get("name"))))
        groups[group].sort(key=lambda item: item.get("relevance_score", 0), reverse=True)

    mapped_keys = {
        (item.get("kind"), _compact(item.get("name")))
        for item in groups["core"] + groups["upper"] + groups["related"]
    }
    general_laws = [item for item in law_items if ("law", _compact(item.get("name"))) not in mapped_keys]
    general_admin = [item for item in admin_items if ("admin_rule", _compact(item.get("name"))) not in mapped_keys]

    return {
        "core_rules": groups["core"],
        "upper_laws": groups["upper"],
        "related_rules": groups["related"],
        "laws": general_laws,
        "admin_rules": general_admin,
        "all_laws": law_items,
        "all_admin_rules": admin_items,
    }


def score_result(item: dict, plan: SearchPlan) -> dict:
    """법령/행정규칙 API 결과에 관련도 점수와 검색 이유를 추가."""
    name = item.get("name") or ""
    department = item.get("department") or ""
    rule_type = item.get("type") or ""
    haystack = _compact(" ".join([name, department, rule_type]))

    score = int(item.get("relevance_score") or 0)
    matched: list[str] = list(item.get("matched_terms") or [])
    original = _compact(plan.normalized_query)

    if original and original == _compact(name):
        score += 180
    elif original and original in _compact(name):
        score += 120

    source_terms = item.get("_source_terms") or []
    for source_term in source_terms:
        if source_term not in matched:
            matched.append(source_term)
            score += 34

    for index, term in enumerate(plan.expanded_terms):
        compact_term = _compact(term)
        if compact_term and compact_term in haystack:
            if term not in matched:
                matched.append(term)
            score += max(18, 72 - index * 7)

    # 핵심 법령명 부분 일치 보너스
    mapped_titles = [rule.get("title") for rule in plan.primary_rules + plan.related_rules + plan.upper_laws]
    for title in mapped_titles:
        if title and _compact(title) == _compact(name):
            score += 260

    if "화학물질관리법" in name:
        score += 30
    if department in {"환경부", "기후에너지환경부", "화학물질안전원", "국립환경과학원"}:
        score += 12

    if item.get("is_mapped"):
        reason = item.get("match_reason") or "법령지도에서 우선 연결"
    elif matched:
        reason = " · ".join(f"‘{term}’ 일치" for term in _unique(matched)[:3])
    elif plan.intent:
        reason = f"{plan.intent} 관련 결과"
    else:
        reason = "관련 법령 후보"

    return {
        **item,
        "relevance_score": score,
        "matched_terms": _unique(matched),
        "match_reason": reason,
    }


def rank_results(items: list[dict], plan: SearchPlan) -> list[dict]:
    scored = [score_result(item, plan) for item in items]
    return sorted(
        scored,
        key=lambda item: (
            item.get("relevance_score", 0),
            item.get("enforcement_date") or item.get("promulgation_date") or "",
            item.get("name") or "",
        ),
        reverse=True,
    )


def public_plan(plan: SearchPlan) -> dict:
    """FastAPI 응답에 넣을 JSON 직렬화 가능한 검색계획."""
    return {
        "query": plan.original_query,
        "normalized_query": plan.normalized_query,
        "correction": plan.correction,
        "intent": plan.intent,
        "intent_summary": plan.intent_summary,
        "topics": plan.topics,
        "checklist": plan.checklist,
        "ambiguities": plan.ambiguities,
        "expanded_terms": plan.expanded_terms,
        "map_verified_on": plan.map_verified_on,
        "map_notice": plan.map_notice,
    }
