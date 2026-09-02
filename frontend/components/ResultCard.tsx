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

import { damageLabel, domainLabel, severityLabel } from "@/lib/labels";
import type { AnalyzeResponse, Finding } from "@/lib/types";
import { classify } from "@/lib/types";
import { Overlay } from "./Overlay";

export function ResultCard({
  result,
  imageUrl,
}: {
  result: AnalyzeResponse;
  imageUrl: string;
}) {
  const kind = classify(result);
  const domain = domainLabel(result.domain);

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

/**
 * The whole-photograph judgement, shown above the findings.
 *
 * The findings answer "what damage is where". They cannot answer "how bad is
 * this car" — a written-off vehicle returns one `dent` at 42%, correct about
 * that dent and useless as an assessment. This band is a separate question asked
 * of the whole frame.
 *
 * It is 64.5% accurate and `severe` is recalled at 51%, so it is labelled as a
 * guess rather than styled like a verdict. Showing it without that label would
 * repeat the mistake it exists to fix.
 */
function OverallSeverity({ result }: { result: AnalyzeResponse }) {
  if (result.overall_severity === null) return null;

  const confidence = result.overall_severity_confidence;
  return (
    <div className={`overall overall--${result.overall_severity}`}>
      <span className="overall__label">Genel değerlendirme</span>
      <strong className="overall__band">
        {severityLabel(result.overall_severity)}
      </strong>
      {confidence !== null && (
        <span className="overall__score">%{Math.round(confidence * 100)}</span>
      )}
      <span
        className="overall__caveat"
        title="Fotoğrafın tamamına bakan sıfır-atışlık bir tahmin. 319 görselde %65.5 doğru; 'ağır' sınıfını %51 yakalıyor. README §7.8"
      >
        tahmin — kalibre edilmemiş, %65.5 doğrulukta ölçüldü
      </span>
      {result.overall_severity_reliability && (
        <BandFrequency reliability={result.overall_severity_reliability} />
      )}
    </div>
  );
}

/**
 * What this band turned out to MEAN, as a frequency.
 *
 * The band alone is a word, and the word on its own is what let a written-off
 * car read as "orta hasar". This is the confusion matrix read down its column
 * rather than across its row: not "of the severe cars, how many did we catch"
 * (recall, the developer's question) but "of the cars we called this, how many
 * were" — which is the question a reader holding a band actually has.
 *
 * `worse_share` is shown separately and only when it is material, because the
 * errors are not symmetric: this estimator under-calls, so the chance that a
 * reader is being told something milder than reality is the one with a cost.
 * For `moderate` that figure is 51% — higher than the chance the band is right.
 */
function BandFrequency({
  reliability,
}: {
  reliability: NonNullable<AnalyzeResponse["overall_severity_reliability"]>;
}) {
  return (
    /* No possessive suffix on a percentage. Turkish vowel harmony makes it
       depend on how the digits are PRONOUNCED -- %85'i but %20'si and %100'ü --
       and a template cannot know that. "kadarında" attaches to a word instead.
       The same bug was fixed once on the write-off lines and came back here,
       which is why the rule is written down rather than remembered. */
    <span className="overall__frequency">
      {reliability.predicted === "none" ? (
        <>
          Bu bandı verdiğimiz {reliability.support} fotoğrafın{" "}
          <strong>%{Math.round(reliability.correct_share * 100)} kadarı</strong> gerçekten
          hasarsızdı
          {reliability.worse_share > 0.05 && (
            <>
              ; <strong>%{Math.round(reliability.worse_share * 100)} kadarında</strong> ise
              hasar vardı
            </>
          )}
          . Ölçümde bu bandı verdiğimiz hiçbir araç ağır hasarlı çıkmadı.
        </>
      ) : (
        <>
          Bu bandı verdiğimiz {reliability.support} fotoğrafın{" "}
          <strong>%{Math.round(reliability.correct_share * 100)} kadarında</strong> hasar
          gerçekten {severityLabel(reliability.predicted).toLocaleLowerCase("tr")} çıktı
          {reliability.worse_share > 0.05 && (
            <>
              ; <strong>%{Math.round(reliability.worse_share * 100)} kadarında</strong> ise
              bundan daha ağırdı
            </>
          )}
          .
        </>
      )}
    </span>
  );
}

/**
 * How much of the CAR is damaged — the question "42% of what?" was asking.
 *
 * The per-finding percentages below are fractions of the photograph, which makes
 * them a measure of where the photographer stood: the same damage padded onto
 * twice the canvas keeps a median 0.23 of its value. Dividing by the car instead
 * holds at 0.92 under the same test.
 *
 * The vehicle-relative figure is not always available — a stock COCO segmenter
 * finds a car on 86% of severe-damage photographs but only 39% of extreme
 * close-ups. When it is missing this says so and falls back to the frame figure
 * **under a different label**, because quietly relabelling one as the other is
 * how a field comes to mean two things.
 */
function DamageExtent({ result }: { result: AnalyzeResponse }) {
  const region = result.damage_region;
  if (!region) return null;

  const vehicle = region.area_ratio_vehicle;
  return (
    <div className="extent">
      <span className="extent__label">Hasarlı alan</span>
      {vehicle !== null ? (
        <>
          <strong className="extent__value">
            aracın %{(vehicle * 100).toFixed(0)} kadarı
          </strong>
          <span className="extent__note">
            Aracın kendi yüzeyine oranı. Fotoğrafın tamamına oranı %
            {(region.area_ratio_image * 100).toFixed(1)} — araç kareyi %
            {Math.round((region.vehicle_frame_share ?? 0) * 100)} dolduruyor, bu
            yüzden iki sayı farklı.
          </span>
        </>
      ) : (
        <>
          <strong className="extent__value">
            karenin %{(region.area_ratio_image * 100).toFixed(1)} kadarı
          </strong>
          <span className="extent__note">
            Aracın sınırı bu fotoğrafta bulunamadı, bu yüzden oran araca değil
            kareye göre. Uzaktan çekilen bir fotoğrafta bu sayı küçülür; hasarın
            küçüldüğü anlamına gelmez.
          </span>
        </>
      )}
      <span className="extent__note extent__note--floor">
        {region.instances} bölgenin birleşimi, %
        {Math.round(region.confidence_floor * 100)} eşiğinden. Aşağıdaki bulgu
        listesi daha yüksek bir eşik kullanır, bu yüzden alan listeden büyük
        olabilir: &quot;ne kadarı hasarlı&quot; ile &quot;hangi hasarlardan
        eminiz&quot; ayrı sorular.
      </span>
    </div>
  );
}

/**
 * Says why two numbers on this screen do not agree, when they do not.
 *
 * A user saw "göçük · %42" over the photograph and "ağır %96" below it and read
 * a contradiction. It is not one — they answer different questions — but a
 * reader has no way to know that, and two numbers that appear to fight are worse
 * than one number that is wrong: the reader stops trusting both.
 *
 * Shown only when the two actually diverge, so it stays information rather than
 * boilerplate. The condition is deliberately narrow: a `severe` band with thin
 * findings under it is the case that misleads, because the detector's silence
 * looks like evidence of nothing being wrong.
 */
function Disagreement({ result }: { result: AnalyzeResponse }) {
  if (result.overall_severity !== "severe") return null;

  const strongFindings = result.findings.filter(
    (finding) => finding.severity === "severe",
  ).length;
  if (strongFindings > 0) return null;

  return (
    <p className="disagreement">
      <strong>Bu iki sayı farklı şeyleri ölçüyor.</strong> Fotoğrafın tamamına
      bakan değerlendirme <em>ağır</em> diyor; kutulardaki yüzdeler ise modelin
      her bir bölge için ayrı ayrı güveni. Uzman model bu tür hasarların çoğunu
      kaçırıyor (aşağıdaki sınıf oranlarına bakın), bu yüzden az sayıda bulgu{" "}
      <em>az hasar</em> anlamına gelmez — bulunabilen hasarın alt sınırıdır.
    </p>
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

      <OverallSeverity result={result} />

      {/* Between the band and the findings, because it is the bridge: the band
          is a word about the whole car, the findings are boxes, and this is the
          one number that is about the car AND measured. */}
      <DamageExtent result={result} />

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
          <Disagreement result={result} />
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
  const recall = finding.class_recall;
  const weak = finding.class_reliable === false;

  return (
    <li className="finding">
      <span className={`finding__severity finding__severity--${finding.severity}`}>
        {severityLabel(finding.severity)}
      </span>
      <span className="finding__type">{damageLabel(finding.type)}</span>
      <span className="finding__score">%{Math.round(finding.score * 100)} güven</span>
      {/* Per instance, and against the photograph -- still framing-sensitive,
          deliberately left that way. The vehicle-relative figure is a property
          of the whole damaged region (see `DamageExtent`); splitting one car
          mask across overlapping instances would double-count the shared pixels
          and could sum past 100%. So the fraction that is safe per box is the
          frame one, and the label says frame. */}
      <span
        className="finding__area"
        title="Bu bulgunun maskesinin fotoğrafın tamamına oranı. Araca göre oran, tek tek bulgular için değil, hasarlı bölgenin tamamı için yukarıda verilir."
      >
        fotoğrafın %{(finding.area_ratio * 100).toFixed(1)} kadarı
      </span>
      {/* severity_calibrated is always false, and the UI says so rather than
          letting a three-band label look like a graded measurement. */}
      <span className="finding__caveat" title="Hasar türünden başlar, alan yükseltebilir">
        şiddet: kalibre edilmemiş
      </span>
      {/* The score says how sure the model is about this box. Recall says how much
          this class tends to be missed — and only the first used to be on screen,
          which let one finding on a written-off car read as light damage. */}
      {recall !== null && (
        <span
          className={`finding__recall${weak ? " finding__recall--weak" : ""}`}
          title={
            weak
              ? `Bu sınıfta ölçülen recall %${Math.round(recall * 100)}: model bu tür hasarın çoğunu kaçırıyor, bu yüzden bulunanlar alt sınırdır`
              : `Bu sınıfta ölçülen recall %${Math.round(recall * 100)}`
          }
        >
          {weak
            ? `bu sınıfta %${Math.round(recall * 100)} bulunuyor — eksik olabilir`
            : `bu sınıfta %${Math.round(recall * 100)} bulunuyor`}
        </span>
      )}
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
