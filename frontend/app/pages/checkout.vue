<script setup lang="ts">
import type { OrderResponse } from "../types/api"

const { apiFetch } = useApi()
const cart = useCart()

const customerName = ref("")
const customerPhone = ref("+91")
const customerAddress = ref("")
const fulfillmentType = ref<"pickup" | "delivery">("pickup")
const paymentMode = ref<"cash" | "upi_manual" | "credit">("upi_manual")
const submitting = ref(false)
const error = ref("")
const order = ref<OrderResponse | null>(null)

const formatMoney = (value: string | number) => `₹${Number(value).toFixed(2)}`
const canSubmit = computed(() => cart.items.value.length > 0 && customerName.value.trim().length >= 2 && /^\+?91[6-9]\d{9}$/.test(customerPhone.value.trim()))

function idempotencyKey() {
    return crypto.randomUUID()
}

async function placeOrder() {
    if (!canSubmit.value) return

    submitting.value = true
    error.value = ""

    try {
        const payload = {
            idempotency_key: idempotencyKey(),
            customer_name: customerName.value.trim(),
            customer_phone: customerPhone.value.trim(),
            customer_address: fulfillmentType.value === "delivery" ? customerAddress.value.trim() : null,
            fulfillment_type: fulfillmentType.value,
            channel: "online",
            payment_mode: paymentMode.value,
            items: cart.items.value.map((item) => ({
                product_id: item.product.id,
                qty: String(item.qty),
                source: "own"
            }))
        }

        order.value = await apiFetch<OrderResponse>("/api/orders/", {
            method: "POST",
            body: payload
        })
        cart.clear()
    } catch (err) {
        error.value = err instanceof Error ? err.message : "Could not place order"
    } finally {
        submitting.value = false
    }
}
</script>

<template>
    <main class="checkout-shell">
        <header class="checkout-header">
            <div>
                <p class="eyebrow">Checkout</p>
                <h1>Confirm your order</h1>
            </div>
            <NuxtLink class="text-link" to="/shop">Back to shop</NuxtLink>
        </header>

        <section v-if="order" class="confirmation-panel">
            <p class="eyebrow">Order placed</p>
            <h2>{{ order.order_number }}</h2>
            <p>Status: {{ order.status }} · Payment: {{ order.payment?.status }}</p>
            <strong>{{ formatMoney(order.final_amount) }}</strong>
        </section>

        <section v-else class="checkout-grid">
            <form class="checkout-form" @submit.prevent="placeOrder">
                <label>
                    Name
                    <input v-model="customerName" required autocomplete="name" placeholder="Customer name">
                </label>
                <label>
                    Phone
                    <input v-model="customerPhone" required autocomplete="tel" placeholder="+919876543210">
                </label>

                <fieldset class="segmented-field">
                    <legend>Fulfillment</legend>
                    <label><input v-model="fulfillmentType" type="radio" value="pickup"> Pickup</label>
                    <label><input v-model="fulfillmentType" type="radio" value="delivery"> Delivery</label>
                </fieldset>

                <label v-if="fulfillmentType === 'delivery'">
                    Address
                    <textarea v-model="customerAddress" rows="4" placeholder="Delivery address" />
                </label>

                <fieldset class="segmented-field">
                    <legend>Payment</legend>
                    <label><input v-model="paymentMode" type="radio" value="upi_manual"> UPI</label>
                    <label><input v-model="paymentMode" type="radio" value="cash"> Cash</label>
                    <label><input v-model="paymentMode" type="radio" value="credit"> Credit</label>
                </fieldset>

                <p v-if="error" class="error-line">{{ error }}</p>
                <button class="primary-action" type="submit" :disabled="!canSubmit || submitting">
                    {{ submitting ? "Placing..." : "Place order" }}
                </button>
            </form>

            <aside class="order-summary">
                <h2>Cart</h2>
                <p v-if="cart.items.value.length === 0" class="status-line">Your cart is empty.</p>
                <article v-for="item in cart.items.value" :key="item.product.id" class="cart-row">
                    <div>
                        <strong>{{ item.product.name }}</strong>
                        <span>{{ formatMoney(item.product.sell_price) }} / {{ item.product.unit }}</span>
                    </div>
                    <input
                        class="qty-input"
                        type="number"
                        min="0"
                        :max="Number(item.product.current_qty)"
                        :value="item.qty"
                        @input="cart.setQty(item.product.id, Number(($event.target as HTMLInputElement).value))"
                    >
                </article>
                <footer class="summary-total">
                    <span>Total</span>
                    <strong>{{ formatMoney(cart.total.value) }}</strong>
                </footer>
            </aside>
        </section>
    </main>
</template>
