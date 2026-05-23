import React from "react";

export default function DashboardLoading() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Page Header Skeleton */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="h-8 w-64 bg-slate-800 rounded-lg mb-2"></div>
          <div className="h-4 w-96 bg-slate-800/50 rounded-lg"></div>
        </div>
        <div className="h-10 w-32 bg-slate-800 rounded-lg"></div>
      </div>

      {/* KPI Cards Skeleton */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="glassmorphism p-5 rounded-xl flex items-center justify-between">
            <div className="space-y-2">
              <div className="h-3 w-24 bg-slate-800 rounded"></div>
              <div className="h-8 w-16 bg-slate-800 rounded"></div>
            </div>
            <div className="w-12 h-12 bg-slate-800 rounded-lg"></div>
          </div>
        ))}
      </div>

      {/* Incidents Table Skeleton */}
      <div className="glassmorphism rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/20">
          <div className="h-4 w-32 bg-slate-800 rounded"></div>
          <div className="h-6 w-24 bg-slate-800 rounded"></div>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-850">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                  <th key={i} className="px-6 py-4"><div className="h-3 w-20 bg-slate-800 rounded"></div></th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-850/50">
              {[1, 2, 3, 4, 5].map((row) => (
                <tr key={row}>
                  {[1, 2, 3, 4, 5, 6].map((col) => (
                    <td key={col} className="px-6 py-4">
                      <div className="h-4 w-full bg-slate-800/50 rounded"></div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
