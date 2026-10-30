---
name: mp-priorizar
description: Score and rank downloaded Mercado Público tenders against the company profile and suggest the top 100 to apply for, with the reasons for each score, as xlsx/csv/json/markdown and an interactive HTML page. Use when the user asks which Chilean public tenders (licitaciones) their company should apply to, or wants the ranking refreshed.
---

# Rank tenders for the company

Requires `data/company_profile.json` (from `mp-perfil-empresa`) and
`data/licitaciones.json` (from `mp-descargar`). If either is missing, run that skill
first. If the data's `descargado` date is not today, offer to refresh it.

## Run

```
python .Codex/skills/mp-priorizar/scripts/rank.py --profile data/company_profile.json --data data/licitaciones.json --top 100 --out data/ranking_top100 --open
```

Outputs `data/ranking_top100.xlsx` (needs `openpyxl`), `.csv`, `.json`, `.md` and `.html`, and
rebuilds `data/reporte.html`, the master page with one tab per report (this ranking, and the
competition and past-awards pages from `mp-competencia` when they exist; see `scripts/reporte.py`).
`--open` opens `data/reporte.html` in Chrome when it is installed, otherwise in the default browser
(leave it out for quick re-runs while tuning the profile if the user doesn't want a new tab each time).
The export has no amounts, so the script reads each ranked tender's "Monto Total Estimado" from
its page on mercadopublico.cl (about 6 s for 100 tenders) and caches it in `data/montos_cache.json`,
so re-runs only fetch new tenders. Many buyers don't publish the amount; those show the UTM
bracket from the tender type instead. `--sin-montos` skips the lookup (offline runs).
The `.html` is a self-contained page built from `scripts/ranking_template.html`: open it in a
browser to search, filter by region / size / score / days to close, and sort columns (including
the amount). Each row shows what the buyer wants and the estimated amount; expanding it shows the job summary (full description, deliverables
with quantities, estimated amount and size bracket, steps to submit before the deadline).
Expanding a row also shows "Por qué calza": the score split into its five parts (table below) with
the keywords and code that matched. Rows can be starred into a shortlist (kept in the browser's
local storage). On phones only the search box stays pinned; the other filters open from "Filtros".
ALL-CAPS titles and descriptions are sentence-cased (acronyms like TI or DGMN kept).

Each ranked tender is remembered in `data/vistas.json` with the day of the data download it first
appeared in. Tenders first seen in today's download get `nueva: true` (a "Nueva" badge and a
"Solo nuevas" filter on the page); re-running on the same day, e.g. while tuning the profile, keeps
the flags, and the very first run flags nothing. Delete `vistas.json` to start over.
The JSON also carries `descripcion` and `entregables` for each ranked tender.
The console prints the counts, the reasons tenders were dropped, the top 10, `nuevas` with the
best new ones (`nuevas_top10`), and how many close within 7 days (`cierran_en_7_dias`).

## How the score works (0–100)

| Part | Max | Basis |
|---|---|---|
| Keywords | 45 | Profile keywords found in the title (×3), item descriptions (×2), categories (×1.5), description (×1); secondary keywords count half; saturates |
| Category | 25 | Best item match on `codigos_onu` prefixes (8 digits = 1.0 … 2 digits = 0.4) or `categorias` names, scaled by the share of items that match |
| Region | 10 | Buyer region in `regiones` (or the company serves all of Chile) |
| Size | 10 | Size bracket in `tamanos`; half credit when the size is unknown (`LS`, `OBRA`) |
| Time | 10 | Full credit at ≥ 6 days beyond `dias_minimos_preparacion` |

Dropped before scoring: closed tenders, tenders with no closing date published more than 90 days ago
(the export keeps some stale ones from as far back as 2010), tenders closing within `dias_minimos_preparacion`,
private tenders (unless `incluir_privadas`), `excluir_palabras` / `excluir_palabras_titulo` / `excluir_organismos`
matches, other regions when `solo_mis_regiones`, other sizes when `solo_mis_tamanos`, and tenders with no keyword or category match.

## Present the results

Write for a business owner, in their language, without jargon: say "calce" or "qué tan bien
encaja", not "score"; "tamaño del contrato", not `tamano`. Keep it short; the page holds the detail.

1. One line: the date of the list, how many tenders were evaluated and how many fit, and
   how many are new since the last ranking (when `nuevas` > 0). Mention the drop reasons only
   if one stands out (e.g. most were dropped as "fuera de tamaño").
2. A table of the **top 15**: rank, calce, code linked to its `url`, name, buyer, region,
   amount (or size bracket), closing date, plus a short plain-language "why it fits".
   On a repeat run with new tenders, show the new ones in the table first (from `nuevas_top10`),
   then the rest of the top. Flag the ones closing within 5 days.
3. Where to look next: the page (`data/reporte.html`) to filter, open each tender's summary and star
   a shortlist; `.xlsx` if they prefer Excel. One line, no list of every file.
4. Quality check. Read the top 30 names. If unrelated tenders appear (a keyword
   matching the wrong sense, e.g. "limpieza de heridas" for a cleaning company), or
   fewer than ~30 tenders matched, propose specific profile edits: an exclusion word,
   a more specific keyword, a code prefix, or a larger region or size range. Re-run
   after the user agrees (with `--sin-montos` left off, the amounts are cached). Don't edit the
   profile silently.
5. Remind the user in one line that the calce is a triage aid. Before bidding they must read the
   bases on the tender page (requirements, guarantees, evaluation criteria, budget).

`--now 2026-10-21T08:00` pins the reference time, which helps when re-running against old data.
