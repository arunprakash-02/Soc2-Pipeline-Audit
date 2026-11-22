"""
Build the final hybrid RAG index.

Uses:
- mxbai-embed-large for semantic retrieval
- Unique chunk IDs
- control_id metadata for exact control retrieval

Creates data/rag_index_v3.
Does not modify mapping artifacts or prior indexes.
"""

import json
from pathlib import Path

import chromadb
import ollama

BASE_DIR = Path(__file__).resolve().parents[1]
CORPUS_FILE = BASE_DIR / "data" / "rag_corpus_v2.json"
INDEX_DIR = BASE_DIR / "data" / "rag_index_v3"

EMBEDDING_MODEL = "mxbai-embed-large:latest"
COLLECTION_NAME = "equinix_soc2_rag_v3"
BATCH_SIZE = 16


def main():
    corpus = json.loads(
        CORPUS_FILE.read_text(encoding="utf-8")
    )

    if not corpus:
        raise ValueError("RAG corpus is empty")

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(INDEX_DIR)
    )

    existing = [
        collection.name
        for collection in client.list_collections()
    ]

    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "embedding_model": EMBEDDING_MODEL,
            "retrieval_mode": "hybrid_control_id_and_semantic",
        },
    )

    # Ensure every chunk has a unique Chroma ID.
    used_ids = set()

    for index, item in enumerate(corpus):
        base_id = item["control_id"]
        chunk_id = f"{base_id}_page{item['page']}_{index}"

        while chunk_id in used_ids:
            index += 1
            chunk_id = f"{base_id}_page{item['page']}_{index}"

        used_ids.add(chunk_id)
        item["chroma_id"] = chunk_id

    total_indexed = 0

    for start in range(0, len(corpus), BATCH_SIZE):
        batch = corpus[start:start + BATCH_SIZE]

        texts = [item["text"] for item in batch]
        ids = [item["chroma_id"] for item in batch]

        metadata = [
            {
                "page": item["page"],
                "control_id": item["control_id"],
                "char_count": item["char_count"],
            }
            for item in batch
        ]

        response = ollama.embed(
            model=EMBEDDING_MODEL,
            input=texts,
        )

        collection.add(
            ids=ids,
            documents=texts,
            embeddings=response["embeddings"],
            metadatas=metadata,
        )

        total_indexed += len(batch)
        print(f"Indexed {total_indexed}/{len(corpus)} chunks")

    print()
    print(f"Embedding model: {EMBEDDING_MODEL}")
    print(f"Indexed chunks: {total_indexed}")
    print(f"Index directory: {INDEX_DIR}")
    print(f"Collection: {COLLECTION_NAME}")


if __name__ == "__main__":
    main()