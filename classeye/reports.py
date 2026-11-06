"""Excel reports: attendance sheet, per-class register (running %), exam incident report."""
import os
import re
import time
from collections import Counter, defaultdict

import cv2
import numpy as np
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

NAVY = PatternFill("solid", fgColor="1E2A4A")
OK = PatternFill("solid", fgColor="D9F2E3")
BAD = PatternFill("solid", fgColor="FBE0E0")
WARN = PatternFill("solid", fgColor="FFF1CC")
WHITE = Font(bold=True, color="FFFFFF")
BOLD = Font(bold=True)
EDGE = Side(style="thin", color="C8CED8")
BOX = Border(left=EDGE, right=EDGE, top=EDGE, bottom=EDGE)
MID = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)


def _safe(name):
    return re.sub(r"[^A-Za-z0-9 _-]", "", name).strip().replace(" ", "_") or "Class"


def _head(ws, row, titles, widths):
    for i, (t, w) in enumerate(zip(titles, widths), 1):
        c = ws.cell(row=row, column=i, value=t)
        c.fill, c.font, c.alignment, c.border = NAVY, WHITE, MID, BOX
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[row].height = 22


def _print_wide(ws):
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0


def _clock(t):
    return time.strftime("%I:%M:%S %p", time.localtime(t)) if t else ""


def _thumb_file(image, path, height=90):
    if image is None:
        return None
    s = height / image.shape[0]
    small = cv2.resize(image, (max(1, int(image.shape[1] * s)), height))
    ok, buf = cv2.imencode(".png", small)
    if ok:
        buf.tofile(path)
        return path
    return None


