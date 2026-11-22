import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { useCallback, useState } from "react";
import { renderHookWithProviders } from "../../test/render";
import { server } from "../../test/server";
import { useTake } from "./useTake";

// A recorder whose takes the test starts by hand: starting, then a recorded WAV.
let fake: { take: (n: number) => void };
vi.mock("./useRecorder", () => ({
  useRecorder: () => {
    const [state, setState] = useState("idle");
    const [wav, setWav] = useState<Uint8Array | null>(null);
    fake = {
      take: (n) => {
        setState("starting");
        setTimeout(() => {
          setWav(new Uint8Array([n]));
          setState("recorded");
        }, 0);
      },
    };
    const reset = useCallback(() => {
      setWav(null);
      setState("idle");
    }, []);
    return { state, level: 0, elapsed: 0, wav, toggle: () => {}, reset, getLevel: () => 0 };
  },
}));

test("each take is uploaded once, to its own attempt, when the attempt id moves on", async () => {
  const posted: string[] = [];
  server.use(
    http.post("/api/attempts/:id/recording", ({ params }) => {
      posted.push(String(params.id));
      return HttpResponse.json({ job_id: "j", attempt_id: String(params.id) }, { status: 202 });
    }),
  );
  const { result, rerender } = renderHookWithProviders(({ id }: { id: string }) => useTake(id, 60, () => {}), {
    id: "a1",
  });
  act(() => fake.take(1));
  await waitFor(() => expect(result.current.phase).toBe("uploaded"));
  rerender({ id: "a2" });
  await waitFor(() => expect(result.current.phase).toBe("ready"));
  act(() => fake.take(2));
  await waitFor(() => expect(result.current.phase).toBe("uploaded"));
  expect(posted).toEqual(["a1", "a2"]);
});
