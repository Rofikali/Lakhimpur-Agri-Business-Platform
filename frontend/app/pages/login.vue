<script setup lang="ts">
import type { LoginResponse } from "../types/api"

const { apiFetch } = useApi()
const username = ref("admin")
const password = ref("changeme123")
const loading = ref(false)
const error = ref("")

async function submitLogin() {
    loading.value = true
    error.value = ""

    try {
        await apiFetch<LoginResponse>("/api/auth/login", {
            method: "POST",
            body: { username: username.value, password: password.value }
        })
        await navigateTo("/dashboard")
    } catch {
        error.value = "Login failed"
    } finally {
        loading.value = false
    }
}
</script>

<template>
    <main class="auth-shell">
        <form class="auth-panel" @submit.prevent="submitLogin">
            <NuxtLink class="text-link" to="/shop">Back to shop</NuxtLink>
            <h1>Owner login</h1>

            <label>
                Username
                <input v-model="username" autocomplete="username" required>
            </label>

            <label>
                Password
                <input v-model="password" autocomplete="current-password" required type="password">
            </label>

            <p v-if="error" class="error-line">{{ error }}</p>
            <button class="primary-action" type="submit" :disabled="loading">
                {{ loading ? "Signing in..." : "Sign in" }}
            </button>
        </form>
    </main>
</template>
