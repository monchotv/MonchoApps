#!/usr/bin/env python3
import argparse
import base64
import json
from pathlib import Path
from urllib.request import Request, urlopen

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


FIREBASE_CONFIG_URL = "https://play-28c3e-default-rtdb.firebaseio.com/configuracion_app.json"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
)


def get_json(url):
    req = Request(url, headers={"User-Agent": DEFAULT_UA})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def decrypt_once(value, key):
    if not value or not key:
        return value
    try:
        cipher = AES.new(key.encode("utf-8"), AES.MODE_ECB)
        return unpad(cipher.decrypt(base64.b64decode(value)), AES.block_size).decode("utf-8")
    except Exception:
        return value


def decrypt_twice(value, key):
    return decrypt_once(decrypt_once(value, key), key)


def decrypt_headers(headers, key):
    if not isinstance(headers, dict):
        return headers
    return {str(k): decrypt_twice(v, key) if isinstance(v, str) else v for k, v in headers.items()}


def decrypt_channel(channel, key):
    out = dict(channel)
    if "url" in out:
        out["original_url"] = decrypt_twice(out.pop("url"), key)
    if "drm_license_uri" in out and isinstance(out["drm_license_uri"], str):
        out["drm_license_uri"] = decrypt_twice(out["drm_license_uri"], key)
    for field in ("headers", "headersUrl", "headersM3u8", "headers2"):
        if field in out:
            out[field] = decrypt_headers(out[field], key)
    return out


def build_catalog(include_hidden=False):
    config = get_json(FIREBASE_CONFIG_URL)
    key = config.get("claveapp", "")
    raw_categories = get_json(config["Channel_url"])
    categories = []
    streams = []
    index = 1

    for raw_category in raw_categories:
        category = {"name": raw_category.get("name", ""), "samples": []}
        groups = [("samples", raw_category.get("samples") or [])]
        if include_hidden:
            groups.append(("hidden_samples", raw_category.get("hidden_samples") or []))

        for group_name, samples in groups:
            for raw_channel in samples:
                channel = decrypt_channel(raw_channel, key)
                channel["globalIndex"] = index
                channel["category"] = category["name"]
                channel["source_group"] = group_name
                category["samples"].append(channel)
                streams.append(channel)
                index += 1

        categories.append(category)

    return {
        "schema": 1,
        "generated_from": {
            "firebase_config_url": FIREBASE_CONFIG_URL,
            "channel_url": config.get("Channel_url"),
        },
        "summary": {
            "categories": len(categories),
            "streams": len(streams),
            "include_hidden": include_hidden,
        },
        "categories": categories,
        "streams": streams,
    }


def main():
    parser = argparse.ArgumentParser(description="Genera original_url.json para la APK Moncho/Femon.")
    parser.add_argument("-o", "--output", default="original_url.json")
    parser.add_argument("--include-hidden", action="store_true")
    args = parser.parse_args()

    catalog = build_catalog(include_hidden=args.include_hidden)
    Path(args.output).write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {catalog['summary']['streams']} streams guardados en {args.output}")


if __name__ == "__main__":
    main()
