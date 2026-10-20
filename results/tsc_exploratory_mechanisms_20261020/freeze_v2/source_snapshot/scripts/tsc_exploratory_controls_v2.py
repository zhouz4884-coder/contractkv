"""Auxiliary real-engine publication controls after the measured service clock."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import http.client
import json
from pathlib import Path
from types import SimpleNamespace
import time
import urllib.error
import urllib.parse
import urllib.request
from scripts.contractkv_authorized_requests import authorized_business_generate
from scripts.tsc_revision_r2_candidate_plan import verification_request
from scripts.phase17_live_common import api_root
from scripts.tsc_revision_final_fixed_client_v2 import finish_after_backend_drain
from scripts.tsc_exploratory_native_v1 import MODE


def run(args, auth, samples, recorded):
    begin = time.perf_counter()
    out = args.output.parent / "auxiliary_controls_v2"
    out.mkdir(exist_ok=False)
    observations = []
    def note(row):
        observations.append(row)
        with (out/"responses.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n")
    registrations = [r for r in recorded if r["row_type"] == "registration" and r["certificate"]["certificate_issued"]]
    if not registrations:
        (out/"summary_v2.json").write_text(json.dumps(dict(status="NOT_APPLICABLE", reason="No native PASS for duplicate/release positive control"))+"\n")
        return
    reg = registrations[0]  # deterministic integration fixture, not source selection for performance
    sample = next(s for s in samples if s["revision_source_group"] == reg["source_group"])
    raw = next(r["result"] for r in recorded if r["row_type"] == "business" and r["access"] == 0
               and (r["source_group"], r["tenant"], r["turn"]) == (reg["source_group"], reg["tenant"], reg["turn"]))
    endpoint = api_root(args.base_url)+"/v1/contractkv/verify"
    def payload(kind):
        identity = auth.cache.bind("controller", auth.domain, auth.epoch, sample["revision_session_id"]+":aux-"+kind)
        rid = args.cell_id+"-aux-"+kind
        value, _ = verification_request(args, reg["plan"], raw, rid, auth.cache.require(identity), False, "aux-publication-controls-v2")
        value["attestation_mode"] = MODE
        return value, identity
    def call(value):
        started = time.perf_counter()
        req = urllib.request.Request(endpoint, data=json.dumps(value).encode(), headers={"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                result = dict(status_code=response.status, body=json.load(response))
        except urllib.error.HTTPError as exc:
            result = dict(status_code=exc.code, error_body=exc.read().decode("utf-8", "replace"))
        result.update(row_type="aux_RPC", request_id=value["request_id"], txn_id=value["txn_id"],
                      elapsed_ms=(time.perf_counter()-started)*1000)
        return result
    for kind in ("wrong-answer", "wrong-EOS", "timeout", "cancel"):
        value, identity = payload(kind)
        if kind == "wrong-answer":
            value["reference_answer_ids"][0] = (value["reference_answer_ids"][0]+1) % 1000
            value["prompt_token_ids"] = reg["plan"]["prompt_token_ids"]+value["reference_answer_ids"]+[value["terminal_stop_token_id"]]
        if kind == "wrong-EOS":
            value["terminal_stop_token_id"] += 1
            value["prompt_token_ids"][-1] = value["terminal_stop_token_id"]
        if kind == "timeout": value["timeout_s"] = .001
        if kind == "cancel":
            url = urllib.parse.urlparse(endpoint)
            conn = http.client.HTTPConnection(url.hostname, url.port, timeout=30)
            started = time.perf_counter()
            conn.request("POST", url.path, body=json.dumps(value).encode(), headers={"Content-Type":"application/json"})
            time.sleep(.05); conn.close()
            note(dict(row_type="aux_cancel", request_id=value["request_id"], txn_id=value["txn_id"],
                      elapsed_ms=(time.perf_counter()-started)*1000, client_disconnected=True))
        else:
            result = call(value)
            note(result)
            if "body" in result:
                assert not result["body"].get("certificate_issued") and result["body"].get("committed_tokens", 0) == 0
        folder = out/kind
        folder.mkdir()
        drain_args = SimpleNamespace(base_url=args.base_url, output=folder/"ignored.jsonl")
        finish_after_backend_drain(drain_args)
        for index in (0, 1):
            result = authorized_business_generate(auth.cache, identity, args, reg["plan"]["messages"], 128,
                args.cell_id+f"-aux-{kind}-read{index}", False)
            assert result["success"]
            note(dict(row_type="aux_read_probe", condition=kind, repeat=index, result=result))
    # Simultaneous duplicate IDs and a subsequent repeated valid transaction.
    value, _ = payload("duplicate")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [f.result() for f in [pool.submit(call, deepcopy(value)) for _ in range(2)]]
    for result in results: note(result)
    again = deepcopy(value)
    again["request_id"] += "-repeat-after-completion"
    note(call(again))
    final = out/"final-drain"
    final.mkdir()
    finish_after_backend_drain(SimpleNamespace(base_url=args.base_url, output=final/"ignored.jsonl"))
    summary = dict(status="COMPLETE_PENDING_NATIVE_AUDIT", HTTP_or_cancel_attempts=7,
                   read_probes=8, wall_s=time.perf_counter()-begin,
                   main_service_clock_excludes_these_auxiliary_test_requests=True,
                   duplicate_pending_error_observed=any(r["status_code"] >= 400 for r in results),
                   publication_claim="Require native release evidence and subsequent cold physical lookups, not just HTTP fields")
    (out/"summary_v2.json").write_text(json.dumps(summary, indent=2)+"\n")
