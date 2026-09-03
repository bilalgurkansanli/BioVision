/**
 * The worked examples shown on the landing page.
 *
 * Three constraints shaped this file, and all three come from the project
 * rather than from taste:
 *
 * 1. **No photographs.** Everything under `data/` is referenced by manifest and
 *    never committed (ADR-005), and the one set that may be redistributed —
 *    `backend/tests/golden/images/` — holds no files. So the sample images are
 *    drawn. That is the better answer anyway: a photorealistic image under a
 *    confident-looking box would imply a measurement happened, and none did.
 *
 * 2. **The responses are typed as the real `AnalyzeResponse`.** If the API
 *    contract gains a field or changes a shape, this file stops compiling
 *    instead of quietly showing a response the API can no longer produce.
 *
 * 3. **Every field here is what the live system would return.** The vehicle
 *    specialist ships, so the `measured` shape is reachable — but the details
 *    have to keep matching production, not flatter it. `calibrated` is false
 *    because temperature scaling was measured and refused (ADR-029); the
 *    severities are what `severity_for` computes from these classes and areas
 *    (ADR-031); `class_recall` carries the measured figures from README 7.3,
 *    including the two classes that miss three quarters of what is there.
 */

import type { AnalyzeResponse, ResultKind } from "./types";

/**
 * Sample images are inline SVG rather than files: they cost no request, scale
 * to any width without a second asset, and cannot be mistaken for evidence.
 *
 * The canvas is fixed at 800×500 because `Overlay` scales finding boxes by the
 * image's natural size — the bounding boxes below are in this coordinate space,
 * which is exactly how the real API reports them (pixels of the stored image).
 */
const CANVAS = { width: 800, height: 500 };

