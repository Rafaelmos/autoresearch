# Technical Update Report — AutoResearch-Aging (Pilot 3)

- **Model Modification Date & Time:** October 30, 2026 (`2026-10-30T20:45:04-03:00`, BRT)
- **Repository Update Date & Time:** October 30, 2026 (`2026-10-30T20:51:00-03:00` to `2026-10-30T21:21:00-03:00`, BRT)
- **Model Used:** Gemini 4 Argon (Medium)
- **Updated Repository:** `C:\Users\rafae\Documents\GitHub\autoresearch`
- **Review Reference:** 9 issues raised by Cesar (Judge Security, Hidden Oracle Isolation, Permission Bugs, and Methodological/Noise Issues)

---

## Executive Summary

This report documents the complete resolution of all **9 technical and methodological issues** identified by Cesar following the review of the Pilot 3 codebase and the `det-out20` / `A/A` campaign results. All fixes have been applied directly to the main repository (`prepare.py`, `harness/`, `.claude/`, `.gitignore`, `run_campaign.sh`, `program_detect.md`, `program_repair.md`, and `README.md`).

| # | Category | Issue Raised by Cesar | Implemented Solution | Modified Files |
|---|---|---|---|---|
| **1** | Judge Security | The agent can alter scoring rules by importing `harness.evaluate` inside `workload.py` | `workload.py` is never imported in the judge process (`prepare.py`); all validation, load generation, and trace building run in an isolated subprocess (`python -m harness.load`), complemented by in-memory verification of `EXPECTED_CONSTANTS` before and after each round | `harness/load.py`, `harness/gates.py`, `prepare.py` |
| **2** | Oracle Security | Hidden tests (`oracle/hidden/`) can be read via `grep`, `head`, `tail`, or `git show HEAD:...` | Added `oracle/hidden/` to `.gitignore` and untracked it from Git (`git rm --cached`); added explicit `deny` rules in `.claude/settings.{detect,repair}.json`; enforced `chmod 700` in `setup` and `run_campaign.sh` + support for `AGENT_USER` and `AGING_HIDDEN_TESTS` | `.gitignore`, `.claude/settings.detect.json`, `.claude/settings.repair.json`, `harness/gates.py`, `prepare.py`, `run_campaign.sh`, `README.md` |
| **3** | Infrastructure Bug | `chmod -R a-w` in `run_campaign.sh` on `apps/` causes `shutil.copytree` to create read-only copies (`EACCES` on symlink and SQLite) | Created `copy_tree_writable` using `shutil.copytree(..., copy_function=shutil.copyfile)` followed by explicit owner write permission restoration (`0o700` on dirs, `0o600` on files) across all instance and candidate copies | `harness/instance.py`, `prepare.py` |
| **4** | Method (Noise) | The `5 MB/h` threshold lies within noise (`-8.5` to `+7.8 MB/h` across null arms) | Recalibrated threshold to `MIN_EFFECT_MB_PER_H = 10.0` MB/h (above the 95th percentile and max of null arms) and introduced **step-robust slope** (`robust_slope_per_h = min(sen_slope_first_half_per_h, sen_slope_second_half_per_h)`) | `harness/stats.py`, `harness/evaluate.py`, `prepare.py`, `program_detect.md` |
| **5** | Method (Statistics) | Mann-Kendall p-value does not discriminate ($p \approx 0$ due to autocorrelation) and distorts `ttd_min` | `mk_p_upward` is now purely descriptive/informational; eligibility and `time_to_detect` (`ttd_min`) are decided strictly by global and step-robust effect size ($\ge 10.0$ MB/h) | `harness/evaluate.py`, `prepare.py`, `program_detect.md` |
| **6** | Method (Selection) | The `keep` rule does not require replication (a single lucky run becomes "previous best") | Enforced **2 distinct seeds** (`MIN_KEEP_SEEDS = 2`) with `score_rss_mb_per_h >= 10.0` MB/h before setting `keep_eligible = True`; a single-seed hit receives status `needs_replica` | `prepare.py`, `program_detect.md` |
| **7** | Anti-Reward Hacking | Baseline copy check (`D4`) compares exact request sequence and is bypassed by swapping read/write order | New `workload_signature` and `same_as_baseline` functions compare **operation proportions** ($\pm 5\%$), concurrency parameters (`threads`, `think_time_s`), and payload/key cardinality regardless of request order | `harness/load.py`, `prepare.py`, `program_detect.md` |
| **8** | Repair Phase | Repair requires an aging original app and does not measure `base` during the round | `repair-init` and `repair` now require prior 3-seed confirmation (`aging_confirmed = True`) from detection; `cmd_repair` also measures `candidates/base` in the same round and computes `gain_vs_base` | `prepare.py`, `program_repair.md`, `README.md` |
| **9** | Data Logging | `results.tsv` loses slope data (`NA`) when an arm is not scored | `results.tsv`, `print_detect`, and `judge_log.jsonl` now always record numerical `rss_slope_mb_per_h` and `robust_slope_mb_per_h` for every arm, even when `score_rss_mb_per_h` is `NA` | `prepare.py`, `program_detect.md`, `program_repair.md` |

