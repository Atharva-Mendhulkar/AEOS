"use client";

import React, { useEffect, useState } from "react";
import { useWebSocket } from "@/providers/WebSocketProvider";

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
  const { events } = useWebSocket();

  // Listen to agent.state_changed WebSocket events
  useEffect(() => {
    if (events.length > 0) {
      const latestEvent = events[events.length - 1];
      if (latestEvent.event_type === "agent.state_changed" || latestEvent.type === "agent.state_changed") {
        const payload = latestEvent.payload || latestEvent;
        const targetRole = payload.agent_role || payload.agent;
        const newStatus = payload.status || "idle";
        const steps = payload.active_steps !== undefined ? payload.active_steps : 0;

        console.log(`Agent ${targetRole} changed state to ${newStatus}`);

        setAgents((prev) =>
          prev.map((agent) => {
            if (agent.role.toLowerCase() === String(targetRole).toLowerCase() || 
                agent.name.toLowerCase().includes(String(targetRole).toLowerCase())) {
              return {
                ...agent,
                status: newStatus.toLowerCase() as "active" | "idle" | "blocked",
                activeSteps: steps,
                lastActive: new Date().toLocaleTimeString(),
              };
            }
            return agent;
          })
        );
      }
    }
  }, [events]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-white">Specialist Agent Orchestration</h1>
        <p className="text-sm text-gray-400 mt-1">
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
                  badge: "bg-glowEmerald/10 border-glowEmerald/20 text-glowEmerald text-glow-green",
                  dot: "bg-glowEmerald pulse-glow",
                  cardBorder: "border-glowEmerald/35 hover:border-glowEmerald/60 shadow-glowGreen",
                }
              : status === "blocked"
              ? {
                  badge: "bg-glowRose/10 border-glowRose/20 text-glowRose text-glow-rose",
                  dot: "bg-glowRose pulse-glow",
                  cardBorder: "border-glowRose/35 hover:border-glowRose/60 shadow-glowRed",
                }
              : {
                  badge: "bg-slate-800 border-slate-750 text-gray-400",
                  dot: "bg-gray-600",
                  cardBorder: "border-slate-800 hover:border-slate-750",
                };

          return (
            <div
              key={agent.role}
              className={`glassmorphism p-5 rounded-xl border flex flex-col justify-between gap-4 transition-all duration-300 ${statusConfig.cardBorder}`}
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2 border-b border-slate-850 pb-2.5">
                  <h3 className="font-extrabold text-white text-sm tracking-wide font-mono truncate">
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

                <p className="text-xs text-gray-400 leading-relaxed min-h-[48px]">{agent.description}</p>
              </div>

              {/* Telemetry info */}
              <div className="grid grid-cols-2 gap-4 text-[10px] font-mono text-gray-500 bg-slate-950/40 p-3 rounded-lg border border-slate-900">
                <div>
                  <span className="block uppercase text-gray-600 font-bold">Active Steps</span>
                  <span className="text-white font-bold block mt-0.5">{agent.activeSteps}</span>
                </div>
                <div>
                  <span className="block uppercase text-gray-600 font-bold">Last Activity</span>
                  <span className="text-gray-300 block mt-0.5 truncate">{agent.lastActive}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
