# Demo script — 90 seconds

Three uploads. Each one makes a different point, and the second is the one that
matters.

Do not open with the architecture. Open with a photograph.

---

## 1. A vehicle photo — the confident answer (≈25s)

> "This is a damaged car. The system routes it to the vehicle domain, and for
> vehicles we have a model trained on CarDD, so it measures."

Point at: the findings list, the boxes on the image, the model name.

Then say the part that sets up the next slide:

> "Note the confidence has a label under it saying whether it is calibrated.
> Every number this system shows you says what kind of number it is."

## 2. A cracked wall — **the point of the project** (≈40s)

> "Now a building. Same pipeline. It correctly identifies the domain — and then
> tells you it has no model for it."

Let the screen do the work. Say nothing for a beat.

> "No findings. Not an empty list because it looked and found nothing — an empty
> list because nothing measured it, and the schema physically cannot produce a
> finding without a model behind it. The description underneath is from a
> general-purpose model, and it is labelled as a description, not a measurement."

If asked *why not just estimate?*:

> "Because an estimate presented as a measurement is exactly what makes these
> systems unusable for underwriting. The moment you can't tell which numbers are
> real, none of them are."

## 3. A selfie — rejected at the door (≈15s)

> "And if it isn't a damage photo at all, it stops at the gate. 422. It doesn't
> try."

## Close (≈10s)

> "Adding a new domain is one line of YAML — no code change, and there's a test
> that enforces that. What takes real work is training the specialist, and until
> that exists the system says so. That's the whole design: it's easy to extend,
> and it doesn't pretend."

---

## What to have open in a second tab

Ready to show only if asked. Do not volunteer them.

| Question you might get | Open |
|---|---|
| "How accurate is it?" | README section 7 — the per-class table, weak rows included |
| "How do you know the confidence means anything?" | The reliability diagram and ECE |
| "What does it cost to run?" | `docs/COST.md` — $0.0028 per described image, $0 for vehicles |
| "What about privacy / KVKK?" | README section 5.1 — and say plainly that plates are **not** blurred and why |
| "Why no queue?" | README section 9 — p95 is 266 ms; the migration trigger is written down |

---

## Two things to say out loud, unprompted

**On what is not measured.** If the mAP table or the redaction miss rate is still
empty when you present, say so before anyone notices:

> "Those cells are empty because I haven't run the measurement yet. When they're
> filled it'll be from a script in the repo, not an estimate."

An empty cell you name yourself reads as rigour. The same cell, found by someone
else, reads as an omission.

**On plates.** Do not let "we blur faces and plates" pass unqualified:

> "Faces are blurred. Plates are not — I couldn't find a detector whose accuracy
> on Turkish plates I could verify, and shipping an unmeasured detector as a
> privacy guarantee would be the same mistake this whole project is arguing
> against."

That answer is more persuasive than the feature would have been.

---

## What not to do

* Do not demo on a laptop with no network and claim the numbers are from the VPS.
* Do not show the vehicle path if the CarDD checkpoint is not loaded — if there
  is no specialist, run the demo on the honest-answer path and say why. A staged
  measurement in a talk about not staging measurements is the one unrecoverable
  mistake here.
* Do not read the architecture diagram aloud. It is there for the questions
  afterwards.
