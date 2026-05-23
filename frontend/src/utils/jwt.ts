/**
 * Client-side HS256 JWT Generator using the native Web Crypto API.
 * This generates genuine cryptographic signatures that the FastAPI backend will verify.
 */

export async function generateJWT(sub: string, role: string): Promise<string> {
  if (typeof window === "undefined") return "";

  const header = { alg: "HS256", typ: "JWT" };
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    sub,
    role,
    iat: now,
    exp: now + 3600 * 24, // 24 hours
  };

  const textEncoder = new TextEncoder();
  
  // Base64Url encoding helpers
  const toBase64Url = (str: string) => {
    return btoa(str)
      .replace(/=/g, "")
      .replace(/\+/g, "-")
      .replace(/\//g, "_");
  };

  const headerBase64 = toBase64Url(JSON.stringify(header));
  const payloadBase64 = toBase64Url(JSON.stringify(payload));
  const tokenInput = `${headerBase64}.${payloadBase64}`;

  // Use the default test secret key
  const secret = "test-jwt-secret-key-for-aeos-123456789";
  const keyData = textEncoder.encode(secret);

  try {
    const cryptoKey = await window.crypto.subtle.importKey(
      "raw",
      keyData,
      { name: "HMAC", hash: { name: "SHA-256" } },
      false,
      ["sign"]
    );

    const signature = await window.crypto.subtle.sign(
      "HMAC",
      cryptoKey,
      textEncoder.encode(tokenInput)
    );

    const signatureBase64 = btoa(String.fromCharCode(...new Uint8Array(signature)))
      .replace(/=/g, "")
      .replace(/\+/g, "-")
      .replace(/\//g, "_");

    return `${tokenInput}.${signatureBase64}`;
  } catch (error) {
    console.error("Failed to cryptographically sign JWT:", error);
    // Fallback to unsigned structure in worst case
    return `${tokenInput}.`;
  }
}

/**
 * Decode JWT claims locally on the client (without verification)
 */
export function decodeJWT(token: string): any {
  try {
    const parts = token.split(".");
    // Ensure the token has all 3 parts and a non-empty signature
    if (parts.length !== 3 || !parts[2]) return null;
    const payloadJson = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(payloadJson);
  } catch (e) {
    return null;
  }
}
