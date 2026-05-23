import React from "react";

export default function SubmitLoading() {
  return (
    <div className="space-y-6 animate-pulse max-w-3xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="h-8 w-64 bg-slate-800 rounded-lg mb-2"></div>
          <div className="h-4 w-96 bg-slate-800/50 rounded-lg"></div>
        </div>
      </div>

      <div className="glassmorphism p-8 rounded-xl space-y-6">
        <div className="space-y-2">
          <div className="h-4 w-32 bg-slate-800 rounded"></div>
          <div className="h-32 w-full bg-slate-800/50 rounded-xl border-2 border-dashed border-slate-700"></div>
        </div>

        <div className="space-y-2">
          <div className="h-4 w-32 bg-slate-800 rounded"></div>
          <div className="h-10 w-full bg-slate-800 rounded-lg"></div>
        </div>

        <div className="space-y-2">
          <div className="h-4 w-32 bg-slate-800 rounded"></div>
          <div className="h-24 w-full bg-slate-800 rounded-lg"></div>
        </div>

        <div className="pt-4 border-t border-slate-800">
          <div className="h-12 w-full bg-slate-800 rounded-lg"></div>
        </div>
      </div>
    </div>
  );
}
