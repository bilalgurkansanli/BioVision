"use client";

/**
 * Draws findings over the photograph.
 *
 * Boxes are in pixels of the *stored* image — the redacted, resized derivative
 * the model actually saw — so they are scaled by the rendered size rather than
 * assumed to match. Getting that wrong puts boxes near the damage instead of on
 * it, which reads as a model that is almost right.
 */

import { useEffect, useRef, useState } from "react";

import { damageLabel } from "@/lib/labels";
import type { Finding } from "@/lib/types";

/**
 * Box colours are the same tokens the severity badges use, referenced rather
 * than duplicated. They previously repeated the hex values, which meant the
 * amber box and the amber badge drifted apart the moment the palette moved off
 * amber to keep clear of the brand accent.
 */
const SEVERITY_COLOR: Record<string, string> = {
  minor: "var(--severity-minor)",
  moderate: "var(--severity-moderate)",
  severe: "var(--severity-severe)",
};

export function Overlay({
  imageUrl,
  findings,
}: {
  imageUrl: string;
  findings: Finding[];
}) {
  const imageRef = useRef<HTMLImageElement>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [rendered, setRendered] = useState<{ w: number; h: number } | null>(null);

  // `onLoad` alone is not enough: an image that finished decoding before React
  // attached the handler never fires it, and the boxes then never appear at
  // all. That happens with anything already in cache and with the inline data
  // URIs the landing page example uses. Found by the boxes silently not
  // rendering there while the findings list below them was correct.
  useEffect(() => {
    const element = imageRef.current;
    if (element?.complete && element.naturalWidth > 0) {
      setNatural({ w: element.naturalWidth, h: element.naturalHeight });
    }
  }, [imageUrl]);

  // The rendered size changes with the viewport, so the scale is recomputed on
  // resize rather than measured once at load.
  useEffect(() => {
    const element = imageRef.current;
    if (!element) return;

    const measure = () =>
      setRendered({ w: element.clientWidth, h: element.clientHeight });

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [natural]);

  const scaleX = natural && rendered ? rendered.w / natural.w : 1;
  const scaleY = natural && rendered ? rendered.h / natural.h : 1;

  return (
    <figure className="overlay">
      <div className="overlay__stage">
        <img
          ref={imageRef}
          src={imageUrl}
          alt="Analiz edilen fotoğraf"
          className="overlay__image"
          onLoad={(event) => {
            const target = event.currentTarget;
            setNatural({ w: target.naturalWidth, h: target.naturalHeight });
          }}
        />

        {natural &&
          findings.map((finding, index) => {
            const [x1, y1, x2, y2] = finding.bbox;
            return (
              <span
                key={index}
                className="overlay__box"
                style={{
                  left: `${x1 * scaleX}px`,
                  top: `${y1 * scaleY}px`,
                  width: `${(x2 - x1) * scaleX}px`,
                  height: `${(y2 - y1) * scaleY}px`,
                  borderColor:
                    SEVERITY_COLOR[finding.severity] ?? "var(--severity-minor)",
                }}
              >
                <span className="overlay__label">
                  {damageLabel(finding.type)} · %{Math.round(finding.score * 100)}
                </span>
              </span>
            );
          })}
      </div>

      {findings.length > 0 && (
        <figcaption className="overlay__caption">
          Kutular, modelin gördüğü işlenmiş görselin koordinatlarındadır.
        </figcaption>
      )}
    </figure>
  );
}
