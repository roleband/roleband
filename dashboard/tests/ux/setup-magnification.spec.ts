import { magnificationTests } from "./setupMagnification";

/* The suite's Chromium: on Linux it rounds each letter to whole pixels (font
   hinting), so magnified text would not be in proportion and setup must stay
   at its plain size. WebKit and Chromium without hinting have their own files
   (setupMagnification.ts says why). */
magnificationTests({ browser: "chromium", magnifies: false });
