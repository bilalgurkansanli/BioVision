"use client";

/**
 * What the damage means for an insurance claim.
 *
 * Ordered by certainty rather than by curiosity, which inverts what a claimant
 * asks. They want to know "will my car be written off"; that is the least
 * certain thing here, so it comes last:
 *
 *   1. Premium    arithmetic over a published table, one input, exact
 *   2. Payout     the total-loss branch is exact; the repair branch is bounded
 *   3. Write-off  the line is exact to the lira; which side is unknown
 *
 * Leading with the most solid figure means every number the reader meets is
 * firmer than the one after it. Leading with the write-off would have put the
 * shakiest claim at the top and coloured everything below it.
 *
 * **This component now takes the analysis result.** It used to be mounted with
 * no props, so the photograph and the money lived on the same page and knew
 * nothing about each other — a claimant read "AĞIR hasar" in one card and a set
 * of unrelated thresholds in another, and had to join them up themselves. The
 * band is passed through to the API so the measured frequency behind it arrives
 * beside the figures it should be read against.
 *
 * **Still nothing here is a model output.** The band travels with the request,
 * but every number that comes back is a regulation or a subtraction. That is why
 * this component carries no "uncalibrated" caveat on its figures — the one
 * uncalibrated thing on screen is the band, and it arrives carrying its own.
 *
 * The inputs cannot come from the photograph and are not guessed. A vehicle
 * value has 27,906 rows behind it, separated by engine and gearbox, which no
 * vision model reads off a body panel. A muafiyet and a no-claims step are
 * printed on a policy. Asking is the honest move; defaulting would produce a
 * confident line for a car nobody described.
 */

import { useState } from "react";

import { fetchAssessment } from "@/lib/api";
import { CLAIM_BLOCKS, type ClaimBlock } from "@/lib/claimCopy";
import type { AnalyzeResponse, Assessment, Valuation } from "@/lib/types";

import { VehiclePicker } from "./VehiclePicker";

const TRY = new Intl.NumberFormat("tr-TR", {
  style: "currency",
  currency: "TRY",
  maximumFractionDigits: 0,
});

function money(value: string | null | undefined): string {
  return value == null ? "—" : TRY.format(Number(value));
}

function percent(ratio: number): string {
  const rounded = Math.round(ratio * 100);
  return `${rounded > 0 ? "+" : ""}%${rounded}`;
}

