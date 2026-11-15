import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { uploadRecording, type UploadAccepted } from "../api/http";
import { useRecorder } from "./useRecorder";

export type TakePhase = "off" | "ready" | "recording" | "uploading" | "uploaded" | "error";

/** One take: record (click or Space), auto-stop at `maxSeconds`, then upload. The take stays in
 * memory until the upload succeeds, so a failed upload can be retried without recording again.
 * With no attempt the microphone is off. */
export function useTake(attemptId: string | null, maxSeconds: number, onUploaded: (accepted: UploadAccepted) => void) {
  const [deviceId, setDeviceId] = useState<string | undefined>();
  const rec = useRecorder({ maxSeconds, keyboard: attemptId !== null, deviceId });
  const upload = useMutation({
    mutationFn: (wav: Uint8Array) => uploadRecording(attemptId!, wav),
    onSuccess: onUploaded,
  });
  const { mutate, reset: resetUpload } = upload;
  const { reset: resetRecording } = rec;

  // A new attempt starts clean, as the old per-attempt recorder did.
  useEffect(() => {
    resetUpload();
    resetRecording();
  }, [attemptId, resetUpload, resetRecording]);

  useEffect(() => {
    if (rec.state === "recorded" && rec.wav && attemptId) mutate(rec.wav);
  }, [rec.state, rec.wav, mutate, attemptId]);

  const message =
    rec.state === "denied"
      ? "Microphone access was denied. Allow it in the browser's site settings, then try again."
      : rec.state === "error"
        ? "The microphone could not be started."
        : upload.isError
          ? `Upload failed: ${upload.error.message}`
          : null;

  const phase: TakePhase =
    attemptId === null
      ? "off"
      : message
        ? "error"
        : rec.state === "recording" || rec.state === "starting"
          ? "recording"
          : upload.isPending
            ? "uploading"
            : upload.isSuccess
              ? "uploaded"
              : "ready";

  return {
    phase,
    message,
    elapsed: rec.elapsed,
    level: rec.level,
    getLevel: rec.getLevel,
    maxSeconds,
    canToggle: attemptId !== null && !upload.isPending && !upload.isSuccess && rec.state !== "starting",
    toggle: rec.toggle,
    retry: upload.isError && rec.wav ? () => mutate(rec.wav!) : null,
    deviceId,
    setDeviceId,
  };
}

export type Take = ReturnType<typeof useTake>;