---

## Detailed Breakdown of Implemented Fixes

### 1. Judge Process Isolation Against Scoring Rule Tampering
- **Problem:** `prepare.py` called `load_module(ROOT / "workload.py", "workload")` inside the judge's own Python process. Because `workload.py` is edited by the agent and cannot be hash-locked in `.judge/manifest.json`, the agent could write `import harness.evaluate as e; e.MIN_EFFECT_MB_PER_H = 0` at the top of `workload.py`, lowering the scoring threshold in memory without modifying any fixed file on disk.
- **Implemented Solution:**
  1. **Subprocess Isolation (`python -m harness.load`):** `prepare.py` **no longer imports `workload.py` or `frozen/workload_frozen.py` in-process**. All interactions with workload code happen in separate child processes communicating strictly via validated JSON:
     - `inspect_workload_subprocess()`: validates `CANDIDATES`, computes each candidate's behavioral signature, and outputs pure JSON metadata (`name`, `hypothesis`, `threads`, `think_time_s`, `same_as_baseline`, `signature`).
     - `run_load_subprocess()`: executes `LoadRun` for each arm in a separate process and writes the bucket summary (`load_summary.json`).
     - `build_trace_subprocess()`: generates the deterministic replay request list for `harness/gates.py` in a separate process.
  2. **In-Memory Constant Verification (`verify_constants()`):** `prepare.py` checks `EXPECTED_CONSTANTS` before and after `run_arms()`, aborting with flag `H5_juiz_ou_oraculo_alterado` if any constant in `harness.evaluate` or `harness.load` differs from its canonical value.

---

### 2. True Protection of Hidden Tests (`oracle/hidden/`)
- **Problem:** Claude Code permissions denied `Read(./oracle/hidden/**)`, but allowed `grep`, `head`, `tail`, `git diff`, and `git log`. Moreover, `setup` ran `git add -A`, committing `oracle/hidden/hidden_tests.py` into Git where `git show HEAD:oracle/hidden/hidden_tests.py` exposed the entire file.
- **Implemented Solution:**
  1. Added `oracle/hidden/` to `.gitignore` and removed `oracle/hidden/hidden_tests.py` from the Git index (`git rm --cached oracle/hidden/hidden_tests.py`), keeping the file on disk only.
  2. Added explicit `deny` rules in `.claude/settings.detect.json` and `.claude/settings.repair.json` for `Bash(*oracle/hidden*)`, `Bash(*hidden_tests*)`, `Bash(git show:*)`, `Bash(git cat-file:*)`, `Bash(git grep:*)`, `Bash(grep:*oracle*)`, `Bash(head:*oracle*)`, `Bash(tail:*oracle*)`, `Bash(cat:*oracle/hidden*)`, and `Bash(find:*oracle*)`.
  3. `cmd_setup` in `prepare.py` and `run_campaign.sh` enforce `chmod 700` on `oracle/hidden` (and `0600` on the file), and support `AGENT_USER` (to run the agent under a separate unprivileged Linux user via `sudo -u "$AGENT_USER"`) as well as the `AGING_HIDDEN_TESTS` environment variable in `harness/gates.py` to store hidden tests outside the repository tree.

