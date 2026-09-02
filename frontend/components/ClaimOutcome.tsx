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
import { CLAIM_BLOCKS, type ClaimBlock, GLOSSARY } from "@/lib/claimCopy";
import type {
  AnalyzeResponse,
  Assessment,
  Consequence,
  Valuation,
} from "@/lib/types";

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
          Aşağıdaki rakamların hiçbirini yapay zekâ tahmin etmiyor. Hepsi{" "}
          <strong>yasal kurallar ve dört işlem</strong> — her birinin yanında
          hangi maddeden geldiği yazıyor. Onarımın kaça mal olacağı ise tahmin
          edilmiyor; bunu fotoğraftan bilmenin güvenilir bir yolu yok.
        </p>
      </header>

      <form className="claim__form" onSubmit={compute}>
        <VehiclePicker
          onValue={(next, manual) => {
            setValuation(next);
            setManualValue(manual);
          }}
        />

        {/* One notice above the three policy fields rather than a line under
            each. All three are printed on the same document, so a reader who
            does not have it to hand is stuck on all three at once. */}
        <p className="claim__lookup">
          Aşağıdaki üç bilgi poliçenizde yazar. Elinizde yoksa{" "}
          <a href="https://biopolicy.bilalgurkansanli.com" target="_blank" rel="noreferrer">
            BioPolicy
          </a>{" "}
          üzerinden bakabilirsiniz. Bilmiyorsanız boş bırakın — o bölümler
          hesaplanmaz, geri kalanı yine gelir.
        </p>

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
            <span className="claim__hint">
              Kaç yıldır hasarsız gittiğinizi gösteren sıra numarası. 8 en iyisi.
            </span>
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
              Kaskonun kendi hasarsızlık sırası. Trafikten ayrıdır ve her şirkette
              farklıdır, o yüzden buradaki sonuç kesin değil, örnektir.
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
            Her hasarda sizin cebinizden çıkan sabit tutar. Poliçenizde yoksa 0
            yazın. Boş bırakırsanız rakamlardan düşülmez.
          </span>
        </label>

        <label className="claim__checkbox">
          <input
            type="checkbox"
            checked={salvageRetained}
            onChange={(event) => setSalvageRetained(event.target.checked)}
          />
          <span>
            Araç pert çıkarsa hurdası bende kalsın
            <span className="claim__hint">
              Normalde araç sigortaya geçer ve değerinin tamamı konuşulur. Hurdayı
              siz alırsanız, hurdanın değeri bu tutardan düşülür.
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
          <PlainSummary assessment={assessment} />
          <Glossary />
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
 * The whole answer in five plain sentences, before any of the rigour.
 *
 * The blocks below are cited to the article and were adversarially reviewed, and
 * a reader who knows what "rayiç", "sovtaj" and "muafiyet" mean gets a great
 * deal from them. Someone reading this an hour after a crash knows none of those
 * words, and the page as it stood gave them a wall of them.
 *
 * So this goes first and uses none of that vocabulary. Nothing is softened — the
 * same figures, the same refusals — but a person who reads only this box should
 * still leave knowing what happens to their car, roughly what money is involved,
 * and what nobody can tell them yet.
 *
 * The last line is the one to be careful with. Ek-2 is a ceiling, so "artabilir"
 * is not hedging, it is the accurate verb; "artacak" would be a price claim and
 * `test_no_binding_language.py` fails the build on it.
 */
