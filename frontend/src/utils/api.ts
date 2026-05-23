/**
 * REST Client and fetcher wrapper that automatically appends JWT token authorization headers.
 */

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  
  // Read from cookie
  const value = `; ${document.cookie}`;
  const parts = value.split(`; token=`);
  if (parts.length === 2) return parts.pop()?.split(";").shift() || null;
  
  // Fallback to localStorage
  return localStorage.getItem("aeos_token");
}

export async function fetcher(url: string) {
  const token = getToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };
  
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(url, { headers });
  
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const error = new Error(errorData.detail || "An error occurred while fetching data.");
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

    const res = await fetch(url, {
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

    const res = await fetch(url, {
      method: "POST",
      headers,
      body: formData,
    });

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      throw new Error(errorData.detail || "Failed to upload file");
    }

    return res.json();
  }
};
