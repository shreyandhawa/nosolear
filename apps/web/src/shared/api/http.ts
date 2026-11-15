import type { components } from "./schema";

export type UploadAccepted = components["schemas"]["UploadAcceptedOut"];

export class ApiFailure extends Error {
  constructor(
    readonly status: number,
    readonly code: string | undefined,
    message: string,
  ) {
    super(message);
  }
}

type Result<T> = { data?: T; error?: unknown; response: Response };

function failure(r: Result<unknown>, what: string): ApiFailure {
  const body = (r.error ?? {}) as { code?: string; message?: string };
  return new ApiFailure(r.response.status, body.code, body.message ?? `${what} failed: ${r.response.status}`);
}

/** The body, or throws an `ApiFailure` with the API's code and message. */
export async function must<T>(call: Promise<Result<T>>, what: string): Promise<T> {
  const r = await call;
  if (!r.response.ok || r.data === undefined) throw failure(r, what);
  return r.data;
}

/** Like `must`, but a 404 (nothing made yet) is `null`. */
export async function orNull<T>(call: Promise<Result<T>>, what: string): Promise<T | null> {
  const r = await call;
  if (r.response.status === 404) return null;
  if (!r.response.ok || r.data === undefined) throw failure(r, what);
  return r.data;
}

export async function uploadRecording(attemptId: string, wav: Uint8Array): Promise<UploadAccepted> {
  const response = await globalThis.fetch(
    `${globalThis.location.origin}/api/attempts/${encodeURIComponent(attemptId)}/recording`,
    { method: "POST", headers: { "content-type": "audio/wav" }, body: wav as BodyInit },
  );
  const body: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const b = body as { code?: string; message?: string };
    throw new ApiFailure(response.status, b.code, b.message ?? `upload failed: ${response.status}`);
  }
  return body as UploadAccepted;
}

export const recordingUrl = (attemptId: string) => `/api/attempts/${encodeURIComponent(attemptId)}/recording`;
export const modelVoiceUrl = (clipId: string) => `/api/model-voice/${clipId}`;
