import { test } from "./fixtures";
import { magnificationTests } from "./setupMagnification";

/* Chromium without font hinting, as on macOS and Windows: text in proportion,
   so setup magnifies (setupMagnification.ts). */
test.use({ browserName: "chromium", launchOptions: { args: ["--font-render-hinting=none"] } });
magnificationTests({ browser: "chromium", magnifies: true });
