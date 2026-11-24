import { describe, expect, it, vi } from "vitest";
import { chunkOnce } from "./notesEditorChunk";

describe("a chunk asked for ahead", () => {
  it("is asked for once however many ask, and is here once it has loaded", async () => {
    const importer = vi.fn(async () => "editor");
    const chunk = chunkOnce(importer);
    expect(chunk.now()).toBeNull();
    const [first, second] = await Promise.all([chunk.load(), chunk.load()]);
    expect([first, second]).toEqual(["editor", "editor"]);
    expect(importer).toHaveBeenCalledTimes(1);
    expect(chunk.now()).toBe("editor");
    await chunk.load();
    expect(importer, "loaded, it is not asked for again").toHaveBeenCalledTimes(1);
  });

  it("asks again after a load that failed, so an early ask on a dropped connection is not the last word", async () => {
    const importer = vi.fn<() => Promise<string>>()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce("editor");
    const chunk = chunkOnce(importer);
    await expect(chunk.load()).rejects.toThrow("offline");
    expect(chunk.now(), "nothing is here after the failure").toBeNull();
    // The Workspace asks for itself when it opens.
    await expect(chunk.load()).resolves.toBe("editor");
    expect(importer).toHaveBeenCalledTimes(2);
    expect(chunk.now()).toBe("editor");
  });
});
