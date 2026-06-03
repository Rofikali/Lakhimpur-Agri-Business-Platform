export function useApi() {
    const config = useRuntimeConfig()
    const apiBase = String(config.public.apiBase)

    function apiFetch<T>(path: string, options: Parameters<typeof $fetch<T>>[1] = {}) {
        return $fetch<T>(path, {
            baseURL: apiBase,
            credentials: "include",
            ...options
        })
    }

    return { apiBase, apiFetch }
}
