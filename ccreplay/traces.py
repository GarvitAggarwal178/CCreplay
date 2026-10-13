"""Trace library: scan, parse+cache, JSON-safe event/series access.

Wraps user/ccr_trace*.py and user/ccreplay_diff._detect_version_and_parse.
Never modifies, re-parses with a different schema, or re-derives a verdict
from the underlying .ccr files -- it only exposes what the existing parser
already computes.
"""
import collections
import hashlib
import json
import os
import pathlib
import threading

import ccreplay  # noqa: F401  (sets up sys.path)
from user.ccreplay_diff import _detect_version_and_parse

ROOT = ccreplay.ROOT
RAW_DIR = ROOT / "raw"
UPLOADS_DIR = ROOT / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

ABI_NAMES = {0: "Reno", 1: "CUBIC", 2: "CoVegas"}

# Two caches, not one -- measured consequence of getting this wrong: a single
# cache that retains full per-event lists for every trace it has ever parsed
# made list_traces() (the library table, which only needs counts) pull ~3.3 GB
# of Python heap and take ~5 s cold with all 15 library traces present
# (scripts/studio_measure_load.py; see STUDIO_STATUS.md). A trace's SUMMARY
# (header + counts + duration) is computed by parsing once and then
# deliberately dropping the event list -- GC reclaims it -- so list_traces()
# never retains full events. Only the small, bounded set of traces someone is
# actually looking at (get_trace/get_series/get_events, the Trace Explorer)
# keeps its full parsed events, in an LRU capped at _FULL_CACHE_MAX entries.
_FULL_CACHE_MAX = 3

_cache_lock = threading.Lock()
_summary_cache = {}  # path -> (mtime, hdr, n_dominant, n_other, duration_s, callback_counts)
_full_cache = collections.OrderedDict()  # path -> (mtime, hdr, dominant_cookie, dominant_events, other_events, CALLBACK_NAMES)


def _slug(rel_path: str) -> str:
    return rel_path.replace("/", "__").replace("\\", "__").rsplit(".ccr", 1)[0]


def _iter_trace_files():
    for base in (RAW_DIR, UPLOADS_DIR):
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.ccr")):
            yield p


def _rel(p: pathlib.Path) -> str:
    return str(p.relative_to(ROOT)).replace("\\", "/")


def _meta_path(p: pathlib.Path) -> pathlib.Path:
    return p.with_suffix("").with_suffix(p.suffix + ".meta.json") if False else p.with_name(p.stem + ".meta.json")


def _load_meta(p: pathlib.Path):
    mp = _meta_path(p)
    if mp.exists():
        try:
            return json.loads(mp.read_text())
        except Exception:
            return None
    return None


def _sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _full_cached(path: pathlib.Path):
    """Full parsed (hdr, dominant_cookie, dominant_events, other_events,
    CALLBACK_NAMES) for one trace someone is actively viewing -- bounded LRU,
    see the cache-split note above."""
    key = str(path)
    mtime = path.stat().st_mtime
    with _cache_lock:
        cached = _full_cache.get(key)
        if cached and cached[0] == mtime:
            _full_cache.move_to_end(key)
            return cached[1:]
    hdr, events, select_dominant_connection, CALLBACK_NAMES = _detect_version_and_parse(str(path))
    dominant_cookie, dominant_events, other_events = select_dominant_connection(events)
    dominant_events.sort(key=lambda e: e["seq"])
    result = (hdr, dominant_cookie, dominant_events, other_events, CALLBACK_NAMES)
    with _cache_lock:
        _full_cache[key] = (mtime,) + result
        _full_cache.move_to_end(key)
        while len(_full_cache) > _FULL_CACHE_MAX:
            _full_cache.popitem(last=False)
    return result


