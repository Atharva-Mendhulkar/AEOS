import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/providers/AuthProvider";
import { WebSocketProvider } from "@/providers/WebSocketProvider";
import RootLayoutClient from "./RootLayoutClient";

export const metadata: Metadata = {
  title: "AEOS Control Panel",
  description: "Autonomous Escallation & Operations Suite Control Dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-gray-100 antialiased font-sans">
        <AuthProvider>
          <WebSocketProvider>
            <RootLayoutClient>{children}</RootLayoutClient>
          </WebSocketProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
