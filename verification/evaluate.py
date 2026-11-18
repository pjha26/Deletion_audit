"""Run baseline and model on frozen synthetic evidence, separate from runtime inputs."""
import argparse
import json
from pathlib import Path
from time import perf_counter

from .extract import extract

FIXTURES = Path(__file__).with_name("evaluation_cases.json")


def evaluate(endpoint):
    cases = json.loads(FIXTURES.read_text(encoding="utf8"))
    outcome = []
    for label, url in [("baseline", None), ("baseline_plus_local_model", endpoint)]:
        if label != "baseline" and not url:
            continue
        start = perf_counter()
        tp = predicted = expected = failures = reviews = 0
        errors = []
        for case in cases:
            result = extract(case["text"], case["subject"], url)
            actual = {(f["event"], f["line"]) for f in result["facts"]}
            truth = {tuple(f) for f in case["facts"]}
            tp += len(truth & actual)
            predicted += len(actual)
            expected += len(truth)
            failures += "note" in result
            reviews += result["review_required"]
            if truth != actual or "note" in result:
                errors.append({"id": case["id"], "missing": sorted(truth - actual),
                               "extra": sorted(actual - truth), "note": result.get("note")})
        outcome.append({"mode": label, "cases": len(cases), "correct_facts": tp,
                        "cited_facts": predicted, "expected_facts": expected,
                        "citation_precision": round(tp / predicted, 3) if predicted else None,
                        "fact_recall": round(tp / expected, 3) if expected else None,
                        "review_cases": reviews, "failed_calls": failures,
                        "seconds": round(perf_counter() - start, 2), "errors": errors})
    return outcome


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-url")
    print(json.dumps(evaluate(parser.parse_args().model_url), indent=2))
