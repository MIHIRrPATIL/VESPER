import React from "react";
import { AgendaView } from "./AgendaView";

export interface TaskItem {
  id: string;
  title: string;
  priority?: "normal" | "high" | "urgent" | string;
  deadline?: string | null;
  done?: boolean;
  isPendingSync?: boolean;
  [key: string]: any;
}

export interface CalendarItem {
  id: string;
  title: string;
  start_time?: string;
  end_time?: string;
  location?: string;
  [key: string]: any;
}

export const AgendaTab: React.FC = () => {
  return <AgendaView />;
};
