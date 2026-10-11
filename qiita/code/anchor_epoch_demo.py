"""A hash-chained ledger + an external anchor, checked by epoch (standalone demo, stdlib only).

Reproduces the 2026-10-11 incident in miniature: a replay process appended its own ledger's heads to the LIVE anchor.
  - old rule  (look at the anchor's last line only): the live ledger looks "rolled back" -> fails closed for nothing,
              and a forged last line can make a real rollback look fine.
  - new rule  (anchor lines name their ledger; the whole current epoch must match, gap-free): foreign lines are
              ignored, a real rollback is caught even when the last line is forged.

    python3 anchor_epoch_demo.py
"""
import hashlib
import json


def h(prev, body):
    return hashlib.sha256((prev + json.dumps(body, sort_keys=True)).encode()).hexdigest()


class Ledger:
    def __init__(self, name):
        self.name, self.entries = name, []

    def append(self, kind, anchor):
        prev = self.entries[-1]["hash"] if self.entries else "GENESIS"
        body = {"seq": len(self.entries) + 1, "kind": kind}
        e = {**body, "prev": prev, "hash": h(prev, body)}
        self.entries.append(e)
        anchor.append({"seq": e["seq"], "hash": e["hash"], "ledger": self.name})   # every line says whose it is
        return e


def old_rule(ledger, anchor):
    last = anchor[-1]
    if last["seq"] > len(ledger.entries):
        return f"rollback? ledger {len(ledger.entries)} < anchor {last['seq']}"
    if ledger.entries[last["seq"] - 1]["hash"] != last["hash"]:
        return "rewritten?"
    return "ok"


def new_rule(ledger, anchor):
    own = [x for x in anchor if x.get("ledger") == ledger.name]       # foreign lines do not count
    if not own:
        return "no anchor" if ledger.entries else "ok"
    seqs = [x["seq"] for x in own]                                    # epoch = from seq 1 here (no re-anchoring)
    n = len(ledger.entries)
    if max(seqs) > n:
        return f"rollback: ledger {n}, anchor {max(seqs)}"
    if seqs != list(range(1, len(seqs) + 1)):
        return "gap / duplicate / out of order in the anchor"
    if seqs[-1] < n:
        return f"anchor missing seq {seqs[-1] + 1}..{n}"
    if any(ledger.entries[x["seq"] - 1]["hash"] != x["hash"] for x in own):
        return "rewritten"
    return "ok"


if __name__ == "__main__":
    anchor = []                                  # the one live anchor file
    live = Ledger("live")
    for k in ("POLICY", "GRANT", "MISSION"):
        live.append(k, anchor)
    print("1 normal              old:", old_rule(live, anchor), "| new:", new_rule(live, anchor))

    replay = Ledger("replay")                    # the incident: a replay writes into the same anchor
    for _ in range(50):
        replay.append("REPLAYED", anchor)
    print("2 replay polluted     old:", old_rule(live, anchor), "| new:", new_rule(live, anchor))

    live.append("MISSION", anchor)
    rolled = Ledger("live")                      # a restore rolled the live ledger back to 2 entries
    rolled.entries = live.entries[:2]
    forged = dict(anchor[1]); anchor.append(forged)   # and someone appends a last line that matches it
    print("3 rollback + forged   old:", old_rule(rolled, anchor), "| new:", new_rule(rolled, anchor))

    assert old_rule(live, anchor[:53]).startswith("rollback?")          # old: false alarm after the replay
    assert new_rule(live, anchor[:53] + [anchor[53]]) == "ok"
    assert old_rule(rolled, anchor) == "ok"                             # old: the real rollback passes
    assert new_rule(rolled, anchor).startswith("rollback")              # new: caught
    print("all checks passed")
