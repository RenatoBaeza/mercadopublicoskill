"""Suggest UNSPSC (Código ONU) codes and categories for a set of keywords.

Scans the downloaded tenders, finds line items whose description / product name
matches any keyword, and lists the most frequent codes and category names so the
user can pick the ones that describe their business.

Usage:
    python suggest_codes.py --data data/licitaciones.json "aseo" "limpieza de oficinas" [--top 25]
"""
import argparse
import collections
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rank import matches, norm, phrase_stems  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("keywords", nargs="+")
    ap.add_argument("--data", default="data/licitaciones.json")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    with open(args.data, encoding="utf-8") as f:
        tenders = json.load(f)["licitaciones"]
    kws = [(k, phrase_stems(k)) for k in args.keywords]
    kws = [k for k in kws if k[1]]

    codes = collections.Counter()
    code_names = {}
    level3 = collections.Counter()
    tender_hits = collections.Counter()
    for t in tenders:
        hit_kws = set()
        for item in t.get("items", []):
            tokens = set(norm(f"{item.get('item_descripcion', '')} {item.get('producto', '')}").split())
            found = [k for k, stems in kws if matches(stems, tokens)]
            if not found:
                continue
            hit_kws.update(found)
            code = item.get("codigo_onu", "")
            codes[code] += 1
            code_names.setdefault(code, f"{item.get('producto', '')} › {item.get('nivel3', '')}")
            level3[f"{item.get('nivel1', '')} › {item.get('nivel2', '')} › {item.get('nivel3', '')}"] += 1
        for k in hit_kws:
            tender_hits[k] += 1

    print(json.dumps({
        "licitaciones_por_palabra": {k: tender_hits.get(k, 0) for k, _ in kws},
        "codigos_onu": [{"codigo": c, "prefijo_4": c[:4], "nombre": code_names[c], "items": n}
                        for c, n in codes.most_common(args.top)],
        "categorias": [{"ruta": p, "items": n} for p, n in level3.most_common(args.top)],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
