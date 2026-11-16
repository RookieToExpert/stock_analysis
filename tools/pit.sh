#!/bin/bash
# Baostock 时点数据下载的启动、查看、停止。不经过 Claude，不花额度。
#
#   tools/pit.sh status   看进度，并判断：在跑 / 网络抖动 / 被拉黑 / 额度用完 / 到点 / 被杀
#   tools/pit.sh start    启动（后台，交给 systemd）。先探测，探测不过不下载
#   tools/pit.sh stop     停掉
#   tools/pit.sh log      跟着看日志
#   tools/pit.sh run      前台跑一轮，给 systemd 定时器用（每天 07:00）
#
# 规则不在这里，在 model/pit_fetch.py 和 model/pit_guard.py：
# 单进程、请求间隔 1 秒、每天 4 万次、收到 10001011 即停、不走代理。
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1
STATE=data/pit_state
LIBS=(--lib data/pylib/stub --lib data/pylib/pylib2)
UNIT=pit-fetch.service
export TZ=Asia/Shanghai
NOPROXY=(env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u all_proxy -u ALL_PROXY)

now() { date '+%F %T %z'; }
latest_log() { ls -t data/logs/pit_trial_*.log 2>/dev/null | head -1; }
# 下载进程运行时一直握着这把锁；拿得到说明没人在跑
running() { [ -e $STATE/lock ] && ! flock -n $STATE/lock true; }
pid() { pgrep -f '^python3 -u model/pit_fetch.py' | head -1; }

run() {
  mkdir -p data/logs
  LOG=data/logs/pit_trial_$(date +%F).log
  trap 'true' TERM   # 被 stop 时也要把 end 行写完
  if running; then echo "skip $(now) 已有下载进程在跑" >> "$LOG"; exit 0; fi
  if [ -e $STATE/blocked.json ]; then echo "skip $(now) 黑名单标记存在，不发请求" >> "$LOG"; exit 0; fi
  END=$(( $(date -d "$(date +%F) 23:55:00" +%s) - $(date +%s) ))
  if [ "$END" -le 60 ]; then echo "skip $(now) 已过 23:55" >> "$LOG"; exit 0; fi
  echo "probe $(now)" >> "$LOG"
  "${NOPROXY[@]}" python3 -u model/pit_fetch.py "${LIBS[@]}" --probe >> "$LOG" 2>&1
  rc=$?; echo "probe exit=$rc" >> "$LOG"
  [ $rc -ne 0 ] && exit 0
  echo "start $(now) timeout ${END}s" >> "$LOG"
  "${NOPROXY[@]}" timeout "$END" python3 -u model/pit_fetch.py "${LIBS[@]}" >> "$LOG" 2>&1
  rc=$?; echo "end $(now) exit=$rc" >> "$LOG"
  exit 0
}

