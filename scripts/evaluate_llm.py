import argparse
import json
import math
from collections import defaultdict
from pathlib import Path


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1.0 + (z * z) / total
    center = (p + (z * z) / (2.0 * total)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * total)) / total)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def norm_req(val) -> str:
    if val is None:
        return "NONE"
    s = str(val).strip().upper()
    return s if s else "NONE"


def get_domain(req_id: str) -> str:
    if req_id == "NONE" or "-" not in req_id:
        return "UNMAPPED_OR_OOS"
    return req_id.split("-", 1)[0]


def compute_slice_metrics(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {
            "count": 0,
            "accuracy": 0.0,
            "accuracy_ci95": [0.0, 0.0],
            "matcher_recall": 0.0,
            "human_review_rate": 0.0,
        }

    correct = sum(1 for r in rows if r["pred_req"] == r["gold_req"])
    in_scope = [r for r in rows if r["gold_req"] != "NONE"]
    matcher_hits = sum(1 for r in in_scope if r["gold_req"] in r["candidates"])
    review_hits = sum(1 for r in rows if r["needs_review"])

    lo, hi = wilson_ci(correct, n)
    return {
        "count": n,
        "accuracy": round(correct / n, 4),
        "accuracy_ci95": [round(lo, 4), round(hi, 4)],
        "matcher_recall": round(matcher_hits / len(in_scope), 4) if in_scope else 1.0,
        "human_review_rate": round(review_hits / n, 4),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate Vidi mapping predictions against gold standard.")
    parser.add_argument("--gold", default="data/gold_standard_full.json", help="Path to gold standard JSON")
    parser.add_argument("--preds", default="data/mapped_claims.json", help="Path to mapped claims JSON")
    parser.add_argument("--report-md", default="docs/evaluation_report.md", help="Output markdown report path")
    parser.add_argument("--report-json", default="data/evaluation_metrics.json", help="Output JSON metrics path")
    args = parser.parse_args()

    gold_path = Path(args.gold)
    preds_path = Path(args.preds)
    if not gold_path.exists():
        raise FileNotFoundError(f"Gold file not found: {gold_path}")
    if not preds_path.exists():
        raise FileNotFoundError(f"Predictions file not found: {preds_path}")

    gold_items = json.loads(gold_path.read_text(encoding="utf-8"))
    pred_items = json.loads(preds_path.read_text(encoding="utf-8"))

    pred_by_claim = {}
    pred_by_ctrl_page = {}
    for p in pred_items:
        cid = str(p.get("claim_id", "")).strip()
        if cid:
            pred_by_claim[cid] = p
        key = (str(p.get("control_id", "")).strip(), str(p.get("page", "")).strip())
        if key[0]:
            pred_by_ctrl_page[key] = p

    joined = []
    for idx, g in enumerate(gold_items):
        cid = str(g.get("claim_id", "")).strip()
        key = (str(g.get("control_id", "")).strip(), str(g.get("page", "")).strip())
        pred = pred_by_claim.get(cid) or pred_by_ctrl_page.get(key) or (pred_items[idx] if idx < len(pred_items) else {})

        gold_req = norm_req(g.get("requirement_id") or g.get("gold_requirement"))
        pred_req = norm_req(pred.get("requirement_id"))
        cands = [norm_req(c) for c in (pred.get("candidate_requirements") or pred.get("candidates") or [])]
        if pred_req != "NONE" and pred_req not in cands:
            cands.append(pred_req)

        joined.append(
            {
                "claim_id": cid or f"ITEM-{idx+1:04d}",
                "split": str(g.get("split", "test")),
                "ambiguous": bool(g.get("ambiguous", False)),
                "oos": bool(g.get("out_of_scope_current_taxonomy", gold_req == "NONE")),
                "gold_req": gold_req,
                "pred_req": pred_req,
                "candidates": cands,
                "needs_review": bool(pred.get("needs_review", False)),
                "domain": get_domain(gold_req),
            }
        )

    summary = {
        "overall": compute_slice_metrics(joined),
        "by_split": {
            s: compute_slice_metrics([r for r in joined if r["split"] == s])
            for s in sorted({r["split"] for r in joined})
        },
        "by_scope": {
            "in_scope": compute_slice_metrics([r for r in joined if not r["oos"]]),
            "out_of_scope_current_taxonomy": compute_slice_metrics([r for r in joined if r["oos"]]),
        },
        "by_ambiguity": {
            "unambiguous": compute_slice_metrics([r for r in joined if not r["ambiguous"]]),
            "ambiguous": compute_slice_metrics([r for r in joined if r["ambiguous"]]),
        },
        "by_domain": {
            d: compute_slice_metrics([r for r in joined if r["domain"] == d])
            for d in sorted({r["domain"] for r in joined})
        },
    }

    out_json = Path(args.report_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    ov = summary["overall"]
    lines = [
        "# Vidi Evaluation Report",
        "",
        f"- **Total Evaluated Items:** {ov['count']}",
        f"- **Overall Exact-Match Accuracy:** {ov['accuracy']*100:.2f}% (95% Wilson CI: [{ov['accuracy_ci95'][0]*100:.2f}%, {ov['accuracy_ci95'][1]*100:.2f}%])",
        f"- **Candidate Matcher Recall (In-Scope):** {ov['matcher_recall']*100:.2f}%",
        f"- **Human-Review Flag Rate:** {ov['human_review_rate']*100:.2f}%",
        "",
        "## Breakdown by Split",
        "| Split | Count | Accuracy | 95% CI | Matcher Recall | Human-Review Rate |",
        "| :--- | ---: | ---: | :--- | ---: | ---: |",
    ]
    for k, m in summary["by_split"].items():
        lines.append(
            f"| {k} | {m['count']} | {m['accuracy']*100:.2f}% | [{m['accuracy_ci95'][0]*100:.2f}%, {m['accuracy_ci95'][1]*100:.2f}%] | {m['matcher_recall']*100:.2f}% | {m['human_review_rate']*100:.2f}% |"
        )

    lines.extend(
        [
            "",
            "## Breakdown by Taxonomy Scope & Ambiguity",
            "| Slice | Count | Accuracy | 95% CI | Matcher Recall | Human-Review Rate |",
            "| :--- | ---: | ---: | :--- | ---: | ---: |",
        ]
    )
    for label, m in {**summary["by_scope"], **summary["by_ambiguity"]}.items():
        lines.append(
            f"| {label} | {m['count']} | {m['accuracy']*100:.2f}% | [{m['accuracy_ci95'][0]*100:.2f}%, {m['accuracy_ci95'][1]*100:.2f}%] | {m['matcher_recall']*100:.2f}% | {m['human_review_rate']*100:.2f}% |"
        )

    lines.extend(
        [
            "",
            "## Breakdown by Control Domain",
            "| Domain | Count | Accuracy | 95% CI | Matcher Recall | Human-Review Rate |",
            "| :--- | ---: | ---: | :--- | ---: | ---: |",
        ]
    )
    for d, m in summary["by_domain"].items():
        lines.append(
            f"| {d} | {m['count']} | {m['accuracy']*100:.2f}% | [{m['accuracy_ci95'][0]*100:.2f}%, {m['accuracy_ci95'][1]*100:.2f}%] | {m['matcher_recall']*100:.2f}% | {m['human_review_rate']*100:.2f}% |"
        )

    out_md = Path(args.report_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved evaluation report to {out_md} and {out_json}")


if __name__ == "__main__":
    main()
