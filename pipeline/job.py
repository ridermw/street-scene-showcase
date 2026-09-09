"""Run one owned process with a deadline and monitored storage."""

import argparse
import datetime
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

from pipeline.runtime import heavy_lock
from pipeline.evidence import atomic_json


def run_owned(command, run, deadline, *, min_free, max_bytes, log_name="job.log"):
    run = Path(run)
    run.mkdir(parents=True, exist_ok=True)

    next_storage_check = 0

    def capacity(force_storage=False):
        nonlocal next_storage_check
        if (run / "PAUSE").exists():
            raise RuntimeError("Owned job paused; preserve checkpoint and remove PAUSE to resume")
        if time.time() >= deadline:
            raise RuntimeError("Owned job reached deadline")
        if not force_storage and time.monotonic() < next_storage_check:
            return
        used = sum(p.stat().st_size for p in run.rglob("*") if p.is_file())
        if shutil.disk_usage(run).free < min_free or used > max_bytes:
            raise RuntimeError("Owned job reached storage limit")
        next_storage_check = time.monotonic() + 1

    with heavy_lock(run.parent / "heavy.lock"), (run / log_name).open("a") as log:
        capacity(force_storage=True)
        log.write(f"\nInvocation at {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n")
        log.flush()
        start = time.monotonic()
        events=run/"job-events"
        events.mkdir(exist_ok=True)
        event=events/f"{uuid.uuid4().hex}.json"
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        result={"pid":process.pid,"state":"running","executable":command[0],
                "started_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "log":str(run/log_name)}
        try:
            atomic_json(event,result)
            while process.poll() is None:
                capacity()
                time.sleep(.1)
            capacity(force_storage=True)
            if process.returncode != 0:
                raise RuntimeError(f"Owned job failed with exit {process.returncode}; see {log.name}")
            result["state"]="complete"
            return {"pid": process.pid, "returncode": process.returncode,
                    "seconds": time.monotonic() - start}
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            result.update({"returncode":process.returncode,"seconds":time.monotonic()-start})
            if result["state"]!="complete":
                result["state"]="failed"
                result["error"]=str(sys.exception())
            atomic_json(event,result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/street_scene.json")
    parser.add_argument("--log", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    deadline = datetime.datetime.fromisoformat(config["deadline_utc"]).timestamp() - 300
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    print(json.dumps(run_owned(command, Path(config["data_root"]) / config["run_id"],
                               deadline, min_free=config["min_free_bytes"],
                               max_bytes=config["max_additional_bytes"], log_name=args.log)))
