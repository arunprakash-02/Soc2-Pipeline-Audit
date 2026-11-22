"""
TPRM evidence mapping and assessment pipeline for SOC 2 reports.

The local LLM proposes an internal requirement mapping. Deterministic rules
validate the proposal, resolve limited expert-approved conflicts, preserve
the supporting evidence span, and flag uncertain or exception-bearing
evidence for analyst review.

This workflow does not issue a final SOC 2 attestation or legal compliance
opinion.
"""

import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import fitz
import ollama

from mapping_keywords import (
    get_candidate_requirements,
    is_report_narrative,
    normalize_for_matching,
    resolve_candidate_conflict,
)

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PDF_PATH = BASE_DIR / "data" / "raw" / "equinix_soc2.pdf"
DEFAULT_OUTPUT_FILE = BASE_DIR / "data" / "mapped_claims.json"
DEFAULT_MANIFEST_FILE = BASE_DIR / "data" / "run_manifest.json"
DEFAULT_FAILURE_LOG_FILE = BASE_DIR / "data" / "pipeline_failures.jsonl"

MODEL_NAME = "llama3.2:3b"
NUM_CTX = 4096
TEMPERATURE = 0
SEED = 42

FRAMEWORK = "SOC 2"
SOURCE_VERSION = (
    "2017 Trust Services Criteria with Revised Points of Focus (2022); "
    "includes March 2020 updates"
)
ASSESSMENT_DATE = "2026-11-16"

PASS_PATTERNS = [
    r"\bno exceptions were noted\b",
    r"\bno exceptions noted\b",
    r"\bno exceptions were identified\b",
    r"\bno exceptions identified\b",
    r"\bno exceptions\b",
    r"\bno deviations\b",
    r"\bthe results of tests indicate\b",
    r"\bindicates that the control was operating effectively\b",
    r"\bindicates that the controls were operating effectively\b",
]

FAIL_PATTERNS = [
    r"\bcontrol was not operating effectively\b",
    r"\bcontrols were not operating effectively\b",
    r"\bcontrol failure\b",
    r"\bcontrol failures\b",
    r"\bexceptions were noted\b",
    r"\bexception was noted\b",
    r"\bexceptions were identified\b",
    r"\bexception was identified\b",
    r"\bexceptions identified\b",
    r"\bexception identified\b",
    r"\bexception raised\b",
    r"\bexceptions raised\b",
    r"\bwere not reported\b",
    r"\bwas not reported\b",
    r"\bnot reported\b",
    r"\bunreported\b",
    r"\bfailed to\b",
]

VALID_REQUIREMENT_IDS = {
    "SEC-01",
    "SEC-02",
    "SEC-03",
    "SEC-04",
    "SEC-05",
    "SEC-06",
    "SEC-07",
    "SEC-08",
    "SEC-09",
    "SEC-10",
    "PRV-01",
    "PRV-02",
    "PRV-03",
    "PRV-04",
    "PRV-05",
    "PRV-06",
    "GOV-01",
    "GOV-02",
    "GOV-03",
    "GOV-04",
    "PHY-01",
    "VEN-01",
    "CHG-01",
}


