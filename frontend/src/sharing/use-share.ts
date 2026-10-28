import { useEffect, useSyncExternalStore } from "react";

import { getShare, restoreShare, subscribe } from "@/src/sharing/session";

export function useShare() {
  useEffect(() => {
    restoreShare();
  }, []);
  return useSyncExternalStore(subscribe, getShare, getShare);
}
