import { describe, expect, it } from "vitest";
import { formatDate, formatDuration } from "./callFormatting";

describe("call formatting", () => {
  it("formats durations and handles missing duration values", () => {
    expect(formatDuration(125)).toBe("2:05");
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });

  it("returns an em dash for invalid dates", () => {
    expect(formatDate("not-a-date")).toBe("—");
  });
});
