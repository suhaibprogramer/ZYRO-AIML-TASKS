"""
Generates a synthetic labeled dataset (text, label) for the three document
classes used by the project: Invoice, Resume, Other.

Run: python dataset/generate_dataset.py
Produces: dataset/dataset.csv
"""

import csv
import random

random.seed(42)

FIRST_NAMES = ["Ayesha", "Bilal", "Hina", "Usman", "Sara", "Ahmed", "Zara", "Hamza",
               "Mahnoor", "Fahad", "Nadia", "Omar", "Sana", "Tariq", "Iqra", "Danish"]
LAST_NAMES = ["Khan", "Ahmed", "Malik", "Shah", "Butt", "Iqbal", "Raza", "Hussain",
              "Farooq", "Siddiqui", "Chaudhry", "Aslam"]
COMPANY_WORDS = ["Tech", "Solutions", "Global", "Systems", "Digital", "Enterprises",
                  "Innovations", "Traders", "Industries", "Consulting", "Networks", "Labs"]
COMPANY_SUFFIX = ["Pvt Ltd", "Inc.", "LLC", "& Co.", "Group", ""]
SKILLS_POOL = ["Python", "Java", "SQL", "Machine Learning", "Excel", "Communication",
               "Project Management", "React", "Data Analysis", "Streamlit", "AWS",
               "Docker", "C++", "Leadership", "Photoshop", "Marketing", "Sales", "Pandas"]
ITEMS_POOL = ["Web development services", "Hosting (annual)", "UI/UX design",
              "Consulting hours", "Software license", "Maintenance & support",
              "Cloud services", "Graphic design", "Copywriting", "SEO services"]
OTHER_TOPICS = [
    """Meeting Minutes
Date: {date}
Attendees: {names}
Agenda: Project timeline review, budget discussion, next steps.
Notes: The team agreed to move the deadline by two weeks. Marketing will
share the campaign draft by next Friday. Action items were assigned to
each attendee for follow-up.""",
    """Weekly Newsletter
Topic: Local community garden update
This week the community garden welcomed five new volunteers who helped
plant tomatoes and peppers for the season. The next cleanup day is
scheduled for the coming weekend, and everyone is welcome to join.""",
    """Recipe: Simple Vegetable Soup
Ingredients: carrots, potatoes, onions, celery, vegetable broth, salt, pepper.
Instructions: Chop all vegetables into small cubes. Saute onions until soft,
add the rest of the vegetables and broth, then simmer for 25 minutes until
tender. Season to taste and serve warm.""",
    """Terms and Conditions
By using this service you agree to the following terms. Users must not
misuse the platform for unlawful purposes. The company reserves the right
to suspend accounts that violate these terms. These terms may be updated
periodically without prior notice.""",
    """Research Note
Abstract: This short note summarizes early observations from a field study
on urban traffic patterns. Preliminary data suggests congestion peaks occur
consistently between 8-9am and 5-6pm on weekdays, with notable variation on
public holidays.""",
    """Product Description
The new UltraBrew coffee maker features a 12-cup capacity, programmable
timer, and a reusable filter. Its sleek stainless-steel design fits easily
on any kitchen counter, and the auto-shutoff feature ensures safety when
you're on the go.""",
    """Personal Letter
Dear friend, I hope this letter finds you well. It has been a while since
we last spoke, and I wanted to share some updates about my recent trip to
the mountains. The weather was wonderful and the views were breathtaking.""",
    """Event Invitation
You are cordially invited to the annual community fundraiser dinner. The
event will take place at the town hall and will feature live music, a
silent auction, and a keynote speech from a local community leader.""",
    """Job Posting
We are hiring a Marketing Coordinator. Required skills include social
media management, content writing, and basic design tools. Candidates
should have at least two years of experience and a background in
communications or a related field. Education: Bachelor's degree preferred.""",
    """Training Program Brochure
Our 6-week bootcamp helps participants build practical skills in data
analysis and project management. Topics include experience-based case
studies, teamwork exercises, and a final capstone project. No prior
education in the field is required to enroll.""",
]

# Ambiguous "Other" snippets that share keywords with Resume/Invoice rules,
# used to make the rule-based baseline vs ML comparison meaningful.
AMBIGUOUS_OTHER = [
    "Course Syllabus\nThis course covers core skills in negotiation and communication. "
    "Prior experience is helpful but not required. Education level: open to all.",
    "Company Newsletter\nOur training team has been building new skills workshops this "
    "quarter, focused on hands-on experience for new hires across departments.",
]


def make_receipt_style_invoice():
    """An invoice-like document that avoids the word 'invoice' entirely —
    harder for the keyword-rule baseline, useful for a realistic evaluation."""
    receipt_no = f"RCPT-{random.randint(1000, 9999)}"
    date = rand_date()
    company = rand_company()
    total = rand_amount()
    return (f"Payment Receipt\nReceipt No: {receipt_no}\nDate: {date}\n"
            f"Paid to: {company}\nAmount Paid: {total}\nPayment Method: Bank Transfer\n"
            f"Thank you for your payment!")


