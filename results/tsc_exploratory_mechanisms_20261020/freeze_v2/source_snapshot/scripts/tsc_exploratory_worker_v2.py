"""Bounded isolated development matrix, with preflight/publication gates."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from threading import Event, Thread
import time
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import tsc_revision_final_raw_worker_v1 as base
from scripts.tsc_revision_mechanism_worker_v3 import validate_preflight
from scripts.tsc_tableIII_fullcost_worker_v3 import runtime_inventory
from scripts.tsc_exploratory_runtime_patch_v2 import patch

REL = Path("results/tsc_exploratory_mechanisms_20261020")
CORE = Path("results/tsc_revision_mechanism_controls_20261018")
PARENT = Path("results/tsc_behavior_scope_repair_20261020")


def read(p): return json.loads(p.read_text(encoding="utf-8"))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("x", encoding="utf-8") as f: json.dump(x, f, indent=2); f.write("\n")
def state(p, x):
    q = p.with_suffix(".tmp")
    q.write_text(json.dumps(x, indent=2)+"\n")
    q.replace(p)


def start(root, study, job, policy, owned):
    cell = study / "runs" / job["id"] / "attempt1"
    cell.mkdir(parents=True, exist_ok=False)
    assert not base.foreign_pids(base.resource_snapshot(), owned)
    with socket.socket() as sock: sock.bind(("127.0.0.1", job["port"]))
    source = study / "freeze_v2/source_snapshot"
    runtime = study / "preflight_v2/runtime"
    cache, tmp = cell / "cache", cell / "tmp"
    tmp.mkdir()
    alias = Path("/tmp") / ("ckvEX-" + hashlib.sha256(str(tmp).encode()).hexdigest()[:12])
    assert not alias.exists() and not alias.is_symlink()
    alias.symlink_to(tmp, target_is_directory=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CONTRACTKV_", "VLLM_"))
           and k not in ["TORCHINDUCTOR_CACHE_DIR", "TORCH_COMPILE_CACHE_DIR"]}
    env.update(CUDA_VISIBLE_DEVICES=str(job["lane"]), PYTHONPATH=os.pathsep.join([str(runtime), str(source)]),
        TMPDIR=str(alias), HF_HOME=str(cache/"hf"), HF_HUB_CACHE=str(cache/"hf/hub"),
        TRANSFORMERS_CACHE=str(cache/"hf/transformers"), XDG_CACHE_HOME=str(cache/"xdg"),
        TORCH_HOME=str(cache/"torch"), TRITON_CACHE_DIR=str(cache/"triton"), VLLM_CACHE_ROOT=str(cache/"vllm"),
        CUDA_CACHE_PATH=str(cache/"cuda"), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
        PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1", VLLM_USE_V1="1", CONTRACTKV_POLICY_HASH=policy,
        CONTRACTKV_MIN_CANDIDATE_MARGIN="-1000000000", CONTRACTKV_MAX_DEGRADATION="1000000000",
        CONTRACTKV_MIN_RAW_TOKEN_MARGIN=".0625", CONTRACTKV_MIN_CANDIDATE_TOKEN_MARGIN=".125",
        CONTRACTKV_SHADOW_CHUNK_TOKENS="128", CONTRACTKV_SHADOW_ROUND_TOKENS="128",
        CONTRACTKV_PREFIX_METRICS="1", CONTRACTKV_PREFIX_INITIAL_ONLY="1",
        CONTRACTKV_PREFIX_METRICS_LOG=str(cell/"metrics.jsonl"),
        CONTRACTKV_EXPLORATORY_TRACE=str(cell/"mechanism_trace.jsonl"),
        CONTRACTKV_EXPLORATORY_RESIDENCY=job["residency"])
    served = base.SERVED[job["model"]]
    server = [base.PY, "-B", "-m", "vllm.entrypoints.openai.api_server", "--model", str(base.DISK/"models"/job["model"]),
              "--served-model-name", served, "--host", "127.0.0.1", "--port", str(job["port"]),
              "--dtype", "float16", "--tensor-parallel-size", "1", "--max-model-len", "16384",
              "--max-num-seqs", "2", "--gpu-memory-utilization", ".88", "--enable-prefix-caching",
              "--num-gpu-blocks-override", str(job["pool_blocks"])]
    client = [base.PY, "-B", str(source/"scripts/tsc_exploratory_client_v2.py"), "--study", str(study),
              "--job", str(study/job["job_file"]), "--identity", str(study/"preflight_v2"/("identity_"+job["model"]+".json")),
              "--output", str(cell/"responses.jsonl"), "--summary", str(cell/"summary_v1.json"),
              "--metrics-events", str(cell/"metrics.jsonl"), "--base-url", f'http://127.0.0.1:{job["port"]}/v1',
              "--model", served, "--policy-hash", policy]
    write(cell/"launch_v2.json", dict(job=job, server=server, client=client,
        environment={k: v for k, v in env.items() if k.startswith(("CONTRACTKV_", "VLLM_", "CUDA_")) or k in ["PYTHONPATH", "TMPDIR"]}))
    with (cell/"server.log").open("xb") as handle:
        process = subprocess.Popen(server, cwd=source, env=env, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
    owned.add(process.pid)
    write(cell/"server_process_v1.json", dict(pid=process.pid, process_group=process.pid))
    return dict(job=job, cell=cell, process=process, client=client, environment=env, source=source)


def client(item):
    stop = Event()
    thread = Thread(target=base.monitor, args=(item["job"]["port"], item["cell"]/"telemetry_v1.jsonl", stop), daemon=True)
    thread.start()
    try:
        with (item["cell"]/"client.log").open("xb") as handle:
            done = subprocess.run(item["client"], cwd=item["source"], env=item["environment"],
                                  stdout=handle, stderr=subprocess.STDOUT, timeout=1200)
        assert done.returncode == 0, "Cell failure retained; no scientific auto-retry"
        summary = read(item["cell"]/"summary_v1.json")
        assert summary["offered"] == item["job"]["expected_business"] == summary["successful"]
        assert summary["raw_file_sha256"] == sha(item["cell"]/"responses.jsonl")
        assert read(item["cell"]/"measured_backend_drain_v1.json")["backend_request_counters_drained"]
        return summary
    finally:
        stop.set(); thread.join(timeout=10)


def wave(root, study, jobs, policy):
    owned, items = set(), []
    stop, violation = Event(), Event()
    monitor = None
    try:
        for job in jobs:
            items.append(start(root, study, job, policy, owned)); time.sleep(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            for f in [pool.submit(base.ready, x) for x in items]: f.result()
        label = str(jobs[0]["wave"])
        write(study/"waves"/(label+"_ready.json"), dict(jobs=[j["id"] for j in jobs], all_ready_before_clients=True))
        monitor = Thread(target=base.resource_monitor, args=(study/"waves"/(label+"_GPU_resources.jsonl"), owned, stop, violation), daemon=True)
        monitor.start()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [f.result() for f in [pool.submit(client, x) for x in items]]
        stop.set(); monitor.join(timeout=10)
        assert not monitor.is_alive() and not violation.is_set()
        assert not base.foreign_pids(base.resource_snapshot(), owned)
        for item, result in zip(items, results):
            write(item["cell"]/"completion_v1.json", dict(status="complete", job=item["job"], summary_sha256=sha(item["cell"]/"summary_v1.json")))
        return [j["id"] for j in jobs]
    except BaseException as exc:
        for item in items:
            write(item["cell"]/"failure_v1.json", dict(type=type(exc).__name__, message=str(exc), outputs_preserved=True))
        raise
    finally:
        stop.set()
        if monitor: monitor.join(timeout=10)
        for item in items: base.stop_own_group(item["process"])


def main(a):
    root = a.root.resolve()
    study = root/REL
    assert sys.platform == "linux" and root.is_relative_to(base.DISK)
    frozen = study/"freeze_v2/freeze.json"
    assert sha(frozen) == a.freeze_sha256
    freeze = read(frozen)
    for row in freeze["files"]:
        assert sha(root/row["path"]) == row["sha256"]
    for row in freeze["snapshot_files"]:
        assert sha(study/"freeze_v2/source_snapshot"/row["path"]) == row["sha256"]
    if a.mode == "preflight":
        assert not base.foreign_pids(base.resource_snapshot())
        validate_preflight(root/CORE)
        out = study/"preflight_v2"
        out.mkdir(exist_ok=False)
        registry = read(root/CORE/"preflight_v3/model_asset_registry_v1.json")
        stats = []
        for model in registry["models"]:
            if model["model"] not in read(study/"protocol_v1.json")["models"]: continue
            for row in model["files"]:
                p = base.DISK/"models"/model["model"]/row["file"]
                st = p.stat()
                assert (st.st_size, st.st_mtime_ns) == (row["bytes"], row["mtime_ns"])
            stats.append(dict(model=model["model"], full_SHA_registered_files=len(model["files"]), current_size_mtime_match=True))
        parent = root/CORE/"preflight_v3/runtime"
        before = runtime_inventory(parent/"vllm")
        runtime = out/"runtime"
        shutil.copytree(parent, runtime, symlinks=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
        assert before == runtime_inventory(runtime/"vllm")
        changed = patch(runtime)
        assert runtime_inventory(parent/"vllm") == before
        write(out/"runtime_inventory_v1.json", dict(files=runtime_inventory(runtime/"vllm"), parent_source_unchanged=True))
        for model in stats:
            name = "identity_" + model["model"] + ".json"
            identity = read(root/CORE/"preflight_v3"/name)
            identity["parent_runtime_revision"] = identity["runtime_revision"]
            identity["runtime_revision"] = sha(out/"runtime_inventory_v1.json")
            write(out/name, identity)
        env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(runtime), str(study/"freeze_v2/source_snapshot")]), "PYTHONDONTWRITEBYTECODE": "1"}
        code = "from vllm.v1.engine import ContractKVCompactResult; from vllm.v1.engine.async_llm import AsyncLLM; from vllm.v1.core.sched.scheduler import Scheduler; import scripts.tsc_exploratory_client_v2; print('ISOLATED_NATIVE_IMPORT_PASS')"
        done = subprocess.run([base.PY, "-B", "-c", code], env=env, cwd=study/"freeze_v2/source_snapshot", capture_output=True, text=True, timeout=120)
        (out/"CPU_import.log").write_text(done.stdout+done.stderr)
        assert done.returncode == 0
        write(out/"receipt_v1.json", dict(status="PASS", freeze_sha256=sha(frozen), changed_runtime_files=changed,
              parent_runtime_unchanged=True, parent_inventory_sha256=sha(root/CORE/"preflight_v3/runtime_inventory_v1.json"),
              model_assets=stats, actual_resources=base.resource_snapshot(), no_GPU_inference=True))
        print(sha(out/"receipt_v1.json")); return
    receipt = study/"preflight_v2/receipt_v1.json"
    assert a.receipt_sha256 and sha(receipt) == a.receipt_sha256 and read(receipt)["status"] == "PASS"
    if a.mode == "launch":
        assert a.published_commit and not (study/"launch_v2.json").exists()
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "--root", str(root), "--mode", "execute",
                   "--freeze-sha256", a.freeze_sha256, "--receipt-sha256", a.receipt_sha256]
        with (study/"worker_v2.log").open("xb") as handle:
            process = subprocess.Popen(command, cwd=root, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
        write(study/"launch_v2.json", dict(worker_pid=process.pid, command=command, published_commit=a.published_commit))
        print(json.dumps(dict(worker_pid=process.pid))); return
    import fcntl
    with (study/"worker.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status = study/"execution_state_v2.json"
        assert not status.exists()
        current = dict(status="RUNNING", worker_pid=os.getpid(), completed_cells=[], current_wave=None)
        state(status, current)
        try:
            jobs = read(study/"jobs_v1.json")["jobs"]
            for index in sorted({j["wave"] for j in jobs}):
                current["current_wave"] = index; state(status, current)
                current["completed_cells"] += wave(root, study, [j for j in jobs if j["wave"] == index], a.freeze_sha256)
                state(status, current)
            current.update(status="COMPLETE_PENDING_ANALYSIS", worker_pid=None, current_wave=None)
            state(status, current)
        except BaseException as exc:
            current.update(status="FAILURE_PRESERVED", worker_pid=None, error_type=type(exc).__name__, error_message=str(exc))
            state(status, current); raise


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--mode", choices=["preflight", "launch", "execute"], required=True)
    p.add_argument("--freeze-sha256", required=True)
    p.add_argument("--receipt-sha256")
    p.add_argument("--published-commit")
    main(p.parse_args())
