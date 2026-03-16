#!/usr/bin/env python3
"""Convert RULES.md enforced section to AgentPolicy YAML.

Usage:
  python3 scripts/rules_to_policy.py RULES.md
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def parse_enforced_rules(text: str) -> list[str]:
    lines = text.splitlines()
    in_section = False
    rules: list[str] = []
    for line in lines:
        if line.strip().startswith("## Enforced rules"):
            in_section = True
            continue
        if in_section and line.strip().startswith("## "):
            break
        if in_section:
            m = re.match(r"^\s*-\s+(.*\S)\s*$", line)
            if m:
                rules.append(m.group(1))
    return rules


def emit_yaml(policy_name: str, rules: list[str]) -> str:
    out: list[str] = [
        "apiVersion: astragraph.io/v1",
        "kind: AgentPolicy",
        "metadata:",
        f"  name: {policy_name}",
        '  version: "1.0"',
        '  owner: "agentstack-reference"',
        "spec:",
        "  rules:",
    ]
    for idx, rule in enumerate(rules, start=1):
        escaped = rule.replace('"', "'")
        out.extend(
            [
                f"    - id: rule-{idx:02d}",
                f'      description: "{escaped}"',
                f'      condition: "rule_{idx:02d}_violated is true"',
                "      action: BLOCK",
            ]
        )
    if not rules:
        out.append("    []")
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rules_md", help="Path to RULES.md")
    parser.add_argument("--policy-name", default="agentstack-platform")
    args = parser.parse_args()

    path = Path(args.rules_md)
    text = path.read_text(encoding="utf-8")
    rules = parse_enforced_rules(text)
    print(emit_yaml(args.policy_name, rules), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