export function ClaimOutcome({ result }: { result: AnalyzeResponse }) {
  const [valuation, setValuation] = useState<Valuation | null>(null);
  const [manualValue, setManualValue] = useState<string | null>(null);
  const [step, setStep] = useState("");
  const [kademe, setKademe] = useState("");
  const [deductible, setDeductible] = useState("");
  const [salvageRetained, setSalvageRetained] = useState(false);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function compute(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setAssessment(
        await fetchAssessment({
          // A picked trim carries its own provenance; a typed figure says so.
          // The response repeats whichever it was, so a reader can weigh it.
          ...(valuation
            ? {
                model_year: valuation.model_year,
                brand_code: valuation.vehicle.brand_code,
                type_code: valuation.vehicle.type_code,
              }
            : manualValue
              ? { vehicle_value_try: manualValue }
              : {}),
          ...(result.overall_severity ? { overall_severity: result.overall_severity } : {}),
          ...(deductible.trim() ? { deductible_try: deductible } : {}),
          ...(step.trim() ? { traffic_step: Number(step) } : {}),
          ...(kademe.trim() ? { kasko_kademe: Number(kademe) } : {}),
          salvage_retained: salvageRetained,
        }),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Hesaplanamadı.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="claim">
      <header className="claim__header">
        <h2 className="claim__title">Sigorta açısından ne anlama geliyor?</h2>
        <p className="claim__lead">
          Aşağıdakilerin hepsi <strong>mevzuat ve aritmetik</strong> — model
          çıktısı değil. Her sayının yanında dayandığı madde var. Onarım bedeli
          tahmin edilmez; nedeni üçüncü bölümde yazıyor.
        </p>
      </header>

      <form className="claim__form" onSubmit={compute}>
        <VehiclePicker
          onValue={(next, manual) => {
            setValuation(next);
            setManualValue(manual);
          }}
        />

        <div className="picker__row">
          <label className="claim__field">
            <span className="claim__label">Trafik sigortası basamağınız (0–8)</span>
            <input
              className="claim__input"
              inputMode="numeric"
              placeholder="örn. 8"
              value={step}
              onChange={(event) => setStep(event.target.value.replace(/[^\d]/g, "").slice(0, 1))}
            />
            <span className="claim__hint">Poliçenizde yazar. Boş bırakabilirsiniz.</span>
          </label>

          <label className="claim__field">
            <span className="claim__label">Kasko hasarsızlık kademeniz (0–5)</span>
            <input
              className="claim__input"
              inputMode="numeric"
              placeholder="örn. 4"
              value={kademe}
              onChange={(event) => setKademe(event.target.value.replace(/[^\d]/g, "").slice(0, 1))}
            />
            <span className="claim__hint">
              Kaskoda ulusal bir merdiven yoktur; girerseniz yayımlanmış tek bir
              şirket klozu üzerinden örneklenir.
            </span>
          </label>
        </div>

        <label className="claim__field">
          <span className="claim__label">Kasko muafiyetiniz (TL)</span>
          <input
            className="claim__input"
            inputMode="numeric"
            placeholder="yoksa 0"
            value={deductible}
            onChange={(event) => setDeductible(event.target.value.replace(/[^\d]/g, ""))}
          />
          <span className="claim__hint">
            Boş bırakırsanız hiçbir senaryodan düşülmez ve rakamlar üst sınır
            olarak kalır — sıfır varsayılmaz.
          </span>
        </label>

        <label className="claim__checkbox">
          <input
            type="checkbox"
            checked={salvageRetained}
            onChange={(event) => setSalvageRetained(event.target.checked)}
          />
          <span>
            Tam hasar hâlinde hasarlı araç bende kalsın
            <span className="claim__hint">
              Varsayılan tersidir: araç sigortacıya geçer ve rayiç değerin tamamı
              ödenir. Sizde kalırsa ödeme &quot;rayiç eksi sovtaj&quot; olur.
            </span>
          </span>
        </label>

        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Hesaplanıyor…" : "Hesapla"}
        </button>
      </form>

      {error && <p className="claim__error">{error}</p>}

      {assessment && (
        <>
          <div className="claim__blocks">
            {CLAIM_BLOCKS.map((block) => (
              <Block key={block.order} block={block} assessment={assessment} />
            ))}
          </div>
          <OpenQuestions assessment={assessment} />
          <Gaps assessment={assessment} />
        </>
      )}
    </section>
  );
}

/**
 * One block: its computed figures first, then the explanation.
 *
 * Figures lead because a reader who reads nothing else should still leave with
 * the number. The prose is long and cited and sits behind a disclosure, which is
 * where length belongs — a claimant reading this has had a bad morning.
 */
function Block({ block, assessment }: { block: ClaimBlock; assessment: Assessment }) {
  return (
    <article className="claim-block">
      <header className="claim-block__head">
        <span className="claim-block__order">{block.order}</span>
        <h3 className="claim-block__title">{block.heading_tr}</h3>
      </header>

      <Figures block={block} assessment={assessment} />

      <details className="claim-block__detail">
        <summary>Kuralın tamamı ve dayanakları</summary>
        <div className="claim-block__body">
          {block.body_tr.split("\n\n").map((paragraph, index) => (
            <p key={index} dangerouslySetInnerHTML={{ __html: bold(paragraph) }} />
          ))}
        </div>

        <ul className="claim-block__citations">
          {block.citations.map((citation, index) => (
            <li key={index}>
              <span>{citation.text_tr}</span>
              <cite>{citation.source}</cite>
            </li>
          ))}
        </ul>
      </details>

      {/* What the block does NOT say, outside the disclosure: a limitation
          hidden behind a click is a limitation nobody reads. */}
      <p className="claim-block__caveat">{block.caveat_tr}</p>
    </article>
  );
}

function Figures({ block, assessment }: { block: ClaimBlock; assessment: Assessment }) {
  if (block.order === 1) return <PremiumFigures assessment={assessment} />;
  if (block.order === 2) return <PayoutFigures assessment={assessment} />;
  return <WriteOffFigures assessment={assessment} />;
}

function PremiumFigures({ assessment }: { assessment: Assessment }) {
  const { traffic_premium: traffic, kasko_premium: kasko } = assessment;
  if (!traffic && !kasko) {
    return <Missing what="Basamağınızı veya kasko kademenizi girerseniz bu bölüm hesaplanır." />;
  }
  return (
    <>
      {traffic && (
        <dl className="figures">
          <Figure
            term="Trafik basamağı"
            value={`${traffic.from_step} → ${traffic.to_step}`}
            note="bir maddi hasar ödemesi için"
          />
          <Figure
            term="Baz prime etkisi"
            value={percent(traffic.relative_increase)}
            note="Ek-2 tavanı üzerinden — fiyat değil"
          />
          <Figure
            term="Geri dönüş"
            value={`${traffic.recovery_years} hasarsız yıl`}
            note={traffic.recovery_years >= 5 ? "en üst basamak ayrı kurala tabi" : undefined}
          />
          <p className="figures__source">{traffic.source}</p>
        </dl>
      )}

      {kasko && (
        <dl className="figures figures--secondary">
          <Figure
            term="Kasko indirimi"
            value={`%${Math.round(kasko.from_discount * 100)} → %${Math.round(
              kasko.to_discount * 100,
            )}`}
            note={
              kasko.from_kademe !== null
                ? `kademe ${kasko.from_kademe} → ${kasko.to_kademe}`
                : undefined
            }
          />
          <Figure
            term="Kasko priminize etkisi"
            value={percent(kasko.relative_increase)}
            note="kendi priminiz üzerinden"
          />
          {/* Outside any disclosure. The trafik figure above is a national
              table; this one is one company's clause, and rendering the two as
              peers is exactly the mistake the API's `sample_size` exists to
              prevent. */}
          <p className="figures__warning">
            Bu satır ulusal bir kural değildir. Kaskoda yasal bir hasarsızlık
            merdiveni yoktur (Kasko GŞ C.11); yukarıdaki oran{" "}
            {kasko.sample_size === 1 ? "TEK bir şirketin" : `${kasko.sample_size} şirketin`}{" "}
            yayımlanmış klozundan{kasko.insurer ? ` (${kasko.insurer})` : ""} örneklenmiştir.
            Geçerli olan, kendi poliçenizde basılı klozdur.
          </p>
          <p className="figures__source">{kasko.source}</p>
        </dl>
      )}
    </>
  );
}

function PayoutFigures({ assessment }: { assessment: Assessment }) {
  const { payout, write_off: lines, traffic_limit: limit } = assessment;
  if (!lines) return <Missing what="Araç değerini girerseniz bu bölüm hesaplanır." />;

  return (
    <dl className="figures">
      <Figure
        term="Ödemenin tavanı"
        value={money(lines.vehicle_value_try)}
        note="riziko tarihindeki rayiç değer — poliçe tarihindeki değil"
        source={lines.value_basis_source}
      />

      {/* The product's statement about its own number, and not behind a
          disclosure. Every figure in this block is a ratio against the value
          above, and the value above came from a list the regulation does not
          name as the default reference. A reader who takes the lira figures as
          settled without this sentence has been misled by precision. */}
      <p className="figures__warning">
        {lines.value_reference_default_tr}
        <cite>{lines.value_reference_default_source}</cite>
      </p>

      {payout.map((scenario) => (
        <div className="figure figure--scenario" key={scenario.key}>
          <dt>{scenario.label_tr}</dt>
          <dd>
            <strong>
              {scenario.amount_try !== null
                ? money(scenario.amount_try)
                : `${money(scenario.lower_try ?? "0")} – ${money(scenario.upper_try)}`}
            </strong>
            <span className="figure__note">{scenario.basis_tr}</span>
            {scenario.missing_tr.length > 0 && (
              <ul className="figure__missing">
                {scenario.missing_tr.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            )}
          </dd>
        </div>
      ))}

      {limit && (
        <div className="figure figure--limit">
          <dt>Karşı tarafın trafik sigortasının tavanı</dt>
          <dd>
            <strong>{money(limit.property_per_vehicle_try)}</strong>
            <span className="figure__note">araç başına · {limit.applies_on_tr}</span>
            {limit.shortfall_try && (
              <span className="figure__gap">
                Aracınızın değeri bu tavanı {money(limit.shortfall_try)} aşıyor. Karşı
                taraf tamamen kusurlu olsa bile, zorunlu trafik sigortası bu farkı
                karşılamaz.
              </span>
            )}
            <cite>
              {limit.source} · {limit.official_gazette}
            </cite>
          </dd>
        </div>
      )}
    </dl>
  );
}

function WriteOffFigures({ assessment }: { assessment: Assessment }) {
  const lines = assessment.write_off;
  if (!lines) return <Missing what="Araç değerini girerseniz bu bölüm hesaplanır." />;

  return (
    <dl className="figures">
      {lines.lines.map((line) => (
        <Figure
          key={line.key}
          term={`${line.label_tr} çizgisi`}
          value={money(line.amount_try)}
          /* No possessive suffix on the number. Turkish vowel harmony makes it
             depend on how the digits are *pronounced* -- %60'ı but %100'ü -- and
             a template cannot know that. "kadarı" attaches to a word instead. */
          note={
            line.requires_expert_finding
              ? `değerin %${Math.round(line.ratio * 100)} kadarı + eksper raporu`
              : `değerin %${Math.round(line.ratio * 100)} kadarı`
          }
          source={line.source}
        />
      ))}

      {assessment.severity_reliability && (
        <BandFrequency reliability={assessment.severity_reliability} />
      )}

      <p className="figures__verdict">
        Bu çizgilerin hangi tarafında olduğunuzu bu sistem söylemez.{" "}
        {lines.determined_by_tr} belirler.
        <cite>{lines.determined_by_source}</cite>
      </p>
    </dl>
  );
}

/**
 * The one probability on the page, and it is a count.
 *
 * Placed in the write-off block because that is where a reader is trying to
 * guess which side of the line they are on, and it is the only honest input to
 * that guess this system has: not "your car will be written off", but "of the
 * photographs we called this band, here is what they turned out to be".
 */
function BandFrequency({
  reliability,
}: {
  reliability: NonNullable<Assessment["severity_reliability"]>;
}) {
  const LABEL: Record<string, string> = {
    minor: "hafif",
    moderate: "orta",
    severe: "ağır",
  };
  return (
    <div className="figure figure--frequency">
      <dt>Fotoğrafınıza verilen bant: {LABEL[reliability.predicted]}</dt>
      <dd>
        <strong>%{Math.round(reliability.correct_share * 100)}</strong>
        <span className="figure__note">
          Ölçüm setinde bu bandı verdiğimiz {reliability.support} fotoğrafın bu
          kadarında hasar gerçekten {LABEL[reliability.predicted]} çıktı.
        </span>
        {/* No possessive suffix on a percentage: Turkish vowel harmony makes it
            depend on the pronunciation of the digits (%51'inde but %20'sinde),
            which a template cannot know. "kadarında" attaches to a word. */}
        {reliability.worse_share > 0.05 && (
          <span className="figure__gap">
            Aynı setin %{Math.round(reliability.worse_share * 100)} kadarında ise
            hasar bundan DAHA AĞIRDI. Bu model olduğundan hafif söyleme
            eğilimindedir; bandı bir taban olarak okuyun.
          </span>
        )}
        <span className="figure__note">{reliability.evaluation_note_tr}</span>
      </dd>
    </div>
  );
}

/**
 * What the claimant could answer next, and what each answer would close.
 *
 * The most useful thing this product does when it cannot compute something.
 * "Bilinmiyor" is a dead end; "şu belgeye bakın, şu rakam netleşir" is a step.
 */
function OpenQuestions({ assessment }: { assessment: Assessment }) {
  if (assessment.open_questions.length === 0) return null;
  return (
    <section className="claim-open">
      <h3 className="claim-open__title">Bunları söylerseniz rakamlar netleşir</h3>
      <ul className="claim-open__list">
        {assessment.open_questions.map((question) => (
          <li key={question.key}>
            <strong>{question.question_tr}</strong>
            <span>{question.unlocks_tr}</span>
            {question.from_document && (
              <em>Poliçenizde yazar — fotoğraftan çıkarılamaz.</em>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** What this system does not know, published beside what it does. */
function Gaps({ assessment }: { assessment: Assessment }) {
  if (assessment.gaps.length === 0) return null;
  return (
    <details className="claim-gaps">
      <summary>Bu sistemin bilmediği {assessment.gaps.length} şey</summary>
      <ul>
        {assessment.gaps.map((gap) => (
          <li key={gap.key}>
            <strong>{gap.question_tr}</strong>
            <span>{gap.reason_tr}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function Figure({
  term,
  value,
  note,
  source,
}: {
  term: string;
  value: string;
  note?: string;
  source?: string;
}) {
  return (
    <div className="figure">
      <dt>{term}</dt>
      <dd>
        <strong>{value}</strong>
        {note && <span className="figure__note">{note}</span>}
        {source && <cite>{source}</cite>}
      </dd>
    </div>
  );
}

function Missing({ what }: { what: string }) {
  return <p className="figures__missing">{what}</p>;
}

/**
 * `**bold**` only, and nothing else.
 *
 * The copy is written by this project and lives in a committed module, not user
 * input — but escaping first costs nothing and means a future edit that pastes
 * in something from elsewhere cannot become an injection.
 */
function bold(text: string): string {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}
