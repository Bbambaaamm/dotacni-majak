import type { Env } from "./env";
import { ApiInputError, hashOwnerToken } from "./projectAccess";

const PROJECT_ID_RE = /^prj_[a-f0-9]{32}$/;
const ATTACHMENT_ID_RE = /^att_[a-f0-9]{32}$/;
const TOKEN_RE = /^[A-Za-z0-9_-]{40,128}$/;

const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024; // 10 MB
const MAX_FILENAME_LENGTH = 255;

const ALLOWED_MIME_TYPES = new Set([
  "application/pdf",
  "image/png",
  "image/jpeg",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
  "text/csv",
  "text/plain",
]);

const MIME_TO_EXTENSIONS: Record<string, string[]> = {
  "application/pdf": ["pdf"],
  "image/png": ["png"],
  "image/jpeg": ["jpg", "jpeg"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ["docx"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ["xlsx"],
  "application/vnd.ms-excel": ["xls"],
  "text/csv": ["csv"],
  "text/plain": ["txt", "text"],
};

export interface ValidatedAttachment {
  readonly filename: string;
  readonly mimeType: string;
  readonly sizeBytes: number;
  readonly body: ArrayBuffer;
}

export interface Attachment {
  readonly id: string;
  readonly projectId: string;
  readonly filename: string;
  readonly mimeType: string;
  readonly sizeBytes: number;
  readonly status: "UPLOADED" | "REJECTED" | "DELETED";
  readonly createdAt: string;
  readonly updatedAt: string;
}

export interface CreatedAttachment extends Attachment {}

function filenameExtension(filename: string): string | null {
  const idx = filename.lastIndexOf(".");
  if (idx <= 0 || idx === filename.length - 1) return null;
  return filename.slice(idx + 1).toLowerCase();
}

function assertProjectId(projectId: string): void {
  if (!PROJECT_ID_RE.test(projectId)) {
    throw new ApiInputError("PROJECT_NOT_FOUND", 404);
  }
}

function assertAttachmentId(id: string): void {
  if (!ATTACHMENT_ID_RE.test(id)) {
    throw new ApiInputError("ATTACHMENT_NOT_FOUND", 404);
  }
}

function assertOwnerToken(token: string): void {
  if (!TOKEN_RE.test(token)) {
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }
}

async function verifyOwnerCapability(
  env: Env,
  projectId: string,
  ownerToken: string,
): Promise<string> {
  assertProjectId(projectId);
  assertOwnerToken(ownerToken);
  const ownerHash = await hashOwnerToken(ownerToken);
  const row = await env.DB.prepare(
    `SELECT 1 AS ok FROM project_owner_capabilities WHERE project_id = ? AND token_hash = ? AND revoked_at IS NULL LIMIT 1`,
  ).bind(projectId, ownerHash).first<{ ok: number }>();
  if (row?.ok !== 1) {
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }
  return ownerHash;
}

export interface AttachmentRow {
  id: string;
  project_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  created_at: string;
  updated_at: string;
}

function attachmentFromRow(row: AttachmentRow, projectId: string): Attachment {
  return {
    id: row.id,
    projectId,
    filename: row.filename,
    mimeType: row.mime_type,
    sizeBytes: row.size_bytes,
    status: row.status as Attachment["status"],
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

export async function validateAttachmentUpload(
  request: Request,
): Promise<ValidatedAttachment> {
  const contentType = request.headers.get("content-type");
  if (!contentType || !ALLOWED_MIME_TYPES.has(contentType)) {
    throw new ApiInputError("INVALID_ATTACHMENT_MIME", 400);
  }

  const filenameHeader = request.headers.get("x-attachment-filename");
  if (!filenameHeader || typeof filenameHeader !== "string") {
    throw new ApiInputError("INVALID_ATTACHMENT_FILENAME", 400);
  }
  const filename = filenameHeader.trim();
  if (filename.length === 0 || filename.length > MAX_FILENAME_LENGTH) {
    throw new ApiInputError("INVALID_ATTACHMENT_FILENAME", 400);
  }
  if (!/^[^\/\\\x00]+$/.test(filename)) {
    throw new ApiInputError("INVALID_ATTACHMENT_FILENAME", 400);
  }

  // Extension must be consistent with the declared MIME when a filename
  // extension is present. This prevents a client from claiming an allowed
  // MIME while uploading a differently-typed file under a non-matching name.
  const ext = filenameExtension(filename);
  if (ext !== null) {
    const allowed = MIME_TO_EXTENSIONS[contentType];
    if (!allowed || !allowed.includes(ext)) {
      throw new ApiInputError("INVALID_ATTACHMENT_MIME", 400);
    }
  }

  const contentLength = request.headers.get("content-length");
  if (contentLength !== null) {
    const declared = Number(contentLength);
    if (
      !Number.isSafeInteger(declared) ||
      declared < 0 ||
      declared > MAX_ATTACHMENT_BYTES
    ) {
      throw new ApiInputError("ATTACHMENT_TOO_LARGE", 400);
    }
  }

  let body: ArrayBuffer;
  try {
    body = await request.arrayBuffer();
  } catch {
    throw new ApiInputError("REQUEST_TOO_LARGE", 413);
  }
  if (body.byteLength > MAX_ATTACHMENT_BYTES) {
    throw new ApiInputError("ATTACHMENT_TOO_LARGE", 400);
  }
  if (body.byteLength === 0) {
    throw new ApiInputError("INVALID_ATTACHMENT_EMPTY", 400);
  }

  return { filename, mimeType: contentType, sizeBytes: body.byteLength, body };
}

export async function createAttachment(
  env: Env,
  projectId: string,
  ownerToken: string,
  validated: ValidatedAttachment,
  now: Date = new Date(),
): Promise<CreatedAttachment> {
  await verifyOwnerCapability(env, projectId, ownerToken);

  const timestamp = now.toISOString();
  const attachmentId = "att_" + crypto.randomUUID().replaceAll("-", "");
  const storageKey =
    "proj/" +
    projectId +
    "/" +
    attachmentId +
    "/" +
    crypto.randomUUID().replaceAll("-", "");

  // R2 put first so the object exists before the DB metadata is committed.
  // Fail-closed: if the put fails, nothing is persisted.
  const r2Result = await env.ATTACHMENTS.put(storageKey, {
    body: validated.body,
    contentType: validated.mimeType,
  });
  if (!r2Result || !r2Result.key) {
    throw new Error("ATTACHMENT_STORAGE_PUT_FAILED");
  }

  const ownerHash = await hashOwnerToken(ownerToken);
  const ownerRow = await env.DB.prepare(
    `SELECT p.owner_user_id
     FROM projects AS p
     INNER JOIN project_owner_capabilities AS c
       ON c.project_id = p.id
     WHERE p.id = ? AND c.token_hash = ? AND c.revoked_at IS NULL
     LIMIT 1`,
  ).bind(projectId, ownerHash).first<{ owner_user_id: string }>();
  if (!ownerRow) {
    // Best-effort cleanup of the object we just wrote; the attachment is
    // not persisted. Fail-closed: no metadata + no reachable object.
    await env.ATTACHMENTS.delete(storageKey).catch(() => {});
    throw new ApiInputError("OWNER_CAPABILITY_INVALID", 404);
  }

  const insertAttachment = env.DB.prepare(
    `INSERT INTO user_document_attachments(
       id, project_id, owner_user_id, storage_key, filename,
       mime_type, size_bytes, status, created_at, updated_at
     ) VALUES (?,?,?,?,?,?,?,?,?,?)`,
  ).bind(
    attachmentId,
    projectId,
    ownerRow.owner_user_id,
    storageKey,
    validated.filename,
    validated.mimeType,
    validated.sizeBytes,
    "UPLOADED",
    timestamp,
    timestamp,
  );

  const insertEvent = env.DB.prepare(
    `INSERT INTO user_document_attachment_events(
       id, attachment_id, project_id, actor_user_id, event_type,
       filename, mime_type, size_bytes, created_at
     ) VALUES (?,?,?,?,?,?,?,?,?)`,
  ).bind(
    "evt_" + crypto.randomUUID().replaceAll("-", ""),
    attachmentId,
    projectId,
    ownerRow.owner_user_id,
    "CREATED",
    validated.filename,
    validated.mimeType,
    validated.sizeBytes,
    timestamp,
  );

  const results = await env.DB.batch([insertAttachment, insertEvent]);
  if (
    !results.every((r) => r.success) ||
    (results[0]?.meta?.changes ?? 0) !== 1
  ) {
    // Best-effort cleanup of the object we just wrote.
    await env.ATTACHMENTS.delete(storageKey).catch(() => {});
    throw new Error("ATTACHMENT_CREATE_DB_FAILED");
  }

  return {
    id: attachmentId,
    projectId,
    filename: validated.filename,
    mimeType: validated.mimeType,
    sizeBytes: validated.sizeBytes,
    status: "UPLOADED",
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}

export async function listAttachments(
  env: Env,
  projectId: string,
  ownerToken: string,
): Promise<Attachment[]> {
  await verifyOwnerCapability(env, projectId, ownerToken);
  assertProjectId(projectId);

  const rows = await env.DB.prepare(
    `SELECT id, project_id, filename, mime_type, size_bytes, status, created_at, updated_at
     FROM user_document_attachments
     WHERE project_id = ? AND status <> 'DELETED'
     ORDER BY created_at DESC
     LIMIT 200`,
  ).bind(projectId).all<AttachmentRow>();

  const result = rows?.results ?? [];
  return result.map((row: AttachmentRow) => attachmentFromRow(row, projectId));
}

export async function getAttachment(
  env: Env,
  projectId: string,
  ownerToken: string,
  attachmentId: string,
): Promise<Attachment | null> {
  await verifyOwnerCapability(env, projectId, ownerToken);
  assertProjectId(projectId);
  assertAttachmentId(attachmentId);

  const row = await env.DB.prepare(
    `SELECT id, project_id, filename, mime_type, size_bytes, status, created_at, updated_at
     FROM user_document_attachments
     WHERE id = ? AND project_id = ? AND status <> 'DELETED'
     LIMIT 1`,
  ).bind(attachmentId, projectId).first<AttachmentRow>();

  if (!row) return null;
  return attachmentFromRow(row, projectId);
}

export async function deleteAttachment(
  env: Env,
  projectId: string,
  ownerToken: string,
  attachmentId: string,
  now: Date = new Date(),
): Promise<void> {
  await verifyOwnerCapability(env, projectId, ownerToken);
  assertProjectId(projectId);
  assertAttachmentId(attachmentId);

  const timestamp = now.toISOString();

  // Read the storage key before soft-deleting so we can also revoke the R2
  // object. Fail-closed: if either the DB commit or the R2 delete fails, the
  // attachment is not cleanly gone, but no new public access is created.
  const row = await env.DB.prepare(
    `SELECT storage_key FROM user_document_attachments
     WHERE id = ? AND project_id = ? AND status <> 'DELETED'
     LIMIT 1`,
  ).bind(attachmentId, projectId).first<{ storage_key: string }>();

  if (!row) {
    // Non-disclosing: unknown or already-deleted attachment -> 204.
    return;
  }

  const update = env.DB.prepare(
    `UPDATE user_document_attachments
     SET status = 'DELETED', updated_at = ?
     WHERE id = ? AND project_id = ? AND status <> 'DELETED'`,
  ).bind(timestamp, attachmentId, projectId);

  const insertEvent = env.DB.prepare(
    `INSERT INTO user_document_attachment_events(
       id, attachment_id, project_id, actor_user_id, event_type,
       filename, mime_type, size_bytes, created_at
     ) SELECT
       'evt_' || lower(hex(randomblob(16))), id, project_id, owner_user_id,
       'DELETED', filename, mime_type, size_bytes, ?
     FROM user_document_attachments
     WHERE id = ? AND project_id = ? AND status = 'DELETED' AND updated_at = ?`,
  ).bind(timestamp, attachmentId, projectId, timestamp);

  const results = await env.DB.batch([update, insertEvent]);
  if (!results.every((r) => r.success) || (results[0]?.meta?.changes ?? 0) !== 1) {
    throw new Error("ATTACHMENT_DELETE_DB_FAILED");
  }

  // Revoke the underlying R2 object. Best-effort; a future reaper can clean
  // any object whose DB row is DELETED/missing.
  await env.ATTACHMENTS.delete(row.storage_key).catch(() => {});
}

export function projectAttachmentPath(
  pathname: string,
): { projectId: string; attachmentId: string } | { projectId: string; attachmentId: null } | null {
  const collectionMatch = pathname.match(
    /^\/projects\/(prj_[a-f0-9]{32})\/attachments$/,
  );
  if (collectionMatch) {
    return { projectId: collectionMatch[1], attachmentId: null };
  }
  const itemMatch = pathname.match(
    /^\/projects\/(prj_[a-f0-9]{32})\/attachments\/(att_[a-f0-9]{32})$/,
  );
  if (itemMatch) {
    return { projectId: itemMatch[1], attachmentId: itemMatch[2] };
  }
  return null;
}
