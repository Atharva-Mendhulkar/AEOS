import React from "react";

export default function SubmitLoading() {
  return (
    <div className="space-y-6 animate-pulse max-w-3xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="h-8 w-64 bg-gray-200 rounded-lg mb-2"></div>
          <div className="h-4 w-96 bg-gray-100 rounded-lg"></div>
        </div>
      </div>

      <div className="glassmorphism p-8 rounded-xl space-y-6 border border-gray-200">
        <div className="space-y-2">
          <div className="h-4 w-32 bg-gray-200 rounded"></div>
          <div className="h-32 w-full bg-gray-100 rounded-xl border-2 border-dashed border-gray-200"></div>
        </div>

        <div className="space-y-2">
          <div className="h-4 w-32 bg-gray-200 rounded"></div>
          <div className="h-10 w-full bg-gray-200 rounded-lg"></div>
        </div>

        <div className="space-y-2">
          <div className="h-4 w-32 bg-gray-200 rounded"></div>
          <div className="h-24 w-full bg-gray-200 rounded-lg"></div>
        </div>

        <div className="pt-4 border-t border-gray-200">
          <div className="h-12 w-full bg-gray-200 rounded-lg"></div>
        </div>
      </div>
    </div>
  );
}
