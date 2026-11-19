import { apiUrl } from "./sharedProject";

export interface WorkspaceResult {
  workspace: { id: string; grantCallId: string; baselineGrantVersionId: string; currentGrantVersionId: string; status: string };
  tasks: Array<{ id: string; title: string; source: string; necessity: string; status: string; blocking: number; reason_code: string | null }>;
  readiness: { state: string; completedCount: number; totalCount: number; completionPercent: number; nextAction: { title: string } | null };
  versionReview: { required: boolean; diff: Array<{ field: string; before: string | null; after: string | null; evidenceId: string | null }>; sourceUrl: string | null; sourceCheckedAt: string; alerts: Array<{ versionId: string; createdAt: string }> };
}

async function request(path: string, token: string, method = "GET", body?: unknown): Promise<unknown> {
  const response = await fetch(apiUrl(path), {
    method,
    headers: { authorization: `Bearer ${token}`, accept: "application/json", ...(body ? { "content-type": "application/json" } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
    credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer",
  });
  if (!response.ok) throw new Error(`WORKSPACE_REQUEST_${response.status}`);
  return response.json();
}

export async function listWorkspaces(projectId: string, token: string): Promise<Array<{ id: string; grantCallId: string }>> {
  const result = await request(`/projects/${projectId}/workspaces`, token) as {workspaces: Array<{id: string; grantCallId: string}>};
  return result.workspaces;
}
export async function createWorkspace(projectId: string, token: string, grantCallId: string): Promise<WorkspaceResult> {
  return request(`/projects/${projectId}/workspaces`, token, "POST", { grantCallId }) as Promise<WorkspaceResult>;
}
export async function getWorkspace(projectId: string, token: string, id: string): Promise<WorkspaceResult> {
  return request(`/projects/${projectId}/workspaces/${id}`, token) as Promise<WorkspaceResult>;
}
export async function updateTask(projectId: string, token: string, id: string, taskId: string, status: string): Promise<WorkspaceResult> {
  return request(`/projects/${projectId}/workspaces/${id}/tasks/${taskId}`, token, "PATCH", { status }) as Promise<WorkspaceResult>;
}