def record_failure(
    failure_log_path: Path,
    run_id: str,
    stage: str,
    error_type: str,
    message: str,
    page: int | None = None,
    control_id: str | None = None,
):
    """Append a structured technical failure entry as JSON Lines (B-17)."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "stage": stage,
        "page": page,
        "control_id": control_id,
        "model": MODEL_NAME,
        "error_type": error_type,
        "message": str(message),
    }
    failure_log_path.parent.mkdir(parents=True, exist_ok=True)
    with failure_log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_soc2_pdf(pdf_path: Path) -> dict:
    """Validate PDF existence, extension, size, PyMuPDF structure, and SOC 2 signals (B-14)."""
    if not pdf_path.exists() or not pdf_path.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {pdf_path.name}")

    file_size = pdf_path.stat().st_size
    if file_size <= 0:
        raise ValueError(f"PDF file is empty (0 bytes): {pdf_path}")

    sha256 = compute_sha256(pdf_path)

    try:
        document = fitz.open(pdf_path)
    except Exception as exc:
        raise ValueError(f"Failed to open PDF with PyMuPDF: {exc}") from exc

    try:
        page_count = len(document)
        if page_count <= 0:
            raise ValueError(f"PDF has no pages: {pdf_path}")

        sample_texts = []
        for idx in range(min(page_count, 50)):
            sample_texts.append(document[idx].get_text("text") or "")
        combined_sample = "\n".join(sample_texts)

        has_soc2_marker = bool(
            re.search(
                r"\b(soc\s*2|service\s+organization\s+control|trust\s+services\s+criteria)\b",
                combined_sample,
                re.IGNORECASE,
            )
        )
        has_cc_id = bool(re.search(r"\bCC\s*\d+\.\d+\.\d+\b", combined_sample))

        if not (has_soc2_marker or has_cc_id):
            raise ValueError(
                "PDF does not appear to be a SOC 2 report (missing SOC 2 / Trust Services "
                "Criteria markers and CCx.x.x control identifiers in sampled pages)."
            )
    finally:
        document.close()

    return {
        "file_name": pdf_path.name,
        "sha256": sha256,
        "size_bytes": file_size,
        "page_count": page_count,
    }


def trim_leaked_section_header(text: str) -> str:
    """Trim trailing standalone section or framework headers from extracted evidence (B-02)."""
    if not text:
        return ""

    cleaned = text.strip()
    trailing_patterns = [
        r"\n\s*(?:COSO Principle|Trust Services Criteria|Common Criteria|Section \d+|Appendix)\b[^\n]*$",
        r"\n\s*(?:Control Activity Specified(?:\s+by the Service Organization)?|Test Applied(?:\s+by the Service Auditor)?|Test Results|Results of(?:\s+the)?\s+Tests)\s*$",
    ]
    for pattern in trailing_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    return cleaned


def extract_pdf_text(pdf_path: Path):
    """Extract text from every page of the SOC 2 PDF."""
    document = fitz.open(pdf_path)
    pages = []

    try:
        for page_number, page in enumerate(document, start=1):
            pages.append(
                {
                    "page": page_number,
                    "text": page.get_text("text"),
                }
            )
    finally:
        document.close()

    return pages


def extract_control_blocks(pages):
    """Extract individual SOC 2 control rows as evidence blocks."""
    blocks = []

    control_pattern = re.compile(
        r"(CC\s*\d+\.\d+\.\d+)(.*?)(?=CC\s*\d+\.\d+\.\d+|\Z)",
        re.IGNORECASE | re.DOTALL,
    )

    for page in pages:
        page_text = page["text"]
        page_number = page["page"]

        matches = list(control_pattern.finditer(page_text))

        for match in matches:
            control_id = re.sub(r"\s+", "", match.group(1)).upper()
            section_text = trim_leaked_section_header(match.group(2))

            if is_report_narrative(section_text):
                continue

            if len(section_text) < 100:
                continue

            blocks.append(
                {
                    "page": page_number,
                    "control_id": control_id,
                    "evidence": section_text,
                    "audit_evidence": section_text,
                    "raw_block": section_text,
                }
            )

    return blocks


def infer_audit_signal(audit_evidence):
    """Determine the audit result fail-closed from test results and management response."""
    normalized_evidence = normalize_for_matching(audit_evidence)

    has_fail = any(re.search(pattern, normalized_evidence) for pattern in FAIL_PATTERNS)
    has_pass = any(re.search(pattern, normalized_evidence) for pattern in PASS_PATTERNS)

    if has_fail:
        return "exception"

    if has_pass:
        return "no_exception"

    return "unknown"


def build_prompt(evidence, candidates):
    """Build a tightly constrained prompt for the local LLM (B-02)."""
    allowed_ids = list(candidates) if candidates else []
    candidate_text = ", ".join(allowed_ids) if allowed_ids else "NONE"

    none_rule = (
        "3. Return NONE only if none of the allowed requirement IDs applies, or if the "
        "text is purely a table heading, a COSO principle, or unrelated to security and privacy."
        if "NONE" in allowed_ids or not allowed_ids
        else "3. Choose strictly from the allowed requirement IDs above; do not return NONE "
        "unless the text is purely a table heading, a COSO principle, or unrelated to security and privacy."
    )

    return f"""You are a TPRM evidence-mapping assistant.

