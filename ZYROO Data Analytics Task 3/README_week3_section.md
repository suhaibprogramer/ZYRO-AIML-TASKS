## Week 3: Revenue & Driver Performance Analysis

### Objective
Understand where revenue comes from and how reliably rides are fulfilled, using the same ride-hailing dataset from Week 2.

### Data Preparation
Raw dataset had 126 rows; 6 were removed during cleaning (1 duplicate ride ID, 2 missing/invalid dates, 1 missing pickup location, 1 missing fare, 1 negative fare). 120 clean rows remained (96 Completed, 24 Cancelled). Missing ratings on cancelled rides were kept as expected, since cancelled rides are never rated.

**Note:** this dataset has no `driver_id` or `ride_type` column, so driver-level KPIs and ride-type revenue could not be computed this week (see Limitations).

### Revenue KPIs
- Total completed rides: 96
- Total revenue: PKR 65,427
- Average fare per completed ride: PKR 681.53

### Revenue Findings
- Highest-revenue day: Sunday (PKR 11,910); lowest: Thursday (PKR 5,483)
- Highest-revenue location: Johar Town (PKR 11,323); lowest: DHA (PKR 3,514)
- Card is the top revenue channel (PKR 26,425); Wallet has the highest average fare (PKR 698.16) despite fewest rides

### Completion & Rating Findings
- Overall cancellation rate: 20.0%
- Highest cancellation rate: Lahore (30.0%); lowest: Gulberg (6.7%)
- Average customer rating: 3.96 / 5, concentrated at 4 and 5 stars, none below 3

### Charts
See `screenshots/week-03/` for: revenue by day of week, revenue by location, revenue by payment method, completed vs. cancelled rides, cancellation rate by location, rating distribution.

### Business Insights
- Johar Town combines high revenue with a moderate cancellation rate, making it the strongest-performing zone.
- Lahore's high cancellation rate despite mid-tier revenue suggests fulfillment issues are suppressing realized revenue there.
- Gulberg's low cancellation rate is a useful internal benchmark for what reliable fulfillment looks like.

### Recommendations
1. Investigate high cancellation rates in Lahore and Model Town.
2. Prioritize driver availability in the top three revenue locations (Johar Town, Model Town, Wapda Town).
3. Promote Wallet as a payment method given its higher average fare per ride.
4. Re-collect data with `driver_id` and `ride_type` included to complete the driver performance ranking in a future pass.

### Limitations
- No driver-level analysis possible (no `driver_id` column).
- No ride-type revenue breakdown possible (no `ride_type`/`vehicle_type` column).
- All data falls within a single month, so month-over-month trends could not be assessed.
