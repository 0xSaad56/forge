#!/usr/bin/env fish
# Download one NVD 2.0 year feed → split markdown parts under knowledge/cves/
# Usage: fish scripts/fetch-nvd-year.fish 2025

set -l YEAR $argv[1]
if test -z "$YEAR"
    echo "Usage: fish scripts/fetch-nvd-year.fish <year>"
    exit 1
end

set -l ROOT (cd (dirname (status -f))/..; and pwd)
set -l OUTDIR $ROOT/knowledge/cves
set -l CACHE $ROOT/data/nvd-cache
mkdir -p $OUTDIR $CACHE

set -l URL "https://nvd.nist.gov/feeds/json/cve/2.0/nvdcve-2.0-$YEAR.json.gz"
set -l GZ $CACHE/nvdcve-2.0-$YEAR.json.gz
set -l JSON $CACHE/nvdcve-2.0-$YEAR.json

echo "Fetching NVD year $YEAR …"
if not test -s $GZ
    curl -fL --retry 3 -o $GZ $URL
    or begin; echo "Download failed"; exit 1; end
end
if not test -s $JSON
    gunzip -c $GZ > $JSON
    or begin; echo "Decompress failed"; exit 1; end
end

rm -f $OUTDIR/nvd-$YEAR.md $OUTDIR/nvd-$YEAR-part-*.md 2>/dev/null

echo "Writing split parts …"
$ROOT/.venv/bin/python -c "
import json, pathlib, sys
year, src_s, out_s = sys.argv[1], sys.argv[2], sys.argv[3]
src, outdir = pathlib.Path(src_s), pathlib.Path(out_s)
vulns = (json.loads(src.read_text(encoding='utf-8', errors='ignore')).get('vulnerabilities') or [])
PER = 400
n = 0
for start in range(0, len(vulns), PER):
    batch = vulns[start:start+PER]
    lines = [f'# NVD {year} part {start//PER+1}', f'Count: {len(batch)} / {len(vulns)}', '']
    for item in batch:
        cve = item.get('cve') or {}
        cid = cve.get('id') or 'UNKNOWN'
        descs = cve.get('descriptions') or []
        desc = next((d.get('value') or '' for d in descs if d.get('lang')=='en'), '') or (descs[0].get('value') if descs else '') or ''
        metrics = cve.get('metrics') or {}
        cvss = ''
        for key in ('cvssMetricV31','cvssMetricV30','cvssMetricV2'):
            arr = metrics.get(key) or []
            if arr:
                m = (arr[0].get('cvssData') or {})
                cvss = f\"{m.get('baseScore','')} {m.get('baseSeverity','')} {m.get('vectorString','')}\"
                break
        refs = [r.get('url') for r in (cve.get('references') or [])[:6] if r.get('url')]
        lines += [f'## {cid}']
        if cvss: lines.append(f'CVSS: {cvss}')
        if desc: lines.append(desc)
        if refs:
            lines.append('References:')
            lines += [f'- {u}' for u in refs]
        lines.append('')
    out = outdir / f'nvd-{year}-part-{start//PER+1:03d}.md'
    out.write_text('\\n'.join(lines), encoding='utf-8')
    n += 1
    print(f'  {out.name}  {out.stat().st_size//1024} KB')
print(f'Done: {n} files, {len(vulns)} CVEs')
" $YEAR $JSON $OUTDIR

echo "Next: cd $ROOT && .venv/bin/python ingest.py --force --device cuda"
