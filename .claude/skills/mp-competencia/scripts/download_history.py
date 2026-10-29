"""Download past Mercado Público tenders (with every bid and award) and keep those relevant to the profile.

Source: ChileCompra open data, one zip per month of publication:
    https://transparenciachc.blob.core.windows.net/lic-da/{YYYY}-{M}.zip
Each zip holds a ~250 MB CSV (';'-separated, cp1252) with one row per offer per line item,
including losing offers, the awarded amount and whether the offer was selected.

A tender is kept when anything the ranking can score on matches: a line's Código ONU starts with a
profile prefix, or a keyword (primary or secondary) or category name appears in the title,
description, a line or its categories. Each kept tender carries `relevante`, a stricter test used
by the competitor report: a matching Código ONU, a primary keyword in the title or a line, or a
secondary keyword in the title. Tenders matching the profile's exclusions are dropped. Zips are
cached in data/raw/historico/; recent months are re-downloaded after a week because awards keep
arriving.

Usage:
    python download_history.py --profile data/company_profile.json [--meses 12] [--hasta 2026-09]
                               [--out data/historico.json] [--refrescar]
"""
import argparse
import concurrent.futures
import csv
import datetime as dt
import io
import json
import pathlib
import sys
import time
import urllib.request
import zipfile

SKILLS = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILLS / "mp-priorizar" / "scripts"))
sys.path.insert(0, str(SKILLS / "mp-descargar" / "scripts"))
from download import PRIVATE_CODES, SIZE_BRACKET  # noqa: E402
from rank import matches, norm, phrase_stems  # noqa: E402

URL = "https://transparenciachc.blob.core.windows.net/lic-da/{y}-{m}.zip"
DETAIL_URL = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={}"
REFRESH_RECENT_MONTHS = 3
REFRESH_AFTER_DAYS = 7
MAX_DESCRIPTION = 3000
# Approximate CLP value of other currencies, only used to add up amounts across tenders.
CLP_PER = {"peso chileno": 1, "unidad de fomento": 39500, "dolar": 950, "euro": 1050,
           "unidad tributaria mensual": 69000}
CODE_CURRENCY = {"CLP": "peso chileno", "CLF": "unidad de fomento", "USD": "dolar", "EUR": "euro",
                 "UTM": "unidad tributaria mensual"}


def months_back(until, n):
    y, m = until
    out = []
    for _ in range(n):
        out.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def month_of(path):
    y, m = path.stem.split("_")[1].split("-")
    return int(y), int(m)


