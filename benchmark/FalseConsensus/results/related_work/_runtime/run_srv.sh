#!/usr/bin/env bash
# run_srv.sh <serve_script> <log_path>  (line-buffered)
exec stdbuf -oL -eL bash "" 2>&1 | stdbuf -oL -eL tee ""
