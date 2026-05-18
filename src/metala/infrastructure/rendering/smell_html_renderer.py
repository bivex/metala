"""Render code smell reports as self-contained HTML."""

from __future__ import annotations

from html import escape
from pathlib import Path

from metala.domain.ports import SmellReportRenderer
from metala.domain.smells import SmellBundle, SourceSmellReport
from metala.domain.smells import SmellKind

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2, "note": 3}

# (accent fg, dim bg)
_KIND_COLORS: dict[str, tuple[str, str]] = {
    "long_function": ("#ffb86b", "#3d2200"),
    "long_parameter_list": ("#ffb86b", "#3d2200"),
    "large_class": ("#ffb86b", "#3d2200"),
    "deep_nesting": ("#ffb86b", "#3d2200"),
    "complex_flow": ("#ffb86b", "#3d2200"),
    "magic_number": ("#ffb86b", "#3d2200"),
    "excessive_locals": ("#ffb86b", "#3d2200"),
    "unused_parameter": ("#82aaff", "#1a2b52"),
    "switch_statement": ("#56d4dd", "#0d2b30"),
    "message_chain": ("#c4a7ff", "#281d40"),
    "data_clump": ("#c4a7ff", "#281d40"),
    "feature_envy": ("#ff93a9", "#3d1520"),
    "primitive_obsession": ("#ff93a9", "#3d1520"),
    "middle_man": ("#ff93a9", "#3d1520"),
    "speculative_generality": ("#ff93a9", "#3d1520"),
    "divergent_change": ("#ff93a9", "#3d1520"),
    "shotgun_surgery": ("#ff93a9", "#3d1520"),
    "temporary_field": ("#ff93a9", "#3d1520"),
    "refused_bequest": ("#ff93a9", "#3d1520"),
    "comment_density": ("#ff93a9", "#3d1520"),
    "divergent_branch": ("#ff93a9", "#3d1520"),
    "resource_overload": ("#ff93a9", "#3d1520"),
    "atomic_contention": ("#ff93a9", "#3d1520"),
}

# (fg, bg)
_SEVERITY_BADGE: dict[str, tuple[str, str]] = {
    "error": ("#ff93a9", "#371925"),
    "warning": ("#ffb86b", "#37230f"),
    "info": ("#82aaff", "#142550"),
    "note": ("#a6da95", "#163628"),
}


