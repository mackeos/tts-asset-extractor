#!/usr/bin/env python3
"""
Extract asset URLs from a Tabletop Simulator JSON save and download them 
into categorized folders based on asset type.
Optionally rewrites the JSON to point to local files for fully offline play.

Usage:
    python tts_download.py <path-to-json> [--proxy http://host:port]
                          [--out DIR] [--workers 8] [--list-only]
                          [--keep-steam-cdn] [--keep-imgur] [--make-offline]
"""

import argparse
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
from tqdm import tqdm

# Map of known TTS JSON keys to their asset type category
URL_KEYS_MAP = {
    "AssetbundleURL": "Assetbundles",
    "AssetbundleSecondaryURL": "Assetbundles",
    "CurrentAudioURL": "Audio",
    "Item1": "Audio",
    "ImageURL": "Images",
    "ImageSecondaryURL": "Images",
    "FaceURL": "Images",
    "BackURL": "Images",
    "DiffuseURL": "Images",
    "NormalURL": "Images",
    "PDFUrl": "PDF",
    "PDFURL": "PDF",
    "MeshURL": "Models",
    "ColliderURL": "Models",
    "LuaScript": "Text",
    "LuaScriptState": "Text",
}

# Mapping of file extensions to their target folders
EXTENSION_MAP = [
    (".unity3d", "Assetbundles"),
    (".mp3", "Audio"),
    (".jpg", "Images"),
    (".jpeg", "Images"),
    (".png", "Images"),
    (".rawt", "Images Raw"),
    (".obj", "Models"),
    (".rawm", "Models Raw"),
    (".pdf", "PDF"),
    (".txt", "Text"),
    (".lua", "Text"),
]

CT_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "application/pdf": ".pdf",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "application/octet-stream": ".unity3d",
    "text/plain": ".txt",
}

URL_REGEX = re.compile(r"https?://[^\s\"'\\]+", re.IGNORECASE)

def sanitize_filename(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9]', '', name)

def clean_url(u: str) -> str:
    return u.rstrip("\"'\\,);]")

def rewrite_imgur(url: str, enabled: bool = True) -> str:
    if not enabled:
        return url
    parsed = urlparse(url)
    if "imgur.com" in parsed.netloc:
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            return f"https://imgur.kageurufu.net/{parts[-1]}"
    return url

def rewrite_steam_cdn(url: str, enabled: bool = True) -> str:
    if not enabled:
        return url
    parsed = urlparse(url)
    if "steamusercontent.com" in parsed.netloc and "akamaihd" not in parsed.netloc:
        return parsed._replace(netloc="steamusercontent-a.akamaihd.net", scheme="https").geturl()
    return url

def extract_urls(obj, found: dict, use_steam_mirror: bool, use_imgur_mirror: bool):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                low = k.lower()
                hint = None
                for key, h in URL_KEYS_MAP.items():
                    if k == key or low.endswith(key.lower()):
                        hint = h
                        break
                
                if v.startswith("http"):
                    orig = clean_url(v)
                    clean = rewrite_steam_cdn(rewrite_imgur(orig, use_imgur_mirror), use_steam_mirror)
                    if clean not in found or (found[clean][1] is None and hint is not None):
                        found[clean] = (orig, hint)
                elif k in ("LuaScriptState", "LuaScript") and v.strip().startswith("{"):
                    try:
                        extract_urls(json.loads(v), found, use_steam_mirror, use_imgur_mirror)
                    except Exception:
                        for m in URL_REGEX.findall(v):
                            orig = clean_url(m)
                            clean = rewrite_steam_cdn(rewrite_imgur(orig, use_imgur_mirror), use_steam_mirror)
                            found.setdefault(clean, (orig, None))
                elif "http" in v:
                    for m in URL_REGEX.findall(v):
                        orig = clean_url(m)
                        clean = rewrite_steam_cdn(rewrite_imgur(orig, use_imgur_mirror), use_steam_mirror)
                        found.setdefault(clean, (orig, None))
            else:
                extract_urls(v, found, use_steam_mirror, use_imgur_mirror)
    elif isinstance(obj, list):
        for item in obj:
            extract_urls(item, found, use_steam_mirror, use_imgur_mirror)
    elif isinstance(obj, str) and obj.strip().startswith("{"):
        try:
            extract_urls(json.loads(obj), found, use_steam_mirror, use_imgur_mirror)
        except Exception:
            pass

