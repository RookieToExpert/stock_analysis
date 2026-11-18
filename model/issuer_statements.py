"""Read dated A-share consolidated financial statements from pdftotext -layout output."""
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
import re
import unicodedata


NUMBER = re.compile(r'(?<![\d.,])(?:\(\s*[-+]?\d[\d,]*(?:\.\d+)?\s*\)|[-+]?\d[\d,]*(?:\.\d+)?)(?![\d.,])')
UNITS = {'亿元': 100000000, '百万元': 1000000, '万元': 10000, '千元': 1000, '元': 1}
UNIT_RE = r'(亿元|百万元|万元|千元|元)'
HEADING = re.compile(r'^(?:(?:附表)?[（(]?[\d一二三四五六七八九十]+[)）、.．]\s*)?(?:20\d\d年(?:度|12月31日)?的?)?(合并及母公司|合并及公司|合并|母公司|公司)(资产负债表|利润表|损益表|现金流量表|所有者权益变动表|股东权益变动表)(?:[（(]续[）)])?$')


def normalize(value):
    return unicodedata.normalize('NFKC', value).replace('−', '-').replace('–', '-').replace('﹣', '-')


def compact(value):
    return ''.join(normalize(value).split())


def fiscal_year_evidence(lines, year):
    digits = str.maketrans('零〇○一二三四五六七八九', '000123456789')
    observed = {}
    for i, line in enumerate(lines):
        if line.page > 12:
            break
        key = line.key.translate(digits)
        if re.fullmatch(r'20\d\d年?', key) and i + 1 < len(lines) and lines[i+1].page == line.page:
            key += lines[i+1].key
        if len(key) > 120 or re.search(r'详见|请参|查阅|参见|披露于', key):
            continue
        patterns = (r'(20\d\d)年(?:年?度|年)?报告(?:全文|摘要|正文)?(?:[（(][^()（）]{1,12}[）)])?\d*$',
                    r'AnnualReport(20\d\d)', r'^(20\d\d)[\u4e00-\u9fff]{2,15}年度报告',
                    r'本公司董事.{0,34}对《(20\d\d)年年度报告》',
                    r'(20\d\d)年年度报告已经本公司',
                    r'报告期(?:间)?(?:指|为|[:：])(20\d\d)年(?:1|01)月')
        for pattern in patterns:
            match = re.search(pattern, key, re.I)
            if match:
                observed.setdefault(match[1], []).append(line)
                break
    own = observed.pop(str(year), [])
    if not own or any(len(lines) >= len(own) for lines in observed.values()):
        return []
    return quoted(own[:2])


def decimal_tokens(line):
    numbers = []
    for match in NUMBER.finditer(normalize(line)):
        token = match[0].replace(',', '').replace(' ', '')
        if token.startswith('('):
            token = '-' + token[1:-1]
        numbers.append(Decimal(token))
    return numbers


def decimals_in_columns(line, count=2):
    """Read the monetary columns, including explicit dashes, after any statement note."""
    line = normalize(line).strip()
    amount = r'(?:\(\s*[-+]?\d[\d,]*(?:\.\d+)?\s*\)|[-+]?\d[\d,]*(?:\.\d+)?|[-—/])'
    tail = re.search(r'(?<![\d,.])' + r'\s+'.join(['(' + amount + ')'] * count) + r'\s*$', line)
    if tail:
        return tuple(decimal_tokens(s)[0] if decimal_tokens(s) else None for s in tail.groups())
    cells = re.split(r'\s{2,}|\t+', line)
    values = []
    for cell in cells:
        if NUMBER.fullmatch(cell.strip()):
            values.append(decimal_tokens(cell)[0])
        elif cell.strip() in ('-', '—', '/'):
            values.append(None)
    if len(values) >= count:
        return tuple(values[-count:])
    return None


@dataclass(frozen=True)
class Line:
    page: int
    text: str

    @cached_property
    def key(self):
        return compact(self.text)


