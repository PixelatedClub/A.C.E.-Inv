"""Dependency-free, presentation-style Excel reports for A.C.E."""

from __future__ import annotations

import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


NAVY = "FF0C2340"
ORANGE = "FFE87722"
PALE_BLUE = "FFEAF1F7"
PALE_GREEN = "FFE6F2EA"
PALE_RED = "FFFCE8E6"
PALE_GOLD = "FFFFF4D6"
LIGHT_GRAY = "FFF3F5F7"
STRIPE_BLUE = "FFD9EFF8"
BORDER = "FFC8D1DA"
TEXT = "FF17212B"
GRAY = "FF5F6B76"


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result or "A"


def _cell(column: int, row: int, value: Any, style: int = 0) -> str:
    ref = f"{_column_name(column)}{row}"
    if isinstance(value, bool):
        return f'<c r="{ref}" s="{style}" t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    text = escape("" if value is None else str(value))
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _row(number: int, cells: list[str], height: int | None = None) -> str:
    height_xml = f' ht="{height}" customHeight="1"' if height else ""
    return f'<row r="{number}"{height_xml}>{"".join(cells)}</row>'


def _safe_sheet_name(value: str, used: set[str]) -> str:
    base = re.sub(r"[:\\/?*\[\]]", "-", value).strip()[:31] or "Sheet"
    candidate = base
    number = 2
    while candidate in used:
        suffix = f"_{number}"
        candidate = base[: 31 - len(suffix)] + suffix
        number += 1
    used.add(candidate)
    return candidate


