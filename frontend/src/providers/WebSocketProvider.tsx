"use client";

import React, { createContext, useContext, useEffect, useState, useRef } from "react";
import { io, Socket } from "socket.io-client";
import { useAuth } from "./AuthProvider";

type ConnectionStatus = "connecting" | "connected" | "disconnected";

interface WebSocketContextType {
  socket: Socket | null;
  status: ConnectionStatus;
  subscribeToWorkflow: (workflowId: string) => void;
  events: any[];
  clearEvents: () => void;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

export const WebSocketProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { token } = useAuth();
  const [socket, setSocket] = useState<Socket | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [events, setEvents] = useState<any[]>([]);
  const subscribedWorkflowsRef = useRef<Set<string>>(new Set());

  const clearEvents = () => setEvents([]);

  const subscribeToWorkflow = (workflowId: string) => {
    if (!socket || status !== "connected" || !workflowId) return;
    
    // Retrieve last sequence for this workflow
    const storedSeq = localStorage.getItem(`aeos_last_seq_${workflowId}`);
    const lastSeq = storedSeq ? parseInt(storedSeq, 10) : 0;
    
    console.log(`Subscribing to workflow ${workflowId} from sequence ${lastSeq}`);
    socket.emit("subscribe", {
      workflow_id: workflowId,
      last_sequence: lastSeq
    });
    subscribedWorkflowsRef.current.add(workflowId);
  };

  useEffect(() => {
    if (!token) {
      if (socket) {
        socket.disconnect();
        setSocket(null);
        setStatus("disconnected");
      }
      return;
    }

    console.log("Initializing Socket.IO client...");
    setStatus("connecting");

    // Connect to current origin, which proxies /ws/events and /socket.io via next.config rewrites
    const socketInstance = io(window.location.origin, {
      path: "/ws/events",
      query: { token },
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: Infinity,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 20000,
    });

    socketInstance.on("connect", () => {
      console.log("Socket.IO connected successfully.");
      setStatus("connected");
      
      // Resubscribe to active workflows on reconnection
      subscribedWorkflowsRef.current.forEach((wfId) => {
        const storedSeq = localStorage.getItem(`aeos_last_seq_${wfId}`);
        const lastSeq = storedSeq ? parseInt(storedSeq, 10) : 0;
        socketInstance.emit("subscribe", {
          workflow_id: wfId,
          last_sequence: lastSeq
        });
      });
    });

    socketInstance.on("disconnect", (reason) => {
      console.warn("Socket.IO disconnected:", reason);
      setStatus("disconnected");
    });

    socketInstance.on("connect_error", (error) => {
      console.error("Socket.IO connection error:", error);
      setStatus("disconnected");
    });

    socketInstance.on("event", (eventData: any) => {
      console.log("Received WebSocket event:", eventData);
      
      // Update local storage sequence number if available
      if (eventData.workflow_id && eventData.sequence) {
        const currentLastSeq = localStorage.getItem(`aeos_last_seq_${eventData.workflow_id}`);
        const currentSeq = currentLastSeq ? parseInt(currentLastSeq, 10) : 0;
        if (eventData.sequence > currentSeq) {
          localStorage.setItem(`aeos_last_seq_${eventData.workflow_id}`, eventData.sequence.toString());
        }
      }

      setEvents((prev) => {
        // Prevent duplicate events
        const isDuplicate = prev.some(
          (e) => e.sequence === eventData.sequence && e.workflow_id === eventData.workflow_id
        );
        if (isDuplicate) return prev;
        
        // Keep events sorted chronologically
        const updated = [...prev, eventData];
        return updated.sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
      });
    });

    setSocket(socketInstance);

    return () => {
      console.log("Cleaning up Socket.IO connection...");
      socketInstance.disconnect();
    };
  }, [token]);

  return (
    <WebSocketContext.Provider value={{ socket, status, subscribeToWorkflow, events, clearEvents }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error("useWebSocket must be used within a WebSocketProvider");
  }
  return context;
};
