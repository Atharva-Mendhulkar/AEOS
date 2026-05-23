import express, { Request, Response } from "express";
import Redis from "ioredis";
import { Pool } from "pg";
import axios from "axios";
import { v4 as uuidv4 } from "uuid";
import winston from "winston";

const logger = winston.createLogger({
  level: "info",
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [new winston.transports.Console()],
});

const app = express();
app.use(express.json());

const port = process.env.PORT || 8001;
const redisUrl = process.env.REDIS_URL || "redis://:aeosredis@redis:6379/0";
const dbUrl = process.env.DATABASE_URL || "postgresql://postgres:postgres@postgres:5432/aeos";
const memoryAgentUrl = process.env.MEMORY_AGENT_URL || "http://memory-agent:8017";
const observabilityUrl = process.env.OBSERVABILITY_URL || "http://observability-service:8040";
const plannerAgentUrl = process.env.PLANNER_AGENT_URL || "http://planner-agent:8010";

const redis = new Redis(redisUrl);
const dbPool = new Pool({ connectionString: dbUrl });

redis.on("connect", () => logger.info("Coordinator connected to Redis"));
redis.on("error", (err: any) => logger.error("Redis Error", err));

dbPool.on("connect", () => logger.info("Coordinator connected to PostgreSQL"));
dbPool.on("error", (err: any) => logger.error("PostgreSQL Pool Error", err));

// Helper: SLA active step logging
async function activateStep(workflowId: string, stepId: string) {
  const startTime = Date.now();
  logger.info(`Activating step ${stepId} for workflow ${workflowId}`);

  try {
    // 1. Fetch step details from DB
    const stepResult = await dbPool.query(
      "SELECT id, agent_type, action, depends_on FROM workflow_steps WHERE id = $1",
      [stepId]
    );
    if (stepResult.rows.length === 0) {
      logger.error(`Step ${stepId} not found in database`);
      return;
    }
    const step = stepResult.rows[0];

    // 2. Update step status to 'active'
    await dbPool.query(
      "UPDATE workflow_steps SET status = 'active', updated_at = NOW() WHERE id = $1",
      [stepId]
    );

    // Get incident_id
    const wfResult = await dbPool.query(
      "SELECT incident_id FROM workflows WHERE id = $1",
      [workflowId]
    );
    if (wfResult.rows.length === 0) {
      logger.error(`Workflow ${workflowId} not found`);
      return;
    }
    const incidentId = wfResult.rows[0].incident_id;

    // Query all completed steps to propagate their outputs
    const completedStepsResult = await dbPool.query(
      "SELECT id, agent_type, output FROM workflow_steps WHERE workflow_id = $1 AND status = 'completed'",
      [workflowId]
    );
    const stepOutputs: Record<string, any> = {};
    const agentOutputs: Record<string, any> = {};
    for (const row of completedStepsResult.rows) {
      stepOutputs[row.id] = row.output;
      agentOutputs[row.agent_type] = row.output;
    }

    // 3. Publish task details to agent:{agent_type}:tasks pub-sub
    const taskPayload = {
      task_id: uuidv4(),
      workflow_id: workflowId,
      step_id: stepId,
      incident_id: incidentId,
      action: step.action,
      context: {
        incident_id: incidentId,
        historical_resolutions: [],
        agent_metrics: {},
        policy_constraints: {
          step_outputs: stepOutputs,
          agent_outputs: agentOutputs
        }
      },
      permissions: {
        agent_type: step.agent_type,
        allowed_resources: [],
        denied_resources: [],
        allowed_api_scopes: []
      }
    };

    await redis.publish(`agent:${step.agent_type}:tasks`, JSON.stringify(taskPayload));
    logger.info(`Published task to agent:${step.agent_type}:tasks for step ${stepId}`);

    const duration = (Date.now() - startTime) / 1000;
    if (duration > 2.0) {
      logger.warn(`SLA warning: Step ${stepId} activation took ${duration} seconds (limit: 2s)`);
    }

    // 4. Emit event to Observability
    try {
      await axios.post(`${observabilityUrl}/observability/events`, {
        type: "step.started",
        sequence: 2,
        payload: {
          workflow_id: workflowId,
          step_id: stepId,
          agent_type: step.agent_type,
          action: step.action,
        },
        emitted_at: new Date().toISOString()
      });
    } catch (err: any) {
      logger.warn(`Failed to emit step.started event: ${err.message}`);
    }
  } catch (err: any) {
    logger.error(`Error activating step ${stepId}:`, err);
  }
}

