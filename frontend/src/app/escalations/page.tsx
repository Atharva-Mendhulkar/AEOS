"use client";

import React, { useEffect, useState } from "react";
import useSWR from "swr";
import { fetcher, apiClient } from "@/utils/api";
import { useWebSocket } from "@/providers/WebSocketProvider";
import { RoleGate, useRole } from "@/hooks/useRole";

export default function EscalationQueue() {
  const { data: escalations, error, mutate } = useSWR(
    "/api/v1/escalations/pending",
    fetcher,
    { refreshInterval: 5000 }
  );

  const { events } = useWebSocket();
  const { role } = useRole();
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Modal State for MODIFIED action flow
  const [modifyingEscalation, setModifyingEscalation] = useState<any | null>(null);
  const [modifiedActionJson, setModifiedActionJson] = useState<string>("");

  // Trigger mutate when WebSocket notifies about escalations
  useEffect(() => {
    if (events.length > 0) {
      const latestEvent = events[events.length - 1];
      const type = latestEvent.event_type || "";
      if (type.includes("escalation") || type.includes("resolved") || type.includes("triggered")) {
        console.log(`Websocket escalation event: ${type}. Re-syncing pending queue.`);
        mutate();
      }
    }
  }, [events, mutate]);

  const handleRespond = async (id: string, decision: "approve" | "reject" | "modify", notesText?: string) => {
    setSubmittingId(id);
    setErrorMessage(null);
    try {
      const formData = new FormData();
      formData.append("decision", decision);
      formData.append("notes", notesText || `Action ${decision}d by operator`);

      await apiClient.postMultipart(`/api/v1/escalations/${id}/respond`, formData);
      
      // Close modal if open
      setModifyingEscalation(null);
      // Re-fetch data
      mutate();
    } catch (e: any) {
      console.error(e);
      setErrorMessage(e.message || "Failed to submit decision to gateway.");
    } finally {
      setSubmittingId(null);
    }
  };

  const openModifyModal = (esc: any) => {
    setModifyingEscalation(esc);
    setModifiedActionJson(JSON.stringify(esc, null, 2));
  };

  if (error) {
    return <div className="text-red-400">Failed to load escalation queue.</div>;
  }

  const list = escalations || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-black">Manual Intervention & Escalations</h1>
        <p className="text-sm text-gray-500 mt-1">Review actions suspended by runtime policy governance score limit gates.</p>
      </div>

      {errorMessage && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-200 rounded-xl text-xs font-mono">
          <p className="font-bold">Execution Failed:</p>
          <p>{errorMessage}</p>
        </div>
      )}

      {!escalations ? (
        <div className="py-20 flex flex-col items-center justify-center gap-4">
          <div className="w-10 h-10 border-4 border-t-blue-500 border-r-transparent border-gray-200 rounded-full animate-spin"></div>
          <p className="text-xs text-gray-500 font-mono">Querying governance engine...</p>
        </div>
      ) : list.length === 0 ? (
        <div className="py-20 text-center space-y-4 glassmorphism rounded-xl border border-gray-200">
          <div className="text-gray-400 inline-block p-4 bg-gray-50 border border-gray-200 rounded-full">
            <svg className="w-8 h-8 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <h3 className="font-bold text-black text-sm">Escalation Queue Clear</h3>
          <p className="text-xs text-gray-500 max-w-sm mx-auto">No steps are currently suspended or waiting for manual intervention.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {list.map((esc: any) => {
            const risk = esc.risk_score || 0.0;
            return (
              <div
                key={esc.id}
                className="glassmorphism p-6 rounded-xl border border-gray-200 flex flex-col justify-between gap-5 relative hover:border-gray-300 transition shadow-sm"
              >
                {/* Risk score pill badge */}
                <div className="absolute top-6 right-6">
                  <span
                    className={`px-2.5 py-1 rounded text-xs font-mono font-extrabold border ${
                      risk >= 9.0
                        ? "bg-red-500/10 border-red-500/20 text-red-400 text-glow-rose shadow-glowRed"
                        : "bg-orange-500/10 border-orange-500/20 text-orange-400 text-glow-amber shadow-glowOrange"
                    }`}
                  >
                    Risk: {risk.toFixed(1)}
                  </span>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-blue-400 font-extrabold uppercase bg-blue-600/10 px-2 py-0.5 rounded">
                      {esc.agent_type}
                    </span>
                    <span className="text-[10px] font-mono text-gray-500">
                      Tier: {esc.tier || "Tier 1"}
                    </span>
                  </div>

                  <h3 className="font-bold text-black tracking-wide text-sm font-mono truncate max-w-[70%]">
                    {esc.incident_summary}
                  </h3>

                  <div className="space-y-1 text-[11px] font-mono text-gray-500 bg-gray-50 p-3 rounded-lg border border-gray-200">
                    <div>
                      <span className="text-gray-500">Step ID: </span>
                      <span className="text-black">{esc.step_id.substring(0, 8)}...</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Incident/Wf ID: </span>
                      <span className="text-black">{esc.workflow_id.substring(0, 8)}...</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Suspended: </span>
                      <span className="text-black">{new Date(esc.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                </div>

                {/* Operations Buttons */}
                <div className="pt-3 border-t border-gray-200 flex items-center justify-between gap-3">
                  <RoleGate
                    roles={["admin", "operator"]}
                    fallback={
                      <div className="text-[10px] font-mono text-gray-500 leading-tight">
                        🔒 Read-only view for {role}. Requires Operator or Admin role.
                      </div>
                    }
                  >
                    <div className="flex gap-2 w-full">
                      <button
                        onClick={() => handleRespond(esc.id, "approve")}
                        disabled={submittingId !== null}
                        className="flex-1 py-2 bg-green-50 hover:bg-green-100 border border-green-200 hover:border-green-300 text-green-700 rounded-lg text-xs font-bold transition disabled:opacity-40"
                      >
                        Approve
                      </button>
                      
                      <button
                        onClick={() => openModifyModal(esc)}
                        disabled={submittingId !== null}
                        className="flex-1 py-2 bg-blue-50 hover:bg-blue-100 border border-blue-200 hover:border-blue-300 text-blue-700 rounded-lg text-xs font-bold transition disabled:opacity-40"
                      >
                        Modify
                      </button>

                      <button
                        onClick={() => handleRespond(esc.id, "reject")}
                        disabled={submittingId !== null}
                        className="flex-1 py-2 bg-red-50 hover:bg-red-100 border border-red-200 hover:border-red-300 text-red-700 rounded-lg text-xs font-bold transition disabled:opacity-40"
                      >
                        Reject
                      </button>
                    </div>
                  </RoleGate>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modify Action Configuration Modal */}
      {modifyingEscalation && (
        <div className="fixed inset-0 bg-gray-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-xl bg-white border border-gray-200 rounded-xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-gray-200 pb-3">
              <h3 className="font-extrabold text-black text-base font-mono">Modify Action Scope</h3>
              <button
                onClick={() => setModifyingEscalation(null)}
                className="text-gray-500 hover:text-black transition font-mono text-sm"
              >
                ✕ Close
              </button>
            </div>

            <div className="space-y-2">
              <p className="text-xs text-gray-500">
                Adjust step properties, input variables, or tool details to safely resume execution:
              </p>
              <textarea
                value={modifiedActionJson}
                onChange={(e) => setModifiedActionJson(e.target.value)}
                rows={10}
                className="w-full bg-gray-50 border border-gray-200 text-xs font-mono text-black rounded-lg p-3 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setModifyingEscalation(null)}
                className="px-4 py-2 border border-gray-200 hover:border-gray-300 text-gray-600 bg-white rounded-lg text-xs font-semibold shadow-sm transition"
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  handleRespond(modifyingEscalation.id, "modify", modifiedActionJson)
                }
                disabled={submittingId !== null}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold transition flex items-center gap-1.5"
              >
                {submittingId ? (
                  <>
                    <div className="w-3 h-3 border-2 border-t-white border-r-transparent border-slate-400 rounded-full animate-spin"></div>
                    <span>Saving...</span>
                  </>
                ) : (
                  <span>Submit Modified Action</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
