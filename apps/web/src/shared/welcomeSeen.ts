const KEY = "nosolear.welcomeSeen";

// A per-browser convenience only: storage can be blocked, and then Welcome shows again.
export function welcomeSeen(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function markWelcomeSeen() {
  try {
    localStorage.setItem(KEY, "1");
  } catch {
    /* storage blocked: Welcome just shows again */
  }
}
