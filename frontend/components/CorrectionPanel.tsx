"use client";

/**
 * "Bu sonuçta yanlış olan ne?" — and why the product asks.
 *
 * `docs/OPEN_QUESTIONS.md` has given the same answer since the first evaluation
 * set was built: what this project lacks is not code, it is photographs from a
 * real intake. README §7.7 says the whole published evaluation was measured on
 * close-ups, because the dataset is close-ups, so it cannot see the failure that
 * matters most; §7.7 again says the part-based comparison cannot be settled
 * without whole-vehicle photographs carrying damage annotations.
 *
 * The person on this screen is looking at the photograph and at the boxes drawn
 * on it, and knows which ones are wrong. That was being thrown away.
 *
 * **Three things this deliberately does not do.**
 *
 * 1. It does not retrain anything. These are rows in an evaluation set being
 *    assembled by hand, and a loop that closed automatically would learn from
 *    whatever somebody was willing to click.
 * 2. It does not edit the result. The analysis stays exactly as the model
 *    produced it; the correction sits beside it. Both are readable and which is
 *    which is never in doubt.
 * 3. It does not quietly keep the photograph. Retention is 7 days and the
 *    checkbox that extends it says so, in the sentence the user is agreeing to,
 *    off by default.
 */

import { useEffect, useState } from "react";

import { ApiError, fileCorrection } from "@/lib/api";
import { damageLabel } from "@/lib/labels";
import { currentAccessToken } from "@/lib/supabase";
import type { AnalyzeResponse, CorrectionKind, DamageType } from "@/lib/types";

const DAMAGE_TYPES: DamageType[] = [
  "dent",
  "glass_shatter",
  "lamp_broken",
  "missing_part",
  "punctured",
  "scratch",
  "torn",
];

type Choice =
  | { kind: "wrong_finding"; index: number }
  | { kind: "wrong_type"; index: number }
  | { kind: "missed_damage" }
  | { kind: "nothing_wrong" };

const choiceLabel = (choice: Choice, result: AnalyzeResponse): string => {
  switch (choice.kind) {
    case "wrong_finding":
      return `“${damageLabel(result.findings[choice.index]!.type)}” burada yok`;
    case "wrong_type":
      return `“${damageLabel(result.findings[choice.index]!.type)}” yanlış tür`;
    case "missed_damage":
      return "Atlanan bir hasar var";
    case "nothing_wrong":
      return "Araç hasarsız";
  }
};

function choicesFor(result: AnalyzeResponse): Choice[] {
  const perFinding = result.findings.flatMap((_, index): Choice[] => [
    { kind: "wrong_finding", index },
    { kind: "wrong_type", index },
  ]);
  const whole: Choice[] = [{ kind: "missed_damage" }];
  if (result.findings.length > 0) whole.push({ kind: "nothing_wrong" });
  return [...perFinding, ...whole];
}

