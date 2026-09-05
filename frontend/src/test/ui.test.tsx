import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  Badge, ConfidenceMeter, EmptyState, ErrorBox, ResultPanel,
} from "../components/ui";
import type { EngineResult } from "../types/api";

describe("Badge", () => {
  it("renders children with the tone class", () => {
    render(<Badge tone="danger">BLOCKED</Badge>);
    const b = screen.getByText("BLOCKED");
    expect(b.className).toContain("badge-danger");
  });
});

describe("EmptyState", () => {
  it("announces empty state politely", () => {
    render(<EmptyState message="No data available" />);
    expect(screen.getByRole("status").textContent).toContain("No data available");
  });
});

describe("ErrorBox", () => {
  it("shows the correlation id when present", () => {
    render(<ErrorBox error={{ message: "Rate limit reached.", requestId: "abc-123" }} />);
    expect(screen.getByRole("alert").textContent).toContain("Rate limit reached.");
    expect(screen.getByRole("alert").textContent).toContain("abc-123");
  });

  it("shows retry timing for 429 responses", () => {
    render(<ErrorBox error={{ message: "Rate limit reached.", retryAfter: 42 }} />);
    expect(screen.getByRole("alert").textContent).toContain("42");
  });
});

describe("ConfidenceMeter", () => {
  it("exposes an accessible meter with the value", () => {
    render(<ConfidenceMeter value={0.91} />);
    const meter = screen.getByRole("meter");
    expect(meter.getAttribute("aria-valuenow")).toBe("91");
  });
});

const SAMPLE: EngineResult = {
  engine: "payment",
  risk_score: 0.15,
  confidence: 0.86,
  decision: "CLEAR",
  signals: [{
    name: "velocity_24h", value: 0.1, weight: 0.2,
    reason: "24-hour velocity signal", source: "payment",
  }],
  reasons: ["Risk below CLEAR threshold"],
  evidence: [],
  model_version: "rules-only",
  processing_time_ms: 2.4,
  extra: {},
  timestamp: "2026-08-30T12:00:00Z",
};

describe("ResultPanel", () => {
  it("renders decision, reasons and signals from the engine result", () => {
    render(<ResultPanel result={SAMPLE} />);
    expect(screen.getByText("Verified")).toBeTruthy();
    expect(screen.getByText("Risk below CLEAR threshold")).toBeTruthy();
    expect(screen.getByText("velocity_24h")).toBeTruthy();
    expect(screen.getByText(/rules-only/)).toBeTruthy();
  });

  it("labels reasons section accessibly", () => {
    render(<ResultPanel result={SAMPLE} />);
    expect(screen.getByText("Why this decision")).toBeTruthy();
  });
});
