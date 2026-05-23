import React from "react";

export default function PoliciesLoading() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="h-8 w-64 bg-slate-800 rounded-lg mb-2"></div>
          <div className="h-4 w-96 bg-slate-800/50 rounded-lg"></div>
        </div>
        <div className="h-10 w-32 bg-slate-800 rounded-lg"></div>
      </div>

      <div className="glassmorphism rounded-xl overflow-hidden p-6 space-y-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="flex justify-between items-center border border-slate-800 rounded-lg p-4 bg-slate-900/30">
            <div className="space-y-2">
              <div className="h-5 w-48 bg-slate-800 rounded"></div>
              <div className="h-4 w-32 bg-slate-800/50 rounded"></div>
            </div>
            <div className="flex gap-2">
              <div className="h-8 w-16 bg-slate-800 rounded"></div>
              <div className="h-8 w-16 bg-slate-800 rounded"></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
