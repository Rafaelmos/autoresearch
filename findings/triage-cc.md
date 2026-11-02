# Triage cc (apps/credit-card/original) - hypotheses for runtime validation

Inputs: source read in full (index.js, db/init.js, models/card.js, controllers, routes, middleware, utils/logger.js); tool findings only (no AI reviews). Nothing here is confirmed aging.

## 1. All candidates

| Merged id | Sources | Verdict | Reason |
|---|---|---|---|
| cc-F1 | semgrep-aging:aging-js-insert-without-retention (card.js:18-95, 42-91, 66-87) + read-side unindexed join found by own reading | conditional | Rows in 3 tables never deleted; UNIQUE only dedups identical keys, so growth needs distinct keys. Retrieve query has no LIMIT and cpa has no phone_id-leading index, so read cost grows with data. |
| cc-C2 (connection per request, db/init.js:72) | semgrep-aging:aging-js-db-connection-per-call (init.js:72-76); README hypothesis | unsupported (as leak) | Every path closes: createCardPhoneAssociation closes at each error branch (card.js:24, 35, 48, 59, 72) and in the COMMIT callback (78); getCardsByPhoneNumbers closes first in the db.all callback (127). Open churn is a constant per-call cost (non-aging). Residual risk: allocator fragmentation from open/close churn, not decidable statically. |
| cc-C3 (initDatabase connection, init.js:16-22) | semgrep-aging:aging-js-db-connection-per-call (init.js:16) | unsupported | Called once at startup (index.js:21) and closed at init.js:61. |
| cc-C4 (SQLITE_BUSY under concurrency) | README hypothesis | non-aging | Connections opened with OPEN_READWRITE, no busy_timeout, deferred BEGIN: concurrent writers fail with immediate 500 from the first request; no accumulation (indirect coupling noted in cc-F1 symptoms). |
| cc-C5 (unbounded phone_numbers array / no LIMIT) | own reading | non-aging (partly folded into cc-F1) | Request size capped by express.json default 100kb; placeholder count limit gives a constant-cost error. Response size growth with data is part of cc-F1. |
| cc-C6 (unhandled TypeError at cardRow.id / phoneRow.id, card.js:39, 63) | own reading | unsupported | Rows always exist after INSERT OR IGNORE + SELECT on a committed UNIQUE key; no reachable path found. If it did throw, it would leave the connection open and crash the process (uncaught exception in callback), not accumulate. BEGIN (card.js:15) has no error callback, ignored. |
| cc-C7 (global state / middleware) | README hypothesis | unsupported | No module-level arrays/Maps/caches; express.json, validation, errorHandler and logger are stateless (logger is not even imported). |
| cc-C8 (error handler logs stack to console) | own reading | non-aging | Constant cost per error; stdout growth only if redirected, not process memory. |

## 2. Source contribution

| Card | AI reviews | Tools |
|---|---|---|
| cc-F1 | none available | aging-js-insert-without-retention (3 hits); read-side part from own reading only |

## 3. Disagreements

- No AI reviews, so no AI vs. AI disagreement.
- Tools vs. README hypothesis: tools flag db/init.js:72 as C3 connection-per-call (INFO, explicitly "check closes"). Verified closed on all paths, so the RSS-up/heap-flat native-retention hypothesis via leaked connections is not supported by the code. If RSS rises at runtime, look to sqlite page cache/allocator behavior or DB growth effects (cc-F1) instead.
- Tools rated the insert-without-retention hits WARNING; downgraded to conditional because the UNIQUE constraints and INSERT OR IGNORE make growth depend on distinct keys.

## EXPLAIN QUERY PLAN de `getCardsByPhoneNumbers` (verificação de cc-F1, lado da leitura)

Esquema de `db/init.js` em memória, SQLite 3.45.1 do Python (o pacote `sqlite3` do Node embute outra
versão: confirmar no runtime). A app nunca roda `ANALYZE`, então vale o plano "vazio":

    SCAN cc                                   <- varre credit_cards inteira a cada chamada
    SEARCH p USING COVERING INDEX sqlite_autoindex_phones_1 (phone_number=?)
    SEARCH cpa USING COVERING INDEX sqlite_autoindex_card_phone_associations_1 (card_id=? AND phone_id=?)
    USE TEMP B-TREE FOR count(DISTINCT)

Com 1000 linhas e ANALYZE o plano continua com `SCAN cc` (cpa por `card_id=?`, mais um BLOOM FILTER em p).
Leitura: o custo de `POST /retrieve_cards` é O(cartões), não O(cartões associados ao telefone), porque
`card_phone_associations` não tem índice com `phone_id` na frente (o UNIQUE é `(card_id, phone_id)`).
Não há índice automático por chamada; há um temp B-tree transitório para `count(DISTINCT)`.
Isso sustenta a parte de leitura de cc-F1 (latência sobe com o número de cartões) e dá um alvo de
reparo (índice em `phone_id`), mas não explica RSS alto com heap plano.