class MetalaSmellHtmlRenderer(SmellReportRenderer):
    """Dark-theme, self-contained HTML report for a SourceSmellReport."""

    def render_file(self, report: SourceSmellReport) -> str:
        smells = sorted(
            report.smells,
            key=lambda s: (
                _SEVERITY_ORDER.get(getattr(s, "severity", "warning"), 99),
                s.line,
                s.column,
            ),
        )
        total = len(smells)
        location = escape(report.source_location)

        # ── counts ──────────────────────────────────────────────────────────
        severity_counts: dict[str, int] = {}
        kind_counts: dict[str, int] = {}
        for s in smells:
            sev = getattr(s, "severity", "warning")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            k = s.kind.value if isinstance(s.kind, SmellKind) else str(s.kind)
            kind_counts[k] = kind_counts.get(k, 0) + 1

        # ── severity pills ──────────────────────────────────────────────────
        sev_pills = ""
        for sev in ("error", "warning", "info", "note"):
            cnt = severity_counts.get(sev, 0)
            if cnt == 0:
                continue
            fg, bg = _SEVERITY_BADGE.get(sev, ("#888", "#333"))
            sev_pills += (
                '<span class="pill" style="background:'
                + bg
                + ";color:"
                + fg
                + '">'
                + sev.title()
                + "</span>\n      "
            )

        # ── kind pills ──────────────────────────────────────────────────────
        kind_pills = ""
        items = sorted(kind_counts.items(), key=lambda x: -x[1])
        for kind, cnt in items[:10]:
            accent, dim_bg = _KIND_COLORS.get(kind, ("#888", "#333"))
            kind_pills += (
                '<span class="pill" style="background:'
                + dim_bg
                + ";color:"
                + accent
                + ";border-color:"
                + accent
                + '33">'
                + (kind.replace("_", " ").title() + " (" + str(cnt) + ")")
                + "</span>\n      "
            )
        if len(items) > 10:
            accent2, _ = _KIND_COLORS.get(items[0][0], ("#888", "#333"))
            kind_pills += (
                '<span class="pill" style="background:#1e293b;color:'
                + accent2
                + '">'
                + "+"
                + str(len(items) - 10)
                + " more"
                + "</span>\n      "
            )

        # ── summary card ────────────────────────────────────────────────────
        summary_card = '<div class="card">'
        if sev_pills or kind_pills:
            summary_card += '<div class="card-head">Summary</div>'
            summary_card += '<div class="card-body">'
            if sev_pills.strip():
                summary_card += (
                    '<div class="pill-group">'
                    '<span class="group-label">Severities</span>'
                    '<div class="pill-row">' + sev_pills.rstrip() + "</div>"
                    "</div>"
                )
            if kind_pills.strip():
                summary_card += (
                    '<div class="pill-group">'
                    '<span class="group-label">Smell Kinds</span>'
                    '<div class="pill-row">' + kind_pills.rstrip() + "</div>"
                    "</div>"
                )
            summary_card += "</div>"
        summary_card += "</div>"

        # ── table rows ──────────────────────────────────────────────────────
        rows_html = ""
        for s in smells:
            k = s.kind.value if isinstance(s.kind, SmellKind) else str(s.kind)
            accent, _dim_bg = _KIND_COLORS.get(k, ("#888", "#333"))
            fg, bg = _SEVERITY_BADGE.get(getattr(s, "severity", "warning"), ("#ffb86b", "#37230f"))
            ctx_html = (
                '<pre class="smell-context">' + escape(s.context) + "</pre>" if s.context else ""
            )
            rows_html += (
                "<tr class='smell-row'><td>"
                '<span class="sev-badge" style="background:'
                + bg
                + ";color:"
                + fg
                + '">'
                + escape(getattr(s, "severity", "warning"))
                + '</span></td><td><span class="kind-name" style="color:'
                + accent
                + '">'
                + escape(k.replace("_", " ").title())
                + '</span></td><td class="msg-cell">'
                + escape(s.message)
                + '</td><td class="loc"><code>L'
                + str(s.line)
                + "&#160;C"
                + str(s.column)
                + "</code></td>"
                + "<td class='ctx-cell'>"
                + ctx_html
                + "</td></tr>\n"
            )
        if not rows_html.strip():
            rows_html = (
                '<tr><td colspan="5" class="empty-row">No smells detected in this file.</td></tr>'
            )

        # ── danger badge ────────────────────────────────────────────────────
        if total == 0:
            d_text, d_fg, d_bg = "Clean", "#a6da95", "rgba(166,218,149,0.12)"
        elif total <= 3:
            d_text, d_fg, d_bg = "Low", "#a6da95", "rgba(166,218,149,0.12)"
        elif total <= 8:
            d_text, d_fg, d_bg = "Medium", "#ffb86b", "rgba(255,184,107,0.15)"
        elif total <= 20:
            d_text, d_fg, d_bg = "High", "#ff93a9", "rgba(255,147,169,0.14)"
        else:
            d_text, d_fg, d_bg = "Critical", "#ff79c6", "rgba(255,121,198,0.14)"

        return (
            "<!DOCTYPE html><html lang='en'><head>"
            '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>Code Smells " + location + "</title>"
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&amp;family=JetBrains+Mono:wght@400;500;700&amp;family=Inter:wght@500;600&amp;display=swap" rel="stylesheet">'
            "<style>:root{--bg:#0a0f18;--surface:#111827;--surface-2:#172131;--border:#2b3b59;"
            "--border-strong:#3f5378;--text:#cfd8f6;--text-bright:#f4f7ff;--text-dim:#6b7a96;"
            "--muted:#8e9bbb;--row-hover:rgba(130,170,255,0.06);"
            '--font-u:"Inter","IBM Plex Sans",-apple-system,"Segoe UI",system-ui,sans-serif;'
            '--font-m:"JetBrains Mono","Fira Code","SF Mono","Menlo",monospace}'
            "*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}"
            "body{font-family:var(--font-u);font-size:14px;color:var(--text);"
            "background:radial-gradient(ellipse at top,rgba(130,170,255,0.07),transparent 65%),var(--bg);"
            "min-height:100vh;padding:28px 24px;-webkit-font-smoothing:antialiased}"
            ".report{max-width:1140px;margin:0 auto}"
            ".titlebar{display:flex;align-items:baseline;gap:10px;margin-bottom:24px;flex-wrap:wrap}"
            ".titlebar h1{font-family:var(--font-m);font-size:18px;font-weight:700;color:var(--text-bright)}"
            ".titlebar .sep{color:var(--text-dim)}"
            ".titlebar .path{font-family:var(--font-m);font-size:12px;color:var(--muted);overflow-wrap:anywhere}"
            ".meta-row{display:flex;align-items:center;gap:12px;margin-bottom:22px;flex-wrap:wrap}"
            ".danger-badge{font-size:12px;font-weight:700;letter-spacing:0.09em;text-transform:uppercase;"
            "padding:6px 16px;border-radius:99px;border:1.5px solid;font-family:var(--font-m)}"
            ".total-label{font-family:var(--font-m);font-size:13px;color:var(--muted);font-weight:500}"
            ".card{background:linear-gradient(180deg,rgba(255,255,255,0.022),rgba(255,255,255,0.007)),"
            "var(--surface);border:1px solid var(--border-strong);border-radius:14px;"
            "box-shadow:0 22px 60px rgba(3,8,18,0.52);overflow:hidden;margin-bottom:22px}"
            ".card-head{padding:12px 20px;background:linear-gradient(180deg,rgba(255,255,255,0.04),"
            "rgba(255,255,255,0.01)),var(--surface-3);border-bottom:1px solid var(--border-strong);"
            "font-family:var(--font-m);font-size:11px;font-weight:600;text-transform:uppercase;"
            "letter-spacing:0.08em;color:var(--muted);display:flex;gap:8px;flex-wrap:wrap;align-items:center}"
            ".card-body{padding:16px 20px}"
            ".pill-row{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}"
            ".pill-group{margin-bottom:6px}"
            ".group-label{display:block;font-size:10px;font-weight:700;text-transform:uppercase;"
            "letter-spacing:0.08em;color:var(--text-dim);margin-bottom:7px}"
            ".pill{font-family:var(--font-m);font-size:11px;font-weight:600;padding:4px 12px;"
            "border-radius:99px;border:1px solid;white-space:nowrap}"
            ".table-wrap{overflow-x:auto}"
            "table{width:100%;border-collapse:collapse;font-size:13px}"
            "thead th{text-align:left;padding:10px 16px;background:var(--surface-2);"
            "border-bottom:1px solid var(--border-strong);font-size:10.5px;font-weight:600;color:var(--text-dim);"
            "text-transform:uppercase;letter-spacing:0.08em;position:sticky;top:0;backdrop-filter:blur(6px)}"
            "tbody td{padding:9px 16px;border-bottom:1px solid var(--border-soft);vertical-align:top}"
            "tr:last-child td{border-bottom:0}tr:hover td{background:var(--row-hover)}"
            ".sev-badge{display:inline-block;font-family:var(--font-m);font-size:10px;font-weight:700;"
            "letter-spacing:0.06em;text-transform:uppercase;padding:3px 8px;border-radius:6px;white-space:nowrap}"
            ".kind-name{font-family:var(--font-m);font-size:12px;font-weight:500}"
            ".msg-cell{font-family:var(--font-m);font-size:12.5px;line-height:1.7;color:var(--text-bright)}"
            ".loc{width:84px}"
            ".ctx-cell{width:240px}"
            ".smell-context{font-family:var(--font-m);font-size:10.5px;color:var(--text-dim);"
            "white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;"
            "line-height:1.6;background:rgba(0,0,0,0.2);border:1px solid var(--border-soft);"
            "border-radius:6px;padding:5px 9px;max-height:110px;overflow-y:auto}"
            ".loc code{font-family:var(--font-m);font-size:11px;color:var(--text-dim)}"
            ".empty-row{text-align:center;font-style:italic;color:var(--text-dim);padding:22px!important}"
            "@media(max-width:740px){body{padding:16px 12px}.ctx-cell{display:none}"
            "thead th:nth-child(5),tbody td:nth-child(5){display:none}}"
            "</style></head><body><div class='report'>"
            '<div class="titlebar"><h1>Code Smell Report</h1>'
            '<span class="sep">&#8227;</span>'
            '<span class="path">' + location + "</span></div>"
            '<div class="meta-row">'
            '<span class="danger-badge" style="color:'
            + d_fg
            + ";background:"
            + d_bg
            + ";border-color:"
            + d_fg
            + '55">'
            + d_text
            + "</span>"
            '<span class="total-label">'
            + str(total)
            + " smell"
            + ("" if total == 1 else "s")
            + " detected</span>"
            "</div>"
            + summary_card
            + '<div class="card"><div class="card-head">Detailed Findings</div>'
            '<div class="card-body table-wrap"><table><thead><tr>'
            "<th style='width:84px'>Severity</th>"
            "<th style='width:170px'>Smell</th>"
            "<th>Message</th>"
            "<th style='width:84px'>Location</th>"
            "<th style='width:200px'>Context</th>"
            "</tr></thead><tbody>" + rows_html.rstrip() + "</tbody></table></div></div>"
            "</div></body></html>"
        )

    def render_bundle(self, bundle: SmellBundle) -> str:
        rows = ""
        root_path = Path(bundle.root_path)
        for r in bundle.reports:
            source_path = Path(r.source_location)
            try:
                rel_path = source_path.relative_to(root_path)
            except ValueError:
                rel_path = source_path
            
            href = escape(str(rel_path)) + ".smells.html"
            cnt = r.smell_count
            cnt_style = (
                "display:inline-flex;align-items:center;justify-content:center;"
                "min-width:28px;height:28px;padding:0 8px;border-radius:8px;"
                "font-family:var(--font-m);font-size:13px;font-weight:600;"
                "background:rgba(255,184,107,0.12);color:#ffb86b;"
                if cnt > 0
                else "display:inline-flex;align-items:center;justify-content:center;"
                "min-width:28px;height:28px;padding:0 8px;border-radius:8px;"
                "font-family:var(--font-m);font-size:13px;font-weight:600;"
                "background:rgba(130,170,255,0.08);color:var(--muted);"
            )
            cnt_str = str(cnt) if cnt > 0 else "0"
            rows += (
                "<tr>"
                '<td><a href="'
                + href
                + '" class="file-link">'
                + escape(str(rel_path))
                + "</a></td>"
                '<td style="text-align:center"><span style="'
                + cnt_style
                + '">'
                + cnt_str
                + "</span></td></tr>\n"
            )
        if not rows:
            rows = '<tr><td colspan="2" class="empty-row">No smells found.</td></tr>'

        total = bundle.total_smell_count
        root = escape(bundle.root_path)

        return (
            "<!DOCTYPE html><html lang='en'><head>"
            '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>Smell Index " + root + "</title>"
            '<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&amp;family=JetBrains+Mono:wght@400;500&amp;display=swap" rel="stylesheet">'
            "<style>:root{--bg:#0a0f18;--surface:#111827;--surface-2:#172131;"
            "--border:#2b3b59;--border-strong:#3f5378;"
            "--text:#cfd8f6;--text-bright:#f4f7ff;--text-dim:#6b7a96;--blue:#82aaff;"
            '--font-u:"Inter","IBM Plex Sans",-apple-system,"Segoe UI",system-ui,sans-serif;'
            '--font-m:"JetBrains Mono","Fira Code","SF Mono","Menlo",monospace}'
            "*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}"
            "body{font-family:var(--font-u);font-size:14px;color:var(--text);"
            "background:radial-gradient(ellipse at top,rgba(130,170,255,0.07),transparent 65%),var(--bg);"
            "min-height:100vh;padding:32px 28px;-webkit-font-smoothing:antialiased}"
            ".report{max-width:900px;margin:0 auto}"
            ".titlebar{display:flex;align-items:baseline;gap:10px;margin-bottom:24px}"
            ".titlebar h1{font-family:var(--font-m);font-size:18px;font-weight:700;color:var(--text-bright)}"
            "h2{font-size:13px;color:var(--muted);font-weight:500;font-family:var(--font-m);margin-bottom:20px}"
            ".card{background:linear-gradient(180deg,rgba(255,255,255,0.022),rgba(255,255,255,0.007)),var(--surface);"
            "border:1px solid var(--border-strong);border-radius:14px;"
            "box-shadow:0 20px 56px rgba(3,8,18,0.5);overflow:hidden}"
            ".card-head{padding:12px 20px;background:var(--surface-3);"
            "border-bottom:1px solid var(--border-strong);"
            "font-family:var(--font-m);font-size:11px;color:var(--text-dim);"
            "text-transform:uppercase;letter-spacing:0.06em}"
            "table{width:100%;border-collapse:collapse;font-size:13px}"
            "thead th{text-align:left;padding:11px 18px;background:var(--surface-2);"
            "border-bottom:1px solid var(--border-strong);font-size:10.5px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em}"
            "tbody td{padding:10px 18px;border-bottom:1px solid var(--border-soft);vertical-align:top}"
            "tr:last-child td{border-bottom:0}tr:hover td{background:rgba(130,170,255,0.05)}"
            "a.file-link{font-family:var(--font-m);font-size:12px;font-weight:500;color:var(--blue);text-decoration:none}"
            ".file-link:hover{text-decoration:underline}"
            ".empty-row{text-align:center;font-style:italic;color:var(--text-dim);padding:22px!important}"
            "@media(max-width:640px){body{padding:18px 14px}}"
            "</style></head><body><div class='report'>"
            '<div class="titlebar"><h1>Directory Smell Index</h1></div>'
            "<h2>" + root + "</h2>"
            '<div class="card"><div class="card-head">'
            + str(len(bundle.reports))
            + " file(s) scanned</div>"
            '<div class="card-body" style="padding:0">'
            "<table><thead><tr>"
            "<th>Source File</th><th style='width:120px;text-align:center'>Smells</th></tr></thead><tbody>"
            + rows
            + "</tbody></table></div></div>"
            "</div></body></html>"
        )
