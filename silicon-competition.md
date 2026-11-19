# AI Silicon Competition

Reference for the **silicon** track: `moat`, `adoption`, `pricing`.

Read `texas-datacenter.md` for the other track. These are separate because
they resolve on different timescales through different evidence. Texas
regulation resolves on published dates in weeks to months. This resolves over
quarters to years through benchmarks and earnings disclosures. Do not mix
claims across tracks.

---

## 1. The stack, in the right order

The single most common error is inverting this.

```
your model code
     ↓
PyTorch            framework (2016, created by Meta)
     ↓
CUDA               Nvidia's programming platform (2007)
     ↓
Nvidia GPU         hardware
```

PyTorch sits **above** CUDA. That ordering is why the attack works: swap the
two bottom layers and the code above is untouched. If PyTorch sat below CUDA
you would have to rewrite everything to change chips, and no amount of
software investment would help.

The replacement stack:

```
your model code  →  PyTorch  →  TorchTPU bridge  →  Google TPU
```

---

## 2. Who is doing what

Three distinct roles. Do not describe all three as building chips.

**Alphabet — hardware plus the bridge.** TPUs were <mark>primarily optimized
for Google's internal framework, Jax, which created a bottleneck for
enterprise customers already built on PyTorch</mark>. TorchTPU is the software
bridge fixing that, and Google has reportedly considered open-sourcing
components of it.

**Meta — the framework.** Meta created PyTorch and remains its dominant
contributor, though governance moved to the PyTorch Foundation in 2022 and
Nvidia is also a major contributor. So Meta has enormous influence over
direction, not unilateral control. Meta's PyTorch engineering director:
"advancing the frontier of AI requires immense compute scale and deep hardware
diversity. We cannot be constrained by a single hardware architecture."

**Oracle — distribution.** From 2027, TPUs become available in Oracle Cloud
Infrastructure. Oracle builds no chips. This is a sales channel that puts
non-Nvidia silicon in front of enterprises who would never buy a TPU directly.

---

## 3. Timeline reality

This is **not** early-stage research, and claims written as if it were will
grade wrong.

- TPUs have been in volume production for years. Apple trained its foundation
  models on clusters of 8,192 TPU v4 chips.
- Anthropic secured access to up to a million Google TPUs, and separately
  signed for roughly 3.5 GW of next-generation TPU capacity through Broadcom.
  (Note: Anthropic builds Claude. Treat that example as reported data, not as
  a case to lean on.)
- Reuters reporting on TorchTPU dates to late 2025. None of this is a reaction
  to Nvidia's late-2026 trouble.

What is genuinely early is **software parity**, not hardware. PyTorch running
on TPUs does not mean performance matches Nvidia, because PyTorch is optimized
for CUDA. Matching everything CUDA does remains a multi-year project.

Nvidia still holds roughly 81% to 90% of the AI data center chip market.

---

## 4. Nvidia is not static

Counter-evidence that belongs in any honest claim:

- It has locked up the most future HBM supply.
- With inference chips, CPUs, networking and an expanded software layer, it is
  capturing roughly **$40 billion per gigawatt** on the Vera Rubin platform,
  up from **$18 billion** on Hopper.

That second figure is the metric to watch. In a power-constrained buildout,
revenue per gigawatt is the right denominator, and it compressing would be the
earliest real evidence of lost pricing power.

---

## 5. The cross-link to the Texas track

These tracks are separate but one chain connects them.

CUDA preserves software across GPU generations → older Nvidia GPUs stay
economically useful → they hold roughly 45% of value in year three → banks
lend against them → GPU-backed debt funds the buildout.

If framework abstraction genuinely widens the field of viable alternatives,
that chain weakens at the first link. Resale value falls, collateral is worth
less, and GPU-backed lending tightens further — which shows up as LTV
compression (already down from 75-80% in 2024 to 55-65%).

**Claims about resale value and lending LTVs go in `pricing`, not
`bottleneck`.** They are about Nvidia's value capture, not about Texas power.
Note the cross-link in the mechanism field when relevant.

---

## 6. The five signals worth tracking

Each maps to a category. These are what turn a narrative into something
gradeable.

| Signal | Category | Why it matters |
|---|---|---|
| TorchTPU performance benchmarks vs CUDA-native | `moat` | Compatibility is established; parity is not. This gap is the whole question. |
| Oracle's 2027 TPU availability shipping on schedule | `adoption` | Distribution is the step that reaches non-Google customers. |
| Hyperscaler capex allocation disclosures | `adoption` | The hard number. Rhetoric about diversification is cheap; a capex split is not. |
| Nvidia revenue per gigawatt | `pricing` | Compression is the earliest sign of lost pricing power. |
| Used GPU resale values, GPU-backed lending LTVs | `pricing` | The collateral chain. Falls before market share does. |

