"""Synthetic local smoke-test feed, NOT the real replay/detector/Guardian."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import time
from urllib.request import Request, urlopen
from urllib.error import URLError


def fixture(step: int) -> dict:
    if step < 0:
        raise ValueError("step must be nonnegative")
    base = datetime(2022, 9, 1, 10, 0, tzinfo=timezone.utc)
    transactions = []
    for i in range(step + 1):
        from_bank = ["Bank_1", "Bank_2", "Bank_3"][i % 3]
        to_bank = ["Bank_2", "Bank_3", "Bank_1"][i % 3]
        transactions.append({"tx_id":f"SYN-{i}", "timestamp":(base + timedelta(minutes=i)).isoformat(),
                             "from_acct":f"A_MOCK_{i}", "to_acct":f"A_MOCK_{i+1}",
                             "from_bank":from_bank, "to_bank":to_bank, "currency":"USD"})
    score = min(0.99, 0.58 + 0.08 * step)
    as_of = transactions[-1]["timestamp"]
    cross = step + 1
    scores = [{"acct":"A_MOCK_TARGET", "risk_score":score,
               "as_of":as_of, "reason_facts":f"{cross} historical transfers; {min(cross+1,7)} counterparties; {cross} cross-bank transfers"},
              {"acct":"A_MOCK_OTHER", "risk_score":0.70,"as_of":as_of,"reason_facts":"2 historical transfers; 2 counterparties; 1 cross-bank transfers"}]
    rec = []
    if score >= 0.8:
        rec = [{"acct":"A_MOCK_TARGET", "rank":1, "risk_score":score,
                "as_of":as_of, "reason_facts":scores[0]["reason_facts"],
                "requires_human_approval":True}]
    return {"snapshot":{"as_of":as_of,"snapshot_id":f"synthetic-{step}","mode":"synthetic_demo",
                        "total_seen":len(transactions),"recent_transactions":transactions,
                        "bank_links":[{"from_bank":"Bank_1","to_bank":"Bank_2","count":(step+3)//3},
                                      {"from_bank":"Bank_2","to_bank":"Bank_3","count":(step+2)//3},
                                      {"from_bank":"Bank_3","to_bank":"Bank_1","count":(step+1)//3}]},
            "scores":scores,"recommendations":rec}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",default="http://127.0.0.1:8765/api/publish")
    p.add_argument("--steps",type=int,default=6)
    p.add_argument("--delay",type=float,default=1.0)
    args=p.parse_args()
    for step in range(args.steps):
        payload=json.dumps(fixture(step)).encode()
        from os import getenv
        headers={"Content-Type":"application/json"}
        if getenv("GH_V3_INGEST_TOKEN"):headers["X-Ingest-Token"]=getenv("GH_V3_INGEST_TOKEN")
        req=Request(args.url,data=payload,headers=headers,method="POST")
        try:
            with urlopen(req,timeout=5) as res:
                print(f"Mock checkpoint {step}:",res.read().decode(),flush=True)
        except URLError as exc:
            raise SystemExit(f"Local dashboard service unavailable: {exc}")
        time.sleep(args.delay)

if __name__=="__main__":main()
