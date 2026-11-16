import { useRef, type CSSProperties, type ReactNode } from "react";

// The composed entrance plays once per page load, not on every navigation.
let introduced = false;

type Slots = {
  /** Changes when the screen's state changes (speak, analyzing, feedback); slots then cross-fade. */
  stateKey: string;
  title: ReactNode;
  media?: ReactNode;
  text?: ReactNode;
  stage: ReactNode;
  card?: ReactNode;
  note?: ReactNode;
  cta?: ReactNode;
};

/** The one layout every screen uses. Only the content changes; the stage never moves. */
export function Desk({ stateKey, title, media, text, stage, card, note, cta }: Slots) {
  const mountedKey = useRef(stateKey);
  const animate = !introduced || stateKey !== mountedKey.current;
  introduced = true;
  const slot = (content: ReactNode, i: number, label: string) => (
    <section aria-label={label} className="slot">
      <div key={stateKey} className={animate ? "swap" : undefined} style={{ "--i": i } as CSSProperties}>
        {content}
      </div>
    </section>
  );
  return (
    <main className="desk">
      <div className="desk-left">
        {slot(title, 0, "Title")}
        {slot(media, 1, "Listen")}
        {slot(text, 2, "Instructions")}
      </div>
      <div className="stage">{stage}</div>
      <div className="desk-right">
        {slot(card, 3, "This step")}
        {slot(note, 4, "Notes")}
        <div className="flex items-end p-4">{cta}</div>
      </div>
    </main>
  );
}

/** The step and count, then the thing to say, large. */
export function TitleBlock({ step, children, sub }: { step: ReactNode; children?: ReactNode; sub?: ReactNode }) {
  return (
    <div className="flex h-full flex-col">
      <h1 className="text-[1.0625rem] font-semibold">{step}</h1>
      {children && (
        <p lang="en" className="font-display mt-auto text-[clamp(4rem,6.5vw,7.5rem)] leading-[0.95] tracking-[-0.02em] break-words">
          {children}
        </p>
      )}
      {sub && <p className="mt-3 text-fg/72">{sub}</p>}
    </div>
  );
}

export function Label({ children }: { children: ReactNode }) {
  return <h2 className="mb-3 text-[0.8125rem] font-medium text-fg/72">{children}</h2>;
}

/** Status by shape and words: a filled dot when ready, a hollow one otherwise. */
export function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      aria-hidden
      className={`inline-block size-2.5 shrink-0 rounded-full border-[1.5px] border-current ${ok ? "bg-current" : ""}`}
    />
  );
}

/** The one primary action: an On air fill with Ink text. */
export function Cta({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className="press w-full rounded-md bg-onair px-4 py-4 text-left text-[1.0625rem] font-semibold text-ink hover:bg-[color-mix(in_oklch,var(--color-onair)_88%,var(--color-ink))] disabled:bg-fg/8 disabled:text-fg/72 disabled:opacity-100"
    >
      {children}
    </button>
  );
}

/** A secondary action: an Ink outline on Paper. */
/** After a pointer click, give focus back to the page, so Space stays the record shortcut
 * instead of pressing this button again. Keyboard focus is left where it is. */
export const releaseFocus = (e: React.MouseEvent<HTMLButtonElement>) => {
  if (e.detail) e.currentTarget.blur();
};

export function Action({ children, onClick, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      onClick={(e) => {
        onClick?.(e);
        releaseFocus(e);
      }}
      className={`press rounded-full border border-fg/40 px-4 py-1.5 text-[0.9375rem] font-medium hover:border-fg ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}