// ---------------------------------------------------------------------------
// Health Endpoint
// ---------------------------------------------------------------------------
app.get("/health", (req: Request, res: Response) => {
  res.json({ status: "healthy", service: "coordinator", timestamp: new Date().toISOString() });
});

// ---------------------------------------------------------------------------
// Route Input Endpoint
// ---------------------------------------------------------------------------
app.post("/coordinator/route-input", async (req: Request, res: Response) => {
  const { input_id } = req.body;
  if (!input_id) {
    return res.status(400).json({ error: "input_id is required" });
  }

  logger.info(`Routing input: ${input_id}`);
  const taskId = uuidv4();
  const workflowId = uuidv4();
  const stepId = uuidv4();

  const task = {
    task_id: taskId,
    workflow_id: workflowId,
    step_id: stepId,
    incident_id: input_id,
    action: {
      tool: "classify",
      params: {}
    },
    context: {
      incident_id: input_id,
      historical_resolutions: [],
      agent_metrics: {},
      policy_constraints: {}
    },
    permissions: {
      agent_type: "incident_analysis",
      allowed_resources: [],
      denied_resources: [],
      allowed_api_scopes: []
    },
  };

  try {
    // Fetch input created_at for routing SLA check
    const dbResult = await dbPool.query("SELECT created_at FROM multimodal_inputs WHERE id = $1", [input_id]);
    const createdAt = dbResult.rows[0]?.created_at;

    await redis.publish("agent:incident_analysis:tasks", JSON.stringify(task));
    logger.info(`Task published to agent:incident_analysis:tasks. Task ID: ${taskId}`);

    const dispatchedAt = new Date().toISOString();
    
    // Emit routing.dispatched event to Observability Layer
    try {
      await axios.post(`${observabilityUrl}/observability/events`, {
        event_type: "routing.dispatched",
        timestamp: dispatchedAt,
        agent_identity: "coordinator",
        incident_id: input_id,
        workflow_id: workflowId,
        action_description: `Routing dispatched for input ${input_id}`,
        inputs: {
          input_id,
          ingested_at: createdAt ? new Date(createdAt).toISOString() : null,
          dispatched_at: dispatchedAt
        },
        outputs: {
          task_id: taskId
        }
      });
      
      if (createdAt) {
        const diffMs = new Date(dispatchedAt).getTime() - new Date(createdAt).getTime();
        if (diffMs > 5000) {
          logger.warn(`SLA violation: routing dispatched took ${diffMs / 1000} seconds (limit: 5s)`);
        }
      }
    } catch (obsErr: any) {
      logger.error("Failed to emit routing.dispatched event to Observability", obsErr.message);
    }

    res.json({ status: "routing", task_id: taskId });
  } catch (err: any) {
    logger.error("Failed to publish task to Redis or query DB", err);
    res.status(500).json({ error: "Failed to publish routing task", details: err.message });
  }
});

