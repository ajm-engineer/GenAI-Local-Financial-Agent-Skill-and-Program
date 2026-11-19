# Texas Generation and the Cost Allocation Fight

Companion to `texas-datacenter.md`. That file covers the load side (who wants
to connect). This covers the power side (who supplies it) and the political
question of who pays.

## Contents
1. Dispatchable generation and the Texas Energy Fund
2. Who is actually building
3. Behind-the-meter and WLPUN
4. Curtailment flexibility as an alternative to buildout
5. Cost allocation: the actual fight
6. The audit rubric
7. What December 10 is and is not

---

## 1. Dispatchable generation and the Texas Energy Fund

**Dispatchable** means generation an operator can turn up or down on command:
gas, coal, nuclear, hydro, batteries. Wind and solar are non-dispatchable —
output arrives when the resource does. ERCOT needs dispatchable capacity
because it must meet peak demand on command.

This is not rental or bridge power. These are permanent power plants, mostly
combined-cycle and peaker gas.

**Texas Energy Fund (TxEF)** — created by SB 2627, the Powering Texas Forward
Act, approved by voters in 2023 and administered by the PUCT. The Legislature
appropriated $5 billion for FY2025-2026 and a further $4 billion for
FY2027-2028; the 2025 session voted to fully fund the $10 billion program.
SB 2268 (89th session) adjusted financing requirements, caps and deadlines.

Programs that matter here:
- **In-ERCOT Generation Loan Program** — low-interest loans for new or
  expanded dispatchable generation inside ERCOT. Minimum 100 MW of new
  capacity.
- **Completion Bonus Grant Program** — performance-contingent grants for new
  dispatchable facilities of 100 MW or more nameplate, interconnecting to
  ERCOT before June 1, 2029. Tiered at $120,000/MW and $80,000/MW by
  interconnection date, per 16 TAC § 25.511. Paid over 10 years.

Application status is visible in the TxEF Portal on the PUCT site.

---

## 2. Who is actually building

Nine In-ERCOT loans finalized as of October 2026, state-backed buildout past
5,400 MW.

| Company | Project | Capacity | Award | Notes |
|---|---|---|---|---|
| NRG Energy | Cedar Bayou 5 | 721 MW | $562M loan, 20yr @ 3% | Finances 60% of $936M project. Completion 2028. |
| NRG Energy | T.H. Wharton | 456 MW | up to $216M | NRG had turbines already on site, a real advantage. |
| NRG Energy | Greens Bayou | 455 MW | — | Harris County, online 2028. |
| Constellation Energy Generation | — | 460 MW | $278M | |
| Rayburn Electric Cooperative | Rayburn Energy Station 2, Sherman | 570 MW | $411M | First cooperative to qualify. ERCOT North Load Zone. Online 2028. |
| LCRA | Timmerman Unit 1, Caldwell County | 188 MW | up to $22.56M grant | First Completion Bonus Grant. RICE peaker. |
| CPV | Basin Ranch, Ward County | 1,350 MW | — | Combined cycle, GE Vernova 7HA.03 turbines, Permian Basin. |
| — | Reeves County | 452 MW | — | Ninth loan, announced Oct 7 2026. |

**Track withdrawals as closely as awards.** Of the initial slate of 17
projects, six companies voluntarily withdrew, citing increasing costs,
equipment procurement constraints and lower-than-anticipated returns. Merchant
gas economics in Texas are harder than the program headline suggests, and a
withdrawal is a cleaner signal than an announcement because nobody publicises
one.

**Gas market linkage:** gas capacity in the ERCOT generation interconnection
queue grew 271% since the TxEF passed in 2023 and surpassed wind for six
consecutive months. As of February 28, 2026 the generation queue held 2,008
active requests totalling about 453,562 MW. Data centers are now a significant
driver of Texas gas demand, which feeds fuel prices, which feeds power prices,
which feeds the political fight in section 5.

About 23 GW of new generation was synchronized to ERCOT across 2024-2025, with
a further 9.9 GW expected in H1 2026.

---

## 3. Behind-the-meter and WLPUN

Behind-the-meter (BTM) means a dedicated power plant co-located with the data
center, connected directly rather than through the grid. ERCOT's pathway is
the **Withdrawal-Limited Private Use Network (WLPUN)**, sometimes called
"Bring Your Own Generation," which allows co-located generation and load to
operate behind an enforceable grid-withdrawal limit.

It became the dominant model: roughly 140 Texas projects totalling about
75,089 MW of power procurement, with nearly half of power plants under
construction in Texas serving data centers exclusively this way. The
Microsoft–Chevron Permian Basin arrangement is the headline example.

**Two corrections to the common reading:**

