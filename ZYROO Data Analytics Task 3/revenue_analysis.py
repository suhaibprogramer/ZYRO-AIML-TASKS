"""
ZYROO Data Analytics Internship - Week 3
Task 03: Revenue & Driver Performance Analysis

Cleans raw_rides.csv and produces the revenue, cancellation, and rating
analysis used in reports/week-03/Week3_Revenue_Driver_Report.docx.

NOTE: This dataset has no driver_id or ride_type/vehicle_type column,
so driver-level KPIs and ride-type revenue breakdown are not computed
here. See the Limitations section of the report. If a version of the
dataset with those columns becomes available, extend this script using
the driver_summary pattern shown (commented out) near the bottom.
"""

import pandas as pd

RAW_PATH = "data/raw_rides.csv"
CLEAN_PATH = "data/clean_rides.csv"


def load_and_clean(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    original_count = len(df)

    # 1. Drop duplicate Ride IDs, keep first occurrence
    dup_count = df["Ride ID"].duplicated().sum()
    df = df.drop_duplicates(subset="Ride ID", keep="first")

    # 2. Parse dates; drop rows with missing/invalid dates
    df["Date_parsed"] = pd.to_datetime(df["Date"], format="%d-%m-%Y", errors="coerce")
    bad_dates = df["Date_parsed"].isna().sum()
    df = df[df["Date_parsed"].notna()]

    # 3. Drop missing pickup location
    missing_pickup = df["Pickup Location"].isna().sum()
    df = df[df["Pickup Location"].notna()]

    # 4. Drop missing or negative fares
    neg_fare = (df["Fare"] < 0).sum()
    missing_fare = df["Fare"].isna().sum()
    df = df[(df["Fare"].notna()) & (df["Fare"] >= 0)]

    # 5. Missing ratings on Cancelled rides are expected and kept as-is
    completed_missing_rating = ((df["Ride Status"] == "Completed") & (df["Rating"].isna())).sum()

    df["Month"] = df["Date_parsed"].dt.strftime("%b %Y")
    df["DayOfWeek"] = df["Date_parsed"].dt.day_name()

    print(f"Removed {dup_count} duplicate Ride ID row(s).")
    print(f"Removed {bad_dates} row(s) with missing/invalid date.")
    print(f"Removed {missing_pickup} row(s) with missing pickup location.")
    print(f"Removed {neg_fare} row(s) with negative fare, {missing_fare} with missing fare.")
    print(f"Completed rides missing a rating (kept): {completed_missing_rating}")
    print(f"Final clean dataset: {len(df)} rows (from {original_count} raw rows).")

    return df


def revenue_analysis(df: pd.DataFrame) -> None:
    completed = df[df["Ride Status"] == "Completed"].copy()

    total_revenue = completed["Fare"].sum()
    total_completed = len(completed)
    avg_fare = completed["Fare"].mean()

    print("\n=== TOTAL REVENUE ===")
    print(f"Total completed rides: {total_completed}")
    print(f"Total revenue: PKR {total_revenue:,.0f}")
    print(f"Average fare per completed ride: PKR {avg_fare:,.2f}")

    print("\n=== REVENUE BY DAY OF WEEK ===")
    print(completed.groupby("DayOfWeek")["Fare"].sum().sort_values(ascending=False))

    print("\n=== REVENUE BY LOCATION ===")
    rev_loc = completed.groupby("Pickup Location")["Fare"].sum().sort_values(ascending=False)
    print(rev_loc)
    print(f"Highest-revenue location: {rev_loc.idxmax()} (PKR {rev_loc.max():,.0f})")
    print(f"Lowest-revenue location: {rev_loc.idxmin()} (PKR {rev_loc.min():,.0f})")

    print("\n=== REVENUE BY PAYMENT METHOD ===")
    pay = (
        completed.groupby("Payment Method")
        .agg(rides=("Ride ID", "count"), revenue=("Fare", "sum"), avg_fare=("Fare", "mean"))
        .sort_values("revenue", ascending=False)
    )
    print(pay)


def cancellation_and_rating_analysis(df: pd.DataFrame) -> None:
    completed = df[df["Ride Status"] == "Completed"]

    overall_cancel_rate = (df["Ride Status"] == "Cancelled").mean() * 100
    print(f"\n=== CANCELLATION ===\nOverall cancellation rate: {overall_cancel_rate:.1f}%")

    print("\n=== CANCELLATION RATE BY LOCATION ===")
    canc = (
        df.groupby("Pickup Location")["Ride Status"]
        .apply(lambda s: (s == "Cancelled").mean() * 100)
        .sort_values(ascending=False)
    )
    print(canc)

    print("\n=== RATING ===")
    print(f"Average rating (completed rides): {completed['Rating'].mean():.2f}")
    print(completed["Rating"].value_counts().sort_index())


# --- Placeholder for when driver_id / ride_type become available ---
# def driver_summary(df):
#     completed = df[df["Ride Status"] == "Completed"]
#     summary = (
#         df.groupby("driver_id")
#         .agg(
#             total_rides=("Ride ID", "count"),
#             completed_rides=("Ride Status", lambda s: (s == "Completed").sum()),
#             cancelled_rides=("Ride Status", lambda s: (s == "Cancelled").sum()),
#             revenue=("Fare", lambda s: s[df.loc[s.index, "Ride Status"] == "Completed"].sum()),
#             avg_rating=("Rating", "mean"),
#         )
#     )
#     summary["completion_rate"] = summary["completed_rides"] / summary["total_rides"] * 100
#     summary["cancellation_rate"] = summary["cancelled_rides"] / summary["total_rides"] * 100
#     return summary.sort_values("revenue", ascending=False)


if __name__ == "__main__":
    clean_df = load_and_clean(RAW_PATH)
    clean_df.to_csv(CLEAN_PATH, index=False)
    revenue_analysis(clean_df)
    cancellation_and_rating_analysis(clean_df)
