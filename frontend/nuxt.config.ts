export default defineNuxtConfig({
    compatibilityDate: "2026-05-01",

    devtools: {
        enabled: true
    },

    css: ["~/assets/css/main.css"],

    modules: [
        "@pinia/nuxt",
        "nuxt-security",
        "@sentry/nuxt",
        "@nuxt/eslint"
    ],

    runtimeConfig: {
        public: {
            apiBase: process.env.NUXT_PUBLIC_API_BASE || "http://localhost:8000"
        }
    },

    security: {
        headers: {
            contentSecurityPolicy: {
                "base-uri": ["'none'"],
                "font-src": ["'self'", "https:", "data:"],
                "form-action": ["'self'"],
                "frame-ancestors": ["'self'"],
                "img-src": ["'self'", "data:", "https://images.unsplash.com"],
                "connect-src": ["'self'", "http://localhost:8000", "http://127.0.0.1:8000"],
                "object-src": ["'none'"],
                "script-src-attr": ["'none'"],
                "style-src": ["'self'", "https:", "'unsafe-inline'"],
                "script-src": ["'self'", "https:", "'unsafe-inline'", "'strict-dynamic'", "'nonce-{{nonce}}'"],
                "upgrade-insecure-requests": true
            }
        }
    },

    typescript: {
        strict: true,
        typeCheck: true
    },

    future: {
        compatibilityVersion: 4
    },

    nitro: {
        compressPublicAssets: true
    },

    app: {
        head: {
            title: "Lakhimpur Agri-Business",
            meta: [
                { name: "viewport", content: "width=device-width, initial-scale=1" }
            ]
        }
    }
})
