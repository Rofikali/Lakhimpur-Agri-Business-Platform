<script setup lang="ts">
import type { Product } from "../../types/api"

const { apiFetch } = useApi()

const { data: products, pending, error } = await useAsyncData(
    "dashboard-products",
    () => apiFetch<Product[]>("/api/products/")
)

const productList = computed(() => products.value ?? [])
const totalSkus = computed(() => productList.value.length)
const lowStock = computed(() => productList.value.filter((p) => Number(p.current_qty) <= Number(p.low_stock_threshold)).length)
const catalogValue = computed(() => productList.value.reduce((sum, p) => sum + Number(p.sell_price) * Number(p.current_qty), 0))
</script>

<template>
    <main class="dashboard-shell">
        <aside class="dashboard-nav">
            <strong>Lakhimpur Biz</strong>
            <NuxtLink to="/shop">Shop</NuxtLink>
            <NuxtLink to="/dashboard">Dashboard</NuxtLink>
        </aside>

        <section class="dashboard-main">
            <header class="dashboard-header">
                <div>
                    <p class="eyebrow">Owner dashboard</p>
                    <h1>Operations overview</h1>
                </div>
            </header>

            <p v-if="pending" class="status-line">Loading dashboard...</p>
            <p v-else-if="error" class="status-line error-line">Dashboard data unavailable.</p>

            <template v-else>
                <section class="metric-grid">
                    <article class="metric-tile">
                        <span>SKUs</span>
                        <strong>{{ totalSkus }}</strong>
                    </article>
                    <article class="metric-tile">
                        <span>Low stock</span>
                        <strong>{{ lowStock }}</strong>
                    </article>
                    <article class="metric-tile">
                        <span>Stock value</span>
                        <strong>₹{{ catalogValue.toFixed(2) }}</strong>
                    </article>
                </section>

                <section class="table-panel">
                    <table>
                        <thead>
                            <tr>
                                <th>Product</th>
                                <th>Category</th>
                                <th class="numeric">Stock</th>
                                <th class="numeric">Price</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="product in productList" :key="product.id">
                                <td>{{ product.name }}</td>
                                <td>{{ product.category }}</td>
                                <td class="numeric">{{ product.current_qty }} {{ product.unit }}</td>
                                <td class="numeric">₹{{ Number(product.sell_price).toFixed(2) }}</td>
                            </tr>
                        </tbody>
                    </table>
                </section>
            </template>
        </section>
    </main>
</template>
