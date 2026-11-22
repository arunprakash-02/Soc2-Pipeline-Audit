"""
Final hybrid RAG retrieval evaluation.

Measures:
- Semantic-only Top-1/3/5 retrieval
- Hybrid retrieval: exact control_id match first, semantic results second

Does not call the mapping LLM.
Does not modify mapping artifacts.
"""

import json
from pathlib import Path

import chromadb
import ollama

BASE_DIR = Path(__file__).resolve().parents[1]
GOLD_FILE = BASE_DIR / "data" / "gold_standard_full.json"
INDEX_DIR = BASE_DIR / "data" / "rag_index_v3"
RESULTS_FILE = BASE_DIR / "data" / "rag_evaluation_results_v3.json"

EMBEDDING_MODEL = "mxbai-embed-large:latest"
COLLECTION_NAME = "equinix_soc2_rag_v3"
TOP_K = 5

OUT_OF_SCOPE_CONTROLS = {
    "CC1.4.4",
    "CC1.4.5",
    "CC1.5.3",
    "CC2.2.3",
}


def normalize(value):
    return str(value or "").strip().upper()


def semantic_query(control_id):
    return (
        f"{control_id} SOC 2 control activity service auditor "
        f"test applied test results exceptions management response"
    )


def main():
    gold = json.loads(
        GOLD_FILE.read_text(encoding="utf-8")
    )

    client = chromadb.PersistentClient(
        path=str(INDEX_DIR)
    )

    collection = client.get_collection(
        name=COLLECTION_NAME
    )

    semantic_results = []
    hybrid_results = []

    semantic_top1 = semantic_top3 = semantic_top5 = 0
    hybrid_top1 = hybrid_top3 = hybrid_top5 = 0
    evaluated = 0

    for item in gold:
        control_id = normalize(item["control_id"])

        if control_id in OUT_OF_SCOPE_CONTROLS:
            continue

        evaluated += 1

        # Semantic retrieval
        query = semantic_query(control_id)

        embedding = ollama.embed(
            model=EMBEDDING_MODEL,
            input=query,
        )["embeddings"][0]

        response = collection.query(
            query_embeddings=[embedding],
            n_results=TOP_K,
            include=["metadatas", "documents", "distances"],
        )

        semantic_controls = [
            normalize(metadata["control_id"])
            for metadata in response["metadatas"][0]
        ]

        semantic_top1_hit = control_id in semantic_controls[:1]
        semantic_top3_hit = control_id in semantic_controls[:3]
        semantic_top5_hit = control_id in semantic_controls[:5]

        if semantic_top1_hit:
            semantic_top1 += 1
        if semantic_top3_hit:
            semantic_top3 += 1
        if semantic_top5_hit:
            semantic_top5 += 1

        semantic_results.append(
            {
                "control_id": control_id,
                "mode": "semantic",
                "retrieved_controls": semantic_controls,
                "top1_hit": semantic_top1_hit,
                "top3_hit": semantic_top3_hit,
                "top5_hit": semantic_top5_hit,
                "chunks": response["documents"][0],
            }
        )

        # Hybrid retrieval: exact control ID first
        exact = collection.get(
            where={"control_id": control_id},
            include=["documents", "metadatas"],
        )

        hybrid_controls = []
        hybrid_chunks = []

        for metadata, document in zip(
            exact["metadatas"],
            exact["documents"],
        ):
            hybrid_controls.append(
                normalize(metadata["control_id"])
            )
            hybrid_chunks.append(document)

        # Add semantic results that are not duplicates.
        for metadata, document in zip(
            response["metadatas"][0],
            response["documents"][0],
        ):
            metadata_control = normalize(
                metadata["control_id"]
            )

            if metadata_control not in hybrid_controls:
                hybrid_controls.append(metadata_control)
                hybrid_chunks.append(document)

        hybrid_top1_hit = control_id in hybrid_controls[:1]
        hybrid_top3_hit = control_id in hybrid_controls[:3]
        hybrid_top5_hit = control_id in hybrid_controls[:5]

        if hybrid_top1_hit:
            hybrid_top1 += 1
        if hybrid_top3_hit:
            hybrid_top3 += 1
        if hybrid_top5_hit:
            hybrid_top5 += 1

        hybrid_results.append(
            {
                "control_id": control_id,
                "mode": "hybrid",
                "retrieved_controls": hybrid_controls[:TOP_K],
                "top1_hit": hybrid_top1_hit,
                "top3_hit": hybrid_top3_hit,
                "top5_hit": hybrid_top5_hit,
                "chunks": hybrid_chunks[:TOP_K],
            }
        )

        print(
            f"[{evaluated}] {control_id} | "
            f"semantic top1={semantic_top1_hit} | "
            f"hybrid top1={hybrid_top1_hit}"
        )

    def percentage(correct):
        return round(correct / evaluated * 100, 1) if evaluated else 0.0

    summary = {
        "embedding_model": EMBEDDING_MODEL,
        "collection": COLLECTION_NAME,
        "indexed_chunks": collection.count(),
        "evaluated_controls": evaluated,
        "semantic": {
            "top1_correct": semantic_top1,
            "top3_correct": semantic_top3,
            "top5_correct": semantic_top5,
            "top1_accuracy": percentage(semantic_top1),
            "top3_accuracy": percentage(semantic_top3),
            "top5_accuracy": percentage(semantic_top5),
        },
        "hybrid": {
            "top1_correct": hybrid_top1,
            "top3_correct": hybrid_top3,
            "top5_correct": hybrid_top5,
            "top1_accuracy": percentage(hybrid_top1),
            "top3_accuracy": percentage(hybrid_top3),
            "top5_accuracy": percentage(hybrid_top5),
        },
        "semantic_results": semantic_results,
        "hybrid_results": hybrid_results,
    }

    RESULTS_FILE.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print()
    print("--- FINAL RAG V3 RETRIEVAL EVALUATION ---")
    print(f"Embedding model: {EMBEDDING_MODEL}")
    print(f"Indexed chunks: {collection.count()}")
    print(f"Evaluated controls: {evaluated}")
    print()
    print("Semantic-only retrieval")
    print(f"Top-1: {summary['semantic']['top1_accuracy']}%")
    print(f"Top-3: {summary['semantic']['top3_accuracy']}%")
    print(f"Top-5: {summary['semantic']['top5_accuracy']}%")
    print()
    print("Hybrid retrieval: exact control ID + semantic")
    print(f"Top-1: {summary['hybrid']['top1_accuracy']}%")
    print(f"Top-3: {summary['hybrid']['top3_accuracy']}%")
    print(f"Top-5: {summary['hybrid']['top5_accuracy']}%")
    print(f"Saved: {RESULTS_FILE}")


if __name__ == "__main__":
    main()