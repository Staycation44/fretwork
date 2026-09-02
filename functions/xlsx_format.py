"""
XLSX_FORMAT - Styling pass applied to output after ANALYZE

Formatting:
    - Frozen header row / leading columns (Code / Song Title / Artist)
    - autofilter & auto-fit column widths
    - Green<yellow<red color scale on difficulties
    - '-1' placeholder seaparate white background to not skew scale
    - Raw NPS/VPS breakdown and the N/V/COV formula components are hidden, not deleted
"""

from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import ColorScaleRule

BODY_FONT = Font(name="Arial", size=10)
HEADER_FONT = Font(name="Arial", size=10, bold=True)
WHITE_FILL = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
THIN_BORDER = Border(*[Side(style="thin", color="A6A6A6")] * 4)

# color scale
SCALE_GREEN = "C6EFCE"
SCALE_YELLOW = "FFEB9C"
SCALE_RED = "FFC7CE"

FLOAT_COLS = {'aNPS', 'pNPS', 'stdNPS', 'medNPS', 'aVPS', 'pVPS', 'stdVPS', 'medVPS', 'N', 'V', 'COV', 'D'}

# difficulty columns
SCALED_COLS = ['Difficulty', 'D', 'RemapDiff', 'CalcTier']

# raw NPS/VPS + formula pieces
DEFAULT_HIDDEN_COLS = ['pNPS', 'aNPS', 'medNPS', 'stdNPS',
                        'pVPS', 'aVPS', 'medVPS', 'stdVPS',
                        'N', 'V', 'COV']

FREEZE_AT = "D2"  # keeps Code / Song Title / Artist visible


def _diff_scale(ws, col_letter, rows):
    """rows: excel row numbers to include - lets sentinel rows (e.g. Difficulty == -1) opt out"""
    if not rows:
        return
    addr = " ".join(f"{col_letter}{r}" for r in rows)
    ws.conditional_formatting.add(
        addr,
        ColorScaleRule(start_type='min', start_color=SCALE_GREEN,
                        mid_type='percentile', mid_value=50, mid_color=SCALE_YELLOW,
                        end_type='max', end_color=SCALE_RED)
    )


def style_sheet(ws, df, hidden_cols=DEFAULT_HIDDEN_COLS, scaled_cols=SCALED_COLS,
                 sentinel_col='Difficulty', sentinel_value=-1, freeze_at=FREEZE_AT):
    n_rows, n_cols = df.shape
    columns = list(df.columns)

    # header
    for c in range(1, n_cols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.freeze_panes = freeze_at
    ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 20

    # body
    for r in range(2, n_rows + 2):
        for c in range(1, n_cols + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = BODY_FONT
            if columns[c - 1] in FLOAT_COLS:
                cell.number_format = '0.00'

    # diff color scales, each scaled against its own range
    for col_name in scaled_cols:
        if col_name not in columns:
            continue
        col_idx = columns.index(col_name) + 1
        col_letter = get_column_letter(col_idx)

        if col_name == sentinel_col:
            real_rows, sentinel_rows = [], []
            for r in range(2, n_rows + 2):
                val = ws.cell(row=r, column=col_idx).value
                (sentinel_rows if val == sentinel_value else real_rows).append(r)
            for r in sentinel_rows:
                ws.cell(row=r, column=col_idx).fill = WHITE_FILL
            _diff_scale(ws, col_letter, real_rows)
        else:
            _diff_scale(ws, col_letter, list(range(2, n_rows + 2)))

    # border boxing
    for col_name in scaled_cols:
        if col_name not in columns:
            continue
        col_idx = columns.index(col_name) + 1
        for r in range(1, n_rows + 2):
            ws.cell(row=r, column=col_idx).border = THIN_BORDER

    # auto-fit column widths
    for i, col in enumerate(columns, start=1):
        longest = max(df[col].astype(str).map(len).max(), len(col))
        ws.column_dimensions[get_column_letter(i)].width = min(max(longest + 2, 6), 40)

    # pre-collapse detail columns
    for col_name in hidden_cols:
        if col_name not in columns:
            continue
        col_idx = columns.index(col_name) + 1
        ws.column_dimensions[get_column_letter(col_idx)].hidden = True
