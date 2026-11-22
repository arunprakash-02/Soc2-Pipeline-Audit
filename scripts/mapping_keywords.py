"""
Shared keyword, normalization, candidate-matching, and conflict-resolution
logic for the TPRM evidence-mapping pipeline.
"""

import re


REQUIREMENT_KEYWORDS = {
    "SEC-01": [
        "asset inventory",
        "asset management",
        "hardware inventory",
        "software inventory",
        "asset register",
        "configuration management database",
        "cmdb",
        "inventory of assets",
    ],
    "SEC-02": [
        "logical access",
        "access control",
        "access management",
        "user access",
        "privileged access",
        "least privilege",
        "role-based access",
        "multi-factor authentication",
        "multifactor authentication",
        "mfa",
        "two-factor authentication",
        "2fa",
        "password",
        "authentication",
        "authorization",
        "access review",
        "access recertification",
        "account provisioning",
        "account deprovisioning",
        "account termination",
        "background check",
        "background checks",
        "background and reference check",
        "background and reference checks",
    ],
    "SEC-03": [
        "data classification",
        "data handling",
        "data retention",
        "data disposal",
        "data destruction",
        "secure deletion",
        "media sanitization",
        "data loss prevention",
        "dlp",
        "encryption at rest",
        "encryption in transit",
        "data protection",
        "asset removal and disposal",
        "securely wiped",
	"confidential information",
        "nondisclosure agreement",
	"confidential or proprietary",
    ],
    "SEC-04": [
        "encryption",
        "encrypted",
        "cryptography",
        "cryptographic",
        "key management",
        "encryption key",
        "tls",
        "transport layer security",
        "ssl",
        "secure sockets layer",
        "certificate",
        "digital certificate",
        "hashing",
        "hash",
    ],
    "SEC-05": [
        "vulnerability management",
        "vulnerability scanning",
        "vulnerability assessment",
        "penetration test",
        "penetration testing",
        "security patch",
        "patch management",
        "patching",
        "software update",
        "security update",
        "vulnerability remediation",
    ],
    "SEC-06": [
        "security monitoring",
        "log monitoring",
        "log management",
        "audit log",
        "audit logging",
        "system logging",
        "security event",
        "security incident",
        "intrusion detection",
        "intrusion prevention",
        "ids",
        "ips",
        "siem",
        "alert",
        "anomaly",
        "monitoring",
        "incident response procedures",
        "incident management policies",
        "incident ticket",
	"emerging technologies and threats",
        "security impact",
    ],
    "SEC-07": [
        "firewall",
        "firewalls",
        "network segmentation",
        "segmentation",
        "network security",
        "network device",
        "network configuration",
        "network traffic",
        "vpn",
        "virtual private network",
        "perimeter",
        "intrusion detection",
        "intrusion prevention",
        "ids",
        "ips",
    ],
    "SEC-08": [
        "incident response",
        "security incident",
        "incident response plan",
        "incident response procedure",
        "incident response team",
        "incident management",
        "incident identification",
        "incident reporting",
        "incident escalation",
        "incident notification",
        "incident communication",
        "incident classification",
        "incident severity",
        "post incident review",
        "lessons learned",
        "root cause analysis",
        "security incident response",
        "incident containment",
        "incident remediation",
        "incident closure",
    ],
    "SEC-09": [
        "business continuity",
        "disaster recovery",
        "backup",
        "backups",
        "backup and recovery",
        "data backup",
        "restore",
        "recovery time objective",
        "rto",
        "recovery point objective",
        "rpo",
        "failover",
        "redundancy",
    ],
    "SEC-10": [
        "security awareness",
        "security awareness training",
        "security training",
        "security education",
        "employee training",
        "personnel training",
        "phishing",
        "social engineering",
        "acceptable use",
        "code of conduct",
    ],
    "PRV-01": [
        "privacy notice",
        "privacy policy",
        "personal information",
        "personal data",
        "personally identifiable information",
        "pii",
        "data subject",
        "data collection",
    ],
    "PRV-02": [
        "consent",
        "opt in",
        "opt-in",
        "opt out",
        "opt-out",
        "privacy preference",
        "data subject rights",
        "right to access",
        "right to deletion",
        "right to erasure",
    ],
    "PRV-03": [
        "data minimization",
        "purpose limitation",
        "data retention",
        "retention period",
        "data disposal",
        "data deletion",
    ],
    "PRV-04": [
        "subprocessor",
        "sub processor",
        "sub-processor",
        "data sharing",
        "data transfer",
        "cross-border transfer",
        "personal information transfer",
        "personal data transfer",
        "privacy third party",
    ],
    "PRV-05": [
        "data processing agreement",
        "dpa",
        "privacy agreement",
        "contractual privacy",
        "privacy obligations",
        "privacy requirements",
    ],
    "PRV-06": [
        "privacy incident",
        "data breach",
        "breach notification",
        "personal data breach",
        "privacy breach",
        "notification requirement",
    ],
    "GOV-01": [
        "governance",
        "governance framework",
        "information security program",
        "security program",
        "security strategy",
        "security objectives",
        "management commitment",
        "board",
        "senior management",
        "executive management",
        "risk appetite",
        "strategic planning",
        "code of conduct",
    ],
    "GOV-02": [
        "risk assessment",
        "risk management",
        "risk register",
        "risk identification",
        "risk analysis",
        "risk evaluation",
        "risk treatment",
        "risk mitigation",
        "risk acceptance",
        "risk tolerance",
        "annual risk assessment",
        "threat and risk",
        "risk evaluation process",
    ],
    "GOV-03": [
        "policy document",
        "policy and procedure",
        "policies and procedures",
        "standard operating procedure",
        "standard operating procedures",
        "procedure document",
        "documented procedure",
        "documented process",
        "documented control",
        "management approval",
        "review and approval",
        "policy review",
        "procedure review",
	"internal control performance metrics",
        "performance metrics dashboard",
    ],
    "GOV-04": [
        "internal audit",
        "internal audit program",
        "independent assessment",
        "compliance assessment",
        "compliance review",
        "regulatory compliance",
        "legal requirement",
        "regulatory requirement",
        "regulatory examination",
    ],
    "PHY-01": [
        "physical security",
        "physical access",
        "physical access control",
        "data center",
        "data centre",
        "facility",
        "premises",
        "visitor",
        "visitors",
        "visitor access",
        "badge",
        "access card",
        "access badge",
        "security guard",
        "security officer",
        "surveillance",
        "cctv",
        "camera",
        "locked",
        "lock",
        "entry point",
        "physical entry",
    ],
    "VEN-01": [
        "vendor",
        "vendors",
        "third party",
        "third-party",
        "supplier",
        "service provider",
        "outsourcing",
        "vendor risk",
        "vendor management",
        "vendor assessment",
        "vendor due diligence",
    ],
    "CHG-01": [
        "change management",
        "change control",
        "change request",
        "change approval",
        "change authorization",
        "change testing",
        "change deployment",
        "change implementation",
        "configuration change",
        "system change",
	"change review meeting",
        "approved prior to implementation",
    ],
}


