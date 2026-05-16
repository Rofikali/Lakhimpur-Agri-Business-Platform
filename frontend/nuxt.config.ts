export default defineNuxtConfig({
    compatibilityDate: "2026-05-01",

    devtools: {
        enabled: true
    },

    css: [
        "~/assets/css/main.css"
    ],

    modules: [
        "@pinia/nuxt",
        "@nuxt/image",
        "nuxt-security",
        "@sentry/nuxt",
        "@nuxt/eslint"
    ],

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
            title: "Lakhimpur ERP"
        }
    }
})