def get_folder_and_ext(url: str, hint: str | None, content_type: str | None) -> tuple[str, str]:
    path_lower = urlparse(url).path.lower()
    for ext, folder in EXTENSION_MAP:
        if path_lower.endswith(ext):
            return folder, ext
            
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct.startswith("image/"):
        return "Images", CT_TO_EXT.get(ct, ".png")
    elif ct.startswith("audio/"):
        return "Audio", CT_TO_EXT.get(ct, ".mp3")
    elif ct == "application/pdf":
        return "PDF", ".pdf"
    elif ct.startswith("text/"):
        return "Text", ".txt"
        
    if hint:
        default_exts = {
            "Assetbundles": ".unity3d",
            "Models": ".obj",
            "Models Raw": ".rawm",
            "Images Raw": ".rawt",
            "Images": ".png",
            "Audio": ".mp3",
            "PDF": ".pdf",
            "Text": ".txt"
        }
        return hint, default_exts.get(hint, ".bin")
    return "Unknown", ".bin"

def filename_for(url: str, ext: str) -> str:
    return sanitize_filename(url) + ext

def download_one(rewritten_url: str, original_url: str, hint: str | None, base_dir: str, proxy: str | None, retries: int = 3):
    proxies = {"http": proxy, "https": proxy} if proxy else None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://tabletopsimulator.com/"
    }
    for attempt in range(1, retries + 1):
        try:
            with requests.get(rewritten_url, proxies=proxies, stream=True, timeout=60, headers=headers) as r:
                r.raise_for_status()
                content_type = r.headers.get("Content-Type", "")
                folder, ext = get_folder_and_ext(original_url, hint, content_type)
                target_dir = os.path.join(base_dir, folder)
                os.makedirs(target_dir, exist_ok=True)
                
                fname = filename_for(original_url, ext)
                path = os.path.join(target_dir, fname)
                
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    return fname, "skipped"
                    
                tmp = path + ".part"
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(8192):
                        if chunk:
                            f.write(chunk)
                os.replace(tmp, path)
            return fname, "ok"
        except Exception as e:
            last_err = e
    return None, f"failed: {last_err}"

# ==========================================
# OFFLINE MOD GENERATION LOGIC
# ==========================================

def build_local_uri_map(base_dir: str) -> dict:
    """Scans the downloaded assets folder and creates a map of {original_url: file_uri}."""
    uri_map = {}
    abs_base = os.path.abspath(base_dir)
    
    for folder in os.listdir(abs_base):
        folder_path = os.path.join(abs_base, folder)
        if not os.path.isdir(folder_path):
            continue
            
        for fname in os.listdir(folder_path):
            if fname == "_failed.txt":
                continue
                
            # To reverse-engineer the original URL, we remove the extension 
            # and un-sanitize the filename back into a URL format.
            name_without_ext = os.path.splitext(fname)[0]
            
            # The sanitizer stripped all non-alphanumeric chars.
            # We can reconstruct the original URL by inserting the symbols back.
            # But an easier hack is to just map the sanitized name to the local file path.
            # We will use this map to replace ANY url that sanitizes to this name.
            uri_map[name_without_ext] = f"file:///{folder_path.replace(chr(92), '/')}/{fname}"
            
    return uri_map

