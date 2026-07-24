"""
법령/행정규칙 스냅샷 모델.

검색할 때마다 결과를 그대로 저장하는 게 아니라, 같은 항목(external_id)의
이전 스냅샷과 내용이 달라졌을 때만 새 스냅샷을 추가합니다.
-> 시간이 지나면서 자연스럽게 '개정 이력 타임라인'이 쌓입니다.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from .db import Base


class LawSnapshot(Base):
    __tablename__ = "law_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, index=True)  # 법령일련번호
    name = Column(String, index=True)
    promulgation_date = Column(String)
    enforcement_date = Column(String)
    department = Column(String)
    detail_link = Column(String)
    source_query = Column(String)  # 어떤 검색어로 수집됐는지
    fetched_at = Column(DateTime, default=datetime.utcnow)


class AdminRuleSnapshot(Base):
    __tablename__ = "admin_rule_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, index=True)  # 행정규칙일련번호
    name = Column(String, index=True)
    rule_type = Column(String)  # 고시/훈령/예규
    promulgation_date = Column(String)
    department = Column(String)
    detail_link = Column(String)
    source_query = Column(String)
    fetched_at = Column(DateTime, default=datetime.utcnow)
