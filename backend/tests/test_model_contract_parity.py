"""Keep the SQLAlchemy model and the Pydantic contract in step.

Two hand-written definitions of the complaint exist, and that is deliberate:
Pydantic owns validation and the wire format, SQLAlchemy owns storage and
relationships. Neither is a good fit for the other's job.

What is *not* acceptable is for them to drift. A field added to the schema but
not the model fails at runtime with a database error; a field added to the model
but not the schema is invisible to the API and quietly unreachable. This module
fails the build instead.
"""

from sqlalchemy import inspect

from app.models.complaint import Complaint
from app.schemas.complaint import ComplaintBase, ComplaintRead, ComplaintUpdate

# Present on the model only, with a reason for each.
MODEL_ONLY: frozenset[str] = frozenset(
    {
        "id",
        "reference_code",
        "status",
        "created_at",
        "updated_at",
        "created_by_id",
        "closed_at",
        # Foreign keys. The API exchanges human-readable names; resolving them to
        # ids is the server's job, because AI extraction routinely produces a
        # customer or product that matches no existing row.
        "customer_id",
        "product_id",
        "batch_id",
    }
)

# Present on the schema only.
SCHEMA_ONLY: frozenset[str] = frozenset(
    {
        # Computed from due_date and status rather than stored - a stored flag
        # would need a scheduled job to stay truthful.
        "is_overdue",
    }
)


def _model_columns() -> set[str]:
    return {c.key for c in inspect(Complaint).mapper.column_attrs}


def test_every_schema_field_has_a_column() -> None:
    """A schema field with no column fails at write time, in production."""
    missing = set(ComplaintBase.model_fields) - _model_columns() - SCHEMA_ONLY
    assert not missing, (
        f"ComplaintBase declares fields the Complaint model cannot store: "
        f"{sorted(missing)}. Add the column or document it in SCHEMA_ONLY."
    )


def test_every_column_is_exposed_by_the_schema() -> None:
    """A column no schema exposes is unreachable through the API."""
    exposed = set(ComplaintBase.model_fields) | set(ComplaintRead.model_fields)
    orphaned = _model_columns() - exposed - MODEL_ONLY
    assert not orphaned, (
        f"Complaint model has columns no schema exposes: {sorted(orphaned)}. "
        f"Add them to ComplaintBase or document them in MODEL_ONLY."
    )


def test_update_schema_covers_every_editable_field() -> None:
    """ComplaintUpdate is what the AI edit tool emits. A field it cannot express
    is a field natural-language editing silently cannot reach."""
    editable = set(ComplaintBase.model_fields) - SCHEMA_ONLY
    missing = editable - set(ComplaintUpdate.model_fields)
    assert not missing, (
        f"ComplaintUpdate cannot express: {sorted(missing)}. "
        f"AI edits would be unable to change these fields."
    )


def test_update_schema_adds_nothing_unexpected() -> None:
    extra = set(ComplaintUpdate.model_fields) - set(ComplaintBase.model_fields)
    assert not extra, f"ComplaintUpdate declares unknown fields: {sorted(extra)}"


def test_documented_exception_lists_stay_accurate() -> None:
    """If a documented exception no longer exists, the list is stale and the
    tests above are weaker than they look."""
    columns = _model_columns()
    stale = {name for name in MODEL_ONLY if name not in columns}
    assert not stale, f"MODEL_ONLY names columns that no longer exist: {sorted(stale)}"

    schema_fields = set(ComplaintBase.model_fields) | set(ComplaintRead.model_fields)
    stale_schema = {name for name in SCHEMA_ONLY if name not in schema_fields}
    assert not stale_schema, (
        f"SCHEMA_ONLY names fields that no longer exist: {sorted(stale_schema)}"
    )
