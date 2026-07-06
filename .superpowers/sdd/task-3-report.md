# Task 3 Report

Status: DONE

## Modified files
- C:\Users\11616\douban-taste-recommender\tests\test_crawler.py
- C:\Users\11616\douban-taste-recommender\src\douban_recommender\crawler.py

## Commit
- afc08e05013ddd33495b0b5d1bb974ee43ff223b

## Test commands and results
1. Baseline before changes:
   - Command: `$env:PYTHONPATH='C:\Users\11616\douban-taste-recommender\src'; python -m unittest tests.test_crawler -v`
   - Result: PASS, 5 tests OK.
2. RED after appending orchestration tests:
   - Command: `$env:PYTHONPATH='C:\Users\11616\douban-taste-recommender\src'; python -m unittest tests.test_crawler -v`
   - Result: expected ERROR, 2 import errors because `crawl_user_collections` was not defined; 5 existing tests OK.
3. First GREEN attempt after adding crawl functions:
   - Command: `$env:PYTHONPATH='C:\Users\11616\douban-taste-recommender\src'; python -m unittest tests.test_crawler -v`
   - Result: FAIL, 1 failure because collect/wish duplicate IDs were globally deduped, returning 2 items where test expected at least 4.
4. After status-scoped dedupe fix:
   - Command: `$env:PYTHONPATH='C:\Users\11616\douban-taste-recommender\src'; python -m unittest tests.test_crawler -v`
   - Result: PASS, 7 tests OK.
5. Full suite check:
   - Command: `$env:PYTHONPATH='C:\Users\11616\douban-taste-recommender\src'; python -m unittest discover -s tests -v`
   - Result: PASS, 9 tests OK.
6. Encoding/string self-review correction re-run:
   - Command: `$env:PYTHONPATH='C:\Users\11616\douban-taste-recommender\src'; python -m unittest tests.test_crawler -v`
   - Result: PASS, 7 tests OK.
7. Final full suite:
   - Command: `$env:PYTHONPATH='C:\Users\11616\douban-taste-recommender\src'; python -m unittest discover -s tests -v`
   - Result: PASS, 9 tests OK.

## Self-review
- TDD RED verified: new tests failed for the expected missing `crawl_user_collections` import before implementation.
- Implemented `fetch_user_collection_page` with Douban collection URL, default headers, Referer, optional Cookie header, timeout, and UTF-8 ignore decode.
- Implemented `crawl_user_collections` with user ID normalization, max page cap, collect/wish orchestration, dependency-injected fetcher, parse integration, page counters, error capture, sleep, stopped reason, and cookie redaction in errors.
- Cookie is only passed to the fetcher/request header and is redacted from captured error messages.
- Kept edits limited to the two task source/test files for the commit; report written separately as requested.

## Concerns
- The brief snippet used globally unique item dedupe, but the required test expects identical IDs from collect and wish to both be retained. I scoped dedupe by status to satisfy the required behavior.
- Source uses Unicode escape literals for newly added Chinese stopped reasons to avoid Windows PowerShell encoding corruption in this environment; runtime values are normal Unicode strings.

## Task 3 review-fix follow-up (2026-07-06)

Status: DONE

### Modified files
- C:\Users\11616\douban-taste-recommender\tests\test_crawler.py
- C:\Users\11616\douban-taste-recommender\src\douban_recommender\crawler.py

### Fixes
- Added RED coverage for cookie leaks where exception text contains only a cookie value, one key/value pair, a no-space Cookie header, or a partial `Cookie:` header.
- Added RED coverage for `max_pages=0` clamping to exactly one page and preserving fake fetcher compatibility with `timeout=12`.
- Implemented crawler-side error message cookie redaction for full cookies, whitespace-normalized cookies, individual cookie values, and individual key/value pairs.
- Changed `max_pages=0` handling from defaulting to 8 pages to clamping to 1 page.
- Passed `timeout=12` when calling the injected/default fetcher.

### Test commands and results
1. RED after adding review-fix tests:
   - Command: `$env:PYTHONPATH='C:\Users\11616\douban-taste-recommender\src'; python -m unittest tests.test_crawler -v`
   - Result: expected FAIL, 5 failures: `max_pages=0` fetched 8 pages; cookie value/key-value/no-space/partial-header leaks remained in errors.
2. GREEN after implementation:
   - Command: `$env:PYTHONPATH='C:\Users\11616\douban-taste-recommender\src'; python -m unittest tests.test_crawler -v`
   - Result: PASS, 9 tests OK.
3. Full suite:
   - Command: `$env:PYTHONPATH='C:\Users\11616\douban-taste-recommender\src'; python -m unittest discover -s tests -v`
   - Result: PASS, 11 tests OK.

### Concerns
- None.