// ---------------------------------------------------------------------------
// Plan Ready Endpoint
// ---------------------------------------------------------------------------
app.post("/coordinator/plan-ready", async (req: Request, res: Response) => {
  const { workflow_id, steps } = req.body;
  if (!workflow_id || !steps || !Array.isArray(steps)) {
    return res.status(400).json({ error: "Missing workflow_id or steps array" });
  }

  logger.info(`Plan ready received for workflow ${workflow_id}`);
  const client = await dbPool.connect();

  try {
    await client.query("BEGIN");

    // 1. Update workflow status to executing and store the plan JSON
    const planJSON = JSON.stringify({ steps });
    await client.query(
      "UPDATE workflows SET status = 'executing', plan = $1, updated_at = NOW() WHERE id = $2",
      [planJSON, workflow_id]
    );

    // 2. Write all steps to the workflow_steps table in DB
    for (const step of steps) {
      // Ensure depend_on format is array of UUIDs or empty array
      const dependsOn = step.depends_on || [];
      await client.query(
        `INSERT INTO workflow_steps (id, workflow_id, agent_type, action, status, depends_on, risk_score, output, retry_count, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $5, $6, NULL, NULL, 0, NOW(), NOW())`,
        [step.id, workflow_id, step.agent_type, JSON.stringify(step.action), "pending", dependsOn]
      );
    }

    await client.query("COMMIT");

    // 3. Initialize DAG in Redis
    await redis.set(`workflow:${workflow_id}:status`, "executing");
    for (const step of steps) {
      await redis.sadd(`workflow:${workflow_id}:all_steps`, step.id);
      if (step.depends_on && step.depends_on.length > 0) {
        await redis.sadd(`workflow:${workflow_id}:step:${step.id}:deps`, ...step.depends_on);
      }
    }

    // 4. Emit workflow.started event to Observability
    try {
      await axios.post(`${observabilityUrl}/observability/events`, {
        type: "workflow.started",
        sequence: 1,
        payload: { workflow_id },
        emitted_at: new Date().toISOString()
      });
    } catch (err: any) {
      logger.warn(`Failed to emit workflow.started event: ${err.message}`);
    }

    // 5. Activate all steps with no dependencies
    const rootSteps = steps.filter(s => !s.depends_on || s.depends_on.length === 0);
    logger.info(`Activating ${rootSteps.length} root steps for workflow ${workflow_id}`);
    
    // Concurrent activation of independent steps
    await Promise.all(rootSteps.map(step => activateStep(workflow_id, step.id)));

    res.json({ status: "executing", activated_steps: rootSteps.map(s => s.id) });
  } catch (err: any) {
    await client.query("ROLLBACK");
    logger.error(`Failed to load and start execution plan: ${err.message}`, err);
    res.status(500).json({ error: "Failed to initialize execution plan", details: err.message });
  } finally {
    client.release();
  }
});

