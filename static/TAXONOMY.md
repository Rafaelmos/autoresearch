# Aging rule set (autoresearch-aging): taxonomy

Static rules (Semgrep) that flag **candidate** code-level aging mechanisms in backend services.
A match is a *candidate*, never a confirmed aging mechanism: it enters the triage step, which
checks the four required elements (repeatable trigger, persistent accumulation or progressive
exhaustion, insufficient cleanup/bounding, plausible degradation over long-running execution)
and, if supported, the runtime validation pipeline.

## Taxonomy (where the rules come from)

The classes follow the software aging / aging-related bug (ARB) literature, which distinguishes
aging by the **resource that accumulates or is exhausted**, and the mechanism-class vocabulary
already used in the previous paper's AI adjudication step:

| class | mechanism (paper vocabulary) | resource | typical code-level cause |
|---|---|---|---|
| **C1 Memory / state retention** | cumulative resource retention | heap: in-process collections, caches | state added on a repeatable path and never evicted (no bound, no TTL) |
| **C2 Persistent storage growth** | cumulative resource retention | disk: DB rows, files, temp files | records/files created per request with no retention, rotation or cleanup |
| **C3 Logical resource leak** | finite-resource exhaustion | file descriptors, sockets, DB connections, processes | resource acquired without a guaranteed release on every path |
| **C4 Concurrency resource exhaustion** | finite-resource exhaustion | threads, worker slots, tasks, timers, listeners | unbounded creation, or blocking on an external dependency with no timeout |
| **C5 Unbounded work per request** | (amplifies C1/C2) | CPU/memory per call | reads whose cost grows with accumulated state (no LIMIT/pagination) |

Reference basis (to be cited in the paper; check exact bibliographic details when writing):
- M. Grottke, R. Matias, K. Trivedi, *The fundamentals of software aging*, WoSAR/ISSRE workshops 2008.
- D. Cotroneo, R. Natella, R. Pietrantuono, S. Russo, *A survey of software aging and rejuvenation
  studies*, ACM JETC, 2014.
- D. Cotroneo, M. Grottke, R. Natella, R. Pietrantuono, K. Trivedi, *Fault triggers in open-source
  software: an experience report*, ISSRE 2013 (aging-related bug classification).
- F. Machida et al., *Aging-related bugs in cloud computing software*, WoSAR 2012.

Numerical error accumulation (another ARB class) is **out of scope**: it is not expressible as
a reliable syntactic pattern in these service apps.

Fragmentation of the allocator is **not** a class: it is a hypothesis that explains steps and
drops in post-GC RSS (see the A/A notes in `program_detect.md`), not something a syntactic rule can flag.

## Provenance and protocol

Ported from chas42/llm-aging-detection-agents (`static/rules/aging`, v1.0; JS and Python only).
Added here: `aging-js-db-connection-per-call` and `aging-py-open-without-close` (class C3, which
upstream leaves to LeakAudit). Freeze the rule set (`VERSION`) before a campaign; afterwards only
bug fixes, so the rules are not tuned to what the campaign finds. The rules were written knowing
the target (`credit-card`): a threat to validity to report.

File-level conditions (`unless_file_matches` / `if_file_matches`) are applied by `static/aging_rules.py`.
