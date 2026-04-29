/**
 * Centralized fetch helper for the web portal.
 * Handles API Versioning and Error Handling (401 redirects).
 */
async function apiFetch(url, options = {}) {
    const defaultHeaders = {
        'X-API-Version': '1', // Required by Stage 3
        'Content-Type': 'application/json',
    };

    const config = {
        ...options,
        headers: {
            ...defaultHeaders,
            ...options.headers,
        },
    };

    try {
        const response = await fetch(url, config);
        
        if (response.status === 401) {
            // Unauthorized - Redirect to login
            window.location.href = "/";
            return null;
        }

        const data = await response.json();

        if (!response.ok) {
            alert(data.message || "An error occurred");
            return null;
        }

        return data;
    } catch (error) {
        console.error("API Fetch Error:", error);
        return null;
    }
}