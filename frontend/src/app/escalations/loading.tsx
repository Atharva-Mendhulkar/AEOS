import React from "react";

export default function EscalationsLoading() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Page Header Skeleton */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="h-8 w-64 bg-gray-200 rounded-lg mb-2"></div>
          <div className="h-4 w-96 bg-gray-100 rounded-lg"></div>
        </div>
      </div>

      {/* Cards Skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="glassmorphism p-6 rounded-xl space-y-4 border border-gray-200">
            <div className="flex justify-between items-center border-b border-gray-200 pb-4">
              <div className="h-5 w-32 bg-gray-200 rounded"></div>
              <div className="h-6 w-16 bg-gray-200 rounded-full"></div>
            </div>
            <div className="space-y-2">
              <div className="h-4 w-full bg-gray-100 rounded"></div>
              <div className="h-4 w-5/6 bg-gray-100 rounded"></div>
            </div>
            <div className="h-20 w-full bg-gray-200 rounded mt-4"></div>
            <div className="flex gap-2 pt-4 border-t border-gray-200">
              <div className="h-10 flex-1 bg-gray-200 rounded-lg"></div>
              <div className="h-10 flex-1 bg-gray-200 rounded-lg"></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
