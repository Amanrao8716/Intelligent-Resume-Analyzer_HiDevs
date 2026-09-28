"""
reporter.py — Multi-format report generator: plain text, JSON summary, HTML.
"""

from __future__ import annotations
import json
from typing import List
from datetime import datetime

from .models import Candidate, MatchResult, AnalyticsReport


class ReportGenerator:
    """
    Generates hiring reports in three formats:
      - Plain text (.txt) — for terminals and email
      - JSON summary (.json) — for downstream tools
      - HTML report (.html) — for browser viewing / sharing
    """

    # ──────────────────────────────────────────────────
    #  PLAIN TEXT
    # ──────────────────────────────────────────────────

    def candidate_report_text(
        self, candidate: Candidate, results: List[MatchResult]
    ) -> str:
        W = 64
        div  = "═" * W
        thin = "─" * W
        lines = [
            div,
            "  CANDIDATE ANALYSIS REPORT".center(W),
            f"  {datetime.now().strftime('%B %d, %Y  %H:%M')}".center(W),
            div, "",
            "  CANDIDATE PROFILE",
            thin,
            f"  Name         : {candidate.name}",
            f"  Email        : {candidate.email or '—'}",
            f"  Phone        : {candidate.phone or '—'}",
            f"  LinkedIn     : {candidate.linkedin or '—'}",
            f"  GitHub       : {candidate.github or '—'}",
            f"  Location     : {candidate.location or '—'}",
            f"  Experience   : {candidate.experience_years:.1f} year(s)",
            f"  Education    : {candidate.education.label()}"
            + (f" in {candidate.education_field}" if candidate.education_field else ""),
            f"  Skill Count  : {candidate.skill_count}",
            f"  Parse Conf.  : {candidate.parse_confidence*100:.0f}%",
        ]

        if candidate.skills:
            skill_lines = self._wrap_list(candidate.skills, prefix="  ", width=W)
            lines += ["  Skills       :"] + skill_lines

        if candidate.certifications:
            lines.append(f"  Certs        : {', '.join(candidate.certifications)}")

        if candidate.work_history:
            lines += ["", "  WORK HISTORY", thin]
            for job in candidate.work_history[:4]:
                end = str(job.end_year) if job.end_year else "Present"
                lines.append(f"  {job.start_year}–{end}  {job.title} @ {job.company}")

        if candidate.summary:
            lines += ["", "  SUMMARY", thin]
            lines += self._wrap_text(candidate.summary, width=W, prefix="  ")

        lines += [""]

        for result in results:
            lines += [
                f"  JOB MATCH: {result.job_title}",
                thin,
                f"  Overall Score    : {result.overall_score:.1f} / 100",
                f"  {self._score_bar(result.overall_score)}",
                "",
                f"  ├─ Skills        : {result.breakdown.skills_total:.1f}",
                f"  │    Required     : {result.breakdown.skills_required_score:.1f}",
                f"  │    Preferred    : {result.breakdown.skills_preferred_score:.1f}",
                f"  │    Cert Bonus   : +{result.breakdown.certifications_bonus:.1f}",
                f"  ├─ Experience     : {result.breakdown.experience_total:.1f}",
                f"  └─ Education      : {result.breakdown.education_total:.1f}",
                "",
                f"  Matched Skills   : {', '.join(result.matched_required_skills) or 'None'}",
                f"  Preferred Matched: {', '.join(result.matched_preferred_skills) or 'None'}",
                f"  Missing Skills   : {', '.join(result.missing_required_skills) or 'None'}",
                "",
            ]
            if result.strengths:
                lines.append("  STRENGTHS")
                for s in result.strengths:
                    lines.append(f"    ✓ {s}")
            if result.gaps:
                lines.append("  GAPS")
                for g in result.gaps:
                    lines.append(f"    ✗ {g}")
            lines += [
                "",
                f"  ★ {result.recommendation.emoji} RECOMMENDATION: {result.recommendation.value}",
                "",
            ]

        lines.append(div)
        return "\n".join(lines)

    def ranking_report_text(
        self, results: List[MatchResult], analytics: AnalyticsReport
    ) -> str:
        W = 64
        div  = "═" * W
        thin = "─" * W
        ranked = sorted(results, key=lambda r: r.overall_score, reverse=True)

        lines = [
            div,
            f"  CANDIDATE RANKING: {analytics.job_title}".center(W),
            f"  {datetime.now().strftime('%B %d, %Y  %H:%M')}".center(W),
            div, "",
        ]

        for rank, r in enumerate(ranked, 1):
            bar = self._mini_bar(r.overall_score)
            lines += [
                f"  #{rank:>2}  {r.candidate_name:<25} {r.overall_score:>5.1f}/100",
                f"       {bar}  {r.recommendation.emoji} {r.recommendation.value}",
                "",
            ]

        lines += [
            thin,
            "  ANALYTICS SUMMARY",
            thin,
            f"  Total evaluated      : {analytics.total_candidates}",
            f"  Recommended          : {analytics.recommended_count}",
            f"  Average score        : {analytics.avg_score:.1f}",
            f"  Top candidate        : {analytics.top_candidate}",
        ]

        if analytics.most_missing_skills:
            lines.append(
                f"  Common skill gaps    : {', '.join(analytics.most_missing_skills[:5])}"
            )

        lines += ["", "  SCORE DISTRIBUTION", thin]
        for tier, count in analytics.score_distribution.items():
            bar = "█" * count
            lines.append(f"  {tier:<10}: {bar} ({count})")

        lines += ["", div]
        return "\n".join(lines)

    # ──────────────────────────────────────────────────
    #  HTML
    # ──────────────────────────────────────────────────

    def candidate_report_html(
        self, candidate: Candidate, results: List[MatchResult]
    ) -> str:
        """Generate a self-contained HTML report with inline CSS."""
        skill_tags = "".join(
            f'<span class="skill-tag">{s}</span>' for s in candidate.skills
        )
        cert_tags = "".join(
            f'<span class="cert-tag">{c}</span>' for c in candidate.certifications
        ) if candidate.certifications else "<em>None</em>"

        wh_rows = ""
        for w in candidate.work_history[:5]:
            end = str(w.end_year) if w.end_year else "Present"
            wh_rows += f"""
            <tr>
              <td>{w.start_year}–{end}</td>
              <td>{w.title}</td>
              <td>{w.company}</td>
            </tr>"""

        match_cards = ""
        for r in results:
            color = self._tier_color(r.overall_score)
            matched_html = "".join(
                f'<span class="skill-tag matched">{s}</span>'
                for s in r.matched_required_skills
            )
            missing_html = "".join(
                f'<span class="skill-tag missing">{s}</span>'
                for s in r.missing_required_skills
            ) or "<em>None</em>"

            strengths_html = "".join(f"<li>✓ {s}</li>" for s in r.strengths)
            gaps_html = "".join(f"<li>✗ {g}</li>" for g in r.gaps)

            match_cards += f"""
            <div class="match-card">
              <div class="match-header">
                <h3>{r.job_title}</h3>
                <div class="score-badge" style="background:{color}">
                  {r.overall_score:.1f}
                </div>
              </div>
              <div class="score-bars">
                {self._html_bar('Skills', r.breakdown.skills_total, color)}
                {self._html_bar('Experience', r.breakdown.experience_total, color)}
                {self._html_bar('Education', r.breakdown.education_total, color)}
              </div>
              <div class="skill-section">
                <strong>Matched:</strong><br>{matched_html}
              </div>
              <div class="skill-section">
                <strong>Missing:</strong><br>{missing_html}
              </div>
              <div class="two-col">
                <div><strong>Strengths</strong><ul>{strengths_html}</ul></div>
                <div><strong>Gaps</strong><ul>{gaps_html}</ul></div>
              </div>
              <div class="recommendation" style="border-left: 4px solid {color}">
                {r.recommendation.emoji} {r.recommendation.value}
              </div>
            </div>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Resume Report — {candidate.name}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: #0f172a; color: #e2e8f0;
      line-height: 1.6; padding: 2rem;
    }}
    h1 {{ color: #38bdf8; font-size: 1.8rem; }}
    h2 {{ color: #94a3b8; font-size: 1rem; font-weight: 500; margin-bottom: 1.5rem; }}
    h3 {{ color: #f1f5f9; }}
    .container {{ max-width: 900px; margin: 0 auto; }}
    .header {{
      background: #1e293b; border-radius: 12px; padding: 2rem;
      margin-bottom: 1.5rem; border: 1px solid #334155;
    }}
    .meta-grid {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 0.75rem; margin-top: 1.25rem;
    }}
    .meta-item {{ background: #0f172a; border-radius: 8px; padding: 0.6rem 1rem; }}
    .meta-label {{ color: #64748b; font-size: 0.75rem; text-transform: uppercase; }}
    .meta-value {{ color: #f1f5f9; font-size: 0.95rem; }}
    .skills-container {{ margin-top: 1.25rem; }}
    .skill-tag {{
      display: inline-block; background: #1e3a5f; color: #7dd3fc;
      border-radius: 4px; padding: 0.2rem 0.6rem; font-size: 0.8rem;
      margin: 0.2rem; border: 1px solid #2563eb33;
    }}
    .skill-tag.matched {{ background: #14532d; color: #86efac; border-color: #16a34a33; }}
    .skill-tag.missing {{ background: #450a0a; color: #fca5a5; border-color: #dc262633; }}
    .cert-tag {{
      display: inline-block; background: #312e81; color: #a5b4fc;
      border-radius: 4px; padding: 0.2rem 0.6rem; font-size: 0.8rem; margin: 0.2rem;
    }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 0.75rem; }}
    th, td {{ padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid #1e293b; }}
    th {{ color: #64748b; font-size: 0.75rem; text-transform: uppercase; }}
    .match-card {{
      background: #1e293b; border-radius: 12px; padding: 1.5rem;
      margin-bottom: 1.25rem; border: 1px solid #334155;
    }}
    .match-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
    .score-badge {{
      font-size: 1.5rem; font-weight: 800; padding: 0.3rem 0.8rem;
      border-radius: 8px; color: #fff;
    }}
    .bar-row {{ margin: 0.4rem 0; }}
    .bar-label {{ color: #94a3b8; font-size: 0.8rem; margin-bottom: 0.2rem; }}
    .bar-track {{
      height: 8px; background: #0f172a; border-radius: 4px; overflow: hidden;
    }}
    .bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s; }}
    .score-bars {{ margin-bottom: 1rem; }}
    .skill-section {{ margin: 0.75rem 0; }}
    .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 1rem 0; }}
    .two-col ul {{ padding-left: 1rem; color: #94a3b8; font-size: 0.9rem; }}
    .recommendation {{
      margin-top: 1rem; padding: 0.75rem 1rem;
      background: #0f172a; border-radius: 6px;
      font-weight: 600; font-size: 0.95rem;
    }}
    .section-title {{
      color: #38bdf8; font-size: 1.1rem; font-weight: 600;
      margin: 1.5rem 0 0.75rem; padding-bottom: 0.4rem;
      border-bottom: 1px solid #1e293b;
    }}
    .confidence-badge {{
      display: inline-block; padding: 0.2rem 0.6rem;
      border-radius: 99px; font-size: 0.75rem; font-weight: 600;
      background: #0c4a6e; color: #38bdf8;
    }}
    footer {{ text-align: center; color: #334155; font-size: 0.75rem; margin-top: 2rem; }}
  </style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{candidate.name}</h1>
    <h2>Resume Analysis Report &nbsp;
      <span class="confidence-badge">
        Parse Confidence: {candidate.parse_confidence*100:.0f}%
      </span>
    </h2>
    <div class="meta-grid">
      <div class="meta-item">
        <div class="meta-label">Email</div>
        <div class="meta-value">{candidate.email or '—'}</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Phone</div>
        <div class="meta-value">{candidate.phone or '—'}</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Experience</div>
        <div class="meta-value">{candidate.experience_years:.1f} years</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Education</div>
        <div class="meta-value">{candidate.education.label()}</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">LinkedIn</div>
        <div class="meta-value">{candidate.linkedin or '—'}</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">GitHub</div>
        <div class="meta-value">{candidate.github or '—'}</div>
      </div>
    </div>

    <div class="skills-container">
      <div class="section-title">Skills ({candidate.skill_count})</div>
      {skill_tags or '<em>None detected</em>'}
    </div>

    <div>
      <div class="section-title">Certifications</div>
      {cert_tags}
    </div>

    {f'''
    <div>
      <div class="section-title">Work History</div>
      <table>
        <thead><tr><th>Period</th><th>Title</th><th>Company</th></tr></thead>
        <tbody>{wh_rows}</tbody>
      </table>
    </div>''' if candidate.work_history else ''}

    {f'<div><div class="section-title">Summary</div><p style="color:#94a3b8">{candidate.summary}</p></div>' if candidate.summary else ''}
  </div>

  <div class="section-title" style="font-size:1.3rem">Job Match Results</div>
  {match_cards}

  <footer>Generated by Smart Hiring Assistant v2 · {datetime.now().strftime('%Y-%m-%d %H:%M')}</footer>
</div>
</body>
</html>"""

    # ──────────────────────────────────────────────────
    #  HELPERS
    # ──────────────────────────────────────────────────

    def _score_bar(self, score: float) -> str:
        filled = int(score / 5)
        bar = "█" * filled + "░" * (20 - filled)
        return f"[{bar}] {score:.1f}%"

    def _mini_bar(self, score: float) -> str:
        filled = int(score / 10)
        return "█" * filled + "░" * (10 - filled)

    def _tier_color(self, score: float) -> str:
        if score >= 80: return "#22c55e"
        if score >= 65: return "#3b82f6"
        if score >= 50: return "#eab308"
        if score >= 35: return "#f97316"
        return "#ef4444"

    def _html_bar(self, label: str, value: float, color: str) -> str:
        return f"""
        <div class="bar-row">
          <div class="bar-label">{label}: {value:.1f}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:{value:.1f}%;background:{color}"></div>
          </div>
        </div>"""

    def _wrap_list(self, items: list, prefix: str = "", width: int = 72) -> list:
        line, lines = prefix, []
        for item in items:
            addition = item + ", "
            if len(line) + len(addition) > width:
                lines.append(line)
                line = " " * len(prefix) + addition
            else:
                line += addition
        if line.strip():
            lines.append(line.rstrip(", "))
        return lines

    def _wrap_text(self, text: str, width: int = 72, prefix: str = "") -> list:
        words, lines, current = text.split(), [], prefix
        for word in words:
            if len(current) + len(word) + 1 > width:
                lines.append(current)
                current = " " * len(prefix) + word
            else:
                current += (" " if current.strip() else "") + word
        if current.strip():
            lines.append(current)
        return lines