const draw = (body: string): string =>
  `data:image/svg+xml;utf8,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${CANVAS.width}" height="${CANVAS.height}" viewBox="0 0 800 500">${body}</svg>`,
  )}`;

/* A car seen from behind: dented rear quarter, scratched panel, broken lamp. */
const CAR = draw(`
<rect width="800" height="500" fill="#d7d3cc"/>
<rect y="392" width="800" height="108" fill="#bcb7ae"/>
<ellipse cx="400" cy="404" rx="286" ry="24" fill="#a49f95" opacity="0.5"/>
<rect x="150" y="132" width="500" height="262" rx="30" fill="#5c6879"/>
<rect x="212" y="152" width="376" height="88" rx="14" fill="#333c48"/>
<path d="M224 162 L392 158 L388 232 L220 234 Z" fill="#3f4a58"/>
<rect x="160" y="286" width="480" height="5" rx="2" fill="#4d5867"/>
<rect x="168" y="252" width="104" height="40" rx="9" fill="#a83a3a"/>
<rect x="528" y="252" width="104" height="40" rx="9" fill="#a83a3a"/>
<rect x="150" y="336" width="500" height="56" rx="16" fill="#4a5563"/>
<rect x="352" y="350" width="96" height="30" rx="5" fill="#d3cfc8"/>
<g opacity="0.85">
<ellipse cx="258" cy="316" rx="46" ry="28" fill="#4b5666"/>
<ellipse cx="258" cy="316" rx="28" ry="16" fill="#414b59"/>
<ellipse cx="256" cy="313" rx="12" ry="7" fill="#39424e"/>
</g>
<g stroke="#96a1b0" stroke-width="3" stroke-linecap="round" opacity="0.9">
<path d="M446 330 L600 302"/>
<path d="M452 338 L588 313"/>
<path d="M470 344 L566 324"/>
</g>
<g stroke="#f0d9d9" stroke-width="2.5" stroke-linecap="round">
<path d="M556 254 L572 292"/>
<path d="M580 252 L566 290"/>
<path d="M534 274 L628 268"/>
</g>
<rect x="528" y="252" width="104" height="40" rx="9" fill="#7d2c2c" opacity="0.45"/>
`);

/* A phone with a shattered screen: a real domain, with no specialist behind it. */
const PHONE = draw(`
<rect width="800" height="500" fill="#cbc6be"/>
<rect x="70" y="60" width="660" height="380" rx="18" fill="#bdb8af"/>
<rect x="286" y="52" width="228" height="396" rx="30" fill="#23262b"/>
<rect x="298" y="72" width="204" height="356" rx="20" fill="#3d434c"/>
<rect x="366" y="60" width="68" height="12" rx="6" fill="#191c20"/>
<g stroke="#cfd6df" stroke-width="2.2" stroke-linecap="round" opacity="0.95">
<path d="M400 168 L336 92"/>
<path d="M400 168 L470 96"/>
<path d="M400 168 L318 196"/>
<path d="M400 168 L486 210"/>
<path d="M400 168 L360 268"/>
<path d="M400 168 L452 286"/>
<path d="M336 92 L470 96"/>
<path d="M318 196 L360 268"/>
<path d="M486 210 L452 286"/>
<path d="M360 268 L452 286"/>
<path d="M318 196 L302 300"/>
<path d="M486 210 L496 312"/>
<path d="M360 268 L330 400"/>
<path d="M452 286 L470 404"/>
</g>
<circle cx="400" cy="168" r="7" fill="#e8edf3"/>
`);

/* Deliberately unreadable: overlapping surfaces with no identifiable subject. */
const AMBIGUOUS = draw(`
<rect width="800" height="500" fill="#8f8b84"/>
<path d="M0 300 Q200 210 420 268 T800 232 L800 500 L0 500 Z" fill="#7b776f"/>
<path d="M0 372 Q260 316 520 366 T800 340 L800 500 L0 500 Z" fill="#696560"/>
<ellipse cx="250" cy="190" rx="230" ry="150" fill="#9b968e" opacity="0.55"/>
<ellipse cx="596" cy="150" rx="180" ry="128" fill="#a49f96" opacity="0.4"/>
<g stroke="#5f5b56" stroke-width="9" opacity="0.3" stroke-linecap="round">
<path d="M-20 120 L300 420"/>
<path d="M180 40 L520 470"/>
<path d="M420 20 L760 400"/>
</g>
<ellipse cx="400" cy="250" rx="420" ry="260" fill="#8f8b84" opacity="0.28"/>
`);

export interface DemoSample {
  /** Tab label. */
  label: string;
  /** One line under the tabs, explaining what this outcome means. */
  summary: string;
  /**
   * What is not true about this example. Rendered as a notice, never hidden in
   * small print — for `measured` it says the system cannot produce this today.
   */
  caveat: string;
  image: string;
  response: AnalyzeResponse;
}

const PRIVACY_CLEAN = {
  faces_blurred: 0,
  plates_blurred: 0,
  face_detector: "yunet_2023mar",
  /** Never redacted — a different claim from "none found". See ADR-015. */
  plate_detector: null,
} as const;

export const DEMO_SAMPLES: Record<ResultKind, DemoSample> = {
  measured: {
    label: "Ölçüldü",
    summary:
      "Alan için eğitilmiş bir uzman model var. Bulgular, kutular ve alan oranları o modelin çıktısı.",
    caveat:
      "Canlı sistem bu cevabı bugün üretiyor: araç uzmanı VehiDE üzerinde eğitildi ve çalışıyor. Buradaki fotoğraf ve kutular temsilîdir; gerçek doğruluk sınıftan sınıfa çok değişiyor — README §7.3'te yedi sınıfın hepsi, en kötü satırlar dahil.",
    image: CAR,
    response: {
      request_id: "ornek-olculdu",
      overall_severity: "severe",
      overall_severity_confidence: 0.9591,
      overall_severity_calibrated: false,
      // The real counts from README 7.8, not invented ones. A sample that
      // showed a rounder, friendlier frequency would be advertising a
      // reliability the live system does not report.
      overall_severity_reliability: {
        predicted: "severe",
        support: 54,
        outcomes: [
          { band: "minor", count: 0, share: 0 },
          { band: "moderate", count: 8, share: 0.1481 },
          { band: "severe", count: 46, share: 0.8519 },
        ],
        correct_share: 0.8519,
        worse_share: 0,
        evaluation_set: "prajwalbhamere/car-damage-severity-dataset (248 held-out images)",
        evaluation_note_tr:
          "Bu oranlar 248 görselden ölçüldü. Bir olasılık modelinden değil, sayımdan geliyorlar. Ölçüm setindeki hafif/orta/ağır dağılımı gerçek bir hasar kuyruğunun dağılımı değildir; dağılım değişirse bu oranlar da değişir.",
      },
      domain: "vehicle",
      domain_confidence: 0.94,
      // False, because it is false in production: temperature scaling was fitted,
      // made ECE worse on held-out data, and was not loaded. A sample that
      // claimed otherwise would advertise a guarantee the system does not give.
      domain_confidence_calibrated: false,
      specialist_model: "vehide-yolo-seg-v1",
      calibrated: false,
      // A vehicle WAS located in this sample, so the vehicle-relative figure
      // is present. The null case is exercised by the other two samples.
      damage_region: {
        area_ratio_image: 0.0447,
        area_ratio_vehicle: 0.2131,
        vehicle_frame_share: 0.2077,
        instances: 3,
        confidence_floor: 0.1,
        calibrated: false,
      },
      findings: [
        {
          type: "dent",
          class_recall: 0.253,
          class_reliable: false,
          score: 0.91,
          bbox: [206, 282, 312, 350],
          area_ratio: 0.018,
          severity: "moderate",
          severity_calibrated: false,
        },
        {
          type: "scratch",
          class_recall: 0.275,
          class_reliable: false,
          score: 0.83,
          bbox: [438, 294, 612, 344],
          area_ratio: 0.0217,
          severity: "moderate",
          severity_calibrated: false,
        },
        {
          type: "lamp_broken",
          class_recall: 0.48,
          class_reliable: true,
          score: 0.88,
          bbox: [520, 246, 640, 300],
          area_ratio: 0.0162,
          severity: "moderate",
          severity_calibrated: false,
        },
      ],
      vlm_description: null,
      warning: null,
      integrity: {
        exif_datetime: "2026-03-11 14:22:08",
        exif_gps_present: true,
        device: "Pixel 8",
        duplicate_of: null,
      },
      privacy: { ...PRIVACY_CLEAN, faces_blurred: 1 },
      // Measured through the API on a development CPU, not invented -- README
      // section 7.3 publishes the same figures. The router costs ~0 ms because
      // it reuses the gate's embedding.
      timing_ms: {
        preprocess: 106,
        gate: 70,
        router: 0,
        specialist: 113,
        vlm: null,
        total: 312,
      },
    },
  },

  described: {
    label: "Uzman model yok",
    summary:
      "Alanı belirleyebiliyoruz ama ölçecek modelimiz yok, o yüzden hiçbir bulgu üretmiyoruz.",
    caveat:
      "Bu, sistemin bugün gerçekten verdiği cevap şekli — telefon ekranı dahil hiçbir alanda uzman model bulunmuyor.",
    image: PHONE,
    response: {
      request_id: "ornek-model-yok",
      // Null: the severity prompts describe cars, and this is a phone. A band
      // here would be the estimator answering a question it was not asked.
      overall_severity: null,
      overall_severity_confidence: null,
      overall_severity_calibrated: false,
      // No specialist ran, so neither field can carry anything: a region
      // without a model behind it is a measurement nobody made.
      overall_severity_reliability: null,
      damage_region: null,
      domain: "other",
      domain_confidence: 0.89,
      domain_confidence_calibrated: false,
      specialist_model: null,
      calibrated: false,
      findings: [],
      vlm_description:
        "Koyu renkli bir akıllı telefon, ekranı yukarı bakacak şekilde düz bir yüzeyde duruyor. Ekranın üst yarısında bir noktadan dışa doğru yayılan çok sayıda çatlak görünüyor; çatlaklar cihazın kenarlarına kadar uzanıyor. Gövdede belirgin bir eğilme ya da kırık görünmüyor.",
      warning: "no_specialist_model_for_domain",
      integrity: {
        exif_datetime: null,
        exif_gps_present: false,
        device: null,
        duplicate_of: null,
      },
      privacy: PRIVACY_CLEAN,
      timing_ms: {
        preprocess: 38,
        gate: 60,
        router: 57,
        specialist: null,
        vlm: 1840,
        total: 1995,
      },
    },
  },

  unplaced: {
    label: "Yerleştirilemedi",
    summary:
      "Yönlendirici yeterince emin olamadı, o yüzden zayıf bir tahminle uzman model çalıştırmadık.",
    caveat:
      "Bu da bugün üretilebilen gerçek bir cevap şekli. Eşiğin altında kalan her fotoğraf burada durur.",
    image: AMBIGUOUS,
    response: {
      request_id: "ornek-yerlesmedi",
      overall_severity: null,
      overall_severity_confidence: null,
      overall_severity_calibrated: false,
      // No specialist ran, so neither field can carry anything: a region
      // without a model behind it is a measurement nobody made.
      overall_severity_reliability: null,
      damage_region: null,
      domain: "unknown",
      domain_confidence: 0.31,
      domain_confidence_calibrated: false,
      specialist_model: null,
      calibrated: false,
      findings: [],
      vlm_description: null,
      warning: "low_domain_confidence",
      integrity: {
        exif_datetime: null,
        exif_gps_present: false,
        device: null,
        duplicate_of: null,
      },
      privacy: PRIVACY_CLEAN,
      timing_ms: {
        preprocess: 36,
        gate: 59,
        router: 55,
        specialist: null,
        vlm: null,
        total: 150,
      },
    },
  },
};

export const DEMO_ORDER: ResultKind[] = ["measured", "described", "unplaced"];
