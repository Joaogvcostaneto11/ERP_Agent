from typing import Optional

from sqlalchemy.orm import Session

from db.models import AuditLogDB


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        user_id: str,
        action: str,
        entity_type: str,
        entity_id: str,
        rule_applied: Optional[str] = None,
        rule_version: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Append-only. Audit records are never updated or deleted."""
        entry = AuditLogDB(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            rule_applied=rule_applied,
            rule_version=rule_version,
            details=details,
        )
        self.db.add(entry)
        self.db.flush()
