---
name: mp-find-tenders
description: End-to-end assistant that helps an entrepreneur find Chilean State tenders (licitaciones de Mercado Público / ChileCompra) worth applying to. It interviews them about the company, downloads today's published tenders, and ranks the top 100 matches. Use when the user asks to find government contracts, public tenders, or licitaciones in Chile for their business.
---

# Find Chilean public tenders for a company

This skill chains three skills. Follow each one's SKILL.md when you reach its step.

1. **Profile**: `mp-company-profile` ([SKILL.md](../mp-company-profile/SKILL.md)).
   If `data/company_profile.json` exists, summarise it and ask whether to reuse it.
   Otherwise run the interview.
2. **Data**: `mp-download` ([SKILL.md](../mp-download/SKILL.md)).
   Skip it if `data/licitaciones.json` was downloaded today (check its `descargado` field).
   You can run this step while waiting for the user's interview answers.
3. **Refine**: with the data present, run step 4 of `mp-company-profile`
   (`suggest_codes.py`) to propose Código ONU codes and exclusions, and confirm them with the user.
4. **Rank**: `mp-rank` ([SKILL.md](../mp-rank/SKILL.md)). Produce the top 100 and present
   the top 15 with reasons. Then run its quality check and offer one round of profile tuning.

All files live in `data/` at the project root:
`company_profile.json`, `licitaciones.xlsx`, `licitaciones.json`, `ranking_top100.{xlsx,csv,json,md,html}`.
