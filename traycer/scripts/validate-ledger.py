#!/usr/bin/env python3
"""Deterministic physical-invariant validator for conveyor ledgers.

Checks ONLY physical event-log invariants — no semantics, no content judgment:
  E1 monotonic sequence (each entry = previous + 1)
  E2 unique sequence numbers
  E3 close-once: closes_sequence targets an existing 'decision' entry,
     not already closed, never a non-decision (no close-of-a-close)

Detective by default: reports, never blocks. Exit 0 = clean, 1 = findings.
# ponytail: line-scanner, not a YAML parser — ledger blocks are flat key:value;
# upgrade to real YAML parsing if entries ever nest.
"""
import re
import sys


def parse_entries(path):
    entries = []  # dicts: line, sequence, event, closes, request_id
    cur = None
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            m = re.match(r"^sequence:\s*(\d+)\s*$", line)
            if m:
                cur = {"line": lineno, "sequence": int(m.group(1)),
                       "event": None, "closes": None, "request_id": None}
                entries.append(cur)
                continue
            if cur is None:
                continue
            for key, field, cast in (("event", "event", str),
                                     ("closes_sequence", "closes", int),
                                     ("request_id", "request_id", str)):
                m = re.match(rf"^{key}:\s*(\S+)\s*$", line)
                if m and cur[field] is None:
                    cur[field] = cast(m.group(1))
    return entries


def validate(path):
    entries = parse_entries(path)
    findings = []
    seen = {}          # sequence -> first entry
    closed = {}        # decision sequence -> closing entry
    prev = None
    for e in entries:
        s = e["sequence"]
        if s in seen:
            findings.append((e, f"E2 duplicate sequence {s} "
                             f"(first at line {seen[s]['line']})"))
        else:
            seen[s] = e
        if prev is not None and s != prev + 1:
            kind = "regression/insertion" if s <= prev else "gap"
            findings.append((e, f"E1 non-monotonic: {prev} -> {s} ({kind})"))
        prev = s
        if e["closes"] is not None:
            t = seen.get(e["closes"])
            if t is None:
                findings.append((e, f"E3 closes_sequence {e['closes']}: no such prior entry"))
            elif t["event"] != "decision":
                findings.append((e, f"E3 closes_sequence {e['closes']}: target is "
                                 f"'{t['event']}' not a decision (close-of-a-close)"))
            elif e["closes"] in closed:
                findings.append((e, f"E3 closes_sequence {e['closes']}: already closed "
                                 f"at line {closed[e['closes']]['line']}"))
            else:
                closed[e["closes"]] = e
    return entries, findings


def main(paths):
    total_entries = total_findings = 0
    for path in paths:
        entries, findings = validate(path)
        total_entries += len(entries)
        total_findings += len(findings)
        print(f"\n== {path}")
        print(f"   entries: {len(entries)}, findings: {len(findings)}")
        for e, msg in findings:
            print(f"   line {e['line']:5d} seq {e['sequence']:4d} "
                  f"[{e['event'] or '?'}] {msg}")
    print(f"\nTOTAL: {total_entries} entries, {total_findings} findings")
    return 1 if total_findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
