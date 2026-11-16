import { phoneticPair } from "../phonetic";

/** The sound to make, large, then the sound to avoid: "/θ/ not /t/". A key without a pair shows
 * its description. */
export function PhoneticPair({ errorKey, fallback }: { errorKey: string; fallback: string }) {
  const pair = phoneticPair(errorKey);
  if (!pair) return <span className="text-[0.6em]">{fallback}</span>;
  return (
    <>
      /{pair[0]}/
      <span className="text-[0.4em] text-fg/72"> not </span>
      <span className="text-fg/72">/{pair[1]}/</span>
    </>
  );
}
