import type { Product } from "../types/api"

export interface CartItem {
    product: Product
    qty: number
}

const items = ref<CartItem[]>([])

function clampQty(product: Product, qty: number) {
    const max = Math.max(0, Number(product.current_qty))
    return Math.min(Math.max(qty, 0), max)
}

export function useCart() {
    const count = computed(() => items.value.reduce((sum, item) => sum + item.qty, 0))
    const total = computed(() =>
        items.value.reduce((sum, item) => sum + Number(item.product.sell_price) * item.qty, 0)
    )

    function add(product: Product) {
        const existing = items.value.find((item) => item.product.id === product.id)
        if (existing) {
            existing.qty = clampQty(product, existing.qty + 1)
            return
        }

        const qty = clampQty(product, 1)
        if (qty > 0) {
            items.value.push({ product, qty })
        }
    }

    function setQty(productId: string, qty: number) {
        const existing = items.value.find((item) => item.product.id === productId)
        if (!existing) return

        existing.qty = clampQty(existing.product, qty)
        if (existing.qty <= 0) {
            remove(productId)
        }
    }

    function remove(productId: string) {
        items.value = items.value.filter((item) => item.product.id !== productId)
    }

    function clear() {
        items.value = []
    }

    return { items, count, total, add, setQty, remove, clear }
}
