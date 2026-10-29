"""Bundle the HTML reports into one master page, data/reporte.html, with a tab per report.

Embeds whichever of these exist in the data folder (a missing one shows the command that builds it):
    ranking_top100.html     (mp-priorizar/rank.py)          current tenders worth applying to
    competencia.html        (mp-competencia/competitors.py) competitors, incumbents, past winners
    historico_ranking.html  (mp-competencia/rank_history.py) past awarded tenders that fit the profile

rank.py, competitors.py and rank_history.py call this after writing their own page, and their
--open opens the master page. Run it on its own to rebuild the page from the existing reports.

Usage:
    python reporte.py [--dir data] [--open]
"""
import argparse
import datetime as dt
import io
import json
import pathlib
import sys

PAGES = [
    ("ranking", "Licitaciones abiertas", "ranking_top100",
     "python .claude/skills/mp-priorizar/scripts/rank.py --open"),
    ("competencia", "Competencia", "competencia",
     "python .claude/skills/mp-competencia/scripts/competitors.py --open"),
    ("historico", "Adjudicaciones pasadas", "historico_ranking",
     "python .claude/skills/mp-competencia/scripts/rank_history.py --open"),
]


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _summary(page_id, d):
    # One line under each tab, read from the report's .json sibling.
    if page_id == "ranking" and d.get("ranking") is not None:
        return f"top {len(d['ranking'])} de {d.get('stats', {}).get('total', '?')}"
    if page_id == "competencia" and d.get("meta"):
        m = d["meta"]
        return f"{m.get('proveedores', '?')} proveedores · {m.get('meses', '')}"
    if page_id == "historico" and d.get("stats"):
        return f"{d['stats'].get('ranked', '?')} que calzan"
    return ""


def build(data_dir="data"):
    """Writes <data_dir>/reporte.html and returns its path."""
    data_dir = pathlib.Path(data_dir)
    pages = []
    for page_id, title, stem, cmd in PAGES:
        html_path = data_dir / f"{stem}.html"
        html = html_path.read_text(encoding="utf-8") if html_path.exists() else None
        pages.append({
            "id": page_id, "titulo": title, "comando": cmd, "html": html,
            "resumen": _summary(page_id, _json(data_dir / f"{stem}.json")) if html else "",
        })
    payload = {
        "empresa": _json(data_dir / "company_profile.json").get("empresa", ""),
        "generado": dt.datetime.now().isoformat(timespec="minutes"),
        "paginas": pages,
    }
    template = pathlib.Path(__file__).with_name("reporte_template.html").read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    out = data_dir / "reporte.html"
    out.write_text(template.replace("/*__DATA__*/", data), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default="data", help="folder with the reports (default: data)")
    ap.add_argument("--open", action="store_true", help="open the page in Chrome (or the default browser)")
    a = ap.parse_args()
    out = build(a.dir)
    print(f"Reporte unificado: {out}")
    if a.open:
        from rank import open_in_browser
        opened = open_in_browser(out)
        print(f"HTML abierto en {opened}" if opened else "No se pudo abrir el HTML en un navegador")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
