# 🛡️ ThirdRisk: Local-First TPRM Automation Pipeline

An end-to-end, local-first Third-Party Risk Management (TPRM) workbench that ingests vendor SOC 2 Type II PDFs, extracts control-level evidence, maps it to internal security requirements, and provides a human-in-the-loop interface for risk sign-off.

Built to run entirely on standard laptop hardware (CPU/Integrated GPU) without relying on expensive cloud APIs or compromising data privacy.

## 📌 The Problem

Manual TPRM reviews are slow, inconsistent, and unauditable. A standard SOC 2 report is 80–150 pages of dense legal and technical text. Analysts must manually search for evidence, map auditor controls (e.g., `CC7.4.4`) to internal policies, and catch documented exceptions hidden in the fine print. 

Off-the-shelf GRC tools (like Vanta or Drata) automate the *workflow* of collecting documents, but they rarely audit the *document itself*. They rely on the vendor's claims, leaving companies vulnerable to "false passes" when a vendor's SOC 2 explicitly notes a control exception.

## 🚀 The Solution

**ThirdRisk** is a deep-document analysis engine. It acts as an AI-assisted auditor, combining deterministic parsing with local LLMs to extract, classify, and validate risk evidence with page-level provenance. 

It does not just generate a score; it generates a **defensible audit trail**.

### Key Capabilities
*   **Hybrid Retrieval (96.8% Baseline Accuracy):** Combines exact control-ID matching, deterministic keyword shortlisting, and semantic vector search (`mxbai-embed-large`) to ensure the LLM only chooses from highly relevant candidate requirements.
*   **Deterministic Audit Guardrails:** A regex-based reconciliation layer that overrides the LLM. If the auditor wrote "exception noted," Python forces the status to `PARTIAL` and flags it for human review—preventing the AI from hallucinating a "pass."
*   **Document Intelligence:** Utilizes `PyMuPDF` to deterministically segment control blocks, preserving page numbers and exact evidence text without LLM interference.
*   **Human-in-the-Loop Workbench:** A Streamlit-based enterprise UI (Enterprise Console, Audit Workspace, and GRC Dashboard) where analysts can inspect highlighted PDF evidence, review AI drafts, record rationale, and lock decisions.
*   **100% Local Execution:** Powered by Ollama (`granite4:3b` for mapping, `qwen2.5:1.5b` for fast tasks). No data leaves your machine.

## 🏗️ Architecture

The pipeline consists of five distinct stages:

1. **Extraction:** `PyMuPDF` extracts text blocks and isolates `CCx.x.x` control rows.
2. **Hybrid Retrieval:** A deterministic keyword table + exact control-ID matching + `mxbai-embed-large` semantic embeddings generate a shortlist of 2–6 candidate requirements.
3. **LLM Mapping:** A local LLM (`granite4:3b`) is constrained to select exactly one requirement from the shortlist, using a strict JSON schema.
4. **Audit-Signal Reconciliation:** Python regex scans the auditor's test results. If it detects "exception," it overrides the LLM's status and forces a `needs_review` flag.
5. **Rule Engine & UI:** Claims are aggregated into 23 internal requirements (Security, Privacy, Governance), scored based on domain weights, and rendered in the Streamlit workbench for analyst sign-off.

## 📊 Evaluation (Equinix SOC 2 Type II)

Tested against a 125-claim gold standard hand-labeled by a TPRM analyst:

| Metric | Score |
| :--- | :--- |
| **Mapping Baseline** | 121 / 125 (96.8%) |
| **In-Scope Mapping Accuracy** | 121 / 121 (100.0%) |
| **LLM Selection Errors** | 0 |
| **RAG Hybrid Retrieval** | 121 / 121 (100.0%) |
| **Answer Generation (3/3 sampled)** | Grounded & Correct |

*Note: The 4 unmapped claims were narrative sections (COSO principles) correctly identified as out-of-scope by the pipeline.*

## 💻 Tech Stack

*   **Frontend:** Streamlit (Custom CSS, Plotly, Native row-selection state management)
*   **AI Engine:** Ollama (`granite4:3b`, `qwen2.5:1.5b`, `mxbai-embed-large`)
*   **Document Parsing:** PyMuPDF (`fitz`)
*   **Data Processing:** Python, Pandas
*   **Storage:** JSON (Local-first, easily swappable to SQLite)

## ⚙️ How to Run Locally

### 1. Prerequisites
*   Python 3.11+
*   [Ollama](https://ollama.com/) installed and running.

### 2. Install Dependencies
```bash
git clone https://github.com/yourusername/thirdrisk.git
cd thirdrisk
python -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate
pip install -r requirements.txt