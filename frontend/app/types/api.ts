export interface Product {
    id: string
    name: string
    slug: string
    category: "rice" | "petha" | string
    unit: string
    sell_price: string
    true_cost: string
    gross_margin: string
    margin_pct: string
    is_active: boolean
    current_qty: string
    low_stock_threshold: string
    image_url?: string | null
}

export interface LoginResponse {
    owner_id: string
    username: string
    expires_at: string
}

export interface OrderItemResponse {
    product_id: string
    product_name: string
    unit_price: string
    qty: string
    total: string
    source: string
}

export interface OrderResponse {
    id: string
    order_number: string
    status: string
    channel: string
    fulfillment_type: string
    customer_name: string
    customer_phone: string
    total_amount: string
    final_amount: string
    razorpay_order_id?: string | null
    cancel_reason?: string | null
    created_at: string
    items: OrderItemResponse[]
    payment?: {
        mode: string
        status: string
        amount: string
    } | null
}
