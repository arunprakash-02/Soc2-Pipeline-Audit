import hashlib, sys, pathlib, yaml

MANIFEST = pathlib.Path("data/raw/SOURCES.yaml")
RAW_DIR = pathlib.Path("data/raw")

def sha256(path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()

def main():
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8-sig"))
    failures = 0
    for doc in manifest["documents"]:
        target = RAW_DIR / doc["filename"]
        if not target.exists():
            print(f"[MISSING] {doc['id']}: {target} not found")
            failures += 1
            continue
        actual = sha256(target).lower()
        pinned = doc.get("sha256", "").strip().lower()
        if actual == pinned:
            print(f"[OK]      {doc['id']}: {actual[:16]}...")
        else:
            print(f"[FAIL]    {doc['id']}: expected {pinned[:16]}..., got {actual[:16]}...")
            failures += 1
    sys.exit(1 if failures else 0)

if __name__ == "__main__":
    main()
