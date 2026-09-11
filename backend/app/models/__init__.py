"""All ORM models.

Imported here so that `Base.metadata` is fully populated by the time Alembic or
`create_all` runs. A model that is never imported is invisible to both, which
produces the confusing failure of a migration that silently omits a table.
"""

from app.models.audit import AuditEntry
from app.models.base import Base, TimestampMixin, utcnow
from app.models.complaint import AIAssessmentRecord, Complaint, ComplaintDocument
from app.models.investigation import CAPA, Investigation, RootCause, StatusTransition
from app.models.reference import Batch, Customer, Product
from app.models.user import User

__all__ = [
    "CAPA",
    "AIAssessmentRecord",
    "AuditEntry",
    "Base",
    "Batch",
    "Complaint",
    "ComplaintDocument",
    "Customer",
    "Investigation",
    "Product",
    "RootCause",
    "StatusTransition",
    "TimestampMixin",
    "User",
    "utcnow",
]
