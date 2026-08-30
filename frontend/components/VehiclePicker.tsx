"use client";

/**
 * Model year → brand → trim, from the mirrored TSB Kasko Değer Listesi.
 *
 * **Three selects rather than one text box, because the trim decides the value.**
 * A 2020 Renault has 69 listed types separated by engine and gearbox: CAPTUR ICON
 * 1.3 TCe EDC 130 is 1,584,880 TL, CAPTUR TOUCH 1.3 TCe EDC 140 is 1,348,114 TL.
 * A quarter of a million lira between two trims of the same car in the same year,
 * and every write-off line is a ratio against that figure. Nothing in the
 * photograph distinguishes them.
 *
 * **Degrading rather than failing.** If the mirror has not been built, or the
 * vehicle is older than the fifteen model years the list covers, this falls back
 * to a plain amount field and says which of the two happened. Both are real
 * situations with different answers, and collapsing them into "something went
 * wrong" would leave the user unable to act.
 */

import { useEffect, useState } from "react";

import {
  fetchValueListMeta,
  fetchVehicleBrands,
  fetchVehicleTypes,
  fetchVehicleValue,
  fetchVehicleYears,
} from "@/lib/api";
import type { Valuation, ValueListMeta, VehicleTypeOption } from "@/lib/types";

export function VehiclePicker({
  onValue,
}: {
  /** Called with the chosen figure, or null when the selection is cleared. */
  onValue: (valuation: Valuation | null, manualAmount: string | null) => void;
}) {
  const [meta, setMeta] = useState<ValueListMeta | null>(null);
  const [years, setYears] = useState<number[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [types, setTypes] = useState<VehicleTypeOption[]>([]);

  const [year, setYear] = useState("");
  const [brand, setBrand] = useState("");
  const [typeKey, setTypeKey] = useState("");
  const [manual, setManual] = useState("");
  const [valuation, setValuation] = useState<Valuation | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const listMeta = await fetchValueListMeta();
        if (cancelled) return;
        setMeta(listMeta);
        if (listMeta.available) setYears(await fetchVehicleYears());
      } catch {
        // The picker is a convenience over a number field. If it cannot load,
        // the manual path below still works and the user is told why.
        if (!cancelled) setMeta({
          available: false,
          revision: null,
          month_label: null,
          oldest_model_year: null,
          newest_model_year: null,
          fetched_at: null,
          caveat_tr: null,
          unavailable_reason_tr:
            "Değer listesine ulaşılamadı. Aracınızın değerini elle girebilirsiniz.",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function pickYear(next: string) {
    setYear(next);
    setBrand("");
    setTypeKey("");
    setTypes([]);
    setValuation(null);
    onValue(null, null);
    setBrands(next ? await fetchVehicleBrands(Number(next)) : []);
  }

  async function pickBrand(next: string) {
    setBrand(next);
    setTypeKey("");
    setValuation(null);
    onValue(null, null);
    setTypes(next ? await fetchVehicleTypes(Number(year), next) : []);
  }

  async function pickType(next: string) {
    setTypeKey(next);
    setNote(null);
    if (!next) {
      setValuation(null);
      onValue(null, null);
      return;
    }
    // `noUncheckedIndexedAccess` is right to complain: a malformed option value
    // would hand NaN to the API and get a confusing 404 back rather than a clear
    // client-side failure.
    const parts = next.split(":").map(Number);
    if (parts.length !== 2 || parts.some(Number.isNaN)) {
      setNote("Tip seçimi okunamadı.");
      return;
    }
    const [brandCode, typeCode] = parts as [number, number];
    try {
      const found = await fetchVehicleValue(Number(year), brandCode, typeCode);
      setValuation(found);
      onValue(found, null);
    } catch (error) {
      setValuation(null);
      onValue(null, null);
      setNote(
        error instanceof Error
          ? error.message
          : "Bu tip için listede değer bulunamadı.",
      );
    }
  }

  function setManualAmount(next: string) {
    const digits = next.replace(/[^\d]/g, "");
    setManual(digits);
    setValuation(null);
    onValue(null, digits || null);
  }

  const listUnavailable = meta !== null && !meta.available;

  return (
    <div className="picker">
      {listUnavailable ? (
        <>
          <p className="picker__unavailable">{meta?.unavailable_reason_tr}</p>
          <ManualAmount value={manual} onChange={setManualAmount} />
        </>
      ) : (
        <>
          <div className="picker__row">
            <label className="claim__field">
              <span className="claim__label">Model yılı</span>
              <select
                className="claim__input"
                value={year}
                onChange={(event) => void pickYear(event.target.value)}
              >
                <option value="">Seçin</option>
                {years.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>

            <label className="claim__field">
              <span className="claim__label">Marka</span>
              <select
                className="claim__input"
                value={brand}
                disabled={!year}
                onChange={(event) => void pickBrand(event.target.value)}
              >
                <option value="">{year ? "Seçin" : "Önce model yılı"}</option>
                {brands.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="claim__field">
            <span className="claim__label">Tip</span>
            <select
              className="claim__input"
              value={typeKey}
              disabled={!brand}
              onChange={(event) => void pickType(event.target.value)}
            >
              <option value="">{brand ? `Seçin (${types.length} tip)` : "Önce marka"}</option>
              {types.map((option) => (
                <option
                  key={`${option.brand_code}:${option.type_code}`}
                  value={`${option.brand_code}:${option.type_code}`}
                >
                  {option.type_name}
                </option>
              ))}
            </select>
            <span className="claim__hint">
              Motor ve şanzıman farkı değeri değiştirir; aynı modelin iki tipi
              arasında yüz binlerce lira fark olabilir.
            </span>
          </label>

          {note && <p className="picker__note">{note}</p>}

          {valuation && (
            <div className="picker__value">
              <strong>
                {new Intl.NumberFormat("tr-TR", {
                  style: "currency",
                  currency: "TRY",
                  maximumFractionDigits: 0,
                }).format(Number(valuation.amount_try))}
              </strong>
              <span className="picker__source">{valuation.source_label}</span>
              {/* The caveat comes from the API rather than being written here, so
                  a figure cannot be rendered without the sentence that bounds it. */}
              <span className="picker__caveat">{valuation.caveat_tr}</span>
            </div>
          )}

          <details className="picker__manual">
            <summary>Aracım listede yok, değeri elle gireyim</summary>
            <p className="picker__manual-why">
              Liste {meta?.oldest_model_year ?? "—"}–{meta?.newest_model_year ?? "—"} model
              yıllarını kapsar. Daha eski araçlarda sigorta bedeli sigortacı ile
              sigortalı arasında kararlaştırılır.
            </p>
            <ManualAmount value={manual} onChange={setManualAmount} />
          </details>
        </>
      )}
    </div>
  );
}

function ManualAmount({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <label className="claim__field">
      <span className="claim__label">Aracınızın kaza tarihindeki değeri (TL)</span>
      <input
        className="claim__input"
        inputMode="numeric"
        placeholder="örn. 1584880"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
