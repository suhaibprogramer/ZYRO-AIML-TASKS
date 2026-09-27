"""
Generates 3 sample PDFs for testing the Document Intelligence MVP:
- invoice_001.pdf
- invoice_002.pdf
- resume_001.pdf

Run: python generate_samples.py
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def make_invoice(path, invoice_number, date, company, total, items):
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter
    y = height - 80

    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, y, "INVOICE")
    y -= 30

    c.setFont("Helvetica", 11)
    c.drawString(72, y, f"Invoice Number: {invoice_number}")
    y -= 18
    c.drawString(72, y, f"Date: {date}")
    y -= 18
    c.drawString(72, y, f"Company: {company}")
    y -= 30

    c.setFont("Helvetica-Bold", 11)
    c.drawString(72, y, "Description")
    c.drawString(350, y, "Qty")
    c.drawString(420, y, "Unit Price")
    c.drawString(500, y, "Amount")
    y -= 8
    c.line(72, y, 540, y)
    y -= 18

    c.setFont("Helvetica", 10)
    for desc, qty, unit_price, amount in items:
        c.drawString(72, y, desc)
        c.drawString(350, y, str(qty))
        c.drawString(420, y, unit_price)
        c.drawString(500, y, amount)
        y -= 18

    y -= 10
    c.line(72, y, 540, y)
    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(400, y, f"Total: {total}")

    y -= 40
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(72, y, "Thank you for your business.")

    c.save()


def make_resume(path, name, email, phone, education, experience, skills):
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter
    y = height - 72

    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, y, name)
    y -= 22

    c.setFont("Helvetica", 10)
    c.drawString(72, y, f"Email: {email}    Phone: {phone}")
    y -= 30

    c.setFont("Helvetica-Bold", 13)
    c.drawString(72, y, "Education")
    y -= 18
    c.setFont("Helvetica", 10)
    for line in education:
        c.drawString(72, y, line)
        y -= 16

    y -= 12
    c.setFont("Helvetica-Bold", 13)
    c.drawString(72, y, "Experience")
    y -= 18
    c.setFont("Helvetica", 10)
    for line in experience:
        c.drawString(72, y, line)
        y -= 16

    y -= 12
    c.setFont("Helvetica-Bold", 13)
    c.drawString(72, y, "Skills")
    y -= 18
    c.setFont("Helvetica", 10)
    c.drawString(72, y, skills)

    c.save()


if __name__ == "__main__":
    make_invoice(
        "invoice_001.pdf",
        invoice_number="INV-1024",
        date="02-09-2026",
        company="ABC Technologies",
        total="PKR 125,000",
        items=[
            ("Web development services", "1", "PKR 100,000", "PKR 100,000"),
            ("Hosting (annual)", "1", "PKR 25,000", "PKR 25,000"),
        ],
    )

    make_invoice(
        "invoice_002.pdf",
        invoice_number="INV-2077",
        date="15-09-2026",
        company="Zyroo Solutions Pvt Ltd",
        total="PKR 48,500",
        items=[
            ("UI/UX design consultation", "5", "PKR 7,000", "PKR 35,000"),
            ("Revisions", "3", "PKR 4,500", "PKR 13,500"),
        ],
    )

    make_resume(
        "resume_001.pdf",
        name="Ayesha Khan",
        email="ayesha.khan@example.com",
        phone="+92 300 1234567",
        education=[
            "BS Computer Science, COMSATS University Islamabad, 2022-2026",
        ],
        experience=[
            "AI/ML Intern, ZYROO (2026-Present)",
            "Data Analyst Intern, Local Startup (2025)",
        ],
        skills="Python, Machine Learning, Streamlit, SQL, Pandas",
    )

    print("Generated invoice_001.pdf, invoice_002.pdf, resume_001.pdf")