# =============================================================================
def write_attendance(scan, folder, subject="", teacher=""):
    os.makedirs(folder, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H-%M")
    cls = _safe(scan.classroom)
    path = os.path.join(folder, f"Attendance_{cls}_{stamp}.xlsx")
    s = scan.summary()

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws["A1"] = f"{scan.classroom} - Attendance"
    ws["A1"].font = Font(bold=True, size=15, color="1E2A4A")
    ws["A2"] = (f"Date: {time.strftime('%d %b %Y')}    Time: {time.strftime('%I:%M %p')}"
                + (f"    Subject: {subject}" if subject else "") + (f"    Faculty: {teacher}" if teacher else ""))
    ws["A3"] = f"Present {s['present']} / {s['total']}    Absent {s['absent']}    Attendance {s['percent']}%"
    ws["A3"].font = BOLD
    _head(ws, 5, ["Sl", "Photo", "USN", "Name", "Status", "First seen", "Seen (frames)", "Match %", "Remarks"],
          [5, 14, 15, 26, 11, 13, 13, 10, 32])

    tmp_dir = os.path.join(folder, ".tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    marks = sorted(scan.marks.values(), key=lambda m: m.usn)
    for i, m in enumerate(marks, 1):
        r = 5 + i
        present = scan.is_present(m)
        remark = ""
        if not m.enrolled:
            remark = "No usable photo in dataset"
        elif not present and m.hits:
            remark = f"Seen only {m.hits}x - please verify"
        vals = [i, "", m.usn, m.name, "Present" if present else "Absent", _clock(m.first_seen),
                m.hits, round(m.best * 100) if m.hits else "", remark]
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=j, value=v)
            c.border, c.alignment = BOX, LEFT if j in (4, 9) else MID
        ws.cell(row=r, column=5).fill = OK if present else (WARN if remark else BAD)
        if m.snapshot is not None:
            t = _thumb_file(m.snapshot, os.path.join(tmp_dir, f"{m.usn}.png"), 70)
            if t:
                img = XLImage(t)
                ws.add_image(img, f"B{r}")
                ws.row_dimensions[r].height = 56
    ws.freeze_panes = "A6"
    _print_wide(ws)

    ab = wb.create_sheet("Absentees")
    _head(ab, 1, ["Sl", "USN", "Name", "Remarks"], [5, 15, 26, 32])
    for i, m in enumerate([m for m in marks if not scan.is_present(m)], 1):
        for j, v in enumerate([i, m.usn, m.name, "No usable photo" if not m.enrolled else
                               (f"Seen {m.hits}x - verify" if m.hits else "")], 1):
            c = ab.cell(row=1 + i, column=j, value=v)
            c.border = BOX

    info = wb.create_sheet("Scan details")
    for i, (k, v) in enumerate([("Frames analysed", s["frames"]), ("Most faces in one frame", s["peak_faces"]),
                                ("Unrecognised face sightings", s["unknown"]),
                                ("Faces too small to recognise", s["too_small"]),
                                ("Students without usable photo", s["no_photo"]),
                                ("Match threshold", scan.threshold),
                                ("Recognitions needed for Present", scan.hits_needed)], 1):
        info.cell(row=i, column=1, value=k).font = BOLD
        info.cell(row=i, column=2, value=v)
    info.column_dimensions["A"].width = 34
    wb.save(path)

    for f in os.listdir(tmp_dir):
        try:
            os.remove(os.path.join(tmp_dir, f))
        except OSError:
            pass
    register = update_register(scan, folder, subject)
    return path, register


def update_register(scan, folder, subject=""):
    """One workbook per class: a column per session (P/A) and each student's running %."""
    path = os.path.join(folder, f"Register_{_safe(scan.classroom)}.xlsx")
    title = time.strftime("%d-%b %I:%M%p") + (f"\n{subject}" if subject else "")
    if os.path.exists(path):
        wb = load_workbook(path)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Register"
        _head(ws, 1, ["USN", "Name", "Classes held", "Attended", "Attendance %"], [15, 26, 12, 10, 13])
    col = max(ws.max_column + 1, 6)
    c = ws.cell(row=1, column=col, value=title)
    c.fill, c.font, c.alignment, c.border = NAVY, WHITE, MID, BOX
    ws.column_dimensions[get_column_letter(col)].width = 13
    ws.row_dimensions[1].height = 32
    rows = {str(ws.cell(row=r, column=1).value).upper(): r
            for r in range(2, ws.max_row + 1) if ws.cell(row=r, column=1).value}
    for m in sorted(scan.marks.values(), key=lambda m: m.usn):
        r = rows.get(m.usn.upper())
        if r is None:
            r = ws.max_row + 1
            ws.cell(row=r, column=1, value=m.usn)
            ws.cell(row=r, column=2, value=m.name)
            rows[m.usn.upper()] = r
        p = scan.is_present(m)
        cell = ws.cell(row=r, column=col, value="P" if p else "A")
        cell.alignment, cell.border, cell.fill = MID, BOX, OK if p else BAD
    first, last = get_column_letter(6), get_column_letter(col)
    for r in range(2, ws.max_row + 1):
        ws.cell(row=r, column=3, value=f"=COUNTA({first}{r}:{last}{r})")
        ws.cell(row=r, column=4, value=f'=COUNTIF({first}{r}:{last}{r},"P")')
        ws.cell(row=r, column=5, value=f"=IF(C{r}=0,0,ROUND(D{r}/C{r}*100,1))")
    ws.freeze_panes = "F2"
    wb.save(path)
    return path


# =============================================================================
def write_exam_report(incidents, folder, hall="Exam Hall", exam_name=""):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"Exam_Report_{_safe(hall)}_{time.strftime('%Y-%m-%d_%H-%M')}.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Incidents"
    ws["A1"] = f"Exam Monitoring Report - {hall}" + (f" - {exam_name}" if exam_name else "")
    ws["A1"].font = Font(bold=True, size=15, color="1E2A4A")
    ws["A2"] = f"Date: {time.strftime('%d %b %Y')}    Incidents: {len(incidents)}"
    _head(ws, 4, ["#", "Time", "USN", "Name", "Class", "Incident", "Severity", "Lasted (s)",
                  "Evidence", "Full photo"], [5, 12, 15, 22, 16, 34, 10, 10, 18, 12])
    for i, ev in enumerate(incidents, 1):
        r = 4 + i
        vals = [i, _clock(ev.time), ev.usn or "Unidentified", ev.name or f"Person #{ev.track_id}",
                ev.class_name, ev.title, ev.severity, ev.duration, "", "Open"]
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=j, value=v)
            c.border, c.alignment = BOX, LEFT if j in (4, 6) else MID
        ws.cell(row=r, column=7).fill = BAD if ev.severity == "High" else WARN
        if ev.photo and os.path.exists(ev.photo):
            link = ws.cell(row=r, column=10)
            link.hyperlink = os.path.abspath(ev.photo)
            link.font = Font(color="1F5FBF", underline="single")
        if ev.crop and os.path.exists(ev.crop):
            img = cv2.imdecode(np.fromfile(ev.crop, np.uint8), cv2.IMREAD_COLOR)
            t = _thumb_file(img, ev.crop[:-4] + "_t.png", 90)
            if t:
                ws.add_image(XLImage(t), f"I{r}")
                ws.row_dimensions[r].height = 72
    ws.freeze_panes = "A5"
    _print_wide(ws)

    sm = wb.create_sheet("Summary")
    _head(sm, 1, ["Incident type", "Count"], [36, 10])
    for i, (k, v) in enumerate(Counter(e.title for e in incidents).most_common(), 2):
        sm.cell(row=i, column=1, value=k).border = BOX
        sm.cell(row=i, column=2, value=v).border = BOX
    start = sm.max_row + 3
    sm.cell(row=start - 1, column=1, value="By student").font = BOLD
    _head(sm, start, ["Student", "Incidents", "Details"], [36, 10, 60])
    per = defaultdict(list)
    for e in incidents:
        per[f"{e.usn} {e.name}".strip() or f"Unidentified person #{e.track_id}"].append(e.title)
    for i, (who, items) in enumerate(sorted(per.items(), key=lambda kv: -len(kv[1])), start + 1):
        sm.cell(row=i, column=1, value=who).border = BOX
        sm.cell(row=i, column=2, value=len(items)).border = BOX
        sm.cell(row=i, column=3, value=", ".join(f"{k} x{v}" for k, v in Counter(items).items())).border = BOX
    wb.save(path)
    return path


