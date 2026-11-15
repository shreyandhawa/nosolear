import { phoneticPair } from "../phonetic";

/** The sound to make, large, then the sound to avoid: "/θ/ not /t/". A key without a pair shows
 * its description. */
export function PhoneticPair({ errorKey, fallback }: { errorKey: string; fallback: string }) {
  const pair = phoneticPair(errorKey);
  if (!pair) return <span className="text-[0.6em]">{fallback}</span>;
  return (
    <>
      /{pair[0]}/
      <span className="text-[0.4em] text-ink/70"> not </span>
      <span className="text-ink/70">/{pair[1]}/</span>
    </>
  );
}
