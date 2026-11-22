import sqlite3
from pathlib import Path

DB = Path("data/demo.db")
SCHEMA = Path("src/schema.sql")

if DB.exists():
    DB.unlink()
    print(f"Removed existing {DB}")

conn = sqlite3.connect(DB)
conn.executescript(SCHEMA.read_text())
print(f"Schema created: {DB}")

# --- 12 vendors (4 fully assessed, 8 triage-only) ---
vendors = [
    ("EQ",      "Equinix, Inc.",                    "real",      1, "Real SOC 2 Type II 2022 (Schellman)"),
    ("FR",      "Frappe Technologies",              "real",      0, "Real SOC 2 Type II 2025"),
    ("VB",      "Vendor B (synthetic)",             "synthetic", 0, "Missing/expired evidence scenario"),
    ("VC",      "Vendor C (synthetic)",             "synthetic", 0, "Conflicting statements scenario"),
    ("T05",     "Cloud Infra Co. (synthetic)",      "synthetic", 1, "Triage only"),
    ("T06",     "Payroll HCM Co. (synthetic)",      "synthetic", 1, "Triage only"),
    ("T07",     "Health Data Aggregator (synthetic)","synthetic", 0, "Triage only"),
    ("T08",     "Payment Processor Co. (synthetic)","synthetic", 1, "Triage only"),
    ("T09",     "Managed Security Co. (synthetic)", "synthetic", 0, "Triage only"),
    ("T10",     "Marketing Analytics SaaS (synthetic)","synthetic", 0, "Triage only"),
    ("T11",     "Data Enrichment Co. (synthetic)",  "synthetic", 0, "Triage only"),
    ("T12",     "Low-Risk SaaS Co. (synthetic)",    "synthetic", 0, "Triage only"),
]
conn.executemany(
    "INSERT INTO vendors (vendor_id, legal_name, evidence_source, financial_data, notes) VALUES (?,?,?,?,?)",
    vendors,
)

# --- 4 services for the fully-assessed vendors ---
services = [
    ("EQ-GDCS",   "EQ", "Global Data Center Housing Services", 1,
     '["production","remote","privileged"]',
     '["confidential","regulated"]',
     '["gdpr","ccpa"]',
     '["US","GB","DE","NL","JP","SG","BR","AU","CA","FR"]'),
    ("FR-ERP",    "FR", "ERPNext Cloud", 2,
     '["production","remote"]',
     '["confidential"]',
     '["gdpr"]',
     '["IN","GB","DE"]'),
    ("VB-SAAS",   "VB", "Vendor B SaaS", 2,
     '["production","remote"]',
     '["pii","confidential"]',
     '["gdpr","ccpa"]',
     '["US"]'),
    ("VC-SAAS",   "VC", "Vendor C SaaS", 2,
     '["production","remote"]',
     '["pii","confidential"]',
     '["gdpr","ccpa"]',
     '["US","DE"]'),
]
conn.executemany(
    "INSERT INTO services (service_id, vendor_id, name, criticality_tier, scope_json, data_classes, regimes, jurisdictions) VALUES (?,?,?,?,?,?,?,?)",
    services,
)

# --- Equinix SOC 2 document record ---
conn.execute(
    "INSERT INTO documents (doc_id, service_id, doc_type, filename, sha256, scope_services, valid_from, valid_to, allow_external_model, parsed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
    ("EQ-SOC2-2022", "EQ-GDCS", "soc2", "equinix_soc2.pdf",
     "4CE1F7F2DB383896D1B1C15D846B9D3A326F4A67D8EA3D516B23D1AE2F5D6E53",
     '["EQ-GDCS"]', "2022-11-01", "2023-10-31", 0, None)
)

conn.commit()

# --- Verify counts ---
print("\n--- Verification ---")
for table in ["vendors","services","documents","claims","assessments","findings","audit_events"]:
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table:15s} {n:4d} rows")

conn.close()
print("\nDone.")
