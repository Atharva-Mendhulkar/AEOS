import request from 'supertest';
import { v4 as uuidv4 } from 'uuid';

// Mock pg and ioredis before importing app
const mockPublish = jest.fn().mockResolvedValue(1);
const mockSet = jest.fn().mockResolvedValue('OK');
const mockSadd = jest.fn().mockResolvedValue(1);
const mockSmembers = jest.fn().mockResolvedValue([]);
const mockSismember = jest.fn().mockResolvedValue(0);
const mockSrem = jest.fn().mockResolvedValue(1);
const mockScard = jest.fn().mockResolvedValue(0);
const mockDel = jest.fn().mockResolvedValue(1);

const mockSend = jest.fn().mockResolvedValue([]);

jest.mock('kafkajs', () => {
  return {
    Kafka: jest.fn().mockImplementation(() => {
      return {
        producer: jest.fn().mockImplementation(() => {
          return {
            connect: jest.fn().mockResolvedValue(true),
            send: mockSend,
            disconnect: jest.fn().mockResolvedValue(true),
          };
        }),
      };
    }),
  };
});

jest.mock('ioredis', () => {
  return jest.fn().mockImplementation(() => {
    return {
      on: jest.fn(),
      publish: mockPublish,
      set: mockSet,
      sadd: mockSadd,
      smembers: mockSmembers,
      sismember: mockSismember,
      srem: mockSrem,
      scard: mockScard,
      del: mockDel,
    };
  });
});

const mockQuery = jest.fn();
const mockConnect = jest.fn();
jest.mock('pg', () => {
  return {
    Pool: jest.fn().mockImplementation(() => {
      return {
        on: jest.fn(),
        query: mockQuery,
        connect: mockConnect,
      };
    }),
  };
});

// Mock axios to prevent actual outgoing HTTP calls in tests
jest.mock('axios', () => {
  return {
    post: jest.fn().mockResolvedValue({ status: 200, data: {} }),
  };
});

import { app } from '../index';

