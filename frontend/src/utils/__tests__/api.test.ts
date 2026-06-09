import { apiClient } from "../api";

describe("Property 30: frontend API layer RBAC handling", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    document.cookie = "token=; Max-Age=0; path=/";
    localStorage.clear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it.each([
    ["admin", 200],
    ["compliance", 200],
    ["operator", 403],
    ["read_only", 403],
  ])("propagates authorization for %s policy writes", async (role, status) => {
    localStorage.setItem("aeos_token", `${role}-token`);
    global.fetch = jest.fn().mockImplementation((_url, init: RequestInit) => {
      expect(init.headers).toMatchObject({ Authorization: `Bearer ${role}-token` });
      return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(status === 200 ? { status: "created" } : { detail: "Forbidden" }),
      });
    }) as jest.Mock;

    const formData = new FormData();
    formData.append("name", "RBAC Test Policy");
    formData.append("policy_type", "permission");
    formData.append("config", '{"agent_type":"operations","allowed_tools":["gather_logs"]}');

    if (status === 200) {
      await expect(apiClient.postMultipart("/api/v1/policies", formData)).resolves.toEqual({ status: "created" });
    } else {
      await expect(apiClient.postMultipart("/api/v1/policies", formData)).rejects.toThrow("Forbidden");
    }
  });
});
