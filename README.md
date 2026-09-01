# Zyro AI/ML Internship

This repository contains my weekly submissions for the Zyroo AI/ML Internship program.

## Structure

```
zyro-aiml-internship/
├── week-01/
│   ├── environment_test.py
│   ├── requirements.txt
│   └── README.md (this file, at repo root)
├── README.md
└── .gitignore
```

## Week 01: Onboarding & Environment Setup

**Objective:** Prepare the AI/ML development environment, join official Zyroo
communication channels, configure GitHub, and run a basic ML program.

**What was done:**
- Installed Python 3.12, Git, VS Code, and Jupyter Notebook
- Created a virtual environment (`.venv`) and installed required libraries:
  `numpy`, `pandas`, `matplotlib`, `seaborn`, `scikit-learn`, `jupyter`
- Verified the setup with `environment_test.py`, which:
  - Imports and prints the version of every required library
  - Trains a `RandomForestClassifier` on the Iris dataset and reports accuracy
  - Generates a sample plot to confirm `matplotlib`/`seaborn` work correctly
- Joined the official Zyroo WhatsApp Community and AI/ML Channel
- Pushed this Week 1 work to GitHub

**How to run:**

```bash
python -m venv .venv
source .venv/bin/activate      # on Windows: .venv\Scripts\activate
pip install -r week-01/requirements.txt
python week-01/environment_test.py
```

## Progress

- [x] Week 01 - Onboarding & Environment Setup
- [ ] Week 02 - (upcoming)
