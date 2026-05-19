"""
WhatsApp message templates.
Template names must match approved WATI templates.
All params are positional strings {{1}}, {{2}}, ...
"""

TEMPLATES = {
    "order_confirmed": {
        "name": "order_confirmed",
        "params": lambda order: [
            order.order_number,
            order.customer_name,
            str(order.final_amount),
            order.fulfillment_type,
        ],
    },
    "order_packed": {
        "name": "order_packed",
        "params": lambda order: [
            order.order_number,
            order.customer_name,
        ],
    },
    "order_ready_pickup": {
        "name": "order_ready_pickup",
        "params": lambda order: [
            order.order_number,
            order.customer_name,
        ],
    },
    "order_delivered": {
        "name": "order_delivered",
        "params": lambda order: [
            order.order_number,
            order.customer_name,
        ],
    },
    "new_order_owner": {
        "name": "new_order_owner",
        "params": lambda order: [
            order.order_number,
            order.customer_name,
            order.customer_phone,
            str(order.final_amount),
            order.fulfillment_type,
            order.channel,
        ],
    },
    "low_stock_alert": {
        "name": "low_stock_alert",
        "params": lambda product_name, current_qty, threshold: [
            product_name,
            str(current_qty),
            str(threshold),
        ],
    },
    "petha_expiry_alert": {
        "name": "petha_expiry_alert",
        "params": lambda variety, days_left, batch_date: [
            variety,
            str(days_left),
            str(batch_date),
        ],
    },
    "daily_summary": {
        "name": "daily_summary",
        "params": lambda orders_count, revenue, net_profit: [
            str(orders_count),
            str(revenue),
            str(net_profit),
        ],
    },
}
