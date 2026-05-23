"use client";

import React, { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/utils/api";

const supportedFormats = [
  { value: "text", label: "Plain Text / Incident Narrative" },
  { value: "json", label: "Structured JSON Event" },
  { value: "pdf", label: "PDF System Summary Document" },
  { value: "image", label: "Screenshot Image (JPEG/PNG)" },
  { value: "log", label: "System Console Log Logfile" },
  { value: "audio", label: "Audio Recording (MP3/WAV/M4A)" },
  { value: "transcript", label: "Conversation Transcript File" },
];

export default function SubmitIncident() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const [format, setFormat] = useState("text");
  const [directText, setDirectText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [successInfo, setSuccessInfo] = useState<any>(null);
  const [errorText, setErrorText] = useState<string | null>(null);

  // File size limit: 50 MB
  const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;

  const handleFileChange = (selectedFile: File | null) => {
    if (!selectedFile) return;
    
    if (selectedFile.size > MAX_FILE_SIZE_BYTES) {
      setErrorText("File size exceeds 50 MB limit constraint.");
      setFile(null);
      return;
    }
    
    setErrorText(null);
    setFile(selectedFile);
    
    // Auto-detect format based on file extension
    const ext = selectedFile.name.split(".").pop()?.toLowerCase();
    if (ext === "json") setFormat("json");
    else if (ext === "pdf") setFormat("pdf");
    else if (ext === "png" || ext === "jpg" || ext === "jpeg") setFormat("image");
    else if (ext === "log" || ext === "txt") setFormat("log");
    else if (ext === "mp3" || ext === "wav" || ext === "m4a") setFormat("audio");
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileChange(e.dataTransfer.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSuccessInfo(null);
    setErrorText(null);

    try {
      const formData = new FormData();
      formData.append("format", format);

      if (file) {
        formData.append("file", file);
      } else if (directText.trim()) {
        // Submit raw text entry as a blob representation
        const blob = new Blob([directText], { type: "text/plain" });
        formData.append("file", blob, "direct_text_narrative.txt");
      } else {
        throw new Error("Please upload a file or write an incident summary narrative.");
      }

      const result = await apiClient.postMultipart("/api/v1/incidents/ingest", formData);
      setSuccessInfo(result);
      
      // Reset inputs
      setFile(null);
      setDirectText("");
      
      // Auto redirect to incident page in 3 seconds
      setTimeout(() => {
        if (result.incident_id) {
          router.push(`/incidents/${result.incident_id}`);
        } else {
          router.push("/dashboard");
        }
      }, 3000);
    } catch (e: any) {
      console.error(e);
      setErrorText(e.message || "Failed to ingest incident.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-white">Ingest Multimodal Incident</h1>
        <p className="text-sm text-gray-400 mt-1">
          Upload log files, call recordings, system audits, or submit a manual description to trigger autonomous analysis.
        </p>
      </div>

      {errorText && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-200 rounded-xl text-xs font-mono">
          <p className="font-bold">Ingestion Blocked:</p>
          <p>{errorText}</p>
        </div>
      )}

      {successInfo && (
        <div className="p-5 bg-green-500/10 border border-green-500/20 text-green-200 rounded-xl space-y-2 text-xs font-mono">
          <h4 className="font-extrabold text-sm flex items-center gap-1.5 text-green-300">
            <span className="w-2 h-2 bg-glowEmerald rounded-full pulse-glow"></span>
            Ingestion Dispatched Successfully
          </h4>
          <p>Incident generated with unique ID: {successInfo.incident_id}</p>
          <p className="text-gray-400">Classified Severity: <span className="text-white uppercase font-bold">{successInfo.severity}</span></p>
          <p className="text-gray-500">Redirecting to incident console in 3 seconds...</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="glassmorphism p-6 rounded-xl border border-slate-800 space-y-6">
        {/* Format Selector */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider font-mono">
            Payload Format
          </label>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            className="w-full bg-slate-900 border border-slate-800 text-sm font-mono text-gray-300 rounded-lg px-3 py-2.5 focus:outline-none focus:border-blue-500 cursor-pointer"
          >
            {supportedFormats.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </div>

        {/* Input Methods Tab-like structure */}
        <div className="space-y-4">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider font-mono block">
            Payload Ingestion Content
          </span>

          {/* Drag & Drop File Upload Area */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200 ${
              isDragOver
                ? "border-blue-500 bg-blue-500/5 text-blue-400"
                : file
                ? "border-glowEmerald/50 bg-glowEmerald/5 text-glowEmerald"
                : "border-slate-800 hover:border-slate-700 bg-slate-900/30 text-gray-400"
            }`}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={(e) => handleFileChange(e.target.files?.[0] || null)}
              className="hidden"
            />
            <div className="space-y-2">
              <svg className="w-10 h-10 mx-auto opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              {file ? (
                <div>
                  <p className="text-sm font-bold text-white truncate max-w-md mx-auto">{file.name}</p>
                  <p className="text-xs text-gray-400 mt-1 font-mono">
                    {(file.size / 1024 / 1024).toFixed(2)} MB • Click to replace
                  </p>
                </div>
              ) : (
                <div>
                  <p className="text-sm font-semibold text-gray-300">Drag and drop file here, or click to browse</p>
                  <p className="text-xs text-gray-500 mt-1">Accepts all 7 multimodal files. Max size 50 MB.</p>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center justify-center text-xs font-mono text-gray-600 uppercase tracking-widest my-2">
            <span>— OR Write Directly —</span>
          </div>

          {/* Text Area input */}
          <div className="space-y-1">
            <textarea
              placeholder="Paste logs, transcribe chat conversations, or type description summary manually..."
              value={directText}
              disabled={file !== null}
              onChange={(e) => setDirectText(e.target.value)}
              rows={6}
              className="w-full bg-slate-900 border border-slate-800 text-xs font-mono text-gray-300 rounded-lg p-3.5 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-30 disabled:cursor-not-allowed"
            />
            {file && (
              <span className="text-[10px] text-gray-500 font-mono">
                * Text area disabled when a file is staged for upload.
              </span>
            )}
          </div>
        </div>

        {/* Submit Actions */}
        <div className="pt-4 border-t border-slate-850 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={() => {
              setFile(null);
              setDirectText("");
              setSuccessInfo(null);
              setErrorText(null);
            }}
            disabled={submitting}
            className="px-4 py-2 border border-slate-800 hover:border-slate-700 text-gray-400 hover:text-white rounded-lg text-xs font-semibold transition disabled:opacity-40"
          >
            Clear Fields
          </button>
          
          <button
            type="submit"
            disabled={submitting || (!file && !directText.trim())}
            className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold shadow-glow transition duration-150 flex items-center gap-2 disabled:opacity-40"
          >
            {submitting ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-t-white border-r-transparent border-slate-400 rounded-full animate-spin"></div>
                <span>Processing Ingest...</span>
              </>
            ) : (
              <span>Dispatch Ingestion</span>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