# =============================================================================
def write_shortage_report(class_name, rows, sessions, threshold, folder):
    """Attendance summary for the HOD: every student's %, shortage list first."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"Shortage_{_safe(class_name)}_{time.strftime('%Y-%m-%d_%H-%M')}.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance summary"
    short = [r for r in rows if r.status == "Shortage"]
    ws["A1"] = f"{class_name} - Attendance summary"
    ws["A1"].font = Font(bold=True, size=15, color="1E2A4A")
    ws["A2"] = (f"Date: {time.strftime('%d %b %Y')}    Classes held: {len(sessions)}    "
                f"Minimum required: {threshold:g}%    Students in shortage: {len(short)}")
    ws["A2"].font = BOLD
    _head(ws, 4, ["Sl", "USN", "Name", "Attended", "Held", "Attendance %", "Status",
                  "Must attend next", "Can still miss"], [5, 15, 26, 10, 8, 13, 14, 16, 14])
    for i, r in enumerate(rows, 1):
        vals = [i, r.usn, r.name, r.attended, r.held, r.percent, r.status,
                r.need if r.status == "Shortage" else "", r.can_miss if r.status != "Shortage" else 0]
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=4 + i, column=j, value=v)
            c.border, c.alignment = BOX, LEFT if j == 3 else MID
        ws.cell(row=4 + i, column=7).fill = {"Shortage": BAD, "At risk": WARN, "Safe": OK}.get(r.status, PatternFill())
    ws.freeze_panes = "A5"
    _print_wide(ws)

    sh = wb.create_sheet("Shortage list")
    _head(sh, 1, ["Sl", "USN", "Name", "Attendance %", "Must attend next"], [5, 15, 26, 13, 16])
    for i, r in enumerate(short, 1):
        for j, v in enumerate([i, r.usn, r.name, r.percent, r.need], 1):
            sh.cell(row=1 + i, column=j, value=v).border = BOX

    hist = wb.create_sheet("Sessions")
    _head(hist, 1, ["#", "Date & time", "Subject", "Present", "Absent"], [5, 18, 22, 10, 10])
    for i, s in enumerate(sessions, 1):
        for j, v in enumerate([i, s["time"], s.get("subject", ""), len(s["present"]), len(s["absent"])], 1):
            hist.cell(row=1 + i, column=j, value=v).border = BOX
    wb.save(path)
    return path
