# University research, commercialization, IP and licensing

[Hub](../README.md) · **Proposed strategy; ownership and legal decisions remain unresolved.**

## Research first

Use the platform to produce reproducible instrumentation and modest, well-defined scientific results. Potential university collaborations include electrical/computer engineering for embedded/RF systems, robotics/computer vision for geometry and estimation, metrology for calibration, and biomedical/atomic-physics laboratories for the advanced sensing tracks. No university relationship or endorsement is asserted by this document.

A useful first research package is the apparatus description, source snapshot, calibration/error model, controlled protocol, raw-to-result manifest, negative controls and negative results. A paper should claim only the measured regime. A new UI or combination of familiar sensors is not by itself a novel scientific result.

Before participant studies, coordinate institutional review and reference equipment. Before a sponsored project, document equipment ownership, publication conditions, data access, confidentiality, return obligations and background/foreground IP. Keep sponsor deliverables separate from scientific conclusions.

## Open repository versus first-party ownership

The repository [LICENSE](../../LICENSE) is MIT at the baseline. First-party means SPECTER-authored/integrated code, not automatically confidential or exclusively controlled. A public repository can contain first-party software while permitting broad reuse under its license. Calling it proprietary does not undo permissions already granted for existing releases.

Future code can have a deliberately chosen licensing/distribution model only after identifying contributor rights, dependency constraints and sponsor/university terms. Do not silently replace the existing license or assume all contributors assigned ownership. Existing history and permissions remain part of the review. Keep any future confidential invention work in a separately authorized private area; this docs handoff creates no private repository and changes no license.

## Third-party bill of materials

Record exact component/version/hash, source URL, license, distribution obligations, modifications and intended product use. Include firmware libraries, drivers, Python packages, trained models/weights, datasets, fonts/assets and generated build artifacts. Dependency code and model weights may have different terms.

[Espressif's framework page](https://www.espressif.com/en/products/sdks/esp-idf) describes its mostly Apache-2.0 source framework; [binary Wi-Fi libraries](https://github.com/espressif/esp32-wifi-lib/blob/master/README.rst) remain dependencies. The baseline optional pose path uses Ultralytics; its [license page](https://www.ultralytics.com/license) describes AGPL-3.0 and enterprise licensing options. The top-level MIT file does not resolve obligations for that dependency or its weights. Evaluate exact use and current terms with qualified review before distributing a closed product; this is an unresolved release gate, not a finding of compliance or infringement.

A hardware donation is neither a software license nor an IP assignment. A supplier lead is neither a sponsorship agreement nor permission to use its logo. Do not announce sponsors until receipt/terms and public attribution permission are evidenced.

## IP and disclosure workflow

Maintain a private contribution/disclosure ledger: contributor, dated idea/implementation, supporting artifact, funding/employment context, prior public disclosures and any signed terms. Consult the university technology-transfer office or appropriate counsel before a disclosure if patent protection matters. Do not invent an ownership answer from who paid for a board.

The [USPTO provisional-application guidance](https://www.uspto.gov/patents/basics/apply/provisional-application) discusses a US inventor-disclosure grace period and consequences for foreign protection. Do not rely on a grace-period assumption as a global strategy. Filing, public disclosure, export/dual-use questions and contract commitments require case-specific review; no filings or external disclosures are made here.

## Commercialization sequence

1. Identify a narrow, consent-based instrumentation or research workflow with a real unmet need.
2. Show repeatable performance, calibration effort and failure modes against a cheaper/simpler baseline.
3. Measure assembly cost, software/model obligations, test time, power, support burden and supply risk.
4. Run an explicitly authorized pilot with clear data, claims and responsibilities.
5. Choose hardware kits, research software/services, calibration tooling or a complete device based on evidence, not branding alone.
6. Budget manufacturing test fixtures, traceability, secure updates, privacy/security and product-specific compliance before sale.

Possible differentiators:

- **Verifiable fusion:** every fused output cites observations, parents, time,
  calibration and uncertainty.
- **Uncertainty-aware world models:** missing coverage, age and disagreement
  stay visible instead of being smoothed away.
- **Heterogeneous interoperability:** the same contracts span cameras, radar,
  CSI, wearables and future AIR nodes.
- **Affordable hardware tiers:** different coverage and uncertainty at
  different prices, with the same evidence semantics.
- **Graceful degradation:** local fail-safes and honest degraded modes rather
  than silent failure.

Through-wall life detection or quantum cardiac sensing must not be marketing
claims while they remain unproven research.

## Regulatory and export-control gates

Aerial autonomy, thermal imaging, RF sensing and encryption can be subject to
export-control, spectrum, privacy and product-safety rules that vary by
jurisdiction. Classify the exact hardware/software and intended destination
with qualified counsel before sale, transfer, demonstration or public
disclosure. Nothing in this repository is a legal determination, licence or
authorization to fly, transmit or export.

## Decisions still required

University affiliation/project status, contributor ownership, sponsor commitments, protected inventions, public/private module boundaries, intended product jurisdiction/use, commercial model and budget are not established. The immediate deliverable is a research platform with evidence; a company, grant, patent or certified product is not implied.
