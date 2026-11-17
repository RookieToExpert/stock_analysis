"""仅按已经人工核对的发行人公告纠正已知原始错误，保留修改前记录。"""
import copy
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from total_return import CoverageError


def exclude_verified_adjustments(snapshot, as_of, ledger=None):
    if ledger is None:
        ledger=json.loads(Path(__file__).with_name('verified_adjustment_exclusions.json').read_text())
    date.fromisoformat(as_of)
    changes=[]
    for fix in ledger:
        if fix['code']!=snapshot.get('code'):continue
        available=date.fromisoformat(fix['available_date'])
        if available>date.fromisoformat(as_of):continue
        if date.fromisoformat(fix['date'])>available:
            raise CoverageError('invalid adjustment evidence date')
        if not fix.get('source'):raise CoverageError('adjustment exclusion lacks source')
        rows=[r for r in snapshot.get('adjust',[]) if r.get('dividOperateDate')==fix['date']]
        if not rows:continue
        if len(rows)!=1 or any(rows[0].get(k)!=v for k,v in fix['expected'].items()):
            raise CoverageError('excluded adjustment source changed')
        if any(r.get('dividOperateDate')==fix['date'] for r in snapshot.get('dividend',[])):
            raise CoverageError('excluded adjustment now has corporate action')
        daily=sorted((r for r in snapshot['daily'] if r['date']<=fix['date']),key=lambda r:r['date'])
        try:
            continuous=(len(daily)>=2 and daily[-1]['date']==fix['date']
                        and Decimal(daily[-1]['preclose']).is_finite()
                        and Decimal(daily[-1]['preclose'])>0
                        and Decimal(daily[-1]['preclose'])==Decimal(daily[-2]['close']))
        except (InvalidOperation,TypeError,KeyError) as exc:
            raise CoverageError('invalid adjustment continuity input') from exc
        if not continuous:
            raise CoverageError('excluded adjustment price continuity changed')
        changes.append({'evidence':copy.deepcopy(fix),'original':copy.deepcopy(rows[0])})
        snapshot['adjust'].remove(rows[0])
    return changes


def check_supported_actions(code, start, end, as_of, ledger=None):
    """Known paid rights need a funding model, not a fabricated free-share event."""
    if ledger is None:
        ledger=json.loads(Path(__file__).with_name('unsupported_actions.json').read_text())
    for event in ledger:
        if (event['code']==code and start<event['ex_date']<=end
                and event['available_date']<=as_of):
            raise CoverageError('unsupported '+event['kind']+' '+event['ex_date']+
                                ': '+event['reason']+'; source='+event['source'])


def apply_verified_actions(snapshot, as_of, ledger=None):
    if ledger is None:
        ledger=json.loads(Path(__file__).with_name('verified_actions.json').read_text())
    changes=[]
    for fix in ledger:
        if fix['code']!=snapshot.get('code'):
            continue
        available=date.fromisoformat(fix['available_date']);ex=date.fromisoformat(fix['ex_date'])
        if available>date.fromisoformat(as_of) or ex>date.fromisoformat(as_of):
            continue
        if available>ex or not fix.get('source'):
            raise CoverageError('invalid verified-action evidence')
        for row in snapshot.get('dividend',[]):
            if row.get('dividOperateDate')!=fix['ex_date']:
                continue
            try:
                cash=Decimal(row.get('dividCashPsBeforeTax') or '0')
                shares=sum(Decimal(row.get(k) or '0') for k in ('dividStocksPs','dividReserveToStockPs'))
                allowed={(Decimal(v),Decimal(fix['shares'])) for v in fix.get('expected_cash',[])}
                allowed.update((Decimal(v['cash']),Decimal(v['shares'])) for v in fix.get('expected_positions',[]))
                allowed.add((Decimal(fix['cash']),Decimal(fix['shares'])))
                if (cash,shares) not in allowed:
                    raise CoverageError('verified-action source changed: '+fix['ex_date'])
            except (InvalidOperation,TypeError,KeyError) as exc:
                raise CoverageError('invalid verified-action input') from exc
            references={k:fix[k] for k in ('reference_cash','reference_shares',
                                         'announced_reference_price','announced_previous_close') if k in fix}
            corrected={'dividCashPsBeforeTax':fix['cash'],**references}
            if 'reserve' in fix:
                corrected.update(dividStocksPs=fix.get('stocks','0'),dividReserveToStockPs=fix['reserve'])
            if all(row.get(k)==v for k,v in corrected.items()):
                continue
            changes.append({'evidence':copy.deepcopy(fix),'original':copy.deepcopy(row)})
            row.update(dividCashStock='公告核验公司行动',verified_action_source=fix['source'],**corrected)
    return changes
