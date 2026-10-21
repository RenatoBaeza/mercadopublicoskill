"""Download the Mercado Público "Licitaciones Publicadas" snapshot and convert it.

Fetches https://www.mercadopublico.cl/Portal/att.ashx?id=5 (a .zip with an
.xlsx and a .csv), extracts it, keeps the .xlsx and writes a .json with one
record per tender (line items grouped under "items").

Usage:
    python download.py [--out data] [--url URL] [--zip existing.zip]
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.request
import zipfile

DEFAULT_URL = "https://www.mercadopublico.cl/Portal/att.ashx?id=5"
DETAIL_URL = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={}"
MAX_MEMBER_BYTES = 500 * 1024 * 1024

# Column names as they appear in the CSV export and in the XLSX export.
COLUMNS = {
    "codigo": ("Textbox36", "Numero Adquisición"),
    "tipo": ("TipoLC", "Tipo Adquisición"),
    "nombre": ("Textbox37", "Nombre Adquisición"),
    "descripcion": ("Textbox38", "Descripción"),
    "organismo": ("Textbox39", "Organismo"),
    "region": ("citName", "Región Compradora"),
    "fecha_publicacion": ("Textbox40", "Fecha Publicación"),
    "fecha_cierre": ("FechaCierre1", "Fecha Cierre"),
    "item_descripcion": ("rbiDescription", "Descripción del producto/servicio"),
    "codigo_onu": ("rbiGoodAndService", "Código ONU"),
    "unidad": ("Unidad_de_Medida", "Unidad de Medida"),
    "cantidad": ("Cantidad", "Cantidad"),
    "producto": ("ProductoName", "Genérico"),
    "nivel1": ("Level1", "Nivel 1"),
    "nivel2": ("Level2", "Nivel 2"),
    "nivel3": ("Level3", "Nivel 3"),
}
TENDER_FIELDS = ("codigo", "tipo", "nombre", "descripcion", "organismo", "region",
                 "fecha_publicacion", "fecha_cierre")
ITEM_FIELDS = ("item_descripcion", "codigo_onu", "unidad", "cantidad", "producto",
               "nivel1", "nivel2", "nivel3")

# Tender-type code (suffix of the tender id, e.g. 1234-5-LE26) -> size bracket.
SIZE_BRACKET = {
    "L1": "L1", "E2": "L1",   # < 100 UTM
    "LE": "LE", "CO": "LE",   # 100 - 1.000 UTM
    "LP": "LP", "B2": "LP",   # 1.000 - 2.000 UTM
    "LQ": "LQ", "H2": "LQ",   # 2.000 - 5.000 UTM
    "LR": "LR", "I2": "LR",   # > 5.000 UTM
    "LS": "LS",               # servicios personales especializados (size unknown)
    "O1": "OBRA", "O2": "OBRA",
}
# Private (invitation-only) tenders; O2 = licitación privada de obras.
PRIVATE_CODES = {"E2", "CO", "B2", "H2", "I2", "O2"}


def download(url, dest, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (mp-download skill)"})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
            return
        except Exception as e:  # noqa: BLE001 - report and retry any network error
            print(f"download attempt {attempt} failed: {e}", file=sys.stderr)
            if attempt == retries:
                raise
            time.sleep(5 * attempt)


def safe_extract(zip_path, out_dir):
    """Extract only .xlsx/.csv members, flattened to their basename (no zip-slip)."""
    extracted = {}
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = os.path.basename(info.filename)
            ext = os.path.splitext(name)[1].lower()
            if info.is_dir() or ext not in (".xlsx", ".csv"):
                continue
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError(f"{name} is suspiciously large ({info.file_size} bytes)")
            target = os.path.join(out_dir, name)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted[ext] = target
    return extracted


def _header_index(header, field):
    for name in COLUMNS[field]:
        if name in header:
            return header.index(name)
    return None


def _rows_from_table(table):
    """table: list of rows (lists). Finds the header row and yields dicts."""
    title = ""
    header_at = None
    for i, row in enumerate(table):
        cells = [str(c).strip() if c is not None else "" for c in row]
        if not title:
            title = next((c for c in cells if c.startswith("Listado de Licitaciones")), "")
        if "Textbox36" in cells or "Numero Adquisición" in cells:
            header_at = i
            break
    if header_at is None:
        raise ValueError("could not find the header row in the export")
    header = [str(c).strip() if c is not None else "" for c in table[header_at]]
    idx = {f: _header_index(header, f) for f in COLUMNS}
    missing = [f for f in ("codigo", "nombre") if idx[f] is None]
    if missing:
        raise ValueError(f"export is missing required columns: {missing}")
    rows = []
    for row in table[header_at + 1:]:
        rec = {f: (row[i] if i is not None and i < len(row) else None) for f, i in idx.items()}
        if rec["codigo"]:
            rows.append(rec)
    return title, rows


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return _rows_from_table(list(csv.reader(f)))


def read_xlsx(path):
    import openpyxl  # only needed for the fallback path
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    table = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    wb.close()
    return _rows_from_table(table)


def to_iso(value):
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.replace(microsecond=0).isoformat()
    s = str(value).strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(s, fmt).isoformat()
        except ValueError:
            pass
    return s


def to_number(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return value
    # The export uses "." as decimal separator and no thousands separator.
    s = str(value).strip().replace(",", ".")
    try:
        n = float(s)
        return int(n) if n.is_integer() else n
    except ValueError:
        return str(value).strip()


def clean(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def group_tenders(rows):
    tenders = {}
    for r in rows:
        code = clean(r["codigo"])
        t = tenders.get(code)
        if t is None:
            t = {f: clean(r[f]) for f in TENDER_FIELDS}
            t["fecha_publicacion"] = to_iso(r["fecha_publicacion"])
            t["fecha_cierre"] = to_iso(r["fecha_cierre"])
            m = re.search(r"-([A-Z][A-Z0-9])\d{2}$", code)
            t["tipo_codigo"] = m.group(1) if m else ""
            t["tamano"] = SIZE_BRACKET.get(t["tipo_codigo"], "")
            t["privada"] = t["tipo_codigo"] in PRIVATE_CODES or t["tipo"].lower().startswith("licitación privada")
            t["url"] = DETAIL_URL.format(code)
            t["items"] = []
            tenders[code] = t
        item = {f: clean(r[f]) for f in ITEM_FIELDS}
        item["codigo_onu"] = re.sub(r"\D", "", item["codigo_onu"])
        item["cantidad"] = to_number(r["cantidad"])
        t["items"].append(item)
    return list(tenders.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data", help="output directory (default: data)")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--zip", help="use an already-downloaded zip instead of fetching")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    raw = os.path.join(out, "raw")
    os.makedirs(raw, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")

    if args.zip:
        zip_path = os.path.abspath(args.zip)
    else:
        zip_path = os.path.join(raw, f"Licitacion_Publicada_{stamp}.zip")
        print(f"Downloading {args.url} ...")
        download(args.url, zip_path)
    if not zipfile.is_zipfile(zip_path):
        sys.exit(f"ERROR: {zip_path} is not a zip file (the portal may have returned an error page)")

    extract_dir = os.path.join(raw, f"extract_{stamp}")
    os.makedirs(extract_dir, exist_ok=True)
    files = safe_extract(zip_path, extract_dir)
    if ".csv" not in files and ".xlsx" not in files:
        sys.exit("ERROR: the zip contains neither an .xlsx nor a .csv")

    if ".csv" in files:
        title, rows = read_csv(files[".csv"])
    else:
        title, rows = read_xlsx(files[".xlsx"])
    tenders = group_tenders(rows)

    xlsx_out = os.path.join(out, "licitaciones.xlsx")
    if ".xlsx" in files:
        shutil.copyfile(files[".xlsx"], xlsx_out)
    else:
        xlsx_out = None

    json_out = os.path.join(out, "licitaciones.json")
    payload = {
        "fuente": args.url,
        "descargado": dt.datetime.now().replace(microsecond=0).isoformat(),
        "titulo": title,
        "total_licitaciones": len(tenders),
        "total_lineas": len(rows),
        "licitaciones": tenders,
    }
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(json.dumps({
        "titulo": title,
        "licitaciones": len(tenders),
        "lineas": len(rows),
        "xlsx": xlsx_out,
        "json": json_out,
        "zip": zip_path,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
