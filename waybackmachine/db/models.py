from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    link: Mapped[str] = mapped_column(Text, nullable=False)
    subcategories: Mapped[list["Subcategory"]] = relationship(back_populates="category")


class Subcategory(Base):
    __tablename__ = "subcategories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    link: Mapped[str] = mapped_column(Text, nullable=False)
    threads_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    posts_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_list_fetched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    category: Mapped["Category"] = relationship(back_populates="subcategories")
    threads: Mapped[list["Thread"]] = relationship(back_populates="subcategory")


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    link: Mapped[str] = mapped_column(Text, nullable=False)
    replies_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    views_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pagination: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_sticky: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pagination_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subcategory_id: Mapped[int] = mapped_column(ForeignKey("subcategories.id"), nullable=False)
    scrape_in_progress: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    posts_fetched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subcategory: Mapped["Subcategory"] = relationship(back_populates="threads")
    posts: Mapped[list["Post"]] = relationship(back_populates="thread")
    evergreen_score: Mapped["ThreadEvergreenScore | None"] = relationship(
        back_populates="thread", uselist=False, cascade="all, delete-orphan"
    )


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_joindate: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    user_posts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_register: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    post_date_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    post_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id"), nullable=False)
    post_page_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    post_counter: Mapped[str | None] = mapped_column(String(32), nullable=True)
    thread: Mapped["Thread"] = relationship(back_populates="posts")


class ThreadEvergreenScore(Base):
    __tablename__ = "thread_evergreen_score"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    thread_id: Mapped[int] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
    final_score: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_score: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    ai_article_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_post_rewrites_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    era_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    era_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tech_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tech_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forum_main: Mapped[str | None] = mapped_column(String(512), nullable=True)
    forum_sub: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    thread: Mapped["Thread"] = relationship(back_populates="evergreen_score")


class Phase1ExportRun(Base):
    __tablename__ = "phase1_export_run"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exported_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    exported_decision: Mapped[str] = mapped_column(String(16), nullable=False)
    exported_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_scored_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    by_decision: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_version_filter: Mapped[str | None] = mapped_column(String(32), nullable=True)
    top_n: Mapped[int] = mapped_column(Integer, nullable=False)
    threads: Mapped[list["Phase1ExportThread"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    category_rows: Mapped[list["Phase1ExportCategory"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    keyword_hits: Mapped[list["Phase1ExportKeywordHit"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    crossgen_hits: Mapped[list["Phase1ExportCrossgenHit"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class Phase1ExportThread(Base):
    __tablename__ = "phase1_export_thread"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("phase1_export_run.id", ondelete="CASCADE"), nullable=False
    )
    thread_id: Mapped[int] = mapped_column(Integer, nullable=False)
    final_score: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    category_path: Mapped[str] = mapped_column(Text, nullable=False)
    is_sticky: Mapped[bool] = mapped_column(Boolean, nullable=False)
    replies_no: Mapped[int] = mapped_column(Integer, nullable=False)
    pagination_no: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_post_at: Mapped[str] = mapped_column(Text, nullable=False)
    activity_span_years: Mapped[int] = mapped_column(Integer, nullable=False)
    revival_count: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_category: Mapped[str] = mapped_column(String(512), nullable=False)
    problem_keywords: Mapped[str] = mapped_column(Text, nullable=False)
    cross_gen_signals: Mapped[str] = mapped_column(Text, nullable=False)
    noise_flags: Mapped[str] = mapped_column(Text, nullable=False)
    run: Mapped["Phase1ExportRun"] = relationship(back_populates="threads")


class Phase1ExportCategory(Base):
    __tablename__ = "phase1_export_category"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("phase1_export_run.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(512), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_score: Mapped[float] = mapped_column(Float, nullable=False)
    median_score: Mapped[float] = mapped_column(Float, nullable=False)
    run: Mapped["Phase1ExportRun"] = relationship(back_populates="category_rows")


class Phase1ExportKeywordHit(Base):
    __tablename__ = "phase1_export_keyword_hit"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("phase1_export_run.id", ondelete="CASCADE"), nullable=False
    )
    keyword: Mapped[str] = mapped_column(String(256), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    run: Mapped["Phase1ExportRun"] = relationship(back_populates="keyword_hits")


class Phase1ExportCrossgenHit(Base):
    __tablename__ = "phase1_export_crossgen_hit"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("phase1_export_run.id", ondelete="CASCADE"), nullable=False
    )
    signal: Mapped[str] = mapped_column(String(256), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    run: Mapped["Phase1ExportRun"] = relationship(back_populates="crossgen_hits")
