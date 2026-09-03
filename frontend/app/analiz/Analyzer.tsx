"use client";

/**
 * The analyser.
 *
 * This used to live at `/`, which meant the page that had to rank for "hasar
 * analizi" was a client component whose entire body was empty until a user
 * uploaded something. Moving it here lets `/` be server-rendered prose and lets
 * this page be what it actually is: a tool.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ClaimOutcome } from "@/components/ClaimOutcome";
import { ClaimSummaryCard } from "@/components/ClaimSummaryCard";
import { ResultCard } from "@/components/ResultCard";
import { ApiError, analyze, analyzeClaim, fetchDomains } from "@/lib/api";
import { currentAccessToken } from "@/lib/supabase";
import type {
  AnalyzeResponse,
  ClaimSummary,
  DomainsResponse,
} from "@/lib/types";

/** Matches MAX_CLAIM_PHOTOS on the API, which took it from the measured
 *  distribution of real claims: 735 pairs, 111 triples, 31 quads, a thin tail
 *  to seven. Six covers all but one claim in the corpus. */
const MAX_PHOTOS = 6;

export function Analyzer() {
  // One list for one photograph and for six. A separate "claim mode" would
  // mean two rendering paths that drift, and a single photograph is just a
  // claim with one photograph in it.
  const [shots, setShots] = useState<{ result: AnalyzeResponse; url: string }[]>(
    [],
  );
  const [summary, setSummary] = useState<ClaimSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [domains, setDomains] = useState<DomainsResponse | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // dragenter/dragleave fire for every child element the pointer crosses, so a
  // boolean flag flickers as the cursor moves over the button inside the zone.
  // Counting enters and leaves is the standard fix.
  const dragDepth = useRef(0);

  useEffect(() => {
    fetchDomains().then(setDomains).catch(() => setDomains(null));
  }, []);

  // Object URLs leak until revoked, and a user analysing a dozen photos would
  // pin every one of them in memory. With a claim carrying up to six at a time
  // this matters more than it did for one.
  useEffect(() => {
    return () => {
      for (const shot of shots) URL.revokeObjectURL(shot.url);
    };
  }, [shots]);

  const handleFiles = useCallback(async (files: File[]) => {
    if (files.length === 0) return;
    const chosen = files.slice(0, MAX_PHOTOS);

    setBusy(true);
    setError(null);
    setSummary(null);
    // Revoke the previous batch here rather than only on unmount: analysing a
    // second claim without this pins the first claim's photographs for the life
    // of the page.
    setShots((previous) => {
      for (const shot of previous) URL.revokeObjectURL(shot.url);
      return [];
    });

    const urls = chosen.map((file) => URL.createObjectURL(file));

    try {
      // The token has to be attached here, not just on the history page.
      // Without it the API treats a signed-in user as anonymous: the analysis
      // is never stored, so their history stays permanently empty, and the
      // request is charged against the anonymous quota. Found by signing in and
      // looking at the history page, which is the only place the symptom shows.
      const accessToken = await currentAccessToken();

      const [only, onlyUrl] = [chosen[0]!, urls[0]!];
      if (chosen.length === 1) {
        const result = await analyze(only, {
          accessToken: accessToken ?? undefined,
        });
        setShots([{ result, url: onlyUrl }]);
      } else {
        // One request, not one per photograph -- the API counts a claim as a
        // single call against the quota, so photographing the whole car is not
        // the expensive choice.
        const claim = await analyzeClaim(chosen, {
          accessToken: accessToken ?? undefined,
        });
        setSummary(claim.summary);
        // Pair only as far as both lists reach. If the API ever returned a
        // different number of results than were uploaded, indexing blindly
        // would put each photograph beside the wrong findings -- the same
        // alignment bug that a strict zip caught in the capture-quality
        // measurement. Dropping a pair is visible; misaligning one is not.
        const paired = Math.min(claim.photos.length, urls.length);
        for (const spare of urls.slice(paired)) URL.revokeObjectURL(spare);
        setShots(
          claim.photos
            .slice(0, paired)
            .map((result, index) => ({ result, url: urls[index]! })),
        );
      }
    } catch (caught) {
      // The object URLs were created before the request; if it failed nothing
      // will render them, so they have to be released here or they leak.
      for (const url of urls) URL.revokeObjectURL(url);
      // Every documented failure already has a human sentence attached; this is
      // only the safety net for something genuinely unexpected.
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Beklenmeyen bir hata oluştu.",
      );
    } finally {
      setBusy(false);
    }
  }, []);

  return (
    <>
      {domains && <DomainList domains={domains} />}

      <section
        className={[
          "dropzone",
          dragging ? "dropzone--dragging" : "",
          busy ? "dropzone--busy" : "",
        ]
          .filter(Boolean)
          .join(" ")}
        onDragEnter={(event) => {
          event.preventDefault();
          dragDepth.current += 1;
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => {
          dragDepth.current -= 1;
          if (dragDepth.current <= 0) {
            dragDepth.current = 0;
            setDragging(false);
          }
        }}
        onDrop={(event) => {
          event.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          void handleFiles(Array.from(event.dataTransfer.files));
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/heic,.heic"
          // A claim is several photographs of one car, and a claim's photographs
          // find 30% more damage types than any single one of them (README
          // 7.12). Letting the user pick several is the whole feature.
          multiple
          className="dropzone__input"
          onChange={(event) => {
            void handleFiles(Array.from(event.target.files ?? []));
            // Without this, choosing the same file twice in a row fires no
            // change event and the second attempt silently does nothing.
            event.target.value = "";
          }}
        />
        <button
          type="button"
          className="btn btn--primary"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {busy ? "Analiz ediliyor…" : "Fotoğraf seç"}
        </button>
        <p className="dropzone__hint">
          veya sürükleyip bırakın · JPEG, PNG, WebP, HEIC · en fazla 10 MB
        </p>
        <p className="dropzone__privacy">
          Yüzler bulanıklaştırılır ve konum verisi silinir. Yüklediğiniz orijinal
          dosya hiçbir yerde saklanmaz.
        </p>
      </section>

      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}

      {/* Only for a real claim. One photograph needs no summary of itself, and
          printing "1/1 fotoğrafta bulgu var" would be noise dressed as rigour. */}
      {summary && <ClaimSummaryCard summary={summary} />}

      {shots.map((shot) => (
        <ResultCard
          key={shot.result.request_id}
          result={shot.result}
          imageUrl={shot.url}
        />
      ))}

      {/* Only after a vehicle was recognised: the thresholds are motor-insurance
          rules, and offering them beside a photograph of a cracked wall would be
          answering a question nobody asked.

          Driven by the FIRST vehicle photograph rather than by the claim, because
          the payout layer takes a single severity band and a claim's band is the
          maximum across photographs -- feeding it a band that came from a
          different photograph than the findings shown beside it would be quietly
          mixing two answers. Extending the payout layer to a claim is its own
          piece of work. */}
      {shots.find((shot) => shot.result.domain === "vehicle") && (
        <ClaimOutcome
          result={shots.find((shot) => shot.result.domain === "vehicle")!.result}
        />
      )}
    </>
  );
}

/**
 * Which domains have a model behind them, stated before the user uploads
 * anything. Setting the expectation up front is more honest than letting them
 * discover it from a result.
 */
function DomainList({ domains }: { domains: DomainsResponse }) {
  return (
    <section className="domains">
      {/* Reads as a scope statement, not as a scoreboard. Since ADR-034 the
          product measures vehicle damage and nothing else: `other` exists so a
          non-vehicle photograph can be told what it is rather than guessed at,
          and "1 / 2" would invite the reader to see a job half done. */}
      <h2 className="domains__title">
        BioVision ne ölçer
        <span className="domains__count">
          Yalnızca araç hasarı. Diğer fotoğrafları tanır, ama ölçmez.
        </span>
      </h2>
      <ul className="domains__list">
        {domains.domains.map((domain) => (
          <li
            key={domain.key}
            className={`domain ${domain.has_specialist ? "domain--specialist" : ""}`}
          >
            <span className="domain__label">{domain.label}</span>
            <span className="domain__status">
              {domain.has_specialist ? "ölçülür" : "ölçülmez — uzman modelimiz yok"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
