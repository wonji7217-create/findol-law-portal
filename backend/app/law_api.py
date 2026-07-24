"""
법제처 Open API (국가법령정보 공동활용, open.law.go.kr) 연동 클라이언트

주의: 법제처 Open API는 XML만 안정적으로 지원합니다 (JSON은 일부 API만 지원).
      아래는 '법령 검색' API 기준 표준 URL 패턴입니다.
      로그인 후 마이페이지 > API인증키관리 에서 정확한 요청 URL/파라미터를
      한 번 더 확인하시는 걸 권장합니다 (API별로 파라미터가 조금씩 다를 수 있음).
"""

import os
import httpx
import xmltodict
from typing import Optional

LAW_SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
LAW_SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"


class LawApiError(Exception):
    pass


def _get_oc() -> str:
    """법제처 Open API 인증키를 호출 시점에 읽음 (임포트 순서 문제 방지)"""
    return os.getenv("LAW_API_OC", "")


async def search_law(query: str, display: int = 20, page: int = 1) -> dict:
    """
    법령 검색 (target=law)
    - query: 검색어 (예: '안전진단', '화학물질관리법')
    - display: 페이지당 결과 수
    - page: 페이지 번호
    """
    oc = _get_oc()
    if not oc:
        raise LawApiError("LAW_API_OC 환경변수(법제처 Open API 인증키)가 설정되지 않았습니다.")

    params = {
        "OC": oc,
        "target": "law",
        "type": "XML",
        "query": query,
        "display": display,
        "page": page,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(LAW_SEARCH_URL, params=params)
        resp.raise_for_status()

    try:
        data = xmltodict.parse(resp.text)
    except Exception as e:
        raise LawApiError(f"응답 파싱 실패: {e}")

    return data


async def search_admrul(query: str, display: int = 20, page: int = 1) -> dict:
    """행정규칙(고시·훈령·예규) 검색 (target=admrul)"""
    oc = _get_oc()
    if not oc:
        raise LawApiError("LAW_API_OC 환경변수(법제처 Open API 인증키)가 설정되지 않았습니다.")

    params = {
        "OC": oc,
        "target": "admrul",
        "type": "XML",
        "query": query,
        "display": display,
        "page": page,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(LAW_SEARCH_URL, params=params)
        resp.raise_for_status()

    try:
        data = xmltodict.parse(resp.text)
    except Exception as e:
        raise LawApiError(f"응답 파싱 실패: {e}")

    return data


def normalize_law_results(raw: dict) -> list[dict]:
    """법제처 XML 파싱 결과를 프론트에서 쓰기 좋은 형태로 정규화"""
    root = raw.get("LawSearch", {})
    items = root.get("law", [])
    if isinstance(items, dict):
        items = [items]

    results = []
    for item in items:
        results.append({
            "id": item.get("법령일련번호"),
            "name": item.get("법령명한글"),
            "promulgation_date": item.get("공포일자"),
            "enforcement_date": item.get("시행일자"),
            "department": item.get("소관부처명"),
            "detail_link": item.get("법령상세링크"),
        })
    return results


def normalize_admrul_results(raw: dict) -> list[dict]:
    """행정규칙(고시·훈령) XML 파싱 결과 정규화"""
    root = raw.get("AdmRulSearch", {})
    items = root.get("admrul", [])
    if isinstance(items, dict):
        items = [items]

    results = []
    for item in items:
        results.append({
            "id": item.get("행정규칙일련번호"),
            "name": item.get("행정규칙명"),
            "type": item.get("행정규칙종류"),
            "promulgation_date": item.get("발령일자"),
            "department": item.get("소관부처명"),
            "detail_link": item.get("행정규칙상세링크"),
        })
    return results


# 환경·안전 관련 여부 판단 기준.
# - 소관부처가 환경·안전 관련 부처인 경우 (부처명 변경 이력 대응을 위해 여러 개 나열)
# - 또는 법령/고시명 자체에 환경·안전 관련 법령 키워드가 포함된 경우
#
# 환경·안전 종사자(대기/수질/폐기물/화학물질/산업안전 등) 실무 기준으로 구성했습니다.
# 필요한 법령이 빠져있으면 알려주시면 바로 추가해드릴게요.
ENV_SAFETY_DEPARTMENTS = {
    "환경부",
    "기후에너지환경부",  # 2026년 조직개편 이후 명칭
    "화학물질안전원",
    "국립환경과학원",
    "고용노동부",
    "산업안전보건공단",
    "소방청",
    "행정안전부",  # 재난안전 관련 법령 다수 소관
}

ENV_SAFETY_NAME_KEYWORDS = (
    # 화학물질 관련 (화관법·화평법)
    "화학물질관리법",
    "화학물질의 등록 및 평가 등에 관한 법률",
    "화학물질",
    "유해화학물질",
    "유독물질",
    "화평법",
    "화관법",
    "취급시설",
    # 대기·수질·토양·소음
    "대기환경보전법",
    "물환경보전법",
    "수질 및 수생태계",
    "토양환경보전법",
    "소음·진동관리법",
    "소음진동관리법",
    "악취방지법",
    # 폐기물·자원순환
    "폐기물관리법",
    "자원순환기본법",
    "잔류성유기오염물질",
    # 산업안전·위험물
    "산업안전보건법",
    "위험물안전관리법",
    "고압가스",
    "가스안전관리법",
    # 환경영향평가·화학사고 대응
    "환경영향평가법",
    "화학사고",
)


def is_chem_related(item: dict) -> bool:
    """법령/행정규칙 하나가 환경·안전 실무 관련인지 판단"""
    dept = (item.get("department") or "").strip()
    name = (item.get("name") or "")

    if dept in ENV_SAFETY_DEPARTMENTS:
        return True
    if any(keyword in name for keyword in ENV_SAFETY_NAME_KEYWORDS):
        return True
    return False


def filter_chem_related(items: list[dict]) -> list[dict]:
    """환경·안전 관련 항목만 남기고 필터링"""
    return [item for item in items if is_chem_related(item)]
