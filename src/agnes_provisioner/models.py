from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    consent: Mapped[bool] = mapped_column(Boolean)
    consent_reference: Mapped[str] = mapped_column(String(256))
    mailbox_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    secret_ref: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[float] = mapped_column(Float)


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(20), default="READY")
    pause_reason: Mapped[str] = mapped_column(String(256), default="")
    blocked_until: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[float] = mapped_column(Float)


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(40))
    remote_id: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40))
    evidence: Mapped[str] = mapped_column(String(256), default="")
    activated_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    api_key_ref: Mapped[str] = mapped_column(String(120), default="")


class Proxy(Base):
    __tablename__ = "proxies"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    server: Mapped[str] = mapped_column(String(256))
    provider: Mapped[str] = mapped_column(String(120), default="")
    username_env: Mapped[str] = mapped_column(String(120), default="")
    password_env: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(20), default="UNCHECKED")
    failures: Mapped[int] = mapped_column(Integer, default=0)
    successes: Mapped[int] = mapped_column(Integer, default=0)
    last_checked: Mapped[float | None] = mapped_column(Float, nullable=True)
    leased_job_id: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)


class ProxyMeta(Base):
    __tablename__ = "proxy_meta"
    proxy_id: Mapped[str] = mapped_column(
        ForeignKey("proxies.id", ondelete="CASCADE"), primary_key=True
    )
    generation: Mapped[int] = mapped_column(Integer, default=0)
    window_executions: Mapped[int] = mapped_column(Integer, default=0)
    window_results: Mapped[int] = mapped_column(Integer, default=0)
    total_executions: Mapped[int] = mapped_column(Integer, default=0)
    total_results: Mapped[int] = mapped_column(Integer, default=0)
    session_sticky_id: Mapped[str] = mapped_column(String(80), default="")
    session_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    last_ip: Mapped[str] = mapped_column(String(80), default="")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_rotated_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    inline_username: Mapped[str] = mapped_column(Text, default="")
    inline_password: Mapped[str] = mapped_column(Text, default="")


class Job(Base):
    __tablename__ = "registration_jobs"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(40), index=True)
    phase: Mapped[str] = mapped_column(String(40), default="PREPARE")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[float] = mapped_column(Float, default=0)
    error_code: Mapped[str] = mapped_column(String(80), default="")
    message: Mapped[str] = mapped_column(String(256), default="")
    proxy_id: Mapped[str | None] = mapped_column(ForeignKey("proxies.id"), nullable=True)
    submitted_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float)


class JobEvent(Base):
    __tablename__ = "job_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("registration_jobs.id", ondelete="CASCADE"), index=True
    )
    at: Mapped[float] = mapped_column(Float)
    from_state: Mapped[str] = mapped_column(String(40), default="")
    to_state: Mapped[str] = mapped_column(String(40))
    code: Mapped[str] = mapped_column(String(80), default="")
    message: Mapped[str] = mapped_column(Text, default="")
