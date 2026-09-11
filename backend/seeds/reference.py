"""Reference data for the demo: customers, products and manufactured lots.

A complaint is only interesting when it points at something. This module builds
the world the Phase 2 complaint seeds hang off - a portfolio of finished dose
forms, the customers who bought them and the lots those customers received - so
that the cross-complaint queries that matter ("every complaint against lot
AZG-41866") have real material to work on.

Two deliberate choices:

* **Dates are relative to today.** Every manufacturing and expiry date is
  derived from ``date.today()``. A demo run six months from now still shows
  in-date stock and complaints raised against live lots, rather than a portfolio
  that quietly expired.
* **Lot codes carry no date.** The house format is a three-letter product
  mnemonic plus the plant's sequential lot counter (``AZG-41866``). Encoding the
  manufacturing month in the code - the more common real-world convention -
  would go stale the moment the relative dates rolled and would then silently
  contradict the ``manufacturing_date`` column.

Idempotent in the same way as ``seeds/users.py``: customers match on ``name``,
products on ``product_code`` and batches on ``(product_id, batch_number)``, so
``python -m seeds.run`` is safe to repeat. One commit at the end.

The manufacturer, every customer and every brand name here are invented.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reference import Batch, Customer, Product
from app.schemas.enums import ComplaintSource, DosageForm, QuantityUnit

# The three plants the demo company runs. Kept as a named constant set so a
# batch can never be attributed to a site that does not exist.
SITE_VAPI = "Unit I - Vapi, Gujarat"
SITE_BADDI = "Unit II - Baddi, Himachal Pradesh"
SITE_HYDERABAD = "Unit III - Hyderabad, Telangana"

# Shelf lives expressed in days rather than months so the arithmetic stays
# exact against date.today() with no calendar helper. 730 / 913 / 1095 days are
# the 24 / 30 / 36 month registered shelf lives used across this portfolio.
SHELF_LIFE_24_MONTHS = 730
SHELF_LIFE_30_MONTHS = 913
SHELF_LIFE_36_MONTHS = 1095


@dataclass(frozen=True)
class CustomerSpec:
    """A customer as demo content, independent of the ORM."""

    name: str
    customer_type: ComplaintSource
    contact_email: str | None
    contact_phone: str | None
    city: str
    country: str


@dataclass(frozen=True)
class ProductSpec:
    """A marketed finished dose form."""

    name: str
    generic_name: str
    strength: str
    dosage_form: DosageForm
    product_code: str
    therapeutic_category: str


@dataclass(frozen=True)
class BatchSpec:
    """A manufactured lot, positioned in time relative to today."""

    product_code: str
    batch_number: str
    manufactured_days_ago: int
    shelf_life_days: int
    quantity_produced: float
    quantity_unit: QuantityUnit
    manufacturing_site: str
    units_released: int


CUSTOMERS: list[CustomerSpec] = [
    CustomerSpec(
        name="Sunrise Multispeciality Hospital Pharmacy",
        customer_type=ComplaintSource.HOSPITAL_PHARMACY,
        contact_email="qa.pharmacy@sunrisemultispeciality.in",
        contact_phone="+91 20 6644 8120",
        city="Pune",
        country="India",
    ),
    CustomerSpec(
        name="Ashwin Institute of Medical Sciences Pharmacy",
        customer_type=ComplaintSource.HOSPITAL_PHARMACY,
        contact_email="pharmacy@ashwinmedsciences.in",
        contact_phone="+91 44 2815 7740",
        city="Chennai",
        country="India",
    ),
    CustomerSpec(
        name="St. Clare Mission Hospital Pharmacy",
        customer_type=ComplaintSource.HOSPITAL_PHARMACY,
        contact_email="pharmacy@stclaremission-hospital.org",
        contact_phone="+233 30 276 1188",
        city="Accra",
        country="Ghana",
    ),
    CustomerSpec(
        name="Arogya Chemists & Druggists",
        customer_type=ComplaintSource.RETAIL_PHARMACY,
        contact_email="store@arogyachemists.in",
        contact_phone="+91 79 4002 6611",
        city="Ahmedabad",
        country="India",
    ),
    CustomerSpec(
        name="WellSpring Pharmacy Chain",
        customer_type=ComplaintSource.RETAIL_PHARMACY,
        contact_email="quality@wellspringpharmacy.in",
        contact_phone="+91 484 273 9050",
        city="Kochi",
        country="India",
    ),
    CustomerSpec(
        name="Deccan Healthcare Distributors Pvt Ltd",
        customer_type=ComplaintSource.DISTRIBUTOR,
        contact_email="qa@deccanhealthcaredist.in",
        contact_phone="+91 40 2789 4412",
        city="Hyderabad",
        country="India",
    ),
    CustomerSpec(
        name="Trans-Gulf Medical Supplies FZ-LLC",
        customer_type=ComplaintSource.DISTRIBUTOR,
        contact_email="quality@transgulfmedical.ae",
        contact_phone="+971 4 883 2270",
        city="Dubai",
        country="United Arab Emirates",
    ),
    CustomerSpec(
        name="Continental Drug Wholesalers Ltd",
        customer_type=ComplaintSource.DISTRIBUTOR,
        contact_email="qc@continentaldrugwholesalers.ng",
        contact_phone="+234 1 460 7731",
        city="Lagos",
        country="Nigeria",
    ),
    CustomerSpec(
        name="Andes Pharma Distribuidora S.A.",
        customer_type=ComplaintSource.DISTRIBUTOR,
        contact_email="calidad@andespharmadist.pe",
        contact_phone="+51 1 611 4408",
        city="Lima",
        country="Peru",
    ),
    CustomerSpec(
        name="State Drug Control Bureau (Western Zone)",
        customer_type=ComplaintSource.REGULATORY_AUTHORITY,
        contact_email="wz.complaints@sdcb-westernzone.in",
        contact_phone="+91 265 242 9014",
        city="Vadodara",
        country="India",
    ),
]

PRODUCTS: list[ProductSpec] = [
    ProductSpec(
        name="Azigen 500",
        generic_name="Azithromycin",
        strength="500 mg",
        dosage_form=DosageForm.TABLET,
        product_code="PHC-TAB-1001",
        therapeutic_category="Anti-infective - macrolide antibiotic",
    ),
    ProductSpec(
        name="Metfosure 850",
        generic_name="Metformin Hydrochloride",
        strength="850 mg",
        dosage_form=DosageForm.TABLET,
        product_code="PHC-TAB-1002",
        therapeutic_category="Antidiabetic - biguanide",
    ),
    ProductSpec(
        name="Amlovas 5",
        generic_name="Amlodipine Besylate",
        strength="5 mg",
        dosage_form=DosageForm.TABLET,
        product_code="PHC-TAB-1003",
        therapeutic_category="Cardiovascular - calcium channel blocker",
    ),
    ProductSpec(
        name="Pantorex 40",
        generic_name="Pantoprazole Sodium",
        strength="40 mg",
        dosage_form=DosageForm.TABLET,
        product_code="PHC-TAB-1004",
        therapeutic_category="Gastrointestinal - proton pump inhibitor",
    ),
    ProductSpec(
        name="Omecap 20",
        generic_name="Omeprazole",
        strength="20 mg",
        dosage_form=DosageForm.CAPSULE,
        product_code="PHC-CAP-2001",
        therapeutic_category="Gastrointestinal - proton pump inhibitor",
    ),
    ProductSpec(
        name="Fluconzo 150",
        generic_name="Fluconazole",
        strength="150 mg",
        dosage_form=DosageForm.CAPSULE,
        product_code="PHC-CAP-2002",
        therapeutic_category="Antifungal - triazole",
    ),
    ProductSpec(
        name="Ceftrizen 1 g",
        generic_name="Ceftriaxone Sodium",
        strength="1 g",
        dosage_form=DosageForm.INJECTION,
        product_code="PHC-INJ-3001",
        therapeutic_category="Anti-infective - third generation cephalosporin",
    ),
    ProductSpec(
        name="Ondaset Injection",
        generic_name="Ondansetron Hydrochloride",
        strength="2 mg/mL",
        dosage_form=DosageForm.INJECTION,
        product_code="PHC-INJ-3002",
        therapeutic_category="Antiemetic - 5-HT3 receptor antagonist",
    ),
    ProductSpec(
        name="Paracip Kids Syrup",
        generic_name="Paracetamol",
        strength="125 mg/5 mL",
        dosage_form=DosageForm.SYRUP,
        product_code="PHC-SYR-4001",
        therapeutic_category="Analgesic and antipyretic",
    ),
    ProductSpec(
        name="Ibucalm 100 Suspension",
        generic_name="Ibuprofen",
        strength="100 mg/5 mL",
        dosage_form=DosageForm.SUSPENSION,
        product_code="PHC-SUS-4002",
        therapeutic_category="Analgesic - non-steroidal anti-inflammatory",
    ),
    ProductSpec(
        name="Clotrizen Cream 1%",
        generic_name="Clotrimazole",
        strength="1% w/w",
        dosage_form=DosageForm.CREAM,
        product_code="PHC-CRM-5001",
        therapeutic_category="Dermatology - topical antifungal",
    ),
    ProductSpec(
        name="Moxivis Eye Drops",
        generic_name="Moxifloxacin Hydrochloride",
        strength="0.5% w/v",
        dosage_form=DosageForm.DROPS,
        product_code="PHC-DRP-6001",
        therapeutic_category="Ophthalmic anti-infective - fluoroquinolone",
    ),
]

BATCHES: list[BatchSpec] = [
    # Azigen 500 - AZG-41866 is the lot the clustered complaints point at.
    BatchSpec(
        product_code="PHC-TAB-1001",
        batch_number="AZG-40712",
        manufactured_days_ago=400,
        shelf_life_days=SHELF_LIFE_36_MONTHS,
        quantity_produced=1_240_000.0,
        quantity_unit=QuantityUnit.TABLETS,
        manufacturing_site=SITE_VAPI,
        units_released=1_228_400,
    ),
    BatchSpec(
        product_code="PHC-TAB-1001",
        batch_number="AZG-41866",
        manufactured_days_ago=250,
        shelf_life_days=SHELF_LIFE_36_MONTHS,
        quantity_produced=1_180_000.0,
        quantity_unit=QuantityUnit.TABLETS,
        manufacturing_site=SITE_VAPI,
        units_released=1_166_500,
    ),
    BatchSpec(
        product_code="PHC-TAB-1001",
        batch_number="AZG-42931",
        manufactured_days_ago=95,
        shelf_life_days=SHELF_LIFE_36_MONTHS,
        quantity_produced=1_310_000.0,
        quantity_unit=QuantityUnit.TABLETS,
        manufacturing_site=SITE_VAPI,
        units_released=1_297_800,
    ),
    # Metfosure 850
    BatchSpec(
        product_code="PHC-TAB-1002",
        batch_number="MFS-31204",
        manufactured_days_ago=470,
        shelf_life_days=SHELF_LIFE_36_MONTHS,
        quantity_produced=2_050_000.0,
        quantity_unit=QuantityUnit.TABLETS,
        manufacturing_site=SITE_BADDI,
        units_released=2_031_600,
    ),
    BatchSpec(
        product_code="PHC-TAB-1002",
        batch_number="MFS-32117",
        manufactured_days_ago=215,
        shelf_life_days=SHELF_LIFE_36_MONTHS,
        quantity_produced=1_960_000.0,
        quantity_unit=QuantityUnit.TABLETS,
        manufacturing_site=SITE_BADDI,
        units_released=1_944_200,
    ),
    # Amlovas 5
    BatchSpec(
        product_code="PHC-TAB-1003",
        batch_number="AMV-28450",
        manufactured_days_ago=505,
        shelf_life_days=SHELF_LIFE_36_MONTHS,
        quantity_produced=1_520_000.0,
        quantity_unit=QuantityUnit.TABLETS,
        manufacturing_site=SITE_BADDI,
        units_released=1_508_900,
    ),
    BatchSpec(
        product_code="PHC-TAB-1003",
        batch_number="AMV-29306",
        manufactured_days_ago=300,
        shelf_life_days=SHELF_LIFE_36_MONTHS,
        quantity_produced=1_475_000.0,
        quantity_unit=QuantityUnit.TABLETS,
        manufacturing_site=SITE_BADDI,
        units_released=1_461_300,
    ),
    # Pantorex 40
    BatchSpec(
        product_code="PHC-TAB-1004",
        batch_number="PTX-55023",
        manufactured_days_ago=365,
        shelf_life_days=SHELF_LIFE_30_MONTHS,
        quantity_produced=880_000.0,
        quantity_unit=QuantityUnit.TABLETS,
        manufacturing_site=SITE_VAPI,
        units_released=871_200,
    ),
    BatchSpec(
        product_code="PHC-TAB-1004",
        batch_number="PTX-56190",
        manufactured_days_ago=160,
        shelf_life_days=SHELF_LIFE_30_MONTHS,
        quantity_produced=925_000.0,
        quantity_unit=QuantityUnit.TABLETS,
        manufacturing_site=SITE_VAPI,
        units_released=914_700,
    ),
    # Omecap 20
    BatchSpec(
        product_code="PHC-CAP-2001",
        batch_number="OMC-61840",
        manufactured_days_ago=430,
        shelf_life_days=SHELF_LIFE_30_MONTHS,
        quantity_produced=760_000.0,
        quantity_unit=QuantityUnit.CAPSULES,
        manufacturing_site=SITE_VAPI,
        units_released=751_400,
    ),
    BatchSpec(
        product_code="PHC-CAP-2001",
        batch_number="OMC-62755",
        manufactured_days_ago=190,
        shelf_life_days=SHELF_LIFE_30_MONTHS,
        quantity_produced=812_000.0,
        quantity_unit=QuantityUnit.CAPSULES,
        manufacturing_site=SITE_VAPI,
        units_released=803_600,
    ),
    # Fluconzo 150
    BatchSpec(
        product_code="PHC-CAP-2002",
        batch_number="FLZ-17902",
        manufactured_days_ago=520,
        shelf_life_days=SHELF_LIFE_36_MONTHS,
        quantity_produced=430_000.0,
        quantity_unit=QuantityUnit.CAPSULES,
        manufacturing_site=SITE_BADDI,
        units_released=424_100,
    ),
    BatchSpec(
        product_code="PHC-CAP-2002",
        batch_number="FLZ-18644",
        manufactured_days_ago=245,
        shelf_life_days=SHELF_LIFE_36_MONTHS,
        quantity_produced=465_000.0,
        quantity_unit=QuantityUnit.CAPSULES,
        manufacturing_site=SITE_BADDI,
        units_released=459_800,
    ),
    # Ceftrizen 1 g
    BatchSpec(
        product_code="PHC-INJ-3001",
        batch_number="CFZ-70311",
        manufactured_days_ago=390,
        shelf_life_days=SHELF_LIFE_24_MONTHS,
        quantity_produced=182_000.0,
        quantity_unit=QuantityUnit.VIALS,
        manufacturing_site=SITE_HYDERABAD,
        units_released=178_600,
    ),
    BatchSpec(
        product_code="PHC-INJ-3001",
        batch_number="CFZ-71208",
        manufactured_days_ago=205,
        shelf_life_days=SHELF_LIFE_24_MONTHS,
        quantity_produced=196_500.0,
        quantity_unit=QuantityUnit.VIALS,
        manufacturing_site=SITE_HYDERABAD,
        units_released=192_900,
    ),
    BatchSpec(
        product_code="PHC-INJ-3001",
        batch_number="CFZ-72104",
        manufactured_days_ago=80,
        shelf_life_days=SHELF_LIFE_24_MONTHS,
        quantity_produced=171_000.0,
        quantity_unit=QuantityUnit.VIALS,
        manufacturing_site=SITE_HYDERABAD,
        units_released=167_800,
    ),
    # Ondaset Injection
    BatchSpec(
        product_code="PHC-INJ-3002",
        batch_number="ODS-83417",
        manufactured_days_ago=330,
        shelf_life_days=SHELF_LIFE_24_MONTHS,
        quantity_produced=248_000.0,
        quantity_unit=QuantityUnit.AMPOULES,
        manufacturing_site=SITE_HYDERABAD,
        units_released=243_500,
    ),
    BatchSpec(
        product_code="PHC-INJ-3002",
        batch_number="ODS-84260",
        manufactured_days_ago=140,
        shelf_life_days=SHELF_LIFE_24_MONTHS,
        quantity_produced=262_000.0,
        quantity_unit=QuantityUnit.AMPOULES,
        manufacturing_site=SITE_HYDERABAD,
        units_released=257_100,
    ),
    # Paracip Kids Syrup
    BatchSpec(
        product_code="PHC-SYR-4001",
        batch_number="PCP-90562",
        manufactured_days_ago=410,
        shelf_life_days=SHELF_LIFE_24_MONTHS,
        quantity_produced=96_000.0,
        quantity_unit=QuantityUnit.BOTTLES,
        manufacturing_site=SITE_VAPI,
        units_released=94_300,
    ),
    BatchSpec(
        product_code="PHC-SYR-4001",
        batch_number="PCP-91478",
        manufactured_days_ago=175,
        shelf_life_days=SHELF_LIFE_24_MONTHS,
        quantity_produced=104_500.0,
        quantity_unit=QuantityUnit.BOTTLES,
        manufacturing_site=SITE_VAPI,
        units_released=102_900,
    ),
    # Ibucalm 100 Suspension
    BatchSpec(
        product_code="PHC-SUS-4002",
        batch_number="IBC-12037",
        manufactured_days_ago=285,
        shelf_life_days=SHELF_LIFE_24_MONTHS,
        quantity_produced=71_500.0,
        quantity_unit=QuantityUnit.BOTTLES,
        manufacturing_site=SITE_VAPI,
        units_released=70_200,
    ),
    BatchSpec(
        product_code="PHC-SUS-4002",
        batch_number="IBC-12885",
        manufactured_days_ago=110,
        shelf_life_days=SHELF_LIFE_24_MONTHS,
        quantity_produced=68_000.0,
        quantity_unit=QuantityUnit.BOTTLES,
        manufacturing_site=SITE_VAPI,
        units_released=66_900,
    ),
    # Clotrizen Cream 1%
    BatchSpec(
        product_code="PHC-CRM-5001",
        batch_number="CLZ-46229",
        manufactured_days_ago=455,
        shelf_life_days=SHELF_LIFE_30_MONTHS,
        quantity_produced=138_000.0,
        quantity_unit=QuantityUnit.TUBES,
        manufacturing_site=SITE_BADDI,
        units_released=135_700,
    ),
    BatchSpec(
        product_code="PHC-CRM-5001",
        batch_number="CLZ-47104",
        manufactured_days_ago=165,
        shelf_life_days=SHELF_LIFE_30_MONTHS,
        quantity_produced=142_500.0,
        quantity_unit=QuantityUnit.TUBES,
        manufacturing_site=SITE_BADDI,
        units_released=140_100,
    ),
    # Moxivis Eye Drops
    BatchSpec(
        product_code="PHC-DRP-6001",
        batch_number="MXV-53718",
        manufactured_days_ago=310,
        shelf_life_days=SHELF_LIFE_24_MONTHS,
        quantity_produced=58_000.0,
        quantity_unit=QuantityUnit.BOTTLES,
        manufacturing_site=SITE_HYDERABAD,
        units_released=56_800,
    ),
    BatchSpec(
        product_code="PHC-DRP-6001",
        batch_number="MXV-54602",
        manufactured_days_ago=120,
        shelf_life_days=SHELF_LIFE_24_MONTHS,
        quantity_produced=61_200.0,
        quantity_unit=QuantityUnit.BOTTLES,
        manufacturing_site=SITE_HYDERABAD,
        units_released=60_100,
    ),
]


def _upsert_customer(db: Session, spec: CustomerSpec) -> Customer:
    """Match on name - the field the complaint seeds join against."""
    customer = db.execute(select(Customer).where(Customer.name == spec.name)).scalar_one_or_none()

    if customer is None:
        customer = Customer(name=spec.name)
        db.add(customer)

    customer.customer_type = spec.customer_type
    customer.contact_email = spec.contact_email
    customer.contact_phone = spec.contact_phone
    customer.city = spec.city
    customer.country = spec.country
    return customer


def _upsert_product(db: Session, spec: ProductSpec) -> Product:
    """Match on product_code - the stable identifier, unlike a brand name."""
    product = db.execute(
        select(Product).where(Product.product_code == spec.product_code)
    ).scalar_one_or_none()

    if product is None:
        product = Product(product_code=spec.product_code)
        db.add(product)

    product.name = spec.name
    product.generic_name = spec.generic_name
    product.strength = spec.strength
    product.dosage_form = spec.dosage_form
    product.therapeutic_category = spec.therapeutic_category
    return product


def _upsert_batch(db: Session, spec: BatchSpec, product: Product, today: date) -> Batch:
    """Match on (product_id, batch_number), mirroring the table's constraint."""
    batch = db.execute(
        select(Batch).where(
            Batch.product_id == product.id,
            Batch.batch_number == spec.batch_number,
        )
    ).scalar_one_or_none()

    if batch is None:
        batch = Batch(product_id=product.id, batch_number=spec.batch_number)
        db.add(batch)

    manufactured_on = today - timedelta(days=spec.manufactured_days_ago)
    batch.manufacturing_date = manufactured_on
    batch.expiry_date = manufactured_on + timedelta(days=spec.shelf_life_days)
    batch.quantity_produced = spec.quantity_produced
    batch.quantity_unit = spec.quantity_unit
    batch.manufacturing_site = spec.manufacturing_site
    batch.units_released = spec.units_released
    return batch


def seed_reference_data(db: Session) -> tuple[list[Customer], list[Product], list[Batch]]:
    """Create or refresh customers, products and batches.

    Re-running updates the existing rows in place rather than failing on a
    unique constraint, so the whole seed is repeatable. Returns the three
    collections in declaration order for the complaint loader to index.
    """
    today = date.today()

    customers = [_upsert_customer(db, spec) for spec in CUSTOMERS]

    products: list[Product] = []
    products_by_code: dict[str, Product] = {}
    for product_spec in PRODUCTS:
        product = _upsert_product(db, product_spec)
        products.append(product)
        products_by_code[product_spec.product_code] = product

    # Batches match on product_id, so the products need identities first.
    db.flush()

    batches = [
        _upsert_batch(db, batch_spec, products_by_code[batch_spec.product_code], today)
        for batch_spec in BATCHES
    ]

    db.commit()

    for row in (*customers, *products, *batches):
        db.refresh(row)

    return customers, products, batches