def _summary_cached(path: pathlib.Path):
    """Lightweight (hdr, n_dominant, n_other, duration_s, callback_counts)
    for the library table -- parses once but never retains the per-event
    list (not even in a bounded cache); only the derived scalars are kept."""
    key = str(path)
    mtime = path.stat().st_mtime
    with _cache_lock:
        cached = _summary_cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1:]
    # Reuse an already-resident full parse if this trace happens to be in the
    # LRU (e.g. just opened in the Trace Explorer) instead of parsing twice.
    with _cache_lock:
        full = _full_cache.get(key)
    if full and full[0] == mtime:
        _mtime, hdr, _cookie, dominant_events, other_events, CALLBACK_NAMES = full
    else:
        hdr, events, select_dominant_connection, CALLBACK_NAMES = _detect_version_and_parse(str(path))
        _cookie, dominant_events, other_events = select_dominant_connection(events)
    callback_counts = {}
    for e in dominant_events:
        name = CALLBACK_NAMES.get(e["callback_id"], str(e["callback_id"]))
        callback_counts[name] = callback_counts.get(name, 0) + 1
    duration_s = None
    if dominant_events:
        duration_s = (dominant_events[-1]["ts_ns"] - dominant_events[0]["ts_ns"]) / 1e9
    result = (hdr, len(dominant_events), len(other_events), duration_s, callback_counts)
    with _cache_lock:
        _summary_cache[key] = (mtime,) + result
    return result


def resolve_id(trace_id: str) -> pathlib.Path:
    for p in _iter_trace_files():
        if _slug(_rel(p)) == trace_id:
            return p
    raise KeyError(f"unknown trace id: {trace_id}")


def list_traces():
    out = []
    for p in _iter_trace_files():
        rel = _rel(p)
        tid = _slug(rel)
        try:
            hdr, n_dominant, n_other, duration_s, callback_counts = _summary_cached(p)
        except Exception as exc:  # corrupt/partial upload etc.
            out.append({"id": tid, "path": rel, "error": str(exc)})
            continue
        meta = _load_meta(p)
        out.append({
            "id": tid,
            "path": rel,
            "abi": hdr.trace_version,
            "abi_name": ABI_NAMES.get(hdr.trace_version, f"v{hdr.trace_version}"),
            "controller_name": ABI_NAMES.get(hdr.trace_version, "unknown"),
            "kernel_release": hdr.kernel_release,
            "n_dominant_events": n_dominant,
            "n_total_events": n_dominant + n_other,
            "n_other_events": n_other,
            "duration_s": duration_s,
            "callback_counts": callback_counts,
            "size_bytes": p.stat().st_size,
            "meta": meta,
        })
    out.sort(key=lambda t: t["path"])
    return out


def get_trace(trace_id: str):
    p = resolve_id(trace_id)
    hdr, n_dominant, n_other, duration_s, callback_counts = _summary_cached(p)
    meta = _load_meta(p)
    return {
        "id": trace_id,
        "path": _rel(p),
        "abi": hdr.trace_version,
        "abi_name": ABI_NAMES.get(hdr.trace_version, f"v{hdr.trace_version}"),
        "kernel_release": hdr.kernel_release,
        "reference_impl_id": hdr.reference_impl_id,
        "recorder_version": hdr.recorder_version,
        "n_dominant_events": n_dominant,
        "n_other_events": n_other,
        "duration_s": duration_s,
        "callback_counts": callback_counts,
        "size_bytes": p.stat().st_size,
        "sha256": _sha256(p),
        "meta": meta,
        "other_connections": {
            "n_other_events": n_other,
            "note": "read-only info -- CCReplay always replays the dominant connection only",
        },
    }


def _json_safe_event(e: dict) -> dict:
    out = {}
    for k, v in e.items():
        if k in ("priv_pre_raw", "priv_post_raw"):
            if isinstance(v, bytes):
                out[k] = v.hex()
            continue
        if k == "sock_cookie":
            out[k] = str(v)
            continue
        if isinstance(v, bytes):
            out[k] = v.hex()
            continue
        out[k] = v
    return out


def get_events(trace_id: str, offset: int = 0, limit: int = 100, callback: str | None = None):
    p = resolve_id(trace_id)
    hdr, dominant_cookie, dominant_events, other_events, CALLBACK_NAMES = _full_cached(p)
    name_to_id = {v: k for k, v in CALLBACK_NAMES.items()}
    events = dominant_events
    if callback:
        cb_id = name_to_id.get(callback)
        if cb_id is None:
            events = []
        else:
            events = [e for e in events if e["callback_id"] == cb_id]
    total = len(events)
    page = events[offset:offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "events": [_json_safe_event(e) for e in page],
    }