def normalize_for_matching(text):
    """Normalize text for deterministic keyword matching."""
    if not text:
        return ""

    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def keyword_matches(keyword, normalized_text):
    """Return True when a keyword appears as a whole word or phrase."""
    if not keyword or not normalized_text:
        return False

    keyword = normalize_for_matching(keyword)
    normalized_text = normalize_for_matching(normalized_text)

    if not keyword or not normalized_text:
        return False

    keyword_tokens = keyword.split()

    if not keyword_tokens:
        return False

    escaped_tokens = []

    for index, token in enumerate(keyword_tokens):
        escaped_token = re.escape(token)

        if index == len(keyword_tokens) - 1:
            escaped_token += r"s?"

        escaped_tokens.append(escaped_token)

    pattern = (
        r"(?<![a-z0-9])"
        + r"[\s-]+".join(escaped_tokens)
        + r"(?![a-z0-9])"
    )

    return bool(re.search(pattern, normalized_text))


def get_candidate_requirements(text, minimum_matches=1):
    """Return requirement IDs whose keywords match the supplied text."""
    normalized_text = normalize_for_matching(text)
    candidates = []

    if not normalized_text:
        return candidates

    for requirement_id, keywords in REQUIREMENT_KEYWORDS.items():
        matches = sum(
            1
            for keyword in keywords
            if keyword_matches(keyword, normalized_text)
        )

        if matches >= minimum_matches:
            candidates.append(requirement_id)

    return candidates


