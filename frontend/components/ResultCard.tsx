"use client";

/**
 * The result view.
 *
 * This component is where the project's central claim either lands or does not.
 * A user must be able to tell a *measurement* from a *description* without
 * reading JSON, without knowing what "specialist model" means, and without
 * having to notice a small grey caveat under a confident-looking number.
 *
 * So the three outcomes do not share a layout with a changed label. They look
 * different:
 *
 *   measured   findings, scores, an overlay — the confident presentation
 *   described  no findings at all; a plain statement that no trained model
 *              exists for this kind of photograph, and prose clearly marked as
 *              a description
 *   unplaced   neither; the router could not place the photograph and says so
 *
 * A shared layout with a swapped badge would let "no model exists for this"
 * read as a minor caveat on an otherwise authoritative answer. It is not a
 * caveat — it is the answer.
 */

import type { AnalyzeResponse, Finding, Severity } from "@/lib/types";
import { classify } from "@/lib/types";
import { Overlay } from "./Overlay";

const SEVERITY_LABEL: Record<Severity, string> = {
  minor: "hafif",
  moderate: "orta",
  severe: "ağır",
};

const DOMAIN_LABEL: Record<string, string> = {
  vehicle: "Araç",
  building: "Bina",
  phone_screen: "Telefon ekranı",
  other: "Diğer",
  unknown: "Belirlenemedi",
};

const DAMAGE_LABEL: Record<string, string> = {
  dent: "göçük",
  glass_shatter: "cam kırığı",
  lamp_broken: "far kırığı",
  missing_part: "eksik parça",
  punctured: "delik",
  scratch: "çizik",
  torn: "yırtık",
};

export function ResultCard({
  result,
  imageUrl,
}: {
  result: AnalyzeResponse;
  imageUrl: string;
}) {
  const kind = classify(result);
  const domain = DOMAIN_LABEL[result.domain] ?? result.domain;

  return (
    <article className={`result result--${kind}`}>
      <header className="result__header">
        <div>
          <p className="result__eyebrow">Alan</p>
          <h2 className="result__domain">{domain}</h2>
        </div>
        <Confidence
          value={result.domain_confidence}
          calibrated={result.domain_confidence_calibrated}
        />
      </header>

      {kind === "measured" && (
        <MeasuredBody result={result} imageUrl={imageUrl} />
      )}
      {kind === "described" && <DescribedBody result={result} imageUrl={imageUrl} />}
      {kind === "unplaced" && <UnplacedBody imageUrl={imageUrl} />}

      <Provenance result={result} />
    </article>
  );
}

/**
 * A confidence number that says what kind of number it is.
 *
 * An uncalibrated softmax output presented as "93%" is the exact claim this
 * project exists not to make, so the two states are visually distinct and the
 * uncalibrated one carries the caveat inline rather than in a tooltip.
 */
function Confidence({ value, calibrated }: { value: number; calibrated: boolean }) {
  return (
    <div className={`confidence ${calibrated ? "confidence--calibrated" : ""}`}>
      <span className="confidence__value">{Math.round(value * 100)}%</span>
      <span className="confidence__note">
        {calibrated ? "kalibre edilmiş güven" : "ham skor — kalibre edilmemiş"}
      </span>
    </div>
  );
}

function MeasuredBody({
  result,
  imageUrl,
}: {
  result: AnalyzeResponse;
  imageUrl: string;
}) {
  return (
    <>
      <Overlay imageUrl={imageUrl} findings={result.findings} />

      {result.findings.length === 0 ? (
        <p className="result__lead">
          Uzman model çalıştı ve <strong>hasar bulamadı</strong>. Bu bir ölçüm
          sonucudur, bilgi eksikliği değil.
        </p>
      ) : (
        <>
          <p className="result__lead">
            <strong>{result.findings.length} bulgu</strong> — bu alan için eğitilmiş
            bir model tarafından ölçüldü.
          </p>
          <ul className="findings">
            {result.findings.map((finding, index) => (
              <FindingRow key={index} finding={finding} />
            ))}
          </ul>
        </>
      )}

      <p className="result__model">
        Model: <code>{result.specialist_model}</code>
      </p>
    </>
  );
}