def quoted(lines):
    return [[line.page, line.text.strip()] for line in lines if line.text.strip()]


def ratio_agrees(numerator, denominator, reported, rounding=Decimal(0)):
    if reported in (None, '') or not denominator:
        return False
    return abs(numerator - Decimal(reported) * denominator) <= abs(denominator) * Decimal('0.00000051') + rounding


class Statement:
    def __init__(self, lines, year, currency, combined=False):
        self.lines = lines
        self.year = year
        self.currency = currency
        self.combined = combined

    @cached_property
    def heading(self):
        # A split-page heading can include the prior page number and the report running title.
        limit = next((i + 1 for i, l in enumerate(self.lines[:35]) if
                      re.match(r'^(?:[一1][、.])?(?:经营活动产生|流动资产|营业总收入|营业收入|营业总成本)', l.key)), 18)
        return self.lines[:limit]

    @cached_property
    def unit(self):
        text = ''.join(l.key for l in self.heading)
        if re.search(r'(?:币种|单位)[:为]*(?:港币|美元|港元|美金)', text):
            raise ValueError('non-RMB statement')
        match = re.search(r'(?:单位[均皆为以:]*[（(]?(?:人民币)?|人民币)' + UNIT_RE, text)
        if not match:
            raise ValueError('statement unit missing')
        if '人民币' not in text and not self.currency:
            raise ValueError('RMB presentation needs confirmation')
        return Decimal(UNITS[match[1]])

    @cached_property
    def columns(self):
        text = ''.join(l.key for l in self.heading)
        current, previous = str(self.year), str(self.year - 1)
        for l in self.heading:
            k = l.key
            if current in k and previous in k:
                return (0, 1) if k.index(current) < k.index(previous) else (1, 0)
            year_end = re.search(current + r'年12月31日', k)
            year_start = re.search(current + r'年0?1月0?1日', k)
            if year_end and year_start:
                return (0, 1) if year_end.start() < year_start.start() else (1, 0)
        for pattern in (r'本(?:期|年)(?:本期)?(?:度|发生额|金额|数|累计|实际|已审计)*.{0,15}上(?:期|年)',
                        r'(?:期|年)末(?:余额|数|金额)?.{0,15}(?:期|年)初(?:余额|数|金额)?'):
            if re.search(pattern, text):
                return 0, 1
        raise ValueError('current/prior columns missing')

    def row(self, pattern, *, start=0, end=None, skip=()):
        """Find a labelled row, accepting PDF line wrapping around the two numeric columns."""
        head = re.compile(pattern)
        stop = len(self.lines) if end is None else end
        for i in range(start, stop):
            if not head.search(self.lines[i].key) or any(word in self.lines[i].key for word in skip):
                continue
            for j in range(i, min(i + 5, stop)):
                line = self.lines[j]
                if j > i and not re.match(r'^[-—+(/\d]|^[一二三四五六七八九十]+[、.]\d+|^(?:额|净额|净利润|权|益|者|本|量|股东权益|'
                                          r'所有者权益|的净|的现|的股|的权|的合|的余|的利|归属)[^:]{0,20}', line.key):
                    break
                if self.combined:
                    hdr = ''.join(l.key for l in self.heading[1:])
                    group_first = re.search(r'(?:合并|集团)(?:合并|本集团|集团)?.{0,18}(?:母公司|公司)', hdr)
                    cells = decimals_in_columns(line.text, 4) if group_first else None
                    pair = cells[:2] if cells else None
                else:
                    pair = decimals_in_columns(line.text)
                if pair:
                    order = self.columns
                    return (pair[order[0]], pair[order[1]]), self.lines[i:j + 1], i, j
        raise ValueError('row missing: ' + pattern)


