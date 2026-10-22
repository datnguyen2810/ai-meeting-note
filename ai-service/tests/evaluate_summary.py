"""Opt-in cached-model benchmark. Never downloads weights or starts ASR.

From ai-service: python -m tests.evaluate_summary --case customer_service
Add --baseline-ref HEAD to compare against the pre-change committed pipeline.
Checks measure factual coverage, not fluency or semantic correctness.
"""

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys
import time

from summarization.service import run_summarize
from summarization.validation import normalize


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--baseline-ref", help="Git revision containing the old run_summarize helper")
    parser.add_argument("--output", type=Path, help="Optional JSON report path (do not commit private transcripts)")
    parser.add_argument("--trace", action="store_true", help="Print raw extraction for these public fixtures only")
    parser.add_argument("--fixture", type=Path, help="Use a different JSON fixture list")
    args = parser.parse_args()
    if args.trace:
        from summarization import service
        original_parse = service.parse_extraction

        def trace(raw):
            print(json.dumps({"raw_extraction": raw}, ensure_ascii=False), flush=True)
            return original_parse(raw)

        service.parse_extraction = trace
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    model_id = "Qwen/Qwen2.5-1.5B-Instruct"
    tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, local_files_only=True,
        dtype=torch.float16 if device != "cpu" else torch.float32,
    ).to(device).eval()
    runners = {"updated": run_summarize}
    if args.baseline_ref:
        source = subprocess.check_output(
            ["git", "show", f"{args.baseline_ref}:ai-service/main.py"], encoding="utf-8"
        )
        # Load only the old pure helpers; do not execute app imports/lifespan.
        names = {"_split_text_into_chunks", "_clean_repeated_headers", "run_summarize"}
        nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
        namespace = {"torch": torch}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<baseline>", "exec"), namespace)
        runners = {"baseline": namespace["run_summarize"], **runners}
    fixtures = args.fixture or Path(__file__).parent / "fixtures/summary_cases.json"
    cases = json.loads(fixtures.read_text(encoding="utf-8"))
    reports = []
    for case in cases:
        if args.cases and case["id"] not in args.cases:
            continue
        for name, runner in runners.items():
            started = time.perf_counter()
            torch.manual_seed(42)
            if device != "cpu":
                torch.cuda.reset_peak_memory_stats()
            summary = runner(model, tokenizer, case["transcript"], device)
            missing = [term for term in case["required"] if normalize(term) not in normalize(summary)]
            invented = [term for term in case["forbidden"] if normalize(term) in normalize(summary)]
            report = dict(case=case["id"], pipeline=name, seconds=round(time.perf_counter() - started, 2),
                          missing=missing, forbidden_found=invented, summary=summary,
                          peak_gpu_mb=round(torch.cuda.max_memory_allocated() / 1024**2) if device != "cpu" else None)
            reports.append(report)
            print(json.dumps(report, ensure_ascii=False), flush=True)
            if args.output:
                args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