def replace_urls_in_json(obj, uri_map: dict):
    """Recursively replaces internet URLs with local file:/// URIs in the JSON data."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                if v.startswith("http"):
                    orig = clean_url(v)
                    sanitized = sanitize_filename(orig)
                    # If we downloaded this file, replace it with the local path
                    if sanitized in uri_map:
                        obj[k] = uri_map[sanitized]
                elif "http" in v and k in ("LuaScriptState", "LuaScript"):
                    # Embedded text/JSON with URLs
                    def replace_match(m):
                        orig = clean_url(m.group(0))
                        sanitized = sanitize_filename(orig)
                        return uri_map.get(sanitized, m.group(0))
                    obj[k] = URL_REGEX.sub(replace_match, v)
            else:
                replace_urls_in_json(v, uri_map)
    elif isinstance(obj, list):
        for i in range(len(obj)):
            if isinstance(obj[i], str):
                if obj[i].startswith("http"):
                    orig = clean_url(obj[i])
                    sanitized = sanitize_filename(orig)
                    if sanitized in uri_map:
                        obj[i] = uri_map[sanitized]
            else:
                replace_urls_in_json(obj[i], uri_map)
    return obj

def make_offline_json(json_file: str, out_dir: str):
    """Reads the original JSON, replaces URLs, and saves a new _offline.json file."""
    print("\n--- Making Offline JSON ---")
    uri_map = build_local_uri_map(out_dir)
    print(f"Found {len(uri_map)} downloaded assets to redirect.")
    
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    new_data = replace_urls_in_json(data, uri_map)
    
    base, ext = os.path.splitext(json_file)
    out_file = f"{base}_offline{ext}"
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, separators=(',', ':')) # Compact JSON like TTS uses
        
    print(f"Offline JSON saved to: {out_file}")

# ==========================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file", help="Path to TTS .json save file")
    ap.add_argument("--out", default="assets", help="Base output directory")
    ap.add_argument("--proxy", default=None, help="Proxy URL like http://user:pass@host:port")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--list-only", action="store_true", help="Only print URLs and detected types")
    
    ap.add_argument("--keep-steam-cdn", action="store_true", help="Do not rewrite Steam URLs to Akamai mirror")
    ap.add_argument("--keep-imgur", action="store_true", help="Do not rewrite Imgur URLs to kageurufu.net mirror")
    
    # NEW FLAG FOR OFFLINE MOD
    ap.add_argument("--make-offline", action="store_true", 
                    help="After downloading, creates a new JSON file pointing to local downloaded files.")
    
    args = ap.parse_args()

    with open(args.json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    urls_dict = {}
    extract_urls(data, urls_dict, 
                 use_steam_mirror=not args.keep_steam_cdn, 
                 use_imgur_mirror=not args.keep_imgur)
    
    urls = sorted(urls_dict.keys())

    print(f"Found {len(urls)} unique URLs")
    print(f"Steam Mirror: {'Disabled' if args.keep_steam_cdn else 'Enabled'}")
    print(f"Imgur Mirror: {'Disabled' if args.keep_imgur else 'Enabled'}")

    if args.list_only:
        for u in urls:
            orig, hint = urls_dict[u]
            folder, ext = get_folder_and_ext(orig, hint, None)
            print(f"[{folder: <12}] {orig}")
        return

    os.makedirs(args.out, exist_ok=True)

    print(f"Downloading to '{args.out}/' with {args.workers} workers"
          + (f" via proxy {args.proxy}" if args.proxy else ""))

    failed = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(download_one, u, urls_dict[u][0], urls_dict[u][1], args.out, args.proxy): u 
            for u in urls
        }
        
        for fut in tqdm(as_completed(futures), total=len(futures), unit="file"):
            url = futures[fut]
            try:
                fname, status = fut.result()
            except Exception as e:
                failed.append((url, str(e)))
                continue
            if status.startswith("failed"):
                failed.append((url, status))

    print(f"\nDone. {len(urls) - len(failed)} ok, {len(failed)} failed.")
    if failed:
        fail_path = os.path.join(args.out, "_failed.txt")
        with open(fail_path, "w", encoding="utf-8") as f:
            for u, s in failed:
                f.write(f"{u}\t{s}\n")
        print("Failed URLs written to", fail_path)

    # Run the offline JSON generator if requested
    if args.make_offline:
        make_offline_json(args.json_file, args.out)

if __name__ == "__main__":
    main()