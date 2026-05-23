"use client";

import React from "react";
import { useAuth } from "@/providers/AuthProvider";

export const useRole = () => {
  const { user } = useAuth();
  const role = user?.role || "visitor";

  const isRole = (checkRoles: string | string[]) => {
    const list = Array.isArray(checkRoles) ? checkRoles : [checkRoles];
    return list.includes(role);
  };

  return {
    role,
    user,
    isRole,
    isAdmin: role === "admin",
    isOperator: role === "operator",
    isCompliance: role === "compliance",
    isVisitor: role === "visitor",
  };
};

interface RoleGateProps {
  roles: string[];
  fallback?: React.ReactNode;
  children: React.ReactNode;
}

export const RoleGate: React.FC<RoleGateProps> = ({ roles, fallback = null, children }) => {
  const { isRole } = useRole();

  if (!isRole(roles)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
};
