"""
XLSX_FORMAT - Styling pass applied to output after ANALYZE

Formatting:
    - Frozen header row / leading columns (Code / Song Title / Artist)
    - autofilter & auto-fit column widths
    - Green<yellow<red color scale on difficulties
    - '-1' placeholder gets a separate white background so it doesn't skew the scale
    - Raw NPS/VPS breakdown and the N/V/COV formula components are hidden, not deleted
"""

from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, NamedStyle
from openpyxl.formatting.rule import ColorScaleRule

BODY_FONT = Font(name="Arial", size=10)
HEADER_FONT = Font(name="Arial", size=10, bold=True)
WHITE_FILL = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
THIN_BORDER = Border(*[Side(style="thin", color="A6A6A6")] * 4)
HEADER_ALIGN = Alignment(horizontal="center", vertical="center")

SCALE_GREEN = "C6EFCE"
SCALE_YELLOW = "FFEB9C"
SCALE_RED = "FFC7CE"

# columns needing '0.00' formatting
FLOAT_COLS = {'aNPS', 'pNPS', 'stdNPS', 'medNPS', 'aVPS', 'pVPS', 'stdVPS', 'medVPS', 'N', 'V', 'COV', 'D'}

# difficulty columns - get a color scale + a bordered box
SCALED_COLS = ['Difficulty', 'D', 'RemapDiff', 'CalcTier']

# raw NPS/VPS + formula pieces, hidden by default but not deleted
DEFAULT_HIDDEN_COLS = ['pNPS', 'aNPS', 'medNPS', 'stdNPS',
                        'pVPS', 'aVPS', 'medVPS', 'stdVPS',
                        'N', 'V', 'COV']

FREEZE_AT = "D2"  # keeps Code / Song Title / Artist visible

# Adds a green-yellow-red color scale for difficulty
def _diff_scale(ws, col_letter, rows):

    if not rows:
        return

    rows = sorted(rows)
    ranges = []
    start = prev = rows[0]
    for r in rows[1:]:
        if r == prev + 1:
            prev = r
            continue
        ranges.append((start, prev))
        start = prev = r
    ranges.append((start, prev))

    addr = " ".join(
        f"{col_letter}{a}" if a == b else f"{col_letter}{a}:{col_letter}{b}"
        for a, b in ranges
    )

    ws.conditional_formatting.add(
        addr,
        ColorScaleRule(start_type='min', start_color=SCALE_GREEN,
                        mid_type='percentile', mid_value=50, mid_color=SCALE_YELLOW,
                        end_type='max', end_color=SCALE_RED)
    )


def _named_style(wb, name, **attrs):
    if name not in wb.named_styles:
        style = NamedStyle(name=name)
        for attr, value in attrs.items():
            setattr(style, attr, value)
        wb.add_named_style(style)
    return name


def _body_style(wb, is_scaled, is_float):
    name = f"FW_{'Scaled' if is_scaled else 'Body'}{'Float' if is_float else ''}"
    attrs = {'font': BODY_FONT}
    if is_float:
        attrs['number_format'] = '0.00'
    if is_scaled:
        attrs['border'] = THIN_BORDER
    return _named_style(wb, name, **attrs)


def style_sheet(ws, df, hidden_cols=DEFAULT_HIDDEN_COLS, scaled_cols=SCALED_COLS,
                 sentinel_col='Difficulty', sentinel_value=-1, freeze_at=FREEZE_AT):
    n_rows, n_cols = df.shape
    columns = list(df.columns)
    scaled_set = set(scaled_cols)
    wb = ws.parent

    sentinel_style = _named_style(wb, 'FW_Sentinel', font=BODY_FONT, border=THIN_BORDER, fill=WHITE_FILL)
    header_style = _named_style(wb, 'FW_Header', font=HEADER_FONT, alignment=HEADER_ALIGN)
    header_scaled_style = _named_style(wb, 'FW_HeaderScaled', font=HEADER_FONT,
                                        alignment=HEADER_ALIGN, border=THIN_BORDER)

    ws.freeze_panes = freeze_at
    ws.row_dimensions[1].height = 20

    # style the header + every column's body in one pass, then add the color scale for
    # scaled columns using the sentinel-aware row list we already have on hand
    for c, col_name in enumerate(columns, start=1):
        is_scaled = col_name in scaled_set
        is_float = col_name in FLOAT_COLS
        is_sentinel_col = col_name == sentinel_col

        ws.cell(row=1, column=c).style = header_scaled_style if is_scaled else header_style
        normal_style = _body_style(wb, is_scaled, is_float)

        if is_sentinel_col:
            values = df[col_name].to_numpy()
            real_rows = []
            for i, r in enumerate(range(2, n_rows + 2)):
                cell = ws.cell(row=r, column=c)
                if values[i] == sentinel_value:
                    cell.style = sentinel_style
                else:
                    cell.style = normal_style
                    real_rows.append(r)
            _diff_scale(ws, get_column_letter(c), real_rows)
        else:
            for r in range(2, n_rows + 2):
                ws.cell(row=r, column=c).style = normal_style
            if is_scaled:
                _diff_scale(ws, get_column_letter(c), list(range(2, n_rows + 2)))

    ws.auto_filter.ref = ws.dimensions

    # auto-fit column widths, hiding the raw NPS/VPS/formula columns
    for i, col_name in enumerate(columns, start=1):
        longest = max(df[col_name].astype(str).map(len).max(), len(col_name))
        ws.column_dimensions[get_column_letter(i)].width = min(max(longest + 2, 6), 40)
        if col_name in hidden_cols:
            ws.column_dimensions[get_column_letter(i)].hidden = True
