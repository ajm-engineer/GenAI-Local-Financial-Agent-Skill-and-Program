# Audit Questions

**Registered 2026-11-12, before the first claim was logged.**

These are the only questions an audit may report as findings. Anything else
noticed while looking is a hint: it becomes a new claim or a new panel member
and has to prove itself on future data.

Why this matters: with a few hundred graded calls, slicing the data fifty
ways will turn up several patterns that are pure chance. Writing the
questions down first is what makes the answers to these five worth believing.

## The five questions

**Q1. Which kind of evidence has been worth trusting?**
Score calls by what they rested on: `unread_source`, `engineering`,
`headline`, `scheduled`, `market`. Is any of them better than a coin flip?
This is the operator's edge question.

**Q2. Which sources produce calls that hold up?**
For research-loop calls, score by the source that triggered them (PUCT,
ERCOT, SEC, PyTorch, MLPerf, AMD and Nvidia IR, and so on).

**Q3. Are the odds honest?**
Compare stated confidence with how often calls came true, for the stated odds
and for the panel's blend. Report overconfidence or underconfidence.

**Q4. Which forecaster leads, and by more than luck?**
Panel member scores against the coin, with standard errors.

**Q5. Does accuracy change with how far ahead the call was made?**
Calls made under 7 days, 7 to 30 days, and over 30 days before their date.

## Rules

1. **Hold-out.** Calls graded in the 30 days before the export are set aside.
   Answer the questions on the older calls, then check each answer on the
   held-out month. A finding that does not hold there is not a finding.
2. **Minimum size.** Under 15 graded calls in a group, report it as too few.
   Under 30, report it as a hint.
3. **Noise.** A difference smaller than two standard errors is reported as
   "no clear difference", never as a win or a loss.
4. **Voided calls** are excluded from everything.
5. **Changes go forward only.** A finding becomes a challenger: a new panel
   member, a source weighting, a config change. It runs alongside what it
   would replace and is judged on calls made after it was introduced. The
   past is never rewritten, and the box is never retrained on the data it is
   scored on.
6. **New questions** may be added to this file with the date they were added.
   They count only for data collected after that date.

## Added questions

(none yet)
