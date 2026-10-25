# Model usage report

Final full-dataset run: 518 requests. Generated 2026-10-25T15:51:43.711922+00:00.

| Provider / runtime | Model | Calls / predictions | Input LLM tokens | Output LLM tokens | API cost USD |
|---|---|---:|---:|---:|---:|
| Local Python standard library | authored-multilingual-char-ngram-naive-bayes-v1 | 518 | N/A | N/A | 0 |
| Local ONNX Runtime / RapidOCR | PP-OCR detection, classification and recognition pipeline | 0 image-pipeline calls, 11 cached images | N/A | N/A | 0 |
| Overall LLM usage | No LLM invoked | 0 | 0 | 0 | 0.00 |

The intent model is trained once in memory from 41 authored deletion examples and 30 authored other-intent examples. Character n-grams are statistical features, not billable LLM tokens. The classifier produces one intent decision per request. Its real-valued score is not calibrated probability.

OCR detection/angle/recognition neural inference is reported as a whole image-pipeline call, not as a fabricated number of LLM calls. The first development extraction used 11 cold image calls. This table describes the actual final output run, including its cache state. Cached OCR remains content-addressed; no manual verdicts are cached or bundled.

- Overall LLM tokens: 0.
- Average LLM tokens per request: 0.00.
- Estimated total paid API cost: USD 0.00.
- Estimated paid API cost per request: USD 0.000000.
- Final run elapsed time, including extraction/cache loading and all requests: 3.070 seconds.
- Final output SHA-256: `0932878aee1570be7f149af992c7579e4dd81d107a2f8fa0e267f5b82d47cc5f`.

Local CPU/GPU time, electricity, bandwidth and dependency downloads are not priced or claimed to be costless. No provider endpoint, API key or remote inference service was used by the submitted runtime. Development assistance in Codex is distinct from this inference-run usage and is recorded in `log.txt`. The local intent model and ONNX models are described directly above; there is no unreported LLM provider.
