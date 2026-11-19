# The Forecaster Panel

How the system improves. Read this before changing anything about how
probabilities are produced, and before interpreting `panel.py --report`.

## Contents
1. The idea in one paragraph
2. Why not "run hundreds, keep the best"
3. The members
4. How weights work
5. What the guarantee does and does not promise
6. Adding a challenger (the only way to change a forecaster)
7. Free feedback: coherence and ladders
8. Reading the report
9. What this cannot do

---

## 1. The idea in one paragraph

Every claim gets a probability from several forecasters, called members, all
answering the same claim at the same time. Members are scored on the same
outcomes, weighted by accumulated error, and blended. Nothing ever picks a
winner and nothing ever rewrites a forecaster. A new idea joins as a new
member and has to earn its weight against the old one, which keeps running.

---

## 2. Why not "run hundreds, keep the best"

Selection needs data. Funds that mine thousands of strategies have millions
of observations, and still overfit. This system resolves on the order of a
hundred claims a year. Choose the best of 300 forecasters on that and you
have chosen the luckiest.

An earlier study cited in this project found the same thing from the other
side: across 888 strategies, backtest results explained under 2.5% of live
results, and more tuning made the gap worse. Tuning a single forecaster after
each miss is that mistake in miniature.

Weighting instead of selecting avoids it. A lucky member gains a little
weight and loses it again; nobody has to be right about who is good.

---

## 3. The members

**Free, logged for every claim automatically** (by `ledger.add`, so no code
path can skip them):

| Member | What it says | What it tests |
|---|---|---|
| `coin` | Always 50% | The baseline. Anything that cannot beat this is worthless. |
| `base_rate` | The share of this category's graded claims that came true | Whether knowing nothing but the category is enough |
| `primary` | The odds stated by whoever made the claim (desk or analyst) | The main forecaster |
| `primary_shrunk` | The stated odds pulled halfway to 50% | Wins if `primary` is overconfident |
| `primary_sharp` | The stated odds pushed away from 50% | Wins if `primary` is too timid |

The last two are a live calibration test. If the stated odds are
overconfident, `primary_shrunk` gains weight, the blend moves toward it, and
the correction happens without anyone editing a prompt.

**LLM members**, listed under `panel.members` in `config.yaml`, defined in
`panel.STYLES`:

| Member | How it thinks |
|---|---|
| `outside` | Base rate for the kind of situation first, then a modest adjustment |
| `inside` | The specific facts: who decides, what they have signalled |
| `skeptic` | Argues against the obvious story first, then forecasts |

They run on the `panel:` model, local by default, one call per member per
batch of new claims.

**Others**

- `analyst_raw`: when the research loop runs on a small local model, its own
  stated confidence is not used as the headline (small models say ~85% to
  everything). It used to be thrown away. Now it is logged as a member, so
  the claim about small models is tested rather than assumed.
- Anything you log by hand: `panel.py --add ID market 0.44` records a
  prediction market's price for a claim. If a market exists for a question
  and the panel cannot beat it, the right move is to use the market.

Keep the whole panel near a dozen. See section 5.

---

## 4. How weights work

All members start equal. After each graded claim, each member's weight is
multiplied by `exp(-ETA * (probability - outcome)^2)` with `ETA = 0.5`, and
weights are renormalised. A member that said 90% on something that happened
loses almost nothing; one that said 10% loses about a third of its weight.

A member that did not forecast a claim (it joined later, or its call failed)
is left exactly where it was: neither rewarded nor punished for a question it
never saw.

Weights are recomputed from the full record every time. They are never
stored, so they cannot drift out of step with the ledger.

The panel's forecast for a claim is the weighted average of the members who
forecast it. The blend **as shown at the time** is saved with the claim and
is what gets scored as "the panel", because that is the number the operator
actually saw.

`ETA` is not a tuning knob. 0.5 is the largest value for which the guarantee
below holds for squared error; smaller learns more slowly.

---

## 5. What the guarantee does and does not promise

With these weights, the blend's total squared error exceeds the best single
member's, in hindsight, by at most `2 ln(N)` for N members. That is a
classical result (prediction with expert advice, exp-concave losses).

It is why the panel is small. The cost is paid once:

| Members | Worst-case total cost | Per claim over 100 claims |
|---|---|---|
| 8 | 4.2 | 0.04 |
| 12 | 5.0 | 0.05 |
| 50 | 7.8 | 0.08 |
| 300 | 11.4 | 0.11 |

The gap between a coin flip (0.25) and a decent forecaster (0.20) is 0.05. At
this data volume, hundreds of members would cost more than the skill being
looked for.

Three honest limits:

- It is a worst case. Typical cost is far lower; in simulation the blend
  usually beats the best member outright.
- It assumes each outcome arrives before the next forecast. Here many claims
  are open at once, and delayed feedback loosens the worst case roughly in
  proportion to how many are outstanding.
- It says the blend is nearly as good as the best member. If the best member
  is bad, the blend is nearly as bad. The guarantee is about not losing to
  your own panel, not about beating the world.

There is deliberately no forgetting of old results. It would let a member
recover after the world changes, at a cost that grows with every claim and
outweighs the benefit at this scale. When the world changes, add a member.

---

## 6. Adding a challenger

This is the only sanctioned way to change how forecasts are made.

1. In `scripts/panel.py`, add a **new** key to `STYLES`, for example
   `outside_v2`, with the new prompt. Leave `outside` untouched.
2. Add the new name under `panel.members` in `config.yaml`.
3. Do nothing else. Both run on every new claim. After enough graded claims,
   `panel.py --report` shows which is better, on the same questions.

Never edit an existing style's text. Doing so puts two different forecasters
under one name and makes its record meaningless.

The same pattern covers everything: a different model (run a style under
another provider with a new name), a recalibration, a rule of thumb. If it
produces a probability, it can be a member.

When to retire one: almost never. A member with negligible weight costs
nothing in accuracy. Remove it from `config.yaml` only to save model calls,
and note that its history stays in the ledger.

---

## 7. Free feedback: coherence and ladders

Outcomes take weeks. Some errors are visible on the day:

- Scenario odds must sum to 100%. The desk rescales and flags if not.
- The same claim at two dates is a ladder, and the earlier date can never be
  more likely than the later. The desk is asked to write ladders for its main
  event, and `event_desk.normalise()` flags any that are incoherent.

Ladders also double what the ledger learns from one event.

The strongest lever on learning speed is not compute and not the panel. It is
writing more claims that resolve soon and cleanly.

---

## 8. Reading the report

```
python scripts/panel.py --report      # or the Score tab
```

- **weight**: share of the blend. Early on, all near equal.
- **Brier**: mean squared error on the claims that member forecast. 0 is
  perfect, 0.25 is a coin.
- **vs coin**: mean difference from the coin on the same claims, with a
  standard error. Negative is better. "Within noise" means the difference is
  smaller than two standard errors, so it could easily be luck.
- **Blend as shown**: how the panel's own number has scored.

Under 30 graded claims, do not rank members. The report says so.

If `coin` has the top weight, the forecasts have shown no skill. The report,
every desk brief, and the Score tab say this in plain words. Do not soften it.

---

## 9. What this cannot do

It cannot learn faster than claims resolve. For the first couple of months
the weights will barely move, and that is the method working: it is declining
to learn from noise.

It cannot create skill. It finds which of the available forecasters is least
wrong and leans on it.

And better event odds are not trading profit. The panel improves the
probabilities. What the market does with an event is a separate question,
scored separately on the desk track's `reaction` category.
