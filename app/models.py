"""SQLAlchemy models for projects, verifications, keys, logs, and blobs."""

from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint, and_, or_

from app.extensions import db


def utcnow():
    """Return a naive UTC timestamp for SQLite storage.

    Returns:
        datetime: Current UTC time without tzinfo.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def reset_database():
    """Drop and recreate every table, erasing all stored data."""
    db.session.remove()
    db.drop_all()
    db.create_all()


class Project(db.Model):
    """Top-level project that groups verification schemes."""

    __tablename__ = "project"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(80), nullable=False, unique=True, index=True)
    description = db.Column(db.Text, nullable=False, default="")
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    verifications = db.relationship(
        "Verification",
        backref="project",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    blobs = db.relationship(
        "BlobObject",
        backref="project",
        cascade="all, delete-orphan",
        lazy="dynamic",
        foreign_keys="BlobObject.project_id",
    )


class Verification(db.Model):
    """Verification scheme that owns keys, replies, and check rules."""

    __tablename__ = "verification"
    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_verification_project_slug"),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("project.id"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(80), nullable=False, index=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    bind_hwid = db.Column(db.Boolean, nullable=False, default=False)
    default_ttl_seconds = db.Column(db.Integer, nullable=True)
    default_max_uses = db.Column(db.Integer, nullable=True)
    default_valid_from = db.Column(db.DateTime, nullable=True)
    default_valid_until = db.Column(db.DateTime, nullable=True)
    config_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    keys = db.relationship(
        "LicenseKey",
        backref="verification",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    batches = db.relationship(
        "KeyBatch",
        backref="verification",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    logs = db.relationship(
        "VerifyLog",
        backref="verification",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )
    blobs = db.relationship(
        "BlobObject",
        backref="verification",
        cascade="all, delete-orphan",
        lazy="dynamic",
        foreign_keys="BlobObject.verification_id",
    )


class KeyBatch(db.Model):
    """Snapshot of a bulk key issuance request."""

    __tablename__ = "key_batch"

    id = db.Column(db.Integer, primary_key=True)
    verification_id = db.Column(
        db.Integer,
        db.ForeignKey("verification.id"),
        nullable=False,
        index=True,
    )
    count = db.Column(db.Integer, nullable=False)
    prefix = db.Column(db.String(32), nullable=False, default="")
    key_length = db.Column(db.Integer, nullable=False)
    charset = db.Column(db.String(128), nullable=False)
    ttl_seconds = db.Column(db.Integer, nullable=True)
    max_uses = db.Column(db.Integer, nullable=True)
    valid_from = db.Column(db.DateTime, nullable=True)
    valid_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    keys = db.relationship("LicenseKey", backref="batch", lazy="dynamic")


class LicenseKey(db.Model):
    """A distributable license key bound to one verification scheme."""

    __tablename__ = "license_key"
    __table_args__ = (
        UniqueConstraint(
            "verification_id",
            "key_code",
            name="uq_license_key_verification_code",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    verification_id = db.Column(
        db.Integer,
        db.ForeignKey("verification.id"),
        nullable=False,
        index=True,
    )
    batch_id = db.Column(
        db.Integer,
        db.ForeignKey("key_batch.id"),
        nullable=True,
        index=True,
    )
    key_code = db.Column(db.String(128), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="active")
    ttl_seconds = db.Column(db.Integer, nullable=True)
    max_uses = db.Column(db.Integer, nullable=True)
    used_count = db.Column(db.Integer, nullable=False, default=0)
    valid_from = db.Column(db.DateTime, nullable=True)
    valid_until = db.Column(db.DateTime, nullable=True)
    first_used_at = db.Column(db.DateTime, nullable=True)
    hwid = db.Column(db.String(128), nullable=True)
    note = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class VerifyLog(db.Model):
    """One public verify API invocation used by the dashboard."""

    __tablename__ = "verify_log"

    id = db.Column(db.Integer, primary_key=True)
    verification_id = db.Column(
        db.Integer,
        db.ForeignKey("verification.id"),
        nullable=True,
        index=True,
    )
    key_id = db.Column(
        db.Integer,
        db.ForeignKey("license_key.id"),
        nullable=True,
        index=True,
    )
    key_code = db.Column(db.String(128), nullable=False, default="")
    result = db.Column(db.String(32), nullable=False, index=True)
    hwid = db.Column(db.String(128), nullable=True)
    ip = db.Column(db.String(64), nullable=False, default="")
    user_agent = db.Column(db.String(255), nullable=False, default="")
    duration_ms = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)


class BlobObject(db.Model):
    """Small binary object stored in SQLite and optionally referenced in replies."""

    __tablename__ = "blob_object"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    content_type = db.Column(db.String(120), nullable=False, default="application/octet-stream")
    size = db.Column(db.Integer, nullable=False, default=0)
    data = db.Column(db.LargeBinary, nullable=False)
    project_id = db.Column(
        db.Integer,
        db.ForeignKey("project.id"),
        nullable=True,
        index=True,
    )
    verification_id = db.Column(
        db.Integer,
        db.ForeignKey("verification.id"),
        nullable=True,
        index=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def available_to(self, verification):
        """Return whether this blob may be served for a verification scheme.

        Global blobs (no project or scheme) are visible everywhere. Project
        blobs apply to every scheme in that project. Scheme blobs apply only
        to that scheme.

        Args:
            verification: Verification scheme requesting the blob.

        Returns:
            bool: True when the blob is in scope.
        """
        if verification is None:
            return False
        if self.verification_id is not None:
            return self.verification_id == verification.id
        if self.project_id is not None:
            return self.project_id == verification.project_id
        return True

    @classmethod
    def visible_for(cls, verification):
        """List blobs a scheme can reference, most specific name winning.

        Args:
            verification: Current verification scheme.

        Returns:
            list: BlobObject rows ordered by name.
        """
        rows = (
            cls.query.filter(
                or_(
                    cls.verification_id == verification.id,
                    and_(
                        cls.project_id == verification.project_id,
                        cls.verification_id.is_(None),
                    ),
                    and_(
                        cls.project_id.is_(None),
                        cls.verification_id.is_(None),
                    ),
                )
            )
            .all()
        )

        def specificity(blob):
            if blob.verification_id is not None:
                return 0
            if blob.project_id is not None:
                return 1
            return 2

        rows.sort(key=lambda blob: (specificity(blob), blob.name.lower()))
        seen = set()
        unique = []
        for blob in rows:
            if blob.name in seen:
                continue
            seen.add(blob.name)
            unique.append(blob)
        unique.sort(key=lambda blob: blob.name.lower())
        return unique


class AdminAccount(db.Model):
    """Single administrator account created on first visit."""

    __tablename__ = "admin_account"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
