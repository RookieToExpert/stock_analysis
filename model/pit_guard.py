"""Baostock 请求闸门：单进程、限速、每日额度、黑名单即停。不依赖 baostock，可离线测试。

所有请求都从 baostock.util.socketutil.send_msg 发出，包括登录、登出和翻页。
闸门替换这个入口，所以不会漏算。计数在发送前写盘，进程中途被杀只会多算，不会少算。
"""
import fcntl, json, os, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BLACKLIST = "10001011"
DAILY_LIMIT = 40000
MIN_INTERVAL = 1.0
HEADER_LENGTH = 21
CN = timezone(timedelta(hours=8))


class Stop(SystemExit):
    """必须结束进程。继承 SystemExit，`except Exception` 拦不住。"""


class Blocked(Stop):
    pass


class QuotaDone(SystemExit):
    """今日额度用完，属于正常结束。"""
    def __init__(self, message):
        print(message, flush=True)
        super().__init__(0)


class Guard:
    def __init__(self, state_dir, limit=DAILY_LIMIT, interval=MIN_INTERVAL, now=time.time, sleep=time.sleep):
        self.dir = Path(state_dir)
        self.limit, self.interval, self.now, self.sleep = limit, interval, now, sleep
        self.state_file = self.dir / "state.json"
        self.block_file = self.dir / "blocked.json"
        self.lock = None
        self.state = None

    def acquire(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        lock = open(self.dir / "lock", "w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock.close()
            raise Stop("已有下载进程在运行，禁止并发")
        self.lock = lock
        self.check_block()
        self.state = self.load()

    def release(self):
        if self.lock:
            self.lock.close()
            self.lock = None

    def load(self):
        if not self.state_file.exists():
            return {"days": {}, "last": 0.0}
        try:
            s = json.loads(self.state_file.read_text())
            s["days"] = {str(k): int(v) for k, v in s["days"].items()}
            s["last"] = float(s["last"])
            return s
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise Stop(f"计数文件损坏，不重置，请人工检查 {self.state_file}: {e!r}")

    def save(self):
        tmp = self.state_file.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self.state, f)
            f.flush()
            os.fsync(f.fileno())
        tmp.rename(self.state_file)

    def today(self):
        return datetime.fromtimestamp(self.now(), CN).date().isoformat()

    def used(self):
        return self.state["days"].get(self.today(), 0)

    def remaining(self):
        return self.limit - self.used()

    def check_block(self):
        if self.block_file.exists():
            raise Blocked(f"黑名单标记存在，不发送请求：{self.block_file}")

    def block(self, message):
        self.block_file.write_text(json.dumps({"at": datetime.fromtimestamp(self.now(), CN).isoformat(), "message": message}, ensure_ascii=False))
        raise Blocked(f"{BLACKLIST} {message}，已停止，不重试")

    def check_response(self, resp):
        if isinstance(resp, str):
            fields = resp[HEADER_LENGTH:].split("\1", 2)
            if fields[0] == BLACKLIST:
                self.block(fields[1] if len(fields) > 1 else "黑名单")

    def send(self, real, msg):
        if self.state is None:
            raise Stop("未取得运行锁，不发送请求")
        self.check_block()
        if self.remaining() <= 0:
            raise QuotaDone(f"今日额度 {self.limit} 已用完")
        wait = self.state["last"] + self.interval - self.now()
        if wait > 0:
            self.sleep(min(wait, self.interval))
        day = self.today()
        self.state["days"][day] = self.state["days"].get(day, 0) + 1
        self.state["last"] = self.now()
        self.save()
        try:
            resp = real(msg)
        finally:
            self.state["last"] = self.now()
            self.save()
        self.check_response(resp)
        return resp

    def install(self, sock):
        real = sock.send_msg
        sock.send_msg = lambda msg: self.send(real, msg)