describe('Coordinator Express App', () => {
  let mockClient: any;

  beforeEach(() => {
    jest.clearAllMocks();
    mockQuery.mockResolvedValue({ rows: [] });
    mockClient = {
      query: jest.fn().mockResolvedValue({ rows: [] }),
      release: jest.fn(),
    };
    mockConnect.mockResolvedValue(mockClient);
  });

  test('GET /health returns healthy status', async () => {
    const res = await request(app).get('/health');
    expect(res.status).toBe(200);
    expect(res.body).toMatchObject({ status: "healthy", service: "coordinator" });
  });

  test('POST /coordinator/route-input routes raw content and publishes to Redis', async () => {
    const payload = {
      input_id: uuidv4(),
    };

    const res = await request(app)
      .post('/coordinator/route-input')
      .send(payload);

    expect(res.status).toBe(200);
    expect(res.body.status).toBe('routing');
    expect(res.body.task_id).toBeDefined();
    expect(mockSend).toHaveBeenCalledWith({
      topic: 'agent_incident_analysis_tasks',
      messages: [{ value: expect.any(String) }]
    });
  });

  test('POST /coordinator/plan-ready writes plan and triggers first steps', async () => {
    const workflowId = uuidv4();
    const step1Id = uuidv4();
    const step2Id = uuidv4();

    const payload = {
      workflow_id: workflowId,
      steps: [
        {
          id: step1Id,
          agent_type: 'operations',
          action: { tool: 'gather_logs', params: { service: 'db' }, timeout_seconds: 30 },
          depends_on: [],
        },
        {
          id: step2Id,
          agent_type: 'compliance',
          action: { tool: 'verify_policy', params: { policy_id: '1' }, timeout_seconds: 30 },
          depends_on: [step1Id],
        }
      ]
    };

    // Mock DB queries for plan ingestion and step detail lookup in activateStep
    mockClient.query.mockResolvedValueOnce({ rows: [] }); // BEGIN
    mockClient.query.mockResolvedValueOnce({ rows: [] }); // Insert step 1
    mockClient.query.mockResolvedValueOnce({ rows: [] }); // Insert step 2
    mockClient.query.mockResolvedValueOnce({ rows: [] }); // COMMIT
    
    // For activateStep of step 1 (which has no depends_on)
    mockQuery.mockResolvedValueOnce({
      rows: [{
        id: step1Id,
        agent_type: 'operations',
        action: { tool: 'gather_logs', params: { service: 'db' }, timeout_seconds: 30 },
        depends_on: [],
      }]
    }); // SELECT step
    mockQuery.mockResolvedValueOnce({ rows: [] }); // UPDATE step to active
    mockQuery.mockResolvedValueOnce({ rows: [{ incident_id: uuidv4() }] }); // SELECT incident_id
    mockQuery.mockResolvedValueOnce({ rows: [] }); // SELECT completed steps (for output propagation)

    const res = await request(app)
      .post('/coordinator/plan-ready')
      .send(payload);

    expect(res.status).toBe(200);
    expect(res.body.status).toBe('executing');
    expect(res.body.activated_steps).toContain(step1Id);
    expect(mockSend).toHaveBeenCalledWith({
      topic: 'agent_operations_tasks',
      messages: [{ value: expect.any(String) }]
    });
  });

  test('POST /coordinator/step-complete (classification callback) creates incident and triggers planner', async () => {
    const workflowId = uuidv4();
    const taskId = uuidv4();
    const inputId = uuidv4();
    const payload = {
      task_id: taskId,
      workflow_id: workflowId,
      incident_id: inputId,
      output: {
        severity: 'high',
        confidence_score: 0.95,
        root_signature: 'sig-abc-123'
      },
      requires_escalation: false
    };

    // Deduplication check returns no duplicates
    mockClient.query.mockResolvedValueOnce({ rows: [] });
    // Inserts incident
    mockClient.query.mockResolvedValueOnce({ rows: [] });
    // Inserts workflow
    mockClient.query.mockResolvedValueOnce({ rows: [] });
    // Updates multimodal input status
    mockClient.query.mockResolvedValueOnce({ rows: [] });

    const res = await request(app)
      .post('/coordinator/step-complete')
      .send(payload);

    expect(res.status).toBe(200);
    expect(res.body.status).toBe('created');
    expect(res.body.incident_id).toBeDefined();
    expect(res.body.workflow_id).toBe(workflowId);
  });

  test('POST /coordinator/step-complete (execution callback) updates step status and checks DAG', async () => {
    const workflowId = uuidv4();
    const step1Id = uuidv4();
    const step2Id = uuidv4();
    const payload = {
      task_id: uuidv4(),
      step_id: step1Id,
      workflow_id: workflowId,
      output: { status: 'success' }
    };

    const incidentId = uuidv4();
    mockQuery.mockResolvedValueOnce({ rows: [{ incident_id: incidentId }] }); // SELECT workflow incident
    mockQuery.mockResolvedValueOnce({ rows: [{ agent_type: 'operations' }] }); // SELECT completed step agent
    mockQuery.mockResolvedValueOnce({ rows: [] }); // UPDATE completed step status/output

    // Redis mock setup: check if finished step releases step 2
    mockSmembers.mockResolvedValueOnce([step2Id]);
    mockSismember.mockResolvedValueOnce(1); // step 2 depends on step 1
    mockScard.mockResolvedValueOnce(0);     // remaining dependencies card is 0

    // mock activateStep for step 2
    mockQuery.mockResolvedValueOnce({
      rows: [{
        id: step2Id,
        agent_type: 'compliance',
        action: { tool: 'verify_policy', params: { policy_id: '1' }, timeout_seconds: 30 },
        depends_on: [step1Id],
      }]
    }); // SELECT step 2
    mockQuery.mockResolvedValueOnce({ rows: [] }); // UPDATE step 2 active
    mockQuery.mockResolvedValueOnce({ rows: [{ incident_id: incidentId }] }); // SELECT incident_id
    mockQuery.mockResolvedValueOnce({ rows: [{ id: step1Id, agent_type: 'operations', output: { status: 'success' } }] }); // SELECT completed steps (for output propagation)

    // Check if workflow is finished: count of active/pending steps > 0
    mockQuery.mockResolvedValueOnce({ rows: [{ count: '1' }] });

    const res = await request(app)
      .post('/coordinator/step-complete')
      .send(payload);

    expect(res.status).toBe(200);
    expect(res.body.status).toBe('processed');
    expect(res.body.activated_steps).toContain(step2Id);
    expect(mockSend).toHaveBeenCalledWith({
      topic: 'agent_compliance_tasks',
      messages: [{ value: expect.any(String) }]
    });
  });

  test('POST /coordinator/step-failed marks step as failed', async () => {
    const workflowId = uuidv4();
    const stepId = uuidv4();
    const payload = {
      task_id: uuidv4(),
      step_id: stepId,
      workflow_id: workflowId,
      error: 'Simulated execution timeout'
    };

    mockQuery.mockResolvedValueOnce({ rows: [{ incident_id: uuidv4() }] }); // SELECT workflow incident
    mockQuery.mockResolvedValueOnce({ rows: [{ agent_type: 'operations' }] }); // SELECT failed step agent
    mockQuery.mockResolvedValueOnce({ rows: [] }); // UPDATE step status failed
    mockQuery.mockResolvedValueOnce({ rows: [{ count: '0' }] }); // count active steps = 0 (workflow finished)
    mockQuery.mockResolvedValueOnce({ rows: [] }); // UPDATE workflow status failed

    const res = await request(app)
      .post('/coordinator/step-failed')
      .send(payload);

    expect(res.status).toBe(200);
    expect(res.body.status).toBe('step_marked_failed');
  });
});
