import { test } from "./fixtures";
import { magnificationTests } from "./setupMagnification";

/* WebKit draws text in proportion, so setup magnifies (setupMagnification.ts). */
test.use({ browserName: "webkit" });
magnificationTests({ browser: "webkit", magnifies: true });