export function CorrectionPanel({ result }: { result: AnalyzeResponse }) {
  const [token, setToken] = useState<string | null>(null);
  const [checkedAuth, setCheckedAuth] = useState(false);
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [expectedType, setExpectedType] = useState<DamageType | "">("");
  const [note, setNote] = useState("");
  const [retain, setRetain] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ retained: boolean; days: number } | null>(null);

  useEffect(() => {
    let live = true;
    currentAccessToken()
      .then((value) => {
        if (live) setToken(value);
      })
      .finally(() => {
        if (live) setCheckedAuth(true);
      });
    return () => {
      live = false;
    };
  }, []);

  // Nothing is shown until the token question is settled, so a signed-in user
  // never sees "sign in to report this" for a moment and then the form.
  if (!checkedAuth) return null;

  if (!token) {
    return (
      <p className="correction__signin">
        Yanlış bir bulguyu bildirmek için <strong>giriş yapmanız gerekiyor</strong>.
        Anonim analizler hiç saklanmıyor, dolayısıyla bildirimin bağlanacağı bir
        kayıt da olmuyor.
      </p>
    );
  }

  if (done) {
    return (
      <p className="correction__done" role="status">
        Kaydedildi. Bu bildirim <strong>modeli otomatik olarak değiştirmez</strong>;
        elle kurulan bir ölçüm setine ekleniyor.{" "}
        {done.retained
          ? `Fotoğraf ${done.days} güne kadar saklanacak — analizi silerseniz bildirimle birlikte silinir.`
          : `Fotoğraf her zamanki gibi ${done.days} gün sonra silinecek.`}
      </p>
    );
  }

  if (!open) {
    return (
      <button type="button" className="correction__open" onClick={() => setOpen(true)}>
        Bu sonuçta yanlış olan ne?
      </button>
    );
  }

  const needsType = choice?.kind === "wrong_type";
  const canSubmit = choice !== null && (!needsType || expectedType !== "") && !busy;

  const submit = async () => {
    if (!choice || !token) return;
    setBusy(true);
    setError(null);
    try {
      const accepted = await fileCorrection(
        result.request_id,
        {
          kind: choice.kind as CorrectionKind,
          finding_index: "index" in choice ? choice.index : null,
          expected_type: expectedType === "" ? null : expectedType,
          note: note.trim() === "" ? null : note.trim(),
          retain_image: retain,
        },
        token,
      );
      setDone({ retained: accepted.image_retained, days: accepted.retention_days });
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Bildirim gönderilemedi. Tekrar deneyin.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="correction">
      <p className="correction__intro">
        Bu ekrandaki en değerli şey sizin gördüğünüz. Yayımlanan ölçümlerin tamamı
        yakın çekim bir veri setinden geliyor (README 7.7), gerçek bir ihbardan
        gelen fotoğraf elimizde yok. Bildirdikleriniz{" "}
        <strong>elle kurulan bir ölçüm setine</strong> ekleniyor — hiçbir model
        otomatik olarak yeniden eğitilmiyor.
      </p>

      <fieldset className="correction__choices">
        <legend>Ne yanlış?</legend>
        {choicesFor(result).map((option, index) => (
          <label key={index} className="correction__choice">
            <input
              type="radio"
              name="correction-kind"
              checked={JSON.stringify(choice) === JSON.stringify(option)}
              onChange={() => {
                setChoice(option);
                if (option.kind !== "wrong_type" && option.kind !== "missed_damage") {
                  setExpectedType("");
                }
              }}
            />
            {choiceLabel(option, result)}
          </label>
        ))}
      </fieldset>

      {(choice?.kind === "wrong_type" || choice?.kind === "missed_damage") && (
        <label className="correction__field">
          Doğrusu ne?{" "}
          {choice.kind === "missed_damage" && (
            <span className="correction__optional">(bilmiyorsanız boş bırakın)</span>
          )}
          <select
            value={expectedType}
            onChange={(event) => setExpectedType(event.target.value as DamageType | "")}
          >
            <option value="">—</option>
            {DAMAGE_TYPES.map((type) => (
              <option key={type} value={type}>
                {damageLabel(type)}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className="correction__field">
        Not <span className="correction__optional">(isteğe bağlı)</span>
        <textarea
          value={note}
          maxLength={1000}
          rows={2}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Örn. arka tamponun sol köşesi kopmuş"
        />
      </label>

      {/* The consent, written out. A correction must not become a consent form
          nobody read, so the sentence names both windows and the way back out. */}
      <label className="correction__consent">
        <input
          type="checkbox"
          checked={retain}
          onChange={(event) => setRetain(event.target.checked)}
        />
        <span>
          Bu fotoğraf <strong>1 yıla kadar</strong> saklansın (normalde 7 gün).
          Bildirim ancak fotoğrafla birlikte işe yarıyor. Analizi geçmişinizden
          silerseniz fotoğraf ve bildirim birlikte silinir.
        </span>
      </label>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      <div className="correction__actions">
        <button type="button" onClick={submit} disabled={!canSubmit}>
          {busy ? "Gönderiliyor…" : "Gönder"}
        </button>
        <button type="button" className="correction__cancel" onClick={() => setOpen(false)}>
          Vazgeç
        </button>
      </div>
    </div>
  );
}
