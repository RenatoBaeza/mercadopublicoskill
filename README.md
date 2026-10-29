# mercadopublicoskill

Claude Code skills that help an entrepreneur find Chilean public tenders
(licitaciones de [Mercado Público](https://www.mercadopublico.cl)) worth applying to.

| Skill | What it does |
|---|---|
| `/mp-buscar-licitaciones` | Runs the full flow below, start to finish |
| `/mp-perfil-empresa` | Interviews you about your company and saves `data/company_profile.json` |
| `/mp-descargar` | Downloads today's published tenders (`att.ashx?id=5`), unzips them to `data/licitaciones.xlsx` and `data/licitaciones.json` |
| `/mp-priorizar` | Scores every tender against your profile (0–100) and writes the top 100 to `data/ranking_top100.{xlsx,csv,json,md,html}` |
| `/mp-competencia` | Downloads 12 months of past tenders with every bid and award (ChileCompra open data) and reports competitors, incumbents and past winners for your ranked tenders in `data/competencia.{json,md,xlsx,html}`, and ranks past awarded tenders with the same scoring, with who won them, in `data/historico_ranking.{json,csv,xlsx,html}` |

Every `.html` report is also bundled into `data/reporte.html`, one page with a tab per report,
rebuilt each time a report is generated (or on demand with `python .claude/skills/mp-priorizar/scripts/reporte.py --open`).

Requirements: Python 3.9+; `openpyxl` for the Excel ranking output (`pip install openpyxl`).

Scripts can also be run directly:

```
python .claude/skills/mp-descargar/scripts/download.py --out data
python .claude/skills/mp-priorizar/scripts/suggest_codes.py --data data/licitaciones.json aseo limpieza
python .claude/skills/mp-priorizar/scripts/rank.py --profile data/company_profile.json --data data/licitaciones.json
python .claude/skills/mp-competencia/scripts/download_history.py --profile data/company_profile.json --meses 12
python .claude/skills/mp-competencia/scripts/competitors.py
python .claude/skills/mp-competencia/scripts/rank_history.py
```

See [profile_template.json](.claude/skills/mp-perfil-empresa/profile_template.json) for the profile format.
