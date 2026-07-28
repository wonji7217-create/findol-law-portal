"""국민참여입법센터 정보공개 API 연동.

사용자가 제공한 공식 활용가이드와 실제 XML 응답 구조를 기준으로 구현했습니다.

- 행정예고 목록: /rest/ptcpAdmPp.xml
- 행정예고 상세: /rest/ptcpAdmPp/{ogAdmPpSeq}/{mappingAdmRulSeq}/{announceType}.xml
- 입법예고 목록: /rest/ogLmPp.xml
- 입법예고 상세: /rest/ogLmPp/{ogLmPpSeq}/{mappingLbicId}/{announceType}.xml

인증값은 정보공개 신청 ID의 @ 앞부분이며, LAWMAKING_API_OC 환경변수로만 읽습니다.
외부에 노출되는 URL에는 OC 값을 포함하지 않습니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import os
import re
from typing import Iterable
from urllib.parse import urlparse, urlunparse
from xml.etree import ElementTree as ET

import httpx

BASE_URL = "https://www.lawmaking.go.kr"
ADMIN_LIST_URL = f"{BASE_URL}/rest/ptcpAdmPp.xml"
LEGISLATIVE_LIST_URL = f"{BASE_URL}/rest/ogLmPp.xml"
PUBLIC_HOME_URL = BASE_URL

DEFAULT_AGENCIES = (
    "기후에너지환경부",
    "환경부",
    "화학물질안전원",
    "국립환경과학원",
)
DEFAULT_KEYWORDS = (
    "화학물질",
    "유해화학물질",
    "유독물질",
    "인체급성유해성물질",
    "인체만성유해성물질",
    "생태유해성물질",
    "사고대비물질",
    "제한물질",
    "금지물질",
    "허가물질",
    "화학물질관리법",
    "취급시설",
    "화학사고",
)
DEFAULT_MINISTRY_CODE = "1480000"


class LawmakingApiError(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = re.sub(r"\s+", " ", data or "").strip()
        if value:
            self.parts.append(value)

    def text(self) -> str:
        return "\n".join(self.parts)


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(unescape(value))
        parser.close()
        return re.sub(r"\n{3,}", "\n\n", parser.text()).strip()
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def _text(node: ET.Element | None, tag: str) -> str | None:
    if node is None:
        return None
    child = node.find(tag)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _normalize_download_url(url: str | None) -> str | None:
    if not url:
        return None
    value = url.strip()
    if value.startswith("/"):
        return f"{BASE_URL}{value}"
    parsed = urlparse(value)
    if parsed.scheme == "http" and parsed.netloc.endswith("lawmaking.go.kr"):
        return urlunparse(parsed._replace(scheme="https"))
    return value


def _get_oc() -> str:
    value = (os.getenv("LAWMAKING_API_OC") or "").strip()
    if not value:
        raise LawmakingApiError("LAWMAKING_API_OC 환경변수가 설정되지 않았습니다.")
    if "@" in value:
        # 실수로 이메일 전체를 넣어도 @ 앞부분만 사용한다.
        value = value.split("@", 1)[0]
    return value


def configured() -> bool:
    return bool((os.getenv("LAWMAKING_API_OC") or "").strip())


def _parse_xml(xml_text: str) -> ET.Element:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise LawmakingApiError(f"XML 응답을 읽지 못했습니다: {exc}") from exc
    ret_msg = _text(root, "retMsg")
    if ret_msg and ret_msg != "200":
        raise LawmakingApiError(f"국민참여입법센터 API 오류 코드: {ret_msg}")
    return root


async def _get_xml(url: str, params: dict | None = None, timeout: float = 20.0) -> ET.Element:
    request_params = {"OC": _get_oc(), **(params or {})}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url, params=request_params)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LawmakingApiError(f"국민참여입법센터 API 호출 실패: {exc}") from exc
    return _parse_xml(response.text)


def _list_nodes(root: ET.Element) -> list[ET.Element]:
    list_node = root.find("list")
    if list_node is None:
        return []
    # 실제 행정예고 응답은 ApiList05Vo이며, 다른 API는 태그명이 다를 수 있어
    # list의 직계 자식 전체를 항목으로 처리한다.
    return list(list_node)


def _parse_list_item(node: ET.Element, kind: str) -> dict:
    if kind == "administrative_notice":
        seq = _text(node, "ogAdmPpSeq")
        mapping_id = _text(node, "mappingAdmRulSeq")
        title = _text(node, "admRulNm")
    else:
        seq = _text(node, "ogLmPpSeq")
        mapping_id = _text(node, "mappingLbicId")
        title = _text(node, "lsNm")

    return {
        "kind": kind,
        "seq": seq,
        "mapping_id": mapping_id,
        "announce_type": _text(node, "announceType"),
        "title": title,
        "rule_type": _text(node, "lsClsNm"),
        "department": _text(node, "asndOfiNm"),
        "notice_no": _text(node, "pntcNo"),
        "notice_date": _text(node, "pntcDt"),
        "start_date": _text(node, "stYd"),
        "end_date": _text(node, "edYd"),
        "file_name": _text(node, "FileName") or _text(node, "flNm"),
        "file_url": _normalize_download_url(_text(node, "FileDownLink") or _text(node, "FileDownUrl") or _text(node, "fileDownUrl")),
        "read_count": _text(node, "readCnt"),
    }


async def fetch_administrative_list(**params) -> list[dict]:
    root = await _get_xml(ADMIN_LIST_URL, params)
    return [_parse_list_item(node, "administrative_notice") for node in _list_nodes(root)]


async def fetch_legislative_list(**params) -> list[dict]:
    root = await _get_xml(LEGISLATIVE_LIST_URL, params)
    return [_parse_list_item(node, "legislative_notice") for node in _list_nodes(root)]


def _parse_files(parent: ET.Element | None, group: str) -> list[dict]:
    if parent is None:
        return []
    attachments: list[dict] = []
    # 실제 응답은 <FileListVo>가 반복되며, 빈 목록은 self-closing 태그다.
    for item in list(parent):
        name = _text(item, "FileName") or _text(item, "flNm")
        url = _normalize_download_url(_text(item, "FileDownUrl") or _text(item, "fileDownUrl"))
        if name or url:
            attachments.append({"name": name or "첨부파일", "url": url, "group": group})
    return attachments


def _detail_root(root: ET.Element) -> ET.Element | None:
    info = root.find("info")
    if info is None:
        return None
    children = list(info)
    return children[0] if children else None


async def fetch_administrative_detail(item: dict) -> dict:
    if not item.get("seq") or not item.get("mapping_id") or not item.get("announce_type"):
        return item
    url = f"{BASE_URL}/rest/ptcpAdmPp/{item['seq']}/{item['mapping_id']}/{item['announce_type']}.xml"
    root = await _get_xml(url)
    node = _detail_root(root)
    if node is None:
        return item
    body_html = _text(node, "admPpCts") or ""
    attachments = _parse_files(node.find("ogAdmFlList"), "행정규칙안")
    attachments += _parse_files(node.find("ptcpAdmPpFlList"), "첨부파일")
    return {
        **item,
        "title": _text(node, "admRulNm") or item.get("title"),
        "notice_guide": _text(node, "asndOfiNm"),
        "revision_type": _text(node, "lmTpNm"),
        "rule_type": _text(node, "lsClsNm") or item.get("rule_type"),
        "start_date": _text(node, "stYd") or item.get("start_date"),
        "end_date": _text(node, "edYd") or item.get("end_date"),
        "telephone": _text(node, "telNo"),
        "fax": _text(node, "faxNo"),
        "email": _text(node, "email"),
        "body_html": body_html,
        "body_text": html_to_text(body_html),
        "attachments": attachments,
    }


async def fetch_legislative_detail(item: dict) -> dict:
    if not item.get("seq") or not item.get("mapping_id") or not item.get("announce_type"):
        return item
    url = f"{BASE_URL}/rest/ogLmPp/{item['seq']}/{item['mapping_id']}/{item['announce_type']}.xml"
    root = await _get_xml(url)
    node = _detail_root(root)
    if node is None:
        return item
    body_html = _text(node, "lmPpCts") or ""
    attachments = _parse_files(node.find("ogLsFlList"), "법령안")
    attachments += _parse_files(node.find("ogLmPpFlList"), "첨부파일")
    return {
        **item,
        "title": _text(node, "lsNm") or item.get("title"),
        "notice_guide": _text(node, "asndOfiNm"),
        "department_detail": _text(node, "asndDptNm"),
        "revision_type": _text(node, "lmTpNm"),
        "rule_type": _text(node, "lsClsNm") or item.get("rule_type"),
        "start_date": _text(node, "stYd") or item.get("start_date"),
        "end_date": _text(node, "edYd") or item.get("end_date"),
        "telephone": _text(node, "telNo"),
        "fax": _text(node, "faxNo"),
        "email": _text(node, "email"),
        "body_html": body_html,
        "body_text": html_to_text(body_html),
        "attachments": attachments,
    }


def _unique(items: Iterable[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in items:
        key = f"{item.get('kind')}:{item.get('seq') or ''}:{item.get('mapping_id') or ''}:{item.get('announce_type') or ''}"
        if key.strip(":") and key not in merged:
            merged[key] = item
    return list(merged.values())


def agencies() -> tuple[str, ...]:
    raw = os.getenv("LAWMAKING_AGENCIES")
    if not raw:
        return DEFAULT_AGENCIES
    values = tuple(value.strip() for value in raw.split(",") if value.strip())
    return values or DEFAULT_AGENCIES


def keywords() -> tuple[str, ...]:
    raw = os.getenv("LAWMAKING_KEYWORDS")
    if not raw:
        return DEFAULT_KEYWORDS
    values = tuple(value.strip() for value in raw.split(",") if value.strip())
    return values or DEFAULT_KEYWORDS


def relevant(item: dict) -> bool:
    text = " ".join([
        item.get("title") or "",
        item.get("department") or "",
        item.get("body_text") or "",
    ])
    if any(agency in text for agency in agencies()):
        return True
    return any(keyword in text for keyword in keywords())


async def collect_candidates(
    *,
    include_administrative: bool = True,
    include_legislative: bool = True,
    max_items: int = 60,
) -> list[dict]:
    """관련 목록을 여러 필터로 조회한 뒤 상세정보까지 합친다.

    API 가이드에 페이지 변수 안내가 없어, 기관/키워드별 조회를 병렬이 아닌
    순차 호출해 서버 부하를 낮추고 각 응답의 기본 최신 20건을 중복 제거한다.
    """
    raw: list[dict] = []

    if include_administrative:
        for agency in agencies():
            raw.extend(await fetch_administrative_list(asndOfiNm=agency))
        for keyword in keywords()[:10]:
            raw.extend(await fetch_administrative_list(admRulNm=keyword))

    if include_legislative:
        ministry_code = (os.getenv("LAWMAKING_MINISTRY_CODE") or DEFAULT_MINISTRY_CODE).strip()
        raw.extend(await fetch_legislative_list(cptOfiOrgCd=ministry_code))
        for keyword in keywords()[:10]:
            raw.extend(await fetch_legislative_list(lsNm=keyword))

    candidates = [item for item in _unique(raw) if item.get("seq") and item.get("mapping_id") and item.get("announce_type")]
    candidates = candidates[:max(1, min(max_items, 200))]

    detailed: list[dict] = []
    for item in candidates:
        try:
            if item["kind"] == "administrative_notice":
                detail = await fetch_administrative_detail(item)
            else:
                detail = await fetch_legislative_detail(item)
        except LawmakingApiError as exc:
            detail = {**item, "detail_warning": str(exc), "attachments": []}
        if relevant(detail):
            detailed.append(detail)
    return detailed

def _summary_from_body(body_text: str | None, limit: int = 700) -> str:
    text = re.sub(r"\s+", " ", body_text or "").strip()
    if not text:
        return "국민참여입법센터 정보공개 API에서 수집한 예고 자료입니다."
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def _matched_tags(item: dict) -> list[str]:
    text = " ".join([item.get("title") or "", item.get("body_text") or ""])
    matches = [keyword for keyword in keywords() if keyword in text]
    base = ["행정예고" if item.get("kind") == "administrative_notice" else "입법예고"]
    return list(dict.fromkeys(base + matches))[:10]


def to_archive_payload(item: dict) -> dict:
    kind = item.get("kind") or "administrative_notice"
    seq = item.get("seq") or ""
    mapping_id = item.get("mapping_id") or ""
    announce_type = item.get("announce_type") or ""
    source_key = f"lawmaking:{kind}:{seq}:{mapping_id}:{announce_type}"
    notice_label = "행정예고" if kind == "administrative_notice" else "입법예고"
    material_type = " · ".join(value for value in [notice_label, item.get("rule_type"), item.get("revision_type")] if value)

    contact_parts = []
    if item.get("department_detail"):
        contact_parts.append(f"담당부서: {item['department_detail']}")
    if item.get("telephone"):
        contact_parts.append(f"전화: {item['telephone']}")
    if item.get("fax"):
        contact_parts.append(f"팩스: {item['fax']}")
    if item.get("email"):
        contact_parts.append(f"이메일: {item['email']}")

    body_text = item.get("body_text") or ""
    note_parts = []
    if item.get("notice_guide"):
        note_parts.append(str(item["notice_guide"]))
    if contact_parts:
        note_parts.append(" / ".join(contact_parts))
    if body_text:
        note_parts.append(body_text[:12000])
    if item.get("detail_warning"):
        note_parts.append(f"상세조회 경고: {item['detail_warning']}")

    return {
        "source_key": source_key,
        "kind": "notice",
        "external_id": str(seq),
        "title": item.get("title") or "(제목 없음)",
        "material_type": material_type or notice_label,
        "department": item.get("department"),
        "source_name": "국민참여입법센터",
        # 인증값이 포함된 상세 API 주소는 외부에 저장하지 않는다.
        "official_url": PUBLIC_HOME_URL,
        "source_query": ", ".join(_matched_tags(item)),
        "published_date": item.get("notice_date") or item.get("start_date"),
        "deadline_date": item.get("end_date"),
        "summary": _summary_from_body(body_text),
        "findol_note": "\n\n".join(note_parts),
        "tags": _matched_tags(item),
        "related_laws": [],
        "related_tasks": _matched_tags(item)[1:],
        "attachments": item.get("attachments") or ([{
            "name": item.get("file_name") or "첨부파일",
            "url": item.get("file_url"),
            "group": "목록 첨부파일",
        }] if item.get("file_url") else []),
    }
