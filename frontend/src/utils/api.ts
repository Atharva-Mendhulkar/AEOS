/**
 * REST Client and fetcher wrapper that automatically appends JWT token authorization headers.
 */

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  
  // Read from cookie
  const value = `; ${document.cookie}`;
  const parts = value.split(`; token=`);
  if (parts.length === 2) {
    const token = parts.pop()?.split(";").shift();
    if (token) return token;
  }
  
  // Fallback to localStorage
  return localStorage.getItem("aeos_token");
}

function resolveApiUrl(url: string): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:80";
  return url.startsWith("/") ? `${baseUrl}${url}` : url;
}

export async function fetcher(url: string) {
  const token = getToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };
  
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Prepend API base URL if relative to bypass Next.js rewrites dropping auth headers
  const finalUrl = resolveApiUrl(url);

  // cache: no-store prevents Next.js from caching 401s during SSR
  const res = await fetch(finalUrl, { headers, cache: "no-store" });
  
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const error = new Error(errorData?.error?.message || errorData.detail || "An error occurred while fetching data.");
    (error as any).status = res.status;
    throw error;
  }
  
  return res.json();
}

export const apiClient = {
  async get(url: string) {
    return fetcher(url);
  },

  async post(url: string, body: any) {
    const token = getToken();
    const headers: HeadersInit = {
      "Content-Type": "application/json",
    };
    
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(resolveApiUrl(url), {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || "Failed to post data");
    }

    return res.json();
  },

  async postMultipart(url: string, formData: FormData) {
    const token = getToken();
    const headers: HeadersInit = {};

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(resolveApiUrl(url), {
      method: "POST",
      headers,
      body: formData,
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || "Failed to upload file");
    }

    return res.json();
  },

  async putMultipart(url: string, formData: FormData) {
    const token = getToken();
    const headers: HeadersInit = {};

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(resolveApiUrl(url), {
      method: "PUT",
      headers,
      body: formData,
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData?.error?.message || errorData.detail || "Failed to update resource");
    }

    return res.json();
  },

  async delete(url: string) {
    const token = getToken();
    const headers: HeadersInit = {};

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(resolveApiUrl(url), {
      method: "DELETE",
      headers,
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData?.error?.message || errorData.detail || "Failed to delete resource");
    }

    return res.json();
  }
};
