"""
environment_test.py

Zyroo AI/ML Internship - Week 01
Verifies that Python, core AI/ML libraries, and Jupyter are installed
correctly, and confirms a basic ML model can be trained and evaluated.
"""

import sys


def check_imports():
    """Import all required libraries and print their versions."""
    print("=" * 50)
    print("STEP 1: Checking library imports and versions")
    print("=" * 50)

    print(f"Python version   : {sys.version.split()[0]}")

    import numpy as np
    print(f"NumPy version    : {np.__version__}")

    import pandas as pd
    print(f"Pandas version   : {pd.__version__}")

    import matplotlib
    print(f"Matplotlib version: {matplotlib.__version__}")

    import seaborn as sns
    print(f"Seaborn version  : {sns.__version__}")

    import sklearn
    print(f"Scikit-learn ver.: {sklearn.__version__}")

    print("\nAll required libraries imported successfully!\n")


def run_basic_ml_model():
    """Train and evaluate a simple ML model on a built-in dataset."""
    print("=" * 50)
    print("STEP 2: Running a basic ML model (Iris classification)")
    print("=" * 50)

    from sklearn.datasets import load_iris
    from sklearn.model_selection import train_test_split
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score

    # Load a classic toy dataset
    data = load_iris()
    X, y = data.data, data.target

    # Split into train/test sets
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # Train a simple model
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    # Evaluate
    predictions = model.predict(X_test)
    accuracy = accuracy_score(y_test, predictions)

    print(f"Training samples : {len(X_train)}")
    print(f"Test samples     : {len(X_test)}")
    print(f"Model accuracy   : {accuracy * 100:.2f}%")
    print("\nBasic ML model ran successfully!\n")

    return accuracy


def make_sample_plot():
    """Generate a simple plot to confirm matplotlib/seaborn work end-to-end."""
    print("=" * 50)
    print("STEP 3: Generating a sample plot")
    print("=" * 50)

    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend, safe for any environment
    import matplotlib.pyplot as plt
    import seaborn as sns
    from sklearn.datasets import load_iris
    import pandas as pd

    data = load_iris()
    df = pd.DataFrame(data.data, columns=data.feature_names)
    df["species"] = data.target

    sns.scatterplot(
        data=df,
        x="sepal length (cm)",
        y="sepal width (cm)",
        hue="species",
        palette="deep",
    )
    plt.title("Iris Dataset - Sepal Length vs Width")
    plt.tight_layout()
    plt.savefig("environment_test_plot.png")
    print("Sample plot saved as 'environment_test_plot.png'\n")


def main():
    print("\nZYROO AI/ML INTERNSHIP - WEEK 01 ENVIRONMENT TEST\n")

    check_imports()
    accuracy = run_basic_ml_model()
    make_sample_plot()

    print("=" * 50)
    print("ENVIRONMENT TEST COMPLETE")
    print("=" * 50)
    print("Result: Python, required libraries, and a basic ML model")
    print(f"all work correctly (model accuracy: {accuracy * 100:.2f}%).")
    print("Take a screenshot of this output for your submission.\n")


if __name__ == "__main__":
    main()
