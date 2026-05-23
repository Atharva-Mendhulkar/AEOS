import React from "react";

export default function IncidentsLoading() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Page Header Skeleton */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="h-8 w-64 bg-slate-800 rounded-lg mb-2"></div>
          <div className="h-4 w-96 bg-slate-800/50 rounded-lg"></div>
        </div>
      </div>

      {/* Main Content Area Skeleton */}
      <div className="glassmorphism rounded-xl overflow-hidden p-6 space-y-4">
        <div className="flex gap-4">
          <div className="h-10 w-1/4 bg-slate-800 rounded-lg"></div>
          <div className="h-10 w-1/4 bg-slate-800 rounded-lg"></div>
          <div className="h-10 w-24 bg-slate-800 rounded-lg"></div>
        </div>
        
        <div className="h-64 w-full bg-slate-800/50 rounded-xl mt-6"></div>
      </div>
    </div>
  );
}
