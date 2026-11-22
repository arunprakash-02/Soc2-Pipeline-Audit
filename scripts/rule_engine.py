"""
Aggregate mapped SOC 2 claims into TPRM requirement results, domain scores,
coverage metrics, and a vendor risk assessment.
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
CLAIMS_FILE = BASE_DIR / "data" / "mapped_claims.json"
ASSESSMENT_FILE = BASE_DIR / "data" / "risk_assessment.json"

CLAIM_STATUS_WEIGHTS = {
    "pass": 1.0,
    "partial": 0.5,
    "unknown": 0.0,
    "fail": 0.0,
}

REVIEW_ADJUSTMENT = 0.8

DOMAIN_WEIGHTS = {
    "Security": 0.5,
    "Privacy": 0.25,
    "Governance": 0.25,
}

REQUIREMENTS = {
    "SEC-01": {
        "name": "Asset inventory and configuration management",
        "domain": "Security",
    },
    "SEC-02": {
        "name": "Logical access and authentication",
        "domain": "Security",
    },
    "SEC-03": {
        "name": "Data classification, handling, retention, and disposal",
        "domain": "Security",
    },
    "SEC-04": {
        "name": "Encryption and cryptographic key management",
        "domain": "Security",
    },
    "SEC-05": {
        "name": "Vulnerability and patch management",
        "domain": "Security",
    },
    "SEC-06": {
        "name": "Security monitoring, logging, and alerting",
        "domain": "Security",
    },
    "SEC-07": {
        "name": "Network security and segmentation",
        "domain": "Security",
    },
    "SEC-08": {
        "name": "Incident response and exception management",
        "domain": "Security",
    },
    "SEC-09": {
        "name": "Business continuity and disaster recovery",
        "domain": "Security",
    },
    "SEC-10": {
        "name": "Security awareness and training",
        "domain": "Security",
    },
    "PRV-01": {
        "name": "Privacy notice and personal data transparency",
        "domain": "Privacy",
    },
    "PRV-02": {
        "name": "Consent and data subject rights",
        "domain": "Privacy",
    },
    "PRV-03": {
        "name": "Data minimization, retention, and disposal",
        "domain": "Privacy",
    },
    "PRV-04": {
        "name": "Third-party data sharing and transfers",
        "domain": "Privacy",
    },
    "PRV-05": {
        "name": "Data processing agreements and privacy obligations",
        "domain": "Privacy",
    },
    "PRV-06": {
        "name": "Privacy incident and breach notification",
        "domain": "Privacy",
    },
    "GOV-01": {
        "name": "Security governance and strategy",
        "domain": "Governance",
    },
    "GOV-02": {
        "name": "Risk management",
        "domain": "Governance",
    },
    "GOV-03": {
        "name": "Policies, procedures, and documentation",
        "domain": "Governance",
    },
    "GOV-04": {
        "name": "Audit, compliance, and regulatory oversight",
        "domain": "Governance",
    },
    "PHY-01": {
        "name": "Physical security and facility access",
        "domain": "Governance",
    },
    "VEN-01": {
        "name": "Vendor and third-party risk management",
        "domain": "Governance",
    },
    "CHG-01": {
        "name": "Change management",
        "domain": "Governance",
    },
}


def normalize_status(status):
    """Normalize claim status values."""
    value = str(status or "").strip().lower()

    if value in {"pass", "passed", "effective"}:
        return "pass"

    if value in {"partial", "partially effective", "exception"}:
        return "partial"

    if value in {"fail", "failed", "not effective"}:
        return "fail"

    return "unknown"


def evaluate_requirement(requirement_id, claims):
    """Evaluate one requirement using its mapped claims."""
    matched = [
        claim
        for claim in claims
        if claim.get("requirement_id") == requirement_id
    ]

    statuses = [
        normalize_status(claim.get("final_status"))
        for claim in matched
    ]

    pass_count = statuses.count("pass")
    partial_count = statuses.count("partial")
    fail_count = statuses.count("fail")
    unknown_count = statuses.count("unknown")

    review_count = sum(
        1
        for claim in matched
        if claim.get("needs_review") is True
    )

    weighted_points = 0.0

    for claim, status in zip(matched, statuses):
        base_score = CLAIM_STATUS_WEIGHTS.get(status, 0.0)

        if status == "pass" and claim.get("needs_review") is True:
            base_score *= REVIEW_ADJUSTMENT

        weighted_points += base_score

    score = weighted_points / len(matched) * 100 if matched else 0.0

    if fail_count:
        state = "CONTROL_FAILURE"
        action = (
            "Request remediation evidence, root-cause analysis, "
            "and management response."
        )

    elif partial_count:
        state = "PARTIALLY_SUPPORTED"
        action = (
            "Request exception details, compensating controls, "
            "and remediation evidence."
        )

    elif matched and review_count:
        state = "SUPPORTED_WITH_REVIEW"
        action = "Analyst review required before accepting evidence."

    elif matched:
        state = "SUPPORTED"
        action = "No additional evidence required for this requirement."

    else:
        state = "NOT_EVIDENCED"
        action = (
            "Request vendor evidence or policy documentation."
        )

    return {
        "requirement_id": requirement_id,
        "name": REQUIREMENTS[requirement_id]["name"],
        "domain": REQUIREMENTS[requirement_id]["domain"],
        "state": state,
        "score": round(score, 1),
        "claim_count": len(matched),
        "pass_count": pass_count,
        "partial_count": partial_count,
        "fail_count": fail_count,
        "unknown_count": unknown_count,
        "review_count": review_count,
        "action": action,
    }


def calculate_domain_scores(results):
    """Calculate weighted domain scores from requirement results."""
    domain_scores = {}

    for domain in ["Security", "Privacy", "Governance"]:
        domain_results = [
            result
            for result in results.values()
            if result["domain"] == domain
        ]

        if not domain_results:
            domain_scores[domain] = 0.0
            continue

        domain_scores[domain] = round(
            sum(result["score"] for result in domain_results)
            / len(domain_results),
            1,
        )

    return domain_scores


def calculate_overall_score(domain_scores):
    """Calculate the weighted overall vendor score."""
    weighted_total = sum(
        domain_scores.get(domain, 0.0) * weight
        for domain, weight in DOMAIN_WEIGHTS.items()
    )

    total_weight = sum(DOMAIN_WEIGHTS.values())

    return round(weighted_total / total_weight, 1)


def calculate_risk_tier(score):
    """Convert the overall score into a risk tier."""
    if score >= 85:
        return "Low Risk (Tier 1)"

    if score >= 70:
        return "Medium Risk (Tier 2)"

    if score >= 50:
        return "Medium Risk (Tier 3)"

    return "High Risk (Tier 4)"


def calculate_coverage(claims, results):
    """Calculate evidence coverage and unmapped-claim metrics."""
    mapped_claims = [
        claim
        for claim in claims
        if claim.get("requirement_id") != "NONE"
    ]

    unmapped_claims = [
        claim
        for claim in claims
        if claim.get("requirement_id") == "NONE"
    ]

    review_claims = [
        claim
        for claim in claims
        if claim.get("needs_review") is True
    ]

    mapped_count = len(mapped_claims)
    total_count = len(claims)

    coverage_ratio = (
        mapped_count / total_count
        if total_count
        else 0.0
    )

    evidenced_requirements = [
        requirement_id
        for requirement_id, result in results.items()
        if result["claim_count"] > 0
    ]

    return {
        "total_claim_count": total_count,
        "mapped_claim_count": mapped_count,
        "unmapped_claim_count": len(unmapped_claims),
        "review_claim_count": len(review_claims),
        "coverage_ratio": round(coverage_ratio, 3),
        "evidenced_requirement_count": len(evidenced_requirements),
        "total_requirement_count": len(results),
        "evidenced_requirement_ids": evidenced_requirements,
    }


def build_memo(assessment, results):
    """Build a plain-text analyst memo."""
    lines = []
    lines.append("VENDOR RISK ASSESSMENT MEMO")
    lines.append("=" * 60)
    lines.append(f"Vendor: {assessment['vendor']}")
    lines.append(
        f"Overall score: {assessment['overall_score']}/100"
    )
    lines.append(f"Risk tier: {assessment['risk_tier']}")
    lines.append("")

    coverage = assessment["coverage"]

    lines.append(
        f"Equinix has {len(coverage['evidenced_requirement_ids'])} "
        "requirement area(s) with evidence."
    )

    unmapped_count = coverage["unmapped_claim_count"]

    if unmapped_count:
        lines.append(
            f"{unmapped_count} claim(s) remain unmapped and require "
            "analyst review."
        )

    lines.append("")
    lines.append("REQUIREMENT RESULTS")
    lines.append("-" * 60)

    for requirement_id, result in results.items():
        lines.append(
            f"{requirement_id}: {result['state']} | "
            f"score={result['score']} | "
            f"claims={result['claim_count']} | "
            f"review={result['review_count']}"
        )
        lines.append(f"  Finding: {result['action']}")
        lines.append("")

    return "\n".join(lines)


def main():
    if not CLAIMS_FILE.exists():
        raise FileNotFoundError(
            f"Mapped claims file not found: {CLAIMS_FILE}"
        )

    claims = json.loads(
        CLAIMS_FILE.read_text(encoding="utf-8")
    )

    results = {
        requirement_id: evaluate_requirement(requirement_id, claims)
        for requirement_id in REQUIREMENTS
    }

    domain_scores = calculate_domain_scores(results)
    overall_score = calculate_overall_score(domain_scores)
    risk_tier = calculate_risk_tier(overall_score)
    coverage = calculate_coverage(claims, results)

    assessment = {
        "vendor": "Equinix",
        "source_document": str(CLAIMS_FILE),
        "overall_score": overall_score,
        "risk_tier": risk_tier,
        "coverage": coverage,
        "domain_scores": domain_scores,
        "requirement_results": results,
    }

    ASSESSMENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    ASSESSMENT_FILE.write_text(
        json.dumps(assessment, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("--- TPRM RULE ENGINE ---")
    print()

    for requirement_id, result in results.items():
        print(
            f"{requirement_id}: {result['state']:<22} | "
            f"score={result['score']:>5.1f} | "
            f"claims={result['claim_count']:>3} | "
            f"pass={result['pass_count']:>3} | "
            f"partial={result['partial_count']:>2} | "
            f"fail={result['fail_count']:>2} | "
            f"review={result['review_count']:>2}"
        )
        print(f"      {result['action']}")
        print()

    print("--- EVIDENCE COVERAGE ---")
    print(
        f"Mapped claims: {coverage['mapped_claim_count']} / "
        f"{coverage['total_claim_count']} "
        f"({coverage['coverage_ratio'] * 100:.1f}%)"
    )
    print(
        f"Unmapped claims requiring review: "
        f"{coverage['unmapped_claim_count']}"
    )
    print(
        f"Requirements with evidence: "
        f"{coverage['evidenced_requirement_count']} / "
        f"{coverage['total_requirement_count']}"
    )
    print()

    print("--- DOMAIN SCORES ---")

    for domain, score in domain_scores.items():
        print(f"{domain}: {score}/100")

    print()
    print(f"Overall score: {overall_score}/100")
    print(f"Vendor tier: {risk_tier}")
    print()
    print(f"Saved assessment to: {ASSESSMENT_FILE}")
    print()
    print(build_memo(assessment, results))


if __name__ == "__main__":
    main()