#!/usr/bin/python3
from __future__ import annotations

import argparse
import datetime
import fcntl
import glob
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

UTC = datetime.timezone.utc
ROLES = ("user", "assistant")
CLAUDE_SKIP_PREFIXES = (
    "<local-command-caveat>",
    "<command-name>",
    "<local-command-stdout>",
)
CODEX_SID = re.compile(
    r"-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$",
    re.I,
)
ISO_FRAC = re.compile(
    r"^(.*T\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$",
)
JSONL_GLOBS = (
    (
        "codex",
        (
            "~/.codex/sessions/**/*.jsonl",
            "~/code/codex-home/sessions/**/*.jsonl",
        ),
    ),
    (
        "claude",
        (
            "~/.claude/projects/**/*.jsonl",
            "~/.claude-glm/projects/**/*.jsonl",
            "~/.klaude/projects/**/*.jsonl",
        ),
    ),
    ("omp", ("~/.omp/agent/sessions/*/*.jsonl",)),
    ("pi", ("~/.pi/agent/sessions/*/*.jsonl",)),
    ("grok", ("~/.grok/sessions/*/*/chat_history.jsonl",)),
    ("cursor", ("~/.cursor/projects/*/agent-transcripts/*/*.jsonl",)),
)
HERMES_GLOBS = ("~/.hermes/state.db", "~/.hermes/profiles/*/state.db")
OPENCODE_GLOBS = ("~/.local/share/opencode/opencode.db",)
HUB_HOST = "agent-box"
REMOTE_HOME = "~/.local/share/agent-memory"
OPENCODE_GRACE_MS = 120000
HOSTS = ["johns-macbook-air", "mbp", "mini", "agent-box"]


def mem_home():
    return os.path.expanduser(
        os.environ.get("AGENT_MEMORY_HOME", "~/.local/share/agent-memory")
    )


def host_id():
    return os.environ.get("AGENT_MEMORY_HOST") or socket.gethostname().split(".")[0]


def is_hub():
    return os.environ.get("AGENT_MEMORY_ROLE") == "hub"


def user_home():
    return os.path.expanduser("~")


def ensure_dirs(home):
    for part in ("out", "in", "logs"):
        os.makedirs(os.path.join(home, part), exist_ok=True)


def state_path(home):
    return os.path.join(home, "state.json")


def out_path(home, host):
    return os.path.join(home, "out", host + ".jsonl")


def load_state(home):
    path = state_path(home)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def atomic_write(path, data):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_state(home, state):
    atomic_write(state_path(home), json.dumps(state, sort_keys=True) + "\n")


