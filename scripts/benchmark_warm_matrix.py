"""
Warm timing matrix for six representative SOC 2 blocks.

This script does not modify mapped_claims.json or risk_assessment.json.
"""

import json
import time
from pathlib import Path

import ollama

from run_mapping import build_prompt

BASE_DIR = Path(__file__).resolve().parents[1]
CLAIMS_FILE = BASE_DIR / "data" / "mapped_claims.json"

MODELS = [
    "llama3.2:3b",
    "qwen2.5:1.5b",
]

OPTION_SETS = [
    ("production_defaults", {}),
    ("cpu_only", {
        "temperature": 0,
        "num_gpu": 0,
    }),
]


def as_dict(response):
    if isinstance(response, dict):
        return response

    return response.model_dump()


def main():
    claims = json.loads(
        CLAIMS_FILE.read_text(encoding="utf-8")
    )

    ranked = sorted(
        claims,
        key=lambda claim: len(claim["evidence"]),
    )

    middle = len(ranked) // 2
    sample = ranked[-3:] + ranked[middle:middle + 3]

    print(f"Total claims: {len(claims)}")
    print(
        "Sample controls: "
        f"{[claim['control_id'] for claim in sample]}"
    )

    for model in MODELS:
        for option_name, options in OPTION_SETS:
            print()
            print(
                f"=== {model} | {option_name} | options={options} ==="
            )

            warmup = ollama.chat(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": "ok",
                    }
                ],
                options=options,
                keep_alive="5m",
                stream=False,
            )

            print(
                "control    "
                "wall  "
                "prompt_tok  "
                "prompt_s  "
                "out_tok  "
                "out_s"
            )

            for claim in sample:
                prompt = build_prompt(
                    claim["evidence"],
                    claim["candidates"],
                )

                start = time.perf_counter()

                response = ollama.chat(
                    model=model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    options=options,
                    keep_alive="5m",
                    stream=False,
                )

                wall = time.perf_counter() - start
                data = as_dict(response)

                prompt_tokens = data.get("prompt_eval_count", 0)
                prompt_seconds = (
                    data.get("prompt_eval_duration", 0)
                    / 1_000_000_000
                )
                output_tokens = data.get("eval_count", 0)
                output_seconds = (
                    data.get("eval_duration", 0)
                    / 1_000_000_000
                )

                print(
                    f"{claim['control_id']:<10} "
                    f"{wall:5.1f} "
                    f"{prompt_tokens:>10} "
                    f"{prompt_seconds:>8.1f} "
                    f"{output_tokens:>7} "
                    f"{output_seconds:>6.1f}"
                )

            print(
                f"model={model} "
                f"option_set={option_name} "
                "complete"
            )


if __name__ == "__main__":
    main()