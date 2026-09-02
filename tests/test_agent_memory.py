#!/usr/bin/python3
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import agent_memory as am  # noqa: E402

TS_RE = r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$"
CODEX_UUID = "01a05da2-770b-7503-b546-9bad3cdc134b"


def dump(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            if isinstance(row, str):
                fh.write(row)
                if not row.endswith("\n"):
                    fh.write("\n")
            else:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_out(home, host):
    path = os.path.join(home, "out", host + ".jsonl")
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            rows.append(json.loads(line))
    return rows


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "am")
        self.user = os.path.join(self.tmp.name, "user")
        os.makedirs(self.user)
        self.old = os.environ.copy()
        os.environ["HOME"] = self.user
        os.environ["AGENT_MEMORY_HOME"] = self.home
        os.environ["AGENT_MEMORY_HOST"] = "johns-macbook-air"
        os.environ.pop("AGENT_MEMORY_ROLE", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old)
        self.tmp.cleanup()

    def capture(self):
        self.assertEqual(am.main(["capture"]), 0)

    def merge(self):
        os.environ["AGENT_MEMORY_ROLE"] = "hub"
        os.environ["AGENT_MEMORY_HOST"] = "agent-box"
        self.assertEqual(am.main(["merge"]), 0)

    def test_to_ts_formats(self):
        self.assertRegex(am.to_ts("2026-09-01T12:00:00.000Z"), TS_RE)
        self.assertEqual(am.to_ts("2026-09-01T12:00:00.000Z"), "2026-09-01T12:00:00.000Z")
        self.assertEqual(am.to_ts("2026-08-31T15:43:51.592852044Z"), "2026-08-31T15:43:51.592Z")
        self.assertEqual(am.to_ts(1750000000.0), "2025-06-15T15:06:40.000Z")
        self.assertEqual(am.to_ts(1750000000123), "2025-06-15T15:06:40.123Z")
        self.assertEqual(am.to_ts(1788380179006471), "2026-09-02T20:16:19.006Z")
        self.assertRegex(am.to_ts(None, 1750000000.0), TS_RE)

    def test_capture_all_file_runtimes(self):
        dump(
            os.path.join(
                self.user,
                ".codex/sessions/2026/09/01/rollout-2026-09-01T16-42-03-%s.jsonl" % CODEX_UUID,
            ),
            [
                {
                    "timestamp": "2026-09-01T12:00:00.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "id": "msg_user",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "codex hello"}],
                    },
                },
                {
                    "timestamp": "2026-09-01T12:00:01.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "id": "msg_dev",
                        "role": "developer",
                        "content": [{"type": "input_text", "text": "skip me"}],
                    },
                },
                {
                    "timestamp": "2026-09-01T12:00:02.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "id": "msg_asst",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "codex hi"}],
                    },
                },
            ],
        )
        dump(
            os.path.join(self.user, ".claude/projects/p/sess.jsonl"),
            [
                {
                    "type": "user",
                    "isMeta": False,
                    "sessionId": "claude-sid",
                    "uuid": "u1",
                    "timestamp": "2026-09-01T12:00:00.000Z",
                    "message": {"role": "user", "content": "claude hello"},
                },
                {
                    "type": "user",
                    "isMeta": True,
                    "sessionId": "claude-sid",
                    "uuid": "meta",
                    "timestamp": "2026-09-01T12:00:00.000Z",
                    "message": {"role": "user", "content": "meta"},
                },
                {
                    "type": "user",
                    "sessionId": "claude-sid",
                    "uuid": "cmd",
                    "timestamp": "2026-09-01T12:00:00.000Z",
                    "message": {
                        "role": "user",
                        "content": "<command-name>/model</command-name>",
                    },
                },
                {
                    "type": "assistant",
                    "sessionId": "claude-sid",
                    "uuid": "a1",
                    "timestamp": "2026-09-01T12:00:01.000Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "thinking", "text": "nope"},
                            {"type": "text", "text": "claude hi"},
                        ],
                    },
                },
            ],
        )
        dump(
            os.path.join(
                self.user,
                ".omp/agent/sessions/proj/2026-09-01T12-00-00-000Z_omp-sid.jsonl",
            ),
            [
                {
                    "type": "title",
                    "title": "ignore",
                },
                {
                    "type": "message",
                    "id": "m1",
                    "timestamp": "2026-09-01T12:00:00.000Z",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": "omp hello"}],
                    },
                },
                {
                    "type": "message",
                    "id": "m2",
                    "timestamp": "2026-09-01T12:00:01.000Z",
                    "message": {
                        "role": "developer",
                        "content": [{"type": "text", "text": "dev"}],
                    },
                },
                {
                    "type": "message",
                    "id": "m3",
                    "timestamp": "2026-09-01T12:00:02.000Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "thinking", "thinking": "x"},
                            {"type": "text", "text": "omp hi"},
                        ],
                    },
                },
            ],
        )
        grok_dir = os.path.join(self.user, ".grok/sessions/proj/grok-sid")
        dump(
            os.path.join(grok_dir, "chat_history.jsonl"),
            [
                {"type": "system", "content": "ignore"},
                {
                    "type": "user",
                    "content": [{"type": "text", "text": "grok hello"}],
                },
                {
                    "type": "user",
                    "synthetic_reason": "retry",
                    "content": [{"type": "text", "text": "skip synth"}],
                },
                {"type": "assistant", "content": "grok hi"},
            ],
        )
        with open(os.path.join(grok_dir, "summary.json"), "w", encoding="utf-8") as fh:
            json.dump({"updated_at": "2026-08-31T15:43:51.592852044Z"}, fh)
        dump(
            os.path.join(
                self.user,
                ".cursor/projects/p/agent-transcripts/t/cursor-sid.jsonl",
            ),
            [
                {
                    "role": "user",
                    "message": {"content": [{"type": "text", "text": "cursor hello"}]},
                },
                {"type": "turn_ended"},
                {
                    "role": "assistant",
                    "message": {"content": [{"type": "text", "text": "cursor hi"}]},
                },
            ],
        )
        self.capture()
        rows = load_out(self.home, "johns-macbook-air")
        runtimes = sorted(set(r["runtime"] for r in rows))
        self.assertEqual(runtimes, ["claude", "codex", "cursor", "grok", "omp"])
        texts = sorted(r["text"] for r in rows)
        self.assertEqual(
            texts,
            [
                "claude hello",
                "claude hi",
                "codex hello",
                "codex hi",
                "cursor hello",
                "cursor hi",
                "grok hello",
                "grok hi",
                "omp hello",
                "omp hi",
            ],
        )
        for row in rows:
            self.assertIn(row["role"], ("user", "assistant"))
            self.assertRegex(row["ts"], TS_RE)
        keys = [r["key"] for r in rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(any(r["key"].startswith("codex/%s/" % CODEX_UUID) for r in rows))
        self.assertTrue(any(r["session_id"] == "omp-sid" for r in rows))
        grok = [r for r in rows if r["runtime"] == "grok"]
        self.assertEqual(grok[0]["ts"], "2026-08-31T15:43:51.592Z")
        n = len(rows)
        self.capture()
        self.assertEqual(len(load_out(self.home, "johns-macbook-air")), n)

    def test_capture_muse(self):
        sid = "muse-sid-1"
        child = "muse-child-1"
        dump(
            os.path.join(
                self.user,
                ".local/share/muse/sessions/2026/09/02/%s/session.jsonl" % sid,
            ),
            [
                {"record_type": "retained_marker"},
                {
                    "schema_version": 1,
                    "id": "e0",
                    "stream": {"kind": "main", "id": sid},
                    "sequence": 0,
                    "recorded_at": 1788380179006471,
                    "record_type": "envelope",
                    "payload_type": "runtime.session.metadata",
                    "payload": {},
                },
                {
                    "schema_version": 1,
                    "id": "e1",
                    "stream": {"kind": "main", "id": sid},
                    "sequence": 1,
                    "recorded_at": 1788380179006471,
                    "record_type": "envelope",
                    "payload_type": "runtime.user_intent.accepted",
                    "payload": {
                        "surface": "main",
                        "intent_id": "i1",
                        "model_messages": [
                            {"content": [{"kind": "text", "text": "muse hello"}]}
                        ],
                    },
                },
                {
                    "schema_version": 1,
                    "id": "e2",
                    "stream": {"kind": "main", "id": sid},
                    "sequence": 2,
                    "recorded_at": 1788380179006471,
                    "record_type": "envelope",
                    "payload_type": "runtime.session",
                    "payload": {"kind": "run", "event": {"kind": "task_stream_linked"}},
                },
                {
                    "schema_version": 1,
                    "id": "e3",
                    "stream": {"kind": "main", "id": sid},
                    "sequence": 3,
                    "recorded_at": 1788380179006471,
                    "record_type": "envelope",
                    "payload_type": "runtime.session",
                    "payload": {
                        "kind": "run",
                        "event": {
                            "kind": "assistant_message_committed",
                            "text": "muse hi",
                            "message_id": "m1",
                        },
                    },
                },
                {
                    "schema_version": 1,
                    "id": "e4",
                    "stream": {"kind": "main", "id": sid},
                    "sequence": 4,
                    "recorded_at": 1788380179006471,
                    "record_type": "envelope",
                    "payload_type": "runtime.session",
                    "payload": {"kind": "run"},
                },
            ],
        )
        dump(
            os.path.join(
                self.user,
                ".local/share/muse/sessions/2026/09/02/%s/subagent/%s/session.jsonl" % (sid, child),
            ),
            [
                {
                    "schema_version": 1,
                    "id": "c1",
                    "stream": {"kind": "subagent", "id": child},
                    "sequence": 0,
                    "recorded_at": 1788380179006471,
                    "record_type": "envelope",
                    "payload_type": "runtime.session",
                    "payload": {
                        "kind": "run",
                        "event": {
                            "kind": "assistant_message_committed",
                            "text": "child hi",
                            "message_id": "c1",
                        },
                    },
                },
            ],
        )
        self.capture()
        rows = [r for r in load_out(self.home, "johns-macbook-air") if r["runtime"] == "muse"]
        self.assertEqual(sorted(r["text"] for r in rows), ["child hi", "muse hello", "muse hi"])
        by_text = {r["text"]: r for r in rows}
        self.assertEqual(by_text["muse hello"]["key"], "muse/%s/i1" % sid)
        self.assertEqual(by_text["muse hi"]["key"], "muse/%s/m1" % sid)
        self.assertEqual(by_text["child hi"]["key"], "muse/%s/c1" % child)
        self.assertEqual(by_text["muse hello"]["role"], "user")
        self.assertEqual(by_text["muse hi"]["role"], "assistant")
        for row in rows:
            self.assertRegex(row["ts"], TS_RE)


    def test_torn_tail_then_complete(self):
        path = os.path.join(
            self.user,
            ".omp/agent/sessions/proj/2026-09-02T00-00-00-000Z_torn.jsonl",
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                '{"type":"message","id":"abcd1234","timestamp":"2026-09-02T00:00:00.000Z",'
                '"message":{"role":"user","content":[{"type":"text","text":"half'
            )
        self.capture()
        self.assertEqual(load_out(self.home, "johns-macbook-air"), [])
        self.assertEqual(am.load_state(self.home).get("_meta", {}).get("malformed"), 0)
        state = am.load_state(self.home)
        offset = state[path]["offset"]
        with open(path, "a", encoding="utf-8") as fh:
            fh.write('"}]}}\n')
        self.capture()
        rows = load_out(self.home, "johns-macbook-air")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "half")
        self.assertEqual(am.load_state(self.home).get("_meta", {}).get("malformed"), 0)
        self.assertGreater(am.load_state(self.home)[path]["offset"], offset)

    def test_truncation_reset_and_merge_dedupe(self):
        path = os.path.join(
            self.user,
            ".omp/agent/sessions/proj/2026-09-02T00-00-00-000Z_trunc.jsonl",
        )
        rec = {
            "type": "message",
            "id": "keep",
            "timestamp": "2026-09-02T00:00:00.000Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "once"}]},
        }
        dump(path, [rec])
        self.capture()
        first = load_out(self.home, "johns-macbook-air")
        self.assertEqual(len(first), 1)
        key = first[0]["key"]
        open(path, "w").close()
        self.capture()
        state = am.load_state(self.home)
        self.assertEqual(state[path]["offset"], 0)
        dump(path, [rec])
        self.capture()
        rows = load_out(self.home, "johns-macbook-air")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["key"], rows[1]["key"])
        os.environ["AGENT_MEMORY_HOST"] = "agent-box"
        os.environ["AGENT_MEMORY_ROLE"] = "hub"
        in_dir = os.path.join(self.home, "in")
        os.makedirs(in_dir, exist_ok=True)
        src = os.path.join(self.home, "out", "johns-macbook-air.jsonl")
        with open(src, "r", encoding="utf-8") as fh:
            data = fh.read()
        with open(os.path.join(in_dir, "johns-macbook-air.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(data)
        self.assertEqual(am.main(["merge"]), 0)
        mem = os.path.join(self.home, "memory.jsonl")
        with open(mem, "r", encoding="utf-8") as fh:
            merged = [json.loads(line) for line in fh]
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["key"], key)

    def test_merge_includes_source_with_older_mtime(self):
        os.environ["AGENT_MEMORY_HOST"] = "agent-box"
        os.environ["AGENT_MEMORY_ROLE"] = "hub"
        os.makedirs(os.path.join(self.home, "out"), exist_ok=True)
        os.makedirs(os.path.join(self.home, "in"), exist_ok=True)

        def rec(host, key, text, ts):
            return {
                "host": host,
                "key": key,
                "path": "x",
                "role": "user",
                "runtime": "omp",
                "session_id": "s",
                "text": text,
                "ts": ts,
            }

        dump(
            os.path.join(self.home, "out", "agent-box.jsonl"),
            [rec("agent-box", "omp/s/box", "hub", "2026-09-01T12:00:00.000Z")],
        )
        self.assertEqual(am.main(["merge"]), 0)
        mem = os.path.join(self.home, "memory.jsonl")
        with open(mem, "r", encoding="utf-8") as fh:
            hosts = [json.loads(line)["host"] for line in fh]
        self.assertEqual(hosts, ["agent-box"])
        late = os.path.join(self.home, "in", "mbp.jsonl")
        dump(late, [rec("mbp", "omp/s/mbp", "from mbp", "2026-09-01T12:00:01.000Z")])
        os.utime(late, (1, 1))
        self.assertLess(os.path.getmtime(late), os.path.getmtime(mem))
        self.assertEqual(am.main(["merge"]), 0)
        with open(mem, "r", encoding="utf-8") as fh:
            hosts = sorted(json.loads(line)["host"] for line in fh)
        self.assertEqual(hosts, ["agent-box", "mbp"])
        self.assertEqual(am.main(["merge"]), 0)

    def test_merge_picks_up_append_to_already_merged_file(self):
        os.environ["AGENT_MEMORY_HOST"] = "agent-box"
        os.environ["AGENT_MEMORY_ROLE"] = "hub"
        os.makedirs(os.path.join(self.home, "out"), exist_ok=True)
        os.makedirs(os.path.join(self.home, "in"), exist_ok=True)
        rec1 = {
            "host": "mini",
            "key": "omp/s/1",
            "path": "x",
            "role": "user",
            "runtime": "omp",
            "session_id": "s",
            "text": "first",
            "ts": "2026-09-01T12:00:00.000Z",
        }
        rec2 = dict(rec1)
        rec2["key"] = "omp/s/2"
        rec2["text"] = "second"
        rec2["ts"] = "2026-09-01T12:00:01.000Z"
        path = os.path.join(self.home, "in", "mini.jsonl")
        dump(path, [rec1])
        self.assertEqual(am.main(["merge"]), 0)
        dump(path, [rec1, rec2])
        self.assertEqual(am.main(["merge"]), 0)
        mem = os.path.join(self.home, "memory.jsonl")
        with open(mem, "r", encoding="utf-8") as fh:
            texts = [json.loads(line)["text"] for line in fh]
        self.assertEqual(texts, ["first", "second"])

    def test_merge_append_only_and_index_matches_jsonl(self):
        os.environ["AGENT_MEMORY_HOST"] = "agent-box"
        os.environ["AGENT_MEMORY_ROLE"] = "hub"
        os.makedirs(os.path.join(self.home, "out"), exist_ok=True)
        os.makedirs(os.path.join(self.home, "in"), exist_ok=True)

        def rec(key, text):
            return {
                "host": "mini",
                "key": key,
                "path": "x",
                "role": "user",
                "runtime": "omp",
                "session_id": "s",
                "text": text,
                "ts": "2026-09-01T12:00:00.000Z",
            }

        path = os.path.join(self.home, "in", "mini.jsonl")
        dump(path, [rec("omp/s/1", "first")])
        self.assertEqual(am.main(["merge"]), 0)
        mem = os.path.join(self.home, "memory.jsonl")
        dump(path, [rec("omp/s/1", "first"), rec("omp/s/2", "second")])
        self.assertEqual(am.main(["merge"]), 0)
        with open(mem, "r", encoding="utf-8") as fh:
            texts = [json.loads(line)["text"] for line in fh]
        self.assertEqual(texts, ["first", "second"])
        mtime = os.path.getmtime(mem)
        self.assertEqual(am.main(["merge"]), 0)
        self.assertEqual(os.path.getmtime(mem), mtime)
        con = sqlite3.connect(os.path.join(self.home, "memory.sqlite"))
        try:
            n_keys = con.execute("SELECT count(*) FROM keys").fetchone()[0]
        finally:
            con.close()
        self.assertEqual(n_keys, len(texts))

    def test_merge_replaced_inode_same_prefix_is_incremental(self):
        os.environ["AGENT_MEMORY_HOST"] = "agent-box"
        os.environ["AGENT_MEMORY_ROLE"] = "hub"
        os.makedirs(os.path.join(self.home, "out"), exist_ok=True)
        os.makedirs(os.path.join(self.home, "in"), exist_ok=True)

        def rec(key, text):
            return {
                "host": "mini",
                "key": key,
                "path": "x",
                "role": "user",
                "runtime": "omp",
                "session_id": "s",
                "text": text,
                "ts": "2026-09-01T12:00:00.000Z",
            }

        path = os.path.join(self.home, "in", "mini.jsonl")
        dump(path, [rec("omp/s/1", "first")])
        self.assertEqual(am.main(["merge"]), 0)
        old_ino = am.load_state(self.home)["merge:" + path]["ino"]
        old_cursor = am.load_state(self.home)["merge:" + path]
        tmp = path + ".tmp"
        with open(path, "r", encoding="utf-8") as fh:
            body = fh.read()
        extra = json.dumps(rec("omp/s/2", "second"), ensure_ascii=False) + "\n"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body + extra)
        os.replace(tmp, path)
        self.assertEqual(am.main(["merge"]), 0)
        mem = os.path.join(self.home, "memory.jsonl")
        with open(mem, "r", encoding="utf-8") as fh:
            texts = [json.loads(line)["text"] for line in fh]
        self.assertEqual(texts, ["first", "second"])
        cursor = am.load_state(self.home)["merge:" + path]
        self.assertNotEqual(cursor["ino"], old_ino)
        self.assertEqual(cursor["lines"], old_cursor["lines"] + 1)
        self.assertEqual(
            cursor["offset"], old_cursor["offset"] + len(extra.encode("utf-8"))
        )

    def test_merge_replaced_inode_different_prefix_resets_and_dedupes(self):
        os.environ["AGENT_MEMORY_HOST"] = "agent-box"
        os.environ["AGENT_MEMORY_ROLE"] = "hub"
        os.makedirs(os.path.join(self.home, "out"), exist_ok=True)
        os.makedirs(os.path.join(self.home, "in"), exist_ok=True)

        def rec(key, text):
            return {
                "host": "mini",
                "key": key,
                "path": "x",
                "role": "user",
                "runtime": "omp",
                "session_id": "s",
                "text": text,
                "ts": "2026-09-01T12:00:00.000Z",
            }

        path = os.path.join(self.home, "in", "mini.jsonl")
        dump(path, [rec("omp/s/1", "first")])
        self.assertEqual(am.main(["merge"]), 0)
        tmp = path + ".tmp"
        dump(tmp, [rec("omp/s/1", "rewritten"), rec("omp/s/2", "second")])
        os.replace(tmp, path)
        self.assertEqual(am.main(["merge"]), 0)
        mem = os.path.join(self.home, "memory.jsonl")
        with open(mem, "r", encoding="utf-8") as fh:
            keys = [json.loads(line)["key"] for line in fh]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("omp/s/2", keys)

    def test_capture_replaced_inode_same_prefix_keeps_offset(self):
        path = os.path.join(
            self.user,
            ".omp/agent/sessions/proj/2026-09-02T00-00-00-000Z_repl.jsonl",
        )
        rec = {
            "type": "message",
            "id": "abcd1234",
            "timestamp": "2026-09-02T00:00:00.000Z",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "before"}],
            },
        }
        dump(path, [rec])
        self.capture()
        self.assertEqual(len(load_out(self.home, "johns-macbook-air")), 1)
        tmp = path + ".tmp"
        with open(path, "r", encoding="utf-8") as fh:
            body = fh.read()
        extra = (
            json.dumps(
                {
                    "type": "message",
                    "id": "abcd1235",
                    "timestamp": "2026-09-02T00:00:01.000Z",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "after"}],
                    },
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(body + extra)
        os.replace(tmp, path)
        self.capture()
        rows = load_out(self.home, "johns-macbook-air")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["text"], "after")

    def test_sqlite_hermes_and_opencode(self):
        hermes = os.path.join(self.user, ".hermes/state.db")
        os.makedirs(os.path.dirname(hermes), exist_ok=True)
        con = sqlite3.connect(hermes)
        con.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, "
            "role TEXT, content TEXT, timestamp REAL)"
        )
        con.executemany(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
            [
                (1, "s1", "user", "hermes hello", 1750000000.0),
                (2, "s1", "system", "nope", 1750000001.0),
                (3, "s1", "assistant", "hermes hi", 1750000002.0),
            ],
        )
        con.commit()
        con.close()
        oc = os.path.join(self.user, ".local/share/opencode/opencode.db")
        os.makedirs(os.path.dirname(oc), exist_ok=True)
        con = sqlite3.connect(oc)
        con.execute(
            "CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, data TEXT)"
        )
        con.execute(
            "CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, "
            "time_created INTEGER, data TEXT)"
        )
        now_ms = 1700000000000
        con.execute(
            "INSERT INTO message VALUES (?, ?, ?)",
            ("m1", "ocs", json.dumps({"role": "user"})),
        )
        con.execute(
            "INSERT INTO part VALUES (?, ?, ?, ?, ?)",
            (
                "p1",
                "m1",
                "ocs",
                now_ms,
                json.dumps({"type": "text", "text": "opencode hello", "ignored": 0}),
            ),
        )
        con.commit()
        con.close()
        old_time = am.time.time
        am.time.time = lambda: (now_ms / 1000.0) + 200
        try:
            self.capture()
        finally:
            am.time.time = old_time
        rows = load_out(self.home, "johns-macbook-air")
        runtimes = sorted(set(r["runtime"] for r in rows))
        self.assertEqual(runtimes, ["hermes", "opencode"])
        self.assertEqual(
            sorted(r["text"] for r in rows),
            ["hermes hello", "hermes hi", "opencode hello"],
        )
        n = len(rows)
        am.time.time = lambda: (now_ms / 1000.0) + 200
        try:
            self.capture()
        finally:
            am.time.time = old_time
        self.assertEqual(len(load_out(self.home, "johns-macbook-air")), n)

    def test_search_fts_and_fallback(self):
        os.environ["AGENT_MEMORY_HOST"] = "agent-box"
        os.environ["AGENT_MEMORY_ROLE"] = "hub"
        os.makedirs(os.path.join(self.home, "out"), exist_ok=True)
        dump(
            os.path.join(self.home, "out", "agent-box.jsonl"),
            [
                {
                    "host": "agent-box",
                    "key": "omp/s/1",
                    "path": "x",
                    "role": "user",
                    "runtime": "omp",
                    "session_id": "s",
                    "text": "please handle the repeat prescription",
                    "ts": "2026-09-01T12:00:00.000Z",
                },
                {
                    "host": "mini",
                    "key": "omp/s/2",
                    "path": "x",
                    "role": "assistant",
                    "runtime": "omp",
                    "session_id": "s",
                    "text": "unrelated",
                    "ts": "2026-09-01T12:00:01.000Z",
                },
            ],
        )
        self.assertEqual(am.main(["merge"]), 0)
        from io import StringIO

        buf = StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            self.assertEqual(am.main(["search", "repeat prescription"]), 0)
        finally:
            sys.stdout = old
        hits = [json.loads(line) for line in buf.getvalue().splitlines()]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["host"], "agent-box")
        self.assertEqual(hits[0]["runtime"], "omp")
        self.assertIn("[repeat prescription]", hits[0]["snippet"])
        os.unlink(os.path.join(self.home, "memory.sqlite"))
        buf = StringIO()
        sys.stdout = buf
        try:
            self.assertEqual(am.main(["search", "repeat prescription"]), 0)
        finally:
            sys.stdout = old
        hits = [json.loads(line) for line in buf.getvalue().splitlines()]
        self.assertEqual(len(hits), 1)
        self.assertIn("[repeat prescription]", hits[0]["snippet"])

    def test_lock_exits_zero(self):
        am.ensure_dirs(self.home)
        fd = am.acquire_lock(self.home)
        self.assertIsNotNone(fd)
        try:
            self.assertEqual(am.main(["capture"]), 0)
            self.assertFalse(os.path.exists(os.path.join(self.home, "state.json")))
        finally:
            os.close(fd)


if __name__ == "__main__":
    unittest.main()
