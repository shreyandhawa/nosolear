import { useMutation } from "@tanstack/react-query";
import { useEffect } from "react";
import { uploadRecording, type UploadAccepted } from "../api/http";
import { useRecorder } from "./useRecorder";

/** Record (click or Space), auto-stop at `maxSeconds`, then upload. The take stays in memory
 * until the upload succeeds, so a failed upload can be retried without recording again. */
export function Recorder({
  attemptId,
  maxSeconds,
  onUploaded,
}: {
  attemptId: string;
  maxSeconds: number;
  onUploaded: (accepted: UploadAccepted) => void;
}) {
  const rec = useRecorder({ maxSeconds });
  const upload = useMutation({
    mutationFn: (wav: Uint8Array) => uploadRecording(attemptId, wav),
    onSuccess: onUploaded,
  });
  const { mutate } = upload;

  useEffect(() => {
    if (rec.state === "recorded" && rec.wav) mutate(rec.wav);
  }, [rec.state, rec.wav, mutate]);

  const recording = rec.state === "recording";
  return (
    <section aria-label="Recorder" className="mt-4 flex flex-col gap-2">
      <div className="flex items-center gap-4">
        <button
          type="button"
          className="rounded border px-4 py-2"
          onClick={rec.toggle}
          disabled={rec.state === "starting" || upload.isPending || upload.isSuccess}
        >
          {recording ? "Stop" : rec.wav ? "Record again" : "Record"}
        </button>
        <meter aria-label="Input level" min={0} max={1} value={Math.min(1, rec.level * 4)} />
        <span>
          {rec.elapsed.toFixed(1)} s of {maxSeconds} s
        </span>
      </div>
      <p className="text-sm text-slate-600">Click or press Space to start and stop.</p>
      {rec.state === "denied" && (
        <p role="alert">Microphone access was denied. Allow it in the browser's site settings, then try again.</p>
      )}
      {rec.state === "error" && <p role="alert">The microphone could not be started.</p>}
      {upload.isPending && <p>Uploading…</p>}
      {upload.isSuccess && <p>Uploaded.</p>}
      {upload.isError && rec.wav && (
        <p role="alert">
          Upload failed: {upload.error.message}{" "}
          <button type="button" className="underline" onClick={() => mutate(rec.wav!)}>
            Retry upload
          </button>
        </p>
      )}
    </section>
  );
}
