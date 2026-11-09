"""Generate the synthetic sample corpus and its ground-truth manifest.

Writes ./sample_docs/*.pdf|png and sample_docs/manifest.json. Every document is
invented for testing (no real people or companies). The manifest lists, for each
file, the expected document type, extracted fields and workflow outcome, so
evaluate.py can measure accuracy instead of just checking that nothing crashed.

Files are listed in processing order: order matters for the duplicate-identifier
and unusual-amount checks (they compare against documents processed earlier).
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = "sample_docs"
DONE, REVIEW = "Completed", "Needs Review"


def inv(company, number, date, sub, tax, total, extra=()):
    lines = [company, "INVOICE", f"Invoice No: {number}", f"Date: {date}", "Bill To: Sample Customer Co"]
    if sub:
        lines.append(f"Subtotal: {sub}")
    if tax:
        lines.append(f"Tax: {tax}")
    if total:
        lines.append(f"Total Amount: {total}")
    lines.append("Payment terms: net 30")
    return lines + list(extra)


# name -> (lines, expected dict)
PDFS = {
    "invoice_acme.pdf": (inv("ACME Trading Ltd", "INV-1001", "2025-03-14", "1,100.00", "100.00", "$1,200.00"),
        {"type": "Invoice", "status": DONE, "fields": {"invoice_number": "INV-1001", "date": "2025-03-14",
         "company_name": "ACME Trading Ltd", "total_amount": "$1,200.00", "subtotal": "1,100.00", "tax": "100.00"}}),
    "invoice_bluebird.pdf": (inv("Bluebird Supplies LLC", "BB-77", "12/05/2025", "480.00", "20.00", "$500.00"),
        {"type": "Invoice", "status": DONE, "fields": {"invoice_number": "BB-77", "date": "12/05/2025",
         "company_name": "Bluebird Supplies LLC", "total_amount": "$500.00", "subtotal": "480.00", "tax": "20.00"}}),
    "invoice_northwind.pdf": (inv("Northwind Traders Inc", "NW-2043", "2025-06-30", "2,300.00", "230.00", "$2,530.00"),
        {"type": "Invoice", "status": DONE, "fields": {"invoice_number": "NW-2043", "date": "2025-06-30",
         "company_name": "Northwind Traders Inc", "total_amount": "$2,530.00", "subtotal": "2,300.00", "tax": "230.00"}}),
    "invoice_harbor.pdf": (inv("Harbor Logistics Co", "HL-310", "2025-07-08", "760.00", "40.00", "$800.00"),
        {"type": "Invoice", "status": DONE, "fields": {"invoice_number": "HL-310", "date": "2025-07-08",
         "company_name": "Harbor Logistics Co", "total_amount": "$800.00", "subtotal": "760.00", "tax": "40.00"}}),
    "invoice_missing_total.pdf": (inv("Delta Works Inc", "DW-55", "2025-01-02", None, None, None, ["Tax: to be confirmed"]),
        {"type": "Invoice", "status": REVIEW, "reason": "missing_fields", "fields": {
         "invoice_number": "DW-55", "date": "2025-01-02", "company_name": "Delta Works Inc",
         "total_amount": "Not Found"}}),
    "invoice_invalid_date.pdf": (inv("Crest Industries Ltd", "CI-9", "45/45/2025", "90.00", "10.00", "$100.00"),
        {"type": "Invoice", "status": REVIEW, "reason": "invalid_fields", "fields": {
         "invoice_number": "CI-9", "company_name": "Crest Industries Ltd", "total_amount": "$100.00"}}),
    "invoice_zero_total.pdf": (inv("Echo Parts Ltd", "EP-3", "2025-02-20", "0.00", "0.00", "$0.00"),
        {"type": "Invoice", "status": REVIEW, "reason": "invalid_fields", "fields": {
         "invoice_number": "EP-3", "company_name": "Echo Parts Ltd", "total_amount": "$0.00"}}),
    "invoice_arithmetic_mismatch.pdf": (inv("Pioneer Tools Ltd", "PT-808", "2025-04-02", "1,000.00", "100.00", "$1,300.00"),
        {"type": "Invoice", "status": REVIEW, "reason": "arithmetic_mismatch", "fields": {
         "invoice_number": "PT-808", "date": "2025-04-02", "company_name": "Pioneer Tools Ltd",
         "total_amount": "$1,300.00", "subtotal": "1,000.00", "tax": "100.00"}}),
    "invoice_repeated_number.pdf": (inv("Falcon Freight Ltd", "INV-1001", "2025-08-01", "600.00", "50.00", "$650.00"),
        {"type": "Invoice", "status": REVIEW, "reason": "duplicate_identifier", "fields": {
         "invoice_number": "INV-1001", "date": "2025-08-01", "company_name": "Falcon Freight Ltd",
         "total_amount": "$650.00"}}),
    "invoice_future_date.pdf": (inv("Zenith Supplies Ltd", "ZS-12", "2031-01-15", "200.00", "20.00", "$220.00"),
        {"type": "Invoice", "status": REVIEW, "reason": "future_date", "fields": {
         "invoice_number": "ZS-12", "date": "2031-01-15", "company_name": "Zenith Supplies Ltd",
         "total_amount": "$220.00"}}),
    "invoice_huge_amount.pdf": (inv("Titan Equipment Ltd", "TE-1", "2025-09-09", "5,000,000.00", "500,000.00", "$5,500,000.00"),
        {"type": "Invoice", "status": REVIEW, "reason": "unusual_amount", "fields": {
         "invoice_number": "TE-1", "date": "2025-09-09", "company_name": "Titan Equipment Ltd",
         "total_amount": "$5,500,000.00"}}),
    "resume_sara.pdf": (["Sara Khan", "Email: sara.khan@example.com", "Phone: +92 300 1234567",
        "Skills: Python, SQL, Pandas, Machine Learning, Git", "Education: BS Computer Science",
        "Work Experience: Data analyst intern"],
        {"type": "Resume", "status": DONE, "fields": {"name": "Sara Khan", "email": "sara.khan@example.com",
         "phone": "+92 300 1234567", "skills": "python, sql, pandas, machine learning, git"}}),
    "resume_ali.pdf": (["Ali Raza", "ali.raza@mail.org", "+1 (555) 123-4567", "Resume",
        "Skills: Java, Docker, AWS, Linux", "Education: BSc Software Engineering",
        "Experience: Backend developer"],
        {"type": "Resume", "status": DONE, "fields": {"name": "Ali Raza", "email": "ali.raza@mail.org",
         "phone": "+1 (555) 123-4567", "skills": "java, aws, docker, linux"}}),
    "resume_missing_email.pdf": (["Omar Farooq", "Phone: +92 311 7654321", "Skills: Python, Excel, Power BI",
        "Education: BBA", "Work Experience: Analyst"],
        {"type": "Resume", "status": REVIEW, "reason": "missing_fields", "fields": {
         "name": "Omar Farooq", "email": "Not Found", "phone": "+92 311 7654321"}}),
    "resume_repeated_email.pdf": (["Zara Iqbal", "Email: sara.khan@example.com", "Phone: +92 322 5550101",
        "Skills: Excel, Tableau, SQL", "Education: BA Economics", "Work Experience: Analyst"],
        {"type": "Resume", "status": REVIEW, "reason": "duplicate_identifier", "fields": {
         "name": "Zara Iqbal", "email": "sara.khan@example.com", "phone": "+92 322 5550101"}}),
    "memo_team_meeting.pdf": (["Team Meeting Memo", "We will meet on Friday to discuss the roadmap.",
        "Please bring your laptops and prepare an update for the group."],
        {"type": "Other", "status": REVIEW, "reason": "unsupported_type", "fields": {}}),
}

# scanned documents: rendered to PNG and read back with OCR
IMAGES = {
    "scan_invoice_lakeside.png": (inv("Lakeside Printing Ltd", "LP-905", "2025-05-21", "300.00", "30.00", "$330.00"),
        {"type": "Invoice", "status": DONE, "fields": {"invoice_number": "LP-905", "date": "2025-05-21",
         "company_name": "Lakeside Printing Ltd", "total_amount": "$330.00", "subtotal": "300.00", "tax": "30.00"}}),
    "scan_resume_hina.png": (["Hina Malik", "Email: hina.malik@example.com", "Phone: +92 333 4445566",
        "Skills: Python, Django, SQL", "Education: BS Software Engineering", "Work Experience: Web developer"],
        {"type": "Resume", "status": DONE, "fields": {"name": "Hina Malik", "email": "hina.malik@example.com",
         "phone": "+92 333 4445566", "skills": "python, django, sql"}}),
}

# Files that must be rejected at upload (never stored) - name -> (bytes factory, expected code)
def _bad_files():
    good_pdf_head = b"%PDF-1.4\n"
    return {
        "notes.txt": (b"plain text is not a supported type", "unsupported_type"),
        "fake_invoice.pdf": (b"this is not really a pdf file at all" * 5, "invalid_content"),
        "program.exe.pdf": (b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 200, "invalid_content"),
        "truncated.pdf": (good_pdf_head + b"1 0 obj <<garbage>> \x00\x01\x02" * 5, "corrupt"),
        "broken.png": (b"\x89PNG\r\n\x1a\n" + b"\x00\x01notapng" * 20, "corrupt"),
        "empty.pdf": (b"", "empty"),
    }


def make_pdf(path, lines):
    c = canvas.Canvas(path, pagesize=A4)
    y = 800
    for line in lines:
        c.drawString(60, y, line)
        y -= 24
    c.save()


def make_image(path, lines, size=(1100, 720)):
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    y = 40
    for line in lines:
        draw.text((50, y), line, fill="black", font=font)
        y += 60
    img.save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = []
    for name, (lines, expected) in PDFS.items():
        make_pdf(os.path.join(OUT, name), lines)
        manifest.append({"file": name, **expected})
    for name, (lines, expected) in IMAGES.items():
        make_image(os.path.join(OUT, name), lines)
        manifest.append({"file": name, **expected})
    Image.new("RGB", (800, 600), "white").save(os.path.join(OUT, "scan_blank_unreadable.png"))
    manifest.append({"file": "scan_blank_unreadable.png", "type": "Other", "status": REVIEW,
                     "reason": "no_text", "fields": {}})
    rejected = []
    for name, (data, code) in _bad_files().items():
        with open(os.path.join(OUT, name), "wb") as fh:
            fh.write(data)
        rejected.append({"file": name, "expected_code": code})
    with open(os.path.join(OUT, "manifest.json"), "w") as fh:
        json.dump({"documents": manifest, "rejected_uploads": rejected}, fh, indent=2)
    print(f"Wrote {len(manifest)} documents and {len(rejected)} invalid files to {OUT}/")


if __name__ == "__main__":
    main()
