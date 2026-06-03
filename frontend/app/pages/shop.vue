<script setup lang="ts">
import type { Product } from "../types/api"

const { apiFetch } = useApi()
const cart = useCart()

const { data: products, pending, error, refresh } = await useAsyncData(
    "shop-products",
    () => apiFetch<Product[]>("/api/products/")
)

const categoryLabel = (category: string) => category === "rice" ? "Rice" : "Petha"
const formatMoney = (value: string | number) => `₹${Number(value).toFixed(2)}`
const visualClass = (product: Product) => product.category === "rice" ? "visual-rice" : "visual-petha"
const isOut = (product: Product) => Number(product.current_qty) <= 0
</script>

<template>
    <main class="shop-shell">
        <header class="shop-header">
            <div>
                <p class="eyebrow">Lakhimpur District, Assam</p>
                <h1>Farm-direct rice and Assamese petha</h1>
            </div>
            <nav class="shop-actions" aria-label="Shop actions">
                <NuxtLink class="cart-link" to="/checkout">Cart {{ cart.count.value }}</NuxtLink>
                <NuxtLink class="text-link" to="/login">Owner login</NuxtLink>
            </nav>
        </header>

        <section v-if="pending" class="status-line">Loading products...</section>
        <section v-else-if="error" class="status-line error-line">
            Catalog is unavailable.
            <button class="inline-action" type="button" @click="refresh()">Retry</button>
        </section>

        <section v-else class="shop-grid" aria-label="Products">
            <article v-for="product in products" :key="product.id" class="product-card">
                <div class="product-visual" :class="visualClass(product)">
                    <span>{{ categoryLabel(product.category) }}</span>
                </div>
                <div class="product-body">
                    <div class="product-title-row">
                        <h2>{{ product.name }}</h2>
                        <strong class="money">{{ formatMoney(product.sell_price) }}</strong>
                    </div>
                    <p>{{ product.current_qty }} {{ product.unit }} available</p>
                    <button class="primary-action" type="button" :disabled="isOut(product)" @click="cart.add(product)">
                        {{ isOut(product) ? "Out of stock" : "Add" }}
                    </button>
                </div>
            </article>
        </section>
    </main>
</template>
