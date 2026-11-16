"""仅按已经人工核对的发行人公告纠正已知原始错误，保留修改前记录。"""
import copy
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from total_return import CoverageError


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
                cash=Decimal(row['dividCashPsBeforeTax'])
                shares=sum(Decimal(row.get(k) or '0') for k in ('dividStocksPs','dividReserveToStockPs'))
                allowed=[Decimal(v) for v in fix['expected_cash']]+[Decimal(fix['cash'])]
                if shares!=Decimal(fix['shares']) or cash not in allowed:
                    raise CoverageError('verified-action source changed: '+fix['ex_date'])
            except (InvalidOperation,TypeError,KeyError) as exc:
                raise CoverageError('invalid verified-action input') from exc
            if cash==Decimal(fix['cash']):
                continue
            changes.append({'evidence':copy.deepcopy(fix),'original':copy.deepcopy(row)})
            row.update(dividCashPsBeforeTax=fix['cash'],dividCashStock='公告核验现金分红',
                       verified_action_source=fix['source'])
    return changes
