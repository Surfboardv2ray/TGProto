#!/usr/bin/env python3
"""
py_tcp.py (TCP-based proxy checker)

- Reads proxies.txt (base64 or raw proxies)
- Extracts server + port
- Resolves domain → IP
- Tests TCP connection to IP:PORT
- Saves working proxies (RAW) to proxies-tested.txt
"""

import argparse
import base64
import re
import socket
import sys
import time
import threading
import concurrent.futures
from datetime import datetime, timezone
from typing import Optional, Tuple, List

INPUT_FILE = "proxies.txt"
LOG_FILE = "logs.txt"
OUTPUT_FILE = "proxies-tested.txt"

DEFAULT_CONCURRENCY = 50
DEFAULT_TIMEOUT = 2.0

IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d{1,2})(?:\.(?!$)|$)){4}\b")

_log_lock = threading.Lock()
_results_lock = threading.Lock()
_console_lock = threading.Lock()

try:
    from tqdm import tqdm
    _HAS_TQDM = True
except Exception:
    _HAS_TQDM = False


# ------------------- Utils -------------------

def clear_file(path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.truncate(0)

def append_log(line: str):
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with _log_lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{now} - {line}\n")

def try_decode_base64(s: str) -> Optional[str]:
    try:
        decoded = base64.b64decode(s.strip() + "===", validate=False)
        text = decoded.decode("utf-8", errors="replace")
        if "server=" in text or "tg://" in text or "http" in text:
            return text
    except Exception:
        pass
    return None

def split_lines(s: str) -> List[str]:
    return [l.strip() for l in s.splitlines() if l.strip()]


# ------------------- Extraction -------------------

def extract_server(s: str) -> Optional[str]:
    m = re.search(r"[?&]server=([^&\s]+)", s, re.IGNORECASE)
    if m:
        return m.group(1)
    return None

def extract_port(s: str) -> int:
    m = re.search(r"[?&]port=(\d+)", s)
    if m:
        return int(m.group(1))
    return 443

def fallback_host(s: str) -> Optional[str]:
    ip = IPV4_RE.search(s)
    if ip:
        return ip.group(0)
    m = re.search(r"([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", s)
    if m:
        return m.group(1)
    return None

def resolve(host: str) -> Optional[str]:
    try:
        return socket.gethostbyname(host)
    except Exception:
        return None


# ------------------- TCP Check -------------------

def tcp_check(ip: str, port: int, timeout: float) -> Tuple[bool, Optional[float], str]:
    start = time.time()
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            latency = (time.time() - start) * 1000
            return True, latency, "connected"
    except Exception as e:
        return False, None, str(e)


# ------------------- Processing -------------------

def process(item_idx: int, proxy: str, success: List[str], timeout: float):
    server = extract_server(proxy)
    source = "server_param"

    if not server:
        server = fallback_host(proxy)
        source = "fallback"

    if not server:
        append_log(f"[{item_idx}] SKIP - no host found")
        return

    port = extract_port(proxy)

    if IPV4_RE.fullmatch(server):
        ip = server
    else:
        ip = resolve(server)
        if not ip:
            append_log(f"[{item_idx}] SKIP - resolve failed for {server}")
            return

    append_log(f"[{item_idx}] TEST {ip}:{port} ({source})")

    ok, latency, msg = tcp_check(ip, port, timeout)

    if ok:
        append_log(f"[{item_idx}] SUCCESS {ip}:{port} {latency:.2f}ms")
        clean_proxy = proxy.strip()
        if clean_proxy:
            with _results_lock:
                success.append(clean_proxy)   # ✅ append RAW proxy

    else:
        append_log(f"[{item_idx}] FAIL {ip}:{port} ({msg})")


def gather(lines: List[str]) -> List[Tuple[int, str]]:
    items = []
    idx = 0

    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue

        decoded = try_decode_base64(raw)

        if decoded:
            for p in split_lines(decoded):
                idx += 1
                items.append((idx, p))
        else:
            for p in split_lines(raw):
                idx += 1
                items.append((idx, p))

    return items


# ------------------- Main -------------------

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("-n", "--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    p.add_argument("-t", "--timeout", type=float, default=DEFAULT_TIMEOUT)
    return p.parse_args()


def main():
    args = parse_args()
    concurrency = max(1, args.concurrency)
    timeout = max(0.1, args.timeout)

    clear_file(LOG_FILE)
    clear_file(OUTPUT_FILE)

    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print("proxies.txt not found")
        sys.exit(1)

    items = gather(lines)
    total = len(items)

    print(f"Loaded {total} proxies")

    success: List[str] = []
    done = 0

    bar = tqdm(total=total) if _HAS_TQDM else None

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)

    futures = [executor.submit(process, i, p, success, timeout) for i, p in items]

    try:
        for f in concurrent.futures.as_completed(futures):
            done += 1
            if bar:
                bar.update(1)
            else:
                with _console_lock:
                    sys.stdout.write(f"\r{done}/{total}")
                    sys.stdout.flush()

    except KeyboardInterrupt:
        print("\nInterrupted")
        for f in futures:
            f.cancel()

    finally:
        executor.shutdown(wait=False)
        if bar:
            bar.close()
        else:
            print()

    # Save results
    with _results_lock:
        unique = list(set(success))

    if unique:
        with open(OUTPUT_FILE, "w") as f:
            for x in unique:
                f.write(x + "\n")

    print(f"Done. Working: {len(unique)}/{total}")


if __name__ == "__main__":
    main()
