"""데이터베이스 연결 설정.

기본은 로컬 SQLite이며, Render/Supabase/PostgreSQL을 사용할 때는
DATABASE_URL 환경변수를 지정하면 같은 코드로 전환됩니다.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./law_portal.db")
# 일부 플랫폼이 예전 postgres:// 스킴을 전달하는 경우 SQLAlchemy용으로 보정
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    from . import models  # noqa: 모델 등록
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
