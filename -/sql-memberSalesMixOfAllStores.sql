-- Overall Member Sales Mix

SELECT 
	SUM(price) AS total_amount,
    SUM(
        CASE
            WHEN member_id IS NOT NULL
             AND TRIM(member_id) <> ''
            THEN price
            ELSE 0
        END
    ) AS member_amount,
    ROUND(
        SUM(
            CASE
                WHEN member_id IS NOT NULL
                 AND TRIM(member_id) <> ''
                THEN price
                ELSE 0
            END
        ) * 100.0 / SUM(price),
    2) AS member_amount_ratio_percent 
FROM kiosk.orders
WHERE 
Created_at BETWEEN '2026-06-05 16:00:00' AND '2026-06-07 16:00:00'
AND status = '20'
AND shop_code <> 'TWI000';