def add_ocr_noise(text: str, prob: float = 0.02) -> str:
    """Randomly corrupt a few characters to simulate OCR misreads."""
    chars = list(text)
    swaps = {"o": "0", "l": "1", "S": "5", "B": "8", "e": "c"}
    for i, ch in enumerate(chars):
        if ch in swaps and random.random() < prob:
            chars[i] = swaps[ch]
    return "".join(chars)


def rand_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def rand_company():
    return f"{random.choice(COMPANY_WORDS)} {random.choice(COMPANY_WORDS)} {random.choice(COMPANY_SUFFIX)}".strip()


def rand_date():
    return f"{random.randint(1,28):02d}-{random.randint(1,12):02d}-2026"


def rand_email(name):
    return f"{name.split()[0].lower()}.{name.split()[1].lower()}@example.com"


def rand_phone():
    return f"+92 3{random.randint(0,9)}{random.randint(0,9)} {random.randint(1000000,9999999)}"


def rand_amount():
    return f"PKR {random.randint(5, 500) * 1000:,}"


def make_invoice():
    inv_no = f"INV-{random.randint(1000, 9999)}"
    date = rand_date()
    company = rand_company()
    total = rand_amount()
    items = random.sample(ITEMS_POOL, k=random.randint(1, 3))
    item_lines = "\n".join(f"{item}   Qty: {random.randint(1,5)}   {rand_amount()}" for item in items)

    templates = [
        f"INVOICE\nInvoice Number: {inv_no}\nDate: {date}\nCompany: {company}\n\n{item_lines}\n\nTotal: {total}\nThank you for your business.",
        f"TAX INVOICE\nInvoice No: {inv_no}\nInvoice Date: {date}\nVendor: {company}\n\n{item_lines}\n\nGrand Total: {total}\nPayment terms: Net 30",
        f"Invoice #{inv_no}\nIssued: {date}\nBilled by: {company}\n\n{item_lines}\n\nAmount Due: {total}",
        f"BILL\nInvoice number: {inv_no}\nBill to: {company}\nDate: {date}\n\n{item_lines}\n\nTotal Amount: {total}\nPlease pay within 15 days.",
    ]
    return random.choice(templates)


def make_resume():
    name = rand_name()
    email = rand_email(name)
    phone = rand_phone()
    skills = ", ".join(random.sample(SKILLS_POOL, k=random.randint(3, 6)))
    edu = f"BS Computer Science, {random.choice(['COMSATS', 'FAST-NUCES', 'LUMS', 'NUST', 'UET'])}, 2020-2024"
    exp = f"{random.choice(['Software Engineer', 'Data Analyst', 'AI/ML Intern', 'Marketing Associate'])} at {rand_company()} ({random.randint(2022,2025)}-Present)"

    templates = [
        f"{name}\nEmail: {email}    Phone: {phone}\n\nEducation\n{edu}\n\nExperience\n{exp}\n\nSkills\n{skills}",
        f"Curriculum Vitae\nName: {name}\nContact: {phone}, {email}\n\nWork Experience\n{exp}\n\nEducation\n{edu}\n\nKey Skills\n{skills}",
        f"RESUME\n{name}\n{email} | {phone}\n\nSummary: Motivated professional with hands-on experience.\n\nExperience: {exp}\nEducation: {edu}\nSkills: {skills}",
        f"{name}\nPhone: {phone}   Email: {email}\n\nObjective: Seeking a challenging role to apply my skills.\n\nSkills: {skills}\nEducation: {edu}\nExperience: {exp}",
    ]
    return random.choice(templates)


def make_other(ambiguous: bool = False):
    if ambiguous:
        return random.choice(AMBIGUOUS_OTHER)
    topic = random.choice(OTHER_TOPICS)
    names = ", ".join(rand_name() for _ in range(3))
    return topic.format(date=rand_date(), names=names)


def generate_dataset(n_per_class=120, ambiguous_fraction=0.12, noise_fraction=0.15):
    rows = []
    for i in range(n_per_class):
        # Invoices: mix in receipt-style ones with no "invoice" keyword
        if i < n_per_class * 0.2:
            rows.append((make_receipt_style_invoice(), "Invoice"))
        else:
            rows.append((make_invoice(), "Invoice"))

        rows.append((make_resume(), "Resume"))

        # Other: mix in ambiguous ones that share Resume/Invoice keywords
        is_ambiguous = random.random() < ambiguous_fraction
        rows.append((make_other(ambiguous=is_ambiguous), "Other"))

    # Simulate OCR noise on a fraction of samples
    noisy_rows = []
    for text, label in rows:
        if random.random() < noise_fraction:
            text = add_ocr_noise(text)
        noisy_rows.append((text, label))

    random.shuffle(noisy_rows)
    return noisy_rows


if __name__ == "__main__":
    rows = generate_dataset(n_per_class=120)
    with open("dataset/dataset.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label"])
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to dataset/dataset.csv")
    from collections import Counter
    print(Counter(label for _, label in rows))
