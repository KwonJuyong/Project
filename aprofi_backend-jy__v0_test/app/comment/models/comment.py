from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base

class Comment(Base):
    __tablename__ = "comment"

    comment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    is_problem_comment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    problem_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("problem.problem_id"), nullable=True)

    is_submission_comment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submission_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("submissions.submission_id"), nullable=True)

    maker_id: Mapped[str] = mapped_column(String, ForeignKey("user.user_id"), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    latest_edit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_edited_at: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
