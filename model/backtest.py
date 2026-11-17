"""交易模拟器：实现 docs/STRATEGY_SPEC.md 的成交和费用规则。

只负责执行，不取数，也不产生策略结论。真实回测需要通过规格里的数据门槛。
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
import copy
from rights import validate as validate_rights

COMMISSION, MIN_COMMISSION = 0.00025, 5.0
TRANSFER, STAMP, SLIPPAGE = 0.00001, 0.0005, 0.001
LOT = 100


def limit_pct(code, day):
    """当日涨跌幅限制。创业板 2020-08-24 起、科创板 20%，其他 10%。"""
    if code.startswith("688"):
        return 0.20
    if code.startswith("30") and day >= date(2020, 8, 24):
        return 0.20
    return 0.10


def at_limit(bar, code, day, up):
    """开盘是否封在涨停或跌停。"""
    p, prev = bar.get("open"), bar.get("prev_close")
    if not p or not prev:
        return False
    limit = round(prev * (1 + limit_pct(code, day) * (1 if up else -1)), 2)
    return p >= limit if up else p <= limit


def fee(amount, sell):
    return max(amount * COMMISSION, MIN_COMMISSION) + amount * TRANSFER + (amount * STAMP if sell else 0)


def dividend_tax_rate(buy_day, ex_day):
    days = (ex_day - buy_day).days
    return 0.20 if days <= 30 else 0.10 if days <= 365 else 0.0


@dataclass
class Lot:
    shares: int
    buy_day: date


@dataclass
class Portfolio:
    cash: float
    lots: dict = field(default_factory=dict)
    log: list = field(default_factory=list)
    rights: dict = field(default_factory=dict)

    def shares(self, code):
        return sum(x.shares for x in self.lots.get(code, []))

    def _record(self, day, code, action, status, shares=0, price=0.0, cost=0.0, cash=0.0):
        self.log.append({"day": day.isoformat(), "code": code, "action": action, "status": status, "shares": shares,
                         "price": price, "cost": round(cost, 2), "cash_change": round(cash, 2)})

    def buy(self, day, code, value, bar):
        if bar is None or bar.get("suspended") or not bar.get("open"):
            return self._record(day, code, "buy", "停牌")
        if at_limit(bar, code, day, True):
            return self._record(day, code, "buy", "涨停未成交")
        price = bar["open"] * (1 + SLIPPAGE)
        n = int(min(value, self.cash) / price / LOT) * LOT
        while n > 0 and n * price + fee(n * price, False) > self.cash:
            n -= LOT
        if n <= 0:
            return self._record(day, code, "buy", "资金不足一手")
        amount = n * price
        cost = fee(amount, False)
        self.cash -= amount + cost
        self.lots.setdefault(code, []).append(Lot(n, day))
        self._record(day, code, "buy", "成交", n, price, cost, -(amount + cost))

    def sell(self, day, code, bar, reason="规则卖出"):
        n = self.shares(code)
        if n == 0:
            return False
        if bar is None or bar.get("suspended") or not bar.get("open"):
            self._record(day, code, "sell", "停牌顺延")
            return False
        if at_limit(bar, code, day, False):
            self._record(day, code, "sell", "跌停顺延")
            return False
        price = bar["open"] * (1 - SLIPPAGE)
        amount = n * price
        cost = fee(amount, True)
        self.cash += amount - cost
        del self.lots[code]
        self._record(day, code, "sell", reason, n, price, cost, amount - cost)
        return True

    def dividend(self, day, code, cash_per_share):
        net = 0.0
        for lot in self.lots.get(code, []):
            net += lot.shares * cash_per_share * (1 - dividend_tax_rate(lot.buy_day, day))
        if net:
            self.cash += net
            self._record(day, code, "dividend", "入账", self.shares(code), cash_per_share, 0, net)

    def split(self, day, code, ratio):
        """送转：ratio=1.2 表示 10 转 2。不足一股的部分舍去。"""
        for lot in self.lots.get(code, []):
            lot.shares = int(lot.shares * ratio)
        self._record(day, code, "split", "股本调整", self.shares(code), ratio)

    def record_rights(self, day, code, event):
        """Freeze entitlement on record date; later purchases create no rights."""
        validate_rights(event)
        if (day.isoformat()!=event['record_date'] or event['offer_available_date']>day.isoformat()
                or code.split('.')[-1]!=event['code'].split('.')[-1]):
            raise ValueError('rights record date/security mismatch')
        if event['id'] in self.rights:raise ValueError('rights entitlement already recorded')
        entitlement=Decimal(self.shares(code))*Decimal(event['offered_shares_per_share'])
        if entitlement!=entitlement.to_integral_value():
            raise ValueError('fractional rights require verified allocation; cannot assume rounding')
        n=int(entitlement)
        self.rights[event['id']]=dict(event=copy.deepcopy(event),code=code,entitlement=n,paid=0,settled=False)

    def subscribe_rights(self, day, event_id, shares=None):
        """Pay from existing cash, at most remaining entitlement; no borrowing."""
        claim=self.rights[event_id];event=claim['event']
        if not event['payment_start']<=day.isoformat()<=event['payment_end'] or claim['settled']:
            raise ValueError('outside rights payment window')
        price=Decimal(event['subscription_price']);left=claim['entitlement']-claim['paid']
        affordable=max(0,int(Decimal(str(self.cash))/price))
        if shares is None:shares=min(left,affordable)
        if isinstance(shares,bool) or not isinstance(shares,int) or not 0<=shares<=min(left,affordable):
            raise ValueError('invalid or unfunded rights subscription')
        cost=float(price*shares)
        self.cash-=cost;claim['paid']+=shares
        self._record(day,claim['code'],'rights_payment','已缴款待上市',shares,float(price),0,-cost)
        return shares

    def settle_rights(self, day, event_id):
        claim=self.rights[event_id];event=claim['event']
        if (day.isoformat()<event['listing_date'] or day.isoformat()<event['listing_available_date']):
            raise ValueError('rights shares not listed')
        if claim['settled']:raise ValueError('rights shares already settled')
        claim['settled']=True
        if claim['paid']:
            self.lots.setdefault(claim['code'],[]).append(Lot(claim['paid'],date.fromisoformat(event['listing_date'])))
        self._record(day,claim['code'],'rights_listing','股份到账',claim['paid'])

    def delist(self, day, code, last_price):
        n = self.shares(code)
        if n:
            amount = n * last_price
            cost = fee(amount, True)
            self.cash += amount - cost
            del self.lots[code]
            self._record(day, code, "delist", "退市按最后价卖出", n, last_price, cost, amount - cost)

    def value(self, closes, day=None):
        pending=[r for r in self.rights.values() if r['paid'] and not r['settled']]
        if pending and day is None:raise ValueError('valuation date required for pending rights')
        required=set(self.lots)|{r['code'] for r in pending if day.isoformat()>=r['event']['ex_date']}
        missing = [c for c in required if c not in closes]
        if missing:
            raise ValueError(f"缺收盘价: {missing}")
        claims=sum(r['paid']*(closes[r['code']] if day.isoformat()>=r['event']['ex_date']
                             else float(r['event']['subscription_price'])) for r in pending)
        return self.cash + sum(self.shares(c) * closes[c] for c in self.lots)+claims


def choose(candidates, held, industries, top=20, single=0.10, group=0.25):
    """按已排序候选补足持仓。返回新增代码，执行行业上限和目标权重。"""
    max_group = max(1, int(top * group))
    used = {}
    for c in held:
        used[industries[c]] = used.get(industries[c], 0) + 1
    out = []
    for c in candidates:
        if len(held) + len(out) >= top:
            break
        if c in held or used.get(industries[c], 0) >= max_group:
            continue
        used[industries[c]] = used.get(industries[c], 0) + 1
        out.append(c)
    return out, min(1 / top, single)


def must_sell(vetoed, total, lost_main_times):
    """规格的三条卖出规则。"""
    return bool(vetoed) or total < 60 or lost_main_times >= 2
