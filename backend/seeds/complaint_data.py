"""The demo complaint corpus, expressed as pure data.

This module deliberately imports nothing from SQLAlchemy and touches no session.
It is the *content* - what was reported, by whom, against which lot - and the
loader in ``seeds/complaints.py`` is the only thing that knows how to turn it
into rows. Keeping the split means the corpus can be read, reviewed and
diffed by a domain reviewer without any database in the picture, and it can be
reused later as fixture material for the extraction and duplicate-detection
tests.

Three conventions the loader depends on:

* ``customer_name``, ``product_name`` and ``batch_number`` are joined by exact
  string match against ``seeds/reference.py``. Nothing here invents a customer,
  product or lot that does not exist there.
* Dates are relative. ``complaint_date = today - days_ago`` and, when a due date
  applies, ``due_date = complaint_date + due_in_days``. A complaint is therefore
  overdue when ``days_ago > due_in_days`` and its status is not CLOSED.
* ``manufacturing_date`` and ``expiry_date`` are absent on purpose - the loader
  copies them from the linked batch, so they cannot drift out of agreement.

Shape of the corpus, which matters as much as the prose:

* 26 complaints across all seven lifecycle states, weighted to the early ones.
* 4 critical / 11 major / 11 minor, with priority kept coherent with severity.
* Four complaints against lot ``AZG-41866`` - the recall query and the
  duplicate-detection demo both need a real cluster to find. Two of those four
  are a near-duplicate pair: same lot, same defect, two different customers.
* Three intentionally overdue complaints so the dashboard's Overdue tile is
  non-zero: Ceftrizen CFZ-70311, Omecap OMC-61840 and Pantorex PTX-55023.
* A few records with fields deliberately left unset, so the completeness
  checker has something true to flag.

On the narratives: each is written as the customer would have written it, in
that customer's register - a ward pharmacist's note reads nothing like a
distributor's formal notice or a drug controller's field alert. Every one
describes what was *observed*. None of them asserts a cause; determining that is
the investigation's job, not the complainant's.

Every customer, reporter and brand name here is invented.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.schemas.enums import (
    ComplaintSource,
    ComplaintStatus,
    ComplaintType,
    DosageForm,
    Priority,
    QuantityUnit,
    Severity,
)


@dataclass(frozen=True)
class ComplaintSeed:
    """One demo complaint, expressed independently of the database."""

    source: ComplaintSource
    customer_name: str
    customer_contact: str | None
    reporter_name: str | None
    product_name: str
    product_strength: str | None
    dosage_form: DosageForm
    batch_number: str
    quantity_affected: Decimal | None
    quantity_unit: QuantityUnit | None
    complaint_type: ComplaintType
    description: str
    severity: Severity
    priority: Priority
    target_status: ComplaintStatus
    days_ago: int
    due_in_days: int | None
    investigator: bool


COMPLAINT_SEEDS: list[ComplaintSeed] = [
    # ── NEW ─────────────────────────────────────────────────────────────────
    ComplaintSeed(
        source=ComplaintSource.DISTRIBUTOR,
        customer_name="Deccan Healthcare Distributors Pvt Ltd",
        customer_contact="qa@deccanhealthcaredist.in",
        reporter_name="Srikanth Reddy",
        product_name="Azigen 500",
        product_strength="500 mg",
        dosage_form=DosageForm.TABLET,
        batch_number="AZG-41866",
        quantity_affected=Decimal("240"),
        quantity_unit=QuantityUnit.TABLETS,
        complaint_type=ComplaintType.APPEARANCE_DISCOLORATION,
        description=(
            "Raised by our Nagpur depot during pre-dispatch inspection of lot AZG-41866. "
            "Around 240 tablets across eight cartons carry light brown speckling on one "
            "face; stock from the same consignment inspected alongside appeared normal. "
            "The affected cartons are segregated in our quarantine cage and photographs "
            "are attached for your reference."
        ),
        severity=Severity.MAJOR,
        priority=Priority.HIGH,
        target_status=ComplaintStatus.NEW,
        days_ago=12,
        due_in_days=45,
        investigator=False,
    ),
    ComplaintSeed(
        source=ComplaintSource.EMAIL,
        customer_name="St. Clare Mission Hospital Pharmacy",
        customer_contact="pharmacy@stclaremission-hospital.org",
        reporter_name="Abena Mensah",
        product_name="Moxivis Eye Drops",
        product_strength="0.5% w/v",
        dosage_form=DosageForm.DROPS,
        batch_number="MXV-54602",
        quantity_affected=Decimal("9"),
        quantity_unit=QuantityUnit.BOTTLES,
        complaint_type=ComplaintType.TAMPER_EVIDENCE,
        description=(
            "Nine bottles from the carton we opened this morning had the outer shrink "
            "band split along the neck, though the inner dropper seal was intact on all "
            "of them. Our technician noticed it while decanting stock into the OPD tray. "
            "The nine bottles are set aside and we are dispensing from a different "
            "carton in the meantime."
        ),
        severity=Severity.MINOR,
        priority=Priority.MEDIUM,
        target_status=ComplaintStatus.NEW,
        days_ago=6,
        due_in_days=30,
        investigator=False,
    ),
    ComplaintSeed(
        source=ComplaintSource.DISTRIBUTOR,
        customer_name="Continental Drug Wholesalers Ltd",
        customer_contact="qc@continentaldrugwholesalers.ng",
        reporter_name=None,
        product_name="Metfosure 850",
        product_strength="850 mg",
        dosage_form=DosageForm.TABLET,
        batch_number="MFS-32117",
        quantity_affected=Decimal("340"),
        quantity_unit=QuantityUnit.TABLETS,
        complaint_type=ComplaintType.BROKEN_OR_CHIPPED,
        description=(
            "While palletising lot MFS-32117 for onward supply our warehouse team opened "
            "four shippers and found broken or chipped tablets visible through the "
            "blister film in roughly 340 pockets. The blisters themselves were sealed "
            "and the shippers showed no transit damage. Please advise whether the "
            "balance of the consignment should be held pending your review."
        ),
        severity=Severity.MINOR,
        priority=Priority.MEDIUM,
        target_status=ComplaintStatus.NEW,
        days_ago=9,
        due_in_days=60,
        investigator=False,
    ),
    ComplaintSeed(
        source=ComplaintSource.PHONE,
        customer_name="Arogya Chemists & Druggists",
        customer_contact="+91 79 4002 6611",
        reporter_name=None,
        product_name="Paracip Kids Syrup",
        product_strength=None,
        dosage_form=DosageForm.SYRUP,
        batch_number="PCP-91478",
        quantity_affected=Decimal("2"),
        quantity_unit=QuantityUnit.BOTTLES,
        complaint_type=ComplaintType.ODOR_OR_TASTE,
        description=(
            "Phone call logged at the counter. A parent returned two bottles saying the "
            "syrup smelled sharper than the pack bought the previous month and the child "
            "would not take the dose. One bottle was unopened, the other had been in use "
            "for three days. Both are retained at the store and a replacement has been "
            "offered pending advice."
        ),
        severity=Severity.MINOR,
        priority=Priority.LOW,
        target_status=ComplaintStatus.NEW,
        days_ago=4,
        due_in_days=60,
        investigator=False,
    ),
    ComplaintSeed(
        source=ComplaintSource.RETAIL_PHARMACY,
        customer_name="WellSpring Pharmacy Chain",
        customer_contact="quality@wellspringpharmacy.in",
        reporter_name="Rosemary Thomas",
        product_name="Clotrizen Cream 1%",
        product_strength="1% w/w",
        dosage_form=DosageForm.CREAM,
        batch_number="CLZ-47104",
        quantity_affected=Decimal("14"),
        quantity_unit=QuantityUnit.TUBES,
        complaint_type=ComplaintType.PACKAGING_DEFECT,
        description=(
            "Our Ernakulam branch reports 14 tubes from lot CLZ-47104 with a weak crimp "
            "at the tail end, two of which had leaked a small quantity of cream inside "
            "the carton. The tube mouths were sealed and the cartons were otherwise "
            "undamaged. All 14 tubes have been pulled from the shelf and are held at the "
            "branch for collection."
        ),
        severity=Severity.MINOR,
        priority=Priority.MEDIUM,
        target_status=ComplaintStatus.NEW,
        days_ago=17,
        due_in_days=60,
        investigator=False,
    ),
    ComplaintSeed(
        source=ComplaintSource.EMAIL,
        customer_name="Trans-Gulf Medical Supplies FZ-LLC",
        customer_contact="quality@transgulfmedical.ae",
        reporter_name="Faisal Al-Mansoori",
        product_name="Ceftrizen 1 g",
        product_strength="1 g",
        dosage_form=DosageForm.INJECTION,
        batch_number="CFZ-72104",
        quantity_affected=Decimal("24"),
        quantity_unit=QuantityUnit.VIALS,
        complaint_type=ComplaintType.APPEARANCE_DISCOLORATION,
        description=(
            "On incoming inspection at our Jebel Ali store, 24 vials of lot CFZ-72104 "
            "were noted to have a deeper yellow cast to the powder bed than previously "
            "supplied lots. Two vials were reconstituted as a check and the resulting "
            "solution was a distinctly darker straw colour. The consignment is on hold; "
            "we would ask for a comparison against your retained sample before we "
            "release it into the registered channel."
        ),
        severity=Severity.MAJOR,
        priority=Priority.HIGH,
        target_status=ComplaintStatus.NEW,
        days_ago=21,
        due_in_days=45,
        investigator=False,
    ),
    # ── UNDER REVIEW ────────────────────────────────────────────────────────
    ComplaintSeed(
        source=ComplaintSource.PHONE,
        customer_name="Arogya Chemists & Druggists",
        customer_contact="+91 79 4002 6611",
        reporter_name="Jignesh Patel",
        product_name="Azigen 500",
        product_strength="500 mg",
        dosage_form=DosageForm.TABLET,
        batch_number="AZG-41866",
        quantity_affected=Decimal("12"),
        quantity_unit=QuantityUnit.TABLETS,
        complaint_type=ComplaintType.APPEARANCE_DISCOLORATION,
        description=(
            "Pharmacist telephoned to report brown speckling on tablets in two strips of "
            "lot AZG-41866 dispensed over the counter last week. The customer returned "
            "both strips; twelve tablets are affected and the remaining tablets in the "
            "same strips look normal. The strips are held at the store and the "
            "pharmacist asks whether the other nine strips of this lot can continue to "
            "be sold."
        ),
        severity=Severity.MAJOR,
        priority=Priority.MEDIUM,
        target_status=ComplaintStatus.UNDER_REVIEW,
        days_ago=26,
        due_in_days=45,
        investigator=False,
    ),
    ComplaintSeed(
        source=ComplaintSource.DISTRIBUTOR,
        customer_name="Andes Pharma Distribuidora S.A.",
        customer_contact="calidad@andespharmadist.pe",
        reporter_name="Mariana Quispe",
        product_name="Omecap 20",
        product_strength="20 mg",
        dosage_form=DosageForm.CAPSULE,
        batch_number="OMC-61840",
        quantity_affected=Decimal("180"),
        quantity_unit=QuantityUnit.CAPSULES,
        complaint_type=ComplaintType.PACKAGING_DEFECT,
        description=(
            "Formal notification. On receipt inspection of lot OMC-61840 at our Callao "
            "warehouse the aluminium foil was found delaminating from the blister base "
            "across approximately 180 pockets in three shippers, with several capsules "
            "loose within the cavity. Samples have been photographed and retained under "
            "controlled conditions. The consignment remains quarantined and we require a "
            "written response within the period set out in our distribution agreement."
        ),
        severity=Severity.MAJOR,
        priority=Priority.HIGH,
        target_status=ComplaintStatus.UNDER_REVIEW,
        days_ago=74,
        due_in_days=45,
        investigator=True,
    ),
    ComplaintSeed(
        source=ComplaintSource.HOSPITAL_PHARMACY,
        customer_name="Ashwin Institute of Medical Sciences Pharmacy",
        customer_contact="pharmacy@ashwinmedsciences.in",
        reporter_name="Kavitha Raghavan",
        product_name="Ibucalm 100 Suspension",
        product_strength="100 mg/5 mL",
        dosage_form=DosageForm.SUSPENSION,
        batch_number="IBC-12885",
        quantity_affected=Decimal("7"),
        quantity_unit=QuantityUnit.BOTTLES,
        complaint_type=ComplaintType.STABILITY_DEFECT,
        description=(
            "Seven bottles from current ward stock of lot IBC-12885 show a compacted "
            "sediment at the base that needs noticeably longer shaking than usual before "
            "the suspension looks uniform. It does redisperse on continued shaking and "
            "no change in colour or odour was noted. The nursing station has set them "
            "aside and pharmacy is holding them for your inspection."
        ),
        severity=Severity.MINOR,
        priority=Priority.MEDIUM,
        target_status=ComplaintStatus.UNDER_REVIEW,
        days_ago=19,
        due_in_days=45,
        investigator=False,
    ),
    ComplaintSeed(
        source=ComplaintSource.DISTRIBUTOR,
        customer_name="Deccan Healthcare Distributors Pvt Ltd",
        customer_contact="qa@deccanhealthcaredist.in",
        reporter_name="Srikanth Reddy",
        product_name="Amlovas 5",
        product_strength="5 mg",
        dosage_form=DosageForm.TABLET,
        batch_number="AMV-29306",
        quantity_affected=Decimal("46"),
        quantity_unit=QuantityUnit.BOXES,
        complaint_type=ComplaintType.SHORT_COUNT_OR_FILL,
        description=(
            "A stock audit at our Secunderabad depot found 46 boxes of lot AMV-29306 "
            "containing nine strips against the ten declared on the carton. The shortfall "
            "was consistent across every box checked and the cartons were sealed with no "
            "sign of having been opened. The boxes are segregated and a count sheet is "
            "attached for your reconciliation."
        ),
        severity=Severity.MINOR,
        priority=Priority.LOW,
        target_status=ComplaintStatus.UNDER_REVIEW,
        days_ago=31,
        due_in_days=60,
        investigator=False,
    ),
    ComplaintSeed(
        source=ComplaintSource.CUSTOMER_PORTAL,
        customer_name="WellSpring Pharmacy Chain",
        customer_contact="quality@wellspringpharmacy.in",
        reporter_name="Rosemary Thomas",
        product_name="Fluconzo 150",
        product_strength="150 mg",
        dosage_form=DosageForm.CAPSULE,
        batch_number="FLZ-18644",
        quantity_affected=Decimal("60"),
        quantity_unit=QuantityUnit.BLISTERS,
        complaint_type=ComplaintType.LABELING_ERROR,
        description=(
            "Logged through the portal by our central quality desk. The batch number and "
            "expiry overprint on roughly 60 blisters of lot FLZ-18644 is smudged and "
            "partially illegible, the month digits worst of all; the carton print is "
            "clear. Branches have been instructed not to dispense the affected blisters "
            "until the identification can be confirmed."
        ),
        severity=Severity.MINOR,
        priority=Priority.MEDIUM,
        target_status=ComplaintStatus.UNDER_REVIEW,
        days_ago=44,
        due_in_days=60,
        investigator=False,
    ),
    # ── INVESTIGATION ───────────────────────────────────────────────────────
    ComplaintSeed(
        source=ComplaintSource.HOSPITAL_PHARMACY,
        customer_name="Sunrise Multispeciality Hospital Pharmacy",
        customer_contact="qa.pharmacy@sunrisemultispeciality.in",
        reporter_name="Anita Deshpande",
        product_name="Azigen 500",
        product_strength="500 mg",
        dosage_form=DosageForm.TABLET,
        batch_number="AZG-41866",
        quantity_affected=Decimal("6"),
        quantity_unit=QuantityUnit.BLISTERS,
        complaint_type=ComplaintType.PACKAGING_DEFECT,
        description=(
            "Our stores pharmacist found six blisters of lot AZG-41866 with an "
            "incomplete seal along the long edge, open far enough to slide the corner of "
            "a paper slip into the pocket. Two of those blisters also held tablets with "
            "light brown speckling on the surface. The six blisters are quarantined in "
            "the QA cupboard and the balance of the supply against our purchase order is "
            "on hold pending your response."
        ),
        severity=Severity.MAJOR,
        priority=Priority.HIGH,
        target_status=ComplaintStatus.INVESTIGATION,
        days_ago=33,
        due_in_days=45,
        investigator=True,
    ),
    ComplaintSeed(
        source=ComplaintSource.HOSPITAL_PHARMACY,
        customer_name="Ashwin Institute of Medical Sciences Pharmacy",
        customer_contact="pharmacy@ashwinmedsciences.in",
        reporter_name="Kavitha Raghavan",
        product_name="Ceftrizen 1 g",
        product_strength="1 g",
        dosage_form=DosageForm.INJECTION,
        batch_number="CFZ-70311",
        quantity_affected=Decimal("3"),
        quantity_unit=QuantityUnit.VIALS,
        complaint_type=ComplaintType.FOREIGN_MATTER,
        description=(
            "During reconstitution in the IV room the duty pharmacist observed a fine "
            "dark fibre suspended in the solution from one vial of lot CFZ-70311. Two "
            "further vials from the same carton were reconstituted for comparison and "
            "both showed similar particulate matter against the light box. None of the "
            "affected vials were administered to any patient. All three vials, the "
            "carton and the remaining 45 vials are sequestered and available for "
            "collection."
        ),
        severity=Severity.CRITICAL,
        priority=Priority.URGENT,
        target_status=ComplaintStatus.INVESTIGATION,
        days_ago=96,
        due_in_days=30,
        investigator=True,
    ),
    ComplaintSeed(
        source=ComplaintSource.DISTRIBUTOR,
        customer_name="Trans-Gulf Medical Supplies FZ-LLC",
        customer_contact="quality@transgulfmedical.ae",
        reporter_name="Faisal Al-Mansoori",
        product_name="Pantorex 40",
        product_strength="40 mg",
        dosage_form=DosageForm.TABLET,
        batch_number="PTX-56190",
        quantity_affected=None,
        quantity_unit=None,
        complaint_type=ComplaintType.ASSAY_OUT_OF_SPECIFICATION,
        description=(
            "Our accredited contract laboratory tested a retained sample of lot "
            "PTX-56190 as part of routine incoming verification and has reported an "
            "assay result below the registered specification limit; the certificate of "
            "analysis is attached. Description and dissolution were reported as "
            "conforming on the same sample. Distribution of this lot in our market is "
            "suspended and we request your written out-of-specification confirmation."
        ),
        severity=Severity.MAJOR,
        priority=Priority.HIGH,
        target_status=ComplaintStatus.INVESTIGATION,
        days_ago=58,
        due_in_days=90,
        investigator=True,
    ),
    ComplaintSeed(
        source=ComplaintSource.HOSPITAL_PHARMACY,
        customer_name="St. Clare Mission Hospital Pharmacy",
        customer_contact="pharmacy@stclaremission-hospital.org",
        reporter_name="Abena Mensah",
        product_name="Ondaset Injection",
        product_strength="2 mg/mL",
        dosage_form=DosageForm.INJECTION,
        batch_number="ODS-84260",
        quantity_affected=Decimal("2"),
        quantity_unit=QuantityUnit.AMPOULES,
        complaint_type=ComplaintType.FOREIGN_MATTER,
        description=(
            "Theatre staff drawing up pre-medication noticed a translucent fibre moving "
            "freely inside two ampoules of lot ODS-84260 when held against the light. "
            "Neither ampoule was used and no product from this carton has been "
            "administered. The two ampoules and the remaining sixteen in the carton are "
            "locked in the pharmacy safe, and our medical director has asked to be "
            "informed of your findings."
        ),
        severity=Severity.CRITICAL,
        priority=Priority.URGENT,
        target_status=ComplaintStatus.INVESTIGATION,
        days_ago=52,
        due_in_days=60,
        investigator=True,
    ),
    ComplaintSeed(
        source=ComplaintSource.REGULATORY_AUTHORITY,
        customer_name="State Drug Control Bureau (Western Zone)",
        customer_contact="wz.complaints@sdcb-westernzone.in",
        reporter_name="R. Bhatt, Drugs Inspector",
        product_name="Moxivis Eye Drops",
        product_strength="0.5% w/v",
        dosage_form=DosageForm.DROPS,
        batch_number="MXV-53718",
        quantity_affected=Decimal("6"),
        quantity_unit=QuantityUnit.BOTTLES,
        complaint_type=ComplaintType.CONTAMINATION_MICROBIAL,
        description=(
            "Field alert raised by this office following testing of a market sample of "
            "lot MXV-53718 drawn from a retail outlet in this zone. The sample has been "
            "reported as not complying with the sterility requirement of the applicable "
            "monograph; the test report reference and sampling memorandum are enclosed. "
            "You are directed to place all remaining stock of this lot on hold and to "
            "submit your investigation report, batch manufacturing record and "
            "retained-sample results to this office."
        ),
        severity=Severity.CRITICAL,
        priority=Priority.URGENT,
        target_status=ComplaintStatus.INVESTIGATION,
        days_ago=47,
        due_in_days=60,
        investigator=True,
    ),
    # ── ROOT CAUSE IDENTIFIED ───────────────────────────────────────────────
    ComplaintSeed(
        source=ComplaintSource.RETAIL_PHARMACY,
        customer_name="Arogya Chemists & Druggists",
        customer_contact="store@arogyachemists.in",
        reporter_name="Jignesh Patel",
        product_name="Clotrizen Cream 1%",
        product_strength="1% w/w",
        dosage_form=DosageForm.CREAM,
        batch_number="CLZ-46229",
        quantity_affected=Decimal("22"),
        quantity_unit=QuantityUnit.TUBES,
        complaint_type=ComplaintType.STABILITY_DEFECT,
        description=(
            "Customers have returned 22 tubes of lot CLZ-46229 over the past fortnight, "
            "all reporting that a clear liquid comes out of the tube ahead of the cream. "
            "We opened two of the returned tubes at the counter and a watery layer was "
            "visible above the white cream in both. The lot has been withdrawn from all "
            "three of our outlets and is held at the Ahmedabad store."
        ),
        severity=Severity.MAJOR,
        priority=Priority.MEDIUM,
        target_status=ComplaintStatus.ROOT_CAUSE_IDENTIFIED,
        days_ago=88,
        due_in_days=120,
        investigator=True,
    ),
    ComplaintSeed(
        source=ComplaintSource.DISTRIBUTOR,
        customer_name="Continental Drug Wholesalers Ltd",
        customer_contact="qc@continentaldrugwholesalers.ng",
        reporter_name="Chidi Okonkwo",
        product_name="Metfosure 850",
        product_strength="850 mg",
        dosage_form=DosageForm.TABLET,
        batch_number="MFS-31204",
        quantity_affected=Decimal("900"),
        quantity_unit=QuantityUnit.TABLETS,
        complaint_type=ComplaintType.APPEARANCE_DISCOLORATION,
        description=(
            "Our Lagos warehouse reports mottled grey-brown patches on tablets in "
            "roughly 900 pockets of lot MFS-31204, first noticed when a pharmacy "
            "customer returned three shippers. The affected blisters came from the upper "
            "layers of the pallet; stock from the lower layers inspected at the same time "
            "appeared normal. The returned shippers are held in our air-conditioned "
            "quarantine area awaiting your disposition instruction."
        ),
        severity=Severity.MAJOR,
        priority=Priority.HIGH,
        target_status=ComplaintStatus.ROOT_CAUSE_IDENTIFIED,
        days_ago=103,
        due_in_days=None,
        investigator=True,
    ),
    # ── CAPA REQUIRED ───────────────────────────────────────────────────────
    ComplaintSeed(
        source=ComplaintSource.HOSPITAL_PHARMACY,
        customer_name="Sunrise Multispeciality Hospital Pharmacy",
        customer_contact="qa.pharmacy@sunrisemultispeciality.in",
        reporter_name="Anita Deshpande",
        product_name="Pantorex 40",
        product_strength="40 mg",
        dosage_form=DosageForm.TABLET,
        batch_number="PTX-55023",
        quantity_affected=Decimal("300"),
        quantity_unit=QuantityUnit.CARTONS,
        complaint_type=ComplaintType.LABELING_ERROR,
        description=(
            "While updating our formulary file the pharmacy noticed that the patient "
            "information leaflet packed with lot PTX-55023 is the superseded revision "
            "and does not carry the revised storage statement printed on the carton. The "
            "carton and blister artwork are themselves correct. About 300 cartons of "
            "this lot are in our stores; we are inserting the current leaflet at "
            "dispensing and request written confirmation of your corrective action."
        ),
        severity=Severity.MINOR,
        priority=Priority.MEDIUM,
        target_status=ComplaintStatus.CAPA_REQUIRED,
        days_ago=132,
        due_in_days=90,
        investigator=True,
    ),
    ComplaintSeed(
        source=ComplaintSource.DISTRIBUTOR,
        customer_name="Andes Pharma Distribuidora S.A.",
        customer_contact="calidad@andespharmadist.pe",
        reporter_name="Mariana Quispe",
        product_name="Fluconzo 150",
        product_strength="150 mg",
        dosage_form=DosageForm.CAPSULE,
        batch_number="FLZ-17902",
        quantity_affected=Decimal("75"),
        quantity_unit=QuantityUnit.BLISTERS,
        complaint_type=ComplaintType.SHORT_COUNT_OR_FILL,
        description=(
            "Our quality desk in Lima found sealed but empty blister pockets in "
            "approximately 75 blisters of lot FLZ-17902, identified during routine "
            "sampling of ten shippers. The foil over the empty pockets was intact and "
            "the printing showed no damage. The lot is blocked in our system and the "
            "national agency has been notified as our licence requires; we ask for your "
            "corrective and preventive action plan."
        ),
        severity=Severity.MAJOR,
        priority=Priority.HIGH,
        target_status=ComplaintStatus.CAPA_REQUIRED,
        days_ago=118,
        due_in_days=150,
        investigator=True,
    ),
    # ── QA REVIEW ───────────────────────────────────────────────────────────
    ComplaintSeed(
        source=ComplaintSource.HOSPITAL_PHARMACY,
        customer_name="Ashwin Institute of Medical Sciences Pharmacy",
        customer_contact="pharmacy@ashwinmedsciences.in",
        reporter_name="Kavitha Raghavan",
        product_name="Ibucalm 100 Suspension",
        product_strength="100 mg/5 mL",
        dosage_form=DosageForm.SUSPENSION,
        batch_number="IBC-12037",
        quantity_affected=Decimal("1"),
        quantity_unit=QuantityUnit.BOTTLES,
        complaint_type=ComplaintType.FOREIGN_MATTER,
        description=(
            "A ward sister returned one bottle of lot IBC-12037 after noticing a black "
            "speck of about one millimetre adhering to the inside of the bottle shoulder, "
            "above the liquid line. The remainder of the suspension looked normal and the "
            "bottle had been opened two days earlier. The bottle has been recapped, "
            "labelled and retained in the pharmacy QA locker for your collection."
        ),
        severity=Severity.MAJOR,
        priority=Priority.HIGH,
        target_status=ComplaintStatus.QA_REVIEW,
        days_ago=79,
        due_in_days=90,
        investigator=True,
    ),
    ComplaintSeed(
        source=ComplaintSource.RETAIL_PHARMACY,
        customer_name="WellSpring Pharmacy Chain",
        customer_contact="quality@wellspringpharmacy.in",
        reporter_name="Rosemary Thomas",
        product_name="Amlovas 5",
        product_strength="5 mg",
        dosage_form=DosageForm.TABLET,
        batch_number="AMV-28450",
        quantity_affected=Decimal("55"),
        quantity_unit=QuantityUnit.TABLETS,
        complaint_type=ComplaintType.BROKEN_OR_CHIPPED,
        description=(
            "Across four branches our staff have logged 55 tablets of lot AMV-28450 "
            "arriving chipped at the edge, generally one or two per strip. No blister "
            "pockets were found punctured and none of the cartons showed crush damage. "
            "The affected strips are consolidated at our Kochi central store and a "
            "branch-wise tally is attached."
        ),
        severity=Severity.MINOR,
        priority=Priority.LOW,
        target_status=ComplaintStatus.QA_REVIEW,
        days_ago=91,
        due_in_days=120,
        investigator=True,
    ),
    # ── CLOSED ──────────────────────────────────────────────────────────────
    ComplaintSeed(
        source=ComplaintSource.RETAIL_PHARMACY,
        customer_name="WellSpring Pharmacy Chain",
        customer_contact="quality@wellspringpharmacy.in",
        reporter_name="Rosemary Thomas",
        product_name="Azigen 500",
        product_strength="500 mg",
        dosage_form=DosageForm.TABLET,
        batch_number="AZG-41866",
        quantity_affected=Decimal("18"),
        quantity_unit=QuantityUnit.TABLETS,
        complaint_type=ComplaintType.APPEARANCE_DISCOLORATION,
        description=(
            "Our Thrissur branch reported light brown speckling on the tablet faces in "
            "three strips of lot AZG-41866 returned by a customer, eighteen tablets in "
            "all. The pharmacist compared them against an unopened strip of the same lot, "
            "which appeared normal. The returned strips were couriered to your Vapi site "
            "on our account and the customer has been issued a replacement pack."
        ),
        severity=Severity.MAJOR,
        priority=Priority.HIGH,
        target_status=ComplaintStatus.CLOSED,
        days_ago=41,
        due_in_days=45,
        investigator=True,
    ),
    ComplaintSeed(
        source=ComplaintSource.DISTRIBUTOR,
        customer_name="Trans-Gulf Medical Supplies FZ-LLC",
        customer_contact="quality@transgulfmedical.ae",
        reporter_name="Faisal Al-Mansoori",
        product_name="Ceftrizen 1 g",
        product_strength="1 g",
        dosage_form=DosageForm.INJECTION,
        batch_number="CFZ-71208",
        quantity_affected=Decimal("48"),
        quantity_unit=QuantityUnit.VIALS,
        complaint_type=ComplaintType.LABELING_ERROR,
        description=(
            "Urgent. During a witnessed release inspection at our Dubai store, 48 vials "
            "drawn from six cartons of lot CFZ-71208 carried a vial label whose batch "
            "number did not match the batch number printed on the secondary carton, and "
            "the two expiry dates differed by one month. The full consignment of 600 "
            "vials is under seal at our facility and no stock has moved to customers. "
            "Please treat this as requiring an immediate response."
        ),
        severity=Severity.CRITICAL,
        priority=Priority.URGENT,
        target_status=ComplaintStatus.CLOSED,
        days_ago=161,
        due_in_days=30,
        investigator=True,
    ),
    ComplaintSeed(
        source=ComplaintSource.WRITTEN_LETTER,
        customer_name="St. Clare Mission Hospital Pharmacy",
        customer_contact="pharmacy@stclaremission-hospital.org",
        reporter_name="Abena Mensah",
        product_name="Paracip Kids Syrup",
        product_strength="125 mg/5 mL",
        dosage_form=DosageForm.SYRUP,
        batch_number="PCP-90562",
        quantity_affected=Decimal("34"),
        quantity_unit=QuantityUnit.BOTTLES,
        complaint_type=ComplaintType.PHYSICAL_DAMAGE,
        description=(
            "We write to place on record that the consignment received against our last "
            "order included 34 bottles of lot PCP-90562 leaking syrup inside their "
            "cartons, while the outer shrink wrap of the shippers was intact. The "
            "affected bottles came from the lower two layers of the pallet. The leaked "
            "bottles have been destroyed under witness as our procedure requires, and "
            "the cartons and photographs are retained for your records."
        ),
        severity=Severity.MINOR,
        priority=Priority.MEDIUM,
        target_status=ComplaintStatus.CLOSED,
        days_ago=147,
        due_in_days=60,
        investigator=True,
    ),
    ComplaintSeed(
        source=ComplaintSource.EMAIL,
        customer_name="Arogya Chemists & Druggists",
        customer_contact="store@arogyachemists.in",
        reporter_name=None,
        product_name="Omecap 20",
        product_strength="20 mg",
        dosage_form=DosageForm.CAPSULE,
        batch_number="OMC-62755",
        quantity_affected=Decimal("10"),
        quantity_unit=QuantityUnit.CAPSULES,
        complaint_type=ComplaintType.ODOR_OR_TASTE,
        description=(
            "Forwarded from our counter staff. A customer returned one strip saying the "
            "capsules gave off a sour smell when the blister was opened; ten capsules "
            "were in the strip and none were taken. We have kept the strip in a sealed "
            "pouch at the store and would like to know whether to return it to you or "
            "destroy it locally."
        ),
        severity=Severity.MINOR,
        priority=Priority.LOW,
        target_status=ComplaintStatus.CLOSED,
        days_ago=126,
        due_in_days=90,
        investigator=False,
    ),
]