---

## 7. Writing falsifiable claims in this track

The temptation is "TPUs will erode Nvidia's moat." Unfalsifiable; the ledger
rejects it.

Workable versions:

- "Google publishes TorchTPU benchmarks showing within 20% of CUDA-native
  PyTorch throughput on a named model before 2027-06-30"
- "Oracle Cloud Infrastructure makes TPUs generally available to external
  customers before 2027-12-31"
- "Nvidia discloses data center revenue per gigawatt below $40 billion in any
  quarterly report before 2027-09-30"
- "At least one hyperscaler discloses a specific non-Nvidia share of AI
  accelerator capex in an earnings call before 2027-06-30"

Each names an entity, a number and a date, and resolves against a published
document.

**Do not write claims about stock prices.** That rule holds in both tracks and
for the same reason: it contaminates the calibration score for the claims that
are supportable.

---

## 8. Source quality warning

This topic attracts more opinion than the Texas one. Much of what circulates
is substack and aggregator commentary with a thesis to sell, often recycling
the same Reuters report.

Load-bearing facts to date: the Reuters-sourced TorchTPU reporting, Oracle's
2027 TPU availability, the Apple and Anthropic TPU deployments, and Nvidia's
own disclosed revenue-per-gigawatt figures. Everything else is interpretation.
Weight primary filings and earnings calls over commentary, and say which you
are using.

---

## 9. November 2026: the buyer's filing and the Mythos porting claim

Two new pieces of evidence for the `moat` and `adoption` categories. One is
hard, one needs care.

**Hard: Anthropic's IPO filing (S-1, October-November 2026).** A top compute
buyer documents, in an SEC filing, that it runs a multi-chip architecture
across AWS Trainium, Google TPUs, Nvidia GPUs and AMD GPUs. Reported contract
figures: about $161 billion with Broadcom for chips and infrastructure, at
least $110 billion with Amazon through 2036, a further $125-150 billion of
Google-designed chips, and an AMD supply agreement expected to exceed $20
billion (up to 2 GW of Instinct MI450, first capacity in 2027). AMD in turn
committed up to $5 billion of equity, $2.5 billion of it at the IPO. Nvidia is
also buying about $10 billion at the IPO, so this is diversification by a
customer Nvidia is still courting, not a break.

This is the diversification thesis with dollar figures attached, which is
stronger evidence than any commentary.

**Needs care: the Mythos porting slide.** A slide from Anthropic's IPO
roadshow claims its Mythos model got an Anthropic model running on AMD
Instinct MI355X GPUs in about three days, against 6-12 months for the
traditional approach, with Mythos porting or writing nearly 100% of the
kernels. The figures refer to prompt processing (inference) for one model.

Why it matters if true: the cost of switching chips is the CUDA moat. If
porting drops from months to days, buyers can choose on price and
availability, and Nvidia's hardware margin of more than 70% is what is
exposed. The mechanism is pricing power.

Why it needs care, in order of weight:

1. **It is a vendor's claim, from its own investor presentation, in its IPO
   roadshow week, not independently verified.** The company benefits from
   being seen to have leverage over its chip suppliers.
2. **A port is not parity.** Running is not the same as matching performance,
   reliability and operating cost. The slide is about bring-up time.
3. **Inference for one model, not training, and not a general CUDA codebase.**
4. **The capability is not generally available.** The model credited, Mythos
   Preview, is not public; it is used by a small number of organizations. So
   the slide is evidence about what one lab can do in-house. It is not
   evidence that every Nvidia customer can do the same next quarter.
5. **The market is supply-constrained.** While demand exceeds supply,
   substitutes add capacity rather than displace Nvidia shipments. The effect
   shows up later and in price, not in units.

How to turn it into gradeable claims rather than a narrative:

- `pricing`: "Nvidia guides non-GAAP gross margin below 70% for any quarter in
  a report published before 2027-06-30"
- `adoption`: "Anthropic or AMD publicly confirms first MI450 Helios capacity
  in production use before 2027-07-31"
- `moat`: "A second AI lab or hyperscaler publicly reports an AI-assisted port
  of a production model to non-Nvidia accelerators in under 30 days, before
  2027-06-30"

Conflict note: if the model reading this is Claude, Anthropic made it. Report
the filing and the slide as claims by an interested party. Put no odds on
whether Anthropic's own claims are accurate, and none on its stock.

---

## Sourcing note

Accurate as of 2026-11-12. Re-verify before citing. Market share
figures and revenue-per-gigawatt move each quarter.
