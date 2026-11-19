# Texas Data Center Pipeline

Read this before interpreting tracker output or answering any Texas data center question.

## Contents
1. Why the headline number lies
2. The pipeline stages
3. Who actually decides
4. Key dates
5. Named projects
6. What to track and what to ignore

---

## 1. Why the headline number lies

As of June 2026, ERCOT was tracking roughly **474.7 GW** of large-load interconnection requests, of which about **420.8 GW (90.2%)** were identified as data centers. ERCOT's record grid peak is around **85.5–91 GW**.

So the queue is about five times the entire grid's peak demand. That is not a forecast of buildout. It is a measure of speculative and duplicative filings: developers file at multiple sites for the same project, and filing is cheap relative to the option value of holding a queue position.

The number that matters:

| Stage | Approximate GW |
|---|---|
| Interconnection requests filed | ~474.7 |
| Conditionally in Batch Zero | ~194.3 |
| Approval to Energize | ~9.0 |
| Observed peak large-load consumption | ~3.9 |

Request to operating is roughly **0.8%** against the June snapshot.

A caution on this figure, because it is easy to quote wrong. The widely cited
**1.6%** conversion was computed against the **March 2026** queue of 238.6 GW
(then 77.5% data centers). Against the June figure of 474.7 GW the same ~3.9 GW
of operating load gives about **0.8%**. Both are correct for their snapshot.
The conversion rate *halved* in three months because the queue roughly doubled
while operating load did not move. Always state which snapshot a ratio uses.

Anyone quoting the 474 GW figure as evidence of a buildout boom is quoting an application count. Treat it as a measure of *interest*, never of capacity.

---

## 2. The pipeline stages

A Texas data center passes through these. Each is a separate gate with a separate decision-maker.

1. **Announced** — a press release. No regulatory meaning whatsoever.
2. **Site control and land** — county or municipal. Texas counties have limited zoning authority, so this gate is weaker here than in Virginia or Georgia. Cities have zoning plus extraterritorial jurisdiction.
3. **Interconnection request filed with ERCOT** — triggers the large-load process at the **75 MW** threshold under PURA § 37.0561. The PUCT may set a lower threshold.
4. **Batch Zero screening** — front-end screening with enhanced disclosure and financial-security requirements, introduced after the ad hoc process was overwhelmed.
5. **Batch study complete** — the real technical gate.
6. **Approval to Energize** — ERCOT clearance to connect.
7. **Energized and ramping** — drawing power.

Parallel tracks that can independently kill a project: water (groundwater conservation districts, TCEQ), tax abatement (Texas Comptroller, JETI program under Chapter 403 Subchapter T), and local opposition.

---

## 3. Who actually decides

This is the part worth internalising, because "who holds the decision" determines what evidence predicts the outcome.

**ERCOT** — the grid operator, not a regulator. Runs the queue, performs the studies, grants Approval to Energize. Currently the binding constraint. President and CEO: Pablo Vegas.

**PUCT (Public Utility Commission of Texas)** — three commissioners, appointed by the Governor. Writes the rules ERCOT applies. Adopted large-load interconnection standards as **16 TAC § 25.194** in September 2026 under **Project 58481**. Chairman: Thomas Gleeson.

Note the structure: the Governor appoints the PUCT, the PUCT writes the rules, ERCOT applies them. Gubernatorial preference transmits to the queue with a lag, through appointments and directives rather than legislation.

**The Governor** — on **August 3, 2026**, Governor Abbott directed the PUCT and ERCOT to audit all data center projects advancing through the interconnection process before any additional ones are approved, warning that projects failing to disclose ownership, financial, water and community-impact information could be denied grid access. ERCOT responded by **pausing energization** of new large-load data centers and crypto mining facilities pending the audit and a community impact review.

**Governor-elect Gina Hinojosa** — won the November 2026 election. Her platform calls for a data center moratorium until the legislature acts, and a residential rate freeze until data centers "pay for themselves." Reuters reported the industry has been plunged into uncertainty by this. Takes office January 2027.

**The Texas Legislature** — meets in regular session only in odd-numbered years. Passed **SB 6 in 2025**, which gave the PUCT authority over large-load interconnection rules. Next regular session convenes **January 2027**, which is the first opportunity for statutory change.

**Counties and municipalities** — weaker than in most states. Texas has no statewide zoning and county zoning authority is limited. Do not model Texas local control on Loudoun County, Virginia.

---

## 4. Key dates

| Date | Event | Why it matters |
|---|---|---|
| **Dec 10, 2026** | ERCOT audit and community impact review reports due to the PUCT | Hard deadline. Determines whether the energization pause lifts. |
| **Dec 31, 2026** | PUCT final SB 6 large-load rule deadline | Sets curtailment obligations for 75 MW+ loads. |
| **January 2027** | Hinojosa inauguration | New appointments begin flowing to the PUCT over subsequent terms. |
| **January 2027** | Texas Legislature convenes | First window for statutory moratorium or cost-allocation change. |

These are calendar facts, known in advance. Surface them. Do not attach a directional forecast to them.

---

## 5. Named projects

| Project | Location | Capacity | Status |
|---|---|---|---|
| Stargate / Abilene (Lancium Clean Campus) | Abilene | 1,200 MW | Operational. Crossed 1 GW facility power July 2026. Two buildings live since Sept 2025, six ramping. |
| Vantage "Frontier" Campus | Albany / Abilene | 1,400 MW | Under construction, first building H2 2026. |
| Fermi America "Project Matador" | Amarillo | 11,000 MW | Delayed. Construction paused early 2026. |

Project Matador is the cautionary case: an 11 GW announcement that became a construction pause. It is why announcements are not tracked as capacity.

Texas is the second largest US data center market behind Virginia, and had been widely expected to take the top position before the pause.

---

## 6. What to track, what to ignore

**Track:**
- Stage transitions for named projects, especially Batch Zero study completions and Approval to Energize grants
- PUCT docket filings under Project 58481 and successor dockets
- ERCOT board and Technical Advisory Committee agendas
- Texas Legislature bill filings mentioning data centers, large loads, or ERCOT cost allocation
- Groundwater conservation district permit decisions in project counties
- Comptroller JETI agreement approvals and denials

**Ignore:**
- Total queue GW as a buildout measure
- Press-release capacity announcements with no filed interconnection request
- Any figure that does not name a pipeline stage

**The analytical frame:** a project's probability of completion is a product of independent gates, not a single approval. A project with land, financing and a signed offtake can still die on water rights or a curtailment obligation it cannot accept. Track gates separately.

---

## Sourcing note

Figures here were accurate as of early November 2026 and come from ERCOT testimony to the Texas Senate, Abbott's August 3 letter, PUCT filings, and reporting on those. The queue moves. Re-verify before citing a number, and prefer ERCOT's own filings over secondary reporting of them.
