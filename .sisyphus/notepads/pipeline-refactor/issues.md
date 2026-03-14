
## Task 6: CTC Alignment Quality on Singing Voice
- Alignment tail drift: last words ("let", "you", "down") have unrealistically wide spans (e.g., "let" = 115.9s–137.8s)
- This is because MMS_FA is a speech model — singing voice with music bleed causes confidence/span issues
- avg_score = 0.238 is usable but low — speech typically gets 0.7+
- These are expected limitations, not bugs. Task F3 will evaluate and decide if post-processing is needed

## RESOLVED: Hyphen Blank Token Crash (CTC Alignment)
- **Issue**: `normalize_for_alignment()` allowed hyphens through (e.g., `never-ending` → `['never-ending']`)
- **Root Cause**: MMS_FA tokenizer maps `-` to token index 0 (blank token), causing `torchaudio.functional.forced_align` to crash with `ValueError: targets Tensor shouldn't contain blank index`
- **Fix Applied**:
  1. Updated `_STRIP_PATTERN` to remove hyphen from safe characters: `r"[^a-z'\s]"` (was `r"[^a-z'\-\s]"`)
  2. Added Step 3.5 to replace hyphens with spaces: `text = text.replace("-", " ")`
  3. Updated docstring to clarify hyphens are NOT safe and must be replaced
  4. Added tests: `test_hyphenated_word_splits()` verifies `never-ending` → `['never', 'ending']`
- **Verification**: All 29 text_normalize tests + 18 ctc_aligner tests pass
- **Apostrophes Preserved**: `we're` still works correctly (apostrophe maps to index 26, not 0)
- **Commit**: `fix(alignment): replace hyphens with spaces to prevent CTC blank token crash`