/** The response this project is built around. */
function DescribedBody({
  result,
  imageUrl,
}: {
  result: AnalyzeResponse;
  imageUrl: string;
}) {
  return (
    <>
      <div className="notice notice--no-specialist">
        <h3 className="notice__title">Bu alan için eğitilmiş bir modelimiz yok</h3>
        <p>
          Fotoğrafın hangi alana ait olduğunu belirleyebiliyoruz, ama bu alanda
          ölçüm yapacak bir uzman modelimiz bulunmuyor. Bu yüzden{" "}
          <strong>hiçbir bulgu üretmiyoruz</strong> — tahmin yürütmek yerine
          bilmediğimizi söylüyoruz.
        </p>
      </div>

      {/* No overlay: there is nothing measured to draw, and an empty overlay on
          a photograph would imply we looked and found nothing. */}
      <img className="result__photo" src={imageUrl} alt="Yüklenen fotoğraf" />

      {result.vlm_description && (
        <div className="description">
          <p className="description__label">
            Genel amaçlı bir dil modelinin serbest metin açıklaması
          </p>
          <blockquote className="description__text">{result.vlm_description}</blockquote>
          <p className="description__caveat">
            Bu bir <strong>betimleme</strong>, ölçüm değil. Doğruluğu
            değerlendirilmemiştir ve bir karar dayanağı olarak kullanılmamalıdır.
          </p>
        </div>
      )}
    </>
  );
}

function UnplacedBody({ imageUrl }: { imageUrl: string }) {
  return (
    <>
      <div className="notice notice--unplaced">
        <h3 className="notice__title">Bu fotoğrafı bir alana yerleştiremedik</h3>
        <p>
          Fotoğrafın bir nesneye ait olduğunu görüyoruz, ama hangi alana girdiğine
          yeterince emin olamadık. Zayıf bir tahminle uzman model çalıştırmak yerine
          durduk — yanlış alanda üretilmiş kendinden emin bir sonuç, hiç sonuç
          vermemekten kötüdür.
        </p>
      </div>
      <img className="result__photo" src={imageUrl} alt="Yüklenen fotoğraf" />
    </>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  const label = DAMAGE_LABEL[finding.type] ?? finding.type;

  return (
    <li className="finding">
      <span className={`finding__severity finding__severity--${finding.severity}`}>
        {SEVERITY_LABEL[finding.severity]}
      </span>
      <span className="finding__type">{label}</span>
      <span className="finding__score">%{Math.round(finding.score * 100)} güven</span>
      <span className="finding__area">
        yüzeyin %{(finding.area_ratio * 100).toFixed(1)}&apos;i
      </span>
      {/* severity_calibrated is always false, and the UI says so rather than
          letting a three-band label look like a graded measurement. */}
      <span className="finding__caveat" title="Alan oranından türetilmiş sabit eşik">
        şiddet: kalibre edilmemiş
      </span>
    </li>
  );
}

/** What was read from the file and what was redacted before storage. */
function Provenance({ result }: { result: AnalyzeResponse }) {
  const { integrity, privacy, timing_ms } = result;

  return (
    <details className="provenance">
      <summary>Bu sonuç nasıl üretildi</summary>

      <dl className="provenance__grid">
        <dt>Çekim zamanı</dt>
        <dd>{integrity.exif_datetime ?? "fotoğrafta yok"}</dd>

        <dt>Cihaz</dt>
        <dd>{integrity.device ?? "fotoğrafta yok"}</dd>

        <dt>Konum verisi</dt>
        <dd>
          {integrity.exif_gps_present ? "var" : "yok"}
          <span className="provenance__hint">
            Koordinatlar hiçbir zaman okunmaz veya saklanmaz — yalnızca varlığı.
          </span>
        </dd>

        <dt>Yüz bulanıklaştırma</dt>
        <dd>
          {privacy.face_detector === null ? (
            <span className="provenance__absent">uygulanmadı</span>
          ) : (
            `${privacy.faces_blurred} yüz (${privacy.face_detector})`
          )}
        </dd>

        <dt>Plaka bulanıklaştırma</dt>
        <dd>
          {privacy.plate_detector === null ? (
            <span className="provenance__absent">
              uygulanmadı — güvenilir bir detektör bulunamadı
            </span>
          ) : (
            `${privacy.plates_blurred} plaka (${privacy.plate_detector})`
          )}
        </dd>

        <dt>Süre</dt>
        <dd>{timing_ms.total} ms</dd>
      </dl>
    </details>
  );
}