---

### 3. Fixing the `chmod` Copy Permission Bug (`EACCES`)
- **Problem:** `run_campaign.sh` removes write permissions from `apps/` (`chmod -R a-w`). Because `shutil.copytree` uses `shutil.copy2` by default, copied directories in `workdir/app` inherited read-only permission bits (`r-xr-xr-x`), preventing creation of the `node_modules` symlink and the SQLite `uptime_db` file (causing the `Errno 13 / EACCES` failure in the first attempt of `det-out20`).
- **Implemented Solution:**
  - Implemented `copy_tree_writable(src, dst, ignore=None)` in `harness/instance.py`, which uses `shutil.copytree(..., copy_function=shutil.copyfile)` and applies `_force_writable(dst)` (`0o700` for directories and `0o600` for files).
  - Used across `copy_app()`, `cmd_setup()`, `cmd_repair_init()`, `cmd_promote()`, and `cmd_repair()` snapshots.

---

### 4. Threshold Recalibration to `10.0 MB/h` and Step-Robust Slope Metric
- **Problem:** Across the 32 valid arms of `det-out20` and 4 arms of `A/A`, arms that should not age (including `baseline_artigo` itself, which hit `7.77 MB/h` in round 4) ranged from `-8.5` to `+7.8 MB/h` due to discrete native allocator step changes. Thus, the `5.0 MB/h` threshold rewarded noise.
- **Implemented Solution:**
  1. Raised `MIN_EFFECT_MB_PER_H` from `5.0` to **`10.0` MB/h** in `harness/evaluate.py` (above the 95th percentile and maximum of all null arms).
  2. In `harness/stats.py` (`trend`), the post-warmup series is split into two temporal halves, computing:
     - `sen_slope_first_half_per_h` (1st half, ~5 to 32.5 min);
     - `sen_slope_second_half_per_h` (2nd half / last ~30 min);
     - `robust_slope_per_h = min(sen_slope_first_half_per_h, sen_slope_second_half_per_h)`.
  3. For an arm to achieve `rss_upward_significant = True`, **both** `sen_slope_per_h` (global) **and** `robust_slope_per_h` must be $\ge 10.0$ MB/h, and `score_rss_mb_per_h` is set to `robust_slope_per_h`. One-time allocator step jumps in a single half of the run are therefore rejected.

---

### 5. Decoupling Mann-Kendall p-value from Scoring Decisions and `ttd_min`
- **Problem:** In time series of ~660 consecutive RSS samples, strong autocorrelation causes the Mann-Kendall test to yield $p \approx 0$ (e.g., $10^{-52}$ to $10^{-135}$) even for flat trajectories (`0.4 MB/h`). `time_to_detect` (`ttd_min`) inherited the same flaw.
- **Implemented Solution:**
  - Removed `mk_p_upward < ALPHA` from `rss_upward_significant` in `harness/evaluate.py`, keeping `mk_p_upward` strictly as descriptive information.
  - Rewrote `time_to_detect(probe, warm, key="rss")` to report the first 5-minute checkpoint from which **both** `sen_slope_per_h >= 10.0` **and** `robust_slope_per_h >= 10.0` and **remain above threshold** until the end of the run.

---

