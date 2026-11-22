"""
Generate a grounded SOC 2 control assessment using Granite and hybrid RAG.

Usage:
python scripts\generate_answer.py CC7.4.4

Retrieves evidence from data/rag_index_v3, sends only that evidence to
granite4:3b, and saves the answer to data/generated_answers.json.

Does not modify mapping artifacts.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import chromadb
import ollama

BASE_DIR = Path(__file__).resolve().parents[1]
INDEX_DIR = BASE_DIR / "data" / "rag_index_v3"
OUTPUT_FILE = BASE_DIR / "data" / "generated_answers.json"

EMBEDDING_MODEL = "mxbai-embed-large:latest"
GENERATION_MODEL = "granite4:3b"
COLLECTION_NAME = "equinix_soc2_rag_v3"


def normalize_control_id(value):
    return str(value or "").strip().upper()


def retrieve_evidence(control_id):
    client = chromadb.PersistentClient(
        path=str(INDEX_DIR)
    )

    collection = client.get_collection(
        name=COLLECTION_NAME
    )

    exact = collection.get(
        where={"control_id": control_id},
        include=["documents", "metadatas"],
    )

    if not exact["ids"]:
        raise ValueError(
            f"No evidence found for control {control_id}"
        )

    evidence_blocks = []

    for metadata, document in zip(
        exact["metadatas"],
        exact["documents"],
    ):
        evidence_blocks.append(
            {
                "page": metadata["page"],
                "text": document,
            }
        )

    return evidence_blocks


def build_prompt(control_id, evidence_blocks):
    evidence_text = "\n\n".join(
        f"[Page {block['page']}]\n{block['text']}"
        for block in evidence_blocks
    )

    return f"""You are a SOC 2 control assessment assistant.

Use ONLY the evidence below. Do not use outside knowledge.
Do not invent facts, controls, pages, or test results.

Control ID: {control_id}

Evidence:
{evidence_text}

Return your response in exactly this format:

CONTROL ID: {control_id}

ASSESSMENT:
Write 2-4 concise sentences describing what the evidence shows.

EXCEPTIONS:
Write "None identified in retrieved evidence" if no exception appears.
Otherwise, state the exception factually.

PAGE CITATIONS:
List only the page numbers that contain the evidence used.
"""


def generate_answer(control_id, evidence_blocks):
    prompt = build_prompt(
        control_id,
        evidence_blocks,
    )

    response = ollama.chat(
        model=GENERATION_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        options={
            "temperature": 0.0,
            "num_predict": 500,
        },
    )

    return response["message"]["content"]


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python scripts\\generate_answer.py CC7.4.4"
        )

    control_id = normalize_control_id(sys.argv[1])

    evidence_blocks = retrieve_evidence(control_id)

    answer = generate_answer(
        control_id,
        evidence_blocks,
    )

    record = {
        "control_id": control_id,
        "generation_model": GENERATION_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "retrieval_mode": "hybrid_exact_control_id",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "evidence_pages": [
            block["page"]
            for block in evidence_blocks
        ],
        "evidence": evidence_blocks,
        "answer": answer,
    }

    existing = []

    if OUTPUT_FILE.exists():
        existing = json.loads(
            OUTPUT_FILE.read_text(encoding="utf-8")
        )

    existing = [
        item
        for item in existing
        if item["control_id"] != control_id
    ]

    existing.append(record)

    OUTPUT_FILE.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Control: {control_id}")
    print(f"Model: {GENERATION_MODEL}")
    print(f"Evidence pages: {record['evidence_pages']}")
    print()
    print(answer)
    print()
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()