def _styles_xml() -> str:
    fonts = [
        '<font><sz val="9"/><name val="Arial"/><color rgb="%s"/></font>' % TEXT,
        '<font><b/><sz val="18"/><name val="Arial"/><color rgb="FFFFFFFF"/></font>',
        '<font><b/><sz val="10"/><name val="Arial"/><color rgb="%s"/></font>' % NAVY,
        '<font><i/><sz val="9"/><name val="Arial"/><color rgb="%s"/></font>' % GRAY,
        '<font><b/><sz val="9"/><name val="Arial"/><color rgb="FFFFFFFF"/></font>',
        '<font><b/><sz val="11"/><name val="Arial"/><color rgb="FFFFFFFF"/></font>',
        '<font><b/><sz val="20"/><name val="Arial"/><color rgb="%s"/></font>' % NAVY,
        '<font><i/><sz val="8"/><name val="Arial"/><color rgb="%s"/></font>' % GRAY,
        '<font><b/><sz val="9"/><name val="Arial"/><color rgb="%s"/></font>' % NAVY,
    ]
    fills = [
        '<fill><patternFill patternType="none"/></fill>',
        '<fill><patternFill patternType="gray125"/></fill>',
        f'<fill><patternFill patternType="solid"><fgColor rgb="{NAVY}"/><bgColor indexed="64"/></patternFill></fill>',
        f'<fill><patternFill patternType="solid"><fgColor rgb="{PALE_BLUE}"/><bgColor indexed="64"/></patternFill></fill>',
        f'<fill><patternFill patternType="solid"><fgColor rgb="{PALE_GREEN}"/><bgColor indexed="64"/></patternFill></fill>',
        f'<fill><patternFill patternType="solid"><fgColor rgb="{PALE_RED}"/><bgColor indexed="64"/></patternFill></fill>',
        f'<fill><patternFill patternType="solid"><fgColor rgb="{PALE_GOLD}"/><bgColor indexed="64"/></patternFill></fill>',
        f'<fill><patternFill patternType="solid"><fgColor rgb="{LIGHT_GRAY}"/><bgColor indexed="64"/></patternFill></fill>',
        f'<fill><patternFill patternType="solid"><fgColor rgb="{ORANGE}"/><bgColor indexed="64"/></patternFill></fill>',
        f'<fill><patternFill patternType="solid"><fgColor rgb="{STRIPE_BLUE}"/><bgColor indexed="64"/></patternFill></fill>',
    ]
    border = (
        f'<border><left style="thin"><color rgb="{BORDER}"/></left>'
        f'<right style="thin"><color rgb="{BORDER}"/></right>'
        f'<top style="thin"><color rgb="{BORDER}"/></top>'
        f'<bottom style="thin"><color rgb="{BORDER}"/></bottom><diagonal/></border>'
    )
    def xf(font=0, fill=0, border=0, align=""):
        flags = ' applyFont="1"' if font else ""
        flags += ' applyFill="1"' if fill else ""
        flags += ' applyBorder="1"' if border else ""
        flags += ' applyAlignment="1"' if align else ""
        alignment = f'<alignment {align}/>' if align else ""
        return f'<xf numFmtId="0" fontId="{font}" fillId="{fill}" borderId="{border}" xfId="0"{flags}>{alignment}</xf>'
    xfs = [
        xf(),
        xf(1, 2, 0, 'vertical="center"'),
        xf(2, 3, 0, 'vertical="center"'),
        xf(3, 0, 0, 'vertical="center"'),
        xf(4, 2, 1, 'horizontal="center" vertical="center" wrapText="1"'),
        xf(0, 0, 1, 'vertical="top" wrapText="1"'),
        xf(0, 9, 1, 'vertical="top" wrapText="1"'),
        xf(5, 8, 0, 'vertical="center"'),
        xf(0, 7, 1, 'vertical="center" wrapText="1"'),
        xf(8, 6, 1, 'vertical="center" wrapText="1"'),
        xf(7, 0, 0, 'vertical="center"'),
        xf(8, 3, 1, 'horizontal="center" vertical="center"'),
        xf(6, 3, 1, 'horizontal="center" vertical="center"'),
        xf(8, 4, 1, 'horizontal="center" vertical="center"'),
        xf(6, 4, 1, 'horizontal="center" vertical="center"'),
        xf(8, 5, 1, 'horizontal="center" vertical="center"'),
        xf(6, 5, 1, 'horizontal="center" vertical="center"'),
        xf(8, 6, 1, 'horizontal="center" vertical="center"'),
        xf(6, 6, 1, 'horizontal="center" vertical="center"'),
        xf(8, 3, 1, 'vertical="center"'),
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<fonts count="{len(fonts)}">{"".join(fonts)}</fonts>'
        f'<fills count="{len(fills)}">{"".join(fills)}</fills>'
        f'<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>{border}</borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )


def _summary_xml(title: str, subtitle: str, org_line: str, summary: dict[str, Any]) -> str:
    rows: list[str] = []
    merges = ["A1:H1", "A2:H2", "A3:H3"]
    rows.append(_row(1, [_cell(1, 1, title, 1)], 30))
    rows.append(_row(2, [_cell(1, 2, subtitle, 2)], 22))
    rows.append(_row(3, [_cell(1, 3, org_line, 3)], 20))
    metrics = list(summary.get("metrics") or [])[:8]
    while len(metrics) < 8:
        metrics.append(("", 0))
    label_styles = [13, 11, 15, 17, 11, 13, 13, 17]
    value_styles = [14, 12, 16, 18, 12, 14, 14, 18]
    metric_cells: dict[int, list[str]] = {5: [], 6: [], 9: [], 10: []}
    for card, (label, value) in enumerate(metrics):
        band = 0 if card < 4 else 1
        start_col = (card % 4) * 2 + 1
        label_row = 5 + band * 4
        value_row = label_row + 1
        end_col = start_col + 1
        merges.extend([
            f"{_column_name(start_col)}{label_row}:{_column_name(end_col)}{label_row}",
            f"{_column_name(start_col)}{value_row}:{_column_name(end_col)}{value_row + 1}",
        ])
        metric_cells[label_row].append(_cell(start_col, label_row, str(label).upper(), label_styles[card]))
        metric_cells[value_row].append(_cell(start_col, value_row, value, value_styles[card]))

    for row_number in (5, 6, 9, 10):
        rows.append(_row(row_number, metric_cells[row_number], 20 if row_number in {5, 9} else 24))

    rows.append(_row(13, [_cell(1, 13, "BLUF", 7)], 24)); merges.append("A13:H13")
    rows.append(_row(14, [_cell(1, 14, summary.get("bluf", ""), 8)], 26)); merges.append("A14:H16")
    rows.append(_row(18, [_cell(1, 18, "DAILY ACTIVITY", 7)], 24)); merges.append("A18:H18")
    daily_columns = list(summary.get("daily_columns") or ["Date", "Records"])
    daily_rows = list(summary.get("daily_rows") or [])
    rows.append(_row(19, [_cell(i + 1, 19, value, 4) for i, value in enumerate(daily_columns)], 30))
    daily_start = 20
    for offset, record in enumerate(daily_rows):
        row_number = daily_start + offset
        rows.append(_row(row_number, [_cell(i + 1, row_number, record.get(col, ""), 6 if offset % 2 else 5) for i, col in enumerate(daily_columns)]))
    total_row = daily_start + len(daily_rows)
    totals = summary.get("daily_totals") or {}
    rows.append(_row(total_row, [_cell(i + 1, total_row, "TOTAL" if i == 0 else totals.get(col, ""), 19) for i, col in enumerate(daily_columns)], 20))

    ma_row = total_row + 2
    rows.append(_row(ma_row, [_cell(1, ma_row, "MAJOR ACTIVITIES", 7)], 24)); merges.append(f"A{ma_row}:H{ma_row}")
    rows.append(_row(ma_row + 1, [_cell(1, ma_row + 1, summary.get("major_activities", ""), 5)], 72)); merges.append(f"A{ma_row + 1}:H{ma_row + 4}")
    coa_row = ma_row + 6
    rows.append(_row(coa_row, [_cell(1, coa_row, "COURSE OF ACTION / VALIDATION", 7)], 24)); merges.append(f"A{coa_row}:H{coa_row}")
    rows.append(_row(coa_row + 1, [_cell(1, coa_row + 1, summary.get("coa_validation", ""), 9)], 54)); merges.append(f"A{coa_row + 1}:H{coa_row + 3}")
    source_row = coa_row + 5
    rows.append(_row(source_row, [_cell(1, source_row, summary.get("source_note", "Source: live A.C.E. inventory database."), 10)], 18)); merges.append(f"A{source_row}:H{source_row}")
    dimension = f"A1:H{source_row}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension}"/><sheetViews><sheetView workbookViewId="0" showGridLines="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/><cols>'
        + ''.join(f'<col min="{i}" max="{i}" width="15" customWidth="1"/>' for i in range(1, 9))
        + f'</cols><sheetData>{"".join(sorted(rows, key=lambda value: int(re.search(r"r=\"(\d+)\"", value).group(1))))}</sheetData>'
        + f'<mergeCells count="{len(merges)}">' + ''.join(f'<mergeCell ref="{ref}"/>' for ref in merges) + '</mergeCells>'
        + '<pageMargins left="0.3" right="0.3" top="0.4" bottom="0.4" header="0.2" footer="0.2"/>'
        + '</worksheet>'
    )