BTM was never a full ERCOT bypass. Generators proposed as part of a WLPUN
remain subject to generation-interconnection requirements.

And since **September 21, 2026** it is not a way around the pause either.
Abbott wrote to TCEQ broadening the moratorium to environmental permits,
stating that no other state agency shall move forward with regulatory
approvals related to data centers until the required information is acquired.
The order explicitly addressed developers building behind the meter to bypass
grid approval.

BTM still carries durable advantages — no transmission charges, no curtailment
obligation — so it is a worse *shortcut* than it looked, not a worse strategy.

---

## 4. Curtailment flexibility

Frequently misread. This is **not** a permanent reduction in consumption and
**not** a temporary measure until the grid catches up.

Tyler Norris and colleagues at Duke estimated that, setting transmission
limits aside, ERCOT could absorb roughly **10 GW of new load without any new
generation** if that load accepted curtailment totalling about **0.5% of its
annual electricity** — being shut down during the small number of hours per
year when the grid is most stressed.

It is a permanent arrangement, and it is a real competitor to the buildout
thesis: giving up half a percent of annual energy to connect years earlier is
a trade many operators would take. A campus can also shift compute to other
hours or other sites, or run its own generators during those windows.

Relatedly, ERCOT's NOGRR282 has required new large computing loads to ride
through set frequency and voltage disturbances since August 1, 2026.

---

## 5. Cost allocation: the actual fight

This is **not** a choice between funding the grid and funding more efficient
data centers. It is the question of **who pays**.

Building transmission and generation to serve a large load costs money. That
cost lands either on the data center or spread across all ratepayers.

- **June 2026** — Abbott ordered ERCOT and the PUCT to require data centers
  fully fund the costs of electric infrastructure needed to serve them, and to
  take measures reducing electricity costs to residents.
- **The driver** — Texas residential power prices rose about 25% over five
  years. Hyperscale computing in Texas now draws roughly 12 GW, about 15% of
  ERCOT load.
- **Governor-elect Hinojosa** — platform calls for a data center moratorium
  until the legislature acts, and a residential rate freeze until data centers
  "pay for themselves." Takes office January 2027.

**Stated neutrally, and this is the structurally important part:** the
outgoing Republican governor and the incoming Democratic governor have both
moved toward restriction, differing in degree and mechanism rather than
direction. Abbott's instruments are an audit and a conditional pause;
Hinojosa's stated instrument is a moratorium pending legislation. Do not model
this as a conventional partisan split, and do not assume a change of
administration reverses it.

Also note ERCOT's own stance: it is not assessing whether sufficient
electricity exists to serve these loads. It operates on the assumption that
the market will build generation to meet paying demand.

---

## 6. The audit rubric

Abbott's August 3 order requires data center developers to provide:

1. Tax breaks the project will receive
2. Power use and generation
3. Water use and cooling operations
4. Efforts to reduce impacts on local communities
5. Ownership of the facility
6. Financial information

This is effectively a scoring sheet. Projects that can document all six are
positioned to clear verification; projects that cannot are the ones at risk.
Build tracking against these six categories rather than against general
sentiment.

**On lobbying:** it is legal and substantially public. Texas Ethics Commission
lobbyist registrations, campaign finance filings, and PUCT ex parte disclosure
requirements in contested cases are all free and searchable. Track those.

**Hard limit:** obtaining material nonpublic information about a public
company and trading on it is securities fraud under SEC Rule 10b-5. Public
disclosure channels are the entire playing field. This skill does not assist
with anything outside them.

---

## 7. What December 10 is and is not

**Is:** the date ERCOT plans to file its verification report with the PUCT.

**Is not:** a list of approvals, a winners list, or the end of the pause.

Sequence after the report: the PUCT acts on it, then ERCOT can resume Batch
Zero studies, then studies complete, then approvals to energize. Each step has
its own timeline and none is published in advance.

Context on scale: BNEF estimated the audit could delay 49.8 GW of load and
cost projects up to $15 billion, and forecast only 1.2 GW of ERCOT data center
capacity additions between 2Q 2026 and 1Q 2027, reaching 17.2 GW installed by
2030. Seventeen projects had completed every other ERCOT step and are paused
anyway — execution is not sufficient when the gate is political.

Fully connecting a large data center can take 5 to 10 years. Generator
interconnection runs 18 to 30 months to commercial operation.

---

## Sourcing note

Figures accurate as of early November 2026, drawn from PUCT TxEF program
pages and press releases, ERCOT testimony to the Texas Senate, Abbott's
August 3 and September 21 letters, CBRE and BNEF analysis, and reporting on
those. Re-verify before citing. Prefer primary filings over secondary
reporting of them.
