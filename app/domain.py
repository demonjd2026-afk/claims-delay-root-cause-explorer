"""Domain model: claim stages, delay themes and the operations playbook.

Everything business-facing (names, plain-English explanations, owners) lives
here so analytics, the AI analyst and the UI all describe a theme the same way.

The playbook fields `addressability` and `effort` are planning assumptions,
not measurements. They are surfaced as assumptions in the UI and should be
replaced with operations' own estimates before any real decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field

STAGES: dict[str, dict[str, str]] = {
    "intake": {
        "name": "Intake",
        "does": "Receives the claim, validates format and HIPAA rules, assigns tracking numbers and routes it.",
    },
    "pre_adjudication": {
        "name": "Pre-Adjudication",
        "does": "Matches the claim to the right member and provider, and screens for duplicates and fraud, waste and abuse.",
    },
    "adjudication": {
        "name": "Adjudication",
        "does": "Decides whether and how much to pay: eligibility, authorization, clinical edits, benefits, COB and pricing.",
    },
    "post_adjudication": {
        "name": "Post-Adjudication",
        "does": "Updates accumulators, releases payment and issues the EOB to the member and the remittance to the provider.",
    },
}
STAGE_ORDER = list(STAGES)

NEEDS_REVIEW = "needs_review"
NEEDS_REVIEW_NAME = "Needs human review"

GENERIC_PEND_CODE = "PND-000"


@dataclass(frozen=True)
class SubCause:
    key: str
    label: str
    weight: float
    pend_factor: float  # multiplies the theme's mean pend duration
    notes: tuple[str, ...]


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    stage: str
    pend_code: str
    plain: str            # what it is, for a non-claims reader
    why: str              # why it happens
    intervention: str     # what to do about it
    owner: str            # accountable function
    addressability: float  # planning assumption: share of delay removable
    effort: int           # planning assumption: 1 low, 2 medium, 3 high
    base_rate: float      # synthetic generator: share of all claims
    mean_pend_days: float  # synthetic generator
    mean_touches: float   # synthetic generator
    deny_rate: float      # synthetic generator
    denial_code: str | None
    sub_causes: tuple[SubCause, ...] = field(default_factory=tuple)


# Denial codes are standard Claim Adjustment Reason Codes (CARC). Pend codes
# are invented for this demo; real pend codes are platform-specific.
DENIAL_CODE_TEXT = {
    "16": "Claim lacks information or has submission errors",
    "18": "Exact duplicate claim or service",
    "22": "Care may be covered by another payer (coordination of benefits)",
    "27": "Expenses incurred after coverage terminated",
    "31": "Patient cannot be identified as our insured",
    "50": "Not deemed a medical necessity by the payer",
    "96": "Non-covered charge(s)",
    "97": "Benefit included in the payment for another service (bundled)",
    "197": "Precertification, authorization or notification absent",
}

THEMES: tuple[Theme, ...] = (
    Theme(
        key="edi_validation", name="Claim format or data errors", stage="intake", pend_code="PND-110",
        plain="The claim arrived with missing or invalid data and could not be read cleanly.",
        why="Submitters send claims that fail format or HIPAA checks, and paper claims are keyed or scanned with errors.",
        intervention="Reject at the front door with a specific error instead of pending, and coach the highest-error submitters.",
        owner="Intake / EDI operations", addressability=0.55, effort=1,
        base_rate=0.0110, mean_pend_days=1.4, mean_touches=1.2, deny_rate=0.10, denial_code="16",
        sub_causes=(
            SubCause("ocr_keying", "Paper claim scanned or keyed incorrectly", 0.45, 1.3, (
                "paper clm from mail room, OCR misread {field}. rekeyed from image and released",
                "scan quality poor, {field} illegible on image. sent back to RMO for rescan",
                "keying error on paper submission - {field} wrong vs image. corrected manually",
            )),
            SubCause("missing_segment", "Required data element missing on electronic claim", 0.55, 0.8, (
                "837 missing required {field}, failed syntax validation. repaired and reprocessed",
                "HIPAA edit failed - {field} not populated on inbound file from clearinghouse",
                "inbound EDI rejected at front end edit, invalid {field}. submitter notified",
            )),
        ),
    ),
    Theme(
        key="intake_routing", name="Misrouted or needs splitting at intake", stage="intake", pend_code="PND-120",
        plain="The claim reached the wrong work queue, or one submission has to be split into several claims before processing.",
        why="Routing rules send the claim to the wrong platform or queue, or a multi-page or multi-provider submission cannot be handled as one claim.",
        intervention="Tighten routing rules using the claim's own data, and split multi-claim submissions automatically at intake.",
        owner="Intake / EDI operations", addressability=0.60, effort=1,
        base_rate=0.0040, mean_pend_days=2.6, mean_touches=1.4, deny_rate=0.0, denial_code=None,
        sub_causes=(
            SubCause("misrouted", "Routed to the wrong platform or queue", 0.55, 1.1, (
                "claim routed to wrong platform at intake, belongs to different line of business. rerouted to correct queue",
                "misrouted - landed in wrong work queue, payer id on submission maps to other plan. transferred",
                "wrong queue at front end, routing rule sent it to incorrect region. manually rerouted",
            )),
            SubCause("needs_split", "One submission must be split into several claims", 0.45, 0.9, (
                "multi page paper submission contains {n} separate claims. split into individual claims and new ICN assigned",
                "special handling - single submission covers multiple rendering providers, needs splitting before processing",
                "interim bill with several service periods on one form. split by period and reassigned tracking numbers",
            )),
        ),
    ),
    Theme(
        key="member_match", name="Member could not be matched", stage="pre_adjudication", pend_code="PND-210",
        plain="The patient on the claim could not be confidently matched to a member record.",
        why="Name, date of birth or ID on the claim differs from the enrollment record, or a newborn is not yet enrolled.",
        intervention="Add fuzzy matching on name and date of birth, and auto-link newborn claims to the subscriber for the first 30 days.",
        owner="Enrollment and member data", addressability=0.50, effort=2,
        base_rate=0.0050, mean_pend_days=4.0, mean_touches=1.8, deny_rate=0.12, denial_code="31",
        sub_causes=(
            SubCause("demographic_mismatch", "Name, date of birth or member ID does not match", 0.70, 0.9, (
                "member pick failed - DOB on clm does not match enrollment. verified via {src} and linked",
                "subscriber ID on claim has transposed digits, no member found. searched by name/DOB",
                "mbr name mismatch (maiden vs married name). manual member pick after {src} lookup",
            )),
            SubCause("newborn", "Newborn not yet added to the plan", 0.30, 1.5, (
                "newborn claim billed under mother ID, baby not yet enrolled. holding for enrollment add",
                "baby not on file - waiting on newborn enrollment from employer group. f/u {n} days",
            )),
        ),
    ),
    Theme(
        key="provider_match", name="Provider or tax ID could not be matched", stage="pre_adjudication", pend_code="PND-220",
        plain="The billing or servicing provider could not be matched to the provider file.",
        why="Provider data on the claim (NPI, tax ID, address) does not match the provider file, often after a roster or contract update.",
        intervention="Reconcile the provider file after every roster load before claims are released, and auto-match on NPI plus tax ID.",
        owner="Provider data management", addressability=0.70, effort=1,
        base_rate=0.0060, mean_pend_days=6.0, mean_touches=2.1, deny_rate=0.0, denial_code=None,
        sub_causes=(
            SubCause("tin_not_on_file", "Tax ID not on the provider file after a roster update", 0.40, 1.2, (
                "TIN on claim not on provider file after roster update. ticket to PDM to load TIN",
                "TIN validation failed - tax id missing from provider record since last roster load. sent to provider data",
                "billing TIN not found, provider roster load appears incomplete. pended for PDM correction",
            )),
            SubCause("npi_mismatch", "NPI on the claim does not match the provider record", 0.35, 0.9, (
                "provider pick failed, rendering NPI not linked to billing group. manual prov match",
                "NPI on clm maps to different provider name. confirmed via NPPES and corrected pick",
            )),
            SubCause("multiple_locations", "Several provider records match; location unclear", 0.25, 0.8, (
                "multiple provider records returned for same NPI, service location zip differs. selected by address",
                "prov has {n} active locations, could not auto-select. matched on taxonomy and zip",
            )),
        ),
    ),
    Theme(
        key="duplicate", name="Possible duplicate claim", stage="pre_adjudication", pend_code="PND-230",
        plain="The claim looks like one already received and is held to avoid paying twice.",
        why="Providers resubmit when they have not seen payment, or send a corrected claim without marking it as a correction.",
        intervention="Give providers real-time claim status so they stop resubmitting, and auto-deny exact matches.",
        owner="Claims operations", addressability=0.65, effort=1,
        base_rate=0.0045, mean_pend_days=3.0, mean_touches=1.4, deny_rate=0.60, denial_code="18",
        sub_causes=(
            SubCause("exact_resubmission", "Provider resubmitted the same claim", 0.60, 0.8, (
                "exact match to prior claim - same mbr, DOS, codes and charges. provider resubmitted, original still in process",
                "dup check hit, identical to claim received {n} days ago. no payment seen by provider so they rebilled",
            )),
            SubCause("unmarked_correction", "Corrected claim sent without a correction indicator", 0.40, 1.3, (
                "possible dup but charges differ from original. looks like corrected claim without frequency code 7",
                "same DOS and provider, procedure code changed. corrected clm not flagged as replacement, reviewing both",
            )),
        ),
    ),
    Theme(
        key="fwa_review", name="Fraud, waste and abuse review", stage="pre_adjudication", pend_code="PND-240",
        plain="The claim matched an unusual billing pattern and is held for investigation.",
        why="Billing patterns exceed what is plausible, or the provider is already on a watch list.",
        intervention="Tune screening thresholds to cut false positives and set a turnaround target for the investigations unit.",
        owner="Payment integrity", addressability=0.25, effort=3,
        base_rate=0.0013, mean_pend_days=16.0, mean_touches=3.2, deny_rate=0.25, denial_code="16",
        sub_causes=(
            SubCause("billing_pattern", "Unusual billing volume or pattern", 0.65, 1.0, (
                "flagged by FWA screen - units billed exceed plausible daily max. referred to SIU",
                "aberrant billing pattern, same high level E/M on every visit. hold pending SIU review",
            )),
            SubCause("watch_list", "Provider already under review", 0.35, 1.2, (
                "provider on prepay review list. all claims held for investigator sign off",
                "prepayment review flag active on this provider, requested itemized bill",
            )),
        ),
    ),
    Theme(
        key="eligibility", name="Coverage or eligibility discrepancy", stage="adjudication", pend_code="PND-310",
        plain="It is unclear whether the member was covered on the date of service.",
        why="Enrollment changes arrive late or retroactively, so the claim reaches adjudication before coverage is updated.",
        intervention="Shorten the enrollment file cycle and automatically re-run held claims when eligibility updates land.",
        owner="Enrollment and eligibility", addressability=0.55, effort=2,
        base_rate=0.0043, mean_pend_days=7.0, mean_touches=1.7, deny_rate=0.45, denial_code="27",
        sub_causes=(
            SubCause("retro_change", "Retroactive enrollment change in progress", 0.60, 1.2, (
                "elig shows termed before DOS but retro reinstatement in progress. holding for eligibility update",
                "coverage gap on DOS, state file shows retro enrollment pending. recycle after next elig load",
            )),
            SubCause("termed_coverage", "Coverage ended before the date of service", 0.40, 0.7, (
                "member coverage ended prior to DOS. confirmed term date with enrollment, no active span",
                "inactive coverage on date of service, group termed. verifying no COBRA election",
            )),
        ),
    ),
    Theme(
        key="prior_auth", name="Prior authorization missing or not matched", stage="adjudication", pend_code="PND-320",
        plain="The service needed advance approval and no matching approval was found on the claim.",
        why="The authorization was never requested, has expired, or exists but under different details so the system cannot match it.",
        intervention="Auto-match authorizations on member, service and date window instead of exact provider, and show auth status to providers before they bill.",
        owner="Utilization management and claims", addressability=0.60, effort=2,
        base_rate=0.0130, mean_pend_days=11.0, mean_touches=2.4, deny_rate=0.35, denial_code="197",
        sub_causes=(
            SubCause("auth_other_provider", "Authorization exists but under a different provider", 0.45, 0.8, (
                "auth on file but under different NPI than billing provider. manual auth match required",
                "PA found for same mbr and procedure, issued to ordering physician not rendering facility. linked manually",
                "prior auth matching failed, auth is under group TIN and clm billed under individual. matched by hand",
            )),
            SubCause("no_auth", "No authorization was requested", 0.35, 1.3, (
                "no auth on file for {svc}. PA required per plan. letter sent to provider requesting auth info",
                "{svc} requires precert, none found in UM system. called provider office, awaiting response",
            )),
            SubCause("auth_expired", "Authorization expired or units exhausted", 0.20, 1.0, (
                "auth expired before DOS, approved date range ended. sent to UM for extension review",
                "auth units exhausted, {n} visits approved and all used. routed to UM for additional units",
            )),
        ),
    ),
    Theme(
        key="clinical_edit", name="Clinical edit or bundling review", stage="adjudication", pend_code="PND-330",
        plain="The billed codes conflict with each other or with the patient's details and need a coding review.",
        why="Services are billed separately when they should be bundled, or modifiers and diagnosis codes do not line up.",
        intervention="Publish the top edit conflicts to providers and auto-apply the edits that are overturned least often.",
        owner="Payment policy and coding", addressability=0.45, effort=2,
        base_rate=0.0035, mean_pend_days=5.0, mean_touches=1.6, deny_rate=0.30, denial_code="97",
        sub_causes=(
            SubCause("unbundling", "Services billed separately that belong together", 0.60, 1.0, (
                "clinical edit - component code billed separately with comprehensive surgical code. bundling review",
                "unbundled procedure, incidental service billed with primary. coder review for modifier 59 support",
            )),
            SubCause("code_conflict", "Code conflicts with the patient's age, gender or diagnosis", 0.40, 0.9, (
                "edit fired - procedure inconsistent with patient age. sent to coding for validation",
                "dx code does not support billed procedure, invalid code relationship. coding review",
            )),
        ),
    ),
    Theme(
        key="medical_records", name="Medical records needed for clinical review", stage="adjudication", pend_code="PND-340",
        plain="A clinician must review the patient's records to confirm the service was medically necessary.",
        why="Records are requested by letter or fax after the claim arrives, and providers are slow or incomplete in responding.",
        intervention="Request records electronically at the point of authorization and accept digital submission through the provider portal.",
        owner="Clinical review", addressability=0.40, effort=3,
        base_rate=0.0060, mean_pend_days=19.0, mean_touches=3.0, deny_rate=0.25, denial_code="50",
        sub_causes=(
            SubCause("awaiting_records", "Waiting for the provider to send records", 0.60, 1.15, (
                "med recs requested from facility by fax, not yet received. 2nd request sent",
                "medical necessity review needs clinical notes. records request letter mailed, f/u {n} days",
                "awaiting medical records from provider for {svc}. no response to first request",
            )),
            SubCause("clinical_queue", "Records received; waiting in the nurse review queue", 0.40, 0.8, (
                "records received and attached. in nurse review queue for medical necessity determination",
                "clinicals received, routed to medical director for review against policy guideline",
            )),
        ),
    ),
    Theme(
        key="cob", name="Other insurance information needed", stage="adjudication", pend_code="PND-350",
        plain="The member may have another insurer, and it is unclear which plan should pay first.",
        why="Other-coverage details are missing or out of date, so the member or the other insurer has to be contacted.",
        intervention="Verify other coverage through an eligibility clearinghouse instead of mailing questionnaires to members.",
        owner="Coordination of benefits", addressability=0.50, effort=2,
        base_rate=0.0070, mean_pend_days=15.0, mean_touches=2.3, deny_rate=0.15, denial_code="22",
        sub_causes=(
            SubCause("questionnaire", "Waiting for the member to confirm other coverage", 0.55, 1.2, (
                "COB questionnaire mailed to member, no response yet. other insurance indicator on file is over 12 months old",
                "other coverage suspected for dependent child, both parents insured. COB letter sent to subscriber",
            )),
            SubCause("primary_eob", "Waiting for the primary insurer's payment statement", 0.45, 0.8, (
                "we are secondary. primary carrier EOB not attached to claim. requested primary EOB from provider",
                "need primary payer EOB to coordinate benefits, clm submitted without it. provider contacted",
            )),
        ),
    ),
    Theme(
        key="pricing", name="Manual pricing or contract not loaded", stage="adjudication", pend_code="PND-360",
        plain="The system could not price the claim automatically and someone must calculate the allowed amount.",
        why="The provider's contract or fee schedule is not loaded, or the provider is out of network and needs a negotiated rate.",
        intervention="Load contracts before their effective date and set default pricing rules for out-of-network claims.",
        owner="Network contracting and pricing", addressability=0.60, effort=2,
        base_rate=0.0050, mean_pend_days=9.0, mean_touches=2.2, deny_rate=0.0, denial_code=None,
        sub_causes=(
            SubCause("contract_not_loaded", "Contract or fee schedule not loaded", 0.50, 1.1, (
                "no fee schedule loaded for provider contract effective this year. manual pricing required",
                "contract rate missing in pricing system, new agreement not yet loaded. sent to contracting",
            )),
            SubCause("out_of_network", "Out-of-network claim needs a negotiated rate", 0.50, 0.9, (
                "non-par provider, no contracted rate. routed to vendor for out of network repricing",
                "OON claim, billed charges exceed threshold. sent for negotiation before allowed amount set",
            )),
        ),
    ),
    Theme(
        key="payment_hold", name="Payment could not be released", stage="post_adjudication", pend_code="PND-410",
        plain="The claim was approved but the payment could not be sent.",
        why="The provider's bank or mailing details failed validation, or the payment was held for a balance owed.",
        intervention="Validate bank details when providers enroll for electronic payment rather than at the time of payment.",
        owner="Payment and finance operations", addressability=0.60, effort=1,
        base_rate=0.0021, mean_pend_days=6.0, mean_touches=1.5, deny_rate=0.0, denial_code=None,
        sub_causes=(
            SubCause("eft_failure", "Electronic payment details failed validation", 0.60, 0.9, (
                "EFT rejected by bank, account details on file invalid. payment reissue pending new enrollment form",
                "ACH returned - provider bank account closed. outreach for updated EFT enrollment",
            )),
            SubCause("offset_hold", "Payment held against a balance the provider owes", 0.40, 1.2, (
                "payment held, open overpayment recovery on provider. finance reviewing offset amount",
                "check run hold - provider has outstanding refund balance. awaiting finance release",
            )),
        ),
    ),
)

THEME_BY_KEY = {t.key: t for t in THEMES}
THEME_BY_CODE = {t.pend_code: t for t in THEMES}

LOBS = ("Commercial", "Medicare Advantage", "Medicaid")
PLATFORMS = ("TOPS", "USP", "COSMOS", "CSP")
CHANNELS = ("Clearinghouse (EDI)", "Provider portal", "Paper (mail office)")
CLAIM_TYPES = ("Professional", "Institutional")
SPECIALTIES = (
    "Primary care", "Radiology", "Orthopedics", "Cardiology", "Behavioral health",
    "Physical therapy", "Emergency medicine", "Laboratory", "Hospital inpatient", "Outpatient surgery",
)


def theme_name(key: str) -> str:
    if key == NEEDS_REVIEW:
        return NEEDS_REVIEW_NAME
    return THEME_BY_KEY[key].name


def stage_name(key: str) -> str:
    return STAGES[key]["name"]
