# AlphaProject evaluation notes

This lab is a **measurement subject**, not an extension host. The evaluation instrument lives in a
separate repository and is never copied into `AgenticLab/` or the application source.

## Roles

| Location | Role |
|---|---|
| `/home/peet/Projects/agenticlab-tools` (if present) or `../AgenticLab-tools/` | Instrument: session metrics and rubric scoring |
| `AlphaProject/` | Subject: FastAPI lab workspace and installed AgenticLab payload |
| `AgenticLab-v5/evaluation/` | Record: preregistrations, results, and interpretation |

## Commands

Set the subject once per shell:

```bash
export AGENTICLAB_LAB=/home/peet/Projects/AlphaProject
export PAYLOAD_ROOT=$AGENTICLAB_LAB/AgenticLab
```

Then, from the tools repository:

```bash
node session-metrics.mjs --config runs/<run>.json
node eval/eval.mjs score --rubric eval/rubrics/<id>.json --dir $AGENTICLAB_LAB --label <pbi>
node eval/eval.mjs compare --score a.json:control --score b.json:treatment
```

Never symlink or copy the tools into `AgenticLab/`; `/refresh-payload` owns that directory.
