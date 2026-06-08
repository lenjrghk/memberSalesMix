WITH OrderStats AS (
    -- Script 1: Aggregated order statistics per shop
    SELECT 
        o.shop_code,
        c.digital AS storeType,
        s.shop_name,
        SUM(o.price) AS total_amount,
        SUM(CASE
            WHEN o.member_id IS NOT NULL AND TRIM(o.member_id) <> ''
            THEN o.price
            ELSE 0
        END) AS member_amount,
        ROUND(SUM(CASE
                    WHEN o.member_id IS NOT NULL AND TRIM(o.member_id) <> ''
                    THEN o.price
                    ELSE 0
                END) * 100.0 / SUM(o.price),
                2) AS member_amount_ratio_percent
    FROM
        kiosk.orders o
    LEFT JOIN
        kiosk.shop s ON o.shop_code = s.shop_code
    LEFT JOIN 
        kiosk.shop_config c ON o.shop_code = c.shop_code
    WHERE
        o.created_at BETWEEN '2026-06-01 16:00:00' AND '2026-06-07 16:00:00'
        AND o.status = '20'
        AND o.shop_code <> 'TWI000'
    GROUP BY 
        o.shop_code, 
        c.digital,
        s.shop_name
)
-- Joining Script 1 (OrderStats) with Script 2 (ShopsArea)
SELECT 
    os.shop_code,
    os.storeType,
    os.shop_name,
    os.total_amount,
    os.member_amount,
    os.member_amount_ratio_percent,
    sa.area, 
    sa.Addr1, 
    sa.Addr2, 
    sa.Addr3, 
    sa.phone, 
    sa.openingtime, 
    sa.LON, 
    sa.LAT, 
    sa.isEnable, 
    sa.isdelivery, 
    sa.SMS_addr
FROM 
    OrderStats os
LEFT JOIN 
    kiosk.ShopsArea sa ON os.shop_code = sa.shopcode
ORDER BY 
    os.member_amount_ratio_percent;
