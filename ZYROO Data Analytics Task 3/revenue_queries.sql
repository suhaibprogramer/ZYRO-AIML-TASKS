-- ZYROO Data Analytics Internship - Week 3
-- Task 03: Revenue & Driver Performance Analysis
--
-- Assumes a table called rides with columns matching raw_rides.csv:
--   ride_id, ride_date, pickup_location, dropoff_location,
--   fare, payment_method, ride_status, rating
--
-- NOTE: This dataset has no driver_id or ride_type column, so the
-- driver-performance and ride-type queries from the task template are
-- omitted here. Add them back once those columns are available (see
-- the commented template at the bottom).

-- 1. Total revenue and average fare (completed rides only)
SELECT
    COUNT(*)              AS completed_rides,
    SUM(fare)              AS total_revenue,
    AVG(fare)              AS average_fare
FROM rides
WHERE ride_status = 'Completed';

-- 2. Revenue by day of week
SELECT
    DAYNAME(ride_date)     AS day_of_week,   -- use TO_CHAR(ride_date,'Day') in Postgres
    COUNT(*)               AS completed_rides,
    SUM(fare)               AS total_revenue
FROM rides
WHERE ride_status = 'Completed'
GROUP BY DAYNAME(ride_date)
ORDER BY total_revenue DESC;

-- 3. Revenue by pickup location
SELECT
    pickup_location,
    COUNT(*)               AS completed_rides,
    SUM(fare)               AS total_revenue,
    AVG(fare)               AS average_fare
FROM rides
WHERE ride_status = 'Completed'
GROUP BY pickup_location
ORDER BY total_revenue DESC;

-- 4. Revenue by payment method
SELECT
    payment_method,
    COUNT(*)               AS completed_rides,
    SUM(fare)               AS total_revenue,
    AVG(fare)               AS average_fare
FROM rides
WHERE ride_status = 'Completed'
GROUP BY payment_method
ORDER BY total_revenue DESC;

-- 5. Overall cancellation rate
SELECT
    SUM(CASE WHEN ride_status = 'Cancelled' THEN 1 ELSE 0 END) * 100.0
        / COUNT(*)          AS cancellation_rate_pct
FROM rides;

-- 6. Cancellation rate by pickup location
SELECT
    pickup_location,
    COUNT(*)               AS total_rides,
    SUM(CASE WHEN ride_status = 'Cancelled' THEN 1 ELSE 0 END)            AS cancelled_rides,
    SUM(CASE WHEN ride_status = 'Cancelled' THEN 1 ELSE 0 END) * 100.0
        / COUNT(*)          AS cancellation_rate_pct
FROM rides
GROUP BY pickup_location
ORDER BY cancellation_rate_pct DESC;

-- 7. Average customer rating (completed rides only)
SELECT
    AVG(rating)             AS average_rating,
    COUNT(*)                AS rated_rides
FROM rides
WHERE ride_status = 'Completed';

-- 8. Rating distribution
SELECT
    rating,
    COUNT(*)                AS num_rides
FROM rides
WHERE ride_status = 'Completed'
GROUP BY rating
ORDER BY rating;


-- ============================================================
-- TEMPLATE (uncomment / adapt if driver_id and ride_type are
-- added to the dataset later):
-- ============================================================

-- Driver performance:
-- SELECT driver_id,
--     COUNT(*) AS total_rides,
--     SUM(CASE WHEN ride_status = 'Completed' THEN 1 ELSE 0 END) AS completed_rides,
--     SUM(CASE WHEN ride_status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_rides,
--     SUM(CASE WHEN ride_status = 'Completed' THEN fare ELSE 0 END) AS revenue,
--     AVG(rating) AS average_rating
-- FROM rides
-- GROUP BY driver_id
-- ORDER BY revenue DESC;

-- Revenue by ride type:
-- SELECT ride_type,
--     COUNT(*) AS rides,
--     SUM(fare) AS total_revenue,
--     AVG(fare) AS average_fare
-- FROM rides
-- WHERE ride_status = 'Completed'
-- GROUP BY ride_type
-- ORDER BY total_revenue DESC;
