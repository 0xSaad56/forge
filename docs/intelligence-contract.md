# Forge Intel -> Forge Contract

Forge should consume security intelligence as normal local knowledge rather than embedding feed-specific collectors into the application.

The future `Forge Intel` project should export two layers:

1. **Structured records** for exact filtering/correlation.
2. **Human-readable documents** for Forge's existing hybrid retrieval pipeline.

## Recommended record identity

Use the CVE ID when available. A GHSA, advisory ID, package vulnerability ID, or vendor advisory ID can be retained as an additional identifier.

## Suggested record shape

```json
{
  "schema_version": "1.0",
  "record_type": "vulnerability",
  "id": "CVE-YYYY-NNNNN",
  "title": "Example vulnerability",
  "summary": "Short technical description.",
  "published_at": "2026-01-01T00:00:00Z",
  "modified_at": "2026-01-02T00:00:00Z",
  "affected": [],
  "severity": {
    "cvss_v3": null,
    "cvss_v4": null
  },
  "exploitability": {
    "epss": null,
    "epss_percentile": null,
    "cisa_kev": false
  },
  "exploitation": {
    "public_poc": false,
    "exploitdb": false,
    "metasploit": false,
    "github_poc": false
  },
  "detection": {
    "nuclei": false,
    "sigma": false,
    "yara": false
  },
  "references": [],
  "sources": []
}
```

## Design rules

- Preserve source provenance.
- Keep publication and modification timestamps.
- Never silently merge conflicting source facts.
- Prefer canonical identifiers for correlation.
- Keep exploit code separate from vulnerability metadata.
- Keep raw source snapshots outside the Forge repository unless licensing permits redistribution.
- Export deterministic JSON/Markdown so Forge can re-index it reproducibly.

## Example export layout

```text
forge-intel-export/
├── records/
│   ├── CVE-2026-00001.json
│   └── CVE-2026-00002.json
├── documents/
│   ├── CVE-2026-00001.md
│   └── CVE-2026-00002.md
└── manifest.json
```
