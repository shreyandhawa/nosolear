import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import { modelVoiceUrl, must } from "../api/http";
import { Action } from "../ui/Desk";

/** The model voice for stored text, normal and slow. Synthesis (a cached, metered POST) runs only
 * on a click. */
export function ModelVoice({ source, id }: { source: "feedback_item" | "content_item"; id: string }) {
  const voice = useMutation({
    mutationFn: (rate_percent: number) =>
      must(api.POST("/api/model-voice", { body: { source, id, rate_percent } }), "model voice"),
    onSuccess: (clip) => void new Audio(modelVoiceUrl(clip.clip_id)).play(),
  });
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="mr-1 text-[0.8125rem] font-medium text-ink/70">Model voice</span>
      <Action onClick={() => voice.mutate(0)} disabled={voice.isPending}>
        Normal
      </Action>
      <Action onClick={() => voice.mutate(-30)} disabled={voice.isPending}>
        Slow
      </Action>
      {voice.isError && (
        <p role="alert" className="w-full text-[0.9375rem]">
          {voice.error.message}
        </p>
      )}
    </div>
  );
}