Map the following SOC 2 control evidence to one internal TPRM requirement
from the allowed list.

Allowed requirement IDs:
{candidate_text}

Rules:
1. Choose only one requirement ID from the allowed list.
2. If the text describes a control tested by the auditor, map it to the most
   relevant requirement in the allowed list.
{none_rule}
4. If the text describes a policy or procedure and the test result says
   "No exceptions noted", treat it as valid control evidence and map it.
5. Do not invent requirement IDs.
6. Do not explain your answer.
7. Return only valid JSON with keys "requirement_id" and "confidence" (a number between 0.0 and 1.0).

Requirement meanings:
- SEC-01: Asset inventory and configuration management
- SEC-02: Logical access and authentication
- SEC-03: Data classification, handling, retention, and disposal
- SEC-04: Encryption and cryptographic key management
- SEC-05: Vulnerability and patch management
- SEC-06: Security monitoring, logging, and alerting
- SEC-07: Network security and segmentation
- SEC-08: Incident response and exception management
- SEC-09: Business continuity and disaster recovery
- SEC-10: Security awareness and training
- PRV-01: Privacy notices and personal-information handling
- PRV-02: Consent and data-subject rights
- PRV-03: Data minimization, retention, and deletion
- PRV-04: Third-party data sharing and transfers
- PRV-05: Privacy contracts and data-processing agreements
- PRV-06: Privacy incidents and breach notification
- GOV-01: Security governance and strategy
- GOV-02: Risk management
- GOV-03: Policies, procedures, and documentation
- GOV-04: Audit, compliance, and regulatory oversight
- PHY-01: Physical security and facility access
- VEN-01: Vendor and third-party risk management
- CHG-01: Change management
- NONE: No listed requirement clearly applies

Evidence:
\"\"\"
{evidence}
\"\"\"