def _lttb(xs, ys, n_out):
    """Largest-Triangle-Three-Buckets downsampling. xs/ys same length,
    returns (xs_ds, ys_ds) with len <= n_out, always keeping first/last."""
    n = len(xs)
    if n_out >= n or n_out <= 2:
        return xs, ys
    sampled_x = [xs[0]]
    sampled_y = [ys[0]]
    bucket_size = (n - 2) / (n_out - 2)
    a = 0
    for i in range(n_out - 2):
        bucket_start = int((i + 0) * bucket_size) + 1
        bucket_end = int((i + 1) * bucket_size) + 1
        bucket_end = min(bucket_end, n - 1)
        next_bucket_start = int((i + 1) * bucket_size) + 1
        next_bucket_end = int((i + 2) * bucket_size) + 1
        next_bucket_end = min(next_bucket_end, n)
        if next_bucket_start >= next_bucket_end:
            next_bucket_start = max(0, next_bucket_end - 1)
        avg_x = sum(xs[next_bucket_start:next_bucket_end]) / max(1, next_bucket_end - next_bucket_start)
        avg_y = sum(ys[next_bucket_start:next_bucket_end]) / max(1, next_bucket_end - next_bucket_start)

        point_ax, point_ay = xs[a], ys[a]
        max_area = -1.0
        max_area_idx = bucket_start
        for j in range(bucket_start, bucket_end):
            area = abs(
                (point_ax - avg_x) * (ys[j] - point_ay) - (point_ax - xs[j]) * (avg_y - point_ay)
            ) * 0.5
            if area > max_area:
                max_area = area
                max_area_idx = j
        sampled_x.append(xs[max_area_idx])
        sampled_y.append(ys[max_area_idx])
        a = max_area_idx
    sampled_x.append(xs[-1])
    sampled_y.append(ys[-1])
    return sampled_x, sampled_y


def get_series(trace_id: str, fields: list[str], max_points: int = 4000,
                t0: float | None = None, t1: float | None = None):
    p = resolve_id(trace_id)
    hdr, dominant_cookie, dominant_events, other_events, CALLBACK_NAMES = _full_cached(p)
    if not dominant_events:
        return {"t": [], "series": {f: [] for f in fields}}
    first_ts = dominant_events[0]["ts_ns"]
    all_t = [(e["ts_ns"] - first_ts) / 1e9 for e in dominant_events]
    lo_idx, hi_idx = 0, len(all_t)
    if t0 is not None:
        lo_idx = next((i for i, t in enumerate(all_t) if t >= t0), len(all_t))
    if t1 is not None:
        hi_idx = next((i for i, t in enumerate(all_t) if t > t1), len(all_t))
    t_window = all_t[lo_idx:hi_idx]
    events_window = dominant_events[lo_idx:hi_idx]

    out_series = {}
    out_t = t_window
    for field in fields:
        ys = []
        for e in events_window:
            v = e.get(field)
            if field == "in_sample_rtt_us" and (v is None or v == 0):
                ys.append(None)
            else:
                ys.append(v)
        out_series[field] = ys

    if len(t_window) > max_points:
        # Downsample the first numeric field to pick representative indices,
        # then apply the same index selection to every field + t for alignment.
        ref_field = next((f for f in fields if all(isinstance(v, (int, float)) for v in out_series[f])), None)
        if ref_field is not None:
            idx_map = {v: i for i, v in enumerate(t_window)}
            ds_t, _ = _lttb(t_window, [x if x is not None else 0 for x in out_series[ref_field]], max_points)
            keep_idx = sorted({idx_map[v] for v in ds_t if v in idx_map})
            out_t = [t_window[i] for i in keep_idx]
            out_series = {f: [out_series[f][i] for i in keep_idx] for f in fields}

    return {"t": out_t, "series": out_series, "n_total_events_in_window": len(t_window)}