def rank_candidates(text, candidates):
    """Rank candidate requirements by number of keyword matches."""
    normalized_text = normalize_for_matching(text)

    ranked = []

    for candidate in candidates:
        keywords = REQUIREMENT_KEYWORDS.get(candidate, [])

        matches = sum(
            1
            for keyword in keywords
            if keyword_matches(keyword, normalized_text)
        )

        ranked.append(
            {
                "requirement_id": candidate,
                "matches": matches,
            }
        )

    ranked.sort(
        key=lambda item: item["matches"],
        reverse=True,
    )

    return ranked


def is_framework_header(text):
    """Identify framework, principle, and section headers."""
    normalized_text = normalize_for_matching(text)

    if not normalized_text:
        return False

    header_patterns = [
        r"^coso principle\b",
        r"^trust services criteria\b",
        r"^common criteria\b",
        r"^cc\d+\b",
        r"^section \d+\b",
        r"^appendix\b",
    ]

    return any(
        re.match(pattern, normalized_text)
        for pattern in header_patterns
    )


def is_extractor_artifact(text):
    """Identify standalone PDF extraction artifacts."""
    normalized_text = normalize_for_matching(text)

    artifact_patterns = [
        r"^control activity specified by the service organization$",
        r"^control activity specified$",
        r"^test applied$",
        r"^test applied by the service auditor$",
        r"^test results$",
        r"^results of tests$",
        r"^results of the tests$",
        r"^change management$",
        r"^logical access$",
        r"^physical access$",
        r"^system operations$",
    ]

    return any(
        re.match(pattern, normalized_text)
        for pattern in artifact_patterns
    )


def is_report_narrative(text):
    """Identify report narrative that should not be treated as evidence."""
    normalized_text = normalize_for_matching(text)

    narrative_patterns = [
        r"^coso principle",
        r"^trust services criteria",
        r"^description of",
        r"^management assertion",
        r"^management s assertion",
        r"^in line with",
        r"^the service organization",
        r"^the service auditor",
        r"^our examination",
        r"^we examined",
        r"^we tested",
        r"^our tests",
        r"^the tests",
        r"^in our opinion",
        r"^basis for opinion",
        r"^scope of examination",
    ]

    return any(
        re.search(pattern, normalized_text)
        for pattern in narrative_patterns
    )


PHYSICAL_SECURITY_HINTS = [
    "data center",
    "data centre",
    "physical access",
    "visitor",
    "visitors",
    "badge",
    "access card",
    "security guard",
    "surveillance",
    "cctv",
    "camera",
    "locked",
    "lock",
    "facility",
    "premises",
    "entry point",
    "physical security",
]

NETWORK_SECURITY_HINTS = [
    "firewall",
    "network segmentation",
    "segmentation",
    "intrusion detection",
    "intrusion prevention",
    "ids",
    "ips",
    "vpn",
    "network device",
    "network configuration",
    "network traffic",
]


def resolve_candidate_conflict(text, candidates, llm_choice):
    """Apply deterministic tie-breaks for known ambiguous mappings."""
    normalized_text = normalize_for_matching(text)

    physical_hits = sum(
        1
        for keyword in PHYSICAL_SECURITY_HINTS
        if keyword in normalized_text
    )

    network_hits = sum(
        1
        for keyword in NETWORK_SECURITY_HINTS
        if keyword in normalized_text
    )

    if (
        "PHY-01" in candidates
        and "SEC-07" in candidates
        and physical_hits > network_hits
    ):
        return "PHY-01"

    if (
        "SEC-07" in candidates
        and "PHY-01" in candidates
        and network_hits > physical_hits
    ):
        return "SEC-07"

    return llm_choice