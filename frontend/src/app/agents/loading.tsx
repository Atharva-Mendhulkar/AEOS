import React from "react";

export default function AgentsLoading() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="h-8 w-64 bg-gray-200 rounded-lg mb-2"></div>
          <div className="h-4 w-96 bg-gray-100 rounded-lg"></div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => (
          <div key={i} className="glassmorphism p-6 rounded-xl flex flex-col items-center justify-center space-y-4 h-48">
            <div className="w-16 h-16 bg-gray-200 rounded-full"></div>
            <div className="h-5 w-32 bg-gray-200 rounded"></div>
            <div className="h-4 w-24 bg-gray-100 rounded-full"></div>
          </div>
        ))}
      </div>
    </div>
  );
}
