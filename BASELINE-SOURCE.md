# Baseline source and sanitization

This repository is the **AlphaProject delivery lab**: a pristine copy of the upstream Full Stack
FastAPI Template plus a local AgenticLab payload, used for end-to-end delivery practice.

- **Upstream project:** [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template)
- **License:** MIT. The upstream `LICENSE` is retained unchanged.
- **Template snapshot:** copied from a local clean directory (`Clean Baselines/full-stack-fastapi-template-master/`),
  which carries no `.git` metadata, so no exact upstream commit can be claimed locally.
- **No prior feature work:** this baseline deliberately contains none of the earlier PBI
  implementations (item priority, conversations). It is the upstream template as shipped.
- **Sanitization:** the snapshot's `.env` and `frontend/.env` were moved out of the repository
  without reading their contents. In their place this repo carries a documented `.env.example`
  and `frontend/.env.example`; a local `.env` with generated values is created but never committed.
  No database contents, credentials, or generated output were copied.
- **AgenticLab payload:** copied separately from the published clean payload and installed as the
  gitignored `AgenticLab/` directory, with the source revision recorded in
  `AgenticLab/SOURCE-REVISION.json` during initialization.

This file records origin and limits; it is not a claim of authorship of the upstream template.
