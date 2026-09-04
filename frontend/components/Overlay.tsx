"use client";

/**
 * Draws findings over the photograph — the measured shape, and the box around it.
 *
 * **Why the shape and not only the box.** The specialist measures `area_ratio`
 * from a segmentation mask, and the box is the shape it deliberately refuses to
 * measure: a thin diagonal scratch's bounding box is large and mostly empty, so
 * measuring it would overstate the damage several-fold. For a long time the box
 * was nonetheless the only thing on screen, beside a percentage taken from the
 * mask — a number nobody looking at the picture could check. `finding.outline` is
 * that mask, simplified for transport, so the two agree.
 *
 * The box stays, dashed and faint. It is what the model reports as the extent of
 * the instance, and hiding it would replace one incomplete picture with another.
 *
 * **Coordinates come from the response, not from the pixels on screen.** Boxes
 * are in the *stored* image's frame — the redacted, resized derivative the model
 * saw — which is not the file the user picked: ingestion resizes to a 1280 px
 * long edge, so a 4000×3000 photograph put every box at 32% of its true offset
 * and size when this scaled by the rendered image's natural size. It now scales
 * by `AnalyzeResponse.image`, through an SVG `viewBox` and CSS percentages.
 *
 * That also removes a bug class rather than fixing an instance of it: nothing
 * here waits for a load event any more. An image already decoded before React
 * attached its handler never fired `onLoad`, and the boxes then never appeared
 * at all — which is what happened with anything in cache and with the inline
 * data URIs the landing page uses.
 */

import { damageLabel } from "@/lib/labels";
import type { Finding, ImageFrame } from "@/lib/types";

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

const colorFor = (severity: string) =>
  SEVERITY_COLOR[severity] ?? "var(--severity-minor)";

export function Overlay({
  imageUrl,
  findings,
  frame,
  placeholder = false,
}: {
  imageUrl: string;
  findings: Finding[];
  /** The coordinate space `findings[].bbox` and `findings[].outline` are in. */
  frame: ImageFrame;
  /**
   * True when a stand-in model produced these shapes. The caption below explains
   * what a mask IS, and printing that under a fixed box invented by a mock would
   * make the most confident sentence on the screen describe the least real thing
   * on it.
   */
  placeholder?: boolean;
}) {
  const drawn = findings.length > 0 && frame.width > 0 && frame.height > 0;
  const shapes = findings.filter((finding) => finding.outline !== null).length;

  return (
    <figure className="overlay">
      <div className="overlay__stage">
        <img src={imageUrl} alt="Analiz edilen fotoğraf" className="overlay__image" />

        {drawn && (
          // `preserveAspectRatio="none"` is exact here rather than a shortcut:
          // the ingestion resize keeps the aspect ratio, so the frame and the
          // rendered image have the same one and there is nothing to letterbox.
          <svg
            className="overlay__shapes"
            viewBox={`0 0 ${frame.width} ${frame.height}`}
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            {findings.map((finding, index) => {
              const [x1, y1, x2, y2] = finding.bbox;
              const color = colorFor(finding.severity);
              return (
                <g key={index} style={{ color }}>
                  {/* The measured shape first, so the box sits over it. */}
                  {finding.outline && (
                    <polygon
                      className="overlay__mask"
                      points={finding.outline
                        .map(([x, y]) => `${x},${y}`)
                        .join(" ")}
                      vectorEffect="non-scaling-stroke"
                    />
                  )}
                  <rect
                    className={
                      finding.outline ? "overlay__rect overlay__rect--hint" : "overlay__rect"
                    }
                    x={x1}
                    y={y1}
                    width={x2 - x1}
                    height={y2 - y1}
                    vectorEffect="non-scaling-stroke"
                  />
                </g>
              );
            })}
          </svg>
        )}

        {drawn &&
          findings.map((finding, index) => {
            const [x1, y1] = finding.bbox;
            return (
              <span
                key={index}
                className="overlay__label"
                style={{
                  // Percentages rather than pixels: the stage is exactly the
                  // image, so this needs no measurement and survives a resize.
                  left: `${(x1 / frame.width) * 100}%`,
                  top: `${(y1 / frame.height) * 100}%`,
                  color: colorFor(finding.severity),
                }}
              >
                {/* "göçük · %42" was read as "42% of the car is dented". It is
                    the model's confidence in this one box, and the label has to
                    say which of the four percentages on this screen it is. */}
                {damageLabel(finding.type)} · %{Math.round(finding.score * 100)} güven
              </span>
            );
          })}
      </div>

      {findings.length > 0 && (
        <figcaption className="overlay__caption">
          {placeholder
            ? "Bu şekiller sahte bir model tarafından üretildi: konumları fotoğrafla ilgisiz ve her görselde aynı."
            : shapes > 0
              ? "Dolu alan modelin ölçtüğü hasar maskesi; kesikli kutu o maskeyi çevreleyen sınırdır. Yüzde alan bu maskeden hesaplanır, kutudan değil."
              : "Kutular, modelin gördüğü işlenmiş görselin koordinatlarındadır."}
        </figcaption>
      )}
    </figure>
  );
}
