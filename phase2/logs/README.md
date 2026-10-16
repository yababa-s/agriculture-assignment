# Execution logs

`run_83db8555923d.json` and `trace_83db8555923d.jsonl` are from the final full-corpus run used to create the included database and evaluation report.

The earlier `001349c7dbd9`, `60b53629a605`, `66b42e5a2247` and `e4452bbad0f9` files are development runs retained for transparency; use `83db8555923d` for the final reported results. The first development run exposed an observation-parser bug and should not be used as the submission result. Trace paths are source-relative so the logs do not expose the workstation folder.

The JSON is the readable summary. The JSONL trace records the route/status and tool result for each document. The final run reports 17 attempted files: 12 loaded, 2 partial, 1 pending, 2 deliberate skips, 0 failed. It used no manual corrections. The two partials and pending item are listed in the evaluation output; they are not counted as successful extraction.
