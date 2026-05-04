#!/bin/bash
# Claude Code with full context observation via OTel
# 产物:~/claude-otel/run-<TS>.log + ~/claude-otel/bodies-<TS>/*.request.json

OUT_DIR="$HOME/claude-otel"
TS=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$OUT_DIR/run-$TS.log"
BODIES_DIR="$OUT_DIR/bodies-$TS"

mkdir -p "$BODIES_DIR"

export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_LOG_USER_PROMPTS=1
export OTEL_LOG_TOOL_DETAILS=1
export OTEL_LOG_TOOL_CONTENT=1
export OTEL_LOG_RAW_API_BODIES="file:$BODIES_DIR"   # ← 关键:file 模式不截断
export OTEL_LOGS_EXPORTER=console
export OTEL_METRICS_EXPORTER=none
export OTEL_TRACES_EXPORTER=none

echo ">>> Telemetry events log: $LOG_FILE"
echo ">>> Raw bodies dir:       $BODIES_DIR"
echo ">>> Starting claude... (use /exit or Ctrl-D to quit)"
echo ""

# 关键:只重定向 stderr,stdout 必须保留给 TTY
claude "$@" 2> >(tee "$LOG_FILE" >&2)

echo ""
echo ">>> Done."
echo ">>> Events log size:   $(du -h "$LOG_FILE" | cut -f1)"
echo ">>> Raw bodies count:  $(ls "$BODIES_DIR"/*.request.json 2>/dev/null | wc -l) requests"
echo ">>> Bodies dir size:   $(du -sh "$BODIES_DIR" | cut -f1)"
