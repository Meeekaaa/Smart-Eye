import io
import os
from datetime import datetime

import cv2
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.analytics.heatmap_generator import generate_heatmap_from_db
from backend.analytics import stats_engine
from utils import config


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _build_hourly_chart(hourly):
    values = [_safe_int(h.get("count", 0)) for h in hourly]
    if not values:
        return None
    labels = [f"{_safe_int(h.get('hour', 0)):02d}" for h in hourly]
    drawing = Drawing(520, 240)
    drawing.add(String(12, 220, "Hourly Violations Diagram", fontSize=12, fillColor=colors.HexColor("#333333")))
    chart = VerticalBarChart()
    chart.x = 36
    chart.y = 34
    chart.height = 170
    chart.width = 460
    chart.data = [values]
    chart.strokeColor = colors.HexColor("#D0D0D0")
    chart.valueAxis.valueMin = 0
    value_max = max(values) if max(values) > 0 else 1
    chart.valueAxis.valueMax = max(5, int(round(value_max * 1.15)))
    chart.valueAxis.valueStep = max(1, chart.valueAxis.valueMax // 5)
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.angle = 45
    chart.categoryAxis.labels.dy = -14
    chart.bars[0].fillColor = colors.HexColor("#EA4335")
    drawing.add(chart)
    return drawing


def _build_compliance_chart(trend):
    rates = [float(t.get("rate", 0.0) or 0.0) for t in trend]
    if not rates:
        return None
    labels = [str(t.get("date", ""))[-5:] for t in trend]
    drawing = Drawing(520, 240)
    drawing.add(String(12, 220, "Compliance Trend Diagram", fontSize=12, fillColor=colors.HexColor("#333333")))
    chart = HorizontalLineChart()
    chart.x = 36
    chart.y = 36
    chart.height = 168
    chart.width = 460
    chart.data = [rates]
    chart.lines[0].strokeWidth = 2
    chart.lines[0].strokeColor = colors.HexColor("#34A853")
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.angle = 35
    chart.categoryAxis.labels.dy = -14
    min_rate = min(rates)
    max_rate = max(rates)
    chart.valueAxis.valueMin = max(0, int(min_rate - 6))
    chart.valueAxis.valueMax = min(100, int(max_rate + 6)) if max_rate < 100 else 100
    if chart.valueAxis.valueMax <= chart.valueAxis.valueMin:
        chart.valueAxis.valueMax = chart.valueAxis.valueMin + 5
    chart.valueAxis.valueStep = max(1, (chart.valueAxis.valueMax - chart.valueAxis.valueMin) // 5)
    drawing.add(chart)
    return drawing


def _build_camera_chart(cam_data):
    values = [_safe_int(c.get("count", 0)) for c in cam_data]
    if not values:
        return None
    labels = [str(c.get("camera_name") or "Camera")[:14] for c in cam_data]
    drawing = Drawing(520, 240)
    drawing.add(String(12, 220, "Camera Activity Diagram", fontSize=12, fillColor=colors.HexColor("#333333")))
    chart = VerticalBarChart()
    chart.x = 36
    chart.y = 34
    chart.height = 170
    chart.width = 460
    chart.data = [values]
    chart.strokeColor = colors.HexColor("#D0D0D0")
    chart.valueAxis.valueMin = 0
    value_max = max(values) if max(values) > 0 else 1
    chart.valueAxis.valueMax = max(5, int(round(value_max * 1.10)))
    chart.valueAxis.valueStep = max(1, chart.valueAxis.valueMax // 5)
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.angle = 20
    chart.categoryAxis.labels.dy = -10
    chart.bars[0].fillColor = colors.HexColor("#1A73E8")
    drawing.add(chart)
    return drawing


def _build_gender_pie(by_gender):
    labels = []
    values = []
    for row in by_gender:
        labels.append(str(row.get("gender") or "unknown").title())
        values.append(_safe_int(row.get("count", 0)))
    if not values or sum(values) <= 0:
        return None
    drawing = Drawing(520, 230)
    drawing.add(String(12, 212, "Violations By Gender Diagram", fontSize=12, fillColor=colors.HexColor("#333333")))
    chart = Pie()
    chart.x = 140
    chart.y = 16
    chart.width = 200
    chart.height = 170
    chart.data = values
    chart.labels = labels
    chart.sideLabels = True
    palette = [
        colors.HexColor("#4285F4"),
        colors.HexColor("#EA4335"),
        colors.HexColor("#FBBC05"),
        colors.HexColor("#34A853"),
    ]
    for idx in range(min(len(values), len(palette))):
        chart.slices[idx].fillColor = palette[idx]
    drawing.add(chart)
    return drawing


def _build_heatmap_image(camera_id, date_from=None, date_to=None, rule_name=None, min_alarm_level=None, gender=None):
    heatmap = generate_heatmap_from_db(
        camera_id=camera_id,
        date_from=date_from,
        date_to=date_to,
        rule_name=rule_name,
        min_alarm_level=min_alarm_level,
        gender=gender,
    )
    if heatmap is None:
        return None
    ok, buff = cv2.imencode(".png", heatmap)
    if not ok:
        return None
    data = io.BytesIO(buff.tobytes())
    image = Image(data, width=5.7 * inch, height=3.2 * inch)
    image.hAlign = "CENTER"
    return image


def generate_report(
    filepath, date_from=None, date_to=None, camera_id=None, rule_name=None, min_alarm_level=None, time_basis=None, gender=None
):
    doc = SimpleDocTemplate(filepath, pagesize=A4, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=24, textColor=colors.HexColor("#1a73e8"), spaceAfter=20)
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=12, textColor=colors.grey, spaceAfter=10)
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontSize=16, textColor=colors.HexColor("#333333"), spaceBefore=20, spaceAfter=10
    )
    elements = []
    logo_path = config.get("report_logo_path", "")
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image(logo_path, width=2 * inch, height=1 * inch)
            logo.hAlign = "CENTER"
            elements.append(logo)
            elements.append(Spacer(1, 10))
        except Exception:
            pass
    elements.append(Paragraph("SmartEye Analytics Report", title_style))
    date_range = ""
    if date_from and date_to:
        date_range = f"Period: {date_from} to {date_to}"
    elif date_from:
        date_range = f"From: {date_from}"
    elif date_to:
        date_range = f"Until: {date_to}"
    else:
        date_range = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    elements.append(Paragraph(date_range, subtitle_style))
    filters = []
    if time_basis:
        filters.append(f"Time basis: {time_basis}")
    if rule_name:
        filters.append(f"Rule: {rule_name}")
    if min_alarm_level is not None:
        filters.append(f"Min alarm level: {min_alarm_level}")
    if gender:
        filters.append(f"Gender: {str(gender).title()}")
    if filters:
        elements.append(Paragraph(" | ".join(filters), subtitle_style))
    if stats_engine.is_dummy_analytics_enabled():
        elements.append(Paragraph("Report mode: Synthetic debug analytics data is enabled.", subtitle_style))
    elements.append(Spacer(1, 20))

    summary = stats_engine.get_summary(
        date_from,
        date_to,
        camera_id,
        rule_name=rule_name,
        min_alarm_level=min_alarm_level,
        gender=gender,
    )
    elements.append(Paragraph("Summary", section_style))
    summary_data = [
        ["Metric", "Value"],
        ["Total Detections", str(summary["total_detections"])],
        ["Violations", str(summary["violations"])],
        ["Compliant", str(summary["compliant"])],
        ["Compliance Rate", f"{summary['compliance_rate']}%"],
    ]
    summary_table = Table(summary_data, colWidths=[3 * inch, 3 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a73e8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(summary_table)

    trend = stats_engine.get_compliance_trend(
        rule_name=rule_name,
        date_from=date_from,
        date_to=date_to,
        camera_id=camera_id,
        time_basis=time_basis,
        gender=gender,
        min_alarm_level=min_alarm_level,
    )
    elements.append(Spacer(1, 16))
    elements.append(Paragraph("Compliance Trend", section_style))
    compliance_chart = _build_compliance_chart(trend)
    if compliance_chart is not None:
        elements.append(compliance_chart)
    else:
        elements.append(Paragraph("No compliance trend data available for charting.", styles["Normal"]))

    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Hourly Violation Distribution", section_style))
    hourly = stats_engine.get_hourly_violation_chart(
        date_from,
        date_to,
        camera_id=camera_id,
        rule_name=rule_name,
        min_alarm_level=min_alarm_level,
        time_basis=time_basis,
        gender=gender,
    )
    hourly_chart = _build_hourly_chart(hourly)
    if hourly_chart is not None:
        elements.append(hourly_chart)
        elements.append(Spacer(1, 8))
    hourly_data = [["Hour", "Violations"]]
    for h in hourly:
        hourly_data.append([h["hour"] + ":00", str(h["count"])])
    hourly_table = Table(hourly_data, colWidths=[2 * inch, 2 * inch])
    hourly_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34a853")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ]
        )
    )
    elements.append(hourly_table)

    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Camera Activity", section_style))
    cam_data = stats_engine.get_camera_activity_data(
        date_from,
        date_to,
        camera_id=camera_id,
        rule_name=rule_name,
        min_alarm_level=min_alarm_level,
        gender=gender,
    )
    camera_chart = _build_camera_chart(cam_data)
    if camera_chart is not None:
        elements.append(camera_chart)
    camera_data = [["Camera", "Events"]]
    for row in cam_data:
        camera_data.append([str(row.get("camera_name") or "Unknown"), str(_safe_int(row.get("count", 0)))])
    if len(camera_data) > 1:
        camera_table = Table(camera_data, colWidths=[3.2 * inch, 2.8 * inch])
        camera_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a73e8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ]
            )
        )
        elements.append(camera_table)

    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Top Violators", section_style))
    persons = stats_engine.get_person_violations(
        date_from, date_to, camera_id=camera_id, rule_name=rule_name, min_alarm_level=min_alarm_level, gender=gender
    )
    person_data = [["Person", "Gender", "Violations"]]
    for p in persons:
        person_data.append([p["identity"], (p.get("gender") or "unknown").title(), str(p["count"])])
    if len(person_data) > 1:
        person_table = Table(person_data, colWidths=[2.8 * inch, 1.2 * inch, 1.0 * inch])
        person_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ea4335")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ]
            )
        )
        elements.append(person_table)
    else:
        elements.append(Paragraph("No violations recorded in this period.", styles["Normal"]))

    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Violations by Gender", section_style))
    by_gender = stats_engine.get_gender_violations(
        date_from=date_from,
        date_to=date_to,
        camera_id=camera_id,
        rule_name=rule_name,
        min_alarm_level=min_alarm_level,
        gender=gender,
    )
    gender_chart = _build_gender_pie(by_gender)
    if gender_chart is not None:
        elements.append(gender_chart)
        elements.append(Spacer(1, 8))
    gender_data = [["Gender", "Violations"]]
    for row in by_gender:
        gender_data.append([(row.get("gender") or "unknown").title(), str(row.get("count", 0))])
    gender_table = Table(gender_data, colWidths=[2.5 * inch, 2.5 * inch])
    gender_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4285f4")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ]
        )
    )
    elements.append(gender_table)

    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Heatmap Snapshot", section_style))
    selected_heatmap_camera = camera_id
    if selected_heatmap_camera is None and cam_data:
        selected_heatmap_camera = cam_data[0].get("camera_id")
    heatmap_image = _build_heatmap_image(
        camera_id=selected_heatmap_camera,
        date_from=date_from,
        date_to=date_to,
        rule_name=rule_name,
        min_alarm_level=min_alarm_level,
        gender=gender,
    )
    if heatmap_image is not None:
        elements.append(heatmap_image)
    else:
        elements.append(Paragraph("No heatmap image is available for the selected filters.", styles["Normal"]))

    elements.append(Spacer(1, 18))
    elements.append(Paragraph("Report Methodology", section_style))
    notes = [
        "All tables and charts use the same date, camera, rule, severity, and gender filters shown at the top of the report.",
        "Liveness verification failures are treated as identity checks and are excluded from detection logs and violation counts.",
        "The severity filter applies to violation counts. Total detections remain the denominator for compliance calculations.",
        f"Report generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    elements.append(Paragraph("<br/>".join(notes), styles["Normal"]))

    doc.build(elements)
    return filepath
