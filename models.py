"""
Database models for Issue #1: Register a Camper.

A "model" is a Python class that matches a database table. Each attribute
below becomes a column. SQLAlchemy turns Python code like Camper(...) into
the right SQL for SQLite (on your computer) or PostgreSQL (Supabase).

Tables:
  guardians - the parent or guardian's contact information
  campers   - each camper, linked to one guardian by guardian_id

This matches the class diagram, where a parent/guardian (User) manages
zero or more Campers.
"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

# One shared database object. app.py connects it to the Flask app.
db = SQLAlchemy()

# Longest values we accept. registration.py uses these to validate the form,
# so the form rules and the column sizes can never disagree.
NAME_MAX_LENGTH = 50
GUARDIAN_NAME_MAX_LENGTH = 100
EMAIL_MAX_LENGTH = 254  # the longest a real email address can be
PHONE_LENGTH = 12       # phone numbers are saved as +1 and 10 digits, e.g. +14105550123


class Guardian(db.Model):
    """A parent or guardian and how to contact them."""

    __tablename__ = "guardians"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(GUARDIAN_NAME_MAX_LENGTH))
    email: Mapped[str] = mapped_column(String(EMAIL_MAX_LENGTH))
    phone: Mapped[str] = mapped_column(String(PHONE_LENGTH))
    # The database fills these in automatically.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    campers: Mapped[list["Camper"]] = relationship(back_populates="guardian")


class Camper(db.Model):
    """A child attending camp. Each camper belongs to one guardian."""

    __tablename__ = "campers"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    last_name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    guardian_id: Mapped[int] = mapped_column(ForeignKey("guardians.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    guardian: Mapped[Guardian] = relationship(back_populates="campers")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