Return JSON in this format:
{{
  "requirement_id": "REQUIREMENT_ID",
  "confidence": 0.85
}}
"""


def call_local_llm(
    prompt,
    failure_log_path: Path | None = None,
    run_id: str = "",
    page: int | None = None,
    control_id: str | None = None,
):
    """Call the local Ollama model and parse its JSON response."""
    call_start = time.perf_counter()

    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            options={
                "temperature": TEMPERATURE,
                "seed": SEED,
                "num_ctx": NUM_CTX,
            },
        )
    except Exception as exc:
        if failure_log_path:
            record_failure(
                failure_log_path=failure_log_path,
                run_id=run_id,
                stage="ollama_chat",
                error_type=type(exc).__name__,
                message=exc,
                page=page,
                control_id=control_id,
            )
        return {"requirement_id": "NONE", "confidence": 0.0}

    call_elapsed = time.perf_counter() - call_start

    if isinstance(response, dict):
        response_data = response
    else:
        response_data = response.model_dump()

    load_seconds = response_data.get("load_duration", 0) / 1_000_000_000
    prompt_tokens = response_data.get("prompt_eval_count", 0)
    prompt_seconds = response_data.get("prompt_eval_duration", 0) / 1_000_000_000
    output_tokens = response_data.get("eval_count", 0)
    output_seconds = response_data.get("eval_duration", 0) / 1_000_000_000

    print(
        "LLM_CALL "
        f"wall={call_elapsed:.1f}s "
        f"load={load_seconds:.1f}s "
        f"prompt_tokens={prompt_tokens} "
        f"prompt_s={prompt_seconds:.1f}s "
        f"output_tokens={output_tokens} "
        f"output_s={output_seconds:.1f}s"
    )

    content = (response_data.get("message") or {}).get("content", "").strip()

    json_match = re.search(r"\{.*\}", content, re.DOTALL)
    if not json_match:
        if failure_log_path:
            record_failure(
                failure_log_path=failure_log_path,
                run_id=run_id,
                stage="llm_json_extract",
                error_type="JSONDecodeError",
                message=f"No JSON object found in LLM output: {content[:200]}",
                page=page,
                control_id=control_id,
            )
        return {"requirement_id": "NONE", "confidence": 0.0}

    try:
        parsed = json.loads(json_match.group(0))
    except json.JSONDecodeError as exc:
        if failure_log_path:
            record_failure(
                failure_log_path=failure_log_path,
                run_id=run_id,
                stage="llm_json_parse",
                error_type=type(exc).__name__,
                message=f"Invalid JSON from LLM: {exc}",
                page=page,
                control_id=control_id,
            )
        return {"requirement_id": "NONE", "confidence": 0.0}

    return parsed if isinstance(parsed, dict) else {"requirement_id": "NONE", "confidence": 0.0}


def apply_expert_disambiguation(
    evidence,
    candidates,
    requirement_id,
    audit_signal,
):
    """Apply narrowly scoped, deterministic disambiguation rules."""
    normalized_evidence = normalize_for_matching(evidence)

    if (
        "GOV-01" in candidates
        and "assigned authorities" in normalized_evidence
        and "security policies" in normalized_evidence
    ):
        return "GOV-01", "Governance authority assignment"

    if (
        "GOV-02" in candidates
        and (
            "risk assessment" in normalized_evidence
            or "risk evaluation process" in normalized_evidence
            or "mitigation strategies" in normalized_evidence
            or "risk treatment" in normalized_evidence
        )
        and (
            "mitigation strategies" in normalized_evidence
            or "mitigation tracking" in normalized_evidence
            or "risk treatment" in normalized_evidence
        )
        and "asset inventory" not in normalized_evidence
    ):
        return "GOV-02", "Risk assessment and mitigation evidence"

    if (
        "GOV-01" in candidates
        and "SEC-10" in candidates
        and "code of conduct" in normalized_evidence
        and (
            "values" in normalized_evidence
            or "behavioral standards" in normalized_evidence
        )
    ):
        return "GOV-01", "Governance values and code-of-conduct evidence"

    if (
        "SEC-02" in candidates
        and "PHY-01" in candidates
        and "authenticate" in normalized_evidence
        and "password" in normalized_evidence
        and "user account" in normalized_evidence
    ):
        return "SEC-02", "Logical authentication and password controls"

    if (
        "SEC-06" in candidates
        and "SEC-08" in candidates
        and "incident response procedure" in normalized_evidence
        and (
            "security event" in normalized_evidence
            or "lessons learned" in normalized_evidence
            or "incident response process" in normalized_evidence
        )
    ):
        return "SEC-06", "Incident-response procedure documentation"

    if (
        candidates == ["SEC-10"]
        and "obligations and responsibilities to comply" in normalized_evidence
        and "security policies" in normalized_evidence
    ):
        return "GOV-02", "Training obligations tied to security-policy compliance"

    if (
        "GOV-02" in candidates
        and "GOV-03" in candidates
        and (
            "risk assessment" in normalized_evidence
            or "risk management" in normalized_evidence
            or "risk identification" in normalized_evidence
            or "business disruptions" in normalized_evidence
        )
    ):
        return (
            "GOV-02",
            "Risk-management evidence preferred over generic policy documentation",
        )

    if (
        "PHY-01" in candidates
        and "SEC-06" in candidates
        and "mantrap" in normalized_evidence
        and "ingress" in normalized_evidence
    ):
        return (
            "PHY-01",
            "Ingress-mantrap physical-access evidence",
        )

    return requirement_id, "No expert disambiguation rule applied"


def infer_block_type(text):
    """Classify SOC 2 block scope as subservice_carveout, cuec, or control_test."""
    normalized = normalize_for_matching(text or "")
    if re.search(
        r"\b(subservice organization|carved out|carve-out|carve out)\b",
        normalized,
    ):
        return "subservice_carveout"
    if re.search(
        r"\b(complementary user entity|cuec|user entity controls)\b",
        normalized,
    ):
        return "cuec"
    return "control_test"


def validate_model_result(
    evidence,
    candidates,
    model_result,
    audit_signal,
):
    """Validate and normalize the LLM result using deterministic rules."""
    safe_result = model_result if isinstance(model_result, dict) else {}
    raw_req = safe_result.get("requirement_id", "NONE")
    requirement_id = (
        raw_req.strip().upper() if isinstance(raw_req, str) and raw_req.strip() else "NONE"
    )
    norm_signal = (audit_signal or "").strip().lower()
    candidate_list = list(candidates or [])

    normalized_evidence = normalize_for_matching(evidence)

    if requirement_id not in VALID_REQUIREMENT_IDS:
        requirement_id = "NONE"

    if not candidate_list:
        return {
            "requirement_id": "NONE",
            "confidence": 0.0,
            "needs_review": True,
            "validation_note": (
                "No keyword candidates available and LLM returned NONE"
                if requirement_id == "NONE"
                else "Rejected LLM requirement selection with no keyword candidates"
            ),
        }

    if requirement_id != "NONE" and requirement_id not in candidate_list:
        requirement_id = "NONE"

    if (
        norm_signal == "exception"
        and "SEC-08" in candidate_list
        and (
            "incident" in normalized_evidence
            or "corrective measure" in normalized_evidence
            or "corrective measures" in normalized_evidence
        )
    ):
        requirement_id = "SEC-08"

    if norm_signal in {"unknown", "exception", "fail"}:
        needs_review = True
    elif requirement_id == "NONE":
        needs_review = True
    elif len(candidate_list) > 1:
        needs_review = True
    else:
        needs_review = False

    if requirement_id == "NONE":
        confidence = 0.0
        validation_note = (
            "No valid candidate mapped; routed to analyst review"
            if needs_review
            else "Mapped to NONE"
        )
    else:
        confidence = 0.9 if len(candidate_list) == 1 else 0.6
        validation_note = "Valid candidate selected"

    return {
        "requirement_id": requirement_id,
        "confidence": confidence,
        "needs_review": needs_review,
        "validation_note": validation_note,
    }


def infer_final_status(audit_signal, requirement_id, needs_review):
    """Convert the audit signal into a normalized final status (B-01)."""
    sig = (audit_signal or "").strip().lower()

    if sig == "fail":
        return "fail"

    if sig == "exception":
        return "partial"

    if sig == "no_exception":
        return "pass"

    return "unknown"


def identify_missing_information(audit_signal, requirement_id):
    """Identify the evidence needed before a reviewer can accept a finding."""
    if requirement_id == "NONE":
        return [
            "Identify the applicable internal requirement or confirm that "
            "no requirement applies."
        ]

    sig = (audit_signal or "").strip().lower()
    if sig in {"exception", "fail"}:
        return [
            "Request exception details and affected systems or locations.",
            "Request compensating controls and remediation status.",
        ]

    if sig == "unknown":
        return [
            "Request the auditor test result and management response.",
        ]

    return []


def write_run_manifest(
    manifest_path: Path,
    run_id: str,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    pdf_meta: dict,
    output_file: Path,
    failure_log_file: Path,
    block_count: int,
    mapped_claims: list[dict],
):
    """Write a structured run manifest alongside output claims (B-12)."""
    unmapped_count = sum(1 for item in mapped_claims if item.get("requirement_id") == "NONE")
    review_count = sum(1 for item in mapped_claims if item.get("needs_review") is True)

    manifest = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(duration_seconds, 2),
        "model": MODEL_NAME,
        "options": {
            "temperature": TEMPERATURE,
            "seed": SEED,
            "num_ctx": NUM_CTX,
        },
        "framework": FRAMEWORK,
        "source_version": SOURCE_VERSION,
        "assessment_date": ASSESSMENT_DATE,
        "input_pdf": pdf_meta,
        "output_claims_file": str(output_file),
        "failure_log_file": str(failure_log_file),
        "counts": {
            "extracted_blocks": block_count,
            "mapped_claims": len(mapped_claims) - unmapped_count,
            "unmapped_claims": unmapped_count,
            "needs_review_claims": review_count,
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Run SOC 2 TPRM evidence mapping.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF_PATH, help="Input SOC 2 PDF path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_FILE, help="Output mapped_claims JSON path")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_FILE, help="Output run manifest JSON path")
    parser.add_argument("--failure-log", type=Path, default=DEFAULT_FAILURE_LOG_FILE, help="Failure JSONL log path")
    return parser.parse_args()


def main():
    args = parse_args()
    run_started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    print("Validating and extracting SOC 2 evidence...")
    try:
        pdf_meta = validate_soc2_pdf(args.pdf)
        pages = extract_pdf_text(args.pdf)
        blocks = extract_control_blocks(pages)
    except Exception as exc:
        record_failure(
            failure_log_path=args.failure_log,
            run_id=run_id,
            stage="pdf_ingest_or_extract",
            error_type=type(exc).__name__,
            message=exc,
        )
        raise

    print(f"Extracted {len(blocks)} candidate evidence blocks.")

    mapped_claims = []

    for index, block in enumerate(blocks, start=1):
        evidence = block["evidence"]
        audit_evidence = block["audit_evidence"]
        page = block["page"]
        control_id = block["control_id"]

        candidates = get_candidate_requirements(evidence)
        audit_signal = infer_audit_signal(audit_evidence)

        prompt = build_prompt(evidence, candidates)
        model_result = call_local_llm(
            prompt,
            failure_log_path=args.failure_log,
            run_id=run_id,
            page=page,
            control_id=control_id,
        )

        validated = validate_model_result(
            evidence,
            candidates,
            model_result,
            audit_signal,
        )

        llm_requirement = model_result.get("requirement_id", "NONE")

        final_requirement = resolve_candidate_conflict(
            evidence,
            candidates,
            validated["requirement_id"],
        )

        final_requirement, disambiguation_note = apply_expert_disambiguation(
            evidence,
            candidates,
            final_requirement,
            audit_signal,
        )

        needs_review = validated["needs_review"]

        if final_requirement == "NONE":
            needs_review = True

        final_status = infer_final_status(
            audit_signal,
            final_requirement,
            needs_review,
        )

        missing_information = identify_missing_information(
            audit_signal,
            final_requirement,
        )

        reviewer_status = (
            "requires_analyst_review"
            if needs_review
            else "ready_for_analyst_review"
        )

        mapped_claims.append(
            {
                "claim_id": f"CLAIM-{index:04d}",
                "block_type": infer_block_type(audit_evidence),
                "framework": FRAMEWORK,
                "source_version": SOURCE_VERSION,
                "assessment_date": ASSESSMENT_DATE,
                "page": page,
                "control_id": control_id,
                "evidence": evidence,
                "evidence_span": evidence,
                "audit_evidence": audit_evidence,
                "candidates": candidates,
                "llm_requirement": llm_requirement,
                "requirement_id": final_requirement,
                "confidence": validated["confidence"],
                "audit_signal": audit_signal,
                "final_status": final_status,
                "needs_review": needs_review,
                "reviewer_status": reviewer_status,
                "validation_note": validated["validation_note"],
                "disambiguation_note": disambiguation_note,
                "missing_information": missing_information,
            }
        )

        print(
            f"[{index}/{len(blocks)}] "
            f"page={page} control={control_id} "
            f"requirement={final_requirement} "
            f"status={final_status} signal={audit_signal}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(mapped_claims, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    finished_at = datetime.now(timezone.utc).isoformat()
    duration_seconds = time.perf_counter() - run_started
    write_run_manifest(
        manifest_path=args.manifest,
        run_id=run_id,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        pdf_meta=pdf_meta,
        output_file=args.output,
        failure_log_file=args.failure_log,
        block_count=len(blocks),
        mapped_claims=mapped_claims,
    )

    print(f"\nSaved {len(mapped_claims)} mapped claims to {args.output}")
    print(f"Saved run manifest to {args.manifest}")


if __name__ == "__main__":
    main()