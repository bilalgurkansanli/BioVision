import { ImageResponse } from "next/og";

export const alt = "BioVision — ne bilmediğini söyleyen hasar analizi";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * The share card.
 *
 * Generated rather than shipped as a file so it cannot drift from the wording it
 * illustrates. The card shows the *refusal* state, not a successful measurement:
 * what is distinctive about this system is the answer it gives when it cannot
 * measure, and a share preview showing green checkmarks would advertise the
 * opposite of the argument.
 *
 * Drawn on the dark ground because that is the site's default theme, and a
 * light card would misrepresent the page it links to. The colours are the
 * literal values of --bg, --accent and --absent; changing them in globals.css
 * means changing them here.
 */
export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          background: "#0f1115",
          padding: "72px",
          fontFamily: "sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 14,
            fontSize: 26,
            letterSpacing: 3,
            color: "#9ba1aa",
            fontWeight: 700,
          }}
        >
          <div
            style={{
              display: "flex",
              width: 18,
              height: 18,
              borderRadius: 4,
              background: "#f5c518",
            }}
          />
          BIOVISION
        </div>

        {/* Two blocks rather than a <br />: ImageResponse lays out with flexbox
            and ignores line breaks, which silently ran the title off the edge. */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            marginTop: 20,
            fontSize: 62,
            fontWeight: 700,
            color: "#f2f2f0",
            lineHeight: 1.18,
            letterSpacing: -1.5,
          }}
        >
          <div style={{ display: "flex" }}>Ne bilmediğini söyleyen</div>
          <div style={{ display: "flex" }}>hasar analizi</div>
        </div>

        <div
          style={{
            display: "flex",
            marginTop: 44,
            borderLeft: "8px solid #a78bfa",
            background: "#221b38",
            borderRadius: 12,
            padding: "26px 32px",
            fontSize: 30,
            color: "#e6e2f5",
            lineHeight: 1.35,
          }}
        >
          &laquo;Bu alan için eğitilmiş bir modelimiz yok — tahmin yürütmek yerine
          bilmediğimizi söylüyoruz.&raquo;
        </div>

        <div
          style={{
            display: "flex",
            marginTop: 40,
            fontSize: 24,
            color: "#9ba1aa",
          }}
        >
          Ölçülmeyen hiçbir sayı yayınlanmaz · AGPL-3.0
        </div>
      </div>
    ),
    size,
  );
}
