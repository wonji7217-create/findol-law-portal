"""findol 데이터 모델.

- LawSnapshot / AdminRuleSnapshot: 법제처 검색 결과의 변경 스냅샷
- ArchiveEntry: 스냅샷 또는 외부 뉴스레터 수집기에서 생성된 개정 아카이브 게시글
"""

from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import Column, Integer, String, DateTime, Text
from .db import Base

KST = ZoneInfo("Asia/Seoul")

def now_kst_naive():
    return datetime.now(KST).replace(tzinfo=None)


class LawSnapshot(Base):
    __tablename__ = "law_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, index=True)
    name = Column(String, index=True)
    promulgation_date = Column(String)
    enforcement_date = Column(String)
    department = Column(String)
    detail_link = Column(String)
    source_query = Column(String)
    fetched_at = Column(DateTime, default=now_kst_naive, index=True)


class AdminRuleSnapshot(Base):
    __tablename__ = "admin_rule_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, index=True)
    name = Column(String, index=True)
    rule_type = Column(String)
    promulgation_date = Column(String)
    department = Column(String)
    detail_link = Column(String)
    source_query = Column(String)
    fetched_at = Column(DateTime, default=now_kst_naive, index=True)


class ArchiveEntry(Base):
    """개정정보 아카이브 게시글.

    archive_key는 중복 방지용 고유키입니다. 법제처 스냅샷은
    kind/external_id/fetched_at 조합으로, 외부 수집기는 source_key로 생성합니다.
    """

    __tablename__ = "archive_entries"

    id = Column(Integer, primary_key=True, index=True)
    archive_key = Column(String, unique=True, index=True, nullable=False)

    kind = Column(String, index=True)  # law / admin_rule / notice / material
    external_id = Column(String, index=True)
    source_key = Column(String, index=True)
    content_hash = Column(String, index=True)
    revision_no = Column(Integer, default=1)
    previous_entry_id = Column(Integer)
    event_action = Column(String, index=True)  # new / changed / imported

    title = Column(String, index=True, nullable=False)
    material_type = Column(String, index=True)
    department = Column(String, index=True)
    source_name = Column(String)
    official_url = Column(Text)
    source_query = Column(String)

    # YYYYMMDD 문자열. 게시일은 아카이브 기본 정렬 기준.
    published_date = Column(String, index=True)
    promulgation_date = Column(String, index=True)
    enforcement_date = Column(String, index=True)
    deadline_date = Column(String, index=True)

    summary = Column(Text)
    findol_note = Column(Text)
    tags_json = Column(Text)
    related_laws_json = Column(Text)
    related_tasks_json = Column(Text)
    attachments_json = Column(Text)

    collected_at = Column(DateTime, default=now_kst_naive, index=True)
    updated_at = Column(DateTime, default=now_kst_naive, onupdate=now_kst_naive)

class KnowledgeTopic(Base):
    """관리자 화면에서 편집하는 동적 환경지식 주제."""

    __tablename__ = "knowledge_topics"

    id = Column(Integer, primary_key=True, index=True)
    topic_key = Column(String, unique=True, index=True, nullable=False)
    label = Column(String, index=True, nullable=False)
    description = Column(Text)
    intent_summary = Column(Text)
    triggers_json = Column(Text)
    search_terms_json = Column(Text)
    primary_rules_json = Column(Text)
    upper_laws_json = Column(Text)
    related_rules_json = Column(Text)
    checklist_json = Column(Text)
    related_tasks_json = Column(Text)
    notes = Column(Text)
    is_active = Column(Integer, default=1, index=True)
    priority = Column(Integer, default=50)
    created_at = Column(DateTime, default=now_kst_naive)
    updated_at = Column(DateTime, default=now_kst_naive, onupdate=now_kst_naive)
