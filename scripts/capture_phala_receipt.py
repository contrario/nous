from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

DEFAULT_BASE_URL = "https://api.redpill.ai/v1"
DEFAULT_MODEL = "phala/deepseek-r1-70b"
DEFAULT_PROMPT = "Reply with exactly the two words: attested receipt."
SCHEME = "phala_response_sig_v1"


def compute_sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_text(request_sha256: str, response_sha256: str) -> str:
    return f"{request_sha256}:{response_sha256}"


def build_bundle(
    *,
    model: str,
    base_url: str,
    request_body: bytes,
    response_body: bytes,
    signature_hex: str,
    signing_address: Optional[str],
    intel_quote: Optional[str],
    nvidia_payload: Optional[str],
    captured_at: str,
) -> dict[str, object]:
    request_sha256 = compute_sha256_hex(request_body)
    response_sha256 = compute_sha256_hex(response_body)
    return {
        "scheme": SCHEME,
        "model": model,
        "base_url": base_url,
        "request_body": request_body.decode("utf-8"),
        "request_sha256": request_sha256,
        "response_body": response_body.decode("utf-8"),
        "response_sha256": response_sha256,
        "text": build_text(request_sha256, response_sha256),
        "signature_hex": signature_hex,
        "signing_address": signing_address,
        "intel_quote_sha256": (
            compute_sha256_hex(intel_quote.encode("utf-8"))
            if intel_quote
            else None
        ),
        "nvidia_payload_sha256": (
            compute_sha256_hex(nvidia_payload.encode("utf-8"))
            if nvidia_payload
            else None
        ),
        "captured_at": captured_at,
    }


def assert_bundle_consistent(bundle: dict[str, object], vendor_text: str) -> None:
    if bundle["text"] != vendor_text:
        raise RuntimeError(
            f"text mismatch: vendor {vendor_text!r} != reconstructed {bundle['text']!r}"
        )


def capture(
    api_key: str,
    *,
    model: str,
    base_url: str,
    prompt: str,
) -> dict[str, object]:
    auth = {"Authorization": f"Bearer {api_key}"}
    post_headers = {**auth, "Content-Type": "application/json"}
    with httpx.Client(timeout=60.0) as client:
        report = client.get(
            f"{base_url}/attestation/report",
            params={"model": model},
            headers=auth,
        )
        report.raise_for_status()
        report_json = report.json()

        request_obj = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        request_body = json.dumps(request_obj, separators=(",", ":")).encode("utf-8")
        completion = client.post(
            f"{base_url}/chat/completions",
            content=request_body,
            headers=post_headers,
        )
        completion.raise_for_status()
        response_body = completion.content
        response_id = completion.json().get("id")
        if not response_id:
            raise RuntimeError("completion response has no id")

        signature = client.get(
            f"{base_url}/signature/{response_id}",
            params={"model": model, "signing_algo": "ecdsa"},
            headers=auth,
        )
        signature.raise_for_status()
        signature_json = signature.json()

    bundle = build_bundle(
        model=model,
        base_url=base_url,
        request_body=request_body,
        response_body=response_body,
        signature_hex=signature_json.get("signature", ""),
        signing_address=report_json.get("signing_address"),
        intel_quote=report_json.get("intel_quote"),
        nvidia_payload=report_json.get("nvidia_payload"),
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
    assert_bundle_consistent(bundle, signature_json.get("text", ""))
    return bundle


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture a genuine redpill/Phala signed inference receipt bundle."
    )
    parser.add_argument("--api-key", default=os.environ.get("REDPILL_API_KEY"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if not args.api_key:
        print(
            "error: no API key (pass --api-key or set REDPILL_API_KEY)",
            file=sys.stderr,
        )
        return 2

    bundle = capture(
        args.api_key,
        model=args.model,
        base_url=args.base_url,
        prompt=args.prompt,
    )
    out_path = Path(args.out)
    out_path.write_text(
        json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"captured receipt bundle -> {out_path}")
    print(f"  signing_address: {bundle['signing_address']}")
    print(f"  text: {bundle['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
