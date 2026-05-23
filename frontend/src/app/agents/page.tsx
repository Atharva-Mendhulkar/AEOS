"use client";

import React, { useEffect, useState } from "react";
import { useWebSocket } from "@/providers/WebSocketProvider";
import { apiClient } from "@/utils/api";

interface AgentState {
  name: string;
  role: string;
  status: "active" | "idle" | "blocked";
  activeSteps: number;
  lastActive: string;
  description: string;
}

const initialAgents: AgentState[] = [
  {
    name: "Incident Analysis Agent",
    role: "analysis",
    status: "idle",
    activeSteps: 0,
    lastActive: "System startup",
    description: "Ingests and parses multimodal inputs. Uses Gemini LLM to classify severity and build root signatures.",
  },
  {
    name: "Planner Agent",
    role: "planner",
    status: "idle",
    activeSteps: 0,
    lastActive: "System startup",
    description: "Constructs execution Directed Acyclic Graphs (DAG) mapping dependency step paths for resolution.",
  },
  {
    name: "Governance Agent",
    role: "governance",
    status: "idle",
    activeSteps: 0,
    lastActive: "System startup",
    description: "Enforces pre-execution risk checks and validation gating limits before specialist actions launch.",
  },
  {
    name: "Workflow Engine",
    role: "engine",
    status: "idle",
    activeSteps: 0,
    lastActive: "System startup",
    description: "Coordinates DAG state validation, polling, step resolution hooks, and Celery task execution logs.",
  },
  {
    name: "Escalation Agent",
    role: "escalation",
    status: "idle",
    activeSteps: 0,
    lastActive: "System startup",
    description: "Handles suspended approval items, operators notification webhooks, and manual response actions.",
  },
  {
    name: "Recovery Agent",
    role: "recovery",
    status: "idle",
    activeSteps: 0,
    lastActive: "System startup",
    description: "Evaluates failure transients and initiates plan retries or replanning requests on critical failures.",
  },
  {
    name: "Memory Agent",
    role: "memory",
    status: "idle",
    activeSteps: 0,
    lastActive: "System startup",
    description: "Manages state checkpoint restoration, audits trail records, and logs tamper-evident block hashes.",
  },
  {
    name: "Operations Specialist",
    role: "operations",
    status: "idle",
    activeSteps: 0,
    lastActive: "System startup",
    description: "Executes target infrastructure shell commands, system reboots, and automation scripts.",
  },
  {
    name: "Compliance Specialist",
    role: "compliance",
    status: "idle",
    activeSteps: 0,
    lastActive: "System startup",
    description: "Performs audit logging, updates rules policy blocks, and runs regulatory validation telemetry.",
  },
];

export default function AgentCoordinationMap() {
  const [agents, setAgents] = useState<AgentState[]>(initialAgents);
  const { events, status } = useWebSocket();
  const lastProcessedIndexRef = React.useRef(0);

  // Fetch initial agent states on mount/reconnect
  useEffect(() => {
    if (status !== "connected") return;

    const fetchAgentStates = async () => {
      try {
        const data = await apiClient.get("/api/v1/observability/agents");
        setAgents((prev) => {
          return prev.map((agent) => {
            const roleKey = agent.role.toLowerCase();
            if (data && data[roleKey]) {
              const persisted = data[roleKey];
              return {
                ...agent,
                status: (persisted.status || "idle").toLowerCase() as "active" | "idle" | "blocked",
                activeSteps: persisted.active_steps !== undefined ? persisted.active_steps : 0,
                lastActive: persisted.last_active 
                  ? new Date(persisted.last_active).toLocaleTimeString() 
                  : agent.lastActive,
              };
            }
            return agent;
          });
        });
      } catch (err) {
        console.error("Failed to fetch initial agent states:", err);
      }
    };

    fetchAgentStates();
  }, [status]);

  // Listen to agent.state_changed WebSocket events
  useEffect(() => {
    if (events.length > lastProcessedIndexRef.current) {
      const newEvents = events.slice(lastProcessedIndexRef.current);
      lastProcessedIndexRef.current = events.length;

      setAgents((prev) => {
        let updatedAgents = [...prev];
        
        for (const event of newEvents) {
          if (event.event_type === "agent.state_changed" || event.type === "agent.state_changed") {
            const payload = event.payload || event;
            const targetRole = payload.agent_role || payload.agent;
            const newStatus = payload.status || "idle";
            const steps = payload.active_steps !== undefined ? payload.active_steps : 0;
            const eventTime = event.emitted_at || event.timestamp || new Date().toISOString();

            console.log(`Processing event: Agent ${targetRole} changed state to ${newStatus}`);

            updatedAgents = updatedAgents.map((agent) => {
              if (agent.role.toLowerCase() === String(targetRole).toLowerCase() || 
                  agent.name.toLowerCase().includes(String(targetRole).toLowerCase())) {
                return {
                  ...agent,
                  status: newStatus.toLowerCase() as "active" | "idle" | "blocked",
                  activeSteps: steps,
                  lastActive: new Date(eventTime).toLocaleTimeString(),
                };
              }
              return agent;
            });
          }
        }
        
        return updatedAgents;
      });
    }
  }, [events]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-black">Specialist Agent Orchestration</h1>
        <p className="text-sm text-gray-500 mt-1">
          Active-state monitoring grid tracking the 9 sub-agents of the AEOS remediation layer.
        </p>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {agents.map((agent) => {
          const status = agent.status;
          
          const statusConfig =
            status === "active"
              ? {
                  badge: "bg-green-100 border-green-200 text-green-700",
                  dot: "bg-green-500 pulse-glow",
                  cardBorder: "border-green-300 hover:border-green-400 shadow-sm",
                }
              : status === "blocked"
              ? {
                  badge: "bg-red-100 border-red-200 text-red-700",
                  dot: "bg-red-500 pulse-glow",
                  cardBorder: "border-red-300 hover:border-red-400 shadow-sm",
                }
              : {
                  badge: "bg-gray-100 border-gray-200 text-gray-500",
                  dot: "bg-gray-400",
                  cardBorder: "border-gray-200 hover:border-gray-300",
                };

          return (
            <div
              key={agent.role}
              className={`glassmorphism p-5 rounded-xl border flex flex-col justify-between gap-4 transition-all duration-300 ${statusConfig.cardBorder}`}
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2 border-b border-gray-200 pb-2.5">
                  <h3 className="font-extrabold text-black text-sm tracking-wide font-mono truncate">
                    {agent.name}
                  </h3>
                  
                  {/* Status Indicator */}
                  <span
                    className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase border ${statusConfig.badge}`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${statusConfig.dot}`}></span>
                    {agent.status}
                  </span>
                </div>

                <p className="text-xs text-gray-500 leading-relaxed min-h-[48px]">{agent.description}</p>
              </div>

              {/* Telemetry info */}
              <div className="grid grid-cols-2 gap-4 text-[10px] font-mono text-gray-500 bg-gray-50 p-3 rounded-lg border border-gray-200">
                <div>
                  <span className="block uppercase text-gray-500 font-bold">Active Steps</span>
                  <span className="text-black font-bold block mt-0.5">{agent.activeSteps}</span>
                </div>
                <div>
                  <span className="block uppercase text-gray-500 font-bold">Last Activity</span>
                  <span className="text-gray-600 block mt-0.5 truncate">{agent.lastActive}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
