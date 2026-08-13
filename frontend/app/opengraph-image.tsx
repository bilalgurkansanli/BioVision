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
          background: "#fbfaf8",
          padding: "72px",
          fontFamily: "sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            fontSize: 26,
            letterSpacing: 3,
            color: "#6b6b6b",
            fontWeight: 700,
          }}
        >
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
            color: "#1a1a1a",
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
            borderLeft: "8px solid #7c5cbf",
            background: "#f5f2fc",
            borderRadius: 12,
            padding: "26px 32px",
            fontSize: 30,
            color: "#3a3a3a",
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
            color: "#5b5b5b",
          }}
        >
          Ölçülmeyen hiçbir sayı yayınlanmaz · AGPL-3.0
        </div>
      </div>
    ),
    size,
  );
}
