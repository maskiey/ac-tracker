from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.fetcher import FetcherConfig, OJFetcher


def _memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_is_source_configured_codeforces():
    db = _memory_db()
    cfg = FetcherConfig(codeforces_handle="tourist")
    f = OJFetcher(db, cfg)
    assert f._is_source_configured("codeforces") is True
    assert f._is_source_configured("luogu") is False


def test_is_source_configured_luogu_requires_cookie_and_identity():
    db = _memory_db()
    cfg = FetcherConfig(luogu_uid="1", luogu_cookie="")
    f = OJFetcher(db, cfg)
    assert f._is_source_configured("luogu") is False

    cfg2 = FetcherConfig(luogu_cookie="x=y", luogu_uid="1")
    f2 = OJFetcher(db, cfg2)
    assert f2._is_source_configured("luogu") is True


def test_is_source_configured_nowcoder_atcoder():
    db = _memory_db()
    f = OJFetcher(db, FetcherConfig(nowcoder_uid="123"))
    assert f._is_source_configured("nowcoder") is True
    f2 = OJFetcher(db, FetcherConfig(atcoder_username="u"))
    assert f2._is_source_configured("atcoder") is True