def fetch(y, m, cache_dir, refresh):
    path = cache_dir / f"lic_{y}-{m}.zip"
    today = dt.date.today()
    age_months = (today.year - y) * 12 + today.month - m
    if path.exists() and not refresh:
        stale = (age_months <= REFRESH_RECENT_MONTHS
                 and time.time() - path.stat().st_mtime > REFRESH_AFTER_DAYS * 86400)
        if not stale:
            return path, "cache"
    req = urllib.request.Request(URL.format(y=y, m=m), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    if data[:2] != b"PK":
        raise RuntimeError(f"{y}-{m}: the server did not return a zip")
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path, "descargado"


def num(s):
    try:
        return float(str(s).replace(",", "."))
    except ValueError:
        return 0.0


# Upper bracket limit in CLP (UTM ≈ 70.000); multi-year contracts can run well past it.
SIZE_CAP_CLP = {"L1": 7e6, "LE": 7e7, "LP": 1.4e8, "LQ": 3.5e8}
MAX_OVER_CAP = 50
MAX_PLAUSIBLE_CLP = 2e10


def to_clp(amount, currency, size=""):
    """CLP value of an amount. Some amounts are labelled UF/USD although the figures are already
    pesos (350.000 "UF" a month on an LE tender): when the conversion lands far beyond what the size
    bracket allows and the raw figure does not, keep the raw figure."""
    rate = CLP_PER.get(norm(currency), 0)
    converted = amount * rate
    limit = SIZE_CAP_CLP[size] * MAX_OVER_CAP if size in SIZE_CAP_CLP else MAX_PLAUSIBLE_CLP
    if rate > 1 and converted > limit and amount <= limit:
        return amount
    return converted


def stems_of(phrases):
    return [s for s in (phrase_stems(k) for k in phrases) if s]


class Matcher:
    def __init__(self, p):
        self.onu = tuple(sorted({"".join(c for c in str(x) if c.isdigit()) for x in p.get("codigos_onu", [])} - {""}))
        self.kw1 = stems_of(p.get("palabras_clave", []))
        self.kw2 = stems_of(p.get("palabras_clave_secundarias", []))
        self.cats = stems_of(p.get("categorias", []))
        self.excl = stems_of(p.get("excluir_palabras", []))
        self.excl_title = stems_of(p.get("excluir_palabras_titulo", []))
        self.excl_org = [norm(o) for o in p.get("excluir_organismos", []) if norm(o)]

    @staticmethod
    def any_in(stem_list, tokens):
        return any(matches(s, tokens) for s in stem_list)

    def tender(self, title, description, org):
        """(excluded, strict hit, broad hit) from the tender-level fields."""
        title_t = set(norm(title).split())
        desc_t = set(norm(description).split())
        excluded = (self.any_in(self.excl + self.excl_title, title_t)
                    or any(o in norm(org) for o in self.excl_org))
        strict = self.any_in(self.kw1 + self.kw2, title_t)
        broad = strict or self.any_in(self.kw1 + self.kw2, desc_t)
        return excluded, strict, broad

    def line(self, onu, text, categories):
        """(excluded, strict hit, broad hit) for one line item."""
        tokens = set(norm(text).split())
        if self.any_in(self.excl, tokens):
            return True, False, False
        onu_hit = bool(self.onu) and onu.startswith(self.onu)
        strict = onu_hit or self.any_in(self.kw1, tokens)
        cat_tokens = set(norm(categories).split())
        broad = (strict or self.any_in(self.kw2, tokens)
                 or self.any_in(self.kw1 + self.kw2 + self.cats, cat_tokens))
        return False, strict, broad


def parse_month(path, profile):
    m = Matcher(profile)
    tenders, rows_seen, malformed = {}, 0, 0
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(name) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="cp1252", errors="replace", newline=""),
                                    delimiter=";")
            for r in reader:
                rows_seen += 1
                if r.get("Oferta seleccionada") is None:  # truncated row (last column missing)
                    malformed += 1
                    continue
                code = r["CodigoExterno"].strip()
                if not code:
                    continue
                t = tenders.get(code)
                if t is None:
                    excluded, strict, broad = m.tender(r["Nombre"], r["Descripcion"], r["NombreOrganismo"])
                    tipo = r["Tipo"].strip()
                    adjudicacion = r["FechaAdjudicacion"][:10]
                    t = tenders[code] = {
                        "codigo": code,
                        "nombre": r["Nombre"].strip(),
                        "descripcion": r["Descripcion"].strip()[:MAX_DESCRIPTION],
                        "organismo": r["NombreOrganismo"].strip(),
                        "unidad": r["NombreUnidad"].strip(),
                        "region": r["RegionUnidad"].strip(),
                        "tipo": r["Tipo de Adquisicion"].strip(),
                        "tipo_codigo": tipo,
                        "tamano": SIZE_BRACKET.get(tipo, tipo),
                        "privada": tipo in PRIVATE_CODES,
                        "estado": r["Estado"].strip(),
                        "fecha_publicacion": r["FechaPublicacion"][:10],
                        "fecha_cierre": r["FechaCierre"][:10] if not r["FechaCierre"].startswith("1900") else "",
                        "fecha_adjudicacion": adjudicacion if not adjudicacion.startswith("1900") else "",
                        "monto_estimado": to_clp(num(r["MontoEstimado"]), CODE_CURRENCY.get(r["CodigoMoneda"].strip(), ""),
                                                 SIZE_BRACKET.get(tipo, tipo)),
                        "n_oferentes": int(num(r["NumeroOferentes"])),
                        "url": DETAIL_URL.format(code),
                        "_excluded": excluded, "_strict": strict, "_broad": broad,
                        "items": {},
                        "ofertas": {},
                    }
                if t["_excluded"]:
                    continue
                onu = r["CodigoProductoONU"].strip()
                categories = f"{r['Rubro1']} {r['Rubro2']} {r['Rubro3']} {r['Nombre producto genrico']}"
                line_id = r["Codigoitem"].strip() or r["Correlativo"].strip()
                if line_id not in t["items"]:
                    l_excl, l_strict, l_broad = m.line(
                        onu, f"{r['Nombre linea Adquisicion']} {r['Descripcion linea Adquisicion']}", categories)
                    t["_excluded"] |= l_excl
                    t["_strict"] |= l_strict
                    t["_broad"] |= l_broad
                    t["items"][line_id] = {
                        "item_descripcion": r["Descripcion linea Adquisicion"].strip()[:300],
                        "codigo_onu": onu,
                        "unidad": r["UnidadMedida"].strip(),
                        "cantidad": num(r["Cantidad"]),
                        "producto": r["Nombre producto genrico"].strip(),
                        "nivel1": r["Rubro1"].strip(),
                        "nivel2": r["Rubro2"].strip(),
                        "nivel3": r["Rubro3"].strip(),
                    }
                rut = r["RutProveedor"].strip()
                if not rut:
                    continue
                o = t["ofertas"].setdefault(rut, {"rut": rut, "nombre": r["NombreProveedor"].strip(),
                                                  "ofertado": 0.0, "adjudicado": 0.0, "gano": False,
                                                  "moneda": r["Moneda de la Oferta"].strip()})
                o["ofertado"] += to_clp(num(r["Valor Total Ofertado"]), o["moneda"], t["tamano"])
                if r["Oferta seleccionada"].strip().lower().startswith("selec"):
                    o["gano"] = True
                    o["adjudicado"] += to_clp(num(r["MontoLineaAdjudica"]), o["moneda"], t["tamano"])
    kept = {}
    for code, t in tenders.items():
        if t.pop("_excluded") or not t["_broad"]:
            continue
        t["relevante"] = t.pop("_strict")
        del t["_broad"]
        t["items"] = list(t["items"].values())
        t["codigos_onu"] = sorted({i["codigo_onu"] for i in t["items"] if i["codigo_onu"]})
        t["n_lineas"] = len(t["items"])
        t["ofertas"] = sorted(t["ofertas"].values(), key=lambda o: (not o["gano"], -o["adjudicado"]))
        kept[code] = t
    return path.name, rows_seen, malformed, kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="data/company_profile.json")
    ap.add_argument("--meses", type=int, default=12)
    ap.add_argument("--hasta", help="Last month YYYY-MM (default: last month)")
    ap.add_argument("--out", default="data/historico.json")
    ap.add_argument("--cache", default="data/raw/historico")
    ap.add_argument("--refrescar", action="store_true", help="Re-download every month")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    profile = json.loads(pathlib.Path(a.profile).read_text(encoding="utf-8"))
    if a.hasta:
        until = tuple(int(x) for x in a.hasta.split("-"))
    else:
        first = dt.date.today().replace(day=1) - dt.timedelta(days=1)
        until = (first.year, first.month)
    months = months_back(until, a.meses)
    cache = pathlib.Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)

    paths = []
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        futs = {ex.submit(fetch, y, m, cache, a.refrescar): (y, m) for y, m in months}
        for f in concurrent.futures.as_completed(futs):
            y, m = futs[f]
            try:
                path, how = f.result()
                paths.append(path)
                print(f"{y}-{m:02d}: {how}", file=sys.stderr)
            except Exception as e:  # a missing month should not sink the rest
                print(f"{y}-{m:02d}: ERROR {e}", file=sys.stderr)

    merged, rows_total = {}, 0
    with concurrent.futures.ProcessPoolExecutor(a.workers) as ex:
        for name, rows_seen, malformed, tenders in ex.map(parse_month, sorted(paths, key=month_of),
                                                           [profile] * len(paths)):
            rows_total += rows_seen
            merged.update(tenders)  # months are processed in order, so the newest copy wins
            bad = f", {malformed} filas incompletas omitidas" if malformed else ""
            strict = sum(1 for t in tenders.values() if t["relevante"])
            print(f"{name}: {rows_seen} filas, {len(tenders)} licitaciones ({strict} relevantes){bad}", file=sys.stderr)

    out = {
        "fuente": URL.format(y="{YYYY}", m="{M}"),
        "generado": dt.datetime.now().isoformat(timespec="seconds"),
        "meses": [f"{y}-{m:02d}" for y, m in months],
        "meses_ok": len(paths),
        "filas_leidas": rows_total,
        "empresa": profile.get("empresa", ""),
        "licitaciones": sorted(merged.values(), key=lambda t: t["fecha_publicacion"], reverse=True),
    }
    pathlib.Path(a.out).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    vals = merged.values()
    print(json.dumps({"meses": f"{out['meses'][0]} a {out['meses'][-1]}", "meses_ok": len(paths),
                      "filas_leidas": rows_total, "licitaciones": len(merged),
                      "relevantes": sum(1 for t in vals if t["relevante"]),
                      "con_adjudicacion": sum(1 for t in vals if any(o["gano"] for o in t["ofertas"])),
                      "salida": a.out}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
