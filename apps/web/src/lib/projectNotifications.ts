import { apiUrl } from "./sharedProject";

export interface ProjectNotification {
  id: string;
  title: string;
  body: string;
  grantCallId: string;
  status: "SENT" | "READ";
  createdAt: string;
}

export async function getProjectNotifications(
  projectId: string, ownerCapability: string,
): Promise<ProjectNotification[]> {
  const response = await fetch(apiUrl(`/projects/${encodeURIComponent(projectId)}/notifications`), {
    headers: { authorization: `Bearer ${ownerCapability}`, accept: "application/json" },
    credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer",
  });
  if (!response.ok) throw new Error("NOTIFICATIONS_UNAVAILABLE");
  const data: { notifications: ProjectNotification[] } = await response.json();
  return data.notifications;
}
