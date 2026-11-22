"""
Build a control-aware RAG corpus from the Equinix SOC 2 PDF.

Each chunk groups:
- SOC 2 control ID and description
- Service organization control activity
- Service auditor test applied
- Service auditor test result
- Management response, when directly associated with the control

Stops accumulation at appendix and privacy-statement boundaries.
Creates data/rag_corpus_v2.json.
Does not modify existing mapping artifacts or data/rag_corpus.json.
"""

import json
import re
from pathlib import Path

import fitz

BASE_DIR = Path(__file__).resolve().parents[1]
PDF_FILE = BASE_DIR / "data" / "raw" / "equinix_soc2.pdf"
OUTPUT_FILE = BASE_DIR / "data" / "rag_corpus_v2.json"

CONTROL_PATTERN = re.compile(
    r"\b(CC\d+(?:\.\d+)*)\b",
    flags=re.IGNORECASE,
)

STOP_MARKERS = [
    "EQUINIX’S GLOBAL DATA PRIVACY POSITIONING STATEMENT",
    "EQUINIX'S GLOBAL DATA PRIVACY POSITIONING STATEMENT",
    "GLOBAL DATA PRIVACY POSITIONING STATEMENT",
]

MAX_CHUNK_CHARS = 4000
MIN_CHUNK_CHARS = 80


def is_stop_marker(text):
    normalized_text = str(text or "").lower()

    return any(
        marker.lower() in normalized_text
        for marker in STOP_MARKERS
    )


def extract_pdf_blocks(pdf_path):
    document = fitz.open(pdf_path)

    blocks = []

    for page_number, page in enumerate(document, start=1):
        raw_blocks = page.get_text("blocks")

        for block_index, block in enumerate(raw_blocks):
            text = " ".join(
                str(part).strip()
                for part in block[4].splitlines()
                if str(part).strip()
            )

            if text:
                blocks.append(
                    {
                        "page": page_number,
                        "block_index": block_index,
                        "text": text,
                    }
                )

    document.close()
    return blocks


def build_control_chunks(blocks):
    chunks = []

    current_control_id = None
    current_buffer = []
    current_buffer_page = None

    def flush():
        nonlocal current_buffer
        nonlocal current_buffer_page

        if current_control_id and current_buffer:
            text = "\n".join(current_buffer).strip()

            if len(text) >= MIN_CHUNK_CHARS:
                chunks.append(
                    {
                        "chunk_id": f"control_{current_control_id}",
                        "control_id": current_control_id,
                        "page": current_buffer_page,
                        "text": text,
                        "char_count": len(text),
                        "source_document": PDF_FILE.name,
                    }
                )

        current_buffer = []
        current_buffer_page = None

    for block in blocks:
        text = block["text"]
        page = block["page"]

        if is_stop_marker(text):
            flush()
            current_control_id = None
            continue

        match = CONTROL_PATTERN.search(text)

        if match:
            flush()

            current_control_id = match.group(1).upper()
            current_buffer_page = page
            current_buffer = [text]
            continue

        if current_control_id:
            proposed_text = "\n".join(
                current_buffer + [text]
            )

            if len(proposed_text) > MAX_CHUNK_CHARS:
                flush()

                current_control_id = f"{current_control_id}_continued"
                current_buffer_page = page
                current_buffer = [text]
                continue

            current_buffer.append(text)

    flush()

    return chunks


def main():
    if not PDF_FILE.exists():
        raise FileNotFoundError(f"Source PDF not found: {PDF_FILE}")

    blocks = extract_pdf_blocks(PDF_FILE)

    if not blocks:
        raise ValueError("No text blocks extracted from PDF")

    chunks = build_control_chunks(blocks)

    if not chunks:
        raise ValueError("No control-aware chunks created")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_FILE.write_text(
        json.dumps(chunks, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Source PDF: {PDF_FILE}")
    print(f"Extracted blocks: {len(blocks)}")
    print(f"Control-aware chunks: {len(chunks)}")
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Min chunk chars: {MIN_CHUNK_CHARS}")
    print(f"Max chunk chars: {MAX_CHUNK_CHARS}")

    base_control_ids = sorted(
        {
            chunk["control_id"]
            for chunk in chunks
            if not chunk["control_id"].endswith("_continued")
        }
    )

    continued_chunks = [
        chunk
        for chunk in chunks
        if chunk["control_id"].endswith("_continued")
    ]

    print(f"Unique base control IDs: {len(base_control_ids)}")
    print(f"Continuation chunks: {len(continued_chunks)}")


if __name__ == "__main__":
    main()