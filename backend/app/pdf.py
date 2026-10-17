from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from xml.sax.saxutils import escape


def build_report(meeting):
    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=letter, rightMargin=0.7*inch, leftMargin=0.7*inch, topMargin=0.7*inch, bottomMargin=0.7*inch)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="SmallMeta", parent=styles["BodyText"], textColor=colors.HexColor("#64736f"), fontSize=9, leading=13))
    story = [Paragraph(escape(meeting.title), styles["Title"]), Paragraph(f"Meeting date: {escape(str(meeting.meeting_date or 'Not specified'))}", styles["SmallMeta"]), Spacer(1, 16), Paragraph("Summary", styles["Heading2"]), Paragraph(escape(meeting.summary).replace("\n", "<br/>"), styles["BodyText"]), Spacer(1, 12)]
    for title, entries in (("Key discussion points", meeting.key_points or []), ("Decisions", [x.get("decision", "") if isinstance(x, dict) else str(x) for x in meeting.decisions or []]), ("Unresolved questions", meeting.unresolved_questions or [])):
        if entries:
            story.append(Paragraph(title, styles["Heading2"]))
            story.extend(Paragraph("• " + escape(str(item)), styles["BodyText"]) for item in entries)
            story.append(Spacer(1, 9))
    story.append(Paragraph("Action items", styles["Heading2"]))
    rows = [[Paragraph("Task", styles["Heading4"]), Paragraph("Owner", styles["Heading4"]), Paragraph("Deadline", styles["Heading4"]), Paragraph("Status", styles["Heading4"])]]
    rows.extend([[Paragraph(escape(a.task), styles["BodyText"]), Paragraph(escape(a.owner or "Unassigned"), styles["BodyText"]), Paragraph(escape(str(a.deadline or "—")), styles["BodyText"]), Paragraph(escape(a.status.replace("_", " ").title()), styles["BodyText"])] for a in meeting.action_items])
    if len(rows) == 1:
        rows.append([Paragraph("No action items", styles["BodyText"]), "", "", ""])
    table = Table(rows, colWidths=[3.45*inch, 1.25*inch, 1.05*inch, 1.1*inch], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e9efeb")), ("TEXTCOLOR", (0,0), (-1,0), colors.HexColor("#283a34")), ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#d8e0dc")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7), ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7)]))
    story.append(table)
    doc.build(story)
    return stream.getvalue()