status() {
  LOG=$(latest_log)
  python3 - "$ROOT" <<'EOF'
import json, sys, datetime
from pathlib import Path
root = Path(sys.argv[1])
cn = datetime.timezone(datetime.timedelta(hours=8))
today = datetime.datetime.now(cn).date().isoformat()
try:
    used = json.loads((root / "data/pit_state/state.json").read_text())["days"].get(today, 0)
except Exception as e:
    used = f"读不出（{e!r}）"
try:
    u = json.loads((root / "data/pit/universe.json").read_text())
    total = len({c for xs in u.values() for c in xs})
except Exception:
    total = "?"
done = len([f for f in (root / "data/pit").glob("*.json") if f.name != "universe.json"])
print(f"进度     已下 {done} / {total} 只")
print(f"今日额度 已用 {used} / 40000")
EOF
  [ -z "$LOG" ] && { echo "判断     还没跑过，没有日志"; return; }
  # 只看最后一轮：从最后一个 probe/start/resume 行往后
  SEG=$(awk '/^(probe|start|resume) [0-9]/{buf=""} {buf=buf $0 "\n"} END{printf "%s", buf}' "$LOG")
  # probe 和 start 是一轮，把紧挨着的 probe 段也带上
  LAST=$(printf '%s' "$SEG" | tail -3)
  echo "日志     $LOG"
  if running; then
    P=$(pid); AGE=$(( $(date +%s) - $(stat -c %Y $STATE/state.json) ))
    echo "进程     在跑 pid=${P:-?} 已运行 $(ps -o etime= -p "${P:-0}" 2>/dev/null | tr -d ' ')，上次发请求 ${AGE} 秒前"
    if printf '%s' "$LAST" | grep -q '^wait [0-9]'; then
      echo "判断     网络抖动：断线后正在等待重新登录（5/10/20/40 分钟递增），不用管"
    elif [ "$AGE" -gt 420 ]; then
      echo "判断     疑似卡死：超过 7 分钟没发请求（正常最长 5 分钟等待+1 分钟超时）。tools/pit.sh stop 再 start"
    else
      echo "判断     正常"
    fi
  else
    echo "进程     没在跑"
    if [ -e $STATE/blocked.json ] || printf '%s' "$SEG" | grep -q 10001011; then
      echo "判断     被拉黑（10001011）。不要重启。等一段时间、你确认可以恢复后："
      echo "         python3 model/pit_fetch.py --clear-block   然后 tools/pit.sh start"
      [ -e $STATE/blocked.json ] && echo "         标记：$(cat $STATE/blocked.json)"
    elif printf '%s' "$SEG" | grep -q -E '今日剩余|今日额度'; then
      echo "判断     今日额度用完，正常结束。明早 07:00 定时器自动接着跑"
    elif printf '%s' "$SEG" | grep -q '^done'; then
      echo "判断     这一轮要下的全部下完"
    elif printf '%s' "$SEG" | grep -q 'exit=124'; then
      echo "判断     到 23:55 截止，正常结束。明早 07:00 自动接着跑"
    elif printf '%s' "$SEG" | grep -q -E '重新登录失败|再次出现网络错误|连不上服务器|10002007|probe exit=[1-9]'; then
      echo "判断     网络问题停的（断线后重登也失败）。可以重启：tools/pit.sh start"
      echo "         start 会先探测，网络还没好它自己会停，不会硬下"
    elif printf '%s' "$SEG" | grep -q '连续失败 10 只'; then
      echo "判断     连续 10 只失败。看下面日志里 fail 行的错误码再决定，别直接重启"
    elif printf '%s' "$SEG" | grep -q '已有下载进程'; then
      echo "判断     上次启动时已有进程在跑，被挡下了（禁止并发）"
    elif printf '%s' "$SEG" | grep -q -E '^end .* exit=(15|137|143)'; then
      echo "判断     被人或系统杀掉的。可以重启：tools/pit.sh start"
    elif ! printf '%s' "$SEG" | grep -q -E '^(end|probe exit)'; then
      echo "判断     没有结束记录：进程被强杀或机器重启过。可以重启：tools/pit.sh start"
    else
      echo "判断     认不出，看下面日志"
    fi
  fi
  echo "---- 日志最后 8 行"
  tail -8 "$LOG" | cut -c1-200
}

case "${1:-status}" in
  run) run ;;
  status) status ;;
  start)
    running && { echo "已有下载进程在跑，不重复启动"; exit 1; }
    [ -e $STATE/blocked.json ] && { echo "黑名单标记存在，不启动。见 tools/pit.sh status"; exit 1; }
    systemctl --user start --no-block $UNIT && echo "已启动。过 20 秒看 tools/pit.sh status" ;;
  stop)
    systemctl --user stop $UNIT 2>/dev/null
    P=$(pid); [ -n "$P" ] && kill "$P"
    sleep 2; running && echo "还在跑，再等等" || echo "已停" ;;
  log) tail -f "$(latest_log)" ;;
  *) sed -n 2,9p "$0" ;;
esac
