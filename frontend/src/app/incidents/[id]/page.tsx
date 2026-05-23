"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { useParams } from "next/navigation";
import { fetcher, apiClient } from "@/utils/api";
import { useWebSocket } from "@/providers/WebSocketProvider";

export default function IncidentDetail() {
  const { id: incidentId } = useParams();
  const { subscribeToWorkflow, events } = useWebSocket();
  const [integrityStatus, setIntegrityStatus] = useState<any>(null);
  const [checkingIntegrity, setCheckingIntegrity] = useState(false);

  // Fetch Incident
  const { data: incident, error: incidentErr, mutate: mutateInc } = useSWR(
    `/api/v1/incidents/${incidentId}`,
    fetcher
  );

  // Fetch Workflow (using SWR conditionally once incident is loaded)
  const workflowId = incident?.workflow_id;
  const { data: workflow, error: workflowErr, mutate: mutateWf } = useSWR(
    workflowId ? `/api/v1/workflows/${workflowId}` : null,
    fetcher
  );

  // Fetch Audit Logs
  const { data: auditLogs, error: auditErr, mutate: mutateAudit } = useSWR(
    incidentId ? `/api/v1/incidents/${incidentId}/audit` : null,
    fetcher
  );

  // Subscribe to WebSocket events when workflowId is available
  useEffect(() => {
    if (workflowId) {
      subscribeToWorkflow(workflowId);
    }
  }, [workflowId, subscribeToWorkflow]);

  // Reload caches when WebSocket signals execution activity
  useEffect(() => {
    if (events.length > 0) {
      const latestEvent = events[events.length - 1];
      if (latestEvent.workflow_id === workflowId) {
        console.log("WebSocket event matching current workflow detected. Reloading data...");
        mutateInc();
        mutateWf();
        mutateAudit();
      }
    }
  }, [events, workflowId, mutateInc, mutateWf, mutateAudit]);

  // Run cryptographic verification check
  const runIntegrityCheck = async () => {
    setCheckingIntegrity(true);
    setIntegrityStatus(null);
    try {
      // Direct call to validation endpoint using apiClient to include auth headers
      const res = await apiClient.get("/api/v1/observability/audit/validate-chain");
      // Using apiClient.get handles json parsing automatically
      setIntegrityStatus(res);
    } catch (e: any) {
      console.error(e);
      setIntegrityStatus({ status: "error", detail: e.message || "Failed verification connection." });
    } finally {
      setCheckingIntegrity(false);
    }
  };

  if (incidentErr) {
    return <div className="text-red-400">Failed to load incident detail.</div>;
  }

  if (!incident) {
    return (
      <div className="py-20 flex flex-col items-center justify-center gap-4">
        <div className="w-10 h-10 border-4 border-t-blue-500 border-r-transparent border-gray-200 rounded-full animate-spin"></div>
        <p className="text-xs text-gray-500 font-mono">Loading incident telemetry...</p>
      </div>
    );
  }

  // Build DAG workflow steps layout layers
  const rawSteps = workflow?.plan?.steps || [];
  
  // Layering sorting algorithm for clean visual presentation
  const buildLayers = (steps: any[]) => {
    const layers: any[][] = [];
    const processed = new Set<string>();
    let remaining = [...steps];

    while (remaining.length > 0) {
      const currentLayer = remaining.filter((step) =>
        (step.depends_on || []).every((depId: string) => processed.has(depId))
      );

      if (currentLayer.length === 0) {
        layers.push(remaining);
        break;
      }

      layers.push(currentLayer);
      currentLayer.forEach((step) => processed.add(step.id));
      remaining = remaining.filter((step) => !processed.has(step.id));
    }
    return layers;
  };

  const stepsLayers = buildLayers(rawSteps);

  return (
    <div className="space-y-6">
      {/* Back to Dashboard and Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Link href="/dashboard" className="text-xs text-blue-600 hover:underline flex items-center gap-1 font-mono">
              &larr; Back to Telemetry Streams
            </Link>
          </div>
          <h1 className="text-2xl font-extrabold tracking-tight text-black flex items-center gap-3">
            <span>Incident Console</span>
            <span className="text-xs font-mono bg-gray-50 border border-gray-200 px-2 py-1 rounded text-gray-600 font-normal shadow-sm">
              ID: {incidentId}
            </span>
          </h1>
        </div>

        {/* Cryptographic Chain Integrity Trigger */}
        <button
          onClick={runIntegrityCheck}
          disabled={checkingIntegrity}
          className="px-4 py-2 bg-white hover:bg-gray-50 border border-gray-200 rounded-lg text-xs font-mono text-gray-700 transition duration-150 flex items-center gap-2 hover:border-gray-300 disabled:opacity-40 shadow-sm"
        >
          {checkingIntegrity ? (
            <>
              <div className="w-3.5 h-3.5 border-2 border-t-blue-500 border-r-transparent border-gray-200 rounded-full animate-spin"></div>
              <span>Verifying Chaining Linkages...</span>
            </>
          ) : (
            <>
              <svg className="w-4 h-4 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              <span>Verify Cryptographic Chain</span>
            </>
          )}
        </button>
      </div>

      {/* Integrity Report Alert */}
      {integrityStatus && (
        <div
          className={`p-4 rounded-xl border flex items-start gap-3 font-mono text-xs shadow-sm ${
            integrityStatus.status === "valid"
              ? "bg-green-50 border-green-200 text-green-800"
              : integrityStatus.status === "tampered"
              ? "bg-red-50 border-red-200 text-red-800"
              : "bg-amber-50 border-amber-200 text-amber-800"
          }`}
        >
          <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            {integrityStatus.status === "valid" ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            )}
          </svg>
          <div className="space-y-1">
            <h4 className="font-extrabold text-sm capitalize">
              Cryptographic Integrity Audit: {integrityStatus.status === "valid" ? "Verified" : "Compromised"}
            </h4>
            <p>
              {integrityStatus.status === "valid"
                ? `All ${integrityStatus.validated_count} audit trail entries sequentially verified using SHA-256 block hashes. Zero links broken.`
                : integrityStatus.status === "tampered"
                ? `Tampering detected at block audit ID ${integrityStatus.compromised_id}. Chained linkage hash matches failed verification criteria.`
                : `Error performing verification: ${integrityStatus.detail}`}
            </p>
          </div>
        </div>
      )}

      {/* Incident Metadata & Workflow Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="glassmorphism p-6 rounded-xl space-y-4 lg:col-span-1 border border-gray-200 shadow-sm">
          <h3 className="font-bold text-black tracking-wide text-sm font-mono border-b border-gray-200 pb-2.5">
            Operational Telemetry
          </h3>
          <div className="grid grid-cols-2 gap-4 text-xs font-mono">
            <div>
              <span className="text-gray-500 block uppercase">Severity</span>
              <span className="text-black font-bold text-sm block mt-1 uppercase">{incident.severity}</span>
            </div>
            <div>
              <span className="text-gray-500 block uppercase">Status</span>
              <span className="text-black font-bold text-sm block mt-1 uppercase">{incident.status}</span>
            </div>
            <div>
              <span className="text-gray-500 block uppercase">Confidence</span>
              <span className="text-black font-bold text-sm block mt-1">{(incident.confidence_score * 100).toFixed(0)}%</span>
            </div>
            <div>
              <span className="text-gray-500 block uppercase">Workflow Connected</span>
              <span className="text-blue-600 font-bold block mt-1 truncate">
                {incident.workflow_id ? incident.workflow_id.substring(0, 8) + "..." : "None"}
              </span>
            </div>
            <div className="col-span-2">
              <span className="text-gray-500 block uppercase">Root Signature</span>
              <span className="text-gray-800 block mt-1 bg-gray-50 border border-gray-200 p-2.5 rounded font-mono text-[11px] leading-relaxed shadow-inner">
                {incident.root_signature || "Analysis processing in queue..."}
              </span>
            </div>
            <div className="col-span-2">
              <span className="text-gray-500 block uppercase">Ingestion Reference File</span>
              <span className="text-gray-600 block mt-1 font-mono text-[11px] truncate">
                {incident.source_input_ref || "Direct Text entry"}
              </span>
            </div>
          </div>
        </div>

        {/* Custom Visual DAG Workflow Chart */}
        <div className="glassmorphism p-6 rounded-xl space-y-4 lg:col-span-2 flex flex-col justify-between border border-gray-200 shadow-sm">
          <div>
            <h3 className="font-bold text-black tracking-wide text-sm font-mono border-b border-gray-200 pb-2.5 flex items-center justify-between">
              <span>DAG Execution Visualizer</span>
              <span className="text-xs text-gray-500 bg-gray-50 border border-gray-200 px-2 py-0.5 rounded font-normal shadow-sm">
                {workflow?.status?.toUpperCase() || "PENDING"}
              </span>
            </h3>
            <p className="text-xs text-gray-500 mt-2">
              Layered Directed Acyclic Graph tracking concurrent execution of planner steps.
            </p>
          </div>

          {rawSteps.length === 0 ? (
            <div className="py-24 text-center text-gray-500 text-xs font-mono">
              No workflow execution steps generated.
            </div>
          ) : (
            <div className="relative mt-6 border border-gray-200 bg-gray-50 p-6 rounded-xl overflow-x-auto min-h-[300px] flex flex-col justify-center shadow-inner">
              {/* Layers wrapper */}
              <div className="flex justify-between items-center gap-12 min-w-[600px] relative">
                {stepsLayers.map((layer, lIdx) => (
                  <div key={lIdx} className="flex flex-col gap-6 justify-center items-center relative z-10">
                    {layer.map((step) => {
                      const status = (step.status || "pending").toLowerCase();
                      const statusColor =
                        status === "completed"
                          ? "border-green-500 bg-green-50 text-green-600 shadow-sm"
                          : status === "running"
                          ? "border-blue-500 bg-blue-50 text-blue-600 animate-pulse shadow-sm"
                          : status === "failed"
                          ? "border-red-500 bg-red-50 text-red-600 shadow-sm"
                          : status === "suspended"
                          ? "border-amber-500 bg-amber-50 text-amber-600 shadow-sm"
                          : "border-gray-300 bg-white text-gray-500 shadow-sm";

                      return (
                        <div
                          key={step.id}
                          className={`w-40 border p-3 rounded-lg flex flex-col justify-between font-mono text-[10px] transition-all duration-300 ${statusColor}`}
                        >
                          <div className="font-extrabold uppercase truncate tracking-wider">{step.agent_type}</div>
                          <div className="mt-1 truncate opacity-80">{step.action.tool}</div>
                          <div className="mt-2 pt-1.5 border-t border-current/20 flex items-center justify-between text-[8px] opacity-70">
                            <span>ID: {step.id.substring(0, 4)}...</span>
                            <span className="uppercase font-bold">{step.status}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ))}

                {/* SVG Connections connector overlay */}
                <div className="absolute inset-0 pointer-events-none z-0">
                  {/* Connectors will be drawn natively by HTML layouts or simplified arrows. 
                      For clean browser presentation, CSS borders and flex positions represent linkages naturally. */}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Audit Logs Timeline */}
      <div className="glassmorphism p-6 rounded-xl space-y-4 border border-gray-200 shadow-sm">
        <h3 className="font-bold text-black tracking-wide text-sm font-mono border-b border-gray-200 pb-2.5">
          Tamper-Evident Incident History
        </h3>

        {!auditLogs ? (
          <div className="py-12 text-center text-xs font-mono text-gray-500">
            Polling block records...
          </div>
        ) : auditLogs.length === 0 ? (
          <div className="py-12 text-center text-xs font-mono text-gray-500">
            No audit logs captured for this incident.
          </div>
        ) : (
          <div className="space-y-4 relative before:absolute before:left-3 before:top-2 before:bottom-2 before:w-0.5 before:bg-gray-200">
            {auditLogs.map((log: any, idx: number) => {
              const risk = log.risk_score || 0;
              return (
                <div key={log.id} className="relative pl-10 flex flex-col md:flex-row md:items-start gap-4">
                  {/* Timeline point */}
                  <span className="absolute left-1.5 top-2 w-3.5 h-3.5 rounded-full border-4 border-white bg-blue-500 z-10 shadow-sm"></span>

                  {/* Log Content Card */}
                  <div className="glassmorphism p-4 rounded-xl flex-1 space-y-2 relative border border-gray-200 hover:border-gray-300 transition shadow-sm bg-white/50">
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 pb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-black uppercase bg-gray-100 border border-gray-200 px-2.5 py-1 rounded font-mono shadow-sm">
                          {log.agent_identity}
                        </span>
                        <span className="text-xs font-mono text-gray-500 font-bold">
                          {log.event_type}
                        </span>
                      </div>
                      
                      {/* Risk Score Indicator */}
                      <div className="flex items-center gap-2">
                        {risk > 0 && (
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                              risk >= 9.0
                                ? "bg-red-50 text-red-600 border border-red-200"
                                : risk >= 7.0
                                ? "bg-orange-50 text-orange-600 border border-orange-200"
                                : "bg-blue-50 text-blue-600 border border-blue-200"
                            }`}
                          >
                            Risk: {risk.toFixed(1)}
                          </span>
                        )}
                        
                        {/* Link Hash Verification Emblem */}
                        <div
                          className="flex items-center gap-1.5 px-2 py-0.5 bg-gray-50 rounded border border-gray-200 text-[10px] font-mono text-gray-500 shadow-sm"
                          title={`Prev Hash: ${log.prev_entry_hash || "genesis"}`}
                        >
                          <svg className="w-3 h-3 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                          </svg>
                          <span>Chained</span>
                        </div>
                      </div>
                    </div>

                    <p className="text-xs text-gray-700 leading-relaxed font-mono">
                      {log.action_description}
                    </p>

                    {/* Expandable Inputs/Outputs details */}
                    {(log.inputs || log.outputs) && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3 pt-3 border-t border-gray-200 text-[10px] font-mono text-gray-500">
                        {log.inputs && Object.keys(log.inputs).length > 0 && (
                          <div className="bg-gray-50 p-2 rounded border border-gray-200 shadow-inner">
                            <span className="text-gray-500 block uppercase font-bold mb-1">Inputs</span>
                            <pre className="overflow-x-auto text-[10px] leading-relaxed text-gray-700">
                              {JSON.stringify(log.inputs, null, 2)}
                            </pre>
                          </div>
                        )}
                        {log.outputs && Object.keys(log.outputs).length > 0 && (
                          <div className="bg-gray-50 p-2 rounded border border-gray-200 shadow-inner">
                            <span className="text-gray-500 block uppercase font-bold mb-1">Outputs</span>
                            <pre className="overflow-x-auto text-[10px] leading-relaxed text-gray-700">
                              {JSON.stringify(log.outputs, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}

                    <div className="text-[9px] text-gray-500 font-mono text-right pt-1">
                      {new Date(log.timestamp).toLocaleString()}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
