import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { api } from "../../shared/api/client";
import { must } from "../../shared/api/http";
import { MicStage } from "../../shared/audio/MicStage";
import { Desk, Label, StatusDot, TitleBlock } from "../../shared/ui/Desk";
import { ctaLink } from "../../shared/ui/styles";
import { markWelcomeSeen } from "../../shared/welcomeSeen";

const PARTS = [
  {
    name: "Setup",
    time: "About 10 minutes, once",
    what: "Add your Azure Speech key to .env, and an Anthropic key if you want the coach, then press Run check. Azure scores your sounds and speaks the model voice. The coach is optional; without it, feedback uses written templates.",
  },
  {
    name: "Calibration",
    time: "About 10 minutes, once",
    what: "You say a set of words, some on purpose with the wrong sound. This shows which detectors can be trusted on your voice. Press Space to record, one take per prompt.",
  },
  {
    name: "Baseline",
    time: "About 5 minutes, once",
    what: "Read a passage and a word list, talk freely, answer quick questions and make one point with a reason and an example. Press Space to record, one take per prompt.",
  },
  {
    name: "Report",
    time: "A minute to read",
    what: "Your errors ranked, each with its miss rate and clips of you making it. Open it again any time from Report.",
  },
  {
    name: "Today",
    time: "About 15 minutes a day",
    what: "Speak for 60 seconds, then get one fix per skill. Play your clip against the model voice and say it again. Space records.",
  },
  {
    name: "Progress",
    time: "A minute",
    what: "Each tracked error with its miss rate, how sure the app is, and the clips behind it. It changes as you practise.",
  },
];

export function WelcomePage() {
  const [i, setI] = useState(0);
  const part = PARTS[i];
  const onboarding = useQuery({
    queryKey: ["onboarding"],
    queryFn: () => must(api.GET("/api/onboarding"), "GET /api/onboarding"),
  });
  useEffect(markWelcomeSeen, []);
  return (
    <Desk
      stateKey={part.name}
      title={
        <TitleBlock step="Welcome" sub="Nosolear learns your own errors and practises exactly those.">
          {part.name}
        </TitleBlock>
      }
      text={
        <>
          <p className="text-[0.8125rem] text-fg/72">{part.time}</p>
          <p className="mt-2">{part.what}</p>
        </>
      }
      stage={<MicStage state="idle" hint="Space records" />}
      card={
        <>
          <Label>The parts</Label>
          <ol className="flex flex-col gap-1">
            {PARTS.map((p, n) => (
              <li key={p.name}>
                <button
                  type="button"
                  aria-pressed={n === i}
                  onClick={() => setI(n)}
                  className="flex w-full items-center gap-2 py-1 text-left text-fg/72 hover:text-fg aria-pressed:font-semibold aria-pressed:text-fg"
                >
                  <StatusDot ok={n === i} />
                  {p.name}
                </button>
              </li>
            ))}
          </ol>
        </>
      }
      cta={
        onboarding.data?.step === "daily_plan" ? (
          <Link to="/today" className={ctaLink}>
            Go to Today
          </Link>
        ) : (
          <Link to="/setup" className={ctaLink}>
            Start setup
          </Link>
        )
      }
    />
  );
}
