"""© 2026 Vyges/TrustStix Inc.
Licensed under the Apache License, Version 2.0. See LICENSE/NOTICE.

Score the quality of a vyges-metadata.json file on completeness and
integration-readiness, so SoC orchestrators and downstream tooling can
see up front which IPs carry hidden integration cost (missing
interfaces, no verification data, absent ASIC/FPGA readiness fields).

Scoring rubric (100 points):
- Identity       (20): name, version, license, description, maturity
- Interfaces     (25): clock/reset identified, at least one bus with protocol,
                       signals declared
- Parameters     (10): parameters[] declared (any)
- Implementation (20): target[], design_type[], asic{} or fpga{} populated
- Verification   (15): test{} block with coverage or testbenches
- Provenance     (10): source.url, maintainers[], created+updated timestamps

Tiers: >=80 Good, 60–79 Medium, <60 High-risk.

Returns IpScore per IP and a SocMetadataReport aggregate. The generator
emits a markdown report (metadata-quality-report.md) so every SoC build
ships with an integration-risk snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── Scoring dimensions ──────────────────────────────────────────────────────


def _score_identity(md: Dict[str, Any]) -> Tuple[int, List[str]]:
    gaps: List[str] = []
    pts = 0
    if md.get("name"):        pts += 4
    else:                     gaps.append("name")
    if md.get("version"):     pts += 4
    else:                     gaps.append("version")
    if md.get("license"):     pts += 4
    else:                     gaps.append("license")
    if md.get("description"): pts += 4
    else:                     gaps.append("description")
    if md.get("maturity"):    pts += 4
    else:                     gaps.append("maturity")
    return pts, gaps


def _score_interfaces(md: Dict[str, Any]) -> Tuple[int, List[str]]:
    gaps: List[str] = []
    interfaces = md.get("interfaces") or []
    if not interfaces:
        return 0, ["interfaces (none declared)"]

    pts = 5  # for having any interfaces at all
    types = {i.get("type") for i in interfaces if isinstance(i, dict)}

    if "clock" in types:  pts += 5
    else:                 gaps.append("interfaces[].type=clock")
    if "reset" in types:  pts += 5
    else:                 gaps.append("interfaces[].type=reset")

    buses = [i for i in interfaces if isinstance(i, dict) and i.get("type") == "bus"]
    if buses:
        pts += 5
        if any(b.get("protocol") for b in buses):
            pts += 3
        else:
            gaps.append("interfaces[].bus.protocol")
        if any(b.get("signals") for b in buses):
            pts += 2
        else:
            gaps.append("interfaces[].bus.signals")
    else:
        gaps.append("interfaces[].type=bus")

    return pts, gaps


def _score_parameters(md: Dict[str, Any]) -> Tuple[int, List[str]]:
    params = md.get("parameters")
    if not params:
        return 0, ["parameters (none declared)"]
    pts = 6
    if any(isinstance(p, dict) and p.get("description") for p in params):
        pts += 4
    else:
        return pts, ["parameters[].description"]
    return pts, []


def _score_implementation(md: Dict[str, Any]) -> Tuple[int, List[str]]:
    gaps: List[str] = []
    pts = 0
    if md.get("target"):       pts += 5
    else:                      gaps.append("target[]")
    if md.get("design_type"):  pts += 5
    else:                      gaps.append("design_type[]")
    if md.get("asic") or md.get("fpga"):
        pts += 10
    else:
        gaps.append("asic{} or fpga{}")
    return pts, gaps


def _score_verification(md: Dict[str, Any]) -> Tuple[int, List[str]]:
    test = md.get("test")
    if not test or not isinstance(test, dict):
        return 0, ["test{}"]
    pts = 5
    gaps: List[str] = []
    if test.get("coverage"):   pts += 5
    else:                      gaps.append("test.coverage")
    if test.get("testbenches") or test.get("testbench") or test.get("bench"):
        pts += 5
    else:
        gaps.append("test.testbenches")
    return pts, gaps


def _score_provenance(md: Dict[str, Any]) -> Tuple[int, List[str]]:
    gaps: List[str] = []
    pts = 0
    src = md.get("source") or {}
    if isinstance(src, dict) and src.get("url"):  pts += 4
    else:                                         gaps.append("source.url")
    if md.get("maintainers") or md.get("owner"):  pts += 3
    else:                                         gaps.append("maintainers[]")
    if md.get("created") and md.get("updated"):   pts += 3
    else:                                         gaps.append("created/updated")
    return pts, gaps


# ── Result types ────────────────────────────────────────────────────────────


@dataclass
class IpScore:
    ip_name: str
    instance: str
    resolved: bool
    score: int = 0
    breakdown: Dict[str, int] = field(default_factory=dict)
    gaps: List[str] = field(default_factory=list)

    @property
    def tier(self) -> str:
        if not self.resolved:
            return "Unresolved"
        if self.score >= 80:
            return "Good"
        if self.score >= 60:
            return "Medium"
        return "High-risk"


@dataclass
class SocMetadataReport:
    soc_name: str
    ips: List[IpScore] = field(default_factory=list)

    @property
    def aggregate(self) -> int:
        scored = [i for i in self.ips if i.resolved]
        if not scored:
            return 0
        return sum(i.score for i in scored) // len(scored)

    @property
    def integration_risk(self) -> str:
        agg = self.aggregate
        unresolved = sum(1 for i in self.ips if not i.resolved)
        if unresolved > 0:
            return "High"
        if agg >= 80:
            return "Low"
        if agg >= 60:
            return "Medium"
        return "High"


# ── Public API ──────────────────────────────────────────────────────────────


DIMENSIONS = [
    ("identity",       _score_identity,       20),
    ("interfaces",     _score_interfaces,     25),
    ("parameters",     _score_parameters,     10),
    ("implementation", _score_implementation, 20),
    ("verification",   _score_verification,   15),
    ("provenance",     _score_provenance,     10),
]


def score_metadata(md: Optional[Dict[str, Any]]) -> Tuple[int, Dict[str, int], List[str]]:
    """Score a single metadata dict. Returns (total, breakdown, gaps)."""
    if not md:
        return 0, {}, ["metadata (unresolved)"]
    breakdown: Dict[str, int] = {}
    gaps: List[str] = []
    total = 0
    for name, fn, _max in DIMENSIONS:
        pts, g = fn(md)
        breakdown[name] = pts
        gaps.extend(f"{name}: {item}" for item in g)
        total += pts
    return total, breakdown, gaps


# ── Report rendering ────────────────────────────────────────────────────────


def render_markdown(report: SocMetadataReport) -> str:
    """Render a SocMetadataReport as a markdown file.

    Shipped alongside every SoC build as metadata-quality-report.md so
    whoever runs the generator can see integration-risk areas at a glance.
    """
    lines: List[str] = []
    lines.append(f"# Metadata Quality Report — {report.soc_name}")
    lines.append("")
    lines.append(f"**Aggregate score:** {report.aggregate}/100  ")
    lines.append(f"**Integration risk:** {report.integration_risk}")
    lines.append("")
    lines.append("Scoring: Identity 20, Interfaces 25, Parameters 10, "
                 "Implementation 20, Verification 15, Provenance 10.")
    lines.append("Tiers: ≥80 Good, 60–79 Medium, <60 High-risk.")
    lines.append("")

    lines.append("## Per-IP scores")
    lines.append("")
    lines.append("| Instance | IP | Score | Tier | Top gaps |")
    lines.append("|---|---|---|---|---|")
    for ip in sorted(report.ips, key=lambda i: i.score):
        top_gaps = "; ".join(ip.gaps[:3]) or "—"
        lines.append(f"| {ip.instance} | {ip.ip_name} | {ip.score} | {ip.tier} | {top_gaps} |")
    lines.append("")

    high_risk = [i for i in report.ips if i.tier in ("High-risk", "Unresolved")]
    if high_risk:
        lines.append("## High-risk IPs — integration challenges ahead")
        lines.append("")
        for ip in high_risk:
            lines.append(f"### {ip.instance} ({ip.ip_name}) — {ip.score}/100, {ip.tier}")
            if ip.gaps:
                for g in ip.gaps:
                    lines.append(f"- {g}")
            lines.append("")

    return "\n".join(lines) + "\n"


def write_report(report: SocMetadataReport, output_dir: Path) -> Path:
    out = output_dir / "metadata-quality-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(report))
    return out
