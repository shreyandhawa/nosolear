/** Plays `src`, or only `startMs`–`endMs` of it. */
export function ClipPlayer({
  src,
  label,
  startMs,
  endMs,
}: {
  src: string;
  label: string;
  startMs?: number | null;
  endMs?: number | null;
}) {
  const play = () => {
    const audio = new Audio(src);
    audio.addEventListener("loadedmetadata", () => {
      if (startMs != null) audio.currentTime = startMs / 1000;
      void audio.play();
    });
    if (endMs != null) {
      audio.addEventListener("timeupdate", () => {
        if (audio.currentTime >= endMs / 1000) audio.pause();
      });
    }
  };
  return (
    <button type="button" className="rounded border px-3 py-1" onClick={play}>
      {label}
    </button>
  );
}
