---
name: mp-buscar-licitaciones
description: End-to-end assistant that helps an entrepreneur find Chilean State tenders (licitaciones de Mercado Público / ChileCompra) worth applying to. It interviews them about the company, downloads today's published tenders, and ranks the top 100 matches. Use when the user asks to find government contracts, public tenders, or licitaciones in Chile for their business.
---

# Find Chilean public tenders for a company

This skill chains three skills. Follow each one's SKILL.md when you reach its step.

The user is usually a business owner, not a developer: talk in their language (most often
Spanish), in plain words. Never show them commands, JSON, file internals or field names
(`palabras_clave`, `tamanos`); say "tus palabras clave", "los tamaños de contrato que manejas".
Run the scripts yourself and report the outcome. Between steps, say in one short line what
you are doing ("Descargando las licitaciones de hoy…").

## Start

Before anything else, check whether `data/company_profile.json` exists and whether
`data/licitaciones.json` was downloaded today (its `descargado` field). If the data is missing or
old, start `mp-descargar` in the background right away so it is ready by the time it is needed.

- **First time** (no profile): tell the user in two lines what will happen: a few questions about
  the company (~3 minutes), then today's tenders ranked by how well they fit, in a page they can
  filter. Nothing is submitted for them. Then go to step 1.
- **Returning user** (profile exists): don't re-interview and don't ask whether to reuse it.
  Say in one line which profile you are using ("Uso tu perfil de *Empresa*: desarrollo de software,
  RM y Valparaíso, contratos L1–LE") and go straight to step 4. Offer changes after the results.
  If the user's message asks for something different ("ahora también hago aseo"), update just
  that part of the profile first.

## Steps

1. **Profile**: `mp-perfil-empresa` ([SKILL.md](../mp-perfil-empresa/SKILL.md)). Run the interview.
2. **Data**: `mp-descargar` ([SKILL.md](../mp-descargar/SKILL.md)), already started in the background.
3. **Refine**: with the data present, run step 4 of `mp-perfil-empresa`
   (`suggest_codes.py`) to propose Código ONU codes and exclusions, and confirm them with the user.
   Skip it for returning users unless they changed what the company sells.
4. **Rank**: `mp-priorizar` ([SKILL.md](../mp-priorizar/SKILL.md)). Produce the top 100 and present
   them as its "Present the results" section says (new tenders first on a repeat run). Then run its
   quality check.
5. **Next step**: end with one `AskUserQuestion` offering what to do next, so the user never has to
   guess. Options (pick the ones that apply, at most 4):
   - *Ajustar el perfil*: when the quality check found unrelated tenders or too few matches; name the fix.
   - *Ver la competencia*: run `mp-competencia` ([SKILL.md](../mp-competencia/SKILL.md)): who won
     similar tenders in the last 12 months, incumbents by buyer, bidder counts and reference amounts
     for the ranked tenders, and past awarded tenders that fit the profile with who won them.
     Mention the first run downloads ~180 MB and takes a few minutes.
   - *Revisar una licitación*: go through one tender's details and what its bases require.
   - *Listo por hoy*: remind them that running this skill again another day marks which tenders are new.

All files live in `data/` at the project root:
`company_profile.json`, `licitaciones.xlsx`, `licitaciones.json`, `ranking_top100.{xlsx,csv,json,md,html}`,
`historico.json`, `competencia.{json,md,xlsx,html}`, `historico_ranking.{json,csv,xlsx,html}`, and
`reporte.html`, the master page that puts every `.html` report in one place, a tab each. Point the
user to `data/reporte.html` rather than the individual pages.
