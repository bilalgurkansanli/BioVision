"use client";

/**
 * What the damage means for an insurance claim.
 *
 * Ordered by certainty rather than by curiosity, which inverts what a claimant
 * asks. They want to know "will my car be written off"; that is the least
 * certain thing here, so it comes last:
 *
 *   1. Premium    arithmetic over a published table, one input, exact
 *   2. Payout     the ceiling is a rule; the amount underneath it is unknowable
 *   3. Write-off  the line is exact to the lira; which side is unknown
 *
 * Leading with the most solid figure means every number the reader meets is
 * firmer than the one after it. Leading with the write-off would have put the
 * shakiest claim at the top and coloured everything below it.
 *
 * **Nothing here is a model output.** No confidence, no band, no estimate — each
 * figure is a regulation or a division. That is why this component has no
 * "uncalibrated" caveat anywhere: there is nothing to calibrate, only articles
 * to cite.
 *
 * The two inputs cannot come from the photograph and are not guessed. A vehicle
 * value has 27,906 rows behind it, separated by engine and gearbox, which no
 * vision model reads off a body panel. A no-claims step is printed on a policy.
 * Asking is the honest move; defaulting would produce a confident line for a car
 * nobody described.
 */

import { useState } from "react";

import { fetchPremiumImpact, fetchWriteOffLines } from "@/lib/api";
import { CLAIM_BLOCKS, type ClaimBlock } from "@/lib/claimCopy";
import type { PremiumImpact, Valuation, WriteOffLines } from "@/lib/types";

import { VehiclePicker } from "./VehiclePicker";

const TRY = new Intl.NumberFormat("tr-TR", {
  style: "currency",
  currency: "TRY",
  maximumFractionDigits: 0,
});

export function ClaimOutcome() {
  const [valuation, setValuation] = useState<Valuation | null>(null);
  const [manualValue, setManualValue] = useState<string | null>(null);
  const [step, setStep] = useState("");
  const [lines, setLines] = useState<WriteOffLines | null>(null);
  const [premium, setPremium] = useState<PremiumImpact | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function compute(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // Independent requests; either input may be absent and the other still
      // answers. A missing vehicle value costs the two lines, not the page.
      // A picked trim carries its own provenance; a typed figure says so. The
      // response repeats whichever it was, so a reader can weigh the number.
      const amount = valuation ? valuation.amount_try : manualValue;
      const source = valuation ? valuation.source_label : "kullanıcı girdisi";

      const [nextLines, nextPremium] = await Promise.all([
        amount ? fetchWriteOffLines(amount, source) : Promise.resolve(null),
        step.trim() ? fetchPremiumImpact(Number(step)) : Promise.resolve(null),
      ]);
      setLines(nextLines);
      setPremium(nextPremium);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Hesaplanamadı.");
    } finally {
      setBusy(false);
    }
  }

  const answered = lines !== null || premium !== null;

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

        <button className="btn btn--primary" type="submit" disabled={busy}>
          {busy ? "Hesaplanıyor…" : "Hesapla"}
        </button>
      </form>

      {error && <p className="claim__error">{error}</p>}

      {answered && (
        <div className="claim__blocks">
          {CLAIM_BLOCKS.map((block) => (
            <Block
              key={block.order}
              block={block}
              lines={lines}
              premium={premium}
            />
          ))}
        </div>
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
function Block({
  block,
  lines,
  premium,
}: {
  block: ClaimBlock;
  lines: WriteOffLines | null;
  premium: PremiumImpact | null;
}) {
  const figures = <Figures block={block} lines={lines} premium={premium} />;

  return (
    <article className="claim-block">
      <header className="claim-block__head">
        <span className="claim-block__order">{block.order}</span>
        <h3 className="claim-block__title">{block.heading_tr}</h3>
      </header>

      {figures}

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

function Figures({
  block,
  lines,
  premium,
}: {
  block: ClaimBlock;
  lines: WriteOffLines | null;
  premium: PremiumImpact | null;
}) {
  if (block.order === 1) {
    if (!premium) return <Missing what="Basamağınızı girerseniz bu bölüm hesaplanır." />;
    return (
      <dl className="figures">
        <Figure
          term="Basamak"
          value={`${premium.from_step} → ${premium.to_step}`}
          note="bir maddi hasar ödemesi için"
        />
        <Figure
          term="Baz prime etkisi"
          value={`%${Math.round(premium.relative_increase * 100)}`}
          note="Ek-2 tavanı üzerinden — fiyat değil"
        />
        <Figure
          term="Geri dönüş"
          value={`${premium.recovery_years} hasarsız yıl`}
          note={premium.recovery_years >= 5 ? "en üst basamak ayrı kurala tabi" : undefined}
        />
        <p className="figures__source">{premium.source}</p>
      </dl>
    );
  }

  if (!lines) return <Missing what="Araç değerini girerseniz bu bölüm hesaplanır." />;

  if (block.order === 2) {
    return (
      <dl className="figures">
        <Figure
          term="Ödemenin tavanı"
          value={TRY.format(Number(lines.vehicle_value_try))}
          note="riziko tarihindeki rayiç değer — poliçe tarihindeki değil"
        />
        <p className="figures__source">{lines.value_basis_source}</p>
      </dl>
    );
  }

  return (
    <dl className="figures">
      {lines.lines.map((line) => (
        <Figure
          key={line.key}
          term={`${line.label_tr} çizgisi`}
          value={TRY.format(Number(line.amount_try))}
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
      <p className="figures__verdict">
        Bu çizgilerin hangi tarafında olduğunuzu bu sistem söylemez.{" "}
        {lines.determined_by_tr} belirler.
        <cite>{lines.determined_by_source}</cite>
      </p>
    </dl>
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
