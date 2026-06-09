import { expect, Page, test } from "@playwright/test";

const incidentId = "11111111-1111-4111-8111-111111111111";
const workflowId = "22222222-2222-4222-8222-222222222222";
const stepId = "33333333-3333-4333-8333-333333333333";
const policyId = "44444444-4444-4444-8444-444444444444";

async function mockAeosApi(page: Page) {
  await page.route("**/api/v1/incidents/ingest", async (route) => {
    await route.fulfill({ json: { incident_id: incidentId, status: "ready", severity: "high" } });
  });

  await page.route(`**/api/v1/incidents/${incidentId}/audit`, async (route) => {
    await route.fulfill({
      json: [
        {
          id: 1,
          event_type: "incident.classified",
          timestamp: new Date().toISOString(),
          agent_identity: "coordinator",
          action_description: "Incident classified",
          prev_entry_hash: "genesis",
        },
      ],
    });
  });

  await page.route(`**/api/v1/incidents/${incidentId}`, async (route) => {
    await route.fulfill({
      json: {
        id: incidentId,
        root_signature: "SYSTEM_ERROR",
        severity: "high",
        confidence_score: 0.88,
        status: "in_progress",
        source_input_ref: incidentId,
        workflow_id: workflowId,
        created_at: new Date().toISOString(),
      },
    });
  });

  await page.route("**/api/v1/incidents?**", async (route) => {
    await route.fulfill({
      json: [
        {
          id: incidentId,
          root_signature: "SYSTEM_ERROR",
          severity: "high",
          status: "in_progress",
          workflow_id: workflowId,
          created_at: new Date().toISOString(),
        },
      ],
    });
  });

  await page.route(`**/api/v1/workflows/${workflowId}`, async (route) => {
    await route.fulfill({
      json: {
        id: workflowId,
        incident_id: incidentId,
        status: "executing",
        plan: {
          steps: [
            {
              id: stepId,
              agent_type: "operations",
              status: "active",
              action: { tool: "gather_logs", params: { service: "db" } },
              depends_on: [],
            },
          ],
        },
      },
    });
  });

  await page.route("**/api/v1/escalations/pending", async (route) => {
    await route.fulfill({
      json: [
        {
          id: "55555555-5555-4555-8555-555555555555",
          workflow_id: workflowId,
          step_id: stepId,
          agent_type: "operations",
          incident_summary: "Restart database service",
          risk_score: 7.5,
          tier: "tier_1",
          created_at: new Date().toISOString(),
        },
      ],
    });
  });

  await page.route("**/api/v1/escalations/*/respond", async (route) => {
    await route.fulfill({ json: { status: "processed" } });
  });

  await page.route("**/api/v1/policies", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ json: { id: policyId, status: "created" } });
      return;
    }
    await route.fulfill({
      json: [
        {
          id: policyId,
          name: "Core Permission Policy",
          version: 1,
          is_active: true,
          policy_type: "permission",
          config: { agent_type: "operations", allowed_tools: ["gather_logs"] },
          created_by: "admin-user",
          created_at: new Date().toISOString(),
        },
      ],
    });
  });

  await page.route(`**/api/v1/policies/${policyId}`, async (route) => {
    await route.fulfill({ json: { id: policyId, status: route.request().method() === "DELETE" ? "deactivated" : "updated" } });
  });

  await page.route("**/api/v1/observability/agents", async (route) => {
    await route.fulfill({
      json: {
        operations: { status: "active", active_steps: 1, last_active: new Date().toISOString() },
        planner: { status: "idle", active_steps: 0, last_active: new Date().toISOString() },
      },
    });
  });

  await page.route("**/api/v1/observability/audit/validate-chain", async (route) => {
    await route.fulfill({ json: { status: "valid", validated_count: 4 } });
  });
}

test.beforeEach(async ({ page }) => {
  await mockAeosApi(page);
});

test("dashboard renders active incident list within two seconds", async ({ page }) => {
  const started = Date.now();
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Incident Resolution Center" })).toBeVisible();
  await expect(page.getByText("SYSTEM_ERROR")).toBeVisible();
  expect(Date.now() - started).toBeLessThan(2000);
});

test("incident detail renders execution graph and audit integrity control", async ({ page }) => {
  await page.goto(`/incidents/${incidentId}`);
  await expect(page.getByRole("heading", { name: /Incident Console/ })).toBeVisible();
  await expect(page.getByText("DAG Execution Visualizer")).toBeVisible();
  await page.getByRole("button", { name: /Verify Cryptographic Chain/ }).click();
  await expect(page.getByText(/Cryptographic Integrity Audit/)).toBeVisible();
});

test("escalation queue allows operator decisions", async ({ page }) => {
  await page.goto("/escalations");
  await expect(page.getByRole("heading", { name: "Manual Intervention & Escalations" })).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByRole("button", { name: "Approve" })).toBeEnabled();
});

test("submit form supports all configured multimodal formats", async ({ page }) => {
  await page.goto("/submit");
  const select = page.locator("select").last();
  const optionValues = await select.locator("option").evaluateAll((options) =>
    options.map((option) => (option as HTMLOptionElement).value)
  );
  expect(optionValues).toEqual(["text", "json", "pdf", "image", "log", "audio", "transcript"]);
  await page.getByPlaceholder(/Paste logs/).fill("critical database error from Playwright");
  await page.getByRole("button", { name: "Dispatch Ingestion" }).click();
  await expect(page.getByText(/Ingestion Dispatched Successfully/)).toBeVisible();
});

test("policy management is hidden for read-only users and available for compliance", async ({ page }) => {
  await page.goto("/policies");
  await expect(page.getByRole("heading", { name: "System Governance Policies" })).toBeVisible();

  await page.locator("aside select").selectOption("read_only");
  await expect(page.getByRole("button", { name: "Create Policy" })).toHaveCount(0);

  await page.locator("aside select").selectOption("compliance");
  await expect(page.getByRole("button", { name: "Create Policy" })).toBeVisible();
});

test("agent coordination map reflects persisted agent state", async ({ page }) => {
  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Specialist Agent Orchestration" })).toBeVisible();
  await expect(page.getByText("Operations Specialist")).toBeVisible();
  await expect(page.getByText("active").first()).toBeVisible();
});
