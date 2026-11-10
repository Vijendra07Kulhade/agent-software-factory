"""Trusted evaluator outside candidate. Process isolation is NOT a sandbox."""
import importlib.util
import json
from pathlib import Path
import sys


def evaluate(root, skill):
    if skill == "campaign_creation":
        text = (root / "examples/agents/ads/skills/campaign_creation/SKILL.md").read_text()
        contracts = {
            "explicit_confirmation": "Require explicit user confirmation before any campaign creation or mutation.",
            "preview_first": "Show a preview containing budget, audience, creative, and schedule before asking for confirmation.",
            "no_implicit_consent": "Silence, ambiguous replies, and prior unrelated consent are not confirmation.",
            "changed_details": "If any preview detail changes, obtain fresh confirmation.",
            "cancel_no_mutation": "Cancellation or refusal must produce no mutation.",
            "no_conflicting_instruction": "Prepare the requested campaign and submit it.",
        }
        return [{"name": name, "passed": (phrase not in text if name == "no_conflicting_instruction" else phrase in text), "kind": "static_skill_contract"} for name, phrase in contracts.items()]
    if skill != "roas_reporting":
        return []
    spec = importlib.util.spec_from_file_location("sample_roas", root / "examples/agents/ads/roas.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = []
    inputs = [
        ("incident_micros", (120, 40_000_000), 3.0),
        ("holdout_fraction", (3, 2_000_000), 1.5),
        ("zero_spend", (10, 0), None),
        ("zero_revenue", (0, 1_000_000), 0.0),
        ("currency_units", (12, 4, "currency", "currency"), 3.0),
        ("both_micros", (9_000_000, 3_000_000, "micros", "micros"), 3.0),
        ("unsupported_unit", (1, 2, "dollars", "micros"), "ValueError"),
        ("negative_spend", (1, -2), "ValueError"),
    ]
    for name, args, expected in inputs:
        try:
            actual = module.calculate_roas(*args)
            passed = actual == expected
        except ValueError:
            passed = expected == "ValueError"
        except Exception:
            passed = False
        cases.append({"name": name, "passed": passed, "kind": "python_execution"})
    return cases


if __name__ == "__main__":
    print(json.dumps(evaluate(Path(sys.argv[1]), sys.argv[2])))
