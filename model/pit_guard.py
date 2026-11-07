"""Baostock 请求闸门：单进程、限速、每日额度、黑名单即停。不依赖 baostock，可离线测试。

所有请求都从 baostock.util.socketutil.send_msg 发出，包括登录、登出和翻页。
闸门替换这个入口，所以不会漏算。计数在发送前写盘，进程中途被杀只会多算，不会少算。

客户端 send_msg 不设超时，吞掉所有异常后返回 None，翻页时 None 还会被当成数据读完；
对方关闭连接时它的接收循环会一直空转。所以闸门用 Deadline 包住连接，把超时、断开和
无响应都变成 NetworkError，并丢弃这条连接：迟到的响应不能被下一个请求读到。
"""
import fcntl, json, os, socket, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

BLACKLIST = "10001011"
DAILY_LIMIT = 40000
MIN_INTERVAL = 1.0
REQUEST_TIMEOUT = 60.0
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


class NetworkError(Exception):
    """请求超时、连接断开或没有响应。这条连接已被丢弃，要重新登录才能再发请求。"""


class Deadline:
    """包住真实连接：一次请求从发送到收完不超过 timeout 秒，对方关闭连接按失败算。

    抛出的异常会被客户端吞掉，所以原因同时记在 failure，由 Guard.call 读取。
    """
    def __init__(self, raw, timeout, clock=time.monotonic):
        self.raw, self.timeout, self.clock = raw, timeout, clock
        self.deadline, self.failure = 0.0, None

    def fail(self, why):
        self.failure = why
        raise NetworkError(why)

    def send(self, data):
        self.deadline, self.failure = self.clock() + self.timeout, None
        try:
            self.raw.settimeout(self.timeout)
            return self.raw.send(data)
        except OSError as e:
            self.fail(f"发送失败 {e!r}")

    def recv(self, size):
        left = self.deadline - self.clock()
        if left <= 0:
            self.fail(f"{self.timeout:g} 秒内没有收完响应")
        try:
            self.raw.settimeout(left)
            data = self.raw.recv(size)
        except socket.timeout:
            self.fail(f"{self.timeout:g} 秒内没有收完响应")
        except OSError as e:
            self.fail(f"接收失败 {e!r}")
        if not data:
            self.fail("对方关闭了连接")
        return data

    def close(self):
        self.raw.close()


class Guard:
    def __init__(self, state_dir, limit=DAILY_LIMIT, interval=MIN_INTERVAL, now=time.time, sleep=time.sleep, timeout=REQUEST_TIMEOUT):
        self.dir = Path(state_dir)
        self.limit, self.interval, self.now, self.sleep, self.timeout = limit, interval, now, sleep, timeout
        self.context = None
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
        if self.context is not None and getattr(self.context, "default_socket", None) is None:
            raise NetworkError("连接已丢弃，需要重新登录")
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

    def call(self, real, msg):
        raw = self.context.default_socket
        conn = raw if isinstance(raw, Deadline) else Deadline(raw, self.timeout)
        self.context.default_socket = conn
        resp = real(msg)
        if conn.failure or resp is None:
            self.drop()
            raise NetworkError(conn.failure or "没有收到响应")
        return resp

    def drop(self):
        conn, self.context.default_socket = self.context.default_socket, None
        try:
            conn.close()
        except OSError:
            pass

    def install(self, sock):
        real = sock.send_msg
        self.context = sock.context
        socket.setdefaulttimeout(self.timeout)  # 建立连接时也不能无限等
        sock.send_msg = lambda msg: self.send(lambda m: self.call(real, m), msg)
