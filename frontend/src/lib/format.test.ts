import { describe, expect, it } from "vitest";
import { formatKickoff } from "./format";

describe("formatKickoff", () => {
  it("states when kickoff time is not available", () => {
    expect(formatKickoff(null)).toBe("Kickoff time unavailable");
  });

  it("does not emit a placeholder for a valid timestamp", () => {
    expect(formatKickoff("2025-01-01T15:00:00Z", "en-GB")).not.toBe("Kickoff time unavailable");
  });
});
