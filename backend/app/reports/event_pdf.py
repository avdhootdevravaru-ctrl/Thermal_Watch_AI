"""Professional event report generation from the current event record."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


BRAND = colors.HexColor("#E95016")
NAVY = colors.HexColor("#102736")
MUTED = colors.HexColor("#526773")
LIGHT = colors.HexColor("#EEF3F5")
LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "thermal-watch-logo.png"


def _value(value: Any, *, suffix: str = "") -> str:
    if value is None or value == "":
        return "Not available"
    if isinstance(value, float):
        return f"{value:.3f}{suffix}"
    return f"{value}{suffix}"


def _iso(value: Any) -> str:
    if value is None:
        return "Not available"
    if hasattr(value, "astimezone"):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    except (TypeError, ValueError):
        return str(value)


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(text, style)


def _section(title: str, rows: list[tuple[str, Any]], styles: dict[str, ParagraphStyle]) -> list[Any]:
    data = [[_paragraph(label, styles["label"]), _paragraph(_value(value), styles["body"])] for label, value in rows]
    table = Table(data, colWidths=[58 * mm, 196 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C8D4D9")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [KeepTogether([Paragraph(title, styles["section"]), Spacer(1, 2 * mm), table]), Spacer(1, 5 * mm)]


def render_event_pdf(context: dict[str, Any]) -> bytes:
    """Render a PDF from actual event, evidence, model, and validation data."""
    event = context["event"]
    persistence = event["persistence"]
    classification = event["classification"]
    risk = event["risk"]
    evidence = context["evidence"]
    integrity = context["integrity"]
    weak = context.get("weak") or {}
    validation = context.get("validation") or {}
    observations = event["observations"]

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=22,
                                leading=25, textColor=NAVY, alignment=TA_LEFT, spaceAfter=2),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontSize=9, leading=12, textColor=MUTED),
        "section": ParagraphStyle("Section", parent=base["Heading2"], fontName="Helvetica-Bold",
                                  fontSize=12, leading=15, textColor=BRAND, spaceBefore=3),
        "label": ParagraphStyle("Label", parent=base["Normal"], fontName="Helvetica-Bold",
                                fontSize=8, leading=10, textColor=NAVY),
        "body": ParagraphStyle("Body", parent=base["Normal"], fontSize=8, leading=10, textColor=NAVY),
        "small": ParagraphStyle("Small", parent=base["Normal"], fontSize=7, leading=9, textColor=MUTED),
        "warning": ParagraphStyle("Warning", parent=base["Normal"], fontSize=8, leading=11,
                                  textColor=colors.HexColor("#7A3C00"), backColor=colors.HexColor("#FFF3E8"),
                                  borderColor=colors.HexColor("#F2B37C"), borderWidth=.5, borderPadding=7),
    }

    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=16 * mm, leftMargin=16 * mm,
                            topMargin=18 * mm, bottomMargin=16 * mm,
                            title=f"Thermal Watch.AI Event {event['id']} Report",
                            author="Thermal Watch.AI")

    def page(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CAD6DB"))
        canvas.line(16 * mm, 12 * mm, 281 * mm, 12 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 7.5 * mm, "Thermal Watch.AI - Satellite thermal event intelligence")
        canvas.drawRightString(281 * mm, 7.5 * mm, f"Page {document.page}")
        canvas.restoreState()

    story: list[Any] = []
    header = Table([
        [Image(str(LOGO_PATH), width=9.4 * mm, height=16 * mm),
         Paragraph("THERMAL WATCH.AI", styles["title"]),
         Paragraph(f"EVENT REPORT<br/><b>#{event['id']}</b>", styles["subtitle"])],
    ], colWidths=[14 * mm, 205 * mm, 36 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 0), (2, 0), "RIGHT")]))
    story.extend([header, Spacer(1, 2 * mm),
                  Paragraph("Generated from the selected event's current FIRMS observations, model outputs, risk assessment, and evidence record.", styles["subtitle"]),
                  Spacer(1, 5 * mm)])

    story.extend(_section("Event overview", [
        ("Event ID", event["id"]), ("Status", event.get("status")),
        ("Location", event.get("place")),
        ("Coordinates", f"{event['latitude']:.6f}, {event['longitude']:.6f}"),
        ("First observation", _iso(event.get("start_time"))),
        ("Last observation", _iso(event.get("end_time"))),
        ("Data mode", event.get("data_mode")),
        ("Geographic scope", "India-only Natural Earth polygon filter active"),
    ], styles))

    sources = sorted({getattr(o, "source", None) for o in observations if getattr(o, "source", None)})
    satellites = sorted({getattr(o, "satellite", None) or getattr(o, "sensor", None)
                         for o in observations if getattr(o, "satellite", None) or getattr(o, "sensor", None)})
    confidence_categories = sorted({getattr(o, "confidence_category", None)
                                    for o in observations if getattr(o, "confidence_category", None)})
    story.extend(_section("NASA FIRMS observations", [
        ("Source product", ", ".join(sources) or None),
        ("Satellite / platform", ", ".join(satellites) or None),
        ("Observation count", len(observations)),
        ("Active days", persistence.get("active_days")),
        ("Temporal span", f"{classification.get('features', {}).get('duration_hours', 'Not available')} hours"),
        ("Mean brightness", _value(persistence.get("average_intensity"), suffix=" K")),
        ("Peak brightness", _value(classification.get("features", {}).get("max_intensity"), suffix=" K")),
        ("Mean FRP", _value(classification.get("features", {}).get("mean_frp"), suffix=" MW")),
        ("Peak FRP", _value(classification.get("features", {}).get("max_frp"), suffix=" MW")),
        ("FIRMS confidence", ", ".join(confidence_categories) or "Not available"),
        ("Persistence score", persistence.get("persistence_score")),
        ("Trend", persistence.get("trend")),
    ], styles))

    story.extend(_section("Model and risk intelligence", [
        ("ML classification", str(classification.get("classification", "Not available")).replace("_", " ").title()),
        ("Model status", str(classification.get("model_status", "Not available")).replace("_", " ")),
        ("Model version", classification.get("model_version")),
        ("Anomaly decision score", classification.get("anomaly_score")),
        ("Methodology", classification.get("methodology")),
        ("Operational risk score", risk.get("score")),
        ("Operational risk category", risk.get("severity")),
        ("Risk explanation", risk.get("explanation")),
        ("Recurrence classifier", str(weak.get("prediction", "Not available")).replace("_", " ").title()),
        ("Recurrence model", weak.get("model_version")),
    ], styles))

    local_chain = integrity.get("local_chain", {})
    blockchain = integrity.get("blockchain", {})
    story.extend(_section("Evidence and verification", [
        ("Evidence ID", evidence.get("evidence_id")),
        ("Evidence SHA-256", evidence.get("sha256")),
        ("Generated at", _iso(evidence.get("generated_at"))),
        ("Content hash", "Verified" if integrity.get("content_hash_valid") else "Verification failed"),
        ("Local receipt", "Verified" if integrity.get("local_anchor_valid") else "Not anchored locally"),
        ("Local chain", f"{'Valid' if local_chain.get('valid') else 'Invalid'}; {local_chain.get('receipt_count', 0)} receipts"),
        ("Blockchain status", blockchain.get("status")),
        ("On-chain anchor", "Verified" if integrity.get("on_chain") else "Not available"),
        ("Blockchain network", blockchain.get("network")),
        ("Transaction hash", blockchain.get("tx_hash")),
    ], styles))

    story.extend(_section("Data validation", [
        ("Records received", validation.get("records_received")),
        ("Records accepted in India", validation.get("records_accepted")),
        ("Records rejected", validation.get("records_rejected")),
        ("Outside India", validation.get("outside_india")),
        ("Duplicates removed", validation.get("duplicates_removed")),
        ("Invalid coordinates", validation.get("invalid_coordinates")),
        ("Invalid timestamps", validation.get("invalid_timestamps")),
        ("Boundary source", context.get("boundary_source")),
    ], styles))

    story.append(PageBreak())
    story.extend([Paragraph("Observation record", styles["section"]), Spacer(1, 2 * mm)])
    obs_header = ["Timestamp (UTC)", "Latitude", "Longitude", "Brightness K", "FRP MW", "Confidence", "Satellite", "Source"]
    obs_rows = [obs_header]
    for observation in observations:
        metadata = getattr(observation, "metadata_json", {}) or {}
        confidence = getattr(observation, "confidence_category", None)
        if not confidence:
            confidence = getattr(observation, "confidence", None)
        obs_rows.append([
            _iso(getattr(observation, "timestamp", None)),
            _value(getattr(observation, "latitude", None)), _value(getattr(observation, "longitude", None)),
            _value(getattr(observation, "intensity", None)), _value(getattr(observation, "frp", None) or metadata.get("frp")),
            _value(confidence), _value(getattr(observation, "satellite", None) or metadata.get("raw_satellite") or getattr(observation, "sensor", None)),
            _value(getattr(observation, "source", None)),
        ])
    obs_table = Table(obs_rows, repeatRows=1, colWidths=[38 * mm, 23 * mm, 23 * mm, 27 * mm, 21 * mm, 27 * mm, 31 * mm, 65 * mm])
    obs_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 6.7),
        ("LEADING", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#C8D4D9")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([obs_table, Spacer(1, 5 * mm), Paragraph(
        "Interpretation notice: NASA FIRMS records satellite thermal detections. An anomaly score ranks unusual patterns within the captured data, and the risk score prioritizes investigation. Neither result confirms a fire, its cause, or future escalation.",
        styles["warning"]), Spacer(1, 3 * mm), Paragraph(
        f"Report generated {_iso(context['generated_at'])}. Unavailable fields are shown explicitly and no values are fabricated.",
        styles["small"]),
    ])
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return output.getvalue()