// ---------------------------------------------------------------------------
// Step Complete Endpoint (Classification / Execution Callback)
// ---------------------------------------------------------------------------
app.post("/coordinator/step-complete", async (req: Request, res: Response) => {
  const { task_id, step_id, workflow_id, output, requires_escalation } = req.body;
  
  if (!workflow_id || !output) {
    return res.status(400).json({ error: "Missing required callback parameters" });
  }

  // 1. Classification callback from incident-analysis-agent
  if (output && output.root_signature) {
    const { severity, confidence_score, root_signature } = output;
    const resolvedInputId = req.body.incident_id || req.body.task_id;

    logger.info(`Received classification callback for task ${task_id}, root_signature: ${root_signature}`);

    const client = await dbPool.connect();
    try {
      await client.query("BEGIN");

      // Deduplication Check
      const dupCheck = await client.query(
        "SELECT id, status FROM incidents WHERE root_signature = $1 AND created_at >= NOW() - INTERVAL '60 seconds' LIMIT 1",
        [root_signature]
      );

      if (dupCheck.rows.length > 0) {
        const existingIncident = dupCheck.rows[0];
        logger.info(`Duplicate incident detected. Merging input ${resolvedInputId} with existing incident ${existingIncident.id}`);
        
        await client.query(
          "UPDATE multimodal_inputs SET processing_status = 'ready' WHERE id = $1",
          [resolvedInputId]
        );
        
        await client.query("COMMIT");
        
        try {
          await axios.post(`${memoryAgentUrl}/memory/audit`, {
            event_type: "incident.classified",
            timestamp: new Date().toISOString(),
            agent_identity: "coordinator",
            incident_id: existingIncident.id,
            action_description: `Multimodal input ${resolvedInputId} was merged as duplicate of ${existingIncident.id}`,
            inputs: { input_id: resolvedInputId, root_signature },
            outputs: { duplicate_of: existingIncident.id },
            prev_entry_hash: "genesis"
          });
        } catch (err: any) {
          logger.warn(`Failed to audit duplicate merge: ${err.message}`);
        }
        
        return res.json({ status: "merged", incident_id: existingIncident.id });
      }

      // Create new incident
      const incidentId = uuidv4();
      const incidentStatus = requires_escalation ? "escalated" : "open";
      const finalSeverity = requires_escalation ? null : severity;

      await client.query(
        `INSERT INTO incidents (id, root_signature, severity, confidence_score, status, source_input_ref, workflow_id, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $5, $6, NULL, NOW(), NOW())`,
        [incidentId, root_signature, finalSeverity, confidence_score, incidentStatus, resolvedInputId]
      );

      // Create workflow
      await client.query(
        `INSERT INTO workflows (id, incident_id, plan, status, current_step_ids, retry_count, checkpoint, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $5, 0, NULL, NOW(), NOW())`,
        [workflow_id, incidentId, JSON.stringify({ steps: [] }), "planning", []]
      );

      // Update incident with workflow_id
      await client.query(
        `UPDATE incidents SET workflow_id = $1 WHERE id = $2`,
        [workflow_id, incidentId]
      );

      await client.query(
        "UPDATE multimodal_inputs SET processing_status = 'ready' WHERE id = $1",
        [resolvedInputId]
      );

      await client.query("COMMIT");
      logger.info(`Created new incident ${incidentId} and workflow ${workflow_id}`);

      // Emit event
      try {
        await axios.post(`${observabilityUrl}/observability/events`, {
          type: "incident.classified",
          sequence: 1,
          payload: { incident_id: incidentId, workflow_id, severity: finalSeverity, root_signature, status: incidentStatus },
          emitted_at: new Date().toISOString()
        });
      } catch (err: any) {
        logger.warn(`Failed to emit classified event: ${err.message}`);
      }

      // Invoke Planner Agent if not escalated
      if (!requires_escalation) {
        axios.post(`${plannerAgentUrl}/planner/generate`, {
          incident_id: incidentId,
          severity: finalSeverity,
          root_signature: root_signature,
          workflow_id: workflow_id
        }).catch(err => logger.error(`Failed to invoke planner-agent: ${err.message}`));
      }

      res.json({ status: "created", incident_id: incidentId, workflow_id });
    } catch (err: any) {
      await client.query("ROLLBACK");
      logger.error("Failed to process classification callback", err);
      res.status(500).json({ error: "Database transaction failed", details: err.message });
    } finally {
      client.release();
    }
  } else {
    // 2. Execution step callback from Workflow Engine
    logger.info(`Received execution callback for step ${step_id} completed in workflow ${workflow_id}`);
    
    try {
      // Update step status in DB
      await dbPool.query(
        "UPDATE workflow_steps SET status = 'completed', output = $1, updated_at = NOW() WHERE id = $2",
        [JSON.stringify(output), step_id]
      );

      // Emit step.completed event to Observability
      try {
        await axios.post(`${observabilityUrl}/observability/events`, {
          type: "step.completed",
          sequence: 3,
          payload: { workflow_id, step_id, output },
          emitted_at: new Date().toISOString()
        });
      } catch (err: any) {
        logger.warn(`Failed to emit step.completed event: ${err.message}`);
      }

      // Evaluate DAG dependency satisfaction
      const allStepIds = await redis.smembers(`workflow:${workflow_id}:all_steps`);
      const activatedSteps: string[] = [];

      for (const pendingStepId of allStepIds) {
        const hasDep = await redis.sismember(`workflow:${workflow_id}:step:${pendingStepId}:deps`, step_id);
        if (hasDep) {
          await redis.srem(`workflow:${workflow_id}:step:${pendingStepId}:deps`, step_id);
          const remaining = await redis.scard(`workflow:${workflow_id}:step:${pendingStepId}:deps`);
          if (remaining === 0) {
            activatedSteps.push(pendingStepId);
          }
        }
      }

      // Activate all satisfied steps concurrently
      await Promise.all(activatedSteps.map(sid => activateStep(workflow_id, sid)));

      // Check if workflow is completely finished
      const activeOrPending = await dbPool.query(
        "SELECT count(*) FROM workflow_steps WHERE workflow_id = $1 AND status IN ('pending', 'active', 'suspended')",
        [workflow_id]
      );

      if (parseInt(activeOrPending.rows[0].count) === 0) {
        logger.info(`All steps completed for workflow ${workflow_id}. Marking workflow as completed.`);
        await dbPool.query(
          "UPDATE workflows SET status = 'completed', updated_at = NOW() WHERE id = $1",
          [workflow_id]
        );

        // Clean up Redis keys
        await redis.del(
          `workflow:${workflow_id}:status`,
          `workflow:${workflow_id}:all_steps`,
          ...allStepIds.map(sid => `workflow:${workflow_id}:step:${sid}:deps`)
        );

        // Emit workflow.completed event to Observability
        try {
          await axios.post(`${observabilityUrl}/observability/events`, {
            type: "workflow.completed",
            sequence: 4,
            payload: { workflow_id },
            emitted_at: new Date().toISOString()
          });
        } catch (err: any) {
          logger.warn(`Failed to emit workflow.completed event: ${err.message}`);
        }
      }

      res.json({ status: "processed", activated_steps: activatedSteps });
    } catch (err: any) {
      logger.error("Failed to complete workflow step", err);
      res.status(500).json({ error: "Step completion failed", details: err.message });
    }
  }
});

