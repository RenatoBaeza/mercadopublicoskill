---
name: mp-rank
description: Score and rank downloaded Mercado Público tenders against the company profile and suggest the top 100 to apply for, with the reasons for each score, as xlsx/csv/json/markdown and an interactive HTML page. Use when the user asks which Chilean public tenders (licitaciones) their company should apply to, or wants the ranking refreshed.
---

# Rank tenders for the company

Requires `data/company_profile.json` (from `mp-company-profile`) and
`data/licitaciones.json` (from `mp-download`). If either is missing, run that skill
first. If the data's `descargado` date is not today, offer to refresh it.

## Run

```
python .claude/skills/mp-rank/scripts/rank.py --profile data/company_profile.json --data data/licitaciones.json --top 100 --out data/ranking_top100
```

Outputs `data/ranking_top100.xlsx` (needs `openpyxl`), `.csv`, `.json`, `.md` and `.html`.
The `.html` is a self-contained page built from `scripts/ranking_template.html`: open it in a
browser to search, filter by region / size / score / days to close, sort columns, expand a row
for its score breakdown and reasons, and star a shortlist (kept in the browser's local storage).
The console prints the counts, the reasons tenders were dropped, and the top 10.

## How the score works (0–100)

| Part | Max | Basis |
|---|---|---|
| Keywords | 45 | Profile keywords found in the title (×3), item descriptions (×2), categories (×1.5), description (×1); secondary keywords count half; saturates |
| Category | 25 | Best item match on `codigos_onu` prefixes (8 digits = 1.0 … 2 digits = 0.4) or `categorias` names, scaled by the share of items that match |
| Region | 10 | Buyer region in `regiones` (or the company serves all of Chile) |
| Size | 10 | Size bracket in `tamanos`; half credit when the size is unknown (`LS`, `OBRA`) |
| Time | 10 | Full credit at ≥ 6 days beyond `dias_minimos_preparacion` |

Dropped before scoring: closed tenders, tenders closing within `dias_minimos_preparacion`,
private tenders (unless `incluir_privadas`), `excluir_palabras` / `excluir_palabras_titulo` / `excluir_organismos`
matches, other regions when `solo_mis_regiones`, and tenders with no keyword or category match.

## Present the results

1. One line with the source date, the number of tenders evaluated and matched, and the
   main reasons tenders were dropped.
2. A table of the **top 15**: rank, score, code linked to its `url`, name, buyer,
   region, size, closing date, plus a short plain-language "why it fits".
3. The paths to the full top-100 files (`.html` to explore interactively, `.xlsx` for filtering, `.md` to read).
4. Quality check. Read the top 30 names. If unrelated tenders appear (a keyword
   matching the wrong sense, e.g. "limpieza de heridas" for a cleaning company), or
   fewer than ~30 tenders matched, propose specific profile edits: an exclusion word,
   a more specific keyword, a code prefix, or a larger region or size range. Re-run
   after the user agrees. Don't edit the profile silently.
5. Remind the user that the score is a triage aid. Before bidding they must read the
   bases on the tender page (requirements, guarantees, evaluation criteria, budget).

`--now 2026-10-21T08:00` pins the reference time, which helps when re-running against old data.