### 6. Mandatory 2-Seed Replication for the `keep` Rule
- **Problem:** In `det-out20`, a single lucky result in round 3 (`retrieve_longo = 6.56 MB/h` on seed 1) became the "previous best" (`keep`), skewing the remainder of the campaign even after failing replication (`0.50 MB/h`).
- **Implemented Solution:**
  - Set `MIN_KEEP_SEEDS = 2` in `prepare.py`.
  - `_historical_confirmed_seeds()` cross-references the candidate's canonical signature (`sig_hash`) and name in `results/judge_log.jsonl` with the current round to count how many **distinct seeds** (e.g., `--seed 1` and `--seed 2`) achieved `score_rss_mb_per_h >= 10.0` MB/h.
  - While `len(confirmed_seeds) < 2`, the judge sets `keep_eligible = False` (status `needs_replica`). Only when $\ge 2$ distinct seeds pass the threshold does the candidate receive `keep_eligible = True` and `replicated_score_mb_per_h` (mean across confirmed seeds).

---

### 7. Robust Baseline Copy Detection (`D4_copia_da_baseline`)
- **Problem:** `same_as_baseline` compared `spec["request"](ra, i) != BASELINE["request"](rb, i)` index by index. Simply swapping `i % 2 == 0` to `i % 2 == 1` (inverting `/associate_card` and `/retrieve_cards` order) bypassed `D4`.
- **Implemented Solution:**
  - `workload_signature(spec)` and `same_as_baseline(spec)` in `harness/load.py` sample 400 requests per seed and compare:
    1. `threads` and `think_time_s` ($\pm 0.002\text{ s}$);
    2. **Operation proportions** (`op_ratios` for `/associate_card` and `/retrieve_cards` within $\pm 5\%$ of the baseline's 50/50 split);
    3. Distinct card and phone cardinality ($\le 1$ card and $\le 1$ phone) and average payload size ($\pm 16$ bytes).
  - Inverting even/odd order, shuffling 50/50 requests, or changing the literal string of the single card/phone pair is still flagged as `D4_copia_da_baseline`.

---

### 8. Confirmed Aging Precondition for Repair and Measuring `base` in Each Round
- **Problem:** `score_repair` requires `original` to grow above threshold in the same round (which fails if Campaign 2 starts without a truly aging workload), and the `keep` rule compared against `base` without measuring `base` in the round.
- **Implemented Solution:**
  1. **Precondition Gate:** `cmd_freeze` requires the frozen arm to have scored $\ge 10.0$ MB/h, and `cmd_confirm --phase detect` checks whether all 3 confirmation seeds (`11, 12, 13`) scored $\ge 10.0$ MB/h, writing `FROZEN_CONFIRMED = True` in `frozen/workload_frozen.py` and `"aging_confirmed": true` in `judge_log.jsonl`. `cmd_repair_init` and `cmd_repair` abort if the frozen workload is not confirmed (`require_confirmed=True`).
  2. **Measuring `base` in Repair Rounds:** Whenever `candidates/base` differs from `original` (after a `promote`), `cmd_repair` includes `base` as a measured arm in the round, computes `base_reduction` in the same time window, and reports `gain_vs_base = score_reduction(vN) - score_reduction(base)` for each candidate `v1..v3`.

---

### 9. Preserving `rss_slope` and `robust_slope` in `results.tsv` and `judge_log.jsonl`
- **Problem:** Whenever an arm did not score (`score_rss_mb_per_h = NA`), its RSS slope was omitted from `results.tsv` and the `judge_log.jsonl` summary, losing valuable data for post-hoc analysis.
- **Implemented Solution:**
  - Updated `prepare.py` (`cmd_detect`, `print_detect`, and `log_judge`) as well as `program_detect.md` and `program_repair.md` to always record numerical `rss_slope_mb_per_h` and `robust_slope_mb_per_h` across all arms (including `baseline`, `discard`, and `E2`), reserving `NA` strictly for `score_rss_mb_per_h` when an arm is ineligible.