class Report:
    def __init__(self, text, code, year):
        self.text = text
        self.code = code
        self.year = year
        self.lines = [Line(i, l) for i, page in enumerate(text.split('\f'), 1) for l in page.splitlines() if l.strip()]
        self.headers = []
        for i, line in enumerate(self.lines):
            if len(line.text.strip()) > 64:
                continue
            match = HEADING.fullmatch(line.key)
            if match:
                self.headers.append((i, *match.groups()))
        cover = [l for l in self.lines if l.page <= 25]
        self.identity = []
        self.foreign_owner = False
        ticker = code[3:]
        for i, line in enumerate(cover):
            codes = re.findall(r'(?:公司代码|股票代码|证券代码|A股代码)[:：]?(\d{6})(?!\d)', line.key)
            if line.page <= 2 and any(s.startswith(('0','3','6')) and s != ticker for s in codes) and ticker not in codes:
                self.foreign_owner = True
            if not re.search(r'(?<!\d)' + ticker + r'(?!\d)', normalize(line.text)):
                continue
            context = cover[max(0,i-3):i+2]
            if ticker in codes or re.search(r'股票代码|股票代号|证券代码|公司代码|Companycode|上海证券交易所|深圳证券交易所|股票上市地|A股代码|A股.*(?:上交所|深交所)', ''.join(l.key for l in context), re.I):
                self.identity = quoted(context)
                break
        fiscal = fiscal_year_evidence(cover, year)
        self.cover_ok = bool(self.identity and fiscal and not self.foreign_owner)
        self.identity += fiscal
        self.currency = self.find_currency()

    def find_currency(self):
        for i, line in enumerate(self.lines):
            if '人民币' not in line.key or len(line.text) > 250:
                continue
            span = self.lines[max(0,i-1):i+1]
            text = ''.join(l.key for l in span)
            if re.search(r'(?:本位币.{0,18}人民币|(?:以|采用)?人民币(?:作为|为|是|作).{0,10}(?:记[账帐]本位币|报表列报货币|报告货币)|以人民币.{0,12}(?:编制|列报)|(?:财务报表|列报货币|记[账帐]本位币).{0,20}人民币|币种[:为]人民币|(?:单位|金额单位)[:为]*人民币元|元[、,/]万元.{0,16}人民币元)', text):
                return quoted(span)
        return []

    def sections(self, kind):
        for n, (i, scope, label) in enumerate(self.headers):
            if not scope.startswith('合并') or label != kind:
                continue
            end = min(i + 380, len(self.lines))
            for j, next_scope, next_kind in self.headers[n + 1:]:
                if next_scope != scope or next_kind != kind:
                    end = min(j, end)
                    break
            yield Statement(self.lines[i:end], self.year, self.currency, combined=scope != '合并')

    def cash(self):
        errors = []
        for stmt in self.sections('现金流量表'):
            try:
                unit = stmt.unit
                ending = next((i for i, l in enumerate(stmt.lines) if re.match(r'^(?:二[、.]|2[、.])?投资活动(?:产生|所用|所得)', l.key)), len(stmt.lines))
                incoming, inc_lines, _, _ = stmt.row(r'^(?:其中:)?(?:经营活动)?现金流入(?:小|合)计?', end=ending)
                outgoing, out_lines, _, last = stmt.row(r'^(?:其中:)?(?:经营活动)?现金流出(?:小|合)计?', end=ending)
                net_vals, net_lines, _, net_end = stmt.row(r'^经营活动(?:产生|使用|所产生|所得|现金|[(/])', start=last + 1, end=ending)
                label = re.sub(r'[^\u4e00-\u9fff]', '', ''.join(l.key for l in stmt.lines[last + 1: min(net_end + 3, ending)]))
                if not re.search(r'净(?:额|流入|流出)|现金流量净[一二三四五六七八九十]{1,5}额', label):
                    raise ValueError('net cash label incomplete')
                if any(v is None for v in (incoming[0], outgoing[0], net_vals[0])):
                    raise ValueError('empty current-period cash figure')
                for inc, out, net in zip(incoming, outgoing, net_vals):
                    if None not in (inc, out, net):
                        # Some issuers round their RMB-thousand or RMB-million totals independently.
                        quantum = Decimal(1).scaleb(min(v.as_tuple().exponent for v in (inc, out, net)))
                        tolerance = quantum if unit > 1 else Decimal('0.01')
                        if abs(inc - abs(out) - net) > tolerance:
                            raise ValueError('printed cash subtotals disagree')
                proof = {'value': str(net_vals[0] * unit), 'unit_multiplier': str(unit),
                         'precision': str(Decimal(1).scaleb(net_vals[0].as_tuple().exponent) * unit),
                         'inflow': str(incoming[0] * unit), 'printed_outflow': str(outgoing[0] * unit),
                         'outflow': str(abs(outgoing[0]) * unit),
                         'page': net_lines[-1].page, 'header': quoted(stmt.heading),
                         'inflow_row': quoted(inc_lines), 'outflow_row': quoted(out_lines),
                         'net_row': quoted(stmt.lines[last + 1:min(net_end + 3, ending)])}
                return proof
            except ValueError as exc:
                errors.append(str(exc))
        raise ValueError('cash: ' + ' / '.join(dict.fromkeys(errors or ['consolidated heading missing'])))

    def annual_cash_table(self):
        """Operating activities in the issuer's annual cash comparison, including both subtotals."""
        for i, line in enumerate(self.lines):
            if line.page > 95:
                break
            if not line.key.startswith('经营活动现金流入小计'):
                continue
            header = self.lines[max(0, i-6):i]
            head = ''.join(l.key for l in header)
            if '母公司' in head or not re.search(str(self.year) + r'年.*?' + str(self.year - 1) + '年.*?同比', head):
                continue
            unit = re.search(r'单位[:为]*(?:人民币)?' + UNIT_RE, head)
            if not unit or not self.currency:
                continue
            region = self.lines[i:i+8]
            end = next((j for j, l in enumerate(region) if l.key.startswith('投资活动')), len(region))
            region = region[:end]
            if not re.search(r'经营活动产生的现金流量净额', re.sub(r'[^\u4e00-\u9fff]', '', ''.join(l.key for l in region))):
                continue
            if len(region) < 3 or not region[1].key.startswith('经营活动现金流出小计'):
                continue
            rows = [decimal_tokens(l.text)[:2] for l in region]
            pairs = [pair for pair in rows if len(pair) == 2]
            if len(pairs) != 3:
                continue
            factor = Decimal(UNITS[unit[1]])
            if any(incoming - abs(outgoing) != net for incoming, outgoing, net in zip(*pairs)):
                continue
            return {'value': str(pairs[2][0] * factor), 'unit_multiplier': str(factor),
                    'precision': str(Decimal(1).scaleb(pairs[2][0].as_tuple().exponent) * factor),
                    'inflow': str(pairs[0][0] * factor), 'outflow': str(abs(pairs[1][0]) * factor),
                    'page': line.page, 'header': quoted(header), 'row': quoted(region)}
        raise ValueError('annual cash comparison with reconciling subtotals missing')

    def consolidated_profit(self):
        errors = []
        for kind in ('利润表', '损益表'):
            for stmt in self.sections(kind):
                try:
                    unit = stmt.unit
                    pair, lines, _, _ = stmt.row(r'^(?:[四五六][、.])?(?:净利润|净亏损|净\(亏损\)|净\(利润\)|净损益|本年(?:度)?(?:净利润|亏损))',
                                                 skip=('归属于', '归属母公司', '调节为', '持续经营', '每股'))
                    if pair[0] is None:
                        raise ValueError('empty net profit')
                    quantum = Decimal(1).scaleb(pair[0].as_tuple().exponent) * unit
                    return {'value': str(pair[0] * unit), 'precision': str(quantum), 'unit_multiplier': str(unit),
                            'header': quoted(stmt.heading), 'row': quoted(lines), 'page': lines[-1].page}
                except ValueError as exc:
                    errors.append(str(exc))
        raise ValueError('profit: ' + ' / '.join(dict.fromkeys(errors or ['consolidated heading missing'])))

    def annual_highlights(self):
        """Read a company's annual comparison table, stopping before its quarterly table."""
        labels = {
            'revenue': r'^(?:营业(?:总)?收入|营业额)',
            'parent_profit': r'^归属于(?:上市公司|母公司)(?:普通股|所有者|股东).*?(?:净|的|扣)',
            'cash': r'^经营活动(?:产生|使用|所产生|现金|[(/]).*?(?:现|净)',
        }
        anchors = r'(?:主要会计数据|主要财务数据|主要财务指标|利润表及现金流量表相关科目变动分析|近三年主要|近3年主要)'
        for i, line in enumerate(self.lines):
            if line.page > 95:
                break
            if len(line.key) > 85 or not re.search(anchors, line.key) or re.search('非经常|差异原因|调整原因', line.key):
                continue
            region = self.lines[i:i + 62]
            first_row = next((j for j, l in enumerate(region[1:], 1) if re.match(labels['revenue'], l.key)), None)
            if first_row is None or first_row > 22:
                continue
            heading = region[:first_row]
            head = ''.join(l.key for l in heading)
            current, prior = str(self.year), str(self.year - 1)
            actual_years = any(current in l.key and prior in l.key and l.key.index(current) < l.key.index(prior) for l in heading)
            if not actual_years and not re.search(r'本(?:期|年)(?:数|金额|发生额|度)?.{0,10}上年同期', head):
                continue
            if '第一季度' in head or '母公司现金流量表' in head or re.search('币种[:为]*(?:港币|美元)', head):
                continue
            explicit = re.search(r'(?:单位[均为以:]*[（(]?(?:人民币)?|人民币)' + UNIT_RE, head)
            facts = {}
            for j in range(first_row, len(region)):
                l = region[j]
                if j > first_row and re.search('第一季度|分季度|^二[、.]|^三[、.]|非经常性损益项目', l.key):
                    break
                for name, pattern in labels.items():
                    if name in facts or not re.match(pattern, l.key):
                        continue
                    if '扣除' in l.key or '非经常' in l.key or '每股' in l.key:
                        continue
                    entry = [l]
                    nums = decimal_tokens(l.text)
                    if len(nums) < 2 and j + 1 < len(region):
                        following = region[j+1]
                        if re.match(r'^(?:[-(（\d]|额|量净额|利润|净额)', following.key):
                            entry.append(following)
                            nums = decimal_tokens(following.text)
                    if len(nums) < 2:
                        continue
                    own = re.search(r'[（(](?:人民币)?' + UNIT_RE + r'[）)]', ''.join(x.key for x in entry))
                    if not (own or explicit):
                        continue
                    factor = Decimal(UNITS[(own or explicit)[1]])
                    facts[name] = {'value': str(nums[0] * factor), 'page': entry[-1].page,
                                   'precision': str(Decimal(1).scaleb(nums[0].as_tuple().exponent) * factor),
                                   'unit_multiplier': str(factor), 'row': quoted(entry)}
            if 'cash' in facts and 'revenue' in facts:
                yield {'header': quoted(heading), **facts}

    def corroborated_highlight_cash(self, raw, printed_profit=None):
        profit, cash = raw.get('profit', {}), raw.get('cash', {})
        if not profit.get('netProfit'):
            raise ValueError('no provider profit anchor')
        net_profit = Decimal(profit['netProfit'])
        output = []
        for table in self.annual_highlights():
            amount = Decimal(table['cash']['value'])
            revenue = Decimal(table['revenue']['value'])
            pr = Decimal(table['revenue']['precision']) / 2
            pc = Decimal(table['cash']['precision']) / 2
            cash_rate = cash.get('CFOToOR') or cash.get('CFOToGr')
            cash_ratio_agrees = ratio_agrees(amount, revenue, cash_rate, pc + pr * abs(Decimal(cash_rate or 0)))
            anchored = ratio_agrees(net_profit, revenue, profit.get('npMargin'), pr * abs(Decimal(profit.get('npMargin') or 0)))
            if printed_profit:
                anchored |= abs(net_profit - Decimal(printed_profit['value'])) <= Decimal(printed_profit['precision']) / 2
            parent = table.get('parent_profit')
            if parent:
                anchored |= ratio_agrees(Decimal(parent['value']), net_profit, raw.get('dupont', {}).get('dupontPnitoni'),
                                         Decimal(parent['precision']) / 2)
            if anchored and (cash_ratio_agrees or printed_profit or (parent and ratio_agrees(Decimal(parent['value']), net_profit, raw.get('dupont', {}).get('dupontPnitoni'), Decimal(parent['precision']) / 2))):
                output.append(table)
        if output:
            best = min(output, key=lambda t: Decimal(t['cash']['precision']))
            if all(abs(Decimal(t['cash']['value']) - Decimal(best['cash']['value'])) <= Decimal(t['cash']['precision']) / 2
                   for t in output):
                return best
        raise ValueError('annual cash comparisons do not match the archived provider ratios')

    def statement_pair(self, kind, pattern, description=None):
        problems = []
        for stmt in self.sections(kind):
            try:
                factor = stmt.unit
                values, row, first, last = stmt.row(pattern)
                if description:
                    label = re.sub(r'[^\u4e00-\u9fff]', '', ''.join(l.key for l in stmt.lines[first:last+3]))
                    if not re.search(description, label):
                        raise ValueError('ambiguous wrapped statement label')
                if values[0] is None:
                    raise ValueError('no current amount')
                return {'value': str(values[0] * factor), 'prior': str(values[1] * factor) if values[1] is not None else None,
                        'page': row[-1].page, 'header': quoted(stmt.heading), 'row': quoted(row), 'unit_multiplier': str(factor)}
            except ValueError as exc:
                problems.append(str(exc))
        raise ValueError(', '.join(dict.fromkeys(problems)) or ('missing: ' + kind))

    def comparison_parent_pair(self, field):
        """Parent-attributable earnings or equity in the statutory annual comparison."""
        term = '净利润' if field == 'parent' else '净资产'
        for i, line in enumerate(self.lines):
            if line.page > 25:
                break
            if not re.match(r'^[*＊]?归属于(?:上市公|母公司)', line.key):
                continue
            group = [line]
            for nxt in self.lines[i+1:i+4]:
                if re.match(r'^(?:[＊*]?归属于|营业|经营活动|总资产|资产总|加权|基本|扣除后|非经常性损益项目)', nxt.key):
                    break
                group.append(nxt)
            label = re.sub(r'[^\u4e00-\u9fff]', '', ''.join(l.key for l in group)).replace('不适用', '')
            if term not in label or '扣除' in label or '每股' in label:
                continue
            before = self.lines[max(0,i-48):i]
            header_index = next((n for n in reversed(range(len(before)))
                                 if re.search(str(self.year) + r'年.{0,15}' + str(self.year-1) + r'年', before[n].key)), None)
            if header_index is None:
                continue
            header = before[header_index:]
            if any(re.search(r'季度|调整前|调整后|母公司资产负债表', l.key) for l in header):
                continue
            # The unit may be printed on the row itself, or above the annual comparison.
            units = [m for l in before + group for m in re.findall(r'单位[:为]*(?:人民币)?' + UNIT_RE, l.key)]
            own_unit = re.search(r'[(](?:人民币)?' + UNIT_RE + r'[)]', ''.join(l.key for l in group))
            if not own_unit and not units:
                continue
            factor = Decimal(UNITS[own_unit[1] if own_unit else units[-1]])
            pair = next((decimal_tokens(l.text) for l in group if len(decimal_tokens(l.text)) >= 2), [])
            if len(pair) < 2:
                continue
            return {'value': str(pair[0]*factor), 'prior':str(pair[1]*factor), 'page':line.page,
                    'unit_multiplier':str(factor), 'header':quoted(header[:1]), 'row':quoted(group)}
        raise ValueError('annual parent comparison missing: ' + field)

    def main_business(self, turnover):
        target = Decimal(turnover)
        lines = []
        for line in self.lines:
            if len(lines) and lines[-1].key in ('主营', '其他') and len(decimal_tokens(line.text)) == 4:
                label = lines.pop()
                line = Line(line.page, label.text.strip() + ' ' + line.text.strip())
            lines.append(line)
        for i, line in enumerate(lines):
            if not re.match(r'^(?:其中:)?主营(?:业(?:务(?:收入)?)?)?[-\d(]', line.key):
                continue
            heads = lines[max(0, i-12):i]
            header = ''.join(l.key for l in heads)
            explicit = bool(re.match(r'^(?:其中:)?主营业务收入', line.key))
            if (not explicit and not re.search(r'收入成本|营业收入.{0,4}营业成本', header)) or not re.search(r'本[期年]|' + str(self.year) + '年', header):
                continue
            others = next((l for l in lines[i+1:i+15] if re.match(r'^其他(?:业务(?:收入)?)?[\d(]', l.key)), None)
            total = next((l for l in lines[i+1:i+16] if re.match(r'^(?:合计|总计)[\d(]', l.key)), None)
            main = decimal_tokens(line.text)
            other = decimal_tokens(others.text) if others else [Decimal(0)]
            if not (main and other):
                continue
            combined = main[0] + other[0]
            if explicit and others and others.key.startswith('其他业务收入'):
                # Older notes show main and ancillary sales on separate rows, without a total.
                total = None
            elif not total or decimal_tokens(total.text)[0] != combined:
                continue
            scales = [scale for scale in UNITS.values() if combined * scale == target]
            if combined == target == 0:
                declared = re.search(r'单位[:为]*(?:人民币)?' + UNIT_RE, header)
                scales = [UNITS[declared[1]]] if declared else []
            if len(scales) == 1:
                return {'value': str(main[0] * scales[0]), 'unit_multiplier': str(scales[0]), 'page': line.page,
                        'header': quoted(heads[-5:]), 'row': quoted([r for r in (line, others, total) if r])}
        raise ValueError('no main-business note matching consolidated sales')

    def share_count(self):
        for i, line in enumerate(self.lines):
            if not re.match(r'^(?:三[、.]|3[、.])?股份总数[\d(]', line.key):
                continue
            header = self.lines[max(0, i-72):i]
            ordered = ''.join(l.key for l in header)
            if not re.search(r'本次变动前.*本次变动后|期初.*期末', ordered):
                continue
            values = decimal_tokens(line.text)
            if (len(values) >= 4 and values[-1] == 100 and values[-2] == values[-2].to_integral_value()
                    and values[-2] > 100 and values[1] == 100 and '单位:股' in ordered):
                return {'value': str(values[-2]), 'page': line.page, 'row': quoted([line]),
                        'header': quoted([l for l in header if re.search(r'单位:股|本次变动前|本次变动后|期初|期末|数量.*比例', l.key)][-7:])}
        # Some older change tables state capital in yuan. Require a separate share-denominated
        # issuer disclosure of the same count, keeping both the balance and the share evidence.
        capital = self.statement_pair('资产负债表', r'^(?:实收资本(?:\(或股本\))?|股本)(?=\d|[-(]|$)')
        closing = Decimal(capital['value'])
        number = r'([\d,]+(?:\.\d+)?)(万|亿)?股'
        for i, line in enumerate(self.lines):
            if not re.search('总股本|股份总数', line.key):
                continue
            span = self.lines[max(0, i-1):i+3]
            text = ''.join(l.key for l in span)
            for match in re.finditer(r'(?:总股本|股份总数)(?:变更为|为|共|合计|计|共计|由)?' + number, text):
                shares = Decimal(match[1].replace(',', '')) * {'万': 10000, '亿': 100000000, None: 1}[match[2]]
                if shares == closing and shares > 0 and shares == shares.to_integral_value():
                    return {'value': str(int(shares)), 'page': line.page, 'row': quoted(span),
                            'header': capital['header'], 'capital_row': capital['row']}
        raise ValueError('no year-end share count in shares')

    def extra_fields(self, fields, printed_profit):
        facts, problems, basis = {}, {}, {}
        want = set(fields)
        patterns = {
            'parent': ('利润表', r'^(?:[0-9(一二)]+[、.)]?)?归属于母公司(?:股东|所有者)的?(?:净|(?=[-\d(])|$)'),
            'equity': ('资产负债表', r'^归属于母公司(?:所有者|股东)(?:权益|的权益|权|(?=[-\d(])|$)'),
            'turnover': ('利润表', r'^(?:其中:|[一1][、.])?营业收入(?!及|和|增长|占|与)'),
            'cost': ('利润表', r'^(?:其中:|减:|[二2][、.])?营业成本(?!及|和|增长|占|与)'),
            'assets': ('资产负债表', r'^资产总计'),
            'liabilities': ('资产负债表', r'^负债合计'),
        }
        def source(name):
            if name not in basis:
                kind, pattern = patterns[name]
                try:
                    description = {'parent':r'归属于母公司(?:股东|所有者)的?净(?:利润|亏损)',
                                   'equity':r'归属于母公司(?:所有者|股东)的?权益'}.get(name)
                    basis[name] = self.statement_pair(kind, pattern, description)
                except ValueError:
                    if name in ('parent', 'equity'):
                        basis[name] = self.comparison_parent_pair(name)
                        return basis[name]
                    if name != 'turnover':
                        raise
                    # An explicitly identified total revenue line is only used when the non-financial income
                    # statement has no distinct operating or non-operating revenue components in total revenue.
                    proof = self.statement_pair(kind, r'^(?:[一1][、.])?营业总收入')
                    # The business note is independently reconciled to this total below.
                    basis[name] = proof
            return basis[name]
        def val(name):
            return Decimal(source(name)['value'])
        def ratio(a,b):
            if not b: raise ValueError('zero denominator')
            return str(a/b)
        for field in sorted(want):
            try:
                if field == 'netProfit':
                    if not printed_profit: raise ValueError('no consolidated net profit')
                    facts[field] = printed_profit['value']
                elif field == 'dupontPnitoni':
                    if not printed_profit: raise ValueError('no consolidated net profit')
                    facts[field] = ratio(val('parent'), Decimal(printed_profit['value']))
                elif field == 'roeAvg':
                    pair = source('equity')
                    if pair['prior'] is None: raise ValueError('missing opening parent equity')
                    average = (Decimal(pair['value']) + Decimal(pair['prior'])) / 2
                    facts[field] = ratio(val('parent'), average)
                    basis['average_parent_equity'] = str(average)
                elif field == 'gpMargin':
                    if any('营业总收入' in line[1] for line in source('turnover')['row']):
                        raise ValueError('gross margin needs operating revenue excluding other components')
                    facts[field] = ratio(val('turnover') - val('cost'), val('turnover'))
                elif field == 'MBRevenue':
                    basis['main_business'] = self.main_business(source('turnover')['value'])
                    facts[field] = basis['main_business']['value']
                elif field == 'totalShare':
                    basis['shares'] = self.share_count()
                    facts[field] = basis['shares']['value']
                elif field == 'liabilityToAsset':
                    facts[field] = ratio(val('liabilities'), val('assets'))
            except ValueError as exc:
                problems[field] = str(exc)
        return facts, basis, problems
