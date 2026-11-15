import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { modelVoiceUrl, must } from "../api/http";

/** The model voice for stored text. Synthesis (a cached, metered POST) runs only on a click. */
export function ModelVoice({ source, id }: { source: "feedback_item" | "content_item"; id: string }) {
  const voice = useMutation({
    mutationFn: (rate_percent: number) =>
      must(api.POST("/api/model-voice", { body: { source, id, rate_percent } }), "model voice"),
    onSuccess: (clip) => void new Audio(modelVoiceUrl(clip.clip_id)).play(),
  });
  return (
    <span className="inline-flex gap-2">
      <button type="button" className="rounded border px-3 py-1" onClick={() => voice.mutate(0)} disabled={voice.isPending}>
        Model voice
      </button>
      <button type="button" className="rounded border px-3 py-1" onClick={() => voice.mutate(-30)} disabled={voice.isPending}>
        Slower
      </button>
      {voice.isError && <span role="alert">{voice.error.message}</span>}
    </span>
  );
}