// ---------------------------------------------------------------------------
// Step Failed Endpoint
// ---------------------------------------------------------------------------
app.post("/coordinator/step-failed", async (req: Request, res: Response) => {
  const { task_id, step_id, workflow_id, error } = req.body;
  const inputId = req.body.incident_id || req.body.task_id;
  
  if (workflow_id && step_id) {
    logger.error(`Workflow step ${step_id} failed in workflow ${workflow_id}: ${error}`);
    try {
      await dbPool.query(
        "UPDATE workflow_steps SET status = 'failed', updated_at = NOW() WHERE id = $1",
        [step_id]
      );

      // Emit step.failed event
      try {
        await axios.post(`${observabilityUrl}/observability/events`, {
          type: "step.failed",
          sequence: 3,
          payload: { workflow_id, step_id, error },
          emitted_at: new Date().toISOString()
        });
      } catch (err: any) {
        logger.warn(`Failed to emit step.failed event: ${err.message}`);
      }

      // Check if workflow is finished (all terminal)
      const activeOrPending = await dbPool.query(
        "SELECT count(*) FROM workflow_steps WHERE workflow_id = $1 AND status IN ('pending', 'active', 'suspended')",
        [workflow_id]
      );

      if (parseInt(activeOrPending.rows[0].count) === 0) {
        logger.warn(`Workflow ${workflow_id} ended in failure.`);
        await dbPool.query(
          "UPDATE workflows SET status = 'failed', updated_at = NOW() WHERE id = $1",
          [workflow_id]
        );

        // Clean up Redis
        const allStepIds = await redis.smembers(`workflow:${workflow_id}:all_steps`);
        await redis.del(
          `workflow:${workflow_id}:status`,
          `workflow:${workflow_id}:all_steps`,
          ...allStepIds.map(sid => `workflow:${workflow_id}:step:${sid}:deps`)
        );

        // Emit workflow.completed (terminal failure) event
        try {
          await axios.post(`${observabilityUrl}/observability/events`, {
            type: "workflow.completed",
            sequence: 4,
            payload: { workflow_id, success: false },
            emitted_at: new Date().toISOString()
          });
        } catch (err: any) {
          logger.warn(`Failed to emit workflow.completed event: ${err.message}`);
        }
      }

      res.json({ status: "step_marked_failed" });
    } catch (err: any) {
      logger.error("Failed to update step failure status", err);
      res.status(500).json({ error: "Failed to update step failure", details: err.message });
    }
  } else {
    // Classification step failed fallback
    logger.error(`Task ${task_id} failed: ${error}`);
    try {
      await dbPool.query(
        "UPDATE multimodal_inputs SET processing_status = 'failed' WHERE id = $1",
        [inputId]
      );
      res.json({ status: "marked_failed" });
    } catch (err: any) {
      logger.error("Failed to mark input as failed", err);
      res.status(500).json({ error: "Database update failed", details: err.message });
    }
  }
});

export { app };

if (process.env.NODE_ENV !== "test") {
  app.listen(port, () => {
    logger.info(`Coordinator service listening on port ${port}`);
  });
}
