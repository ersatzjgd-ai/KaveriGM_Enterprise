from fpdf import FPDF
import base64
from io import BytesIO
import tempfile
import os
import datetime

def generate_daily_report(df):
    """Generates a PDF report containing a table of today's guests and their photos."""
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    pdf.cell(200, 10, txt=f"KaveriGM Daily Report - {date_str}", ln=1, align='C')
    
    # Table Header
    cols = ["Photo", "Name", "Lounge", "LMW", "Demo", "Met Gurudev"]
    col_widths = [40, 50, 30, 40, 40, 30]
    
    for i, col in enumerate(cols):
        pdf.cell(col_widths[i], 10, col, border=1, align='C')
    pdf.ln()

    # Table Body
    for _, row in df.iterrows():
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        
        # 1. Image Cell (20mm height requirement)
        pdf.rect(x_start, y_start, col_widths[0], 20)
        if row.get('photo_data'):
            try:
                # Decode base64 to temp file (fpdf2 requires a file path or BytesIO with specific setups)
                img_data = base64.b64decode(row['photo_data'].split(",")[-1])
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                    tmp_file.write(img_data)
                    tmp_file_path = tmp_file.name
                pdf.image(tmp_file_path, x=x_start + 2, y=y_start + 2, w=36, h=16)
                os.remove(tmp_file_path)
            except Exception:
                pdf.text(x_start + 2, y_start + 10, "Invalid Image")
        else:
            pdf.text(x_start + 5, y_start + 10, "No Photo")
        
        pdf.set_xy(x_start + col_widths[0], y_start)
        
        # 2. Text Cells
        pdf.cell(col_widths[1], 20, str(row['guest_name']), border=1, align='C')
        pdf.cell(col_widths[2], 20, str(row['lounge']), border=1, align='C')
        pdf.cell(col_widths[3], 20, str(row['lmw_status']), border=1, align='C')
        pdf.cell(col_widths[4], 20, str(row['demo_status']), border=1, align='C')
        pdf.cell(col_widths[5], 20, "Yes" if row['met_gurudev'] else "No", border=1, align='C')
        
        pdf.ln(20)

    # Save to temp file and return path for Taipy download
    file_path = f"/tmp/kaveri_report_{date_str}.pdf"
    pdf.output(file_path)
    return file_path
