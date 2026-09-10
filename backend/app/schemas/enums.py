"""Canonical domain vocabulary for the CCMS.

This module is the root of the project's single source of truth. Every enum here
flows outward in three directions and is never redefined along the way:

    enums.py ──┬─> SQLAlchemy columns      (app/models/)
               ├─> Pydantic request/response schemas (app/schemas/)
               │      └─> FastAPI OpenAPI spec
               │            └─> frontend/src/types/api.ts  (GENERATED)
               └─> LangGraph structured-output schemas (app/ai/tools/)

Because the AI extraction tools bind to these same enums, the model physically
cannot return a status or severity the database will reject.

Terminology follows pharmaceutical QMS convention (ICH Q10, 21 CFR 211.198).
"""

from enum import StrEnum


class UserRole(StrEnum):
    """Access roles. Ordering here is not privilege ordering - see core.rbac."""

    ADMIN = "admin"
    QA_MANAGER = "qa_manager"
    COMPLAINT_OFFICER = "complaint_officer"
    INVESTIGATOR = "investigator"
    VIEWER = "viewer"


class ComplaintStatus(StrEnum):
    """The complaint lifecycle.

    Legal transitions are defined once in services/workflow.py; this enum only
    names the states.
    """

    NEW = "new"
    UNDER_REVIEW = "under_review"
    INVESTIGATION = "investigation"
    ROOT_CAUSE_IDENTIFIED = "root_cause_identified"
    CAPA_REQUIRED = "capa_required"
    QA_REVIEW = "qa_review"
    CLOSED = "closed"


class Severity(StrEnum):
    """Complaint severity, per standard pharmaceutical quality classification.

    CRITICAL - may cause death or serious adverse health consequence; candidate
               for recall and regulatory field alert.
    MAJOR    - may cause temporary or medically reversible harm, or is a
               significant GMP/specification failure.
    MINOR    - cosmetic or administrative; no expected health consequence.
    """

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class Priority(StrEnum):
    """Handling urgency. Distinct from severity: a MINOR complaint from a key
    account under regulatory scrutiny can still be HIGH priority."""

    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ComplaintSource(StrEnum):
    """How the complaint reached us. Drives regulatory reporting obligations."""

    EMAIL = "email"
    PHONE = "phone"
    CUSTOMER_PORTAL = "customer_portal"
    SALES_REPRESENTATIVE = "sales_representative"
    DISTRIBUTOR = "distributor"
    HOSPITAL_PHARMACY = "hospital_pharmacy"
    RETAIL_PHARMACY = "retail_pharmacy"
    REGULATORY_AUTHORITY = "regulatory_authority"
    FIELD_ALERT = "field_alert"
    WRITTEN_LETTER = "written_letter"
    OTHER = "other"


class ComplaintType(StrEnum):
    """Pharmaceutical product complaint categories.

    These map to the defect families a QA team actually triages against; the AI
    classifier is constrained to this list so it cannot invent a category.
    """

    APPEARANCE_DISCOLORATION = "appearance_discoloration"
    FOREIGN_MATTER = "foreign_matter"
    CONTAMINATION_MICROBIAL = "contamination_microbial"
    CONTAMINATION_CROSS = "contamination_cross"
    PACKAGING_DEFECT = "packaging_defect"
    LABELING_ERROR = "labeling_error"
    PHYSICAL_DAMAGE = "physical_damage"
    BROKEN_OR_CHIPPED = "broken_or_chipped"
    ODOR_OR_TASTE = "odor_or_taste"
    DISSOLUTION_FAILURE = "dissolution_failure"
    ASSAY_OUT_OF_SPECIFICATION = "assay_out_of_specification"
    STABILITY_DEFECT = "stability_defect"
    EFFICACY_COMPLAINT = "efficacy_complaint"
    ADVERSE_EVENT = "adverse_event"
    SHORT_COUNT_OR_FILL = "short_count_or_fill"
    TAMPER_EVIDENCE = "tamper_evidence"
    DEVICE_MALFUNCTION = "device_malfunction"
    OTHER = "other"


class DosageForm(StrEnum):
    """Physical form of the finished drug product (FDF)."""

    TABLET = "tablet"
    CAPSULE = "capsule"
    INJECTION = "injection"
    SYRUP = "syrup"
    SUSPENSION = "suspension"
    CREAM = "cream"
    OINTMENT = "ointment"
    GEL = "gel"
    DROPS = "drops"
    INHALER = "inhaler"
    POWDER = "powder"
    SACHET = "sachet"
    SUPPOSITORY = "suppository"
    PATCH = "patch"
    OTHER = "other"


class QuantityUnit(StrEnum):
    """Unit for the affected quantity. The reference UI defaults to KG for API
    material; finished dose forms use countable units."""

    TABLETS = "tablets"
    CAPSULES = "capsules"
    VIALS = "vials"
    AMPOULES = "ampoules"
    BOTTLES = "bottles"
    BLISTERS = "blisters"
    SACHETS = "sachets"
    TUBES = "tubes"
    BOXES = "boxes"
    CARTONS = "cartons"
    UNITS = "units"
    KG = "kg"
    G = "g"
    MG = "mg"
    L = "l"
    ML = "ml"


class DocumentKind(StrEnum):
    """Uploaded evidence types the extraction pipeline accepts."""

    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    EML = "eml"
    PNG = "png"
    JPG = "jpg"


class AIConfidence(StrEnum):
    """How sure the extractor is about a populated field. Surfaced in the UI so a
    reviewer knows what to double-check - AI output is a recommendation, never a
    confirmed regulatory determination."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AuditAction(StrEnum):
    """Audit trail verbs. Written automatically by SQLAlchemy event listeners."""

    CREATED = "created"
    UPDATED = "updated"
    STATUS_CHANGED = "status_changed"
    DELETED = "deleted"
    DOCUMENT_UPLOADED = "document_uploaded"
    AI_EXTRACTION = "ai_extraction"
    AI_ASSESSMENT = "ai_assessment"
    ASSIGNED = "assigned"
    LOGIN = "login"
