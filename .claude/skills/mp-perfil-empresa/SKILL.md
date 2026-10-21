---
name: mp-perfil-empresa
description: Interview an entrepreneur about their company's skills, products, regions and capacity, and save a company profile (data/company_profile.json) used to match Chilean public tenders from Mercado Público. Use when the user wants to set up or update their company profile for licitaciones / ChileCompra, or before ranking tenders.
---

# Company profile for Mercado Público tenders

Goal: produce `data/company_profile.json`, which `mp-priorizar` uses to score tenders.
Talk to the user in their language (Spanish or English). Keep the interview short:
group questions, use `AskUserQuestion` for multiple-choice ones, and never ask
something you can infer from earlier answers.

If `data/company_profile.json` already exists, show a short summary of it and ask
whether to update specific fields or start over.

## 1. Free-text questions (ask together, in one message)

1. Company name (and RUT, optional).
2. What does the company do? 2–3 sentences.
3. List the main products and/or services you sell (as specific as possible, e.g.
   "aseo de oficinas", "notebooks y monitores", "mantención de aire acondicionado").
4. Secondary things you could also deliver, even if they are not your core business.
5. Anything you definitely do NOT want (products, buyers, kinds of work).
6. Experience selling to the State? (none / some / frequent) and whether you are
   registered in the Registro de Proveedores (ChileProveedores).

## 2. Multiple-choice questions (`AskUserQuestion`, up to 4 per call)

- **Offer type**: Bienes (goods) / Servicios / Obras (construction) / Mixto.
- **Regions**: Todo Chile / Only my region / A few regions. If not "Todo Chile",
  follow up asking which regions (free text), and whether tenders outside those
  regions should be hidden entirely (`solo_mis_regiones`) or only scored lower.
- **Contract size** (multiSelect). UTM ≈ CLP 70.000 (approximate, it changes monthly):
  - `L1` — under 100 UTM (≈ < CLP 7M)
  - `LE` — 100 to 1.000 UTM (≈ CLP 7M–70M)
  - `LP` — 1.000 to 2.000 UTM (≈ CLP 70M–140M)
  - `LQ`/`LR` — over 2.000 UTM (≈ > CLP 140M); ask as one option, store both codes
- **Preparation time**: minimum days you need to prepare a bid: 2 / 5 / 10 / 15.
- **Bank guarantees**: Can you issue boletas de garantía / pólizas? If not, advise
  that larger tenders (LP and above) usually require a garantía de fiel cumplimiento,
  and suggest leaving `LQ`/`LR` out of `tamanos`.
- **Private tenders** (licitaciones privadas, invitation only): include or not
  (default: no).

## 3. Build the keyword list

From the answers, write Spanish keywords **as Chilean public buyers phrase them**.
Include synonyms and common procurement wording; each keyword is matched as a phrase
(all words must appear, accents and plurals are ignored):

- Cleaning company → `aseo`, `limpieza`, `sanitización`, `desinfección`, `control de plagas`
- IT → `software`, `desarrollo de sistemas`, `soporte computacional`, `notebook`, `licencias`
- Catering → `alimentación`, `colaciones`, `servicio de casino`, `coffee break`

Use 5–15 primary keywords (`palabras_clave`) and up to 10 secondary ones
(`palabras_clave_secundarias`, which count half). Avoid generic words that match
everything (`servicio`, `adquisición`, `suministro`, `compra`).

## 4. Suggest UNSPSC codes from real data (if the data is downloaded)

If `data/licitaciones.json` exists (otherwise run the `mp-descargar` skill first, or skip
this step), run:

```
python .claude/skills/mp-priorizar/scripts/suggest_codes.py --data data/licitaciones.json "<kw1>" "<kw2>" ...
```

The output lists the Código ONU codes and category paths of items that match the
keywords, and how many tenders each keyword hits. Use it to:
- pick 4-digit (family) or 8-digit (exact) code prefixes that fit the business → `codigos_onu`
- pick category names (Nivel 3 names) that fit → `categorias`
- spot keywords that hit unrelated things (e.g. "limpieza" also hits "limpieza de heridas"
  in medical supplies) → add an exclusion word (`heridas`, `quirúrgico`) or drop the keyword
- spot keywords with 0 hits → reword them

Show the user the proposed codes/categories and exclusions in a short list and let
them confirm or edit.

## 5. Save the profile

Write `data/company_profile.json` (create `data/` if needed) following
[profile_template.json](profile_template.json). Field reference:

| Field | Meaning |
|---|---|
| `empresa`, `rut`, `descripcion`, `tipo_oferta`, `experiencia_estado`, `registro_proveedores`, `puede_emitir_garantias` | Informational; shown in the report |
| `palabras_clave` | Primary keywords (full weight) |
| `palabras_clave_secundarias` | Secondary keywords (half weight) |
| `codigos_onu` | UNSPSC prefixes, 2–8 digits (longer = more precise) |
| `categorias` | Category names matched against Nivel 1/2/3 and product name |
| `excluir_palabras` | Tender is dropped if the title or any item matches |
| `excluir_palabras_titulo` | Tender is dropped only if the title matches (e.g. `adquisición de licencias`, keeps service tenders that include a licence item) |
| `excluir_organismos` | Buyer names (substring) to drop |
| `regiones` | Region names, e.g. `"Metropolitana"`, `"Biobío"`, `"Los Lagos"`. Empty = all Chile |
| `solo_mis_regiones` | `true` drops other regions instead of scoring them lower |
| `tamanos` | Any of `L1`, `LE`, `LP`, `LQ`, `LR` |
| `dias_minimos_preparacion` | Tenders closing sooner than this are dropped |
| `incluir_privadas` | Include invitation-only tenders |

Finish with a 5-line summary of the profile and point to the next step (`mp-priorizar`).
