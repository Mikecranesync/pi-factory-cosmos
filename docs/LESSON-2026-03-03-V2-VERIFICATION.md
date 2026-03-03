# LESSON LOG — 2026-03-03 — Pi-Factory v2.0.0 Live Verification

**Node:** CHARLIE (192.168.1.12)
**Session type:** Verification + bugfix
**Repo:** pi-factory-cosmos @ `d46607f`

---

## What Was Done (with proof)

### 1. Full test suite executed — 43/43 PASS
- VFD Reader: 24/24 tests passed (mocked pymodbus 3.8.6)
- Belt Tachometer: 19/19 tests passed
- Runtime: 0.14s total
- **Proof:** `python3 -m pytest tests/ -v` output captured

### 2. Live server verification (no-VFD mode)
- `GET /api/health` → `{"status":"ok"}` — PASS
- `GET /api/vfd/status` → HTTP 503, correct degradation — PASS
- `GET /api/tags` → 15 PLC-only tags, zero `vfd_*` keys — PASS
- `GET /api/combined` → `vfd_tags: {}`, `conflicts: []` — PASS
- `GET /api/conflicts` → empty array — PASS
- `GET /api/faults` → C001 conveyor jam from simulator — PASS
- `GET /` → 19,805 bytes HTML, "Pi-Factory v2.0", VFD panel present — PASS
- **Proof:** curl responses captured in session

### 3. File change audit (v1.5.0 → v2.0.0)
- 13 files verified: 10 modified + 3 new
- All match plan spec: register counts, fault codes, tag counts, endpoint names
- Python 3.9 compatibility verified via `ast.parse()` on all new/modified files
- **Proof:** grep/wc output per file captured

### 4. Bugfix: SyntaxError in tag_server.py:467
- **Bug:** Em dash (`—`) inside `b""` byte string → `SyntaxError: bytes can only contain ASCII literal characters`
- **Impact:** Server could not start at all — total v2.0.0 blocker
- **Fix:** Replaced `—` with `-` (1-line change)
- **Commit:** `d46607f` on main, pushed to origin
- **Proof:** Server starts and serves all endpoints after fix

### 5. Release management
- v2.0.0 tag updated: `b14d5a3` → `d46607f` (includes bugfix)
- `rollback/v2.0.0` branch updated to match
- GitHub release updated: added bugfix section, published (was draft), marked Latest
- v1.5.0 release demoted from Latest
- **Proof:** `gh release view v2.0.0` confirms published state

---

## Human Mistakes This Session

1. **None observed.** User gave clear, sequential instructions.

---

## AI Mistakes This Session

1. **Missed SyntaxError during plan implementation (prior session).**
   The v2.0.0 commit (`b14d5a3`) shipped with a non-ASCII em dash inside a `b""` byte literal. This is a Python syntax error that prevents the module from loading at all. The AI that wrote the v2.0.0 code either:
   - Did not run `python3 simulate.py` after writing the code, OR
   - Ran it but did not catch the traceback
   This violates **Law 1 (Evidence-Only Completion)** — the code was committed without proof it actually ran.

2. **Port 8080 was occupied by a different repo (`factorylm-cosmos-cookoff`).**
   Not an AI mistake per se, but the verification initially tried port 8081 rather than checking what was running first. Minor — recovered quickly.

---

## Fine-Tuning Candidates

1. **Byte string validation pattern.**
   Before committing any Python file, scan for non-ASCII characters inside `b""` or `b''` literals. One-liner check:
   ```bash
   python3 -c "import ast; ast.parse(open('file.py').read())"
   ```
   This should be a pre-commit rule.

2. **Server smoke test as acceptance criteria.**
   Any commit that modifies `tag_server.py` or `simulate.py` must include proof that the server actually starts:
   ```bash
   timeout 5 python3 simulate.py --port 9999 2>&1 | head -20
   ```
   If it doesn't print the banner + "Simulation started", the commit is not done.

3. **Non-ASCII in byte strings → rule candidate.**
   Same mistake pattern: using em dashes, curly quotes, or other Unicode in contexts that require ASCII. Likely sourced from LLM training data or copy-paste from formatted docs.

---

## Rule Candidates

**If this pattern repeats, write to `/cluster/betterclaw/rules/`:**

- `RULE-BYTE-STRING-ASCII.md` — All `b""` literals must contain only ASCII (0x00-0x7F). Pre-commit check: `python3 -c "import ast; ast.parse(open(f).read())"` on every `.py` file in the diff.
- `RULE-SERVER-SMOKE-TEST.md` — Any commit touching `simulate.py` or `tag_server.py` requires a 5-second startup smoke test as proof of completion.