function PlainSummary({ assessment }: { assessment: Assessment }) {
  const { write_off: lines, payout, traffic_premium: traffic, kasko_premium: kasko } = assessment;
  const heavy = lines?.lines.find((line) => line.key === "agir_hasar");
  const totalLoss = payout.find((branch) => branch.key === "tam_hasar");

  // `wide` marks a row whose value is a sentence rather than one number:
  // set at figure size it out-shouted the money above it and wrapped its own
  // label.
  const rows: { label: string; value: string; note: string; wide?: boolean }[] = [];

  if (lines) {
    rows.push({
      label: "Aracınızın değeri",
      value: money(lines.vehicle_value_try),
      note: "Kaza günündeki piyasa değeri. Listeden okundu, aracınız tek tek değerlenmedi.",
    });
  }
  if (heavy) {
    rows.push({
      label: "Onarım bunu aşarsa araç «ağır hasarlı» olur",
      value: money(heavy.amount_try),
      note: "Ruhsatına işleyen kalıcı bir kayıt. Onarımın kaça mal olacağını eksper söyler, bu sistem değil.",
    });
  }
  if (totalLoss) {
    rows.push({
      label: "Araç pert çıkarsa en fazla bu kadarı konuşulur",
      value:
        totalLoss.amount_try !== null
          ? money(totalLoss.amount_try)
          : money(totalLoss.upper_try),
      note: "Bir tavan, söz değil. Kesin rakam poliçenize ve eksper raporuna bağlı.",
    });
  }
  if (traffic || kasko) {
    const parts = [
      traffic ? `trafik sigortanız en fazla ${percent(traffic.relative_increase)}` : null,
      kasko ? `kaskonuz en fazla ${percent(kasko.relative_increase)}` : null,
    ].filter(Boolean);
    rows.push({
      label: "Sigorta bir ödeme yaparsa, gelecek yıl",
      value: parts.join(" · "),
      wide: true,
      note: "Üst sınır. Gerçek rakamı ancak yenileme teklifinde görürsünüz.",
    });
  }

  if (rows.length === 0) return null;

  return (
    <section className="plain">
      <h3 className="plain__title">Kısaca</h3>
      <dl className="plain__rows">
        {rows.map((row) => (
          <div
            className={`plain__row${row.wide ? " plain__row--wide" : ""}`}
            key={row.label}
          >
            <dt>{row.label}</dt>
            <dd>
              <strong>{row.value}</strong>
              <span>{row.note}</span>
            </dd>
          </div>
        ))}
      </dl>
      <p className="plain__unknown">
        <strong>Bu sistemin söyleyemediği tek şey, en çok merak edilen şey:</strong>{" "}
        onarımın kaça mal olacağı. Onu bir fotoğraftan çıkarmanın ölçülmüş bir
        yolu yok, o yüzden tahmin edilmiyor. Aracınızın hangi tarafta kaldığına
        sigorta eksperi karar verir.
      </p>
    </section>
  );
}

