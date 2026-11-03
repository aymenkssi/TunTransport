// Entry point. The background location task is defined before anything else: when the app has been
// closed, Android restarts it without any screen to deliver GPS fixes, and the task must exist then.
import "./src/sharing/task";
import "expo-router/entry";
