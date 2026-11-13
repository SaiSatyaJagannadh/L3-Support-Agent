"""Golden-set eval (release gate): retrieval recall@3, citation accuracy, routing accuracy."""
import uuid, sys, core
from data import GOLDEN, RULES, ADVERSARIAL

def run_evals():
    hit = cite = 0; ans_cases = [g for g in GOLDEN if g[2] == "answer"]
    for q, doc, _ in ans_cases:
        r = core.run(str(uuid.uuid4()), _t="eval", action="chat", message=q, groups=["staff"])
        ids = [c["id"] for c in (r["citations"] or [])]
        hit += doc in ids; cite += bool(ids) and ids[0] == doc
    ticket_ok = sum(core.run(str(uuid.uuid4()), _t="eval", action="chat", message=q, groups=["staff"])["citations"] == [] for q, d, a in GOLDEN if a == "ticket")
    routing = sum(core.DB.execute("select l2 from rules where app=?", (a,)).fetchone()[0] == l2 for a, _, l2, _ in RULES) / len(RULES)
    m = {"recall@3": hit / len(ans_cases), "citation_accuracy": cite / len(ans_cases), "no_answer_ok": ticket_ok, "routing_accuracy": routing}
    adv = 0
    for q, bad, st in ADVERSARIAL:
        r = core.run(str(uuid.uuid4()), _t="eval", action="chat", message=q, groups=["staff"])
        adv += not any(c["id"] in bad for c in (r["citations"] or [])) and (st is None or r["status"] == st)
    m["adversarial_pass"] = adv / len(ADVERSARIAL)
    m["passed"] = m["adversarial_pass"] == 1 and m["recall@3"] >= .8 and m["citation_accuracy"] >= .8 and routing == 1
    return m

if __name__ == "__main__":
    m = run_evals(); print(m); sys.exit(not m["passed"])
