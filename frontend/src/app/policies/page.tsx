"use client";

import React, { useEffect, useState } from "react";
import useSWR from "swr";
import { fetcher, apiClient } from "@/utils/api";
import { useWebSocket } from "@/providers/WebSocketProvider";
import { RoleGate, useRole } from "@/hooks/useRole";

const defaultPolicyTemplates: Record<string, string> = {
  risk_threshold: `{
  "suspend_threshold": 7.0,
  "halt_threshold": 9.0
}`,
  permission: `{
  "agent_type": "operations",
  "allowed_tools": ["gather_logs", "restart_service"],
  "denied_tools": []
}`,
  anomaly: `{
  "max_frequency_per_minute": 30,
  "max_consecutive_identical_actions": 5
}`,
  retention: `{
  "retention_days": 90
}`
};

export default function PolicyManager() {
  const { data: policies, error, mutate } = useSWR("/api/v1/policies", fetcher);
  const { events } = useWebSocket();
  const { role } = useRole();

  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Modals visibility state
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editingPolicy, setEditingPolicy] = useState<any | null>(null);
  const [deactivatingPolicy, setDeactivatingPolicy] = useState<any | null>(null);

  // Form states
  const [name, setName] = useState("");
  const [policyType, setPolicyType] = useState("risk_threshold");
  const [configJson, setConfigJson] = useState(defaultPolicyTemplates.risk_threshold);

  // Sync edit form fields
  useEffect(() => {
    if (editingPolicy) {
      setName(editingPolicy.name);
      setConfigJson(
        typeof editingPolicy.config === "string"
          ? editingPolicy.config
          : JSON.stringify(editingPolicy.config, null, 2)
      );
    }
  }, [editingPolicy]);

  // Handle template change based on type selection
  useEffect(() => {
    if (!editingPolicy) {
      setConfigJson(defaultPolicyTemplates[policyType] || defaultPolicyTemplates.risk_threshold);
    }
  }, [policyType, editingPolicy]);

  // Live WebSocket updates
  useEffect(() => {
    if (events.length > 0) {
      const latestEvent = events[events.length - 1];
      if (latestEvent.event_type?.includes("policy")) {
        console.log("Policy update event received. Mutating list.");
        mutate();
      }
    }
  }, [events, mutate]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    // Validate JSON config locally
    try {
      JSON.parse(configJson);
    } catch (err) {
      setErrorMessage("Configuration payload is not valid JSON.");
      return;
    }

    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("name", name);
      formData.append("policy_type", policyType);
      formData.append("config", configJson);

      await apiClient.postMultipart("/api/v1/policies", formData);
      setCreateModalOpen(false);
      resetForm();
      mutate();
    } catch (e: any) {
      setErrorMessage(e.message || "Failed to create policy.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!editingPolicy) return;

    try {
      JSON.parse(configJson);
    } catch (err) {
      setErrorMessage("Configuration payload is not valid JSON.");
      return;
    }

    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("name", name);
      formData.append("config", configJson);

      await apiClient.putMultipart(`/api/v1/policies/${editingPolicy.id}`, formData);

      setEditingPolicy(null);
      resetForm();
      mutate();
    } catch (e: any) {
      setErrorMessage(e.message || "Failed to update policy.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeactivate = async () => {
    if (!deactivatingPolicy) return;
    setErrorMessage(null);
    setSubmitting(true);

    try {
      await apiClient.delete(`/api/v1/policies/${deactivatingPolicy.id}`);

      setDeactivatingPolicy(null);
      mutate();
    } catch (e: any) {
      setErrorMessage(e.message || "Failed to deactivate policy.");
    } finally {
      setSubmitting(false);
    }
  };

  const resetForm = () => {
    setName("");
    setPolicyType("risk_threshold");
    setConfigJson(defaultPolicyTemplates.risk_threshold);
    setErrorMessage(null);
  };

  if (error) {
    return <div className="text-red-400">Failed to load system policies.</div>;
  }

  const list = policies || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-black">System Governance Policies</h1>
          <p className="text-sm text-gray-500 mt-1">Manage active risk constraints, anomaly bounds, and automation thresholds.</p>
        </div>

        <RoleGate roles={["admin", "compliance"]}>
          <button
            onClick={() => {
              resetForm();
              setCreateModalOpen(true);
            }}
            className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-semibold shadow-glow transition duration-200 flex items-center gap-1.5 w-fit"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
            </svg>
            Create Policy
          </button>
        </RoleGate>
      </div>

      {/* Policies List */}
      {!policies ? (
        <div className="py-20 flex flex-col items-center justify-center gap-4">
          <div className="w-10 h-10 border-4 border-t-blue-500 border-r-transparent border-gray-200 rounded-full animate-spin"></div>
          <p className="text-xs text-gray-500 font-mono">Loading active governance profiles...</p>
        </div>
      ) : list.length === 0 ? (
        <div className="py-24 text-center glassmorphism rounded-xl border border-gray-200">
          <p className="text-sm text-gray-500">No policies configured in current workspace.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {list.map((policy: any) => {
            const isActive = policy.is_active;
            const configFormatted =
              typeof policy.config === "string"
                ? JSON.stringify(JSON.parse(policy.config), null, 2)
                : JSON.stringify(policy.config, null, 2);

            return (
              <div
                key={policy.id}
                className="glassmorphism p-5 rounded-xl border border-gray-200 flex flex-col justify-between gap-4 hover:border-gray-300 transition shadow-sm"
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-2 border-b border-gray-200 pb-2">
                    <span className="text-xs font-mono font-bold text-blue-600 uppercase bg-blue-100 px-2 py-0.5 rounded">
                      {policy.policy_type}
                    </span>
                    <div className="flex items-center gap-1">
                      <span className={`w-1.5 h-1.5 rounded-full ${isActive ? "bg-green-500" : "bg-gray-400"}`}></span>
                      <span className={`text-[10px] font-mono font-bold ${isActive ? "text-green-600" : "text-gray-500"}`}>
                        {isActive ? "ACTIVE" : "INACTIVE"}
                      </span>
                    </div>
                  </div>

                  <div>
                    <h3 className="font-bold text-black text-sm tracking-wide">{policy.name}</h3>
                    <p className="text-[10px] text-gray-500 font-mono mt-0.5">
                      Version: {policy.version} • Created by: {policy.created_by.substring(0, 12)}
                    </p>
                  </div>

                  <div className="bg-gray-50 p-3 rounded-lg border border-gray-200 overflow-hidden">
                    <pre className="text-[10px] font-mono text-black leading-relaxed overflow-x-auto max-h-40 scrollbar-thin">
                      {configFormatted}
                    </pre>
                  </div>
                </div>

                {/* CRUD Controls */}
                <div className="pt-2 flex items-center justify-end gap-2">
                  <RoleGate
                    roles={["admin", "compliance"]}
                    fallback={
                      <div className="text-[9px] font-mono text-gray-500 w-full text-left">
                        🔒 Read-only view for {role}.
                      </div>
                    }
                  >
                    <button
                      onClick={() => setEditingPolicy(policy)}
                      className="px-2.5 py-1.5 bg-white hover:bg-gray-50 border border-gray-200 text-gray-700 rounded text-[10px] font-bold font-mono transition"
                    >
                      Edit
                    </button>
                    {isActive && (
                      <button
                        onClick={() => setDeactivatingPolicy(policy)}
                        className="px-2.5 py-1.5 bg-red-50 hover:bg-red-100 border border-red-200 text-red-700 rounded text-[10px] font-bold font-mono transition"
                      >
                        Deactivate
                      </button>
                    )}
                  </RoleGate>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* CREATE Policy Modal */}
      {createModalOpen && (
        <div className="fixed inset-0 bg-gray-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-xl bg-white border border-gray-200 rounded-xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-gray-200 pb-3">
              <h3 className="font-extrabold text-black text-base font-mono">Create Governance Policy</h3>
              <button
                onClick={() => setCreateModalOpen(false)}
                className="text-gray-500 hover:text-black transition font-mono text-sm"
              >
                ✕ Close
              </button>
            </div>

            {errorMessage && (
              <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-xs font-mono">
                {errorMessage}
              </div>
            )}

            <form onSubmit={handleCreate} className="space-y-4 text-xs font-mono text-gray-600">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-[10px] uppercase font-bold text-gray-500 block">Policy Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Core Risk Limits"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full bg-gray-50 border border-gray-200 text-black rounded-lg px-3 py-2.5 focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] uppercase font-bold text-gray-500 block">Policy Type</label>
                  <select
                    value={policyType}
                    onChange={(e) => setPolicyType(e.target.value)}
                    className="w-full bg-gray-50 border border-gray-200 text-black rounded-lg px-3 py-2.5 focus:outline-none focus:border-blue-500 cursor-pointer"
                  >
                    <option value="risk_threshold">Risk Engine Rule</option>
                    <option value="permission">Permission Scope</option>
                    <option value="anomaly">Anomaly Detector</option>
                    <option value="retention">Retention Policy</option>
                  </select>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] uppercase font-bold text-gray-500 block">Configuration JSON</label>
                <textarea
                  value={configJson}
                  onChange={(e) => setConfigJson(e.target.value)}
                  rows={8}
                  className="w-full bg-gray-50 border border-gray-200 text-black rounded-lg p-3 focus:outline-none focus:border-blue-500 font-mono text-xs leading-relaxed"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setCreateModalOpen(false)}
                  className="px-4 py-2 border border-gray-200 hover:border-gray-300 text-gray-600 bg-white rounded-lg text-[10px] font-semibold transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-[10px] font-semibold transition flex items-center gap-1.5"
                >
                  {submitting ? "Saving..." : "Create Policy"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT Policy Modal */}
      {editingPolicy && (
        <div className="fixed inset-0 bg-gray-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-xl bg-white border border-gray-200 rounded-xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-gray-200 pb-3">
              <h3 className="font-extrabold text-black text-base font-mono">Update Policy: {editingPolicy.name}</h3>
              <button
                onClick={() => setEditingPolicy(null)}
                className="text-gray-500 hover:text-black transition font-mono text-sm"
              >
                ✕ Close
              </button>
            </div>

            {errorMessage && (
              <div className="p-3 bg-red-50 border border-red-200 text-red-700 rounded-lg text-xs font-mono">
                {errorMessage}
              </div>
            )}

            <form onSubmit={handleUpdate} className="space-y-4 text-xs font-mono text-gray-600">
              <div className="space-y-1.5">
                <label className="text-[10px] uppercase font-bold text-gray-500 block">Policy Name</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-gray-50 border border-gray-200 text-black rounded-lg px-3 py-2.5 focus:outline-none focus:border-blue-500"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] uppercase font-bold text-gray-500 block">Configuration JSON</label>
                <textarea
                  value={configJson}
                  onChange={(e) => setConfigJson(e.target.value)}
                  rows={8}
                  className="w-full bg-gray-50 border border-gray-200 text-black rounded-lg p-3 focus:outline-none focus:border-blue-500 font-mono text-xs leading-relaxed"
                />
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setEditingPolicy(null)}
                  className="px-4 py-2 border border-gray-200 hover:border-gray-300 text-gray-600 bg-white rounded-lg text-[10px] font-semibold transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-[10px] font-semibold transition flex items-center gap-1.5"
                >
                  {submitting ? "Saving..." : "Update Policy"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* DEACTIVATE Policy Confirmation Modal */}
      {deactivatingPolicy && (
        <div className="fixed inset-0 bg-gray-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-md bg-white border border-gray-200 rounded-xl p-6 shadow-2xl space-y-4">
            <h3 className="font-extrabold text-black text-base font-mono">Deactivate Policy?</h3>
            <p className="text-xs text-gray-500">
              Are you sure you want to deactivate policy <span className="text-black font-bold">{deactivatingPolicy.name}</span>?
              This will disable active runtime governance checks associated with this policy block.
            </p>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setDeactivatingPolicy(null)}
                className="px-4 py-2 border border-gray-200 hover:border-gray-300 text-gray-600 bg-white rounded-lg text-xs font-semibold shadow-sm transition"
              >
                Cancel
              </button>
              <button
                onClick={handleDeactivate}
                disabled={submitting}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-semibold transition"
              >
                Deactivate Policy
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