/** The six words the page cannot avoid, said plainly. Closed by default. */
function Glossary() {
  return (
    <details className="glossary">
      <summary>Buradaki kelimeler ne demek?</summary>
      <dl>
        {GLOSSARY.map((entry) => (
          <div key={entry.term}>
            <dt>{entry.term}</dt>
            <dd>{entry.plain_tr}</dd>
          </div>
        ))}
      </dl>
    </details>
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

      {/* What the block does NOT say, outside its own disclosure: a limitation
          hidden behind a click is a limitation nobody reads. The plain sentence
          leads; the exhaustive version is one click further, which keeps both
          readers -- the one who needs the warning and the one who needs all of
          it -- without making the first read the second. */}
      <div className="claim-block__caveat">
        <p>{block.caveat_lead_tr}</p>
        <details>
          <summary>Bu bölümün söylemediklerinin tamamı</summary>
          <p>{block.caveat_tr}</p>
        </details>
      </div>
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
            term="Trafik sigortası basamağınız"
            value={`${traffic.from_step} → ${traffic.to_step}`}
            note="bir maddi hasar ödemesi yapılırsa"
          />
          <Figure
            term="Trafik priminize etkisi"
            value={percent(traffic.relative_increase)}
            note="üst sınır, fiyat değil — şirket daha azını isteyebilir"
          />
          <Figure
            term="Eski basamağınıza dönmek"
            value={`${traffic.recovery_years} hasarsız yıl`}
            note={traffic.recovery_years >= 5 ? "en üst basamak ayrı kurala tabi" : undefined}
          />
          <p className="figures__source">{traffic.source}</p>
        </dl>
      )}

      {kasko && (
        <dl className="figures figures--secondary">
          <Figure
            term="Kasko hasarsızlık indiriminiz"
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
            note="şu anki priminizin üzerine"
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
        term="Aracınızın değeri"
        value={money(lines.vehicle_value_try)}
        note="kaza günündeki piyasa değeri — poliçeyi yaptırdığınız gündeki değil"
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
          <dt>Karşı taraf kusurluysa, onun sigortasından en fazla</dt>
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
        <div className="figure figure--line" key={line.key}>
          <dt>Onarım bunu aşarsa: {line.label_tr}</dt>
          <dd>
            <strong>{money(line.amount_try)}</strong>
            {/* No possessive suffix on the number. Turkish vowel harmony makes it
                depend on how the digits are PRONOUNCED -- %60'ı but %100'ü -- and
                a template cannot know that. "kadarı" attaches to a word. */}
            <span className="figure__note">
              {line.requires_expert_finding
                ? `değerin %${Math.round(line.ratio * 100)} kadarı + eksper raporu`
                : `değerin %${Math.round(line.ratio * 100)} kadarı`}
            </span>
            <cite>{line.source}</cite>

            {/* Split by whether it can be undone, not by importance in general.
                Crossing 60% produces six consequences and five are procedural;
                listing all six under the figure buried the one that matters —
                the record ends the değer kaybı claim outright. Money is
                recoverable, that is not, so the permanent ones stay in front of
                the reader and the rest go behind a click. */}
            <Consequences items={line.consequences} />
          </dd>
        </div>
      ))}

      {lines.below_threshold_tr.length > 0 && (
        <div className="figure figure--below">
          <dt>Her iki sınırın da altında kalırsanız — bunlar sizin lehinize</dt>
          <dd>
            <ul className="figure__consequences">
              {lines.below_threshold_tr.map((item) => (
                <li key={item.key}>
                  <span>{item.text_tr}</span>
                  <cite>{item.source}</cite>
                </li>
              ))}
            </ul>
          </dd>
        </div>
      )}

      {assessment.procedure.length > 0 && (
        <div className="figure figure--below">
          {/* Neither side of the line: how the claim runs either way. These used
              to hang off the thresholds, which implied they followed from
              crossing one. */}
          <dt>Hangi tarafta olursanız olun</dt>
          <dd>
            <ul className="figure__consequences">
              {assessment.procedure.map((item) => (
                <li key={item.key}>
                  <span>{item.text_tr}</span>
                  <cite>{item.source}</cite>
                </li>
              ))}
            </ul>
          </dd>
        </div>
      )}

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
 * What crossing a line does, split by whether the reader can afford to miss it.
 *
 * In front of the reader: what happens to the vehicle's registration (the direct
 * meaning of the line), and anything that cannot be undone. Behind a click: the
 * procedural entries — which document blocks payment, what a lien does.
 *
 * The split exists because attaching all six to the 60% line buried the only one
 * that is permanent: the record ends the değer kaybı claim outright. Money is
 * recoverable and that is not, so the two cannot compete for the same space.
 */
function Consequences({ items }: { items: Consequence[] }) {
  if (items.length === 0) return null;
  const upfront = items.filter((item) => item.irreversible || item.line_specific);
  const rest = items.filter((item) => !item.irreversible && !item.line_specific);

  return (
    <>
      {upfront.length > 0 && (
        <ul className="figure__consequences">
          {upfront.map((item) => (
            <li key={item.key} className={item.irreversible ? "is-irreversible" : undefined}>
              <span>
                {item.irreversible && <em>Geri alınamaz. </em>}
                {item.text_tr}
              </span>
              <cite>{item.source}</cite>
            </li>
          ))}
        </ul>
      )}

      {rest.length > 0 && (
        <details className="figure__procedure">
          <summary>Bu çizginin ötesindeki işlem sırası ({rest.length})</summary>
          <ul className="figure__consequences">
            {rest.map((item) => (
              <li key={item.key}>
                <span>{item.text_tr}</span>
                <cite>{item.source}</cite>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
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
      <dt>Fotoğrafa bakıp «{LABEL[reliability.predicted]}» dedik. Ne kadar güvenilir?</dt>
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