def acquire_lock(home):
    path = os.path.join(home, "lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def rel_native(path):
    home = user_home()
    try:
        return os.path.relpath(path, home)
    except ValueError:
        return path


def to_ts(value, fallback_mtime=None):
    dt = None
    if isinstance(value, bool):
        value = None
    if isinstance(value, (int, float)):
        x = float(value)
        if x >= 1e11:
            x /= 1000.0
        try:
            dt = datetime.datetime.fromtimestamp(x, UTC)
        except (OSError, OverflowError, ValueError):
            dt = None
    elif isinstance(value, str) and value.strip():
        s = value.strip()
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        match = ISO_FRAC.match(s)
        if match is not None:
            frac = match.group(2) or ""
            if len(frac) > 7:
                frac = frac[:7]
            s = match.group(1) + frac + (match.group(3) or "")
        try:
            dt = datetime.datetime.fromisoformat(s)
        except ValueError:
            dt = None
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            else:
                dt = dt.astimezone(UTC)
    if dt is None and fallback_mtime is not None:
        try:
            dt = datetime.datetime.fromtimestamp(float(fallback_mtime), UTC)
        except (OSError, OverflowError, ValueError):
            dt = None
    if dt is None:
        dt = datetime.datetime.now(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + ".%03dZ" % (dt.microsecond // 1000)


def now_ts():
    return to_ts(None)


def discover(patterns):
    seen = []
    found = set()
    for pattern in patterns:
        for path in glob.glob(os.path.expanduser(pattern), recursive=True):
            if path in found:
                continue
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            found.add(path)
            seen.append(path)
    seen.sort()
    return seen


def parts_text(parts, pred):
    if isinstance(parts, str):
        return parts
    if not isinstance(parts, list):
        return ""
    bits = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if pred(part.get("type")) and isinstance(part.get("text"), str):
            bits.append(part["text"])
    return "\n".join(bits)


def record(host, runtime, session_id, line_key, ts, role, text, path):
    text = text.strip() if isinstance(text, str) else ""
    if not text or role not in ROLES:
        return None
    sid = session_id or "unknown"
    return {
        "host": host,
        "key": "%s/%s/%s" % (runtime, sid, line_key),
        "path": rel_native(path),
        "role": role,
        "runtime": runtime,
        "session_id": sid,
        "text": text,
        "ts": ts,
    }


def stem_of(path):
    return os.path.splitext(os.path.basename(path))[0]


def extract_codex(obj, path, lines, mtime):
    if obj.get("type") != "response_item":
        return None
    payload = obj.get("payload") or {}
    if payload.get("type") != "message":
        return None
    role = payload.get("role")
    text = parts_text(
        payload.get("content"),
        lambda t: isinstance(t, str) and t.endswith("_text"),
    )
    match = CODEX_SID.search(path)
    sid = match.group(1) if match else stem_of(path)
    line_key = payload.get("id") or ("L%d" % lines)
    return record(
        host_id(), "codex", sid, line_key, to_ts(obj.get("timestamp"), mtime), role, text, path
    )


def extract_claude(obj, path, lines, mtime):
    if obj.get("type") not in ROLES:
        return None
    if obj.get("isMeta") is True:
        return None
    message = obj.get("message") or {}
    role = message.get("role") or obj.get("type")
    content = message.get("content")
    if isinstance(content, str):
        text = content
    else:
        text = parts_text(content, lambda t: t == "text")
    if role == "user":
        stripped = text.lstrip()
        for prefix in CLAUDE_SKIP_PREFIXES:
            if stripped.startswith(prefix):
                return None
    sid = obj.get("sessionId") or stem_of(path)
    line_key = obj.get("uuid") or ("L%d" % lines)
    return record(
        host_id(), "claude", sid, line_key, to_ts(obj.get("timestamp"), mtime), role, text, path
    )


def extract_omp_pi(runtime):
    def extract(obj, path, lines, mtime):
        if obj.get("type") != "message":
            return None
        message = obj.get("message") or {}
        role = message.get("role")
        text = parts_text(message.get("content"), lambda t: t == "text")
        stem = stem_of(path)
        sid = stem.split("_", 1)[1] if "_" in stem else stem
        line_key = obj.get("id") or ("L%d" % lines)
        return record(
            host_id(), runtime, sid, line_key, to_ts(obj.get("timestamp"), mtime), role, text, path
        )

    return extract


def grok_updated_at(path):
    summary = os.path.join(os.path.dirname(path), "summary.json")
    try:
        with open(summary, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data.get("updated_at")
    except (OSError, ValueError):
        return None
    return None


def extract_grok(obj, path, lines, mtime):
    role = obj.get("type")
    if role not in ROLES:
        return None
    if role == "user" and "synthetic_reason" in obj:
        return None
    content = obj.get("content")
    if role == "assistant" and isinstance(content, str):
        text = content
    else:
        text = parts_text(content, lambda t: t == "text")
    sid = os.path.basename(os.path.dirname(path))
    ts = to_ts(grok_updated_at(path), mtime)
    return record(host_id(), "grok", sid, "L%d" % lines, ts, role, text, path)


def extract_cursor(obj, path, lines, mtime):
    if obj.get("type") == "turn_ended":
        return None
    role = obj.get("role")
    message = obj.get("message") or {}
    text = parts_text(message.get("content"), lambda t: t == "text")
    return record(
        host_id(),
        "cursor",
        stem_of(path),
        "L%d" % lines,
        to_ts(None, mtime),
        role,
        text,
        path,
    )


EXTRACTORS = {
    "codex": extract_codex,
    "claude": extract_claude,
    "omp": extract_omp_pi("omp"),
    "pi": extract_omp_pi("pi"),
    "grok": extract_grok,
    "cursor": extract_cursor,
}


def tail_file(path, cursor, extract, host, runtime, out_fh, status):
    st = os.stat(path)
    if cursor is None or st.st_ino != cursor.get("ino") or st.st_size < cursor.get("size", 0):
        offset = 0
        lines = 0
    elif st.st_size == cursor.get("size"):
        return {
            "ino": st.st_ino,
            "size": st.st_size,
            "offset": cursor.get("offset", 0),
            "lines": cursor.get("lines", 0),
        }, 0
    else:
        offset = cursor.get("offset", 0)
        lines = cursor.get("lines", 0)
    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read()
    end = data.rfind(b"\n")
    if end < 0:
        return {
            "ino": st.st_ino,
            "size": st.st_size,
            "offset": offset,
            "lines": lines,
        }, 0
    emitted = 0
    chunk = data[: end + 1]
    parts = chunk.split(b"\n")
    if parts and parts[-1] == b"":
        parts.pop()
    for raw in parts:
        lines += 1
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            status["malformed"] += 1
            continue
        if not isinstance(obj, dict):
            continue
        rec = extract(obj, path, lines, st.st_mtime)
        if rec is None:
            continue
        out_fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        emitted += 1
    return {
        "ino": st.st_ino,
        "size": st.st_size,
        "offset": offset + end + 1,
        "lines": lines,
    }, emitted


def capture_jsonl(home, host, state, out_fh, status):
    for runtime, patterns in JSONL_GLOBS:
        extract = EXTRACTORS[runtime]
        for path in discover(patterns):
            status["files_tracked"] += 1
            cursor = state.get(path)
            try:
                new_cursor, n = tail_file(
                    path, cursor, extract, host, runtime, out_fh, status
                )
            except OSError as exc:
                status["errors"].append("%s: %s" % (path, exc))
                continue
            state[path] = new_cursor
            status["emitted"] += n


def open_sqlite(path):
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True)


def sqlite_key(path):
    return "sqlite:" + path


def capture_hermes(home, host, state, out_fh, status):
    for path in discover(HERMES_GLOBS):
        status["files_tracked"] += 1
        mark_key = sqlite_key(path)
        mark = (state.get(mark_key) or {}).get("messages_max_id", 0)
        try:
            con = open_sqlite(path)
        except sqlite3.Error as exc:
            status["errors"].append("sqlite %s: %s" % (path, exc))
            continue
        try:
            rows = con.execute(
                "SELECT id, session_id, role, content, timestamp FROM messages "
                "WHERE role IN ('user','assistant') AND id > ? ORDER BY id",
                (mark,),
            ).fetchall()
        except sqlite3.Error as exc:
            status["errors"].append("sqlite %s: %s" % (path, exc))
            con.close()
            continue
        con.close()
        last = mark
        for row_id, session_id, role, content, timestamp in rows:
            rec = record(
                host,
                "hermes",
                session_id,
                str(row_id),
                to_ts(timestamp),
                role,
                content if isinstance(content, str) else "",
                path,
            )
            if rec is None:
                last = row_id
                continue
            out_fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            status["emitted"] += 1
            last = row_id
        state[mark_key] = {"messages_max_id": last}


def capture_opencode(home, host, state, out_fh, status):
    upper = int(time.time() * 1000) - OPENCODE_GRACE_MS
    for path in discover(OPENCODE_GLOBS):
        status["files_tracked"] += 1
        mark_key = sqlite_key(path)
        mark = (state.get(mark_key) or {}).get("messages_max_id", 0)
        try:
            con = open_sqlite(path)
        except sqlite3.Error as exc:
            status["errors"].append("sqlite %s: %s" % (path, exc))
            continue
        try:
            rows = con.execute(
                "SELECT p.id, p.session_id, json_extract(m.data,'$.role'), "
                "json_extract(p.data,'$.text'), p.time_created "
                "FROM part p JOIN message m ON m.id=p.message_id "
                "WHERE json_extract(p.data,'$.type')='text' "
                "AND COALESCE(json_extract(p.data,'$.ignored'),0)=0 "
                "AND json_extract(m.data,'$.role') IN ('user','assistant') "
                "AND p.time_created > ? AND p.time_created < ? "
                "ORDER BY p.time_created, p.id",
                (mark, upper),
            ).fetchall()
        except sqlite3.Error as exc:
            status["errors"].append("sqlite %s: %s" % (path, exc))
            con.close()
            continue
        con.close()
        last = mark
        for part_id, session_id, role, text, time_created in rows:
            rec = record(
                host,
                "opencode",
                session_id,
                str(part_id),
                to_ts(time_created),
                role,
                text if isinstance(text, str) else "",
                path,
            )
            if rec is None:
                last = time_created
                continue
            out_fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            status["emitted"] += 1
            last = time_created
        state[mark_key] = {"messages_max_id": last}


def cmd_capture(_args):
    home = mem_home()
    host = host_id()
    ensure_dirs(home)
    lock = acquire_lock(home)
    if lock is None:
        return 0
    try:
        return _capture(home, host)
    finally:
        os.close(lock)


def _capture(home, host):
    state = load_state(home)
    status = {"malformed": 0, "errors": [], "files_tracked": 0, "emitted": 0}
    dest = out_path(home, host)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "a", encoding="utf-8") as out_fh:
        capture_jsonl(home, host, state, out_fh, status)
        capture_hermes(home, host, state, out_fh, status)
        capture_opencode(home, host, state, out_fh, status)
        out_fh.flush()
        os.fsync(out_fh.fileno())
    meta = state.get("_meta") or {}
    meta.update(
        {
            "last_capture": now_ts(),
            "malformed": status["malformed"],
            "errors": status["errors"],
            "files_tracked": status["files_tracked"],
            "emitted": status["emitted"],
        }
    )
    state["_meta"] = meta
    save_state(home, state)
    return 0


def rsync_cmd(extra, src, dest):
    cmd = ["/usr/bin/rsync", "-az"] + extra + [src, dest]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stderr.decode("utf-8", "replace")


def append_flag():
    proc = subprocess.run(
        ["/usr/bin/rsync", "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    text = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    if "--append-verify" in text:
        return ["--append-verify"]
    return []


def remote(path):
    return "%s:%s/%s" % (HUB_HOST, REMOTE_HOME, path)


def cmd_push(_args):
    home = mem_home()
    host = host_id()
    src = out_path(home, host)
    if not os.path.exists(src):
        return 0
    code, err = rsync_cmd(append_flag(), src, remote("in/%s.jsonl" % host))
    if code != 0:
        sys.stderr.write(err)
        return 1
    return 0


def source_paths(home):
    paths = []
    for folder in ("in", "out"):
        paths.extend(
            discover((os.path.join(home, folder, "*.jsonl"),))
        )
    return paths


def input_sizes(home):
    sizes = {}
    for path in source_paths(home):
        try:
            sizes[path] = os.path.getsize(path)
        except OSError:
            continue
    return sizes


def read_jsonl_records(path, seen, rows, errors):
    try:
        fh = open(path, "r", encoding="utf-8")
    except OSError as exc:
        errors.append("%s: %s" % (path, exc))
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            key = rec.get("key")
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append(rec)


def rebuild_fts(home, rows):
    dest = os.path.join(home, "memory.sqlite")
    tmp = dest + ".tmp"
    if os.path.exists(tmp):
        os.unlink(tmp)
    con = sqlite3.connect(tmp)
    try:
        con.execute(
            "CREATE VIRTUAL TABLE mem USING fts5("
            "key UNINDEXED, host UNINDEXED, runtime UNINDEXED, "
            "session_id UNINDEXED, ts UNINDEXED, role UNINDEXED, text)"
        )
        con.executemany(
            "INSERT INTO mem (key, host, runtime, session_id, ts, role, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    rec.get("key") or "",
                    rec.get("host") or "",
                    rec.get("runtime") or "",
                    rec.get("session_id") or "",
                    rec.get("ts") or "",
                    rec.get("role") or "",
                    rec.get("text") or "",
                )
                for rec in rows
            ],
        )
        con.commit()
    finally:
        con.close()
    os.replace(tmp, dest)


def cmd_merge(_args):
    home = mem_home()
    ensure_dirs(home)
    lock = acquire_lock(home)
    if lock is None:
        return 0
    try:
        return _merge(home)
    finally:
        os.close(lock)


def _merge(home):
    mem_path = os.path.join(home, "memory.jsonl")
    sizes = input_sizes(home)
    if os.path.exists(mem_path):
        prev = (load_state(home).get("_meta") or {}).get("merge_inputs")
        if isinstance(prev, dict) and sizes == prev:
            return 0
    seen = set()
    rows = []
    errors = []
    for path in sorted(sizes):
        read_jsonl_records(path, seen, rows, errors)
    rows.sort(key=lambda rec: (rec.get("ts") or "", rec.get("key") or ""))
    tmp = mem_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for rec in rows:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, mem_path)
    rebuild_fts(home, rows)
    state = load_state(home)
    meta = state.get("_meta") or {}
    if errors:
        meta["errors"] = list(meta.get("errors") or []) + errors
    meta["merge_inputs"] = sizes
    state["_meta"] = meta
    save_state(home, state)
    return 0


def cmd_pull(_args):
    home = mem_home()
    ensure_dirs(home)
    lock = acquire_lock(home)
    if lock is None:
        return 0
    try:
        for name in ("memory.jsonl", "memory.sqlite"):
            dest = os.path.join(home, name)
            code, err = rsync_cmd([], remote(name), dest)
            if code != 0:
                sys.stderr.write(err)
                return 1
        return 0
    finally:
        os.close(lock)


def fts_phrase(phrase):
    return '"' + phrase.replace('"', '""') + '"'


def fallback_snippet(text, phrase):
    lower = text.lower()
    needle = phrase.lower()
    idx = lower.find(needle)
    if idx < 0:
        return text[:120]
    start = max(0, idx - 40)
    end = min(len(text), idx + len(phrase) + 40)
    chunk = text[start:end]
    local = chunk.lower().find(needle)
    if local >= 0:
        chunk = (
            chunk[:local]
            + "["
            + chunk[local : local + len(phrase)]
            + "]"
            + chunk[local + len(phrase) :]
        )
    prefix = " … " if start else ""
    suffix = " … " if end < len(text) else ""
    return prefix + chunk + suffix


def print_hit(rec):
    sys.stdout.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def cmd_search(args):
    home = mem_home()
    phrase = args.phrase
    limit = args.limit
    index = os.path.join(home, "memory.sqlite")
    if os.path.exists(index):
        try:
            con = sqlite3.connect("file:%s?mode=ro" % index, uri=True)
            rows = con.execute(
                "SELECT key, host, runtime, session_id, ts, role, "
                "snippet(mem, 6, '[', ']', ' … ', 24) "
                "FROM mem WHERE mem MATCH ? ORDER BY ts DESC LIMIT ?",
                (fts_phrase(phrase), limit),
            ).fetchall()
            con.close()
            for key, host, runtime, session_id, ts, role, snippet in rows:
                print_hit(
                    {
                        "host": host,
                        "key": key,
                        "role": role,
                        "runtime": runtime,
                        "session_id": session_id,
                        "snippet": snippet,
                        "ts": ts,
                    }
                )
            return 0
        except sqlite3.Error:
            pass
    path = os.path.join(home, "memory.jsonl")
    if not os.path.exists(path):
        return 0
    needle = phrase.lower()
    hits = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            text = rec.get("text") or ""
            if needle not in text.lower():
                continue
            hits.append(
                {
                    "host": rec.get("host"),
                    "key": rec.get("key"),
                    "role": rec.get("role"),
                    "runtime": rec.get("runtime"),
                    "session_id": rec.get("session_id"),
                    "snippet": fallback_snippet(text, phrase),
                    "ts": rec.get("ts"),
                }
            )
    hits.sort(key=lambda rec: rec.get("ts") or "", reverse=True)
    for rec in hits[:limit]:
        print_hit(rec)
    return 0


def count_lines(path):
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            n += chunk.count(b"\n")
    return n


def cmd_status(_args):
    home = mem_home()
    host = host_id()
    state = load_state(home)
    meta = state.get("_meta") or {}
    mem_path = os.path.join(home, "memory.jsonl")
    memory_mtime = None
    if os.path.exists(mem_path):
        memory_mtime = to_ts(os.path.getmtime(mem_path))
    payload = {
        "errors": list(meta.get("errors") or []),
        "files_tracked": meta.get("files_tracked", 0),
        "host": host,
        "last_capture": meta.get("last_capture"),
        "lines_out": count_lines(out_path(home, host)),
        "malformed": meta.get("malformed", 0),
        "memory_lines": count_lines(mem_path),
        "memory_mtime": memory_mtime,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


def cmd_cycle(_args):
    home = mem_home()
    host = host_id()
    ensure_dirs(home)
    lock = acquire_lock(home)
    if lock is None:
        return 0
    try:
        code = _capture(home, host)
        if code != 0:
            return code
        if is_hub():
            return _merge(home)
        code = cmd_push(_args)
        if code != 0:
            return code
        # pull without taking a second lock
        for name in ("memory.jsonl", "memory.sqlite"):
            dest = os.path.join(home, name)
            pcode, err = rsync_cmd([], remote(name), dest)
            if pcode != 0:
                sys.stderr.write(err)
                return 1
        return 0
    finally:
        os.close(lock)


def build_parser():
    parser = argparse.ArgumentParser(prog="agent-memory")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("capture").set_defaults(func=cmd_capture)
    sub.add_parser("merge").set_defaults(func=cmd_merge)
    sub.add_parser("push").set_defaults(func=cmd_push)
    sub.add_parser("pull").set_defaults(func=cmd_pull)
    search = sub.add_parser("search")
    search.add_argument("phrase")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--json", action="store_true")
    search.set_defaults(func=cmd_search)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("cycle").set_defaults(func=cmd_cycle)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
