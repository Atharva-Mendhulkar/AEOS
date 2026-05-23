"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/providers/AuthProvider";
import { useWebSocket } from "@/providers/WebSocketProvider";

const navigationItems = [
  {
    name: "Dashboard",
    href: "/dashboard",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2v-4zM14 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2v-4z" />
      </svg>
    ),
  },
  {
    name: "Submit Incident",
    href: "/submit",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    name: "Escalations Queue",
    href: "/escalations",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
      </svg>
    ),
  },
  {
    name: "Policy Manager",
    href: "/policies",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
  },
  {
    name: "Specialist Agents",
    href: "/agents",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
      </svg>
    ),
  },
];

export default function RootLayoutClient({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, loginAs } = useAuth();
  const { status: socketStatus } = useWebSocket();

  const handleRoleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    loginAs(e.target.value);
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="w-64 border-r border-gray-200 bg-white flex flex-col justify-between shrink-0 shadow-sm z-10 relative">
        <div>
          {/* Logo */}
          <div className="h-16 px-6 border-b border-gray-200 flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-black flex items-center justify-center">
              <span className="text-white font-extrabold text-sm tracking-widest">AE</span>
            </div>
            <div>
              <h1 className="font-extrabold text-base tracking-wider text-black">AEOS Control</h1>
              <p className="text-[10px] text-gray-500 font-mono">v1.2.0-STABLE</p>
            </div>
          </div>

          {/* Nav links */}
          <nav className="p-4 space-y-1">
            {navigationItems.map((item) => {
              const isActive = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? "bg-gray-100 text-black border-l-4 border-black pl-3"
                      : "text-gray-500 hover:bg-gray-50 hover:text-black"
                  }`}
                >
                  {item.icon}
                  {item.name}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* System connection Status */}
        <div className="p-4 border-t border-gray-200 bg-gray-50 space-y-3">
          <div className="flex items-center justify-between text-xs font-mono">
            <span className="text-gray-500">WS Gateway</span>
            <div className="flex items-center gap-1.5">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  socketStatus === "connected"
                    ? "bg-glowEmerald pulse-glow"
                    : socketStatus === "connecting"
                    ? "bg-glowAmber"
                    : "bg-glowRose"
                }`}
              />
              <span
                className={
                  socketStatus === "connected"
                    ? "text-glow-green text-glowEmerald"
                    : socketStatus === "connecting"
                    ? "text-glow-amber text-glowAmber"
                    : "text-glow-rose text-glowRose"
                }
              >
                {socketStatus.toUpperCase()}
              </span>
            </div>
          </div>
          
          {/* ASSUMED ROLE Switcher */}
          <div className="space-y-1">
            <label className="text-[10px] uppercase font-bold tracking-wider text-gray-500 block font-mono">
              Assumed Role
            </label>
            <div className="relative">
              <select
                value={user?.role || "visitor"}
                onChange={handleRoleChange}
                className="w-full bg-white border border-gray-300 text-xs font-mono text-black rounded px-2.5 py-1.5 focus:outline-none focus:border-black cursor-pointer appearance-none shadow-sm"
              >
                <option value="admin">Administrator</option>
                <option value="operator">Operator</option>
                <option value="compliance">Compliance</option>
                <option value="visitor">Auditor / Visitor</option>
              </select>
              <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-gray-400">
                <svg className="fill-current h-3 w-3" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
                  <path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z" />
                </svg>
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto bg-gray-50/30">
        <header className="h-16 border-b border-gray-200 flex items-center justify-between px-8 bg-white/80 backdrop-blur-md shrink-0 sticky top-0 z-10">
          <div className="flex items-center gap-4">
            <h2 className="text-lg font-bold text-black tracking-tight capitalize">
              {pathname === "/" ? "Home" : pathname.split("/")[1].replace("-", " ")}
            </h2>
          </div>
          <div className="flex items-center gap-3 font-mono text-xs text-gray-600 bg-white border border-gray-200 px-3 py-1.5 rounded-md shadow-sm">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 pulse-glow"></span>
            <span>Operator Identity:</span>
            <span className="text-black font-bold">{user?.sub || "loading..."}</span>
          </div>
        </header>
        <div className="flex-1 p-8 space-y-6">
          {children}
        </div>
      </main>
    </div>
  );
}
