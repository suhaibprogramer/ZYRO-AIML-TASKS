"""Generate sample test documents into ./sample_docs (PDFs and images)."""
import os

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = "sample_docs"

DOCS = {
    "invoice_normal.pdf": [
        "ACME Trading Ltd", "INVOICE", "Invoice No: INV-1001", "Date: 2025-03-14",
        "Bill To: Zeta Corp", "Subtotal: 1,100.00", "Tax: 100.00", "Total Amount: $1,200.00",
        "Payment terms: net 30"],
    "invoice_second.pdf": [
        "Bluebird Supplies LLC", "INVOICE", "Invoice Number: BB-77", "Date: 12/05/2025",
        "Bill To: Orion Inc", "Subtotal: 480.00", "Tax: 20.00", "Total Due: $500.00",
        "Payment terms: net 15"],
    "invoice_missing_total.pdf": [
        "Delta Works Inc", "INVOICE", "Invoice No: DW-55", "Date: 2025-01-02",
        "Bill To: Nova Ltd", "Payment terms: net 30", "Tax: to be confirmed"],
    "invoice_invalid_date.pdf": [
        "Crest Industries Ltd", "INVOICE", "Invoice No: CI-9", "Date: 45/45/2025",
        "Bill To: Kappa Co", "Subtotal: 90.00", "Tax: 10.00", "Total Amount: $100.00"],
    "invoice_invalid_amount.pdf": [
        "Echo Parts Ltd", "INVOICE", "Invoice No: EP-3", "Date: 2025-02-20",
        "Bill To: Sigma Co", "Subtotal: 0.00", "Tax: 0.00", "Total Amount: $0.00"],
    "resume_normal.pdf": [
        "Sara Khan", "Email: sara.khan@example.com", "Phone: +92 300 1234567",
        "Skills: Python, SQL, Pandas, Machine Learning, Git",
        "Education: BS Computer Science", "Work Experience: Data analyst intern"],
    "resume_second.pdf": [
        "Ali Raza", "ali.raza@mail.org", "+1 (555) 123-4567", "Resume",
        "Skills: Java, Docker, AWS, Linux", "Education: BSc Software Engineering",
        "Experience: Backend developer"],
    "resume_missing_email.pdf": [
        "Omar Farooq", "Phone: +92 311 7654321", "Skills: Python, Excel, Power BI",
        "Education: BBA", "Work Experience: Analyst"],
    "other_memo.pdf": [
        "Team Meeting Memo", "We will meet on Friday to discuss the roadmap.",
        "Please bring your laptops and prepare an update for the group."],
}


def make_pdf(path, lines):
    c = canvas.Canvas(path, pagesize=A4)
    y = 800
    for line in lines:
        c.drawString(60, y, line)
        y -= 24
    c.save()


def make_image(path, lines, size=(900, 700)):
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
    except OSError:
        font = ImageFont.load_default()
    y = 40
    for line in lines:
        draw.text((50, y), line, fill="black", font=font)
        y += 55
    img.save(path)


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, lines in DOCS.items():
        make_pdf(os.path.join(OUT, name), lines)
    make_image(os.path.join(OUT, "invoice_scanned.png"), DOCS["invoice_normal.pdf"][:8])
    Image.new("RGB", (800, 600), "white").save(os.path.join(OUT, "unreadable_blank.png"))
    with open(os.path.join(OUT, "corrupt.pdf"), "wb") as fh:
        fh.write(b"this is not really a pdf file at all" * 5)
    with open(os.path.join(OUT, "notes.txt"), "wb") as fh:
        fh.write(b"unsupported file type")
    print("Samples written to", OUT, "->", len(os.listdir(OUT)), "files")


if __name__ == "__main__":
    main()