def _detail_xml(sheet: dict[str, Any], subtitle: str, org_line: str) -> str:
    columns = list(sheet.get("columns") or [])
    data = list(sheet.get("rows") or [])
    end_col = _column_name(max(1, len(columns)))
    width_map = {
        "Date & Time": 23, "Checked Out": 23, "Closed": 23, "Created": 23,
        "Last Updated": 23, "Item": 30, "Cadet": 27, "Cadet Email": 28,
        "Explanation": 55, "Details": 55, "Notes": 42, "Validation Note": 48,
        "WINGS / Local Item #": 25, "Size / Variant": 20, "Recorded By": 24,
    }
    rows = [
        _row(1, [_cell(1, 1, sheet["sheet_name"], 1)], 30),
        _row(2, [_cell(1, 2, subtitle, 2)], 22),
        _row(3, [_cell(1, 3, org_line, 3)], 20),
        _row(6, [_cell(i + 1, 6, col, 4) for i, col in enumerate(columns)], 30),
    ]
    for offset, record in enumerate(data):
        row_number = 7 + offset
        style = 6 if offset % 2 else 5
        rows.append(_row(row_number, [_cell(i + 1, row_number, record.get(col, ""), style) for i, col in enumerate(columns)], 22))
    last_row = max(6, 6 + len(data))
    cols = ''.join(
        f'<col min="{i}" max="{i}" width="{width_map.get(col, 18)}" customWidth="1"/>'
        for i, col in enumerate(columns, 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="A1:{end_col}{last_row}"/>'
        '<sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="6" topLeftCell="A7" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f'<sheetFormatPr defaultRowHeight="15"/><cols>{cols}</cols><sheetData>{"".join(rows)}</sheetData>'
        f'<mergeCells count="3"><mergeCell ref="A1:{end_col}1"/><mergeCell ref="A2:{end_col}2"/><mergeCell ref="A3:{end_col}3"/></mergeCells>'
        f'<autoFilter ref="A6:{end_col}{last_row}"/>'
        '<pageMargins left="0.25" right="0.25" top="0.4" bottom="0.4" header="0.2" footer="0.2"/>'
        '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>'
        '</worksheet>'
    )


def write_report_workbook(
    path: Path,
    *,
    title: str,
    subtitle: str,
    org_line: str,
    summary: dict[str, Any],
    detail_sheets: list[dict[str, Any]],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    sheets = [{"sheet_name": _safe_sheet_name("Executive Summary", used), "summary": True}]
    for detail in detail_sheets:
        sheets.append({**detail, "sheet_name": _safe_sheet_name(str(detail.get("sheet_name") or "Detail"), used)})
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        + ''.join(f'<sheet name="{escape(s["sheet_name"])}" sheetId="{i}" r:id="rId{i}"/>' for i, s in enumerate(sheets, 1))
        + '</sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + ''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
        + f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    )
    types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(sheets)+1))
        + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>'
    )
    root_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>'
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{escape(title)}</dc:title><dc:creator>{escape(org_line)}</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified></cp:coreProperties>'
    app = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>A.C.E.</Application><TitlesOfParts><vt:vector size="{len(sheets)}" baseType="lpstr">' + ''.join(f'<vt:lpstr>{escape(s["sheet_name"])}</vt:lpstr>' for s in sheets) + '</vt:vector></TitlesOfParts></Properties>'
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as book:
        book.writestr("[Content_Types].xml", types); book.writestr("_rels/.rels", root_rels)
        book.writestr("docProps/core.xml", core); book.writestr("docProps/app.xml", app)
        book.writestr("xl/workbook.xml", workbook_xml); book.writestr("xl/_rels/workbook.xml.rels", rels)
        book.writestr("xl/styles.xml", _styles_xml())
        book.writestr("xl/worksheets/sheet1.xml", _summary_xml(title, subtitle, org_line, summary))
        for index, sheet in enumerate(sheets[1:], 2):
            book.writestr(f"xl/worksheets/sheet{index}.xml", _detail_xml(sheet, subtitle, org_line))
    return path
