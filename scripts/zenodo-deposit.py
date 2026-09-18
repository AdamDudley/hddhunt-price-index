#!/usr/bin/env python3
"""
Headless Zenodo deposit for the HDD Price Index dataset.

This is the "agent-runnable" half of the dataset-hosting-mirror lever (HDD-301).
Everything below runs with NO human interaction *once a personal access token
exists*: it creates a deposition, uploads the dataset files, attaches the
metadata from .zenodo.json, and (optionally) publishes to mint a real DataCite
DOI. The published Zenodo record page links back to hddhunt.com with a
**dofollow** link (verified 2026-09-18: Zenodo record pages carry no
rel=nofollow on outbound metadata links; DA ~62).

The ONLY step that is NOT agent-runnable is the one-time creation of the account
+ token (Zenodo blocks automated signup via anti-spam / email verification).
See ZENODO-RUNBOOK.md for the ~5-minute owner step.

Usage:
    # 1. Validate everything structurally, no network calls, no token needed:
    python3 scripts/zenodo-deposit.py --dry-run

    # 2. Dress rehearsal against the sandbox (needs a sandbox token; issues a
    #    throwaway 10.5072 test DOI):
    ZENODO_TOKEN=xxx ZENODO_BASE=https://sandbox.zenodo.org \
        python3 scripts/zenodo-deposit.py --publish

    # 3. The real thing (needs a real zenodo.org token, mints a permanent DOI):
    ZENODO_TOKEN=xxx python3 scripts/zenodo-deposit.py --publish

Without --publish the deposition is left as an unpublished draft (safe: you can
review it in the Zenodo web UI and hit Publish or Discard by hand).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Core machine-readable dataset artifacts to attach to the record. Kept small
# and canonical on purpose; the full per-day file set lives in the GitHub repo
# that .zenodo.json points at via related_identifiers.
DATASET_FILES = [
    "price-index-timeseries.jsonl",
    "price-index-latest.csv",
    "README.md",
    "LICENSE",
    "CITATION.cff",
]


def log(msg):
    print(msg, flush=True)


def load_metadata():
    path = os.path.join(REPO_ROOT, ".zenodo.json")
    with open(path, "r", encoding="utf-8") as fh:
        meta = json.load(fh)
    # Zenodo's deposit API wants the metadata wrapped under a "metadata" key.
    # .zenodo.json already uses the deposit metadata schema, so pass it through.
    required = ["title", "upload_type", "description", "creators"]
    missing = [k for k in required if k not in meta]
    if missing:
        sys.exit(f"ERROR: .zenodo.json missing required fields: {missing}")
    return meta


def resolve_files():
    resolved = []
    for name in DATASET_FILES:
        p = os.path.join(REPO_ROOT, name)
        if os.path.exists(p):
            resolved.append((name, p, os.path.getsize(p)))
        else:
            log(f"  WARN: dataset file not found, skipping: {name}")
    if not resolved:
        sys.exit("ERROR: no dataset files resolved; nothing to deposit.")
    return resolved


def api(method, url, token, data=None, headers=None):
    hdrs = {"Authorization": f"Bearer {token}"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        sys.exit(f"ERROR {method} {url} -> HTTP {e.code}\n{detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true",
                    help="publish the deposition (mint DOI); default leaves a draft")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate metadata + files, print the plan, make no network calls")
    args = ap.parse_args()

    base = os.environ.get("ZENODO_BASE", "https://zenodo.org").rstrip("/")
    meta = load_metadata()
    files = resolve_files()

    log(f"Zenodo base:   {base}")
    log(f"Title:         {meta['title'][:80]}...")
    log(f"Upload type:   {meta['upload_type']}  License: {meta.get('license')}")
    log(f"Files to send: {len(files)}")
    for name, _, size in files:
        log(f"  - {name} ({size:,} bytes)")
    log(f"Publish:       {args.publish}")

    if args.dry_run:
        # Prove the metadata is a well-formed deposit payload without touching
        # the network. json.dumps will raise if anything is unserializable.
        json.dumps({"metadata": meta})
        log("\nDRY RUN OK: metadata is a valid JSON deposit payload and all "
            "files resolve. Provide ZENODO_TOKEN to run for real.")
        return

    token = os.environ.get("ZENODO_TOKEN")
    if not token:
        sys.exit("ERROR: ZENODO_TOKEN not set. See ZENODO-RUNBOOK.md for the "
                 "one-time owner step to create it.")

    # 1. Create an empty deposition.
    log("\nCreating deposition...")
    status, dep = api("POST", f"{base}/api/deposit/depositions", token,
                      data=json.dumps({}).encode(),
                      headers={"Content-Type": "application/json"})
    dep_id = dep["id"]
    bucket = dep["links"]["bucket"]
    log(f"  deposition id: {dep_id}")

    # 2. Upload each file to the deposition bucket (new files API).
    for name, path, size in files:
        log(f"Uploading {name} ({size:,} bytes)...")
        with open(path, "rb") as fh:
            api("PUT", f"{bucket}/{name}", token, data=fh.read(),
                headers={"Content-Type": "application/octet-stream"})

    # 3. Attach metadata.
    log("Attaching metadata...")
    api("PUT", f"{base}/api/deposit/depositions/{dep_id}", token,
        data=json.dumps({"metadata": meta}).encode(),
        headers={"Content-Type": "application/json"})

    # 4. Publish (mints the DOI) unless we're leaving a draft.
    if args.publish:
        log("Publishing (minting DOI)...")
        _, pub = api("POST",
                     f"{base}/api/deposit/depositions/{dep_id}/actions/publish",
                     token)
        doi = pub.get("doi") or pub.get("metadata", {}).get("prereserve_doi", {}).get("doi")
        rec = pub.get("links", {}).get("record_html", f"{base}/records/{dep_id}")
        log(f"\nPUBLISHED. DOI: {doi}\nRecord: {rec}")
    else:
        html = dep["links"].get("html", f"{base}/deposit/{dep_id}")
        log(f"\nDRAFT created (not published). Review/publish at: {html}")


if __name__ == "__main__":
    main()
