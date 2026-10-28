// Background location task: must be defined at module scope, imported from the root layout.
import type { LocationObject } from "expo-location";
import * as TaskManager from "expo-task-manager";

import { handleLocations, LOCATION_TASK } from "@/src/sharing/session";

TaskManager.defineTask<{ locations: LocationObject[] }>(LOCATION_TASK, async ({ data, error }) => {
  if (error || !data) return;
  await handleLocations(data.locations);
});
