"use client";

/**
 * The worked example on the landing page.
 *
 * It renders `ResultCard` — the same component `/analiz` renders, not a
 * mock-up of it. That is the point: a hand-built approximation of the result
 * card would drift from the real one within a release or two, and a landing
 * page showing an interface the product no longer has is its own kind of
 * unmeasured claim.
 *
 * The three outcomes are tabs rather than three stacked cards because seeing
 * them replace each other in the same frame is what makes the distinction
 * land — they are alternatives, not a list.
 */

import { useRef, useState } from "react";

import { DEMO_ORDER, DEMO_SAMPLES } from "@/lib/demo";
import type { ResultKind } from "@/lib/types";
import { ResultCard } from "./ResultCard";

export function Demo() {
  const [active, setActive] = useState<ResultKind>("measured");
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const sample = DEMO_SAMPLES[active];

  // A tablist owns its arrow keys: Tab moves out of the group, arrows move
  // within it. Without this the component looks like tabs and behaves like a
  // row of buttons, which is worse than not using the role at all.
  function onKeyDown(event: React.KeyboardEvent, index: number) {
    const delta =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (delta === 0) return;

    event.preventDefault();
    const next = (index + delta + DEMO_ORDER.length) % DEMO_ORDER.length;
    // The modulo cannot leave the array, but `noUncheckedIndexedAccess` is on
    // and this is the honest way to satisfy it: no assertion, no cast.
    const kind = DEMO_ORDER[next];
    if (!kind) return;

    setActive(kind);
    tabs.current[next]?.focus();
  }

  return (
    <div className="demo">
      <div className="demo__tabs" role="tablist" aria-label="Örnek sonuç türü">
        {DEMO_ORDER.map((kind, index) => (
          <button
            key={kind}
            ref={(node) => {
              tabs.current[index] = node;
            }}
            type="button"
            role="tab"
            id={`demo-tab-${kind}`}
            aria-controls="demo-panel"
            aria-selected={active === kind}
            tabIndex={active === kind ? 0 : -1}
            className={`demo__tab demo__tab--${kind} ${
              active === kind ? "demo__tab--active" : ""
            }`}
            onClick={() => setActive(kind)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {DEMO_SAMPLES[kind].label}
          </button>
        ))}
      </div>

      <div
        className="demo__panel"
        role="tabpanel"
        id="demo-panel"
        aria-labelledby={`demo-tab-${active}`}
      >
        <p className="demo__summary">{sample.summary}</p>

        <p className="demo__caveat">
          <span className="demo__caveat-tag">Örnek</span>
          {sample.caveat}
        </p>

        {/* key forces a remount per outcome: ResultCard's Overlay measures the
            image on load, and reusing the instance across a source change left
            boxes scaled to the previous image for a frame. */}
        <ResultCard key={active} result={sample.response} imageUrl={sample.image} />
      </div>
    </div>
  );
}
