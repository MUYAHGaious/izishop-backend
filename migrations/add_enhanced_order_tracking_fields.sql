-- Enhanced Order Status Tracking Fields Migration
-- This script adds new timestamp and tracking fields to support granular order status updates

-- Add new timestamp fields for enhanced order tracking
ALTER TABLE orders ADD COLUMN confirmed_at DATETIME NULL;
ALTER TABLE orders ADD COLUMN payment_confirmed_at DATETIME NULL;
ALTER TABLE orders ADD COLUMN processing_started_at DATETIME NULL;
ALTER TABLE orders ADD COLUMN packed_at DATETIME NULL;
ALTER TABLE orders ADD COLUMN picked_up_at DATETIME NULL;
ALTER TABLE orders ADD COLUMN shipped_at DATETIME NULL;
ALTER TABLE orders ADD COLUMN out_for_delivery_at DATETIME NULL;
ALTER TABLE orders ADD COLUMN delivered_at DATETIME NULL;
ALTER TABLE orders ADD COLUMN completed_at DATETIME NULL;

-- Add dynamic delivery estimate fields
ALTER TABLE orders ADD COLUMN current_estimated_delivery DATETIME NULL;
ALTER TABLE orders ADD COLUMN delivery_window_start DATETIME NULL;
ALTER TABLE orders ADD COLUMN delivery_window_end DATETIME NULL;

-- Update existing orders to populate some timestamps based on current status
-- This is a one-time migration to ensure existing orders have proper timeline data

UPDATE orders
SET confirmed_at = created_at
WHERE status IN ('confirmed', 'processing', 'shipped', 'delivered', 'completed');

UPDATE orders
SET processing_started_at = created_at
WHERE status IN ('processing', 'shipped', 'delivered', 'completed');

UPDATE orders
SET shipped_at = updated_at
WHERE status IN ('shipped', 'delivered', 'completed');

UPDATE orders
SET delivered_at = updated_at
WHERE status = 'delivered' OR status = 'completed';

UPDATE orders
SET completed_at = updated_at
WHERE status = 'completed';

-- Set current_estimated_delivery to the original estimate for existing orders
UPDATE orders
SET current_estimated_delivery = estimated_delivery_date
WHERE estimated_delivery_date IS NOT NULL;

-- Create indexes for performance on new timestamp fields
CREATE INDEX IF NOT EXISTS idx_orders_confirmed_at ON orders(confirmed_at);
CREATE INDEX IF NOT EXISTS idx_orders_processing_started_at ON orders(processing_started_at);
CREATE INDEX IF NOT EXISTS idx_orders_packed_at ON orders(packed_at);
CREATE INDEX IF NOT EXISTS idx_orders_picked_up_at ON orders(picked_up_at);
CREATE INDEX IF NOT EXISTS idx_orders_shipped_at ON orders(shipped_at);
CREATE INDEX IF NOT EXISTS idx_orders_out_for_delivery_at ON orders(out_for_delivery_at);
CREATE INDEX IF NOT EXISTS idx_orders_delivered_at ON orders(delivered_at);
CREATE INDEX IF NOT EXISTS idx_orders_completed_at ON orders(completed_at);
CREATE INDEX IF NOT EXISTS idx_orders_current_estimated_delivery ON orders(current_estimated_delivery);

-- Add comments for documentation
-- Note: In a production PostgreSQL environment, you would use COMMENT ON COLUMN
-- For SQLite compatibility, we'll document here:

-- confirmed_at: When order was confirmed by the system
-- payment_confirmed_at: When payment was successfully processed
-- processing_started_at: When seller started preparing the order
-- packed_at: When order was packed and ready for pickup
-- picked_up_at: When carrier picked up the package
-- shipped_at: When package started transit (replaces old logic)
-- out_for_delivery_at: When package is out for final delivery
-- delivered_at: When package was delivered to customer
-- completed_at: When order was marked as completed (after delivery confirmation)
-- current_estimated_delivery: Dynamic delivery estimate (updated by carrier APIs)
-- delivery_window_start: Start of delivery time window
-- delivery_window_end: End of delivery time window