"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { fetcher } from "@/utils/api";
import { useWebSocket } from "@/providers/WebSocketProvider";

export default function Dashboard() {
  const [limit] = useState(10);
  const [offset, setOffset] = useState(0);

  const { data: incidents, error, mutate } = useSWR(
    `/api/v1/incidents?limit=${limit}&offset=${offset}`,
    fetcher,
    { refreshInterval: 5000 } // Poll every 5s as a fallback
  );

  const { events } = useWebSocket();

  // Trigger SWR revalidation whenever a relevant websocket event is received
  useEffect(() => {
    if (events.length > 0) {
      const latestEvent = events[events.length - 1];
      const type = latestEvent.event_type || "";
      if (
        type.includes("classified") || 
        type.includes("completed") || 
        type.includes("failed") || 
        type.includes("triggered") || 
        type.includes("resolved")
      ) {
        console.log(`Websocket event '${type}' detected. Mutating incidents cache.`);
        mutate();
      }
    }
  }, [events, mutate]);

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 p-6 rounded-xl text-red-200">
        <h3 className="font-bold text-lg mb-2">Error Connecting to Gateway</h3>
        <p>{error.message}</p>
        <button
          onClick={() => mutate()}
          className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm font-semibold transition"
        >
          Retry Connection
        </button>
      </div>
    );
  }

  // Derived KPI Stats
  const list = incidents || [];
  const totalCount = list.length;
  const criticalCount = list.filter((i: any) => i.severity?.toLowerCase() === "critical").length;
  const activeCount = list.filter((i: any) => i.status?.toLowerCase() === "active" || i.status?.toLowerCase() === "routing").length;
  const escalatedCount = list.filter((i: any) => i.status?.toLowerCase() === "escalated").length;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-white">Incident Resolution Center</h1>
          <p className="text-sm text-gray-400 mt-1">Real-time telemetry and autonomous remediation flow control.</p>
        </div>
        <Link
          href="/submit"
          className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-semibold shadow-glow transition duration-200 flex items-center gap-2 w-fit"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
          </svg>
          Ingest Incident
        </Link>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1 */}
        <div className="glassmorphism p-5 rounded-xl flex items-center justify-between">
          <div className="space-y-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 font-mono">Total Tracked</span>
            <h3 className="text-3xl font-extrabold text-white tracking-tight">{totalCount}</h3>
          </div>
          <div className="p-3 bg-blue-600/10 rounded-lg text-blue-400">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
        </div>

        {/* KPI 2 */}
        <div className="glassmorphism p-5 rounded-xl flex items-center justify-between">
          <div className="space-y-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 font-mono">Active Incidents</span>
            <h3 className="text-3xl font-extrabold text-white tracking-tight">{activeCount}</h3>
          </div>
          <div className="p-3 bg-glowEmerald/10 rounded-lg text-glowEmerald">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
        </div>

        {/* KPI 3 */}
        <div className="glassmorphism p-5 rounded-xl flex items-center justify-between">
          <div className="space-y-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 font-mono">Escalations Pending</span>
            <h3 className="text-3xl font-extrabold text-white tracking-tight">{escalatedCount}</h3>
          </div>
          <div className="p-3 bg-glowAmber/10 rounded-lg text-glowAmber">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
        </div>

        {/* KPI 4 */}
        <div className="glassmorphism p-5 rounded-xl flex items-center justify-between">
          <div className="space-y-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-gray-500 font-mono">Critical Tier</span>
            <h3 className="text-3xl font-extrabold text-glow-rose text-glowRose tracking-tight">{criticalCount}</h3>
          </div>
          <div className="p-3 bg-glowRose/10 rounded-lg text-glowRose">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        </div>
      </div>

      {/* Incidents Table / Main list */}
      <div className="glassmorphism rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/20">
          <h3 className="font-bold text-white tracking-wide text-sm font-mono">Telemetry Streams</h3>
          <span className="text-xs text-gray-400 bg-slate-900 border border-slate-800 px-2 py-1 rounded">
            Live Feed Active
          </span>
        </div>

        {!incidents ? (
          <div className="py-20 flex flex-col items-center justify-center gap-4">
            <div className="w-10 h-10 border-4 border-t-blue-500 border-r-transparent border-slate-800 rounded-full animate-spin"></div>
            <p className="text-xs text-gray-500 font-mono">Polling operational matrix...</p>
          </div>
        ) : list.length === 0 ? (
          <div className="py-24 text-center space-y-4">
            <div className="text-gray-600 inline-block p-4 bg-slate-900 border border-slate-850 rounded-full">
              <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <p className="text-sm text-gray-400">No incidents ingested or tracked in current period.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-850 text-xs font-semibold text-gray-400 bg-slate-950/30 uppercase tracking-wider font-mono">
                  <th className="px-6 py-4">Incident ID</th>
                  <th className="px-6 py-4">Severity</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4">Root Signature</th>
                  <th className="px-6 py-4">Created Time</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-850/50 text-sm font-medium">
                {list.map((inc: any) => {
                  const severity = (inc.severity || "unknown").toLowerCase();
                  const status = (inc.status || "unknown").toLowerCase();

                  return (
                    <tr key={inc.id} className="hover:bg-slate-900/40 transition duration-150">
                      <td className="px-6 py-4 font-mono text-xs text-blue-400">
                        <Link href={`/incidents/${inc.id}`} className="hover:underline">
                          {inc.id.substring(0, 8)}...
                        </Link>
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold uppercase ${
                            severity === "critical"
                              ? "bg-red-500/10 text-red-400 border border-red-500/20 text-glow-rose"
                              : severity === "high"
                              ? "bg-orange-500/10 text-orange-400 border border-orange-500/20 text-glow-amber"
                              : severity === "medium"
                              ? "bg-yellow-500/10 text-yellow-400 border border-yellow-500/20"
                              : "bg-green-500/10 text-green-400 border border-green-500/20 text-glow-green"
                          }`}
                        >
                          {inc.severity || "LOW"}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
                            status === "active" || status === "running"
                              ? "bg-blue-500/10 text-blue-400"
                              : status === "escalated"
                              ? "bg-glowAmber/15 text-glowAmber animate-pulse"
                              : status === "resolved" || status === "completed"
                              ? "bg-glowEmerald/10 text-glowEmerald"
                              : "bg-gray-500/10 text-gray-400"
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              status === "active" || status === "running"
                                ? "bg-blue-500"
                                : status === "escalated"
                                ? "bg-glowAmber"
                                : status === "resolved" || status === "completed"
                                ? "bg-glowEmerald"
                                : "bg-gray-500"
                            }`}
                          />
                          {inc.status || "IDLE"}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-gray-300 font-mono text-xs max-w-xs truncate">
                        {inc.root_signature || "Ingestion Preprocessing..."}
                      </td>
                      <td className="px-6 py-4 text-gray-400 font-mono text-xs">
                        {new Date(inc.created_at).toLocaleString()}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Link
                          href={`/incidents/${inc.id}`}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-blue-600/20 hover:text-blue-400 text-gray-300 border border-slate-700 hover:border-blue-500/50 rounded-lg text-xs font-semibold transition"
                        >
                          <span>Open Console</span>
                          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination controls */}
        <div className="px-6 py-4 border-t border-slate-850 flex items-center justify-between text-xs font-mono">
          <button
            onClick={() => setOffset((o) => Math.max(0, o - limit))}
            disabled={offset === 0}
            className="px-3 py-1.5 bg-slate-900 border border-slate-800 rounded text-gray-400 hover:text-white disabled:opacity-30 disabled:pointer-events-none transition"
          >
            Previous
          </button>
          <span className="text-gray-500">Offset: {offset}</span>
          <button
            onClick={() => setOffset((o) => o + limit)}
            disabled={list.length < limit}
            className="px-3 py-1.5 bg-slate-900 border border-slate-800 rounded text-gray-400 hover:text-white disabled:opacity-30 disabled:pointer-events-none transition"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
