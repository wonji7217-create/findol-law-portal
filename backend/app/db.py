"""
SQLite 데이터베이스 연결 설정.
2단계: 검색할 때마다 결과를 누적 저장 -> 법령/고시별 변경 이력(타임라인)을 쌓아감.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./law_portal.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    from . import models  # noqa: 모델 등록을 위해 임포트
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
